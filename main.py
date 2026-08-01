# ============================================
# CS2 Case Simulator — FastAPI Backend
# ============================================

import random
import secrets
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func

from database import async_session, init_db, User, Inventory, PromoCode

app = FastAPI(title="CS2 Case Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    await init_db()

# ============================================
# 1. БАЗА КЕЙСОВ И ПРЕДМЕТОВ
# ============================================

STEAM_CDN = "https://community.cloudflare.steamstatic.com/economy/image/"

RARITY_WEIGHTS_BASE = {
    "Consumer": 79.92,
    "Industrial": 15.98,
    "Mil-Spec": 3.2,
    "Restricted": 0.64,
    "Classified": 0.28,
    "Covert": 0.26,
    "Knife": 0.26,
}

RARITY_WEIGHTS_FUN = {
    "Consumer": 78.5,
    "Industrial": 15.5,
    "Mil-Spec": 3.6,
    "Restricted": 0.9,
    "Classified": 0.4,
    "Covert": 0.6,
    "Knife": 1.0,
}

CASES = {
    "weapons_case_1": {
        "name": "Weapons Case",
        "image": f"{STEAM_CDN}IzMF03bi9WpSBq-S-ekoE33L-iLqGFHVaU25ZzQNQcXKfE6ZAUxUYAVGZWSSPnkPU0zBjcS0P1AA1MSPTA/62fx62f",
        "items": [
            {"name": "AK-47 | Case Hardened", "rarity": "Restricted", "price": 45.0},
            {"name": "P90 | Death by Kitty", "rarity": "Mil-Spec", "price": 3.5},
            {"name": "Glock-18 | Groundwater", "rarity": "Mil-Spec", "price": 2.0},
            {"name": "Dual Berettas | Colony", "rarity": "Mil-Spec", "price": 1.8},
            {"name": "M4A4 | Faded Zebra", "rarity": "Consumer", "price": 0.6},
            {"name": "MAC-10 | Rasguardo", "rarity": "Consumer", "price": 0.5},
            {"name": "P250 | Splash", "rarity": "Consumer", "price": 0.4},
            {"name": "Five-SeveN | Copper Galaxy", "rarity": "Industrial", "price": 1.2},
            {"name": "AWP | Lightning Strike", "rarity": "Covert", "price": 120.0},
            {"name": "★ Bayonet | Fade", "rarity": "Knife", "price": 950.0},
        ],
    },
    "bravo_case": {
        "name": "Operation Bravo Case",
        "image": f"{STEAM_CDN}-9a81dlWLwJ2UUGoWMzHVIcpKQP-DzPZDGf1_agnDDlxjBaJcaqxfIzkP0BvV9zzgTsHKa1i0T1TPvVA/62fx62f",
        "items": [
            {"name": "M4A1-S | Hyper Beast", "rarity": "Classified", "price": 60.0},
            {"name": "P2000 | Ivory", "rarity": "Mil-Spec", "price": 2.5},
            {"name": "Nova | Tempest", "rarity": "Consumer", "price": 0.8},
            {"name": "MP7 | Skulls", "rarity": "Consumer", "price": 0.7},
            {"name": "Desert Eagle | Naga", "rarity": "Restricted", "price": 30.0},
            {"name": "AK-47 | Fire Serpent", "rarity": "Covert", "price": 4500.0},
            {"name": "★ Karambit | Fade", "rarity": "Knife", "price": 1800.0},
        ],
    },
    "dreams_nightmares": {
        "name": "Dreams & Nightmares Case",
        "image": f"{STEAM_CDN}fq2Nq4vN6DLXi6l8FpiA7fnrVs1cWKY0GLGnfKQoIGrIU2r_qKPh6yeWANyDcXaW0k4NHf1KsobFCg/62fx62f",
        "items": [
            {"name": "MP9 | Featherweight", "rarity": "Consumer", "price": 0.5},
            {"name": "Nova | Wild Six", "rarity": "Industrial", "price": 1.0},
            {"name": "Glock-18 | Neo-Noir", "rarity": "Mil-Spec", "price": 3.0},
            {"name": "USP-S | Jawbreaker", "rarity": "Restricted", "price": 12.0},
            {"name": "AWP | Chromatic Aberration", "rarity": "Classified", "price": 85.0},
            {"name": "M4A1-S | Printstream", "rarity": "Covert", "price": 140.0},
            {"name": "★ Sport Gloves | Pandora's Box", "rarity": "Knife", "price": 620.0},
        ],
    },
    "kilowatt_case": {
        "name": "Kilowatt Case",
        "image": f"{STEAM_CDN}kAcKGXvR9DjK7lYfLPI9k8j8QGm7XsFqFXBQNjeS2b9aB0j5MJmb9OZQAJl9AJyzD9SVOOtn0j4/62fx62f",
        "items": [
            {"name": "Tec-9 | Brother", "rarity": "Consumer", "price": 0.4},
            {"name": "MAG-7 | Insomnia", "rarity": "Industrial", "price": 0.9},
            {"name": "Five-SeveN | Fowl Play", "rarity": "Mil-Spec", "price": 2.8},
            {"name": "Galil AR | Sugar Rush", "rarity": "Restricted", "price": 8.0},
            {"name": "USP-S | Torque", "rarity": "Classified", "price": 40.0},
            {"name": "AK-47 | Head Shot", "rarity": "Covert", "price": 65.0},
            {"name": "★ Butterfly Knife | Fade", "rarity": "Knife", "price": 2100.0},
        ],
    },
}


def calculate_case_price(case_key: str) -> float:
    items = CASES[case_key]["items"]
    weights = RARITY_WEIGHTS_FUN

    total_weight = sum(weights[i["rarity"]] for i in items)
    expected_value = sum(
        (weights[i["rarity"]] / total_weight) * i["price"] for i in items
    )

    target_rtp = 0.70
    price = expected_value / target_rtp
    return round(price, 2)


def roll_item(case_key: str) -> dict:
    items = CASES[case_key]["items"]
    weights = RARITY_WEIGHTS_FUN

    pool = [(item, weights[item["rarity"]]) for item in items]
    total = sum(w for _, w in pool)
    roll = random.uniform(0, total)

    cumulative = 0
    for item, weight in pool:
        cumulative += weight
        if roll <= cumulative:
            chosen = item
            break
    else:
        chosen = pool[-1][0]

    float_val = round(random.uniform(0.00, 1.00), 4)
    stattrak = random.random() < 0.10

    return {
        "name": chosen["name"],
        "rarity": chosen["rarity"],
        "price": chosen["price"],
        "float_val": float_val,
        "stattrak": stattrak,
    }


# ============================================
# Pydantic-схемы
# ============================================
class OpenCaseRequest(BaseModel):
    telegram_id: int
    case_key: str


class SellSkinRequest(BaseModel):
    telegram_id: int
    inventory_id: int


class PromoRequest(BaseModel):
    telegram_id: int
    code: str


class AdRewardRequest(BaseModel):
    telegram_id: int


class UpgradeRequest(BaseModel):
    telegram_id: int
    inventory_id: int
    target_multiplier: float


class CrashBetRequest(BaseModel):
    telegram_id: int
    bet_amount: float
    cashout_at: float


# ============================================
# 2. GET /api/cases
# ============================================
@app.get("/api/cases")
async def get_cases():
    result = []
    for key, case in CASES.items():
        result.append({
            "key": key,
            "name": case["name"],
            "image": case["image"],
            "price": calculate_case_price(key),
            "items": [
                {
                    "name": i["name"],
                    "rarity": i["rarity"],
                    "price": i["price"],
                }
                for i in case["items"]
            ],
        })
    return {"cases": result}


# ============================================
# 3. POST /api/open-case
# ============================================
@app.post("/api/open-case")
async def open_case(req: OpenCaseRequest):
    if req.case_key not in CASES:
        raise HTTPException(404, "Кейс не найден")

    case_price = calculate_case_price(req.case_key)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if user.balance < case_price:
            raise HTTPException(400, "Недостаточно баланса")

        user.balance -= case_price
        user.total_cases_opened += 1
        user.favorite_case = CASES[req.case_key]["name"]

        drop = roll_item(req.case_key)

        item_record = Inventory(
            user_id=user.id,
            skin_name=drop["name"],
            skin_price=drop["price"],
            rarity=drop["rarity"],
            stattrak=drop["stattrak"],
            float_val=drop["float_val"],
            image_url=None,
            obtained_from_case=CASES[req.case_key]["name"],
        )
        session.add(item_record)

        await session.commit()
        await session.refresh(item_record)
        await session.refresh(user)

        return {
            "success": True,
            "drop": {
                "id": item_record.id,
                "name": drop["name"],
                "rarity": drop["rarity"],
                "price": drop["price"],
                "float_val": drop["float_val"],
                "stattrak": drop["stattrak"],
            },
            "new_balance": user.balance,
        }


# ============================================
# 4. POST /api/sell-skin
# ============================================
@app.post("/api/sell-skin")
async def sell_skin(req: SellSkinRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_item = await session.execute(
            select(Inventory).where(
                Inventory.id == req.inventory_id,
                Inventory.user_id == user.id,
            )
        )
        item = result_item.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в инвентаре")

        sell_price = item.skin_price
        user.balance += sell_price

        await session.delete(item)
        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "sold_for": sell_price,
            "new_balance": user.balance,
        }


# ============================================
# 5. POST /api/promo
# ============================================
@app.post("/api/promo")
async def activate_promo(req: PromoRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_promo = await session.execute(
            select(PromoCode).where(PromoCode.code == req.code)
        )
        promo = result_promo.scalar_one_or_none()
        if not promo:
            raise HTTPException(404, "Промокод не найден")

        if promo.expires_at and promo.expires_at < datetime.datetime.utcnow():
            raise HTTPException(400, "Промокод просрочен")

        if promo.used_count >= promo.max_activations:
            raise HTTPException(400, "Лимит активаций исчерпан")

        message = ""
        if promo.reward_type == "balance":
            amount = float(promo.reward_value)
            user.balance += amount
            message = f"Начислено ${amount:.0f} на баланс"

        elif promo.reward_type == "case":
            case_key = promo.reward_value
            if case_key not in CASES:
                raise HTTPException(400, "Кейс в промокоде не найден")
            drop = roll_item(case_key)
            item_record = Inventory(
                user_id=user.id,
                skin_name=drop["name"],
                skin_price=drop["price"],
                rarity=drop["rarity"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                obtained_from_case=CASES[case_key]["name"] + " (промо)",
            )
            session.add(item_record)
            message = f"Открыт бесплатный кейс: {CASES[case_key]['name']}"

        elif promo.reward_type == "skin":
            parts = promo.reward_value.split("|")
            name, rarity, price = parts[0], parts[1], float(parts[2])
            item_record = Inventory(
                user_id=user.id,
                skin_name=name,
                skin_price=price,
                rarity=rarity,
                stattrak=False,
                float_val=round(random.uniform(0, 1), 4),
                obtained_from_case="Промокод",
            )
            session.add(item_record)
            message = f"Получен скин: {name}"

        promo.used_count += 1
        await session.commit()

        return {"success": True, "message": message}


# ============================================
# 6. GET /api/user/profile (ИСПРАВЛЕННЫЙ)
# ============================================
@app.get("/api/user/profile")
async def get_profile(telegram_id: int, username: Optional[str] = "Игрок"):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        # Если пользователя еще нет в базе — автоматически регистрируем
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                balance=500.0,
                ref_code=secrets.token_hex(4),
                total_cases_opened=0
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        result_inv = await session.execute(
            select(Inventory).where(Inventory.user_id == user.id)
        )
        inventory = result_inv.scalars().all()

        total_value = sum(i.skin_price for i in inventory) if inventory else 0
        most_expensive = max(inventory, key=lambda i: i.skin_price, default=None) if inventory else None

        return {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "balance": user.balance,
            "is_vip": user.is_vip,
            "total_cases_opened": user.total_cases_opened,
            "favorite_case": user.favorite_case or "Отсутствует",
            "inventory_total_value": round(total_value, 2),
            "most_expensive_item": {
                "name": most_expensive.skin_name,
                "price": most_expensive.skin_price,
                "rarity": most_expensive.rarity,
            } if most_expensive else None,
            "inventory_count": len(inventory),
        }


# ============================================
# 7. POST /api/ad-reward
# ============================================
AD_REWARD_AMOUNT = 2000.0
AD_REWARD_COOLDOWN_SECONDS = 60
_last_ad_reward: dict[int, datetime.datetime] = {}


@app.post("/api/ad-reward")
async def ad_reward(req: AdRewardRequest):
    now = datetime.datetime.utcnow()
    last = _last_ad_reward.get(req.telegram_id)

    if last and (now - last).total_seconds() < AD_REWARD_COOLDOWN_SECONDS:
        raise HTTPException(429, "Слишком часто. Подожди немного перед следующим просмотром.")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        user.balance += AD_REWARD_AMOUNT
        await session.commit()
        await session.refresh(user)

        _last_ad_reward[req.telegram_id] = now

        return {
            "success": True,
            "reward": AD_REWARD_AMOUNT,
            "new_balance": user.balance,
        }


# ============================================
# 8. UPGRADE
# ============================================
@app.post("/api/minigames/upgrade")
async def upgrade_skin(req: UpgradeRequest):
    if req.target_multiplier < 1.1 or req.target_multiplier > 20.0:
        raise HTTPException(400, "Множитель должен быть от 1.1x до 20x")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_item = await session.execute(
            select(Inventory).where(
                Inventory.id == req.inventory_id,
                Inventory.user_id == user.id,
            )
        )
        item = result_item.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в инвентаре")

        target_house_edge = 0.85
        success_chance = target_house_edge / req.target_multiplier
        success_chance = max(0.01, min(0.80, success_chance))

        roll = random.random()
        success = roll < success_chance

        old_price = item.skin_price

        if success:
            new_price = round(old_price * req.target_multiplier, 2)
            item.skin_price = new_price
            item.skin_name = f"{item.skin_name} (Upgraded)"
            await session.commit()

            return {
                "success": True,
                "result": "win",
                "chance_used": round(success_chance * 100, 2),
                "old_price": old_price,
                "new_price": new_price,
                "item_id": item.id,
            }
        else:
            await session.delete(item)
            await session.commit()

            return {
                "success": True,
                "result": "lose",
                "chance_used": round(success_chance * 100, 2),
                "old_price": old_price,
                "new_price": 0,
                "item_id": None,
            }


# ============================================
# 9. CRASH
# ============================================
def generate_crash_point() -> float:
    house_edge = 0.97
    r = random.random()
    if r == 0:
        r = 0.0001
    crash_point = house_edge / r
    return max(1.00, round(crash_point, 2))


@app.post("/api/minigames/crash")
async def play_crash(req: CrashBetRequest):
    if req.bet_amount <= 0:
        raise HTTPException(400, "Некорректная ставка")
    if req.cashout_at < 1.01:
        raise HTTPException(400, "Множитель должен быть больше 1.01x")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно баланса")

        user.balance -= req.bet_amount
        crash_point = generate_crash_point()

        if req.cashout_at <= crash_point:
            winnings = round(req.bet_amount * req.cashout_at, 2)
            user.balance += winnings
            result_status = "win"
        else:
            winnings = 0
            result_status = "lose"

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "result": result_status,
            "crash_point": crash_point,
            "cashout_at": req.cashout_at,
            "bet_amount": req.bet_amount,
            "winnings": winnings,
            "new_balance": user.balance,
        }


# ============================================
# 10. GET /api/inventory
# ============================================
@app.get("/api/inventory")
async def get_inventory(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_inv = await session.execute(
            select(Inventory).where(Inventory.user_id == user.id).order_by(Inventory.obtained_at.desc())
        )
        items = result_inv.scalars().all()

        return {
            "inventory": [
                {
                    "id": i.id,
                    "name": i.skin_name,
                    "price": i.skin_price,
                    "rarity": i.rarity,
                    "stattrak": i.stattrak,
                    "float_val": i.float_val,
                    "obtained_from_case": i.obtained_from_case,
                }
                for i in items
            ]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
