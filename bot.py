# ============================================
# CS2 Case Simulator — Telegram Bot (Aiogram 3)
# ============================================

import asyncio
import logging
import uuid
import datetime
import traceback

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, LabeledPrice, PreCheckoutQuery,
    BotCommand, MenuButtonWebApp, ErrorEvent,
)
from sqlalchemy import select, func

from config import (
    BOT_TOKEN, ADMIN_IDS, WEBAPP_URL, START_BALANCE,
    VIP_PRICE_STARS, REF_BONUS_INVITER, REF_BONUS_INVITED,
)
from database import init_db, close_db, async_session, User, Inventory, PromoCode
from format_utils import format_balance, format_balance_with_icon

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
            # Новый юзер, зашедший по реф-ссылке, получает старт + бонус приглашённого
            starting_balance = START_BALANCE + (REF_BONUS_INVITED if referred_by else 0)

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
        elif first_name and user.first_name != first_name:
            # Освежаем имя, если юзер его сменил в Telegram
            user.first_name = first_name
            await session.commit()
            await session.refresh(user)

            # Бонус пригласившему — начисляется автоматически, ровно один раз,
            # в момент первой регистрации приглашённого (а не при каждом /start)
            if referred_by:
                result_inviter = await session.execute(
                    select(User).where(User.telegram_id == referred_by)
                )
                inviter = result_inviter.scalar_one_or_none()
                if inviter:
                    inviter.balance += REF_BONUS_INVITER
                    await session.commit()
                    try:
                        await bot.send_message(
                            referred_by,
                            f"👥 По твоей реферальной ссылке зарегистрировался новый игрок!\n"
                            f"Тебе начислено <b>+{REF_BONUS_INVITER} 💎</b>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass  # юзер мог заблокировать бота — не критично

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

        text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Добро пожаловать в <b>CS2 Case Simulator</b> — фановый симулятор открытия кейсов "
            f"без реального вывода денег и скинов.\n"
            f"{bonus_note}\n"
            f"💰 Твой баланс: <b>{format_balance_with_icon(user.balance)}</b>\n\n"
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

    await callback.message.answer(
        f"👥 Твоя реферальная ссылка:\n<code>{link}</code>\n\n"
        f"За каждого друга, который зайдёт по ссылке, ты автоматически получишь "
        f"<b>+{REF_BONUS_INVITER} 💎</b>, а друг стартует с бонусом <b>+{REF_BONUS_INVITED} 💎</b>!",
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
    "/stats — общая статистика по всем юзерам в базе\n"
    "/give_crystals &lt;user_id&gt; &lt;amount&gt; — выдать 💎 Кристаллы по TG ID\n"
    "/give_vip &lt;user_id&gt; — выдать VIP-статус навсегда по TG ID\n"
    "/create_promo &lt;code&gt; &lt;reward_crystals&gt; &lt;activations&gt; — создать промокод на 💎\n"
    "/addpromo &lt;code&gt; &lt;type:value&gt; &lt;max_activations&gt; — создать промокод (case/skin)\n"
    "/user_info &lt;user_id&gt; — подробная информация о пользователе"
)


@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(ADMIN_MENU_TEXT, parse_mode="HTML")


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

        await message.answer(
            f"👤 <b>Пользователь {target_id}</b>\n\n"
            f"Username: @{user.username or '—'}\n"
            f"Баланс: {format_balance_with_icon(user.balance)}\n"
            f"VIP: {'✅ навсегда' if (user.is_vip and not user.vip_expires_at) else ('✅ до ' + user.vip_expires_at.strftime('%d.%m.%Y') if user.is_vip else '❌')}\n"
            f"Кейсов открыто: {user.total_cases_opened}\n"
            f"Предметов в инвентаре: {inv_count}\n"
            f"Реф. код: {user.ref_code}\n"
            f"Приглашён: {user.referred_by or '—'}",
            parse_mode="HTML"
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
