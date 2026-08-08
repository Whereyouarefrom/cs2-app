# ============================================
# СПРИНТ 5: КОНТРАКТЫ ОБМЕНА (TRADE-UP CONTRACTS)
# ============================================
#
# POST /api/contracts/craft
#   {
#     "telegram_id": 123456789,
#     "inventory_item_ids": [101, 102, ..., 110]   # РОВНО 10 ID предметов (Inventory.id)
#   }
#
# Правила (см. ТЗ спринта 5):
#   - Ровно 10 предметов, все ОДНОЙ редкости.
#   - avg_price = sum(prices) / 10.
#   - Результат — 1 предмет на 1 ранг редкости выше, цена ~ avg_price * 1.25.
#   - 10 исходных предметов сгорают безвозвратно.
#   - Награда: +25 XP, +25 очков турнира текущей недели.
#
# Отличие от уже существующего /api/craft (main.py, "Крафт", 5 предметов):
# тот эндпоинт даёт игроку ВЫБРАТЬ конкретный целевой предмет из каталога
# следующей редкости за отдельную плату в Кристаллах. Контракт обмена —
# другая механика: игрок НЕ выбирает результат (он подбирается автоматически
# по цене), исходных предметов нужно вдвое больше (10 вместо 5) и никакой
# отдельной платы в Кристаллах не берётся — "ценой" служат сами 10 скинов.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и в routers/cases.py
# и routers/upgrader.py — этот роутер подключается в main.py через
# app.include_router(...) в САМОМ КОНЦЕ файла, после того как уже определены
# RARITY_ORDER, _pick_item_for_price, _instance_from_registry_item,
# _maybe_update_top_drop, _award_xp и т.д. Обращаемся к ним как main.<имя>
# ТОЛЬКО внутри обработчика запроса — поэтому цикличный импорт
# main -> routers.contracts -> main безопасен.

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sqlalchemy import select

import main
from database import Inventory, TournamentScore, User, async_session

router = APIRouter()

CONTRACT_ITEMS_REQUIRED = 10
CONTRACT_PRICE_MULTIPLIER = 1.25
CONTRACT_XP = 25
CONTRACT_TOURNAMENT_POINTS = 25


class ContractCraftRequest(BaseModel):
    telegram_id: int
    inventory_item_ids: list[int]


def _current_week_identifier(now: Optional[datetime.datetime] = None) -> str:
    """ISO-неделя вида '2026-W32' — тот же формат, что и в
    database.TournamentScore.week_identifier / routers/upgrader.py."""
    now = now or datetime.datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def _get_or_create_tournament_score(session, user: User) -> TournamentScore:
    week = _current_week_identifier()
    result = await session.execute(
        select(TournamentScore).where(
            TournamentScore.user_id == user.id,
            TournamentScore.week_identifier == week,
        )
    )
    score = result.scalar_one_or_none()
    if not score:
        score = TournamentScore(
            user_id=user.id, week_identifier=week, activity_points=0, best_upgrade_mult=0.0
        )
        session.add(score)
    return score


@router.post("/api/contracts/craft")
async def contracts_craft(req: ContractCraftRequest):
    ids = req.inventory_item_ids or []

    if len(ids) != CONTRACT_ITEMS_REQUIRED:
        raise HTTPException(400, f"Нужно ровно {CONTRACT_ITEMS_REQUIRED} предметов для контракта обмена")
    if len(set(ids)) != CONTRACT_ITEMS_REQUIRED:
        raise HTTPException(400, "Предметы не должны повторяться")

    async with async_session() as session:
        result_user = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id).with_for_update()
        )
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_items = await session.execute(
            select(Inventory)
            .where(Inventory.id.in_(ids), Inventory.user_id == user.id)
            .with_for_update()
        )
        source_items = list(result_items.scalars().all())
        if len(source_items) != CONTRACT_ITEMS_REQUIRED:
            raise HTTPException(404, "Один или несколько предметов не найдены в твоём инвентаре")

        # Ни один из заложенных предметов не должен быть выставлен на
        # P2P-маркет — иначе можно было бы "сжечь" чужой лот, который
        # покупатель в этот момент пытается купить.
        if any(item.is_on_market for item in source_items):
            raise HTTPException(400, "Нельзя использовать в контракте предметы, выставленные на продажу")

        rarities = {i.rarity for i in source_items}
        if len(rarities) != 1:
            raise HTTPException(400, "Все 10 предметов должны быть одной редкости")
        source_rarity = rarities.pop()

        target_rarity = main._next_craft_rarity(source_rarity)
        if target_rarity is None:
            raise HTTPException(400, "Эта редкость уже максимальная — контракт обмена дальше недоступен")

        avg_price = sum(i.skin_price for i in source_items) / CONTRACT_ITEMS_REQUIRED
        target_price = round(avg_price * CONTRACT_PRICE_MULTIPLIER, 2)

        # Подбираем реальный предмет нужной (следующей) редкости, чья цена
        # ближе всего к target_price — та же логика, что и в Апгрейдере
        # (main._pick_item_for_price), но пул сужаем строго до target_rarity,
        # чтобы результат контракта гарантированно был на ранг выше исходных.
        candidates = main.items_data.ITEMS_BY_RARITY.get(target_rarity) or []
        if not candidates:
            raise HTTPException(400, "В каталоге нет предметов следующей редкости — попробуй позже")

        target_log = main.math.log(max(target_price, 1.0))

        def _log_distance(it: dict) -> float:
            price = main.get_base_price_rub(it["name"], it["rarity"])
            return abs(main.math.log(max(price, 0.01)) - target_log)

        ranked = sorted(candidates, key=_log_distance)
        pool = ranked[:12] or ranked
        chosen_entry = main.random.choice(pool)

        for item in source_items:
            await session.delete(item)

        won_instance = main._instance_from_registry_item(chosen_entry, target_price)
        new_item = Inventory(
            user_id=user.id,
            skin_name=won_instance["name"],
            skin_price=won_instance["price"],
            rarity=won_instance["rarity"],
            quality=won_instance["quality"],
            stattrak=won_instance["stattrak"],
            float_val=won_instance["float_val"],
            image_url=won_instance["image"],
            obtained_from_case="Контракт обмена",
        )
        session.add(new_item)
        main._maybe_update_top_drop(user, won_instance)

        # ПРАВКИ В ТЗ №13: реферальная комиссия с контракта обмена — staked
        # это суммарная цена всех 10 сожжённых предметов, returned — цена
        # полученного предмета следующей редкости. Почти всегда staked >
        # returned (10 предметов сгорают ради 1), поэтому обычно списывается
        # как проигрыш; если когда-либо returned окажется больше — как выигрыш.
        staked_value = sum(i.skin_price for i in source_items)
        await main._credit_referral_round_outcome(session, user, staked_value, target_price, source="contract")

        xp_info = await main._award_xp(session, user, CONTRACT_XP)

        score = await _get_or_create_tournament_score(session, user)
        score.activity_points = (score.activity_points or 0) + CONTRACT_TOURNAMENT_POINTS

        await session.commit()
        await session.refresh(new_item)
        await session.refresh(user)

        return {
            "success": True,
            "source_rarity": source_rarity,
            "target_rarity": target_rarity,
            "avg_price": round(avg_price, 2),
            "target_price": target_price,
            "item": {
                "id": new_item.id,
                "name": won_instance["name"],
                "rarity": won_instance["rarity"],
                "quality": won_instance["quality"],
                "quality_name": won_instance["quality_name"],
                "price": won_instance["price"],
                "image": won_instance["image"],
                "stattrak": won_instance["stattrak"],
                "float_val": won_instance["float_val"],
            },
            "xp": xp_info,
            "tournament_points_total": score.activity_points,
            "new_balance": user.balance,
        }
