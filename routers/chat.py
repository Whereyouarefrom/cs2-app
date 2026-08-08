# ============================================
# СПРИНТ 11: Глобальный чат, авто-модерация и жалобы
# ============================================
#
# GET  /api/chat/messages?telegram_id=...&after_id=...
#     — последние видимые (не скрытые) сообщения глобального чата + статус
#       мута/бана текущего игрока (чтобы фронт заранее заблокировал ввод).
# POST /api/chat/send   { telegram_id, text }
#     — отправка сообщения с проверками: бан чата → мут → rate-limit
#       (config.CHAT_RATE_LIMIT_SECONDS) → авто-фильтр (ссылки/казино/VPN/18+).
#       Нарушение авто-фильтра => сообщение сохраняется скрытым
#       (is_hidden=True, hide_reason="auto_filter"), игроку выдаётся
#       АВТО-МУТ на config.CHAT_AUTO_MUTE_HOURS часов, админ уведомляется.
# POST /api/chat/report { telegram_id, message_id }
#     — жалоба на сообщение. При 3+ (config.CHAT_REPORT_THRESHOLD) жалобах
#       от РАЗНЫХ игроков за config.CHAT_REPORT_WINDOW_MINUTES минут
#       сообщение авто-скрывается (is_hidden=True) и уходит админу в Telegram.
#
# Авто-лента дорогих дропов (системные сообщения is_system=True) публикуется
# НЕ отсюда, а из main._maybe_post_drop_to_chat при открытии кейса — см. main.py.
#
# ВАЖНО про импорт `main`: та же отложенная схема, что и у остальных
# роутеров — модуль подключается в main.py в самом конце файла. Здесь main
# нужен только ради main.notify_admin_telegram (общий helper Bot API).

from __future__ import annotations

import datetime
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, distinct

import config
import main
from database import async_session, User, ChatMessage, ChatReport

router = APIRouter()


# ---- Детектор ссылок: http(s)://..., www...., t.me/..., голый домен.зона/... ----
# Ловит и "csgorun.com", и "заходи на t.me/xxx", и "http://foo.bar".
_LINK_RE = re.compile(
    r"(https?://\S+"                       # http:// или https://
    r"|www\.\S+"                            # www.
    r"|t\.me/\S+"                           # t.me/...
    r"|\b[a-z0-9\-]+\.[a-z]{2,}(?:/\S*)?)",  # голый домен вида name.tld[/path]
    re.IGNORECASE,
)


def _extract_links(text: str) -> list[str]:
    return [m.group(0).lower() for m in _LINK_RE.finditer(text or "")]


def _is_official_link(link: str) -> bool:
    """True, если ссылка ведёт на официальный домен симулятора
    (config.CHAT_OFFICIAL_LINK_WHITELIST) — такие автофильтр пропускает."""
    normalized = link.replace("https://", "").replace("http://", "").replace("www.", "")
    return any(
        allowed.lower().replace("https://", "").replace("http://", "").replace("www.", "") in normalized
        for allowed in config.CHAT_OFFICIAL_LINK_WHITELIST
    )


def _auto_filter_reason(text: str) -> str | None:
    """Возвращает причину блокировки сообщения авто-фильтром или None, если
    сообщение чистое. Причины: 'link' (реклама/сторонняя ссылка вне белого
    списка) либо 'keyword:<слово>' (казино/рулетка/VPN/18+)."""
    low = (text or "").lower()

    # 1) Запрещённые ключевые слова (казино/рулетки/VPN/18+)
    for kw in config.CHAT_BANNED_KEYWORDS:
        if kw.lower() in low:
            return f"keyword:{kw}"

    # 2) Любая сторонняя ссылка вне белого списка официальных доменов
    for link in _extract_links(text):
        if not _is_official_link(link):
            return "link"

    return None


def _mute_state(user: User, now: datetime.datetime) -> tuple[bool, datetime.datetime | None]:
    """Активен ли мут прямо сейчас. Возвращает (muted, mute_until).
    mute_until=None при is_muted=True трактуется как мут навсегда;
    просроченный мут (mute_until в прошлом) считается снятым."""
    if not user.is_muted:
        return False, None
    if user.mute_until is None:
        return True, None
    if user.mute_until > now:
        return True, user.mute_until
    return False, user.mute_until  # мут истёк


async def _serialize_messages(session, rows: list[ChatMessage]) -> list[dict]:
    """Собирает сообщения + краткие данные их авторов (имя/аватар) одним
    запросом, чтобы не дёргать БД по одному пользователю на сообщение."""
    if not rows:
        return []
    user_ids = {m.user_id for m in rows}
    res = await session.execute(select(User).where(User.id.in_(user_ids)))
    users = {u.id: u for u in res.scalars().all()}

    out = []
    for m in rows:
        author = users.get(m.user_id)
        out.append({
            "id": m.id,
            "text": m.text,
            "is_system": bool(m.is_system),
            "user_id": m.user_id,
            "author_telegram_id": author.telegram_id if author else None,
            "author_name": (author.first_name or author.username or "Игрок") if author else "Игрок",
            "author_photo": author.photo_url if author else None,
            "created_at": (m.created_at or datetime.datetime.utcnow()).isoformat(),
        })
    return out


# ============================================
# GET /api/chat/messages
# ============================================
@router.get("/api/chat/messages")
async def get_messages(telegram_id: int, after_id: int = 0, limit: int = 50):
    limit = max(1, min(limit, 100))
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        query = (
            select(ChatMessage)
            .where(ChatMessage.is_hidden == False)  # noqa: E712 — скрытые не отдаём
        )
        if after_id:
            # Инкрементальный опрос: только сообщения новее уже показанных.
            query = query.where(ChatMessage.id > after_id).order_by(ChatMessage.id.asc()).limit(limit)
            rows = (await session.execute(query)).scalars().all()
        else:
            # Первичная загрузка: последние N, но отдаём по возрастанию id.
            query = query.order_by(ChatMessage.id.desc()).limit(limit)
            rows = list((await session.execute(query)).scalars().all())[::-1]

        now = datetime.datetime.utcnow()
        muted, mute_until = _mute_state(user, now)

        return {
            "messages": await _serialize_messages(session, rows),
            "me": {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "is_chat_banned": bool(user.is_chat_banned),
                "is_muted": muted,
                "mute_until": mute_until.isoformat() if mute_until else None,
                "mute_reason": user.mute_reason if muted else None,
            },
            "rate_limit_seconds": config.CHAT_RATE_LIMIT_SECONDS,
        }


# ============================================
# POST /api/chat/send
# ============================================
class SendRequest(BaseModel):
    telegram_id: int
    text: str


@router.post("/api/chat/send")
async def send_message(req: SendRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    if len(text) > config.CHAT_MESSAGE_MAX_LENGTH:
        raise HTTPException(400, f"Слишком длинное сообщение (максимум {config.CHAT_MESSAGE_MAX_LENGTH} символов)")

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        now = datetime.datetime.utcnow()

        # 1) Полный бан чата (жёстче мута) — писать нельзя вообще.
        if user.is_chat_banned:
            raise HTTPException(403, "Вы заблокированы в чате")

        # 2) Активный мут.
        muted, mute_until = _mute_state(user, now)
        if muted:
            if mute_until:
                left = int((mute_until - now).total_seconds() // 60) + 1
                raise HTTPException(403, f"Вы в муте ещё ~{left} мин. Причина: {user.mute_reason or '—'}")
            raise HTTPException(403, f"Вы в муте. Причина: {user.mute_reason or '—'}")

        # 3) Rate-limit (1 сообщение в config.CHAT_RATE_LIMIT_SECONDS секунд).
        if user.last_chat_message_at:
            elapsed = (now - user.last_chat_message_at).total_seconds()
            if elapsed < config.CHAT_RATE_LIMIT_SECONDS:
                wait = round(config.CHAT_RATE_LIMIT_SECONDS - elapsed, 1)
                raise HTTPException(429, f"Не так быстро — подожди ещё {wait} сек.")

        # 4) Авто-фильтр (ссылки/казино/VPN/18+).
        reason = _auto_filter_reason(text)
        if reason:
            # Сообщение сохраняем скрытым (для истории/модерации) и выдаём
            # АВТО-МУТ на config.CHAT_AUTO_MUTE_HOURS часов.
            hidden_msg = ChatMessage(
                user_id=user.id, text=text, is_hidden=True, hide_reason="auto_filter",
            )
            session.add(hidden_msg)
            user.is_muted = True
            user.mute_until = now + datetime.timedelta(hours=config.CHAT_AUTO_MUTE_HOURS)
            human = "реклама/сторонняя ссылка" if reason == "link" else f"запрещённое слово ({reason.split(':', 1)[-1]})"
            user.mute_reason = f"Авто-мут: {human}"
            await session.commit()

            await main.notify_admin_telegram(
                f"🚫 <b>Авто-мут по фильтру чата</b>\n"
                f"👤 Игрок: <code>{user.telegram_id}</code> (@{user.username or '—'})\n"
                f"⏱ Мут на {config.CHAT_AUTO_MUTE_HOURS}ч\n"
                f"📝 Причина: {human}\n"
                f"💬 Текст: <i>{text[:200]}</i>"
            )
            raise HTTPException(
                403,
                f"Сообщение заблокировано авто-фильтром ({human}). "
                f"Вы получили мут на {config.CHAT_AUTO_MUTE_HOURS} часа.",
            )

        # 5) Чистое сообщение — публикуем.
        msg = ChatMessage(user_id=user.id, text=text, is_system=False, is_hidden=False)
        session.add(msg)
        user.last_chat_message_at = now
        await session.commit()
        await session.refresh(msg)

        return {
            "success": True,
            "message": {
                "id": msg.id,
                "text": msg.text,
                "is_system": False,
                "user_id": user.id,
                "author_telegram_id": user.telegram_id,
                "author_name": user.first_name or user.username or "Игрок",
                "author_photo": user.photo_url,
                "created_at": msg.created_at.isoformat() if msg.created_at else now.isoformat(),
            },
        }


# ============================================
# POST /api/chat/report
# ============================================
class ReportRequest(BaseModel):
    telegram_id: int
    message_id: int
    reason: str | None = None


@router.post("/api/chat/report")
async def report_message(req: ReportRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        reporter = result.scalar_one_or_none()
        if not reporter:
            raise HTTPException(404, "Пользователь не найден")

        msg_res = await session.execute(select(ChatMessage).where(ChatMessage.id == req.message_id))
        msg = msg_res.scalar_one_or_none()
        if not msg:
            raise HTTPException(404, "Сообщение не найдено")

        if msg.is_system:
            raise HTTPException(400, "Нельзя пожаловаться на системное сообщение")
        if msg.user_id == reporter.id:
            raise HTTPException(400, "Нельзя пожаловаться на своё сообщение")
        if msg.is_hidden:
            return {"success": True, "already_hidden": True}

        now = datetime.datetime.utcnow()
        message_key = str(msg.id)

        # Не даём одному игроку накручивать счётчик несколькими жалобами на
        # одно сообщение — учитываем максимум одну жалобу на пару (repоrter, msg).
        existing = await session.execute(
            select(ChatReport).where(
                ChatReport.reporter_id == reporter.id,
                ChatReport.message_id == message_key,
            )
        )
        already = existing.scalar_one_or_none()
        if not already:
            session.add(ChatReport(
                reporter_id=reporter.id,
                reported_user_id=msg.user_id,
                message_id=message_key,
                reason=req.reason,
            ))
            await session.commit()

        # Считаем УНИКАЛЬНЫХ жалобщиков на это сообщение за окно WINDOW минут.
        window_start = now - datetime.timedelta(minutes=config.CHAT_REPORT_WINDOW_MINUTES)
        distinct_reporters = await session.scalar(
            select(func.count(distinct(ChatReport.reporter_id))).where(
                ChatReport.message_id == message_key,
                ChatReport.created_at >= window_start,
            )
        ) or 0

        hidden_now = False
        if distinct_reporters >= config.CHAT_REPORT_THRESHOLD and not msg.is_hidden:
            msg.is_hidden = True
            msg.hide_reason = "reports"
            await session.commit()
            hidden_now = True

            author_res = await session.execute(select(User).where(User.id == msg.user_id))
            author = author_res.scalar_one_or_none()
            author_label = (
                f"<code>{author.telegram_id}</code> (@{author.username or '—'})" if author else str(msg.user_id)
            )
            await main.notify_admin_telegram(
                f"⚠️ <b>Сообщение скрыто по жалобам</b>\n"
                f"👤 Автор: {author_label}\n"
                f"🚩 Жалоб за {config.CHAT_REPORT_WINDOW_MINUTES} мин: <b>{distinct_reporters}</b>\n"
                f"💬 Текст: <i>{(msg.text or '')[:200]}</i>"
            )

        return {
            "success": True,
            "reports": distinct_reporters,
            "threshold": config.CHAT_REPORT_THRESHOLD,
            "hidden": hidden_now or bool(msg.is_hidden),
        }
