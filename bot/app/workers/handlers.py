"""Логика рабочих ботов: ловим заявку в канал — выдаём промокод.

Все боты — админы одних и тех же каналов, поэтому один и тот же
chat_join_request прилетает каждому. Отвечает только тот бот, за которым
закреплён пользователь (см. services/assignment.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import ChatJoinRequest, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app import settings_store
from app.models import Channel, JoinRequest, User
from app.services import messaging
from app.services.assignment import get_or_create_user
from app.services.sender import SendResult, sender

log = logging.getLogger(__name__)

router = Router(name="worker")


async def _channel_by_chat(session: AsyncSession, tg_chat_id: int) -> Channel | None:
    return await session.scalar(
        select(Channel).where(Channel.tg_chat_id == tg_chat_id, Channel.enabled.is_(True))
    )


async def _deliver_promo(
    session: AsyncSession,
    bot: Bot,
    *,
    user: User,
    channel: Channel,
) -> bool:
    promo = await messaging.promo_for_channel(session, channel)
    if promo is None:
        log.warning("Канал %s без промокода — сообщение не отправлено", channel.title)
        return False

    text = await messaging.build_promo_text(session, user=user, channel=channel, promo=promo)
    result = await sender.send(bot, user.dm_chat_id, text)

    if result == SendResult.BLOCKED:
        user.is_blocked = True
        await session.commit()
        return False
    if result != SendResult.OK:
        return False

    user.is_blocked = False
    user.last_sent_at = datetime.now(timezone.utc)
    await session.commit()

    offers = await messaging.build_offers_keyboard(session, user=user)
    if offers is not None:
        header, keyboard = offers
        await sender.send(bot, user.dm_chat_id, header, reply_markup=keyboard)

    return True


@router.chat_join_request()
async def on_join_request(
    event: ChatJoinRequest,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    bot_map: dict[int, int],
) -> None:
    my_bot_id = bot_map.get(bot.id)
    if my_bot_id is None:
        return

    async with sessionmaker() as session:
        channel = await _channel_by_chat(session, event.chat.id)
        if channel is None:
            log.info("Заявка в неизвестный канал %s (%s) — пропускаем", event.chat.id, event.chat.title)
            return

        user, _ = await get_or_create_user(
            session,
            tg_id=event.from_user.id,
            dm_chat_id=event.user_chat_id,
            username=event.from_user.username,
            first_name=event.from_user.first_name,
            last_name=event.from_user.last_name,
            language_code=event.from_user.language_code,
            source_channel_id=channel.id,
        )

        # Не мой пользователь — отвечает закреплённый за ним бот.
        if user.bot_id != my_bot_id:
            return

        join = await session.scalar(
            select(JoinRequest).where(
                JoinRequest.user_id == user.id, JoinRequest.channel_id == channel.id
            )
        )
        if join is None:
            join = JoinRequest(user_id=user.id, channel_id=channel.id, status="pending")
            session.add(join)
            await session.commit()
            await session.refresh(join)

        if channel.approve_mode == "instant" and join.status == "pending":
            try:
                await bot.approve_chat_join_request(event.chat.id, event.from_user.id)
                join.status = "approved"
                join.approved_at = datetime.now(timezone.utc)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                log.error("Не удалось одобрить заявку %s в %s: %s", user.tg_id, channel.title, exc)
        # weekly — заявка ждёт планировщика; never — не одобряем вообще.

        if join.promo_sent:
            note = await settings_store.get(session, "already_have_promo")
            await sender.send(bot, user.dm_chat_id, note)
            return

        if await _deliver_promo(session, bot, user=user, channel=channel):
            join.promo_sent = True
            await session.commit()
            log.info("Промокод выдан: user=%s channel=%s bot=%s", user.tg_id, channel.title, bot.id)


async def webapp_keyboard(session: AsyncSession, webapp_url: str) -> InlineKeyboardMarkup | None:
    """Кнопка открытия мини-аппа. Telegram принимает только https-адреса."""

    if not webapp_url.startswith("https://"):
        return None
    text = await settings_store.get(session, "webapp_button_text")
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url))]]
    )


@router.message(CommandStart())
async def on_start(
    message: Message,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    bot_map: dict[int, int],
    webapp_url: str = "",
    single_bot: bool = False,
    admin_ids: frozenset[int] = frozenset(),
) -> None:
    if message.from_user is None:
        return

    async with sessionmaker() as session:
        user, _ = await get_or_create_user(
            session,
            tg_id=message.from_user.id,
            dm_chat_id=message.chat.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
        )
        user.started_bot = True
        user.is_blocked = False
        await session.commit()

        text = messaging.render(
            await settings_store.get(session, "start_text"),
            name=message.from_user.first_name or "друг",
            ref_link=await settings_store.get(session, "ref_link"),
        )
        if single_bot and message.from_user.id in admin_ids:
            text += "\n\n🛠 Вы админ. Админка: /admin"
        await message.answer(
            text,
            disable_web_page_preview=True,
            reply_markup=await webapp_keyboard(session, webapp_url),
        )

        offers = await messaging.build_offers_keyboard(session, user=user)
        if offers is not None:
            header, keyboard = offers
            await message.answer(header, reply_markup=keyboard)


@router.message(F.text)
async def on_any_text(message: Message, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Любое сообщение — снимаем флаг блокировки и напоминаем про каналы."""

    if message.from_user is None:
        return

    async with sessionmaker() as session:
        user = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        if user is None:
            return
        user.is_blocked = False
        await session.commit()

        offers = await messaging.build_offers_keyboard(session, user=user)
        if offers is not None:
            header, keyboard = offers
            await message.answer(header, reply_markup=keyboard)
