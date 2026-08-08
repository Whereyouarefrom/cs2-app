// ============================================
// СПРИНТ 8: Battle Pass — фронтенд
// ============================================
// Подключается ДО app.js (см. index.html) — здесь только ОБЪЯВЛЯЮТСЯ
// функции/обработчики, а обращение к `state`/`apiGet`/`apiPost`/`fmt`
// (объявлены в app.js) происходит только ВНУТРИ них, то есть уже ПОСЛЕ
// того, как app.js полностью выполнится и они станут доступны — порядок
// объявления файлов не имеет значения, важен только порядок ВЫЗОВА.

const passState = {
  status: null,        // последний ответ GET /api/pass/status
  tasks: null,         // последний ответ GET /api/pass/daily-tasks
  activeTab: "tree",
  finalChestLocked: { free: false, vip: false }, // одна карточка уже выбрана -> остальные 2 блокируются
  // ПРАВКИ В ТЗ №11, п.1: таймеры окончания сезона и обновления заданий.
  seasonEndMs: null,      // из status.season_end (ISO), мс с эпохи
  tasksNextResetMs: null, // из daily-tasks.next_reset (ISO), мс с эпохи
  timerId: null,          // id setInterval общего 1-секундного тика
  // ПРАВКИ В ТЗ №12, п.4: пока открыта вкладка "Задания", опрашиваем
  // бэкенд, чтобы поймать автозачёт XP, случившийся где-то ещё в
  // приложении (например, игрок открыл кейс на вкладке "Кейсы", не
  // закрывая модалку Pass) — см. startPassTasksPolling/stopPassTasksPolling.
  tasksPollId: null,
};

const PASS_RARITY_COLOR = {
  Consumer: "#b0c3d9", Industrial: "#5e98d9", "Mil-Spec": "#4b69ff", Restricted: "#8847ff",
  Classified: "#d32ce6", Covert: "#eb4b4b", Knife: "#ffd700", Gloves: "#e4ae39",
};

function passRewardIcon(reward) {
  switch (reward.type) {
    case "crystals": return "💎";
    case "case": return "📦";
    case "custom_case": return "🎁";
    case "vip_time": return "⭐";
    case "frame": return "🖼️";
    case "nick_color": return "🎨";
    // ПРАВКИ В ТЗ №11, п.2: превью финального 50-го уровня в общей сетке.
    case "final_chest": return "🏆";
    default: return "🎁";
  }
}

function passRewardLabel(reward) {
  if (reward.type === "crystals") return `${(reward.amount || 0).toLocaleString("ru-RU")} 💎`;
  if (reward.type === "case") return reward.label;
  if (reward.type === "custom_case") return reward.label;
  if (reward.type === "vip_time") return reward.label;
  if (reward.type === "frame") return `Рамка «${reward.label}»`;
  if (reward.type === "nick_color") return `Цвет ника: ${reward.label}`;
  if (reward.type === "final_chest") return reward.label;
  return reward.label || "Награда";
}

// ============================================
// ПРАВКИ В ТЗ №11, п.1: таймеры обратного отсчёта
// ============================================
// Один общий 1-секундный тик обновляет оба таймера (конец сезона и
// обновление заданий) — обе точки времени приходят готовыми с бэкенда
// (season_end / next_reset, оба ISO с явным UTC-смещением), фронт только
// вычитает Date.now() и форматирует остаток.
function formatPassCountdown(msLeft) {
  if (msLeft <= 0) return "00:00:00";
  const totalSec = Math.floor(msLeft / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return days > 0
    ? `${days}д ${pad(hours)}:${pad(mins)}:${pad(secs)}`
    : `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
}

function tickPassTimers() {
  const seasonEl = document.getElementById("pass-season-timer");
  if (seasonEl && passState.seasonEndMs) {
    seasonEl.textContent = `⏳ ${formatPassCountdown(passState.seasonEndMs - Date.now())}`;
  }
  const tasksEl = document.getElementById("pass-tasks-timer");
  if (tasksEl && passState.tasksNextResetMs) {
    tasksEl.textContent = `🔄 Задания обновятся через: ${formatPassCountdown(passState.tasksNextResetMs - Date.now())}`;
  }
}

function startPassTimers() {
  stopPassTimers();
  tickPassTimers();
  passState.timerId = setInterval(tickPassTimers, 1000);
}

function stopPassTimers() {
  if (passState.timerId) {
    clearInterval(passState.timerId);
    passState.timerId = null;
  }
}

// ============================================
// Загрузка статуса
// ============================================
async function loadPassStatus() {
  try {
    passState.status = await apiGet(`/pass/status?telegram_id=${state.telegramId}`);
    renderPassWidget();
    renderPassCosmetics();
    if (document.getElementById("pass-modal").classList.contains("active")) {
      renderPassHeader();
      renderPassTree();
      renderFinalChest();
    }
  } catch (e) {
    console.error("Ошибка загрузки Battle Pass:", e);
  }
}

async function loadPassDailyTasks() {
  try {
    // ПРАВКИ В ТЗ №12, п.4: запоминаем предыдущий снимок заданий, чтобы
    // после обновления заметить, что какое-то задание стало claimed=true
    // САМО (бэкенд зачёл его автоматически — см. sync_daily_tasks /
    // _auto_claim_completed_tasks), и показать это анимацией, а не молча.
    const prevTasks = passState.tasks ? passState.tasks.tasks : null;
    passState.tasks = await apiGet(`/pass/daily-tasks?telegram_id=${state.telegramId}`);
    if (passState.tasks.next_reset) {
      passState.tasksNextResetMs = new Date(passState.tasks.next_reset).getTime();
      tickPassTimers();
    }
    renderPassTasks();

    const justAutoClaimed = prevTasks && passState.tasks.tasks.some(t => {
      const prev = prevTasks.find(p => p.key === t.key);
      return t.claimed && (!prev || !prev.claimed);
    });
    if (justAutoClaimed) {
      // Задание зачлось само — подтягиваем актуальные уровень/XP пропуска
      // (шапка модалки + виджет на главной) и коротко подсвечиваем шкалу.
      await loadPassStatus();
      animatePassHeaderBar();
    }
  } catch (e) {
    console.error("Ошибка загрузки заданий Battle Pass:", e);
  }
}

// ПРАВКИ В ТЗ №12, п.4: короткая вспышка на шкале уровня БП, когда XP
// начислился автоматически (без клика игрока) — чтобы прогресс не
// "тихо" прыгнул, а было заметно, что что-то только что зачлось.
function animatePassHeaderBar() {
  const fill = document.getElementById("pass-header-bar-fill");
  if (!fill) return;
  fill.classList.remove("pass-bar-pulse");
  // reflow, чтобы повторный запуск класса перезапустил CSS-анимацию
  void fill.offsetWidth;
  fill.classList.add("pass-bar-pulse");
  setTimeout(() => fill.classList.remove("pass-bar-pulse"), 900);
}

// ============================================
// Рендер: виджет на главной
// ============================================
function renderPassWidget() {
  const s = passState.status;
  if (!s) return;
  const pct = s.xp_needed > 0 ? Math.min(100, Math.round((s.xp / s.xp_needed) * 100)) : 100;

  document.getElementById("pass-widget-level").textContent = `Уровень ${s.level} / ${s.max_level}`;
  document.getElementById("pass-widget-bar-fill").style.width = `${pct}%`;
  document.getElementById("pass-widget-xp").textContent =
    s.level >= s.max_level ? "Пройден полностью!" : `${s.xp} / ${s.xp_needed} XP`;
  document.getElementById("pass-widget-vip-chip").style.display = s.is_vip_pass ? "inline-block" : "none";
}

function renderPassHeader() {
  const s = passState.status;
  if (!s) return;
  const pct = s.xp_needed > 0 ? Math.min(100, Math.round((s.xp / s.xp_needed) * 100)) : 100;

  document.getElementById("pass-header-level").textContent = `Уровень ${s.level} / ${s.max_level}`;
  document.getElementById("pass-header-bar-fill").style.width = `${pct}%`;
  document.getElementById("pass-header-xp").textContent =
    s.level >= s.max_level ? "Пройден полностью!" : `${s.xp} / ${s.xp_needed} XP`;
  document.getElementById("pass-header-vip-chip").style.display = s.is_vip_pass ? "inline-block" : "none";

  // ПРАВКИ В ТЗ №11, п.1: название сезона + таймер до его окончания.
  const seasonNameEl = document.getElementById("pass-season-name");
  if (seasonNameEl && s.season_name) seasonNameEl.textContent = s.season_name;
  if (s.season_end) {
    passState.seasonEndMs = new Date(s.season_end).getTime();
    tickPassTimers();
  }

  const buyBtn = document.getElementById("pass-buy-vip-btn");
  buyBtn.style.display = s.is_vip_pass ? "none" : "inline-block";
  // ПРАВКИ В ТЗ №7: графический значок монеты вместо эмодзи 💰 — кнопки
  // используют innerHTML, а не textContent, чтобы вставить <img>.
  buyBtn.innerHTML = `🌟 Купить VIP Pass — ${s.vip_pass_price_gold} ${goldIconHTML("inline")}`;
  // ПРАВКИ В ТЗ №12, п.3: кнопка докупки уровня больше не живёт в шапке —
  // она рендерится renderPassTree() прямо на карточке следующего уровня.
}

// ============================================
// ПРАВКИ В ТЗ №12, п.3: кнопка "Купить следующий уровень"
// ============================================
// Рендерится ТОЛЬКО на карточке того уровня, который игрок должен
// получить следующим (row.level === nextBuyLevel, т.е. s.level + 1) —
// по мере прокачки (клеймом наград, докупкой Золотом или Level Skip)
// пропадает с текущей карточки и на следующем renderPassTree() (после
// loadPassStatus()) появляется на следующей, "спускаясь" вниз по сетке
// сама собой — без какого-либо отдельного состояния на фронте.
function passBuyLevelButtonHTML(rowLevel, nextBuyLevel, s) {
  if (rowLevel !== nextBuyLevel) return "";
  return `
    <button class="pass-buy-level-btn" title="Купить следующий уровень">
      ⏩ Купить уровень ${rowLevel} — ${s.level_skip_price_gold} ${goldIconHTML("inline")}
    </button>`;
}

// ============================================
// Рендер: дерево наград (уровни 1-49)
// ============================================
function renderPassTree() {
  const s = passState.status;
  const list = document.getElementById("pass-tree-list");
  if (!s) { list.innerHTML = ""; return; }

  // ПРАВКИ В ТЗ №12, п.3: следующий уровень, который можно докупить за
  // Золото ("Купить следующий уровень") — привязан к текущему прогрессу,
  // а не к фиксированному месту в шапке. Если пропуск уже пройден
  // полностью (level >= max_level), докупать нечего — кнопки не будет
  // нигде в сетке (см. также pass_skip_level на бэкенде, тот же лимит).
  const nextBuyLevel = s.level < s.max_level ? s.level + 1 : null;

  list.innerHTML = s.tree.map(row => {
    const freeReward = row.free_rewards[0];
    const vipReward = row.vip_rewards[0];
    const freeExtra = row.free_rewards.length > 1 ? ` +${row.free_rewards.length - 1}` : "";
    const vipExtra = row.vip_rewards.length > 1 ? ` +${row.vip_rewards.length - 1}` : "";
    // ПРАВКИ В ТЗ №11, п.2: подсветка/glow VIP-наград и редких предметов
    // на "вехах" — 10/20/30/40 уровнях; 50-й — отдельный, ещё более
    // заметный стиль (см. ветку row.is_final ниже).
    const isMilestone = row.level % 10 === 0;

    const rowClasses = ["pass-row"];
    if (row.unlocked) rowClasses.push("unlocked");
    if (isMilestone) rowClasses.push("pass-row-milestone");

    if (row.is_final) {
      // 50-й уровень — не обычный клейм по /pass/claim (бэкенд его для
      // этого уровня и так отклоняет), а витрина уже существующего
      // интерактивного сундука (scratch-card) ниже: клик скроллит к нему.
      rowClasses.push("pass-row-final");
      const freeCellClass = [
        "pass-cell", "final",
        row.free_claimed ? "claimed" : (row.unlocked ? "final-ready" : "locked"),
      ].join(" ");
      const vipCellClass = [
        "pass-cell", "vip", "final",
        row.vip_claimed ? "claimed" : ((row.unlocked && s.is_vip_pass) ? "final-ready" : "locked"),
      ].join(" ");
      return `
        <div class="pass-row-block${row.level === nextBuyLevel ? " pass-row-buy-target" : ""}">
        <div class="${rowClasses.join(" ")}">
          <div class="pass-row-level">${row.level}</div>
          <div class="${freeCellClass}" data-track="free">
            <span class="pass-cell-icon">${passRewardIcon(freeReward)}</span>
            <span class="pass-cell-label">${passRewardLabel(freeReward)}</span>
            ${row.free_claimed ? '<span class="pass-cell-check">✓</span>' : ""}
          </div>
          <div class="${vipCellClass}" data-track="vip">
            <span class="pass-cell-icon">${passRewardIcon(vipReward)}</span>
            <span class="pass-cell-label">${passRewardLabel(vipReward)}</span>
            ${row.vip_claimed ? '<span class="pass-cell-check">✓</span>' : ""}
          </div>
        </div>
        ${passBuyLevelButtonHTML(row.level, nextBuyLevel, s)}
        </div>`;
    }

    const freeCellClass = [
      "pass-cell",
      isMilestone ? "pass-cell-milestone" : "",
      row.free_claimed ? "claimed" : (row.unlocked ? "claimable" : "locked"),
    ].filter(Boolean).join(" ");
    const vipCellClass = [
      "pass-cell", "vip",
      isMilestone ? "pass-cell-milestone" : "",
      row.vip_claimed ? "claimed" : ((row.unlocked && s.is_vip_pass) ? "claimable" : "locked"),
    ].filter(Boolean).join(" ");

    return `
      <div class="pass-row-block${row.level === nextBuyLevel ? " pass-row-buy-target" : ""}">
      <div class="${rowClasses.join(" ")}">
        <div class="pass-row-level">${row.level}</div>
        <div class="${freeCellClass}" data-level="${row.level}" data-track="free">
          <span class="pass-cell-icon">${passRewardIcon(freeReward)}</span>
          <span class="pass-cell-label">${passRewardLabel(freeReward)}${freeExtra}</span>
          ${row.free_claimed ? '<span class="pass-cell-check">✓</span>' : ""}
        </div>
        <div class="${vipCellClass}" data-level="${row.level}" data-track="vip">
          <span class="pass-cell-icon">${passRewardIcon(vipReward)}</span>
          <span class="pass-cell-label">${passRewardLabel(vipReward)}${vipExtra}</span>
          ${row.vip_claimed ? '<span class="pass-cell-check">✓</span>' : ""}
        </div>
      </div>
      ${passBuyLevelButtonHTML(row.level, nextBuyLevel, s)}
      </div>`;
  }).join("");

  list.querySelectorAll(".pass-cell.claimable").forEach(cell => {
    cell.addEventListener("click", () => {
      claimPassLevel(parseInt(cell.dataset.level, 10), cell.dataset.track);
    });
  });

  // ПРАВКИ В ТЗ №12, п.3: кнопка докупки уровня привязана к текущему
  // прогрессу — рендерится заново на каждый renderPassTree() ровно на
  // одной карточке (следующий недостигнутый уровень), поэтому обработчик
  // достаточно навесить один раз после вставки разметки.
  const buyLevelBtn = list.querySelector(".pass-buy-level-btn");
  if (buyLevelBtn) buyLevelBtn.addEventListener("click", skipPassLevel);

  // Готовая (открытая, но ещё не забранная) финальная карточка 50-го
  // уровня — клик скроллит к интерактивному сундуку (.pass-final-chest),
  // который рендерится отдельным блоком выше сетки (см. renderFinalChest).
  list.querySelectorAll(".pass-cell.final-ready").forEach(cell => {
    cell.addEventListener("click", () => {
      const chestBox = document.getElementById("pass-final-chest");
      if (chestBox) chestBox.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

// ============================================
// Клейм награды уровня 1-49
// ============================================
async function claimPassLevel(level, track) {
  try {
    const res = await apiPost("/pass/claim", { telegram_id: state.telegramId, level, track });
    showPassResult(res.rewards);
    if (res.new_balance !== undefined) {
      state.balance = res.new_balance;
      refreshCurrencyDisplay();
    }
    if (res.gold_balance !== undefined) {
      state.goldBalance = res.gold_balance;
      document.getElementById("gold-value").textContent = fmtNumber(res.gold_balance);
    }
    await loadPassStatus();
    await loadInventory();
  } catch (e) {
    alert(e.message || "Не удалось получить награду");
  }
}

// ============================================
// Покупка VIP Pass / докупка уровня
// ============================================
async function buyPassVip() {
  try {
    const res = await apiPost("/pass/buy-vip", { telegram_id: state.telegramId });
    state.goldBalance = res.gold_balance;
    document.getElementById("gold-value").textContent = fmtNumber(res.gold_balance);
    await loadPassStatus();
    await loadPassDailyTasks();
  } catch (e) {
    alert(e.message || "Не удалось купить VIP Pass");
  }
}

async function skipPassLevel() {
  try {
    const res = await apiPost("/pass/skip-level", { telegram_id: state.telegramId });
    state.goldBalance = res.gold_balance;
    document.getElementById("gold-value").textContent = fmtNumber(res.gold_balance);
    await loadPassStatus();
  } catch (e) {
    alert(e.message || "Не удалось докупить уровень");
  }
}

// ============================================
// Рендер: результат клейма (модалка)
// ============================================
function showPassResult(rewards) {
  const list = document.getElementById("pass-result-list");
  list.innerHTML = rewards.map(r => {
    if (r.item) {
      const color = PASS_RARITY_COLOR[r.item.rarity] || "#8b93a1";
      return `
        <div class="win-item-card" style="border-color:${color}">
          <img src="${r.item.image || ""}" alt="">
          <div class="win-item-name">${r.item.name}</div>
          <div class="win-item-quality">${r.item.quality_name || ""}${r.item.stattrak ? " · StatTrak™" : ""}</div>
          <div class="win-item-price">${fmt(r.item.price)}</div>
        </div>`;
    }
    return `
      <div class="win-item-card">
        <div class="daily-result-icon">${passRewardIcon(r)}</div>
        <div class="win-item-name">${passRewardLabel(r)}</div>
      </div>`;
  }).join("");
  document.getElementById("pass-result-modal").classList.add("active");
}

// ============================================
// Рендер: ежедневные задания
// ============================================
function renderPassTasks() {
  const t = passState.tasks;
  const list = document.getElementById("pass-tasks-list");
  if (!t) { list.innerHTML = ""; return; }

  // ПРАВКИ В ТЗ №12, п.4: заданию больше не нужна кнопка "Забрать" — XP
  // начисляется на бэкенде сам, как только условие выполнено (см.
  // loadPassDailyTasks/animatePassHeaderBar выше). Карточка теперь только
  // ПОКАЗЫВАЕТ статус: прогресс "1 / 3 кейсов" пока не выполнено, и
  // зелёный градиент + "Выполнено ✓" как только бэкенд зачёл задание.
  list.innerHTML = t.tasks.map(task => {
    const pct = Math.min(100, Math.round((task.progress / task.target) * 100));
    const statusChip = task.claimed
      ? `<span class="pass-task-status done">Выполнено ✓</span>`
      : `<span class="pass-task-status">${task.progress} / ${task.target}</span>`;

    return `
      <div class="pass-task-card ${task.claimed ? "claimed" : ""}">
        <div class="pass-task-top">
          <div class="pass-task-title">${task.title}</div>
          ${statusChip}
        </div>
        <div class="pass-task-desc">${task.description}</div>
        <div class="pass-task-bar"><div class="pass-task-bar-fill" style="width:${pct}%"></div></div>
        <div class="pass-task-xp">${task.claimed ? "Получено" : "Награда"}: +${task.xp} XP</div>
      </div>`;
  }).join("");
}

// ============================================
// Финальный 50-й уровень — интерактивный сундук (canvas-скретч)
// ============================================
function renderFinalChest() {
  const s = passState.status;
  const box = document.getElementById("pass-final-chest");
  if (!s || !s.final_chest.unlocked) { box.style.display = "none"; return; }

  const tracks = [{ key: "free", label: "🎁 Финальный сундук — Free", claimed: s.final_chest.free_claimed, available: true }];
  if (s.is_vip_pass) {
    tracks.push({ key: "vip", label: "⭐ Финальный сундук — VIP", claimed: s.final_chest.vip_claimed, available: true });
  }

  box.style.display = "block";
  box.innerHTML = tracks.map(tr => `
    <div class="pass-final-track">
      <div class="pass-final-track-title">${tr.label}</div>
      ${tr.claimed
        ? `<div class="pass-final-claimed-hint">Уже открыт — загляни в инвентарь!</div>`
        : `<div class="pass-final-cards" id="pass-final-cards-${tr.key}">
            ${[0, 1, 2].map(i => `
              <div class="pass-final-card">
                <canvas class="pass-scratch-canvas" id="pass-scratch-${tr.key}-${i}" width="140" height="140"></canvas>
                <div class="pass-final-card-underlay">🏆</div>
              </div>`).join("")}
          </div>
          <div class="pass-final-hint">Сотри защитный слой на ОДНОЙ карточке пальцем</div>`
      }
    </div>
  `).join("");

  tracks.forEach(tr => {
    if (tr.claimed) return;
    passState.finalChestLocked[tr.key] = false;
    for (let i = 0; i < 3; i++) {
      const canvas = document.getElementById(`pass-scratch-${tr.key}-${i}`);
      if (canvas) setupScratchCard(canvas, tr.key, i);
    }
  });
}

function setupScratchCard(canvas, track, cardIndex) {
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#2a3444";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f89c1c";
  ctx.font = "bold 42px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("?", canvas.width / 2, canvas.height / 2);

  let drawing = false;

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const cy = e.touches ? e.touches[0].clientY : e.clientY;
    return { x: (cx - rect.left) * (canvas.width / rect.width), y: (cy - rect.top) * (canvas.height / rect.height) };
  }

  function erase(x, y) {
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    ctx.arc(x, y, 16, 0, Math.PI * 2);
    ctx.fill();
  }

  function erasedRatio() {
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let cleared = 0;
    let sampled = 0;
    for (let i = 3; i < data.length; i += 4 * 6) {
      sampled++;
      if (data[i] === 0) cleared++;
    }
    return sampled ? cleared / sampled : 0;
  }

  function onMove(e) {
    if (!drawing || passState.finalChestLocked[track]) return;
    const p = pos(e);
    erase(p.x, p.y);
    if (erasedRatio() > 0.45) {
      drawing = false;
      passState.finalChestLocked[track] = true;
      revealFinalChest(track, cardIndex);
    }
  }

  function onDown(e) {
    if (passState.finalChestLocked[track]) return;
    drawing = true;
    const p = pos(e);
    erase(p.x, p.y);
  }

  function onUp() { drawing = false; }

  canvas.addEventListener("mousedown", onDown);
  canvas.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  canvas.addEventListener("touchstart", (e) => { onDown(e); e.preventDefault(); }, { passive: false });
  canvas.addEventListener("touchmove", (e) => { onMove(e); e.preventDefault(); }, { passive: false });
  canvas.addEventListener("touchend", onUp);
}

async function revealFinalChest(track, cardIndex) {
  try {
    const res = await apiPost("/pass/final-chest/reveal", {
      telegram_id: state.telegramId, track, card_index: cardIndex,
    });
    showPassResult([{ item: res.item }]);
    await loadPassStatus();
    await loadInventory();
  } catch (e) {
    alert(e.message || "Не удалось открыть сундук");
    passState.finalChestLocked[track] = false;
  }
}

// ============================================
// Открытие/закрытие модалки, вкладки
// ============================================
function openPassModal() {
  document.getElementById("pass-modal").classList.add("active");
  renderPassHeader();
  renderPassTree();
  renderFinalChest();
  if (!passState.tasks) loadPassDailyTasks();
  else renderPassTasks();
  startPassTimers();
  if (passState.activeTab === "tasks") startPassTasksPolling();
}

function switchPassTab(tab) {
  passState.activeTab = tab;
  document.getElementById("pass-tab-btn-tree").classList.toggle("active", tab === "tree");
  document.getElementById("pass-tab-btn-tasks").classList.toggle("active", tab === "tasks");
  document.getElementById("pass-tab-tree").style.display = tab === "tree" ? "block" : "none";
  document.getElementById("pass-tab-tasks").style.display = tab === "tasks" ? "block" : "none";
  if (tab === "tasks") {
    loadPassDailyTasks();
    startPassTasksPolling();
  } else {
    stopPassTasksPolling();
  }
}

// ПРАВКИ В ТЗ №12, п.4: лёгкий поллинг (раз в 4с) заданий, пока вкладка
// "Задания" реально видна — не создаёт лишней нагрузки (останавливается
// при переключении вкладки/закрытии модалки), но позволяет увидеть
// автозачёт XP почти сразу, а не только при повторном открытии вкладки.
function startPassTasksPolling() {
  stopPassTasksPolling();
  passState.tasksPollId = setInterval(loadPassDailyTasks, 4000);
}

function stopPassTasksPolling() {
  if (passState.tasksPollId) {
    clearInterval(passState.tasksPollId);
    passState.tasksPollId = null;
  }
}

// ============================================
// Косметика Battle Pass (рамки/цвет ника) — экран Профиль
// ============================================
const PASS_FRAME_STYLE = {
  neon_rookie: { label: "Неоновый Новичок", css: "0 0 0 3px #4a9eff, 0 0 14px #4a9eff" },
  fire_burst: { label: "Огненный Всполох", css: "0 0 0 3px #f89c1c, 0 0 14px #ff5e1c" },
  cyberpunk: { label: "Киберпанк", css: "0 0 0 3px #d32ce6, 0 0 14px #4a9eff" },
  golden_dragon: { label: "Золотой Дракон", css: "0 0 0 3px #ffd700, 0 0 14px #ffb300" },
  animated_ice: { label: "Анимированный Лёд", css: "0 0 0 3px #9be7ff, 0 0 16px #4ad1ff" },
  plasma: { label: "Плазма", css: "0 0 0 3px #eb4bd8, 0 0 16px #7b4beb" },
  cosmic_abyss: { label: "Космическая Бездна", css: "0 0 0 3px #4b3fbf, 0 0 18px #1a0f4d" },
  cs2_legend: { label: "Легенда CS2", css: "0 0 0 3px #ffd700, 0 0 20px #eb4b4b" },
  animated_neon: { label: "Анимированный Неон", css: "0 0 0 3px #39ff88, 0 0 18px #39ffe0" },
  pass_finalist: { label: "Финалист Pass", css: "0 0 0 3px #ffd700, 0 0 24px #ff5e1c, 0 0 8px #fff" },
};

const PASS_NICK_COLOR_STYLE = {
  green: { label: "Зелёный", css: "#2ecc71" },
  blue: { label: "Синий", css: "#4a9eff" },
  purple: { label: "Фиолетовый", css: "#8847ff" },
  gold: { label: "Золотой", css: "#ffd700" },
  rainbow_gradient: { label: "Радужный", css: "linear-gradient(90deg,#ff5e5e,#ffd15c,#5cff8f,#5cd1ff,#c25cff)" },
  neon_red: { label: "Неоновый Красный", css: "#ff2e4d" },
  dark_crimson: { label: "Тёмно-Алый", css: "#8b0020" },
  chameleon: { label: "Хамелеон", css: "linear-gradient(90deg,#2ecc71,#4a9eff,#d32ce6)" },
  global_master: { label: "Глобал Мастер", css: "linear-gradient(90deg,#ffd700,#ffffff,#4a9eff)" },
};

function renderPassCosmetics() {
  const s = passState.status;
  const card = document.getElementById("pass-cosmetics-card");
  if (!s || (s.unlocked_pass_frames.length === 0 && s.unlocked_pass_nick_colors.length === 0)) {
    if (card) card.style.display = "none";
    return;
  }
  card.style.display = "block";

  const framesRow = document.getElementById("pass-frames-row");
  framesRow.innerHTML = [`<button class="pass-cosmetic-chip ${!s.selected_pass_frame ? "active" : ""}" data-kind="frame" data-key="">Нет</button>`]
    .concat(s.unlocked_pass_frames.map(key => {
      const def = PASS_FRAME_STYLE[key] || { label: key };
      const active = s.selected_pass_frame === key ? "active" : "";
      return `<button class="pass-cosmetic-chip ${active}" data-kind="frame" data-key="${key}" style="box-shadow:${(PASS_FRAME_STYLE[key] || {}).css || "none"} inset">${def.label}</button>`;
    })).join("");

  const nickRow = document.getElementById("pass-nick-colors-row");
  nickRow.innerHTML = [`<button class="pass-cosmetic-chip ${!s.selected_pass_nick_color ? "active" : ""}" data-kind="nick_color" data-key="">По умолчанию</button>`]
    .concat(s.unlocked_pass_nick_colors.map(key => {
      const def = PASS_NICK_COLOR_STYLE[key] || { label: key, css: "#8b93a1" };
      const active = s.selected_pass_nick_color === key ? "active" : "";
      return `<button class="pass-cosmetic-chip ${active}" data-kind="nick_color" data-key="${key}"><span class="pass-nick-swatch" style="background:${def.css}"></span>${def.label}</button>`;
    })).join("");

  card.querySelectorAll(".pass-cosmetic-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.kind;
      const key = btn.dataset.key || null;
      // ПРАВКИ В ТЗ №12, п.2: карточка «Превью профиля» в модалке Настроек
      // обновляется мгновенно, синхронно с кликом — до ответа
      // selectPassCosmetic() (apiPost уходит следом, в фоне).
      if (typeof updateCustomizePreviewPassFrame === "function" && kind === "frame") updateCustomizePreviewPassFrame(key);
      if (typeof updateCustomizePreviewNickColor === "function" && kind === "nick_color") updateCustomizePreviewNickColor(key);
      selectPassCosmetic(kind, key);
    });
  });

  applyPassCosmeticsToProfile();
}

function applyPassCosmeticsToProfile() {
  const s = passState.status;
  if (!s) return;
  const avatarEls = [document.getElementById("profile-avatar"), document.getElementById("profile-avatar-img")];
  const frameDef = s.selected_pass_frame ? PASS_FRAME_STYLE[s.selected_pass_frame] : null;
  avatarEls.forEach(el => {
    if (!el) return;
    el.style.boxShadow = frameDef ? frameDef.css : "";
    el.style.borderRadius = frameDef ? "50%" : "";
  });

  const nameEl = document.getElementById("profile-name");
  const nickDef = s.selected_pass_nick_color ? PASS_NICK_COLOR_STYLE[s.selected_pass_nick_color] : null;
  if (nameEl) {
    if (nickDef && nickDef.css.startsWith("linear-gradient")) {
      nameEl.style.background = nickDef.css;
      nameEl.style.webkitBackgroundClip = "text";
      nameEl.style.webkitTextFillColor = "transparent";
      nameEl.style.backgroundClip = "text";
    } else {
      nameEl.style.background = "none";
      nameEl.style.webkitTextFillColor = "";
      nameEl.style.color = nickDef ? nickDef.css : "";
    }
  }
}

async function selectPassCosmetic(kind, key) {
  try {
    await apiPost("/pass/select-cosmetic", { telegram_id: state.telegramId, kind, key });
    await loadPassStatus();
    renderPassCosmetics();
  } catch (e) {
    alert(e.message || "Не удалось применить косметику");
  }
}

document.getElementById("pass-widget-open-btn").addEventListener("click", openPassModal);
document.getElementById("pass-close-btn").addEventListener("click", () => {
  document.getElementById("pass-modal").classList.remove("active");
  stopPassTimers();
  stopPassTasksPolling();
});
document.getElementById("pass-modal").addEventListener("click", (e) => {
  if (e.target.id === "pass-modal") {
    document.getElementById("pass-modal").classList.remove("active");
    stopPassTimers();
    stopPassTasksPolling();
  }
});
document.getElementById("pass-result-ok-btn").addEventListener("click", () => {
  document.getElementById("pass-result-modal").classList.remove("active");
});
document.getElementById("pass-buy-vip-btn").addEventListener("click", buyPassVip);
// ПРАВКИ В ТЗ №12, п.3: кнопки #pass-skip-btn в шапке больше нет — клик
// по докупке уровня навешивается динамически в renderPassTree() на ту
// карточку, где кнопка сейчас отрисована (см. passBuyLevelButtonHTML).
document.querySelectorAll(".pass-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchPassTab(btn.dataset.tab));
});
