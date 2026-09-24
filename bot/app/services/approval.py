"""Одобрение накопленных заявок.

Основной канал принимает людей раз в неделю: заявки лежат в статусе pending,
раз в неделю планировщик одобряет их пачкой. Второстепенные каналы
(approve_mode='never') не трогаем — заявка висит, но промокод человек уже получил.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Channel, JoinRequest, User

log = logging.getLogger(__name__)


async def approve_channel(
    session: AsyncSession,
    bot: Bot,
    channel: Channel,
    *,
    limit: int | None = None,
    pause: float = 0.2,
) -> tuple[int, int]:
    """Одобряет pending-заявки канала. Возвращает (одобрено, ошибок)."""

    stmt = (
        select(JoinRequest, User)
        .join(User, User.id == JoinRequest.user_id)
        .where(JoinRequest.channel_id == channel.id, JoinRequest.status == "pending")
        .order_by(JoinRequest.created_at)
    )
    if limit:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).all()
    approved = failed = 0

    for join, user in rows:
        try:
            await bot.approve_chat_join_request(channel.tg_chat_id, user.tg_id)
            join.status = "approved"
            join.approved_at = datetime.now(timezone.utc)
            approved += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            continue
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if "hide_requester_missing" in message or "user_already_participant" in message:
                # заявка уже отозвана или человек уже в канале
                join.status = "approved"
                join.approved_at = datetime.now(timezone.utc)
            else:
                join.status = "failed"
                failed += 1
                log.warning("Не одобрили %s в %s: %s", user.tg_id, channel.title, exc)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.error("Ошибка одобрения %s в %s: %s", user.tg_id, channel.title, exc)
        await asyncio.sleep(pause)

    await session.commit()
    log.info("Канал %s: одобрено %s, ошибок %s", channel.title, approved, failed)
    return approved, failed


async def run_scheduled_approvals(
    sessionmaker: async_sessionmaker[AsyncSession],
    bots: list[Bot],
    tz_name: str,
) -> None:
    """Вызывается планировщиком раз в час: смотрим, чей сейчас день и час."""

    if not bots:
        return

    now = datetime.now(ZoneInfo(tz_name))
    async with sessionmaker() as session:
        channels = (
            await session.scalars(
                select(Channel).where(
                    Channel.enabled.is_(True), Channel.approve_mode == "weekly"
                )
            )
        ).all()

        for channel in channels:
            if channel.approve_weekday != now.weekday() or channel.approve_hour != now.hour:
                continue
            await approve_channel(session, bots[0], channel)
