"""Сборка текстов и клавиатур, которые уходят пользователю."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.models import Channel, JoinRequest, Promo, User


def render(template: str, **values: str) -> str:
    """Безопасная подстановка: неизвестный плейсхолдер не роняет отправку."""

    class _Safe(dict):
        def __missing__(self, key: str) -> str:  # noqa: D105
            return "{" + key + "}"

    try:
        return template.format_map(_Safe(values))
    except (ValueError, IndexError):
        return template


async def promo_for_channel(session: AsyncSession, channel: Channel) -> Promo | None:
    if channel.promo_id is None:
        return None
    promo = await session.get(Promo, channel.promo_id)
    return promo if promo and promo.enabled else None


async def build_promo_text(
    session: AsyncSession,
    *,
    user: User,
    channel: Channel,
    promo: Promo,
) -> str:
    global_ref = await settings_store.get(session, "ref_link")
    template = channel.message_template or await settings_store.get(session, "greeting_template")
    note = await settings_store.get(session, "retention_note")

    body = render(
        template,
        name=user.first_name or "друг",
        promo=promo.code,
        promo_title=promo.description or promo.title,
        ref_link=promo.ref_link or global_ref,
        channel=channel.title,
    )
    return f"{body}\n\n{note}" if note else body


async def build_offers_keyboard(
    session: AsyncSession,
    *,
    user: User,
    exclude_channel_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Кнопки на остальные каналы, за заявку в которые дадут ещё промокод.

    Каналы, где юзер уже оставлял заявку, не показываем.
    """

    done = set(
        (
            await session.scalars(
                select(JoinRequest.channel_id).where(JoinRequest.user_id == user.id)
            )
        ).all()
    )
    if exclude_channel_id is not None:
        done.add(exclude_channel_id)

    channels = (
        await session.scalars(
            select(Channel)
            .where(
                Channel.enabled.is_(True),
                Channel.offer_in_menu.is_(True),
                Channel.invite_link.is_not(None),
            )
            .order_by(Channel.sort_order, Channel.id)
        )
    ).all()

    prefix = await settings_store.get(session, "offer_button_prefix")
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        if channel.id in done or not channel.invite_link:
            continue
        rows.append(
            [InlineKeyboardButton(text=f"{prefix}{channel.title}", url=channel.invite_link)]
        )

    if not rows:
        return None

    header = await settings_store.get(session, "offers_header")
    return header, InlineKeyboardMarkup(inline_keyboard=rows)
