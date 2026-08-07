# ============================================
# CS2 Case Simulator — Система опыта (XP) и лиг/рангов
# ============================================
#
# Лестница рангов — по аналогии с делением сообщества CS2 на "лиги":
# Сильвер → Голд Нова → Калаш → Двойной Калаш → Бигстар → Лем → Суприм → Глобал.
#
# Как это работает:
#   - Игрок получает XP за активность (открытие кейсов, ставки в мини-играх,
#     крафт, ежедневный бонус и т.п. — см. main.py, функции _award_xp/_xp_for_case_open
#     и точки вызова).
#   - Как только накопленный user.xp достигает min_xp следующего ранга —
#     ранг повышается (user.rank_level += 1).
#   - За КАЖДЫЙ новый достигнутый ранг игрок разово получает bonus_crystals
#     💎 на баланс. Начиная с ранга "Калаш" дополнительно открывается
#     доступ к специальному РАНГОВОМУ КЕЙСУ (см. RANK_CASE_WEIGHTS) —
#     он тут же один раз "открывается" для игрока как часть награды за ранг
#     (реальный предмет с реальной ценой/картинкой, взятый из общего пула
#     предметов всех кейсов — см. _roll_rank_case_item в main.py).
#
# Пороги XP подобраны так, чтобы путь Сильвер → Глобал ощущался как
# полноценная прогрессия (десятки открытий кейсов и раундов мини-игр),
# а не разовое достижение за один сеанс.

RANKS = [
    {
        "level": 0,
        "key": "silver",
        "name": "Сильвер",
        "name_en": "Silver",
        "name_uk": "Сільвер",
        "icon": "🔰",
        "min_xp": 0,
        "bonus_crystals": 0,      # стартовый ранг — награды нет, это точка отсчёта
        "case_key": None,
    },
    {
        "level": 1,
        "key": "gold_nova",
        "name": "Голд Нова",
        "name_en": "Gold Nova",
        "name_uk": "Голд Нова",
        "icon": "⭐",
        "min_xp": 500,
        "bonus_crystals": 800,
        "case_key": None,
    },
    {
        "level": 2,
        "key": "kalash",
        "name": "Калаш",
        "name_en": "Kalash",
        "name_uk": "Калаш",
        "icon": "🔫",
        "min_xp": 1500,
        "bonus_crystals": 1500,
        "case_key": "rank_kalash",
    },
    {
        "level": 3,
        "key": "double_kalash",
        "name": "Двойной Калаш",
        "name_en": "Double Kalash",
        "name_uk": "Подвійний Калаш",
        "icon": "🔫🔫",
        "min_xp": 3200,
        "bonus_crystals": 2500,
        "case_key": "rank_double_kalash",
    },
    {
        "level": 4,
        "key": "bigstar",
        "name": "Бигстар",
        "name_en": "Bigstar",
        "name_uk": "Бігстар",
        "icon": "🌟",
        "min_xp": 6000,
        "bonus_crystals": 4000,
        "case_key": "rank_bigstar",
    },
    {
        "level": 5,
        "key": "lem",
        "name": "Лем",
        "name_en": "Lem",
        "name_uk": "Лем",
        "icon": "🦅",
        "min_xp": 11000,
        "bonus_crystals": 7000,
        "case_key": "rank_lem",
    },
    {
        "level": 6,
        "key": "supreme",
        "name": "Суприм",
        "name_en": "Supreme",
        "name_uk": "Супрім",
        "icon": "👑",
        "min_xp": 19000,
        "bonus_crystals": 12000,
        "case_key": "rank_supreme",
    },
    {
        "level": 7,
        "key": "global",
        "name": "Глобал",
        "name_en": "Global Elite",
        "name_uk": "Глобал",
        "icon": "🌍",
        "min_xp": 30000,
        "bonus_crystals": 20000,
        "case_key": "rank_global",
    },
]

MAX_RANK_LEVEL = len(RANKS) - 1


# ---------------------------------------------------------------
# Веса редкостей для каждого рангового кейса (используются вместе с
# порогом min_rarity — см. main.py::_roll_rank_case_item). Чем выше
# ранг, тем сильнее пул смещён к Covert/Gloves/Knife.
# ---------------------------------------------------------------
RANK_CASE_WEIGHTS = {
    "rank_kalash": {
        "name": "Кейс ранга «Калаш»",
        "weights": {"Restricted": 55, "Classified": 35, "Covert": 10},
    },
    "rank_double_kalash": {
        "name": "Кейс ранга «Двойной Калаш»",
        "weights": {"Restricted": 35, "Classified": 45, "Covert": 20},
    },
    "rank_bigstar": {
        "name": "Кейс ранга «Бигстар»",
        "weights": {"Classified": 45, "Covert": 45, "Gloves": 10},
    },
    "rank_lem": {
        "name": "Кейс ранга «Лем»",
        "weights": {"Classified": 25, "Covert": 55, "Gloves": 15, "Knife": 5},
    },
    "rank_supreme": {
        "name": "Кейс ранга «Суприм»",
        "weights": {"Covert": 55, "Gloves": 30, "Knife": 15},
    },
    "rank_global": {
        "name": "Кейс ранга «Глобал»",
        "weights": {"Covert": 30, "Gloves": 35, "Knife": 35},
    },
}


def rank_by_level(level: int) -> dict:
    level = max(0, min(level, MAX_RANK_LEVEL))
    return RANKS[level]


def get_rank_progress(xp: int, rank_level: int) -> dict:
    """Собирает данные для прогресс-бара ранга в профиле: текущий ранг,
    следующий ранг, % прогресса до него (100%, если уже Глобал)."""
    rank_level = max(0, min(rank_level, MAX_RANK_LEVEL))
    current = RANKS[rank_level]
    next_rank = RANKS[rank_level + 1] if rank_level < MAX_RANK_LEVEL else None

    if next_rank:
        span = next_rank["min_xp"] - current["min_xp"]
        progress = (xp - current["min_xp"]) / span if span > 0 else 1.0
        progress = max(0.0, min(1.0, progress))
    else:
        progress = 1.0

    return {
        "level": rank_level,
        "key": current["key"],
        "name": current["name"],
        "name_en": current["name_en"],
        "name_uk": current["name_uk"],
        "icon": current["icon"],
        "xp": xp,
        "current_min_xp": current["min_xp"],
        "next_min_xp": next_rank["min_xp"] if next_rank else None,
        "next_name": next_rank["name"] if next_rank else None,
        "next_name_en": next_rank["name_en"] if next_rank else None,
        "next_name_uk": next_rank["name_uk"] if next_rank else None,
        "next_icon": next_rank["icon"] if next_rank else None,
        "xp_to_next": (next_rank["min_xp"] - xp) if next_rank else 0,
        "progress_percent": round(progress * 100, 1),
        "is_max": next_rank is None,
    }
