"""Отправка сообщений с лимитом скорости и обработкой блокировок.

Telegram режет ботов за всплески — поэтому у каждого бота свой троттлер,
а на 429 мы честно ждём retry_after, а не долбим повторно.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup

log = logging.getLogger(__name__)


class SendResult:
    OK = "ok"
    BLOCKED = "blocked"  # юзер заблокировал бота / чат недоступен
    FAILED = "failed"


@dataclass
class _Throttle:
    rate: float
    _last: float = 0.0
    _lock: asyncio.Lock | None = None

    async def wait(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            interval = 1.0 / max(self.rate, 0.1)
            now = time.monotonic()
            delay = self._last + interval - now
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            self._last = now


class Sender:
    def __init__(self, rate_per_sec: float = 20.0) -> None:
        self.rate = rate_per_sec
        self._throttles: dict[int, _Throttle] = {}

    def _throttle(self, bot: Bot) -> _Throttle:
        if bot.id not in self._throttles:
            self._throttles[bot.id] = _Throttle(rate=self.rate)
        return self._throttles[bot.id]

    async def send(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        *,
        attempts: int = 3,
    ) -> str:
        for attempt in range(1, attempts + 1):
            await self._throttle(bot).wait()
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                return SendResult.OK
            except TelegramRetryAfter as exc:
                log.warning("429 от Telegram, ждём %s c (bot=%s)", exc.retry_after, bot.id)
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError as exc:
                # 403 бывает трёх видов, и лечатся они по-разному:
                #   blocked by the user      — человек заблокировал бота
                #   can't initiate conversation — у этого бота нет права писать первым
                #                                 (он не админ в канале, куда пришла заявка)
                #   user is deactivated      — аккаунт удалён
                reason = str(exc).lower()
                if "initiate conversation" in reason:
                    log.error(
                        "403: бот %s не может писать первым юзеру %s. "
                        "Проверь, что этот бот — админ во всех каналах.",
                        bot.id,
                        chat_id,
                    )
                return SendResult.BLOCKED
            except TelegramBadRequest as exc:
                message = str(exc).lower()
                if "chat not found" in message or "user is deactivated" in message:
                    return SendResult.BLOCKED
                log.error("BadRequest при отправке chat_id=%s: %s", chat_id, exc)
                return SendResult.FAILED
            except Exception as exc:  # noqa: BLE001 — сеть, таймауты и прочее
                log.error("Ошибка отправки chat_id=%s (попытка %s): %s", chat_id, attempt, exc)
                await asyncio.sleep(2 * attempt)
        return SendResult.FAILED


sender = Sender()
