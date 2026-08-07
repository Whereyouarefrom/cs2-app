# ============================================
# CS2 Case Simulator — синхронизация РЕАЛЬНЫХ фото для ВСЕХ предметов
# ============================================
#
# items_data.py уже прекрасно работает без этого скрипта: он строит полный
# реестр из ~1954 предметов (items_source.txt) и подставляет проверенные
# фото там, где скин также встречается в одном из кейсов каталога — а для
# всех остальных использует честную SVG-заглушку, окрашенную в цвет
# редкости, вместо выдуманной ссылки.
#
# Этот скрипт закрывает оставшийся пробел: разово (или по расписанию,
# например раз в неделю через cron) запусти НА СЕРВЕРЕ С ДОСТУПОМ В
# ИНТЕРНЕТ (песочница, в которой собирался этот код, интернета не имеет,
# поэтому здесь список каждой ссылки не забит руками — только логика их
# получения):
#
#   pip install httpx --break-system-packages
#   python sync_items.py
#
# Скрипт скачивает открытый каталог скинов CS2 (ByMykel/CSGO-API,
# https://github.com/ByMykel/CSGO-API — данные берутся из файлов самой
# игры и раздаются с Steam/GitHub CDN), сопоставляет каждую запись с
# нашим items_source.txt ПО ТОЧНОМУ ИМЕНИ ("AK-47 | Redline",
# "★ Karambit | Fade" и т.п.) и сохраняет пары имя -> прямая ссылка на
# картинку в items_images.json рядом с этим файлом.
#
# items_data.py при следующем запуске бэкенда автоматически подхватит
# items_images.json (если он есть) и заменит им SVG-заглушки — правки
# кода не нужны.

import json
import os
import sys

SOURCE_URL = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/skins.json"
OUT_FILE = os.path.join(os.path.dirname(__file__), "items_images.json")
SOURCE_TXT = os.path.join(os.path.dirname(__file__), "items_source.txt")


def _known_names() -> set[str]:
    """Имена из items_source.txt — сверяемся с ними, чтобы не тащить в
    items_images.json тысячи посторонних записей (агенты, наклейки и т.д.,
    которых нет в нашем реестре)."""
    names = set()
    if not os.path.exists(SOURCE_TXT):
        return names
    with open(SOURCE_TXT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and "|" in line and not line.startswith(("StatTrak", "Качество", "---")):
                names.add(line)
    return names


def main():
    try:
        import httpx
    except ImportError:
        print("Нужен httpx: pip install httpx --break-system-packages")
        sys.exit(1)

    wanted = _known_names()
    print(f"В items_source.txt найдено {len(wanted)} предметов для сопоставления")

    print(f"Скачиваю каталог скинов: {SOURCE_URL}")
    resp = httpx.get(SOURCE_URL, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    raw_skins = resp.json()

    images: dict[str, str] = {}
    for entry in raw_skins:
        name = entry.get("name")
        image = entry.get("image")
        if not name or not image:
            continue
        if wanted and name not in wanted:
            continue
        images[name] = image

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(images, f, ensure_ascii=False, indent=1)

    matched = len(images)
    total = len(wanted) or matched
    print(f"Готово: {matched}/{total} предметов получили реальную ссылку Steam CDN")
    print(f"Сохранено в {OUT_FILE}")
    if matched < total:
        print(
            "Часть предметов (обычно самые новые/редкие коллекции) может "
            "отсутствовать в открытом каталоге — для них items_data.py "
            "продолжит показывать SVG-заглушку."
        )


if __name__ == "__main__":
    main()
