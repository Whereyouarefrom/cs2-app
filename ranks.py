# ============================================
# CS2 Case Simulator — Система опыта (XP) и лиг/рангов
# ============================================
#
# ПРАВКИ В ТЗ №5 — полная переработка лестницы рангов:
#
#   1) Названия рангов приведены к канонической лестнице CS2/CS:GO:
#      Сильвер → Голд Нова → Мастер Гвардиан → DMG (Дистингвишед Мастер
#      Гвардиан) → Легендарный Игл → Суприм → Глобал Элит.
#
#   2) Пороги XP больше не подобраны "на глаз", а считаются формулой
#      геометрической прогрессии (см. _min_xp_for_rank ниже) — тот же
#      принцип, что и у уровня аккаунта в levels.py (100 * 1.15^(N-1)),
#      только с собственными константами. Это гарантирует, что КАЖДЫЙ
#      следующий ранг требует строго больше XP, чем предыдущий, причём
#      разрыв между рангами растёт (не линейно, а экспоненциально) —
#      прогрессия ощутимо длиннее прежней (Глобал Элит теперь на 103 000
#      XP вместо прежних 30 000 у "Глобала").
#
#   3) Награды за ранг стали разнообразнее: помимо кристаллов и
#      рангового кейса (было раньше), теперь начиная с середины лестницы
#      выдаются секретные скины (гарантированный дроп ножа/перчаток в
#      обход обычных весов кейса), эксклюзивные рамки аватара и
#      эксклюзивные фоны профиля — см. поля secret_skin / frame_key /
#      background_key. Актуальная логика выдачи — в main.py::_award_xp.
#
# Как это работает:
#   - Игрок получает XP за активность (открытие кейсов, ставки в мини-играх,
#     крафт, ежедневный бонус и т.п. — см. main.py, функции _award_xp/_xp_for_case_open
#     и точки вызова).
#   - Как только накопленный user.xp достигает min_xp следующего ранга —
#     ранг повышается (user.rank_level += 1).
#   - За КАЖДЫЙ новый достигнутый ранг игрок разово получает bonus_crystals
#     💎 на баланс, а также (в зависимости от ранга) ранговый кейс,
#     секретный скин, эксклюзивную рамку и/или эксклюзивный фон профиля.

# ---------------------------------------------------------------
# Формула порогов XP: min_xp(i) = RANK_BASE_XP * RANK_GROWTH^(i-1) для i>=1,
# min_xp(0) = 0 (стартовый ранг "Сильвер" — точка отсчёта, награды нет).
# RANK_GROWTH > GROWTH уровня аккаунта (1.15) намеренно: рангов всего 7 (а
# не 200), поэтому чтобы путь Сильвер → Глобал Элит ощущался как долгая
# прогрессия, а не проходился за пару вечеров, разрыв между СОСЕДНИМИ
# рангами должен расти заметно быстрее.
# ---------------------------------------------------------------
RANK_BASE_XP = 2000.0
RANK_GROWTH = 2.2


def _min_xp_for_rank(index: int) -> int:
    """Минимальный накопленный XP, необходимый для ранга с индексом
    `index` (0 = Сильвер). Чистая формула — используется один раз при
    построении таблицы RANKS ниже, чтобы пороги нельзя было случайно
    рассинхронизировать при правке констант."""
    if index <= 0:
        return 0
    return int(round(RANK_BASE_XP * (RANK_GROWTH ** (index - 1))))


def _bonus_crystals_for_rank(index: int) -> int:
    """Разовая награда 💎 за достижение ранга — тоже экспоненциальная
    (база 1000, рост x2 за ранг), чтобы награда ощущалась пропорционально
    возросшей длительности прогрессии."""
    if index <= 0:
        return 0
    return int(1000 * (2 ** (index - 1)))


# Каноническая лестница рангов CS2. icon — эмодзи-заглушка (реальных
# иконок рангов Valve в проекте нет и не должно быть — это чужой копирайт).
_RANK_DEFS = [
    # (key, name_ru, name_en, name_uk, icon)
    ("silver", "Сильвер", "Silver", "Сільвер", "🔰"),
    ("gold_nova", "Голд Нова", "Gold Nova", "Голд Нова", "⭐"),
    ("master_guardian", "Мастер Гвардиан", "Master Guardian", "Майстер Гвардіан", "🛡️"),
    ("dmg", "Дистингвишед Мастер Гвардиан", "Distinguished Master Guardian", "Видатний Майстер Гвардіан", "⚔️"),
    ("legendary_eagle", "Легендарный Игл", "Legendary Eagle", "Легендарний Ігл", "🦅"),
    ("supreme", "Суприм", "Supreme Master First Class", "Супрім Майстер", "👑"),
    ("global_elite", "Глобал Элит", "Global Elite", "Глобал Еліт", "🌍"),
]

# case_key — ранговый кейс (см. RANK_CASE_WEIGHTS ниже), появляется начиная
# с "Мастер Гвардиан", чтобы первый ранг-другой прогрессии не заваливал
# игрока предметами и кейс воспринимался как значимая награда.
# secret_skin — гарантированный (не по кейсовым весам) дроп ножа/перчаток
# в обход обычной вероятности, начиная с "Легендарного Игла".
# frame_key / background_key — ключи эксклюзивной косметики (см.
# cosmetics.py::FRAMES и main.py::BACKGROUND_OPTIONS), None если для
# этого ранга косметика не положена.
_RANK_REWARDS = {
    "silver":          {"case_key": None,                  "secret_skin": False, "frame_key": None,                  "background_key": None},
    "gold_nova":       {"case_key": None,                  "secret_skin": False, "frame_key": None,                  "background_key": None},
    "master_guardian": {"case_key": "rank_master_guardian", "secret_skin": False, "frame_key": "rank_master_guardian", "background_key": None},
    "dmg":              {"case_key": "rank_dmg",             "secret_skin": False, "frame_key": None,                  "background_key": None},
    "legendary_eagle": {"case_key": "rank_legendary_eagle", "secret_skin": True,  "frame_key": "rank_legendary_eagle", "background_key": None},
    "supreme":         {"case_key": "rank_supreme",         "secret_skin": False, "frame_key": None,                  "background_key": "bg_rank_supreme"},
    "global_elite":    {"case_key": "rank_global_elite",    "secret_skin": True,  "frame_key": "rank_global_elite",    "background_key": "bg_rank_global_elite"},
}

RANKS = []
for _i, (_key, _name, _name_en, _name_uk, _icon) in enumerate(_RANK_DEFS):
    _rewards = _RANK_REWARDS[_key]
    RANKS.append({
        "level": _i,
        "key": _key,
        "name": _name,
        "name_en": _name_en,
        "name_uk": _name_uk,
        "icon": _icon,
        "min_xp": _min_xp_for_rank(_i),
        "bonus_crystals": _bonus_crystals_for_rank(_i),
        "case_key": _rewards["case_key"],
        "secret_skin": _rewards["secret_skin"],
        "frame_key": _rewards["frame_key"],
        "background_key": _rewards["background_key"],
    })
del _i, _key, _name, _name_en, _name_uk, _icon, _rewards

MAX_RANK_LEVEL = len(RANKS) - 1


# ---------------------------------------------------------------
# Веса редкостей для каждого рангового кейса (используются вместе с
# порогом min_rarity — см. main.py::_roll_rank_case_item). Чем выше
# ранг, тем сильнее пул смещён к Covert/Gloves/Knife.
# ---------------------------------------------------------------
RANK_CASE_WEIGHTS = {
    "rank_master_guardian": {
        "name": "Кейс ранга «Мастер Гвардиан»",
        "weights": {"Restricted": 55, "Classified": 35, "Covert": 10},
    },
    "rank_dmg": {
        "name": "Кейс ранга «DMG»",
        "weights": {"Restricted": 35, "Classified": 45, "Covert": 20},
    },
    "rank_legendary_eagle": {
        "name": "Кейс ранга «Легендарный Игл»",
        "weights": {"Classified": 30, "Covert": 55, "Gloves": 15},
    },
    "rank_supreme": {
        "name": "Кейс ранга «Суприм»",
        "weights": {"Covert": 55, "Gloves": 30, "Knife": 15},
    },
    "rank_global_elite": {
        "name": "Кейс ранга «Глобал Элит»",
        "weights": {"Covert": 30, "Gloves": 35, "Knife": 35},
    },
}

# Веса "секретного скина" (rank_def["secret_skin"] = True) — гарантированный
# дроп в обход кейсовых весов, всегда только Gloves/Knife.
SECRET_SKIN_WEIGHTS = {"Gloves": 50, "Knife": 50}


def rank_by_level(level: int) -> dict:
    level = max(0, min(level, MAX_RANK_LEVEL))
    return RANKS[level]


def get_rank_progress(xp: int, rank_level: int) -> dict:
    """Собирает данные для прогресс-бара ранга в профиле: текущий ранг,
    следующий ранг, % прогресса до него (100%, если уже Глобал Элит)."""
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
