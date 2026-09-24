"""Схема БД. Одна база на все боты — конфиг вносится один раз."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class BotAccount(Base):
    """Рабочий бот. Токены приходят из .env и синхронизируются сюда при старте."""

    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_bot_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="bot")


class Promo(Base):
    """Промокод + (опционально) своя реф-ссылка. Если ссылки нет — берётся глобальная."""

    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    code: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    ref_link: Mapped[str | None] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Channel(Base):
    """Канал, в котором боты — админы и ловят заявки на вступление.

    approve_mode:
        weekly  — заявки копятся, одобряются пачкой раз в неделю (основной канал)
        never   — заявки не одобряем никогда (второстепенные каналы)
        instant — одобряем сразу
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    invite_link: Mapped[str | None] = mapped_column(String(512))

    role: Mapped[str] = mapped_column(String(16), default="extra")  # main | extra
    approve_mode: Mapped[str] = mapped_column(String(16), default="never")
    approve_weekday: Mapped[int] = mapped_column(Integer, default=0)  # 0=Пн
    approve_hour: Mapped[int] = mapped_column(Integer, default=12)

    promo_id: Mapped[int | None] = mapped_column(ForeignKey("promos.id", ondelete="SET NULL"))
    message_template: Mapped[str | None] = mapped_column(Text)

    offer_in_menu: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    promo: Mapped[Promo | None] = relationship(lazy="selectin")


class User(Base):
    """Пользователь закреплён за одним ботом навсегда — чтобы не дублировать сообщения."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    dm_chat_id: Mapped[int] = mapped_column(BigInteger)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id"), index=True)

    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))

    source_channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL")
    )
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    started_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    bot: Mapped[BotAccount] = relationship(back_populates="users", lazy="selectin")


class JoinRequest(Base):
    """Заявка в канал. Одна запись на пару (юзер, канал)."""

    __tablename__ = "join_requests"
    __table_args__ = (UniqueConstraint("user_id", "channel_id", name="uq_join_user_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    promo_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    """Key-value для текстов, глобальной реф-ссылки и параметров рассылки."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    button_text: Mapped[str | None] = mapped_column(String(128))
    button_url: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    kind: Mapped[str] = mapped_column(String(16), default="manual")  # manual | weekly
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
