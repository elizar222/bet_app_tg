"""Чтение конфигурации из .env. Ничего кроме окружения тут не хранится —
всё, что меняется на ходу (промокоды, ссылки, тексты), лежит в БД."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    bot_tokens: list[str] = field(default_factory=list)
    admin_bot_token: str = ""
    admin_ids: set[int] = field(default_factory=set)
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    log_level: str = "INFO"
    timezone: str = "Europe/Moscow"

    # мини-апп
    web_enabled: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    webapp_url: str = ""  # публичный https-адрес (туннель cloudflared/ngrok или домен)
    web_dev_user_id: int = 0  # >0 — можно открыть мини-апп в обычном браузере без Telegram


def load_config() -> Config:
    tokens = _split(os.getenv("BOT_TOKENS"))
    admin_ids = {int(x) for x in _split(os.getenv("ADMIN_IDS")) if x.lstrip("-").isdigit()}

    cfg = Config(
        bot_tokens=tokens,
        admin_bot_token=(os.getenv("ADMIN_BOT_TOKEN") or "").strip(),
        admin_ids=admin_ids,
        database_url=(os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./data/bot.db").strip(),
        log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
        timezone=(os.getenv("TIMEZONE") or "Europe/Moscow").strip(),
        web_enabled=(os.getenv("WEB_ENABLED") or "1").strip() not in {"0", "false", "no"},
        web_host=(os.getenv("WEB_HOST") or "127.0.0.1").strip(),
        web_port=int((os.getenv("WEB_PORT") or "8080").strip()),
        webapp_url=(os.getenv("WEBAPP_URL") or "").strip().rstrip("/"),
        web_dev_user_id=int((os.getenv("WEB_DEV_USER_ID") or "0").strip() or 0),
    )

    if not cfg.bot_tokens:
        raise RuntimeError("В .env не задан BOT_TOKENS — нужен хотя бы один токен рабочего бота.")
    if not cfg.admin_bot_token:
        raise RuntimeError("В .env не задан ADMIN_BOT_TOKEN.")
    if not cfg.admin_ids:
        raise RuntimeError("В .env не задан ADMIN_IDS — иначе в админку никто не войдёт.")

    # SQLite: убедимся, что папка под файл БД существует
    if cfg.database_url.startswith("sqlite"):
        db_path = cfg.database_url.split("///", 1)[-1]
        path = Path(db_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)

    return cfg
