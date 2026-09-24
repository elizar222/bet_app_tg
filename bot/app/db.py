"""Подключение к БД. sqlite сейчас, postgres позже — меняется только DATABASE_URL."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str) -> None:
    global _engine, _sessionmaker

    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["timeout"] = 30
        # папка под файл БД может ещё не существовать (первый запуск)
        from pathlib import Path

        db_file = database_url.split("///", 1)[-1]
        if db_file and db_file != ":memory:":
            Path(db_file).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(database_url, echo=False, connect_args=connect_args, pool_pre_ping=True)

    if database_url.startswith("sqlite"):
        # WAL заметно спокойнее переносит параллельную запись из 10 ботов
        from sqlalchemy import text

        async with _engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_db() ещё не вызывался")
    return _sessionmaker


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()
