"""Распределение пользователей между ботами.

Каждый из 10 ботов — админ в канале, поэтому апдейт chat_join_request прилетает
всем десяти одновременно. Отвечать должен ровно один: тот, за кем закреплён
пользователь. Закрепление постоянное — один юзер всегда общается с одним ботом.

Выбираем бота с наименьшим числом закреплённых юзеров (самобалансировка при
добавлении новых ботов), тай-брейк по sort_order.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotAccount, User

# Все боты живут в одном процессе, поэтому обычного asyncio-лока достаточно,
# чтобы два апдейта не создали двух разных закреплений для одного юзера.
_assign_lock = asyncio.Lock()


async def _pick_bot(session: AsyncSession) -> BotAccount | None:
    counts = (
        select(User.bot_id, func.count(User.id).label("cnt"))
        .group_by(User.bot_id)
        .subquery()
    )
    stmt = (
        select(BotAccount, func.coalesce(counts.c.cnt, 0).label("load"))
        .outerjoin(counts, counts.c.bot_id == BotAccount.id)
        .where(BotAccount.enabled.is_(True))
        .order_by("load", BotAccount.sort_order, BotAccount.id)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return row[0] if row else None


async def get_or_create_user(
    session: AsyncSession,
    *,
    tg_id: int,
    dm_chat_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
    source_channel_id: int | None = None,
) -> tuple[User, bool]:
    """Возвращает (пользователь, создан_ли_только_что)."""

    async with _assign_lock:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if user is not None:
            changed = False
            if dm_chat_id and user.dm_chat_id != dm_chat_id:
                user.dm_chat_id = dm_chat_id
                changed = True
            for field, value in (
                ("username", username),
                ("first_name", first_name),
                ("last_name", last_name),
            ):
                if value and getattr(user, field) != value:
                    setattr(user, field, value)
                    changed = True
            if changed:
                await session.commit()
            return user, False

        bot_account = await _pick_bot(session)
        if bot_account is None:
            raise RuntimeError("Нет ни одного активного бота для закрепления пользователя")

        user = User(
            tg_id=tg_id,
            dm_chat_id=dm_chat_id or tg_id,
            bot_id=bot_account.id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            source_channel_id=source_channel_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, True


async def bot_load(session: AsyncSession) -> list[tuple[BotAccount, int, int]]:
    """Список (бот, всего юзеров, из них заблокировали) — для статистики в админке."""

    total = (
        select(User.bot_id, func.count(User.id).label("cnt"))
        .group_by(User.bot_id)
        .subquery()
    )
    blocked = (
        select(User.bot_id, func.count(User.id).label("cnt"))
        .where(User.is_blocked.is_(True))
        .group_by(User.bot_id)
        .subquery()
    )
    stmt = (
        select(
            BotAccount,
            func.coalesce(total.c.cnt, 0),
            func.coalesce(blocked.c.cnt, 0),
        )
        .outerjoin(total, total.c.bot_id == BotAccount.id)
        .outerjoin(blocked, blocked.c.bot_id == BotAccount.id)
        .order_by(BotAccount.sort_order, BotAccount.id)
    )
    return [(row[0], row[1], row[2]) for row in (await session.execute(stmt)).all()]
