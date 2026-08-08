# ============================================
# СПРИНТ 7: Социальные Задания (Free Gold Tasks)
# ============================================
#
# GET  /api/tasks/list  — список активных заданий + статус выполнения для
#                          текущего игрока (НЕ было явно в ТЗ, но нужно
#                          фронту, чтобы отрисовать список заданий ДО
#                          проверки — тот же паттерн, что и GET
#                          /api/wheel/status / GET /api/streak/status).
# POST /api/tasks/check
#   { "telegram_id": 123456789, "task_key": "sub_channel" }
#
# Задания (см. ТЗ спринта 7):
#   - sub_channel   (10 Gold): getChatMember в канале -> 'member' / 'administrator' / 'creator'
#   - join_chat     (5 Gold):  getChatMember в чате    -> 'member' / 'administrator' / 'creator'
#   - invite_3_refs (15 Gold): count(User.referred_by == telegram_id) >= 3
#   - set_avatar    (3 Gold):  установлена кастомная рамка/титул профиля
#     (User.selected_frame или User.selected_title не пустые — отдельного
#     поля для "кастомного аватара" в этой кодовой базе нет, косметика
#     профиля — это именно рамки/титулы, см. database.py User).
#
# Задания хранятся в таблице Task (уже существует в database.py, см.
# сид seed_default_tasks ниже), выполнения — в UserTaskCompletion с
# UNIQUE(user_id, task_id), поэтому повторное выполнение того же задания
# физически невозможно на уровне БД (доп. проверка в коде — для красивой
# ошибки 400 вместо голого IntegrityError).
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у остальных
# роутеров — подключается в main.py в самом конце файла.

from __future__ import annotations

import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

import config
from database import Task, User, UserTaskCompletion, async_session

router = APIRouter()

# ---- ПРАВКИ В ТЗ №6: сколько дней после Task.created_at задание считается
# "новым" и показывается с мигающей плашкой NEW на фронте. ----
TASK_NEW_BADGE_DAYS = 7

# ---- Статусы участника чата/канала, которые Telegram Bot API считает
# "подписан"/"состоит" (getChatMember.result.status) ----
_MEMBER_OK_STATUSES = {"member", "administrator", "creator"}

# ---- Дефолтный набор заданий: ключ -> (тип, награда Gold, тайтл, описание,
# ссылка для кнопки "Перейти" на фронте). Засеивается в БД при старте
# сервера (см. seed_default_tasks), чтобы Task.key/reward_gold всегда
# соответствовали текущему ТЗ, даже если строки уже были созданы раньше
# с другими значениями (апсерт по key). ----
DEFAULT_TASKS = [
    {
        "key": "sub_channel",
        "title": "Подписаться на канал",
        "description": "Подпишись на наш Telegram-канал и получи награду",
        "reward_gold": 10.0,
        "task_type": "telegram_channel",
        "action_url": f"https://t.me/{config.SOCIAL_CHANNEL_USERNAME}",
    },
    {
        "key": "join_chat",
        "title": "Вступить в чат",
        "description": "Вступи в наш Telegram-чат и получи награду",
        "reward_gold": 5.0,
        "task_type": "telegram_chat",
        "action_url": f"https://t.me/{config.SOCIAL_CHAT_USERNAME}",
    },
    {
        "key": "invite_3_refs",
        "title": f"Пригласить {config.REQUIRED_REFERRALS_FOR_TASK} друзей",
        "description": f"Пригласи {config.REQUIRED_REFERRALS_FOR_TASK} друзей по своей реферальной ссылке",
        "reward_gold": 15.0,
        "task_type": "referrals",
        "action_url": None,
    },
    {
        "key": "set_avatar",
        "title": "Установить рамку или титул",
        "description": "Выбери кастомную рамку или титул профиля в косметике",
        "reward_gold": 3.0,
        "task_type": "profile",
        "action_url": None,
    },
]


async def seed_default_tasks(session) -> None:
    """Апсерт дефолтных заданий по Task.key — вызывается один раз при
    старте сервера (см. main.py startup_event), ПОСЛЕ init_db(), чтобы
    таблица tasks уже точно существовала. Идемпотентно: при повторном
    запуске обновляет уже существующие строки (title/description/reward/
    action_url) вместо создания дублей, чтобы правки ТЗ применялись без
    ручных UPDATE в проде."""
    result = await session.execute(select(Task))
    existing = {t.key: t for t in result.scalars().all()}

    for def_ in DEFAULT_TASKS:
        task = existing.get(def_["key"])
        if task is None:
            session.add(Task(
                key=def_["key"],
                title=def_["title"],
                description=def_["description"],
                reward_gold=def_["reward_gold"],
                reward_crystals=0.0,
                action_url=def_["action_url"],
                task_type=def_["task_type"],
                is_active=True,
            ))
        else:
            task.title = def_["title"]
            task.description = def_["description"]
            task.reward_gold = def_["reward_gold"]
            task.action_url = def_["action_url"]
            task.task_type = def_["task_type"]
            task.is_active = True

    await session.commit()


async def _check_telegram_membership(chat_username: str, telegram_user_id: int) -> bool:
    """Спрашивает Telegram Bot API, состоит ли пользователь в канале/чате
    @chat_username. Бот должен быть добавлен туда админом, иначе Telegram
    вернёт ok:false (в этом случае честно считаем задание невыполненным,
    а не роняем 500 — это как правило означает, что канал ещё не
    настроен, а не ошибку пользователя)."""
    if not chat_username or chat_username == "заглшука":
        raise HTTPException(500, "Канал/чат для этого задания ещё не настроен (см. config.py)")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/getChatMember",
            params={"chat_id": f"@{chat_username}", "user_id": telegram_user_id},
        )
    payload = resp.json()
    if not payload.get("ok"):
        # Пользователь не найден в чате / бот не админ / канал не существует —
        # в любом из этих случаев задание считаем невыполненным, а не ошибкой.
        return False

    status = payload["result"].get("status")
    return status in _MEMBER_OK_STATUSES


async def _verify_task(session, user: User, task: Task) -> bool:
    """Выполняет проверку конкретного задания и возвращает True/False —
    выполнено оно фактически прямо сейчас или нет. Ничего не начисляет и
    не коммитит — это делает вызывающий код (POST /api/tasks/check) ПОСЛЕ
    успешной проверки."""
    if task.key == "sub_channel":
        return await _check_telegram_membership(config.SOCIAL_CHANNEL_USERNAME, user.telegram_id)

    if task.key == "join_chat":
        return await _check_telegram_membership(config.SOCIAL_CHAT_USERNAME, user.telegram_id)

    if task.key == "invite_3_refs":
        result = await session.execute(
            select(func.count(User.id)).where(User.referred_by == user.telegram_id)
        )
        referrals_count = result.scalar() or 0
        return referrals_count >= config.REQUIRED_REFERRALS_FOR_TASK

    if task.key == "set_avatar":
        return bool(user.selected_frame) or bool(user.selected_title)

    # Неизвестный/будущий тип задания — по умолчанию считаем невыполненным,
    # а не бросаем 500, чтобы список заданий не ломался при добавлении
    # нового ключа в DEFAULT_TASKS без соответствующей ветки проверки.
    return False


@router.get("/api/tasks/list")
async def tasks_list(telegram_id: int):
    async with async_session() as session:
        result_user = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_tasks = await session.execute(
            select(Task).where(Task.is_active == True).order_by(Task.id)  # noqa: E712
        )
        tasks = result_tasks.scalars().all()

        result_completions = await session.execute(
            select(UserTaskCompletion.task_id).where(UserTaskCompletion.user_id == user.id)
        )
        completed_task_ids = {row[0] for row in result_completions.all()}

        result_ref_count = await session.execute(
            select(func.count(User.id)).where(User.referred_by == user.telegram_id)
        )
        referrals_count = result_ref_count.scalar() or 0

        now = datetime.datetime.utcnow()
        new_threshold = datetime.timedelta(days=TASK_NEW_BADGE_DAYS)

        return {
            "gold_balance": user.gold_balance,
            "referrals_count": referrals_count,
            "tasks": [
                {
                    "key": task.key,
                    "title": task.title,
                    "description": task.description,
                    "reward_gold": task.reward_gold,
                    "reward_crystals": task.reward_crystals,
                    "task_type": task.task_type,
                    "action_url": task.action_url,
                    "completed": task.id in completed_task_ids,
                    # ПРАВКИ В ТЗ №6: плашка "NEW" для заданий младше
                    # TASK_NEW_BADGE_DAYS дней (created_at бэкфиллится
                    # автомиграцией у уже существующих строк — см. database.py).
                    "is_new": bool(task.created_at and (now - task.created_at) < new_threshold),
                }
                for task in tasks
            ],
        }


class TaskCheckRequest(BaseModel):
    telegram_id: int
    task_key: str


@router.post("/api/tasks/check")
async def tasks_check(req: TaskCheckRequest):
    async with async_session() as session:
        result_user = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result_user.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        result_task = await session.execute(
            select(Task).where(Task.key == req.task_key, Task.is_active == True)  # noqa: E712
        )
        task = result_task.scalar_one_or_none()
        if not task:
            raise HTTPException(404, "Задание не найдено")

        result_completion = await session.execute(
            select(UserTaskCompletion).where(
                UserTaskCompletion.user_id == user.id,
                UserTaskCompletion.task_id == task.id,
            )
        )
        if result_completion.scalar_one_or_none():
            raise HTTPException(400, "Задание уже выполнено")

        is_verified = await _verify_task(session, user, task)
        if not is_verified:
            return {"success": False, "task_key": task.key, "verified": False}

        session.add(UserTaskCompletion(user_id=user.id, task_id=task.id))
        user.gold_balance = round((user.gold_balance or 0.0) + (task.reward_gold or 0.0), 2)
        if task.reward_crystals:
            user.balance = round((user.balance or 0.0) + task.reward_crystals, 2)

        await session.commit()
        await session.refresh(user)

        return {
            "success": True,
            "task_key": task.key,
            "verified": True,
            "reward_gold": task.reward_gold,
            "reward_crystals": task.reward_crystals,
            "new_gold_balance": user.gold_balance,
            "new_balance": user.balance,
        }
