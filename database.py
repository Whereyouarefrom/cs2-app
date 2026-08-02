# ============================================
# CS2 Case Simulator — Database Models
# ============================================

import os
import secrets
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, DateTime, BigInteger,
    inspect, text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

Base = declarative_base()


# ---------------------------------------------------
# Пользователи
# ---------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)         # аватар из Telegram WebApp

    balance = Column(Float, default=500.0)           # виртуальный баланс (Кристаллики 💎)
    is_vip = Column(Boolean, default=False)          # снятие рекламы / премиум
    vip_expires_at = Column(DateTime, nullable=True) # None = навсегда, если is_vip=True и это не задано

    lang = Column(String, default="ru")               # ru / en / uk
    sound_enabled = Column(Boolean, default=True)      # звук вкл/выкл

    ref_code = Column(String, unique=True, nullable=False, default=lambda: secrets.token_hex(4))   # собственный реф. код
    referred_by = Column(BigInteger, nullable=True)          # telegram_id пригласившего

    total_cases_opened = Column(Integer, default=0)
    favorite_case = Column(String, nullable=True)

    # ---- Ежедневные награды за вход (Daily Streak, 1-7 день) ----
    daily_streak = Column(Integer, default=0)               # текущая серия дней подряд
    last_daily_claim_at = Column(DateTime, nullable=True)    # когда забрали последнюю ежедневную награду

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    inventory = relationship("Inventory", back_populates="owner", cascade="all, delete-orphan")


# ---------------------------------------------------
# Инвентарь (выбитые скины)
# ---------------------------------------------------
class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    skin_name = Column(String, nullable=False)
    skin_price = Column(Float, nullable=False)     # виртуальная цена на момент выпадения
    rarity = Column(String, nullable=False)        # Consumer / Industrial / ... / Covert / Knife
    quality = Column(String, nullable=True)         # FN / MW / FT / WW / BS
    stattrak = Column(Boolean, default=False)
    float_val = Column(Float, nullable=True)        # Float value (0.00 - 1.00)
    image_url = Column(String, nullable=True)       # прямая ссылка на Steam CDN

    obtained_from_case = Column(String, nullable=True)
    obtained_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="inventory")


# ---------------------------------------------------
# Промокоды
# ---------------------------------------------------
class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)

    reward_type = Column(String, nullable=False)   # "balance" | "case" | "skin"
    reward_value = Column(String, nullable=False)  # сумма баланса, ID кейса или имя скина

    max_activations = Column(Integer, default=1)
    used_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


# ---------------------------------------------------
# Розыгрыши
# ---------------------------------------------------
class Giveaway(Base):
    __tablename__ = "giveaways"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    prize_skin = Column(String, nullable=False)

    required_refs = Column(Integer, default=0)   # сколько друзей нужно пригласить для участия
    end_time = Column(DateTime, nullable=False)

    is_finished = Column(Boolean, default=False)
    winner_telegram_id = Column(BigInteger, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ---------------------------------------------------
# Движок и сессия (PostgreSQL / SQLite)
# ---------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = "sqlite+aiosqlite:///./database.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Создаёт отсутствующие таблицы и, ВАЖНО, добавляет отсутствующие
    КОЛОНКИ в уже существующие таблицы.

    Base.metadata.create_all() сам по себе умеет создавать только целиком
    новые таблицы — если таблица `users` уже есть в базе (а на проде она
    почти всегда есть), но в неё добавили новое поле в модели (как
    photo_url / daily_streak / last_daily_claim_at), create_all() эту
    колонку НЕ добавит и приложение будет падать на каждом SELECT/INSERT
    с ошибкой вида "column users.xxx does not exist".

    Поэтому сначала прогоняем лёгкую авто-миграцию (_auto_migrate_columns),
    а уже потом create_all() — он подчистит то, что миграция не тронула
    (т.е. целиком новые таблицы).

    Это НЕ замена нормальному инструменту миграций (Alembic) — сюда не
    входят переименование/смена типа колонки, DROP и сложные constraints.
    Но для "добавили колонку в модели — она должна появиться в проде без
    ручных ALTER TABLE" этого достаточно и он безопасен для повторного
    запуска (идемпотентен: уже существующие колонки просто пропускаются).
    """
    async with engine.begin() as conn:
        await _auto_migrate_columns(conn)
        await conn.run_sync(Base.metadata.create_all)


def _inspect_existing(sync_conn) -> dict[str, set[str]]:
    """Синхронная функция (вызывается через conn.run_sync) — возвращает
    {имя_таблицы: {имена существующих колонок}} для таблиц, которые уже
    реально есть в базе."""
    inspector = inspect(sync_conn)
    existing = {}
    for table_name in inspector.get_table_names():
        existing[table_name] = {col["name"] for col in inspector.get_columns(table_name)}
    return existing


async def _auto_migrate_columns(conn):
    """Сравнивает модели SQLAlchemy (Base.metadata) с реальной структурой
    БД и добавляет через ALTER TABLE ... ADD COLUMN всё, чего не хватает
    в уже существующих таблицах. Новые таблицы целиком не трогает — их
    создаст последующий create_all()."""
    existing = await conn.run_sync(_inspect_existing)

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # таблицы вообще ещё нет — её создаст create_all() ниже

        existing_cols = existing[table.name]
        for column in table.columns:
            if column.name in existing_cols:
                continue

            col_type = column.type.compile(dialect=engine.dialect)
            await conn.execute(text(
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            ))
            print(f"[db-migrate] {table.name}.{column.name} ({col_type}) — колонка добавлена")

            await _backfill_new_column(conn, table, column)


async def _backfill_new_column(conn, table, column):
    """Заполняет только что добавленную колонку значением по умолчанию из
    модели. Без этого у ВСЕХ существующих строк колонка останется NULL —
    и, например, `user.daily_streak += 1` упадёт с TypeError на None + int.
    Поддерживает и обычные константы (default=0), и вызываемые дефолты
    (default=lambda: secrets.token_hex(4)) — второе нужно, например, для
    уникального ref_code, где каждой строке требуется своё значение."""
    if column.default is None:
        return

    if column.default.is_scalar:
        value = column.default.arg
        await conn.execute(
            text(f'UPDATE "{table.name}" SET "{column.name}" = :val WHERE "{column.name}" IS NULL'),
            {"val": value},
        )
        return

    if callable(getattr(column.default, "arg", None)):
        pk_col = list(table.primary_key.columns)[0]
        rows = (await conn.execute(
            text(f'SELECT "{pk_col.name}" FROM "{table.name}" WHERE "{column.name}" IS NULL')
        )).fetchall()
        default_fn = column.default.arg
        for row in rows:
            try:
                value = default_fn()
            except TypeError:
                value = default_fn(None)   # некоторые дефолты ожидают execution context
            await conn.execute(
                text(f'UPDATE "{table.name}" SET "{column.name}" = :val WHERE "{pk_col.name}" = :pk'),
                {"val": value, "pk": row[0]},
            )


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
