"""Главное меню, боты, статистика и универсальный приём введённых значений."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings_store
from app.admin import channels as channels_module
from app.admin import promos as promos_module
from app.admin.common import Form, back_button, main_menu, show, yes_no
from app.models import BotAccount, Channel, JoinRequest, Promo, User
from app.services.assignment import bot_load

router = Router(name="admin-core")

MENU_TEXT = "🛠 <b>Админка</b>\n\nВсё, что здесь настроено, сразу видят все рабочие боты."


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, single_bot: bool = False) -> None:
    if single_bot:
        # Один бот на всё: /start показывает то же, что видят пользователи,
        # а админка открывается командой /admin.
        raise SkipHandler()
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=main_menu())


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил.", reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, MENU_TEXT, main_menu())


@router.callback_query(F.data == "bots")
async def bots_list(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        rows_data = await bot_load(session)

    lines = ["🤖 <b>Рабочие боты</b>\n"]
    keyboard: list[list[InlineKeyboardButton]] = []
    for account, total, blocked in rows_data:
        lines.append(
            f"{yes_no(account.enabled)} @{account.username or account.tg_bot_id} — "
            f"{total} юзеров, заблокировали {blocked}"
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{yes_no(account.enabled)} @{account.username or account.tg_bot_id}",
                    callback_data=f"bot_tgl:{account.id}",
                )
            ]
        )

    lines.append(
        "\nНовые юзеры уходят боту с наименьшей нагрузкой. "
        "Выключенный бот перестаёт получать новых, но продолжает вести своих."
    )
    keyboard.append(back_button())
    await show(call, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("bot_tgl:"))
async def bot_toggle(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    bot_db_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        account = await session.get(BotAccount, bot_db_id)
        if account is not None:
            account.enabled = not account.enabled
            await session.commit()
    await bots_list(call, sessionmaker)


@router.callback_query(F.data == "stats")
async def stats(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        users = await session.scalar(select(func.count(User.id))) or 0
        blocked = await session.scalar(select(func.count(User.id)).where(User.is_blocked.is_(True))) or 0
        requests = await session.scalar(select(func.count(JoinRequest.id))) or 0
        pending = await session.scalar(
            select(func.count(JoinRequest.id)).where(JoinRequest.status == "pending")
        ) or 0
        promos_sent = await session.scalar(
            select(func.count(JoinRequest.id)).where(JoinRequest.promo_sent.is_(True))
        ) or 0

        per_channel = (
            await session.execute(
                select(Channel.title, func.count(JoinRequest.id))
                .join(JoinRequest, JoinRequest.channel_id == Channel.id)
                .group_by(Channel.id)
                .order_by(func.count(JoinRequest.id).desc())
            )
        ).all()

    lines = [
        "📊 <b>Статистика</b>\n",
        f"Пользователей: <b>{users}</b>",
        f"Заблокировали бота: <b>{blocked}</b>",
        f"Заявок всего: <b>{requests}</b> (ждут одобрения: {pending})",
        f"Промокодов выдано: <b>{promos_sent}</b>",
    ]
    if per_channel:
        lines.append("\n<b>По каналам:</b>")
        lines += [f"• {title} — {count}" for title, count in per_channel]

    await show(call, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[back_button()]))


@router.message(Form.waiting_value)
async def receive_value(
    message: Message, state: FSMContext, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """Один обработчик на все поля: что редактируем — лежит в state."""

    data = await state.get_data()
    kind = data.get("kind")
    entity_id = int(data.get("entity_id") or 0)
    field = data.get("field")

    raw = (message.text or "").strip()

    # Пересланный из канала пост — удобный способ узнать ID канала
    title_from_forward = None
    if field == "tg_chat_id":
        origin_chat = getattr(getattr(message, "forward_origin", None), "chat", None)
        if origin_chat is None:
            origin_chat = getattr(message, "forward_from_chat", None)
        if origin_chat is not None:
            raw = str(origin_chat.id)
            title_from_forward = origin_chat.title

    if not raw:
        await message.answer("Пусто. Пришли значение текстом или /cancel.")
        return

    async with sessionmaker() as session:
        if kind == "setting":
            await settings_store.set_value(session, field, raw)
            await state.clear()
            await message.answer(
                f"✅ Сохранено: <b>{settings_store.label(field)}</b>", reply_markup=main_menu()
            )
            return

        if kind == "promo":
            promo = await session.get(Promo, entity_id)
            if promo is None:
                await state.clear()
                await message.answer("Промокод не найден.", reply_markup=main_menu())
                return
            setattr(promo, field, None if raw == "-" else raw)
            if field == "code" and promo.title == "Новый промокод":
                promo.title = raw
            await session.commit()
            await state.clear()
            await message.answer(
                "✅ Сохранено.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[back_button(f"promo:{entity_id}", "⬅️ К промокоду")]
                ),
            )
            return

        if kind == "channel":
            channel = await session.get(Channel, entity_id)
            if channel is None:
                await state.clear()
                await message.answer("Канал не найден.", reply_markup=main_menu())
                return

            if field == "tg_chat_id":
                try:
                    chat_id = int(raw)
                except ValueError:
                    await message.answer("ID должен быть числом вида <code>-1001234567890</code>.")
                    return
                exists = await session.scalar(
                    select(Channel).where(Channel.tg_chat_id == chat_id, Channel.id != channel.id)
                )
                if exists is not None:
                    await message.answer("Такой канал уже добавлен.")
                    return
                channel.tg_chat_id = chat_id
                if title_from_forward and channel.title == "Новый канал":
                    channel.title = title_from_forward
            elif field == "approve_hour":
                if not raw.isdigit() or not 0 <= int(raw) <= 23:
                    await message.answer("Нужно число от 0 до 23.")
                    return
                channel.approve_hour = int(raw)
            else:
                setattr(channel, field, None if raw == "-" else raw)

            await session.commit()
            await state.clear()
            await message.answer(
                "✅ Сохранено.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[back_button(f"chan:{entity_id}", "⬅️ К каналу")]
                ),
            )
            return

    await state.clear()
    await message.answer("Не понял, что редактируем.", reply_markup=main_menu())


# импорты нужны, чтобы роутеры промокодов/каналов не потерялись при сборке
__all__ = ["router", "promos_module", "channels_module"]
