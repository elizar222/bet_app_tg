"""Раздел «Каналы»: где ловим заявки, что выдаём, когда одобряем."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.common import APPROVE_MODES, WEEKDAYS, Form, back_button, show, yes_no
from app.models import Channel, JoinRequest, Promo

router = Router(name="admin-channels")

FIELDS = {
    "title": "Название",
    "tg_chat_id": "ID канала (например -1001234567890)",
    "invite_link": "Ссылка-приглашение (с заявкой!)",
    "message_template": "Свой текст выдачи (пусто = общий)",
    "approve_hour": "Час одобрения (0-23)",
}


async def render_list(event: CallbackQuery, session: AsyncSession) -> None:
    channels = (await session.scalars(select(Channel).order_by(Channel.sort_order, Channel.id))).all()
    rows = [
        [
            InlineKeyboardButton(
                text=f"{yes_no(c.enabled)} {c.title} · {APPROVE_MODES.get(c.approve_mode, c.approve_mode)}",
                callback_data=f"chan:{c.id}",
            )
        ]
        for c in channels
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="chan_new")])
    rows.append(back_button())

    text = (
        "📢 <b>Каналы</b>\n\n"
        "Не забудь: все рабочие боты должны быть админами канала "
        "с правом добавлять участников, а в самом канале включена "
        "«Заявки на вступление»."
    )
    await show(event, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "channels")
async def channels_list(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await render_list(call, session)


@router.callback_query(F.data.startswith("chan:"))
async def channel_card(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            await render_list(call, session)
            return

        promo = await session.get(Promo, channel.promo_id) if channel.promo_id else None
        waiting = len(
            (
                await session.scalars(
                    select(JoinRequest.id).where(
                        JoinRequest.channel_id == channel.id, JoinRequest.status == "pending"
                    )
                )
            ).all()
        )

        schedule = ""
        if channel.approve_mode == "weekly":
            schedule = (
                f"\nОдобрение: {WEEKDAYS[channel.approve_weekday]} в {channel.approve_hour:02d}:00"
            )

        text = (
            f"📢 <b>{channel.title}</b>\n\n"
            f"ID: <code>{channel.tg_chat_id}</code>\n"
            f"Ссылка: {channel.invite_link or '— (обязательно добавь)'}\n"
            f"Роль: {'основной' if channel.role == 'main' else 'дополнительный'}\n"
            f"Режим заявок: {APPROVE_MODES.get(channel.approve_mode)}{schedule}\n"
            f"Промокод: {promo.code if promo else '— (не выдаётся!)'}\n"
            f"Показывать в офферах: {yes_no(channel.offer_in_menu)}\n"
            f"Активен: {yes_no(channel.enabled)}\n"
            f"Заявок ждёт одобрения: <b>{waiting}</b>"
        )

        rows = [
            [InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"chan_edit:{channel.id}:{field}")]
            for field, label in FIELDS.items()
        ]
        rows.append(
            [
                InlineKeyboardButton(text="🎟 Промокод", callback_data=f"chan_promo:{channel.id}"),
                InlineKeyboardButton(text="🔁 Режим", callback_data=f"chan_mode:{channel.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="📅 День недели", callback_data=f"chan_wd:{channel.id}"),
                InlineKeyboardButton(
                    text=f"{yes_no(channel.offer_in_menu)} В офферах",
                    callback_data=f"chan_offer:{channel.id}",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Выключить" if channel.enabled else "✅ Включить",
                    callback_data=f"chan_tgl:{channel.id}",
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"chan_del:{channel.id}"),
            ]
        )
        if channel.approve_mode == "weekly" and waiting:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Одобрить сейчас ({waiting})", callback_data=f"chan_run:{channel.id}"
                    )
                ]
            )
        rows.append(back_button("channels"))
        await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "chan_new")
async def channel_new(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], state: FSMContext) -> None:
    async with sessionmaker() as session:
        # временный уникальный tg_chat_id, админ заменит его следующим шагом
        placeholder = -(await session.scalar(select(Channel.id).order_by(Channel.id.desc())) or 0) - 1
        channel = Channel(
            tg_chat_id=placeholder,
            title="Новый канал",
            approve_mode="never",
            enabled=False,
        )
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        channel_id = channel.id

    await state.set_state(Form.waiting_value)
    await state.update_data(kind="channel", entity_id=channel_id, field="tg_chat_id")
    await show(
        call,
        (
            "Создан черновик канала.\n\n"
            "Пришли <b>ID канала</b> (вида <code>-1001234567890</code>).\n\n"
            "Где взять: перешли мне любой пост из канала — я вытащу ID сам."
        ),
        InlineKeyboardMarkup(inline_keyboard=[back_button(f"chan:{channel_id}", "⬅️ Отмена")]),
    )


@router.callback_query(F.data.startswith("chan_edit:"))
async def channel_edit(call: CallbackQuery, state: FSMContext) -> None:
    _, channel_id, field = call.data.split(":")
    await state.set_state(Form.waiting_value)
    await state.update_data(kind="channel", entity_id=int(channel_id), field=field)
    hint = ""
    if field == "tg_chat_id":
        hint = "\n\nМожно просто переслать пост из канала."
    if field == "message_template":
        hint = (
            "\n\nПлейсхолдеры: <code>{name}</code> <code>{promo}</code> "
            "<code>{ref_link}</code> <code>{channel}</code>\n"
            "Пришли <code>-</code>, чтобы вернуть общий текст."
        )
    await show(
        call,
        f"Пришли новое значение: <b>{FIELDS[field]}</b>{hint}\n\nОтмена — /cancel",
        InlineKeyboardMarkup(inline_keyboard=[back_button(f"chan:{channel_id}", "⬅️ Отмена")]),
    )


@router.callback_query(F.data.startswith("chan_mode:"))
async def channel_mode(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    order = list(APPROVE_MODES)
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is not None:
            current = order.index(channel.approve_mode) if channel.approve_mode in order else 0
            channel.approve_mode = order[(current + 1) % len(order)]
            channel.role = "main" if channel.approve_mode == "weekly" else "extra"
            await session.commit()
    await channel_card(call, sessionmaker)


@router.callback_query(F.data.startswith("chan_wd:"))
async def channel_weekday(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is not None:
            channel.approve_weekday = (channel.approve_weekday + 1) % 7
            await session.commit()
    await channel_card(call, sessionmaker)


@router.callback_query(F.data.startswith("chan_offer:"))
async def channel_offer(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is not None:
            channel.offer_in_menu = not channel.offer_in_menu
            await session.commit()
    await channel_card(call, sessionmaker)


@router.callback_query(F.data.startswith("chan_tgl:"))
async def channel_toggle(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is not None:
            channel.enabled = not channel.enabled
            await session.commit()
    await channel_card(call, sessionmaker)


@router.callback_query(F.data.startswith("chan_del:"))
async def channel_delete(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is not None:
            await session.delete(channel)
            await session.commit()
        await render_list(call, session)


@router.callback_query(F.data.startswith("chan_promo:"))
async def channel_promo_pick(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    channel_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        promos = (await session.scalars(select(Promo).order_by(Promo.id))).all()
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{yes_no(p.enabled)} {p.title} — {p.code}",
                    callback_data=f"chan_setpromo:{channel_id}:{p.id}",
                )
            ]
            for p in promos
        ]
        rows.append(
            [InlineKeyboardButton(text="— Убрать промокод", callback_data=f"chan_setpromo:{channel_id}:0")]
        )
        rows.append(back_button(f"chan:{channel_id}"))
        await show(call, "Какой промокод выдавать за заявку в этот канал?", InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("chan_setpromo:"))
async def channel_promo_set(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    _, channel_id, promo_id = call.data.split(":")
    async with sessionmaker() as session:
        channel = await session.get(Channel, int(channel_id))
        if channel is not None:
            channel.promo_id = int(promo_id) or None
            await session.commit()
    await channel_card(call, sessionmaker)


@router.callback_query(F.data.startswith("chan_run:"))
async def channel_approve_now(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    worker_bots: list,
) -> None:
    """Ручное одобрение накопленных заявок — не дожидаясь расписания."""

    from app.services.approval import approve_channel

    channel_id = int(call.data.split(":")[1])
    if not worker_bots:
        await call.answer("Нет активных рабочих ботов", show_alert=True)
        return

    await call.answer("Одобряю заявки, это может занять время…")
    async with sessionmaker() as session:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            return
        approved, failed = await approve_channel(session, worker_bots[0], channel)

    if call.message is not None:
        await call.message.answer(f"✅ Одобрено: {approved}\n⚠️ Ошибок: {failed}")
    await channel_card(call, sessionmaker)
