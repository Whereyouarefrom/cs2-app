# ============================================
# CS2 Case Simulator — Telegram WebApp Auth
# ============================================
#
# Проверка подлинности initData, которую присылает Telegram Mini App.
# Алгоритм точно по официальной документации Telegram:
# https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
#
# ВАЖНО: telegram_id ВСЕГДА нужно брать из данных, прошедших эту проверку,
# а не из query-параметров/тела запроса, присланных клиентом напрямую —
# иначе любой человек сможет открыть чужой профиль или создать юзера
# с произвольным telegram_id, просто зная/подобрав число.

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """Подпись initData невалидна, просрочена или данные повреждены."""


def parse_and_verify_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict:
    """Разбирает и проверяет строку initData от Telegram.WebApp.

    Возвращает словарь с полями (в т.ч. распарсенный "user"), если подпись
    валидна. Бросает InitDataError, если данные подделаны/просрочены.
    """
    if not init_data or not isinstance(init_data, str):
        raise InitDataError("initData пустой или отсутствует")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise InitDataError("initData нельзя разобрать")

    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("В initData отсутствует поле hash")

    # Строка для проверки: все пары "key=value" (кроме hash), отсортированные
    # по ключу и склеенные через \n.
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    # secret_key = HMAC_SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise InitDataError("Невалидная подпись initData — данные могли быть подделаны")

    auth_date = int(data.get("auth_date", 0) or 0)
    if max_age_seconds and auth_date and (time.time() - auth_date) > max_age_seconds:
        raise InitDataError("initData просрочен, перезапусти Mini App")

    if "user" in data:
        try:
            data["user"] = json.loads(data["user"])
        except (json.JSONDecodeError, TypeError):
            raise InitDataError("Поле user в initData повреждено")

    return data
