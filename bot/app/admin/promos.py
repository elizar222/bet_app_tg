"""Раздел «Промокоды»."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.common import Form, back_button, show, yes_no
from app.models import Channel, Promo

router = Router(name="admin-promos")

FIELDS = {
    "title": "Название",
    "code": "Код",
    "description": "Описание",
    "ref_link": "Реф-ссылка (пусто = глобальная)",
}


async def render_list(event: CallbackQuery, session: AsyncSession) -> None:
    promos = (await session.scalars(select(Promo).order_by(Promo.id))).all()
    rows = [
        [
            InlineKeyboardButton(
                text=f"{yes_no(p.enabled)} {p.title} — {p.code}", callback_data=f"promo:{p.id}"
            )
        ]
        for p in promos
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить промокод", callback_data="promo_new")])
    rows.append(back_button())

    text = "🎟 <b>Промокоды</b>\n\nВыбери промокод для редактирования."
    if not promos:
        text = "🎟 <b>Промокоды</b>\n\nПока пусто. Добавь первый — он понадобится каналам."
    await show(event, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "promos")
async def promos_list(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await render_list(call, session)


@router.callback_query(F.data.startswith("promo:"))
async def promo_card(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    promo_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        promo = await session.get(Promo, promo_id)
        if promo is None:
            await promos_list(call, sessionmaker)
            return

        used_by = (
            await session.scalars(select(Channel.title).where(Channel.promo_id == promo.id))
        ).all()

        text = (
            f"🎟 <b>{promo.title}</b>\n\n"
            f"Код: <code>{promo.code}</code>\n"
            f"Описание: {promo.description or '—'}\n"
            f"Своя ссылка: {promo.ref_link or 'глобальная'}\n"
            f"Активен: {yes_no(promo.enabled)}\n"
            f"Каналы: {', '.join(used_by) if used_by else '—'}"
        )
        rows = [
            [
                InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"promo_edit:{promo.id}:{field}")
            ]
            for field, label in FIELDS.items()
        ]
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Выключить" if promo.enabled else "✅ Включить",
                    callback_data=f"promo_tgl:{promo.id}",
                ),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"promo_del:{promo.id}"),
            ]
        )
        rows.append(back_button("promos"))
        await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("promo_tgl:"))
async def promo_toggle(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    promo_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        promo = await session.get(Promo, promo_id)
        if promo is not None:
            promo.enabled = not promo.enabled
            await session.commit()
    await promo_card(call, sessionmaker)


@router.callback_query(F.data.startswith("promo_del:"))
async def promo_delete(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    promo_id = int(call.data.split(":")[1])
    async with sessionmaker() as session:
        promo = await session.get(Promo, promo_id)
        if promo is not None:
            await session.execute(
                Channel.__table__.update().where(Channel.promo_id == promo.id).values(promo_id=None)
            )
            await session.delete(promo)
            await session.commit()
        await render_list(call, session)


@router.callback_query(F.data.startswith("promo_edit:"))
async def promo_edit(call: CallbackQuery, state: FSMContext) -> None:
    _, promo_id, field = call.data.split(":")
    await state.set_state(Form.waiting_value)
    await state.update_data(kind="promo", entity_id=int(promo_id), field=field)
    await show(
        call,
        f"Пришли новое значение: <b>{FIELDS[field]}</b>\n\nОтмена — /cancel",
        InlineKeyboardMarkup(inline_keyboard=[back_button(f"promo:{promo_id}", "⬅️ Отмена")]),
    )


@router.callback_query(F.data == "promo_new")
async def promo_new(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], state: FSMContext) -> None:
    async with sessionmaker() as session:
        promo = Promo(title="Новый промокод", code="CHANGEME", enabled=False)
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
        promo_id = promo.id

    await state.set_state(Form.waiting_value)
    await state.update_data(kind="promo", entity_id=promo_id, field="code")
    await show(
        call,
        "Создан черновик промокода.\n\nПришли <b>код</b> (например <code>WIN500</code>):",
        InlineKeyboardMarkup(inline_keyboard=[back_button(f"promo:{promo_id}", "⬅️ Отмена")]),
    )
