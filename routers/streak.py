# ============================================
# СПРИНТ 7: Ежедневный Стрик Входа (Daily Streak)
# ============================================
#
# GET  /api/streak/status  — состояние серии для текущего игрока (какой
#                             день следующий, забрано ли уже сегодня,
#                             превью всех 7 наград) — нужно фронту, чтобы
#                             отрисовать модалку ДО клейма, тем же паттерном,
#                             что и GET /api/wheel/status в routers/wheel.py.
# POST /api/streak/claim
#   { "telegram_id": 123456789 }
#
# Правила (см. ТЗ спринта 7):
#   - last_claim_date == Вчера  -> current_streak += 1
#   - last_claim_date <  Вчера  -> current_streak = 1  (пропуск дня — сброс)
#   - last_claim_date == Сегодня -> ошибка (уже забрано)
#   - Награды идут по циклу 1-7 (см. STREAK_REWARDS), после 7 дня начинается
#     заново, серия (для статистики/меги-бонуса) продолжает расти дальше.
#   - Мега-бонус: ровно в момент, когда НЕПРЕРЫВНАЯ серия (current_streak,
#     "без сброса") достигает 30 -> +25 Gold сверху обычной награды дня.
#     Это тот же самый счётчик User.daily_streak, который и обнуляется при
#     пропуске дня — то есть условие "без сброса" выполняется автоматически:
#     если стрик прервался, счётчик уже не 30, а 1, и бонус не сработает,
#     пока игрок заново не наберёт 30 дней подряд.
#
# ВАЖНО: это ЗАМЕНА старой реализации ежедневного бонуса из main.py
# (раньше — GET /api/daily-status, POST /api/daily-claim с другой таблицей
# наград). Тот код удалён из main.py, чтобы не было двух конкурирующих
# систем начисления на одних и тех же колонках User.daily_streak /
# User.last_daily_claim_at / User.daily_total_claims — эти три поля уже
# существуют в модели (см. database.py), новых колонок для стрика не
# потребовалось, авто-миграция (_auto_migrate_columns) их не тронет.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у остальных
# роутеров (cases.py, wheel.py) — подключается в main.py в самом конце
# файла, после того как уже определены CASES, roll_item,
# _maybe_update_top_drop, _award_xp, XP_DAILY_CLAIM и т.д.

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import main
from database import Inventory, User, async_session

router = APIRouter()

# ---- Кейс, выдаваемый на 2-й день. Как и у секторов Колеса удачи (см.
# routers/wheel.py), в этой кодовой базе нет отдельного понятия "невскрытый
# кейс в инвентаре" — награда "1x Кейс Revolution" реализована как
# немедленное вскрытие этого кейса на сервере, а в инвентарь сразу
# попадает выпавший предмет (тот же подход, что и для сектора "case"
# колеса удачи). ----
STREAK_CASE_KEY = "revolution_case"

# ---- Часы временного VIP-статуса за 6-й день ----
STREAK_VIP_HOURS = 6

# ---- Порог и награда меги-бонуса ----
MEGA_BONUS_STREAK_THRESHOLD = 30
MEGA_BONUS_GOLD = 25

# ---- ПРАВКИ В ТЗ №6: цикл наград расширен с 7 до 30 дней, награды
# нарастают по мере приближения к концу цикла — топовый приз (50 Gold)
# ровно на 30-й день, где он естественно совпадает с порогом мега-бонуса
# MEGA_BONUS_STREAK_THRESHOLD (тот даёт ещё +25 Gold СВЕРХУ этой награды,
# итого 75 Gold за 30-й день непрерывного стрика). VIP-дни (6ч/12ч/24ч)
# и кейсы расставлены равномерно по циклу, чтобы каждую неделю был
# "особый" день, а не только рост чисел. ----
STREAK_REWARDS = [
    {"day": 1, "type": "crystals", "amount": 5000},
    {"day": 2, "type": "crystals", "amount": 6000},
    {"day": 3, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 4, "type": "crystals", "amount": 8000},
    {"day": 5, "type": "gold", "amount": 2},
    {"day": 6, "type": "crystals", "amount": 10000},
    {"day": 7, "type": "crystals", "amount": 12000},
    {"day": 8, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 9, "type": "crystals", "amount": 14000},
    {"day": 10, "type": "gold", "amount": 3},
    {"day": 11, "type": "crystals", "amount": 16000},
    {"day": 12, "type": "crystals", "amount": 18000},
    {"day": 13, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 14, "type": "crystals", "amount": 20000},
    {"day": 15, "type": "vip", "hours": STREAK_VIP_HOURS},
    {"day": 16, "type": "crystals", "amount": 22000},
    {"day": 17, "type": "crystals", "amount": 24000},
    {"day": 18, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 19, "type": "crystals", "amount": 26000},
    {"day": 20, "type": "gold", "amount": 5},
    {"day": 21, "type": "crystals", "amount": 30000},
    {"day": 22, "type": "crystals", "amount": 32000},
    {"day": 23, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 24, "type": "crystals", "amount": 35000},
    {"day": 25, "type": "vip", "hours": STREAK_VIP_HOURS * 2},
    {"day": 26, "type": "crystals", "amount": 40000},
    {"day": 27, "type": "crystals", "amount": 45000},
    {"day": 28, "type": "case", "case_key": STREAK_CASE_KEY},
    {"day": 29, "type": "crystals", "amount": 50000},
    {"day": 30, "type": "gold", "amount": 50},
]
_REWARDS_BY_DAY = {r["day"]: r for r in STREAK_REWARDS}
_CYCLE_LENGTH = len(STREAK_REWARDS)  # 30


def _day_index(streak: int) -> int:
    """Переводит номер серии (растёт бесконечно) в день цикла 1-30."""
    return ((streak - 1) % _CYCLE_LENGTH) + 1 if streak > 0 else 1


def _seconds_until_next_claim(user: User) -> int:
    """Сколько секунд осталось до полуночи UTC (следующего календарного
    дня), если бонус уже забран сегодня — для таймера ЧЧ:ММ:СС на фронте.
    0, если бонус ещё не забран сегодня (доступен прямо сейчас). Claim
    привязан к КАЛЕНДАРНЫМ суткам UTC (см. модуль-докстринг), а не к
    скользящему окну 24ч, как у колеса удачи — поэтому считаем именно до
    полуночи, а не "last_claim + 24h"."""
    now = datetime.datetime.utcnow()
    today = now.date()
    last = user.last_daily_claim_at.date() if user.last_daily_claim_at else None
    if last != today:
        return 0
    tomorrow_midnight = datetime.datetime.combine(
        today + datetime.timedelta(days=1), datetime.time.min
    )
    remaining = tomorrow_midnight - now
    return max(0, int(remaining.total_seconds()))


async def _apply_streak_reward(session, user: User, day_index: int) -> dict:
    """Начисляет награду за day_index (1-7) прямо в открытой сессии/
    транзакции и возвращает данные для отображения на фронте. Ничего не
    коммитит сама — вызывается внутри уже открытой транзакции эндпоинта
    (тот же паттерн, что и _apply_wheel_reward в routers/wheel.py)."""
    reward_def = _REWARDS_BY_DAY[day_index]
    reward: dict = {"day": day_index, "type": reward_def["type"]}

    if reward_def["type"] == "crystals":
        amount = reward_def["amount"]
        user.balance = round((user.balance or 0.0) + amount, 2)
        reward["amount"] = amount
        reward["new_balance"] = user.balance

    elif reward_def["type"] == "gold":
        amount = reward_def["amount"]
        user.gold_balance = round((user.gold_balance or 0.0) + amount, 2)
        reward["amount"] = amount
        reward["new_gold_balance"] = user.gold_balance

    elif reward_def["type"] == "vip":
        now = datetime.datetime.utcnow()
        # Постоянный VIP (is_vip=True, vip_expires_at=None) НЕ трогаем —
        # выставлять ему временный expires_at было бы понижением статуса.
        if user.is_vip and user.vip_expires_at is None:
            reward["already_permanent_vip"] = True
        else:
            base = (
                user.vip_expires_at
                if (user.is_vip and user.vip_expires_at and user.vip_expires_at > now)
                else now
            )
            user.is_vip = True
            user.vip_expires_at = base + datetime.timedelta(hours=reward_def["hours"])
            reward["vip_expires_at"] = user.vip_expires_at.isoformat()
        reward["hours"] = reward_def["hours"]

    elif reward_def["type"] == "case":
        drop = main.roll_item(reward_def["case_key"])
        case_name = main.CASES[reward_def["case_key"]]["name"]
        item_record = Inventory(
            user_id=user.id,
            skin_name=drop["name"],
            skin_price=drop["price"],
            rarity=drop["rarity"],
            quality=drop["quality"],
            stattrak=drop["stattrak"],
            float_val=drop["float_val"],
            image_url=drop["image"],
            obtained_from_case=f"Ежедневный бонус ({case_name})",
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
        }
        reward["case_name"] = case_name

    return reward


@router.get("/api/streak/status")
async def streak_status(telegram_id: int):
    """Статус серии ежедневных наград + превью всех 7 дней (для интерфейса),
    тот же паттерн, что и GET /api/wheel/status."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        today = datetime.datetime.utcnow().date()
        last = user.last_daily_claim_at.date() if user.last_daily_claim_at else None
        claimed_today = last == today

        if claimed_today:
            upcoming_day = _day_index(user.daily_streak)          # уже выдан сегодня
        elif last == today - datetime.timedelta(days=1):
            upcoming_day = _day_index(user.daily_streak + 1)      # завтрашний день серии
        else:
            upcoming_day = 1                                       # серия сброшена / первый визит

        return {
            "streak": user.daily_streak,
            "total_claims": user.daily_total_claims or 0,
            "claimed_today": claimed_today,
            "current_day": upcoming_day,
            "rewards": STREAK_REWARDS,
            "cycle_length": _CYCLE_LENGTH,
            "mega_bonus_threshold": MEGA_BONUS_STREAK_THRESHOLD,
            "mega_bonus_gold": MEGA_BONUS_GOLD,
            # ПРАВКИ В ТЗ №6: таймер ЧЧ:ММ:СС до следующего клейма на фронте.
            "seconds_until_next_claim": _seconds_until_next_claim(user),
        }


class StreakClaimRequest(BaseModel):
    telegram_id: int


@router.post("/api/streak/claim")
async def streak_claim(req: StreakClaimRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        now = datetime.datetime.utcnow()
        today = now.date()
        last = user.last_daily_claim_at.date() if user.last_daily_claim_at else None

        if last == today:
            raise HTTPException(400, "Ежедневный бонус уже получен сегодня. Возвращайся завтра!")

        if last == today - datetime.timedelta(days=1):
            user.daily_streak += 1     # зашёл вчера и сегодня — серия продолжается
        else:
            user.daily_streak = 1      # первый визит или пропуск дня — серия с начала

        day_index = _day_index(user.daily_streak)
        reward = await _apply_streak_reward(session, user, day_index)
        user.last_daily_claim_at = now
        user.daily_total_claims = (user.daily_total_claims or 0) + 1

        # ---- Мега-бонус: ровно на 30-й день непрерывной серии ----
        mega_bonus_awarded = False
        if user.daily_streak == MEGA_BONUS_STREAK_THRESHOLD:
            user.gold_balance = round((user.gold_balance or 0.0) + MEGA_BONUS_GOLD, 2)
            mega_bonus_awarded = True

        xp_info = await main._award_xp(session, user, main.XP_DAILY_CLAIM)

        await session.commit()
        await session.refresh(user)

        response = {
            "success": True,
            "day": day_index,
            "streak": user.daily_streak,
            "total_claims": user.daily_total_claims,
            "new_balance": user.balance,
            "new_gold_balance": user.gold_balance,
            "reward": reward,
            "mega_bonus_awarded": mega_bonus_awarded,
            "xp": xp_info,
        }
        if mega_bonus_awarded:
            response["mega_bonus_gold"] = MEGA_BONUS_GOLD

        return response
