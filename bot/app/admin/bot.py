"""Сборка админ-бота."""

from __future__ import annotations

from aiogram import Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage

from app.admin import channels, core, mailing, promos, texts, vip
from app.admin.common import IsAdmin


def build_admin_router(admin_ids: set[int]) -> Router:
    """Все разделы админки в одном роутере, доступ только для ADMIN_IDS."""

    root = Router(name="admin")
    is_admin = IsAdmin(admin_ids)
    for router in (core.router, promos.router, channels.router, texts.router, mailing.router, vip.router):
        router.message.filter(is_admin)
        router.callback_query.filter(is_admin)
        root.include_router(router)
    return root


def build_admin_dispatcher(admin_ids: set[int]) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_admin_router(admin_ids))
    return dp
