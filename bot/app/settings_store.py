"""Настройки, которые редактируются из админки. Вносятся один раз — читают все боты."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

# Значения по умолчанию + человекочитаемые названия для админки.
# Плейсхолдеры в текстах: {name} {promo} {ref_link} {channel} {promo_title}
DEFAULTS: dict[str, tuple[str, str]] = {
    "ref_link": (
        "Глобальная реф-ссылка",
        "https://example.com/?ref=changeme",
    ),
    "greeting_template": (
        "Текст при заявке в канал",
        (
            "🎁 <b>Твой промокод: <code>{promo}</code></b>\n"
            "{promo_title}\n\n"
            "👉 Активировать: {ref_link}\n\n"
            "Просто скопируй код и вставь при регистрации."
        ),
    ),
    "retention_note": (
        "Приписка «не блокируй бота»",
        (
            "📅 Раз в неделю я присылаю новые промокоды и разборы матчей.\n"
            "Не отключай уведомления, чтобы не пропустить 🔔"
        ),
    ),
    "offers_header": (
        "Заголовок блока с другими каналами",
        "🔥 <b>Забери ещё промокоды</b> — просто подай заявку в каналы ниже:",
    ),
    "offer_button_prefix": (
        "Префикс кнопки канала",
        "🎁 ",
    ),
    "already_have_promo": (
        "Ответ, если промокод уже выдавался",
        "Ты уже получал промокод за этот канал 🙂 Загляни в закреплённые сообщения.",
    ),
    "start_text": (
        "Ответ на /start в рабочем боте",
        (
            "Привет, {name}! 👋\n\n"
            "Здесь раздают промокоды и разборы матчей.\n"
            "Подай заявку в каналы ниже — за каждую пришлю отдельный промокод."
        ),
    ),
    "weekly_enabled": ("Еженедельная рассылка включена (1/0)", "1"),
    "weekly_weekday": ("День недели рассылки (0=Пн … 6=Вс)", "4"),
    "weekly_hour": ("Час рассылки (0-23)", "18"),
    "weekly_text": (
        "Текст еженедельной рассылки",
        (
            "🔥 <b>Промокод недели: <code>{promo}</code></b>\n\n"
            "Разбор топовых матчей уже в канале — забегай.\n"
            "👉 {ref_link}"
        ),
    ),
    "weekly_button_text": ("Текст кнопки в рассылке", "🎰 Забрать бонус"),
    "send_rate_per_sec": ("Сообщений в секунду на одного бота", "20"),
    "hedge_free_per_week": ("Бесплатных расчётов хеджа в неделю", "1"),
    "webapp_button_text": ("Текст кнопки мини-аппа", "📊 Открыть терминал"),
    "vip_text": (
        "Текст окна VIP в мини-аппе",
        "Для безлимитного терминала подтвердите статус VIP: депозит от 200 000 ₽ на 1win.",
    ),
    "bookmaker_name": ("Название БК на кнопках мини-аппа", "1win"),
}


def default_value(key: str) -> str:
    return DEFAULTS.get(key, ("", ""))[1]


def label(key: str) -> str:
    return DEFAULTS.get(key, (key, ""))[0]


async def ensure_defaults(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(Setting.key))).all())
    for key, (_, value) in DEFAULTS.items():
        if key not in existing:
            session.add(Setting(key=key, value=value))
    await session.commit()


async def get(session: AsyncSession, key: str) -> str:
    row = await session.get(Setting, key)
    return row.value if row is not None else default_value(key)


async def get_int(session: AsyncSession, key: str, fallback: int = 0) -> int:
    try:
        return int((await get(session, key)).strip())
    except (TypeError, ValueError):
        return fallback


async def get_bool(session: AsyncSession, key: str) -> bool:
    return (await get(session, key)).strip() in {"1", "true", "True", "да", "yes"}


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    await session.commit()


async def all_values(session: AsyncSession) -> dict[str, str]:
    rows = (await session.scalars(select(Setting))).all()
    data = {key: value for key, (_, value) in DEFAULTS.items()}
    data.update({row.key: row.value for row in rows})
    return data
