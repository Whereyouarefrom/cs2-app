# ============================================
# CS2 Case Simulator — FastAPI Backend
# ============================================

import os
import random
import secrets
import math
import asyncio
import time
import datetime
import logging
import traceback
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func

from database import async_session, init_db, close_db, User, Inventory, PromoCode, ChatMessage
from cases_data import CASES
import items_data
import currency
import ranks
import levels
import cosmetics
from auth import parse_and_verify_init_data, InitDataError
from format_utils import format_balance_with_icon
import config

app = FastAPI(title="CS2 Case Simulator API")

@app.get("/")
async def root():
    # Простой ответ на "/", чтобы Render/аптайм-мониторинг не пугались
    # 404 при обращении к корню — весь реальный API живёт под /api/...
    return {"status": "ok", "service": "CS2 Case Simulator API"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_bot_polling_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup_event():
    global _bot_polling_task

    await init_db()
    # Фоновая задача курса валют — первое обновление прямо сейчас (не
    # блокирует запуск сервера, если сети нет: тихо останется на
    # FALLBACK_RATES), дальше сама себя перезапускает каждые несколько часов.
    asyncio.create_task(currency.periodic_refresh())

    # Спринт 7: апсерт дефолтных социальных заданий (routers/tasks.py) —
    # ПОСЛЕ init_db(), чтобы таблица tasks уже точно существовала.
    from routers.tasks import seed_default_tasks
    async with async_session() as _seed_session:
        await seed_default_tasks(_seed_session)

    # Спринт 9.5: фоновая задача подведения итогов еженедельных турниров —
    # раз в минуту проверяет "не воскресенье 23:59 UTC ли сейчас" и, если
    # да, один раз раздаёт награды (см. routers/tournament.py).
    from routers.tournament import periodic_weekly_payout
    asyncio.create_task(periodic_weekly_payout())

    # ============================================
    # Спринт 12: запуск Telegram-бота (админ-команды) вместе с API
    # ============================================
    # Раньше bot.py запускался отдельным процессом (`python bot.py`) — это
    # по-прежнему рабочий вариант для деплоя на 2 процесса/контейнера.
    # Здесь бот поднимается ВНУТРИ процесса API как фоновая asyncio-задача,
    # чтобы `python main.py` был единой точкой входа для всего бэкенда.
    #
    # ВАЖНО про init_db()/close_db(): bot.py в своём отдельном main() тоже
    # вызывает их — но при запуске отсюда мы используем УЖЕ выполненный
    # выше init_db() этого процесса и НЕ вызываем bot.close_db() на
    # остановке (см. shutdown_event ниже), чтобы не закрыть пул соединений,
    # которым продолжает пользоваться FastAPI. Оба модуля (bot.py и
    # database.py) используют один и тот же движок SQLAlchemy (одиночка на
    # уровне модуля database.py), поэтому это безопасно и не создаёт
    # второй пул.
    #
    # BOT_TOKEN оставлен плейсхолдером в config.py по умолчанию — если его
    # не заполнить, aiogram упадёт при первом запросе к Telegram API.
    # Ошибку логируем, но НЕ роняем весь FastAPI-процесс из-за неё: игровой
    # API должен продолжать работать, даже если бот временно недоступен.
    try:
        import bot as bot_module
        await bot_module.setup_bot()
        _bot_polling_task = asyncio.create_task(bot_module.run_polling_with_reconnect())
    except Exception:
        logging.getLogger(__name__).error(
            "Не удалось запустить Telegram-бота вместе с API "
            "(проверь BOT_TOKEN в config.py):\n" + traceback.format_exc()
        )


@app.on_event("shutdown")
async def shutdown_event():
    # Останавливаем polling бота ДО закрытия пула БД — иначе висящий
    # long-polling запрос может попытаться обратиться к уже закрытому
    # соединению в момент штатной остановки.
    if _bot_polling_task is not None:
        _bot_polling_task.cancel()
        try:
            await _bot_polling_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            import bot as bot_module
            await bot_module.bot.session.close()
        except Exception:
            pass

    # Закрываем пул соединений с БД при штатной остановке процесса
    # (рестарт деплоя, graceful shutdown uvicorn) — иначе соединения
    # остаются висеть до истечения серверного idle-таймаута.
    await close_db()


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

# ---------------------------------------------------------------
# ЦЕНЫ ПРЕДМЕТОВ: реальные цены Steam Market + fallback по редкости
# ---------------------------------------------------------------
# Раньше цена ЛЮБОГО предмета определялась ТОЛЬКО его редкостью (плоская
# таблица BASE_PRICE_BY_RARITY) — то есть AWP | Dragon Lore и любой другой
# "Тайный" (Covert) скин стоили в игре одинаковые 8 000 💎, что не имеет
# ничего общего с реальными ценами на площадке Steam (где Dragon Lore
# стоит тысячи долларов, а рядовой Covert-скин — единицы).
#
# Теперь цена конкретного предмета в 💎 Кристалликах (= ₽, см. currency.py)
# берётся ИЗ РЕАЛЬНОЙ цены Steam Community Market (items_data.py подтягивает
# её из items_prices.json, который генерирует sync_prices.py — см. докстринг
# того файла: полная синхронизация ~1950 предметов делается один раз/по
# расписанию на сервере с доступом в интернет, ключ не нужен).
#
# FALLBACK_USD_BY_RARITY ниже используется ТОЛЬКО для предметов, для
# которых sync_prices.py ещё не нашёл реальную цену (например, скрипт ещё
# ни разу не запускался, либо у конкретного скина сейчас нет предложений
# на площадке) — это заведомо консервативная (нижняя) оценка по редкости,
# просто чтобы экономика не ломалась, а не попытка угадать точную цену.
FALLBACK_USD_BY_RARITY = {
    "Consumer": 0.03,
    "Industrial": 0.08,
    "Mil-Spec": 0.60,
    "Restricted": 3.50,
    "Classified": 14.00,
    "Covert": 45.00,
    "Gloves": 250.00,
    "Knife": 350.00,
}

# Оставлена для обратной совместимости (используется в паре мест как
# отображаемая "базовая" цена редкости до реального лукапа по имени) —
# теперь выражена уже в 💎/₽ через текущий курс, а не захардкожена.
def _fallback_base_price_rub(rarity: str) -> float:
    return currency.usd_to_rub(FALLBACK_USD_BY_RARITY.get(rarity, 1.0))


def get_base_price_rub(name: str, rarity: str, stattrak: bool = False) -> float:
    """Главная точка входа для цены предмета в 💎/₽: реальная цена со Steam
    Market (если для этого имени она уже засинкана), иначе — консервативный
    fallback по редкости. При stattrak=True сначала пробуем реальную
    StatTrak-цену конкретного предмета (если засинкана) — и только если её
    нет, применяем общий множитель STATTRAK_MULTIPLIER к обычной цене
    (см. _roll_item_instance)."""
    item = items_data.get_item(name)
    usd = None
    if item:
        if stattrak and item.get("usd_price_stattrak"):
            return currency.usd_to_rub(item["usd_price_stattrak"])
        usd = item.get("usd_price")
    if usd is None:
        usd = FALLBACK_USD_BY_RARITY.get(rarity, 1.0)
    return currency.usd_to_rub(usd)

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

# Официальные пороги float Valve — граница качества определяется ТОЛЬКО
# позицией float_val внутри этого диапазона (раньше quality и float_val
# роллились независимо друг от друга, из-за чего мог выпасть, например,
# "Factory New" с float 0.9, чего в игр�� быть не может).
QUALITY_FLOAT_RANGE = {
    "FN": (0.00, 0.07),
    "MW": (0.07, 0.15),
    "FT": (0.15, 0.38),
    "WW": (0.38, 0.45),
    "BS": (0.45, 1.00),
}


def _roll_quality_and_float() -> tuple[str, float]:
    """Сначала роллим качество по QUALITY_WEIGHTS (сохраняет заданное
    распределение — большинство предметов Field-Tested/Battle-Scarred), а
    ЗАТЕМ float_val — равномерно, но строго внутри диапазона выбранного
    качества. Порядок важен: генерировать float первым и выводить из него
    качество дало бы распределение, продиктованное шириной диапазонов
    Valve (BS ~55%), а не заданными весами игры."""
    quality = random.choices(QUALITIES, weights=[QUALITY_WEIGHTS[q] for q in QUALITIES])[0]
    lo, hi = QUALITY_FLOAT_RANGE[quality]
    float_val = round(random.uniform(lo, hi), 4)
    return quality, float_val


def serialize_inventory_item(item) -> dict:
    """Единая сериализация строки инвентаря для ВСЕХ эндпоинтов, которые
    отдают предметы (профиль, /api/inventory, витрина, публичная карточка
    друга).

    Раньше этот словарь дублировался копипастой в нескольких местах, и
    добавление поля требовало правок во всех — из-за чего, например,
    stattrak_count вообще никогда не доезжал до фронта. Спринт 10 добавил
    сюда точный float, полное имя категории качества (Factory New,
    Field-Tested и т.д.) и счётчик StatTrak™, поэтому единая точка стала
    обязательной.

    float_val округляем до 6 знаков и отдаём как есть — карточка скина в
    инвентаре показывает ТОЧНОЕ значение (напр. Float: 0.013412), а не
    только категорию качества."""
    float_val = item.float_val
    return {
        "id": item.id,
        "name": item.skin_name,
        "price": item.skin_price,
        "rarity": item.rarity,
        # quality — короткий код (FN/MW/FT/WW/BS), quality_name — полное
        # человекочитаемое имя категории. Фронт показывает ОБА (дублирование
        # категории качества требует ТЗ Спринта 10).
        "quality": item.quality,
        "quality_name": QUALITY_FULL_NAME.get(item.quality, ""),
        "float_val": round(float_val, 6) if float_val is not None else None,
        "stattrak": bool(item.stattrak),
        "stattrak_count": item.stattrak_count or 0,
        "image": item.image_url,
        "obtained_from_case": item.obtained_from_case,
        "is_in_showcase": bool(item.is_in_showcase),
        "is_on_market": bool(item.is_on_market),
    }


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


# Веса по редкостям генерируются с рандомизацией (random.uniform внутри
# build_dynamic_weights), поэтому кэшируем результат ОДИН РАЗ на кейс сразу
# после старта сервера — иначе цена кейса и проценты в модалке "Шансы
# выпадения" будут отличаться от реальных шансов при каждом новом запросе.
_CASE_WEIGHTS_CACHE: dict[str, dict[str, float]] = {}


def get_case_weights(case_key: str) -> dict[str, float]:
    if case_key not in _CASE_WEIGHTS_CACHE:
        _CASE_WEIGHTS_CACHE[case_key] = build_dynamic_weights(CASES[case_key]["items"])
    return _CASE_WEIGHTS_CACHE[case_key]


def get_item_drop_chances(case_key: str) -> dict[str, float]:
    """Точный % шанса выпадения для каждого предмета конкретного кейса
    (используется модалкой "Шансы выпадения" на фронте)."""
    items = CASES[case_key]["items"]
    weights = get_case_weights(case_key)
    counts: dict[str, int] = {}
    for it in items:
        counts[it["rarity"]] = counts.get(it["rarity"], 0) + 1
    return {
        it["name"]: round(weights.get(it["rarity"], 0.0) / counts[it["rarity"]], 4)
        for it in items
    }


def calculate_case_price(case_key: str) -> float:
    """Возвращает цену кейса в 💎.

    ВАЖНО: раньше цена считалась как expected_value / target_rtp без верхней
    границы — из-за высокой базовой цены ножей/перчаток (BASE_PRICE_BY_RARITY)
    цена кейса могла улетать далеко за пределы разумного (тысячи и десятки
    тысяч 💎). Теперь цены всех кейсов в каталоге нормализуются в единый
    диапазон 100–999 💎: самый "дешёвый" по ожидаемой ценности контента кейс
    стоит 100 💎, самый "дорогой" — 999 💎, остальные — линейно между ними.
    Это гарантирует и то, что при открытии списывается ровно эта же сумма
    (open_case ниже использует эту же функцию), и то, что каталог всегда
    отсортирован в разумных пределах, сколько бы кейсов ни было (3 сид-кейса
    или полный список из sync_cases.py).
    """
    return _case_price_map().get(case_key, CASE_PRICE_MIN)


CASE_PRICE_MIN = 100
CASE_PRICE_MAX = 999

_CASE_PRICE_CACHE: dict[str, float] = {}


def _raw_case_expected_value(case_key: str) -> float:
    """Сырая ожидаемая ценность содержимого кейса (для ранжирования цен
    между собой — сама по себе эта величина пользователю не показывается)."""
    items = CASES[case_key]["items"]
    weights = get_case_weights(case_key)

    by_rarity: dict[str, list[dict]] = {}
    for it in items:
        by_rarity.setdefault(it["rarity"], []).append(it)

    expected_value = 0.0
    for rarity, group in by_rarity.items():
        rarity_weight = weights.get(rarity, 0.0)
        per_item_weight = rarity_weight / len(group)
        for it in group:
            expected_value += (per_item_weight / 100) * get_base_price_rub(it["name"], rarity)
    return expected_value


def _case_price_map() -> dict[str, float]:
    """Считает и кэширует нормализованные цены (100–999 💎) один раз для
    всех кейсов сразу — иначе относ��тельное ранжирование "дешевле/дороже"
    между кейсами было бы невозможно посчитать по одному кейсу за раз."""
    if _CASE_PRICE_CACHE:
        return _CASE_PRICE_CACHE

    raw_values = {key: _raw_case_expected_value(key) for key in CASES}
    if not raw_values:
        return _CASE_PRICE_CACHE

    min_v = min(raw_values.values())
    max_v = max(raw_values.values())

    for key, v in raw_values.items():
        if max_v == min_v:
            # Единственный кейс в каталоге (или все с одинаковой EV) —
            # ставим нижнюю границу диапазона.
            price = CASE_PRICE_MIN
        else:
            ratio = (v - min_v) / (max_v - min_v)
            price = CASE_PRICE_MIN + ratio * (CASE_PRICE_MAX - CASE_PRICE_MIN)
        # округляем до десятков для красоты (100, 250, 470, 999 и т.п.),
        # затем на всякий случай подрезаем обратно в границы диапазона
        price = round(price / 10) * 10
        price = max(CASE_PRICE_MIN, min(CASE_PRICE_MAX, price))
        _CASE_PRICE_CACHE[key] = float(price)

    return _CASE_PRICE_CACHE


def _roll_item_instance(name: str, rarity: str, image: str) -> dict:
    """Собирает конкретный экземпляр предмета (качество, StatTrak™, float,
    итоговая цена) для уже ВЫБРАННЫХ имени/редкости/картинки. Вынесено из
    roll_item(), чтобы этой же логикой мог пользоваться крафт (там имя и
    редкость предмета уже известны заранее — рандомна только "физика"
    конкретного экземпляра, а не сам факт получения предмета)."""
    quality, float_val = _roll_quality_and_float()
    stattrak = rarity in STATTRAK_ELIGIBLE_RARITIES and random.random() < STATTRAK_CHANCE

    # Если для этого конкретного предмета есть реальная StatTrak-цена со
    # Steam Market — get_base_price_rub(..., stattrak=True) уже вернёт её
    # напрямую (без дополнительного умножения на STATTRAK_MULTIPLIER, чтобы
    # не задвоить премию). Иначе — обычная цена * приблизительный множитель.
    base_price = get_base_price_rub(name, rarity, stattrak=stattrak)
    has_real_stattrak_price = stattrak and bool(
        (items_data.get_item(name) or {}).get("usd_price_stattrak")
    )
    price = base_price * QUALITY_PRICE_MULTIPLIER[quality]
    if stattrak and not has_real_stattrak_price:
        price *= STATTRAK_MULTIPLIER
    price = round(price)

    return {
        "name": name,
        "rarity": rarity,
        "image": image,
        "quality": quality,
        "quality_name": QUALITY_FULL_NAME[quality],
        "price": price,
        "float_val": float_val,
        "stattrak": stattrak,
    }


def roll_item(case_key: str) -> dict:
    items = CASES[case_key]["items"]
    weights = get_case_weights(case_key)

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
    return _roll_item_instance(chosen["name"], chosen_rarity, chosen["image"])


# Алиас под именование из ТЗ Спринта 3 (routers/cases.py: POST /api/cases/open
# генерирует дропы через generate_item_drop) — та же функция, что и roll_item,
# просто под другим именем для совместимости с новым роутером.
generate_item_drop = roll_item


# ============================================
# КРАФТ / ГАРАНТИРОВАННЫЙ ОБМЕН (Trade-Up Contract)
# ============================================
# Честная механика без риска: игрок отдаёт 5 предметов ОДНОЙ редкости +
# небольшую плату за рецепт — и ГАРАНТИРОВАННО получает 1 предмет
# следующей по старшинству редкости (сам конкретный предмет из каталога
# этой редкости выбирает игрок заранее на фронте — рандома в исходе нет
# вообще, только "физика" экземпляра — качество/float/StatTrak, как и у
# любого другого предмета в инвентаре).

CRAFT_ITEMS_REQUIRED = 5

# Плата за рецепт в 💎 — небольшая по сравнению со стоимостью результата,
# растёт вместе с редкостью исходных предметов.
CRAFT_FEE_BY_RARITY = {
    "Consumer": 10,
    "Industrial": 20,
    "Mil-Spec": 40,
    "Restricted": 80,
    "Classified": 150,
    "Covert": 300,
    "Gloves": 500,
    # Knife — уже максимальная редкость, крафт из неё недоступен (см. проверку ниже)
}


def _next_craft_rarity(rarity: str) -> Optional[str]:
    """Следующая по старшинству редкость для трейд-апа. None — если
    редкость уже максимальная (Knife) и апгрейдить дальше неку��а."""
    try:
        idx = RARITY_ORDER.index(rarity)
    except ValueError:
        return None
    if idx + 1 >= len(RARITY_ORDER):
        return None
    return RARITY_ORDER[idx + 1]


_CRAFT_CATALOG_CACHE: dict[str, list[dict]] = {}


def _craft_catalog_by_rarity() -> dict[str, list[dict]]:
    """Уникальные предметы (по имени) для каждой редкости, собранные из
    всех кейсов сразу — это и есть "общий каталог предметов" для крафта."""
    if _CRAFT_CATALOG_CACHE:
        return _CRAFT_CATALOG_CACHE
    seen: dict[str, set] = {}
    for case in CASES.values():
        for it in case["items"]:
            rarity = it["rarity"]
            seen.setdefault(rarity, set())
            if it["name"] in seen[rarity]:
                continue
            seen[rarity].add(it["name"])
            _CRAFT_CATALOG_CACHE.setdefault(rarity, []).append({
                "name": it["name"],
                "rarity": rarity,
                "image": it["image"],
                "base_price": get_base_price_rub(it["name"], rarity),
            })
    return _CRAFT_CATALOG_CACHE


class CraftRequest(BaseModel):
    telegram_id: int
    inventory_ids: List[int]
    target_name: str


@app.get("/api/craft-catalog")
async def get_craft_catalog():
    """Каталог предметов, доступных как цель крафта, сгруппированный по
    редкости — фронт использует его, чтобы показать игроку, что именно он
    получит ДО того, как тот подтвердит крафт (никакой неожиданности в
    исходе, только сам предмет заранее известен)."""
    return {"catalog": _craft_catalog_by_rarity()}


@app.post("/api/craft")
async def craft_item(req: CraftRequest):
    if len(req.inventory_ids) != CRAFT_ITEMS_REQUIRED:
        raise HTTPException(400, f"Для крафта нужно ровно {CRAFT_ITEMS_REQUIRED} предметов")
    if len(set(req.inventory_ids)) != CRAFT_ITEMS_REQUIRED:
        raise HTTPException(400, "Предметы не должны повторяться")

    async with async_session() as session:
        result_user = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_items = await session.execute(
            select(Inventory).where(
                Inventory.id.in_(req.inventory_ids),
                Inventory.user_id == user.id,
            )
        )
        source_items = result_items.scalars().all()

        if len(source_items) != CRAFT_ITEMS_REQUIRED:
            raise HTTPException(400, "Один или несколько предметов не найдены в твоём инвентаре")

        rarities = {i.rarity for i in source_items}
        if len(rarities) != 1:
            raise HTTPException(400, "Все 5 предметов должны быть одной редкости")
        source_rarity = rarities.pop()

        target_rarity = _next_craft_rarity(source_rarity)
        if target_rarity is None:
            raise HTTPException(400, "Эта редкость уже максимальная — крафтить дальше некуда")

        catalog = _craft_catalog_by_rarity().get(target_rarity, [])
        target_entry = next((c for c in catalog if c["name"] == req.target_name), None)
        if not target_entry:
            raise HTTPException(400, "Выбранный целевой предмет не найден в каталоге этой редкости")

        fee = CRAFT_FEE_BY_RARITY.get(source_rarity, 0)
        if user.balance < fee:
            raise HTTPException(400, "Недостаточно 💎 для оплаты рецепта")

        # Гарантированный обмен: сначала списываем плату и удаляем ровно
        # эти 5 предметов, затем начисляем целевой — атомарно в одной
        # транзакции, без промежуточных состояний.
        user.balance -= fee
        await _credit_referral_commission(session, user, fee)
        for item in source_items:
            await session.delete(item)

        new_item = _roll_item_instance(target_entry["name"], target_rarity, target_entry["image"])
        item_record = Inventory(
            user_id=user.id,
            skin_name=new_item["name"],
            skin_price=new_item["price"],
            rarity=new_item["rarity"],
            quality=new_item["quality"],
            stattrak=new_item["stattrak"],
            float_val=new_item["float_val"],
            image_url=new_item["image"],
            obtained_from_case="Крафт",
        )
        session.add(item_record)
        _maybe_update_top_drop(user, new_item)

        xp_info = await _award_xp(session, user, XP_CRAFT)

        await session.commit()
        await session.refresh(item_record)

        return {
            "success": True,
            "new_balance": user.balance,
            "xp": xp_info,
            "crafted_item": {
                "id": item_record.id,
                "name": new_item["name"],
                "rarity": new_item["rarity"],
                "quality": new_item["quality"],
                "quality_name": new_item["quality_name"],
                "price": new_item["price"],
                "image": new_item["image"],
                "stattrak": new_item["stattrak"],
                "float_val": new_item["float_val"],
            },
        }


# ============================================
# СИСТЕМА ОПЫТА (XP) И ЛИГ/РАНГОВ
# ============================================
# Правила начисления XP за активность. Все цифры — "сырое" значение опыта
# за ОДНО действие; за пачечные операции (открытие сразу нескольких
# кейсов) значение умножается на количество.
XP_PER_CASE_MIN = 8
XP_PER_CASE_MAX = 60
XP_DIVISOR_CASE_PRICE = 25   # чем дороже кейс — тем больше XP (но не бесконечно)

XP_MINIGAME_ROUND = 6        # участие в раунде любой мини-игры (ставка сделана)
XP_CRAFT = 10                 # успешный крафт/трейд-ап
XP_DAILY_CLAIM = 8            # забрал ежедневную награду
XP_AD_REWARD = 4              # посмотрел рекламу за 💎
XP_BONUS_CLAIM = 4            # нажал кнопку "Бонус"


def _xp_for_case_open(case_price: float, count: int) -> int:
    """XP за открытие кейса(ов): чем дороже кейс, тем больше опыта за одно
    открытие, но в разумных пределах (XP_PER_CASE_MIN..XP_PER_CASE_MAX)."""
    per_case = round(case_price / XP_DIVISOR_CASE_PRICE)
    per_case = max(XP_PER_CASE_MIN, min(XP_PER_CASE_MAX, per_case))
    return per_case * count


def _roll_rank_case_item(case_key: str) -> Optional[dict]:
    """Ролл предмета для рангового кейса — использует общий каталог
    предметов (все кейсы сразу, реальные картинки/базовые цены Steam, см.
    _craft_catalog_by_rarity), но с собственным набором весов редкости для
    каждого ранга (ranks.RANK_CASE_WEIGHTS) — старшие ранги смещены в
    сторону Covert/Gloves/Knife сильнее, чем обычные кейсы."""
    case_def = ranks.RANK_CASE_WEIGHTS.get(case_key)
    if not case_def:
        return None

    catalog = _craft_catalog_by_rarity()
    weights = case_def["weights"]
    available = [r for r in weights if catalog.get(r)]
    if not available:
        return None

    total = sum(weights[r] for r in available)
    roll = random.uniform(0, total)
    cumulative = 0.0
    chosen_rarity = available[-1]
    for rarity in available:
        cumulative += weights[rarity]
        if roll <= cumulative:
            chosen_rarity = rarity
            break

    chosen = random.choice(catalog[chosen_rarity])
    return _roll_item_instance(chosen["name"], chosen_rarity, chosen["image"])


async def _credit_referral_commission(session, spender: User, spent_amount: float) -> None:
    """P2P-реферальная система: если у spender есть привязанный реферер
    (spender.referred_by), начисляет ему REF_COMMISSION_PERCENT (например,
    5%) от суммы spent_amount — постоянное пассивное отчисление рефереру
    от КАЖДОЙ траты приглашённого им реферала (открытие кейса, крафт,
    ставка в мини-игре и т.п.), а не только разовый бонус при регистрации.

    Начисление идёт напрямую в balance реферера + в накопительную
    статистику ref_earnings_total (используется в профиле, чтобы показать
    "сколько кристаллов пассивно получено с активности друзей").

    Ничего не коммитит сама — вызывается ВНУТРИ уже открытой транзакции,
    рядом с _award_xp, чтобы спи��ание у спендера и начисление рефереру
    ушли в БД одной атомарной операцией вместе с остальным эндпоинтом.
    """
    if not spender.referred_by or spent_amount <= 0:
        return

    result = await session.execute(
        select(User).where(User.telegram_id == spender.referred_by)
    )
    referrer = result.scalar_one_or_none()
    if not referrer:
        return  # реферер мог удалить аккаунт / привязка "осиротела" — не критично

    commission = round(spent_amount * config.REF_COMMISSION_PERCENT, 2)
    if commission <= 0:
        return

    referrer.balance += commission
    referrer.ref_earnings_total = round((referrer.ref_earnings_total or 0.0) + commission, 2)


async def _find_referrer(session, spender: User) -> Optional[User]:
    if not spender.referred_by:
        return None
    result = await session.execute(
        select(User).where(User.telegram_id == spender.referred_by)
    )
    return result.scalar_one_or_none()


async def _credit_referral_upgrader_loss(session, spender: User, lost_amount: float) -> None:
    """Спринт 9.5: пожизненное отчисление рефереру — config.REF_UPGRADER_LOSS_COMMISSION_PERCENT
    (5%) от ставки, ПРОИГРАННОЙ рефералом в Апгрейдере (routers/upgrader.py,
    результат 'lose'). lost_amount — это staked_value (стоимость сгоревших
    предметов + добавленных Кристаллов), т.е. вся сгоревшая ставка целиком.

    Отдельная функция от _credit_referral_commission (общие траты) — так как
    у Апгрейдера, в отличие от открытия кейса/крафта, есть явный исход
    (выигрыш/проигрыш), комиссия здесь считается от исхода, а не от факта
    самой ставки. Ничего не коммитит сама — вызывается внутри уже открытой
    транзакции эндпоинта, рядом с остальными начислениями."""
    if lost_amount <= 0:
        return
    referrer = await _find_referrer(session, spender)
    if not referrer:
        return

    commission = round(lost_amount * config.REF_UPGRADER_LOSS_COMMISSION_PERCENT, 2)
    if commission <= 0:
        return

    referrer.balance += commission
    referrer.ref_earnings_total = round((referrer.ref_earnings_total or 0.0) + commission, 2)


async def _credit_referral_upgrader_win(session, spender: User, net_win: float) -> None:
    """Спринт 9.5: пожизненное отчисление рефереру — config.REF_UPGRADER_WIN_COMMISSION_PERCENT
    (2%) от ЧИСТОГО выигрыша реферала в Апгрейдере (результат 'win').
    net_win — это (target_value - staked_value), т.е. только "навар" сверх
    той ставки, что уже сгорела в предмет, а НЕ вся стоимость выигранного
    предмета целиком. Если по какой-то причине net_win <= 0 (не должно
    случаться при победе, т.к. цель всегда дороже шанса на неё), комиссия
    просто не начисляется. Ничего не коммитит сама — см. _credit_referral_upgrader_loss."""
    if net_win <= 0:
        return
    referrer = await _find_referrer(session, spender)
    if not referrer:
        return

    commission = round(net_win * config.REF_UPGRADER_WIN_COMMISSION_PERCENT, 2)
    if commission <= 0:
        return

    referrer.balance += commission
    referrer.ref_earnings_total = round((referrer.ref_earnings_total or 0.0) + commission, 2)


async def _award_xp(session, user: User, amount: int) -> dict:
    """Начисляет XP пользователю и, если пройден порог следующего ранга
    (или сразу нескольких — на случай крупного разового начисления),
    выдаёт разовую награду за КАЖДЫЙ вновь достигнутый ранг: бонус в
    Кристалликах + (начиная с ранга «Калаш») один автоматический ролл
    специального рангового кейса, сразу добавляемый в инвентарь.

    Ничего не коммитит сама — вызывается ВНУТРИ уже открытой транзакции
    (перед session.commit() в эндпоинте), чтобы списание/начисление XP,
    крысталлов за ранг и сам предмет ушли в БД одной атомарной операцией.
    """
    if amount <= 0:
        return {
            "gained": 0,
            "total_xp": user.xp or 0,
            "rank_level": user.rank_level or 0,
            "rank_up": [],
            "level_up": [],
            "level": levels.level_from_xp(user.xp or 0),
        }

    # Уровень аккаунта ДО начисления — по нему потом определяем, какие
    # уровни игрок перешагнул этим начислением (см. конец функции).
    level_before = levels.level_from_xp(user.xp or 0)

    user.xp = (user.xp or 0) + amount
    current_level = user.rank_level or 0
    rank_up_events = []

    while current_level < ranks.MAX_RANK_LEVEL and user.xp >= ranks.RANKS[current_level + 1]["min_xp"]:
        current_level += 1
        rank_def = ranks.RANKS[current_level]

        user.balance += rank_def["bonus_crystals"]

        reward_item = None
        if rank_def["case_key"]:
            drop = _roll_rank_case_item(rank_def["case_key"])
            if drop:
                session.add(Inventory(
                    user_id=user.id,
                    skin_name=drop["name"],
                    skin_price=drop["price"],
                    rarity=drop["rarity"],
                    quality=drop["quality"],
                    stattrak=drop["stattrak"],
                    float_val=drop["float_val"],
                    image_url=drop["image"],
                    obtained_from_case=f"Ранговый кейс «{rank_def['name']}»",
                ))
                _maybe_update_top_drop(user, drop)
                reward_item = {
                    "name": drop["name"],
                    "rarity": drop["rarity"],
                    "image": drop["image"],
                    "price": drop["price"],
                    "quality_name": drop["quality_name"],
                    "stattrak": drop["stattrak"],
                }

        rank_up_events.append({
            "level": current_level,
            "key": rank_def["key"],
            "name": rank_def["name"],
            "icon": rank_def["icon"],
            "bonus_crystals": rank_def["bonus_crystals"],
            "reward_item": reward_item,
        })

    user.rank_level = current_level

    # ---- Спринт 10: уровень аккаунта + счётчики StatTrak™ ----
    # Уровень аккаунта нигде не хранится (всегда выводится из xp), поэтому
    # тут мы лишь СРАВНИВАЕМ уровень до и после начисления, чтобы отдать
    # фронту события повышения. За одно крупное начисление можно перешагнуть
    # сразу несколько уровней — отдаём список, а не одно значение.
    level_after = levels.level_from_xp(user.xp)
    level_up_events = []
    for lvl in range(level_before + 1, level_after + 1):
        prev_slots = levels.showcase_slots_for_level(lvl - 1)
        slots = levels.showcase_slots_for_level(lvl)
        level_up_events.append({
            "level": lvl,
            "showcase_slots": slots,
            # +1 слот витрины даётся не на каждом уровне, а раз в 5 — фронт
            # по этому флагу решает, показывать ли строку «+1 слот Витрины».
            "showcase_slot_gained": slots > prev_slots,
        })
    user.last_seen_level = level_after

    await _tick_stattrak_counters(session, user)

    return {
        "gained": amount,
        "total_xp": user.xp,
        "rank_level": user.rank_level,
        "rank_up": rank_up_events,
        # ---- Спринт 10 ----
        "level": level_after,
        "level_up": level_up_events,
    }


async def _tick_stattrak_counters(session, user: User) -> None:
    """Спринт 10: «оживляет» счётчик StatTrak™.

    StatTrak-предмет всегда падает игроку с нулём (stattrak_count=0) и
    набивает счётчик от АКТИВНОСТИ — но только тот предмет, который игрок
    реально "носит", то есть выставил в Витрину профиля (is_in_showcase).
    Это и логика, и защита от абсурда: иначе счётчик рос бы одновременно у
    сотен лежащих в инвентаре скинов и ничего бы не значил.

    Вызывается из _award_xp — единой воронки любой активности (открытие
    кейсов, мини-игры, крафт, контракты, ежедневки, реклама), поэтому
    отдельно врезаться в каждый эндпоинт не нужно. Витрина ограничена 10
    слотами, так что это всегда обновление максимум 10 строк.

    Ничего не коммитит — работает внутри уже открытой транзакции вызывающего.
    """
    result = await session.execute(
        select(Inventory).where(
            Inventory.user_id == user.id,
            Inventory.is_in_showcase == True,   # noqa: E712 — SQLAlchemy требует явное сравнение
            Inventory.stattrak == True,          # noqa: E712
        )
    )
    for item in result.scalars().all():
        item.stattrak_count = (item.stattrak_count or 0) + 1


@app.get("/api/ranks")
async def get_ranks(telegram_id: Optional[int] = None):
    """Полная лестница рангов (для экрана "Лига"/прогрессии) + прогресс
    конкретного игрока, если передан telegram_id."""
    ladder = []
    for rank_def in ranks.RANKS:
        entry = dict(rank_def)
        if rank_def["case_key"]:
            case_meta = ranks.RANK_CASE_WEIGHTS.get(rank_def["case_key"], {})
            entry["case_name"] = case_meta.get("name")
        ladder.append(entry)

    payload = {"ranks": ladder}

    if telegram_id is not None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            if user:
                payload["progress"] = ranks.get_rank_progress(user.xp or 0, user.rank_level or 0)

    return payload


# ============================================
# Pydantic-схемы
# ============================================
class TelegramAuthRequest(BaseModel):
    init_data: str  # сырая строка Telegram.WebApp.initData (НЕ initDataUnsafe)


class DevAuthRequest(BaseModel):
    """Только для config.DEV_MODE=True — вход без проверки подписи,
    чтобы можно было тестировать фронтенд вне Telegram."""
    telegram_id: int
    username: Optional[str] = "Игрок"
    photo_url: Optional[str] = None


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
    # До 6 предметов инвентаря объединяются в один апгрейд — их суммарная
    # стоимость становится "старой ценой" для расчёта шанса/цели.
    # inventory_id оставлен для обратной совместимости со старым фронтом
    # (один предмет); если передан inventory_ids — используется он.
    inventory_id: Optional[int] = None
    inventory_ids: Optional[List[int]] = None
    # Игрок задаёт цель ОДНИМ из четырёх способов (mode):
    #   "item"       — выбрал конкретный скин из поиска -> target_name
    #   "price"      — вручную ввёл желаемую стоимость   -> target_price
    #   "multiplier" — быстрая кнопка/ползунок множителя -> multiplier (x2/x3/x5...)
    #   "chance"     — б��страя кнопка/ползунок шанса     -> chance (30/55/75...)
    # Ровно одно из полей target_name/target_price/multiplier/chance должно
    # соответствовать выбранному mode — остальные игнорируются бэкендом.
    mode: str = "multiplier"
    target_name: Optional[str] = None
    target_price: Optional[float] = None
    multiplier: Optional[float] = None
    chance: Optional[float] = None  # в процентах, 1-80


class CrashBetRequest(BaseModel):
    telegram_id: int
    bet_amount: float
    cashout_at: float


class CrashStartRequest(BaseModel):
    telegram_id: int
    bet_amount: float
    # Необязательный "автовывод" — если задан, фронтенд сам вызовет
    # /minigames/crash/cashout, когда его локальная анимация долетит до этого
    # множителя. Игрок в любой момент может нажать "Забрать" раньше и
    # вручную зафиксировать текущий (более низкий) множитель — ручной вывод
    # всегда имеет приоритет, потому что оба пути ведут в один и тот же
    # /cashout, а выигрывает тот запрос, что придёт первым.
    auto_cashout_at: Optional[float] = None


class CrashCashoutRequest(BaseModel):
    telegram_id: int


class UpdateSettingsRequest(BaseModel):
    telegram_id: int
    lang: Optional[str] = None
    sound_enabled: Optional[bool] = None
    background: Optional[str] = None


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
# Спринт 12: Кастомизация фона симулятора
# ============================================
# Единый каталог доступных фонов — источник истины и для валидации на
# бэкенде (update_settings), и для отрисовки сетки выбора на фронте
# (отдаётся клиенту через /api/app-config, чтобы не дублировать список в
# app.js — новый фон добавляется ровно в одном месте).
#
# type="theme"  — обычная тёмная тема приложения, media не участвует;
# type="image"  — статичная HD-картинка карты (JPG/WebP), растягивается
#                 на весь фон через object-fit: cover;
# type="video"  — зацикленное видео-локация (WebM/MP4), рендерится с
#                 autoplay loop muted playsinline (обязательно для
#                 автовоспроизведения в мобильных WebView Telegram).
#
# thumb — превью для сетки выбора в Настройках (может совпадать с src для
# картинок; для видео — отдельный статичный кадр, чтобы не грузить видео
# только ради иконки выбора).
BACKGROUND_OPTIONS = [
    {
        "key": "dark",
        "label": "Классическая тёмная",
        "type": "theme",
    },
    {
        "key": "map_mirage",
        "label": "Mirage",
        "type": "image",
        "src": "/assets/backgrounds/mirage.jpg",
        "thumb": "/assets/backgrounds/thumbs/mirage.jpg",
    },
    {
        "key": "map_dust2",
        "label": "Dust II",
        "type": "image",
        "src": "/assets/backgrounds/dust2.jpg",
        "thumb": "/assets/backgrounds/thumbs/dust2.jpg",
    },
    {
        "key": "map_inferno",
        "label": "Inferno",
        "type": "image",
        "src": "/assets/backgrounds/inferno.jpg",
        "thumb": "/assets/backgrounds/thumbs/inferno.jpg",
    },
    {
        "key": "video_mirage",
        "label": "Mirage (видео)",
        "type": "video",
        "src": "/assets/backgrounds/mirage_loop.mp4",
        "thumb": "/assets/backgrounds/thumbs/mirage_loop.jpg",
    },
    {
        "key": "video_dust2",
        "label": "Dust II (видео)",
        "type": "video",
        "src": "/assets/backgrounds/dust2_loop.mp4",
        "thumb": "/assets/backgrounds/thumbs/dust2_loop.jpg",
    },
]
BACKGROUND_KEYS = {opt["key"] for opt in BACKGROUND_OPTIONS}
DEFAULT_BACKGROUND = "dark"


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
        "ref_commission_percent": config.REF_COMMISSION_PERCENT,
        "vip_price_stars": config.VIP_PRICE_STARS,
        "bonus_reward_amount": BONUS_REWARD_AMOUNT,
        "bonus_cooldown_seconds": BONUS_COOLDOWN_SECONDS,
        "craft_fee_by_rarity": CRAFT_FEE_BY_RARITY,
        "craft_items_required": CRAFT_ITEMS_REQUIRED,
        # Курс валют для переключателя ₽/$/₴ в шапке WebApp — фронт получает
        # его один раз при старте вместе с остальным конфигом (без лишнего
        # запроса) и сам умножает крестики/цены на нужный множитель при
        # переключении валюты. См. также отдельный /api/currency/rates —
        # он дублирует то же самое для случаев, когда фронт хочет обновить
        # курс без полной перезагрузки конфига (например, раз в несколько
        # минут, пока открыт WebApp).
        "currency_rates": currency.get_rates(),
        "currency_symbols": {"RUB": "💎", "USD": "$", "UAH": "₴"},
        # Спринт 12: каталог фонов симулятора для сетки выбора в Настройках.
        "background_options": BACKGROUND_OPTIONS,
    }


# ============================================
# 2b. GET /api/currency/rates — курс валют отдельным лёгким эндпоинтом
# ============================================
@app.get("/api/currency/rates")
async def currency_rates():
    """Отдаёт актуальный (закэшированный, обновляется раз в 6 часов в
    фоне — см. currency.periodic_refresh) курс RUB->USD/UAH. RUB всегда
    равен 1.0, потому что это и есть внутренняя единица 💎 Кристалла."""
    return {"rates": currency.get_rates(), "base": "RUB"}



# ============================================
# 3. GET /api/cases — список кейсов (с ПОЛНЫМ содержимым для просмотра)
# ============================================
@app.get("/api/cases")
async def get_cases():
    result = []
    for key, case in CASES.items():
        chances = get_item_drop_chances(key)
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
                    "base_price": get_base_price_rub(i["name"], i["rarity"]),
                    "drop_chance": chances.get(i["name"], 0.0),
                    # Есть ли у ЭТОГО конкретного скина StatTrak™-версия (для
                    # нож��й/перчаток не используется — там показывается
                    # агрегированная статистика по всей категории, см. фронт).
                    "stattrak_available": (
                        i["rarity"] != "Gloves"
                        and (i["rarity"] == "Knife" or bool((items_data.get_item(i["name"]) or {}).get("stattrak_available")))
                    ),
                }
                for i in sorted(
                    case["items"],
                    key=lambda x: RARITY_ORDER.index(x["rarity"]),
                )
            ],
        })
    # Каталог всегда отсортирован по цене — от дешёвых (базовых) к дорогим
    # (элитным/ножевым), как и просили: от 100 до 999 💎.
    result.sort(key=lambda c: c["price"])
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
        await _credit_referral_commission(session, user, total_price)
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
            _maybe_update_top_drop(user, drop)
            # Спринт 11: авто-лента в глобальный чат для дорогих дропов (>100k 💎)
            _maybe_post_drop_to_chat(session, user, drop)

        xp_info = await _award_xp(session, user, _xp_for_case_open(case_price, req.count))

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
            "xp": xp_info,
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
            message = f"Начислено {format_balance_with_icon(amount)} на баланс"

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
            _maybe_update_top_drop(user, drop)
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
                float_val=round(random.uniform(*QUALITY_FLOAT_RANGE["FT"]), 4),
                obtained_from_case="Промокод",
            )
            session.add(item_record)
            _maybe_update_top_drop(user, {"name": name, "price": price, "rarity": rarity, "image": None})
            message = f"Получен скин: {name}"

        promo.used_count += 1
        await session.commit()

        return {"success": True, "message": message}


# ============================================
# 7. Авторизация + Профиль
# ============================================

def _maybe_update_top_drop(user: User, drop: dict) -> None:
    """Обновляет "Топ дроп" пользователя, ЕСЛИ новый предмет дороже текущего
    рекорда. Вызывается пр�� любом получении предмета (открытие кейса,
    промокод и т.п.) — само поле живёт на User, а не считается из
    инвентаря, поэтому продажа предмета никогда его не затирает.

    Спринт 10: заодно инкрементит накопительные счётчики редкостей для
    авто-разблокировки титулов («Ножеман» — ножи/перчатки, «Счастливчик» —
    Covert и выше). Врезка сделана ИМЕННО здесь осознанно: эта функция уже
    вызывается из всех 13 мест, где игрок получает предмет (кейсы, крафт,
    контракты, апгрейдер, колесо, промокоды, Battle Pass, ежедневки,
    ранговые кейсы), поэтому счётчики нельзя пропустить ни на одном пути.
    Саму разблокировку тут не делаем — она требует уровень и ст��имость
    инвентаря, поэтому живёт в cosmetics.sync_unlocks() при сборке профиля."""
    cosmetics.register_drop(user, drop.get("rarity"))

    price = drop.get("price", 0) or 0
    if user.top_drop_price is None or price > user.top_drop_price:
        user.top_drop_name = drop.get("name")
        user.top_drop_price = price
        user.top_drop_rarity = drop.get("rarity")
        user.top_drop_image = drop.get("image")


# ============================================
# Спринт 11: уведомления администратору + авто-лента дропов в чат
# ============================================
async def notify_admin_telegram(text: str) -> None:
    """Отправляет служебное уведомление администратору (config.ADMIN_TG_ID)
    напрямую через Telegram Bot API. Используется авто-модерацией чата
    (routers/chat.py) при авто-муте по фильтру и при скрытии сообщения по
    3+ жалобам. Тихо проглатывает любые ошибки сети / отсутствие токена —
    провал уведомления НЕ должен ронять основной HTTP-запрос."""
    if not config.ADMIN_TG_ID or not config.BOT_TOKEN:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={"chat_id": config.ADMIN_TG_ID, "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass


def _maybe_post_drop_to_chat(session, user: User, drop: dict) -> None:
    """Авто-лента дропов (Спринт 11): добавляет СИСТЕМНОЕ сообщение в
    глобальный чат ТОЛЬКО если выбитый скин дороже
    config.CHAT_DROP_FEED_THRESHOLD (100 000 💎). Просто кладёт ChatMessage
    в уже открытую сессию — коммит делает вызывающий эндпоинт (open_case)."""
    price = drop.get("price", 0) or 0
    if price <= config.CHAT_DROP_FEED_THRESHOLD:
        return
    name = user.first_name or user.username or "Игрок"
    item = drop.get("name", "предмет")
    st = "StatTrak™ " if drop.get("stattrak") else ""
    price_str = f"{int(price):,}".replace(",", " ")
    text = f"🔥 {name} выбил редкий предмет — {st}{item} за 💎 {price_str}!"
    session.add(ChatMessage(user_id=user.id, text=text, is_system=True, is_hidden=False))


async def _build_profile_payload(session, user: User) -> dict:
    """Единая сборка полного профиля: баланс, VIP, статистика, инвентарь."""
    result_inv = await session.execute(
        select(Inventory).where(Inventory.user_id == user.id).order_by(Inventory.obtained_at.desc())
    )
    inventory = result_inv.scalars().all()

    total_value = sum(i.skin_price for i in inventory) if inventory else 0

    # ---- Статистика P2P-реферальной системы ----
    # Считаем количество приглашённых друзей "на лету" (а не к��шируе�� в
    # отдельной колонке), т.к. это простой COUNT по индексированному полю
    # referred_by и не требует поддерживать счётчик в актуальном состоянии
    # при каждой регистрации. Пассивный заработок, наоборот, накопительный
    # и хранится в user.ref_earnings_total (см. _credit_referral_commission).
    result_ref_count = await session.execute(
        select(func.count(User.id)).where(User.referred_by == user.telegram_id)
    )
    referrals_count = result_ref_count.scalar() or 0

    # ---- Спринт 10: уровень аккаунта, титулы/рамки, витрина ----
    # Уровень считается из того же xp, что и ранг (см. levels.py — почему
    # это две независимые прогрессии от одного счётчика).
    level_info = levels.get_level_progress(user.xp or 0)
    level = level_info["level"]

    # Пересчитываем условия титулов/рамок ИМЕННО здесь: только на сборке
    # профиля одновременно доступны и уровень, и актуальная стоимость
    # инвентаря (нужна «Магнату»). Функция идемпотентна и заодно поднимает
    # peak_inventory_value, поэтому вызывать её на каждом заходе безопасно.
    newly_unlocked = cosmetics.sync_unlocks(user, level=level, inventory_value=total_value)

    # sync_unlocks мутирует user (peak_inventory_value и, при разблокировке,
    # unlocked_titles/unlocked_frames), а все три вызывающих эндпоинта
    # (/auth/telegram, /auth/telegram/dev, /user/profile) — read-only и
    # своего commit() не делают. Поэтому фиксируем изменения здесь, и только
    # если они реально есть, чтобы не открывать транзакцию на каждый заход
    # в профиль. last_seen_level синхронизируем тем же коммитом: обычно его
    # уже обновил _award_xp, но у игрока, набравшего опыт до появления этой
    # колонки, снимок иначе навсегда остался бы на первом уровне.
    if user.last_seen_level != level:
        user.last_seen_level = level
    if session.dirty:
        await session.commit()

    # Витрина: закреплённые предметы + сколько слотов открыл уровень.
    showcase_items = [i for i in inventory if i.is_in_showcase]
    showcase_items.sort(key=lambda i: i.skin_price, reverse=True)

    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "photo_url": user.photo_url,
        "balance": user.balance,
        "gold_balance": round(user.gold_balance or 0.0, 2),
        "is_vip": user.is_vip,
        "vip_expires_at": user.vip_expires_at.isoformat() if user.vip_expires_at else None,
        "lang": user.lang or "ru",
        "sound_enabled": user.sound_enabled,
        # Спринт 12: сервер — источник истины при рассинхроне с localStorage
        # (напр. игрок сменил фон на другом устройстве) — фронт применяет
        # это значение поверх локального после первого успешного логина.
        "background": user.background or DEFAULT_BACKGROUND,
        "terms_accepted": bool(user.terms_accepted),
        "total_cases_opened": user.total_cases_opened,
        "favorite_case": user.favorite_case or "—",
        # ---- P2P-реферальная система: сколько друзей приглашено и сколько
        # 💎 пассивно получено с их активности (см. REF_COMMISSION_PERCENT) ----
        "referrals_count": referrals_count,
        "ref_earnings_total": round(user.ref_earnings_total or 0.0, 2),
        # ---- Опыт (XP) и ранг/лига (см. ranks.py) ----
        "xp": user.xp or 0,
        "rank": ranks.get_rank_progress(user.xp or 0, user.rank_level or 0),
        # ---- Спринт 10: уровень аккаунта (та же xp, отдельная прогрессия
        # по формуле 100 * 1.15^(N-1) — см. levels.py) ----
        "level": level_info,
        # Косметика профиля: полные каталоги с флагом unlocked и прогрессом
        # по условию — фронт рисует и открытые, и ещё закрытые варианты.
        "titles": cosmetics.serialize_titles(user, level=level),
        "frames": cosmetics.serialize_frames(user, level=level),
        "selected_title": user.selected_title,
        "selected_frame": user.selected_frame,
        "selected_title_info": cosmetics.title_public(user.selected_title),
        "selected_frame_info": cosmetics.frame_public(user.selected_frame),
        # Что открылось ровно этим запросом — фронт показывает уведомление.
        "newly_unlocked": newly_unlocked,
        # ---- Витрина лучших скинов ----
        "showcase": {
            "slots": level_info["showcase_slots"],
            "max_slots": level_info["showcase_max_slots"],
            "next_slot_level": level_info["next_showcase_slot_level"],
            "items": [serialize_inventory_item(i) for i in showcase_items],
        },
        "inventory_total_value": round(total_value, 0),
        "inventory_count": len(inventory),
        # "Топ дроп" — самый дорогой предмет за ВСЁ время, персистентный
        # (не пересчитывается из текущего инвентаря, продажа его не убирает).
        "top_drop": {
            "name": user.top_drop_name,
            "price": user.top_drop_price,
            "rarity": user.top_drop_rarity,
            "image": user.top_drop_image,
        } if user.top_drop_name else None,
        # Полный массив инвентаря — фронту не нужно делать второй запрос,
        # чтобы отрисовать вкладку "Профиль" сразу после логина.
        "inventory": [serialize_inventory_item(i) for i in inventory],
    }


@app.post("/api/accept-terms")
async def accept_terms(req: DevAuthRequest):
    """Отмечает, что пользователь принял Пользовательское соглашение.
    Используем ту же простую схему {telegram_id}, что и dev-логин —
    сюда достаточно передать telegram_id, доп. данных не требуется."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        user.terms_accepted = True
        await session.commit()
        return {"success": True}




async def _get_or_create_user(
    session, telegram_id: int, username: str, photo_url: Optional[str],
    first_name: Optional[str] = None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        # Новый юзер — создаём с дефолтным ба��ансом из config.START_BALANCE
        user = User(
            telegram_id=telegram_id,
            username=username or "Игрок",
            first_name=first_name,
            photo_url=photo_url,
            balance=config.START_BALANCE,
            ref_code=secrets.token_hex(4),
            total_cases_opened=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Существующий юзер — просто освежаем имя/аватар, если Telegram
        # прислал новые значения (пользователь мог сменить их в настройках).
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if photo_url and user.photo_url != photo_url:
            user.photo_url = photo_url
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)

    return user


@app.post("/api/auth/telegram")
async def auth_telegram(req: TelegramAuthRequest):
    """Основная точка входа в приложение.

    Принимает СЫРУЮ строку Telegram.WebApp.initData (не initDataUnsafe!),
    проверяет её HMAC-подпись секретом на основе BOT_TOKEN и только после
    успешной проверки достаёт telegram_id/имя/аватар из подписанных данных.
    Если юзера с таким telegram_id ещё нет в БД — создаёт его с дефолтным
    балансом (config.START_BALANCE), если есть — отдаёт его текущие данные.
    """
    try:
        data = parse_and_verify_init_data(req.init_data, config.BOT_TOKEN)
    except InitDataError as e:
        raise HTTPException(401, f"Ошибка авторизации Telegram: {e}")

    tg_user = data.get("user")
    if not tg_user or "id" not in tg_user:
        raise HTTPException(401, "В initData отсутствуют данные пользователя")

    telegram_id = int(tg_user["id"])
    display_name = " ".join(
        p for p in [tg_user.get("first_name"), tg_user.get("last_name")] if p
    ) or tg_user.get("username") or "Игрок"
    photo_url = tg_user.get("photo_url")

    async with async_session() as session:
        user = await _get_or_create_user(
            session, telegram_id, display_name, photo_url,
            first_name=tg_user.get("first_name"),
        )
        payload = await _build_profile_payload(session, user)
        payload["telegram_username"] = tg_user.get("username")  # @handle, если задан в Telegram
        return payload


@app.post("/api/auth/telegram/dev")
async def auth_telegram_dev(req: DevAuthRequest):
    """Вход БЕЗ проверки подписи — только для локальной разработки вне
    Telegram (когда window.Telegram.WebApp.initData пустой, т.е. страница
    открыта просто в браузере). Работает, только если config.DEV_MODE=True.
    """
    if not config.DEV_MODE:
        raise HTTPException(403, "Dev-вход отключён (config.DEV_MODE=False)")

    async with async_session() as session:
        user = await _get_or_create_user(session, req.telegram_id, req.username or "Игрок", req.photo_url)
        return await _build_profile_payload(session, user)


@app.get("/api/user/profile")
async def get_profile(telegram_id: int):
    """Лёгкое обновление уже существующего профиля (без авто-создания —
    юзер должен сперва пройти /api/auth/telegram или /api/auth/telegram/dev).
    Используется при переключении вкладок, чтобы не гонять initData повторно."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден — сначала выполни вход")
        return await _build_profile_payload(session, user)


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
        # Спринт 12: фон валидируем ТОЛЬКО против BACKGROUND_KEYS — иначе
        # клиент мог бы записать в БД произвольную строку (в т.ч. случайно
        # рассинхронизированную со старой версией фронта после деплоя).
        if req.background is not None:
            if req.background not in BACKGROUND_KEYS:
                raise HTTPException(400, "Неизвестный фон")
            user.background = req.background

        await session.commit()
        return {
            "success": True,
            "lang": user.lang,
            "sound_enabled": user.sound_enabled,
            "background": user.background or DEFAULT_BACKGROUND,
        }


# ============================================
# 8b. POST /api/vip/create-invoice-link — покупка VIP из Mini App
# ============================================
# Telegram Stars нельзя списать напрямую из фронтенда — нужна invoice-ссылка,
# созданная через Bot API (createInvoiceLink), которую фронт открывает через
# tg.openInvoiceLink(). Само зачисление VIP происходит НЕ здесь, а в bot.py
# в обработчике F.successful_payment — Telegram присылает подтверждение
# оплаты именно боту, а не Mini App.
class VipInvoiceRequest(BaseModel):
    telegram_id: int


@app.post("/api/vip/create-invoice-link")
async def create_vip_invoice_link(req: VipInvoiceRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден — сначала выполни вход")
        if user.is_vip:
            raise HTTPException(400, "У тебя уже есть VIP-статус")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/createInvoiceLink",
            json={
                "title": "VIP навсегда",
                "description": "Отключение рекламы + косметические бонусы. Не влияет на игровые шансы.",
                "payload": "vip_forever",  # тот же payload, что и в bot.py — обрабатывается там же
                "currency": "XTR",  # Telegram Stars
                "prices": [{"label": "VIP навсегда", "amount": config.VIP_PRICE_STARS}],
            },
        )
    payload = resp.json()
    if not payload.get("ok"):
        raise HTTPException(502, f"Telegram API вернул ошибку: {payload.get('description', 'unknown')}")

    return {"invoice_link": payload["result"], "price_stars": config.VIP_PRICE_STARS}


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
        xp_info = await _award_xp(session, user, XP_AD_REWARD)
        await session.commit()
        await session.refresh(user)

        _last_ad_reward[telegram_id] = now

        return {"success": True, "reward": AD_REWARD_AMOUNT, "new_balance": user.balance, "xp": xp_info}


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
        xp_info = await _award_xp(session, user, XP_BONUS_CLAIM)
        await session.commit()
        await session.refresh(user)

        _last_bonus_claim[req.telegram_id] = datetime.datetime.utcnow()

        return {
            "success": True,
            "reward": BONUS_REWARD_AMOUNT,
            "new_balance": user.balance,
            "cooldown_seconds": BONUS_COOLDOWN_SECONDS,
            "xp": xp_info,
        }


# ============================================
# 9c. Ежедневные награды за вход (Daily Streak) — СПРИНТ 7
# ============================================
# Реализация вын��сена в routers/streak.py (GET /api/streak/status,
# POST /api/streak/claim) — тот же паттерн вынесения фичи в отдельный
# роутер, что и у Колеса удачи (routers/wheel.py, Спринт 6). Старая
# реализация (GET /api/daily-status, POST /api/daily-claim с другой
# таблицей наград) отсюда удалена, чтобы не было двух конкурирующих
# систем начисления на одних и тех же колонках User.daily_streak /
# User.last_daily_claim_at / User.daily_total_claims. Если на фронте или
# в боте где-то остались старые пути — их нужно обновить на /api/streak/*.


# ============================================
# 10. UPGRADE (Апгрейдер)
# ============================================
# Экономика Апгрейдера:
#   - target_house_edge задаёт средний преимущество казино (85% от
#     "честного" 1/multiplier) — то же значение, что было и раньше.
#   - success_chance всегда пересчитывается ИЗ multiplier (даже если игрок
#     стартовал с шанса кнопкой "55%") — это гарантирует, что выведенные на
#     экран шанс и множитель всегда взаимно согласованы и математика бьётся.
#   - На ПОБЕДЕ игрок получает предмет РОВНО целевой стоимости (либо
#     конкретный выбранный скин — тогда цена берётся из его собственной
#     редкости; либо, если цель задавалась ценой/множителем/шансом без
#     привязки к конкретному скину, случайный предмет из глобального
#     реестра items_data с ближайшей по рынку редкостью для target_price).
#   - На ПРОИГРЫШЕ предмет сгорает, но игрок ГАРАНТИРОВАННО получает
#     утешительный скин ровно на 10% от стоимости сгоревшего предмета
#     (см. _grant_compensation ниже) — предметы для механизма компенсации
#     также берутся из items_data, поэтому пул кандидатов не ограничен
#     содержимым кейсов.

UPGRADE_HOUSE_EDGE = 0.85
UPGRADE_MIN_CHANCE = 0.01   # 1%
UPGRADE_MAX_CHANCE = 0.80   # 80%
UPGRADE_MIN_MULTIPLIER = 1.05
UPGRADE_MAX_MULTIPLIER = 100.0

COMPENSATION_RATIO = 0.10       # 10% от СУММАРНОЙ стоимости всех сгоревших предметов
COMPENSATION_TOLERANCE = 0.01   # допустимая погрешность ±1%
# Если суммарная ставка (стоимость всех выбранных предметов) меньше этого
# порога, выдавать компенсационный скин не имеет смысла (сам предмет стоил
# бы копейки и захламлял бы инвентарь) — вместо этого начисляем утешительные
# 0.01 💎 прямо на баланс.
COMPENSATION_MIN_BET = 11.0
COMPENSATION_FALLBACK_CRYSTALS = 0.01


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _chance_from_multiplier(multiplier: float) -> float:
    return _clamp(UPGRADE_HOUSE_EDGE / multiplier, UPGRADE_MIN_CHANCE, UPGRADE_MAX_CHANCE)


def _resolve_upgrade_target(req: "UpgradeRequest", old_price: float) -> tuple[float, float, Optional[dict]]:
    """Возвращает (target_price, success_chance, explicit_item|None) по
    выбранному режиму (req.mode). explicit_item — запись из items_data,
    если игрок целился в конкретный скин по имени (тогда именно он и будет
    выдан при победе); иначе None (при победе подберём случайный предмет
    нужной стоимости через _pick_item_for_price)."""

    if req.mode == "item":
        if not req.target_name:
            raise HTTPException(400, "Не указан целевой предмет")
        explicit_item = items_data.get_item(req.target_name)
        if not explicit_item:
            raise HTTPException(400, "Целевой предмет не найден в базе")
        target_price = get_base_price_rub(explicit_item["name"], explicit_item["rarity"])
        if target_price <= old_price:
            raise HTTPException(400, "Целевой предмет должен быть дороже улучшаемого")
        multiplier = _clamp(target_price / old_price, UPGRADE_MIN_MULTIPLIER, UPGRADE_MAX_MULTIPLIER)
        return target_price, _chance_from_multiplier(multiplier), explicit_item

    if req.mode == "price":
        if not req.target_price or req.target_price <= old_price:
            raise HTTPException(400, "Целевая стоимость должна быть больше стоимости предмета")
        multiplier = _clamp(req.target_price / old_price, UPGRADE_MIN_MULTIPLIER, UPGRADE_MAX_MULTIPLIER)
        return old_price * multiplier, _chance_from_multiplier(multiplier), None

    if req.mode == "chance":
        if not req.chance or not (1.0 <= req.chance <= 80.0):
            raise HTTPException(400, "Шанс должен быть от 1% до 80%")
        chance_frac = req.chance / 100.0
        multiplier = _clamp(UPGRADE_HOUSE_EDGE / chance_frac, UPGRADE_MIN_MULTIPLIER, UPGRADE_MAX_MULTIPLIER)
        return old_price * multiplier, _chance_from_multiplier(multiplier), None

    # mode == "multiplier" (значение по умолчанию, включая быстрые x2/x3/x5)
    if not req.multiplier or not (UPGRADE_MIN_MULTIPLIER <= req.multiplier <= UPGRADE_MAX_MULTIPLIER):
        raise HTTPException(400, f"Множитель должен быть от {UPGRADE_MIN_MULTIPLIER}x до {UPGRADE_MAX_MULTIPLIER}x")
    return old_price * req.multiplier, _chance_from_multiplier(req.multiplier), None


def _pick_item_for_price(target_price: float) -> dict:
    """Подбирает предмет из глобального реестра items_data, чья РЕАЛЬНАЯ
    цена (Steam Market, с fallback по редкости — см. get_base_price_rub)
    ближе всего к желаемой стоимости target_price.

    Раньше подбор шёл только по редкости (случайный предмет внутри самой
    близкой по логарифму цены редкости), из-за чего Апгрейдер мог выдать
    дешёвый рядовой скин "нужной" редкости с реальной ценой в разы ниже
    target_price — теперь редкость используется только чтобы сузить пул
    кандидатов (иначе пришлось бы на каждый запрос пересчитывать цену для
    всех ~1950 предметов реестра), а финальный выбор — по фактической цене."""
    target_log = math.log(max(target_price, 1.0))

    rarities_by_closeness = sorted(
        RARITY_ORDER,
        key=lambda r: abs(math.log(_fallback_base_price_rub(r)) - target_log),
    )
    candidates: list[dict] = []
    for r in rarities_by_closeness[:3]:
        candidates.extend(items_data.ITEMS_BY_RARITY.get(r) or [])
    if not candidates:
        candidates = items_data.ALL_ITEMS

    def _item_log_distance(it: dict) -> float:
        price = get_base_price_rub(it["name"], it["rarity"])
        return abs(math.log(max(price, 0.01)) - target_log)

    candidates.sort(key=_item_log_distance)
    # Берём топ-12 ближайших по цене и выбираем случайно среди них — иначе
    # результат для одной и той же целевой цены б��л бы всегда одинаковым.
    pool = candidates[:12] or candidates
    return random.choice(pool)


def _instance_from_registry_item(entry: dict, forced_price: float) -> dict:
    """Собирает конкретный экземпляр (качество/StatTrak/float — для
    \"вида\", итоговая цена ФИКСИРОВАНА на forced_price, потому что это
    результат Апгрейдера/компенсации, а не обычный дроп из кейса)."""
    rarity = entry["rarity"]
    quality, float_val = _roll_quality_and_float()
    # У части предметов собственный допустимый диапазон float (уже теснее,
    # чем полный диапазон качества Valve) — пересекаем его с диапазоном
    # выбранного качества, чтобы не выйти за пределы того, что реально
    # возможно для этого конкретного скина.
    entry_lo = entry.get("min_float", 0.0)
    entry_hi = entry.get("max_float", 1.0)
    q_lo, q_hi = QUALITY_FLOAT_RANGE[quality]
    lo, hi = max(entry_lo, q_lo), min(entry_hi, q_hi)
    if lo < hi:
        float_val = round(random.uniform(lo, hi), 4)
    stattrak = bool(entry.get("stattrak_available")) and random.random() < STATTRAK_CHANCE
    return {
        "name": entry["name"],
        "rarity": rarity,
        "image": entry["image"],
        "quality": quality,
        "quality_name": QUALITY_FULL_NAME[quality],
        "price": round(forced_price, 2),
        "float_val": float_val,
        "stattrak": stattrak,
    }


@app.get("/api/items/search")
async def search_items(
    q: str = "",
    limit: int = 30,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
):
    """Поиск целевого скина для Апгрейдера/Синтезатора (используется полем
    поиска на фронте) — обходит ВЕСЬ глобальный реестр items_data, а не
    только предметы из кейсов. ��пциональные min_price/max_price фильтруют
    по уже посчитанной цене (используется каталогом Синтезатора, спринт 4:
    поиск по названию + диапазон цен "от/до")."""
    limit = max(1, min(limit, 60))
    # Берём с запасом до фильтрации по цене, чтобы после отсева по диапазону
    # всё ещё оставалось до `limit` результатов (а не сильно меньше).
    fetch_limit = limit if (min_price is None and max_price is None) else max(limit * 5, 150)
    results = items_data.search_items(q, limit=fetch_limit)

    priced = [
        {
            "name": it["name"],
            "rarity": it["rarity"],
            "category": it["category"],
            "image": it["image"],
            "base_price": get_base_price_rub(it["name"], it["rarity"]),
        }
        for it in results
    ]

    if min_price is not None:
        priced = [it for it in priced if it["base_price"] >= min_price]
    if max_price is not None:
        priced = [it for it in priced if it["base_price"] <= max_price]

    return {"results": priced[:limit]}


MAX_UPGRADE_ITEMS = 6


@app.post("/api/upgrade")
async def upgrade_skin(req: UpgradeRequest):
    async with async_session() as session:
        # with_for_update() блокирует строку юзера до конца транзакции —
        # защита от гонки, когда два параллельных запроса с одним и тем же
        # telegram_id читают один и тот же старый баланс/инвентарь и оба
        # проходят проверки. НО: на SQLite (DATABASE_URL по умолчанию в
        # config.py) этот clause по факту не поддерживается движком и
        # SQLAlchemy молча его игнорирует — реальной блокировки строк там
        # нет. Для полноценной защиты от дублей на SQLite нужен либо
        # переход на Postgres/MySQL (там with_for_update реально работает),
        # либо доп. механизм на уровне приложения (напр. asyncio.Lock per
        # telegram_id вокруг всего блока). Оставляю with_for_update(), т.к.
        # это правильный путь и он "бесплатно" заработает при миграции на
        # Postgres, но это не серебряная пуля прямо сейчас на SQLite.
        result = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        # До 6 предметов сразу — их суммарная цена и есть "старая цена"
        ids = req.inventory_ids if req.inventory_ids else ([req.inventory_id] if req.inventory_id else [])
        ids = list(dict.fromkeys(ids))  # без дублей, сохраняя порядок
        if not ids:
            raise HTTPException(400, "Не выбрано ни одного предмета для апгрейда")
        if len(ids) > MAX_UPGRADE_ITEMS:
            raise HTTPException(400, f"Максимум {MAX_UPGRADE_ITEMS} предметов за раз")

        result_items = await session.execute(
            select(Inventory)
            .where(
                Inventory.id.in_(ids),
                Inventory.user_id == user.id,
            )
            .with_for_update()
        )
        items = result_items.scalars().all()
        if len(items) != len(ids):
            raise HTTPException(404, "Один или несколько предметов не найдены в инвентаре")

        old_price = sum(i.skin_price for i in items)
        target_price, success_chance, explicit_item = _resolve_upgrade_target(req, old_price)

        success = random.random() < success_chance

        if success:
            # Победа: выдаём либо ровно выбранный игроком скин, либо
            # случайный предмет нужной по рынку редкости — но с ценой,
            # РОВНО равной той, что игрок видел на экране (target_price).
            won_entry = explicit_item or _pick_item_for_price(target_price)
            won_instance = _instance_from_registry_item(won_entry, target_price)

            for i in items:
                await session.delete(i)
            new_item = Inventory(
                user_id=user.id,
                skin_name=won_instance["name"],
                skin_price=won_instance["price"],
                rarity=won_instance["rarity"],
                quality=won_instance["quality"],
                stattrak=won_instance["stattrak"],
                float_val=won_instance["float_val"],
                image_url=won_instance["image"],
                obtained_from_case="Апгрейдер",
            )
            session.add(new_item)
            _maybe_update_top_drop(user, won_instance)
            await session.commit()
            await session.refresh(new_item)

            return {
                "success": True,
                "result": "win",
                "chance_used": round(success_chance * 100, 2),
                "old_price": old_price,
                "target_price": round(target_price, 2),
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
            }
        else:
            # ��роигрыш: все выбранные предметы сгорают. Компенсация считается
            # от СУММАРНОЙ стоимости всей ставки (old_price = сумма цен всех
            # выбранных предметов, уже посчитана выше).
            for i in items:
                await session.delete(i)

            comp_price = round(old_price * COMPENSATION_RATIO, 2)

            if old_price < COMPENSATION_MIN_BET:
                # Ставка слишком маленькая — скин-компенсация не выдаётся,
                # вместо этого утешительные 0.01 💎 сразу на баланс.
                user.balance = round(user.balance + COMPENSATION_FALLBACK_CRYSTALS, 2)
                await session.commit()
                await session.refresh(user)

                return {
                    "success": True,
                    "result": "lose",
                    "chance_used": round(success_chance * 100, 2),
                    "old_price": old_price,
                    "target_price": round(target_price, 2),
                    "compensation": None,
                    "compensation_crystals": COMPENSATION_FALLBACK_CRYSTALS,
                    "new_balance": user.balance,
                }

            comp_entry = _pick_item_for_price(comp_price)
            comp_instance = _instance_from_registry_item(comp_entry, comp_price)

            comp_item = Inventory(
                user_id=user.id,
                skin_name=comp_instance["name"],
                skin_price=comp_instance["price"],
                rarity=comp_instance["rarity"],
                quality=comp_instance["quality"],
                stattrak=comp_instance["stattrak"],
                float_val=comp_instance["float_val"],
                image_url=comp_instance["image"],
                obtained_from_case="Компенсация Апгрейдера",
            )
            session.add(comp_item)
            await session.commit()
            await session.refresh(comp_item)

            return {
                "success": True,
                "result": "lose",
                "chance_used": round(success_chance * 100, 2),
                "old_price": old_price,
                "target_price": round(target_price, 2),
                "compensation": {
                    "id": comp_item.id,
                    "name": comp_instance["name"],
                    "rarity": comp_instance["rarity"],
                    "quality": comp_instance["quality"],
                    "quality_name": comp_instance["quality_name"],
                    "price": comp_instance["price"],
                    "image": comp_instance["image"],
                    "stattrak": comp_instance["stattrak"],
                    "float_val": comp_instance["float_val"],
                },
                "compensation_crystals": None,
            }


# Старый путь оставлен как алиас для обратной совместимости (вдруг где-то
# на клиенте закэширован старый билд фронтенда) — просто вызывает ту же
# логику, что и новый /api/upgrade.
@app.post("/api/minigames/upgrade")
async def upgrade_skin_legacy_alias(req: UpgradeRequest):
    return await upgrade_skin(req)


# ============================================
# 11. CRASH / РАКЕТА
# ============================================
# Раунд теперь ЖИВОЙ (сессионный, как Минёр), а не "мгновенно решённый":
#   1) /minigames/crash/start — списывает ставку, тайно генерирует crash_point
#      и запоминает server-side время старта раунда. Клиенту crash_point НЕ
#      возвращается — иначе можно было бы читер-кодом заранее узнать точку
#      краха и подгадать вывод.
#   2) Пока раунд активен, фронтенд рисует полёт ракеты в реальном времени по
#      той же формуле роста, что и бэкенд (growth curve), и может опрашивать
#      /minigames/crash/poll, чтобы узнать текущий множитель/не лопнула ли
#      ракета уже.
#   3) Игрок жмёт "Забрать" (кнопка ручного вывода) В ЛЮБОЙ момент полёта —
#      /minigames/crash/cashout всегда принимает вывод по РЕАЛЬНОМУ,
#      посчитанному на сервере (н�� присланному клиентом) множителю на момент
#      запроса. Это работает, даже если изначально был задан авто-вывод на
#      каком-то X: авто-вывод — это просто тот же самый вызов /cashout,
#      сделанный клиентским таймером автоматически по достижении X, поэтому
#      ручной клик "Забрать" всегда может сработать раньше и выигрывает.

CRASH_HOUSE_EDGE = 0.97


def generate_crash_point() -> float:
    r = random.random()
    if r == 0:
        r = 0.0001
    crash_point = CRASH_HOUSE_EDGE / r
    return max(1.00, round(crash_point, 2))


# Та же кривая роста множителя от времени (в секундах), что и в анимации
# фронтенда (см. RocketGame.growthCurve в app.js) — держим их синхронными,
# иначе визуальный множитель на экране разойдётся с тем, что реально
# посчитает /cashout.
def _crash_multiplier_at(elapsed_seconds: float) -> float:
    t = max(0.0, elapsed_seconds)
    return 1 + 0.06 * t + 0.015 * t * t


_crash_sessions: dict[int, dict] = {}


@app.post("/api/minigames/crash/start")
async def crash_start(req: CrashStartRequest):
    if req.bet_amount <= 0:
        raise HTTPException(400, "Некорректная ставка")

    # Защита от двойной ставки — тот же принцип, что и в Минёре: пока
    # предыдущий раунд активен, повторный /start не спишет баланс ещё раз.
    existing = _crash_sessions.get(req.telegram_id)
    if existing and existing.get("active"):
        raise HTTPException(409, "Раунд уже идёт. Заверши текущий полёт, прежде чем начать новый.")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= req.bet_amount
        await _credit_referral_commission(session, user, req.bet_amount)
        xp_info = await _award_xp(session, user, XP_MINIGAME_ROUND)
        await session.commit()
        await session.refresh(user)

        _crash_sessions[req.telegram_id] = {
            "bet_amount": req.bet_amount,
            "crash_point": generate_crash_point(),
            "start_ts": time.time(),
            "auto_cashout_at": req.auto_cashout_at,
            "active": True,
        }

        return {
            "success": True,
            "bet_amount": req.bet_amount,
            "new_balance": user.balance,
            "xp": xp_info,
        }


@app.get("/api/minigames/crash/poll")
async def crash_poll(telegram_id: int):
    """Ненавязчивый опрос состояния текущего полёта (без списаний/начислений):
    возвращает живой множитель или сообщает, что ракета уже лопнула (если
    игрок не успел/не стал нажимать "Забрать")."""
    session_state = _crash_sessions.get(telegram_id)
    if not session_state or not session_state.get("active"):
        return {"success": True, "active": False}

    elapsed = time.time() - session_state["start_ts"]
    crash_point = session_state["crash_point"]
    current_mult = round(_crash_multiplier_at(elapsed), 4)

    if current_mult >= crash_point:
        # Ракета лопнула, а игрок не успел забрать — раунд закрывается,
        # ставка (уже списанная при /start) сгорает.
        session_state["active"] = False
        del _crash_sessions[telegram_id]
        return {"success": True, "active": False, "busted": True, "crash_point": crash_point}

    return {"success": True, "active": True, "busted": False, "multiplier": current_mult}


@app.post("/api/minigames/crash/cashout")
async def crash_cashout(req: CrashCashoutRequest):
    """Ручной (или авто-триггернутый клиентским таймером) вывод — платит
    РОВНО по множителю, посчитанному на сервере в момент этого запроса, а не
    по тому, что игрок/фронтенд мог бы подставить в теле запроса."""
    session_state = _crash_sessions.get(req.telegram_id)
    if not session_state or not session_state.get("active"):
        raise HTTPException(400, "Нет активного полёта")

    elapsed = time.time() - session_state["start_ts"]
    crash_point = session_state["crash_point"]
    current_mult = round(_crash_multiplier_at(elapsed), 4)
    bet_amount = session_state["bet_amount"]

    session_state["active"] = False
    del _crash_sessions[req.telegram_id]

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if current_mult >= crash_point:
            # Ракета успела лопнуть до того, как запрос дошёл до сервера.
            await session.commit()
            return {
                "success": True,
                "result": "lose",
                "crash_point": crash_point,
                "cashout_at": None,
                "winnings": 0,
                "new_balance": user.balance,
            }

        winnings = round(bet_amount * current_mult, 2)
        user.balance += winnings
        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "result": "win",
            "crash_point": crash_point,
            "cashout_at": current_mult,
            "winnings": winnings,
            "new_balance": user.balance,
        }


# Старый мгновенный эндпоинт оставлен для обратной совместимости (вдруг
# где-то на клиенте закэширован старый билд фронтенда, который шлёт заранее
# выбранный cashout_at одним запросом без живого полёта).
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
        await _credit_referral_commission(session, user, req.bet_amount)
        crash_point = generate_crash_point()

        if req.cashout_at <= crash_point:
            winnings = round(req.bet_amount * req.cashout_at, 2)
            user.balance += winnings
            result_status = "win"
        else:
            winnings = 0
            result_status = "lose"

        xp_info = await _award_xp(session, user, XP_MINIGAME_ROUND)

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
            "xp": xp_info,
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
        await _credit_referral_commission(session, user, req.bet_amount)
        segment_index = spin_wheel()
        multiplier = WHEEL_SEGMENTS[segment_index]
        winnings = round(req.bet_amount * multiplier, 2)
        user.balance += winnings

        xp_info = await _award_xp(session, user, XP_MINIGAME_ROUND)

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
            "xp": xp_info,
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

    # Защита от двойной ставки: если игрок случайно (двойной тап/двойной
    # запрос с фронта) уже начал раунд, который ещё активен, повторный
    # /start не должен списывать баланс ещё раз поверх уже идущего раунда.
    existing = _mines_sessions.get(req.telegram_id)
    if existing and existing.get("active"):
        raise HTTPException(409, "Раунд уже идёт. Заверши текущий раунд, прежде чем начать новый.")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")
        if user.balance < req.bet_amount:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        user.balance -= req.bet_amount
        await _credit_referral_commission(session, user, req.bet_amount)
        xp_info = await _award_xp(session, user, XP_MINIGAME_ROUND)
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
            "xp": xp_info,
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
# Разница только в конфигурации: количество плиток на уровень / кол-во бом�� / уровней.
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
        await _credit_referral_commission(session, user, req.bet_amount)
        xp_info = await _award_xp(session, user, XP_MINIGAME_ROUND)
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
            "xp": xp_info,
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

        return {"inventory": [serialize_inventory_item(i) for i in items]}


# ============================================
# 13. Роутеры Спринта 3: /api/cases/open (мульти-спин)
# ============================================
# Импорт СОЗНАТЕЛЬНО стоит здесь, в самом низу файла — после того, как уже
# определены app, CASES, roll_item/generate_item_drop, calculate_case_price,
# _award_xp, _credit_referral_commission, _maybe_update_top_drop и т.д.
# routers/cases.py делает `import main` и обращается к этим именам через
# main.<имя> только ВНУТРИ обработчиков запросов (то есть в момент реального
# HTTP-запроса, когда весь этот файл уже полностью загружен), а не на этапе
# импорта модуля — поэтому цикличность импорта (main -> routers.cases ->
# main) здесь безопасна и не вызывает ImportError.
from routers.cases import router as cases_router  # noqa: E402
app.include_router(cases_router)

# ============================================
# 14. Роутер Спринта 4: /api/upgrader/spin
# ============================================
# Та же схема отложенного импорта, что и у routers.cases выше — модуль
# routers/upgrader.py делает `import main` и обращается к get_base_price_rub,
# _instance_from_registry_item, _maybe_update_top_drop, _award_xp только
# ВНУТРИ обработчика запроса, поэтому подключать его нужно здесь, в с��мом
# низу файла, когда все эти имена уже определены.
from routers.upgrader import router as upgrader_router  # noqa: E402
app.include_router(upgrader_router)

# ============================================
# 15. Роутеры Спринта 5: /api/contracts/craft, /api/market/*
# ============================================
# Та же отложенная схема импорта, что и у роутеров спринтов 3-4 выше —
# routers/contracts.py и routers/market.py делают `import main` и
# обращаются к RARITY_ORDER, get_base_price_rub, _next_craft_rarity,
# _instance_from_registry_item, _maybe_update_top_drop, _award_xp,
# _credit_referral_commission, QUALITY_FULL_NAME только ВНУТРИ обработчиков
# запросов (или, для market.py::RARITY_RANK, на этапе импорта — но уже
# ПОСЛЕ того, как main.py полностью выполнился до этой строки, так что
# main.RARITY_ORDER на тот момент существует).
from routers.contracts import router as contracts_router  # noqa: E402
app.include_router(contracts_router)

from routers.market import router as market_router  # noqa: E402
app.include_router(market_router)

# ============================================
# 16. Роутер Спринта 6: /api/wheel/spin, /api/wheel/status
# ============================================
# Та же отложенная схема импорта — routers/wheel.py обращается к main.CASES,
# main.roll_item, main._maybe_update_top_drop, main.random только ВНУТРИ
# обработчиков запросов.
from routers.wheel import router as wheel_router  # noqa: E402
app.include_router(wheel_router)

# ============================================
# 17. Роутеры Спринта 7: /api/streak/*, /api/tasks/*
# ============================================
# Та же отложенная схема импорта — routers/streak.py обращается к
# main.CASES, main.roll_item, main._maybe_update_top_drop, main._award_xp,
# main.XP_DAILY_CLAIM только ВНУТРИ обработчиков запросов; routers/tasks.py
# самодостаточен (не обращается к main вообще).
from routers.streak import router as streak_router  # noqa: E402
app.include_router(streak_router)

from routers.tasks import router as tasks_router  # noqa: E402
app.include_router(tasks_router)

# ============================================
# 18. Роутер Спринта 8: /api/pass/* (Battle Pass, 50 уровней)
# ============================================
# Та же отложенная схема импорта — routers/pass.py обращается к main.CASES,
# main.roll_item, main.get_base_price_rub, main._instance_from_registry_item,
# main._maybe_update_top_drop только ВНУТРИ обработчиков запросов.
from routers.pass_ import router as pass_router  # noqa: E402
app.include_router(pass_router)

# ============================================
# 19. Роутеры Спринта 9.5: /api/promocodes/activate, /api/tournament/*
# ============================================
# routers/promocodes.py обращается к main.CASES, main.roll_item,
# main._maybe_update_top_drop, main.QUALITY_FLOAT_RANGE только ВНУТРИ
# обработчика запроса (та же отложенная схема, что и выше).
# routers/tournament.py самодостаточен (не обращается к main вообще) —
# читает только TournamentScore/User, которые уже пишут routers/cases.py,
# routers/contracts.py и routers/upgrader.py.
from routers.promocodes import router as promocodes_router  # noqa: E402
app.include_router(promocodes_router)

from routers.tournament import router as tournament_router  # noqa: E402
app.include_router(tournament_router)


# ============================================
# 20. Роутеры Спринта 10: /api/profile/*, /api/friends/*
# ============================================
# Оба роутера обращаются к main.serialize_inventory_item только ВНУТРИ
# обработчиков (та же отложенная схема, что и у роутеров выше) — на уровне
# модуля они импортируют лишь database / levels / cosmetics / ranks, поэтому
# цикл main -> routers.profile -> main не возникает.
from routers.profile import router as profile_router  # noqa: E402
app.include_router(profile_router)

from routers.friends import router as friends_router  # noqa: E402
app.include_router(friends_router)


# ============================================
# 21. Роутер Спринта 11: /api/chat/* (глобальный чат + авто-модерация)
# ============================================
# routers/chat.py обращается к main.notify_admin_telegram только ВНУТРИ
# обработчиков запросов (та же отложенная схема, что и у роутеров выше),
# поэтому подключается здесь, когда notify_admin_telegram уже определён.
from routers.chat import router as chat_router  # noqa: E402
app.include_router(chat_router)


if __name__ == "__main__":
    import os
    import uvicorn
    # Многие хостинги (Render, Railway и т.п.) сами назначают порт через
    # переменную окружения PORT и ожидают, что приложение слушает именно
    # его — иначе health-check не проходит и деплой считается неудачным.
    # Локально (переменной PORT нет) по-прежнему используется 8000.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
