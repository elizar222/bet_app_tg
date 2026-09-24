"""Планировщик: раз в час смотрит, не пора ли одобрять заявки или слать рассылку."""

from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.approval import run_scheduled_approvals
from app.services.broadcast import run_weekly

log = logging.getLogger(__name__)


def build_scheduler(
    sessionmaker: async_sessionmaker[AsyncSession],
    bots: list[Bot],
    tz_name: str,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=tz_name)

    scheduler.add_job(
        run_scheduled_approvals,
        CronTrigger(minute=1, timezone=tz_name),
        args=[sessionmaker, bots, tz_name],
        id="approvals",
        max_instances=1,
        misfire_grace_time=1800,
    )
    scheduler.add_job(
        run_weekly,
        CronTrigger(minute=5, timezone=tz_name),
        args=[sessionmaker, bots, tz_name],
        id="weekly-broadcast",
        max_instances=1,
        misfire_grace_time=1800,
    )

    return scheduler
