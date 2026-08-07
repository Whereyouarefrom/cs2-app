# ============================================
# CS2 Case Simulator — Глобальный реестр предметов
# ============================================
#
# Этот модуль — ЕДИНЫЙ источник правды по ВСЕМ скинам игры (не только тем,
# что реально лежат в кейсах). Он нужен, чтобы Апгрейдер мог предложить
# игроку в качестве цели буквально любой скин CS2 — винтовку, пистолет,
# ПП, тяжёлое оружие, нож, перчатки или экипировку, — даже если этого
# скина нет ни в одном кейсе каталога.
#
# ИСТОЧНИК ДАННЫХ (имя / категория / редкость / StatTrak / Сувенир /
# диапазон float): бандл `items_source.txt` рядом с этим файлом — это
# копия присланного списка (~1954 предмета), собранного из wiki.cs.money
# и открытой базы ByMykel/CSGO-API.
#
# ИЗОБРАЖЕНИЯ (прямые ссылки Steam CDN): сам TXT-список ссылок на картинки
# не содержит (только текстовые характеристики), поэтому реальные ссылки
# подтягиваются в порядке приоритета:
#   1) уже проверенные изображения из cases_data.py/cases_data.json —
#      это реальные предметы, которые встречаются в кейсах каталога;
#   2) items_images.json (опционально) — генерируется скриптом
#      sync_items.py (см. его докстринг) при запуске С ДОСТУПОМ В
#      ИНТЕРНЕТ: он скачивает актуальный каталог скинов из открытого
#      CS2 Items API (ByMykel/CSGO-API) и сохраняет пары "имя -> прямая
#      ссылка Steam CDN" для ВСЕХ предметов;
#   3) если ни (1), ни (2) не дали реальной ссылки — используется
#      локальная SVG-заглушка (data:), окрашенная в цвет редкости
#      предмета. Это ЧЕСТНО: подделывать несуществующие ссылки Steam CDN
#      мы не будем — до первого запуска sync_items.py такие предметы
#      просто выглядят как цветной силуэт вместо фото, но полностью
#      рабочие (выбираются, апгрейдятся, продаются) уже сейчас.
#
# Один раз (или по расписанию) на сервере С ДОСТУПОМ В ИНТЕРНЕТ выполни:
#   pip install httpx --break-system-packages
#   python sync_items.py
# после этого практически все предметы получат настоящие фото со Steam CDN.

from __future__ import annotations

import base64
import os
import json
import re
from functools import lru_cache

_HERE = os.path.dirname(__file__)
_SOURCE_FILE = os.path.join(_HERE, "items_source.txt")
_IMAGES_FILE = os.path.join(_HERE, "items_images.json")  # генерируется sync_items.py
_PRICES_FILE = os.path.join(_HERE, "items_prices.json")  # генерируется sync_prices.py (реальные цены Steam Market)

# ---------------------------------------------------------------
# Маппинг категории из TXT в короткий внутренний код
# ---------------------------------------------------------------
_CATEGORY_MAP = {
    "ВИНТОВКИ (RIFLES)": "Rifles",
    "ПИСТОЛЕТЫ (PISTOLS)": "Pistols",
    "ПИСТОЛЕТ-ПУЛЕМЁТЫ (SMGs)": "SMGs",
    "ТЯЖЁЛОЕ ОРУЖИЕ (HEAVY)": "Heavy",
    "НОЖИ (KNIVES)": "Knives",
    "ПЕРЧАТКИ (GLOVES)": "Gloves",
    "ЭКИПИРОВКА (EQUIPMENT)": "Equipment",
}

# Редкость, как она записана в TXT ("Редкость: ...") -> внутренняя
# редкость движка (см. RARITY_ORDER в main.py). Ножи и перчатки — особый
# случай: Valve хранит их с редкостью "Extraordinary"/"Covert"/"Contraband",
# но у нас они всегда попадают в отдельные топ-редкости "Knife"/"Gloves"
# независимо от того, что написано в TXT (это и определяет их категория).
_RARITY_MAP = {
    "Consumer Grade": "Consumer",
    "Industrial Grade": "Industrial",
    "Mil-Spec Grade": "Mil-Spec",
    "Restricted": "Restricted",
    "Classified": "Classified",
    "Covert": "Covert",
    "Contraband": "Covert",       # редчайшие "запрещённые" скины (напр. Howl) — приравниваем к Covert
    "Extraordinary": "Covert",    # фолбэк, реально перекрывается категорией ниже
}

_LINE_HEADER_RE = re.compile(r"^--- (.+?) \(\d+\) ---$")
_LINE_META_RE = re.compile(
    r"StatTrak:\s*(\S+)\s*\|\s*Сувенир:\s*(\S+)\s*\|\s*Редкость:\s*(.+)$"
)
_LINE_FLOAT_RE = re.compile(r"Диапазон float:\s*([\d.]+)-([\d.]+)")


def _resolve_rarity(category: str, rarity_raw: str | None) -> str:
    if category == "Knives":
        return "Knife"
    if category == "Gloves":
        return "Gloves"
    return _RARITY_MAP.get(rarity_raw or "", "Mil-Spec")


def _parse_source() -> list[dict]:
    """Парсит items_source.txt в плоский список предметов."""
    if not os.path.exists(_SOURCE_FILE):
        return []

    with open(_SOURCE_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    items: list[dict] = []
    category = None
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        header = _LINE_HEADER_RE.match(line.strip())
        if header:
            category = _CATEGORY_MAP.get(header.group(1), header.group(1))
            i += 1
            continue

        if category and line.strip() and "|" in line and not line.startswith("    "):
            name = line.strip()
            stattrak_available = False
            souvenir_available = False
            rarity_raw = None
            min_float, max_float = 0.0, 1.0

            if i + 1 < n and lines[i + 1].lstrip().startswith("StatTrak"):
                meta = _LINE_META_RE.search(lines[i + 1])
                if meta:
                    stattrak_available = meta.group(1).strip() == "Да"
                    souvenir_available = meta.group(2).strip() == "Да"
                    rarity_raw = meta.group(3).strip()
            if i + 2 < n:
                fl = _LINE_FLOAT_RE.search(lines[i + 2])
                if fl:
                    min_float, max_float = float(fl.group(1)), float(fl.group(2))

            rarity = _resolve_rarity(category, rarity_raw)
            items.append({
                "name": name,
                "category": category,
                "rarity": rarity,
                "stattrak_available": stattrak_available and rarity != "Gloves",
                "souvenir_available": souvenir_available,
                "min_float": min_float,
                "max_float": max_float,
            })
            i += 3
            continue
        i += 1

    return items


# ---------------------------------------------------------------
# Изображения: сборка карты "имя предмета -> прямая ссылка Steam CDN"
# из уже проверенных источников в проекте.
# ---------------------------------------------------------------
def _known_images_from_cases() -> dict[str, str]:
    try:
        from cases_data import CASES
    except Exception:
        return {}
    out: dict[str, str] = {}
    for case in CASES.values():
        for it in case.get("items", []):
            if it.get("image"):
                out.setdefault(it["name"], it["image"])
    return out


def _known_images_from_sync() -> dict[str, str]:
    if not os.path.exists(_IMAGES_FILE):
        return {}
    try:
        with open(_IMAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, str) and v}
    except Exception:
        pass
    return {}


def _known_prices_from_sync() -> dict[str, dict]:
    """Реальные цены Steam Market (в USD), сгенерированные sync_prices.py.
    Формат записи: {"usd": float, "usd_stattrak": float|None, "wear_used": str|None}.
    Пока файла нет (или он ещё не полный) — просто пустой словарь, и все
    предметы честно используют fallback-оценку по редкости в main.py
    (никаких выдуманных цен здесь не подставляется)."""
    if not os.path.exists(_PRICES_FILE):
        return {}
    try:
        with open(_PRICES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


# Цвета редкости — совпадают с --rarity-* переменными в style.css, чтобы
# заглушка выглядела органично рядом с настоящими фото.
_RARITY_COLOR = {
    "Consumer": "b0c3d9", "Industrial": "5e98d9", "Mil-Spec": "4b69ff",
    "Restricted": "8847ff", "Classified": "d32ce6", "Covert": "eb4b4b",
    "Knife": "ffd700", "Gloves": "e4ae39",
}
_CATEGORY_GLYPH = {
    "Rifles": "R", "Pistols": "P", "SMGs": "S", "Heavy": "H",
    "Knives": "★", "Gloves": "G", "Equipment": "E",
}


@lru_cache(maxsize=None)
def _placeholder_image(rarity: str, category: str) -> str:
    """Локальная SVG-заглушка (data: URI) — используется ТОЛЬКО пока для
    предмета ещё не найдена настоящая ссылка Steam CDN (см. докстринг
    модуля). Ничего не выдумываем — просто честно окрашенный силуэт."""
    color = _RARITY_COLOR.get(rarity, "8b93a1")
    glyph = _CATEGORY_GLYPH.get(category, "?")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="96">'
        f'<rect width="128" height="96" rx="10" fill="#1b222c"/>'
        f'<rect x="3" y="3" width="122" height="90" rx="8" fill="none" '
        f'stroke="#{color}" stroke-width="2" stroke-opacity="0.55"/>'
        f'<text x="64" y="58" font-size="34" text-anchor="middle" '
        f'font-family="Arial" fill="#{color}">{glyph}</text>'
        "</svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def _build_registry() -> tuple[list[dict], dict[str, dict], dict[str, list[dict]]]:
    raw_items = _parse_source()
    images = _known_images_from_cases()
    images.update(_known_images_from_sync())  # sync-данные приоритетнее
    prices = _known_prices_from_sync()

    all_items: list[dict] = []
    by_name: dict[str, dict] = {}
    by_rarity: dict[str, list[dict]] = {}

    seen_names: set[str] = set()
    for raw in raw_items:
        name = raw["name"]
        if name in seen_names:
            continue  # на случай дублей в исходном списке
        seen_names.add(name)

        image = images.get(name)
        has_real_image = bool(image)
        if not image:
            image = _placeholder_image(raw["rarity"], raw["category"])

        price_entry = prices.get(name) or {}

        item = {
            **raw,
            "image": image,
            "has_real_image": has_real_image,
            # Реальная цена со Steam Market (USD), если sync_prices.py уже
            # был запущен и нашёл предложения на площадке для этого
            # предмета — иначе None, и main.py сам подставит консервативный
            # fallback по редкости при расчёте внутриигровой цены.
            "usd_price": price_entry.get("usd"),
            "usd_price_stattrak": price_entry.get("usd_stattrak"),
            "has_real_price": price_entry.get("usd") is not None,
        }
        all_items.append(item)
        by_name[name] = item
        by_rarity.setdefault(raw["rarity"], []).append(item)

    return all_items, by_name, by_rarity


ALL_ITEMS, ITEMS_BY_NAME, ITEMS_BY_RARITY = _build_registry()


def get_item(name: str) -> dict | None:
    return ITEMS_BY_NAME.get(name)


def search_items(query: str, limit: int = 30) -> list[dict]:
    """Поиск целевого скина для Апгрейдера по подстроке имени
    (регистронезависимо). Пустой запрос -> первые `limit` предметов."""
    query = (query or "").strip().lower()
    if not query:
        results = ALL_ITEMS[:limit]
    else:
        results = [it for it in ALL_ITEMS if query in it["name"].lower()][:limit]
    return results


def stats() -> dict:
    """Для дебага/README: сколько предметов реально имеют фото со Steam CDN
    и сколько получили реальную цену Steam Market (после sync_prices.py)."""
    total = len(ALL_ITEMS)
    real_image = sum(1 for it in ALL_ITEMS if it["has_real_image"])
    real_price = sum(1 for it in ALL_ITEMS if it["has_real_price"])
    return {
        "total": total,
        "with_real_image": real_image,
        "placeholder": total - real_image,
        "with_real_price": real_price,
        "price_fallback": total - real_price,
    }
