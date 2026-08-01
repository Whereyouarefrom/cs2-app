# ============================================
# CS2 Case Simulator — Telegram Bot (Aiogram 3)
# ============================================

import asyncio
import logging
import uuid
import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, LabeledPrice, PreCheckoutQuery
)
from sqlalchemy import select, func

from config import BOT_TOKEN, ADMIN_ID, WEBAPP_URL, START_BALANCE, VIP_PRICE_STARS_MONTH, VIP_PRICE_STARS_FOREVER
from database import init_db, async_session, User, Inventory, PromoCode

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------
async def get_or_create_user(telegram_id: int, username: str | None, referred_by: int | None = None) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                balance=START_BALANCE,
                ref_code=str(uuid.uuid4())[:8],
                referred_by=referred_by,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Бонус пригласившему
            if referred_by:
                result_inviter = await session.execute(
                    select(User).where(User.telegram_id == referred_by)
                )
                inviter = result_inviter.scalar_one_or_none()
                if inviter:
                    inviter.balance += 2500
                    await session.commit()

        return user


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="⭐ Купить VIP (без рекламы)", callback_data="buy_vip")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="ref_link")],
    ])


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ---------------------------------------------------
# /start
# ---------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: Message):
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
        referred_by=referred_by,
    )

    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Добро пожаловать в CS2 Case Simulator — фановый симулятор открытия кейсов "
        f"без реального вывода денег и скинов.\n\n"
        f"💰 Твой стартовый баланс: <b>${user.balance:.0f}</b>\n\n"
        f"Жми кнопку ниже, чтобы начать открывать кейсы 👇"
    )

    await message.answer(text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


# ---------------------------------------------------
# Реферальная ссылка
# ---------------------------------------------------
@dp.callback_query(F.data == "ref_link")
async def send_ref_link(callback):
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{callback.from_user.id}"

    await callback.message.answer(
        f"👥 Твоя реферальная ссылка:\n<code>{link}</code>\n\n"
        f"За каждого друга получаешь <b>+$2500</b>, а друг — <b>+$1000</b> на старт!",
        parse_mode="HTML"
    )
    await callback.answer()


# ---------------------------------------------------
# Оплата VIP-статуса через Telegram Stars
# ---------------------------------------------------
@dp.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📅 VIP на 30 дней — {VIP_PRICE_STARS_MONTH} ⭐", callback_data="vip_month")],
        [InlineKeyboardButton(text=f"♾️ VIP навсегда — {VIP_PRICE_STARS_FOREVER} ⭐", callback_data="vip_forever")],
    ])
    await callback.message.answer(
        "⭐ <b>VIP-статус</b>\n\n"
        "Что даёт VIP:\n"
        "— Полное отключение рекламы\n"
        "— Эксклюзивная тема интерфейса\n"
        "— Ускоренная анимация открытия кейсов\n\n"
        "<i>VIP не влияет на шансы выпадения предметов — только на удобство.</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["vip_month", "vip_forever"]))
async def send_vip_invoice(callback):
    is_forever = callback.data == "vip_forever"
    price = VIP_PRICE_STARS_FOREVER if is_forever else VIP_PRICE_STARS_MONTH
    title = "VIP навсегда" if is_forever else "VIP на 30 дней"

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description="Отключение рекламы + косметические бонусы. Не влияет на игровые шансы.",
        payload=f"vip_{'forever' if is_forever else 'month'}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=title, amount=price)],
        provider_token="",  # для Stars provider_token не нужен
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    is_forever = payload == "vip_forever"

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.is_vip = True
            if not is_forever:
                user.vip_expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            else:
                user.vip_expires_at = None
            await session.commit()

    await message.answer("✅ Оплата прошла успешно! VIP-статус активирован.")


# ============================================
# АДМИН-КОМАНДЫ
# ============================================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🔧 <b>Админ-панель</b>\n\n"
        "/stats — статистика проекта\n"
        "/give_balance &lt;telegram_id&gt; &lt;amount&gt; — выдать баланс\n"
        "/addpromo &lt;code&gt; &lt;type:value&gt; &lt;max_activations&gt; — создать промокод\n"
        "/user_info &lt;telegram_id&gt; — информация о пользователе",
        parse_mode="HTML"
    )


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

        text = (
            f"📊 <b>Статистика проекта</b>\n\n"
            f"👥 Пользователей: <b>{total_users}</b>\n"
            f"⭐ VIP-пользователей: <b>{vip_users}</b>\n"
            f"📦 Всего открыто кейсов: <b>{total_cases}</b>\n"
            f"🎒 Предметов в инвентарях: <b>{total_items}</b>\n"
            f"💰 Суммарный виртуальный баланс всех юзеров: <b>${total_balance:,.0f}</b>\n"
        )
        await message.answer(text, parse_mode="HTML")


@dp.message(Command("give_balance"))
async def cmd_give_balance(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give_balance <telegram_id> <amount>")
        return

    try:
        target_id = int(args[1])
        amount = float(args[2])
    except ValueError:
        await message.answer("❌ Некорректные параметры")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer(f"❌ Пользователь {target_id} не найден")
            return

        user.balance += amount
        await session.commit()

        await message.answer(
            f"✅ Пользователю <code>{target_id}</code> начислено <b>${amount:,.0f}</b>\n"
            f"Новый баланс: <b>${user.balance:,.0f}</b>",
            parse_mode="HTML"
        )


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
            f"Баланс: ${user.balance:,.0f}\n"
            f"VIP: {'✅' if user.is_vip else '❌'}\n"
            f"Кейсов открыто: {user.total_cases_opened}\n"
            f"Предметов в инвентаре: {inv_count}\n"
            f"Реф. код: {user.ref_code}\n"
            f"Приглашён: {user.referred_by or '—'}",
            parse_mode="HTML"
        )


# ---------------------------------------------------
# Точка входа
# ---------------------------------------------------
async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
