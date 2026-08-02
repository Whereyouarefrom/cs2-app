# ============================================
# CS2 Case Simulator — Database Models
# ============================================

import os
import secrets
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, DateTime, BigInteger
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
    """Создаёт все таблицы при первом запуске."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
