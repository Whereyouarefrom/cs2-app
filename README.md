# CS2 Case Simulator — Telegram Mini App

Фановый симулятор открытия кейсов CS2/CS:GO без реального вывода денег и скинов.

## Структура проекта

- `config.py` — конфигурация (токен бота, admin ID, Adsgram block ID)
- `database.py` — модели SQLAlchemy (Users, Inventory, PromoCodes, Giveaways)
- `bot.py` — Telegram-бот на Aiogram 3 (запуск Mini App, VIP через Stars, админ-команды)
- `main.py` — FastAPI backend (база кейсов, открытие кейсов, инвентарь, мини-игры)
- `index.html`, `style.css`, `app.js` — фронтенд Mini App (кейсы, инвентарь, профиль, мини-игры Upgrade/Crash)

## Установка

```bash
pip install -r requirements.txt
```

Заполни `config.py`:
- `BOT_TOKEN` — токен от @BotFather
- `ADMIN_ID` — твой Telegram ID
- `ADSGRAM_BLOCK_ID` — ID блока с adsgram.ai

## Запуск локально

Backend (FastAPI):
```bash
python main.py
```

Telegram-бот:
```bash
python bot.py
```

Фронтенд — задеплой `index.html`/`style.css`/`app.js` на любой статический хостинг (Vercel, GitHub Pages, Render) и укажи URL:
- в `WEBAPP_URL` внутри `config.py`
- в `API_BASE` внутри `app.js` (адрес твоего задеплоенного backend + `/api`)

## Админ-команды бота

- `/stats` — общая статистика проекта
- `/give_balance <telegram_id> <amount>` — выдать виртуальный баланс
- `/addpromo <code> <type:value> <max_activations>` — создать промокод
- `/user_info <telegram_id>` — информация о пользователе

## API-эндпоинты (FastAPI)

- `GET /api/cases` — список кейсов
- `POST /api/open-case` — открыть кейс
- `POST /api/sell-skin` — продать скин
- `POST /api/promo` — активировать промокод
- `GET /api/user/profile` — профиль пользователя
- `GET /api/inventory` — инвентарь пользователя
- `POST /api/ad-reward` — награда за просмотр rewarded-рекламы
- `POST /api/minigames/upgrade` — мини-игра Upgrade
- `POST /api/minigames/crash` — мини-игра Crash/Dice

## Важно

- Все иконки грузятся по прямым ссылкам Steam CDN, локальные файлы изображений не используются.
- VIP-статус (через Telegram Stars) даёт только косметику и отключение рекламы — не влияет на игровые шансы.
- Виртуальная валюта пополняется через рекламу, рефералов и промокоды.
- Проект не связан с реальным выводом денег или предметов — это развлекательный симулятор.
