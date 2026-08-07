# ============================================
# CS2 Case Simulator — клиент цен Steam Community Market
# ============================================
#
# Этот модуль сам по себе НИЧЕГО не запускает при старте бэкенда —
# он используется только офлайн-скриптом sync_prices.py (см. его докстринг),
# по той же схеме, что уже принята в проекте для sync_cases.py/sync_items.py:
# бэкенд просто подхватывает готовый JSON-файл с результатом (items_prices.json),
# а сам поход в сеть за реальными ценами делается ОТДЕЛЬНО, руками/по cron,
# на сервере с доступом в интернет.
#
# ИСТОЧНИК ЦЕН: официальный публичный (не требующий ключа/логина) эндпоинт
# Steam Community Market — /market/priceoverview/. Он отдаёт текущую цену
# площадки для конкретного market_hash_name (то же самое имя предмета,
# которое видно в самом Steam, включая степень износа и StatTrak™/Souvenir
# префиксы/суффиксы).
#
# ОГРАНИЧЕНИЯ ЭТОГО ПОДХОДА (честно, без прикрас):
#  - У Steam очень жёсткий анонимный рейт-лимит на этот эндпоинт (в среднем
#    один запрос в ~1.5 секунды до временной блокировки по IP на некоторое
#    время — если он всё же словится, скрипт просто ждёт дольше и продолжает).
#    Поэтому полная синхронизация ~1950 предметов реально занимает от
#    получаса до пары часов, и это НОРМАЛЬНО — не баг.
#  - Мы синхронизируем ОДНУ "якорную" цену на предмет (обычно Field-Tested
#    без StatTrak™, либо ближайшее доступное качество) — а не отдельную
#    цену на каждую из 5 степеней износа. Дальше в main.py эта якорная
#    цена масштабируется существующими коэффициентами QUALITY_PRICE_MULTIPLIER
#    / STATTRAK_MULTIPLIER (или отдельно засинканной StatTrak-ценой, если
#    удалось её получить — см. sync_prices.py). Это осознанный компромисс
#    между точностью и временем/нагрузкой синхронизации; если нужна цена
#    ПОЛНОСТЬЮ по каждому качеству отдельно — sync_prices.py можно запустить
#    с флагом --all-wears (медленнее в ~5 раз).
#  - Ножи/перчатки/редкие предметы иногда не имеют предложений на площадке
#    прямо сейчас (Steam возвращает success:false) — для них в
#    items_prices.json просто не будет цены, и бэкенд использует
#    консервативный fallback по редкости (см. FALLBACK_USD_BY_RARITY в main.py).

from __future__ import annotations

import asyncio
import re
import urllib.parse

import httpx

PRICE_URL = "https://steamcommunity.com/market/priceoverview/"
APPID_CS2 = 730

# Порядок степеней износа, в котором пробуем найти цену для "обычной"
# (не-StatTrak) якорной записи — начинаем с Field-Tested, потому что это
# самое ликвидное и репрезентативное качество для большинства скинов.
WEAR_PRIORITY = [
    "Field-Tested", "Minimal Wear", "Well-Worn", "Factory New", "Battle-Scarred",
]

_PRICE_RE = re.compile(r"[\d.,]+")


def _parse_money(text: str | None) -> float | None:
    """'$12.34', '12,34€', '1.234,56 pуб.' -> float. Возвращает None, если
    в строке нет числа (пустая цена/лот без предложений)."""
    if not text:
        return None
    match = _PRICE_RE.search(text)
    if not match:
        return None
    raw = match.group(0)
    # Нормализуем разделители тысяч/десятичных — Steam возвращает разный
    # формат в зависимости от locale валюты (currency=1 всегда USD с точкой,
    # так что это в основном подстраховка).
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def build_market_hash_name(base_name: str, wear: str | None, stattrak: bool, souvenir: bool = False) -> str:
    """Собирает точное имя лота, как оно называется в Steam Market.
    Примеры:
      ("AK-47 | Redline", "Field-Tested", False)  -> "AK-47 | Redline (Field-Tested)"
      ("AK-47 | Redline", "Field-Tested", True)   -> "StatTrak™ AK-47 | Redline (Field-Tested)"
      ("★ Karambit | Fade", "Factory New", False) -> "★ Karambit | Fade (Factory New)"
    Ножи/перчатки в нашем реестре уже хранятся с префиксом "★ " — Steam
    использует его же, поэтому дополнительной обработки не требуется.
    """
    prefix = "StatTrak™ " if stattrak else ("Souvenir " if souvenir else "")
    suffix = f" ({wear})" if wear else ""
    return f"{prefix}{base_name}{suffix}"


async def fetch_price_usd(client: httpx.AsyncClient, market_hash_name: str) -> float | None:
    """Один запрос цены к Steam Market. Возвращает lowest_price (или
    median_price как фолбэк) в USD, либо None, если предмета нет на
    площадке / у него нет активных предложений."""
    params = {
        "appid": APPID_CS2,
        "currency": 1,  # 1 = USD
        "market_hash_name": market_hash_name,
    }
    resp = await client.get(PRICE_URL, params=params, timeout=15)
    if resp.status_code == 429:
        raise RateLimited()
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        return None
    return _parse_money(data.get("lowest_price")) or _parse_money(data.get("median_price"))


class RateLimited(Exception):
    """Steam временно блокирует IP по анонимному рейт-лимиту — вызывающий
    код должен подождать существенно дольше обычной паузы между запросами."""


async def fetch_anchor_price(
    client: httpx.AsyncClient,
    base_name: str,
    wears: list[str] | None,
    stattrak_available: bool,
) -> dict:
    """Пытается найти якорную цену для предмета: сначала не-StatTrak по
    приоритету качеств (WEAR_PRIORITY, отфильтрованному по реально
    доступным для этого предмета качествам), затем — если у предмета
    вообще бывает StatTrak™ — то же самое для StatTrak-версии.
    Возвращает {"usd": float|None, "usd_stattrak": float|None, "wear_used": str|None}."""
    candidate_wears = [w for w in WEAR_PRIORITY if not wears or w in wears] or (wears or [None])

    usd = None
    wear_used = None
    for wear in candidate_wears:
        price = await fetch_price_usd(client, build_market_hash_name(base_name, wear, stattrak=False))
        if price:
            usd = price
            wear_used = wear
            break

    usd_stattrak = None
    if stattrak_available:
        for wear in candidate_wears:
            price = await fetch_price_usd(client, build_market_hash_name(base_name, wear, stattrak=True))
            if price:
                usd_stattrak = price
                break

    return {"usd": usd, "usd_stattrak": usd_stattrak, "wear_used": wear_used}


def wears_for_float_range(min_float: float, max_float: float) -> list[str]:
    """Переводит диапазон float предмета в список реально возможных для
    него степеней износа — так мы не тратим запросы на заведомо
    несуществующие качества (например, у многих ножей нет Battle-Scarred)."""
    ranges = [
        ("Factory New", 0.00, 0.07),
        ("Minimal Wear", 0.07, 0.15),
        ("Field-Tested", 0.15, 0.38),
        ("Well-Worn", 0.38, 0.45),
        ("Battle-Scarred", 0.45, 1.00),
    ]
    out = []
    for name, lo, hi in ranges:
        if max_float > lo and min_float < hi:
            out.append(name)
    return out or ["Field-Tested"]
