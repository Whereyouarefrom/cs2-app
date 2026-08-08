// ============================================
// СПРИНТ 10: МОДУЛЬ "ДРУЗЬЯ"
// ============================================
// Отдельный файл по образцу pass.js: подключается ДО app.js, поэтому
// объявляет только функции/обработчики, а обращение к `state`/`apiGet`/
// `apiPost`/`fmt`/`t` происходит уже в момент вызова (function-declaration
// поднимаются на этап парсинга, а app.js к тому времени загружен).
//
// Взаимодействие с профилем:
//   renderProfileScreen (app.js) -> updateFriendsBadge() — счётчик заявок
//   кнопка "👥 Друзья" -> openFriendsModal()
//   тап по строке друга -> openFriendProfile(telegramId)

const friendsState = {
  list: [],          // принятые друзья
  incoming: [],      // входящие заявки (ждут нашего ответа)
  outgoing: [],      // наши отправленные заявки
  searchResults: [],
  activeTab: "list",
  loading: false,
  // Anti-doubleclick: пока запрос по конкретной заявке/другу летит,
  // его id лежит здесь и кнопки этой строки блокируются. Иначе двойной
  // тап по "Принять" отправлял бы две мутации подряд.
  busyIds: new Set(),
};

// ============================================
// Загрузка данных
// ============================================

// Грузит список друзей + заявки одним параллельным запросом.
// Вызывается при открытии модалки и после каждой мутации.
async function loadFriends() {
  friendsState.loading = true;
  renderFriendsTab();
  try {
    const [listRes, reqRes] = await Promise.all([
      apiGet(`/friends/list?telegram_id=${state.telegramId}`),
      apiGet(`/friends/requests?telegram_id=${state.telegramId}`),
    ]);
    friendsState.list = listRes.friends || [];
    friendsState.incoming = reqRes.incoming || [];
    friendsState.outgoing = reqRes.outgoing || [];
  } catch (e) {
    console.log("[v0] loadFriends error:", e.message);
  } finally {
    friendsState.loading = false;
    renderFriendsTab();
    updateFriendsBadge();
  }
}

// Счётчик входящих заявок — рисуется и на кнопке в профиле, и на вкладке
// "Заявки" внутри модалки. Держим в одной функции, чтобы значения не
// разъезжались между двумя местами.
function updateFriendsBadge() {
  const n = friendsState.incoming.length;
  const badges = [
    document.getElementById("friends-badge"),
    document.getElementById("friends-tab-badge"),
  ];
  badges.forEach(el => {
    if (!el) return;
    el.textContent = n;
    el.style.display = n > 0 ? "inline-flex" : "none";
  });
}

// Подгружает счётчик заявок в фоне, не открывая модалку — нужен, чтобы
// на кнопке "Друзья" в профиле бейдж был виден сразу при заходе на вкладку.
async function refreshFriendsBadgeQuietly() {
  try {
    const reqRes = await apiGet(`/friends/requests?telegram_id=${state.telegramId}`);
    friendsState.incoming = reqRes.incoming || [];
    friendsState.outgoing = reqRes.outgoing || [];
    updateFriendsBadge();
  } catch (e) {
    console.log("[v0] refreshFriendsBadgeQuietly error:", e.message);
  }
}

// ============================================
// Модалка "Друзья"
// ============================================
function openFriendsModal() {
  document.getElementById("friends-modal").classList.add("active");
  switchFriendsTab(friendsState.activeTab);
  loadFriends();
}

function closeFriendsModal() {
  document.getElementById("friends-modal").classList.remove("active");
}

function switchFriendsTab(tab) {
  friendsState.activeTab = tab;
  document.querySelectorAll(".friends-tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.ftab === tab);
  });
  ["list", "requests", "search"].forEach(name => {
    const el = document.getElementById(`friends-tab-${name}`);
    if (el) el.style.display = name === tab ? "" : "none";
  });
  renderFriendsTab();
}

// ============================================
// Рендер
// ============================================
function renderFriendsTab() {
  if (friendsState.activeTab === "list") renderFriendsList();
  else if (friendsState.activeTab === "requests") renderFriendRequests();
  // Вкладка поиска рендерится только по нажатию "Найти" — сама себя не
  // перерисовывает при загрузке списка друзей, чтобы не терять результаты.
}

function renderFriendsList() {
  const box = document.getElementById("friends-list");
  if (!box) return;

  if (friendsState.loading) {
    box.innerHTML = `<div class="empty-state">${t("friends_loading")}</div>`;
    return;
  }
  if (!friendsState.list.length) {
    box.innerHTML = `<div class="empty-state">${t("friends_empty")}</div>`;
    return;
  }

  box.innerHTML = friendsState.list.map(f => friendRowHtml(f, "friend")).join("");
}

function renderFriendRequests() {
  const inBox = document.getElementById("friends-incoming-list");
  const outBox = document.getElementById("friends-outgoing-list");
  if (!inBox || !outBox) return;

  inBox.innerHTML = friendsState.incoming.length
    ? friendsState.incoming.map(f => friendRowHtml(f, "incoming")).join("")
    : `<div class="empty-state">${t("friends_no_incoming")}</div>`;

  outBox.innerHTML = friendsState.outgoing.length
    ? friendsState.outgoing.map(f => friendRowHtml(f, "outgoing")).join("")
    : `<div class="empty-state">${t("friends_no_outgoing")}</div>`;
}

function renderFriendSearchResults() {
  const box = document.getElementById("friends-search-results");
  if (!box) return;

  if (!friendsState.searchResults.length) {
    box.innerHTML = `<div class="empty-state">${t("friends_not_found")}</div>`;
    return;
  }
  box.innerHTML = friendsState.searchResults.map(u => friendRowHtml(u, "search")).join("");
}

// Одна строка пользователя. `mode` определяет только набор кнопок справа —
// аватар/имя/подпись во всех режимах одинаковые, поэтому шаблон общий.
function friendRowHtml(u, mode) {
  const tid = u.telegram_id;
  const busy = friendsState.busyIds.has(tid) ? "disabled" : "";
  const avatar = u.photo_url
    ? `<img class="friend-row-avatar" src="${escapeAttr(u.photo_url)}" alt="">`
    : `<div class="friend-row-avatar">🎮</div>`;

  // Подпись под именем: у друга — уровень и титул, у заявки — username.
  const subParts = [];
  if (u.level) subParts.push(`${t("friends_level_short")} ${u.level}`);
  if (u.title && u.title.name) subParts.push(u.title.name);
  if (!subParts.length && u.username) subParts.push(`@${u.username}`);
  const sub = subParts.join(" · ");

  let actions = "";
  if (mode === "friend") {
    actions = `<button class="friend-mini-btn danger" data-friend-remove="${tid}" ${busy}>${t("friends_remove")}</button>`;
  } else if (mode === "incoming") {
    actions = `
      <button class="friend-mini-btn accept" data-friend-accept="${tid}" ${busy}>${t("friends_accept")}</button>
      <button class="friend-mini-btn danger" data-friend-decline="${tid}" ${busy}>${t("friends_decline")}</button>`;
  } else if (mode === "outgoing") {
    actions = `<button class="friend-mini-btn" data-friend-cancel="${tid}" ${busy}>${t("friends_cancel")}</button>`;
  } else if (mode === "search") {
    // Кнопка зависит от уже существующей связи — статус приходит с бэкенда
    // (relation), чтобы не отправлять заведомо отклоняемые заявки.
    if (u.relation === "self") actions = `<span class="friend-row-sub">${t("friends_you")}</span>`;
    else if (u.relation === "friend") actions = `<span class="friend-row-sub">✓ ${t("friends_already")}</span>`;
    else if (u.relation === "outgoing") actions = `<span class="friend-row-sub">${t("friends_pending")}</span>`;
    else if (u.relation === "incoming")
      actions = `<button class="friend-mini-btn accept" data-friend-accept="${tid}" ${busy}>${t("friends_accept")}</button>`;
    else actions = `<button class="friend-mini-btn accept" data-friend-add="${tid}" ${busy}>+ ${t("friends_add")}</button>`;
  }

  return `
    <div class="friend-row">
      ${avatar}
      <div class="friend-row-info" data-friend-open="${tid}">
        <div class="friend-row-name">${escapeHtmlText(u.display_name || u.first_name || "Игрок")}</div>
        <div class="friend-row-sub">${escapeHtmlText(sub)}</div>
      </div>
      <div class="friend-row-actions">${actions}</div>
    </div>`;
}

// ============================================
// Поиск
// ============================================
async function doFriendSearch() {
  const input = document.getElementById("friends-search-input");
  const q = (input?.value || "").trim();
  if (!q) return;

  const box = document.getElementById("friends-search-results");
  box.innerHTML = `<div class="empty-state">${t("friends_loading")}</div>`;
  try {
    // Эндпоинт /api/friends/search — GET с query-параметрами (telegram_id, q),
    // а не POST с телом: раньше здесь был apiPost({query: q}), из-за чего
    // метод и имя параметра не совпадали с бэкендом и запрос всегда падал.
    const params = new URLSearchParams({ telegram_id: state.telegramId, q });
    const res = await apiGet(`/friends/search?${params.toString()}`);
    friendsState.searchResults = res.results || [];
    renderFriendSearchResults();
  } catch (e) {
    box.innerHTML = `<div class="empty-state">${escapeHtmlText(e.message)}</div>`;
  }
}

// ============================================
// Мутации (заявки / удаление)
// ============================================
// Все четыре действия отличаются только эндпоинтом и текстом успеха,
// поэтому идут через одну обёртку с общей блокировкой кнопок и
// перезагрузкой списков.
async function friendAction(path, targetId, successKey) {
  if (friendsState.busyIds.has(targetId)) return;
  friendsState.busyIds.add(targetId);
  renderFriendsTab();
  if (friendsState.activeTab === "search") renderFriendSearchResults();

  try {
    await apiPost(path, { telegram_id: state.telegramId, target_telegram_id: targetId });
    if (successKey) tg?.showAlert?.(t(successKey));
    // Обновляем поисковую выдачу тоже: после отправки заявки кнопка "+"
    // в результатах должна смениться на "заявка отправлена".
    friendsState.searchResults = friendsState.searchResults.map(u =>
      u.telegram_id === targetId ? { ...u, relation: relationAfterAction(path, u.relation) } : u
    );
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    friendsState.busyIds.delete(targetId);
    await loadFriends();
    if (friendsState.activeTab === "search") renderFriendSearchResults();
  }
}

// Локально предсказывает новое состояние связи для уже отрисованной
// поисковой выдачи — чтобы не гонять повторный поиск после каждого действия.
function relationAfterAction(path, prev) {
  if (path.endsWith("/request")) return "outgoing";
  if (path.endsWith("/accept")) return "friend";
  if (path.endsWith("/remove")) return "none";
  if (path.endsWith("/decline")) return "none";
  return prev;
}

// ============================================
// Публичная карточка профиля друга
// ============================================
async function openFriendProfile(targetId) {
  const modal = document.getElementById("friend-profile-modal");
  modal.classList.add("active");

  // Плейсхолдер, пока летит запрос
  document.getElementById("friend-prof-name").textContent = "…";
  document.getElementById("friend-prof-stats").innerHTML = "";
  document.getElementById("friend-prof-showcase").innerHTML = "";
  document.getElementById("friend-prof-actions").innerHTML = "";

  try {
    const p = await apiGet(`/friends/profile?telegram_id=${state.telegramId}&target_telegram_id=${targetId}`);
    renderFriendProfile(p);
  } catch (e) {
    document.getElementById("friend-prof-name").textContent = t("friends_profile_error");
    document.getElementById("friend-prof-stats").innerHTML =
      `<div class="empty-state">${escapeHtmlText(e.message)}</div>`;
  }
}

function renderFriendProfile(p) {
  // Поля приходят из routers/friends.py:_user_card() + public_profile() —
  // display_name/title/frame/relation/showcase[] тут НЕТ, есть
  // first_name/username, title_info/frame_info, relation_state,
  // showcase.items, is_self. Мапим аккуратно, а не по воображаемой схеме.
  document.getElementById("friend-prof-name").textContent = p.first_name || p.username || "Игрок";
  document.getElementById("friend-prof-username").textContent = p.username ? `@${p.username}` : "";
  document.getElementById("friend-prof-level").textContent = p.level || 1;

  // Аватар: img если есть фото, иначе эмодзи-заглушка
  const img = document.getElementById("friend-prof-avatar-img");
  const ph = document.getElementById("friend-prof-avatar");
  if (p.photo_url) {
    img.src = p.photo_url; img.style.display = ""; ph.style.display = "none";
  } else {
    img.style.display = "none"; ph.style.display = "";
  }

  // Титул и рамка — та же логика оформления, что и в своём профиле
  applyTitlePill(document.getElementById("friend-prof-title"), p.title_info);
  applyAvatarFrame(document.getElementById("friend-prof-avatar-wrap"), p.frame_info);

  const rank = p.rank || {};
  const rankEl = document.getElementById("friend-prof-rank");
  const rankName = rank.name ? rankLocalizedName(rank, "name") : "";
  rankEl.textContent = rankName ? `${rank.icon || ""} ${rankName}`.trim() : "";

  // Публичная статистика (без балансов — их бэкенд не отдаёт)
  const st = p.stats || {};
  document.getElementById("friend-prof-stats").innerHTML = [
    [t("stat_cases"), fmtNumber2(st.total_cases_opened)],
    [t("stat_inv_value"), fmt(st.inventory_total_value || 0)],
    [t("friends_stat_items"), fmtNumber2(st.inventory_count)],
    [t("friends_stat_knives"), fmtNumber2(st.knife_drops_count)],
  ].map(([label, value]) => `
    <div class="friend-prof-stat">
      <div class="friend-prof-stat-label">${escapeHtmlText(label)}</div>
      <div class="friend-prof-stat-value">${value}</div>
    </div>`).join("");

  // Витрина друга — только занятые слоты, пустые/закрытые не показываем:
  // чужие нереализованные слоты игроку не интересны.
  const showcaseItems = (p.showcase && p.showcase.items) || [];
  document.getElementById("friend-prof-showcase").innerHTML = showcaseItems.length
    ? showcaseItems.map(showcaseSlotHtml).join("")
    : `<div class="empty-state">${t("showcase_empty_friend")}</div>`;

  // Действие зависит от связи: друга можно удалить, незнакомцу — отправить
  // заявку. relation_state: none|friends|request_sent|request_incoming.
  const actions = document.getElementById("friend-prof-actions");
  if (p.is_self) {
    actions.innerHTML = "";
  } else if (p.relation_state === "friends") {
    actions.innerHTML = `<button class="btn-secondary full" data-friend-remove="${p.telegram_id}">${t("friends_remove")}</button>`;
  } else if (p.relation_state === "request_incoming") {
    actions.innerHTML = `<button class="btn-primary full" data-friend-accept="${p.telegram_id}">${t("friends_accept")}</button>`;
  } else if (p.relation_state === "request_sent") {
    actions.innerHTML = `<div class="friends-search-hint">${t("friends_pending")}</div>`;
  } else {
    actions.innerHTML = `<button class="btn-primary full" data-friend-add="${p.telegram_id}">+ ${t("friends_add")}</button>`;
  }
}

// ============================================
// Обработчики
// ============================================
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("friends-open-btn")?.addEventListener("click", openFriendsModal);
  document.getElementById("friends-close-btn")?.addEventListener("click", closeFriendsModal);
  document.getElementById("friend-profile-close-btn")?.addEventListener("click", () => {
    document.getElementById("friend-profile-modal").classList.remove("active");
  });

  document.querySelectorAll(".friends-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => switchFriendsTab(btn.dataset.ftab));
  });

  document.getElementById("friends-search-btn")?.addEventListener("click", doFriendSearch);
  document.getElementById("friends-search-input")?.addEventListener("keydown", (e) => {
    // isComposing / keyCode 229 — не отправляем поиск, пока IME (китайский,
    // японский, корейский ввод) подтверждает набранный текст клавишей Enter.
    if (e.key === "Enter" && !e.nativeEvent?.isComposing && !e.isComposing && e.keyCode !== 229) {
      doFriendSearch();
    }
  });

  // Единый делегированный обработчик на весь документ: строки друзей
  // перерисовываются после каждой мутации, поэтому навешивать слушатели на
  // сами кнопки бессмысленно — они тут же уничтожаются вместе с innerHTML.
  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-friend-add]");
    if (add) return void friendAction("/friends/request", +add.dataset.friendAdd, "friends_request_sent");

    const acc = e.target.closest("[data-friend-accept]");
    if (acc) return void friendAction("/friends/accept", +acc.dataset.friendAccept, "friends_accepted");

    const dec = e.target.closest("[data-friend-decline]");
    if (dec) return void friendAction("/friends/decline", +dec.dataset.friendDecline, null);

    const cancel = e.target.closest("[data-friend-cancel]");
    if (cancel) return void friendAction("/friends/remove", +cancel.dataset.friendCancel, null);

    const rem = e.target.closest("[data-friend-remove]");
    if (rem) {
      // Удаление друга необратимо, поэтому спрашиваем подтверждение.
      // Telegram-нативный confirm, с фолбэком на браузерный вне Telegram.
      const id = +rem.dataset.friendRemove;
      const run = () => friendAction("/friends/remove", id, null);
      if (tg?.showConfirm) tg.showConfirm(t("friends_remove_confirm"), ok => { if (ok) run(); });
      else if (confirm(t("friends_remove_confirm"))) run();
      return;
    }

    const open = e.target.closest("[data-friend-open]");
    if (open) openFriendProfile(+open.dataset.friendOpen);
  });
});
