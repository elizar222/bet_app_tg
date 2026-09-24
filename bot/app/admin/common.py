"""Общие штуки для админки: фильтр доступа, клавиатуры, состояния."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

APPROVE_MODES = {
    "weekly": "раз в неделю",
    "never": "не одобрять",
    "instant": "сразу",
}


class IsAdmin(BaseFilter):
    def __init__(self, admin_ids: set[int]) -> None:
        self.admin_ids = admin_ids

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in self.admin_ids


class Form(StatesGroup):
    """Один универсальный экран ввода: что редактируем — лежит в data."""

    waiting_value = State()
    broadcast_text = State()
    broadcast_button_text = State()
    broadcast_button_url = State()


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos"),
                InlineKeyboardButton(text="📢 Каналы", callback_data="channels"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Тексты и ссылки", callback_data="cfg"),
                InlineKeyboardButton(text="📨 Рассылка", callback_data="mail"),
            ],
            [
                InlineKeyboardButton(text="🤖 Боты", callback_data="bots"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
            ],
            [
                InlineKeyboardButton(text="👑 VIP", callback_data="vip"),
                InlineKeyboardButton(text="📱 Мини-апп", callback_data="webstats"),
            ],
        ]
    )


def back_button(callback_data: str = "menu", text: str = "⬅️ Назад") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=text, callback_data=callback_data)]


async def show(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Отправить или отредактировать сообщение — в зависимости от типа апдейта."""

    if isinstance(event, CallbackQuery):
        if event.message is None:
            return
        try:
            await event.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001 — «message is not modified» и подобное
            await event.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup, disable_web_page_preview=True)


def yes_no(value: bool) -> str:
    return "✅" if value else "❌"
