# ============================================
# СПРИНТ 11 + ПРАВКИ В ТЗ №3: Глобальный чат, авто-модерация и жалобы
# ============================================
#
# GET  /api/chat/messages?telegram_id=...&after_id=...
#     — последние видимые (не скрытые) сообщения глобального чата + статус
#       мута/бана текущего игрока (чтобы фронт заранее заблокировал ввод) +
#       removed_ids (ТЗ №3) — id недавно скрытых сообщений (удалены автором
#       или скрыты по жалобам), чтобы уже открытые у других игроков чаты
#       убрали их из своего UI на ближайшем опросе.
# POST /api/chat/send   { telegram_id, text }
#     — отправка сообщения с проверками: бан чата → мут → rate-limit
#       (config.CHAT_RATE_LIMIT_SECONDS) → PII-фильтр (телефон/карта/личные
#       данные, ТЗ №3) → авто-фильтр (ссылки/казино/VPN/18+/контекст
#       веществ, ТЗ №3). Нарушение любого из фильтров => сообщение
#       сохраняется скрытым (is_hidden=True, hide_reason соответствует
#       причине), игроку выдаётся АВТО-МУТ, админ уведомляется.
# POST /api/chat/report { telegram_id, message_id }
#     — жалоба на сообщение. При 3+ (config.CHAT_REPORT_THRESHOLD) жалобах
#       от РАЗНЫХ игроков за config.CHAT_REPORT_WINDOW_MINUTES минут
#       сообщение авто-скрывается (is_hidden=True) и уходит админу в Telegram.
# POST /api/chat/delete { telegram_id, message_id }   [ТЗ №3]
#     — удаление СВОЕГО сообщения. Сообщение скрывается (is_hidden=True,
#       hide_reason="deleted_by_author") — физически из БД не удаляем,
#       чтобы сохранить историю для модерации, но из чата у всех оно
#       пропадает (не отдаётся GET-ом + уходит в removed_ids).
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
from database import async_session, User, ChatMessage, ChatReport, get_setting

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


def _substance_reason(text: str) -> str | None:
    """Контекстный фильтр запрещённых веществ (ТЗ №3): срабатывает ТОЛЬКО
    если в сообщении одновременно есть коммерческий глагол/фраза
    (config.CHAT_SUBSTANCE_COMMERCIAL_VERBS) И упоминание вещества
    (config.CHAT_SUBSTANCE_KEYWORDS) — т.е. похоже на попытку продажи/
    заказа, а не простое упоминание слова в разговоре. Возвращает
    'substance:<слово>' или None."""
    low = (text or "").lower()
    has_commercial = any(v in low for v in config.CHAT_SUBSTANCE_COMMERCIAL_VERBS)
    if not has_commercial:
        return None
    for kw in config.CHAT_SUBSTANCE_KEYWORDS:
        if kw in low:
            return f"substance:{kw}"
    return None


def _auto_filter_reason(text: str) -> str | None:
    """Возвращает причину блокировки сообщения авто-фильтром или None, если
    сообщение чистое. Причины: 'link' (реклама/сторонняя ссылка вне белого
    списка), 'keyword:<слово>' (казино/рулетка/кейс-батл/VPN/18+/промо) либо
    'substance:<слово>' (коммерческий контекст продажи веществ, ТЗ №3)."""
    low = (text or "").lower()

    # 1) Запрещённые ключевые слова (казино/рулетки/кейс-батл сайты/VPN/18+/промо)
    for kw in config.CHAT_BANNED_KEYWORDS:
        if kw.lower() in low:
            return f"keyword:{kw}"

    # 2) Контекстный фильтр веществ — только коммерческий контекст (ТЗ №3)
    substance = _substance_reason(text)
    if substance:
        return substance

    # 3) Любая сторонняя ссылка вне белого списка официальных доменов
    for link in _extract_links(text):
        if not _is_official_link(link):
            return "link"

    return None


# ---- Правки в ТЗ №3: защита личных данных (PII Protection & Auto-Mute) ----
# Отдельный, более строгий контур: срабатывание НЕ просто скрывает
# сообщение как auto_filter, а автоматически мутит игрока с явным
# уведомлением о причине (см. send_message). Проверяется РАНЬШЕ общего
# авто-фильтра.
_PHONE_RE = re.compile(
    r"(?:\+?\d[\s\-\(\)]?){9,14}\d"   # 10-15 цифр подряд, можно через +/-/()/пробел
)
_CARD_RE = re.compile(
    r"\b(?:\d[ \-]?){13,19}\b"        # банковская карта: 13-19 цифр, часто группами по 4
)
# Эвристика адреса: слово-маркер (улица/дом/квартира/проспект и т.п.) рядом
# с числом — намеренно мягкая, чтобы не блокировать обычные сообщения
# ("дом 2" в контексте игры маловероятен, но проверка best-effort).
_ADDRESS_RE = re.compile(
    r"(?:улиц|ул\.|дом\s*\d|д\.\s*\d|кварти|кв\.\s*\d|проспект|просп\.|переулок|мкр\.)",
    re.IGNORECASE,
)


def _looks_like_phone_or_card(text: str) -> bool:
    """Считает цифры в самых длинных цифровых last совпадениях, чтобы не
    ловить ложняк на коротких числах (ставки, множители x2, id кейсов)."""
    for m in _PHONE_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 15:
            return True
    for m in _CARD_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19:
            return True
    return False


def _pii_reason(text: str) -> str | None:
    """Возвращает 'phone_or_card', 'address' либо None. Личные данные —
    самый строгий контур: сообщение вообще не публикуется (см. send_message),
    а не просто скрывается для истории."""
    if _looks_like_phone_or_card(text):
        return "phone_or_card"
    if _ADDRESS_RE.search(text or ""):
        return "address"
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
            # ПРАВКИ В ТЗ №15: /admin_msg — отдельный флаг для особого
            # стиля/плашки "Администрация" на фронте (см. app.js).
            "is_admin_announcement": bool(m.is_admin_announcement),
            "user_id": m.user_id,
            "author_telegram_id": author.telegram_id if author else None,
            "author_name": (author.first_name or author.username or "Игрок") if author else "Игрок",
            "author_photo": author.photo_url if author else None,
            # ПРАВКИ В ТЗ №15: /set_prefix — кастомный визуальный префикс
            # автора сообщения (напр. "[VIP]"), None если не выдан.
            "author_prefix": (author.chat_prefix if author else None),
            "created_at": (m.created_at or datetime.datetime.utcnow()).isoformat(),
        })
    return out


async def _is_chat_locked(session) -> bool:
    """ПРАВКИ В ТЗ №15: /mute_chat — глобальный read-only режим для всех
    ОБЫЧНЫХ пользователей (админы, проверяемые отдельно по config.ADMIN_IDS,
    продолжают писать даже при локе — например, чтобы отправить /admin_msg
    с объяснением, почему чат временно закрыт)."""
    return (await get_setting(session, "chat_locked", "0")) == "1"


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

        # ---- ТЗ №3: removed_ids — id сообщений, скрытых недавно (удалены
        # автором либо скрыты по жалобам за последние N секунд). Нужно, чтобы
        # клиенты, у которых чат УЖЕ открыт и сообщение уже отрисовано,
        # убрали его из DOM на ближайшем опросе, а не только при полной
        # перезагрузке ленты. is_system никогда не скрываются — исключать
        # не нужно, но фильтр по hide_reason на всякий случай не ставим:
        # свежедобавленный auto_filter/pii тоже безопасно прислать (клиент
        # просто попробует удалить несуществующий узел — no-op).
        removed_window_start = now - datetime.timedelta(seconds=config.CHAT_REMOVED_IDS_WINDOW_SECONDS)
        removed_res = await session.execute(
            select(ChatMessage.id).where(
                ChatMessage.is_hidden == True,  # noqa: E712
                ChatMessage.hidden_at != None,  # noqa: E711
                ChatMessage.hidden_at >= removed_window_start,
            )
        )
        removed_ids = [row[0] for row in removed_res.all()]

        return {
            "messages": await _serialize_messages(session, rows),
            "removed_ids": removed_ids,
            "me": {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "is_chat_banned": bool(user.is_chat_banned),
                "is_muted": muted,
                "mute_until": mute_until.isoformat() if mute_until else None,
                "mute_reason": user.mute_reason if muted else None,
                "is_admin": user.telegram_id in config.ADMIN_IDS,
            },
            # ПРАВКИ В ТЗ №15: /mute_chat — фронт скрывает поле ввода и
            # показывает баннер "чат только для чтения", когда True.
            "chat_locked": await _is_chat_locked(session),
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
        is_admin_user = user.telegram_id in config.ADMIN_IDS

        # 0) ПРАВКИ В ТЗ №15: /mute_chat — глобальный read-only режим.
        #    Админы (config.ADMIN_IDS) пишут даже при локе — например,
        #    чтобы объявить о причине временного закрытия чата.
        if not is_admin_user and await _is_chat_locked(session):
            raise HTTPException(403, "Чат временно закрыт администрацией (только чтение)")

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

        # 4) Защита личных данных (PII Protection & Auto-Mute, ТЗ №3) —
        #    проверяем РАНЬШЕ общего авто-фильтра: попытка слить телефон/
        #    карту/адрес наказывается строже и с отдельным сообщением.
        pii_reason = _pii_reason(text)
        if pii_reason:
            hidden_msg = ChatMessage(
                user_id=user.id, text=text, is_hidden=True, hide_reason="pii",
                hidden_at=now,
            )
            session.add(hidden_msg)
            user.is_muted = True
            user.mute_until = now + datetime.timedelta(hours=config.CHAT_PII_AUTO_MUTE_HOURS)
            human = "номер телефона / банковская карта" if pii_reason == "phone_or_card" else "личный адрес"
            user.mute_reason = f"Авто-мут: попытка отправить личные данные ({human})"
            await session.commit()

            await main.notify_admin_telegram(
                f"🔒 <b>PII-фильтр: сообщение заблокировано</b>\n"
                f"👤 Игрок: <code>{user.telegram_id}</code> (@{user.username or '—'})\n"
                f"⏱ Мут на {config.CHAT_PII_AUTO_MUTE_HOURS}ч\n"
                f"📝 Похоже на: {human}\n"
                f"💬 Текст: <i>{text[:200]}</i>"
            )
            raise HTTPException(
                403,
                f"Сообщение не отправлено: похоже, вы пытаетесь поделиться личными "
                f"данными ({human}). Это запрещено правилами чата. Вы получили мут "
                f"на {config.CHAT_PII_AUTO_MUTE_HOURS} часа.",
            )

        # 5) Авто-фильтр (ссылки/казино/кейс-батл/VPN/18+/контекст веществ).
        reason = _auto_filter_reason(text)
        if reason:
            # Сообщение сохраняем скрытым (для истории/модерации) и выдаём
            # АВТО-МУТ на config.CHAT_AUTO_MUTE_HOURS часов.
            hidden_msg = ChatMessage(
                user_id=user.id, text=text, is_hidden=True, hide_reason="auto_filter",
                hidden_at=now,
            )
            session.add(hidden_msg)
            user.is_muted = True
            user.mute_until = now + datetime.timedelta(hours=config.CHAT_AUTO_MUTE_HOURS)
            if reason == "link":
                human = "реклама/сторонняя ссылка"
            elif reason.startswith("substance:"):
                human = "похоже на продажу/заказ запрещённых веществ"
            else:
                human = f"запрещённое слово ({reason.split(':', 1)[-1]})"
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

        # 6) Чистое сообщение — публикуем.
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
                "is_admin_announcement": False,
                "user_id": user.id,
                "author_telegram_id": user.telegram_id,
                "author_name": user.first_name or user.username or "Игрок",
                "author_photo": user.photo_url,
                "author_prefix": user.chat_prefix,
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
            msg.hidden_at = now  # чтобы уже открытые чаты убрали сообщение при опросе (removed_ids)
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


# ============================================
# POST /api/chat/delete   [ТЗ №3: удаление своих сообщений]
# ============================================
class DeleteRequest(BaseModel):
    telegram_id: int
    message_id: int


@router.post("/api/chat/delete")
async def delete_message(req: DeleteRequest):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == req.telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        msg_res = await session.execute(select(ChatMessage).where(ChatMessage.id == req.message_id))
        msg = msg_res.scalar_one_or_none()
        if not msg:
            raise HTTPException(404, "Сообщение не найдено")

        if msg.is_system:
            raise HTTPException(400, "Нельзя удалить системное сообщение")
        if msg.user_id != user.id:
            raise HTTPException(403, "Можно удалять только свои сообщения")

        if not msg.is_hidden:
            now = datetime.datetime.utcnow()
            msg.is_hidden = True
            msg.hide_reason = "deleted_by_author"
            msg.hidden_at = now
            await session.commit()

        return {"success": True, "message_id": msg.id}
