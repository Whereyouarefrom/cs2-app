# ============================================
# СПРИНТ 9.5: Лимитированные промокоды — строгая 1 активация на 1 user_id
# ============================================
#
# POST /api/promocodes/activate
#   { "telegram_id": 123456789, "code": "SUMMER2026" }
#
# Отличие от уже существующего /api/promo (main.py, блок "6"): тот
# endpoint проверяет только общий лимит promo.used_count < max_activations
# (можно активировать один и тот же код второй раз тем же юзером, пока не
# исчерпан общий лимит). Этот — строго 1 активация промокода на 1 user_id,
# используя таблицу PromoActivation (UniqueConstraint(user_id, promo_id) в
# database.py). Старый /api/promo оставлен как есть для обратной
# совместимости с уже задеплоенным фронтендом.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у routers/cases.py,
# routers/upgrader.py и т.д. — подключается в main.py в самом низу файла,
# после того как уже определены CASES, roll_item, _maybe_update_top_drop,
# QUALITY_FLOAT_RANGE. Обращаемся к ним как main.<имя> только ВНУТРИ
# обработчика запроса, поэтому цикличный импорт безопасен.

from __future__ import annotations

import datetime
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import main
from database import Inventory, PromoActivation, PromoCode, User, async_session
from format_utils import format_balance_with_icon

router = APIRouter()


class PromoActivateRequest(BaseModel):
    telegram_id: int
    code: str


@router.post("/api/promocodes/activate")
async def activate_promocode(req: PromoActivateRequest):
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(400, "Промокод не указан")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_promo = await session.execute(select(PromoCode).where(PromoCode.code == code))
        promo = result_promo.scalar_one_or_none()
        if not promo:
            raise HTTPException(404, "Промокод не найден")

        if promo.expires_at and promo.expires_at < datetime.datetime.utcnow():
            raise HTTPException(400, "Промокод просрочен")

        if promo.used_count >= promo.max_activations:
            raise HTTPException(400, "Лимит активаций промокода исчерпан")

        # ---- СТРОГО 1 активация промокода на 1 user_id ----
        result_activation = await session.execute(
            select(PromoActivation).where(
                PromoActivation.user_id == user.id,
                PromoActivation.promo_id == promo.id,
            )
        )
        if result_activation.scalar_one_or_none():
            raise HTTPException(400, "Этот промокод уже был активирован твоим аккаунтом")

        message = ""
        reward_payload: dict = {}

        if promo.reward_type == "balance":
            amount = float(promo.reward_value)
            user.balance = round(user.balance + amount, 2)
            message = f"Начислено {format_balance_with_icon(amount)} на баланс"
            reward_payload = {"type": "balance", "amount": amount}

        elif promo.reward_type == "gold":
            amount = float(promo.reward_value)
            user.gold_balance = round((user.gold_balance or 0.0) + amount, 2)
            message = f"Начислено {amount:g} 🏆 Золота"
            reward_payload = {"type": "gold", "amount": amount}

        elif promo.reward_type == "case":
            case_key = promo.reward_value
            if case_key not in main.CASES:
                raise HTTPException(400, "Кейс в промокоде не найден")
            drop = main.roll_item(case_key)
            item_record = Inventory(
                user_id=user.id,
                skin_name=drop["name"],
                skin_price=drop["price"],
                rarity=drop["rarity"],
                quality=drop["quality"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                image_url=drop["image"],
                obtained_from_case=main.CASES[case_key]["name"] + " (промо)",
            )
            session.add(item_record)
            main._maybe_update_top_drop(user, drop)
            message = f"Открыт бесплатный кейс: {main.CASES[case_key]['name']}"
            reward_payload = {"type": "case", "case_key": case_key, "item_name": drop["name"]}

        elif promo.reward_type == "skin":
            parts = promo.reward_value.split("|")
            name, rarity, price = parts[0], parts[1], float(parts[2])
            item_record = Inventory(
                user_id=user.id,
                skin_name=name,
                skin_price=price,
                rarity=rarity,
                quality="FT",
                stattrak=False,
                float_val=main._roll_float_in_range(*main.QUALITY_FLOAT_RANGE["FT"]),
                obtained_from_case="Промокод",
            )
            session.add(item_record)
            main._maybe_update_top_drop(user, {"name": name, "price": price, "rarity": rarity, "image": None})
            message = f"Получен скин: {name}"
            reward_payload = {"type": "skin", "item_name": name}

        else:
            raise HTTPException(400, "Неизвестный тип награды промокода")

        promo.used_count += 1
        activation = PromoActivation(user_id=user.id, promo_id=promo.id)
        session.add(activation)

        try:
            await session.commit()
        except IntegrityError:
            # Гонка параллельных запросов (двойной тап) — UniqueConstraint
            # на (user_id, promo_id) в БД поймал то, что мы не успели
            # поймать выше SELECT'ом. Откатываем и отдаём тот же 400.
            await session.rollback()
            raise HTTPException(400, "Этот промокод уже был активирован твоим аккаунтом")

        await session.refresh(user)

        return {
            "success": True,
            "message": message,
            "reward": reward_payload,
            "new_balance": user.balance,
            "new_gold_balance": user.gold_balance,
        }
