# ============================================
# CS2 Case Simulator — синхронизация ПОЛНОГО каталога кейсов
# ============================================
#
# Разово (или по расписанию, например раз в неделю через cron) запусти:
#
#   pip install httpx --break-system-packages
#   python sync_cases.py
#
# Скрипт скачивает актуальный список ВСЕХ кейсов CS:GO/CS2 из открытого
# CS2 Items API (данные берутся из самой игры и раздаются с Steam CDN:
# https://github.com/ByMykel/CSGO-API), фильтрует только настоящие кейсы
# (type == "Case", т.е. без подарочных наборов/капсул с наклейками) и
# сохраняет их в cases_data.json рядом с этим файлом.
#
# cases_data.py при следующем запуске бэкенда автоматически подхватит
# cases_data.json и заменит им встроенный сид из 3 кейсов — правки кода
# не нужны.
#
# Каждый предмет в результате содержит настоящее имя, редкость и прямую
# HTTPS-ссылку на изображение со Steam CDN — ссылки не «выдуманы», а
# получены из официального каталога.

import json
import os
import sys

SOURCE_URL = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/crates.json"
OUT_FILE = os.path.join(os.path.dirname(__file__), "cases_data.json")

# Валвовская редкость -> наша внутренняя редкость
RARITY_MAP = {
    "rarity_common_weapon": "Consumer",
    "rarity_uncommon_weapon": "Industrial",
    "rarity_rare_weapon": "Mil-Spec",
    "rarity_mythical_weapon": "Restricted",
    "rarity_legendary_weapon": "Classified",
    "rarity_ancient_weapon": "Covert",
    # для ножей/перчаток Valve использует тот же "ancient", отличаем по имени
}

# Редкие предметы (ножи/перчатки) сохраняем ВСЕ, без обрезки — в кейсе
# реально может быть 5-20+ разных типов ножей/перчаток, и игрок должен
# видеть/выигрывать любой из них, а не только первый в списке API.
MAX_ITEMS_PER_RARITY = 8


def classify_rare(name: str) -> str:
    return "Gloves" if "Gloves" in name or "Wraps" in name else "Knife"


def transform_case(raw: dict) -> dict | None:
    if raw.get("type") != "Case":
        return None
    if not raw.get("contains") and not raw.get("contains_rare"):
        return None

    items = []
    by_rarity_count: dict[str, int] = {}

    for it in raw.get("contains", []):
        rarity_id = (it.get("rarity") or {}).get("id", "")
        rarity = RARITY_MAP.get(rarity_id)
        if not rarity or not it.get("image"):
            continue
        by_rarity_count.setdefault(rarity, 0)
        if by_rarity_count[rarity] >= MAX_ITEMS_PER_RARITY:
            continue
        by_rarity_count[rarity] += 1
        items.append({"name": it["name"], "rarity": rarity, "image": it["image"]})

    for it in raw.get("contains_rare", []):
        if not it.get("image"):
            continue
        rarity = classify_rare(it["name"])
        items.append({"name": it["name"], "rarity": rarity, "image": it["image"]})

    if not items:
        return None

    return {
        "name": raw["name"],
        "image": raw.get("image") or (raw.get("loot_list") or {}).get("image", ""),
        "items": items,
    }


def slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "_" for c in name)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def main():
    try:
        import httpx
    except ImportError:
        print("Нужен httpx: pip install httpx --break-system-packages")
        sys.exit(1)

    print(f"Скачиваю каталог кейсов: {SOURCE_URL}")
    resp = httpx.get(SOURCE_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw_crates = resp.json()

    cases = {}
    for raw in raw_crates:
        case = transform_case(raw)
        if not case:
            continue
        key = slugify(case["name"])
        # избегаем коллизий ключей
        base_key, i = key, 2
        while key in cases:
            key = f"{base_key}_{i}"
            i += 1
        cases[key] = case

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=1)

    print(f"Готово: {len(cases)} кейсов сохранено в {OUT_FILE}")


if __name__ == "__main__":
    main()
