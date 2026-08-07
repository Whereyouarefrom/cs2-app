# ============================================
# CS2 Case Simulator — синхронизация РЕАЛЬНЫХ цен со Steam Market
# ============================================
#
# Как и sync_cases.py / sync_items.py, этот скрипт нужно запускать РУКАМИ
# (или по cron, например раз в неделю) НА СЕРВЕРЕ С ДОСТУПОМ В ИНТЕРНЕТ —
# песочница, в которой писался этот код, доступа к steamcommunity.com не
# имеет, поэтому реальные цены здесь не зашиты, только рабочая логика их
# получения:
#
#   pip install httpx --break-system-packages
#   python sync_prices.py                # полная синхронизация всех предметов
#   python sync_prices.py --limit 50      # тестовый прогон на первых 50
#   python sync_prices.py --resume        # продолжить прерванный прогон
#
# Результат сохраняется в items_prices.json рядом с этим файлом в виде
#   { "AK-47 | Redline": {"usd": 12.5, "usd_stattrak": 45.0, "wear_used": "Field-Tested"}, ... }
# items_data.py при следующем запуске бэкенда автоматически подхватит этот
# файл и подставит реальные цены вместо fallback-оценки по редкости —
# правки кода не нужны.
#
# ВАЖНО ПРО СКОРОСТЬ: у Steam Market очень строгий анонимный рейт-лимит на
# priceoverview — скрипт держит паузу ~1.5с между запросами и увеличивает
# её при 429-ответах. Полный прогон по ~1950 предметам реально занимает
# от 30 минут до пары часов — это нормально, не баг. Скрипт сохраняет
# промежуточный результат каждые SAVE_EVERY предметов, поэтому его можно
# спокойно прервать (Ctrl+C) и продолжить позже флагом --resume.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

_HERE = os.path.dirname(__file__)
OUT_FILE = os.path.join(_HERE, "items_prices.json")

DELAY_BETWEEN_REQUESTS = 1.5   # секунды, базовая пауза между запросами к Steam
RATE_LIMIT_BACKOFF = 60.0      # секунды ожидания при 429 перед повтором
SAVE_EVERY = 25                # сохранять items_prices.json каждые N обработанных предметов


def _load_existing() -> dict:
    if not os.path.exists(OUT_FILE):
        return {}
    try:
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_FILE)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Синхронизация реальных цен Steam Market")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить количество предметов (для теста)")
    parser.add_argument("--resume", action="store_true", help="Пропустить предметы, уже сохранённые в items_prices.json")
    parser.add_argument("--delay", type=float, default=DELAY_BETWEEN_REQUESTS, help="Пауза между запросами, сек")
    args = parser.parse_args()

    try:
        import httpx
    except ImportError:
        print("Нужен httpx: pip install httpx --break-system-packages")
        sys.exit(1)

    import steam_prices
    import items_data

    items = list(items_data.ALL_ITEMS)
    if args.limit:
        items = items[: args.limit]

    results = _load_existing() if args.resume else {}
    if args.resume:
        items = [it for it in items if it["name"] not in results]
        print(f"--resume: пропускаю уже засинканные, осталось {len(items)} предметов")

    print(f"Всего к обработке: {len(items)} предметов. Пауза между запросами: {args.delay}с")
    print("Это ДОЛГО (может занять от получаса до пары часов) — так и должно быть, см. докстринг файла.\n")

    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        processed = 0
        for it in items:
            name = it["name"]
            wears = steam_prices.wears_for_float_range(it.get("min_float", 0.0), it.get("max_float", 1.0))
            stattrak_available = bool(it.get("stattrak_available"))

            delay = args.delay
            for attempt in range(5):
                try:
                    price_info = await steam_prices.fetch_anchor_price(client, name, wears, stattrak_available)
                    break
                except steam_prices.RateLimited:
                    print(f"  [429] Рейт-лимит Steam, жду {RATE_LIMIT_BACKOFF}с и пробую снова...")
                    await asyncio.sleep(RATE_LIMIT_BACKOFF)
                    delay = max(delay, RATE_LIMIT_BACKOFF / 10)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [!] {name}: ошибка запроса ({exc}), повтор через {delay}с")
                    await asyncio.sleep(delay)
                    price_info = {"usd": None, "usd_stattrak": None, "wear_used": None}
            else:
                price_info = {"usd": None, "usd_stattrak": None, "wear_used": None}

            if price_info.get("usd") is not None:
                results[name] = {
                    "usd": round(price_info["usd"], 4),
                    "usd_stattrak": round(price_info["usd_stattrak"], 4) if price_info.get("usd_stattrak") else None,
                    "wear_used": price_info.get("wear_used"),
                }
                print(f"  {name}: ${price_info['usd']:.2f}" + (f" (StatTrak: ${price_info['usd_stattrak']:.2f})" if price_info.get("usd_stattrak") else ""))
            else:
                print(f"  {name}: цена не найдена (нет предложений на площадке)")

            processed += 1
            if processed % SAVE_EVERY == 0:
                _save(results)
                print(f"  -- промежуточное сохранение: {processed}/{len(items)} --")

            await asyncio.sleep(delay)

    _save(results)
    matched = len(results)
    total = len(items_data.ALL_ITEMS)
    print(f"\nГотово: {matched}/{total} предметов получили реальную цену Steam Market")
    print(f"Сохранено в {OUT_FILE}")
    if matched < total:
        print(
            "Часть предметов (обычно самые редкие/новые скины без активных "
            "лотов на площадке) осталась без цены — для них бэкенд использует "
            "консервативный fallback по редкости (FALLBACK_USD_BY_RARITY в main.py)."
        )


if __name__ == "__main__":
    asyncio.run(main())
