# ============================================
# СПРИНТ 9.5: Еженедельные Турниры
# ============================================
#
# Две таблицы лидеров за ТЕКУЩУЮ ISO-неделю (та же неделя и тот же формат
# week_identifier, что уже пишут routers/cases.py и routers/upgrader.py в
# TournamentScore — здесь этот модуль только ЧИТАЕТ/подводит итоги, саму
# запись очков ведут остальные роутеры):
#   GET /api/tournament/leaderboard/activity   — "Топ Активности" (activity_points)
#   GET /api/tournament/leaderboard/upgraders  — "Топ Апгрейдеров" (best_upgrade_mult)
#
# Плюс фоновая задача periodic_weekly_payout() (запускается из main.py
# startup_event через asyncio.create_task, та же схема, что и
# currency.periodic_refresh) — раз в минуту проверяет, не наступило ли
# воскресенье 23:59 UTC, и если да — один раз (идемпотентно, через
# TournamentScore.reward_claimed) раздаёт награды ОБОИМ топам за неделю,
# которая в этот момент заканчивается:
#   ТОП-1     — 100 Золота + рамка "Чемпион Недели" + титул "Легенда Турниров"
#   ТОП 2-3   — 50 Золота + рамка "Призёр"
#   ТОП 4-10  — 15 Золота + 50,000 Кристаллов

from __future__ import annotations

import asyncio
import datetime
import logging

from fastapi import APIRouter
from sqlalchemy import select

import cosmetics
from database import TournamentScore, User, async_session

router = APIRouter()

logger = logging.getLogger(__name__)

LEADERBOARD_DEFAULT_LIMIT = 10
LEADERBOARD_MAX_LIMIT = 50

# ---- Награды по местам (общие для обоих топов — "Топ Активности" и
# "Топ Апгрейдеров"; каждый топ подводится и награждается независимо) ----
FRAME_CHAMPION = "champion_of_week"
FRAME_PRIZE_WINNER = "prize_winner"
TITLE_TOURNAMENT_LEGEND = "legend_of_tournaments"


def _current_week_identifier(now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _user_public(user: User) -> dict:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "photo_url": user.photo_url,
        "selected_frame": user.selected_frame,
        "selected_title": user.selected_title,
    }


@router.get("/api/tournament/leaderboard/activity")
async def leaderboard_activity(limit: int = LEADERBOARD_DEFAULT_LIMIT):
    """Топ Активности текущей недели — по очкам за открытия, контракты,
    апгрейды (TournamentScore.activity_points, начисляется в
    routers/cases.py, routers/contracts.py, routers/upgrader.py)."""
    limit = max(1, min(limit, LEADERBOARD_MAX_LIMIT))
    week = _current_week_identifier()

    async with async_session() as session:
        result = await session.execute(
            select(TournamentScore, User)
            .join(User, User.id == TournamentScore.user_id)
            .where(TournamentScore.week_identifier == week, TournamentScore.activity_points > 0)
            .order_by(TournamentScore.activity_points.desc())
            .limit(limit)
        )
        rows = result.all()

        return {
            "week": week,
            "leaderboard": [
                {
                    "rank": i + 1,
                    "activity_points": score.activity_points,
                    **_user_public(user),
                }
                for i, (score, user) in enumerate(rows)
            ],
        }


@router.get("/api/tournament/leaderboard/upgraders")
async def leaderboard_upgraders(limit: int = LEADERBOARD_DEFAULT_LIMIT):
    """Топ Апгрейдеров текущей недели — по рекордному коэффициенту
    выигрыша (TournamentScore.best_upgrade_mult, см. routers/upgrader.py)."""
    limit = max(1, min(limit, LEADERBOARD_MAX_LIMIT))
    week = _current_week_identifier()

    async with async_session() as session:
        result = await session.execute(
            select(TournamentScore, User)
            .join(User, User.id == TournamentScore.user_id)
            .where(TournamentScore.week_identifier == week, TournamentScore.best_upgrade_mult > 0)
            .order_by(TournamentScore.best_upgrade_mult.desc())
            .limit(limit)
        )
        rows = result.all()

        return {
            "week": week,
            "leaderboard": [
                {
                    "rank": i + 1,
                    "best_upgrade_mult": score.best_upgrade_mult,
                    **_user_public(user),
                }
                for i, (score, user) in enumerate(rows)
            ],
        }


def _apply_rank_reward(user: User, rank: int) -> None:
    """Начисляет награду по месту в топе ПРЯМО в переданный User (не
    коммитит) — общая шкала для обоих топов недели. Косметика (рамка/
    титул) присваивается через selected_frame/selected_title — если игрок
    получает награду сразу по двум топам, более старший приз (обработанный
    позже в порядке activity -> upgraders) просто перезатирает косметику
    младшего, а Золото/Кристаллы при этом складываются за оба топа.

    Спринт 10: помимо ВЫБОРА (selected_*) теперь фиксируем и само ВЛАДЕНИЕ
    косметикой через cosmetics.grant_* (unlocked_titles/unlocked_frames).
    Раньше записывался только выбор — и стоило игроку переключиться на
    другой титул/рамку в профиле, наградная косметика исчезала навсегда,
    т.к. в списке открытого её не было и селектор её больше не предлагал."""
    if rank == 1:
        user.gold_balance = round((user.gold_balance or 0.0) + 100.0, 2)
        cosmetics.grant_frame(user, FRAME_CHAMPION)
        cosmetics.grant_title(user, TITLE_TOURNAMENT_LEGEND)
        user.selected_frame = FRAME_CHAMPION
        user.selected_title = TITLE_TOURNAMENT_LEGEND
    elif rank in (2, 3):
        user.gold_balance = round((user.gold_balance or 0.0) + 50.0, 2)
        cosmetics.grant_frame(user, FRAME_PRIZE_WINNER)
        user.selected_frame = FRAME_PRIZE_WINNER
    elif 4 <= rank <= 10:
        user.gold_balance = round((user.gold_balance or 0.0) + 15.0, 2)
        user.balance = round((user.balance or 0.0) + 50000.0, 2)


async def run_weekly_payout(week: str | None = None) -> dict:
    """Подводит итоги недели `week` (по умолчанию — текущая ISO-неделя,
    которая в момент вызова как раз заканчивается) и раздаёт награды
    ТОП-10 каждого из двух топов НЕЗАВИСИМО (см. reward_claimed_activity /
    reward_claimed_upgraders в database.py — если игрок попал в оба топа,
    получает награду за КАЖДЫЙ из них). Идемпотентно: строки
    TournamentScore, уже помеченные соответствующим флагом, повторно по
    этому топу не награждаются — можно смело вызывать функцию хоть каждую
    минуту в течение payout-окна."""
    week = week or _current_week_identifier()

    async with async_session() as session:
        result = await session.execute(
            select(TournamentScore, User)
            .join(User, User.id == TournamentScore.user_id)
            .where(TournamentScore.week_identifier == week)
        )
        rows = result.all()

        activity_ranked = sorted(
            (r for r in rows if r[0].activity_points > 0),
            key=lambda r: r[0].activity_points,
            reverse=True,
        )[:10]
        upgrader_ranked = sorted(
            (r for r in rows if (r[0].best_upgrade_mult or 0) > 0),
            key=lambda r: r[0].best_upgrade_mult,
            reverse=True,
        )[:10]

        rewarded_users = []
        for board_name, board, claimed_attr in (
            ("activity", activity_ranked, "reward_claimed_activity"),
            ("upgraders", upgrader_ranked, "reward_claimed_upgraders"),
        ):
            for i, (score, user) in enumerate(board):
                if getattr(score, claimed_attr):
                    continue  # уже награждён этим (или другим) прогоном за эту неделю по ЭТОМУ топу
                rank = i + 1
                _apply_rank_reward(user, rank)
                setattr(score, claimed_attr, True)
                rewarded_users.append({"telegram_id": user.telegram_id, "rank": rank, "board": board_name})

        await session.commit()

        logger.info(f"[tournament] Итоги недели {week} подведены, награждено записей: {len(rewarded_users)}")
        return {"week": week, "rewarded": rewarded_users}


_last_payout_week: str | None = None


async def periodic_weekly_payout(check_interval_seconds: int = 60) -> None:
    """Фоновая задача (см. main.py startup_event, та же схема, что и
    currency.periodic_refresh): раз в check_interval_seconds проверяет,
    не наступило ли воскресенье 23:59 UTC — момент окончания ISO-недели
    (недели по isocalendar() идут Пн-Вс, так что 23:59 вс — последняя
    минута ТЕКУЩЕЙ недели, а не следующей). _last_payout_week защищает от
    повторного запуска в течение той же минуты-окна на случай рестарта
    процесса ровно в этот момент (TournamentScore.reward_claimed —
    вторая, персистентная линия защиты от повторной выдачи наград)."""
    global _last_payout_week
    while True:
        try:
            now = datetime.datetime.utcnow()
            if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
                week = _current_week_identifier(now)
                if _last_payout_week != week:
                    await run_weekly_payout(week)
                    _last_payout_week = week
        except Exception:
            logger.exception("[tournament] Ошибка в periodic_weekly_payout")

        await asyncio.sleep(check_interval_seconds)
