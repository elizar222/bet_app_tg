"""Точка входа: поднимает все рабочие боты, админ-бота и планировщик в одном процессе."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import MenuButtonWebApp, WebAppInfo
from sqlalchemy import select

from app.admin.bot import build_admin_dispatcher
from app.config import BASE_DIR, Config, load_config
from app.db import close_db, init_db, session_factory
from app.models import BotAccount
from app.scheduler import build_scheduler
from app.services.sender import sender
from app import settings_store
from app.settings_store import ensure_defaults, get_int
from app.workers.handlers import router as worker_router

log = logging.getLogger("run")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(BASE_DIR / "data" / "bot.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def make_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def sync_bot_accounts(bots: list[Bot]) -> dict[int, int]:
    """Записывает ботов из .env в БД и возвращает {tg_bot_id: id в БД}."""

    mapping: dict[int, int] = {}
    async with session_factory()() as session:
        for order, bot in enumerate(bots):
            me = await bot.get_me()
            account = await session.scalar(select(BotAccount).where(BotAccount.tg_bot_id == me.id))
            if account is None:
                account = BotAccount(
                    tg_bot_id=me.id,
                    token=bot.token,
                    username=me.username,
                    sort_order=order,
                )
                session.add(account)
            else:
                account.token = bot.token
                account.username = me.username
                account.sort_order = order
            await session.commit()
            await session.refresh(account)
            mapping[me.id] = account.id
            log.info("Рабочий бот @%s подключён", me.username)
    return mapping


async def setup_menu_button(bots: list[Bot], cfg: Config, text: str) -> None:
    """Кнопка мини-аппа слева от поля ввода в каждом рабочем боте."""

    if not cfg.webapp_url.startswith("https://"):
        if cfg.webapp_url:
            log.warning("WEBAPP_URL должен начинаться с https:// — кнопка мини-аппа не установлена")
        return
    for bot in bots:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text=text[:64] or "Терминал", web_app=WebAppInfo(url=cfg.webapp_url))
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Не удалось поставить кнопку мини-аппа боту %s: %s", bot.id, exc)


async def serve_web(cfg: Config) -> None:
    import uvicorn

    from app.web.api import build_app

    app = build_app(cfg, session_factory())
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.web_host, port=cfg.web_port, log_level="warning", access_log=False)
    )
    server.install_signal_handlers = lambda: None  # Ctrl+C обрабатывает run.py
    log.info("Мини-апп: http://%s:%s  (публичный адрес: %s)", cfg.web_host, cfg.web_port, cfg.webapp_url or "не задан")
    await server.serve()


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)

    await init_db(cfg.database_url)
    async with session_factory()() as session:
        await ensure_defaults(session)
        sender.rate = float(await get_int(session, "send_rate_per_sec", 20) or 20)

    worker_bots = [make_bot(token) for token in cfg.bot_tokens]
    admin_bot = make_bot(cfg.admin_bot_token)

    bot_map = await sync_bot_accounts(worker_bots)

    worker_dp = Dispatcher(storage=MemoryStorage())
    worker_dp.include_router(worker_router)
    worker_dp.workflow_data.update(sessionmaker=session_factory(), bot_map=bot_map, webapp_url=cfg.webapp_url)

    admin_dp = build_admin_dispatcher(cfg.admin_ids)
    admin_dp.workflow_data.update(sessionmaker=session_factory(), worker_bots=worker_bots)

    scheduler = build_scheduler(session_factory(), worker_bots, cfg.timezone)
    scheduler.start()

    async with session_factory()() as session:
        button_text = await settings_store.get(session, "webapp_button_text")
    await setup_menu_button(worker_bots, cfg, button_text)

    log.info("Запущено: %s рабочих ботов + админка", len(worker_bots))

    tasks = []
    if cfg.web_enabled:
        tasks.append(serve_web(cfg))

    try:
        await asyncio.gather(
            *tasks,
            worker_dp.start_polling(
                *worker_bots,
                allowed_updates=["message", "callback_query", "chat_join_request", "my_chat_member"],
                handle_signals=False,
            ),
            admin_dp.start_polling(
                admin_bot,
                allowed_updates=["message", "callback_query"],
                handle_signals=False,
            ),
        )
    finally:
        scheduler.shutdown(wait=False)
        for bot in [*worker_bots, admin_bot]:
            await bot.session.close()
        await close_db()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановлено вручную")
