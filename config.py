# ============================================
# CS2 Case Simulator — Configuration
# ============================================

# Токен бота, полученный от @BotFather
BOT_TOKEN = "8931804644:AAFEtXabrvy7PNZqabD7ETDo93uqFGBo14k"

# Telegram ID администратора (для доступа к админ-командам)
ADMIN_ID = 7871348781

# Username бота БЕЗ @ (нужен для реферальных ссылок вида t.me/username?start=...)
# Возьми его в @BotFather -> /mybots -> твой бот -> Edit Bot -> Username
BOT_USERNAME = "@cs2_case_simulator_test_bot"

# ID рекламного блока Adsgram.ai
ADSGRAM_BLOCK_ID = "40775"

# Секрет для эндпоинта GET /reward (серверный постбэк Adsgram, если он у тебя настроен
# в кабинете partner.adsgram.ai для блока 40775). Без него ЛЮБОЙ человек, знающий URL
# https://cs2-app.onrender.com/reward?userId=..., смог бы бесконечно начислять себе
# Кристаллики, просто открывая ссылку в браузере — эндпоинт требует secret=<это значение>
# в query-параметрах, поэтому смени плейсхолдер ниже на свою случайную строку и, если
# в кабинете Adsgram есть поле для доп. параметров в Reward URL, пропиши туда то же самое
# значение (например: https://cs2-app.onrender.com/reward?userId=[userId]&secret=ТВОЙ_СЕКРЕТ).
ADSGRAM_REWARD_SECRET = "frombarabolua"

# ============================================
# Прочие настройки (можно менять по желанию)
# ============================================

# URL мини-приложения (замени на свой хостинг после деплоя фронтенда)
WEBAPP_URL = "https://cs2-app-six.vercel.app"

# Стартовый виртуальный баланс нового игрока
START_BALANCE = 500

# Бонус рефереру и приглашённому
REF_BONUS_INVITER = 750
REF_BONUS_INVITED = 1000

# Цены на премиум-статус (в Telegram Stars)
VIP_PRICE_STARS_MONTH = 50   # Например: снятие рекламы на 30 дней
VIP_PRICE_STARS_FOREVER = 150  # Навсегда

# Путь к базе данных SQLite
DATABASE_URL = "sqlite+aiosqlite:///./cs2_simulator.db"
