"""Сборка админ-бота."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.admin import channels, core, mailing, promos, texts
from app.admin.common import IsAdmin


def build_admin_dispatcher(admin_ids: set[int]) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    is_admin = IsAdmin(admin_ids)
    for router in (core.router, promos.router, channels.router, texts.router, mailing.router):
        router.message.filter(is_admin)
        router.callback_query.filter(is_admin)
        dp.include_router(router)

    return dp
