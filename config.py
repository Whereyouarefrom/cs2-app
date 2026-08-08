# ============================================
# CS2 Case Simulator — Configuration
# ============================================

# Токен бота, полученный от @BotFather
BOT_TOKEN = "8931804644:AAFEtXabrvy7PNZqabD7ETDo93uqFGBo14k"

# Telegram ID администраторов (для доступа к админ-командам бота).
# Можно указать несколько через запятую — все команды /admin, /stats,
# /give_crystals, /give_vip проверяют доступ строго по этому списку.
ADMIN_IDS: list[int] = [7871348781]

# Telegram ID администратора, которому бот шлёт служебные уведомления о
# КАЖДОЙ новой регистрации (Спринт 9.5) — Telegram ID и никнеймы нового
# игрока и (если есть) его реферера.
ADMIN_TG_ID = ADMIN_IDS[0] if ADMIN_IDS else None

# Username бота БЕЗ @ (нужен для реферальных ссылок вида t.me/username?start=...)
# Возьми его в @BotFather -> /mybots -> твой бот -> Edit Bot -> Username
BOT_USERNAME = "cs2_case_simulator_test_bot"

# ID рекламного блока Adsgram.ai
ADSGRAM_BLOCK_ID = "40775"

# Секрет для эндпоинта GET /reward (серверный постбэк Adsgram)
ADSGRAM_REWARD_SECRET = "frombarabolua"

# ============================================
# Прочие настройки (можно менять по желанию)
# ============================================

# URL мини-приложения (замени на свой хостинг после деплоя фронтенда)
WEBAPP_URL = "https://cs2-app-six.vercel.app"

# Стартовый виртуальный баланс нового игрока (БЕЗ реферальной ссылки)
START_BALANCE = 5000

# ============================================
# Режим разработки
# ============================================
# True  — разрешает вход БЕЗ проверки подписи Telegram (/api/auth/telegram/dev)
# False — ОБЯЗАТЕЛЬНО поставь False перед продакшн-деплоем!
DEV_MODE = False

# Бонус рефереру и приглашённому (в 💎 Кристалликах), Спринт 9.5.
# Пригласившему начисляется автоматически при регистрации друга по реф-ссылке.
# Новичок БЕЗ реф-ссылки стартует с config.START_BALANCE (5,000 💎).
REF_BONUS_INVITER = 5555.55
REF_BONUS_INVITED = 25000

# P2P-реферальная система (общие траты) — постоянный % отчисления рефереру
# от трат приглашённого им реферала (открытие кейсов, крафт).
REF_COMMISSION_PERCENT = 0.05

# ============================================
# Спринт 9.5: пожизненная комиссия рефереру с Апгрейдера
# ============================================
# REF_UPGRADER_LOSS_COMMISSION_PERCENT — % от ПРОИГРАННОЙ ставки реферала
# REF_UPGRADER_WIN_COMMISSION_PERCENT  — % от ЧИСТОГО ВЫИГРЫША реферала
REF_UPGRADER_LOSS_COMMISSION_PERCENT = 0.05
REF_UPGRADER_WIN_COMMISSION_PERCENT = 0.02

# Цена VIP-статуса в Telegram Stars — зафиксирована: только "навсегда".
VIP_PRICE_STARS = 25

# ============================================
# Золото (Gold) — премиум-валюта за Telegram Stars
# ============================================
# Gold — ОТДЕЛЬНАЯ валюта от Кристаллов (User.gold_balance). Покупается
# ТОЛЬКО за Telegram Stars и тратится ТОЛЬКО на косметику.
STARS_TO_GOLD_RATE = 2  # 1 Telegram Star = 2 Gold


def stars_to_gold(stars_amount: int) -> float:
    """Конвертирует количество купленных Telegram Stars в Gold."""
    return stars_amount * STARS_TO_GOLD_RATE


# ============================================
# Социальные задания (Спринт 7) — routers/tasks.py
# ============================================
# Указывай username БЕЗ @. Бот ОБЯЗАТЕЛЬНО должен быть админом канала/чата.
SOCIAL_CHANNEL_USERNAME = "cs2_case_simulator_test_bot"   # подставь реальный username своего канала
SOCIAL_CHAT_USERNAME = "cs2_case_simulator_test_bot"      # подставь реальный username своего чата

# Сколько рефералов нужно пригласить для задания invite_3_refs
REQUIRED_REFERRALS_FOR_TASK = 3


# ============================================
# Спринт 11: Глобальный чат, авто-модерация
# ============================================

# Rate-limit отправки сообщений в глобальный чат (в секундах)
CHAT_RATE_LIMIT_SECONDS = 4

# Максимальная длина одного сообщения чата (символов)
CHAT_MESSAGE_MAX_LENGTH = 300

# На сколько часов автоматически мутится игрок при нарушении правил
CHAT_AUTO_MUTE_HOURS = 24

# Порог для авто-скрытия сообщения по жалобам (N+ жалоб от РАЗНЫХ игроков за M минут)
CHAT_REPORT_THRESHOLD = 3
CHAT_REPORT_WINDOW_MINUTES = 5

# Порог стоимости дропа (в 💎 Кристаллах) для авто-ленты в чат
CHAT_DROP_FEED_THRESHOLD = 100_000

# Белый список ОФИЦИАЛЬНЫХ доменов симулятора (ссылки на них НЕ блокируются)
CHAT_OFFICIAL_LINK_WHITELIST = [
    f"t.me/{BOT_USERNAME}",
    "cs2-app-six.vercel.app",
]

# Ключевые слова автофильтра — казино/рулетки, VPN-реклама, 18+-маркеры
CHAT_BANNED_KEYWORDS = [
    # казино / рулетки / ставки
    "csgorun", "casedrop", "csgoroll", "csgoempire", "csgocases",
    "рулетк", "казино", "casino", "1xbet", "1xstavka", "мостбет", "mostbet",
    "ставки на спорт", "букмекер", "betting",
    # VPN-реклама
    "vpn", "внп",
    # 18+
    "18+", "порно", "porn", "xxx", "эротик",
]

# Путь к базе данных SQLite
DATABASE_URL = "sqlite+aiosqlite:///./cs2_simulator.db"
