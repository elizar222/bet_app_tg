"""Проверка initData от Telegram.

Мини-апп при каждом запросе шлёт строку Telegram.WebApp.initData в заголовке
X-Init-Data. Подпись проверяется токеном любого из наших ботов — так сервер
знает, что пользователь настоящий, а не подставил чужой ID.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_AGE_SECONDS = 24 * 3600


@dataclass(frozen=True)
class TgUser:
    id: int
    first_name: str = ""
    username: str | None = None
    language_code: str | None = None


def _check(init_data: str, token: str) -> dict[str, str] | None:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    return pairs


def validate_init_data(init_data: str, tokens: list[str]) -> TgUser | None:
    """Возвращает пользователя, если подпись верна хотя бы для одного бота."""

    if not init_data:
        return None
    for token in tokens:
        pairs = _check(init_data, token)
        if pairs is None:
            continue
        try:
            if time.time() - int(pairs.get("auth_date", "0")) > MAX_AGE_SECONDS:
                return None
            raw = json.loads(pairs.get("user", "{}"))
            return TgUser(
                id=int(raw["id"]),
                first_name=raw.get("first_name") or "",
                username=raw.get("username"),
                language_code=raw.get("language_code"),
            )
        except (KeyError, ValueError, TypeError):
            return None
    return None
