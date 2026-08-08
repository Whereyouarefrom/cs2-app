# ============================================
# СПРИНТ 4: МОДУЛЬ АПГРЕЙДЕРА (UPGRADER)
# ============================================
#
# POST /api/upgrader/spin
#   {
#     "telegram_id": 123456789,
#     "inventory_item_ids": [101, 102],   # ID предметов из инвентаря (Inventory.id), которые ставятся на кон
#     "add_crystals": 250.0,              # сколько 💎 с баланса добавляется к ставке (0, если не добавляем)
#     "target_item_id": "AK-47 | Redline" # целевой предмет
#   }
#
# ВАЖНО про target_item_id: в глобальном реестре предметов (items_data.py)
# у скинов нет отдельного числового ID — единственный стабильный ключ,
# по которому предмет однозначно находится в ITEMS_BY_NAME, это его ПОЛНОЕ
# ИМЯ (например "AK-47 | Redline" или "★ Karambit | Doppler"). Именно это
# имя и передаётся во `target_item_id` (см. items_data.get_item()).
#
# Отличие от уже существующего /api/upgrade (main.py, блок "10. UPGRADE"):
# тот эндпоинт работает через режимы item/price/chance/multiplier, умеет
# компенсацию при проигрыше и не трогает Кристаллы напрямую. Этот —
# отдельная, более простая механика по ТЗ спринта 4: ставятся КОНКРЕТНЫЕ
# предметы инвентаря + опционально Кристаллы поверх, шанс считается прямым
# отношением ставки к цели, при проигрыше ставка просто сгорает целиком
# (без утешительного скина), при победе — фиксированные награды (XP,
# очки турнира, лучший коэффициент недели, прогресс ачивки "lucky_upgrade").
#
# ВАЖНО про импорт `main`: этот модуль подключается в main.py через
# `app.include_router(...)` В САМОМ КОНЦЕ файла (после того, как уже
# определены get_base_price_rub, _instance_from_registry_item,
# _maybe_update_top_drop, _award_xp и т.д. — см. routers/cases.py, та же
# схема). Обращаемся к этим именам как main.<имя> ТОЛЬКО внутри
# обработчика запроса, поэтому циклический импорт main -> routers.upgrader
# -> main безопасен.

from __future__ import annotations

import datetime
import random
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

import items_data
import main
from database import Achievement, Inventory, TournamentScore, User, UserAchievement, async_session

router = APIRouter()

# ---- Шанс победы: (staked_value / target_value) * 100, зажатый в [1%, 80%] ----
CHANCE_MIN_PERCENT = 1.0
CHANCE_MAX_PERCENT = 80.0

# ---- Награды за победу ----
XP_ON_WIN = 15
TOURNAMENT_POINTS_ON_WIN = 15

# ---- Предохранители ----
MAX_STAKE_ITEMS = 6  # симметрично MAX_UPGRADE_ITEMS в main.py

# ---- Ачивка "везунчик апгрейдера": прогресс идёт только если ПОБЕДА
# была одержана при шансе < 10% ----
LUCKY_UPGRADE_ACHIEVEMENT_KEY = "lucky_upgrade"
LUCKY_UPGRADE_CHANCE_THRESHOLD = 10.0  # %


class UpgraderSpinRequest(BaseModel):
    telegram_id: int
    inventory_item_ids: list[int] = Field(default_factory=list)
    add_crystals: float = 0.0
    target_item_id: str


def _current_week_identifier(now: Optional[datetime.datetime] = None) -> str:
    """ISO-неделя вида '2026-W32' — тот же формат, что и в
    database.TournamentScore.week_identifier / routers/cases.py."""
    now = now or datetime.datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def _get_or_create_tournament_score(session, user: User) -> TournamentScore:
    """Достаёт (или создаёт) запись TournamentScore пользователя за ТЕКУЩУЮ
    ISO-неделю. Ничего не коммитит сама — вызывается внутри уже открытой
    транзакции эндпоинта."""
    week = _current_week_identifier()
    result = await session.execute(
        select(TournamentScore).where(
            TournamentScore.user_id == user.id,
            TournamentScore.week_identifier == week,
        )
    )
    score = result.scalar_one_or_none()
    if not score:
        score = TournamentScore(
            user_id=user.id, week_identifier=week, activity_points=0, best_upgrade_mult=0.0
        )
        session.add(score)
    return score


async def _bump_lucky_upgrade_achievement(session, user: User) -> None:
    """Продвигает прогресс ачивки 'lucky_upgrade' на +1. Если каталог
    достижений (Achievement) ещё не засеян этим ключом — прогресс всё
    равно сохраняется в UserAchievement (просто не помечается как
    завершённый до появления соответствующей записи Achievement с
    max_progress)."""
    result = await session.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == user.id,
            UserAchievement.achievement_key == LUCKY_UPGRADE_ACHIEVEMENT_KEY,
        )
    )
    progress = result.scalar_one_or_none()
    if not progress:
        progress = UserAchievement(
            user_id=user.id,
            achievement_key=LUCKY_UPGRADE_ACHIEVEMENT_KEY,
            current_progress=0,
        )
        session.add(progress)

    progress.current_progress = (progress.current_progress or 0) + 1

    achievement_result = await session.execute(
        select(Achievement).where(Achievement.key == LUCKY_UPGRADE_ACHIEVEMENT_KEY)
    )
    achievement = achievement_result.scalar_one_or_none()
    if achievement and not progress.is_completed and progress.current_progress >= achievement.max_progress:
        progress.is_completed = True
        progress.completed_at = datetime.datetime.utcnow()


@router.post("/api/upgrader/spin")
async def upgrader_spin(req: UpgraderSpinRequest):
    ids = list(dict.fromkeys(req.inventory_item_ids or []))  # без дублей, сохраняя порядок
    add_crystals = round(max(req.add_crystals or 0.0, 0.0), 2)

    if not ids and add_crystals <= 0:
        raise HTTPException(400, "Нужно поставить хотя бы один предмет из инвентаря или добавить Кристаллы")
    if len(ids) > MAX_STAKE_ITEMS:
        raise HTTPException(400, f"Максимум {MAX_STAKE_ITEMS} предметов за раз")

    target_entry = items_data.get_item(req.target_item_id)
    if not target_entry:
        raise HTTPException(400, "Целевой предмет не найден в базе")

    async with async_session() as session:
        # with_for_update() — та же защита от гонки параллельных запросов,
        # что и в /api/upgrade (main.py) — реально блокирует строки только
        # на Postgres/MySQL, на SQLite молча игнорируется движком.
        result = await session.execute(
            select(User).where(User.telegram_id == req.telegram_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        if add_crystals > 0 and user.balance < add_crystals:
            raise HTTPException(400, "Недостаточно Кристалликов 💎")

        staked_items: list[Inventory] = []
        if ids:
            result_items = await session.execute(
                select(Inventory)
                .where(Inventory.id.in_(ids), Inventory.user_id == user.id)
                .with_for_update()
            )
            staked_items = list(result_items.scalars().all())
            if len(staked_items) != len(ids):
                raise HTTPException(404, "Один или несколько предметов не найдены в инвентаре")

        staked_items_value = sum(i.skin_price for i in staked_items)
        staked_value = round(staked_items_value + add_crystals, 2)
        if staked_value <= 0:
            raise HTTPException(400, "Ставка должна быть больше нуля")

        target_value = main.get_base_price_rub(target_entry["name"], target_entry["rarity"])
        if target_value <= 0:
            raise HTTPException(400, "Не удалось определить стоимость целевого предмета")

        # ПРАВКИ В ТЗ №2, п.1: если ставка дороже (или равна) целевого
        # предмета, формула (staked/target)*100 даёт коэффициент >= 100%,
        # что ломает саму механику "апгрейда" (выгоднее продать ставку
        # напрямую, чем "улучшать" её на заведомо более дешёвый предмет).
        # Такую ставку прямо запрещаем, а не тихо зажимаем шанс в потолок —
        # игрок должен выбрать более дорогую цель.
        if staked_value >= target_value:
            raise HTTPException(
                400,
                "Целевой предмет должен быть дороже ставки — выбери более дорогую цель",
            )

        chance_percent = (staked_value / target_value) * 100.0
        chance_percent = max(CHANCE_MIN_PERCENT, min(CHANCE_MAX_PERCENT, chance_percent))

        roll = round(random.uniform(0.0, 100.0), 6)
        success = roll <= chance_percent

        # ---- Списание ставки: Кристаллы и заложенные предметы уходят
        # СРАЗУ, вне зависимости от исхода — при победе они "превращаются"
        # в целевой предмет, при проигрыше просто сгорают. ----
        if add_crystals > 0:
            user.balance = round(user.balance - add_crystals, 2)
        for item in staked_items:
            await session.delete(item)

        if not success:
            # ПРАВКИ В ТЗ №13: рефереру (если есть) — % от ПРОИГРАННОЙ ставки.
            await main._credit_referral_loss(session, user, staked_value, source="upgrader")
            await session.commit()
            await session.refresh(user)
            return {
                "success": True,
                "result": "lose",
                "roll": roll,
                "chance_used": round(chance_percent, 2),
                "staked_value": staked_value,
                "target_value": round(target_value, 2),
                "new_balance": user.balance,
            }

        # ---- ПОБЕДА ----
        won_instance = main._instance_from_registry_item(target_entry, target_value)
        new_item = Inventory(
            user_id=user.id,
            skin_name=won_instance["name"],
            skin_price=won_instance["price"],
            rarity=won_instance["rarity"],
            quality=won_instance["quality"],
            stattrak=won_instance["stattrak"],
            float_val=won_instance["float_val"],
            image_url=won_instance["image"],
            obtained_from_case="Апгрейдер",
        )
        session.add(new_item)
        main._maybe_update_top_drop(user, won_instance)

        xp_info = await main._award_xp(session, user, XP_ON_WIN)

        score = await _get_or_create_tournament_score(session, user)
        score.activity_points = (score.activity_points or 0) + TOURNAMENT_POINTS_ON_WIN
        win_multiplier = round(target_value / staked_value, 4)
        if win_multiplier > (score.best_upgrade_mult or 0.0):
            score.best_upgrade_mult = win_multiplier

        lucky_achievement_progressed = False
        if chance_percent < LUCKY_UPGRADE_CHANCE_THRESHOLD:
            await _bump_lucky_upgrade_achievement(session, user)
            lucky_achievement_progressed = True

        # Спринт 9.5: рефереру (если есть) — % от ЧИСТОГО выигрыша
        # (стоимость целевого предмета за вычетом сгоревшей в него ставки).
        await main._credit_referral_win(
            session, user, round(target_value - staked_value, 2), source="upgrader"
        )

        await session.commit()
        await session.refresh(new_item)
        await session.refresh(user)

        return {
            "success": True,
            "result": "win",
            "roll": roll,
            "chance_used": round(chance_percent, 2),
            "staked_value": staked_value,
            "target_value": round(target_value, 2),
            "win_multiplier": win_multiplier,
            "item": {
                "id": new_item.id,
                "name": won_instance["name"],
                "rarity": won_instance["rarity"],
                "quality": won_instance["quality"],
                "quality_name": won_instance["quality_name"],
                "price": won_instance["price"],
                "image": won_instance["image"],
                "stattrak": won_instance["stattrak"],
                "float_val": won_instance["float_val"],
            },
            "xp": xp_info,
            "tournament_points_total": score.activity_points,
            "lucky_achievement_progressed": lucky_achievement_progressed,
            "new_balance": user.balance,
        }
