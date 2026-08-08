# ============================================
# CS2 Case Simulator — индивидуализированный fallback по ценам
# ============================================
#
# ПРОБЛЕМА, которую решает этот модуль (ПРАВКИ В ТЗ №1, п.1):
# Раньше FALLBACK_USD_BY_RARITY в main.py давал ОДНО плоское число на всю
# редкость — то есть "★ Karambit | Doppler" и "★ Gut Knife | Safari Mesh"
# (оба Knife) получали одну и ту же базовую цену $350, и различались
# только случайным качеством/StatTrak в диапазоне 0.62x-2.97x. Из-за этого
# ВСЕ ножи в игре выглядели "одинаково дорогими" — именно баг из ТЗ
# (диапазон 19 530 – 51 975 у любого ножа).
#
# Этот модуль ДО реального похода в Steam Market (sync_prices.py) даёт
# честную индивидуальную оценку по имени предмета — конкретному типу ножа/
# перчаток и конкретному паттерну/фазе — на основе публично известных
# ценовых уровней Steam Community Market:
#
#   Дешёвые ножи/перчатки   (Gut, Navaja, Shadow Daggers, Hand Wraps, ...):  $80  – $180
#   Средние ножи/перчатки   (Flip, Huntsman, Bowie, Talon, Ursus, ...):      $200 – $500
#   Топовые ножи/перчатки   (Karambit, Butterfly, M9 Bayonet, Sport, ...):   $700 – $2 600+
#
# Как только для конкретного имени появится реальная цена в items_prices.json
# (после запуска sync_prices.py) — main.get_base_price_rub() всегда
# предпочитает её и в этот модуль вообще не заходит. Всё ниже — ТОЛЬКО
# консервативный, но уже НЕ плоский fallback.

from __future__ import annotations

import hashlib

# ---------------------------------------------------------------
# Ценовые диапазоны (USD) по тиру. Число ниже — это "якорная" цена ДО
# применения QUALITY_PRICE_MULTIPLIER / STATTRAK_MULTIPLIER из main.py
# (та же роль, что и раньше у FALLBACK_USD_BY_RARITY), поэтому итоговая
# цена конкретного экземпляра всё ещё колеблется вокруг этого якоря на
# 0.62x-2.97x в зависимости от качества/StatTrak — как и для обычных
# скинов.
# ---------------------------------------------------------------
CHEAP_BAND = (80.0, 180.0)
MID_BAND = (200.0, 500.0)
TOP_BAND = (1000.0, 8000.0)

# ---------------------------------------------------------------
# Тиры по БАЗОВОМУ ТИПУ ножа (часть имени до " | "). Явно перечисленные в
# ТЗ типы сохранены как есть; остальные типы каталога CS2 расставлены по
# их реальному ценовому уровню на Steam Market.
# ---------------------------------------------------------------
KNIFE_CHEAP_TYPES = {
    "Gut Knife", "Navaja Knife", "Shadow Daggers",
    "Classic Knife", "Paracord Knife", "Survival Knife",
}
KNIFE_MID_TYPES = {
    "Flip Knife", "Huntsman Knife", "Bowie Knife", "Talon Knife", "Ursus Knife",
    "Falchion Knife", "Kukri Knife", "Nomad Knife", "Stiletto Knife", "Skeleton Knife",
}
KNIFE_TOP_TYPES = {
    "Karambit", "Butterfly Knife", "M9 Bayonet", "Bayonet",
}

# ---------------------------------------------------------------
# Тиры по МОДЕЛИ перчаток. В ТЗ явно упомянут только "Safari Mesh" —
# это на самом деле паттерн ножей, а не модель перчаток, поэтому для
# самих перчаток тиры расставлены по их реальному ценовому уровню:
# Hand Wraps исторически самые дешёвые перчатки в игре, Sport/Specialist —
# стабильно самые дорогие.
# ---------------------------------------------------------------
GLOVES_CHEAP_TYPES = {"Hand Wraps", "Bloodhound Gloves"}
GLOVES_MID_TYPES = {"Driver Gloves", "Moto Gloves", "Hydra Gloves", "Broken Fang Gloves"}
GLOVES_TOP_TYPES = {"Sport Gloves", "Specialist Gloves"}

# ---------------------------------------------------------------
# "Желательность" паттерна/фазы (0..1) — насколько дорогим он обычно
# выглядит на площадке относительно других фазей ТОГО ЖЕ типа ножа/
# перчаток. Список собран по общеизвестным ценовым лидерам/аутсайдерам
# Steam Market (Doppler/Gamma Doppler/Marble Fade/Lore — топ; Safari Mesh/
# Forest DDPAT/Scorched/Urban Masked — низ). Паттерн, которого нет в
# словаре (в т.ч. новые/непопулярные фазы), получает средний вес 0.45.
# ---------------------------------------------------------------
FINISH_DESIRABILITY: dict[str, float] = {
    # топ
    "Lore": 1.00, "Gamma Doppler": 0.95, "Doppler": 0.90, "Marble Fade": 0.88,
    "Fade": 0.83, "Autotronic": 0.80, "Tiger Tooth": 0.78, "Pandora's Box": 0.97,
    "Vice": 0.90, "Omega": 0.75, "Nocts": 0.70, "Emerald": 0.72,
    "Rezan the Red": 0.68, "Crimson Kimono": 0.80, "King Snake": 0.60,
    # средне-высокие
    "Damascus Steel": 0.65, "Crimson Web": 0.62, "Black Laminate": 0.58,
    "Case Hardened": 0.55, "Slaughter": 0.50, "Emerald Web": 0.62,
    "Bright Water": 0.48, "Freehand": 0.46, "Convoy": 0.50, "Snow Leopard": 0.55,
    # низкие
    "Blue Steel": 0.35, "Ultraviolet": 0.32, "Night": 0.30, "Night Stripe": 0.30,
    "Stained": 0.28, "Rust Coat": 0.27, "Boreal Forest": 0.25, "Scorched": 0.22,
    "Urban Masked": 0.20, "Forest DDPAT": 0.18, "Safari Mesh": 0.12,
    "Duct Tape": 0.15, "CAUTION!": 0.18,
}

_DEFAULT_FINISH_WEIGHT = 0.45
_VANILLA_FINISH_WEIGHT = 0.30  # нож/перчатки без указанной фазы (голое имя)


def _name_hash_unit(name: str) -> float:
    """Стабильный псевдослучайный коэффициент 0..1, уникальный для каждого
    ТОЧНОГО имени предмета — обеспечивает, что даже у двух ножей с похожим
    типом/фазой итоговая цена не совпадает один-в-один."""
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 10_000) / 10_000.0


def _split_name(name: str) -> tuple[str, str | None]:
    """'★ Karambit | Doppler' -> ('Karambit', 'Doppler'); '★ Karambit' ->
    ('Karambit', None)."""
    clean = name.replace("★", "").strip()
    if "|" in clean:
        base, finish = clean.split("|", 1)
        return base.strip(), finish.strip()
    return clean, None


def _finish_weight(finish: str | None) -> float:
    if not finish:
        return _VANILLA_FINISH_WEIGHT
    return FINISH_DESIRABILITY.get(finish, _DEFAULT_FINISH_WEIGHT)


def _band_for(base_type: str, cheap: set[str], mid: set[str], top: set[str]) -> tuple[float, float]:
    if base_type in top:
        return TOP_BAND
    if base_type in mid:
        return MID_BAND
    if base_type in cheap:
        return CHEAP_BAND
    # Неизвестный/новый тип этой категории — ставим в средний тир, а не
    # молча в дешёвый или дорогой, чтобы не искажать экономику кейсов.
    return MID_BAND


def tiered_fallback_usd(name: str, rarity: str) -> float | None:
    """Индивидуальная fallback-цена (USD) для конкретного ножа/перчаток по
    его типу + фазе. Возвращает None для всех остальных редкостей — там
    используется обычный fallback по редкости (см. main.FALLBACK_USD_BY_RARITY)."""
    if rarity not in ("Knife", "Gloves"):
        return None

    base_type, finish = _split_name(name)
    if rarity == "Knife":
        lo, hi = _band_for(base_type, KNIFE_CHEAP_TYPES, KNIFE_MID_TYPES, KNIFE_TOP_TYPES)
    else:
        lo, hi = _band_for(base_type, GLOVES_CHEAP_TYPES, GLOVES_MID_TYPES, GLOVES_TOP_TYPES)

    finish_score = _finish_weight(finish)
    jitter_score = _name_hash_unit(name)
    # 65% веса — насколько дорога сама фаза/паттерн, 35% — стабильный
    # индивидуальный разброс по имени (чтобы предметы с одинаковой фазой,
    # но разным ножом/перчаткой, тоже не совпадали в лоб).
    score = max(0.0, min(1.0, 0.65 * finish_score + 0.35 * jitter_score))
    return round(lo + score * (hi - lo), 2)


# ---------------------------------------------------------------
# Лёгкая индивидуализация fallback-цены ОБЫЧНЫХ скинов (не ножи/перчатки).
# Раньше любой скин одной редкости (напр. любой Covert) получал одну и ту
# же плоскую цену по FALLBACK_USD_BY_RARITY — теперь она "дрожит" вокруг
# базового значения редкости на ±25% детерминированно по имени, так что
# у разных скинов ОДНОЙ редкости в одном и том же кейсе разные цены (а не
# буквально одно и то же число), не ломая при этом общий баланс экономики
# кейсов (среднее по всё ещё равно базовому значению редкости).
# ---------------------------------------------------------------
_SKIN_JITTER_RANGE = 0.25  # ±25%


def skin_fallback_jitter(name: str, base_usd: float) -> float:
    unit = _name_hash_unit(name)  # 0..1
    factor = 1.0 + (unit * 2 - 1) * _SKIN_JITTER_RANGE  # 0.75x .. 1.25x
    return round(base_usd * factor, 4)


# ---------------------------------------------------------------
# ПРАВКИ В ТЗ №2, п.2 — ТОПОВЫЕ ИМЕННЫЕ СКИНЫ (Dragon Lore и т.д.)
# ---------------------------------------------------------------
# ПРОБЛЕМА: до этого блока любой обычный (не нож/не перчатки) скин без
# засинканной реальной цены Steam Market падал в общий плоский fallback
# по редкости FALLBACK_USD_BY_RARITY["Covert"] = $45 (± jitter 25%) —
# то есть "AWP | Dragon Lore" получал ТОЧНО ТАКУЮ ЖЕ базовую цену, как
# любой рядовой Covert-скин. После конвертации в 💎/₽ по курсу ~90 это и
# давало те самые "4 050.00" из бага в ТЗ (45 * 90 ≈ 4050) — совпадение
# было не багом округления, а прямым следствием плоского fallback.
#
# Здесь — явный якорный прайс-лист по КОНКРЕТНОМУ ПОЛНОМУ ИМЕНИ предмета
# (оружие + паттерн) для скинов, которые на реальном рынке стоят на
# порядки дороже обычного Covert/Classified того же оружия. Список
# заведомо неполный (это не парсер Steam Market, а ручной fallback уровня
# price_tiers.py) — по мере запуска sync_prices.py реальные цены всё
# равно имеют приоритет (см. main.get_base_price_rub).
# ---------------------------------------------------------------
LEGENDARY_SKIN_ANCHOR_USD: dict[str, float] = {
    "AWP | Dragon Lore": 4800.0,
    "AWP | Gungnir": 3400.0,
    "AWP | Medusa": 2600.0,
    "AK-47 | Wild Lotus": 3600.0,
    "AK-47 | Fire Serpent": 1400.0,
    "AK-47 | Gold Arabesque": 1200.0,
    "M4A4 | Howl": 2400.0,
    "M4A1-S | Golden Coil": 1300.0,
    "AWP | Gold Arabesque": 1600.0,
}

# ±20% детерминированного (по имени) разброса вокруг якоря — чтобы даже
# у этих топовых скинов итоговая цена не выглядела "ровным числом", тем
# же приёмом, что и skin_fallback_jitter выше.
_LEGENDARY_JITTER_RANGE = 0.20


def legendary_fallback_usd(name: str) -> float | None:
    """Якорная fallback-цена (USD) для явно перечисленных топовых именных
    скинов (см. LEGENDARY_SKIN_ANCHOR_USD). Возвращает None для всех
    остальных предметов — там используется обычная цепочка fallback'ов
    (tiered_fallback_usd для ножей/перчаток, затем плоский по редкости)."""
    anchor = LEGENDARY_SKIN_ANCHOR_USD.get(name)
    if anchor is None:
        return None
    unit = _name_hash_unit(name)  # 0..1, стабильно для этого имени
    factor = 1.0 + (unit * 2 - 1) * _LEGENDARY_JITTER_RANGE  # 0.8x .. 1.2x
    return round(anchor * factor, 2)
