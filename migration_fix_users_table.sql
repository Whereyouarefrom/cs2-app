-- ============================================================
-- CS2 Case Simulator — экстренная миграция таблицы users
-- ============================================================
-- Причина: таблица users была создана в PostgreSQL ДО того, как в
-- модели database.py появились колонки photo_url / daily_streak /
-- last_daily_claim_at. SQLAlchemy create_all() создаёт только
-- отсутствующие ТАБЛИЦЫ, а не отсутствующие КОЛОНКИ в уже
-- существующих — поэтому SELECT падал с "column does not exist".
--
-- Скрипт ИДЕМПОТЕНТЕН — его можно запускать сколько угодно раз,
-- уже существующие колонки просто пропускаются (IF NOT EXISTS).
-- ============================================================

BEGIN;

-- Базовые поля профиля
ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url VARCHAR;

-- Баланс / VIP
ALTER TABLE users ADD COLUMN IF NOT EXISTS balance DOUBLE PRECISION DEFAULT 500;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expires_at TIMESTAMP;

-- Настройки
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang VARCHAR DEFAULT 'ru';
ALTER TABLE users ADD COLUMN IF NOT EXISTS sound_enabled BOOLEAN DEFAULT TRUE;

-- Реферальная система
ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_code VARCHAR;
-- ref_code уникальный и NOT NULL в модели — если колонку только что
-- добавили, заполняем её случайным кодом на каждую существующую строку,
-- прежде чем накатывать ограничения (иначе UNIQUE/NOT NULL упадёт на NULL).
UPDATE users
   SET ref_code = substr(md5(random()::text || id::text), 1, 8)
 WHERE ref_code IS NULL;

ALTER TABLE users ALTER COLUMN ref_code SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_ref_code_key'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_ref_code_key UNIQUE (ref_code);
    END IF;
END $$;

-- Статистика
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_cases_opened INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_case VARCHAR;

-- Пользовательское соглашение
ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN DEFAULT FALSE;

-- Топ дроп (самый дорогой предмет за всё время, не привязан к инвентарю)
ALTER TABLE users ADD COLUMN IF NOT EXISTS top_drop_name VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS top_drop_price DOUBLE PRECISION;
ALTER TABLE users ADD COLUMN IF NOT EXISTS top_drop_rarity VARCHAR;
ALTER TABLE users ADD COLUMN IF NOT EXISTS top_drop_image VARCHAR;

-- Ежедневные награды (Daily Streak, ШАГ 3) — новые колонки
ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_streak INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily_claim_at TIMESTAMP;

-- created_at
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- Подчищаем NULL там, где DEFAULT не применился к уже существующим строкам
-- (для старых Postgres < 11, где ADD COLUMN ... DEFAULT не бэкфиллит)
UPDATE users SET balance = 500 WHERE balance IS NULL;
UPDATE users SET is_vip = FALSE WHERE is_vip IS NULL;
UPDATE users SET lang = 'ru' WHERE lang IS NULL;
UPDATE users SET sound_enabled = TRUE WHERE sound_enabled IS NULL;
UPDATE users SET total_cases_opened = 0 WHERE total_cases_opened IS NULL;
UPDATE users SET daily_streak = 0 WHERE daily_streak IS NULL;

COMMIT;

-- Проверка результата — должно вывести полный список колонок таблицы users
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'users'
 ORDER BY ordinal_position;
