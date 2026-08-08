# ============================================
# СПРИНТ 8: Боевой пропуск (Battle Pass) — 50 уровней
# ============================================
#
# GET  /api/pass/status         — полный статус: уровень/XP, ветка VIP,
#                                  дерево наград 1-49 с флагами claimed,
#                                  доступность финального 50-го уровня.
# POST /api/pass/claim          { telegram_id, level, track }
# POST /api/pass/buy-vip        { telegram_id }               — 50 Gold
# POST /api/pass/skip-level     { telegram_id }                — 5 Gold / уровень
# GET  /api/pass/daily-tasks    — 5 (6 с VIP) ежедневных заданий + прогресс
# POST /api/pass/daily-task/claim { telegram_id, task_key }
# POST /api/pass/final-chest/reveal { telegram_id, track, card_index }
#
# ЭКОНОМИКА (см. ТЗ):
#   1 уровень = 100 XP.
#   Free: 5 ежедневных заданий по +20 XP (максимум 100 XP/день = 1 уровень).
#   VIP (стоит 50 Gold, открывает VIP-ветку навсегда для этого пропуска):
#     доп. 6-е задание в день на +25 XP (итого 125 XP/день: 100 Free + 25 VIP —
#     в ТЗ округлённо упомянуто "150 XP/день", здесь берём точную сумму по
#     заданным номиналам заданий, +25 XP за 6-е задание оставлено как есть).
#   Докупка уровня (Level Skip): 5 Gold = мгновенно +1 уровень.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у остальных
# роутеров (streak.py, wheel.py и т.д.) — main.py подключает этот роутер
# в самом низу файла, когда все нужные имена (roll_item, CASES,
# get_base_price_rub, _instance_from_registry_item, _maybe_update_top_drop)
# уже определены. Сам этот модуль обращается к ним только ВНУТРИ
# обработчиков запросов, а не на этапе импорта, поэтому цикличность
# main -> routers.pass -> main безопасна.

from __future__ import annotations

import datetime
import json
import random
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import items_data
import main
from database import BattlePassProgress, Inventory, User, async_session

router = APIRouter()

# ============================================
# Константы экономики
# ============================================
XP_PER_LEVEL = 100
MAX_LEVEL = 50

VIP_PASS_PRICE_GOLD = 50
LEVEL_SKIP_PRICE_GOLD = 5

FREE_TASK_XP = 20
VIP_TASK_XP = 25


# ============================================
# Дерево наград — уровни 1-49
# ============================================
# Каждая награда — список из 1+ элементов (некоторые уровни выдают
# комбо-награду, напр. "Капсула цвета ника + N Кристаллов"). Типы:
#   crystals     -> {"type":"crystals","amount":N}
#   case         -> {"type":"case","case_key":"...", "label":"..."}       (реальный кейс каталога)
#   custom_case  -> {"type":"custom_case","rarities":[...], "prefer_expensive":bool, "label":"..."}
#   vip_time     -> {"type":"vip_time","hours":N,"label":"..."}
#   frame        -> {"type":"frame","key":"...","label":"..."}
#   nick_color   -> {"type":"nick_color","key":"...","label":"..."}

def _c(amount: int) -> dict:
    return {"type": "crystals", "amount": amount}


def _case(key: str, label: str) -> dict:
    return {"type": "case", "case_key": key, "label": label}


def _custom(rarities: list[str], label: str, prefer_expensive: bool = False) -> dict:
    return {"type": "custom_case", "rarities": rarities, "prefer_expensive": prefer_expensive, "label": label}


def _vip(hours: int, label: str) -> dict:
    return {"type": "vip_time", "hours": hours, "label": label}


def _frame(key: str, label: str) -> dict:
    return {"type": "frame", "key": key, "label": label}


def _nick(key: str, label: str) -> dict:
    return {"type": "nick_color", "key": key, "label": label}


REWARD_TREE: dict[int, dict[str, list[dict]]] = {
    1: {"free": [_c(5000)], "vip": [_c(25000)]},
    2: {"free": [_case("cs_go_weapon_case", "Стандартный Кейс")],
        "vip": [_vip(24, "VIP-статус (1 день)"), _custom(["Consumer", "Industrial", "Restricted"], "Кастомный Кейс")]},
    3: {"free": [_vip(1, "VIP-статус (1 час)")], "vip": [_frame("neon_rookie", "Неоновый Новичок")]},
    4: {"free": [_c(10000)], "vip": [_c(50000)]},
    5: {"free": [_custom(["Mil-Spec"], "Случайный скин (Армейское)")], "vip": [_nick("green", "Зелёный")]},
    6: {"free": [_c(15000)], "vip": [_vip(48, "VIP-статус (2 дня)")]},
    7: {"free": [_vip(3, "VIP-статус (3 часа)")], "vip": [_custom(["Knife"], "Кастомный «Knife Only Case»")]},
    8: {"free": [_case("revolution_case", "Кейс «Revolution»")], "vip": [_c(100000)]},
    9: {"free": [_c(20000)], "vip": [_frame("fire_burst", "Огненный Всполох")]},
    10: {"free": [_custom(["Restricted"], "Случайный скин (Запрещённое)")],
         "vip": [_nick("blue", "Синий"), _c(150000)]},
    11: {"free": [_vip(6, "VIP-статус (6 часов)")], "vip": [_vip(72, "VIP-статус (3 дня)")]},
    12: {"free": [_c(25000)], "vip": [_custom(["Covert"], "Кейс «Covert Only»")]},
    13: {"free": [_case("dreams_nightmares_case", "Кейс «Dreams & Nightmares»")], "vip": [_c(200000)]},
    14: {"free": [_c(30000)], "vip": [_frame("cyberpunk", "Киберпанк")]},
    15: {"free": [_vip(12, "VIP-статус (12 часов)")], "vip": [_nick("purple", "Фиолетовый")]},
    16: {"free": [_custom(["Restricted"], "Случайный скин (Запрещённое)")], "vip": [_vip(96, "VIP-статус (4 дня)")]},
    17: {"free": [_c(35000)], "vip": [_c(250000)]},
    18: {"free": [_case("snakebite_case", "Кейс «Snakebite»")], "vip": [_case("glove_case", "Кастомный «Gloves Case»")]},
    19: {"free": [_vip(24, "VIP-статус (24 часа)")], "vip": [_frame("golden_dragon", "Золотой Дракон")]},
    20: {"free": [_c(50000)], "vip": [_nick("gold", "Золотой"), _c(300000)]},
    21: {"free": [_custom(["Classified"], "Случайный скин (Засекреченное)")], "vip": [_vip(120, "VIP-статус (5 дней)")]},
    22: {"free": [_c(40000)], "vip": [_c(350000)]},
    23: {"free": [_case("fracture_case", "Кейс «Fracture»")],
         "vip": [_custom(["Knife"], "Кастомный «Secret Knife Case»", prefer_expensive=True)]},
    24: {"free": [_vip(36, "VIP-статус (36 часов)")], "vip": [_frame("animated_ice", "Анимированный Лёд")]},
    25: {"free": [_c(60000)], "vip": [_nick("rainbow_gradient", "Радужный (Gradient)")]},
    26: {"free": [_custom(["Classified"], "Случайный скин (Засекреченное)")], "vip": [_c(400000)]},
    27: {"free": [_c(45000)], "vip": [_vip(144, "VIP-статус (6 дней)")]},
    28: {"free": [_case("clutch_case", "Кейс «Clutch»")],
         "vip": [_custom(["Covert"], "Кастомный «Dragon Lore Chance Case»", prefer_expensive=True)]},
    29: {"free": [_vip(48, "VIP-статус (48 часов)")], "vip": [_frame("plasma", "Плазма")]},
    30: {"free": [_c(75000)], "vip": [_nick("neon_red", "Неоновый Красный"), _c(500000)]},
    31: {"free": [_custom(["Classified"], "Случайный скин (Засекреченное)")], "vip": [_vip(168, "VIP-статус (7 дней)")]},
    32: {"free": [_c(50000)], "vip": [_c(600000)]},
    33: {"free": [_case("recoil_case", "Кейс «Recoil»")],
         "vip": [_custom(["Covert", "Gloves"], "Кастомный «Hyperbeast Case»", prefer_expensive=True)]},
    34: {"free": [_vip(60, "VIP-статус (60 часов)")], "vip": [_frame("cosmic_abyss", "Космическая Бездна")]},
    35: {"free": [_c(85000)], "vip": [_nick("dark_crimson", "Тёмно-Алый")]},
    36: {"free": [_custom(["Covert"], "Случайный скин (Тайное)")], "vip": [_c(700000)]},
    37: {"free": [_c(60000)],
         "vip": [_custom(["Gloves", "Knife"], "Кастомный «Gloves & Knives Top Case»", prefer_expensive=True)]},
    38: {"free": [_case("operation_bravo_case", "Кейс «Operation Bravo»")], "vip": [_c(800000)]},
    39: {"free": [_vip(72, "VIP-статус (72 часа)")], "vip": [_frame("cs2_legend", "Легенда CS2")]},
    40: {"free": [_c(100000)], "vip": [_nick("chameleon", "Хамелеон"), _c(1000000)]},
    41: {"free": [_custom(["Covert"], "Случайный скин (Тайное)")], "vip": [_c(1200000)]},
    42: {"free": [_c(70000)],
         "vip": [_custom(["Covert", "Gloves", "Knife"], "Кастомный «Special Rare Case»", prefer_expensive=True)]},
    43: {"free": [_custom(["Classified", "Covert"], "Элитный Кастомный Кейс", prefer_expensive=True)], "vip": [_c(1500000)]},
    44: {"free": [_c(80000)], "vip": [_frame("animated_neon", "Анимированный Неон")]},
    45: {"free": [_vip(72, "VIP-статус (72 часа)")], "vip": [_nick("global_master", "Глобал Мастер")]},
    46: {"free": [_custom(["Covert"], "Случайный скин (Тайное)")], "vip": [_c(2000000)]},
    47: {"free": [_c(90000)],
         "vip": [_custom(["Gloves", "Knife"], "Кастомный «Ultra High-End Case»", prefer_expensive=True)]},
    48: {"free": [_custom(["Classified", "Covert"], "Финальный Разогревочный Кейс", prefer_expensive=True)],
         "vip": [_c(2500000)]},
    49: {"free": [_c(100000)],
         "vip": [_frame("pass_finalist", "Финалист Pass"), _c(3000000)]},
}

# ---- Финальный 50-й уровень: интерактивный сундук выбора (3 карточки,
# "стирание" защитного слоя на канвасе — реализуется на фронте, бэкенд
# только определяет пул наград для каждой ветки и сам факт выдачи). ----
FINAL_CHEST_LEVEL = 50
FINAL_CHEST_FREE_RARITIES = ["Covert"]
FINAL_CHEST_VIP_RARITIES = ["Knife", "Gloves"]
FINAL_CHEST_CARDS = 3


# ============================================
# Ежедневные задания
# ============================================
# Простая и честная схема без отдельной таблицы под каждый тип задания:
# прогресс каждого задания считается как разница ТЕКУЩЕГО игрового
# счётчика (User.total_cases_opened / User.xp — оба уже ведутся основной
# игрой) и его "снимка" на момент последнего ежедневного сброса
# (BattlePassProgress.daily_baseline_*, см. _maybe_reset_daily). Поэтому
# задания Пропуска не требуют собственного дублирующего учёта активности —
# они просто переиспользуют то, что игра и так считает.
DAILY_TASKS = [
    {"key": "checkin", "title": "Ежедневный вход", "description": "Просто зайди в Боевой пропуск сегодня",
     "xp": FREE_TASK_XP, "vip_only": False, "kind": "checkin"},
    {"key": "open_1_case", "title": "Открой 1 кейс", "description": "Открой любой кейс сегодня",
     "xp": FREE_TASK_XP, "vip_only": False, "kind": "cases", "target": 1},
    {"key": "open_3_cases", "title": "Открой 3 кейса", "description": "Открой любые 3 кейса сегодня",
     "xp": FREE_TASK_XP, "vip_only": False, "kind": "cases", "target": 3},
    {"key": "earn_50_xp", "title": "Заработай 50 XP", "description": "Получи 50 XP игровой активностью (кейсы, мини-игры и т.п.)",
     "xp": FREE_TASK_XP, "vip_only": False, "kind": "xp", "target": 50},
    {"key": "earn_150_xp", "title": "Заработай 150 XP", "description": "Получи 150 XP игровой активностью",
     "xp": FREE_TASK_XP, "vip_only": False, "kind": "xp", "target": 150},
    {"key": "open_5_cases_vip", "title": "VIP: Открой 5 кейсов", "description": "Открой любые 5 кейсов сегодня (только VIP Pass)",
     "xp": VIP_TASK_XP, "vip_only": True, "kind": "cases", "target": 5},
]
_TASKS_BY_KEY = {t["key"]: t for t in DAILY_TASKS}


# ============================================
# Вспомогательные функции
# ============================================
def _load_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _dump_json_list(items: list) -> str:
    return json.dumps(items)


async def _get_or_create_progress(session, user: User) -> BattlePassProgress:
    result = await session.execute(
        select(BattlePassProgress).where(BattlePassProgress.user_id == user.id)
    )
    progress = result.scalar_one_or_none()
    if not progress:
        progress = BattlePassProgress(
            user_id=user.id,
            daily_baseline_cases=user.total_cases_opened or 0,
            daily_baseline_xp=user.xp or 0,
            last_task_reset=datetime.datetime.utcnow().date(),
        )
        session.add(progress)
        await session.flush()
    return progress


def _maybe_reset_daily(progress: BattlePassProgress, user: User) -> bool:
    """Сбрасывает ежедневные задания при смене UTC-дня. Возвращает True,
    если произошёл сброс (вызывающий код должен закоммитить изменения)."""
    today = datetime.datetime.utcnow().date()
    if progress.last_task_reset == today:
        return False
    progress.last_task_reset = today
    progress.claimed_daily_tasks = "[]"
    progress.daily_baseline_cases = user.total_cases_opened or 0
    progress.daily_baseline_xp = user.xp or 0
    return True


def _add_pass_xp(progress: BattlePassProgress, amount: int) -> dict:
    """Начисляет XP пропуска и левелит игрока (макс. MAX_LEVEL, XP на
    последнем уровне не копится дальше — сундук 50 открывается один раз
    через отдельный флоу, а не автоматическим \"уровнем 51\")."""
    if amount <= 0 or progress.level >= MAX_LEVEL:
        return {"gained": 0, "levels_gained": 0}

    progress.xp = (progress.xp or 0) + amount
    levels_gained = 0
    while progress.level < MAX_LEVEL and progress.xp >= XP_PER_LEVEL:
        progress.xp -= XP_PER_LEVEL
        progress.level += 1
        levels_gained += 1

    if progress.level >= MAX_LEVEL:
        progress.xp = 0  # уровень 50 достигнут — прогресс-бар не копит лишнее

    return {"gained": amount, "levels_gained": levels_gained}


def _task_progress(task: dict, progress: BattlePassProgress, user: User) -> tuple[int, int]:
    """(текущий_прогресс, цель) для одного задания на СЕГОДНЯ."""
    if task["kind"] == "checkin":
        return 1, 1
    if task["kind"] == "cases":
        done = max(0, (user.total_cases_opened or 0) - (progress.daily_baseline_cases or 0))
        return min(done, task["target"]), task["target"]
    if task["kind"] == "xp":
        done = max(0, (user.xp or 0) - (progress.daily_baseline_xp or 0))
        return min(done, task["target"]), task["target"]
    return 0, 1


def _roll_custom_case_reward(rarities: list[str], prefer_expensive: bool) -> tuple[dict, float]:
    """Выбирает случайный предмет из глобального реестра items_data среди
    указанных редкостей (используется для \"кастомных\"/тематических
    наград Пропуска, которых нет как готовых кейсов в каталоге). Если
    prefer_expensive=True — выбор идёт только среди самых дорогих 20%
    предметов пула (для \"топовых\" наград типа Dragon Lore Chance Case /
    Ultra High-End Case), иначе — равномерно по всему пулу редкости.
    Возвращает (entry_из_items_data, итоговая_цена_в_💎)."""
    pool: list[dict] = []
    for r in rarities:
        pool.extend(items_data.ITEMS_BY_RARITY.get(r) or [])
    if not pool:
        pool = items_data.ALL_ITEMS

    if prefer_expensive:
        priced = sorted(pool, key=lambda it: main.get_base_price_rub(it["name"], it["rarity"]), reverse=True)
        top_n = max(3, len(priced) // 5)
        pool = priced[:top_n]

    entry = random.choice(pool)
    price = main.get_base_price_rub(entry["name"], entry["rarity"])
    return entry, price


def _roll_top_tier_reward(rarities: list[str], top_fraction: float) -> tuple[dict, float]:
    """Как _roll_custom_case_reward, но с настраиваемой долей самых дорогих
    предметов пула — используется финальным сундуком 50-го уровня, где
    градус \"редкости\" должен быть выше обычных наград дерева."""
    pool: list[dict] = []
    for r in rarities:
        pool.extend(items_data.ITEMS_BY_RARITY.get(r) or [])
    if not pool:
        pool = items_data.ALL_ITEMS

    priced = sorted(pool, key=lambda it: main.get_base_price_rub(it["name"], it["rarity"]), reverse=True)
    top_n = max(1, int(len(priced) * top_fraction))
    entry = random.choice(priced[:top_n])
    price = main.get_base_price_rub(entry["name"], entry["rarity"])
    return entry, price


async def _grant_item(session, user: User, entry: dict, price: float, source_label: str) -> dict:
    instance = main._instance_from_registry_item(entry, price)
    item_record = Inventory(
        user_id=user.id,
        skin_name=instance["name"],
        skin_price=instance["price"],
        rarity=instance["rarity"],
        quality=instance["quality"],
        stattrak=instance["stattrak"],
        float_val=instance["float_val"],
        image_url=instance["image"],
        obtained_from_case=source_label,
    )
    session.add(item_record)
    main._maybe_update_top_drop(user, instance)
    await session.flush()
    await session.refresh(item_record)
    return {
        "id": item_record.id,
        "name": instance["name"],
        "rarity": instance["rarity"],
        "quality": instance["quality"],
        "quality_name": instance["quality_name"],
        "price": instance["price"],
        "image": instance["image"],
        "stattrak": instance["stattrak"],
        "float_val": instance["float_val"],
    }


async def _apply_reward(session, user: User, reward: dict, source_label: str) -> dict:
    """Выдаёт ОДИН элемент награды (см. форматы в комментарии над
    REWARD_TREE) и возвращает JSON-сериализуемое описание того, что
    получил игрок — для показа во всплывающем окне на фронте."""
    rtype = reward["type"]

    if rtype == "crystals":
        user.balance = round((user.balance or 0.0) + reward["amount"], 2)
        return {"type": "crystals", "amount": reward["amount"], "new_balance": user.balance}

    if rtype == "case":
        case_key = reward["case_key"]
        if case_key not in main.CASES:
            raise HTTPException(500, f"Кейс '{case_key}' не найден в каталоге")
        # Кейсы каталога уже возвращают ПОЛНОСТЬЮ готовый экземпляр
        # (качество/float/StatTrak/цена) через roll_item — в отличие от
        # custom_case (там сначала выбирается предмет из глобального
        # реестра, а сам экземпляр катает _grant_item/_instance_from_registry_item),
        # здесь перекатывать что-либо второй раз не нужно: заносим в
        # инвентарь ровно то, что выдал roll_item.
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
            obtained_from_case=f"Battle Pass: {reward['label']}",
        )
        session.add(item_record)
        main._maybe_update_top_drop(user, drop)
        await session.flush()
        await session.refresh(item_record)
        return {"type": "case", "label": reward["label"], "item": {
            "id": item_record.id, "name": drop["name"], "rarity": drop["rarity"],
            "quality": drop["quality"], "quality_name": drop["quality_name"],
            "price": drop["price"], "image": drop["image"],
            "stattrak": drop["stattrak"], "float_val": drop["float_val"],
        }}

    if rtype == "custom_case":
        entry, price = _roll_custom_case_reward(reward["rarities"], reward.get("prefer_expensive", False))
        item = await _grant_item(session, user, entry, price, f"Battle Pass: {reward['label']}")
        return {"type": "custom_case", "label": reward["label"], "item": item}

    if rtype == "vip_time":
        now = datetime.datetime.utcnow()
        if user.is_vip and user.vip_expires_at is None:
            return {"type": "vip_time", "hours": reward["hours"], "already_permanent_vip": True}
        base = user.vip_expires_at if (user.is_vip and user.vip_expires_at and user.vip_expires_at > now) else now
        user.is_vip = True
        user.vip_expires_at = base + datetime.timedelta(hours=reward["hours"])
        return {"type": "vip_time", "hours": reward["hours"], "vip_expires_at": user.vip_expires_at.isoformat()}

    if rtype == "frame":
        unlocked = _load_json_list(user.unlocked_pass_frames)
        if reward["key"] not in unlocked:
            unlocked.append(reward["key"])
            user.unlocked_pass_frames = _dump_json_list(unlocked)
        return {"type": "frame", "key": reward["key"], "label": reward["label"]}

    if rtype == "nick_color":
        unlocked = _load_json_list(user.unlocked_pass_nick_colors)
        if reward["key"] not in unlocked:
            unlocked.append(reward["key"])
            user.unlocked_pass_nick_colors = _dump_json_list(unlocked)
        return {"type": "nick_color", "key": reward["key"], "label": reward["label"]}

    raise HTTPException(500, f"Неизвестный тип награды: {rtype}")


def _reward_preview(reward: dict) -> dict:
    """То же, что _apply_reward, но БЕЗ выдачи — только для превью в
    GET /api/pass/status (список наград дерева до клейма)."""
    rtype = reward["type"]
    if rtype == "crystals":
        return {"type": "crystals", "amount": reward["amount"]}
    if rtype == "case":
        return {"type": "case", "label": reward["label"]}
    if rtype == "custom_case":
        return {"type": "custom_case", "label": reward["label"]}
    if rtype == "vip_time":
        return {"type": "vip_time", "hours": reward["hours"], "label": reward["label"]}
    if rtype == "frame":
        return {"type": "frame", "key": reward["key"], "label": reward["label"]}
    if rtype == "nick_color":
        return {"type": "nick_color", "key": reward["key"], "label": reward["label"]}
    return {"type": rtype}


def _build_tree_payload(progress: BattlePassProgress) -> list[dict]:
    claimed_free = set(_load_json_list(progress.claimed_free_levels))
    claimed_vip = set(_load_json_list(progress.claimed_vip_levels))
    tree = []
    for level in range(1, MAX_LEVEL):
        entry = REWARD_TREE[level]
        tree.append({
            "level": level,
            "unlocked": progress.level >= level,
            "free_rewards": [_reward_preview(r) for r in entry["free"]],
            "vip_rewards": [_reward_preview(r) for r in entry["vip"]],
            "free_claimed": level in claimed_free,
            "vip_claimed": level in claimed_vip,
        })
    return tree


# ============================================
# GET /api/pass/status
# ============================================
@router.get("/api/pass/status")
async def pass_status(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        if _maybe_reset_daily(progress, user):
            await session.commit()
            await session.refresh(progress)

        return {
            "level": progress.level,
            "xp": progress.xp,
            "xp_needed": XP_PER_LEVEL if progress.level < MAX_LEVEL else 0,
            "max_level": MAX_LEVEL,
            "is_vip_pass": progress.is_vip_pass,
            "gold_balance": round(user.gold_balance or 0.0, 2),
            "vip_pass_price_gold": VIP_PASS_PRICE_GOLD,
            "level_skip_price_gold": LEVEL_SKIP_PRICE_GOLD,
            "tree": _build_tree_payload(progress),
            "final_chest": {
                "level": FINAL_CHEST_LEVEL,
                "unlocked": progress.level >= FINAL_CHEST_LEVEL,
                "cards": FINAL_CHEST_CARDS,
                "free_claimed": FINAL_CHEST_LEVEL in _load_json_list(progress.claimed_free_levels),
                "vip_claimed": FINAL_CHEST_LEVEL in _load_json_list(progress.claimed_vip_levels),
            },
            "selected_pass_frame": user.selected_frame,
            "selected_pass_nick_color": user.selected_pass_nick_color,
            "unlocked_pass_frames": _load_json_list(user.unlocked_pass_frames),
            "unlocked_pass_nick_colors": _load_json_list(user.unlocked_pass_nick_colors),
        }


# ============================================
# POST /api/pass/claim
# ============================================
class PassClaimRequest(BaseModel):
    telegram_id: int
    level: int
    track: str  # "free" | "vip"


@router.post("/api/pass/claim")
async def pass_claim(req: PassClaimRequest):
    if req.track not in ("free", "vip"):
        raise HTTPException(400, "track должен быть 'free' или 'vip'")
    if req.level < 1 or req.level >= MAX_LEVEL:
        raise HTTPException(400, f"Уровень должен быть от 1 до {MAX_LEVEL - 1} (50-й уровень — отдельный сундук)")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        _maybe_reset_daily(progress, user)

        if progress.level < req.level:
            raise HTTPException(400, "Этот уровень ещё не достигнут")
        if req.track == "vip" and not progress.is_vip_pass:
            raise HTTPException(403, "VIP Pass не куплен — эта награда недоступна")

        claimed_field = "claimed_free_levels" if req.track == "free" else "claimed_vip_levels"
        claimed = _load_json_list(getattr(progress, claimed_field))
        if req.level in claimed:
            raise HTTPException(400, "Награда этого уровня уже забрана")

        rewards = REWARD_TREE[req.level][req.track]
        results = [await _apply_reward(session, user, r, f"Уровень {req.level} ({req.track})") for r in rewards]

        claimed.append(req.level)
        setattr(progress, claimed_field, _dump_json_list(claimed))

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "level": req.level,
            "track": req.track,
            "rewards": results,
            "new_balance": user.balance,
            "gold_balance": round(user.gold_balance or 0.0, 2),
        }


# ============================================
# POST /api/pass/buy-vip
# ============================================
class TelegramIdRequest(BaseModel):
    telegram_id: int


@router.post("/api/pass/buy-vip")
async def pass_buy_vip(req: TelegramIdRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        if progress.is_vip_pass:
            raise HTTPException(400, "VIP Pass уже куплен")
        if (user.gold_balance or 0.0) < VIP_PASS_PRICE_GOLD:
            raise HTTPException(400, "Недостаточно 💰 Золота")

        user.gold_balance = round(user.gold_balance - VIP_PASS_PRICE_GOLD, 2)
        progress.is_vip_pass = True

        await session.commit()
        await session.refresh(user)

        return {"success": True, "is_vip_pass": True, "gold_balance": round(user.gold_balance or 0.0, 2)}


# ============================================
# POST /api/pass/skip-level
# ============================================
@router.post("/api/pass/skip-level")
async def pass_skip_level(req: TelegramIdRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        if progress.level >= MAX_LEVEL:
            raise HTTPException(400, "Пропуск уже полностью пройден (50 уровень)")
        if (user.gold_balance or 0.0) < LEVEL_SKIP_PRICE_GOLD:
            raise HTTPException(400, "Недостаточно 💰 Золота")

        user.gold_balance = round(user.gold_balance - LEVEL_SKIP_PRICE_GOLD, 2)
        progress.level += 1
        if progress.level >= MAX_LEVEL:
            progress.xp = 0

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "level": progress.level,
            "xp": progress.xp,
            "gold_balance": round(user.gold_balance or 0.0, 2),
        }


# ============================================
# GET /api/pass/daily-tasks
# ============================================
@router.get("/api/pass/daily-tasks")
async def pass_daily_tasks(telegram_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        if _maybe_reset_daily(progress, user):
            await session.commit()
            await session.refresh(progress)

        claimed_today = set(_load_json_list(progress.claimed_daily_tasks))

        tasks_payload = []
        for task in DAILY_TASKS:
            if task["vip_only"] and not progress.is_vip_pass:
                continue
            done, target = _task_progress(task, progress, user)
            tasks_payload.append({
                "key": task["key"],
                "title": task["title"],
                "description": task["description"],
                "xp": task["xp"],
                "progress": done,
                "target": target,
                "completed": done >= target,
                "claimed": task["key"] in claimed_today,
            })

        return {"tasks": tasks_payload, "level": progress.level, "xp": progress.xp}


# ============================================
# POST /api/pass/daily-task/claim
# ============================================
class DailyTaskClaimRequest(BaseModel):
    telegram_id: int
    task_key: str


@router.post("/api/pass/daily-task/claim")
async def pass_daily_task_claim(req: DailyTaskClaimRequest):
    task = _TASKS_BY_KEY.get(req.task_key)
    if not task:
        raise HTTPException(404, "Задание не найдено")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)
        _maybe_reset_daily(progress, user)

        if task["vip_only"] and not progress.is_vip_pass:
            raise HTTPException(403, "Это задание доступно только с VIP Pass")

        claimed_today = _load_json_list(progress.claimed_daily_tasks)
        if req.task_key in claimed_today:
            raise HTTPException(400, "Задание уже забрано сегодня")

        done, target = _task_progress(task, progress, user)
        if done < target:
            raise HTTPException(400, "Задание ещё не выполнено")

        claimed_today.append(req.task_key)
        progress.claimed_daily_tasks = _dump_json_list(claimed_today)
        xp_info = _add_pass_xp(progress, task["xp"])

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "task_key": req.task_key,
            "xp_gained": task["xp"],
            "level": progress.level,
            "xp": progress.xp,
            "levels_gained": xp_info["levels_gained"],
        }


# ============================================
# POST /api/pass/final-chest/reveal — 50-й уровень
# ============================================
class FinalChestRequest(BaseModel):
    telegram_id: int
    track: str  # "free" | "vip"
    card_index: int = 0  # какую из 3 карточек «стёр» игрок (для анимации/аналитики фронта)


@router.post("/api/pass/final-chest/reveal")
async def pass_final_chest_reveal(req: FinalChestRequest):
    if req.track not in ("free", "vip"):
        raise HTTPException(400, "track должен быть 'free' или 'vip'")
    if req.card_index < 0 or req.card_index >= FINAL_CHEST_CARDS:
        raise HTTPException(400, "Некорректный номер карточки")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        progress = await _get_or_create_progress(session, user)

        if progress.level < FINAL_CHEST_LEVEL:
            raise HTTPException(400, "50-й уровень ещё не достигнут")
        if req.track == "vip" and not progress.is_vip_pass:
            raise HTTPException(403, "VIP Pass не куплен — VIP-сундук недоступен")

        claimed_field = "claimed_free_levels" if req.track == "free" else "claimed_vip_levels"
        claimed = _load_json_list(getattr(progress, claimed_field))
        if FINAL_CHEST_LEVEL in claimed:
            raise HTTPException(400, "Финальный сундук этой ветки уже открыт")

        if req.track == "free":
            entry, price = _roll_top_tier_reward(FINAL_CHEST_FREE_RARITIES, top_fraction=0.15)
        else:
            entry, price = _roll_top_tier_reward(FINAL_CHEST_VIP_RARITIES, top_fraction=0.10)

        item = await _grant_item(session, user, entry, price, f"Battle Pass: Финальный сундук ({req.track})")

        claimed.append(FINAL_CHEST_LEVEL)
        setattr(progress, claimed_field, _dump_json_list(claimed))

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "track": req.track,
            "card_index": req.card_index,
            "item": item,
        }


# ============================================
# POST /api/pass/select-cosmetic — выбрать открытую рамку/цвет ника
# ============================================
# Награды frame/nick_color только ОТКРЫВАЮТ косметику (см. _apply_reward) —
# сам "выбранный сейчас" вариант отдельный и переключается здесь в любой
# момент между уже открытыми ключами (или сбрасывается на None). Рамка
# пишется в User.selected_frame — ту же колонку, что использует остальной
# профиль (единое поле "текущая рамка" независимо от источника награды);
# для цвета ника отдельного поля больше нигде нет, поэтому это единственный
# путь его сменить — User.selected_pass_nick_color.
class SelectCosmeticRequest(BaseModel):
    telegram_id: int
    kind: str          # "frame" | "nick_color"
    key: Optional[str] = None  # None -> снять текущий выбор


@router.post("/api/pass/select-cosmetic")
async def pass_select_cosmetic(req: SelectCosmeticRequest):
    if req.kind not in ("frame", "nick_color"):
        raise HTTPException(400, "kind должен быть 'frame' или 'nick_color'")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        unlocked_field = "unlocked_pass_frames" if req.kind == "frame" else "unlocked_pass_nick_colors"
        unlocked = _load_json_list(getattr(user, unlocked_field))
        if req.key is not None and req.key not in unlocked:
            raise HTTPException(400, "Эта косметика ещё не открыта Боевым пропуском")

        if req.kind == "frame":
            user.selected_frame = req.key
        else:
            user.selected_pass_nick_color = req.key

        await session.commit()

        return {
            "success": True,
            "kind": req.kind,
            "key": req.key,
            "selected_frame": user.selected_frame,
            "selected_pass_nick_color": user.selected_pass_nick_color,
        }
