# ============================================
# СПРИНТ 5: P2P МАРКЕТПЛЕЙС
# ============================================
#
# POST /api/market/list   — выставить предмет из своего инвентаря на продажу
# GET  /api/market/items  — каталог предметов на маркете (сортировка/фильтры)
# POST /api/market/buy    — купить предмет с маркета
# POST /api/market/cancel — снять свой предмет с продажи (не было явно в ТЗ,
#                            но без этого выставленный предмет нельзя вернуть
#                            в инвентарь — добавлено как естественное
#                            дополнение к list/buy)
#
# Цена предмета на маркете (Inventory.market_price) — ОТДЕЛЬНОЕ поле от
# Inventory.skin_price. skin_price — это "справочная" стоимость предмета
# (из Steam Market/fallback, см. main.get_base_price_rub), она нигде не
# меняется при выставлении на продажу. market_price — то, что реально
# назначил продавец и что реально спишется с покупателя.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и в остальных
# роутерах спринтов — подключается в main.py в самом конце файла.

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sqlalchemy import select

import main
from database import Inventory, User, async_session

router = APIRouter()

MARKET_COMMISSION_PERCENT = 0.05
MIN_LISTING_PRICE = 1.0

SORT_FIELDS = {"price", "rarity"}
RARITY_RANK = {name: idx for idx, name in enumerate(main.RARITY_ORDER)} if hasattr(main, "RARITY_ORDER") else {}


class MarketListRequest(BaseModel):
    telegram_id: int
    inventory_id: int
    price: float


class MarketBuyRequest(BaseModel):
    telegram_id: int
    inventory_id: int


class MarketCancelRequest(BaseModel):
    telegram_id: int
    inventory_id: int


def _serialize_listing(item: Inventory) -> dict:
    return {
        "id": item.id,
        "name": item.skin_name,
        "rarity": item.rarity,
        "quality": item.quality,
        "quality_name": main.QUALITY_FULL_NAME.get(item.quality, ""),
        "stattrak": item.stattrak,
        "float_val": item.float_val,
        "image": item.image_url,
        "price": item.market_price,
        "reference_price": item.skin_price,
        "listed_at": item.market_listed_at.isoformat() if item.market_listed_at else None,
        "seller_id": item.user_id,
    }


@router.post("/api/market/list")
async def market_list(req: MarketListRequest):
    price = round(req.price or 0.0, 2)
    if price < MIN_LISTING_PRICE:
        raise HTTPException(400, f"Минимальная цена лота — {MIN_LISTING_PRICE} 💎")

    async with async_session() as session:
        result_user = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_item = await session.execute(
            select(Inventory)
            .where(Inventory.id == req.inventory_id, Inventory.user_id == user.id)
            .with_for_update()
        )
        item = result_item.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в твоём инвентаре")
        if item.is_on_market:
            raise HTTPException(400, "Предмет уже выставлен на продажу")

        item.is_on_market = True
        item.market_price = price
        item.market_listed_at = datetime.datetime.utcnow()

        await session.commit()
        await session.refresh(item)

        return {"success": True, "listing": _serialize_listing(item)}


@router.post("/api/market/cancel")
async def market_cancel(req: MarketCancelRequest):
    async with async_session() as session:
        result_user = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_item = await session.execute(
            select(Inventory)
            .where(Inventory.id == req.inventory_id, Inventory.user_id == user.id)
            .with_for_update()
        )
        item = result_item.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в твоём инвентаре")
        if not item.is_on_market:
            raise HTTPException(400, "Предмет не выставлен на продажу")

        item.is_on_market = False
        item.market_price = None
        item.market_listed_at = None

        await session.commit()
        return {"success": True}


@router.get("/api/market/items")
async def market_items(
    sort_by: str = "price",
    order: str = "asc",
    stattrak: Optional[bool] = None,
    rarity: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
):
    if sort_by not in SORT_FIELDS:
        raise HTTPException(400, f"sort_by должен быть одним из: {', '.join(sorted(SORT_FIELDS))}")
    if order not in ("asc", "desc"):
        raise HTTPException(400, "order должен быть 'asc' или 'desc'")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    async with async_session() as session:
        query = select(Inventory).where(Inventory.is_on_market.is_(True))
        if stattrak is not None:
            query = query.where(Inventory.stattrak.is_(stattrak))
        if rarity:
            query = query.where(Inventory.rarity == rarity)
        if min_price is not None:
            query = query.where(Inventory.market_price >= min_price)
        if max_price is not None:
            query = query.where(Inventory.market_price <= max_price)

        result = await session.execute(query)
        items = list(result.scalars().all())

        if sort_by == "price":
            items.sort(key=lambda i: (i.market_price is None, i.market_price or 0.0))
        else:  # sort_by == "rarity"
            items.sort(key=lambda i: RARITY_RANK.get(i.rarity, -1))

        if order == "desc":
            items.reverse()

        total = len(items)
        page = items[offset: offset + limit]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_serialize_listing(i) for i in page],
        }


@router.post("/api/market/buy")
async def market_buy(req: MarketBuyRequest):
    async with async_session() as session:
        result_buyer = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id).with_for_update()
        )
        buyer = result_buyer.scalar_one_or_none()
        if not buyer:
            raise HTTPException(404, "Пользователь не найден")

        result_item = await session.execute(
            select(Inventory).where(Inventory.id == req.inventory_id).with_for_update()
        )
        item = result_item.scalar_one_or_none()
        if not item or not item.is_on_market:
            raise HTTPException(404, "Лот не найден или уже снят с продажи")
        if item.user_id == buyer.id:
            raise HTTPException(400, "Нельзя купить собственный лот")

        price = item.market_price or 0.0
        if buyer.balance < price:
            raise HTTPException(400, "Недостаточно 💎 для покупки")

        result_seller = await session.execute(
            select(User).where(User.id == item.user_id).with_for_update()
        )
        seller = result_seller.scalar_one_or_none()
        if not seller:
            raise HTTPException(404, "Продавец лота не найден")

        commission = round(price * MARKET_COMMISSION_PERCENT, 2)
        seller_payout = round(price - commission, 2)

        buyer.balance = round(buyer.balance - price, 2)
        seller.balance = round(seller.balance + seller_payout, 2)

        # Тот же паттерн пассивной реферальной комиссии, что и при
        # открытии кейсов/крафте (см. main._credit_referral_commission) —
        # трата покупателя на маркете тоже считается "тратой" для его
        # реферера.
        await main._credit_referral_commission(session, buyer, price)

        item.user_id = buyer.id
        item.is_on_market = False
        item.market_price = None
        item.market_listed_at = None
        item.obtained_from_case = "P2P Маркет"
        item.obtained_at = datetime.datetime.utcnow()

        await session.commit()
        await session.refresh(item)
        await session.refresh(buyer)

        return {
            "success": True,
            "item": _serialize_listing(item) | {"price": price},
            "commission": commission,
            "seller_payout": seller_payout,
            "new_balance": buyer.balance,
        }
