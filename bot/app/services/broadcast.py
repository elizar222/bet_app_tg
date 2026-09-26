"""Рассылки. Каждому пользователю пишет тот бот, за которым он закреплён —
иначе человек получит сообщение от незнакомого бота и отправит репорт.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings_store
from app.models import BotAccount, Broadcast, Promo, User
from app.services import messaging
from app.services.sender import SendResult, sender

log = logging.getLogger(__name__)


async def _bots_by_internal_id(session: AsyncSession, bots: list[Bot]) -> dict[int, Bot]:
    accounts = (await session.scalars(select(BotAccount))).all()
    by_tg_id = {bot.id: bot for bot in bots}
    return {acc.id: by_tg_id[acc.tg_bot_id] for acc in accounts if acc.tg_bot_id in by_tg_id}


async def run_broadcast(
    sessionmaker: async_sessionmaker[AsyncSession],
    bots: list[Bot],
    broadcast_id: int,
    *,
    progress_every: int = 50,
) -> Broadcast | None:
    async with sessionmaker() as session:
        broadcast = await session.get(Broadcast, broadcast_id)
        if broadcast is None or broadcast.status == "sending":
            return broadcast

        broadcast.status = "sending"
        broadcast.sent_count = broadcast.failed_count = broadcast.blocked_count = 0
        await session.commit()

        bot_by_id = await _bots_by_internal_id(session, bots)
        global_ref = await settings_store.get(session, "ref_link")
        promo = await session.scalar(
            select(Promo).where(Promo.enabled.is_(True)).order_by(Promo.id.desc())
        )

        keyboard = None
        if broadcast.button_text and broadcast.button_url:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=broadcast.button_text, url=broadcast.button_url)]
                ]
            )

        users = (
            await session.scalars(select(User).where(User.is_blocked.is_(False)))
        ).all()

        for index, user in enumerate(users, start=1):
            bot = bot_by_id.get(user.bot_id)
            if bot is None:
                broadcast.failed_count += 1
                continue

            text = messaging.render(
                broadcast.text,
                name=user.first_name or "друг",
                promo=promo.code if promo else "",
                promo_title=(promo.description or promo.title) if promo else "",
                ref_link=messaging.personal_link(promo.ref_link if promo and promo.ref_link else global_ref, user.tg_id),
            )

            markup = keyboard
            if keyboard is not None and "{tg_id}" in (broadcast.button_url or ""):
                markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                    text=broadcast.button_text, url=messaging.personal_link(broadcast.button_url, user.tg_id))]])
            result = await sender.send(bot, user.dm_chat_id, text, reply_markup=markup)
            if result == SendResult.OK:
                broadcast.sent_count += 1
                user.last_sent_at = datetime.now(timezone.utc)
            elif result == SendResult.BLOCKED:
                broadcast.blocked_count += 1
                user.is_blocked = True
            else:
                broadcast.failed_count += 1

            if index % progress_every == 0:
                await session.commit()

        broadcast.status = "done"
        broadcast.finished_at = datetime.now(timezone.utc)
        await session.commit()
        log.info(
            "Рассылка #%s завершена: отправлено %s, заблокировали %s, ошибок %s",
            broadcast.id,
            broadcast.sent_count,
            broadcast.blocked_count,
            broadcast.failed_count,
        )
        return broadcast


async def run_weekly(
    sessionmaker: async_sessionmaker[AsyncSession],
    bots: list[Bot],
    tz_name: str,
) -> None:
    """Раз в час проверяем, не пора ли слать еженедельную рассылку."""

    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(tz_name))

    async with sessionmaker() as session:
        if not await settings_store.get_bool(session, "weekly_enabled"):
            return
        if await settings_store.get_int(session, "weekly_weekday", 4) != now.weekday():
            return
        if await settings_store.get_int(session, "weekly_hour", 18) != now.hour:
            return

        broadcast = Broadcast(
            text=await settings_store.get(session, "weekly_text"),
            button_text=await settings_store.get(session, "weekly_button_text"),
            button_url=await settings_store.get(session, "ref_link"),
            kind="weekly",
            status="draft",
        )
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)
        broadcast_id = broadcast.id

    await run_broadcast(sessionmaker, bots, broadcast_id)
