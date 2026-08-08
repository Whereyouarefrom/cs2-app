# ============================================
# СПРИНТ 10: Профиль — уровень, титулы, рамки, Витрина
# ============================================
#
# Эндпоинты:
#   GET  /api/profile/cosmetics       — каталог титулов и рамок с флагом unlocked
#   POST /api/profile/select-title    — выбрать активный титул (или снять)
#   POST /api/profile/select-frame    — выбрать рамку аватара (или снять)
#   GET  /api/profile/showcase        — Витрина + сколько слотов открыл уровень
#   POST /api/profile/showcase/add    — закрепить скин в Витрине
#   POST /api/profile/showcase/remove — убрать скин из Витрины
#   GET  /api/profile/levels          — таблица порогов уровней (справка для UI)
#
# Модуль СОЗНАТЕЛЬНО не импортирует main на уровне файла (как и остальные
# роутеры проекта) — main подключает его в самом низу, а обращения к
# main.<имя> происходят только внутри обработчиков, то есть уже после
# полной загрузки main. См. подробный комментарий в routers/cases.py.

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

import cosmetics
import levels
from database import Inventory, User, async_session

router = APIRouter()


# ---------------------------------------------------------------
# Схемы запросов
# ---------------------------------------------------------------
class SelectCosmeticRequest(BaseModel):
    telegram_id: int
    # key = None или "" — снять текущий выбор (показывать профиль без
    # титула/рамки). Это валидное действие, а не ошибка.
    key: str | None = None


class ShowcaseRequest(BaseModel):
    telegram_id: int
    inventory_id: int


# ---------------------------------------------------------------
# Общие хелперы
# ---------------------------------------------------------------
async def _get_user(session, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


def _account_level(user: User) -> int:
    """Уровень аккаунта всегда выводится из xp (см. levels.py) — никогда
    не читаем его из колонки, чтобы не разъезжаться с формулой."""
    return levels.level_from_xp(user.xp or 0)


async def _showcase_payload(session, user: User) -> dict:
    """Собирает состояние Витрины: закреплённые предметы (дороже — выше),
    доступное число слотов по уровню и подсказку про следующий слот."""
    import main   # локальный импорт: см. комментарий в шапке модуля

    level_info = levels.get_level_progress(user.xp or 0)

    result = await session.execute(
        select(Inventory).where(
            Inventory.user_id == user.id,
            Inventory.is_in_showcase == True,   # noqa: E712
        ).order_by(Inventory.skin_price.desc())
    )
    items = result.scalars().all()

    return {
        "level": level_info["level"],
        "slots": level_info["showcase_slots"],
        "max_slots": level_info["showcase_max_slots"],
        "base_slots": level_info["showcase_base_slots"],
        "levels_per_slot": level_info["showcase_levels_per_slot"],
        "next_slot_level": level_info["next_showcase_slot_level"],
        "used": len(items),
        "items": [main.serialize_inventory_item(i) for i in items],
    }


# ---------------------------------------------------------------
# Титулы и рамки
# ---------------------------------------------------------------
@router.get("/api/profile/cosmetics")
async def get_cosmetics(telegram_id: int):
    """Каталог титулов и рамок аватара. Отдаём ВСЕ варианты — и открытые, и
    закрытые (с current_value/unlock_value для прогресса), чтобы игрок видел
    цель, а не пустой список.

    pass_frames — рамки Battle Pass: они живут в своём списке
    (User.unlocked_pass_frames) и своих стилях на фронте (pass.js), поэтому
    здесь отдаются просто ключами, а селектор рамок в профиле показывает
    объединение обоих источников."""
    async with async_session() as session:
        user = await _get_user(session, telegram_id)
        level = _account_level(user)

        return {
            "level": level,
            "titles": cosmetics.serialize_titles(user, level=level),
            "frames": cosmetics.serialize_frames(user, level=level),
            "pass_frames": cosmetics.load_keys(user.unlocked_pass_frames),
            "selected_title": user.selected_title,
            "selected_frame": user.selected_frame,
        }


@router.post("/api/profile/select-title")
async def select_title(req: SelectCosmeticRequest):
    """Ставит активный титул. Разрешён только титул, который РЕАЛЬНО открыт
    игроку (проверка по unlocked_titles на сервере — фронт присылает лишь
    ключ, доверять ему нельзя)."""
    key = (req.key or "").strip() or None

    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        if key is not None:
            if key not in cosmetics.TITLES_BY_KEY:
                raise HTTPException(400, "Неизвестный титул")
            if key not in cosmetics.load_keys(user.unlocked_titles):
                raise HTTPException(403, "Этот титул ещё не открыт")

        user.selected_title = key
        await session.commit()

        return {
            "success": True,
            "selected_title": user.selected_title,
            "selected_title_info": cosmetics.title_public(user.selected_title),
        }


@router.post("/api/profile/select-frame")
async def select_frame(req: SelectCosmeticRequest):
    """Ставит рамку аватара. Валидна рамка из ЛЮБОГО из двух источников:
    каталога cosmetics.FRAMES (уровневые + турнирные) или списка рамок
    Battle Pass (User.unlocked_pass_frames) — колонка selected_frame у них
    общая, поэтому и селектор общий."""
    key = (req.key or "").strip() or None

    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        if key is not None:
            allowed = set(cosmetics.load_keys(user.unlocked_frames))
            allowed |= set(cosmetics.load_keys(user.unlocked_pass_frames))
            if key not in allowed:
                raise HTTPException(403, "Эта рамка ещё не открыта")

        user.selected_frame = key
        await session.commit()

        return {
            "success": True,
            "selected_frame": user.selected_frame,
            "selected_frame_info": cosmetics.frame_public(user.selected_frame),
        }


# ---------------------------------------------------------------
# Витрина лучших скинов (Showcase)
# ---------------------------------------------------------------
@router.get("/api/profile/showcase")
async def get_showcase(telegram_id: int):
    async with async_session() as session:
        user = await _get_user(session, telegram_id)
        return await _showcase_payload(session, user)


@router.post("/api/profile/showcase/add")
async def showcase_add(req: ShowcaseRequest):
    """Закрепляет предмет в Витрине.

    Проверки (все на сервере):
      - предмет принадлежит именно этому игроку;
      - предмет не выставлен на P2P-маркет (иначе витрина показывала бы
        скин, который в любой момент уедет к покупателю);
      - свободен слот — вместимость зависит от уровня аккаунта
        (levels.showcase_slots_for_level: 3 базовых + 1 за каждые 5 уровней,
        максимум 9).
    """
    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        result = await session.execute(
            select(Inventory).where(
                Inventory.id == req.inventory_id,
                Inventory.user_id == user.id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в инвентаре")
        if item.is_on_market:
            raise HTTPException(400, "Предмет выставлен на маркет — сними его с продажи")

        if item.is_in_showcase:
            return {"success": True, "already": True, **(await _showcase_payload(session, user))}

        slots = levels.showcase_slots_for_level(_account_level(user))
        used = await session.execute(
            select(Inventory).where(
                Inventory.user_id == user.id,
                Inventory.is_in_showcase == True,   # noqa: E712
            )
        )
        if len(used.scalars().all()) >= slots:
            raise HTTPException(400, f"Витрина заполнена ({slots} слот(ов)) — повышай уровень или убери другой скин")

        item.is_in_showcase = True
        await session.commit()

        return {"success": True, **(await _showcase_payload(session, user))}


@router.post("/api/profile/showcase/remove")
async def showcase_remove(req: ShowcaseRequest):
    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        result = await session.execute(
            select(Inventory).where(
                Inventory.id == req.inventory_id,
                Inventory.user_id == user.id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в инвентаре")

        item.is_in_showcase = False
        await session.commit()

        return {"success": True, **(await _showcase_payload(session, user))}


@router.post("/api/profile/showcase/toggle")
async def showcase_toggle(req: ShowcaseRequest):
    """Переключает предмет в Витрине одним запросом.

    Это основной эндпоинт для UI: кнопка в карточке скина одна и меняет
    подпись по факту состояния, поэтому фронту не нужно решать, дёргать
    /add или /remove — он присылает намерение «переключи», а сервер сам
    выбирает направление. Гранулярные /add и /remove оставлены для
    сценариев, где направление известно точно (например, массовые операции).
    """
    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        result = await session.execute(
            select(Inventory).where(
                Inventory.id == req.inventory_id,
                Inventory.user_id == user.id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "Предмет не найден в инвентаре")

        if item.is_in_showcase:
            item.is_in_showcase = False
        else:
            if item.is_on_market:
                raise HTTPException(400, "Предмет выставлен на маркет — сними его с продажи")

            slots = levels.showcase_slots_for_level(_account_level(user))
            used = await session.execute(
                select(Inventory).where(
                    Inventory.user_id == user.id,
                    Inventory.is_in_showcase == True,   # noqa: E712
                )
            )
            if len(used.scalars().all()) >= slots:
                raise HTTPException(
                    400,
                    f"Витрина заполнена ({slots} слот(ов)) — повышай уровень или убери другой скин",
                )
            item.is_in_showcase = True

        await session.commit()

        return {
            "success": True,
            "is_in_showcase": bool(item.is_in_showcase),
            **(await _showcase_payload(session, user)),
        }


class SelectCosmeticKindRequest(BaseModel):
    telegram_id: int
    kind: str            # "title" | "frame"
    key: str | None = None


@router.post("/api/profile/select-cosmetic")
async def select_cosmetic(req: SelectCosmeticKindRequest):
    """Единая точка выбора косметики профиля — титул ИЛИ рамка, по полю kind.

    Селектор на фронте один и тот же для обоих видов косметики, поэтому и
    эндпоинт один: иначе UI пришлось бы разветвлять на два запроса ради
    идентичной логики. Возвращает ОБА выбранных значения (титул и рамку),
    чтобы фронт мог перерисовать шапку профиля целиком одним ответом, не
    делая повторный запрос профиля.

    Проверки владения полностью повторяют /select-title и /select-frame —
    доверять присланному ключу нельзя ни в одном из путей.
    """
    kind = (req.kind or "").strip().lower()
    if kind not in ("title", "frame"):
        raise HTTPException(400, "kind должен быть 'title' или 'frame'")

    key = (req.key or "").strip() or None

    async with async_session() as session:
        user = await _get_user(session, req.telegram_id)

        if kind == "title":
            if key is not None:
                if key not in cosmetics.TITLES_BY_KEY:
                    raise HTTPException(400, "Неизвестный титул")
                if key not in cosmetics.load_keys(user.unlocked_titles):
                    raise HTTPException(403, "Этот титул ещё не открыт")
            user.selected_title = key
        else:
            if key is not None:
                # Рамка валидна из двух источников: каталог уровней/турниров
                # и рамки Battle Pass — колонка selected_frame у них общая.
                allowed = set(cosmetics.load_keys(user.unlocked_frames))
                allowed |= set(cosmetics.load_keys(user.unlocked_pass_frames))
                if key not in allowed:
                    raise HTTPException(403, "Эта рамка ещё не открыта")
            user.selected_frame = key

        await session.commit()

        return {
            "success": True,
            "selected_title": user.selected_title,
            "selected_frame": user.selected_frame,
            "selected_title_info": cosmetics.title_public(user.selected_title),
            "selected_frame_info": cosmetics.frame_public(user.selected_frame),
        }


# ---------------------------------------------------------------
# Справка по уровням
# ---------------------------------------------------------------
@router.get("/api/profile/levels")
async def get_levels(telegram_id: int | None = None, up_to: int = 40):
    """Таблица порогов уровней для справочного экрана: сколько XP стоит
    каждый переход и на каком уровне открывается очередной слот Витрины.
    Если передан telegram_id — добавляем прогресс конкретного игрока."""
    up_to = max(5, min(up_to, levels.MAX_LEVEL))

    table = [
        {
            "level": n,
            "xp_required": levels.xp_required_for_level(n),
            "total_xp": levels.total_xp_for_level(n),
            "showcase_slots": levels.showcase_slots_for_level(n),
            "slot_gained": levels.showcase_slots_for_level(n) > levels.showcase_slots_for_level(n - 1) if n > 1 else False,
        }
        for n in range(1, up_to + 1)
    ]

    payload = {
        "base_xp": levels.BASE_XP,
        "growth": levels.GROWTH,
        "formula": "XP_required(N) = 100 * 1.15^(N-1)",
        "max_level": levels.MAX_LEVEL,
        "showcase_base_slots": levels.SHOWCASE_BASE_SLOTS,
        "showcase_levels_per_slot": levels.SHOWCASE_LEVELS_PER_SLOT,
        "showcase_max_slots": levels.SHOWCASE_MAX_SLOTS,
        "table": table,
    }

    if telegram_id is not None:
        async with async_session() as session:
            user = await _get_user(session, telegram_id)
            payload["progress"] = levels.get_level_progress(user.xp or 0)

    return payload
