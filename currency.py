# ============================================
# CS2 Case Simulator — Мультивалютность (RUB / USD / UAH)
# ============================================
#
# ВАЖНО ПРО ЭКОНОМИКУ: базовой внутренней единицей расчёта в игре остаётся
# 💎 Кристалл, и 1 Кристалл = 1 Рубль (RUB) — это НЕ меняется. Баланс
# пользователя, цены в БД (Inventory.skin_price, списания за кейсы/крафт
# и т.д.) всегда хранятся и считаются в Кристаллах/рублях, как и раньше.
#
# Этот модуль отвечает ТОЛЬКО за то, во сколько долларов/гривен превращается
# рублёвая сумма для ОТОБРАЖЕНИЯ во фронтенде — переключатель валюты в
# WebApp меняет то, что игрок ВИДИТ, а не то, что реально списывается или
# начисляется на сервере (это гораздо безопаснее: округления/колебания
# курса никогда не создадут рассинхрон между тем, что показано, и тем,
# что реально в базе).
#
# Курс подтягивается с открытого бесплатного API (exchangerate-api через
# open.er-api.com, ключ не нужен) раз в CACHE_TTL_SECONDS и кэшируется в
# памяти процесса. Если сети нет (как в песочнице, где собирался этот код)
# или API недоступен — используются FALLBACK_RATES ниже, чтобы курс
# валют в интерфейсе не переставал работать. Обнови FALLBACK_RATES вручную,
# если хочешь держать разумный курс "по умолчанию" даже без сети.

from __future__ import annotations

import time
import asyncio
import logging

import httpx

log = logging.getLogger("currency")

SUPPORTED_CURRENCIES = ("RUB", "USD", "UAH")

# Сколько единиц валюты за 1 Рубль (RUB всегда 1.0 — это базовая единица,
# равная 1 Кристаллу). Значения ниже — ориентировочные (актуальны на
# момент написания кода, начало 2026), используются только пока не
# пришёл первый успешный ответ от API или если сеть недоступна.
FALLBACK_RATES: dict[str, float] = {
    "RUB": 1.0,
    "USD": 1 / 90.0,   # ≈ 90 ₽ за $1
    "UAH": 1 / 2.2,     # ≈ 2.2 ₽ за 1 ₴ (≈ 41 ₴ за $1)
}

CACHE_TTL_SECONDS = 6 * 60 * 60  # обновляем курс раз в 6 часов
SOURCE_URL = "https://open.er-api.com/v6/latest/RUB"

_state = {
    "rates": dict(FALLBACK_RATES),
    "updated_at": 0.0,
    "source": "fallback",
}


async def refresh_rates(force: bool = False) -> dict[str, float]:
    """Обновляет курс RUB->USD/UAH из открытого API. Тихо откатывается на
    FALLBACK_RATES при любой ошибке сети/парсинга — вызывающий код
    (currency-эндпоинт, расчёт цен) никогда не падает из-за отсутствия
    интернета или недоступности стороннего сервиса."""
    now = time.time()
    if not force and (now - _state["updated_at"]) < CACHE_TTL_SECONDS:
        return _state["rates"]

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(SOURCE_URL)
            resp.raise_for_status()
            data = resp.json()
        rates = data.get("rates") or {}
        usd = rates.get("USD")
        uah = rates.get("UAH")
        if not usd or not uah:
            raise ValueError("Ответ API не содержит нужных курсов USD/UAH")

        _state["rates"] = {"RUB": 1.0, "USD": float(usd), "UAH": float(uah)}
        _state["updated_at"] = now
        _state["source"] = "live"
        log.info("Курс валют обновлён: %s", _state["rates"])
    except Exception as exc:  # noqa: BLE001 — любая ошибка сети/парсинга не критична
        log.warning("Не удалось обновить курс валют (%s), используем предыдущий/fallback", exc)
        # Не трогаем _state["rates"], если он уже был обновлён живыми
        # данными раньше — только откатываемся на fallback при самом
        # первом запуске, если live-курса ещё не было вообще.
        if _state["source"] == "fallback" and _state["updated_at"] == 0.0:
            _state["rates"] = dict(FALLBACK_RATES)

    return _state["rates"]


def get_rates() -> dict[str, float]:
    """Синхронный доступ к последнему закэшированному курсу (для расчёта
    цен внутри синхронных функций main.py — без сети, без await)."""
    return _state["rates"]


def rub_to(amount_rub: float, target_currency: str) -> float:
    """Конвертирует сумму из Кристаллов/₽ в целевую валюту для отображения."""
    rate = _state["rates"].get(target_currency)
    if rate is None:
        rate = FALLBACK_RATES.get(target_currency, 1.0)
    return amount_rub * rate


def usd_to_rub(amount_usd: float) -> float:
    """Конвертирует сумму в USD (например, реальную цену скина со Steam
    Market) в Кристаллы/₽ — используется при построении внутриигровых цен
    предметов из синхронизированных со Steam данных."""
    usd_rate = _state["rates"].get("USD") or FALLBACK_RATES["USD"]
    if usd_rate <= 0:
        return 0.0
    return amount_usd / usd_rate


async def periodic_refresh() -> None:
    """Фоновая задача: первое обновление сразу при старте сервера, затем
    каждые CACHE_TTL_SECONDS. Запускается один раз из main.py startup_event
    через asyncio.create_task — не блокирует старт сервера, если сети
    временно нет (первая попытка просто тихо откатится на fallback)."""
    while True:
        await refresh_rates()
        await asyncio.sleep(CACHE_TTL_SECONDS)
