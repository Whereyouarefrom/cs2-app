# ============================================
# CS2 Case Simulator — Configuration
# ============================================

# Токен бота, полученный от @BotFather
BOT_TOKEN = "твой_токен_от_BotFather"

# Telegram ID администратора (для доступа к админ-командам)
ADMIN_ID = 12345678

# ID рекламного блока Adsgram.ai
ADSGRAM_BLOCK_ID = "твой_id_рекламы"

# ============================================
# Прочие настройки (можно менять по желанию)
# ============================================

# URL мини-приложения (замени на свой хостинг после деплоя фронтенда)
WEBAPP_URL = "https://your-domain.com/"

# Стартовый виртуальный баланс нового игрока
START_BALANCE = 500

# Бонус рефереру и приглашённому
REF_BONUS_INVITER = 2500
REF_BONUS_INVITED = 1000

# Цены на премиум-статус (в Telegram Stars)
VIP_PRICE_STARS_MONTH = 150   # Например: снятие рекламы на 30 дней
VIP_PRICE_STARS_FOREVER = 999  # Навсегда

# Путь к базе данных SQLite
DATABASE_URL = "sqlite+aiosqlite:///./cs2_simulator.db"
