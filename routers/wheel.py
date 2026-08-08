# ============================================
# СПРИНТ 6: ЕЖЕДНЕВНОЕ КОЛЕСО УДАЧИ (DAILY WHEEL)
# ============================================
#
# GET  /api/wheel/status  — состояние колеса для текущего игрока (доступен
#                            ли бесплатный спин прямо сейчас, сколько платных
#                            попыток осталось сегодня, хватает ли Золота) —
#                            НЕ было явно в ТЗ, но нужно фронту, чтобы
#                            отрисовать кнопку ДО первого спина, тем же
#                            паттерном, что и GET /api/bonus-status и
#                            GET /api/daily-status в main.py.
# POST /api/wheel/spin
#   { "telegram_id": 123456789 }
#
# Правила (см. ТЗ спринта 6):
#   - Проверяем WheelSpin.last_free_spin. Если прошло >= 24 часов (или спина
#     ещё не было) — спин бесплатный.
#   - Иначе проверяем WheelSpin.paid_spins_today (< 3 в сутки) и списываем
#     5 Золота (User.gold_balance).
#   - 8 секторов с фиксированными весами (сумма = 100%).
#   - Ответ содержит ID выигрышного сектора и угол вращения в градусах —
#     начисление награды происходит на бэкенде СРАЗУ, до анимации на фронте.
#
# ВАЖНО про WheelSpin.paid_spins_today: "в сутки" считается по календарным
# UTC-суткам (WheelSpin.last_spin_reset_date), а не по скользящим 24 часам —
# та же семантика, что и у daily_streak/bonus в main.py, а не у самого
# last_free_spin (который, наоборот, использует ИМЕННО скользящее окно в 24
# часа, как явно сказано в ТЗ).
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у остальных
# роутеров — подключается в main.py в самом конце файла, после того как уже
# определены CASES, roll_item, _maybe_update_top_drop и т.д.

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sqlalchemy import select

import main
from database import Inventory, User, WheelSpin, async_session

router = APIRouter()

FREE_SPIN_COOLDOWN_HOURS = 24
MAX_PAID_SPINS_PER_DAY = 3
PAID_SPIN_GOLD_COST = 5

WHEEL_REVOLUTION_CASE_KEY = "revolution_case"
VIP_WHEEL_HOURS = 3

# ---- 8 секторов колеса, в порядке ID 1..8 (см. ТЗ) — тот же порядок и
# определяет расположение секторов по кругу на фронте (сектор 1 первый по
# часовой стрелке от 12 часов и т.д.), поэтому его нельзя менять без
# синхронной правки разметки/CSS колеса на фронтенде. ----
WHEEL_SECTORS = [
    {"id": 1, "type": "crystals", "amount": 1000, "weight": 30},
    {"id": 2, "type": "crystals", "amount": 5000, "weight": 25},
    {"id": 3, "type": "crystals", "amount": 15000, "weight": 15},
    {"id": 4, "type": "gold", "amount": 1, "weight": 12},
    {"id": 5, "type": "gold", "amount": 3, "weight": 8},
    {"id": 6, "type": "gold", "amount": 5, "weight": 4},
    {"id": 7, "type": "vip", "hours": VIP_WHEEL_HOURS, "weight": 4},
    {"id": 8, "type": "case", "case_key": WHEEL_REVOLUTION_CASE_KEY, "weight": 2},
]
_WEIGHT_TOTAL = sum(s["weight"] for s in WHEEL_SECTORS)  # == 100
_SECTOR_COUNT = len(WHEEL_SECTORS)  # 8
_SECTOR_ARC_DEGREES = 360.0 / _SECTOR_COUNT  # 45°

# Сколько полных оборотов "накручивает" колесо для визуального эффекта
# перед остановкой на нужном секторе — чисто фронтовая красота, на исход
# не влияет.
SPIN_FULL_TURNS = 5


class WheelSpinRequest(BaseModel):
    telegram_id: int


def _today_utc() -> datetime.date:
    return datetime.datetime.utcnow().date()


async def _get_or_create_wheel_state(session, user: User) -> WheelSpin:
    result = await session.execute(select(WheelSpin).where(WheelSpin.user_id == user.id).with_for_update())
    wheel = result.scalar_one_or_none()
    if not wheel:
        wheel = WheelSpin(user_id=user.id, last_free_spin=None, paid_spins_today=0, last_spin_reset_date=None)
        session.add(wheel)
        await session.flush()
    if wheel.last_spin_reset_date != _today_utc():
        wheel.paid_spins_today = 0
        wheel.last_spin_reset_date = _today_utc()
    return wheel


def _seconds_until_free_spin(wheel: WheelSpin) -> int:
    if not wheel.last_free_spin:
        return 0
    elapsed = datetime.datetime.utcnow() - wheel.last_free_spin
    remaining = datetime.timedelta(hours=FREE_SPIN_COOLDOWN_HOURS) - elapsed
    return max(0, int(remaining.total_seconds()))


def _pick_sector() -> dict:
    roll = main.random.uniform(0, _WEIGHT_TOTAL)
    cumulative = 0.0
    for sector in WHEEL_SECTORS:
        cumulative += sector["weight"]
        if roll <= cumulative:
            return sector
    return WHEEL_SECTORS[-1]


def _angle_for_sector(sector_id: int) -> float:
    """Итоговый угол поворота диска (градусы, по часовой стрелке), чтобы
    ЦЕНТР выигрышного сектора остановился ровно под неподвижной стрелкой
    наверху (0°/12 часов), плюс несколько полных оборотов для красоты
    анимации. Секторы на диске разложены по порядку ID 1..N по часовой
    стрелке начиная от 12 часов, поэтому центр сектора с индексом idx
    (0-based) исходно находится на угле idx*ARC + ARC/2."""
    idx = sector_id - 1
    sector_center = idx * _SECTOR_ARC_DEGREES + _SECTOR_ARC_DEGREES / 2
    snap = (360 - sector_center) % 360
    return SPIN_FULL_TURNS * 360 + snap


async def _apply_wheel_reward(session, user: User, sector: dict) -> dict:
    """Начисляет награду выигрышного сектора и возвращает описание для
    ответа API. Ничего не коммитит сама — вызывается внутри уже открытой
    транзакции эндпоинта."""
    reward: dict = {"type": sector["type"]}

    if sector["type"] == "crystals":
        amount = sector["amount"]
        user.balance = round((user.balance or 0.0) + amount, 2)
        reward["amount"] = amount
        reward["new_balance"] = user.balance

    elif sector["type"] == "gold":
        amount = sector["amount"]
        user.gold_balance = round((user.gold_balance or 0.0) + amount, 2)
        reward["amount"] = amount
        reward["new_gold_balance"] = user.gold_balance

    elif sector["type"] == "vip":
        now = datetime.datetime.utcnow()
        # Постоянный VIP (is_vip=True, vip_expires_at=None) НЕ трогаем —
        # выставлять ему временный expires_at было бы понижением статуса.
        if user.is_vip and user.vip_expires_at is None:
            reward["already_permanent_vip"] = True
        else:
            base = user.vip_expires_at if (user.is_vip and user.vip_expires_at and user.vip_expires_at > now) else now
            user.is_vip = True
            user.vip_expires_at = base + datetime.timedelta(hours=sector["hours"])
            reward["vip_expires_at"] = user.vip_expires_at.isoformat()
        reward["hours"] = sector["hours"]

    elif sector["type"] == "case":
        drop = main.roll_item(sector["case_key"])
        case_name = main.CASES[sector["case_key"]]["name"]
        item_record = Inventory(
            user_id=user.id,
            skin_name=drop["name"],
            skin_price=drop["price"],
            rarity=drop["rarity"],
            quality=drop["quality"],
            stattrak=drop["stattrak"],
            float_val=drop["float_val"],
            image_url=drop["image"],
            obtained_from_case=f"Колесо удачи ({case_name})",
        )
        session.add(item_record)
        main._maybe_update_top_drop(user, drop)
        await session.flush()
        await session.refresh(item_record)
        reward["item"] = {
            "id": item_record.id,
            "name": drop["name"],
            "rarity": drop["rarity"],
            "quality": drop["quality"],
            "quality_name": drop["quality_name"],
            "price": drop["price"],
            "image": drop["image"],
            "stattrak": drop["stattrak"],
            "float_val": drop["float_val"],
        }

    return reward


@router.get("/api/wheel/status")
async def wheel_status(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        wheel = await _get_or_create_wheel_state(session, user)
        await session.commit()

        seconds_left = _seconds_until_free_spin(wheel)
        return {
            "free_spin_available": seconds_left <= 0,
            "seconds_until_free_spin": seconds_left,
            "paid_spins_today": wheel.paid_spins_today,
            "paid_spins_left": max(0, MAX_PAID_SPINS_PER_DAY - wheel.paid_spins_today),
            "paid_spin_gold_cost": PAID_SPIN_GOLD_COST,
            "gold_balance": user.gold_balance,
            "sectors": WHEEL_SECTORS,
        }


@router.post("/api/wheel/spin")
async def wheel_spin(req: WheelSpinRequest):
    async with async_session() as session:
        result_user = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id).with_for_update()
        )
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        wheel = await _get_or_create_wheel_state(session, user)

        seconds_left = _seconds_until_free_spin(wheel)
        is_free = seconds_left <= 0

        if not is_free:
            if wheel.paid_spins_today >= MAX_PAID_SPINS_PER_DAY:
                raise HTTPException(
                    429,
                    f"Бесплатный спин будет доступен через {seconds_left} сек., "
                    f"платные попытки на сегодня закончились ({MAX_PAID_SPINS_PER_DAY}/день)",
                )
            if (user.gold_balance or 0.0) < PAID_SPIN_GOLD_COST:
                raise HTTPException(400, "Недостаточно Золота для платного спина")

            user.gold_balance = round(user.gold_balance - PAID_SPIN_GOLD_COST, 2)
            wheel.paid_spins_today += 1
        else:
            wheel.last_free_spin = datetime.datetime.utcnow()

        sector = _pick_sector()
        angle_degrees = _angle_for_sector(sector["id"])
        reward = await _apply_wheel_reward(session, user, sector)

        await session.commit()
        await session.refresh(user)
        await session.refresh(wheel)

        return {
            "success": True,
            "is_free": is_free,
            "sector_id": sector["id"],
            "angle_degrees": angle_degrees,
            "reward": reward,
            "new_balance": user.balance,
            "new_gold_balance": user.gold_balance,
            "paid_spins_left": max(0, MAX_PAID_SPINS_PER_DAY - wheel.paid_spins_today),
            "seconds_until_free_spin": _seconds_until_free_spin(wheel),
        }
