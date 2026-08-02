# ============================================
# CS2 Case Simulator — FastAPI Backend
# ============================================

import random
import secrets
import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session, init_db, User, Inventory, PromoCode
from cases_data import CASES
import config

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
# 1. ЭКОНОМИКА: редкости, качество, StatTrak™
# ============================================

RARITY_ORDER = [
    "Consumer", "Industrial", "Mil-Spec", "Restricted",
    "Classified", "Covert", "Gloves", "Knife",
]

# Верхний тик редкости — "Тайное" + "Особо редкое" (ножи/перчатки).
# Их суммарный шанс всегда фиксирован в 1-2%, независимо от состава кейса.
RARE_TIER = {"Covert", "Knife", "Gloves"}

# Базовая цена предмета в 💎 Кристалликах по редкости (до модификаторов
# качества и StatTrak™) — виртуальная величина, подобрана для баланса игры.
BASE_PRICE_BY_RARITY = {
    "Consumer": 25,
    "Industrial": 55,
    "Mil-Spec": 150,
    "Restricted": 650,
    "Classified": 2400,
    "Covert": 8000,
    "Gloves": 42000,
    "Knife": 60000,
}

QUALITIES = ["FN", "MW", "FT", "WW", "BS"]
QUALITY_FULL_NAME = {
    "FN": "Factory New",
    "MW": "Minimal Wear",
    "FT": "Field-Tested",
    "WW": "Well-Worn",
    "BS": "Battle-Scarred",
}
# Распределение шанса качества внутри выпавшего предмета (реалистичное —
# большая часть скинов оседает в Field-Tested/Battle-Scarred)
QUALITY_WEIGHTS = {"FN": 3, "MW": 8, "FT": 45, "WW": 12, "BS": 32}
QUALITY_PRICE_MULTIPLIER = {"FN": 1.65, "MW": 1.25, "FT": 1.0, "WW": 0.82, "BS": 0.62}

STATTRAK_CHANCE = 0.10
STATTRAK_MULTIPLIER = 1.8
# StatTrak™ не бывает у перчаток (как и в самой игре)
STATTRAK_ELIGIBLE_RARITIES = set(RARITY_ORDER) - {"Gloves"}


def build_dynamic_weights(items: list[dict]) -> dict[str, float]:
    """Строит проценты выпадения по редкостям под конкретный состав кейса.

    Правила:
    - 🟥 Тайное / ★ Особо редкое (Covert + Knife/Gloves): фиксированно 1-2%
      суммарно, независимо от кейса.
    - 🟪 Запрещённое (Restricted): ~15-18%
    - 🟖 Засекреченное (Classified): ~5-6%
    - Оставшийся процент (~70-80%) делится между Ширпотребом (Consumer),
      Промышленным (Industrial) и Армейским (Mil-Spec), которые реально
      есть в кейсе. Если Ширпотреба и Промышленного в кейсе нет —
      весь этот остаток (~75-80%) уходит Армейскому (Mil-Spec).
    """
    present = {i["rarity"] for i in items}
    weights: dict[str, float] = {}

    rare_total = random.uniform(1.0, 2.0)
    classified_total = random.uniform(5.0, 6.0) if "Classified" in present else 0.0
    restricted_total = random.uniform(15.0, 18.0) if "Restricted" in present else 0.0

    used = rare_total + classified_total + restricted_total
    base_pool = max(0.0, 100.0 - used)  # ~70-80% в обычном случае

    have_consumer = "Consumer" in present
    have_industrial = "Industrial" in present
    have_milspec = "Mil-Spec" in present

    if have_consumer or have_industrial:
        shares = {
            "Consumer": 0.64 if have_consumer else 0.0,
            "Industrial": 0.20 if have_industrial else 0.0,
            "Mil-Spec": 0.16 if have_milspec else 0.0,
        }
        total_share = sum(shares.values()) or 1.0
        for rarity, share in shares.items():
            if share > 0:
                weights[rarity] = base_pool * share / total_share
    elif have_milspec:
        weights["Mil-Spec"] = base_pool

    if restricted_total:
        weights["Restricted"] = restricted_total
    if classified_total:
        weights["Classified"] = classified_total

    rare_present = [r for r in RARE_TIER if r in present]
    if rare_present:
        share = rare_total / len(rare_present)
        for r in rare_present:
            weights[r] = share

    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total * 100 for k, v in weights.items()}
    return weights


def calculate_case_price(case_key: str) -> float:
    items = CASES[case_key]["items"]
    weights = build_dynamic_weights(items)

    by_rarity: dict[str, list[dict]] = {}
    for it in items:
        by_rarity.setdefault(it["rarity"], []).append(it)

    expected_value = 0.0
    for rarity, group in by_rarity.items():
        rarity_weight = weights.get(rarity, 0.0)
        per_item_weight = rarity_weight / len(group)
        for _ in group:
            expected_value += (per_item_weight / 100) * BASE_PRICE_BY_RARITY[rarity]

    target_rtp = 0.70  # ~70% возврата — казино-баланс виртуальной экономики
    price = expected_value / target_rtp
    return round(price, -1) or 10.0  # округляем до десятков 💎


def roll_item(case_key: str) -> dict:
    items = CASES[case_key]["items"]
    weights = build_dynamic_weights(items)

    by_rarity: dict[str, list[dict]] = {}
    for it in items:
        by_rarity.setdefault(it["rarity"], []).append(it)

    rarities = list(weights.keys())
    roll = random.uniform(0, 100)
    cumulative = 0.0
    chosen_rarity = rarities[-1] if rarities else "Consumer"
    for rarity in rarities:
        cumulative += weights[rarity]
        if roll <= cumulative:
            chosen_rarity = rarity
            break

    chosen = random.choice(by_rarity[chosen_rarity])

    quality = random.choices(QUALITIES, weights=[QUALITY_WEIGHTS[q] for q in QUALITIES])[0]

    stattrak = (
        chosen_rarity in STATTRAK_ELIGIBLE_RARITIES
        and random.random() < STATTRAK_CHANCE
    )

    base_price = BASE_PRICE_BY_RARITY[chosen_rarity]
    price = base_price * QUALITY_PRICE_MULTIPLIER[quality]
    if stattrak:
        price *= STATTRAK_MULTIPLIER
    price = round(price)

    return {
        "name": chosen["name"],
        "rarity": chosen_rarity,
        "image": chosen["image"],
        "quality": quality,
        "quality_name": QUALITY_FULL_NAME[quality],
        "price": price,
        "float_val": round(random.uniform(0.00, 1.00), 4),
        "stattrak": stattrak,
    }


# ============================================
# Pydantic-схемы
# ============================================
class OpenCaseRequest(BaseModel):
    telegram_id: int
    case_key: str
    count: int = 1  # сколько открытий за раз: 1, 2, 3, 4, 5 или 10


class SellSkinRequest(BaseModel):
    telegram_id: int
    inventory_id: int


class SellMultipleRequest(BaseModel):
    telegram_id: int
    inventory_ids: List[int]  # "распылить" несколько предметов в кристаллы за одну транзакцию


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


class UpdateSettingsRequest(BaseModel):
    telegram_id: int
    lang: Optional[str] = None
    sound_enabled: Optional[bool] = None


class BonusClaimRequest(BaseModel):
    telegram_id: int


class WheelBetRequest(BaseModel):
    telegram_id: int
    bet_amount: float


class MinesStartRequest(BaseModel):
    telegram_id: int
    bet_amount: float
    mines_count: int = 3


class MinesRevealRequest(BaseModel):
    telegram_id: int
    tile_index: int


class MinesCashoutRequest(BaseModel):
    telegram_id: int


class ClimbStartRequest(BaseModel):
    telegram_id: int
    bet_amount: float


class ClimbPickRequest(BaseModel):
    telegram_id: int
    tile_index: int


class ClimbCashoutRequest(BaseModel):
    telegram_id: int


# ============================================
# 2. GET /api/app-config — конфиг для фронтенда
# ============================================
@app.get("/api/app-config")
async def app_config():
    return {
        "bot_username": config.BOT_USERNAME,
        "adsgram_block_id": config.ADSGRAM_BLOCK_ID,
        "ref_bonus_inviter": config.REF_BONUS_INVITER,
        "ref_bonus_invited": config.REF_BONUS_INVITED,
        "bonus_reward_amount": BONUS_REWARD_AMOUNT,
        "bonus_cooldown_seconds": BONUS_COOLDOWN_SECONDS,
    }


# ============================================
# 3. GET /api/cases — список кейсов (с ПОЛНЫМ содержимым для просмотра)
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
                    "image": i["image"],
                    "base_price": BASE_PRICE_BY_RARITY[i["rarity"]],
                }
                for i in sorted(
                    case["items"],
                    key=lambda x: RARITY_ORDER.index(x["rarity"]),
                )
            ],
        })
    return {"cases": result}


# ============================================
# 4. POST /api/open-case
# ============================================
ALLOWED_OPEN_COUNTS = {1, 2, 3, 4, 5, 10}


@app.post("/api/open-case")
async def open_case(req: OpenCaseRequest):
    if req.case_key not in CASES:
        raise HTTPException(404, "Кейс не найден")

    if req.count not in ALLOWED_OPEN_COUNTS:
        raise HTTPException(400, "Недопустимое количество открытий")

    case_price = calculate_case_price(req.case_key)
    total_price = case_price * req.count

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if user.balance < total_price:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= total_price
        user.total_cases_opened += req.count
        user.favorite_case = CASES[req.case_key]["name"]

        drops = []
        item_records = []
        for _ in range(req.count):
            drop = roll_item(req.case_key)
            item_record = Inventory(
                user_id=user.id,
                skin_name=drop["name"],
                skin_price=drop["price"],
                rarity=drop["rarity"],
                quality=drop["quality"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                image_url=drop["image"],
                obtained_from_case=CASES[req.case_key]["name"],
            )
            session.add(item_record)
            drops.append(drop)
            item_records.append(item_record)

        await session.commit()
        for item_record in item_records:
            await session.refresh(item_record)
        await session.refresh(user)

        drop_results = [
            {
                "id": item_records[i].id,
                "name": drops[i]["name"],
                "rarity": drops[i]["rarity"],
                "image": drops[i]["image"],
                "quality": drops[i]["quality"],
                "quality_name": drops[i]["quality_name"],
                "price": drops[i]["price"],
                "float_val": drops[i]["float_val"],
                "stattrak": drops[i]["stattrak"],
            }
            for i in range(req.count)
        ]

        return {
            "success": True,
            "drop": drop_results[0],  # для обратной совместимости с одиночным открытием
            "drops": drop_results,
            "new_balance": user.balance,
        }


# ============================================
# 5. POST /api/sell-skin
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
# 5b. POST /api/sell-multiple — «распылить» выбранные предметы в Кристаллы за одну транзакцию
# ============================================
@app.post("/api/sell-multiple")
async def sell_multiple(req: SellMultipleRequest):
    if not req.inventory_ids:
        raise HTTPException(400, "Не выбрано ни одного предмета")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_items = await session.execute(
            select(Inventory).where(
                Inventory.id.in_(req.inventory_ids),
                Inventory.user_id == user.id,
            )
        )
        items = result_items.scalars().all()
        if not items:
            raise HTTPException(404, "Предметы не найдены в инвентаре")

        total_sold_for = sum(item.skin_price for item in items)
        sold_ids = [item.id for item in items]

        for item in items:
            await session.delete(item)

        user.balance += total_sold_for
        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "sold_for": total_sold_for,
            "sold_count": len(sold_ids),
            "sold_ids": sold_ids,
            "new_balance": user.balance,
        }


# ============================================
# 6. POST /api/promo
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
            message = f"Начислено {amount:.0f} 💎 на баланс"

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
                quality=drop["quality"],
                stattrak=drop["stattrak"],
                float_val=drop["float_val"],
                image_url=drop["image"],
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
                quality="FT",
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
# 7. GET /api/user/profile
# ============================================
@app.get("/api/user/profile")
async def get_profile(
    telegram_id: int,
    username: Optional[str] = "Игрок",
    photo_url: Optional[str] = None,
):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                photo_url=photo_url,
                balance=config.START_BALANCE,
                ref_code=secrets.token_hex(4),
                total_cases_opened=0,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        elif photo_url and user.photo_url != photo_url:
            user.photo_url = photo_url
            await session.commit()

        result_inv = await session.execute(
            select(Inventory).where(Inventory.user_id == user.id)
        )
        inventory = result_inv.scalars().all()

        total_value = sum(i.skin_price for i in inventory) if inventory else 0
        most_expensive = max(inventory, key=lambda i: i.skin_price, default=None) if inventory else None

        return {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "photo_url": user.photo_url,
            "balance": user.balance,
            "is_vip": user.is_vip,
            "lang": user.lang or "ru",
            "sound_enabled": user.sound_enabled,
            "total_cases_opened": user.total_cases_opened,
            "favorite_case": user.favorite_case or "—",
            "inventory_total_value": round(total_value, 0),
            "most_expensive_item": {
                "name": most_expensive.skin_name,
                "price": most_expensive.skin_price,
                "rarity": most_expensive.rarity,
            } if most_expensive else None,
            "inventory_count": len(inventory),
        }


# ============================================
# 8. POST /api/user/settings — язык / звук
# ============================================
@app.post("/api/user/settings")
async def update_settings(req: UpdateSettingsRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if req.lang is not None and req.lang in ("ru", "en", "uk"):
            user.lang = req.lang
        if req.sound_enabled is not None:
            user.sound_enabled = req.sound_enabled

        await session.commit()
        return {"success": True, "lang": user.lang, "sound_enabled": user.sound_enabled}


# ============================================
# 9. POST /api/ad-reward
# ============================================
AD_REWARD_AMOUNT = 2000.0
AD_REWARD_COOLDOWN_SECONDS = 60
_last_ad_reward: dict[int, datetime.datetime] = {}


async def _credit_ad_reward(telegram_id: int) -> dict:
    """Общая логика зачисления награды за просмотр рекламы — используется и
    клиентским POST /api/ad-reward (после AdController.show() на фронте),
    и серверным GET /reward (постбэк от Adsgram, если/когда он настроен).
    Один и тот же cooldown-словарь защищает от двойного начисления, даже
    если оба пути сработают на один и тот же просмотр."""
    now = datetime.datetime.utcnow()
    last = _last_ad_reward.get(telegram_id)
    if last and (now - last).total_seconds() < AD_REWARD_COOLDOWN_SECONDS:
        raise HTTPException(429, "Слишком часто. Подожди немного перед следующим просмотром.")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        user.balance += AD_REWARD_AMOUNT
        await session.commit()
        await session.refresh(user)

        _last_ad_reward[telegram_id] = now

        return {"success": True, "reward": AD_REWARD_AMOUNT, "new_balance": user.balance}


@app.post("/api/ad-reward")
async def ad_reward(req: AdRewardRequest):
    return await _credit_ad_reward(req.telegram_id)


# Кнопка «Бонус 💎 2000» — отдельный от рекламы бесплатный бонус раз в 60 секунд
BONUS_REWARD_AMOUNT = 2000.0
BONUS_COOLDOWN_SECONDS = 60
_last_bonus_claim: dict[int, datetime.datetime] = {}


# ============================================
# 9a. GET /reward — Adsgram Reward URL (server-to-server постбэк)
# ============================================
# ⚠️ ВАЖНО: в официальной публичной документации Adsgram (docs.adsgram.ai/publisher/api-reference)
# зафиксирован ТОЛЬКО клиентский флоу — AdController.show() возвращает Promise, который резолвится
# в браузере после досмотра ролика, без серверного постбэка с userId. Я не нашёл подтверждения,
# что для рекламного блока с типом "Rewarded Video" Adsgram реально дёргает Reward URL с твоего
# кабинета — возможно, это фича, которая либо специфична для другого типа блока (например, Task),
# либо появилась в кабинете позже и просто не всплыла в открытой документации.
#
# Поэтому обязательно проверь в личном кабинете Adsgram (partner.adsgram.ai), в настройках блока
# 40775, действительно ли там есть поле "Reward URL" / "Postback URL" и какие параметры он умеет
# подставлять. Если такого поля нет — этот эндпоинт никто никогда не вызовет, и единственный
# реальный источник начисления — уже работающий POST /api/ad-reward на фронте.
#
# Эндпоинт СОЗНАТЕЛЬНО требует secret-токен в query, а не просто userId — потому что GET-запрос
# без проверки подлинности означает, что ЛЮБОЙ человек, узнавший этот URL (а он у тебя уже
# засветился в переписке), сможет накручивать себе Кристаллики бесконечно, просто открывая
# ссылку в браузере с разными userId. Проверь в кабинете Adsgram, можно ли добавить в Reward URL
# свой параметр (секрет/токен) — большинство рекламных сетей это поддерживают именно для этого.
# Если такой возможности нет — НЕ используй этот эндпоинт как единственный источник начисления,
# оставь основным клиентский POST /api/ad-reward.
@app.get("/reward")
async def adsgram_reward_webhook(userId: int, secret: Optional[str] = None):
    if not config.ADSGRAM_REWARD_SECRET:
        # Секрет не настроен в config.py — эндпоинт полностью открыт всем, кто знает URL.
        # Отказываем явно, чтобы не превратить его в бесплатный кран Кристалликов.
        raise HTTPException(503, "ADSGRAM_REWARD_SECRET не настроен в config.py — эндпоинт отключён из соображений безопасности.")
    if secret != config.ADSGRAM_REWARD_SECRET:
        raise HTTPException(403, "Неверный secret-токен.")

    # userId в Reward URL — это telegram_id пользователя (так весь остальной проект
    # идентифицирует юзеров); если твой Adsgram-кабинет подставляет туда что-то другое
    # (например, внутренний auto-increment id), поправь здесь маппинг.
    return await _credit_ad_reward(userId)


# ============================================
# 9b. Кнопка «Бонус 💎 2000» (раз в 60 секунд)
# ============================================
def _bonus_seconds_left(telegram_id: int) -> int:
    last = _last_bonus_claim.get(telegram_id)
    if not last:
        return 0
    elapsed = (datetime.datetime.utcnow() - last).total_seconds()
    remaining = BONUS_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


@app.get("/api/bonus-status")
async def bonus_status(telegram_id: int):
    """Сколько секунд осталось до следующего бонуса — используется фронтендом,
    чтобы правильно восстановить таймер после перезагрузки страницы."""
    return {
        "seconds_left": _bonus_seconds_left(telegram_id),
        "reward": BONUS_REWARD_AMOUNT,
        "cooldown_seconds": BONUS_COOLDOWN_SECONDS,
    }


@app.post("/api/bonus-claim")
async def bonus_claim(req: BonusClaimRequest):
    seconds_left = _bonus_seconds_left(req.telegram_id)
    if seconds_left > 0:
        raise HTTPException(429, f"Бонус будет доступен через {seconds_left} сек.")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        user.balance += BONUS_REWARD_AMOUNT
        await session.commit()
        await session.refresh(user)

        _last_bonus_claim[req.telegram_id] = datetime.datetime.utcnow()

        return {
            "success": True,
            "reward": BONUS_REWARD_AMOUNT,
            "new_balance": user.balance,
            "cooldown_seconds": BONUS_COOLDOWN_SECONDS,
        }


# ============================================
# 10. UPGRADE
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
# 11. CRASH
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
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

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
# 11b. КОЛЕСО (Wheel)
# ============================================
# Сегменты колеса и их веса (сумма весов = 1000). House edge ~7%.
WHEEL_SEGMENTS = [0, 0.3, 0.5, 0.5, 1, 1, 1.5, 1.5, 2, 3, 5, 10]
WHEEL_WEIGHTS =  [180, 160, 140, 140, 130, 120, 60, 50, 30, 20, 8, 2]


def spin_wheel() -> int:
    """Возвращает индекс выпавшего сегмента WHEEL_SEGMENTS с учётом весов."""
    return random.choices(range(len(WHEEL_SEGMENTS)), weights=WHEEL_WEIGHTS, k=1)[0]


@app.post("/api/minigames/wheel")
async def play_wheel(req: WheelBetRequest):
    if req.bet_amount <= 0:
        raise HTTPException(400, "Некорректная ставка")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= req.bet_amount
        segment_index = spin_wheel()
        multiplier = WHEEL_SEGMENTS[segment_index]
        winnings = round(req.bet_amount * multiplier, 2)
        user.balance += winnings

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "segment_index": segment_index,
            "segments": WHEEL_SEGMENTS,
            "multiplier": multiplier,
            "bet_amount": req.bet_amount,
            "winnings": winnings,
            "result": "win" if multiplier > 0 else "lose",
            "new_balance": user.balance,
        }


# ============================================
# 11c. МИНЁР (Mines) — сессионная игра с сеткой 5x5
# ============================================
MINES_GRID_SIZE = 25
_mines_sessions: dict[int, dict] = {}


def _mines_multiplier(total: int, mines: int, revealed: int, house_edge: float = 0.97) -> float:
    mult = 1.0
    for i in range(revealed):
        remaining = total - i
        safe_remaining = remaining - mines
        if safe_remaining <= 0:
            break
        mult *= remaining / safe_remaining
    return round(mult * house_edge, 4)


@app.post("/api/minigames/mines/start")
async def mines_start(req: MinesStartRequest):
    if req.bet_amount <= 0:
        raise HTTPException(400, "Некорректная ставка")
    if req.mines_count < 1 or req.mines_count > 24:
        raise HTTPException(400, "Количество мин должно быть от 1 до 24")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= req.bet_amount
        await session.commit()
        await session.refresh(user)

        mine_positions = set(random.sample(range(MINES_GRID_SIZE), req.mines_count))
        _mines_sessions[req.telegram_id] = {
            "bet_amount": req.bet_amount,
            "mines_count": req.mines_count,
            "mine_positions": mine_positions,
            "revealed": set(),
            "active": True,
        }

        return {
            "success": True,
            "grid_size": MINES_GRID_SIZE,
            "mines_count": req.mines_count,
            "multiplier": 1.0,
            "new_balance": user.balance,
        }


@app.post("/api/minigames/mines/reveal")
async def mines_reveal(req: MinesRevealRequest):
    session_state = _mines_sessions.get(req.telegram_id)
    if not session_state or not session_state["active"]:
        raise HTTPException(400, "Раунд не начат. Сделай ставку, чтобы начать игру.")
    if req.tile_index < 0 or req.tile_index >= MINES_GRID_SIZE:
        raise HTTPException(400, "Некорректная клетка")
    if req.tile_index in session_state["revealed"]:
        raise HTTPException(400, "Эта клетка уже открыта")

    if req.tile_index in session_state["mine_positions"]:
        session_state["active"] = False
        mine_positions = list(session_state["mine_positions"])
        del _mines_sessions[req.telegram_id]
        return {
            "success": True,
            "result": "bust",
            "mine_positions": mine_positions,
            "winnings": 0,
        }

    session_state["revealed"].add(req.tile_index)
    revealed_count = len(session_state["revealed"])
    safe_tiles_total = MINES_GRID_SIZE - session_state["mines_count"]
    multiplier = _mines_multiplier(MINES_GRID_SIZE, session_state["mines_count"], revealed_count)

    # Все безопасные клетки открыты — автоматический выигрыш
    if revealed_count >= safe_tiles_total:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
            user = result.scalar_one_or_none()
            winnings = round(session_state["bet_amount"] * multiplier, 2)
            user.balance += winnings
            await session.commit()
            await session.refresh(user)

        del _mines_sessions[req.telegram_id]
        return {
            "success": True,
            "result": "cleared",
            "multiplier": multiplier,
            "winnings": winnings,
            "new_balance": user.balance,
        }

    return {
        "success": True,
        "result": "safe",
        "multiplier": multiplier,
        "revealed_count": revealed_count,
    }


@app.post("/api/minigames/mines/cashout")
async def mines_cashout(req: MinesCashoutRequest):
    session_state = _mines_sessions.get(req.telegram_id)
    if not session_state or not session_state["active"]:
        raise HTTPException(400, "Нет активного раунда")

    revealed_count = len(session_state["revealed"])
    multiplier = _mines_multiplier(MINES_GRID_SIZE, session_state["mines_count"], revealed_count) if revealed_count else 0

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        winnings = round(session_state["bet_amount"] * multiplier, 2) if multiplier else 0
        user.balance += winnings
        await session.commit()
        await session.refresh(user)

    del _mines_sessions[req.telegram_id]
    return {
        "success": True,
        "result": "cashout",
        "multiplier": multiplier,
        "winnings": winnings,
        "new_balance": user.balance,
    }


# ============================================
# 11d. БАШНЯ (Tower) и ЛЕСЕНКА (Ladder) — общая механика "climb"
# Разница только в конфигурации: количество плиток на уровень / кол-во бомб / уровней.
# ============================================
CLIMB_CONFIGS = {
    "tower": {"levels": 8, "tiles_per_level": 3, "bombs_per_level": 1},
    "ladder": {"levels": 5, "tiles_per_level": 2, "bombs_per_level": 1},
}
_climb_sessions: dict[str, dict] = {}  # key = f"{game}:{telegram_id}"


def _climb_level_multiplier(cfg: dict, house_edge: float = 0.97) -> float:
    safe = cfg["tiles_per_level"] - cfg["bombs_per_level"]
    return cfg["tiles_per_level"] / safe * house_edge


def _climb_multiplier_for_level(cfg: dict, level: int) -> float:
    return round(_climb_level_multiplier(cfg) ** level, 4)


async def _climb_start(game: str, req: ClimbStartRequest):
    cfg = CLIMB_CONFIGS[game]
    if req.bet_amount <= 0:
        raise HTTPException(400, "Некорректная ставка")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= req.bet_amount
        await session.commit()
        await session.refresh(user)

        key = f"{game}:{req.telegram_id}"
        _climb_sessions[key] = {
            "bet_amount": req.bet_amount,
            "level": 0,
            "active": True,
        }

        return {
            "success": True,
            "game": game,
            "levels": cfg["levels"],
            "tiles_per_level": cfg["tiles_per_level"],
            "next_multiplier": _climb_multiplier_for_level(cfg, 1),
            "new_balance": user.balance,
        }


async def _climb_pick(game: str, req: ClimbPickRequest):
    cfg = CLIMB_CONFIGS[game]
    key = f"{game}:{req.telegram_id}"
    session_state = _climb_sessions.get(key)
    if not session_state or not session_state["active"]:
        raise HTTPException(400, "Раунд не начат. Сделай ставку, чтобы начать игру.")
    if req.tile_index < 0 or req.tile_index >= cfg["tiles_per_level"]:
        raise HTTPException(400, "Некорректная плитка")

    bomb_tiles = set(random.sample(range(cfg["tiles_per_level"]), cfg["bombs_per_level"]))
    if req.tile_index in bomb_tiles:
        session_state["active"] = False
        del _climb_sessions[key]
        return {
            "success": True,
            "result": "bust",
            "bomb_tiles": list(bomb_tiles),
            "winnings": 0,
        }

    session_state["level"] += 1
    level = session_state["level"]
    multiplier = _climb_multiplier_for_level(cfg, level)

    if level >= cfg["levels"]:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
            user = result.scalar_one_or_none()
            winnings = round(session_state["bet_amount"] * multiplier, 2)
            user.balance += winnings
            await session.commit()
            await session.refresh(user)

        del _climb_sessions[key]
        return {
            "success": True,
            "result": "cleared",
            "level": level,
            "multiplier": multiplier,
            "winnings": winnings,
            "new_balance": user.balance,
        }

    return {
        "success": True,
        "result": "safe",
        "level": level,
        "multiplier": multiplier,
        "next_multiplier": _climb_multiplier_for_level(cfg, level + 1),
    }


async def _climb_cashout(game: str, req: ClimbCashoutRequest):
    key = f"{game}:{req.telegram_id}"
    session_state = _climb_sessions.get(key)
    if not session_state or not session_state["active"]:
        raise HTTPException(400, "Нет активного раунда")

    cfg = CLIMB_CONFIGS[game]
    level = session_state["level"]
    multiplier = _climb_multiplier_for_level(cfg, level) if level else 0

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        winnings = round(session_state["bet_amount"] * multiplier, 2) if multiplier else 0
        user.balance += winnings
        await session.commit()
        await session.refresh(user)

    del _climb_sessions[key]
    return {
        "success": True,
        "result": "cashout",
        "level": level,
        "multiplier": multiplier,
        "winnings": winnings,
        "new_balance": user.balance,
    }


@app.post("/api/minigames/tower/start")
async def tower_start(req: ClimbStartRequest):
    return await _climb_start("tower", req)


@app.post("/api/minigames/tower/pick")
async def tower_pick(req: ClimbPickRequest):
    return await _climb_pick("tower", req)


@app.post("/api/minigames/tower/cashout")
async def tower_cashout(req: ClimbCashoutRequest):
    return await _climb_cashout("tower", req)


@app.post("/api/minigames/ladder/start")
async def ladder_start(req: ClimbStartRequest):
    return await _climb_start("ladder", req)


@app.post("/api/minigames/ladder/pick")
async def ladder_pick(req: ClimbPickRequest):
    return await _climb_pick("ladder", req)


@app.post("/api/minigames/ladder/cashout")
async def ladder_cashout(req: ClimbCashoutRequest):
    return await _climb_cashout("ladder", req)


# ============================================
# 12. GET /api/inventory
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
                    "quality": i.quality,
                    "quality_name": QUALITY_FULL_NAME.get(i.quality, ""),
                    "stattrak": i.stattrak,
                    "float_val": i.float_val,
                    "image": i.image_url,
                    "obtained_from_case": i.obtained_from_case,
                }
                for i in items
            ]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
