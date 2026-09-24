"""Раздел «Тексты и ссылки» — редактирование settings-ключей."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings_store
from app.admin.common import Form, back_button, show

router = Router(name="admin-texts")

# Порядок показа в меню
KEYS = [
    "ref_link",
    "greeting_template",
    "retention_note",
    "offers_header",
    "offer_button_prefix",
    "start_text",
    "already_have_promo",
    "send_rate_per_sec",
]


@router.callback_query(F.data == "cfg")
async def config_list(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    rows = [
        [InlineKeyboardButton(text=settings_store.label(key), callback_data=f"cfg_edit:{key}")]
        for key in KEYS
    ]
    rows.append(back_button())
    await show(
        call,
        (
            "⚙️ <b>Тексты и ссылки</b>\n\n"
            "Вносятся один раз — их читают все боты сразу.\n\n"
            "Плейсхолдеры: <code>{name}</code> <code>{promo}</code> "
            "<code>{promo_title}</code> <code>{ref_link}</code> <code>{channel}</code>"
        ),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("cfg_edit:"))
async def config_edit(
    call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession], state: FSMContext
) -> None:
    key = call.data.split(":", 1)[1]
    async with sessionmaker() as session:
        current = await settings_store.get(session, key)

    await state.set_state(Form.waiting_value)
    await state.update_data(kind="setting", entity_id=0, field=key)
    await show(
        call,
        (
            f"<b>{settings_store.label(key)}</b>\n\n"
            f"Сейчас:\n<code>{current or '—'}</code>\n\n"
            "Пришли новое значение. Отмена — /cancel"
        ),
        InlineKeyboardMarkup(inline_keyboard=[back_button("cfg", "⬅️ Отмена")]),
    )
