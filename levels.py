# ============================================
# СПРИНТ 10: Уровень аккаунта (Account Level)
# ============================================
#
# ВАЖНО — это НЕ замена системе лиг/рангов из ranks.py.
#
# В проекте живут ДВЕ независимые прогрессии, обе считаются от ОДНОГО и того
# же накопительного User.xp (см. main._award_xp):
#
#   1) Ранг/лига (ranks.py) — 8 фиксированных ступеней Сильвер → Глобал с
#      разовыми наградами (кристаллы + ранговый кейс). Пороги заданы вручную
#      в таблице RANKS, конечная лестница.
#
#   2) Уровень аккаунта (этот модуль) — БЕСКОНЕЧНАЯ гладкая прогрессия по
#      геометрической формуле из ТЗ Спринта 10:
#
#          XP_required(N) = 100 * 1.15^(N-1)
#
#      где XP_required(N) — сколько опыта нужно набрать, находясь НА уровне N,
#      чтобы перейти на уровень N+1 (то есть это стоимость ОДНОГО перехода,
#      а не суммарный опыт с нуля). Игрок начинается на уровне 1 с 0 XP.
#
# Зачем отдельная сущность, если XP тот же: ранг — это "звание" с наградами,
# а уровень аккаунта — технический счётчик прогресса, к которому привязана
# вместимость Витрины лучших скинов (см. showcase_slots_for_level). Держать
# их раздельно позволяет менять экономику витрины, не ломая ранговые награды.
#
# Обратная совместимость: модуль ничего не хранит и не мутирует — уровень
# ВСЕГДА выводится из xp чистой функцией level_from_xp(). Поэтому у любого
# уже существующего игрока уровень появится сам, без миграции данных.

from __future__ import annotations

import math

# ---- Параметры формулы XP_required(N) = BASE_XP * GROWTH^(N-1) ----
BASE_XP = 100.0
GROWTH = 1.15

# Формула геометрическая, поэтому теоретически уровень не ограничен. Верхний
# предел нужен только как страховка от абсурдных значений (переполнение float
# при возведении в степень, битые данные в xp) — на практике недостижим:
# суммарный опыт до 200-го уровня измеряется десятками миллиардов.
MAX_LEVEL = 200

# ---- Витрина лучших скинов (Showcase) ----
# Базовая вместимость 3 слота; каждые SHOWCASE_LEVELS_PER_SLOT уровней
# аккаунта добавляют +1 слот, но не больше SHOWCASE_MAX_SLOTS всего.
# Итог: 3 слота на 1-4 уровнях, 4 на 5-9, ... и максимум 10 слотов
# начиная с 35 уровня.
SHOWCASE_BASE_SLOTS = 3
SHOWCASE_LEVELS_PER_SLOT = 5
SHOWCASE_MAX_SLOTS = 10


def xp_required_for_level(level: int) -> int:
    """XP_required(N) из ТЗ: сколько опыта нужно набрать НА уровне `level`,
    чтобы перейти на следующий. Ровно формула 100 * 1.15^(N-1)."""
    level = max(1, min(int(level), MAX_LEVEL))
    return int(round(BASE_XP * (GROWTH ** (level - 1))))


def total_xp_for_level(level: int) -> int:
    """Суммарный (накопительный) опыт, необходимый, чтобы НАХОДИТЬСЯ на
    уровне `level`. Это сумма геометрической прогрессии стоимостей всех
    предыдущих переходов:

        total(N) = Σ(k=1..N-1) BASE_XP * GROWTH^(k-1)
                 = BASE_XP * (GROWTH^(N-1) - 1) / (GROWTH - 1)

    total(1) = 0 — новый игрок стартует на первом уровне с нулём опыта.
    """
    level = max(1, min(int(level), MAX_LEVEL))
    if level <= 1:
        return 0
    return int(round(BASE_XP * (GROWTH ** (level - 1) - 1) / (GROWTH - 1)))


def level_from_xp(xp: int) -> int:
    """Обратная к total_xp_for_level: уровень по накопленному опыту.

    Аналитически (логарифм от суммы прогрессии):
        N = floor( log_GROWTH( 1 + xp * (GROWTH - 1) / BASE_XP ) ) + 1

    Логарифм на больших значениях может дать ошибку округления ровно на
    границе уровня (например, вернуть 12 вместо 13 при xp, точно равном
    total_xp_for_level(13)), поэтому результат ДОПОЛНИТЕЛЬНО подгоняется
    сверкой с total_xp_for_level — это гарантирует, что функция строго
    согласована с таблицей порогов, которую видит игрок.
    """
    xp = max(0, int(xp or 0))
    if xp < BASE_XP:
        return 1

    approx = int(math.floor(math.log(1 + xp * (GROWTH - 1) / BASE_XP, GROWTH))) + 1
    level = max(1, min(approx, MAX_LEVEL))

    # подгонка вверх, пока опыта хватает на следующий уровень
    while level < MAX_LEVEL and xp >= total_xp_for_level(level + 1):
        level += 1
    # подгонка вниз, если логарифм "перескочил"
    while level > 1 and xp < total_xp_for_level(level):
        level -= 1
    return level


def showcase_slots_for_level(level: int) -> int:
    """Вместимость Витрины лучших скинов для данного уровня аккаунта:
    3 базовых + 1 за каждые 5 уровней, максимум 10."""
    level = max(1, int(level or 1))
    return min(SHOWCASE_MAX_SLOTS, SHOWCASE_BASE_SLOTS + level // SHOWCASE_LEVELS_PER_SLOT)


def next_showcase_slot_level(level: int) -> int | None:
    """На каком уровне игрок получит СЛЕДУЮЩИЙ слот витрины (None, если
    все SHOWCASE_MAX_SLOTS слотов уже открыты). Нужно для подсказки в UI
    вида «+1 слот на 15 уровне»."""
    level = max(1, int(level or 1))
    if showcase_slots_for_level(level) >= SHOWCASE_MAX_SLOTS:
        return None
    return (level // SHOWCASE_LEVELS_PER_SLOT + 1) * SHOWCASE_LEVELS_PER_SLOT


def get_level_progress(xp: int) -> dict:
    """Полный набор данных об уровне для фронтенда (карточка уровня в
    профиле + вместимость витрины). Единственная точка, из которой
    остальной код должен получать уровень — не считайте его вручную."""
    xp = max(0, int(xp or 0))
    level = level_from_xp(xp)

    level_start_xp = total_xp_for_level(level)
    is_max = level >= MAX_LEVEL

    if is_max:
        xp_in_level = xp - level_start_xp
        xp_needed = 0
        progress = 1.0
    else:
        xp_needed = xp_required_for_level(level)
        xp_in_level = xp - level_start_xp
        progress = (xp_in_level / xp_needed) if xp_needed > 0 else 1.0
        progress = max(0.0, min(1.0, progress))

    slots = showcase_slots_for_level(level)
    next_slot_level = next_showcase_slot_level(level)

    return {
        "level": level,
        "xp": xp,
        # прогресс ВНУТРИ текущего уровня (а не с нуля) — именно это
        # рисует прогресс-бар: xp_in_level / xp_needed
        "xp_in_level": xp_in_level,
        "xp_needed": xp_needed,
        "level_start_xp": level_start_xp,
        "next_level_xp": total_xp_for_level(level + 1) if not is_max else None,
        "xp_to_next": max(0, xp_needed - xp_in_level) if not is_max else 0,
        "progress_percent": round(progress * 100, 1),
        "is_max": is_max,
        # ---- витрина ----
        "showcase_slots": slots,
        "showcase_max_slots": SHOWCASE_MAX_SLOTS,
        "showcase_base_slots": SHOWCASE_BASE_SLOTS,
        "showcase_levels_per_slot": SHOWCASE_LEVELS_PER_SLOT,
        "next_showcase_slot_level": next_slot_level,
    }
