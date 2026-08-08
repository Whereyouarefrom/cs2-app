# ============================================
# СПРИНТ 10: Титулы и Рамки аватара (косметика профиля)
# ============================================
#
# Здесь живёт КАТАЛОГ косметики профиля и логика её РАЗБЛОКИРОВКИ.
# Хранение выбора — на User (см. database.py):
#   selected_title / selected_frame — ТЕКУЩИЙ выбор игрока
#   unlocked_titles / unlocked_frames — JSON-массивы открытых ключей
#
# Как титул попадает игроку (два независимых пути):
#
#   1) АВТО-РАЗБЛОКИРОВКА по статистике (основной путь, этот модуль).
#      Условия проверяются по накопительным счётчикам на User, которые
#      инкрементит main._maybe_update_top_drop — единая воронка, через
#      которую проходит ЛЮБОЙ полученный игроком предмет (кейсы, крафт,
#      контракты, апгрейдер, колесо, промокоды, Battle Pass, ежедневки).
#      Поэтому достаточно было врезаться в одну функцию, а не в 13 мест.
#
#   2) ПРЯМАЯ ВЫДАЧА наградой (grant) — титулы/рамки за турниры и Battle
#      Pass. Такие ключи помечены unlock={"type": "grant"}: их нельзя
#      получить по статистике, только записью ключа в unlocked_* (см.
#      grant_title / grant_frame).
#
# ВАЖНО про рамки Battle Pass: они НЕ дублируются в этот каталог. Пропуск
# ведёт свой независимый список (User.unlocked_pass_frames + стили в
# pass.js) — поэтому селектор рамок в профиле показывает ОБЪЕДИНЕНИЕ
# каталога этого модуля и рамок Пропуска (см. routers/profile.py).

from __future__ import annotations

import json

# ---------------------------------------------------------------
# Пороги авто-разблокировки титулов
# ---------------------------------------------------------------
# «Ножеман» — выбить хотя бы один нож/перчатки (User.knife_drops_count).
KNIFEMAN_REQUIRED_KNIVES = 1

# «Магнат» — довести стоимость инвентаря до порога. Считается по
# User.peak_inventory_value (ПИКОВОЕ, а не текущее значение), чтобы
# продажа скинов не отбирала уже заслуженный титул.
MAGNATE_REQUIRED_VALUE = 1_000_000

# «Счастливчик» — накопить N дропов редкости Covert и выше
# (User.covert_drops_count: Covert / Gloves / Knife).
LUCKY_REQUIRED_COVERTS = 10

# Редкости, которые считаются "ножевыми" и "топовыми" для счётчиков.
KNIFE_RARITIES = ("Knife", "Gloves")
COVERT_PLUS_RARITIES = ("Covert", "Gloves", "Knife")


# ---------------------------------------------------------------
# Каталог титулов
# ---------------------------------------------------------------
TITLES = [
    {
        "key": "knifeman",
        "name": "Ножеман",
        "name_en": "Knifeman",
        "name_uk": "Ножеман",
        "icon": "🔪",
        "unlock": {"type": "knives", "value": KNIFEMAN_REQUIRED_KNIVES},
        "hint": f"Выбей нож или перчатки ({KNIFEMAN_REQUIRED_KNIVES} шт.)",
        "hint_en": f"Drop a knife or gloves ({KNIFEMAN_REQUIRED_KNIVES})",
        "hint_uk": f"Вибий ніж або рукавиці ({KNIFEMAN_REQUIRED_KNIVES} шт.)",
    },
    {
        "key": "magnate",
        "name": "Магнат",
        "name_en": "Magnate",
        "name_uk": "Магнат",
        "icon": "💰",
        "unlock": {"type": "inventory_value", "value": MAGNATE_REQUIRED_VALUE},
        "hint": f"Собери инвентарь на {MAGNATE_REQUIRED_VALUE:,} 💎".replace(",", " "),
        "hint_en": f"Reach an inventory worth {MAGNATE_REQUIRED_VALUE:,} 💎",
        "hint_uk": f"Збери інвентар на {MAGNATE_REQUIRED_VALUE:,} 💎".replace(",", " "),
    },
    {
        "key": "lucky",
        "name": "Счастливчик",
        "name_en": "Lucky One",
        "name_uk": "Щасливчик",
        "icon": "🍀",
        "unlock": {"type": "coverts", "value": LUCKY_REQUIRED_COVERTS},
        "hint": f"Выбей {LUCKY_REQUIRED_COVERTS} предметов редкости Covert и выше",
        "hint_en": f"Drop {LUCKY_REQUIRED_COVERTS} items of Covert rarity or above",
        "hint_uk": f"Вибий {LUCKY_REQUIRED_COVERTS} предметів рідкості Covert і вище",
    },
    # ---- Выдаётся только наградой (см. routers/tournament.py) ----
    {
        "key": "legend_of_tournaments",
        "name": "Легенда Турниров",
        "name_en": "Tournament Legend",
        "name_uk": "Легенда Турнірів",
        "icon": "🏆",
        "unlock": {"type": "grant"},
        "hint": "Займи 1-е место в еженедельном турнире",
        "hint_en": "Take 1st place in a weekly tournament",
        "hint_uk": "Займи 1-е місце у щотижневому турнірі",
    },
]

TITLES_BY_KEY = {t["key"]: t for t in TITLES}


# ---------------------------------------------------------------
# Каталог рамок аватара
# ---------------------------------------------------------------
# css — готовая строка box-shadow, фронт применяет её к аватару как есть
# (та же схема, что уже используется для рамок Battle Pass в pass.js).
FRAMES = [
    {
        "key": "level_bronze",
        "name": "Бронзовый Обод",
        "name_en": "Bronze Rim",
        "name_uk": "Бронзовий Обід",
        "css": "0 0 0 3px #cd7f32, 0 0 12px rgba(205,127,50,0.6)",
        "unlock": {"type": "level", "value": 5},
        "hint": "Достигни 5 уровня аккаунта",
        "hint_en": "Reach account level 5",
        "hint_uk": "Досягни 5 рівня акаунта",
    },
    {
        "key": "level_silver",
        "name": "Серебряный Обод",
        "name_en": "Silver Rim",
        "name_uk": "Срібний Обід",
        "css": "0 0 0 3px #c0c8d4, 0 0 14px rgba(192,200,212,0.7)",
        "unlock": {"type": "level", "value": 15},
        "hint": "Достигни 15 уровня аккаунта",
        "hint_en": "Reach account level 15",
        "hint_uk": "Досягни 15 рівня акаунта",
    },
    {
        "key": "level_gold",
        "name": "Золотой Обод",
        "name_en": "Gold Rim",
        "name_uk": "Золотий Обід",
        "css": "0 0 0 3px #ffd700, 0 0 16px rgba(255,215,0,0.75)",
        "unlock": {"type": "level", "value": 30},
        "hint": "Достигни 30 уровня аккаунта",
        "hint_en": "Reach account level 30",
        "hint_uk": "Досягни 30 рівня акаунта",
    },
    {
        "key": "level_diamond",
        "name": "Алмазный Обод",
        "name_en": "Diamond Rim",
        "name_uk": "Алмазний Обід",
        "css": "0 0 0 3px #9be7ff, 0 0 20px rgba(74,209,255,0.85)",
        "unlock": {"type": "level", "value": 50},
        "hint": "Достигни 50 уровня аккаунта",
        "hint_en": "Reach account level 50",
        "hint_uk": "Досягни 50 рівня акаунта",
    },
    # ---- Выдаются только наградой (см. routers/tournament.py) ----
    {
        "key": "champion_of_week",
        "name": "Чемпион Недели",
        "name_en": "Champion of the Week",
        "name_uk": "Чемпіон Тижня",
        "css": "0 0 0 3px #ffd700, 0 0 22px #ff5e1c",
        "unlock": {"type": "grant"},
        "hint": "Займи 1-е место в еженедельном турнире",
        "hint_en": "Take 1st place in a weekly tournament",
        "hint_uk": "Займи 1-е місце у щотижневому турнірі",
    },
    {
        "key": "prize_winner",
        "name": "Призёр",
        "name_en": "Prize Winner",
        "name_uk": "Призер",
        "css": "0 0 0 3px #c0c8d4, 0 0 18px #4a9eff",
        "unlock": {"type": "grant"},
        "hint": "Займи 2-3 место в еженедельном турнире",
        "hint_en": "Take 2nd-3rd place in a weekly tournament",
        "hint_uk": "Займи 2-3 місце у щотижневому турнірі",
    },
]

FRAMES_BY_KEY = {f["key"]: f for f in FRAMES}


# ---------------------------------------------------------------
# JSON-хелперы для накопительных списков на User
# ---------------------------------------------------------------
def load_keys(raw: str | None) -> list[str]:
    """Безопасно читает JSON-массив ключей из текстовой колонки. Любой
    мусор/NULL трактуется как пустой список — колонка добавляется
    авто-миграцией и у старых строк может оказаться пустой."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [str(k) for k in data] if isinstance(data, list) else []


def dump_keys(keys) -> str:
    """Сериализует список ключей, убирая дубликаты и сохраняя порядок
    первого появления (порядок = порядок получения, его видит игрок)."""
    seen, ordered = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            ordered.append(k)
    return json.dumps(ordered, ensure_ascii=False)


# ---------------------------------------------------------------
# Инкремент счётчиков статистики (вызывается на каждый полученный предмет)
# ---------------------------------------------------------------
def register_drop(user, rarity: str | None) -> None:
    """Обновляет счётчики, от которых зависят титулы «Ножеман» и
    «Счастливчик». Вызывается из main._maybe_update_top_drop — то есть
    ровно один раз на каждый предмет, который игрок получает откуда угодно.

    Сама РАЗБЛОКИРОВКА тут не делается: она требует знать уровень и
    стоимость инвентаря, поэтому выполняется в sync_unlocks() при сборке
    профиля. Это осознанно — дроп-путь остаётся синхронным и дешёвым."""
    if not rarity:
        return
    if rarity in KNIFE_RARITIES:
        user.knife_drops_count = (user.knife_drops_count or 0) + 1
    if rarity in COVERT_PLUS_RARITIES:
        user.covert_drops_count = (user.covert_drops_count or 0) + 1


# ---------------------------------------------------------------
# Проверка условий и синхронизация открытого
# ---------------------------------------------------------------
def _is_condition_met(unlock: dict, *, level: int, knives: int, coverts: int, inventory_value: float) -> bool:
    kind = unlock.get("type")
    if kind == "grant":
        return False   # только прямой выдачей, по статистике не открывается
    if kind == "level":
        return level >= unlock.get("value", 0)
    if kind == "knives":
        return knives >= unlock.get("value", 0)
    if kind == "coverts":
        return coverts >= unlock.get("value", 0)
    if kind == "inventory_value":
        return inventory_value >= unlock.get("value", 0)
    return False


def sync_unlocks(user, *, level: int, inventory_value: float) -> dict:
    """Главная точка входа: пересчитывает, какие титулы/рамки игрок УЖЕ
    заслужил, и дописывает новые ключи в user.unlocked_titles /
    user.unlocked_frames.

    Дополнительно поднимает user.peak_inventory_value до текущей стоимости
    инвентаря — «Магнат» проверяется по пику, поэтому распродажа скинов не
    отбирает уже полученный титул.

    Возвращает {"titles": [...], "frames": [...]} — только те ключи,
    которые открылись ИМЕННО СЕЙЧАС (фронт показывает по ним уведомление).
    Функция идемпотентна: повторный вызов вернёт пустые списки.
    """
    peak = max(float(user.peak_inventory_value or 0.0), float(inventory_value or 0.0))
    user.peak_inventory_value = peak

    knives = int(user.knife_drops_count or 0)
    coverts = int(user.covert_drops_count or 0)

    unlocked_titles = load_keys(user.unlocked_titles)
    unlocked_frames = load_keys(user.unlocked_frames)

    new_titles, new_frames = [], []

    for entry in TITLES:
        if entry["key"] in unlocked_titles:
            continue
        if _is_condition_met(entry["unlock"], level=level, knives=knives, coverts=coverts, inventory_value=peak):
            unlocked_titles.append(entry["key"])
            new_titles.append(entry["key"])

    for entry in FRAMES:
        if entry["key"] in unlocked_frames:
            continue
        if _is_condition_met(entry["unlock"], level=level, knives=knives, coverts=coverts, inventory_value=peak):
            unlocked_frames.append(entry["key"])
            new_frames.append(entry["key"])

    if new_titles:
        user.unlocked_titles = dump_keys(unlocked_titles)
    if new_frames:
        user.unlocked_frames = dump_keys(unlocked_frames)

    return {"titles": new_titles, "frames": new_frames}


def grant_title(user, key: str) -> bool:
    """Прямая выдача титула наградой (турниры/Battle Pass/админ). Возвращает
    True, если титул действительно был новым."""
    if key not in TITLES_BY_KEY:
        return False
    keys = load_keys(user.unlocked_titles)
    if key in keys:
        return False
    keys.append(key)
    user.unlocked_titles = dump_keys(keys)
    return True


def grant_frame(user, key: str) -> bool:
    """Прямая выдача рамки наградой. Возвращает True, если рамка новая."""
    if key not in FRAMES_BY_KEY:
        return False
    keys = load_keys(user.unlocked_frames)
    if key in keys:
        return False
    keys.append(key)
    user.unlocked_frames = dump_keys(keys)
    return True


# ---------------------------------------------------------------
# Сериализация для API
# ---------------------------------------------------------------
def _public_entry(entry: dict, unlocked_keys: list[str], progress: dict) -> dict:
    unlock = entry["unlock"]
    return {
        "key": entry["key"],
        "name": entry["name"],
        "name_en": entry["name_en"],
        "name_uk": entry["name_uk"],
        "icon": entry.get("icon"),
        "css": entry.get("css"),
        "hint": entry["hint"],
        "hint_en": entry["hint_en"],
        "hint_uk": entry["hint_uk"],
        "unlocked": entry["key"] in unlocked_keys,
        "unlock_type": unlock.get("type"),
        "unlock_value": unlock.get("value"),
        # текущее значение счётчика, по которому идёт условие — фронт
        # рисует из этого прогресс «7 / 10 Covert-дропов»
        "current_value": progress.get(unlock.get("type")),
    }


def serialize_titles(user, *, level: int) -> list[dict]:
    unlocked = load_keys(user.unlocked_titles)
    progress = {
        "level": level,
        "knives": int(user.knife_drops_count or 0),
        "coverts": int(user.covert_drops_count or 0),
        "inventory_value": round(float(user.peak_inventory_value or 0.0), 0),
    }
    return [_public_entry(t, unlocked, progress) for t in TITLES]


def serialize_frames(user, *, level: int) -> list[dict]:
    unlocked = load_keys(user.unlocked_frames)
    progress = {
        "level": level,
        "knives": int(user.knife_drops_count or 0),
        "coverts": int(user.covert_drops_count or 0),
        "inventory_value": round(float(user.peak_inventory_value or 0.0), 0),
    }
    return [_public_entry(f, unlocked, progress) for f in FRAMES]


def title_public(key: str | None) -> dict | None:
    """Компактное представление ВЫБРАННОГО титула — для карточки профиля,
    публичной карточки друга и лидербордов."""
    entry = TITLES_BY_KEY.get(key or "")
    if not entry:
        return None
    return {
        "key": entry["key"],
        "name": entry["name"],
        "name_en": entry["name_en"],
        "name_uk": entry["name_uk"],
        "icon": entry.get("icon"),
    }


def frame_public(key: str | None) -> dict | None:
    """Компактное представление ВЫБРАННОЙ рамки. Возвращает None для рамок
    Battle Pass — их стили знает только фронт (pass.js), и он подставит их
    сам по ключу selected_frame."""
    entry = FRAMES_BY_KEY.get(key or "")
    if not entry:
        return None
    return {
        "key": entry["key"],
        "name": entry["name"],
        "name_en": entry["name_en"],
        "name_uk": entry["name_uk"],
        "css": entry.get("css"),
    }
