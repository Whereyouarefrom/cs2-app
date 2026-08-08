# ============================================
# CS2 Case Simulator — Telegram Bot (Aiogram 3)
# ============================================

import asyncio
import logging
import uuid
import datetime
import traceback
import json

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, LabeledPrice, PreCheckoutQuery,
    BotCommand, MenuButtonWebApp, ErrorEvent, BufferedInputFile,
)
from sqlalchemy import select, func

from config import (
    BOT_TOKEN, ADMIN_IDS, ADMIN_TG_ID, WEBAPP_URL, START_BALANCE,
    VIP_PRICE_STARS, REF_BONUS_INVITER, REF_BONUS_INVITED,
    REF_COMMISSION_PERCENT, REF_LOSS_COMMISSION_PERCENT,
    REF_WIN_COMMISSION_PERCENT,
)
from database import (
    init_db, close_db, async_session, User, Inventory, PromoCode,
    ChatMessage, get_setting, set_setting,
)
from format_utils import format_balance, format_balance_with_icon, format_gold_with_icon
import items_data
from cases_data import CASES

logging.basicConfig(level=logging.INFO)

# Явный таймаут на HTTP-сессию бота к Telegram Bot API. Без него зависший
# сетевой запрос (обрыв соединения, "тихий" таймаут прокси/файрвола) может
# держать корутину бесконечно — снаружи это выглядит как "бот перестал
# отвечать", хотя процесс жив. 30с с запасом покрывает long-polling запрос
# getUpdates (у него у самого timeout=20 в start_polling ниже) и обычные
# вызовы методов API (send_message и т.п.).
bot_session = AiohttpSession(timeout=30)
bot = Bot(token=BOT_TOKEN, session=bot_session)
dp = Dispatcher()


# ---------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------
async def get_or_create_user(
    telegram_id: int, username: str | None, referred_by: int | None = None,
    first_name: str | None = None,
) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if user is None:
            # Новый юзер: без реф-ссылки — старт config.START_BALANCE (5,000 💎),
            # по реф-ссылке — REF_BONUS_INVITED (25,000 💎) ВМЕСТО обычного
            # старта (Спринт 9.5), а не поверх него.
            starting_balance = REF_BONUS_INVITED if referred_by else START_BALANCE

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                balance=starting_balance,
                ref_code=str(uuid.uuid4())[:8],
                referred_by=referred_by,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # ---- Бонус пригласившему — начисляется автоматически, РОВНО
            # ОДИН РАЗ, в момент первой регистрации приглашённого (сразу
            # при создании юзера, а не задним числом при смене имени —
            # раньше это было забаговано и почти никогда не срабатывало). ----
            inviter = None
            if referred_by:
                result_inviter = await session.execute(
                    select(User).where(User.telegram_id == referred_by)
                )
                inviter = result_inviter.scalar_one_or_none()
                if inviter:
                    inviter.balance += REF_BONUS_INVITER
                    inviter.ref_earnings_total = round(
                        (inviter.ref_earnings_total or 0.0) + REF_BONUS_INVITER, 2
                    )
                    await session.commit()
                    try:
                        loss_pct = round(REF_LOSS_COMMISSION_PERCENT * 100)
                        win_pct = round(REF_WIN_COMMISSION_PERCENT * 100)
                        await bot.send_message(
                            referred_by,
                            f"👥 По твоей реферальной ссылке зарегистрировался новый игрок!\n"
                            f"Тебе начислено <b>+{REF_BONUS_INVITER} 💎</b>\n\n"
                            f"💸 А ещё теперь тебе будет пожизненно капать <b>{loss_pct}%</b> "
                            f"с каждой его проигранной ставки и <b>{win_pct}%</b> "
                            f"с его чистого выигрыша во всех режимах игры и при открытии кейсов — "
                            f"без каких-либо действий с твоей стороны.",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass  # юзер мог заблокировать бота — не критично

            # ---- Уведомление админу о КАЖДОЙ новой регистрации (Спринт 9.5) ----
            if ADMIN_TG_ID:
                try:
                    new_user_label = f"{telegram_id} (@{username})" if username else str(telegram_id)
                    if inviter:
                        inviter_label = (
                            f"{referred_by} (@{inviter.username})" if inviter.username else str(referred_by)
                        )
                        ref_line = f"👤 Реферер: <b>{inviter_label}</b>"
                    elif referred_by:
                        ref_line = f"👤 Реферер: <b>{referred_by}</b> (не найден в базе)"
                    else:
                        ref_line = "👤 Реферер: — (органическая регистрация)"

                    await bot.send_message(
                        ADMIN_TG_ID,
                        f"🆕 Новая регистрация\n"
                        f"🧑 Новичок: <b>{new_user_label}</b>\n"
                        f"{ref_line}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass  # админ мог заблокировать бота — не критично
        elif first_name and user.first_name != first_name:
            # Освежаем имя, если юзер его сменил в Telegram
            user.first_name = first_name
            await session.commit()
            await session.refresh(user)

        return user


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="⭐ Купить VIP (без рекламы)", callback_data="buy_vip")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="ref_link")],
    ])


def is_admin(user_id: int) -> bool:
    """Строгая проверка прав администратора — только по списку config.ADMIN_IDS."""
    return user_id in ADMIN_IDS


# ---------------------------------------------------
# /start
# ---------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    logging.info(f"/start от {message.from_user.id} (@{message.from_user.username}), payload: {message.text!r}")

    try:
        # deep-link payload — то, что идёт после "/start " (например: /start ref_12345)
        args = message.text.split(maxsplit=1)
        referred_by = None

        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referred_by = int(args[1].replace("ref_", ""))
                if referred_by == message.from_user.id:
                    referred_by = None  # нельзя быть рефералом самого себя
            except ValueError:
                referred_by = None

        user = await get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            referred_by=referred_by,
        )

        bonus_note = ""
        if referred_by and user.referred_by == referred_by:
            # Показываем юзеру, что реферальный бонус реально начислен
            bonus_note = f"\n🎁 Ты пришёл по реферальной ссылке — начислен бонус <b>+{REF_BONUS_INVITED} 💎</b>!\n"

        loss_pct = round(REF_LOSS_COMMISSION_PERCENT * 100)
        win_pct = round(REF_WIN_COMMISSION_PERCENT * 100)
        text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Добро пожаловать в <b>CS2 Case Simulator</b> — фановый симулятор открытия кейсов "
            f"без реального вывода денег и скинов.\n"
            f"{bonus_note}\n"
            f"💰 Твой баланс: <b>{format_balance_with_icon(user.balance)}</b>\n\n"
            f"👥 Приглашай друзей по своей реферальной ссылке — получишь разовый бонус "
            f"<b>+{REF_BONUS_INVITER} 💎</b>, а пожизненно — <b>{loss_pct}%</b> с их проигранных "
            f"ставок и <b>{win_pct}%</b> с их чистого выигрыша во всех режимах игры и при "
            f"открытии кейсов!\n\n"
            f"Жми кнопку ниже, чтобы начать открывать кейсы 👇"
        )

        await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")

    except Exception:
        # Раньше любая ошибка внутри хэндлера (например, недоступная БД) приводила
        # к тому, что бот молча ничего не отвечал пользователю — теперь она
        # логируется целиком и юзер получает вменяемое сообщение вместо тишины.
        logging.error("Ошибка в обработчике /start:\n" + traceback.format_exc())
        try:
            await message.answer(
                "⚠️ Что-то пошло не так при запуске. Попробуй ещё раз через пару секунд "
                "или напиши в поддержку, если проблема повторится."
            )
        except Exception:
            pass


# ---------------------------------------------------
# Глобальный перехватчик необработанных ошибок.
# Без него исключение в ЛЮБОМ хэндлере (не только /start) просто уходит
# в логи aiogram и снаружи выглядит как "бот молчит" — теперь всё видно.
# ---------------------------------------------------
@dp.errors()
async def global_error_handler(event: ErrorEvent):
    logging.error(
        f"Необработанное исключение при обработке апдейта {event.update.update_id}:\n"
        + "".join(traceback.format_exception(type(event.exception), event.exception, event.exception.__traceback__))
    )
    return True


# ---------------------------------------------------
# Реферальная ссылка
# ---------------------------------------------------
@dp.callback_query(F.data == "ref_link")
async def send_ref_link(callback):
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{callback.from_user.id}"

    loss_pct = round(REF_LOSS_COMMISSION_PERCENT * 100)
    win_pct = round(REF_WIN_COMMISSION_PERCENT * 100)
    await callback.message.answer(
        f"👥 Твоя реферальная ссылка:\n<code>{link}</code>\n\n"
        f"За каждого друга, который зайдёт по ссылке, ты автоматически получишь "
        f"<b>+{REF_BONUS_INVITER} 💎</b>, а друг стартует с бонусом <b>+{REF_BONUS_INVITED} 💎</b>!\n\n"
        f"💸 И это не разовая история: тебе будет пожизненно капать "
        f"<b>{loss_pct}%</b> с каждой проигранной другом ставки и <b>{win_pct}%</b> "
        f"с его чистого выигрыша во всех режимах игры и при открытии кейсов — "
        f"пока он играет, ты пассивно зарабатываешь вместе с ним.",
        parse_mode="HTML"
    )
    await callback.answer()


# ---------------------------------------------------
# Оплата VIP-статуса через Telegram Stars
# ---------------------------------------------------
@dp.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"♾️ Купить VIP навсегда — {VIP_PRICE_STARS} ⭐", callback_data="vip_forever")],
    ])
    await callback.message.answer(
        "⭐ <b>VIP-статус — навсегда</b>\n\n"
        "Что даёт VIP:\n"
        "— Полное отключение рекламы\n"
        "— Эксклюзивная тема интерфейса\n"
        "— Ускоренная анимация открытия кейсов\n\n"
        f"Цена: <b>{VIP_PRICE_STARS} ⭐ Telegram Stars</b>, один раз, без подписки.\n"
        "<i>VIP не влияет на шансы выпадения предметов — только на удобство.</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "vip_forever")
async def send_vip_invoice(callback):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="VIP навсегда",
        description="Отключение рекламы + косметические бонусы. Не влияет на игровые шансы.",
        payload="vip_forever",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label="VIP навсегда", amount=VIP_PRICE_STARS)],
        provider_token="",  # для Stars provider_token не нужен
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload != "vip_forever":
        return  # неизвестный payload — игнорируем, ничего не начисляем

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.is_vip = True
            user.vip_expires_at = None  # навсегда
            await session.commit()

    await message.answer("✅ Оплата прошла успешно! VIP-статус навсегда активирован. 🎉")


# ============================================
# АДМИН-КОМАНДЫ
# ============================================
# Права проверяются СТРОГО по config.ADMIN_IDS (is_admin()) — никаких других
# способов получить доступ к админ-командам нет. Если message.from_user.id
# не входит в этот список, команда молча ничего не делает.

ADMIN_MENU_TEXT = (
    "🔧 <b>Админ-панель</b>\n\n"
    "/stats или /online — общая статистика по всем юзерам в базе\n"
    "/give_crystals &lt;user_id&gt; &lt;amount&gt; — выдать 💎 Кристаллы по TG ID\n"
    "/give_gold &lt;user_id&gt; &lt;amount&gt; — начислить/списать 💰 Золото по TG ID\n"
    "/set_gold &lt;user_id&gt; &lt;amount&gt; — выставить точный баланс 💰 Золота по TG ID\n"
    "/give_vip &lt;user_id&gt; — выдать VIP-статус навсегда по TG ID\n"
    "/give_case &lt;user_id&gt; &lt;case_id&gt; [amount] — выдать открытие кейса(ов)\n"
    "/give_skin &lt;user_id&gt; &lt;название скина&gt; — выдать конкретный скин\n"
    "/take_gems &lt;user_id&gt; &lt;amount&gt; — списать 💎 Кристаллы\n"
    "/take_gold &lt;user_id&gt; &lt;amount&gt; — списать 💰 Золото\n"
    "/clear_inventory &lt;user_id&gt; — полностью очистить инвентарь\n"
    "/create_promo &lt;code&gt; &lt;reward_crystals&gt; &lt;activations&gt; — создать промокод на 💎\n"
    "/addpromo &lt;code&gt; &lt;type:value&gt; &lt;max_activations&gt; — создать промокод (case/skin)\n"
    "/user_info или /user &lt;tg_id&gt; — статистика, балансы и статус мута игрока\n"
    "/export_users — выгрузить .csv со всеми пользователями\n\n"
    "<b>Модерация чата:</b>\n"
    "/mute &lt;tg_id&gt; &lt;минуты&gt; &lt;причина&gt; — замутить игрока\n"
    "/unmute &lt;tg_id&gt; — снять мут\n"
    "/ban_chat &lt;tg_id&gt; — забанить игрока в чате\n"
    "/unban_chat &lt;tg_id&gt; — разбанить игрока в чате\n"
    "/mute_chat — закрыть глобальный чат на «только чтение»\n"
    "/unmute_chat — открыть чат обратно\n"
    "/admin_msg &lt;текст&gt; — объявление от лица администрации\n"
    "/set_prefix &lt;user_id&gt; &lt;префикс&gt; — выдать префикс в чате\n"
    "/rem_prefix &lt;user_id&gt; — убрать префикс\n\n"
    "<b>Доступ в приложение:</b>\n"
    "/ban &lt;user_id&gt; &lt;причина&gt; — заблокировать доступ к приложению\n"
    "/unban &lt;user_id&gt; — снять блокировку доступа\n\n"
    "<b>Прочее:</b>\n"
    "/broadcast &lt;текст&gt; — рассылка всем пользователям в лс\n"
    "/roll_event &lt;multiplier&gt; &lt;duration_hours&gt; — временный ивент x2 XP и т.п.\n\n"
    "/help или /admin_help — подробная справка по всем командам"
)

# Подробная справка со синтаксисом и примерами (ТЗ Спринта 11 / ТЗ №15: /help / /admin_help).
ADMIN_HELP_TEXT = (
    "📖 <b>Справка по командам бота</b>\n\n"
    "<b>📊 Статистика и выдача</b>\n"
    "<code>/stats</code> или <code>/online</code>\n"
    "└ общая статистика проекта (юзеры, VIP, кейсы, балансы).\n\n"
    "<code>/give_crystals &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ начислить/списать 💎 Кристаллы (amount может быть отрицательным).\n"
    "└ пример: <code>/give_crystals 123456789 5000</code>\n\n"
    "<code>/give_gold &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ начислить/списать 💰 Золото (amount может быть отрицательным, "
    "относительно текущего баланса).\n"
    "└ пример: <code>/give_gold 123456789 50</code>\n\n"
    "<code>/set_gold &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ выставить точный баланс 💰 Золота (перезаписывает, а не прибавляет).\n"
    "└ пример: <code>/set_gold 123456789 100</code>\n\n"
    "<code>/give_vip &lt;tg_id&gt;</code>\n"
    "└ выдать VIP-статус навсегда.\n"
    "└ пример: <code>/give_vip 123456789</code>\n\n"
    "<code>/give_case &lt;tg_id&gt; &lt;case_id&gt; [amount]</code>\n"
    "└ сразу открывает кейс(ы) игроку и добавляет дроп(ы) в инвентарь "
    "(amount по умолчанию 1, максимум 10 за раз). case_id — ключ кейса, "
    "как в cases_data.py/cases_data.json.\n"
    "└ пример: <code>/give_case 123456789 csgo_weapon_case 3</code>\n\n"
    "<code>/give_skin &lt;tg_id&gt; &lt;название скина&gt;</code>\n"
    "└ выдаёт конкретный скин по точному или частичному названию (ищет по "
    "каталогу всех предметов игры). Если совпадений несколько — пришлёт "
    "список вариантов, уточни название.\n"
    "└ пример: <code>/give_skin 123456789 AK-47 | Redline</code>\n\n"
    "<code>/take_gems &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ списывает 💎 Кристаллы (amount — положительное число, сколько снять; "
    "баланс не уходит ниже 0). Для точной установки в 0 — <code>/set_gems</code>.\n"
    "└ пример: <code>/take_gems 123456789 5000</code>\n\n"
    "<code>/set_gems &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ жёстко выставляет баланс 💎 Кристаллов (напр. <code>/set_gems 123456789 0</code>).\n\n"
    "<code>/take_gold &lt;tg_id&gt; &lt;amount&gt;</code>\n"
    "└ списывает 💰 Золото (не уходит ниже 0).\n"
    "└ пример: <code>/take_gold 123456789 50</code>\n\n"
    "<code>/clear_inventory &lt;tg_id&gt;</code>\n"
    "└ полностью очищает инвентарь от нелегитимных/дюпнутых предметов "
    "(снимает все предметы с P2P-маркета автоматически).\n"
    "└ пример: <code>/clear_inventory 123456789</code>\n\n"
    "<code>/user_info &lt;tg_id&gt;</code> или <code>/user &lt;tg_id&gt;</code>\n"
    "└ полная карточка игрока: балансы, VIP, статистика, статус мута/бана. "
    "<code>/user</code> дополнительно присылает .json с последними 50 "
    "предметами из инвентаря (история дропов — для анализа на дюпы).\n"
    "└ пример: <code>/user 123456789</code>\n\n"
    "<code>/export_users</code>\n"
    "└ выгружает .csv со всеми пользователями: Telegram ID | Username | "
    "Имя Фамилия | Дата регистрации | Баланс.\n\n"
    "<b>🎟 Промокоды</b>\n"
    "<code>/create_promo &lt;code&gt; &lt;reward_crystals&gt; &lt;activations&gt;</code>\n"
    "└ промокод на 💎. Пример: <code>/create_promo WELCOME 1000 500</code>\n\n"
    "<code>/addpromo &lt;code&gt; &lt;type:value&gt; &lt;max_activations&gt;</code>\n"
    "└ промокод с типом (balance/case/skin).\n"
    "└ пример: <code>/addpromo FREECASE case:kilowatt_case 100</code>\n\n"
    "<b>🛡 Модерация чата</b>\n"
    "<code>/mute &lt;tg_id&gt; &lt;минуты&gt; &lt;причина&gt;</code>\n"
    "└ замутить игрока на N минут (0 = навсегда). Причина обязательна.\n"
    "└ пример: <code>/mute 123456789 60 спам в чате</code>\n\n"
    "<code>/unmute &lt;tg_id&gt;</code>\n"
    "└ снять мут. Пример: <code>/unmute 123456789</code>\n\n"
    "<code>/ban_chat &lt;tg_id&gt;</code>\n"
    "└ полный бан написания в чат (жёстче мута).\n"
    "└ пример: <code>/ban_chat 123456789</code>\n\n"
    "<code>/unban_chat &lt;tg_id&gt;</code>\n"
    "└ снять бан чата. Пример: <code>/unban_chat 123456789</code>\n\n"
    "<code>/mute_chat</code>\n"
    "└ закрывает ГЛОБАЛЬНЫЙ чат для всех обычных игроков (режим «только "
    "чтение»); админы продолжают писать.\n\n"
    "<code>/unmute_chat</code>\n"
    "└ открывает глобальный чат обратно.\n\n"
    "<code>/admin_msg &lt;текст&gt;</code>\n"
    "└ публикует объявление от лица администрации (особый стиль/плашка "
    "в чате, видно всем).\n"
    "└ пример: <code>/admin_msg Технические работы в 21:00 по МСК</code>\n\n"
    "<code>/set_prefix &lt;tg_id&gt; &lt;префикс&gt;</code>\n"
    "└ выдаёт игроку кастомный визуальный префикс в чате, видимый всем.\n"
    "└ пример: <code>/set_prefix 123456789 [VIP]</code>\n\n"
    "<code>/rem_prefix &lt;tg_id&gt;</code>\n"
    "└ убирает префикс. Пример: <code>/rem_prefix 123456789</code>\n\n"
    "<b>🚫 Доступ в приложение</b>\n"
    "<code>/ban &lt;tg_id&gt; &lt;причина&gt;</code>\n"
    "└ полностью блокирует вход в приложение (жёстче <code>/ban_chat</code>, "
    "который запрещает только писать в чат).\n"
    "└ пример: <code>/ban 123456789 дюп предметов</code>\n\n"
    "<code>/unban &lt;tg_id&gt;</code>\n"
    "└ снимает блокировку доступа. Пример: <code>/unban 123456789</code>\n\n"
    "<b>📣 Прочее</b>\n"
    "<code>/broadcast &lt;текст&gt;</code>\n"
    "└ рассылает сообщение всем зарегистрированным пользователям в лс "
    "(с пометкой 📣 Объявление). Присылает отчёт, скольким доставлено.\n"
    "└ пример: <code>/broadcast Завтра стартует турнир недели!</code>\n\n"
    "<code>/roll_event &lt;multiplier&gt; &lt;duration_hours&gt;</code>\n"
    "└ запускает временный ивент — множитель XP за кейсы/мини-игры на N "
    "часов (напр. x2 на 2 часа). <code>/roll_event 1 0</code> — выключить "
    "текущий ивент досрочно.\n"
    "└ пример: <code>/roll_event 2 2</code>\n\n"
    "<i>Все админ-команды доступны только Telegram ID из config.ADMIN_IDS.</i>"
)


@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_MENU_TEXT, parse_mode="HTML")


@dp.message(Command("help"))
@dp.message(Command("admin_help"))
async def cmd_help(message: Message):
    if not is_admin(message.from_user.id):
        # Обычным игрокам — короткая подсказка вместо админ-справки.
        await message.answer(
            "🎮 Жми синюю кнопку «Играть» слева от поля ввода или /start, "
            "чтобы открыть приложение."
        )
        return
    await message.answer(ADMIN_HELP_TEXT, parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session() as session:
        total_users = await session.scalar(select(func.count(User.id)))
        total_cases = await session.scalar(select(func.sum(User.total_cases_opened))) or 0
        total_balance = await session.scalar(select(func.sum(User.balance))) or 0
        total_items = await session.scalar(select(func.count(Inventory.id)))
        vip_users = await session.scalar(select(func.count(User.id)).where(User.is_vip == True))
        referred_users = await session.scalar(
            select(func.count(User.id)).where(User.referred_by.is_not(None))
        )

        text = (
            f"📊 <b>Статистика проекта</b>\n\n"
            f"👥 Пользователей всего: <b>{total_users}</b>\n"
            f"⭐ VIP-пользователей: <b>{vip_users}</b>\n"
            f"👥 Пришло по рефералке: <b>{referred_users}</b>\n"
            f"📦 Всего открыто кейсов: <b>{total_cases}</b>\n"
            f"🎒 Предметов в инвентарях: <b>{total_items}</b>\n"
            f"💰 Суммарный баланс всех юзеров: <b>{format_balance_with_icon(total_balance)}</b>\n"
        )
        await message.answer(text, parse_mode="HTML")


@dp.message(Command("give_crystals"))
async def cmd_give_crystals(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give_crystals <user_id> <amount>\n\nПример: /give_crystals 123456789 5000")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Некорректные параметры — user_id и amount должны быть числами")
        return

    if amount == 0:
        await message.answer("❌ amount не может быть равен 0")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.balance += amount
        await session.commit()

        sign = "+" if amount > 0 else ""
        await message.answer(
            f"✅ Пользователю <code>{target_id}</code> начислено <b>{sign}{format_balance_with_icon(amount)}</b>\n"
            f"Новый баланс: <b>{format_balance_with_icon(user.balance)}</b>",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(
            target_id,
            f"🎁 Администратор начислил тебе <b>{sign}{format_balance_with_icon(amount)}</b>!",
            parse_mode="HTML",
        )
    except Exception:
        pass  # юзер мог заблокировать бота — не критично для самой выдачи


@dp.message(Command("give_gold"))
async def cmd_give_gold(message: Message):
    """Начисляет (или списывает, если amount отрицательный) 💰 Золото
    ОТНОСИТЕЛЬНО текущего баланса пользователя — по аналогии с
    /give_crystals. Для точной установки баланса используй /set_gold."""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give_gold <user_id> <amount>\n\nПример: /give_gold 123456789 50")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Некорректные параметры — user_id и amount должны быть числами")
        return

    if amount == 0:
        await message.answer("❌ amount не может быть равен 0")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.gold_balance = (user.gold_balance or 0.0) + amount
        await session.commit()

        sign = "+" if amount > 0 else ""
        await message.answer(
            f"✅ Пользователю <code>{target_id}</code> начислено <b>{sign}{format_gold_with_icon(amount)}</b>\n"
            f"Новый баланс золота: <b>{format_gold_with_icon(user.gold_balance)}</b>",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(
            target_id,
            f"🎁 Администратор начислил тебе <b>{sign}{format_gold_with_icon(amount)}</b>!",
            parse_mode="HTML",
        )
    except Exception:
        pass  # юзер мог заблокировать бота — не критично для самой выдачи


@dp.message(Command("set_gold"))
async def cmd_set_gold(message: Message):
    """Жёстко выставляет баланс 💰 Золота ровно в amount (перезаписывает,
    а не прибавляет) — для ручной коррекции баланса, в отличие от
    /give_gold, который прибавляет/вычитает."""
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /set_gold <user_id> <amount>\n\nПример: /set_gold 123456789 100")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Некорректные параметры — user_id и amount должны быть числами")
        return

    if amount < 0:
        await message.answer("❌ amount не может быть отрицательным")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.gold_balance = amount
        await session.commit()

        await message.answer(
            f"✅ Баланс золота пользователя <code>{target_id}</code> установлен: "
            f"<b>{format_gold_with_icon(user.gold_balance)}</b>",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(
            target_id,
            f"🔧 Администратор изменил твой баланс золота: теперь у тебя "
            f"<b>{format_gold_with_icon(amount)}</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass  # юзер мог заблокировать бота — не критично для самой выдачи


@dp.message(Command("give_vip"))
async def cmd_give_vip(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /give_vip <user_id>\n\nПример: /give_vip 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        if user.is_vip:
            await message.answer(f"ℹ️ У пользователя <code>{target_id}</code> уже есть VIP", parse_mode="HTML")
            return

        user.is_vip = True
        user.vip_expires_at = None  # выдаётся навсегда, как и платный VIP
        await session.commit()

        await message.answer(
            f"✅ Пользователю <code>{target_id}</code> выдан VIP-статус навсегда ⭐",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(target_id, "⭐ Тебе выдан VIP-статус навсегда! Реклама отключена.")
    except Exception:
        pass


@dp.message(Command("addpromo"))
async def cmd_add_promo(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 4:
        await message.answer(
            "Использование: /addpromo <code> <reward_type:reward_value> <max_activations>\n\n"
            "Примеры:\n"
            "/addpromo WELCOME2026 balance:1000 500\n"
            "/addpromo FREECASE case:kilowatt_case 100"
        )
        return

    code = args[1].upper()
    try:
        reward_type, reward_value = args[2].split(":", 1)
        max_activations = int(args[3])
    except ValueError:
        await message.answer("❌ Некорректный формат reward (используй тип:значение)")
        return

    if reward_type not in ("balance", "case", "skin"):
        await message.answer("❌ reward_type должен быть: balance | case | skin")
        return

    async with async_session() as session:
        existing = await session.execute(select(PromoCode).where(PromoCode.code == code))
        if existing.scalar_one_or_none():
            await message.answer(f"❌ Промокод {code} уже существует")
            return

        promo = PromoCode(
            code=code,
            reward_type=reward_type,
            reward_value=reward_value,
            max_activations=max_activations,
            used_count=0,
        )
        session.add(promo)
        await session.commit()

        await message.answer(
            f"✅ Промокод создан:\n"
            f"Код: <code>{code}</code>\n"
            f"Награда: {reward_type} = {reward_value}\n"
            f"Лимит активаций: {max_activations}",
            parse_mode="HTML"
        )


@dp.message(Command("create_promo"))
async def cmd_create_promo(message: Message):
    """/create_promo <code> <reward_crystals> <activations>

    Упрощённый алиас поверх /addpromo — всегда создаёт промокод с
    наградой типа "balance" (начисление кристаллов), без необходимости
    указывать reward_type вручную.
    """
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 4:
        await message.answer(
            "Использование: /create_promo <code> <reward_crystals> <activations>\n\n"
            "Пример: /create_promo WELCOME2026 1000 500"
        )
        return

    code = args[1].upper()
    try:
        reward_crystals = float(args[2])
        max_activations = int(args[3])
    except ValueError:
        await message.answer("❌ reward_crystals и activations должны быть числами")
        return

    if reward_crystals <= 0 or max_activations <= 0:
        await message.answer("❌ reward_crystals и activations должны быть положительными")
        return

    async with async_session() as session:
        existing = await session.execute(select(PromoCode).where(PromoCode.code == code))
        if existing.scalar_one_or_none():
            await message.answer(f"❌ Промокод {code} уже существует")
            return

        promo = PromoCode(
            code=code,
            reward_type="balance",
            reward_value=str(reward_crystals),
            max_activations=max_activations,
            used_count=0,
        )
        session.add(promo)
        await session.commit()

        await message.answer(
            f"✅ Промокод создан:\n"
            f"Код: <code>{code}</code>\n"
            f"Награда: {format_balance_with_icon(reward_crystals)}\n"
            f"Лимит активаций: {max_activations}",
            parse_mode="HTML"
        )


@dp.message(Command("user_info"))
async def cmd_user_info(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /user_info <telegram_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный telegram_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден")
            return

        inv_result = await session.execute(select(func.count(Inventory.id)).where(Inventory.user_id == user.id))
        inv_count = inv_result.scalar()

        # ---- Статус мута/бана чата (Спринт 11) ----
        now = datetime.datetime.utcnow()
        if user.is_chat_banned:
            mute_line = "🚫 <b>ЗАБАНЕН в чате</b>"
        elif user.is_muted and (user.mute_until is None or user.mute_until > now):
            if user.mute_until is None:
                until = "навсегда"
            else:
                until = f"до {user.mute_until.strftime('%d.%m.%Y %H:%M')} UTC"
            mute_line = f"🔇 <b>В МУТЕ</b> ({until})\n   Причина: {user.mute_reason or '—'}"
        else:
            mute_line = "✅ Не в муте / не забанен"

        vip_status = (
            "✅ навсегда" if (user.is_vip and not user.vip_expires_at)
            else ("✅ до " + user.vip_expires_at.strftime('%d.%m.%Y') if user.is_vip else "❌")
        )

        await message.answer(
            f"👤 <b>Пользователь {target_id}</b>\n\n"
            f"Username: @{user.username or '—'}\n"
            f"Имя: {user.first_name or '—'}\n\n"
            f"💎 Кристаллы: {format_balance_with_icon(user.balance)}\n"
            f"💰 Золото: {round(user.gold_balance or 0, 2)}\n"
            f"⭐ VIP: {vip_status}\n\n"
            f"📦 Кейсов открыто: {user.total_cases_opened}\n"
            f"🎒 Предметов в инвентаре: {inv_count}\n"
            f"🏆 Топ-дроп: {user.top_drop_name or '—'}\n"
            f"⭐ XP: {user.xp or 0} | Уровень: {user.last_seen_level or 1}\n\n"
            f"👥 Реф. код: {user.ref_code}\n"
            f"👤 Приглашён: {user.referred_by or '—'}\n\n"
            f"<b>Модерация чата:</b>\n{mute_line}",
            parse_mode="HTML"
        )


# ============================================
# Модерация чата (Спринт 11)
# ============================================
@dp.message(Command("mute"))
async def cmd_mute(message: Message):
    if not is_admin(message.from_user.id):
        return

    # /mute <tg_id> <минуты> <причина...> — причина может состоять из
    # нескольких слов, поэтому split с maxsplit=3.
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer(
            "Использование: /mute <tg_id> <минуты> <причина>\n\n"
            "Пример: /mute 123456789 60 спам в чате\n"
            "(минуты = 0 — мут навсегда)"
        )
        return

    try:
        target_id = int(args[1])
        minutes = int(args[2])
    except ValueError:
        await message.answer("❌ tg_id и минуты должны быть числами")
        return

    if minutes < 0:
        await message.answer("❌ Минуты не могут быть отрицательными (0 = навсегда)")
        return

    reason = args[3].strip()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.is_muted = True
        if minutes == 0:
            user.mute_until = None  # навсегда
            until_label = "навсегда"
        else:
            user.mute_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
            until_label = f"на {minutes} мин (до {user.mute_until.strftime('%d.%m.%Y %H:%M')} UTC)"
        user.mute_reason = reason
        await session.commit()

    await message.answer(
        f"🔇 Пользователь <code>{target_id}</code> замучен {until_label}\n"
        f"Причина: {reason}",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            target_id,
            f"🔇 Вы получили мут в чате {until_label}.\nПричина: {reason}",
        )
    except Exception:
        pass


@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /unmute <tg_id>\n\nПример: /unmute 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный tg_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        if not user.is_muted:
            await message.answer(f"ℹ️ Пользователь <code>{target_id}</code> и так не в муте", parse_mode="HTML")
            return

        user.is_muted = False
        user.mute_until = None
        user.mute_reason = None
        await session.commit()

    await message.answer(f"✅ Мут с пользователя <code>{target_id}</code> снят", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "✅ С вас снят мут в чате. Пишите аккуратнее 🙂")
    except Exception:
        pass


@dp.message(Command("ban_chat"))
async def cmd_ban_chat(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /ban_chat <tg_id>\n\nПример: /ban_chat 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный tg_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        if user.is_chat_banned:
            await message.answer(f"ℹ️ Пользователь <code>{target_id}</code> уже забанен в чате", parse_mode="HTML")
            return

        user.is_chat_banned = True
        await session.commit()

    await message.answer(f"🚫 Пользователь <code>{target_id}</code> забанен в чате", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "🚫 Вы заблокированы в глобальном чате.")
    except Exception:
        pass


@dp.message(Command("unban_chat"))
async def cmd_unban_chat(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /unban_chat <tg_id>\n\nПример: /unban_chat 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный tg_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        if not user.is_chat_banned:
            await message.answer(f"ℹ️ Пользователь <code>{target_id}</code> и так не забанен в чате", parse_mode="HTML")
            return

        user.is_chat_banned = False
        await session.commit()

    await message.answer(f"✅ Бан чата с пользователя <code>{target_id}</code> снят", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "✅ Вас разбанили в глобальном чате.")
    except Exception:
        pass


# ============================================
# ПРАВКИ В ТЗ №15: Расширенная админ-панель
# ============================================

# ---------------------------------------------------
# /online — алиас /stats (тот же вывод, другое имя команды по ТЗ)
# ---------------------------------------------------
@dp.message(Command("online"))
async def cmd_online(message: Message):
    await cmd_stats(message)


# ---------------------------------------------------
# /mute_chat, /unmute_chat — глобальный режим "только чтение"
# ---------------------------------------------------
@dp.message(Command("mute_chat"))
async def cmd_mute_chat(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with async_session() as session:
        await set_setting(session, "chat_locked", "1")
        await session.commit()
    await message.answer("🔒 Глобальный чат закрыт для всех игроков (режим «только чтение»). Админы продолжают писать.")


@dp.message(Command("unmute_chat"))
async def cmd_unmute_chat(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with async_session() as session:
        await set_setting(session, "chat_locked", "0")
        await session.commit()
    await message.answer("🔓 Глобальный чат снова открыт для всех игроков.")


# ---------------------------------------------------
# /admin_msg — объявление от лица администрации в глобальном чате
# ---------------------------------------------------
@dp.message(Command("admin_msg"))
async def cmd_admin_msg(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2 or not args[1].strip():
        await message.answer("Использование: /admin_msg <текст>\n\nПример: /admin_msg Технические работы в 21:00 по МСК")
        return

    text = args[1].strip()

    async with async_session() as session:
        # Системное объявление публикуется от лица самого админа (его User-
        # запись создаётся автоматически, если он ни разу не открывал
        # Mini App — это нормально: getpost_or_create тут не нужен, т.к.
        # is_system=True сообщения не привязывают отправителя визуально
        # (фронт рисует их без аватара/ника, см. app.js renderChatMessage).
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin_user = result.scalar_one_or_none()
        if admin_user is None:
            admin_user = await get_or_create_user(message.from_user.id, message.from_user.username, first_name=message.from_user.first_name)
            result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
            admin_user = result.scalar_one_or_none()

        msg = ChatMessage(
            user_id=admin_user.id, text=text, is_system=True,
            is_admin_announcement=True, is_hidden=False,
        )
        session.add(msg)
        await session.commit()

    await message.answer(f"✅ Объявление опубликовано в чате:\n\n🛡 {text}")


# ---------------------------------------------------
# /set_prefix, /rem_prefix — кастомный визуальный префикс в чате
# ---------------------------------------------------
@dp.message(Command("set_prefix"))
async def cmd_set_prefix(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        await message.answer("Использование: /set_prefix <user_id> <префикс>\n\nПример: /set_prefix 123456789 [VIP]")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    prefix = args[2].strip()
    if len(prefix) > 20:
        await message.answer("❌ Префикс слишком длинный (максимум 20 символов)")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.chat_prefix = prefix
        await session.commit()

    await message.answer(f"✅ Пользователю <code>{target_id}</code> выдан префикс: {prefix}", parse_mode="HTML")
    try:
        await bot.send_message(target_id, f"🏷 Администратор выдал тебе новый префикс в чате: {prefix}")
    except Exception:
        pass


@dp.message(Command("rem_prefix"))
async def cmd_rem_prefix(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /rem_prefix <user_id>\n\nПример: /rem_prefix 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.chat_prefix = None
        await session.commit()

    await message.answer(f"✅ Префикс пользователя <code>{target_id}</code> убран", parse_mode="HTML")


# ---------------------------------------------------
# /export_users — выгрузка .csv со всеми пользователями
# ---------------------------------------------------
@dp.message(Command("export_users"))
async def cmd_export_users(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.id.asc()))
        users = result.scalars().all()

    if not users:
        await message.answer("В базе пока нет ни одного пользователя.")
        return

    lines = ["Telegram ID | @username | Имя Фамилия | Дата регистрации | Баланс"]
    for u in users:
        reg_date = u.created_at.strftime("%d.%m.%Y %H:%M") if u.created_at else "—"
        lines.append(
            f"{u.telegram_id} | @{u.username or '—'} | {u.first_name or '—'} | "
            f"{reg_date} | {round(u.balance or 0, 2)}"
        )
    content = "\n".join(lines)
    filename = f"users_export_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"

    await message.answer_document(
        BufferedInputFile(content.encode("utf-8"), filename=filename),
        caption=f"📄 Экспорт пользователей: {len(users)} шт.",
    )


# ---------------------------------------------------
# /user — расширенная выгрузка по одному пользователю (алиас /user_info +
# .json с историей последних 50 предметов инвентаря).
#
# ВАЖНО: в проекте пока нет отдельной таблицы лога действий/раундов
# мини-игр (Crash/Mines/Tower/Ladder/Wheel/Апгрейдер) — только Inventory
# хранит историю ПОЛУЧЕННЫХ предметов (обо всех источниках: кейсы, промо,
# крафт) с датой obtained_at. Поэтому "история последних 50 действий" ниже
# — это история дропов из инвентаря, а не полный лог всех ставок. Для
# полноценного аудита мини-игр на дюпы/читерство потребуется отдельная
# таблица-лог транзакций — это можно добавить отдельной правкой, если нужно.
# ---------------------------------------------------
@dp.message(Command("user"))
async def cmd_user(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /user <telegram_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный telegram_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден")
            return

        inv_result = await session.execute(
            select(Inventory).where(Inventory.user_id == user.id)
            .order_by(Inventory.obtained_at.desc()).limit(50)
        )
        recent_items = inv_result.scalars().all()

        ban_line = (
            f"🚫 <b>ЗАБЛОКИРОВАН</b> ({user.ban_reason or '—'})" if user.is_banned
            else "✅ Доступ не заблокирован"
        )
        vip_status = (
            "✅ навсегда" if (user.is_vip and not user.vip_expires_at)
            else ("✅ до " + user.vip_expires_at.strftime('%d.%m.%Y') if user.is_vip else "❌")
        )

        await message.answer(
            f"👤 <b>Пользователь {target_id}</b>\n\n"
            f"Username: @{user.username or '—'}\n"
            f"Имя: {user.first_name or '—'}\n"
            f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else '—'}\n"
            f"Префикс в чате: {user.chat_prefix or '—'}\n\n"
            f"💎 Кристаллы: {format_balance_with_icon(user.balance)}\n"
            f"💰 Золото: {round(user.gold_balance or 0, 2)}\n"
            f"⭐ VIP: {vip_status}\n\n"
            f"📦 Кейсов открыто: {user.total_cases_opened}\n"
            f"🎒 Предметов в инвентаре сейчас: {len(recent_items) if len(recent_items) < 50 else '50+'}\n"
            f"🏆 Топ-дроп: {user.top_drop_name or '—'} ({round(user.top_drop_price or 0)} 💎)\n"
            f"⭐ XP: {user.xp or 0} | Уровень: {user.last_seen_level or 1}\n\n"
            f"👥 Реф. код: {user.ref_code}\n"
            f"👤 Приглашён: {user.referred_by or '—'}\n\n"
            f"<b>Доступ:</b>\n{ban_line}",
            parse_mode="HTML"
        )

        if recent_items:
            history = [
                {
                    "skin_name": it.skin_name,
                    "rarity": it.rarity,
                    "quality": it.quality,
                    "stattrak": bool(it.stattrak),
                    "price": it.skin_price,
                    "obtained_from_case": it.obtained_from_case,
                    "obtained_at": it.obtained_at.isoformat() if it.obtained_at else None,
                    "is_on_market": bool(it.is_on_market),
                }
                for it in recent_items
            ]
            payload = json.dumps(
                {"telegram_id": target_id, "recent_items_count": len(history), "items": history},
                ensure_ascii=False, indent=2,
            )
            filename = f"user_{target_id}_history.json"
            await message.answer_document(
                BufferedInputFile(payload.encode("utf-8"), filename=filename),
                caption=(
                    f"📄 История последних {len(history)} полученных предметов "
                    f"(для анализа на дюпы). Лог мини-игр (Crash/Mines/Tower/"
                    f"Ladder/Wheel) в проекте пока не ведётся отдельной таблицей."
                ),
            )


# ---------------------------------------------------
# /give_case — выдать открытие кейса(ов) (сразу роллит и кладёт в инвентарь)
# ---------------------------------------------------
@dp.message(Command("give_case"))
async def cmd_give_case(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) not in (3, 4):
        await message.answer(
            "Использование: /give_case <user_id> <case_id> [amount]\n\n"
            "Пример: /give_case 123456789 csgo_weapon_case 3\n\n"
            f"Доступные case_id (первые 10): {', '.join(list(CASES.keys())[:10])}"
        )
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    case_key = args[2]
    if case_key not in CASES:
        await message.answer(
            f"❌ Кейс <code>{case_key}</code> не найден.\n\n"
            f"Доступные case_id (первые 15): {', '.join(list(CASES.keys())[:15])}",
            parse_mode="HTML",
        )
        return

    amount = 1
    if len(args) == 4:
        try:
            amount = int(args[3])
        except ValueError:
            await message.answer("❌ amount должен быть целым числом")
            return
    if amount < 1 or amount > 10:
        await message.answer("❌ amount должен быть от 1 до 10 за раз")
        return

    import main as main_module  # отложенный импорт — main.py при необходимости импортирует bot.py

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        drops = []
        for _ in range(amount):
            drop = main_module.roll_item(case_key)
            item_record = Inventory(
                user_id=user.id,
                skin_name=drop["name"],
                skin_price=drop["price"],
                rarity=drop["rarity"],
                quality=drop["quality"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                image_url=drop["image"],
                obtained_from_case=CASES[case_key]["name"] + " (выдано админом)",
            )
            session.add(item_record)
            main_module._maybe_update_top_drop(user, drop)
            drops.append(drop)

        user.total_cases_opened = (user.total_cases_opened or 0) + amount
        await session.commit()

    drops_text = "\n".join(f"• {d['name']} ({round(d['price'])} 💎)" for d in drops)
    await message.answer(
        f"✅ Пользователю <code>{target_id}</code> выдано открытие «{CASES[case_key]['name']}» ×{amount}:\n\n{drops_text}",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(
            target_id,
            f"🎁 Администратор выдал тебе кейс «{CASES[case_key]['name']}» ×{amount}! Загляни в инвентарь.",
        )
    except Exception:
        pass


# ---------------------------------------------------
# /give_skin — выдать конкретный скин в инвентарь по названию
# ---------------------------------------------------
@dp.message(Command("give_skin"))
async def cmd_give_skin(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        await message.answer(
            "Использование: /give_skin <user_id> <название скина>\n\n"
            "Пример: /give_skin 123456789 AK-47 | Redline"
        )
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    query = args[2].strip()

    # Точное совпадение (регистронезависимо) -> иначе поиск по подстроке
    # с уточнением, если найдено несколько кандидатов.
    exact = items_data.get_item(query)
    if not exact:
        for it in items_data.ALL_ITEMS:
            if it["name"].lower() == query.lower():
                exact = it
                break

    if not exact:
        matches = items_data.search_items(query, limit=10)
        if not matches:
            await message.answer(f"❌ Скин по запросу «{query}» не найден в каталоге")
            return
        if len(matches) > 1:
            names = "\n".join(f"• {m['name']}" for m in matches)
            await message.answer(
                f"Найдено несколько скинов по запросу «{query}» — уточни точное название:\n\n{names}"
            )
            return
        exact = matches[0]

    import main as main_module

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        drop = main_module._roll_item_instance(exact["name"], exact["rarity"], exact.get("image"))
        item_record = Inventory(
            user_id=user.id,
            skin_name=drop["name"],
            skin_price=drop["price"],
            rarity=drop["rarity"],
            quality=drop["quality"],
            stattrak=drop["stattrak"],
            float_val=drop["float_val"],
            image_url=drop["image"],
            obtained_from_case="Выдано админом",
        )
        session.add(item_record)
        main_module._maybe_update_top_drop(user, drop)
        await session.commit()

    await message.answer(
        f"✅ Пользователю <code>{target_id}</code> выдан скин: <b>{drop['name']}</b> "
        f"({round(drop['price'])} 💎, {drop['quality']}{', StatTrak™' if drop['stattrak'] else ''})",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(target_id, f"🎁 Администратор выдал тебе скин: {drop['name']}! Загляни в инвентарь.")
    except Exception:
        pass


# ---------------------------------------------------
# /take_gems, /set_gems — списание / точная установка 💎 Кристаллов
# ---------------------------------------------------
@dp.message(Command("take_gems"))
async def cmd_take_gems(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /take_gems <user_id> <amount>\n\nПример: /take_gems 123456789 5000")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ user_id и amount должны быть числами")
        return

    if amount <= 0:
        await message.answer("❌ amount должен быть положительным числом (сколько списать)")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.balance = max(0.0, (user.balance or 0.0) - amount)
        await session.commit()

        await message.answer(
            f"✅ У пользователя <code>{target_id}</code> списано <b>{format_balance_with_icon(amount)}</b>\n"
            f"Новый баланс: <b>{format_balance_with_icon(user.balance)}</b>",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(target_id, f"⚠️ Администратор списал с твоего баланса {format_balance_with_icon(amount)}.")
    except Exception:
        pass


@dp.message(Command("set_gems"))
async def cmd_set_gems(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /set_gems <user_id> <amount>\n\nПример: /set_gems 123456789 0")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ user_id и amount должны быть числами")
        return

    if amount < 0:
        await message.answer("❌ amount не может быть отрицательным")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.balance = amount
        await session.commit()

        await message.answer(
            f"✅ Баланс Кристаллов пользователя <code>{target_id}</code> установлен: "
            f"<b>{format_balance_with_icon(user.balance)}</b>",
            parse_mode="HTML"
        )


# ---------------------------------------------------
# /take_gold — списание 💰 Золота
# ---------------------------------------------------
@dp.message(Command("take_gold"))
async def cmd_take_gold(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /take_gold <user_id> <amount>\n\nПример: /take_gold 123456789 50")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ user_id и amount должны быть числами")
        return

    if amount <= 0:
        await message.answer("❌ amount должен быть положительным числом (сколько списать)")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.gold_balance = max(0.0, (user.gold_balance or 0.0) - amount)
        await session.commit()

        await message.answer(
            f"✅ У пользователя <code>{target_id}</code> списано <b>{format_gold_with_icon(amount)}</b>\n"
            f"Новый баланс золота: <b>{format_gold_with_icon(user.gold_balance)}</b>",
            parse_mode="HTML"
        )

    try:
        await bot.send_message(target_id, f"⚠️ Администратор списал с твоего баланса {format_gold_with_icon(amount)}.")
    except Exception:
        pass


# ---------------------------------------------------
# /clear_inventory — полностью очистить инвентарь (дюпы/нарушения)
# ---------------------------------------------------
@dp.message(Command("clear_inventory"))
async def cmd_clear_inventory(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /clear_inventory <user_id>\n\nПример: /clear_inventory 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        del_result = await session.execute(select(func.count(Inventory.id)).where(Inventory.user_id == user.id))
        count = del_result.scalar() or 0

        await session.execute(Inventory.__table__.delete().where(Inventory.user_id == user.id))
        await session.commit()

    await message.answer(f"✅ Инвентарь пользователя <code>{target_id}</code> очищен ({count} предметов удалено)", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "⚠️ Администрация очистила твой инвентарь (обнаружены нелегитимные предметы).")
    except Exception:
        pass


# ---------------------------------------------------
# /ban, /unban — полная блокировка доступа к приложению
# ---------------------------------------------------
@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /ban <user_id> <причина>\n\nПример: /ban 123456789 дюп предметов")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    reason = args[2].strip() if len(args) == 3 else "не указана"

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        user.is_banned = True
        user.ban_reason = reason
        user.banned_at = datetime.datetime.utcnow()
        await session.commit()

    await message.answer(f"🚫 Пользователь <code>{target_id}</code> заблокирован. Причина: {reason}", parse_mode="HTML")
    try:
        await bot.send_message(target_id, f"🚫 Доступ к приложению заблокирован администрацией.\nПричина: {reason}")
    except Exception:
        pass


@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /unban <user_id>\n\nПример: /unban 123456789")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Некорректный user_id")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь <code>{target_id}</code> не найден", parse_mode="HTML")
            return

        if not user.is_banned:
            await message.answer(f"ℹ️ Пользователь <code>{target_id}</code> и так не заблокирован", parse_mode="HTML")
            return

        user.is_banned = False
        user.ban_reason = None
        await session.commit()

    await message.answer(f"✅ Блокировка доступа с пользователя <code>{target_id}</code> снята", parse_mode="HTML")
    try:
        await bot.send_message(target_id, "✅ Доступ к приложению восстановлен администрацией.")
    except Exception:
        pass


# ---------------------------------------------------
# /broadcast — рассылка сообщения всем зарегистрированным пользователям
# ---------------------------------------------------
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2 or not args[1].strip():
        await message.answer("Использование: /broadcast <текст>\n\nПример: /broadcast Завтра стартует турнир недели!")
        return

    text = args[1].strip()

    async with async_session() as session:
        result = await session.execute(select(User.telegram_id).where(User.is_banned == False))  # noqa: E712
        telegram_ids = [row[0] for row in result.all()]

    status_msg = await message.answer(f"📣 Рассылка запущена: {len(telegram_ids)} получателей...")

    sent, failed = 0, 0
    for tg_id in telegram_ids:
        try:
            await bot.send_message(tg_id, f"📣 <b>Объявление</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(tg_id, f"📣 <b>Объявление</b>\n\n{text}", parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1  # юзер заблокировал бота / деактивировал аккаунт и т.п.
        await asyncio.sleep(0.05)  # мягкий rate-limit, чтобы не словить общий 429 от Bot API

    await status_msg.edit_text(f"📣 Рассылка завершена: доставлено {sent} из {len(telegram_ids)} (ошибок: {failed}).")


# ---------------------------------------------------
# /roll_event — временный ивент (множитель XP на N часов)
# ---------------------------------------------------
@dp.message(Command("roll_event"))
async def cmd_roll_event(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer(
            "Использование: /roll_event <multiplier> <duration_hours>\n\n"
            "Пример: /roll_event 2 2 — x2 XP за кейсы/мини-игры на 2 часа\n"
            "/roll_event 1 0 — выключить текущий ивент досрочно"
        )
        return

    try:
        multiplier = float(args[1])
        duration_hours = float(args[2])
    except ValueError:
        await message.answer("❌ multiplier и duration_hours должны быть числами")
        return

    if multiplier < 0:
        await message.answer("❌ multiplier не может быть отрицательным")
        return

    async with async_session() as session:
        if duration_hours <= 0:
            # Досрочное выключение — expires_at в прошлом, множитель перестаёт применяться.
            await set_setting(session, "event_xp_multiplier", "1")
            await set_setting(session, "event_xp_expires_at", datetime.datetime.utcnow().isoformat())
            await session.commit()
            await message.answer("✅ Текущий ивент выключен (множитель XP вернулся к x1).")
            return

        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=duration_hours)
        await set_setting(session, "event_xp_multiplier", str(multiplier))
        await set_setting(session, "event_xp_expires_at", expires_at.isoformat())
        await session.commit()

    await message.answer(
        f"🎉 Ивент запущен: x{multiplier} XP за кейсы/крафт/мини-игры на {duration_hours} ч.\n"
        f"Действует до {expires_at.strftime('%d.%m.%Y %H:%M')} UTC."
    )


# ---------------------------------------------------
# Настройка бота при старте: синяя кнопка "Играть" слева от поля ввода
# и список команд (подсказки в интерфейсе Telegram)
# ---------------------------------------------------
async def setup_bot():
    # 1) САМАЯ ЧАСТАЯ причина "бот вообще молчит на /start" — на боте остался
    #    активный webhook (например, после теста на Render/Railway или другого
    #    хостинга). Пока webhook установлен, getUpdates() для long polling
    #    просто не получает апдейты (Telegram отдаёт 409 Conflict в логах,
    #    а внешне выглядит так, будто бот не отвечает вообще ни на что).
    #    drop_pending_updates=True также сбрасывает очередь старых /start,
    #    накопившихся, пока бот был выключен.
    await bot.delete_webhook(drop_pending_updates=True)

    # 2) Синяя кнопка "Играть" слева от поля ввода текста — открывает
    #    Mini App в один тап, без необходимости искать команду/кнопку в чате.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="🎮 Играть",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )

    # 3) Список команд — подсказки при вводе "/" в чате с ботом
    await bot.set_my_commands([
        BotCommand(command="start", description="🎮 Запустить бота / открыть игру"),
        BotCommand(command="help", description="📖 Справка по командам"),
    ])

    logging.info("Бот настроен: webhook сброшен, menu button и команды установлены.")


# ---------------------------------------------------
# Точка входа
# ---------------------------------------------------
# Максимальная задержка между попытками переподключения после сбоя сети —
# растёт экспоненциально от 2 до 60 секунд, чтобы не долбить Telegram API
# запросами при длительном обрыве связи, но и не ждать вечно.
RECONNECT_DELAY_MIN = 2
RECONNECT_DELAY_MAX = 60


async def run_polling_with_reconnect():
    """Обёртка над dp.start_polling с автоматическим переподключением.

    aiogram 3 сам по себе уже перезапускает getUpdates при большинстве
    сетевых сбоев внутри start_polling — но если соединение обрывается
    настолько грубо, что вылетает необработанное исключение (обрыв DNS,
    долгий сбой сети провайдера и т.п.), раньше это просто убивало
    процесс/корутину и бот переставал отвечать до ручного рестарта.
    Теперь любая TelegramNetworkError и прочие сетевые исключения
    перехватываются, и polling запускается заново с задержкой."""
    delay = RECONNECT_DELAY_MIN
    while True:
        try:
            await dp.start_polling(
                bot,
                # Таймаут одного long-polling запроса getUpdates к Telegram —
                # без него зависший запрос может держать цикл бесконечно.
                polling_timeout=20,
                handle_signals=False,
            )
            break  # start_polling завершился штатно (например, dp.stop_polling())
        except (TelegramNetworkError, TelegramRetryAfter, ConnectionError, TimeoutError) as e:
            logging.error(f"Сбой сети при polling, переподключение через {delay}с: {e}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)
        except Exception:
            # Неожиданная ошибка — логируем целиком, но всё равно пробуем
            # переподключиться, а не молча "умирать".
            logging.error("Неожиданная ошибка в polling-цикле:\n" + traceback.format_exc())
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)


async def main():
    await init_db()
    await setup_bot()
    try:
        await run_polling_with_reconnect()
    finally:
        # Гарантированно закрываем HTTP-сессию бота и пул соединений БД
        # при остановке процесса — без этого соединения "подвисают" до
        # истечения собственных таймаутов на стороне Telegram/БД.
        await bot.session.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
