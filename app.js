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
  vipPriceStars: 25,
  openCount: 1,
  openSpeed: "slow",
  lastMultiDrops: [],
  selectedInventoryIds: new Set(),
  dailyStatus: null,
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
    settings_lang: "🌐 Язык", settings_sound: "🔊 Звук",
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
    tab_profile: "Профиль", tab_minigames: "Мини-игры", tab_earn: "Заработать",
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
    select_all_label: "Выделить все", disintegrate_btn: "Продать выбранное",
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
    daily_reward_skin: "Редкий скин!", daily_reward_promo: "Промокод",
    daily_reward_jackpot: "Джекпот 7-го дня!",
    daily_promo_hint: "Активируй его на вкладке «Заработать → Промокод»:",
    daily_already_claimed_toast: "Ежедневный бонус уже получен сегодня. Возвращайся завтра!",
  },
  en: {
    cases_title: "Cases", inventory_title: "Inventory",
    inventory_empty: "Empty for now. Open your first case!",
    terms_title: "📜 Terms of Service",
    terms_accept_btn: "Accept and continue",
    profile_title: "Profile", stat_cases: "Cases opened",
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
    settings_lang: "🌐 Language", settings_sound: "🔊 Sound",
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
    earn_ad_desc: "Get +2000 💎 virtual balance", watch_btn: "Watch",
    earn_giveaway_title: "Giveaways", earn_giveaway_desc: "Join and win rare skins",
    earn_vip_title: "VIP status", earn_vip_desc: "No ads + cosmetic perks",
    buy_btn: "Buy", tab_cases: "Cases", tab_inventory: "Inventory",
    tab_profile: "Profile", tab_minigames: "Games", tab_earn: "Earn",
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
    select_all_label: "Select all", disintegrate_btn: "Sell selected",
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
    daily_reward_skin: "Rare skin!", daily_reward_promo: "Promo code",
    daily_reward_jackpot: "Day 7 jackpot!",
    daily_promo_hint: "Activate it on the Earn → Promo code tab:",
    daily_already_claimed_toast: "Daily bonus already claimed today. Come back tomorrow!",
  },
  uk: {
    cases_title: "Кейси", inventory_title: "Інвентар",
    inventory_empty: "Поки що порожньо. Відкрий перший кейс!",
    terms_title: "📜 Угода користувача",
    terms_accept_btn: "Прийняти і продовжити",
    profile_title: "Профіль", stat_cases: "Відкрито кейсів",
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
    settings_lang: "🌐 Мова", settings_sound: "🔊 Звук",
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
    tab_profile: "Профіль", tab_minigames: "Міні-ігри", tab_earn: "Заробити",
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
    select_all_label: "Виділити все", disintegrate_btn: "Продати вибране",
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

  // Победные фанфары — для редких/особо редких предметов (Тайное/Нож/Перчатки)
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

function fmtNumber(n) {
  const num = Number(n) || 0;
  const truncated = truncateTo2(num);
  return truncated.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
    // Тап по карточке (без закрытия просмотра кейса) показывает
    // полупрозрачный блюр с шансом/ценой — цена по умолчанию скрыта,
    // повторный тап скрывает overlay обратно.
    el.addEventListener("click", () => el.classList.toggle("revealed"));
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
    document.getElementById("multi-results-total").innerHTML =
      `${drops.length} × — <b>${fmt(total)}</b>`;
    document.getElementById("multi-results-actions").style.display = "block";
    const anyRare = drops.some(d => ["Covert", "Knife", "Gloves"].includes(d.rarity));
    if (!anyRare) playSound("win");
  }, totalRevealTime);
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
      // затем переворачиваем плитку и раскрываем настоящий нож/перчатки
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
    <span class="contents-item-chance-price">${fmtNumber(item.base_price)} 💎</span>
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
      <span class="rare-summary-price">${fmtNumber(summary.regularMin)}–${fmtNumber(summary.regularMax)} 💎</span>
    </div>
    ${summary.canStattrak ? `
    <div class="rare-summary-row rare-summary-st">
      <span class="rare-summary-label">StatTrak™</span>
      <span class="rare-summary-chance">${formatDropChance(summary.stattrakChance)}</span>
      <span class="rare-summary-price">${fmtNumber(summary.stattrakMin)}–${fmtNumber(summary.stattrakMax)} 💎</span>
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
  // ВАЖНО: плашку здесь больше НЕ показываем принудительно — её видимость
  // теперь полностью зависит от того, выделены ли предметы прямо сейчас
  // (см. updateInventorySelectionUI ниже, вызывается в конце этой функции).

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
      <div class="craft-item-card-price">${fmtNumber(entry.base_price)} 💎</div>
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
  document.getElementById("craft-fee-value").textContent = `${fmtNumber(fee)} 💎`;
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
// 🔺 УЛУЧШИТЕЛЬ (Upgrader) — v2
// ============================================
// Игрок выбирает предмет из инвентаря и ЦЕЛЬ ОДНИМ из 4 способов:
//   item       — конкретный скин из глобальной базы (поиск)
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
          <div class="upg-summary-value" id="upgrader-summary-old">— 💎</div>
        </div>
        <div class="upg-summary-arrow">→</div>
        <div class="upg-summary-box">
          <div class="upg-summary-label">${t("upgrade_target_label")}</div>
          <div class="upg-summary-value" id="upgrader-summary-target">— 💎</div>
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
            <div class="upg-search-item-price">${fmtNumber(entry.base_price)} 💎</div>
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
        <div class="upg-search-item-price">${fmtNumber(this.targetEntry.base_price)} 💎</div>
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
    } else {
      showUpgradeResult(false, result.compensation);
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
function showUpgradeResult(isWin, item) {
  const modal = document.getElementById("upgrade-result-modal");
  const sheet = modal.querySelector(".modal-sheet");
  sheet.classList.toggle("upgrade-lose-sheet", !isWin);
  document.getElementById("upgrade-result-title").textContent = isWin ? t("upgrade_success_title") : t("upgrade_fail_title");
  document.getElementById("upgrade-result-subtitle").style.display = isWin ? "none" : "block";
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
    state.craftFeeByRarity = cfg.craft_fee_by_rarity || {};
    state.craftItemsRequired = cfg.craft_items_required || 5;
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
})();
