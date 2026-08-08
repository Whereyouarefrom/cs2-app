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
  goldBalance: 0,
  isVip: false,
  vipExpiresAt: null,
  lang: "ru",
  soundEnabled: true,
  currency: "RUB",
  currencyRates: { RUB: 1, USD: 1 / 90, UAH: 1 / 2.2 }, // фолбэк, перезаписывается из /app-config при старте
  background: "dark",       // Спринт 12: активный фон симулятора, см. BACKGROUND_OPTIONS
  backgroundOptions: [],    // каталог фонов, приходит из /app-config
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
  refCommissionPercent: 0.05, // фолбэк, перезаписывается из /app-config (config.REF_COMMISSION_PERCENT)
  referralsCount: 0,          // сколько друзей приглашено (из профиля)
  refEarningsTotal: 0,        // сколько 💎 пассивно получено с активности рефералов (из профиля)
  vipPriceStars: 25,
  openCount: 1,
  openSpeed: "slow",
  lastMultiDrops: [],
  selectedInventoryIds: new Set(),
  inventorySortDir: "desc", // сортировка инвентаря по цене: desc (дорогие сначала) | asc (дешёвые сначала)
  dailyStatus: null,
  lastProfile: null, // последний полный профиль с бэкенда — для перерисовки при смене валюты без лишнего запроса
  // ---- Ежедневное колесо удачи (Спринт 6) ----
  wheelStatus: null,
  wheelSectorsRendered: false,
  wheelSpinning: false,
  wheelCountdownInterval: null,
  wheelCurrentRotation: 0, // накопительный угол диска — не даёт колесу "крутиться назад" между спинами
  rankUpQueue: [],       // очередь событий повышения ранга, ждущих показа модалки
  rankUpModalActive: false,
  // ---- Уровень аккаунта / витрина (Спринт 10) ----
  levelUpQueue: [],        // очередь повышений уровня аккаунта (формула 100*1.15^(N-1))
  levelUpModalActive: false,
  itemDetailId: null,      // id предмета, открытого в карточке Float/StatTrak
  // ---- Крафт / Trade-Up ----
  craftFeeByRarity: {},
  craftItemsRequired: 5,
  craftCatalog: null,        // {rarity: [{name, rarity, image, base_price}]} — грузится один раз
  craftSourceRarity: null,   // редкость, которую сейчас собирает игрок (null пока ничего не выбрано)
  craftSelectedIds: new Set(),
  craftTargetName: null,
};

// ============================================
// i18n
// ============================================
const I18N = {
  ru: {
    cases_title: "Кейсы", inventory_title: "Инвентарь",
    inventory_empty: "Пока пусто. Открой первый кейс!",
    terms_title: "📜 Пользовательское соглашение",
    terms_accept_btn: "Принять и продолжить",
    profile_title: "Профиль", stat_cases: "Открыто кейсов",
    stat_ref_count: "Приглашено друзей", stat_ref_earnings: "Начислено пассивно",
    stat_inv_value: "Стоимость инвентаря", stat_favorite: "Любимый кейс",
    stat_top_drop: "🏆 Топ дроп", top_drop_empty: "Пока нет ни одного дропа — открой первый кейс!", settings_title: "⚙️ Настройки",
    craft_open_btn: "Крафт", craft_title: "🔧 Крафт", craft_progress_sub: "выбрано",
    craft_rarity_hint: "Выбери 5 предметов ОДНОЙ редкости из инвентаря",
    craft_source_title: "1. Исходные предметы (инвентарь)",
    craft_target_title: "2. Целевой предмет (каталог)",
    craft_fee_label: "Плата за рецепт:", craft_submit_btn: "Скрафтить",
    craft_result_title: "✨ Скрафчено!",
    craft_pick_target_hint: "Выбери, что хочешь получить",
    craft_max_rarity: "Эта редкость уже максимальная — крафтить дальше некуда",
    craft_success: "Готово! Новый предмет уже в инвентаре",
    craft_not_enough_balance: "Не хватает 💎 на оплату рецепта",
    settings_lang: "🌐 Язык", settings_sound: "🔊 Звук", settings_currency: "💱 Валюта", settings_background: "🖼️ Фон симулятора",
    sound_on: "Вкл", sound_off: "Выкл",
    ref_title: "👥 Реферальная ссылка", copy_btn: "Копировать",
    promo_title: "🎁 Промокод", promo_placeholder: "Введите промокод",
    activate_btn: "Активировать", minigames_title: "Мини-игры",
    upgrade_desc: "Выбери предмет из инвентаря и цель — при успехе получишь целевой скин, при неудаче предмет сгорает (но ты получишь утешительный скин).",
    multiplier_label: "Множитель", chance_preview_label: "Примерный шанс успеха",
    upgrade_btn: "Улучшить", crash_desc: "Ставь Кристаллики и укажи, на каком множителе хочешь забрать выигрыш.",
    upgrade_mode_item: "Выбрать скин", upgrade_mode_price: "Своя цена", upgrade_mode_multiplier: "Множитель", upgrade_mode_chance: "Шанс",
    upgrade_search_placeholder: "Поиск скина по названию…", upgrade_search_empty: "Ничего не найдено",
    upgrade_target_price_label: "Желаемая стоимость (💎)", upgrade_target_price_placeholder: "Например, 2500",
    upgrade_your_item_label: "Твой предмет", upgrade_target_label: "Цель",
    sort_price_label: "Цена", upgrade_max_items_hint: "Можно выбрать до 6 предметов сразу — их стоимость суммируется",
    upgrade_quick_multiplier: "Быстрый множитель", upgrade_quick_chance: "Быстрый шанс",
    upgrade_spin_btn: "Запуск", upgrade_spinning: "Крутим…",
    upgrade_success_title: "🎉 Апгрейд удался!", upgrade_fail_title: "💥 Апгрейд не удался",
    upgrade_fail_desc: "Предмет сгорел. Но ты получил утешительный скин:",
    upgrade_result_ok_btn: "Отлично!", upgrade_pick_item_first: "Сначала выбери предмет для улучшения",
    upgrade_pick_target_first: "Укажи цель апгрейда",
    bet_label: "Ставка (💎)", cashout_label: "Забрать на", play_btn: "Играть",
    earn_title: "Заработать", earn_ad_title: "Посмотреть видео",
    earn_ad_desc: "Получи +2000 💎 виртуального баланса", watch_btn: "Смотреть",
    earn_giveaway_title: "Розыгрыши", earn_giveaway_desc: "Участвуй и выигрывай редкие скины",
    earn_vip_title: "VIP-статус", earn_vip_desc: "Без рекламы + косметические бонусы",
    buy_btn: "Купить", tab_cases: "Кейсы", tab_inventory: "Инвентарь",
    tab_profile: "Профиль", tab_minigames: "Мини-игры", tab_earn: "Заработать", tab_chat: "Чат",
    chat_title: "Глобальный чат", chat_input_ph: "Написать сообщение…", chat_send: "Отправить",
    chat_empty: "Сообщений пока нет. Будь первым!", chat_report: "Пожаловаться",
    chat_report_done: "Жалоба отправлена", chat_muted: "Вы в муте и не можете писать",
    chat_banned: "Вы заблокированы в чате", chat_you: "Вы",
    open_case_btn: "Открыть кейс", contents_title: "📋 Содержимое кейса",
    win_title: "🎉 Выпало!", keep_btn: "В коллекцию", sell_btn: "Продать", open_again_btn: "Открыть ещё",
    insufficient_balance: "Недостаточно Кристалликов 💎. Посмотри рекламу на вкладке «Заработать»!",
    link_copied: "Ссылка скопирована!", sell_label: "Продать",
    upgrade_success: "🎉 Успех! Новая цена:", upgrade_fail: "💥 Неудача. Предмет сгорел.",
    select_item_first: "Выбери предмет для улучшения", bet_invalid: "Укажи корректную ставку",
    balance_low: "Недостаточно Кристалликов 💎", ads_unavailable: "Реклама недоступна, попробуйте позже.",
    ad_reward_toast: "начислено за просмотр!", vip_hint: "Открой чат с ботом, чтобы оформить VIP через Telegram Stars.",
    giveaways_soon: "Раздел розыгрышей скоро появится здесь!",
    back_btn: "Назад", open_count_label: "Количество открытий", open_speed_label: "Режим скорости",
    speed_slow: "Медленно", speed_fast: "Быстро", sell_all_btn: "Продать всё",
    sell_all_for_btn: "Продать все за", keep_all_btn: "Забрать все в инвентарь",
    sell_for_btn: "Продать за", sold_label: "Продано",
    multi_results_total_label: "Получено предметов на сумму:",
    select_all_label: "Выделить все", disintegrate_btn: "Продать выбранное",
    sort_expensive_first: "Сначала дорогие", sort_cheap_first: "Сначала дешёвые",
    disintegrate_success: "Предметы проданы!", nothing_selected: "Выбери хотя бы один предмет",
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
    daily_reward_case: "Кейс «Revolution»", daily_reward_gold: "Золото",
    daily_reward_vip: "VIP на {h} ч.", daily_reward_vip_already: "У тебя уже постоянный VIP",
    daily_mega_hint: "Ещё {n} дн. подряд — и получишь мега-бонус +{gold} 💰",
    daily_mega_bonus_toast: "🔥 Мега-бонус за 30 дней подряд!",
    daily_already_claimed_toast: "Ежедневный бонус уже получен сегодня. Возвращайся завтра!",
    tasks_earn_title: "Задания", tasks_earn_desc: "Подписки и рефералы — бесплатное 💰 Золото",
    tasks_title: "✅ Задания",
    task_open_btn: "Перейти", task_check_btn: "Проверить", task_done_btn: "Выполнено ✓",
    task_completed_toast: "Задание выполнено! +{gold} 💰 Золота",
    task_not_verified_toast: "Условие ещё не выполнено — попробуй ещё раз чуть позже",
    task_check_error_toast: "Не удалось проверить задание",
    rank_xp_line: "{xp} / {next} XP", rank_max_line: "{xp} XP · Максимальный ранг",
    rank_next_line: "До ранга «{name}»: {xp} XP", rank_next_line_max: "Достигнут максимальный ранг!",
    rankup_title: "🎉 Новый ранг!",
    game_crafter: "Синтезатор",
    crafter_desc: "Заложи предметы из инвентаря и/или добавь Кристаллы, выбери целевой предмет — при успехе получишь его, при неудаче вся ставка сгорает без остатка.",
    crafter_components_label: "Исходные предметы",
    crafter_add_crystals_label: "Добавить Кристаллы",
    crafter_input_value_label: "Стоимость ставки",
    crafter_target_label: "Целевой предмет",
    crafter_synthesize_btn: "Синтезировать",
    crafter_synthesizing: "Синтез…",
    crafter_price_from: "Цена от",
    crafter_price_to: "Цена до",
    crafter_success_title: "✨ Синтез удался!",
    crafter_fail_title: "💥 Синтез не удался",
    crafter_fail_desc: "Ставка сгорела без остатка.",
    crafter_pick_component_first: "Добавь хотя бы о��ин предмет из инвентаря или Кристаллы",
    crafter_pick_target_first: "Выбери целевой предмет из каталога",
    crafter_catalog_empty: "Ничег�� не найдено",
    crafter_catalog_hint: "Найди целевой предмет по названию или диапазону цен",
    wheel_earn_title: "Колесо удачи", wheel_earn_desc: "Крути раз в день бесплатно — или за 💰 Золото",
    wheel_title: "🎡 Колесо удачи", wheel_spin_btn: "Крутить", wheel_spinning: "Крутится…",
    wheel_free_hint: "Бесплатный спин доступен!", wheel_free_in: "Бесплатный спин через",
    wheel_paid_hint: "Платный спин — 💰 5 Золота", wheel_paid_left: "Осталось платных спинов сегодня",
    wheel_no_spins_left: "Спины на сегодня закончились",
    wheel_no_gold: "Не хватает 💰 Золота для платного спина",
    wheel_result_title: "🎉 Приз колеса!", wheel_ok_btn: "Отлично!",
    wheel_sector_crystals: "Кристаллы", wheel_sector_gold: "Золото",
    wheel_sector_vip: "VIP-статус на 3 часа", wheel_sector_case: "Кейс «Revolution»",
    gold_label: "Золото",
    // ---- Спринт 10: уровень, титулы/рамки, витрина, друзья ----
    level_label: "Уровень аккаунта", level_short: "ур.",
    level_max_line: "{xp} XP · Максимальный уровень",
    level_next_slot: "🏅 Слотов витрины: {slots} · +1 на {level} уровне",
    level_slots_max: "🏅 Все {slots} слотов витрины открыты",
    level_table_title: "📈 Уровни аккаунта",
    levelup_title: "🎉 Новый уровень!",
    levelup_slot_gained: "🏅 +1 слот Витрины! Теперь их {slots}",
    showcase_title: "🏅 Витрина лучших скинов",
    showcase_hint: "Закрепи лучшие скины из инвентаря. +1 слот на {level} уровне.",
    showcase_hint_max: "Все слоты витрины открыты — максимум 10.",
    showcase_add: "В витрину", showcase_remove: "Убрать из витрины",
    showcase_empty_friend: "Витрина пуста",
    titles_label: "🎖️ Титул", frames_label: "🖼️ Рамка аватара",
    cosmetic_none: "Без", cosmetic_locked: "Ещё не открыто",
    cosmetic_unlocked: "🎉 Открыто:",
    item_quality: "Качество", item_price: "Цена",
    friends_title: "👥 Друзья",
    friends_tab_list: "Друзья", friends_tab_requests: "Заявки", friends_tab_search: "Поиск",
    friends_incoming: "Входящие", friends_outgoing: "Исходящие",
    friends_search_btn: "Найти",
    friends_search_hint: "Введи Telegram ID (например 123456789) или username (@nick)",
    friends_loading: "Загрузка…", friends_empty: "Друзей пока нет — найди их в поиске!",
    friends_no_incoming: "Нет входящих заявок", friends_no_outgoing: "Нет исходящих заявок",
    friends_not_found: "Никого не найдено",
    friends_add: "Добавить", friends_accept: "Принять", friends_decline: "Отклонить",
    friends_cancel: "Отменить", friends_remove: "Удалить",
    friends_remove_confirm: "Удалить из друзей?",
    friends_request_sent: "Заявка отправлена!", friends_accepted: "Теперь вы друзья!",
    friends_already: "Уже друзья", friends_pending: "Заявка отправлена",
    friends_you: "Это ты", friends_level_short: "ур.",
    friends_stat_items: "Предметов", friends_stat_knives: "Ножей выбито",
    friends_profile_error: "Профиль недоступен",
  },
  en: {
    cases_title: "Cases", inventory_title: "Inventory",
    inventory_empty: "Empty for now. Open your first case!",
    terms_title: "📜 Terms of Service",
    terms_accept_btn: "Accept and continue",
    profile_title: "Profile", stat_cases: "Cases opened",
    stat_ref_count: "Friends invited", stat_ref_earnings: "Earned passively",
    stat_inv_value: "Inventory value", stat_favorite: "Favorite case",
    stat_top_drop: "🏆 Top drop", top_drop_empty: "No drops yet — open your first case!", settings_title: "⚙️ Settings",
    craft_open_btn: "Craft", craft_title: "🔧 Craft", craft_progress_sub: "selected",
    craft_rarity_hint: "Pick 5 items of the SAME rarity from your inventory",
    craft_source_title: "1. Source items (inventory)",
    craft_target_title: "2. Target item (catalog)",
    craft_fee_label: "Recipe fee:", craft_submit_btn: "Craft",
    craft_result_title: "✨ Crafted!",
    craft_pick_target_hint: "Choose what you want to get",
    craft_max_rarity: "This rarity is already the highest — nothing to craft up to",
    craft_success: "Done! New item is in your inventory",
    craft_not_enough_balance: "Not enough 💎 to pay the recipe fee",
    settings_lang: "🌐 Language", settings_sound: "🔊 Sound", settings_currency: "💱 Currency", settings_background: "🖼️ Simulator background",
    sound_on: "On", sound_off: "Off",
    ref_title: "👥 Referral link", copy_btn: "Copy",
    promo_title: "🎁 Promo code", promo_placeholder: "Enter promo code",
    activate_btn: "Activate", minigames_title: "Mini-games",
    upgrade_desc: "Pick an item from inventory and a target — succeed and get the target skin, fail and it burns (you'll still get a consolation skin).",
    multiplier_label: "Multiplier", chance_preview_label: "Approx. success chance",
    upgrade_btn: "Upgrade", crash_desc: "Place a bet and choose the multiplier to cash out at.",
    upgrade_mode_item: "Pick skin", upgrade_mode_price: "Custom price", upgrade_mode_multiplier: "Multiplier", upgrade_mode_chance: "Chance",
    upgrade_search_placeholder: "Search skin by name…", upgrade_search_empty: "Nothing found",
    upgrade_target_price_label: "Desired price (💎)", upgrade_target_price_placeholder: "e.g. 2500",
    upgrade_your_item_label: "Your item", upgrade_target_label: "Target",
    sort_price_label: "Price", upgrade_max_items_hint: "Pick up to 6 items at once — their value is combined",
    upgrade_quick_multiplier: "Quick multiplier", upgrade_quick_chance: "Quick chance",
    upgrade_spin_btn: "Go", upgrade_spinning: "Spinning…",
    upgrade_success_title: "🎉 Upgrade succeeded!", upgrade_fail_title: "💥 Upgrade failed",
    upgrade_fail_desc: "The item burned. But you got a consolation skin:",
    upgrade_result_ok_btn: "Nice!", upgrade_pick_item_first: "Pick an item to upgrade first",
    upgrade_pick_target_first: "Set an upgrade target",
    bet_label: "Bet (💎)", cashout_label: "Cash out at", play_btn: "Play",
    earn_title: "Earn", earn_ad_title: "Watch a video",
    earn_ad_desc: "Get +2000 �� virtual balance", watch_btn: "Watch",
    earn_giveaway_title: "Giveaways", earn_giveaway_desc: "Join and win rare skins",
    earn_vip_title: "VIP status", earn_vip_desc: "No ads + cosmetic perks",
    buy_btn: "Buy", tab_cases: "Cases", tab_inventory: "Inventory",
    tab_profile: "Profile", tab_minigames: "Games", tab_earn: "Earn", tab_chat: "Chat",
    chat_title: "Global chat", chat_input_ph: "Type a message…", chat_send: "Send",
    chat_empty: "No messages yet. Be the first!", chat_report: "Report",
    chat_report_done: "Report sent", chat_muted: "You are muted and can't post",
    chat_banned: "You are banned from the chat", chat_you: "You",
    open_case_btn: "Open case", contents_title: "📋 Case contents",
    win_title: "🎉 You got!", keep_btn: "To collection", sell_btn: "Sell", open_again_btn: "Open again",
    insufficient_balance: "Not enough 💎 Crystals. Watch an ad on the Earn tab!",
    link_copied: "Link copied!", sell_label: "Sell",
    upgrade_success: "🎉 Success! New price:", upgrade_fail: "💥 Failed. The item is gone.",
    select_item_first: "Pick an item to upgrade", bet_invalid: "Enter a valid bet",
    balance_low: "Not enough 💎 Crystals", ads_unavailable: "Ad unavailable, try again later.",
    ad_reward_toast: "credited for watching!", vip_hint: "Open the bot chat to get VIP via Telegram Stars.",
    giveaways_soon: "Giveaways are coming soon!",
    back_btn: "Back", open_count_label: "Number of openings", open_speed_label: "Speed mode",
    speed_slow: "Slow", speed_fast: "Fast", sell_all_btn: "Sell all",
    sell_all_for_btn: "Sell all for", keep_all_btn: "Keep all in inventory",
    sell_for_btn: "Sell for", sold_label: "Sold",
    multi_results_total_label: "Items received worth:",
    select_all_label: "Select all", disintegrate_btn: "Sell selected",
    sort_expensive_first: "Highest price", sort_cheap_first: "Lowest price",
    disintegrate_success: "Items sold!", nothing_selected: "Select at least one item",
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
    daily_reward_case: "Revolution Case", daily_reward_gold: "Gold",
    daily_reward_vip: "VIP for {h}h", daily_reward_vip_already: "You already have permanent VIP",
    daily_mega_hint: "{n} more days in a row for a mega bonus of +{gold} 💰",
    daily_mega_bonus_toast: "🔥 30-day streak mega bonus!",
    daily_already_claimed_toast: "Daily bonus already claimed today. Come back tomorrow!",
    tasks_earn_title: "Tasks", tasks_earn_desc: "Subscriptions and referrals — free 💰 Gold",
    tasks_title: "✅ Tasks",
    task_open_btn: "Open", task_check_btn: "Check", task_done_btn: "Done ✓",
    task_completed_toast: "Task completed! +{gold} 💰 Gold",
    task_not_verified_toast: "Not completed yet — try again in a moment",
    task_check_error_toast: "Couldn't check the task",
    rank_xp_line: "{xp} / {next} XP", rank_max_line: "{xp} XP · Max rank",
    rank_next_line: "To «{name}»: {xp} XP", rank_next_line_max: "Max rank reached!",
    rankup_title: "🎉 New rank!",
    game_crafter: "Crafter",
    crafter_desc: "Stake items from your inventory and/or add Crystals, pick a target item — succeed and you get it, fail and the whole stake burns with nothing back.",
    crafter_components_label: "Source items",
    crafter_add_crystals_label: "Add Crystals",
    crafter_input_value_label: "Stake value",
    crafter_target_label: "Target item",
    crafter_synthesize_btn: "Synthesize",
    crafter_synthesizing: "Synthesizing…",
    crafter_price_from: "Price from",
    crafter_price_to: "Price to",
    crafter_success_title: "✨ Synthesis succeeded!",
    crafter_fail_title: "💥 Synthesis failed",
    crafter_fail_desc: "The stake burned with nothing back.",
    crafter_pick_component_first: "Add at least one inventory item or Crystals",
    crafter_pick_target_first: "Pick a target item from the catalog",
    crafter_catalog_empty: "Nothing found",
    crafter_catalog_hint: "Find a target item by name or price range",
    wheel_earn_title: "Wheel of Luck", wheel_earn_desc: "Spin free once a day — or pay 💰 Gold",
    wheel_title: "🎡 Wheel of Luck", wheel_spin_btn: "Spin", wheel_spinning: "Spinning…",
    wheel_free_hint: "Free spin available!", wheel_free_in: "Free spin in",
    wheel_paid_hint: "Paid spin — 💰 5 Gold", wheel_paid_left: "Paid spins left today",
    wheel_no_spins_left: "No spins left for today",
    wheel_no_gold: "Not enough 💰 Gold for a paid spin",
    wheel_result_title: "🎉 Wheel prize!", wheel_ok_btn: "Awesome!",
    wheel_sector_crystals: "Crystals", wheel_sector_gold: "Gold",
    wheel_sector_vip: "VIP status for 3 hours", wheel_sector_case: "\"Revolution\" case",
    gold_label: "Gold",
    // ---- Sprint 10: level, titles/frames, showcase, friends ----
    level_label: "Account level", level_short: "lvl",
    level_max_line: "{xp} XP · Max level",
    level_next_slot: "🏅 Showcase slots: {slots} · +1 at level {level}",
    level_slots_max: "🏅 All {slots} showcase slots unlocked",
    level_table_title: "📈 Account levels",
    levelup_title: "🎉 Level up!",
    levelup_slot_gained: "🏅 +1 Showcase slot! Now {slots}",
    showcase_title: "🏅 Best skins showcase",
    showcase_hint: "Pin your best skins from inventory. +1 slot at level {level}.",
    showcase_hint_max: "All showcase slots unlocked — 10 max.",
    showcase_add: "Add to showcase", showcase_remove: "Remove from showcase",
    showcase_empty_friend: "Showcase is empty",
    titles_label: "🎖️ Title", frames_label: "🖼️ Avatar frame",
    cosmetic_none: "None", cosmetic_locked: "Not unlocked yet",
    cosmetic_unlocked: "🎉 Unlocked:",
    item_quality: "Quality", item_price: "Price",
    friends_title: "👥 Friends",
    friends_tab_list: "Friends", friends_tab_requests: "Requests", friends_tab_search: "Search",
    friends_incoming: "Incoming", friends_outgoing: "Outgoing",
    friends_search_btn: "Search",
    friends_search_hint: "Enter Telegram ID (e.g. 123456789) or username (@nick)",
    friends_loading: "Loading…", friends_empty: "No friends yet — find them in search!",
    friends_no_incoming: "No incoming requests", friends_no_outgoing: "No outgoing requests",
    friends_not_found: "Nobody found",
    friends_add: "Add", friends_accept: "Accept", friends_decline: "Decline",
    friends_cancel: "Cancel", friends_remove: "Remove",
    friends_remove_confirm: "Remove from friends?",
    friends_request_sent: "Request sent!", friends_accepted: "You are friends now!",
    friends_already: "Already friends", friends_pending: "Request sent",
    friends_you: "That's you", friends_level_short: "lvl",
    friends_stat_items: "Items", friends_stat_knives: "Knives dropped",
    friends_profile_error: "Profile unavailable",
  },
  uk: {
    cases_title: "Кейси", inventory_title: "Інвентар",
    inventory_empty: "Поки що порожньо. Відкрий перший кейс!",
    terms_title: "📜 Угода користувача",
    terms_accept_btn: "Прийняти і продовжити",
    profile_title: "Профіль", stat_cases: "Відкрито кейсів",
    stat_ref_count: "Запрошено друзів", stat_ref_earnings: "Нараховано пасивно",
    stat_inv_value: "Вартість інвентаря", stat_favorite: "Улюблений кейс",
    stat_top_drop: "🏆 Топ дроп", top_drop_empty: "Ще немає жодного дропу — відкрий перший кейс!", settings_title: "⚙️ Налаштування",
    craft_open_btn: "Крафт", craft_title: "🔧 Крафт", craft_progress_sub: "вибрано",
    craft_rarity_hint: "Обери 5 предметів ОДНІЄЇ рідкості з інвентаря",
    craft_source_title: "1. Вихідні предмети (інвентар)",
    craft_target_title: "2. Цільовий предмет (каталог)",
    craft_fee_label: "Плата за рецепт:", craft_submit_btn: "Скрафтити",
    craft_result_title: "✨ Скрафчено!",
    craft_pick_target_hint: "Обери, що хочеш отримати",
    craft_max_rarity: "Ця рідкість вже максимальна — крафтити далі нікуди",
    craft_success: "Готово! Новий предмет вже в інвентарі",
    craft_not_enough_balance: "Не вистачає 💎 на оплату рецепта",
    settings_lang: "🌐 Мова", settings_sound: "🔊 Звук", settings_currency: "💱 Валюта", settings_background: "🖼️ Фон симулятора",
    sound_on: "Увім.", sound_off: "Вимк.",
    ref_title: "👥 Реферальне посилання", copy_btn: "Копіювати",
    promo_title: "🎁 Промокод", promo_placeholder: "Введіть промокод",
    activate_btn: "Активувати", minigames_title: "Міні-ігри",
    upgrade_desc: "Обери предмет з інвентаря та ціль — при успіху отримаєш цільовий скін, при невдачі предмет згорить (але отримаєш втішний скін).",
    multiplier_label: "Множник", chance_preview_label: "Приблизний шанс успіху",
    upgrade_btn: "Покращити", crash_desc: "Став Кристалики та обери множник, на якому забрати виграш.",
    upgrade_mode_item: "Обрати скін", upgrade_mode_price: "Своя ціна", upgrade_mode_multiplier: "Множник", upgrade_mode_chance: "Шанс",
    upgrade_search_placeholder: "Пошук скіна за назвою…", upgrade_search_empty: "Нічого не знайдено",
    upgrade_target_price_label: "Бажана вартість (💎)", upgrade_target_price_placeholder: "Наприклад, 2500",
    upgrade_your_item_label: "Твій предмет", upgrade_target_label: "Ціль",
    sort_price_label: "Ціна", upgrade_max_items_hint: "Можна вибрати до 6 предметів одразу — їх вартість підсумовується",
    upgrade_quick_multiplier: "Швидкий множник", upgrade_quick_chance: "Швидкий шанс",
    upgrade_spin_btn: "Запуск", upgrade_spinning: "Крутимо…",
    upgrade_success_title: "🎉 Апгрейд вдався!", upgrade_fail_title: "💥 Апгрейд не вдався",
    upgrade_fail_desc: "Предмет згорів. Але ти отримав втішний скін:",
    upgrade_result_ok_btn: "Чудово!", upgrade_pick_item_first: "Спочатку обери предмет для покращення",
    upgrade_pick_target_first: "Вкажи ціль апгрейду",
    bet_label: "Ставка (💎)", cashout_label: "Забрати на", play_btn: "Грати",
    earn_title: "Заробити", earn_ad_title: "Переглянути відео",
    earn_ad_desc: "Отримай +2000 💎 віртуального балансу", watch_btn: "Дивитись",
    earn_giveaway_title: "Розіграші", earn_giveaway_desc: "Бери участь і вигравай рідкісні скіни",
    earn_vip_title: "VIP-статус", earn_vip_desc: "Без реклами + косметичні бонуси",
    buy_btn: "Купити", tab_cases: "Кейси", tab_inventory: "Інвентар",
    tab_profile: "Профіль", tab_minigames: "Міні-ігри", tab_earn: "Заробити", tab_chat: "Чат",
    chat_title: "Глобальний чат", chat_input_ph: "Написати повідомлення…", chat_send: "Надіслати",
    chat_empty: "Повідомлень ще немає. Будь першим!", chat_report: "Поскаржитися",
    chat_report_done: "Скаргу надіслано", chat_muted: "Ви в муті й не можете писати",
    chat_banned: "Вас заблоковано в чаті", chat_you: "Ви",
    open_case_btn: "Відкрити кейс", contents_title: "📋 Вміст кейса",
    win_title: "🎉 Випало!", keep_btn: "У колекцію", sell_btn: "Продати", open_again_btn: "Відкрити ще",
    insufficient_balance: "Недостатньо Кристаликів 💎. Подивись рекламу на вкладці «Заробити»!",
    link_copied: "Посилання скопійовано!", sell_label: "Продати",
    upgrade_success: "🎉 Успіх! Нова ціна:", upgrade_fail: "💥 Невдача. Предмет згорів.",
    select_item_first: "Обери предмет для покращення", bet_invalid: "Вкажи коректну ставку",
    balance_low: "Недостатньо Кристаликів 💎", ads_unavailable: "Реклама недоступна, спробуй пізніше.",
    ad_reward_toast: "нараховано за перегляд!", vip_hint: "Відкрий чат з ботом, щоб оформити VIP через Telegram Stars.",
    giveaways_soon: "Розділ розіграшів скоро зʼявиться тут!",
    back_btn: "Назад", open_count_label: "Кількість відкриттів", open_speed_label: "Режим швидкості",
    speed_slow: "Повільно", speed_fast: "Швидко", sell_all_btn: "Продати все",
    sell_all_for_btn: "Продати все за", keep_all_btn: "Забрати все в інвентар",
    sell_for_btn: "Продати за", sold_label: "Продано",
    multi_results_total_label: "Отримано предметів на суму:",
    select_all_label: "Виділити все", disintegrate_btn: "Продати вибране",
    sort_expensive_first: "Спочатку дорогі", sort_cheap_first: "Спочатку дешеві",
    disintegrate_success: "Предмети продано!", nothing_selected: "Обери хоча б один предмет",
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
    daily_reward_case: "Кейс «Revolution»", daily_reward_gold: "Золото",
    daily_reward_vip: "VIP на {h} год.", daily_reward_vip_already: "У тебе вже постійний VIP",
    daily_mega_hint: "Ще {n} дн. поспіль — і отримаєш мега-бонус +{gold} 💰",
    daily_mega_bonus_toast: "🔥 Мега-бонус за 30 днів поспіль!",
    daily_already_claimed_toast: "Щоденний бонус уже отримано сьогодні. Повертайся завтра!",
    tasks_earn_title: "Завдання", tasks_earn_desc: "Підписки та реферали — безкоштовне 💰 Золото",
    tasks_title: "✅ Завдання",
    task_open_btn: "Перейти", task_check_btn: "Перевірити", task_done_btn: "Виконано ✓",
    task_completed_toast: "Завдання виконано! +{gold} 💰 Золота",
    task_not_verified_toast: "Умову ще не виконано — спробуй ще раз трохи пізніше",
    task_check_error_toast: "Не вдалося перевірити завдання",
    rank_xp_line: "{xp} / {next} XP", rank_max_line: "{xp} XP · Максимальний ран��",
    rank_next_line: "До рангу «{name}»: {xp} XP", rank_next_line_max: "Досягнуто максимальний ранг!",
    rankup_title: "🎉 Новий ранг!",
    game_crafter: "Синтезатор",
    crafter_desc: "Заклади предмети з інвентаря та/або додай Кристали, обери цільовий предмет — при успіху отримаєш його, при невдачі вся ставка згорає без залишку.",
    crafter_components_label: "Вихідні предмети",
    crafter_add_crystals_label: "Додати Кристали",
    crafter_input_value_label: "Вартість ставки",
    crafter_target_label: "Цільовий предмет",
    crafter_synthesize_btn: "Синтезувати",
    crafter_synthesizing: "Синтез…",
    crafter_price_from: "Ціна від",
    crafter_price_to: "Ціна до",
    crafter_success_title: "✨ Синтез вдався!",
    crafter_fail_title: "💥 Синтез не вдався",
    crafter_fail_desc: "Ставка згоріла без залишку.",
    crafter_pick_component_first: "Додай хоча б один предмет з інвентаря або Кристали",
    crafter_pick_target_first: "Обери цільовий предмет із каталогу",
    crafter_catalog_empty: "Нічого не знайдено",
    crafter_catalog_hint: "Знайди цільовий предмет за назвою або діапазоном цін",
    wheel_earn_title: "Колесо удачі", wheel_earn_desc: "Крути раз на день безкоштовно — або за 💰 Золото",
    wheel_title: "🎡 Колесо удачі", wheel_spin_btn: "Крутити", wheel_spinning: "Крутиться…",
    wheel_free_hint: "Безкоштовний спін доступний!", wheel_free_in: "Безкоштовний спін через",
    wheel_paid_hint: "Платний спін — 💰 5 Золота", wheel_paid_left: "Залишилось платних спінів сьогодні",
    wheel_no_spins_left: "Спіни на сьогодні закінчились",
    wheel_no_gold: "Не вистачає 💰 Золота для платного спіна",
    wheel_result_title: "🎉 Приз колеса!", wheel_ok_btn: "Чудово!",
    wheel_sector_crystals: "Кристали", wheel_sector_gold: "Золото",
    wheel_sector_vip: "VIP-статус на 3 години", wheel_sector_case: "Кейс «Revolution»",
    gold_label: "Золото",
    // ---- Спринт 10: рівень, титули/рамки, вітрина, друзі ----
    level_label: "Рівень акаунту", level_short: "рів.",
    level_max_line: "{xp} XP · Максимальний рівень",
    level_next_slot: "🏅 Слотів вітрини: {slots} · +1 на {level} рівні",
    level_slots_max: "🏅 Усі {slots} слотів вітрини відкриті",
    level_table_title: "📈 Рівні акаунту",
    levelup_title: "🎉 Новий рівень!",
    levelup_slot_gained: "🏅 +1 слот Вітрини! Тепер їх {slots}",
    showcase_title: "🏅 Вітрина найкращих скінів",
    showcase_hint: "Закріпи найкращі скіни з інвентарю. +1 слот на {level} рівні.",
    showcase_hint_max: "Усі слоти вітрини відкриті — максимум 10.",
    showcase_add: "У вітрину", showcase_remove: "Пр��брати з вітрини",
    showcase_empty_friend: "Вітрина порожня",
    titles_label: "🎖️ Титул", frames_label: "🖼️ Рамка аватара",
    cosmetic_none: "Без", cosmetic_locked: "Ще не відкрито",
    cosmetic_unlocked: "🎉 Відкрито:",
    item_quality: "Якість", item_price: "Ціна",
    friends_title: "👥 Друзі",
    friends_tab_list: "Друзі", friends_tab_requests: "Заявки", friends_tab_search: "Пошук",
    friends_incoming: "Вхідні", friends_outgoing: "Вихідні",
    friends_search_btn: "Знайти",
    friends_search_hint: "Введи Telegram ID (наприклад 123456789) або username (@nick)",
    friends_loading: "Завантаження…", friends_empty: "Друзів поки немає — знайди їх у пошуку!",
    friends_no_incoming: "Немає вхідних заявок", friends_no_outgoing: "Немає вихідних заявок",
    friends_not_found: "Нікого не знайдено",
    friends_add: "Додати", friends_accept: "Прийняти", friends_decline: "Відхилити",
    friends_cancel: "Скасувати", friends_remove: "Видалити",
    friends_remove_confirm: "Видалити з друзів?",
    friends_request_sent: "Заявку надіслано!", friends_accepted: "Тепер ви друзі!",
    friends_already: "Вже друзі", friends_pending: "Заявку надіслано",
    friends_you: "Це ти", friends_level_short: "рів.",
    friends_stat_items: "Предметів", friends_stat_knives: "Ножів вибито",
    friends_profile_error: "Профіль недоступний",
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
  applyTermsBodyTranslation();
}

// ============================================
// Пользовательское соглашение (Terms of Service)
// ============================================
// Текст соглашения содержит HTML (<br><br> для абзацев), поэтому он не
// проходит через обычный data-i18n/textContent (он бы съел разметку) —
// хранится отдельно и подставляется через innerHTML.
const TERMS_TEXT = {
  ru: `Добро пожаловать! Прежде чем начать, ознакомься с условиями:
    <br><br>
    1. Это развлекательное приложение. Все "Кристаллики" 💎 и предметы —
    исключительно внутриигровые виртуальные объекты, не имеющие реальной
    денежной стоимости и не подлежащие обмену, продаже или выводу за
    пределы приложения.
    <br><br>
    2. VIP-статус приобретается за Telegram Stars и даёт только
    косметические/удобные преимущества (отключение рекламы, оформление
    интерфейса) — он не влияет на шансы выпадения предметов.
    <br><br>
    3. Мы сохраняем часть данных твоего профиля Telegram (имя, username,
    аватар) для работы приложения — реферальной программы, отображения
    профиля и лидербордов.
    <br><br>
    4. Продолжая, ты подтверждаешь, что ознакомился(ась) с условиями
    использования и согласен(на) с ними.`,
  en: `Welcome! Before you start, please review the terms:
    <br><br>
    1. This is an entertainment app. All 💎 Crystals and items are purely
    in-app virtual objects with no real-world monetary value, and cannot
    be exchanged, sold, or withdrawn outside the app.
    <br><br>
    2. VIP status is purchased with Telegram Stars and only grants
    cosmetic/convenience perks (ad removal, interface theme) — it does
    not affect item drop odds.
    <br><br>
    3. We store some of your Telegram profile data (name, username,
    avatar) to run the app — the referral program, profile display, and
    leaderboards.
    <br><br>
    4. By continuing, you confirm that you have read and agree to these
    terms of use.`,
  uk: `Ласкаво просимо! Перш ніж почати, ознайомся з умовами:
    <br><br>
    1. Це розважальний застосунок. Усі "Кристалики" 💎 та предмети —
    виключно внутрішньоігрові віртуальні об'єкти, що не мають реальної
    грошової вартості і не підлягають обміну, продажу чи виведенню за
    межі застосунку.
    <br><br>
    2. VIP-статус купується за Telegram Stars і дає лише
    косметичні/зручні переваги (вимкнення реклами, оформлення
    інтерфейсу) — він не впливає на шанси випадіння предметів.
    <br><br>
    3. Ми зберігаємо частину даних твого профілю Telegram (ім'я,
    username, аватар) для роботи застосунку — реферальної програми,
    відображення профілю та лідербордів.
    <br><br>
    4. Продовжуючи, ти підтверджуєш, що ознайомився(лась) з умовами
    використання і згоден(на) з ними.`,
};

function applyTermsBodyTranslation() {
  const el = document.getElementById("terms-body");
  if (el) el.innerHTML = TERMS_TEXT[state.lang] || TERMS_TEXT.ru;
}

// Показывает модалку соглашения, если она ещё не была принята. Источник
// истины — профиль с бэкенда (profile.terms_accepted), localStorage
// используется только для МГНОВЕННОГО показа/скрытия при следующих
// запусках (чтобы не было "мигания" модалки, пока грузится профиль).
function maybeShowTermsModal(termsAcceptedOnBackend) {
  const acceptedLocally = localStorage.getItem("cs2_terms_accepted") === "1";
  if (termsAcceptedOnBackend || acceptedLocally) {
    localStorage.setItem("cs2_terms_accepted", "1");
    return;
  }
  applyTermsBodyTranslation();
  document.getElementById("terms-overlay").classList.add("active");
}

document.getElementById("terms-accept-btn").addEventListener("click", async () => {
  const btn = document.getElementById("terms-accept-btn");
  btn.disabled = true;
  try {
    await apiPost("/accept-terms", { telegram_id: state.telegramId });
  } catch (e) {
    console.error("Не удалось сохранить принятие соглашения на сервере:", e);
    // Даже если запрос не прошёл (например, нет сети) — не блокируем
    // пользователя повторно на этом устройстве; на следующем визите
    // профиль с бэкенда всё равно попробует досинхронизироваться.
  } finally {
    localStorage.setItem("cs2_terms_accepted", "1");
    document.getElementById("terms-overlay").classList.remove("active");
    btn.disabled = false;
  }
});

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
// Звук (Web Audio API — синтезированные CS2-style эффекты)
// ============================================
// ВАЖНО про копирайт: настоящие звуковые файлы CS2/CS:GO принадлежат
// Valve — встраивать их в проект нельзя. Вместо этого все эффекты
// синтезируются на лету через Web Audio API (осцилляторы), но подобраны
// так, чтобы попадать в узнаваемый "фил" CS2: короткие механические
// клики по UI, дробный "тик-тик-тик" прокрутки рулетки, тревожный
// низкий сигнал при проигрыше, восходящие фанфары при редком дропе,
// и отдельный "кассовый" звук при продаже предметов.
const AudioCtx = window.AudioContext || window.webkitAudioContext;
let audioCtx = null;
let audioUnlocked = false;
let masterCompressor = null;

function ensureAudioCtx() {
  if (!AudioCtx) return null; // браузер вообще не поддерживает Web Audio API
  try {
    if (!audioCtx) {
      audioCtx = new AudioCtx();
      // Общий компрессор перед выходом на колонки — сглаживает звук и не
      // даёт эффектам "трещать"/клиппинговать, когда несколько звуков
      // накладываются друг на друга (например, при мульти-открытии
      // кейсов, где карточки раскрываются одна за другой с шагом ~220мс).
      masterCompressor = audioCtx.createDynamicsCompressor();
      masterCompressor.threshold.value = -18;
      masterCompressor.knee.value = 24;
      masterCompressor.ratio.value = 6;
      masterCompressor.attack.value = 0.003;
      masterCompressor.release.value = 0.15;
      masterCompressor.connect(audioCtx.destination);
    }
    if (audioCtx.state === "suspended") {
      // Автовоспроизведение звука до первого клика браузеры блокируют —
      // resume() можно вызывать сколько угодно раз, он безопасен, если
      // AudioContext уже создан внутри обработчика пользовательского
      // жеста (клика/тапа), как здесь.
      audioCtx.resume().catch(() => {
        // Тихо игнорируем: значит браузер ещё не считает это жестом
        // пользователя — звук просто не сыграет в этот раз, это не баг.
      });
    }
    return audioCtx;
  } catch (err) {
    console.warn("Web Audio API недоступен, звук отключается:", err);
    return null;
  }
}

// iOS Safari иногда требует ПОЛНОЦЕННОЕ воспроизведение (пусть и
// беззвучного) буфера внутри самого первого касания, иначе весь
// AudioContext остаётся "залоченным" даже после resume(). Делаем это
// один раз при самом первом клике/тапе по приложению.
function unlockAudioOnce() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  const ctx = ensureAudioCtx();
  if (!ctx) return;
  try {
    const buffer = ctx.createBuffer(1, 1, 22050);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.start(0);
  } catch (err) {
    console.warn("Не удалось разблокировать аудио-контекст:", err);
  }
}
document.addEventListener("pointerdown", unlockAudioOnce, { once: true, capture: true });

function tone(freq, duration, type = "sine", gainStart = 0.15, delay = 0) {
  if (!state.soundEnabled) return;
  const ctx = ensureAudioCtx();
  if (!ctx) return;
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    const startAt = ctx.currentTime + delay;
    gain.gain.setValueAtTime(gainStart, startAt);
    gain.gain.exponentialRampToValueAtTime(0.001, startAt + duration);
    osc.connect(gain);
    gain.connect(masterCompressor || ctx.destination);
    osc.start(startAt);
    osc.stop(startAt + duration);
  } catch (err) {
    // Не даём звуку уронить остальной интерфейс — просто пропускаем его
    console.warn(`Не удалось проиграть звук (${freq}Hz):`, err);
  }
}

// Короткий "белый шум" — используется для механического щелчка клика по
// UI и для кассового "шелеста" при продаже, звучит более "физично",
// чем чистый осциллятор.
function noiseBurst(duration, gainStart = 0.12, delay = 0, filterFreq = 3000) {
  if (!state.soundEnabled) return;
  const ctx = ensureAudioCtx();
  if (!ctx) return;
  try {
    const bufferSize = Math.floor(ctx.sampleRate * duration);
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);

    const src = ctx.createBufferSource();
    src.buffer = buffer;

    const filter = ctx.createBiquadFilter();
    filter.type = "highpass";
    filter.frequency.value = filterFreq;

    const gain = ctx.createGain();
    const startAt = ctx.currentTime + delay;
    gain.gain.setValueAtTime(gainStart, startAt);
    gain.gain.exponentialRampToValueAtTime(0.001, startAt + duration);

    src.connect(filter);
    filter.connect(gain);
    gain.connect(masterCompressor || ctx.destination);
    src.start(startAt);
  } catch (err) {
    console.warn("Не удалось проиграть звук (noise):", err);
  }
}

const sfx = {
  // Короткий механический клик по любой кнопке/пункту меню
  click: () => { tone(700, 0.045, "square", 0.07); noiseBurst(0.02, 0.05, 0, 4000); },

  // "Тик" прокрутки рулетки кейса — короткий, дробный, слегка разной
  // высоты на каждый вызов (имитирует механическое колесо)
  spinTick: () => tone(500 + Math.random() * 200, 0.035, "square", 0.06),

  // Щелчок фиксации предмета в центре рулетки
  lock: () => { tone(220, 0.12, "triangle", 0.18); tone(440, 0.1, "triangle", 0.1, 0.05); },

  // Проигрыш / неудачный исход
  lose: () => { tone(220, 0.25, "sawtooth", 0.12); tone(140, 0.3, "sawtooth", 0.12, 0.08); },

  // Победные фа��фары — для редких/особо редких предметов (Тайное/Нож/Перчатки)
  fanfare: () => {
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => tone(f, 0.35, "triangle", 0.18, i * 0.09));
    noiseBurst(0.4, 0.08, 0.05, 1500); // лёгкий "сияющий" шум поверх нот
  },

  // Обычный (не редкий) выигрыш
  win: () => { tone(523.25, 0.15, "triangle", 0.15); tone(659.25, 0.18, "triangle", 0.15, 0.1); },

  // Продажа предмета(ов) — короткий "кассовый" звук: нисходящий шелест
  // шума + звонкий двойной "дзынь", отдельный от звука выигрыша, чтобы
  // продажа ощущалась как самостоятельное действие.
  sell: () => {
    noiseBurst(0.12, 0.1, 0, 2500);
    tone(1046.5, 0.08, "sine", 0.12, 0.03);
    tone(1568.0, 0.1, "sine", 0.1, 0.09);
  },
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
//
// БАГ, который здесь был исправлен: toLocaleString(..., { maximumFractionDigits: 0 })
// ОКРУГЛЯЕТ дробную часть до целого — баланс 2003.23 показывался как "2,003"
// (а 2003.6 вообще превращался в "2,004", то есть баланс визуально "рос" сам
// по себе). Теперь дробная часть сначала ОТБРАСЫВАЕТСЯ (усечение, а не
// округление) до 2 знаков через Math.trunc, и уже усечённое число форматируется
// с фиксированными 2 знаками после запятой — округления вверх больше нет
// ни при каких значениях баланса.
function truncateTo2(num) {
  // Math.trunc всегда отбрасывает "лишнее" в сторону нуля, а не округляет —
  // 2003.2356 -> 2003.23, а не 2003.24
  return Math.trunc(num * 100) / 100;
}

// ============================================
// Мультивалютность (₽ / $ / ₴)
// ============================================
// ВАЖНО: внутренняя игровая экономика (баланс, цены в БД, списания за
// кейсы/крафт/апгрейдер) всегда считается в 💎 Кристалликах = ₽ — currency
// здесь влияет ТОЛЬКО на то, что игрок ВИДИТ на экране. Переключение
// валюты не отправляет на бэкенд ничего, кроме сохранённого предпочтения
// (для показа той же валюты при следующем визите) — сами суммы,
// участвующие в игре, остаются в Кристалликах.
const CURRENCY_ICON = { RUB: "💎", USD: "$", UAH: "₴" };

function currencyIcon() {
  return CURRENCY_ICON[state.currency] || "💎";
}

// Крестики (=₽) -> число в выбранной валюте отображения.
function convertCrystals(n) {
  const rate = state.currencyRates[state.currency];
  return (Number(n) || 0) * (typeof rate === "number" ? rate : 1);
}

// Число + суффикс-иконка валюты: "1,250.00 💎" / "13.50 $" / "550.00 ₴"
function fmtWithIcon(n) {
  return `${fmtNumber(n)} ${currencyIcon()}`;
}

function setCurrency(cur) {
  if (!CURRENCY_ICON[cur]) return;
  state.currency = cur;
  localStorage.setItem("cs2_currency", cur);
  refreshCurrencyDisplay();
  apiPost("/user/settings", { telegram_id: state.telegramId, currency: cur }).catch(() => {});
}

// Перерисовывает ВСЁ, что уже отрисовано на экране, новыми значениями
// выбранной валюты — без единого лишнего запроса к бэкенду (все данные
// уже есть в state, просто пересчитываем и перезаписываем DOM).
function refreshCurrencyDisplay() {
  document.querySelectorAll(".currency-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.currency === state.currency);
  });
  document.getElementById("header-currency-toggle").textContent = currencyIcon();
  document.querySelectorAll(".balance-icon").forEach(el => { el.textContent = currencyIcon(); });

  updateBalanceDisplay();
  if (state.cases && state.cases.length) renderCases();
  if (state.inventory && state.inventory.length) renderInventory();
  if (state.lastProfile) renderProfileScreen(state.lastProfile);
  if (state.craftCatalog) {
    if (state.craftSourceRarity) renderCraftTargetGrid(state.craftSourceRarity);
    else renderCraftSourceGrid();
    updateCraftFeeDisplay();
  }
}

document.getElementById("header-currency-toggle").addEventListener("click", () => {
  const order = ["RUB", "USD", "UAH"];
  const next = order[(order.indexOf(state.currency) + 1) % order.length];
  setCurrency(next);
});

document.getElementById("currency-switch").addEventListener("click", (e) => {
  const btn = e.target.closest(".currency-btn");
  if (btn) setCurrency(btn.dataset.currency);
});

// ============================================
// Спринт 12: Кастомизация фона симулятора
// ============================================
// Каталог фонов приходит с бэкенда через /app-config (state.backgroundOptions)
// — единый источник истины, см. main.py::BACKGROUND_OPTIONS. Локально
// держим только ключ дефолта на случай, если конфиг ещё не успел
// загрузиться к моменту первой отрисовки.
const DEFAULT_BACKGROUND = "dark";

// Применяет фон к DOM: переключает #bg-layer/#bg-image/#bg-video и класс
// "custom-bg" на #app (даёт панелям полупрозрачность + blur, см. style.css).
// Вызывается и оптимистично (из localStorage, до ответа сервера — для
// мгновенной отрисовки без "мигания" темы), и после подтверждения с бэка.
function applyBackground(key) {
  const options = state.backgroundOptions || [];
  const option = options.find(o => o.key === key) || { key: DEFAULT_BACKGROUND, type: "theme" };

  state.background = option.key;
  localStorage.setItem("cs2_background", option.key);

  const layer = document.getElementById("bg-layer");
  const img = document.getElementById("bg-image");
  const video = document.getElementById("bg-video");
  const appEl = document.getElementById("app");
  if (!layer || !img || !video || !appEl) return;

  const isCustom = option.type === "image" || option.type === "video";
  layer.classList.toggle("active", isCustom);
  appEl.classList.toggle("custom-bg", isCustom);

  if (option.type === "image") {
    img.src = option.src;
    img.classList.add("active");
    video.classList.remove("active");
    video.pause();
    video.removeAttribute("src");
  } else if (option.type === "video") {
    video.classList.add("active");
    img.classList.remove("active");
    if (video.getAttribute("src") !== option.src) {
      video.src = option.src;
    }
    video.play().catch(() => {}); // автоплей может блокироваться до первого тача — не критично, muted облегчает разрешение
  } else {
    // "dark" / любой неизвестный ключ — просто откатываемся к обычной теме
    img.classList.remove("active");
    video.classList.remove("active");
    video.pause();
  }

  renderBackgroundPicker(); // перерисовать активную рамку в сетке выбора
}

// Отрисовывает сетку превью в Настройках. Идемпотентна — можно дёргать
// повторно (при смене языка/после загрузки конфига), просто перерисует DOM.
function renderBackgroundPicker() {
  const grid = document.getElementById("bg-picker-grid");
  if (!grid) return;
  const options = state.backgroundOptions || [];
  if (!options.length) return;

  grid.innerHTML = options.map(opt => {
    const active = opt.key === (state.background || DEFAULT_BACKGROUND);
    const thumbStyle = opt.thumb ? ` style="background-image:url('${opt.thumb}')"` : "";
    const icon = opt.type === "theme" ? "🌑" : (opt.type === "video" ? "🎬" : "");
    return `
      <button class="bg-picker-item${active ? " active" : ""}" data-bg="${opt.key}">
        <span class="bg-picker-thumb${opt.type === "theme" ? " bg-picker-thumb-theme" : ""}"${thumbStyle}>${icon}</span>
        <span class="bg-picker-name">${opt.label}</span>
      </button>`;
  }).join("");
}

document.getElementById("bg-picker-grid").addEventListener("click", (e) => {
  const btn = e.target.closest(".bg-picker-item");
  if (!btn) return;
  const key = btn.dataset.bg;
  if (key === state.background) return;

  applyBackground(key); // мгновенно, до ответа сервера
  apiPost("/user/settings", { telegram_id: state.telegramId, background: key }).catch(() => {
    // Сервер недоступен/отклонил — держим локальный выбор как есть, он
    // синхронизируется сам собой при следующем успешном /user/settings
    // или переопределится значением с сервера при следующем логине.
  });
});

function fmtNumber(n) {
  const converted = convertCrystals(n);
  const truncated = truncateTo2(converted);
  return truncated.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Полное отображение суммы со значком выбранной валюты: 💎 1,250 / $ 13.50 / ₴ 550.00
function fmt(n) {
  return `${currencyIcon()} ${fmtNumber(n)}`;
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

  // Плашка продажи (disintegrate-bar) физически лежит ВНЕ секции
  // #screen-inventory (она "прилипшая" к низу экрана), поэтому раньше при
  // переходе на другую вкладку она оставалась видимой, если в инвентаре
  // были предметы — теперь при уходе с вкладки инвентаря она всегда
  // принудительно скрывается, а на самой вкладке её видимость зависит
  // только от того, выделены ли предметы (см. updateInventorySelectionUI).
  if (name !== "inventory") {
    document.getElementById("disintegrate-bar").style.display = "none";
  } else {
    updateInventorySelectionUI();
  }

  if (name === "inventory") loadInventory();
  if (name === "profile") loadProfile();

  // Чат (Спринт 11): при входе — загрузка + запуск опроса, при уходе — стоп.
  if (name === "chat") {
    openChat();
  } else {
    stopChatPolling();
  }
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

  // Предметы уже приходят с бэкенда отсортированными от дешёвых к дорогим
  // (по возрастанию редкости/base_price) — просто рендерим по порядку.

  // Агрегированная статистика по ножам/перчаткам ЦЕЛОЙ категорией —
  // как в самом CS2: тап по любому ножу показывает не шанс именно ЭТОГО
  // скина, а общий шанс "выпадет какой-то нож" (Обычный / StatTrak) и
  // разброс цен по всей категории. Считаем один раз на кейс.
  const rareSummary = { Knife: null, Gloves: null };
  ["Knife", "Gloves"].forEach(rarity => {
    const group = caseData.items.filter(it => it.rarity === rarity);
    if (!group.length) return;
    const totalChance = group.reduce((s, it) => s + (Number(it.drop_chance) || 0), 0);
    const basePrice = group[0].base_price;
    // Диапазон цены задаётся разбросом качества (Battle-Scarred..Factory New),
    // те же множители, что и в main.py (QUALITY_PRICE_MULTIPLIER: 0.62–1.65).
    const regularMin = Math.round(basePrice * 0.62);
    const regularMax = Math.round(basePrice * 1.65);
    const canStattrak = rarity !== "Gloves"; // как и в игре — перчатки без StatTrak
    rareSummary[rarity] = {
      regularChance: canStattrak ? totalChance * (1 - STATTRAK_CHANCE_JS) : totalChance,
      regularMin, regularMax,
      stattrakChance: canStattrak ? totalChance * STATTRAK_CHANCE_JS : 0,
      stattrakMin: Math.round(regularMin * STATTRAK_MULTIPLIER_JS),
      stattrakMax: Math.round(regularMax * STATTRAK_MULTIPLIER_JS),
      canStattrak,
    };
  });

  caseData.items.forEach(item => {
    const el = document.createElement("div");
    const isRareCategory = item.rarity === "Knife" || item.rarity === "Gloves";
    el.className = `contents-item ${rarityClass(item.rarity)}`;
    const [weapon, skin] = item.name.replace("★ ", "").split(" | ");
    el.innerHTML = `
      <img src="${item.image}" alt="${item.name}" loading="lazy">
      <div class="contents-item-name">
        <span class="contents-item-weapon">${weapon}</span>
        <span class="contents-item-skin">${skin || ""}</span>
      </div>
      <div class="contents-item-chance-overlay">
        ${
          isRareCategory
            ? renderRareCategoryOverlay(rareSummary[item.rarity])
            : renderRegularOverlay(item)
        }
      </div>
    `;
    // Тап по карточке (��ез закрытия просмотра кейса) показывает
    // полупрозрачный блюр с шансом/ценой — цена по умолчанию скрыта,
    // повторный тап скрывает overlay обратно.
    el.addEventListener("click", () => el.classList.toggle("revealed"));
    list.appendChild(el);
  });

  document.getElementById("roulette-wrapper").style.display = "none";
  document.getElementById("vertical-spin-wrapper").style.display = "none";
  document.getElementById("multi-results-grid").style.display = "none";
  document.getElementById("multi-results-actions").style.display = "none";
  document.getElementById("open-case-btn").style.display = "block";
  document.getElementById("case-open-screen").classList.add("active");
}

document.getElementById("case-open-back-btn").addEventListener("click", () => {
  document.getElementById("case-open-screen").classList.remove("active");
  document.getElementById("vertical-spin-wrapper").style.display = "none";
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

    // Показываем модалку нового ранга (если есть) с небольшой задержкой,
    // чтобы она не перекрывала анимацию открытия/win-модалку сразу же.
    if (result.xp && result.xp.rank_up && result.xp.rank_up.length) {
      setTimeout(() => handleXpResult(result.xp), 900);
    }

    state.casesOpenedSinceAd += state.openCount;
    maybeShowInterstitial();

    if (state.openCount > 1) {
      // Несколько кейсов за раз — N параллельных вертикальных лент,
      // каскадная остановка, затем экран результатов с продажей.
      runVerticalMultiSpin(state.currentCase, drops);
    } else if (state.openSpeed === "slow") {
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
  document.getElementById("vertical-spin-wrapper").style.display = "none";
  document.getElementById("open-case-btn").style.display = "none";

  state.lastMultiDrops = drops.slice();

  const grid = document.getElementById("multi-results-grid");
  grid.style.display = "grid";
  grid.innerHTML = "";
  document.getElementById("multi-results-actions").style.display = "none"; // покажем после анимации

  let total = 0;
  const cards = [];
  drops.forEach(drop => {
    total += drop.price;
    const el = document.createElement("div");
    el.className = `multi-result-card ${rarityClass(drop.rarity)} reveal-pending`;
    el.innerHTML = `
      <img src="${drop.image}" alt="${drop.name}" loading="lazy">
      <div class="multi-result-card-name">${drop.name}</div>
      <div class="multi-result-card-price">${fmt(drop.price)}</div>
      <button type="button" class="multi-result-sell-btn" data-inv-id="${drop.id}">${t("sell_for_btn")} ${fmt(drop.price)}</button>
    `;
    grid.appendChild(el);
    cards.push({ el, drop });
  });

  // Вместо мгновенного показа всей сетки — последовательно "открываем"
  // карточки одну за другой с небольшой задержкой (как будто прокручивается
  // каждый выбранный кейс), а не моментальный скип всех сразу.
  const STAGGER_MS = 220;
  cards.forEach(({ el, drop }, i) => {
    setTimeout(() => {
      el.classList.remove("reveal-pending");
      el.classList.add("revealed-pop");
      const isRare = ["Covert", "Knife", "Gloves"].includes(drop.rarity);
      playSound(isRare ? "fanfare" : "spinTick");
    }, i * STAGGER_MS);
  });

  const totalRevealTime = cards.length * STAGGER_MS + 350;
  setTimeout(() => {
    updateMultiResultsSummary();
    document.getElementById("multi-results-actions").style.display = "block";
    const anyRare = drops.some(d => ["Covert", "Knife", "Gloves"].includes(d.rarity));
    if (!anyRare) playSound("win");
  }, totalRevealTime);
}

// Пересчитывает и перерисовывает итоговую сумму + текст кнопки
// "Продать все за [Сумма]" на основе того, что осталось в state.lastMultiDrops
// (уменьшается по мере продажи отдельных предметов кнопками под карточками).
function updateMultiResultsSummary() {
  const total = state.lastMultiDrops.reduce((s, d) => s + d.price, 0);
  document.getElementById("multi-results-total").innerHTML =
    `${t("multi_results_total_label")} <b>${fmt(total)}</b>`;
  const sellAllBtn = document.getElementById("multi-sell-all-btn");
  if (state.lastMultiDrops.length) {
    sellAllBtn.disabled = false;
    sellAllBtn.textContent = `${t("sell_all_for_btn")} ${fmt(total)}`;
  } else {
    sellAllBtn.disabled = true;
    sellAllBtn.textContent = t("sell_all_for_btn");
  }
}

// Продажа ОДНОГО предмета прямо с карточки результата (кнопка "Продать за X").
document.getElementById("multi-results-grid").addEventListener("click", async (e) => {
  const btn = e.target.closest(".multi-result-sell-btn");
  if (!btn || btn.disabled) return;
  const invId = btn.dataset.invId;
  if (!invId) return;

  btn.disabled = true;
  try {
    const result = await apiPost("/sell-skin", {
      telegram_id: state.telegramId,
      inventory_id: invId,
    });
    state.balance = result.new_balance;
    updateBalanceDisplay();
    playSound("sell");

    state.lastMultiDrops = state.lastMultiDrops.filter(d => String(d.id) !== String(invId));
    const card = btn.closest(".multi-result-card");
    card.classList.add("sold-out");
    btn.textContent = t("sold_label");
    updateMultiResultsSummary();
  } catch (err) {
    btn.disabled = false;
    tg?.showAlert?.(err.message);
  }
});

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
    playSound("sell");
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    document.getElementById("multi-results-grid").style.display = "none";
    document.getElementById("multi-results-actions").style.display = "none";
    document.getElementById("open-case-btn").style.display = "block";
    state.lastMultiDrops = [];
  }
});

// ============================================
// Vertical Multi-Spin — N параллельных вертикальных лент (count > 1).
// Каждая лента крутится СВЕРХУ ВНИЗ и тормозит по cubic-bezier; каждая
// следующая лента получает +150мс к длительности анимации, поэтому они
// останавливаются каскадом одна за другой, а не все разом.
// ============================================
function runVerticalMultiSpin(caseData, drops) {
  document.getElementById("roulette-wrapper").style.display = "none";
  document.getElementById("multi-results-grid").style.display = "none";
  document.getElementById("multi-results-actions").style.display = "none";
  document.getElementById("open-case-btn").style.display = "none";

  const wrapper = document.getElementById("vertical-spin-wrapper");
  const lanesContainer = document.getElementById("vertical-spin-lanes");
  wrapper.style.display = "block";
  lanesContainer.innerHTML = "";

  const ITEM_HEIGHT = 82;   // высота карточки (64px) + вертикальные отступы (2×9px) — должно совпадать с CSS
  const REEL_LENGTH = 24;   // сколько карточек в каждой ленте
  const WINNING_INDEX = 18; // на этом индексе лента останавливается
  const CASCADE_STEP_MS = 150; // задержка остановки каждой следующей ленты
  const BASE_DURATION_MS = state.openSpeed === "fast" ? 1500 : 3400;

  const pool = caseData.items;
  const laneRefs = [];

  drops.forEach(drop => {
    const lane = document.createElement("div");
    lane.className = "vertical-spin-lane";

    const pointer = document.createElement("div");
    pointer.className = "vertical-spin-pointer-line";

    const track = document.createElement("div");
    track.className = "vertical-spin-track";

    const isRareDrop = ["Knife", "Gloves"].includes(drop.rarity);
    const reel = [];
    for (let i = 0; i < REEL_LENGTH; i++) {
      reel.push(i === WINNING_INDEX ? drop : pool[Math.floor(Math.random() * pool.length)]);
    }

    let winningEl = null;
    reel.forEach((item, i) => {
      const el = document.createElement("div");
      const mystery = isRareDrop && i === WINNING_INDEX;
      el.className = `vertical-spin-item ${rarityClass(item.rarity)}${mystery ? " mystery-reveal" : ""}`;
      el.innerHTML = mystery
        ? `<div class="mystery-glyph">?</div><img src="${item.image}" alt="${item.name}" style="display:none;">`
        : `<img src="${item.image}" alt="${item.name}">`;
      track.appendChild(el);
      if (i === WINNING_INDEX) winningEl = el;
    });

    lane.appendChild(pointer);
    lane.appendChild(track);
    lanesContainer.appendChild(lane);
    laneRefs.push({ lane, track, drop, isRareDrop, winningEl });
  });

  // тиканье во время прокрутки, замедляется естественно вместе с лентами
  let tickCount = 0;
  const tickInterval = setInterval(() => {
    playSound("spinTick");
    tickCount++;
  }, 150);

  // ждём кадр, чтобы браузер посчитал реальную высоту лент перед стартом transition
  requestAnimationFrame(() => {
    laneRefs.forEach(({ lane, track }, i) => {
      const laneHeight = lane.offsetHeight;
      const targetOffset = WINNING_INDEX * ITEM_HEIGHT - laneHeight / 2 + ITEM_HEIGHT / 2;
      const jitter = (Math.random() - 0.5) * (ITEM_HEIGHT * 0.3);
      const duration = BASE_DURATION_MS + i * CASCADE_STEP_MS;
      track.style.transition = `transform ${duration}ms cubic-bezier(0.12, 0.85, 0.15, 1)`;
      track.style.transform = `translateY(-${targetOffset + jitter}px)`;
    });
  });

  const lastLaneDuration = BASE_DURATION_MS + (laneRefs.length - 1) * CASCADE_STEP_MS;

  // Раскрываем "тайну" (нож/перчатки) для каждой ленты сра��у после того,
  // как ИМЕННО ОНА остановилась — не дожидаясь остановки всех остальных.
  laneRefs.forEach(({ isRareDrop, winningEl, drop }, i) => {
    if (!isRareDrop || !winningEl) return;
    const stopTime = BASE_DURATION_MS + i * CASCADE_STEP_MS;
    setTimeout(() => {
      winningEl.classList.add("mystery-flip");
      setTimeout(() => {
        winningEl.classList.remove("mystery-reveal");
        winningEl.innerHTML = `<img src="${drop.image}" alt="${drop.name}">`;
      }, 250);
    }, stopTime + 150);
  });

  setTimeout(() => {
    clearInterval(tickInterval);
    playSound("lock");
    const anyRare = drops.some(d => ["Covert", "Knife", "Gloves"].includes(d.rarity));
    if (anyRare) playSound("fanfare");
    setTimeout(() => {
      wrapper.style.display = "none";
      showMultiResults(drops);
    }, 500);
  }, lastLaneDuration + 100);
}

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

  // Для ножей/перчаток выигрышная позиция едет по ленте как золотая
  // "тайна" (как в самом CS2 — до раскрытия неясно, какой именно нож
  // и с каким StatTrak выпадет), а не сразу с готовым именем/картинкой.
  const isRareDrop = ["Knife", "Gloves"].includes(drop.rarity);

  reel.forEach((item, i) => {
    const el = document.createElement("div");
    const mystery = isRareDrop && i === WINNING_INDEX;
    el.className = `roulette-item ${rarityClass(item.rarity)}${mystery ? " mystery-reveal" : ""}`;
    el.innerHTML = mystery
      ? `
        <div class="mystery-glyph">?</div>
        <img src="${item.image}" alt="${item.name}">
        <span>???</span>
      `
      : `
        <img src="${item.image}" alt="${item.name}">
        <span>${item.name}</span>
      `;
    track.appendChild(el);
    if (mystery) el.dataset.winningSlot = "1";
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

    if (isRareDrop) {
      // Лента остановилась на золотом "?" — держим интригу чуть-чуть,
      // затем переворачиваем плитку и раскрыв��ем настоящий нож/перчатки
      // (тип и StatTrak уже определены сервером в drop, игрок просто их видит).
      const slot = track.querySelector('[data-winning-slot="1"]');
      setTimeout(() => {
        if (slot) {
          slot.classList.add("mystery-flip");
          setTimeout(() => {
            slot.classList.remove("mystery-reveal");
            slot.innerHTML = `
              <img src="${drop.image}" alt="${drop.name}">
              <span>${drop.name}</span>
            `;
          }, 250); // середина flip-анимации — момент подмены содержимого
        }
        playSound("fanfare");
        setTimeout(() => showWinModal(drop), 550);
      }, 900);
    } else {
      const isRare = drop.rarity === "Covert";
      playSound(isRare ? "fanfare" : "win");
      showWinModal(drop);
    }
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
    playSound("sell");
  } catch (e) {
    tg?.showAlert?.(e.message);
  } finally {
    document.getElementById("win-modal").classList.remove("active");
    state.pendingDrop = null;
  }
});

// "Открыть ещё" — закрывает окно результата и сразу возвращает на экран
// того же кейса, чтобы можно было открыть его снова без лишних кликов.
document.getElementById("win-open-again-btn").addEventListener("click", () => {
  document.getElementById("win-modal").classList.remove("active");
  state.pendingDrop = null;
  loadProfile();
  if (state.currentCase) {
    openCaseScreen(state.currentCase);
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

// Те же константы экономики, что и в main.py (STATTRAK_CHANCE,
// STATTRAK_MULTIPLIER) — нужны фронту только для отображения диапазона
// цен категории ножей/перчаток в оверлее, сам ролл всегда считает бэкенд.
const STATTRAK_CHANCE_JS = 0.10;
const STATTRAK_MULTIPLIER_JS = 1.8;

// Оверлей для обычного скина (не нож/перчатки): точный % + цена + отметка
// о доступности StatTrak™-версии именно у этого скина.
function renderRegularOverlay(item) {
  return `
    <span class="contents-item-chance-value">${formatDropChance(item.drop_chance)}</span>
    <span class="contents-item-chance-sep">|</span>
    <span class="contents-item-chance-price">${fmtWithIcon(item.base_price)}</span>
    ${item.stattrak_available ? `<span class="contents-item-st-badge">StatTrak™ доступен</span>` : ""}
  `;
}

// Оверлей для ножей/перчаток — как в самом CS2: не шанс конкретного скина,
// а сводка по ВСЕЙ категории (Обычный / StatTrak) с диапазоном цен.
function renderRareCategoryOverlay(summary) {
  if (!summary) return "";
  return `
    <div class="rare-summary-row">
      <span class="rare-summary-label">Обычный</span>
      <span class="rare-summary-chance">${formatDropChance(summary.regularChance)}</span>
      <span class="rare-summary-price">${fmtNumber(summary.regularMin)}–${fmtWithIcon(summary.regularMax)}</span>
    </div>
    ${summary.canStattrak ? `
    <div class="rare-summary-row rare-summary-st">
      <span class="rare-summary-label">StatTrak™</span>
      <span class="rare-summary-chance">${formatDropChance(summary.stattrakChance)}</span>
      <span class="rare-summary-price">${fmtNumber(summary.stattrakMin)}–${fmtWithIcon(summary.stattrakMax)}</span>
    </div>` : ""}
  `;
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

function getSortedInventory() {
  // Сортировка только по цене (по возрастанию/убыванию) — сам массив
  // state.inventory не мутируется, чтобы порядок из API не терялся.
  return [...state.inventory].sort((a, b) =>
    state.inventorySortDir === "asc" ? a.price - b.price : b.price - a.price
  );
}

function updateInventorySortButton() {
  const label = document.getElementById("inventory-sort-label");
  if (!label) return;
  label.textContent = state.inventorySortDir === "asc"
    ? `↑ ${t("sort_cheap_first")}`
    : `↓ ${t("sort_expensive_first")}`;
}

document.getElementById("inventory-sort-btn").addEventListener("click", () => {
  state.inventorySortDir = state.inventorySortDir === "asc" ? "desc" : "asc";
  document.getElementById("inventory-sort-btn").dataset.dir = state.inventorySortDir;
  updateInventorySortButton();
  renderInventory();
});

function renderInventory() {
  const grid = document.getElementById("inventory-grid");
  const empty = document.getElementById("inventory-empty");
  const toolbar = document.getElementById("inventory-toolbar");
  const disintegrateBar = document.getElementById("disintegrate-bar");

  updateInventorySortButton();

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
  // ВАЖНО: плашку здесь больше НЕ показываем принудительно — её видимость
  // теперь полностью зависит от того, выделены ли предметы прямо сейчас
  // (см. updateInventorySelectionUI ниже, вызывается в конце этой функции).

  grid.innerHTML = "";
  getSortedInventory().forEach(item => {
    const isSelected = state.selectedInventoryIds.has(item.id);
    const card = document.createElement("div");
    card.className = `inventory-card${isSelected ? " selected" : ""}`;
    // ---- Спринт 10: плашка StatTrak™ со счётчиком, точный Float и
    // дублирование категории качества (Factory New / Field-Tested / ...) ----
    // Оранжевая плашка StatTrak рисуется только при stattrak=true и несёт
    // рядом сам счётчик. Категория качества показывается ДВАЖДЫ намеренно
    // (требование ТЗ): коротким кодом в плашке (FT) и полным именем строкой
    // ниже (Field-Tested) — короткий читается в сетке, полный не требует
    // знания аббревиатур.
    const stTag = item.stattrak
      ? `<span class="inv-st-tag">ST™<span>${fmtNumber2(item.stattrak_count)}</span></span>`
      : "";
    const qualityTag = item.quality ? `<span class="inv-quality-tag">${item.quality}</span>` : "";
    const floatLine = item.float_val != null
      ? `<div class="inv-float-line">Float: ${formatFloatValue(item.float_val)}</div>`
      : "";
    const showcaseMark = item.is_in_showcase ? `<div class="inv-showcase-mark" title="В витрине">🏅</div>` : "";

    card.innerHTML = `
      <input type="checkbox" class="inventory-card-checkbox" data-id="${item.id}" ${isSelected ? "checked" : ""}>
      ${showcaseMark}
      <img src="${item.image || ""}" alt="${escapeAttr(item.name)}" data-item-detail="${item.id}">
      <div class="inventory-card-name" data-item-detail="${item.id}">${escapeHtmlText(item.name)}</div>
      <div class="inv-badges">${stTag}${qualityTag}</div>
      <div class="inventory-card-quality">${escapeHtmlText(item.quality_name || "")}</div>
      ${floatLine}
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

  // Спринт 10: тап по картинке/названию открывает карточку предмета с
  // точным Float, категорией качества и счётчиком StatTrak™. Слушаем на
  // самой картинке и названии (а не на всей карточке), чтобы не
  // перехватывать нажатия по чекбоксу выделения и кнопке продажи.
  grid.querySelectorAll("[data-item-detail]").forEach(el => {
    el.addEventListener("click", () => openItemDetail(Number(el.dataset.itemDetail)));
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
        playSound("sell");
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
  const disintegrateBar = document.getElementById("disintegrate-bar");

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

  // Плашка появляется ТОЛЬКО когда есть активное выделение — и только
  // пока пользователь реально находится на вкладке "Инвентарь" (иначе
  // switchScreen уже принудительно её скрыл при переходе на другую вкладку).
  const onInventoryScreen = document.getElementById("screen-inventory").classList.contains("active");
  disintegrateBar.style.display = (onInventoryScreen && selectedCount > 0) ? "block" : "none";
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
    playSound("sell");
    tg?.showAlert?.(t("disintegrate_success"));
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
});

// ============================================
// Крафт / Гарантированный обмен (Trade-Up Contract)
// ============================================
// Никакого риска: сервер ГАРАНТИРОВАННО меняет 5 предметов одной редкости
// + плату за рецепт на 1 предмет следующей редкости, который игрок сам
// выбирает из каталога заранее — случайность здесь только в "физике"
// нового экземпляра (качество/float/StatTrak™), как у любого предмета.

const RARITY_ORDER_JS = ["Consumer", "Industrial", "Mil-Spec", "Restricted", "Classified", "Covert", "Gloves", "Knife"];

function nextCraftRarity(rarity) {
  const idx = RARITY_ORDER_JS.indexOf(rarity);
  if (idx === -1 || idx + 1 >= RARITY_ORDER_JS.length) return null;
  return RARITY_ORDER_JS[idx + 1];
}

async function ensureCraftCatalogLoaded() {
  if (state.craftCatalog) return;
  try {
    const data = await apiGet("/craft-catalog");
    state.craftCatalog = data.catalog || {};
  } catch (e) {
    console.error("Не удалось загрузить каталог крафта:", e);
    state.craftCatalog = {};
  }
}

async function openCraftScreen() {
  state.craftSourceRarity = null;
  state.craftSelectedIds = new Set();
  state.craftTargetName = null;
  await ensureCraftCatalogLoaded();
  document.getElementById("craft-screen").classList.add("active");
  renderCraftSourceGrid();
  updateCraftProgress();
}

function closeCraftScreen() {
  document.getElementById("craft-screen").classList.remove("active");
}

document.getElementById("craft-open-btn").addEventListener("click", openCraftScreen);
document.getElementById("craft-back-btn").addEventListener("click", closeCraftScreen);

function renderCraftSourceGrid() {
  const grid = document.getElementById("craft-source-grid");
  grid.innerHTML = "";

  state.inventory.forEach(item => {
    const isSelected = state.craftSelectedIds.has(item.id);
    // Пока не выбрана "рабочая" редкость — доступны все предметы.
    // После первого выбора — только предметы ТОЙ ЖЕ редкости, остальные
    // визуально гаснут (disabled), а после набора 5 штук гаснут и они.
    const rarityLocked = state.craftSourceRarity && item.rarity !== state.craftSourceRarity;
    const full = state.craftSelectedIds.size >= state.craftItemsRequired && !isSelected;
    const disabled = rarityLocked || full;

    const el = document.createElement("div");
    el.className = `craft-item-card ${rarityClass(item.rarity)}${isSelected ? " selected" : ""}${disabled ? " disabled" : ""}`;
    el.innerHTML = `
      <div class="craft-item-card-check">✓</div>
      <img src="${item.image || ""}" alt="${item.name}">
      <div class="craft-item-card-name">${item.name}</div>
      <div class="craft-item-card-price">${fmt(item.price)}</div>
    `;
    if (!disabled) {
      el.addEventListener("click", () => toggleCraftSourceItem(item));
    }
    grid.appendChild(el);
  });
}

function toggleCraftSourceItem(item) {
  if (state.craftSelectedIds.has(item.id)) {
    state.craftSelectedIds.delete(item.id);
    if (state.craftSelectedIds.size === 0) state.craftSourceRarity = null;
  } else {
    if (state.craftSelectedIds.size >= state.craftItemsRequired) return;
    state.craftSourceRarity = item.rarity;
    state.craftSelectedIds.add(item.id);
  }
  state.craftTargetName = null; // при изменении набора исходников выбор цели сбрасывается
  renderCraftSourceGrid();
  updateCraftProgress();
}

function renderCraftTargetGrid(targetRarity) {
  const section = document.getElementById("craft-target-section");
  const grid = document.getElementById("craft-target-grid");
  const catalog = (state.craftCatalog && state.craftCatalog[targetRarity]) || [];

  if (!catalog.length) {
    section.style.display = "none";
    return;
  }
  section.style.display = "block";
  grid.innerHTML = "";

  catalog.forEach(entry => {
    const isSelected = state.craftTargetName === entry.name;
    const el = document.createElement("div");
    el.className = `craft-item-card ${rarityClass(entry.rarity)}${isSelected ? " selected" : ""}`;
    el.innerHTML = `
      <div class="craft-item-card-check">✓</div>
      <img src="${entry.image || ""}" alt="${entry.name}">
      <div class="craft-item-card-name">${entry.name}</div>
      <div class="craft-item-card-price">${fmtWithIcon(entry.base_price)}</div>
    `;
    el.addEventListener("click", () => {
      state.craftTargetName = entry.name;
      renderCraftTargetGrid(targetRarity);
      updateCraftSubmitState();
    });
    grid.appendChild(el);
  });
}

function updateCraftProgress() {
  const selectedCount = state.craftSelectedIds.size;
  const total = state.craftItemsRequired;
  const circumference = 326.7; // 2*pi*52, совпадает со значением в CSS

  const fill = document.getElementById("craft-progress-fill");
  fill.style.strokeDashoffset = String(circumference * (1 - selectedCount / total));
  document.getElementById("craft-progress-count").textContent = `${selectedCount}/${total}`;

  const hint = document.getElementById("craft-rarity-hint");
  const targetSection = document.getElementById("craft-target-section");

  if (selectedCount === 0) {
    hint.textContent = t("craft_rarity_hint");
    targetSection.style.display = "none";
    state.craftTargetName = null;
  } else if (selectedCount < total) {
    hint.textContent = `${rarityLabel(state.craftSourceRarity)} — ${selectedCount}/${total}`;
    targetSection.style.display = "none";
    state.craftTargetName = null;
  } else {
    const targetRarity = nextCraftRarity(state.craftSourceRarity);
    if (!targetRarity) {
      hint.textContent = t("craft_max_rarity");
      targetSection.style.display = "none";
    } else {
      hint.textContent = t("craft_pick_target_hint");
      renderCraftTargetGrid(targetRarity);
    }
  }

  updateCraftFeeDisplay();
  updateCraftSubmitState();
}

function updateCraftFeeDisplay() {
  const fee = state.craftSourceRarity ? (state.craftFeeByRarity[state.craftSourceRarity] ?? 0) : 0;
  document.getElementById("craft-fee-value").textContent = fmtWithIcon(fee);
}

function updateCraftSubmitState() {
  const fee = state.craftSourceRarity ? (state.craftFeeByRarity[state.craftSourceRarity] ?? 0) : 0;
  const ready =
    state.craftSelectedIds.size === state.craftItemsRequired &&
    !!state.craftTargetName &&
    !!nextCraftRarity(state.craftSourceRarity) &&
    state.balance >= fee;
  document.getElementById("craft-submit-btn").disabled = !ready;
}

document.getElementById("craft-submit-btn").addEventListener("click", async () => {
  const btn = document.getElementById("craft-submit-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const result = await apiPost("/craft", {
      telegram_id: state.telegramId,
      inventory_ids: Array.from(state.craftSelectedIds),
      target_name: state.craftTargetName,
    });

    state.balance = result.new_balance;
    state.inventory = state.inventory.filter(i => !state.craftSelectedIds.has(i.id));
    updateBalanceDisplay();

    const isRare = ["Covert", "Knife", "Gloves"].includes(result.crafted_item.rarity);
    playSound(isRare ? "fanfare" : "win");

    showCraftResult(result.crafted_item);
    handleXpResult(result.xp);
    closeCraftScreen();
    await loadInventory();
  } catch (e) {
    tg?.showAlert?.(e.message || t("craft_not_enough_balance"));
    updateCraftSubmitState();
  } finally {
    btn.disabled = false;
  }
});

function showCraftResult(item) {
  document.getElementById("craft-result-image").src = item.image || "";
  document.getElementById("craft-result-name").textContent = item.name;
  document.getElementById("craft-result-quality").textContent =
    `${item.quality_name || ""}${item.stattrak ? " · StatTrak™" : ""}`;
  document.getElementById("craft-result-price").textContent = fmt(item.price);
  document.getElementById("craft-result-modal").classList.add("active");
}

document.getElementById("craft-result-ok-btn").addEventListener("click", () => {
  document.getElementById("craft-result-modal").classList.remove("active");
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
  state.goldBalance = profile.gold_balance ?? 0;
  state.isVip = profile.is_vip;
  state.vipExpiresAt = profile.vip_expires_at || null;
  if (Array.isArray(profile.inventory)) state.inventory = profile.inventory;
  // P2P-реферальная система: сколько друзей приглашено и сколько 💎
  // пассивно получено с их активности (см. main.py -> _build_profile_payload).
  state.referralsCount = profile.referrals_count ?? 0;
  state.refEarningsTotal = profile.ref_earnings_total ?? 0;
  state.lastProfile = profile; // сохраняем для перерисовки при смене валюты без лишнего запроса

  if (profile.lang) { state.lang = profile.lang; applyTranslations(); }
  if (typeof profile.sound_enabled === "boolean") {
    state.soundEnabled = profile.sound_enabled;
    updateSoundToggleUI();
  }
  // Спринт 12: сервер — источник истины для фона (например, игрок сменил
  // фон на другом устройстве) — применяем поверх того, что уже нарисовали
  // оптимистично из localStorage при старте init().
  if (profile.background && profile.background !== state.background) {
    applyBackground(profile.background);
  }
  updateBalanceDisplay();
  renderProfileScreen(profile);
  maybeShowTermsModal(!!profile.terms_accepted);
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
  document.getElementById("stat-ref-count").textContent = state.referralsCount ?? 0;
  document.getElementById("stat-ref-earnings").textContent = fmtWithIcon(state.refEarningsTotal ?? 0);

  // Топ дроп — берём ИМЕННО persisted-поле top_drop с бэкенда (не
  // most_expensive_item из текущего инвентаря), чтобы карточка не
  // очищалась после продажи предмета.
  const topDropCard = document.getElementById("top-drop-card");
  const topDropEmpty = document.getElementById("top-drop-empty");
  if (profile.top_drop) {
    document.getElementById("top-drop-image").src = profile.top_drop.image || "";
    document.getElementById("top-drop-name").textContent = profile.top_drop.name;
    document.getElementById("top-drop-price").textContent = fmt(profile.top_drop.price);
    topDropCard.style.display = "block";
    topDropEmpty.style.display = "none";
  } else {
    topDropCard.style.display = "none";
    topDropEmpty.style.display = "block";
  }

  document.getElementById("ref-link-input").value =
    `https://t.me/${state.botUsername}?start=ref_${state.telegramId}`;

  // Текст под реф-ссылкой: разовый бонус тебе + другу, и отдельным
  // предложением — постоянный % отчисления с каждой траты друга.
  const commissionPct = Math.round((state.refCommissionPercent ?? 0.05) * 100);
  const refHintBonus = state.lang === "en"
    ? `+${fmtWithIcon(state.refBonusInviter)} for you and +${fmtWithIcon(state.refBonusInvited)} for a friend for every invite.`
    : state.lang === "uk"
      ? `+${fmtWithIcon(state.refBonusInviter)} тобі і +${fmtWithIcon(state.refBonusInvited)} другу за кожне запрошення.`
      : `+${fmtWithIcon(state.refBonusInviter)} тебе и +${fmtWithIcon(state.refBonusInvited)} другу за каждого приглашённого.`;
  const refHintCommission = state.lang === "en"
    ? ` Plus ${commissionPct}% of everything your friend spends — forever.`
    : state.lang === "uk"
      ? ` Плюс ${commissionPct}% з кожної витрати друга — назавжди.`
      : ` Плюс ${commissionPct}% с каждой траты друга — навсегда.`;
  document.getElementById("ref-hint").textContent = refHintBonus + refHintCommission;

  if (profile.rank) renderRankCard(profile.rank);

  // ---- Спринт 10: уровень аккаунта, титул/рамка, витрина ----
  if (profile.level) renderLevelCard(profile.level);
  applyTitlePill(document.getElementById("profile-title-pill"), profile.selected_title_info);
  applyAvatarFrame(document.getElementById("profile-avatar-wrap"), profile.selected_frame_info);
  renderCosmeticsSelectors(profile);
  renderShowcase(profile);

  // Бейдж входящих заявок в друзья — подтягиваем в фоне, чтобы к��опка
  // "Друзья" сразу показывала, что кто-то ждёт ответа.
  refreshFriendsBadgeQuietly();

  // Уведомление о свежеоткрытой косметике: бэкенд отдаёт её только в тот
  // единственный ответ, в котором условие выполнилось впервые.
  if (Array.isArray(profile.newly_unlocked) && profile.newly_unlocked.length) {
    const names = profile.newly_unlocked.map(x => x.name).join(", ");
    tg?.showAlert?.(`${t("cosmetic_unlocked")} ${names}`);
  }
}

// ============================================
// СПРИНТ 10: УРОВЕНЬ АККАУНТА
// ============================================
// level — объект из levels.get_level_progress(): level, xp, xp_into_level,
// xp_needed, progress_percent, showcase_slots, showcase_max_slots,
// next_showcase_slot_level, is_max.
function renderLevelCard(level) {
  const card = document.getElementById("level-card");
  if (!card) return;

  document.getElementById("level-card-num").textContent = level.level;
  document.getElementById("profile-level-badge").textContent = level.level;
  document.getElementById("level-progress-fill").style.width = `${level.progress_percent ?? 0}%`;
  card.classList.toggle("level-max", !!level.is_max);

  document.getElementById("level-xp-line").textContent = level.is_max
    ? t("level_max_line").replace("{xp}", fmtNumber2(level.xp))
    : `${fmtNumber2(level.xp_into_level)} / ${fmtNumber2(level.xp_needed)} XP`;

  // Подсказка про слоты витрины: пока лимит не выбран — говорим, на каком
  // уровне откроется следующий; на максимуме — что все уже открыты.
  const slotsEl = document.getElementById("level-slots-line");
  if (level.next_showcase_slot_level) {
    slotsEl.textContent = t("level_next_slot")
      .replace("{level}", level.next_showcase_slot_level)
      .replace("{slots}", level.showcase_slots);
  } else {
    slotsEl.textContent = t("level_slots_max").replace("{slots}", level.showcase_slots);
  }
}

// Таблица уровней — показывает окно вокруг текущего уровня, а не все 200
// строк: игроку важны ближайшие пороги и то, где дадут слот витрины.
function openLevelTable() {
  const lvl = state.lastProfile?.level?.level || 1;
  const from = Math.max(1, lvl - 4);
  const to = from + 24;

  const rows = [];
  for (let n = from; n <= to; n++) {
    // Порог = 100 * 1.15^(n-1) — та же формула, что и на бэкенде (levels.py).
    const need = Math.round(100 * Math.pow(1.15, n - 1));
    const slots = showcaseSlotsForLevel(n);
    const gained = n > 1 && slots > showcaseSlotsForLevel(n - 1);
    const cls = n === lvl ? "current" : (n < lvl ? "reached" : "");
    rows.push(`
      <div class="level-table-row ${cls}">
        <div class="level-table-lvl">${n}</div>
        <div class="level-table-xp">${fmtNumber2(need)} XP</div>
        ${gained ? `<div class="level-table-slot">🏅 +1</div>` : ""}
      </div>`);
  }
  document.getElementById("level-table-list").innerHTML = rows.join("");
  document.getElementById("level-table-modal").classList.add("active");
}

// Дублирует levels.showcase_slots_for_level() с бэкенда — нужна локально
// только для таблицы уровней (показать, где дадут слот). Источник истины
// всё равно бэкенд: фактическое число слотов приходит в profile.showcase.
function showcaseSlotsForLevel(n) {
  return Math.min(3 + Math.floor(n / 5), 10);
}

// ============================================
// СПРИНТ 10: ТИТУЛ И РАМКА АВАТАРА
// ============================================
// Красит плашку активного титула. info — объект титула с бэкенда
// (cosmetics.title_public): key, name, color, icon. null = титул не выбран.
function applyTitlePill(el, info) {
  if (!el) return;
  if (!info) { el.style.display = "none"; return; }
  el.style.display = "";
  el.textContent = `${info.icon || ""} ${info.name}`.trim();
  el.style.setProperty("--title-color", info.color || "");
}

// Навешивает рамку на обёртку аватара. info — объект рамки
// (cosmetics.frame_public): key, name, color, style ("solid"|"glow"|"animated").
function applyAvatarFrame(el, info) {
  if (!el) return;
  el.classList.remove("has-frame", "frame-glow", "frame-animated");
  if (!info) return;
  el.style.setProperty("--frame-color", info.color || "");
  el.classList.add("has-frame");
  if (info.style === "glow") el.classList.add("frame-glow");
  else if (info.style === "animated") el.classList.add("frame-animated");
}

// Рисует оба селектора (титулы + рамки). Каталог приходит целиком: и
// открытое, и закрытое с текстом условия — закрытые кликабельны, но вместо
// применения показывают, что нужно сделать.
function renderCosmeticsSelectors(profile) {
  renderCosmeticRow("titles-row", profile.titles || [], profile.selected_title, "title");
  renderCosmeticRow("frames-row", profile.frames || [], profile.selected_frame, "frame");
}

function renderCosmeticRow(containerId, items, selectedKey, kind) {
  const box = document.getElementById(containerId);
  if (!box) return;

  // Опция "без титула/рамки" — иначе выбранное нельзя было бы снять.
  const noneChip = `
    <div class="cosmetic-chip ${!selectedKey ? "active" : ""}"
         data-cosmetic-kind="${kind}" data-cosmetic-key="">
      ${t("cosmetic_none")}
    </div>`;

  const chips = items.map(it => {
    const active = it.key === selectedKey;
    const locked = !it.unlocked;
    // Для закрытой косметики показываем прогресс "3/5", если бэкенд его
    // посчитал — так игрок видит, сколько осталось, а не только условие.
    const progress = locked && it.progress_text
      ? `<span class="cosmetic-chip-progress">${escapeHtmlText(it.progress_text)}</span>`
      : "";
    const swatch = kind === "frame"
      ? `<span class="cosmetic-chip-swatch" style="background:${escapeAttr(it.color || "#888")}"></span>`
      : (it.icon ? `<span>${it.icon}</span>` : "");

    return `
      <div class="cosmetic-chip ${active ? "active" : ""} ${locked ? "locked" : ""}"
           style="--chip-color:${escapeAttr(it.color || "")}"
           data-cosmetic-kind="${kind}"
           data-cosmetic-key="${escapeAttr(it.key)}"
           data-cosmetic-locked="${locked ? "1" : ""}"
           data-cosmetic-hint="${escapeAttr(it.requirement_text || "")}">
        ${swatch}<span>${escapeHtmlText(it.name)}</span>${progress}
      </div>`;
  }).join("");

  box.innerHTML = noneChip + chips;
}

// Применяет выбор титула/рамки. Закрытая косметика не отправляется на
// сервер — вместо запроса показываем условие разблокировки.
async function selectCosmetic(kind, key, locked, hint) {
  if (locked) {
    tg?.showAlert?.(hint || t("cosmetic_locked"));
    return;
  }
  try {
    const res = await apiPost("/profile/select-cosmetic", {
      telegram_id: state.telegramId,
      kind,
      key: key || null,
    });
    // Обновляем локальный профиль и перерисовываем — без полного
    // перезапроса, ответ уже содержит новое состояние косметики.
    if (state.lastProfile) {
      state.lastProfile.selected_title = res.selected_title;
      state.lastProfile.selected_frame = res.selected_frame;
      state.lastProfile.selected_title_info = res.selected_title_info;
      state.lastProfile.selected_frame_info = res.selected_frame_info;
      renderProfileScreen(state.lastProfile);
    }
    playSound("click");
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
}

// ============================================
// СПРИНТ 10: ВИТРИНА ЛУЧШИХ СКИНОВ
// ============================================
// Рисует ровно max_slots ячеек: занятые предметами, свободные пунктиром и
// закрытые (сверх текущего лимита уровня) — приглушённые с номером уровня,
// на котором откроются. Так игрок видит всю перспективу расширения.
function renderShowcase(profile) {
  const sc = profile.showcase;
  const grid = document.getElementById("showcase-grid");
  if (!sc || !grid) return;

  document.getElementById("showcase-counter").textContent = `${sc.items.length} / ${sc.slots}`;

  const cells = [];
  for (let i = 0; i < sc.max_slots; i++) {
    if (i < sc.items.length) {
      cells.push(showcaseSlotHtml(sc.items[i]));
    } else if (i < sc.slots) {
      cells.push(`<div class="showcase-slot empty">+</div>`);
    } else {
      // Уровень, на котором откроется именно этот слот: слот №i (0-based)
      // соответствует (i - 2)-му бонусному слоту, т.е. уровню (i-2)*5.
      const unlockLevel = (i - 2) * 5;
      cells.push(`<div class="showcase-slot locked">🔒<br>${t("level_short")} ${unlockLevel}</div>`);
    }
  }
  grid.innerHTML = cells.join("");

  const hint = document.getElementById("showcase-hint");
  hint.textContent = sc.next_slot_level
    ? t("showcase_hint").replace("{level}", sc.next_slot_level)
    : t("showcase_hint_max");
}

// Ячейка витрины с предметом. Используется и в своём профиле, и в
// публичной карточке друга (friends.js), поэтому лежит здесь как общая.
function showcaseSlotHtml(item) {
  const st = item.stattrak ? `<div class="st-mini">ST™</div>` : "";
  return `
    <div class="showcase-slot ${rarityClass(item.rarity)}" data-showcase-item="${item.id}">
      ${st}
      <img src="${escapeAttr(item.image || "")}" alt="${escapeAttr(item.name)}">
      <div class="showcase-slot-name">${escapeHtmlText(item.name)}</div>
      <div class="showcase-slot-price">${fmt(item.price)}</div>
    </div>`;
}

// ============================================
// СПРИНТ 10: КАРТОЧКА ПРЕДМЕТА (Float / StatTrak / качество)
// ============================================
function openItemDetail(inventoryId) {
  const item = state.inventory.find(i => i.id === inventoryId);
  if (!item) return;

  state.itemDetailId = inventoryId;

  document.getElementById("item-detail-image").src = item.image || "";
  document.getElementById("item-detail-name").textContent = item.name;

  const rarityEl = document.getElementById("item-detail-rarity");
  rarityEl.textContent = rarityLabel(item.rarity);
  rarityEl.className = `item-detail-rarity ${rarityClass(item.rarity)}`;
  // Цвет редкости берём из той же CSS-переменной, что и рамки карточек,
  // чтобы палитра совпадала с сеткой инвентаря.
  rarityEl.style.color = `var(--rarity-${item.rarity.toLowerCase().replace("mil-spec", "milspec")})`;

  // Оранжевая плашка StatTrak™ + счётчик
  const stBox = document.getElementById("item-detail-st");
  if (item.stattrak) {
    stBox.style.display = "inline-flex";
    document.getElementById("item-detail-st-count").textContent = fmtNumber2(item.stattrak_count);
  } else {
    stBox.style.display = "none";
  }

  // Категория качества полным именем + точный Float
  document.getElementById("item-detail-quality").textContent =
    item.quality_name ? `${item.quality_name} (${item.quality})` : (item.quality || "—");
  document.getElementById("item-detail-float").textContent =
    item.float_val != null ? formatFloatValue(item.float_val) : "—";
  document.getElementById("item-detail-price").textContent = fmt(item.price);

  // Маркер на шкале Float: позиция = само значение (шкала 0..1)
  const marker = document.getElementById("item-detail-float-marker");
  if (item.float_val != null) {
    marker.style.display = "";
    marker.style.left = `${Math.min(100, Math.max(0, item.float_val * 100))}%`;
  } else {
    marker.style.display = "none";
  }

  // Кнопка витрины переключает состояние — надпись зависит от того, в
  // витрине предмет уже или ещё нет.
  const btn = document.getElementById("item-detail-showcase-btn");
  btn.textContent = item.is_in_showcase ? `🏅 ${t("showcase_remove")}` : `🏅 ${t("showcase_add")}`;

  document.getElementById("item-detail-modal").classList.add("active");
}

// Закрепление/снятие предмета в Витрине. Лимит слотов проверяет бэкенд —
// здесь только показываем его ответ.
async function toggleShowcaseItem() {
  const id = state.itemDetailId;
  const item = state.inventory.find(i => i.id === id);
  if (!item) return;

  try {
    const res = await apiPost("/profile/showcase/toggle", {
      telegram_id: state.telegramId,
      inventory_id: id,
    });
    item.is_in_showcase = res.is_in_showcase;
    document.getElementById("item-detail-modal").classList.remove("active");
    renderInventory();
    loadProfile();   // перерисовать витрину в профиле новым составом
    playSound("click");
  } catch (e) {
    tg?.showAlert?.(e.message);
  }
}

// Точное значение Float с 6 знаками — ТЗ требует вид "Float: 0.013412",
// поэтому нули в конце НЕ обрезаем (иначе 0.013400 выглядел бы как 0.0134
// и терял ощущение точного измерения).
function formatFloatValue(v) {
  return Number(v).toFixed(6);
}

// ---- Утилиты экранирования ----
// Все строки от бэкенда (имена скинов, ники и username друзей) попадают в
// innerHTML, поэтому их обязательно прогонять через экранирование: ник вида
// <img onerror=...> иначе исполнился бы как разметка.
function escapeHtmlText(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function escapeAttr(s) {
  return escapeHtmlText(s);
}

// Целое число с разделителями групп — для счётчиков (кейсы, StatTrak,
// XP). Отличается от fmt/fmtNumber тем, что НЕ конвертирует валюту и не
// добавляет копейки: это счётчик, а не денежная сумма.
function fmtNumber2(n) {
  return Number(n ?? 0).toLocaleString("en-US");
}

// ============================================
// Карточка ранга (профиль) + модалка "Новый ранг!"
// ============================================
// rank — объект из ranks.get_rank_progress() (см. ranks.py): level, name(_en/_uk),
// icon, xp, next_min_xp, next_name(_en/_uk), xp_to_next, progress_percent, is_max.
function rankLocalizedName(rank, field) {
  const suffix = state.lang === "en" ? "_en" : state.lang === "uk" ? "_uk" : "";
  return rank[`${field}${suffix}`] || rank[field];
}

function renderRankCard(rank) {
  const card = document.getElementById("rank-card");
  document.getElementById("rank-icon").textContent = rank.icon || "🔰";
  document.getElementById("rank-name").textContent = rankLocalizedName(rank, "name");
  document.getElementById("rank-progress-fill").style.width = `${rank.progress_percent ?? 0}%`;
  card.classList.toggle("rank-max", !!rank.is_max);

  if (rank.is_max) {
    document.getElementById("rank-xp-line").textContent = t("rank_max_line").replace("{xp}", rank.xp);
    document.getElementById("rank-next-line").textContent = t("rank_next_line_max");
  } else {
    document.getElementById("rank-xp-line").textContent =
      t("rank_xp_line").replace("{xp}", rank.xp).replace("{next}", rank.next_min_xp);
    document.getElementById("rank-next-line").textContent =
      t("rank_next_line").replace("{name}", rankLocalizedName(rank, "next_name")).replace("{xp}", rank.xp_to_next);
  }
}

// Очередь событий повышения ранга — несколько уровней могут прийти за одно
// крупное начисление XP, показываем модалки по одной, а не все разом.
function enqueueRankUps(rankUpEvents) {
  if (!Array.isArray(rankUpEvents) || !rankUpEvents.length) return;
  state.rankUpQueue.push(...rankUpEvents);
  if (!state.rankUpModalActive) showNextRankUp();
}

function showNextRankUp() {
  const ev = state.rankUpQueue.shift();
  if (!ev) {
    state.rankUpModalActive = false;
    // Спринт 10: ранговая очередь опустела — если за то же начисление XP
    // накопились и повышения уровня, показываем их сразу следом, иначе они
    // остались бы висеть в очереди до следующего начисления.
    if (state.levelUpQueue.length && !state.levelUpModalActive) {
      showNextLevelUp();
      return;
    }
    loadProfile(); // подтягиваем актуальную карточку ранга после всей очереди
    return;
  }
  state.rankUpModalActive = true;

  document.getElementById("rankup-icon").textContent = ev.icon || "⭐";
  document.getElementById("rankup-name").textContent = ev.name || "";
  document.getElementById("rankup-bonus").textContent = `+${fmt(ev.bonus_crystals || 0)}`;

  const itemCard = document.getElementById("rankup-item-card");
  if (ev.reward_item) {
    document.getElementById("rankup-item-image").src = ev.reward_item.image || "";
    document.getElementById("rankup-item-name").textContent = ev.reward_item.name;
    document.getElementById("rankup-item-price").textContent = fmt(ev.reward_item.price);
    itemCard.style.display = "block";
  } else {
    itemCard.style.display = "none";
  }

  playSound("fanfare");
  haptic("success");
  document.getElementById("rankup-modal").classList.add("active");
}

document.getElementById("rankup-ok-btn").addEventListener("click", () => {
  document.getElementById("rankup-modal").classList.remove("active");
  setTimeout(showNextRankUp, 250);
});

// ============================================
// СПРИНТ 10: обработчики (уровень, косметика, витрина, карточка предмета)
// ============================================
document.getElementById("levelup-ok-btn").addEventListener("click", () => {
  document.getElementById("levelup-modal").classList.remove("active");
  setTimeout(showNextLevelUp, 250);
});

document.getElementById("level-info-btn").addEventListener("click", openLevelTable);
document.getElementById("level-table-close-btn").addEventListener("click", () => {
  document.getElementById("level-table-modal").classList.remove("active");
});

document.getElementById("item-detail-close-btn").addEventListener("click", () => {
  document.getElementById("item-detail-modal").classList.remove("active");
});
document.getElementById("item-detail-showcase-btn").addEventListener("click", toggleShowcaseItem);

// Выбор титула/рамки — делегированно на контейнер: чипы полностью
// перерисовываются при каждом рендере профиля, поэтому слушатели на самих
// чипах умирали бы вместе с innerHTML.
document.getElementById("cosmetics-card").addEventListener("click", (e) => {
  const chip = e.target.closest(".cosmetic-chip");
  if (!chip) return;
  selectCosmetic(
    chip.dataset.cosmeticKind,
    chip.dataset.cosmeticKey,
    chip.dataset.cosmeticLocked === "1",
    chip.dataset.cosmeticHint,
  );
});

// Тап по предмету в витрине открывает ту же карточку Float/StatTrak, что и
// из инвентаря — предмет ищется в state.inventory по id.
document.getElementById("showcase-grid").addEventListener("click", (e) => {
  const cell = e.target.closest("[data-showcase-item]");
  if (cell) openItemDetail(Number(cell.dataset.showcaseItem));
});

// Вызывать после КАЖДОГО ответа бэкенда, содержащего поле xp (см. _award_xp
// в main.py — открытие кейсов, крафт, мини-игры, бонус, ежедневная награда, реклама).
function handleXpResult(xpInfo) {
  if (!xpInfo) return;
  if (xpInfo.rank_up) enqueueRankUps(xpInfo.rank_up);
  // Спринт 10: повышения уровня аккаунта. Своя очередь, независимая от
  // ранговой — за одно начисление можно поднять и ранг, и несколько уровней;
  // модалки не должны накладываться друг на друга.
  if (xpInfo.level_up) enqueueLevelUps(xpInfo.level_up);
}

// ============================================
// СПРИНТ 10: очередь модалок "Новый уровень!"
// ============================================
function enqueueLevelUps(levelUpEvents) {
  if (!Array.isArray(levelUpEvents) || !levelUpEvents.length) return;
  state.levelUpQueue.push(...levelUpEvents);
  // Ранговая модалка приоритетнее: если она сейчас на экране, уровни
  // подождут в очереди и покажутся после неё (см. showNextRankUp -> loadProfile).
  if (!state.levelUpModalActive && !state.rankUpModalActive) showNextLevelUp();
}

function showNextLevelUp() {
  const ev = state.levelUpQueue.shift();
  if (!ev) {
    state.levelUpModalActive = false;
    loadProfile();  // обновить карточку уровня и витрину после всей очереди
    return;
  }
  state.levelUpModalActive = true;

  document.getElementById("levelup-num").textContent = ev.level;

  // Строка "+1 слот витрины" — только на уровнях, кратных 5 (пока не
  // достигнут максимум 10 слотов).
  const slotLine = document.getElementById("levelup-slot-line");
  if (ev.showcase_slot_gained) {
    slotLine.style.display = "";
    slotLine.textContent = t("levelup_slot_gained").replace("{slots}", ev.showcase_slots);
  } else {
    slotLine.style.display = "none";
  }

  const unlockLine = document.getElementById("levelup-unlock-line");
  unlockLine.style.display = "none";

  playSound("fanfare");
  haptic("success");
  document.getElementById("levelup-modal").classList.add("active");
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
  const goldValueEl = document.getElementById("gold-value");
  if (goldValueEl) goldValueEl.textContent = truncateTo2(state.goldBalance || 0).toLocaleString("en-US");
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
    tg?.showAlert?.(`+${fmtWithIcon(result.reward)} ${t("ad_reward_toast")}`);
    handleXpResult(result.xp);
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
    tg?.showAlert?.(`+${fmtWithIcon(result.reward)} ${t("bonus_claimed_toast")}`);
    startBonusCountdown(result.cooldown_seconds);
    handleXpResult(result.xp);
  } catch (e) {
    tg?.showAlert?.(e?.message || t("ads_unavailable"));
  }
});

// ============================================
// Ежедневный бонус (Daily Streak, 1-7 день)
// ============================================
const DAILY_DAY_ICONS = { crystals: "💎", case: "🎁", gold: "💰", vip: "⭐" };

function dailyRewardLabel(rewardDef) {
  if (rewardDef.type === "crystals") return fmtWithIcon(rewardDef.amount);
  if (rewardDef.type === "case") return t("daily_reward_case");
  if (rewardDef.type === "gold") return `${rewardDef.amount} 💰`;
  if (rewardDef.type === "vip") return t("daily_reward_vip").replace("{h}", rewardDef.hours);
  return "";
}

function renderDailyDays(data) {
  const grid = document.getElementById("daily-days-grid");
  grid.innerHTML = "";
  data.rewards.forEach(r => {
    const isClaimedDay = r.day < data.current_day || (r.day === data.current_day && data.claimed_today);
    const isCurrent = r.day === data.current_day && !data.claimed_today;
    const el = document.createElement("div");
    el.className = `daily-day-card ${isClaimedDay ? "claimed" : ""} ${isCurrent ? "current" : ""} ${r.day === 7 ? "jackpot" : ""}`.trim();
    el.innerHTML = `
      <div class="day-num">${t("daily_day_label").replace("{n}", r.day)}</div>
      <div class="day-icon">${DAILY_DAY_ICONS[r.type] || currencyIcon()}</div>
      <div class="day-reward">${dailyRewardLabel(r)}</div>
    `;
    grid.appendChild(el);
  });

  document.getElementById("daily-streak-label").innerHTML =
    t("daily_streak_label").replace("{n}", `<b>${data.streak}</b>`);

  const mega = document.getElementById("daily-mega-hint");
  if (mega) {
    const left = Math.max(0, data.mega_bonus_threshold - data.streak);
    mega.textContent = left > 0
      ? t("daily_mega_hint").replace("{n}", left).replace("{gold}", data.mega_bonus_gold)
      : "";
  }

  const btn = document.getElementById("daily-claim-btn");
  btn.textContent = data.claimed_today ? t("daily_claimed_btn") : t("daily_claim_btn");
  btn.disabled = !!data.claimed_today;
}

async function loadDailyStatus() {
  try {
    const data = await apiGet(`/streak/status?telegram_id=${state.telegramId}`);
    state.dailyStatus = data;
    renderDailyDays(data);
  } catch (e) {
    console.error("Ошибка загрузки статуса стрика:", e);
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

  if (reward.type === "crystals") {
    icon.textContent = currencyIcon();
    nameEl.textContent = t("daily_day_label").replace("{n}", reward.day);
    valueEl.textContent = fmt(reward.amount);
  } else if (reward.type === "case") {
    icon.textContent = "🎁";
    nameEl.textContent = `${reward.case_name}: ${reward.item.name}`;
    valueEl.textContent = fmt(reward.item.price);
  } else if (reward.type === "gold") {
    icon.textContent = "💰";
    nameEl.textContent = t("daily_reward_gold");
    valueEl.textContent = `${reward.amount} 💰`;
  } else if (reward.type === "vip") {
    icon.textContent = "⭐";
    nameEl.textContent = reward.already_permanent_vip
      ? t("daily_reward_vip_already")
      : t("daily_reward_vip").replace("{h}", reward.hours);
    valueEl.textContent = "";
  }

  if (result.mega_bonus_awarded) {
    promoEl.style.display = "block";
    promoEl.textContent = `${t("daily_mega_bonus_toast")} +${result.mega_bonus_gold} 💰`;
  }

  playSound(reward.type === "case" || reward.type === "vip" ? "fanfare" : "win");
  haptic("success");
  document.getElementById("daily-result-modal").classList.add("active");
}

document.getElementById("daily-result-ok-btn").addEventListener("click", () => {
  document.getElementById("daily-result-modal").classList.remove("active");
});

document.getElementById("daily-claim-btn").addEventListener("click", async () => {
  try {
    const result = await apiPost("/streak/claim", { telegram_id: state.telegramId });
    state.balance = result.new_balance;
    state.goldBalance = result.new_gold_balance;
    updateBalanceDisplay();
    showDailyResult(result);
    loadDailyStatus();
  } catch (e) {
    tg?.showAlert?.(e?.message || t("daily_already_claimed_toast"));
  }
});

// ============================================
// Ежедневное колесо удачи (Daily Wheel, Спринт 6)
// ============================================
function wheelSectorIcon(sector) {
  if (sector.type === "crystals") return "💎";
  if (sector.type === "gold") return "💰";
  if (sector.type === "vip") return "⭐";
  if (sector.type === "case") return "🎁";
  return "🎲";
}

function wheelSectorAmountText(sector) {
  if (sector.type === "crystals") return fmtNumber(sector.amount);
  if (sector.type === "gold") return `${sector.amount}`;
  if (sector.type === "vip") return `${sector.hours}${state.lang === "en" ? "h" : "ч"}`;
  return "";
}

function renderWheelLabels(sectors) {
  const wrap = document.getElementById("wheel-labels");
  wrap.innerHTML = "";
  const count = sectors.length;
  const arc = 360 / count;
  const radius = 85;

  sectors.forEach((sector, idx) => {
    const centerDeg = idx * arc + arc / 2;
    const outer = document.createElement("div");
    outer.className = "wheel-sector-label";
    outer.style.transform = `rotate(${centerDeg}deg) translate(0, -${radius}px)`;

    const inner = document.createElement("div");
    inner.className = "wheel-sector-label-inner";
    inner.style.transform = `translate(-50%, -50%) rotate(${-centerDeg}deg)`;
    inner.innerHTML = `
      <span class="wheel-sector-icon">${wheelSectorIcon(sector)}</span>
      <span class="wheel-sector-amount">${wheelSectorAmountText(sector)}</span>
    `;

    outer.appendChild(inner);
    wrap.appendChild(outer);
  });
}

function updateWheelHintAndButton(status) {
  const hintEl = document.getElementById("wheel-hint");
  const btn = document.getElementById("wheel-spin-btn");
  hintEl.classList.remove("wheel-hint-ready");

  if (state.wheelSpinning) return;

  if (status.free_spin_available) {
    hintEl.innerHTML = t("wheel_free_hint");
    hintEl.classList.add("wheel-hint-ready");
    btn.disabled = false;
    btn.textContent = t("wheel_spin_btn");
    return;
  }

  if (status.paid_spins_left <= 0) {
    hintEl.textContent = t("wheel_no_spins_left");
    btn.disabled = true;
    btn.textContent = t("wheel_spin_btn");
    return;
  }

  const goldOk = (state.goldBalance || 0) >= status.paid_spin_gold_cost;
  hintEl.innerHTML = `${t("wheel_paid_hint")} · ${t("wheel_paid_left")}: <b>${status.paid_spins_left}</b>`;
  btn.disabled = !goldOk;
  btn.textContent = goldOk ? t("wheel_spin_btn") : t("wheel_no_gold");
}

function stopWheelCountdown() {
  if (state.wheelCountdownInterval) {
    clearInterval(state.wheelCountdownInterval);
    state.wheelCountdownInterval = null;
  }
}

function startWheelCountdown(secondsLeft) {
  stopWheelCountdown();
  let remaining = secondsLeft;
  const hintEl = document.getElementById("wheel-hint");

  function tick() {
    if (state.wheelSpinning) return;
    if (remaining <= 0) {
      stopWheelCountdown();
      loadWheelStatus();
      return;
    }
    const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
    const ss = String(remaining % 60).padStart(2, "0");
    hintEl.innerHTML = `${t("wheel_free_in")} <b>${mm}:${ss}</b>`;
    remaining -= 1;
  }

  tick();
  state.wheelCountdownInterval = setInterval(tick, 1000);
}

async function loadWheelStatus() {
  try {
    const status = await apiGet(`/wheel/status?telegram_id=${state.telegramId}`);
    state.wheelStatus = status;

    if (!state.wheelSectorsRendered) {
      renderWheelLabels(status.sectors);
      state.wheelSectorsRendered = true;
    }

    updateWheelHintAndButton(status);
    if (!status.free_spin_available) {
      startWheelCountdown(status.seconds_until_free_spin);
    } else {
      stopWheelCountdown();
    }
  } catch (e) {
    console.error("Ошибка загрузки статуса колеса:", e);
  }
}

function openWheelModal() {
  document.getElementById("wheel-modal").classList.add("active");
  loadWheelStatus();
}

document.getElementById("open-wheel-modal-btn").addEventListener("click", openWheelModal);
document.getElementById("wheel-earn-btn").addEventListener("click", openWheelModal);

document.getElementById("wheel-close-btn").addEventListener("click", () => {
  document.getElementById("wheel-modal").classList.remove("active");
  if (!state.wheelSpinning) stopWheelCountdown();
});
document.getElementById("wheel-modal").addEventListener("click", (e) => {
  if (e.target.id === "wheel-modal") {
    e.currentTarget.classList.remove("active");
    if (!state.wheelSpinning) stopWheelCountdown();
  }
});

function showWheelResult(result) {
  const reward = result.reward;
  const icon = document.getElementById("wheel-result-icon");
  const nameEl = document.getElementById("wheel-result-name");
  const valueEl = document.getElementById("wheel-result-value");
  valueEl.className = "win-item-price";

  if (reward.type === "crystals") {
    icon.textContent = "💎";
    nameEl.textContent = t("wheel_sector_crystals");
    valueEl.textContent = fmt(reward.amount);
  } else if (reward.type === "gold") {
    icon.textContent = "💰";
    nameEl.textContent = t("wheel_sector_gold");
    valueEl.textContent = `💰 ${reward.amount}`;
    valueEl.classList.add("wheel-result-gold");
  } else if (reward.type === "vip") {
    icon.textContent = "⭐";
    nameEl.textContent = t("wheel_sector_vip");
    valueEl.textContent = "";
  } else if (reward.type === "case") {
    icon.textContent = "🎁";
    nameEl.textContent = `${t("wheel_sector_case")}: ${reward.item.name}`;
    valueEl.textContent = fmt(reward.item.price);
  }

  playSound(reward.type === "case" || reward.type === "vip" ? "fanfare" : "win");
  haptic("success");
  document.getElementById("wheel-result-modal").classList.add("active");
}

document.getElementById("wheel-result-ok-btn").addEventListener("click", () => {
  document.getElementById("wheel-result-modal").classList.remove("active");
});

document.getElementById("wheel-spin-btn").addEventListener("click", async () => {
  if (state.wheelSpinning) return;
  const disc = document.getElementById("wheel-disc");
  const btn = document.getElementById("wheel-spin-btn");

  try {
    state.wheelSpinning = true;
    btn.disabled = true;
    btn.textContent = t("wheel_spinning");
    stopWheelCountdown();

    const result = await apiPost("/wheel/spin", { telegram_id: state.telegramId });

    haptic("light");
    // Всегда крутим ВПЕРЁД от текущего накопленного угла, а не абсолютно —
    // иначе при следующем спине с меньшим "снапом" диск визуально крутился
    // бы назад вместо продолжения по часовой стрелке.
    const baseFull = Math.floor(state.wheelCurrentRotation / 360) * 360;
    const targetRotation = baseFull + result.angle_degrees;
    state.wheelCurrentRotation = targetRotation;
    disc.style.transform = `rotate(${targetRotation}deg)`;

    setTimeout(() => {
      state.balance = result.new_balance;
      state.goldBalance = result.new_gold_balance;
      if (result.reward.type === "vip" && result.reward.vip_expires_at) {
        state.isVip = true;
        state.vipExpiresAt = result.reward.vip_expires_at;
      }
      updateBalanceDisplay();
      showWheelResult(result);
      loadProfile();
      state.wheelSpinning = false;
      loadWheelStatus();
    }, 5100);
  } catch (e) {
    state.wheelSpinning = false;
    btn.disabled = false;
    btn.textContent = t("wheel_spin_btn");
    tg?.showAlert?.(e?.message || t("wheel_no_gold"));
    loadWheelStatus();
  }
});

// ============================================
// СОЦИАЛЬНЫЕ ЗАДАНИЯ (Free Gold Tasks, Спринт 7)
// ============================================
const TASK_ICONS = {
  telegram_channel: "📢",
  telegram_chat: "💬",
  referrals: "👥",
  profile: "🖼️",
};

function renderTasks(data) {
  const list = document.getElementById("tasks-list");
  list.innerHTML = "";

  data.tasks.forEach(task => {
    const el = document.createElement("div");
    el.className = `task-card ${task.completed ? "completed" : ""}`.trim();
    el.innerHTML = `
      <div class="task-icon">${TASK_ICONS[task.task_type] || "✅"}</div>
      <div class="task-info">
        <div class="task-title">${task.title}</div>
        <div class="task-desc">${task.description || ""}</div>
        <div class="task-reward">+${task.reward_gold} 💰</div>
      </div>
      <button class="btn-primary small task-action-btn" data-task-key="${task.key}">
        ${task.completed ? t("task_done_btn") : (task.action_url ? t("task_open_btn") : t("task_check_btn"))}
      </button>
    `;

    const btn = el.querySelector(".task-action-btn");
    if (task.completed) {
      btn.disabled = true;
    } else {
      btn.addEventListener("click", () => onTaskActionClick(task));
    }

    list.appendChild(el);
  });
}

async function loadTasks() {
  try {
    const data = await apiGet(`/tasks/list?telegram_id=${state.telegramId}`);
    state.goldBalance = data.gold_balance;
    updateBalanceDisplay();
    renderTasks(data);
  } catch (e) {
    console.error("Ошибка загрузки заданий:", e);
  }
}

async function onTaskActionClick(task) {
  // Для заданий с внешней ссылкой (подписка на канал/чат) — сперва
  // открываем ссылку, чтобы пользователь реально успел подписаться,
  // саму проверку запускаем сразу же following (Telegram не даёт узнать,
  // когда именно пользователь вернётся из canала, поэтому проверяем
  // оптимистично — если рано, просто покажем "не выполнено").
  if (task.action_url) {
    tg?.openTelegramLink?.(task.action_url) || window.open(task.action_url, "_blank");
  }
  await checkTask(task.key);
}

async function checkTask(taskKey) {
  try {
    const result = await apiPost("/tasks/check", { telegram_id: state.telegramId, task_key: taskKey });
    if (result.success) {
      state.goldBalance = result.new_gold_balance;
      state.balance = result.new_balance;
      updateBalanceDisplay();
      haptic("success");
      tg?.showAlert?.(t("task_completed_toast").replace("{gold}", result.reward_gold));
    } else {
      haptic("error");
      tg?.showAlert?.(t("task_not_verified_toast"));
    }
    loadTasks();
  } catch (e) {
    tg?.showAlert?.(e?.message || t("task_check_error_toast"));
  }
}

function openTasksModal() {
  document.getElementById("tasks-modal").classList.add("active");
  loadTasks();
}

document.getElementById("open-tasks-modal-btn").addEventListener("click", openTasksModal);
document.getElementById("tasks-earn-btn").addEventListener("click", openTasksModal);

document.getElementById("tasks-close-btn").addEventListener("click", () => {
  document.getElementById("tasks-modal").classList.remove("active");
});
document.getElementById("tasks-modal").addEventListener("click", (e) => {
  if (e.target.id === "tasks-modal") e.currentTarget.classList.remove("active");
});

// ============================================
// ХАБ МИНИ-ИГР — единый полноэкранный контейнер,
// в который динамически подгружается разметка нужной игры.
// ============================================
const GAME_TITLES = {
  rocket: () => `🚀 ${t("game_rocket")}`,
  upgrader: () => `🔺 ${t("game_upgrader")}`,
  crafter: () => `🧪 ${t("game_crafter")}`,
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
  // На случай прямого переключения между играми без прохода ��ерез "Назад" —
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
    this.starting = false;
    this.pollTimer = null;
    this.autoCashoutTimer = null;
    this.cashedOut = false;
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

    document.getElementById("rocket-play-btn").addEventListener("click", () => {
      // Одна и та же кнопка: "Играть" пока полёта нет, "Забрать" в любой
      // момент полёта — ручной вывод работает даже если задан авто-вывод.
      if (this.playing) this.manualCashout();
      else this.startFlight();
    });
  },

  setPlayButton({ label, mode, disabled }) {
    const btn = document.getElementById("rocket-play-btn");
    if (!btn) return;
    btn.textContent = label;
    btn.className = mode === "cashout" ? "btn-primary full rocket-cashout-active" : "btn-primary full";
    btn.disabled = !!disabled;
  },

  async startFlight() {
    // Синхронная блокировка немедленно — не даёт двойному клику отправить
    // два /start подряд, пока первый ответ ещё не пришёл.
    if (this.playing || this.starting) return;
    this.starting = true;
    this.setPlayButton({ label: t("upgrade_spinning") || "…", mode: "play", disabled: true });

    const betAmount = parseFloat(document.getElementById("rocket-bet-input").value);
    const autoCashoutAt = parseFloat(document.getElementById("rocket-target-slider").value);

    if (!betAmount || betAmount <= 0) {
      tg?.showAlert?.(t("bet_invalid"));
      this.starting = false;
      this.setPlayButton({ label: t("play_btn"), mode: "play", disabled: false });
      return;
    }
    if (betAmount > state.balance) {
      tg?.showAlert?.(t("balance_low"));
      this.starting = false;
      this.setPlayButton({ label: t("play_btn"), mode: "play", disabled: false });
      return;
    }

    document.getElementById("rocket-result").classList.remove("show");
    haptic("light");

    try {
      const result = await apiPost("/minigames/crash/start", {
        telegram_id: state.telegramId,
        bet_amount: betAmount,
        auto_cashout_at: autoCashoutAt || null,
      });

      state.balance = result.new_balance;
      updateGameScreenBalance();

      this.starting = false;
      this.betAmount = betAmount;
      this.autoCashoutAt = autoCashoutAt;
      this.cashedOut = false;
      document.getElementById("rocket-bet-input").disabled = true;
      document.getElementById("rocket-target-slider").disabled = true;
      // Единственная активная кнопка на время полёта — "Забрать": можно
      // нажать на любом X, вне зависимости от заданного авто-вывода.
      this.setPlayButton({ label: `${t("cashout_btn") || "Забрать"} (1.00x)`, mode: "cashout", disabled: false });
      activeSessionCashout = () => this.manualCashout(true);
      this.playFlight();
    } catch (e) {
      this.starting = false;
      this.setPlayButton({ label: t("play_btn"), mode: "play", disabled: false });
      tg?.showAlert?.(e.message);
    }
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

  // Живой полёт: множитель считается в реальном времени по той же формуле,
  // что и на бэкенде (growthCurve), а ракета летит, пока её либо не заберут
  // вручную ("Забрать" — доступна на ЛЮБОМ X всё время полёта), либо по��а
  // сервер не сообщит через /poll, что она уже лопнула.
  playFlight() {
    this.playing = true;
    const statusEl = document.getElementById("rocket-canvas-status");
    const multEl = document.getElementById("rocket-canvas-mult");
    statusEl.textContent = "🚀 " + t("play_btn");
    statusEl.className = "rocket-canvas-status";

    const flightLog = [];
    const startTs = performance.now();

    const tick = (now) => {
      if (!this.playing) return;
      const elapsed = (now - startTs) / 1000;
      const mult = this.growthCurve(elapsed);
      flightLog.push({ t: elapsed, m: mult });
      multEl.textContent = mult.toFixed(2) + "x";
      if (!this.cashedOut) {
        this.setPlayButton({ label: `${t("cashout_btn") || "Забрать"} (${mult.toFixed(2)}x)`, mode: "cashout", disabled: false });
      }

      this.drawFrame(mult, false, false, flightLog, elapsed);

      // Локальный "автовывод": как только клиентская анимация долетает до
      // выбранного игроком множителя, автоматически шлём тот же /cashout,
      // что и ручная кнопка — но игрок мог успеть нажать "Забрать" раньше.
      if (this.autoCashoutAt && !this.cashedOut && mult >= this.autoCashoutAt) {
        this.manualCashout();
      }

      this.flightLog = flightLog;
      this.elapsed = elapsed;
      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);

    // Параллельно опрашиваем бэкенд — он единственный, кто знает истинную
    // точку краха, и может сообщить, что ракета лопнула, даже если игрок
    // ничего не нажимал.
    this.pollTimer = setInterval(() => this.pollStatus(), 250);
  },

  async pollStatus() {
    if (!this.playing || this.cashedOut) return;
    try {
      const status = await apiGet(`/minigames/crash/poll?telegram_id=${state.telegramId}`);
      if (status.active === false && status.busted) {
        this.onBust(status.crash_point);
      }
    } catch (e) {
      // Сеть моргнула — не рушим раунд, просто попробуем на следующем тике.
    }
  },

  async manualCashout(silent = false) {
    if (!this.playing || this.cashedOut) return;
    this.cashedOut = true;
    this.setPlayButton({ label: t("cashout_btn") || "Забрать", mode: "cashout", disabled: true });
    try {
      const result = await apiPost("/minigames/crash/cashout", { telegram_id: state.telegramId });
      if (!silent) this.finishFlight(result);
      else { this.playing = false; this.stopTimers(); }
    } catch (e) {
      this.cashedOut = false;
      if (!silent) {
        this.setPlayButton({ label: t("cashout_btn") || "Забрать", mode: "cashout", disabled: false });
        tg?.showAlert?.(e.message);
      }
    }
  },

  onBust(crashPoint) {
    if (this.cashedOut) return; // уже успели забрать чуть раньше
    this.finishFlight({
      success: true,
      result: "lose",
      crash_point: crashPoint,
      cashout_at: null,
      winnings: 0,
      new_balance: state.balance,
    });
  },

  stopTimers() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = null;
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  },

  finishFlight(result) {
    this.playing = false;
    this.stopTimers();
    const isWin = result.result === "win";
    const statusEl = document.getElementById("rocket-canvas-status");
    const resultBox = document.getElementById("rocket-result");

    document.getElementById("rocket-bet-input").disabled = false;
    document.getElementById("rocket-target-slider").disabled = false;
    this.setPlayButton({ label: t("play_btn"), mode: "play", disabled: false });
    activeSessionCashout = null;

    state.balance = result.new_balance;
    updateGameScreenBalance();

    const flightLog = this.flightLog || [];
    const elapsed = this.elapsed || 0;

    if (isWin) {
      this.drawFrame(result.cashout_at, false, true, flightLog, elapsed);
      statusEl.textContent = "✅ " + t("win_toast_prefix");
      statusEl.className = "rocket-canvas-status win";
      showGameResult(resultBox, `🚀 ${result.cashout_at}x! +${fmt(result.winnings)}`, true);
      playSound("win");
      haptic("success");
    } else {
      this.drawFrame(result.crash_point || this.growthCurve(elapsed), true, false, flightLog, elapsed);
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
    this.stopTimers();
    this.playing = false;
    if (this._onResize) window.removeEventListener("resize", this._onResize);
    this.canvas = null;
    this.ctx = null;
  },
};

// ============================================
// 🔺 УЛУЧШИТЕЛЬ (Upgrader) — v2
// ============================================
// Игрок выбирает предмет из инвентаря и ЦЕЛЬ ОДНИМ из 4 способов:
//   item       — кон��ретный скин из глобальной базы (поиск)
//   price      — произвольная желаемая стоимость в 💎
//   multiplier — быстрые кнопки x2 / x3 / x5 (или свой множитель)
//   chance     — быстрые кнопки 30% / 55% / 75% (или свой шанс)
// Ползунок стрелки/дуги — чисто визуальный элемент; реальный результат
// всегда приходит с бэкенда (/api/upgrade), сам вращение только красиво
// "доигрывает" уже известный исход после ответа сервера.

const UPGRADER_MULTIPLIER_PRESETS = [2, 3, 5];
const UPGRADER_CHANCE_PRESETS = [30, 55, 75];

function calcUpgradeChance(multiplier) {
  const targetHouseEdge = 0.85;
  const chance = targetHouseEdge / multiplier;
  return Math.max(0.01, Math.min(0.80, chance));
}

const UpgraderGame = {
  mode: "multiplier",       // item | price | multiplier | chance
  selectedItemIds: [],      // выбранные предметы ИЗ ИНВЕНТАРЯ (что улучшаем) — до 6 штук
  sortDir: "asc",           // сортировка списка своих предметов: asc | desc
  targetEntry: null,        // выбранный ЦЕЛЕВОЙ скин (для mode === "item")
  multiplier: 2,
  chance: 42,
  searchTimer: null,
  spinning: false,

  render() {
    return `
      <div class="game-panel-desc">${t("upgrade_desc")}</div>

      <div class="mg-row">
        <div class="upg-your-items-header">
          <label class="mg-label">${t("upgrade_your_item_label")} <span id="upgrader-picked-count">(0/6)</span></label>
          <button type="button" class="upg-sort-btn" id="upgrader-sort-btn" data-dir="asc">
            <span id="upgrader-sort-label">↑ ${t("sort_price_label")}</span>
          </button>
        </div>
        <div class="upg-your-items-grid" id="upgrader-items-grid"></div>
      </div>

      <div class="upg-mode-tabs" id="upgrader-mode-tabs">
        <button type="button" class="upg-mode-tab active" data-mode="multiplier">${t("upgrade_mode_multiplier")}</button>
        <button type="button" class="upg-mode-tab" data-mode="chance">${t("upgrade_mode_chance")}</button>
        <button type="button" class="upg-mode-tab" data-mode="item">${t("upgrade_mode_item")}</button>
        <button type="button" class="upg-mode-tab" data-mode="price">${t("upgrade_mode_price")}</button>
      </div>

      <!-- mode: multiplier -->
      <div class="upg-mode-pane" id="upg-pane-multiplier">
        <div class="upg-preset-row">
          ${UPGRADER_MULTIPLIER_PRESETS.map(m => `<button type="button" class="upg-preset-btn" data-mult="${m}">x${m}</button>`).join("")}
        </div>
        <div class="mg-row">
          <label class="mg-label"><span>${t("multiplier_label")}</span>: <span id="upgrader-multiplier-value">2.0x</span></label>
          <input type="range" id="upgrader-multiplier-slider" min="1.05" max="20" step="0.05" value="2.0">
        </div>
      </div>

      <!-- mode: chance -->
      <div class="upg-mode-pane" id="upg-pane-chance" style="display:none;">
        <div class="upg-preset-row">
          ${UPGRADER_CHANCE_PRESETS.map(c => `<button type="button" class="upg-preset-btn" data-chance="${c}">${c}%</button>`).join("")}
        </div>
        <div class="mg-row">
          <label class="mg-label"><span>${t("chance_preview_label")}</span>: <span id="upgrader-chance-value">42%</span></label>
          <input type="range" id="upgrader-chance-slider" min="1" max="80" step="1" value="42">
        </div>
      </div>

      <!-- mode: item (поиск по глобальной базе скинов) -->
      <div class="upg-mode-pane" id="upg-pane-item" style="display:none;">
        <input type="text" id="upgrader-search-input" class="mg-input" placeholder="${t("upgrade_search_placeholder")}">
        <div class="upg-search-results" id="upgrader-search-results"></div>
        <div class="upg-target-picked" id="upgrader-target-picked" style="display:none;"></div>
      </div>

      <!-- mode: price (своя стоимость) -->
      <div class="upg-mode-pane" id="upg-pane-price" style="display:none;">
        <label class="mg-label">${t("upgrade_target_price_label")}</label>
        <input type="number" id="upgrader-price-input" class="mg-input" min="1" step="1" placeholder="${t("upgrade_target_price_placeholder")}">
      </div>

      <!-- Круговой индикатор шанса + стрелка (визуал) -->
      <div class="upg-wheel-wrap" id="upgrader-wheel-wrap">
        <svg width="200" height="200" viewBox="0 0 200 200" class="upg-wheel-svg">
          <circle class="upg-track-bg" cx="100" cy="100" r="82"></circle>
          <circle class="upg-track-progress" id="upgrader-track-progress" cx="100" cy="100" r="82"
            stroke-dasharray="0 515.2" transform="rotate(-90 100 100)"></circle>
        </svg>
        <div class="upg-needle-pivot" id="upgrader-needle-pivot"><div class="upg-needle"></div></div>
        <div class="upg-wheel-center">
          <div class="upg-wheel-percent"><span id="upgrader-wheel-percent">42</span>%</div>
          <div class="upg-wheel-sub">${t("chance_preview_label")}</div>
        </div>
      </div>

      <div class="upg-summary-row">
        <div class="upg-summary-box">
          <div class="upg-summary-label">${t("upgrade_your_item_label")}</div>
          <div class="upg-summary-value" id="upgrader-summary-old">— ${currencyIcon()}</div>
        </div>
        <div class="upg-summary-arrow">→</div>
        <div class="upg-summary-box">
          <div class="upg-summary-label">${t("upgrade_target_label")}</div>
          <div class="upg-summary-value" id="upgrader-summary-target">— ${currencyIcon()}</div>
        </div>
      </div>

      <button class="btn-primary full" id="upgrader-play-btn">${t("upgrade_spin_btn")}</button>
    `;
  },

  init() {
    this.mode = "multiplier";
    this.selectedItemIds = [];
    this.sortDir = "asc";
    this.targetEntry = null;
    this.multiplier = 2;
    this.chance = 42;
    this.spinning = false;

    this.renderItemsGrid();

    document.getElementById("upgrader-sort-btn").addEventListener("click", () => {
      this.sortDir = this.sortDir === "asc" ? "desc" : "asc";
      this.renderItemsGrid();
    });

    document.getElementById("upgrader-mode-tabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".upg-mode-tab");
      if (!btn) return;
      this.setMode(btn.dataset.mode);
    });

    // Быстрые кнопки-множители (x2/x3/x5)
    document.querySelectorAll("#upg-pane-multiplier .upg-preset-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this.multiplier = parseFloat(btn.dataset.mult);
        document.getElementById("upgrader-multiplier-slider").value = this.multiplier;
        this.onMultiplierChange();
      });
    });
    document.getElementById("upgrader-multiplier-slider").addEventListener("input", (e) => {
      this.multiplier = parseFloat(e.target.value);
      this.onMultiplierChange();
    });

    // Быстрые кнопки-шансы (30/55/75%)
    document.querySelectorAll("#upg-pane-chance .upg-preset-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this.chance = parseFloat(btn.dataset.chance);
        document.getElementById("upgrader-chance-slider").value = this.chance;
        this.onChanceChange();
      });
    });
    document.getElementById("upgrader-chance-slider").addEventListener("input", (e) => {
      this.chance = parseFloat(e.target.value);
      this.onChanceChange();
    });

    // Поиск целевого скина по глобальной базе (items_data на бэкенде)
    const searchInput = document.getElementById("upgrader-search-input");
    searchInput.addEventListener("input", () => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => this.runItemSearch(searchInput.value), 250);
    });

    // Своя стоимость
    document.getElementById("upgrader-price-input").addEventListener("input", () => {
      this.updateSummary();
    });

    document.getElementById("upgrader-play-btn").addEventListener("click", () => this.play());

    this.onMultiplierChange();
    this.updateSummary();
  },

  destroy() {
    clearTimeout(this.searchTimer);
  },

  setMode(mode) {
    this.mode = mode;
    document.querySelectorAll(".upg-mode-tab").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
    ["multiplier", "chance", "item", "price"].forEach(m => {
      document.getElementById(`upg-pane-${m}`).style.display = m === mode ? "" : "none";
    });
    this.updateSummary();
  },

  populateSelect() {
    // Оставлено для обратной совместимости вызовов — реальный рендер
    // теперь в renderItemsGrid() (карточки с чекбоксами + сортировка).
    this.renderItemsGrid();
  },

  // Рисует сетку своих предметов (карточки с чекбоксом) с учётом текущей
  // сортировки по цене; позволяет отметить до MAX_UPGRADE_ITEMS штук —
  // их суммарная стоимость становится "старой ценой" апгрейда.
  renderItemsGrid() {
    const MAX_ITEMS = 6;
    const grid = document.getElementById("upgrader-items-grid");
    const sortBtn = document.getElementById("upgrader-sort-btn");
    const sortLabel = document.getElementById("upgrader-sort-label");
    if (!grid) return;

    if (sortBtn) sortBtn.dataset.dir = this.sortDir;
    if (sortLabel) sortLabel.textContent = `${this.sortDir === "asc" ? "↑" : "↓"} ${t("sort_price_label")}`;

    // убираем из выбранных предметы, которых больше нет в инвентаре
    this.selectedItemIds = this.selectedItemIds.filter(id =>
      state.inventory.some(i => String(i.id) === String(id))
    );

    grid.innerHTML = "";
    if (!state.inventory.length) {
      grid.innerHTML = `<div class="upg-items-empty">${t("inventory_empty")}</div>`;
      this.updatePickedCount();
      return;
    }

    const sorted = [...state.inventory].sort((a, b) =>
      this.sortDir === "asc" ? a.price - b.price : b.price - a.price
    );

    sorted.forEach(item => {
      const picked = this.selectedItemIds.some(id => String(id) === String(item.id));
      const disableUnpicked = !picked && this.selectedItemIds.length >= MAX_ITEMS;
      const el = document.createElement("div");
      el.className = `upg-item-card ${rarityClass(item.rarity)}${picked ? " picked" : ""}${disableUnpicked ? " disabled" : ""}`;
      el.innerHTML = `
        <img src="${item.image}" alt="${item.name}" loading="lazy">
        <div class="upg-item-card-name">${item.name}</div>
        <div class="upg-item-card-price">${fmt(item.price)}</div>
        <div class="upg-item-card-check">${picked ? "✓" : ""}</div>
      `;
      el.addEventListener("click", () => {
        if (picked) {
          this.selectedItemIds = this.selectedItemIds.filter(id => String(id) !== String(item.id));
        } else {
          if (this.selectedItemIds.length >= MAX_ITEMS) return; // лимит 6 штук
          this.selectedItemIds.push(item.id);
        }
        this.renderItemsGrid();
        this.updateSummary();
      });
      grid.appendChild(el);
    });

    this.updatePickedCount();
  },

  updatePickedCount() {
    const el = document.getElementById("upgrader-picked-count");
    if (el) el.textContent = `(${this.selectedItemIds.length}/6)`;
  },

  getSelectedItems() {
    return this.selectedItemIds
      .map(id => state.inventory.find(i => String(i.id) === String(id)))
      .filter(Boolean);
  },

  // Суммарная стоимость всех выбранных предметов — она же "старая цена"
  // апгрейда (несколько скинов объединяются в один апгрейд).
  getSelectedTotalPrice() {
    return this.getSelectedItems().reduce((sum, i) => sum + i.price, 0);
  },

  onMultiplierChange() {
    document.getElementById("upgrader-multiplier-value").textContent = this.multiplier.toFixed(2) + "x";
    document.querySelectorAll("#upg-pane-multiplier .upg-preset-btn").forEach(b => {
      b.classList.toggle("active", parseFloat(b.dataset.mult) === this.multiplier);
    });
    this.chance = calcUpgradeChance(this.multiplier) * 100;
    this.updateSummary();
  },

  onChanceChange() {
    document.getElementById("upgrader-chance-value").textContent = Math.round(this.chance) + "%";
    document.querySelectorAll("#upg-pane-chance .upg-preset-btn").forEach(b => {
      b.classList.toggle("active", parseFloat(b.dataset.chance) === this.chance);
    });
    this.multiplier = 0.85 / (this.chance / 100);
    this.updateSummary();
  },

  async runItemSearch(query) {
    const box = document.getElementById("upgrader-search-results");
    if (!box) return;
    try {
      const data = await apiGet(`/items/search?q=${encodeURIComponent(query)}&limit=20`);
      if (!data.results.length) {
        box.innerHTML = `<div class="upg-search-empty">${t("upgrade_search_empty")}</div>`;
        return;
      }
      box.innerHTML = "";
      data.results.forEach(entry => {
        const el = document.createElement("div");
        el.className = `upg-search-item ${rarityClass(entry.rarity)}`;
        el.innerHTML = `
          <img src="${entry.image}" alt="">
          <div class="upg-search-item-info">
            <div class="upg-search-item-name">${entry.name}</div>
            <div class="upg-search-item-price">${fmtWithIcon(entry.base_price)}</div>
          </div>
        `;
        el.addEventListener("click", () => {
          this.targetEntry = entry;
          box.innerHTML = "";
          document.getElementById("upgrader-search-input").value = entry.name;
          this.showPickedTarget();
          this.updateSummary();
        });
        box.appendChild(el);
      });
    } catch (e) { /* тихо игнорируем сетевые сбои поиска */ }
  },

  showPickedTarget() {
    const el = document.getElementById("upgrader-target-picked");
    if (!this.targetEntry) { el.style.display = "none"; return; }
    el.style.display = "flex";
    el.innerHTML = `
      <img src="${this.targetEntry.image}" alt="">
      <div>
        <div class="upg-search-item-name">${this.targetEntry.name}</div>
        <div class="upg-search-item-price">${fmtWithIcon(this.targetEntry.base_price)}</div>
      </div>
    `;
  },

  // Пересчитывает и показывает старую/целевую стоимость + дугу-индикатор
  // ЧИСТО НА ФРОНТЕ (для мгновенного превью) — финальные цифры при
  // фактическом апгрейде всегда пересчитываются и проверяются на бэкенде.
  updateSummary() {
    const items = this.getSelectedItems();
    const oldPrice = this.getSelectedTotalPrice();
    document.getElementById("upgrader-summary-old").textContent = items.length ? fmt(oldPrice) : "—";

    let targetPrice = 0;
    let chancePct = this.chance;

    if (this.mode === "item") {
      targetPrice = this.targetEntry ? this.targetEntry.base_price : 0;
      if (items.length && targetPrice > oldPrice) chancePct = calcUpgradeChance(targetPrice / oldPrice) * 100;
    } else if (this.mode === "price") {
      const manual = parseFloat(document.getElementById("upgrader-price-input").value);
      targetPrice = manual > 0 ? manual : 0;
      if (items.length && targetPrice > oldPrice) chancePct = calcUpgradeChance(targetPrice / oldPrice) * 100;
    } else if (this.mode === "multiplier") {
      targetPrice = oldPrice * this.multiplier;
      chancePct = calcUpgradeChance(this.multiplier) * 100;
    } else if (this.mode === "chance") {
      const mult = 0.85 / (this.chance / 100);
      targetPrice = oldPrice * mult;
      chancePct = this.chance;
    }

    document.getElementById("upgrader-summary-target").textContent = targetPrice > 0 ? fmt(targetPrice) : "—";
    this.setWheelChance(chancePct);
  },

  setWheelChance(chancePct) {
    chancePct = Math.max(0, Math.min(100, chancePct || 0));
    const CIRC = 2 * Math.PI * 82;
    const dash = (chancePct / 100) * CIRC;
    document.getElementById("upgrader-track-progress").style.strokeDasharray = `${dash} ${CIRC - dash}`;
    document.getElementById("upgrader-wheel-percent").textContent = Math.round(chancePct);
  },

  buildRequestBody() {
    const items = this.getSelectedItems();
    if (!items.length) return null;
    const body = {
      telegram_id: state.telegramId,
      inventory_ids: items.map(i => Number(i.id)),
      mode: this.mode,
    };
    if (this.mode === "item") {
      if (!this.targetEntry) return null;
      body.target_name = this.targetEntry.name;
    } else if (this.mode === "price") {
      const manual = parseFloat(document.getElementById("upgrader-price-input").value);
      if (!(manual > 0)) return null;
      body.target_price = manual;
    } else if (this.mode === "multiplier") {
      body.multiplier = this.multiplier;
    } else if (this.mode === "chance") {
      body.chance = this.chance;
    }
    return body;
  },

  async play() {
    if (this.spinning) return;
    const items = this.getSelectedItems();
    if (!items.length) { tg?.showAlert?.(t("upgrade_pick_item_first")); return; }

    const body = this.buildRequestBody();
    if (!body) { tg?.showAlert?.(t("upgrade_pick_target_first")); return; }

    const playBtn = document.getElementById("upgrader-play-btn");
    this.spinning = true;
    playBtn.disabled = true;
    playBtn.textContent = t("upgrade_spinning");

    try {
      const result = await apiPost("/upgrade", body);
      this.spinWheelToResult(result);
    } catch (e) {
      tg?.showAlert?.(e.message);
      this.spinning = false;
      playBtn.disabled = false;
      playBtn.textContent = t("upgrade_spin_btn");
    }
  },

  // Крутит стрелку "вслепую" (визуально), а по окончании анимации
  // показывает уже известный (пришедший с сервера) результат.
  spinWheelToResult(result) {
    const pivot = document.getElementById("upgrader-needle-pivot");
    const chanceUsed = result.chance_used;
    // Угол "победной" зоны — от 0 до chanceUsed% окружности.
    const winThreshold = chanceUsed * 3.6;
    const landingAngle = result.result === "win"
      ? Math.random() * winThreshold
      : winThreshold + Math.random() * (360 - winThreshold);

    const extraSpins = 5 + Math.floor(Math.random() * 3);
    const targetRotation = extraSpins * 360 + landingAngle;

    pivot.style.transition = "transform 3.6s cubic-bezier(0.12, 0.75, 0.15, 1)";
    pivot.style.transform = `translate(-50%,-50%) rotate(${targetRotation}deg)`;

    setTimeout(() => this.finishRound(result), 3800);
  },

  async finishRound(result) {
    playSound(result.result === "win" ? "win" : "lose");

    if (result.result === "win") {
      showUpgradeResult(true, result.item);
    } else if (result.compensation) {
      showUpgradeResult(false, result.compensation);
    } else {
      // Ставка была меньше порога компенсации — скин не выдаётся,
      // вместо этого утешительные крохи 💎 зачислены прямо на баланс.
      showUpgradeResult(false, null, result.compensation_crystals);
    }

    state.inventory = state.inventory.filter(i => !this.selectedItemIds.some(id => String(id) === String(i.id)));
    await loadInventory();
    this.selectedItemIds = [];
    this.renderItemsGrid();
    this.targetEntry = null;
    document.getElementById("upgrader-search-input").value = "";
    this.showPickedTarget();
    this.updateSummary();
    loadProfile();

    const playBtn = document.getElementById("upgrader-play-btn");
    this.spinning = false;
    playBtn.disabled = false;
    playBtn.textContent = t("upgrade_spin_btn");

    // Сброс стрелки без анимации, чтобы следующий раунд стартовал с нуля
    const pivot = document.getElementById("upgrader-needle-pivot");
    pivot.style.transition = "none";
    pivot.style.transform = "translate(-50%,-50%) rotate(0deg)";
  },
};

// Модалка результата Апгрейдера — используется и для победы (выданный
// целевой скин), и для поражения (утешительный компенсационный скин).
function showUpgradeResult(isWin, item, compensationCrystals) {
  const modal = document.getElementById("upgrade-result-modal");
  const sheet = modal.querySelector(".modal-sheet");
  sheet.classList.toggle("upgrade-lose-sheet", !isWin);
  document.getElementById("upgrade-result-title").textContent = isWin ? t("upgrade_success_title") : t("upgrade_fail_title");
  document.getElementById("upgrade-result-subtitle").style.display = isWin ? "none" : "block";

  if (!isWin && !item) {
    // Ставка была ниже порога компенсации скином — вместо предмета
    // на баланс капнули утешительные крохи 💎.
    document.getElementById("upgrade-result-subtitle").textContent =
      `${t("upgrade_fail_desc")} +${fmt(compensationCrystals ?? 0.01)} ${currencyIcon()}`;
    document.getElementById("upgrade-result-image").src = "";
    document.getElementById("upgrade-result-name").textContent = `+${fmt(compensationCrystals ?? 0.01)} ${currencyIcon()}`;
    document.getElementById("upgrade-result-quality").textContent = "";
    document.getElementById("upgrade-result-price").textContent = fmt(compensationCrystals ?? 0.01);
    modal.classList.add("active");
    return;
  }

  document.getElementById("upgrade-result-subtitle").textContent = t("upgrade_fail_desc");
  document.getElementById("upgrade-result-image").src = item.image || "";
  document.getElementById("upgrade-result-name").textContent = item.name;
  document.getElementById("upgrade-result-quality").textContent =
    `${item.quality_name || ""}${item.stattrak ? " · StatTrak™" : ""}`;
  document.getElementById("upgrade-result-price").textContent = fmt(item.price);
  modal.classList.add("active");
}

document.getElementById("upgrade-result-ok-btn")?.addEventListener("click", () => {
  document.getElementById("upgrade-result-modal").classList.remove("active");
});

// ============================================
// 🧪 СИНТЕЗАТОР (Item Crafter, Спринт 4)
// ============================================
// Отдельная механика от УЛУЧШИТЕЛЯ (UpgraderGame) выше: здесь ставка — это
// КОНКРЕТНЫЕ предметы инвентаря (+опционально Кристаллы поверх), шанс
// считается прямым отношением (staked_value / target_value) * 100, зажатым
// в [1%, 80%], а при поражении вся ставка сгорает целиком без утешительного
// скина. Бэкенд: POST /api/upgrader/spin (routers/upgrader.py).
const CRAFTER_MAX_ITEMS = 6;

const CrafterGame = {
  selectedItemIds: [],
  sortDir: "asc",
  addCrystals: 0,
  targetEntry: null,
  searchTimer: null,
  priceTimer: null,
  spinning: false,

  render() {
    return `
      <div class="game-panel-desc">${t("crafter_desc")}</div>

      <div class="mg-row">
        <div class="upg-your-items-header">
          <label class="mg-label">${t("crafter_components_label")} <span id="crafter-picked-count">(0/${CRAFTER_MAX_ITEMS})</span></label>
          <button type="button" class="upg-sort-btn" id="crafter-sort-btn" data-dir="asc">
            <span id="crafter-sort-label">↑ ${t("sort_price_label")}</span>
          </button>
        </div>
        <div class="upg-your-items-grid" id="crafter-items-grid"></div>
      </div>

      <div class="mg-row">
        <label class="mg-label">${t("crafter_add_crystals_label")}: <span id="crafter-crystals-value">0</span> ${currencyIcon()}</label>
        <input type="range" id="crafter-crystals-slider" min="0" max="0" step="1" value="0">
      </div>

      <div class="upg-wheel-wrap" id="crafter-wheel-wrap">
        <svg width="200" height="200" viewBox="0 0 200 200" class="upg-wheel-svg">
          <circle class="upg-track-bg" cx="100" cy="100" r="82"></circle>
          <circle class="upg-track-progress" id="crafter-track-progress" cx="100" cy="100" r="82"
            stroke-dasharray="0 515.2" transform="rotate(-90 100 100)"></circle>
        </svg>
        <div class="upg-needle-pivot" id="crafter-needle-pivot"><div class="upg-needle"></div></div>
        <div class="upg-wheel-center">
          <div class="upg-wheel-percent"><span id="crafter-wheel-percent">0</span>%</div>
          <div class="upg-wheel-sub">${t("chance_preview_label")}</div>
        </div>
      </div>

      <div class="upg-summary-row">
        <div class="upg-summary-box">
          <div class="upg-summary-label">${t("crafter_input_value_label")}</div>
          <div class="upg-summary-value" id="crafter-summary-input">— ${currencyIcon()}</div>
        </div>
        <div class="upg-summary-arrow">→</div>
        <div class="upg-summary-box">
          <div class="upg-summary-label">${t("crafter_target_label")}</div>
          <div class="upg-summary-value" id="crafter-summary-target">— ${currencyIcon()}</div>
        </div>
      </div>

      <button class="btn-primary full" id="crafter-play-btn">${t("crafter_synthesize_btn")}</button>

      <div class="crf-target-section">
        <label class="mg-label">${t("crafter_target_label")}</label>

        <div class="crf-target-card" id="crafter-target-card" style="display:none;"></div>

        <div class="crf-quick-row" id="crafter-quick-row">
          <button type="button" class="upg-preset-btn" data-qmult="2">x2</button>
          <button type="button" class="upg-preset-btn" data-qmult="4">x4</button>
          <button type="button" class="upg-preset-btn" data-qmult="8">x8</button>
          <button type="button" class="upg-preset-btn" data-qchance="35">35%</button>
          <button type="button" class="upg-preset-btn" data-qchance="55">55%</button>
          <button type="button" class="upg-preset-btn" data-qchance="75">75%</button>
        </div>

        <input type="text" id="crafter-search-input" class="mg-input" placeholder="${t("upgrade_search_placeholder")}">
        <div class="crf-price-range-row">
          <input type="number" id="crafter-price-min" class="mg-input" min="0" step="1" placeholder="${t("crafter_price_from")}">
          <input type="number" id="crafter-price-max" class="mg-input" min="0" step="1" placeholder="${t("crafter_price_to")}">
        </div>

        <div class="crf-catalog-grid" id="crafter-catalog-grid"></div>
      </div>
    `;
  },

  init() {
    this.selectedItemIds = [];
    this.sortDir = "asc";
    this.addCrystals = 0;
    this.targetEntry = null;
    this.spinning = false;

    this.renderItemsGrid();

    document.getElementById("crafter-sort-btn").addEventListener("click", () => {
      this.sortDir = this.sortDir === "asc" ? "desc" : "asc";
      this.renderItemsGrid();
    });

    const crystalsSlider = document.getElementById("crafter-crystals-slider");
    // Максимум слайдера — теку��ий баланс (в "сырых" Кристаллах, без
    // конвертации в отображаемую валюту — на бэкенд всегда уходят Кристаллы).
    crystalsSlider.max = Math.max(0, Math.floor(state.balance));
    crystalsSlider.addEventListener("input", (e) => {
      this.addCrystals = parseFloat(e.target.value) || 0;
      document.getElementById("crafter-crystals-value").textContent = fmtNumber(this.addCrystals);
      this.updateSummary();
    });

    document.getElementById("crafter-quick-row").addEventListener("click", (e) => {
      const btn = e.target.closest(".upg-preset-btn");
      if (!btn) return;
      this.applyQuickValue(btn);
    });

    const searchInput = document.getElementById("crafter-search-input");
    searchInput.addEventListener("input", () => {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => this.runCatalogSearch(), 250);
    });

    const minInput = document.getElementById("crafter-price-min");
    const maxInput = document.getElementById("crafter-price-max");
    [minInput, maxInput].forEach(inp => {
      inp.addEventListener("input", () => {
        clearTimeout(this.priceTimer);
        this.priceTimer = setTimeout(() => this.runCatalogSearch(), 300);
      });
    });

    document.getElementById("crafter-play-btn").addEventListener("click", () => this.play());

    this.updateSummary();
    this.runCatalogSearch();
  },

  destroy() {
    clearTimeout(this.searchTimer);
    clearTimeout(this.priceTimer);
  },

  // Сетка своих предметов (карточки с чекбоксом) — та же логика, что у
  // UpgraderGame.renderItemsGrid, но со своими id/лимитом.
  renderItemsGrid() {
    const grid = document.getElementById("crafter-items-grid");
    const sortBtn = document.getElementById("crafter-sort-btn");
    const sortLabel = document.getElementById("crafter-sort-label");
    if (!grid) return;

    if (sortBtn) sortBtn.dataset.dir = this.sortDir;
    if (sortLabel) sortLabel.textContent = `${this.sortDir === "asc" ? "↑" : "↓"} ${t("sort_price_label")}`;

    this.selectedItemIds = this.selectedItemIds.filter(id =>
      state.inventory.some(i => String(i.id) === String(id))
    );

    grid.innerHTML = "";
    if (!state.inventory.length) {
      grid.innerHTML = `<div class="upg-items-empty">${t("inventory_empty")}</div>`;
      this.updatePickedCount();
      return;
    }

    const sorted = [...state.inventory].sort((a, b) =>
      this.sortDir === "asc" ? a.price - b.price : b.price - a.price
    );

    sorted.forEach(item => {
      const picked = this.selectedItemIds.some(id => String(id) === String(item.id));
      const disableUnpicked = !picked && this.selectedItemIds.length >= CRAFTER_MAX_ITEMS;
      const el = document.createElement("div");
      el.className = `upg-item-card ${rarityClass(item.rarity)}${picked ? " picked" : ""}${disableUnpicked ? " disabled" : ""}`;
      el.innerHTML = `
        <img src="${item.image}" alt="${item.name}" loading="lazy">
        <div class="upg-item-card-name">${item.name}</div>
        <div class="upg-item-card-price">${fmt(item.price)}</div>
        <div class="upg-item-card-check">${picked ? "✓" : ""}</div>
      `;
      el.addEventListener("click", () => {
        if (picked) {
          this.selectedItemIds = this.selectedItemIds.filter(id => String(id) !== String(item.id));
        } else {
          if (this.selectedItemIds.length >= CRAFTER_MAX_ITEMS) return;
          this.selectedItemIds.push(item.id);
        }
        this.renderItemsGrid();
        this.updateSummary();
      });
      grid.appendChild(el);
    });

    this.updatePickedCount();
  },

  updatePickedCount() {
    const el = document.getElementById("crafter-picked-count");
    if (el) el.textContent = `(${this.selectedItemIds.length}/${CRAFTER_MAX_ITEMS})`;
  },

  getSelectedItems() {
    return this.selectedItemIds
      .map(id => state.inventory.find(i => String(i.id) === String(id)))
      .filter(Boolean);
  },

  getInputValue() {
    const itemsTotal = this.getSelectedItems().reduce((sum, i) => sum + i.price, 0);
    return itemsTotal + (this.addCrystals || 0);
  },

  // Быстрые кнопки-множители (x2/x4/x8) и быстрые шансы (35/55/75%):
  // вычисляют желаемую стоимость цели по текущей ставке и подставляют её
  // в диапазон цен "от/до" каталога (±15%), чтобы сразу найти подходящий
  // целевой предмет — сам success_rate всё равно пересчитывается точно
  // после выбора конкретного предмета в updateSummary().
  applyQuickValue(btn) {
    document.querySelectorAll("#crafter-quick-row .upg-preset-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    const inputValue = this.getInputValue();
    if (inputValue <= 0) {
      tg?.showAlert?.(t("crafter_pick_component_first"));
      return;
    }

    let desiredTarget;
    if (btn.dataset.qmult) {
      desiredTarget = inputValue * parseFloat(btn.dataset.qmult);
    } else {
      const pct = parseFloat(btn.dataset.qchance);
      desiredTarget = inputValue / (pct / 100);
    }

    const minInput = document.getElementById("crafter-price-min");
    const maxInput = document.getElementById("crafter-price-max");
    minInput.value = Math.max(0, Math.round(desiredTarget * 0.85));
    maxInput.value = Math.round(desiredTarget * 1.15);

    clearTimeout(this.priceTimer);
    this.runCatalogSearch();
  },

  async runCatalogSearch() {
    const grid = document.getElementById("crafter-catalog-grid");
    if (!grid) return;
    const query = document.getElementById("crafter-search-input").value;
    const minPrice = document.getElementById("crafter-price-min").value;
    const maxPrice = document.getElementById("crafter-price-max").value;

    let url = `/items/search?q=${encodeURIComponent(query)}&limit=24`;
    if (minPrice !== "") url += `&min_price=${encodeURIComponent(minPrice)}`;
    if (maxPrice !== "") url += `&max_price=${encodeURIComponent(maxPrice)}`;

    try {
      const data = await apiGet(url);
      if (!data.results.length) {
        grid.innerHTML = `<div class="upg-search-empty">${t("crafter_catalog_empty")}</div>`;
        return;
      }
      grid.innerHTML = "";
      data.results.forEach(entry => {
        const el = document.createElement("div");
        const isSelected = this.targetEntry && this.targetEntry.name === entry.name;
        el.className = `upg-search-item ${rarityClass(entry.rarity)}${isSelected ? " selected" : ""}`;
        el.innerHTML = `
          <img src="${entry.image}" alt="" loading="lazy">
          <div class="upg-search-item-info">
            <div class="upg-search-item-name">${entry.name}</div>
            <div class="upg-search-item-price">${fmtWithIcon(entry.base_price)}</div>
          </div>
        `;
        el.addEventListener("click", () => {
          this.targetEntry = entry;
          this.showTargetCard();
          this.updateSummary();
          this.runCatalogSearch(); // перерисовать, чтобы подсветить выбранную карточку
        });
        grid.appendChild(el);
      });
    } catch (e) { /* тихо игнорируем сетевые сбои поиска каталога */ }
  },

  showTargetCard() {
    const el = document.getElementById("crafter-target-card");
    if (!this.targetEntry) { el.style.display = "none"; return; }
    el.style.display = "flex";
    el.innerHTML = `
      <img src="${this.targetEntry.image}" alt="">
      <div>
        <div class="upg-search-item-name">${this.targetEntry.name}</div>
        <div class="upg-search-item-price">${fmtWithIcon(this.targetEntry.base_price)}</div>
      </div>
    `;
  },

  // Пересчёт превью ЧИСТО НА ФРОНТЕ: success_rate = (input/target)*100,
  // зажатый в [1%, 80%] — точная копия формулы бэкенда (routers/upgrader.py),
  // финальное число всё равно приходит с сервера в ответе /upgrader/spin.
  updateSummary() {
    const inputValue = this.getInputValue();
    document.getElementById("crafter-summary-input").textContent = inputValue > 0 ? fmt(inputValue) : "—";

    const targetValue = this.targetEntry ? this.targetEntry.base_price : 0;
    document.getElementById("crafter-summary-target").textContent = targetValue > 0 ? fmt(targetValue) : "—";

    let chancePct = 0;
    if (inputValue > 0 && targetValue > 0) {
      chancePct = Math.max(1, Math.min(80, (inputValue / targetValue) * 100));
    }
    this.setWheelChance(chancePct);
  },

  setWheelChance(chancePct) {
    chancePct = Math.max(0, Math.min(100, chancePct || 0));
    const CIRC = 2 * Math.PI * 82;
    const dash = (chancePct / 100) * CIRC;
    document.getElementById("crafter-track-progress").style.strokeDasharray = `${dash} ${CIRC - dash}`;
    document.getElementById("crafter-wheel-percent").textContent = Math.round(chancePct);
  },

  async play() {
    if (this.spinning) return;
    const items = this.getSelectedItems();
    if (!items.length && !(this.addCrystals > 0)) {
      tg?.showAlert?.(t("crafter_pick_component_first"));
      return;
    }
    if (!this.targetEntry) {
      tg?.showAlert?.(t("crafter_pick_target_first"));
      return;
    }

    const playBtn = document.getElementById("crafter-play-btn");
    this.spinning = true;
    playBtn.disabled = true;
    playBtn.textContent = t("crafter_synthesizing");

    try {
      const result = await apiPost("/upgrader/spin", {
        telegram_id: state.telegramId,
        inventory_item_ids: items.map(i => Number(i.id)),
        add_crystals: this.addCrystals || 0,
        target_item_id: this.targetEntry.name,
      });
      this.spinWheelToResult(result);
    } catch (e) {
      tg?.showAlert?.(e.message);
      this.spinning = false;
      playBtn.disabled = false;
      playBtn.textContent = t("crafter_synthesize_btn");
    }
  },

  // Крутит стрелку "вслепую", а по окончании анимации показывает уже
  // известный (пришедший с сервера) результат — тот же приём, что у
  // UpgraderGame.spinWheelToResult, только со своими DOM id.
  spinWheelToResult(result) {
    const pivot = document.getElementById("crafter-needle-pivot");
    const chanceUsed = result.chance_used;
    const winThreshold = chanceUsed * 3.6;
    const landingAngle = result.result === "win"
      ? Math.random() * winThreshold
      : winThreshold + Math.random() * (360 - winThreshold);

    const extraSpins = 5 + Math.floor(Math.random() * 3);
    const targetRotation = extraSpins * 360 + landingAngle;

    pivot.style.transition = "transform 3.6s cubic-bezier(0.12, 0.75, 0.15, 1)";
    pivot.style.transform = `translate(-50%,-50%) rotate(${targetRotation}deg)`;

    setTimeout(() => this.finishRound(result), 3800);
  },

  async finishRound(result) {
    playSound(result.result === "win" ? "win" : "lose");
    showCrafterResult(result.result === "win", result.item || null);

    // Заложенные предметы списываются на бэкенде вне зависимости от исхода
    // (при победе — "превращаются" в цель, при поражении — сгорают).
    state.inventory = state.inventory.filter(i => !this.selectedItemIds.some(id => String(id) === String(i.id)));
    await loadInventory();
    this.selectedItemIds = [];
    this.addCrystals = 0;
    document.getElementById("crafter-crystals-slider").value = 0;
    document.getElementById("crafter-crystals-slider").max = Math.max(0, Math.floor(state.balance));
    document.getElementById("crafter-crystals-value").textContent = "0";
    this.renderItemsGrid();
    this.targetEntry = null;
    this.showTargetCard();
    document.querySelectorAll("#crafter-quick-row .upg-preset-btn").forEach(b => b.classList.remove("active"));
    this.updateSummary();
    this.runCatalogSearch();
    loadProfile();

    const playBtn = document.getElementById("crafter-play-btn");
    this.spinning = false;
    playBtn.disabled = false;
    playBtn.textContent = t("crafter_synthesize_btn");

    const pivot = document.getElementById("crafter-needle-pivot");
    pivot.style.transition = "none";
    pivot.style.transform = "translate(-50%,-50%) rotate(0deg)";
  },
};

// Модалка результата Синтезатора — переиспользует ту же разметку, что и
// showUpgradeResult() выше, но БЕЗ утешительного скина/крох при поражении:
// по ТЗ спринта 4 при неудаче ставка сгорает целиком.
function showCrafterResult(isWin, item) {
  const modal = document.getElementById("upgrade-result-modal");
  const sheet = modal.querySelector(".modal-sheet");
  sheet.classList.toggle("upgrade-lose-sheet", !isWin);
  document.getElementById("upgrade-result-title").textContent = isWin ? t("crafter_success_title") : t("crafter_fail_title");
  document.getElementById("upgrade-result-subtitle").style.display = "block";

  if (!isWin || !item) {
    document.getElementById("upgrade-result-subtitle").textContent = t("crafter_fail_desc");
    document.getElementById("upgrade-result-image").src = "";
    document.getElementById("upgrade-result-name").textContent = "";
    document.getElementById("upgrade-result-quality").textContent = "";
    document.getElementById("upgrade-result-price").textContent = "";
    modal.classList.add("active");
    return;
  }

  document.getElementById("upgrade-result-subtitle").style.display = "none";
  document.getElementById("upgrade-result-image").src = item.image || "";
  document.getElementById("upgrade-result-name").textContent = item.name;
  document.getElementById("upgrade-result-quality").textContent =
    `${item.quality_name || ""}${item.stattrak ? " · StatTrak™" : ""}`;
  document.getElementById("upgrade-result-price").textContent = fmt(item.price);
  modal.classList.add("active");
}

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
        <button class="btn-secondary full" id="miner-action-btn">${t("start_round_btn")}</button>
      </div>
      <div class="game-result-box" id="miner-result"></div>
    `;
  },

  init() {
    this.active = false;
    this.revealedCount = 0;
    this.starting = false;
    activeSessionCashout = null;

    // Единая кнопка: "Начать игру" пока раунда нет, и превращается в
    // "Забрать выигрыш" (единственно активную) на всё время раунда — так
    // физически невозможно повторно нажать "старт" и задублировать ставку.
    document.getElementById("miner-action-btn").addEventListener("click", () => {
      if (this.active) this.cashout();
      else this.startRound();
    });
    document.getElementById("miner-grid").addEventListener("click", (e) => {
      const tile = e.target.closest(".mine-tile");
      if (!tile || !this.active) return;
      this.reveal(Number(tile.dataset.index));
    });
  },

  setActionButton({ label, mode, disabled }) {
    const btn = document.getElementById("miner-action-btn");
    if (!btn) return;
    btn.textContent = label;
    btn.className = mode === "cashout" ? "btn-primary full" : "btn-secondary full";
    btn.disabled = !!disabled;
    btn.dataset.mode = mode;
  },

  resetGridUI() {
    document.querySelectorAll("#miner-grid .mine-tile").forEach(t => {
      t.textContent = "❔";
      t.className = "mine-tile";
    });
  },

  async startRound() {
    // Синхронная защита от двойного тапа: блокируем кнопку СРАЗУ, до
    // всякого await — иначе два быстрых клика успевают уйти на бэкенд как
    // два отдельных /start до того, как придёт первый ответ.
    if (this.active || this.starting) return;
    this.starting = true;
    this.setActionButton({ label: t("upgrade_spinning") || "…", mode: "start", disabled: true });

    const betAmount = parseFloat(document.getElementById("miner-bet-input").value);
    const minesCount = Number(document.getElementById("miner-mines-select").value);

    if (!betAmount || betAmount <= 0) {
      tg?.showAlert?.(t("bet_invalid"));
      this.starting = false;
      this.setActionButton({ label: t("start_round_btn"), mode: "start", disabled: false });
      return;
    }
    if (betAmount > state.balance) {
      tg?.showAlert?.(t("balance_low"));
      this.starting = false;
      this.setActionButton({ label: t("start_round_btn"), mode: "start", disabled: false });
      return;
    }

    try {
      const result = await apiPost("/minigames/mines/start", {
        telegram_id: state.telegramId,
        bet_amount: betAmount,
        mines_count: minesCount,
      });

      state.balance = result.new_balance;
      updateGameScreenBalance();

      this.active = true;
      this.starting = false;
      this.revealedCount = 0;
      this.betAmount = betAmount;
      this.resetGridUI();
      document.getElementById("miner-multiplier").textContent = "1.00x";
      document.getElementById("miner-result").classList.remove("show");
      document.getElementById("miner-bet-input").disabled = true;
      document.getElementById("miner-mines-select").disabled = true;
      // Раунд активен: единственная активная кнопка теперь — "Забрать
      // выигрыш" (отключена, пока не открыта хотя бы одна безопасная клетка).
      this.setActionButton({ label: t("cashout_btn"), mode: "cashout", disabled: true });
      activeSessionCashout = () => this.cashout(true);
      haptic("medium");
    } catch (e) {
      this.starting = false;
      this.setActionButton({ label: t("start_round_btn"), mode: "start", disabled: false });
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

      tile.textContent = currencyIcon();
      tile.className = "mine-tile safe opened";
      this.revealedCount = result.revealed_count || (this.revealedCount + 1);
      document.getElementById("miner-multiplier").textContent = `${result.multiplier.toFixed(2)}x`;
      this.setActionButton({ label: t("cashout_btn"), mode: "cashout", disabled: false });
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
    // Блокируем кнопку немедленно — не даём повторному клику на "Забрать
    // выигрыш" уйти вторым запросом, пока первый ещё не ответил.
    this.setActionButton({ label: t("cashout_btn"), mode: "cashout", disabled: true });
    try {
      const result = await apiPost("/minigames/mines/cashout", { telegram_id: state.telegramId });
      state.balance = result.new_balance;
      updateGameScreenBalance();
      if (!silent) this.endRound(result.winnings > 0, result.winnings);
      else this.active = false;
    } catch (e) {
      if (!silent) {
        tg?.showAlert?.(e.message);
        this.setActionButton({ label: t("cashout_btn"), mode: "cashout", disabled: false });
      }
    }
  },

  endRound(isWin, winnings) {
    this.active = false;
    activeSessionCashout = null;
    this.setActionButton({ label: t("start_round_btn"), mode: "start", disabled: false });
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
  crafter: CrafterGame,
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
  const savedCurrency = localStorage.getItem("cs2_currency");
  if (savedCurrency && CURRENCY_ICON[savedCurrency]) state.currency = savedCurrency;
  applyTranslations();
  updateSoundToggleUI();
  refreshCurrencyDisplay();

  // Спринт 12: фон — оптимистично из localStorage, ДО загрузки конфига и
  // логина, чтобы не было "мигания" темной темы перед появлением картинки.
  // state.backgroundOptions ещё пуст на этом моменте — applyBackground()
  // корректно откатится на "dark", если словаря опций пока нет; сетка
  // выбора и, если нужно, повторное применение перерисуются ниже, как
  // только придёт /app-config.
  const savedBackground = localStorage.getItem("cs2_background");
  if (savedBackground) state.background = savedBackground;

  try {
    const cfg = await apiGet("/app-config");
    state.botUsername = cfg.bot_username;
    state.adsgramBlockId = cfg.adsgram_block_id;
    state.refBonusInviter = cfg.ref_bonus_inviter;
    state.refBonusInvited = cfg.ref_bonus_invited;
    state.refCommissionPercent = cfg.ref_commission_percent ?? state.refCommissionPercent;
    state.vipPriceStars = cfg.vip_price_stars || state.vipPriceStars;
    state.craftFeeByRarity = cfg.craft_fee_by_rarity || {};
    state.craftItemsRequired = cfg.craft_items_required || 5;
    if (cfg.currency_rates) state.currencyRates = cfg.currency_rates;
    state.backgroundOptions = cfg.background_options || [];
    applyBackground(state.background || DEFAULT_BACKGROUND);
    // Раньше загруженная цена VIP из конфига нигде не использовалась —
    // текст в UI оставался захардкоженным "150 ⭐" даже если бэкенд
    // отдавал другое значение. Теперь подставляем актуальную цену в лейбл.
    const vipLabel = document.getElementById("vip-price-label");
    if (vipLabel) vipLabel.textContent = `${state.vipPriceStars} ⭐ Telegram Stars, навсегда`;
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
  if (typeof loadPassStatus === "function") await loadPassStatus();
})();

// ============================================
// ГЛОБАЛЬНЫЙ ЧАТ (Спринт 11)
// --------------------------------------------
// Фронтенд для /api/chat/*: живая лента с polling каждые 3с, отправка
// с учётом rate-limit/мута/бана (ошибки прилетают с бэкенда), жалоба по
// клику на чужое сообщение. Авто-фильтр и авто-мут обрабатываются на
// сервере — здесь мы лишь показываем пользователю статус и ошибки.
// ============================================
const chatState = {
  pollTimer: null,   // id setInterval активного опроса
  lastId: 0,         // max id уже показанного сообщения (для after_id)
  myUserId: null,    // внутренний user_id текущего игрока (для «своих» сообщений)
  sending: false,    // защита от двойной отправки
  bound: false,      // слушатели формы навешены один раз
};

function chatEls() {
  return {
    list: document.getElementById("chat-messages"),
    empty: document.getElementById("chat-empty"),
    status: document.getElementById("chat-status"),
    form: document.getElementById("chat-form"),
    input: document.getElementById("chat-input"),
    sendBtn: document.getElementById("chat-send-btn"),
  };
}

function chatTimeLabel(iso) {
  try {
    const norm = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
    const d = new Date(norm);
    return d.toLocaleTimeString(state.lang === "en" ? "en-GB" : "ru-RU", {
      hour: "2-digit", minute: "2-digit",
    });
  } catch (_) { return ""; }
}

function updateChatEmpty() {
  const { list, empty } = chatEls();
  if (!list || !empty) return;
  const has = list.querySelector(".chat-msg");
  empty.style.display = has ? "none" : "block";
}

function chatScrollToBottom(force) {
  const { list } = chatEls();
  if (!list) return;
  const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 140;
  if (force || nearBottom) list.scrollTop = list.scrollHeight;
}

function renderChatMessage(m) {
  const { list } = chatEls();
  if (!list) return;
  if (document.getElementById(`chat-msg-${m.id}`)) {
    chatState.lastId = Math.max(chatState.lastId, m.id);
    return; // уже отрисовано (гонка polling ↔ оптимистичная вставка)
  }

  if (m.is_system) {
    const el = document.createElement("div");
    el.className = "chat-msg system";
    el.id = `chat-msg-${m.id}`;
    el.innerHTML = `<span class="chat-sys-text">${escapeHtmlText(m.text)}</span>`;
    list.appendChild(el);
  } else {
    const mine = chatState.myUserId != null && m.user_id === chatState.myUserId;
    const el = document.createElement("div");
    el.className = `chat-msg${mine ? " mine" : ""}`;
    el.id = `chat-msg-${m.id}`;
    const initial = escapeHtmlText((m.author_name || "?").trim().slice(0, 1).toUpperCase() || "?");
    const avatar = m.author_photo
      ? `<img class="chat-avatar" src="${escapeAttr(m.author_photo)}" alt="" loading="lazy">`
      : `<div class="chat-avatar chat-avatar-fallback">${initial}</div>`;
    const name = mine ? escapeHtmlText(t("chat_you")) : escapeHtmlText(m.author_name || "Игрок");
    el.innerHTML = `
      ${avatar}
      <div class="chat-bubble">
        <div class="chat-meta">
          <span class="chat-name">${name}</span>
          <span class="chat-time">${chatTimeLabel(m.created_at || "")}</span>
        </div>
        <div class="chat-text">${escapeHtmlText(m.text)}</div>
      </div>`;
    if (!mine) {
      // ТЗ: клик по чужому сообщению ➔ [Пожаловаться].
      el.classList.add("reportable");
      el.setAttribute("title", t("chat_report"));
      el.addEventListener("click", () => reportChatMessage(m.id));
    }
    list.appendChild(el);
  }
  chatState.lastId = Math.max(chatState.lastId, m.id);
}

function applyChatMeState(me) {
  if (!me) return;
  chatState.myUserId = me.user_id;
  const { input, sendBtn, status } = chatEls();
  if (!input || !sendBtn || !status) return;

  let blocked = null;
  if (me.is_chat_banned) {
    blocked = t("chat_banned");
  } else if (me.is_muted) {
    blocked = t("chat_muted");
    if (me.mute_until) {
      const left = Math.max(0, Math.round((new Date(me.mute_until).getTime() - Date.now()) / 60000));
      if (left > 0) blocked += ` (~${left} ${state.lang === "en" ? "min" : "мин"})`;
    }
    if (me.mute_reason) blocked += ` — ${me.mute_reason}`;
  }

  if (blocked) {
    input.disabled = true;
    sendBtn.disabled = true;
    input.value = "";
    status.hidden = false;
    status.textContent = blocked;
    status.classList.add("blocked");
  } else {
    input.disabled = false;
    sendBtn.disabled = false;
    status.hidden = true;
    status.textContent = "";
    status.classList.remove("blocked");
  }
}

async function loadChatMessages(initial) {
  try {
    const afterId = initial ? 0 : chatState.lastId;
    const data = await apiGet(`/chat/messages?telegram_id=${state.telegramId}&after_id=${afterId}`);
    applyChatMeState(data.me);
    if (initial) {
      const { list } = chatEls();
      if (list) list.querySelectorAll(".chat-msg").forEach(n => n.remove());
      chatState.lastId = 0;
    }
    (data.messages || []).forEach(renderChatMessage);
    updateChatEmpty();
    chatScrollToBottom(initial);
  } catch (e) {
    console.error("Ошибка загрузки чата:", e);
  }
}

async function sendChat() {
  if (chatState.sending) return;
  const { input, sendBtn } = chatEls();
  if (!input) return;
  const text = (input.value || "").trim();
  if (!text) return;

  chatState.sending = true;
  if (sendBtn) sendBtn.disabled = true;
  try {
    const res = await apiPost("/chat/send", { telegram_id: state.telegramId, text });
    input.value = "";
    if (res.message) {
      renderChatMessage(res.message);
      updateChatEmpty();
      chatScrollToBottom(true);
    }
    haptic("light");
  } catch (e) {
    haptic("error");
    tg?.showAlert?.(e.message || "Ошибка отправки");
    // Мут/бан/rate-limit могли измениться — подтягиваем актуальный статус.
    loadChatMessages(false);
  } finally {
    chatState.sending = false;
    if (sendBtn && !input.disabled) sendBtn.disabled = false;
  }
}

async function reportChatMessage(messageId) {
  const doReport = async () => {
    try {
      const res = await apiPost("/chat/report", { telegram_id: state.telegramId, message_id: messageId });
      haptic("success");
      if (res.hidden) {
        const el = document.getElementById(`chat-msg-${messageId}`);
        if (el) el.remove();
        updateChatEmpty();
      }
      tg?.showAlert?.(t("chat_report_done"));
    } catch (e) {
      tg?.showAlert?.(e.message || "Ошибка");
    }
  };
  const question = t("chat_report") + "?";
  if (tg?.showConfirm) {
    tg.showConfirm(question, (ok) => { if (ok) doReport(); });
  } else if (confirm(question)) {
    doReport();
  }
}

function bindChatOnce() {
  if (chatState.bound) return;
  chatState.bound = true;
  const { form, input } = chatEls();
  if (!form || !input) return;
  // IME (CJK): не отправляем сообщение, пока идёт композиция иероглифов.
  input.addEventListener("compositionstart", () => { input.dataset.composing = "1"; });
  input.addEventListener("compositionend", () => { input.dataset.composing = ""; });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (input.dataset.composing === "1") return;
    sendChat();
  });
}

function startChatPolling() {
  stopChatPolling();
  chatState.pollTimer = setInterval(() => loadChatMessages(false), 3000);
}

function stopChatPolling() {
  if (chatState.pollTimer) {
    clearInterval(chatState.pollTimer);
    chatState.pollTimer = null;
  }
}

function openChat() {
  bindChatOnce();
  loadChatMessages(true);
  startChatPolling();
}
