# ============================================
# СПРИНТ 3: Открытие кейсов и мульти-спин
# ============================================
#
# POST /api/cases/open — { "case_id": "revolution", "count": 1..10 }
#
#   1. Проверяет crystals_balance (User.balance) >= price * count.
#   2. Списывает баланс (+ реферальная комиссия, как и у остальных трат).
#   3. Генерирует массив из N предметов через generate_item_drop
#      (алиас main.roll_item — см. main.py, конец блока "1. ЭКОНОМИКА").
#   4. Сохраняет каждый предмет в UserInventory (= таблица Inventory).
#   5. Начисляет XP: count * 10, начисляет очки турнира: count * 10
#      (TournamentScore.activity_points за текущую ISO-неделю).
#   6. Возвращает массив предметов с конвертацией цен (RUB / UAH / USD).
#
# ВАЖНО про импорт `main`: этот модуль подключается в main.py через
# `app.include_router(...)` В САМОМ КОНЦЕ файла (после того, как уже
# определены CASES, roll_item/generate_item_drop, calculate_case_price,
# _award_xp, _credit_referral_commission, _maybe_update_top_drop и т.д.).
# Мы обращаемся к этим именам как main.<имя> ТОЛЬКО внутри обработчика
# запроса (в момент реального HTTP-запроса) — на этот момент модуль main
# уже полностью загружен, поэтому циклический импорт main -> routers.cases
# -> main не приводит к ошибке.

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import currency
import main
from database import async_session, Inventory, TournamentScore, User

router = APIRouter()

# Количество открытий за один запрос — от 1 до 10 включительно.
ALLOWED_MULTI_OPEN_COUNTS = set(range(1, 11))

XP_PER_CASE_SPRINT3 = 10          # начисление XP за открытие: count * 10
TOURNAMENT_POINTS_PER_CASE = 10   # очки еженедельного турнира: count * 10


class CaseOpenRequest(BaseModel):
    telegram_id: int
    case_id: str
    count: int = 1


def _convert_price(amount_rub: float) -> dict:
    """Конвертирует сумму в 💎/₽ в отображаемые RUB/UAH/USD — сама сумма,
    которая реально списывается/начисляется на сервере, всегда в ₽
    (см. currency.py), это только представление для фронта."""
    return {
        "RUB": round(amount_rub, 2),
        "USD": round(currency.rub_to(amount_rub, "USD"), 2),
        "UAH": round(currency.rub_to(amount_rub, "UAH"), 2),
    }


def _current_week_identifier(now: Optional[datetime.datetime] = None) -> str:
    """ISO-неделя вида '2026-W32' — тот же формат, что и в докстринге
    database.TournamentScore.week_identifier."""
    now = now or datetime.datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def _add_tournament_points(session, user: User, points: int) -> int:
    """Начисляет очки еженедельного турнира активности за ТЕКУЩУЮ
    ISO-неделю (создаёт запись TournamentScore, если это первое очко
    пользователя на этой неделе). Ничего не коммитит сама — вызывается
    внутри уже открытой транзакции эндпоинта, вместе со списанием баланса
    и начислением XP. Возвращает итоговую сумму очков за неделю."""
    if points <= 0:
        return 0

    week = _current_week_identifier()
    result = await session.execute(
        select(TournamentScore).where(
            TournamentScore.user_id == user.id,
            TournamentScore.week_identifier == week,
        )
    )
    score = result.scalar_one_or_none()
    if not score:
        score = TournamentScore(user_id=user.id, week_identifier=week, activity_points=0)
        session.add(score)

    score.activity_points = (score.activity_points or 0) + points
    return score.activity_points


@router.post("/api/cases/open")
async def open_case_multi(req: CaseOpenRequest):
    """Открытие 1-10 экземпляров одного кейса за один запрос (мульти-спин)."""
    if req.case_id not in main.CASES:
        raise HTTPException(404, "Кейс не найден")

    if req.count not in ALLOWED_MULTI_OPEN_COUNTS:
        raise HTTPException(400, "count должен быть от 1 до 10")

    case_price = main.calculate_case_price(req.case_id)
    total_price = case_price * req.count

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if user.balance < total_price:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        # ---- Списание баланса ----
        user.balance -= total_price
        main._track_wagered(user, total_price)
        user.total_cases_opened += req.count
        user.favorite_case = main.CASES[req.case_id]["name"]

        # ---- Генерация N дропов + сохранение в инвентарь ----
        drops: list[dict] = []
        item_records: list[Inventory] = []
        for _ in range(req.count):
            drop = main.generate_item_drop(req.case_id)
            item_record = Inventory(
                user_id=user.id,
                skin_name=drop["name"],
                skin_price=drop["price"],
                rarity=drop["rarity"],
                quality=drop["quality"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                image_url=drop["image"],
                obtained_from_case=main.CASES[req.case_id]["name"],
            )
            session.add(item_record)
            drops.append(drop)
            item_records.append(item_record)
            main._maybe_update_top_drop(user, drop)

        # ПРАВКИ В ТЗ №13: реферальная комиссия с кейсов — по совокупному
        # исходу всего мульти-спина за этот запрос (total_price против
        # суммарной цены всех выпавших скинов), а не по факту самой траты.
        drops_total_value = round(sum(d.get("price", 0) or 0 for d in drops), 2)
        await main._credit_referral_round_outcome(session, user, total_price, drops_total_value, source="case")

        # ---- XP + очки турнира ----
        xp_gain = req.count * XP_PER_CASE_SPRINT3
        xp_info = await main._award_xp(session, user, xp_gain)

        tournament_points_gained = req.count * TOURNAMENT_POINTS_PER_CASE
        tournament_points_total = await _add_tournament_points(
            session, user, tournament_points_gained
        )

        # ПРАВКИ В ТЗ №12, п.4: моментальный автозачёт ежедневных заданий
        # Battle Pass (напр. "Открой 1/3/5 кейсов") прямо в момент открытия
        # кейса — счётчик user.total_cases_opened уже обновлён выше, так
        # что если условие задания выполнилось именно сейчас, XP пропуска
        # начисляется тут же, в той же транзакции, без ожидания, пока
        # игрок сам откроет вкладку "Задания". Ленивый импорт — см.
        # docstring routers.pass_.sync_daily_tasks про порядок подключения
        # роутеров в main.py.
        from routers.pass_ import sync_daily_tasks
        await sync_daily_tasks(session, user)

        await session.commit()
        for item_record in item_records:
            await session.refresh(item_record)
        await session.refresh(user)

        # ---- Сборка ответа: массив предметов с конвертацией цен ----
        items_payload = [
            {
                "id": item_records[i].id,
                "name": drops[i]["name"],
                "rarity": drops[i]["rarity"],
                "image": drops[i]["image"],
                "quality": drops[i]["quality"],
                "quality_name": drops[i]["quality_name"],
                "price": _convert_price(drops[i]["price"]),
                "float_val": drops[i]["float_val"],
                "stattrak": drops[i]["stattrak"],
            }
            for i in range(req.count)
        ]

        return {
            "success": True,
            "case_id": req.case_id,
            "count": req.count,
            "items": items_payload,
            "case_price": _convert_price(case_price),
            "total_price": _convert_price(total_price),
            "new_balance": _convert_price(user.balance),
            "xp": xp_info,
            "tournament_points_gained": tournament_points_gained,
            "tournament_points_total": tournament_points_total,
        }
