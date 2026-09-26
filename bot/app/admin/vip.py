"""Раздел «VIP» и статистика мини-аппа."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.common import back_button, show
from app import settings_store
from app.models import HedgeCalc, PartnerEvent, TrackedBet, WebProfile

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

    deposits = dict((await session.execute(
        select(PartnerEvent.tg_id, func.sum(PartnerEvent.amount))
        .where(PartnerEvent.event == "deposit", PartnerEvent.tg_id.is_not(None))
        .group_by(PartnerEvent.tg_id))).all())
    threshold = await settings_store.get_int(session, "vip_deposit_threshold", 200000)

    lines = ["👑 <b>VIP мини-аппа</b>\n"]
    if threshold > 0:
        lines.append(f"Авто-VIP: при депозитах от <b>{threshold:,} ₽</b> по постбекам партнёрки.".replace(",", " "))
    lines.append("Ниже — кто прислал 1win ID. Проверь депозит и нажми, чтобы выдать VIP вручную.")
    rows: list[list[InlineKeyboardButton]] = []
    for p in waiting:
        dep = deposits.get(p.tg_id)
        dep_text = f" · деп {int(dep):,} ₽".replace(",", " ") if dep else ""
        rows.append([InlineKeyboardButton(text=f"✅ {_name(p)} · 1win {p.onewin_id}{dep_text}", callback_data=f"vip_on:{p.tg_id}")])
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
            if action == "vip_on":
                # в режиме одного бота админка и пользователь в одном боте — сообщение дойдёт
                try:
                    await call.bot.send_message(profile.tg_id, await settings_store.get(session, "vip_granted_text"))
                except Exception:  # noqa: BLE001
                    pass
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
        regs = await session.scalar(select(func.count(PartnerEvent.id)).where(PartnerEvent.event == "registration")) or 0
        deps = await session.scalar(select(func.count(PartnerEvent.id)).where(PartnerEvent.event == "deposit")) or 0
        dep_sum = await session.scalar(select(func.coalesce(func.sum(PartnerEvent.amount), 0.0)).where(PartnerEvent.event == "deposit")) or 0

    text = (
        "📱 <b>Мини-апп</b>\n\n"
        f"Открывали терминал: <b>{total}</b>\n"
        f"За сутки: <b>{dau}</b> · за неделю: <b>{wau}</b>\n"
        f"Прислали 1win ID: <b>{ids}</b> · VIP: <b>{vips}</b>\n"
        f"Расчётов хеджа: <b>{calcs}</b> (за неделю {calcs_week})\n"
        f"Ставок в трекерах: <b>{bets}</b>\n\n"
        f"🤝 <b>Партнёрка (постбеки)</b>\n"
        f"Регистраций: <b>{regs}</b> · депозитов: <b>{deps}</b> на <b>{int(dep_sum):,} ₽</b>".replace(",", " ")
    )
    from app.web import api as web_api

    provider = web_api.CURRENT_PROVIDER
    if provider is not None and getattr(provider, "remaining", None) is not None:
        text += f"\n\n⚽ API-Football: осталось запросов сегодня <b>{provider.remaining}</b>"
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=[back_button()]))
