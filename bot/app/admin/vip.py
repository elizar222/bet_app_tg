"""Раздел «VIP» и статистика мини-аппа."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.common import back_button, show
from app.models import HedgeCalc, TrackedBet, WebProfile

router = Router(name="admin-vip")


def _name(p: WebProfile) -> str:
    return f"@{p.username}" if p.username else (p.first_name or str(p.tg_id))


async def render(call: CallbackQuery, session: AsyncSession) -> None:
    waiting = (
        await session.scalars(
            select(WebProfile)
            .where(WebProfile.tier == "base", WebProfile.onewin_id.is_not(None))
            .order_by(WebProfile.last_seen_at.desc())
            .limit(15)
        )
    ).all()
    vips = (
        await session.scalars(select(WebProfile).where(WebProfile.tier == "vip").order_by(WebProfile.tg_id).limit(30))
    ).all()

    lines = ["👑 <b>VIP мини-аппа</b>\n"]
    lines.append("Прислали 1win ID — проверь депозит в кабинете партнёрки и нажми, чтобы выдать VIP.")
    rows: list[list[InlineKeyboardButton]] = []
    for p in waiting:
        rows.append([InlineKeyboardButton(text=f"✅ {_name(p)} · 1win {p.onewin_id}", callback_data=f"vip_on:{p.tg_id}")])
    if not waiting:
        lines.append("<i>Заявок нет.</i>")
    lines.append(f"\nСейчас VIP: <b>{len(vips)}</b>. Нажми на VIP, чтобы снять статус.")
    for p in vips:
        rows.append([InlineKeyboardButton(text=f"❌ {_name(p)} · 1win {p.onewin_id or '—'}", callback_data=f"vip_off:{p.tg_id}")])
    rows.append(back_button())
    await show(call, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "vip")
async def vip_list(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await render(call, session)


@router.callback_query(F.data.startswith("vip_on:") | F.data.startswith("vip_off:"))
async def vip_toggle(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    action, tg_id = call.data.split(":")
    async with sessionmaker() as session:
        profile = await session.get(WebProfile, int(tg_id))
        if profile is not None:
            profile.tier = "vip" if action == "vip_on" else "base"
            await session.commit()
        await render(call, session)


@router.callback_query(F.data == "webstats")
async def web_stats(call: CallbackQuery, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    async with sessionmaker() as session:
        total = await session.scalar(select(func.count(WebProfile.tg_id))) or 0
        dau = await session.scalar(select(func.count(WebProfile.tg_id)).where(WebProfile.last_seen_at >= day_ago)) or 0
        wau = await session.scalar(select(func.count(WebProfile.tg_id)).where(WebProfile.last_seen_at >= week_ago)) or 0
        vips = await session.scalar(select(func.count(WebProfile.tg_id)).where(WebProfile.tier == "vip")) or 0
        ids = await session.scalar(select(func.count(WebProfile.tg_id)).where(WebProfile.onewin_id.is_not(None))) or 0
        calcs = await session.scalar(select(func.count(HedgeCalc.id))) or 0
        calcs_week = await session.scalar(select(func.count(HedgeCalc.id)).where(HedgeCalc.created_at >= week_ago)) or 0
        bets = await session.scalar(select(func.count(TrackedBet.id))) or 0

    text = (
        "📱 <b>Мини-апп</b>\n\n"
        f"Открывали терминал: <b>{total}</b>\n"
        f"За сутки: <b>{dau}</b> · за неделю: <b>{wau}</b>\n"
        f"Прислали 1win ID: <b>{ids}</b> · VIP: <b>{vips}</b>\n"
        f"Расчётов хеджа: <b>{calcs}</b> (за неделю {calcs_week})\n"
        f"Ставок в трекерах: <b>{bets}</b>"
    )
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[back_button()]))
