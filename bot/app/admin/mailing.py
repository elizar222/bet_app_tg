"""Раздел «Рассылка»: разовая + настройки еженедельной."""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings_store
from app.admin.common import WEEKDAYS, Form, back_button, show, yes_no
from app.models import Broadcast, User
from app.services.broadcast import run_broadcast

router = Router(name="admin-mailing")


async def _audience(session: AsyncSession) -> int:
    return await session.scalar(select(func.count(User.id)).where(User.is_blocked.is_(False))) or 0


@router.callback_query(F.data == "mail")
async def mail_menu(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        audience = await _audience(session)
        enabled = await settings_store.get_bool(session, "weekly_enabled")
        weekday = await settings_store.get_int(session, "weekly_weekday", 4)
        hour = await settings_store.get_int(session, "weekly_hour", 18)
        last = (
            await session.scalars(
                select(Broadcast).where(Broadcast.status == "done").order_by(Broadcast.id.desc()).limit(1)
            )
        ).first()

    text = (
        "📨 <b>Рассылка</b>\n\n"
        f"Получателей сейчас: <b>{audience}</b>\n\n"
        f"Еженедельная: {yes_no(enabled)} — {WEEKDAYS[weekday % 7]} в {hour:02d}:00"
    )
    if last is not None:
        text += (
            f"\n\nПоследняя: отправлено {last.sent_count}, "
            f"заблокировали {last.blocked_count}, ошибок {last.failed_count}"
        )

    rows = [
        [InlineKeyboardButton(text="✍️ Разовая рассылка", callback_data="mail_new")],
        [
            InlineKeyboardButton(
                text=f"{yes_no(enabled)} Еженедельная", callback_data="mail_weekly_tgl"
            ),
            InlineKeyboardButton(text="📅 День", callback_data="mail_weekly_wd"),
        ],
        [
            InlineKeyboardButton(text="🕐 Час", callback_data="mail_weekly_hour"),
            InlineKeyboardButton(text="✏️ Текст", callback_data="mail_weekly_text"),
        ],
        [InlineKeyboardButton(text="🚀 Отправить еженедельную сейчас", callback_data="mail_weekly_run")],
        back_button(),
    ]
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "mail_weekly_tgl")
async def weekly_toggle(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        current = await settings_store.get_bool(session, "weekly_enabled")
        await settings_store.set_value(session, "weekly_enabled", "0" if current else "1")
    await mail_menu(call, sessionmaker)


@router.callback_query(F.data == "mail_weekly_wd")
async def weekly_weekday(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        current = await settings_store.get_int(session, "weekly_weekday", 4)
        await settings_store.set_value(session, "weekly_weekday", str((current + 1) % 7))
    await mail_menu(call, sessionmaker)


@router.callback_query(F.data == "mail_weekly_hour")
async def weekly_hour(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], state: FSMContext) -> None:
    await state.set_state(Form.waiting_value)
    await state.update_data(kind="setting", entity_id=0, field="weekly_hour")
    await show(
        call,
        "Пришли час рассылки (0-23):",
        InlineKeyboardMarkup(inline_keyboard=[back_button("mail", "⬅️ Отмена")]),
    )


@router.callback_query(F.data == "mail_weekly_text")
async def weekly_text(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], state: FSMContext) -> None:
    async with sessionmaker() as session:
        current = await settings_store.get(session, "weekly_text")
    await state.set_state(Form.waiting_value)
    await state.update_data(kind="setting", entity_id=0, field="weekly_text")
    await show(
        call,
        f"Текст еженедельной рассылки.\n\nСейчас:\n<code>{current}</code>\n\nПришли новый:",
        InlineKeyboardMarkup(inline_keyboard=[back_button("mail", "⬅️ Отмена")]),
    )


@router.callback_query(F.data == "mail_new")
async def mail_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Form.broadcast_text)
    await state.update_data(broadcast={})
    await show(
        call,
        (
            "Пришли текст рассылки.\n\n"
            "Плейсхолдеры: <code>{name}</code> <code>{promo}</code> <code>{ref_link}</code>\n"
            "Отмена — /cancel"
        ),
        InlineKeyboardMarkup(inline_keyboard=[back_button("mail", "⬅️ Отмена")]),
    )


@router.message(Form.broadcast_text)
async def mail_got_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужен текст сообщения.")
        return
    await state.update_data(broadcast={"text": message.html_text})
    await state.set_state(Form.broadcast_button_text)
    await message.answer("Текст кнопки под сообщением? Пришли <code>-</code>, если кнопка не нужна.")


@router.message(Form.broadcast_button_text)
async def mail_got_button(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    payload = data.get("broadcast", {})
    value = (message.text or "").strip()

    if value == "-":
        payload["button_text"] = None
        await state.update_data(broadcast=payload)
        await _preview(message, state)
        return

    payload["button_text"] = value
    await state.update_data(broadcast=payload)
    await state.set_state(Form.broadcast_button_url)
    await message.answer("Ссылка для кнопки? Пришли <code>-</code>, чтобы взять глобальную реф-ссылку.")


@router.message(Form.broadcast_button_url)
async def mail_got_url(message: Message, state: FSMContext, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    data = await state.get_data()
    payload = data.get("broadcast", {})
    value = (message.text or "").strip()

    if value == "-":
        async with sessionmaker() as session:
            value = await settings_store.get(session, "ref_link")
    payload["button_url"] = value
    await state.update_data(broadcast=payload)
    await _preview(message, state)


async def _preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    payload = data.get("broadcast", {})
    await state.set_state(None)

    preview = payload.get("text", "")
    extra = ""
    if payload.get("button_text"):
        extra = f"\n\nКнопка: <b>{payload['button_text']}</b> → {payload.get('button_url')}"

    await message.answer(
        f"<b>Предпросмотр:</b>\n\n{preview}{extra}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Отправить всем", callback_data="mail_go")],
                back_button("mail", "⬅️ Отмена"),
            ]
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "mail_go")
async def mail_go(
    call: CallbackQuery,
    state: FSMContext,
    sessionmaker: async_sessionmaker[AsyncSession],
    worker_bots: list,
) -> None:
    data = await state.get_data()
    payload = data.get("broadcast") or {}
    if not payload.get("text"):
        await call.answer("Текст потерялся, начни заново", show_alert=True)
        return

    async with sessionmaker() as session:
        broadcast = Broadcast(
            text=payload["text"],
            button_text=payload.get("button_text"),
            button_url=payload.get("button_url"),
            kind="manual",
        )
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)
        broadcast_id = broadcast.id

    await state.clear()
    await call.answer("Запустил")
    if call.message is not None:
        await call.message.answer("🚀 Рассылка пошла. Отчёт пришлю, когда закончится.")

    asyncio.create_task(_run_and_report(call, sessionmaker, worker_bots, broadcast_id))


@router.callback_query(F.data == "mail_weekly_run")
async def weekly_run(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], worker_bots: list
) -> None:
    async with sessionmaker() as session:
        broadcast = Broadcast(
            text=await settings_store.get(session, "weekly_text"),
            button_text=await settings_store.get(session, "weekly_button_text"),
            button_url=await settings_store.get(session, "ref_link"),
            kind="weekly",
        )
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)
        broadcast_id = broadcast.id

    await call.answer("Запустил")
    if call.message is not None:
        await call.message.answer("🚀 Еженедельная рассылка пошла.")
    asyncio.create_task(_run_and_report(call, sessionmaker, worker_bots, broadcast_id))


async def _run_and_report(
    call: CallbackQuery,
    sessionmaker: async_sessionmaker[AsyncSession],
    worker_bots: list,
    broadcast_id: int,
) -> None:
    result = await run_broadcast(sessionmaker, worker_bots, broadcast_id)
    if result is not None and call.message is not None:
        await call.message.answer(
            f"✅ Рассылка #{result.id} завершена\n"
            f"Доставлено: {result.sent_count}\n"
            f"Заблокировали бота: {result.blocked_count}\n"
            f"Ошибок: {result.failed_count}"
        )
