# ============================================
# СПРИНТ 10: Модуль «Друзья»
# ============================================
#
# Эндпоинты:
#   GET  /api/friends/search    — поиск игрока по TG ID или username
#   POST /api/friends/request   — отправить заявку в друзья
#   GET  /api/friends/requests  — входящие + исходящие заявки
#   POST /api/friends/respond   — принять / отклонить входящую заявку
#   GET  /api/friends/list      — список друзей
#   POST /api/friends/remove    — удалить из друзей
#   GET  /api/friends/profile   — публичная карточка профиля игрока
#
# Модель данных — одна таблица Friendship со статусом (см. подробное
# обоснование в database.py): заявка и дружба — это одна связь на разных
# стадиях. Дружба НЕнаправленная, поэтому в любом запросе списка друзей мы
# смотрим ОБА поля (from_user_id / to_user_id) и "другом" считаем ту
# сторону, которая не равна нам.
#
# Как и остальные роутеры проекта, main импортируется локально внутри
# обработчиков (см. комментарий в routers/cases.py).

from __future__ import annotations

import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select

import cosmetics
import levels
import ranks
from database import Friendship, Inventory, User, async_session

router = APIRouter()

SEARCH_LIMIT = 20

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"


# ---------------------------------------------------------------
# Схемы запросов
# ---------------------------------------------------------------
class FriendRequestBody(BaseModel):
    telegram_id: int
    target_telegram_id: int


class RespondBody(BaseModel):
    telegram_id: int
    request_id: int
    action: str          # "accept" | "decline"


class RemoveFriendBody(BaseModel):
    telegram_id: int
    friend_telegram_id: int


# ---------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------
async def _get_user(session, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


def _user_card(user: User) -> dict:
    """Короткая карточка игрока для списков (поиск, друзья, заявки).
    Титул и рамка включены сюда сразу — косметика профиля должна быть видна
    везде, где игрок появляется, а не только на его собственном экране."""
    level = levels.level_from_xp(user.xp or 0)
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "photo_url": user.photo_url,
        "level": level,
        "is_vip": bool(user.is_vip),
        "selected_title": user.selected_title,
        "selected_frame": user.selected_frame,
        "title_info": cosmetics.title_public(user.selected_title),
        "frame_info": cosmetics.frame_public(user.selected_frame),
    }


async def _relation(session, me: User, other_id: int) -> Friendship | None:
    """Находит связь между двумя игроками в ЛЮБОМ направлении. Нужна и для
    поиска (показать кнопку «Добавить» / «Заявка отправлена» / «В друзьях»),
    и чтобы не создавать дубли заявок."""
    result = await session.execute(
        select(Friendship).where(
            or_(
                (Friendship.from_user_id == me.id) & (Friendship.to_user_id == other_id),
                (Friendship.from_user_id == other_id) & (Friendship.to_user_id == me.id),
            )
        )
    )
    return result.scalars().first()


def _relation_state(link: Friendship | None, me_id: int) -> str:
    """Переводит запись связи в состояние для кнопки в UI:
      none              — связи нет, можно отправить заявку
      friends           — уже друзья
      request_sent      — я отправил заявку, ждём ответа
      request_incoming  — мне отправили заявку, можно принять
    Отклонённая заявка трактуется как none: игрок вправе попробовать снова."""
    if not link:
        return "none"
    if link.status == STATUS_ACCEPTED:
        return "friends"
    if link.status == STATUS_PENDING:
        return "request_sent" if link.from_user_id == me_id else "request_incoming"
    return "none"


# ---------------------------------------------------------------
# Поиск
# ---------------------------------------------------------------
@router.get("/api/friends/search")
async def search_players(telegram_id: int, q: str, limit: int = SEARCH_LIMIT):
    """Поиск игрока по Telegram ID (если запрос — целое число) или по
    username / имени (регистронезависимое совпадение по подстроке).

    Себя из результатов исключаем, и к каждому найденному сразу отдаём
    relation_state — чтобы фронт нарисовал правильную кнопку без второго
    запроса на каждого игрока."""
    q = (q or "").strip().lstrip("@")
    if len(q) < 2:
        raise HTTPException(400, "Введите минимум 2 символа или Telegram ID")

    limit = max(1, min(limit, SEARCH_LIMIT))

    async with async_session() as session:
        me = await _get_user(session, telegram_id)

        conditions = [
            func.lower(User.username).like(f"%{q.lower()}%"),
            func.lower(User.first_name).like(f"%{q.lower()}%"),
        ]
        # Числовой запрос трактуем ТАКЖЕ как точный поиск по Telegram ID —
        # по ТЗ поиск идёт «по TG ID / Username», поэтому одно поле ввода
        # обслуживает оба случая.
        if q.isdigit():
            conditions.append(User.telegram_id == int(q))

        result = await session.execute(
            select(User).where(or_(*conditions), User.id != me.id).limit(limit)
        )
        found = result.scalars().all()

        cards = []
        for user in found:
            link = await _relation(session, me, user.id)
            cards.append({
                **_user_card(user),
                "relation_state": _relation_state(link, me.id),
                "request_id": link.id if link and link.status == STATUS_PENDING else None,
            })

        return {"query": q, "results": cards}


# ---------------------------------------------------------------
# Заявки
# ---------------------------------------------------------------
@router.post("/api/friends/request")
async def send_request(req: FriendRequestBody):
    """Отправляет заявку в друзья.

    Особый случай — ВСТРЕЧНАЯ заявка: если игрок B уже отправил заявку A, а
    теперь A отправляет заявку B, вторую строку мы не создаём (это была бы
    та же связь в обратную сторону), а сразу ПРИНИМАЕМ существующую —
    обоюдное желание добавить друг друга и есть дружба."""
    if req.telegram_id == req.target_telegram_id:
        raise HTTPException(400, "Нельзя добавить в друзья самого себя")

    async with async_session() as session:
        me = await _get_user(session, req.telegram_id)
        target = await _get_user(session, req.target_telegram_id)

        link = await _relation(session, me, target.id)

        if link:
            if link.status == STATUS_ACCEPTED:
                raise HTTPException(400, "Вы уже друзья")
            if link.status == STATUS_PENDING:
                if link.from_user_id == me.id:
                    raise HTTPException(400, "Заявка уже отправлена")
                # встречная заявка — принимаем существующую
                link.status = STATUS_ACCEPTED
                link.responded_at = datetime.datetime.utcnow()
                await session.commit()
                return {"success": True, "state": "friends", "friend": _user_card(target)}
            # была отклонена — переиспользуем ту же строку, чтобы не
            # нарушить UniqueConstraint(from_user_id, to_user_id)
            link.from_user_id = me.id
            link.to_user_id = target.id
            link.status = STATUS_PENDING
            link.created_at = datetime.datetime.utcnow()
            link.responded_at = None
            await session.commit()
            return {"success": True, "state": "request_sent", "request_id": link.id}

        link = Friendship(from_user_id=me.id, to_user_id=target.id, status=STATUS_PENDING)
        session.add(link)
        await session.commit()
        await session.refresh(link)

        return {"success": True, "state": "request_sent", "request_id": link.id}


@router.get("/api/friends/requests")
async def list_requests(telegram_id: int):
    """Входящие (нужно ответить) и исходящие (ждём ответа) заявки."""
    async with async_session() as session:
        me = await _get_user(session, telegram_id)

        incoming_res = await session.execute(
            select(Friendship, User)
            .join(User, User.id == Friendship.from_user_id)
            .where(Friendship.to_user_id == me.id, Friendship.status == STATUS_PENDING)
            .order_by(Friendship.created_at.desc())
        )
        outgoing_res = await session.execute(
            select(Friendship, User)
            .join(User, User.id == Friendship.to_user_id)
            .where(Friendship.from_user_id == me.id, Friendship.status == STATUS_PENDING)
            .order_by(Friendship.created_at.desc())
        )

        return {
            "incoming": [
                {"request_id": link.id, "created_at": link.created_at.isoformat() if link.created_at else None, **_user_card(user)}
                for link, user in incoming_res.all()
            ],
            "outgoing": [
                {"request_id": link.id, "created_at": link.created_at.isoformat() if link.created_at else None, **_user_card(user)}
                for link, user in outgoing_res.all()
            ],
        }


@router.post("/api/friends/respond")
async def respond_request(req: RespondBody):
    """Принять или отклонить ВХОДЯЩУЮ заявку. Отвечать может только
    получатель (to_user_id) — инициатор своей же заявкой распорядиться
    не может."""
    if req.action not in ("accept", "decline"):
        raise HTTPException(400, "action должен быть 'accept' или 'decline'")

    async with async_session() as session:
        me = await _get_user(session, req.telegram_id)

        result = await session.execute(select(Friendship).where(Friendship.id == req.request_id))
        link = result.scalar_one_or_none()
        if not link:
            raise HTTPException(404, "Заявка не найдена")
        if link.to_user_id != me.id:
            raise HTTPException(403, "Это не ваша заявка")
        if link.status != STATUS_PENDING:
            raise HTTPException(400, "Заявка уже обработана")

        link.status = STATUS_ACCEPTED if req.action == "accept" else STATUS_DECLINED
        link.responded_at = datetime.datetime.utcnow()
        await session.commit()

        return {"success": True, "state": "friends" if req.action == "accept" else "none"}


# ---------------------------------------------------------------
# Список друзей / удаление
# ---------------------------------------------------------------
@router.get("/api/friends/list")
async def list_friends(telegram_id: int):
    """Список друзей. Дружба ненаправленная, поэтому выбираем принятые
    связи, где мы с ЛЮБОЙ стороны, и берём противоположный id."""
    async with async_session() as session:
        me = await _get_user(session, telegram_id)

        result = await session.execute(
            select(Friendship).where(
                Friendship.status == STATUS_ACCEPTED,
                or_(Friendship.from_user_id == me.id, Friendship.to_user_id == me.id),
            )
        )
        links = result.scalars().all()

        friend_ids = [
            link.to_user_id if link.from_user_id == me.id else link.from_user_id
            for link in links
        ]
        if not friend_ids:
            return {"friends": [], "count": 0}

        users_res = await session.execute(select(User).where(User.id.in_(friend_ids)))
        friends = users_res.scalars().all()
        # Сортируем по уровню — самые прокачанные друзья сверху.
        cards = sorted(
            (_user_card(u) for u in friends),
            key=lambda c: c["level"],
            reverse=True,
        )

        return {"friends": cards, "count": len(cards)}


@router.post("/api/friends/remove")
async def remove_friend(req: RemoveFriendBody):
    """Удаляет из друзей — строку связи именно УДАЛЯЕМ, а не переводим в
    declined, чтобы обе стороны могли позже добавить друг друга заново
    без упора в UniqueConstraint."""
    async with async_session() as session:
        me = await _get_user(session, req.telegram_id)
        friend = await _get_user(session, req.friend_telegram_id)

        link = await _relation(session, me, friend.id)
        if not link or link.status != STATUS_ACCEPTED:
            raise HTTPException(404, "Вы не в друзьях")

        await session.delete(link)
        await session.commit()

        return {"success": True, "state": "none"}


# ---------------------------------------------------------------
# Публичная карточка профиля
# ---------------------------------------------------------------
@router.get("/api/friends/profile")
async def public_profile(telegram_id: int, target_telegram_id: int):
    """Публичная карточка профиля другого игрока.

    Отдаём СТРОГО публичные данные: имя/аватар, титул и рамку, уровень и
    ранг, витрину и топ-дроп, обезличенную статистику. Приватного (баланс,
    Золото, реферальный код и заработок, полный инвентарь, настройки) здесь
    НЕТ и быть не должно — эндпоинт доступен любому игроку, а не только
    друзьям, чтобы карточку можно было открыть прямо из результатов поиска."""
    async with async_session() as session:
        me = await _get_user(session, telegram_id)
        target = await _get_user(session, target_telegram_id)

        inv_res = await session.execute(select(Inventory).where(Inventory.user_id == target.id))
        inventory = inv_res.scalars().all()
        total_value = sum(i.skin_price for i in inventory) if inventory else 0

        showcase = sorted(
            (i for i in inventory if i.is_in_showcase),
            key=lambda i: i.skin_price,
            reverse=True,
        )

        refs_res = await session.execute(
            select(func.count(User.id)).where(User.referred_by == target.telegram_id)
        )

        link = await _relation(session, me, target.id)
        level_info = levels.get_level_progress(target.xp or 0)

        import main   # локальный импорт: см. комментарий в шапке модуля

        return {
            **_user_card(target),
            "is_self": target.id == me.id,
            "relation_state": _relation_state(link, me.id),
            "request_id": link.id if link and link.status == STATUS_PENDING else None,
            "level_info": level_info,
            "rank": ranks.get_rank_progress(target.xp or 0, target.rank_level or 0),
            "stats": {
                "total_cases_opened": target.total_cases_opened or 0,
                "favorite_case": target.favorite_case or "—",
                "inventory_count": len(inventory),
                "inventory_total_value": round(total_value, 0),
                "referrals_count": refs_res.scalar() or 0,
                "daily_streak": target.daily_streak or 0,
                "knife_drops_count": target.knife_drops_count or 0,
                "covert_drops_count": target.covert_drops_count or 0,
            },
            "top_drop": {
                "name": target.top_drop_name,
                "price": target.top_drop_price,
                "rarity": target.top_drop_rarity,
                "image": target.top_drop_image,
            } if target.top_drop_name else None,
            "showcase": {
                "slots": level_info["showcase_slots"],
                "items": [main.serialize_inventory_item(i) for i in showcase],
            },
            "titles": [t for t in cosmetics.serialize_titles(target, level=level_info["level"]) if t["unlocked"]],
            "created_at": target.created_at.isoformat() if target.created_at else None,
        }
