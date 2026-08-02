// ============================================
// CS2 Case Simulator — Frontend Logic
// ============================================

const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const API_BASE = "https://cs2-app.onrender.com/api"; // замени на реальный адрес FastAPI

// initDataUnsafe используется ТОЛЬКО для мгновенного отображения плейсхолдера
// (имя/аватар) ещё до ответа сервера — доверять этим данным для авторизации
// нельзя, их легко подделать. Настоящий telegram_id приходит только из
// ответа /api/auth/telegram, где initData проверяется по подписи на бэкенде.
const tgUserUnsafe = tg?.initDataUnsafe?.user;

const state = {
  telegramId: tgUserUnsafe?.id || 123456789, // фолбэк для теста вне Telegram, перезапишется после логина
  username: tgUserUnsafe?.first_name || "Игрок",
  photoUrl: tgUserUnsafe?.photo_url || null,
  authenticated: false,
  balance: 0,
  isVip: false,
  vipExpiresAt: null,
  lang: "ru",
  soundEnabled: true,
  cases: [],
  inventory: [],
  casesOpenedSinceAd: 0,
  adBannerDismissed: false,
  currentCase: null,
  pendingDrop: null,
  botUsername: "your_bot_username",
  adsgramBlockId: null,
  refBonusInviter: 1000,
  refBonusInvited: 1000,
  vipPriceStars: 150,
  openCount: 1,
  openSpeed: "slow",
  lastMultiDrops: [],
  selectedInventoryIds: new Set(),
  dailyStatus: null,
};

// ============================================
// i18n
// ============================================
const I18N = {
  ru: {
    cases_title: "Кейсы", inventory_title: "Инвентарь",
    inventory_empty: "Пока пусто. Открой первый кейс!",
    profile_title: "Профиль", stat_cases: "Открыто кейсов",
    stat_inv_value: "Стоимость инвентаря", stat_favorite: "Любимый кейс",
    stat_top_drop: "Топ дроп", settings_title: "⚙️ Настройки",
    settings_lang: "🌐 Язык", settings_sound: "🔊 Звук",
    sound_on: "Вкл", sound_off: "Выкл",
    ref_title: "👥 Реферальная ссылка", copy_btn: "Копировать",
    promo_title: "🎁 Промокод", promo_placeholder: "Введите промокод",
    activate_btn: "Активировать", minigames_title: "Мини-игры",
    upgrade_desc: "Выбери предмет из инвентаря и множитель — при успехе цена вырастет, при неудаче предмет сгорает.",
    multiplier_label: "Множитель", chance_preview_label: "Примерный шанс успеха",
    upgrade_btn: "Улучшить", crash_desc: "Ставь Кристаллики и укажи, на каком множителе хочешь забрать выигрыш.",
    bet_label: "Ставка (💎)", cashout_label: "Забрать на", play_btn: "Играть",
    earn_title: "Заработать", earn_ad_title: "Посмотреть видео",
    earn_ad_desc: "Получи +2000 💎 виртуального баланса", watch_btn: "Смотреть",
    earn_giveaway_title: "Розыгрыши", earn_giveaway_desc: "Участвуй и выигрывай редкие скины",
    earn_vip_title: "VIP-статус", earn_vip_desc: "Без рекламы + косметические бонусы",
    buy_btn: "Купить", tab_cases: "Кейсы", tab_inventory: "Инвентарь",
    tab_profile: "Профиль", tab_minigames: "Мини-игры", tab_earn: "Заработать",
    open_case_btn: "Открыть кейс", contents_title: "📋 Содержимое кейса",
    win_title: "🎉 Выпало!", keep_btn: "Оставить", sell_btn: "Продать",
    insufficient_balance: "Недостаточно Кристалликов 💎. Посмотри рекламу на вкладке «Заработать»!",
    link_copied: "Ссылка скопирована!", sell_label: "Продать",
    upgrade_success: "🎉 Успех! Новая цена:", upgrade_fail: "💥 Неудача. Предмет сгорел.",
    select_item_first: "Выбери предмет для улучшения", bet_invalid: "Укажи корректную ставку",
    balance_low: "Недостаточно Кристалликов 💎", ads_unavailable: "Реклама недоступна, попробуйте позже.",
    ad_reward_toast: "начислено за просмотр!", vip_hint: "Открой чат с ботом, чтобы оформить VIP через Telegram Stars.",
    giveaways_soon: "Раздел розыгрышей скоро появится здесь!",
    back_btn: "Назад", open_count_label: "Количество открытий", open_speed_label: "Режим скорости",
    speed_slow: "Медленно", speed_fast: "Быстро", sell_all_btn: "Продать всё",
    select_all_label: "Выделить все", disintegrate_btn: "Распылить выбранное в Кристаллы",
    disintegrate_success: "Предметы распылены в Кристаллы!", nothing_selected: "Выбери хотя бы один предмет",
    open_case_for_btn: "Открыть за",
    games_hub_hint: "Выбери игру", game_rocket: "Ракета", game_upgrader: "Улучшитель",
    game_wheel: "Колесо", game_miner: "Минёр", game_tower: "Башня", game_ladder: "Лесенка",
    bonus_btn: "Бонус 💎 2000", bonus_claimed_toast: "начислено бонусом!",
    bonus_wait_prefix: "Бонус через", mines_count_label: "Количество мин",
    cashout_btn: "Забрать", bust_msg: "💥 Бум! Раунд окончен.", cleared_msg: "🎉 Все безопасные клетки открыты!",
    level_label: "Уровень", pick_tile_hint: "Выбери плитку, чтобы продвинуться дальше",
    current_multiplier_label: "Текущий множитель", spin_btn: "Крутить", start_round_btn: "Начать раунд",
    win_toast_prefix: "Выигрыш", lose_toast: "К сожалению, не повезло",
    earn_bonus_desc: "Бесплатный бонус раз в 60 секунд",
    wheel_desc: "Ставь Кристаллики и крути колесо — выпавший множитель сразу начисляется на баланс.",
    miner_desc: "Открывай безопасные клетки на поле 5×5, обходя мины — можно забрать выигрыш в любой момент.",
    tower_desc: "Поднимайся по башне, выбирая безопасную плитку на каждом уровне — чем выше, тем больше множитель.",
    ladder_desc: "Делай шаги по лесенке, выбирая одну из двух плиток — риск выше, но и множитель растёт быстрее.",
    droprate_chance_label: "Точный шанс выпадения", droprate_price_label: "Примерная стоимость",
    ok_btn: "Отлично!",
    daily_title: "🎁 Ежедневный бонус", daily_earn_title: "Ежедневный бонус",
    daily_earn_desc: "Заходи каждый день — награды растут до 7 дня!",
    daily_claim_btn: "Забрать награду", daily_claimed_btn: "Уже забрано сегодня",
    daily_hint: "Заходи каждый день, чтобы не потерять серию! Пропустишь день — серия сбросится.",
    daily_streak_label: "Серия: {n} дн. подряд", daily_day_label: "День {n}",
    daily_result_title: "🎉 Награда получена!",
    daily_reward_skin: "Редкий скин!", daily_reward_promo: "Промокод",
    daily_reward_jackpot: "Джекпот 7-го дня!",
    daily_promo_hint: "Активируй его на вкладке «Заработать → Промокод»:",
    daily_already_claimed_toast: "Ежедневный бонус уже получен сегодня. Возвращайся завтра!",
  },
  en: {
    cases_title: "Cases", inventory_title: "Inventory",
    inventory_empty: "Empty for now. Open your first case!",
    profile_title: "Profile", stat_cases: "Cases opened",
    stat_inv_value: "Inventory value", stat_favorite: "Favorite case",
    stat_top_drop: "Top drop", settings_title: "⚙️ Settings",
    settings_lang: "🌐 Language", settings_sound: "🔊 Sound",
    sound_on: "On", sound_off: "Off",
    ref_title: "👥 Referral link", copy_btn: "Copy",
    promo_title: "🎁 Promo code", promo_placeholder: "Enter promo code",
    activate_btn: "Activate", minigames_title: "Mini-games",
    upgrade_desc: "Pick an item from inventory and a multiplier — succeed and the price grows, fail and it's gone.",
    multiplier_label: "Multiplier", chance_preview_label: "Approx. success chance",
    upgrade_btn: "Upgrade", crash_desc: "Place a bet and choose the multiplier to cash out at.",
    bet_label: "Bet (💎)", cashout_label: "Cash out at", play_btn: "Play",
    earn_title: "Earn", earn_ad_title: "Watch a video",
    earn_ad_desc: "Get +2000 💎 virtual balance", watch_btn: "Watch",
    earn_giveaway_title: "Giveaways", earn_giveaway_desc: "Join and win rare skins",
    earn_vip_title: "VIP status", earn_vip_desc: "No ads + cosmetic perks",
    buy_btn: "Buy", tab_cases: "Cases", tab_inventory: "Inventory",
    tab_profile: "Profile", tab_minigames: "Games", tab_earn: "Earn",
    open_case_btn: "Open case", contents_title: "📋 Case contents",
    win_title: "🎉 You got!", keep_btn: "Keep", sell_btn: "Sell",
    insufficient_balance: "Not enough 💎 Crystals. Watch an ad on the Earn tab!",
    link_copied: "Link copied!", sell_label: "Sell",
    upgrade_success: "🎉 Success! New price:", upgrade_fail: "💥 Failed. The item is gone.",
    select_item_first: "Pick an item to upgrade", bet_invalid: "Enter a valid bet",
    balance_low: "Not enough 💎 Crystals", ads_unavailable: "Ad unavailable, try again later.",
    ad_reward_toast: "credited for watching!", vip_hint: "Open the bot chat to get VIP via Telegram Stars.",
    giveaways_soon: "Giveaways are coming soon!",
    back_btn: "Back", open_count_label: "Number of openings", open_speed_label: "Speed mode",
    speed_slow: "Slow", speed_fast: "Fast", sell_all_btn: "Sell all",
    select_all_label: "Select all", disintegrate_btn: "Disintegrate selected into Crystals",
    disintegrate_success: "Items disintegrated into Crystals!", nothing_selected: "Select at least one item",
    open_case_for_btn: "Open for",
    games_hub_hint: "Pick a game", game_rocket: "Rocket", game_upgrader: "Upgrader",
    game_wheel: "Wheel", game_miner: "Miner", game_tower: "Tower", game_ladder: "Ladder",
    bonus_btn: "Bonus 💎 2000", bonus_claimed_toast: "credited as a bonus!",
    bonus_wait_prefix: "Bonus in", mines_count_label: "Number of mines",
    cashout_btn: "Cash out", bust_msg: "💥 Boom! Round over.", cleared_msg: "🎉 All safe tiles revealed!",
    level_label: "Level", pick_tile_hint: "Pick a tile to move forward",
    current_multiplier_label: "Current multiplier", spin_btn: "Spin", start_round_btn: "Start round",
    win_toast_prefix: "Win", lose_toast: "No luck this time",
    earn_bonus_desc: "Free bonus once every 60 seconds",
    wheel_desc: "Place a bet and spin the wheel — the multiplier you land on is credited instantly.",
    miner_desc: "Reveal safe tiles on a 5×5 field while avoiding mines — cash out anytime.",
    tower_desc: "Climb the tower by picking a safe tile on each level — the higher you go, the bigger the multiplier.",
    ladder_desc: "Step up the ladder by picking one of two tiles — riskier, but the multiplier grows faster.",
    droprate_chance_label: "Exact drop chance", droprate_price_label: "Approx. value",
    ok_btn: "Awesome!",
    daily_title: "🎁 Daily bonus", daily_earn_title: "Daily bonus",
    daily_earn_desc: "Log in every day — rewards grow up to day 7!",
    daily_claim_btn: "Claim reward", daily_claimed_btn: "Already claimed today",
    daily_hint: "Come back every day to keep your streak! Miss a day and it resets.",
    daily_streak_label: "Streak: {n} days in a row", daily_day_label: "Day {n}",
    daily_result_title: "🎉 Reward claimed!",
    daily_reward_skin: "Rare skin!", daily_reward_promo: "Promo code",
    daily_reward_jackpot: "Day 7 jackpot!",
    daily_promo_hint: "Activate it on the Earn → Promo code tab:",
    daily_already_claimed_toast: "Daily bonus already claimed today. Come back tomorrow!",
  },
  uk: {
    cases_title: "Кейси", inventory_title: "Інвентар",
    inventory_empty: "Поки що порожньо. Відкрий перший кейс!",
    profile_title: "Профіль", stat_cases: "Відкрито кейсів",
    stat_inv_value: "Вартість інвентаря", stat_favorite: "Улюблений кейс",
    stat_top_drop: "Топ дроп", settings_title: "⚙️ Налаштування",
    settings_lang: "🌐 Мова", settings_sound: "🔊 Звук",
    sound_on: "Увім.", sound_off: "Вимк.",
    ref_title: "👥 Реферальне посилання", copy_btn: "Копіювати",
    promo_title: "🎁 Промокод", promo_placeholder: "Введіть промокод",
    activate_btn: "Активувати", minigames_title: "Міні-ігри",
    upgrade_desc: "Обери предмет з інвентаря та множник — при успіху ціна зросте, при невдачі предмет згорить.",
    multiplier_label: "Множник", chance_preview_label: "Приблизний шанс успіху",
    upgrade_btn: "Покращити", crash_desc: "Став Кристалики та обери множник, на якому забрати виграш.",
    bet_label: "Ставка (💎)", cashout_label: "Забрати на", play_btn: "Грати",
    earn_title: "Заробити", earn_ad_title: "Переглянути відео",
    earn_ad_desc: "Отримай +2000 💎 віртуального балансу", watch_btn: "Дивитись",
    earn_giveaway_title: "Розіграші", earn_giveaway_desc: "Бери участь і вигравай рідкісні скіни",
    earn_vip_title: "VIP-статус", earn_vip_desc: "Без реклами + косметичні бонуси",
    buy_btn: "Купити", tab_cases: "Кейси", tab_inventory: "Інвентар",
    tab_profile: "Профіль", tab_minigames: "Міні-ігри", tab_earn: "Заробити",
    open_case_btn: "Відкрити кейс", contents_title: "📋 Вміст кейса",
    win_title: "🎉 Випало!", keep_btn: "Залишити", sell_btn: "Продати",
    insufficient_balance: "Недостатньо Кристаликів 💎. Подивись рекламу на вкладці «Заробити»!",
    link_copied: "Посилання скопійовано!", sell_label: "Продати",
    upgrade_success: "🎉 Успіх! Нова ціна:", upgrade_fail: "💥 Невдача. Предмет згорів.",
    select_item_first: "Обери предмет для покращення", bet_invalid: "Вкажи коректну ставку",
    balance_low: "Недостатньо Кристаликів 💎", ads_unavailable: "Реклама недоступна, спробуй пізніше.",
    ad_reward_toast: "нараховано за перегляд!", vip_hint: "Відкрий чат з ботом, щоб оформити VIP через Telegram Stars.",
    giveaways_soon: "Розділ розіграшів скоро зʼявиться тут!",
    back_btn: "Назад", open_count_label: "Кількість відкриттів", open_speed_label: "Режим швидкості",
    speed_slow: "Повільно", speed_fast: "Швидко", sell_all_btn: "Продати все",
    select_all_label: "Виділити все", disintegrate_btn: "Розпилити вибране в Кристалики",
    disintegrate_success: "Предмети розпилено в Кристалики!", nothing_selected: "Обери хоча б один предмет",
    open_case_for_btn: "Відкрити за",
    games_hub_hint: "Обери гру", game_rocket: "Ракета", game_upgrader: "Покращувач",
    game_wheel: "Колесо", game_miner: "Мінер", game_tower: "Вежа", game_ladder: "Драбинка",
    bonus_btn: "Бонус 💎 2000", bonus_claimed_toast: "нараховано бонусом!",
    bonus_wait_prefix: "Бонус через", mines_count_label: "Кількість мін",
    cashout_btn: "Забрати", bust_msg: "💥 Бум! Раунд завершено.", cleared_msg: "🎉 Усі безпечні клітинки відкрито!",
    level_label: "Рівень", pick_tile_hint: "Обери плитку, щоб просунутись далі",
    current_multiplier_label: "Поточний множник", spin_btn: "Крутити", start_round_btn: "Почати раунд",
    win_toast_prefix: "Виграш", lose_toast: "На жаль, не пощастило",
    earn_bonus_desc: "Безкоштовний бонус раз на 60 секунд",
    wheel_desc: "Став Кристалики та крути колесо — множник одразу нараховується на баланс.",
    miner_desc: "Відкривай безпечні клітинки на полі 5×5, оминаючи міни — забрати виграш можна будь-коли.",
    tower_desc: "Піднімайся вежею, обираючи безпечну плитку на кожному рівні — що вище, то більший множник.",
    ladder_desc: "Роби кроки драбинкою, обираючи одну з двох плиток — ризик вищий, але й множник росте швидше.",
    droprate_chance_label: "Точний шанс випадіння", droprate_price_label: "Приблизна вартість",
    ok_btn: "Чудово!",
    daily_title: "🎁 Щоденний бонус", daily_earn_title: "Щоденний бонус",
    daily_earn_desc: "Заходь щодня — нагороди зростають до 7 дня!",
    daily_claim_btn: "Забрати нагороду", daily_claimed_btn: "Вже забрано сьогодні",
    daily_hint: "Заходь щодня, щоб не втратити серію! Пропустиш день — серія скинеться.",
    daily_streak_label: "Серія: {n} дн. поспіль", daily_day_label: "День {n}",
    daily_result_title: "🎉 Нагороду отримано!",
    daily_reward_skin: "Рідкісний скін!", daily_reward_promo: "Промокод",
    daily_reward_jackpot: "Джекпот 7-го дня!",
    daily_promo_hint: "Активуй його на вкладці «Заробити → Промокод»:",
    daily_already_claimed_toast: "Щоденний бонус уже отримано сьогодні. Повертайся завтра!",
  },
};

function t(key) {
  return (I18N[state.lang] && I18N[state.lang][key]) || I18N.ru[key] || key;
}

function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.lang === state.lang);
  });
  const soundLabel = document.getElementById("sound-switch-label");
  if (soundLabel) soundLabel.textContent = state.soundEnabled ? t("sound_on") : t("sound_off");
  document.getElementById("earn-ad-desc").textContent = t("earn_ad_desc");
}

function setLang(lang) {
  state.lang = lang;
  localStorage.setItem("cs2_lang", lang);
  applyTranslations();
  apiPost("/user/settings", { telegram_id: state.telegramId, lang }).catch(() => {});
}

document.getElementById("lang-switch").addEventListener("click", (e) => {
  const btn = e.target.closest(".lang-btn");
  if (btn) setLang(btn.dataset.lang);
});

// ============================================
// Звук (Web Audio API — синтезированные эффекты, файлы не нужны)
// ============================================
const AudioCtx = window.AudioContext || window.webkitAudioContext;
let audioCtx = null;
function ensureAudioCtx() {
  if (!audioCtx && AudioCtx) audioCtx = new AudioCtx();
  if (audioCtx?.state === "suspended") audioCtx.resume();
  return audioCtx;
}

function tone(freq, duration, type = "sine", gainStart = 0.15, delay = 0) {
  if (!state.soundEnabled) return;
  const ctx = ensureAudioCtx();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  const startAt = ctx.currentTime + delay;
  gain.gain.setValueAtTime(gainStart, startAt);
  gain.gain.exponentialRampToValueAtTime(0.001, startAt + duration);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(startAt);
  osc.stop(startAt + duration);
}

const sfx = {
  click: () => tone(700, 0.05, "square", 0.08),
  spinTick: () => tone(500 + Math.random() * 200, 0.04, "square", 0.06),
  lock: () => { tone(220, 0.12, "triangle", 0.18); tone(440, 0.1, "triangle", 0.1, 0.05); },
  lose: () => { tone(220, 0.25, "sawtooth", 0.12); tone(140, 0.3, "sawtooth", 0.12, 0.08); },
  fanfare: () => {
    // победные фанфары для редких/особо редких предметов
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, 0.35, "triangle", 0.18, i * 0.09));
  },
  win: () => { tone(523.25, 0.15, "triangle", 0.15); tone(659.25, 0.18, "triangle", 0.15, 0.1); },
};

// Haptic feedback (Telegram WebApp) — единая точка вызова для всех мини-игр
function haptic(kind) {
  const h = tg?.HapticFeedback;
  if (!h) return;
  if (kind === "light" || kind === "medium" || kind === "heavy" || kind === "rigid" || kind === "soft") {
    h.impactOccurred?.(kind);
  } else if (kind === "success" || kind === "error" || kind === "warning") {
    h.notificationOccurred?.(kind);
  } else if (kind === "select") {
    h.selectionChanged?.();
  }
}

function playSound(name) {
  sfx[name]?.();
}

function updateSoundToggleUI() {
  const headerBtn = document.getElementById("header-sound-toggle");
  const switchBtn = document.getElementById("sound-switch");
  headerBtn.textContent = state.soundEnabled ? "🔊" : "🔇";
  headerBtn.classList.toggle("muted", !state.soundEnabled);
  switchBtn.classList.toggle("off", !state.soundEnabled);
  const label = document.getElementById("sound-switch-label");
  label.textContent = state.soundEnabled ? t("sound_on") : t("sound_off");
}

function toggleSound() {
  state.soundEnabled = !state.soundEnabled;
  localStorage.setItem("cs2_sound", state.soundEnabled ? "1" : "0");
  updateSoundToggleUI();
  if (state.soundEnabled) { ensureAudioCtx(); playSound("click"); }
  apiPost("/user/settings", { telegram_id: state.telegramId, sound_enabled: state.soundEnabled }).catch(() => {});
}

document.getElementById("header-sound-toggle").addEventListener("click", toggleSound);
document.getElementById("sound-switch").addEventListener("click", toggleSound);

// клик по любой кнопке — короткий звук
document.addEventListener("click", (e) => {
  if (e.target.closest("button")) playSound("click");
}, { capture: true });

// ============================================
// Утилиты
// ============================================
// Числовая часть без значка — используется там, где 💎 уже вынесен в отдельный элемент (например, в шапке)
function fmtNumber(n) {
  const num = Number(n) || 0;
  if (num > 0 && num < 1) {
    return num.toFixed(2);
  }
  return num.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

// Полное отображение суммы со значком Кристалла: 💎 1,250 / 💎 0.15
function fmt(n) {
  return "💎 " + fmtNumber(n);
}

function rarityClass(rarity) {
  return "r-" + rarity.replace(" ", "-");
}

const RARITY_LABEL = {
  ru: { Consumer: "Ширпотреб", Industrial: "Промышленное", "Mil-Spec": "Армейское", Restricted: "Запрещённое", Classified: "Засекреченное", Covert: "Тайное", Knife: "★ Нож", Gloves: "★ Перчатки" },
  en: { Consumer: "Consumer", Industrial: "Industrial", "Mil-Spec": "Mil-Spec", Restricted: "Restricted", Classified: "Classified", Covert: "Covert", Knife: "★ Knife", Gloves: "★ Gloves" },
  uk: { Consumer: "Ширвжиток", Industrial: "Промислове", "Mil-Spec": "Армійське", Restricted: "Заборонене", Classified: "Засекречене", Covert: "Таємне", Knife: "★ Ніж", Gloves: "★ Рукавички" },
};
function rarityLabel(rarity) {
  return (RARITY_LABEL[state.lang] && RARITY_LABEL[state.lang][rarity]) || rarity;
}

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Ошибка запроса" }));
    throw new Error(err.detail || "Ошибка запроса");
  }
  return res.json();
}

// ============================================
// Навигация по табам
// ============================================
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchScreen(btn.dataset.screen));
});

function switchScreen(name) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`screen-${name}`).classList.add("active");
  document.querySelector(`.tab-btn[data-screen="${name}"]`).classList.add("active");

  if (name === "inventory") loadInventory();
  if (name === "profile") loadProfile();
}

// ============================================
// Загрузка кейсов
// ============================================
async function loadCases() {
  try {
    const data = await apiGet("/cases");
    state.cases = data.cases;
    renderCases();
  } catch (e) {
    console.error("Ошибка загрузки кейсов:", e);
  }
}

function renderCases() {
  const grid = document.getElementById("cases-grid");
  grid.innerHTML = "";
  state.cases.forEach(c => {
    const card = document.createElement("div");
    card.className = "case-card";
    card.innerHTML = `
      <img src="${c.image}" alt="${c.name}" loading="lazy">
      <div class="case-card-name">${c.name}</div>
      <div class="case-card-price">${fmt(c.price)}</div>
    `;
    card.addEventListener("click", () => openCaseScreen(c));
    grid.appendChild(card);
  });
}

// ============================================
// Полноэкранный экран кейса — с полным скроллируемым списком содержимого
// ============================================
function openCaseScreen(caseData) {
  state.currentCase = caseData;
  state.openCount = 1;
  state.openSpeed = "slow";

  document.getElementById("case-open-header-name").textContent = caseData.name;
  document.getElementById("modal-case-image").src = caseData.image;
  document.getElementById("modal-case-name").textContent = caseData.name;
  document.getElementById("modal-case-price").textContent = fmt(caseData.price);
  updateBalanceDisplay();

  // сброс переключателей на дефолт (1 открытие, медленный режим)
  document.querySelectorAll("#count-switcher .count-btn").forEach(b => b.classList.toggle("active", b.dataset.count === "1"));
  document.querySelectorAll("#speed-switcher .speed-btn").forEach(b => b.classList.toggle("active", b.dataset.speed === "slow"));
  updateOpenCaseBtnLabel();

  const list = document.getElementById("modal-items-list");
  list.innerHTML = "";
  caseData.items.forEach(item => {
    const el = document.createElement("div");
    el.className = `contents-item ${rarityClass(item.rarity)}`;
    el.innerHTML = `
      <img src="${item.image}" alt="${item.name}" loading="lazy">
      <div class="contents-item-info">
        <div class="contents-item-name">${item.name}</div>
        <div class="contents-item-rarity">${rarityLabel(item.rarity)}</div>
      </div>
      <div class="contents-item-price">~${fmt(item.base_price)}</div>
    `;
    el.addEventListener("click", () => showDropRateModal(item));
    list.appendChild(el);
  });

  document.getElementById("roulette-wrapper").style.display = "none";
  document.getElementById("multi-results-grid").style.display = "none";
  document.getElementById("multi-results-actions").style.display = "none";
  document.getElementById("open-case-btn").style.display = "block";
  document.getElementById("case-open-screen").classList.add("active");
}

document.getElementById("case-open-back-btn").addEventListener("click", () => {
  document.getElementById("case-open-screen").classList.remove("active");
  state.currentCase = null;
});

// ============================================
// Переключатель количества открытий: 1, 2, 3, 4, 5, 10
// ============================================
document.getElementById("count-switcher").addEventListener("click", (e) => {
  const btn = e.target.closest(".count-btn");
  if (!btn) return;
  state.openCount = Number(btn.dataset.count);
  document.querySelectorAll("#count-switcher .count-btn").forEach(b => b.classList.toggle("active", b === btn));
  updateOpenCaseBtnLabel();
});

// ============================================
// Переключатель режима скорости: Медленно (рулетка) / Быстро (мгновенно)
// ============================================
document.getElementById("speed-switcher").addEventListener("click", (e) => {
  const btn = e.target.closest(".speed-btn");
  if (!btn) return;
  state.openSpeed = btn.dataset.speed;
  document.querySelectorAll("#speed-switcher .speed-btn").forEach(b => b.classList.toggle("active", b === btn));
});

function updateOpenCaseBtnLabel() {
  const btn = document.getElementById("open-case-btn");
  if (!state.currentCase || !btn) return;
  const total = state.currentCase.price * state.openCount;
  btn.textContent = `${t("open_case_for_btn")} ${fmt(total)}`;
}

// ============================================
// Открытие кейса (1..10 за раз) + анимация рулетки / мгновенный режим
// ============================================
document.getElementById("open-case-btn").addEventListener("click", async () => {
  if (!state.currentCase) return;

  const totalPrice = state.currentCase.price * state.openCount;
  if (state.balance < totalPrice) {
    tg?.showAlert?.(t("insufficient_balance"));
    return;
  }

  try {
    const result = await apiPost("/open-case", {
      telegram_id: state.telegramId,
      case_key: state.currentCase.key,
      count: state.openCount,
    });

    state.balance = result.new_balance;
    updateBalanceDisplay();
    const drops = result.drops || [result.drop];
    state.lastMultiDrops = drops;

    state.casesOpenedSinceAd += state.openCount;
    maybeShowInterstitial();

    if (state.openSpeed === "slow" && state.openCount === 1) {
      state.pendingDrop = drops[0];
      runRouletteAnimation(state.currentCase, drops[0]);
    } else {
      showMultiResults(drops);
    }
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// Мгновенный / множественный результат открытия — сетка предметов
// ============================================
function showMultiResults(drops) {
  document.getElementById("roulette-wrapper").style.display = "none";
  document.getElementById("open-case-btn").style.display = "none";

  const grid = document.getElementById("multi-results-grid");
  grid.style.display = "grid";
  grid.innerHTML = "";
  let total = 0;
  drops.forEach(drop => {
    total += drop.price;
    const el = document.createElement("div");
    el.className = `multi-result-card ${rarityClass(drop.rarity)}`;
    el.innerHTML = `
      <img src="${drop.image}" alt="${drop.name}" loading="lazy">
      <div class="multi-result-card-name">${drop.name}</div>
      <div class="multi-result-card-price">${fmt(drop.price)}</div>
    `;
    grid.appendChild(el);
  });

  document.getElementById("multi-results-total").innerHTML =
    `${drops.length} × — <b>${fmt(total)}</b>`;
  document.getElementById("multi-results-actions").style.display = "block";

  const isRare = drops.some(d => ["Covert", "Knife", "Gloves"].includes(d.rarity));
  playSound(isRare ? "fanfare" : "win");
}

document.getElementById("multi-keep-all-btn").addEventListener("click", () => {
  document.getElementById("multi-results-grid").style.display = "none";
  document.getElementById("multi-results-actions").style.display = "none";
  document.getElementById("open-case-btn").style.display = "block";
  state.lastMultiDrops = [];
  loadProfile();
});

document.getElementById("multi-sell-all-btn").addEventListener("click", async () => {
  if (!state.lastMultiDrops.length) return;
  try {
    const ids = state.lastMultiDrops.map(d => d.id);
    const result = await apiPost("/sell-multiple", {
      telegram_id: state.telegramId,
      inventory_ids: ids,
    });
    state.balance = result.new_balance;
    updateBalanceDisplay();
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    document.getElementById("multi-results-grid").style.display = "none";
    document.getElementById("multi-results-actions").style.display = "none";
    document.getElementById("open-case-btn").style.display = "block";
    state.lastMultiDrops = [];
  }
});

function runRouletteAnimation(caseData, drop) {
  const wrapper = document.getElementById("roulette-wrapper");
  const track = document.getElementById("roulette-track");
  wrapper.style.display = "block";
  track.innerHTML = "";
  track.style.transition = "none";
  track.style.transform = "translateX(0)";

  const REEL_LENGTH = 40;
  const WINNING_INDEX = 32;

  const pool = caseData.items;
  const reel = [];
  for (let i = 0; i < REEL_LENGTH; i++) {
    if (i === WINNING_INDEX) {
      reel.push(drop);
    } else {
      reel.push(pool[Math.floor(Math.random() * pool.length)]);
    }
  }

  reel.forEach(item => {
    const el = document.createElement("div");
    el.className = `roulette-item ${rarityClass(item.rarity)}`;
    el.innerHTML = `
      <img src="${item.image}" alt="${item.name}">
      <span>${item.name}</span>
    `;
    track.appendChild(el);
  });

  const itemWidth = 102;
  const wrapperWidth = wrapper.offsetWidth;
  const targetOffset = WINNING_INDEX * itemWidth - wrapperWidth / 2 + itemWidth / 2;
  const jitter = (Math.random() - 0.5) * 40;

  // звук вращения ленты — серия щелчков, замедляющихся к концу
  let tickCount = 0;
  const totalTicks = 26;
  const tickInterval = setInterval(() => {
    playSound("spinTick");
    tickCount++;
    if (tickCount >= totalTicks) clearInterval(tickInterval);
  }, 160);

  requestAnimationFrame(() => {
    track.style.transition = "transform 4.2s cubic-bezier(0.12, 0.85, 0.15, 1)";
    track.style.transform = `translateX(-${targetOffset + jitter}px)`;
  });

  setTimeout(() => {
    clearInterval(tickInterval);
    playSound("lock");
    const isRare = ["Covert", "Knife", "Gloves"].includes(drop.rarity);
    playSound(isRare ? "fanfare" : "win");
    showWinModal(drop);
  }, 4400);
}

// ============================================
// Окно победы
// ============================================
function showWinModal(drop) {
  document.getElementById("case-open-screen").classList.remove("active");

  document.getElementById("win-item-image").src = drop.image;
  document.getElementById("win-item-name").textContent = drop.name;
  document.getElementById("win-item-quality").textContent =
    `${drop.quality} · ${drop.float_val?.toFixed(4) ?? ""}`;
  document.getElementById("win-item-price").textContent = fmt(drop.price);

  const badges = document.getElementById("win-item-badges");
  badges.innerHTML = `
    <span class="quality-badge">${drop.quality}</span>
    ${drop.stattrak ? `<span class="stattrak-badge">StatTrak™</span>` : ""}
  `;

  const card = document.getElementById("win-item-card");
  const rarityVarMap = {
    "Consumer": "--rarity-consumer",
    "Industrial": "--rarity-industrial",
    "Mil-Spec": "--rarity-milspec",
    "Restricted": "--rarity-restricted",
    "Classified": "--rarity-classified",
    "Covert": "--rarity-covert",
    "Knife": "--rarity-knife",
    "Gloves": "--rarity-gloves",
  };
  const varName = rarityVarMap[drop.rarity] || "--rarity-covert";
  card.style.borderColor = getComputedStyle(document.documentElement).getPropertyValue(varName) || "#eb4b4b";

  document.getElementById("win-modal").classList.add("active");
}

document.getElementById("win-keep-btn").addEventListener("click", () => {
  document.getElementById("win-modal").classList.remove("active");
  state.pendingDrop = null;
  loadProfile();
});

document.getElementById("win-sell-btn").addEventListener("click", async () => {
  if (!state.pendingDrop) return;
  try {
    const result = await apiPost("/sell-skin", {
      telegram_id: state.telegramId,
      inventory_id: state.pendingDrop.id,
    });
    state.balance = result.new_balance;
    updateBalanceDisplay();
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    document.getElementById("win-modal").classList.remove("active");
    state.pendingDrop = null;
  }
});

// ============================================
// Модалка "Шансы выпадения" — клик по предмету внутри кейса
// ============================================
const RARITY_VAR_MAP = {
  "Consumer": "--rarity-consumer",
  "Industrial": "--rarity-industrial",
  "Mil-Spec": "--rarity-milspec",
  "Restricted": "--rarity-restricted",
  "Classified": "--rarity-classified",
  "Covert": "--rarity-covert",
  "Knife": "--rarity-knife",
  "Gloves": "--rarity-gloves",
};

function rarityCssVar(rarity) {
  const varName = RARITY_VAR_MAP[rarity] || "--rarity-consumer";
  return getComputedStyle(document.documentElement).getPropertyValue(varName) || "#b0c3d9";
}

function formatDropChance(chance) {
  const num = Number(chance) || 0;
  // редкие предметы могут иметь доли процента (например 0.15%) — показываем с нужной точностью
  if (num > 0 && num < 0.01) return num.toFixed(4) + "%";
  if (num > 0 && num < 1) return num.toFixed(2) + "%";
  return num.toFixed(2) + "%";
}

function showDropRateModal(item) {
  document.getElementById("droprate-item-image").src = item.image;
  document.getElementById("droprate-item-name").textContent = item.name;
  document.getElementById("droprate-item-rarity").textContent = rarityLabel(item.rarity);
  document.getElementById("droprate-chance-value").textContent = formatDropChance(item.drop_chance);
  document.getElementById("droprate-item-price").textContent = fmt(item.base_price);

  const card = document.getElementById("droprate-item-card");
  card.style.borderColor = rarityCssVar(item.rarity);

  document.getElementById("drop-rate-modal").classList.add("active");
}

document.getElementById("drop-rate-close-btn").addEventListener("click", () => {
  document.getElementById("drop-rate-modal").classList.remove("active");
});
document.getElementById("drop-rate-modal").addEventListener("click", (e) => {
  if (e.target.id === "drop-rate-modal") e.currentTarget.classList.remove("active");
});

// ============================================
// Инвентарь
// ============================================
async function loadInventory() {
  try {
    const data = await apiGet(`/inventory?telegram_id=${state.telegramId}`);
    state.inventory = data.inventory;
    renderInventory();
  } catch (e) {
    console.error("Ошибка загрузки инвентаря:", e);
  }
}

function renderInventory() {
  const grid = document.getElementById("inventory-grid");
  const empty = document.getElementById("inventory-empty");
  const toolbar = document.getElementById("inventory-toolbar");
  const disintegrateBar = document.getElementById("disintegrate-bar");

  // предметы, которых больше нет в инвентаре, снимаем с выделения
  const currentIds = new Set(state.inventory.map(i => i.id));
  state.selectedInventoryIds.forEach(id => {
    if (!currentIds.has(id)) state.selectedInventoryIds.delete(id);
  });

  if (!state.inventory.length) {
    grid.innerHTML = "";
    empty.style.display = "block";
    toolbar.style.display = "none";
    disintegrateBar.style.display = "none";
    return;
  }
  empty.style.display = "none";
  toolbar.style.display = "flex";
  disintegrateBar.style.display = "block";

  grid.innerHTML = "";
  state.inventory.forEach(item => {
    const isSelected = state.selectedInventoryIds.has(item.id);
    const card = document.createElement("div");
    card.className = `inventory-card${isSelected ? " selected" : ""}`;
    card.innerHTML = `
      <input type="checkbox" class="inventory-card-checkbox" data-id="${item.id}" ${isSelected ? "checked" : ""}>
      <img src="${item.image || ""}" alt="${item.name}">
      <div class="inventory-card-name">${item.name}</div>
      <div class="inventory-card-quality">
        ${item.quality || ""}${item.stattrak ? ` · <span class="inventory-card-stattrak">StatTrak™</span>` : ""}
      </div>
      <div class="rarity-bar ${rarityClass(item.rarity)}"></div>
      <div class="inventory-card-price">${fmt(item.price)}</div>
      <button class="sell-btn" data-id="${item.id}">${t("sell_label")}</button>
    `;
    grid.appendChild(card);
  });

  grid.querySelectorAll(".inventory-card-checkbox").forEach(cb => {
    cb.addEventListener("change", () => {
      const id = Number(cb.dataset.id);
      if (cb.checked) state.selectedInventoryIds.add(id);
      else state.selectedInventoryIds.delete(id);
      cb.closest(".inventory-card").classList.toggle("selected", cb.checked);
      updateInventorySelectionUI();
    });
  });

  grid.querySelectorAll(".sell-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      try {
        const result = await apiPost("/sell-skin", {
          telegram_id: state.telegramId,
          inventory_id: id,
        });
        state.balance = result.new_balance;
        state.inventory = state.inventory.filter(i => i.id !== id);
        state.selectedInventoryIds.delete(id);
        updateBalanceDisplay();
        renderInventory();
      } catch (e) {
        tg?.showAlert?.(e.message);
      }
    });
  });

  updateInventorySelectionUI();
}

// ============================================
// Выделение предметов в инвентаре + «Распылить выбранное в Кристаллы»
// ============================================
function updateInventorySelectionUI() {
  const selectAllCb = document.getElementById("inventory-select-all");
  const countLabel = document.getElementById("inventory-selected-count");
  const disintegrateBtn = document.getElementById("disintegrate-btn");
  const totalLabel = document.getElementById("disintegrate-total");

  const selectedCount = state.selectedInventoryIds.size;
  const totalCount = state.inventory.length;

  selectAllCb.checked = totalCount > 0 && selectedCount === totalCount;
  selectAllCb.indeterminate = selectedCount > 0 && selectedCount < totalCount;
  countLabel.textContent = selectedCount > 0 ? `${selectedCount}/${totalCount}` : "";

  const selectedValue = state.inventory
    .filter(i => state.selectedInventoryIds.has(i.id))
    .reduce((sum, i) => sum + i.price, 0);

  disintegrateBtn.disabled = selectedCount === 0;
  totalLabel.textContent = selectedCount > 0 ? `— ${fmt(selectedValue)}` : "";
}

document.getElementById("inventory-select-all").addEventListener("change", (e) => {
  if (e.target.checked) {
    state.inventory.forEach(i => state.selectedInventoryIds.add(i.id));
  } else {
    state.selectedInventoryIds.clear();
  }
  renderInventory();
});

document.getElementById("disintegrate-btn").addEventListener("click", async () => {
  if (!state.selectedInventoryIds.size) {
    tg?.showAlert?.(t("nothing_selected"));
    return;
  }
  const ids = Array.from(state.selectedInventoryIds);
  try {
    const result = await apiPost("/sell-multiple", {
      telegram_id: state.telegramId,
      inventory_ids: ids,
    });
    state.balance = result.new_balance;
    state.inventory = state.inventory.filter(i => !state.selectedInventoryIds.has(i.id));
    state.selectedInventoryIds.clear();
    updateBalanceDisplay();
    renderInventory();
    tg?.showAlert?.(t("disintegrate_success"));
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// Профиль
// ============================================
// ============================================
// Авторизация через Telegram + отрисовка профиля
// ============================================

// Применяет ответ бэкенда (auth или profile) к состоянию и обновляет весь UI.
function applyProfileData(profile) {
  state.telegramId = profile.telegram_id;
  state.username = profile.username;
  state.photoUrl = profile.photo_url || null;
  state.balance = profile.balance;
  state.isVip = profile.is_vip;
  state.vipExpiresAt = profile.vip_expires_at || null;
  if (Array.isArray(profile.inventory)) state.inventory = profile.inventory;

  if (profile.lang) { state.lang = profile.lang; applyTranslations(); }
  if (typeof profile.sound_enabled === "boolean") {
    state.soundEnabled = profile.sound_enabled;
    updateSoundToggleUI();
  }
  updateBalanceDisplay();
  renderProfileScreen(profile);
}

// Только отрисовка DOM вкладки "Профиль" — вызывается после каждого
// обновления данных профиля.
function renderProfileScreen(profile) {
  document.getElementById("profile-name").textContent = state.username || "Игрок";

  const usernameEl = document.getElementById("profile-username");
  if (usernameEl) {
    usernameEl.textContent = profile.telegram_username ? `@${profile.telegram_username}` : `ID ${state.telegramId}`;
  }

  const avatarImg = document.getElementById("profile-avatar-img");
  const avatarFallback = document.getElementById("profile-avatar");
  if (state.photoUrl) {
    avatarImg.src = state.photoUrl;
    avatarImg.style.display = "block";
    avatarFallback.style.display = "none";
  } else {
    avatarImg.style.display = "none";
    avatarFallback.style.display = "flex";
  }

  const vipBadge = document.getElementById("profile-vip-pill");
  if (vipBadge) vipBadge.style.display = state.isVip ? "inline-flex" : "none";

  document.getElementById("stat-cases").textContent = profile.total_cases_opened ?? 0;
  document.getElementById("stat-inventory-value").textContent = fmt(profile.inventory_total_value ?? 0);
  document.getElementById("stat-favorite").textContent = profile.favorite_case || "—";
  document.getElementById("stat-top-drop").textContent =
    profile.most_expensive_item ? profile.most_expensive_item.name : "—";

  document.getElementById("ref-link-input").value =
    `https://t.me/${state.botUsername}?start=ref_${state.telegramId}`;
  document.getElementById("ref-hint").textContent =
    `+${state.refBonusInviter} 💎 ${state.lang === "en" ? "for you and" : "тебе и"} +${state.refBonusInvited} 💎 ${state.lang === "en" ? "for a friend for every invite" : "другу за каждого приглашённого"}`;
}

// Реальный логин: один раз при старте приложения. Проверяет initData на
// бэкенде и создаёт/подтягивает юзера. Если приложение открыто вне Telegram
// (initData пустой — например, тестирование в обычном браузере), используем
// dev-эндпоинт, который работает только при config.DEV_MODE=True на сервере.
async function authenticate() {
  try {
    if (tg?.initData) {
      const profile = await apiPost("/auth/telegram", { init_data: tg.initData });
      state.authenticated = true;
      applyProfileData(profile);
      return;
    }
    console.warn("Telegram.WebApp.initData пуст — вход через dev-режим (не для продакшна).");
    const profile = await apiPost("/auth/telegram/dev", {
      telegram_id: state.telegramId,
      username: state.username,
      photo_url: state.photoUrl,
    });
    state.authenticated = true;
    applyProfileData(profile);
  } catch (e) {
    console.error("Ошибка авторизации:", e);
    tg?.showAlert?.(
      state.lang === "en"
        ? "Login failed. Please reopen the app from Telegram."
        : "Не удалось войти. Перезапусти приложение через Telegram."
    );
  }
}

// Лёгкое обновление уже залогиненного профиля (переключение на вкладку,
// после покупок/продаж и т.д.) — без повторной проверки initData.
async function refreshProfile() {
  if (!state.authenticated) return authenticate();
  try {
    const profile = await apiGet(`/user/profile?telegram_id=${state.telegramId}`);
    applyProfileData(profile);
  } catch (e) {
    console.error("Ошибка обновления профиля:", e);
  }
}

// Старое имя оставлено как алиас, чтобы не трогать остальные ~30 мест
// в коде, которые уже вызывают loadProfile() после покупок/продаж/промо.
async function loadProfile() {
  await refreshProfile();
}

document.getElementById("copy-ref-btn").addEventListener("click", () => {
  const input = document.getElementById("ref-link-input");
  input.select();
  navigator.clipboard?.writeText(input.value);
  tg?.showAlert?.(t("link_copied"));
});

document.getElementById("apply-promo-btn").addEventListener("click", async () => {
  const code = document.getElementById("promo-input").value.trim();
  if (!code) return;
  try {
    const result = await apiPost("/promo", { telegram_id: state.telegramId, code });
    tg?.showAlert?.(result.message);
    loadProfile();
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// Обновление баланса в UI
// ============================================
function updateBalanceDisplay() {
  document.getElementById("balance-value").textContent = fmtNumber(state.balance);
  document.getElementById("vip-pill").style.display = state.isVip ? "block" : "none";
  // VIP отключает рекламу (см. README) — баннер прячем полностью.
  // Для не-VIP уважаем ручное закрытие крестиком — не выскакивает обратно на каждый апдейт баланса.
  const banner = document.getElementById("ad-banner");
  if (banner) banner.style.display = state.isVip ? "none" : (state.adBannerDismissed ? "none" : "flex");
  const caseOpenBalance = document.getElementById("case-open-balance-value");
  if (caseOpenBalance) caseOpenBalance.textContent = fmtNumber(state.balance);
  updateOpenCaseBtnLabel();
}

// ============================================
// Adsgram: баннер + rewarded видео + interstitial
// ============================================
document.getElementById("ad-banner-close").addEventListener("click", () => {
  state.adBannerDismissed = true;
  document.getElementById("ad-banner").style.display = "none";
});

// Контроллер инициализируется ОДИН раз на blockId и переиспользуется —
// повторный Adsgram.init() на каждый клик не нужен и не рекомендован SDK.
let adsgramController = null;

function getAdsgramController() {
  if (!state.adsgramBlockId) return null;
  if (!window.Adsgram) return null; // SDK не подгрузился (например, домен заблокирован)
  if (!adsgramController) {
    adsgramController = window.Adsgram.init({ blockId: state.adsgramBlockId });
  }
  return adsgramController;
}

// Показывает rewarded-блок Adsgram и возвращает Promise, который резолвится
// только если пользователь досмотрел ролик до конца (событие reward).
function showAdsgramRewarded() {
  const controller = getAdsgramController();
  if (!controller) {
    // Фолбэк для локальной разработки без реального SDK/blockId
    return new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return controller.show();
}

document.getElementById("watch-ad-btn").addEventListener("click", async () => {
  const btn = document.getElementById("watch-ad-btn");
  btn.disabled = true;
  try {
    await showAdsgramRewarded();

    const result = await apiPost("/ad-reward", {
      telegram_id: state.telegramId,
    });

    state.balance = result.new_balance;
    updateBalanceDisplay();
    tg?.showAlert?.(`+${result.reward.toLocaleString()} 💎 ${t("ad_reward_toast")}`);
  } catch (e) {
    // Adsgram отклоняет промис, если реклама недоступна или пользователь пропустил ролик
    tg?.showAlert?.(e?.message || t("ads_unavailable"));
  } finally {
    btn.disabled = false;
  }
});

// Interstitial (без награды) каждые 100-250 открытых кейсов — использует тот же
// рекламный блок Adsgram; если SDK/реклама недоступны, показывает локальную заглушку с таймером.
function maybeShowInterstitial() {
  if (state.isVip) return; // VIP отключает рекламу — счётчик даже не тратим впустую
  const threshold = 100 + Math.floor(Math.random() * 150);
  if (state.casesOpenedSinceAd < threshold) return;

  state.casesOpenedSinceAd = 0;
  const controller = getAdsgramController();

  if (controller) {
    controller.show().catch(() => {}).finally(() => {});
    return;
  }

  // Фолбэк: локальная заглушка с обратным отсчётом
  const overlay = document.getElementById("interstitial-overlay");
  const timerEl = document.getElementById("interstitial-timer");
  overlay.classList.add("active");

  let seconds = 5;
  timerEl.textContent = seconds;
  const interval = setInterval(() => {
    seconds--;
    timerEl.textContent = seconds;
    if (seconds <= 0) {
      clearInterval(interval);
      overlay.classList.remove("active");
    }
  }, 1000);
}

// ============================================
// Кнопка «Бонус 💎 2000» — таймер повторного получения раз в 60 секунд
// ============================================
let bonusCountdownInterval = null;

function startBonusCountdown(secondsLeft) {
  const btn = document.getElementById("claim-bonus-btn");
  clearInterval(bonusCountdownInterval);

  if (secondsLeft <= 0) {
    btn.disabled = false;
    btn.classList.remove("on-cooldown");
    btn.textContent = t("bonus_btn");
    return;
  }

  btn.disabled = true;
  btn.classList.add("on-cooldown");
  let remaining = Math.ceil(secondsLeft);
  btn.textContent = `${t("bonus_wait_prefix")} ${remaining}с`;

  bonusCountdownInterval = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(bonusCountdownInterval);
      btn.disabled = false;
      btn.classList.remove("on-cooldown");
      btn.textContent = t("bonus_btn");
    } else {
      btn.textContent = `${t("bonus_wait_prefix")} ${remaining}с`;
    }
  }, 1000);
}

async function loadBonusStatus() {
  try {
    const res = await apiGet(`/bonus-status?telegram_id=${state.telegramId}`);
    startBonusCountdown(res.seconds_left);
  } catch (e) {
    console.error("Ошибка загрузки статуса бонуса:", e);
  }
}

document.getElementById("claim-bonus-btn").addEventListener("click", async () => {
  try {
    const result = await apiPost("/bonus-claim", { telegram_id: state.telegramId });
    state.balance = result.new_balance;
    updateBalanceDisplay();
    tg?.showAlert?.(`+${result.reward.toLocaleString()} 💎 ${t("bonus_claimed_toast")}`);
    startBonusCountdown(result.cooldown_seconds);
  } catch (e) {
    tg?.showAlert?.(e?.message || t("ads_unavailable"));
  }
});

// ============================================
// Ежедневный бонус (Daily Streak, 1-7 день)
// ============================================
const DAILY_DAY_ICONS = { balance: "💎", skin: "🔫", promo: "🎟️", jackpot: "🏆" };

function dailyRewardLabel(rewardDef) {
  if (rewardDef.type === "balance") return `${rewardDef.amount} 💎`;
  if (rewardDef.type === "skin") return t("daily_reward_skin");
  if (rewardDef.type === "promo") return `${rewardDef.amount} 💎`;
  if (rewardDef.type === "jackpot") return `${rewardDef.amount} 💎 + 🏆`;
  return "";
}

function renderDailyDays(data) {
  const grid = document.getElementById("daily-days-grid");
  grid.innerHTML = "";
  data.rewards.forEach(r => {
    const isClaimedDay = r.day < data.current_day || (r.day === data.current_day && data.claimed_today);
    const isCurrent = r.day === data.current_day && !data.claimed_today;
    const el = document.createElement("div");
    el.className = `daily-day-card ${isClaimedDay ? "claimed" : ""} ${isCurrent ? "current" : ""} ${r.type === "jackpot" ? "jackpot" : ""}`.trim();
    el.innerHTML = `
      <div class="day-num">${t("daily_day_label").replace("{n}", r.day)}</div>
      <div class="day-icon">${DAILY_DAY_ICONS[r.type] || "💎"}</div>
      <div class="day-reward">${dailyRewardLabel(r)}</div>
    `;
    grid.appendChild(el);
  });

  document.getElementById("daily-streak-label").innerHTML =
    t("daily_streak_label").replace("{n}", `<b>${data.streak}</b>`);

  const btn = document.getElementById("daily-claim-btn");
  btn.textContent = data.claimed_today ? t("daily_claimed_btn") : t("daily_claim_btn");
  btn.disabled = !!data.claimed_today;
}

async function loadDailyStatus() {
  try {
    const data = await apiGet(`/daily-status?telegram_id=${state.telegramId}`);
    state.dailyStatus = data;
    renderDailyDays(data);
  } catch (e) {
    console.error("Ошибка загрузки ежедневного статуса:", e);
  }
}

function openDailyModal() {
  document.getElementById("daily-modal").classList.add("active");
  loadDailyStatus();
}

document.getElementById("open-daily-modal-btn").addEventListener("click", openDailyModal);

document.getElementById("daily-close-btn").addEventListener("click", () => {
  document.getElementById("daily-modal").classList.remove("active");
});
document.getElementById("daily-modal").addEventListener("click", (e) => {
  if (e.target.id === "daily-modal") e.currentTarget.classList.remove("active");
});

function showDailyResult(result) {
  document.getElementById("daily-modal").classList.remove("active");
  const reward = result.reward;

  const icon = document.getElementById("daily-result-icon");
  const nameEl = document.getElementById("daily-result-name");
  const valueEl = document.getElementById("daily-result-value");
  const promoEl = document.getElementById("daily-result-promo");
  promoEl.style.display = "none";

  if (reward.type === "balance") {
    icon.textContent = "💎";
    nameEl.textContent = t("daily_day_label").replace("{n}", reward.day);
    valueEl.textContent = fmt(reward.amount);
  } else if (reward.type === "skin") {
    icon.textContent = "🔫";
    nameEl.textContent = `${t("daily_reward_skin")} ${reward.skin.name}`;
    valueEl.textContent = fmt(reward.skin.price);
  } else if (reward.type === "promo") {
    icon.textContent = "🎟️";
    nameEl.textContent = t("daily_reward_promo");
    valueEl.textContent = fmt(reward.amount);
    promoEl.style.display = "block";
    promoEl.textContent = `${t("daily_promo_hint")} ${reward.promo_code}`;
  } else if (reward.type === "jackpot") {
    icon.textContent = "🏆";
    nameEl.textContent = `${t("daily_reward_jackpot")} ${reward.skin.name}`;
    valueEl.textContent = fmt(reward.amount + reward.skin.price);
  }

  playSound(reward.type === "skin" || reward.type === "jackpot" ? "fanfare" : "win");
  haptic("success");
  document.getElementById("daily-result-modal").classList.add("active");
}

document.getElementById("daily-result-ok-btn").addEventListener("click", () => {
  document.getElementById("daily-result-modal").classList.remove("active");
});

document.getElementById("daily-claim-btn").addEventListener("click", async () => {
  try {
    const result = await apiPost("/daily-claim", { telegram_id: state.telegramId });
    state.balance = result.new_balance;
    updateBalanceDisplay();
    showDailyResult(result);
    loadDailyStatus();
  } catch (e) {
    tg?.showAlert?.(e?.message || t("daily_already_claimed_toast"));
  }
});

// ============================================
// ХАБ МИНИ-ИГР — единый полноэкранный контейнер,
// в который динамически подгружается разметка нужной игры.
// ============================================
const GAME_TITLES = {
  rocket: () => `🚀 ${t("game_rocket")}`,
  upgrader: () => `🔺 ${t("game_upgrader")}`,
  wheel: () => `🎡 ${t("game_wheel")}`,
  miner: () => `💣 ${t("game_miner")}`,
  tower: () => `🗼 ${t("game_tower")}`,
  ladder: () => `🪜 ${t("game_ladder")}`,
};

// Если в момент ухода с экрана есть активный сессионный раунд (Минёр/Башня/Лесенка) —
// автоматически заберём текущий выигрыш, чтобы ставка не "зависала" молча.
let activeSessionCashout = null; // async function | null

document.getElementById("games-grid").addEventListener("click", (e) => {
  const card = e.target.closest(".game-icon-card");
  if (!card) return;
  haptic("select");
  openGameScreen(card.dataset.game);
});

// Активная в данный момент игра — нужна, чтобы вызвать её destroy() (отмена RAF/таймеров/canvas)
// при выходе из экрана мини-игры, вне зависимости от того, какая игра сейчас открыта.
let activeGameKey = null;

function openGameScreen(gameKey) {
  // На случай прямого переключения между играми без прохода через "Назад" —
  // подчищаем предыдущую игру перед монтированием новой.
  if (activeGameKey && GAME_TEMPLATES[activeGameKey]?.destroy) {
    try { GAME_TEMPLATES[activeGameKey].destroy(); } catch (e) { /* noop */ }
  }
  activeGameKey = gameKey;
  document.getElementById("game-screen-title").textContent = GAME_TITLES[gameKey]();
  document.getElementById("game-screen-balance-value").textContent = fmtNumber(state.balance);
  document.getElementById("game-screen-body").innerHTML = GAME_TEMPLATES[gameKey].render();
  GAME_TEMPLATES[gameKey].init();
  document.getElementById("game-screen").classList.add("active");
}

document.getElementById("game-screen-back-btn").addEventListener("click", async () => {
  if (activeSessionCashout) {
    try { await activeSessionCashout(); } catch (e) { /* раунд уже закрыт — молча игнорируем */ }
    activeSessionCashout = null;
  }
  if (activeGameKey && GAME_TEMPLATES[activeGameKey]?.destroy) {
    try { GAME_TEMPLATES[activeGameKey].destroy(); } catch (e) { /* noop */ }
  }
  activeGameKey = null;
  document.getElementById("game-screen").classList.remove("active");
  document.getElementById("game-screen-body").innerHTML = "";
});

function updateGameScreenBalance() {
  document.getElementById("game-screen-balance-value").textContent = fmtNumber(state.balance);
  updateBalanceDisplay();
}

function showGameResult(el, text, isWin) {
  el.textContent = text;
  el.className = `game-result-box show ${isWin ? "win" : "lose"}`;
}

// ============================================
// 🚀 РАКЕТА (реализация мини-игры Crash: ставка + множитель для автовывода)
// ============================================
const RocketGame = {
  canvas: null,
  ctx: null,
  rafId: null,
  playing: false,

  render() {
    return `
      <div class="game-panel-desc">${t("crash_desc")}</div>
      <div class="rocket-canvas-wrap">
        <canvas id="rocket-canvas"></canvas>
        <div class="rocket-canvas-overlay">
          <div class="rocket-canvas-multiplier" id="rocket-canvas-mult">1.00x</div>
          <div class="rocket-canvas-status" id="rocket-canvas-status">${t("bet_label")}</div>
        </div>
      </div>
      <div class="mg-row">
        <label class="mg-label">${t("bet_label")}</label>
        <input type="number" id="rocket-bet-input" class="mg-input" min="10" step="10" value="100">
      </div>
      <div class="mg-row">
        <div class="mg-target-row">
          <label class="mg-label">${t("cashout_label")}</label>
          <span id="rocket-target-value">2.0x</span>
        </div>
        <input type="range" id="rocket-target-slider" min="1.1" max="20" step="0.1" value="2.0">
      </div>
      <button class="btn-primary full" id="rocket-play-btn">${t("play_btn")}</button>
      <div class="game-result-box" id="rocket-result"></div>
    `;
  },

  init() {
    this.playing = false;
    this.canvas = document.getElementById("rocket-canvas");
    this.ctx = this.canvas.getContext("2d");
    this.resize();
    this._onResize = () => this.resize();
    window.addEventListener("resize", this._onResize);
    this.drawFrame(1, false, false);

    const slider = document.getElementById("rocket-target-slider");
    slider.addEventListener("input", () => {
      document.getElementById("rocket-target-value").textContent = parseFloat(slider.value).toFixed(1) + "x";
    });

    document.getElementById("rocket-play-btn").addEventListener("click", async () => {
      if (this.playing) return;
      const betAmount = parseFloat(document.getElementById("rocket-bet-input").value);
      const cashoutAt = parseFloat(slider.value);

      if (!betAmount || betAmount <= 0) { tg?.showAlert?.(t("bet_invalid")); return; }
      if (betAmount > state.balance) { tg?.showAlert?.(t("balance_low")); return; }

      const playBtn = document.getElementById("rocket-play-btn");
      playBtn.disabled = true;
      document.getElementById("rocket-result").classList.remove("show");
      haptic("light");

      try {
        const result = await apiPost("/minigames/crash", {
          telegram_id: state.telegramId,
          bet_amount: betAmount,
          cashout_at: cashoutAt,
        });
        this.playFlight(result);
      } catch (e) {
        tg?.showAlert?.(e.message);
        playBtn.disabled = false;
      }
    });
  },

  resize() {
    if (!this.canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, rect.width * dpr);
    this.canvas.height = Math.max(1, rect.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  },

  // Множитель растёт нелинейно — та же кривая, что и в визуальном референсе.
  growthCurve(t) { return 1 + 0.06 * t + 0.015 * t * t; },

  // Подбираем время полёта t так, чтобы growthCurve(t) == targetMultiplier.
  timeForMultiplier(mult) {
    // 0.015t^2 + 0.06t + (1 - mult) = 0
    const a = 0.015, b = 0.06, c = 1 - mult;
    const disc = b * b - 4 * a * c;
    return (-b + Math.sqrt(Math.max(0, disc))) / (2 * a);
  },

  // Уже известный от бэкенда исход разыгрываем как анимацию полёта до этой точки.
  playFlight(result) {
    this.playing = true;
    const crashPoint = parseFloat(result.crash_point);
    const cashoutAt = parseFloat(result.cashout_at);
    const isWin = result.result === "win";
    // Финальная точка полёта на графике — момент взрыва (для проигрыша) или
    // момент фиксации (для победы, дальше рисуем "успешный" кадр).
    const stopMultiplier = isWin ? cashoutAt : crashPoint;
    const stopTime = this.timeForMultiplier(stopMultiplier);

    const statusEl = document.getElementById("rocket-canvas-status");
    const multEl = document.getElementById("rocket-canvas-mult");
    statusEl.textContent = "🚀 " + t("play_btn");
    statusEl.className = "rocket-canvas-status";

    const flightLog = [];
    const startTs = performance.now();
    // Полёт всегда идёт вживую ~2.5–4.5с, независимо от итогового множителя —
    // так короткие и длинные раунды выглядят одинаково динамично.
    const durationMs = Math.min(4500, Math.max(2200, stopTime * 380));

    const tick = (now) => {
      const progress = Math.min(1, (now - startTs) / durationMs);
      const elapsed = progress * stopTime;
      const mult = this.growthCurve(elapsed);
      flightLog.push({ t: elapsed, m: mult });
      multEl.textContent = mult.toFixed(2) + "x";

      this.drawFrame(mult, false, false, flightLog, elapsed);

      if (progress < 1) {
        this.rafId = requestAnimationFrame(tick);
      } else {
        this.finishFlight(isWin, result, flightLog, elapsed);
      }
    };
    this.rafId = requestAnimationFrame(tick);
  },

  finishFlight(isWin, result, flightLog, elapsed) {
    this.playing = false;
    this.rafId = null;
    const statusEl = document.getElementById("rocket-canvas-status");
    const resultBox = document.getElementById("rocket-result");
    document.getElementById("rocket-play-btn").disabled = false;

    state.balance = result.new_balance;
    updateGameScreenBalance();

    if (isWin) {
      this.drawFrame(result.cashout_at, false, true, flightLog, elapsed);
      statusEl.textContent = "✅ " + t("win_toast_prefix");
      statusEl.className = "rocket-canvas-status win";
      showGameResult(resultBox, `🚀 ${result.crash_point}x — ${result.cashout_at}x! +${fmt(result.winnings)}`, true);
      playSound("win");
      haptic("success");
    } else {
      this.drawFrame(result.crash_point, true, false, flightLog, elapsed);
      statusEl.textContent = "💥 " + t("lose_toast");
      statusEl.className = "rocket-canvas-status lose";
      showGameResult(resultBox, `💥 ${result.crash_point}x`, false);
      playSound("lose");
      haptic("error");
    }
  },

  drawFrame(currentMult, exploded, cashed, flightLog, elapsed) {
    const ctx = this.ctx;
    if (!ctx) return;
    const rect = this.canvas.getBoundingClientRect();
    const w = rect.width, h = rect.height;
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
    for (let y = 0; y < h; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }

    const padX = 24, padY = 24;
    const graphW = w - padX * 2, graphH = h - padY * 2;
    const log = flightLog && flightLog.length ? flightLog : [{ t: 0, m: currentMult }];
    const maxT = Math.max(log[log.length - 1].t, 1);
    const maxM = Math.max(currentMult, 1.2);

    const toXY = (t, m) => [padX + (t / maxT) * graphW, h - padY - ((m - 1) / (maxM - 1 || 1)) * graphH];

    if (log.length > 1) {
      ctx.beginPath();
      ctx.strokeStyle = exploded ? "#ff3b30" : "#4a9eff";
      ctx.lineWidth = 3;
      log.forEach((p, i) => { const [x, y] = toXY(p.t, p.m); i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); });
      ctx.stroke();

      const [lx, ly] = toXY(log[log.length - 1].t, log[log.length - 1].m);
      ctx.lineTo(lx, h - padY);
      ctx.lineTo(padX, h - padY);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, exploded ? "rgba(255,59,48,0.22)" : "rgba(74,158,255,0.22)");
      grad.addColorStop(1, "rgba(74,158,255,0)");
      ctx.fillStyle = grad;
      ctx.fill();

      if (exploded) this.drawExplosion(lx, ly);
      else this.drawRocket(lx, ly, elapsed || 0, cashed);
    }
  },

  drawRocket(x, y, t, cashed) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-Math.PI / 4 - Math.min(t * 0.03, 0.4));
    ctx.beginPath();
    ctx.moveTo(-6, 10); ctx.lineTo(0, 22 + Math.sin(t * 8) * 3); ctx.lineTo(6, 10);
    ctx.closePath();
    ctx.fillStyle = "#f89c1c";
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(0, -15); ctx.lineTo(6, 7); ctx.lineTo(-6, 7);
    ctx.closePath();
    ctx.fillStyle = "#e9ecf8";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(0, -2, 3, 0, Math.PI * 2);
    ctx.fillStyle = cashed ? "#34c759" : "#4a9eff";
    ctx.fill();
    ctx.restore();
  },

  drawExplosion(x, y) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(x, y);
    const spikes = 10;
    ctx.beginPath();
    for (let i = 0; i < spikes * 2; i++) {
      const r = i % 2 === 0 ? 20 : 8;
      const a = (Math.PI / spikes) * i;
      const px = Math.cos(a) * r, py = Math.sin(a) * r;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = "#ff3b30";
    ctx.fill();
    ctx.restore();
  },

  destroy() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    this.playing = false;
    if (this._onResize) window.removeEventListener("resize", this._onResize);
    this.canvas = null;
    this.ctx = null;
  },
};

// ============================================
// 🔺 УЛУЧШИТЕЛЬ (мини-игра Upgrade)
// ============================================
function calcUpgradeChance(multiplier) {
  const targetHouseEdge = 0.85;
  let chance = targetHouseEdge / multiplier;
  return Math.max(0.01, Math.min(0.80, chance));
}

const UpgraderGame = {
  render() {
    return `
      <div class="game-panel-desc">${t("upgrade_desc")}</div>
      <select id="upgrader-item-select" class="mg-select"></select>
      <div class="mg-row">
        <label class="mg-label"><span>${t("multiplier_label")}</span>: <span id="upgrader-multiplier-value">2.0x</span></label>
        <input type="range" id="upgrader-multiplier-slider" min="1.1" max="10" step="0.1" value="2.0">
      </div>
      <div class="mg-chance-preview">
        <span>${t("chance_preview_label")}</span>: <span id="upgrader-chance-preview">42%</span>
      </div>
      <button class="btn-primary full" id="upgrader-play-btn">${t("upgrade_btn")}</button>
    `;
  },
  init() {
    this.populateSelect();

    const slider = document.getElementById("upgrader-multiplier-slider");
    slider.addEventListener("input", () => {
      const mult = parseFloat(slider.value);
      document.getElementById("upgrader-multiplier-value").textContent = mult.toFixed(1) + "x";
      document.getElementById("upgrader-chance-preview").textContent = (calcUpgradeChance(mult) * 100).toFixed(0) + "%";
    });

    document.getElementById("upgrader-play-btn").addEventListener("click", async () => {
      const itemId = document.getElementById("upgrader-item-select").value;
      const multiplier = parseFloat(slider.value);

      if (!itemId) { tg?.showAlert?.(t("select_item_first")); return; }

      try {
        const result = await apiPost("/minigames/upgrade", {
          telegram_id: state.telegramId,
          inventory_id: Number(itemId),
          target_multiplier: multiplier,
        });

        playSound(result.result === "win" ? "win" : "lose");
        tg?.showAlert?.(result.result === "win" ? `${t("upgrade_success")} ${fmt(result.new_price)}` : t("upgrade_fail"));

        state.inventory = state.inventory.filter(i => i.id !== Number(itemId));
        this.populateSelect();
        renderInventory();
        loadProfile();
      } catch (e) {
        tg?.showAlert?.(e.message);
      }
    });
  },
  populateSelect() {
    const select = document.getElementById("upgrader-item-select");
    if (!select) return;
    select.innerHTML = "";
    if (!state.inventory.length) {
      select.innerHTML = `<option value="">${t("inventory_empty")}</option>`;
      return;
    }
    state.inventory.forEach(item => {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = `${item.name} — ${fmt(item.price)}`;
      select.appendChild(opt);
    });
  },
};

// ============================================
// 🎡 КОЛЕСО (Wheel)
// ============================================
const WheelGame = {
  // Тот же порядок сегментов, что и WHEEL_SEGMENTS в main.py — используется только
  // для отрисовки диска ДО ответа сервера; финальный множитель всегда берётся из API.
  segments: [0, 0.3, 0.5, 0.5, 1, 1, 1.5, 1.5, 2, 3, 5, 10],
  colors: ["#3a4352", "#4a9eff", "#34c759", "#34c759", "#f89c1c", "#f89c1c", "#d32ce6", "#d32ce6", "#eb4b4b", "#eb4b4b", "#ffd700", "#ffd700"],
  totalRotation: 0,

  render() {
    const segCount = this.segments.length;
    const step = 360 / segCount;
    const gradientStops = this.segments.map((_, i) => `${this.colors[i]} ${i * step}deg ${(i + 1) * step}deg`).join(", ");

    let labels = "";
    this.segments.forEach((mult, i) => {
      const angle = i * step + step / 2;
      labels += `<div class="wheel-segment-label" style="transform: rotate(${angle}deg) translate(90px) rotate(-${angle}deg);">${mult}x</div>`;
    });

    return `
      <div class="game-panel-desc">${t("wheel_desc")}</div>
      <div class="wheel-wrapper">
        <div class="wheel-pointer"></div>
        <div class="wheel-disc" id="wheel-disc" style="background: conic-gradient(${gradientStops});">
          <div class="wheel-segment-labels">${labels}</div>
        </div>
      </div>
      <div class="mg-row">
        <label class="mg-label">${t("bet_label")}</label>
        <input type="number" id="wheel-bet-input" class="mg-input" min="10" step="10" value="100">
      </div>
      <button class="btn-primary full" id="wheel-spin-btn">${t("spin_btn")}</button>
      <div class="game-result-box" id="wheel-result"></div>
    `;
  },

  init() {
    this.totalRotation = 0;
    document.getElementById("wheel-spin-btn").addEventListener("click", async () => {
      const betInput = document.getElementById("wheel-bet-input");
      const betAmount = parseFloat(betInput.value);
      const spinBtn = document.getElementById("wheel-spin-btn");

      if (!betAmount || betAmount <= 0) { tg?.showAlert?.(t("bet_invalid")); return; }
      if (betAmount > state.balance) { tg?.showAlert?.(t("balance_low")); return; }

      spinBtn.disabled = true;
      document.getElementById("wheel-result").classList.remove("show");
      document.querySelector(".wheel-wrapper")?.classList.remove("glow-win", "glow-lose");
      haptic("light");

      try {
        const result = await apiPost("/minigames/wheel", {
          telegram_id: state.telegramId,
          bet_amount: betAmount,
        });

        const segCount = this.segments.length;
        const step = 360 / segCount;
        const segmentCenter = result.segment_index * step + step / 2;
        // 5 полных оборотов + доворот так, чтобы центр выпавшего сегмента встал под указатель (0deg сверху)
        const extraSpins = 5 * 360;
        const targetOffset = 360 - (segmentCenter % 360);
        this.totalRotation += extraSpins + targetOffset;

        const disc = document.getElementById("wheel-disc");
        disc.style.transform = `rotate(${this.totalRotation}deg)`;

        setTimeout(() => {
          state.balance = result.new_balance;
          updateGameScreenBalance();

          const resultBox = document.getElementById("wheel-result");
          const wrapper = document.querySelector(".wheel-wrapper");
          if (result.result === "win") {
            showGameResult(resultBox, `🎉 ${result.multiplier}x — +${fmt(result.winnings)}`, true);
            playSound("win");
            haptic("success");
            wrapper?.classList.add("glow-win");
          } else {
            showGameResult(resultBox, `${t("lose_toast")} — 0x`, false);
            playSound("lose");
            haptic("error");
            wrapper?.classList.add("glow-lose");
          }
          spinBtn.disabled = false;
        }, 4000);
      } catch (e) {
        tg?.showAlert?.(e.message);
        spinBtn.disabled = false;
      }
    });
  },
};

// ============================================
// 💣 МИНЁР (Mines) — сессионная игра, поле 5×5
// ============================================
const MinerGame = {
  gridSize: 25,
  active: false,
  revealedCount: 0,

  render() {
    let tiles = "";
    for (let i = 0; i < this.gridSize; i++) {
      tiles += `<div class="mine-tile" data-index="${i}">❔</div>`;
    }
    const minesOptions = [1, 2, 3, 5, 7, 10, 15, 24].map(n => `<option value="${n}" ${n === 3 ? "selected" : ""}>${n}</option>`).join("");

    return `
      <div class="game-panel-desc">${t("miner_desc")}</div>
      <div class="mg-row">
        <label class="mg-label">${t("bet_label")}</label>
        <input type="number" id="miner-bet-input" class="mg-input" min="10" step="10" value="100">
      </div>
      <div class="mines-config-row">
        <label class="mg-label">${t("mines_count_label")}</label>
        <select id="miner-mines-select" class="mg-select">${minesOptions}</select>
      </div>
      <div class="game-multiplier-readout" id="miner-multiplier">1.00x</div>
      <div class="mines-grid" id="miner-grid">${tiles}</div>
      <div class="game-btn-row">
        <button class="btn-secondary" id="miner-start-btn">${t("start_round_btn")}</button>
        <button class="btn-primary" id="miner-cashout-btn" disabled>${t("cashout_btn")}</button>
      </div>
      <div class="game-result-box" id="miner-result"></div>
    `;
  },

  init() {
    this.active = false;
    this.revealedCount = 0;
    activeSessionCashout = null;

    document.getElementById("miner-start-btn").addEventListener("click", () => this.startRound());
    document.getElementById("miner-cashout-btn").addEventListener("click", () => this.cashout());
    document.getElementById("miner-grid").addEventListener("click", (e) => {
      const tile = e.target.closest(".mine-tile");
      if (!tile || !this.active) return;
      this.reveal(Number(tile.dataset.index));
    });
  },

  resetGridUI() {
    document.querySelectorAll("#miner-grid .mine-tile").forEach(t => {
      t.textContent = "❔";
      t.className = "mine-tile";
    });
  },

  async startRound() {
    const betAmount = parseFloat(document.getElementById("miner-bet-input").value);
    const minesCount = Number(document.getElementById("miner-mines-select").value);

    if (!betAmount || betAmount <= 0) { tg?.showAlert?.(t("bet_invalid")); return; }
    if (betAmount > state.balance) { tg?.showAlert?.(t("balance_low")); return; }

    try {
      const result = await apiPost("/minigames/mines/start", {
        telegram_id: state.telegramId,
        bet_amount: betAmount,
        mines_count: minesCount,
      });

      state.balance = result.new_balance;
      updateGameScreenBalance();

      this.active = true;
      this.revealedCount = 0;
      this.betAmount = betAmount;
      this.resetGridUI();
      document.getElementById("miner-multiplier").textContent = "1.00x";
      document.getElementById("miner-cashout-btn").disabled = true;
      document.getElementById("miner-result").classList.remove("show");
      document.getElementById("miner-start-btn").disabled = true;
      document.getElementById("miner-bet-input").disabled = true;
      document.getElementById("miner-mines-select").disabled = true;
      activeSessionCashout = () => this.cashout(true);
      haptic("medium");
    } catch (e) {
      tg?.showAlert?.(e.message);
    }
  },

  async reveal(index) {
    const tile = document.querySelector(`#miner-grid .mine-tile[data-index="${index}"]`);
    if (!tile || tile.classList.contains("safe") || tile.classList.contains("bomb")) return;

    try {
      const result = await apiPost("/minigames/mines/reveal", {
        telegram_id: state.telegramId,
        tile_index: index,
      });

      if (result.result === "bust") {
        tile.textContent = "💥";
        tile.className = "mine-tile bomb exploded";
        haptic("error");
        let delay = 60;
        (result.mine_positions || []).forEach(pos => {
          const el = document.querySelector(`#miner-grid .mine-tile[data-index="${pos}"]`);
          if (el && !el.classList.contains("bomb")) {
            setTimeout(() => { el.textContent = "💣"; el.className = "mine-tile bomb opened disabled"; }, delay);
            delay += 60;
          }
        });
        this.endRound(false, 0);
        return;
      }

      tile.textContent = "💎";
      tile.className = "mine-tile safe opened";
      this.revealedCount = result.revealed_count || (this.revealedCount + 1);
      document.getElementById("miner-multiplier").textContent = `${result.multiplier.toFixed(2)}x`;
      document.getElementById("miner-cashout-btn").disabled = false;
      haptic("light");

      if (result.result === "cleared") {
        state.balance = result.new_balance;
        updateGameScreenBalance();
        this.endRound(true, result.winnings);
      }
    } catch (e) {
      tg?.showAlert?.(e.message);
    }
  },

  async cashout(silent = false) {
    if (!this.active) return;
    try {
      const result = await apiPost("/minigames/mines/cashout", { telegram_id: state.telegramId });
      state.balance = result.new_balance;
      updateGameScreenBalance();
      if (!silent) this.endRound(result.winnings > 0, result.winnings);
      else this.active = false;
    } catch (e) {
      if (!silent) tg?.showAlert?.(e.message);
    }
  },

  endRound(isWin, winnings) {
    this.active = false;
    activeSessionCashout = null;
    document.getElementById("miner-cashout-btn").disabled = true;
    document.getElementById("miner-start-btn").disabled = false;
    document.getElementById("miner-bet-input").disabled = false;
    document.getElementById("miner-mines-select").disabled = false;
    document.querySelectorAll("#miner-grid .mine-tile").forEach(t => t.classList.add("disabled"));

    const resultBox = document.getElementById("miner-result");
    if (isWin) {
      showGameResult(resultBox, `${t("cleared_msg")} +${fmt(winnings)}`, true);
      playSound("win");
      haptic("success");
    } else {
      showGameResult(resultBox, t("bust_msg"), false);
      playSound("lose");
    }
    setTimeout(() => this.resetGridUI(), 1400);
  },
};

// ============================================
// 🗼 БАШНЯ / 🪜 ЛЕСЕНКА — общая механика "climb" (уровни, 1 бомба на уровень)
// ============================================
function createClimbGame(gameType, levelsTotal, tilesPerLevel) {
  return {
    active: false,
    level: 0,

    render() {
      return `
        <div class="game-panel-desc">${t(gameType === "tower" ? "tower_desc" : "ladder_desc")}</div>
        <div class="mg-row">
          <label class="mg-label">${t("bet_label")}</label>
          <input type="number" id="${gameType}-bet-input" class="mg-input" min="10" step="10" value="100">
        </div>
        <div class="game-multiplier-readout" id="${gameType}-multiplier">1.00x</div>
        <div class="climb-frame">
          <div class="climb-rail"><div class="climb-rail-fill" id="${gameType}-rail-fill"></div></div>
          <div class="climb-levels" id="${gameType}-levels"></div>
        </div>
        <div class="game-btn-row">
          <button class="btn-secondary" id="${gameType}-start-btn">${t("start_round_btn")}</button>
          <button class="btn-primary" id="${gameType}-cashout-btn" disabled>${t("cashout_btn")}</button>
        </div>
        <div class="game-result-box" id="${gameType}-result"></div>
      `;
    },

    init() {
      this.active = false;
      this.level = 0;
      activeSessionCashout = null;
      document.getElementById(`${gameType}-start-btn`).addEventListener("click", () => this.startRound());
      document.getElementById(`${gameType}-cashout-btn`).addEventListener("click", () => this.cashout());
    },

    buildLevels() {
      const container = document.getElementById(`${gameType}-levels`);
      container.innerHTML = "";
      // column-reverse в CSS уже переворачивает порядок на экране (уровень 1 внизу),
      // поэтому в разметке идём от последнего уровня к первому — держим DOM-порядок предсказуемым.
      for (let lvl = 1; lvl <= levelsTotal; lvl++) {
        const row = document.createElement("div");
        row.className = "climb-level-row" + (lvl === 1 ? " active" : " locked");
        row.dataset.level = lvl;
        let tiles = `<div class="climb-level-tag">${t("level_label")} ${lvl}</div>`;
        for (let i = 0; i < tilesPerLevel; i++) {
          tiles += `<div class="climb-tile" data-index="${i}">❔</div>`;
        }
        row.innerHTML = tiles;
        container.appendChild(row);
      }
      container.querySelectorAll(".climb-tile").forEach(tile => {
        tile.addEventListener("click", () => {
          const row = tile.closest(".climb-level-row");
          if (Number(row.dataset.level) !== this.level + 1 || !this.active) return;
          this.pick(Number(tile.dataset.index), row, tile);
        });
      });
      this.updateRail();
    },

    updateRail() {
      const rail = document.getElementById(`${gameType}-rail-fill`);
      if (rail) rail.style.height = Math.round((this.level / levelsTotal) * 100) + "%";
    },

    async startRound() {
      const betAmount = parseFloat(document.getElementById(`${gameType}-bet-input`).value);
      if (!betAmount || betAmount <= 0) { tg?.showAlert?.(t("bet_invalid")); return; }
      if (betAmount > state.balance) { tg?.showAlert?.(t("balance_low")); return; }

      try {
        const result = await apiPost(`/minigames/${gameType}/start`, {
          telegram_id: state.telegramId,
          bet_amount: betAmount,
        });

        state.balance = result.new_balance;
        updateGameScreenBalance();

        this.active = true;
        this.level = 0;
        this.betAmount = betAmount;
        this.buildLevels();
        document.getElementById(`${gameType}-multiplier`).textContent = "1.00x";
        document.getElementById(`${gameType}-cashout-btn`).disabled = true;
        document.getElementById(`${gameType}-result`).classList.remove("show");
        document.getElementById(`${gameType}-start-btn`).disabled = true;
        document.getElementById(`${gameType}-bet-input`).disabled = true;
        activeSessionCashout = () => this.cashout(true);
        haptic("medium");
      } catch (e) {
        tg?.showAlert?.(e.message);
      }
    },

    async pick(tileIndex, row, tile) {
      try {
        const result = await apiPost(`/minigames/${gameType}/pick`, {
          telegram_id: state.telegramId,
          tile_index: tileIndex,
        });

        if (result.result === "bust") {
          tile.textContent = "💥";
          tile.classList.add("bomb");
          (result.bomb_tiles || []).forEach(idx => {
            const other = row.querySelector(`.climb-tile[data-index="${idx}"]`);
            if (other && other !== tile) { other.textContent = "💣"; other.classList.add("bomb"); }
          });
          row.classList.remove("active");
          row.classList.add("done");
          haptic("error");
          this.endRound(false, 0);
          return;
        }

        tile.textContent = "✅";
        tile.classList.add("safe");
        row.classList.remove("active");
        row.classList.add("done");
        this.level = result.level;
        document.getElementById(`${gameType}-multiplier`).textContent = `${result.multiplier.toFixed(2)}x`;
        document.getElementById(`${gameType}-cashout-btn`).disabled = false;
        this.updateRail();
        haptic("light");

        if (result.result === "cleared") {
          state.balance = result.new_balance;
          updateGameScreenBalance();
          this.endRound(true, result.winnings);
          return;
        }

        const nextRow = document.querySelector(`#${gameType}-levels .climb-level-row[data-level="${this.level + 1}"]`);
        if (nextRow) { nextRow.classList.remove("locked"); nextRow.classList.add("active"); }
      } catch (e) {
        tg?.showAlert?.(e.message);
      }
    },

    async cashout(silent = false) {
      if (!this.active) return;
      try {
        const result = await apiPost(`/minigames/${gameType}/cashout`, { telegram_id: state.telegramId });
        state.balance = result.new_balance;
        updateGameScreenBalance();
        if (!silent) { this.endRound(result.winnings > 0, result.winnings); haptic(result.winnings > 0 ? "success" : "warning"); }
        else this.active = false;
      } catch (e) {
        if (!silent) tg?.showAlert?.(e.message);
      }
    },

    endRound(isWin, winnings) {
      this.active = false;
      activeSessionCashout = null;
      document.getElementById(`${gameType}-cashout-btn`).disabled = true;
      document.getElementById(`${gameType}-start-btn`).disabled = false;
      document.getElementById(`${gameType}-bet-input`).disabled = false;

      const resultBox = document.getElementById(`${gameType}-result`);
      if (isWin) {
        showGameResult(resultBox, `${t("cleared_msg")} +${fmt(winnings)}`, true);
        playSound("win");
      } else {
        showGameResult(resultBox, t("bust_msg"), false);
        playSound("lose");
      }
    },
  };
}

const TowerGame = createClimbGame("tower", 8, 3);
const LadderGame = createClimbGame("ladder", 5, 2);

const GAME_TEMPLATES = {
  rocket: RocketGame,
  upgrader: UpgraderGame,
  wheel: WheelGame,
  miner: MinerGame,
  tower: TowerGame,
  ladder: LadderGame,
};

// ============================================
// VIP покупка / Розыгрыши — переход в бота
// ============================================
// ============================================
// Покупка VIP через Telegram Stars — прямо из Mini App
// ============================================
document.getElementById("buy-vip-btn").addEventListener("click", async () => {
  if (state.isVip) {
    tg?.showAlert?.(state.lang === "en" ? "You already have VIP!" : "У тебя уже есть VIP!");
    return;
  }
  if (!tg?.openInvoiceLink) {
    // Мы не внутри Telegram (например, тестирование в браузере) — оплата Stars недоступна
    tg?.showAlert?.(t("vip_hint"));
    return;
  }

  try {
    const { invoice_link } = await apiPost("/vip/create-invoice-link", { telegram_id: state.telegramId });
    tg.openInvoiceLink(invoice_link, (status) => {
      // Само зачисление VIP делает бот (см. bot.py: F.successful_payment) —
      // здесь только обновляем экран после того, как Telegram сообщил об оплате.
      if (status === "paid") {
        tg?.showAlert?.(state.lang === "en" ? "Payment successful! VIP activated." : "Оплата прошла успешно! VIP активирован.");
        refreshProfile();
      } else if (status === "failed") {
        tg?.showAlert?.(state.lang === "en" ? "Payment failed." : "Оплата не прошла.");
      }
    });
  } catch (e) {
    tg?.showAlert?.(e.message || (state.lang === "en" ? "Could not start VIP purchase." : "Не удалось начать покупку VIP."));
  }
});

document.getElementById("open-giveaways").addEventListener("click", () => {
  tg?.showAlert?.(t("giveaways_soon"));
});

// ============================================
// Инициализация приложения
// ============================================
(async function init() {
  // язык/звук: сначала локальные настройки устройства (для мгновенного UI)
  const savedLang = localStorage.getItem("cs2_lang");
  if (savedLang) state.lang = savedLang;
  const savedSound = localStorage.getItem("cs2_sound");
  if (savedSound !== null) state.soundEnabled = savedSound === "1";
  applyTranslations();
  updateSoundToggleUI();

  try {
    const cfg = await apiGet("/app-config");
    state.botUsername = cfg.bot_username;
    state.adsgramBlockId = cfg.adsgram_block_id;
    state.refBonusInviter = cfg.ref_bonus_inviter;
    state.refBonusInvited = cfg.ref_bonus_invited;
    state.vipPriceStars = cfg.vip_price_stars || state.vipPriceStars;
  } catch (e) {
    console.error("Ошибка загрузки конфигурации:", e);
  }

  // Сначала логинимся (проверка initData на сервере, auto-create юзера) —
  // остальные запросы используют уже подтверждённый telegram_id.
  await authenticate();
  await loadCases();
  await loadInventory();
  await loadBonusStatus();
  await loadDailyStatus();
})();
