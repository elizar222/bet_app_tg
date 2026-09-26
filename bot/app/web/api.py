"""HTTP API мини-аппа и раздача интерфейса.

Запускается в том же процессе, что и боты (см. run.py), и работает с той же
базой: промокоды, каналы и тексты из админки сразу видны в мини-аппе.
"""

from __future__ import annotations

import inspect
import json
from urllib.parse import parse_qsl
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import settings_store
from app.config import Config
from app.models import Channel, HedgeCalc, JoinRequest, PartnerEvent, Promo, TrackedBet, User, WebProfile
from app.services.messaging import personal_link
from app.web import hedge
from app.web.auth import TgUser, validate_init_data
from app.web.demo import DemoProvider

CURRENT_PROVIDER = None  # для статистики в админке

STATIC_DIR = Path(__file__).resolve().parent / "static"
WEEK = timedelta(days=7)


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite отдаёт даты без таймзоны — считаем их UTC."""

    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── схемы запросов ───────────────────────────────────────────────────────────
class HedgeIn(BaseModel):
    payout: float = Field(gt=0)
    stake: float = Field(gt=0)
    odds: float = Field(gt=1)
    mode: str = "equal"
    ratio: float = 0.6
    cashout: float | None = None


class BetIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    sport: str = "Футбол"
    league: str | None = None
    market: str = "Исход"
    stake: float = Field(gt=0)
    odds: float = Field(gt=1)


class BetSettle(BaseModel):
    status: str  # won | lost | void | hedged | pending
    payout: float | None = None
    hedge_saved: float | None = None


class OnewinIn(BaseModel):
    onewin_id: str = Field(min_length=3, max_length=64)


class BankIn(BaseModel):
    start_bank: float = Field(ge=0)


# ── статистика ставок ────────────────────────────────────────────────────────
def bet_profit(bet: TrackedBet) -> float:
    if bet.status == "won":
        return bet.stake * (bet.odds - 1)
    if bet.status == "lost":
        return -bet.stake
    if bet.status == "hedged":
        return (bet.payout or 0) - bet.stake
    return 0.0


def bet_stats(bets: list[TrackedBet], start_bank: float) -> dict:
    settled = sorted(
        (b for b in bets if b.status in {"won", "lost", "void", "hedged"}),
        key=lambda b: _utc(b.settled_at or b.placed_at),
    )
    pending = [b for b in bets if b.status == "pending"]
    now = datetime.now(timezone.utc)

    def period(days: int | None) -> dict:
        rows = [b for b in settled if days is None or _utc(b.settled_at or b.placed_at) >= now - timedelta(days=days)]
        staked = sum(b.stake for b in rows if b.status != "void")
        profit = sum(bet_profit(b) for b in rows)
        decided = [b for b in rows if b.status in {"won", "lost"}]
        wins = sum(1 for b in decided if b.status == "won")
        return {
            "bets": len(rows), "staked": staked, "profit": profit,
            "roi": profit / staked if staked else 0.0,
            "win_rate": wins / len(decided) if decided else 0.0,
        }

    curve, bank = [], start_bank
    curve.append({"t": None, "v": bank})
    for b in settled:
        bank += bet_profit(b)
        curve.append({"t": _utc(b.settled_at or b.placed_at).isoformat(), "v": round(bank, 2)})

    def breakdown(attr: str) -> list[dict]:
        groups: dict[str, list[TrackedBet]] = defaultdict(list)
        for b in settled:
            groups[getattr(b, attr) or "Другое"].append(b)
        out = []
        for name, rows in groups.items():
            decided = [b for b in rows if b.status in {"won", "lost"}]
            staked = sum(b.stake for b in rows if b.status != "void")
            profit = sum(bet_profit(b) for b in rows)
            out.append({
                "name": name, "bets": len(rows),
                "win_rate": sum(1 for b in decided if b.status == "won") / len(decided) if decided else 0.0,
                "profit": profit, "roi": profit / staked if staked else 0.0,
            })
        return sorted(out, key=lambda r: -r["bets"])

    streak_now, streak_kind = 0, None
    best_win_streak = best_lose_streak = run_w = run_l = 0
    for b in settled:
        if b.status == "won":
            run_w, run_l = run_w + 1, 0
        elif b.status == "lost":
            run_l, run_w = run_l + 1, 0
        best_win_streak, best_lose_streak = max(best_win_streak, run_w), max(best_lose_streak, run_l)
    for b in reversed(settled):
        if b.status not in {"won", "lost"}:
            continue
        if streak_kind is None:
            streak_kind = b.status
        if b.status != streak_kind:
            break
        streak_now += 1

    profits = [(bet_profit(b), b) for b in settled]
    best = max(profits, key=lambda p: p[0], default=None)
    worst = min(profits, key=lambda p: p[0], default=None)
    decided_all = [b for b in settled if b.status in {"won", "lost"}]

    return {
        "bank": bank,
        "start_bank": start_bank,
        "pending_count": len(pending),
        "pending_stake": sum(b.stake for b in pending),
        "periods": {"7d": period(7), "30d": period(30), "all": period(None)},
        "curve": curve,
        "by_sport": breakdown("sport"),
        "by_league": breakdown("league"),
        "by_market": breakdown("market"),
        "avg_odds": sum(b.odds for b in decided_all) / len(decided_all) if decided_all else 0.0,
        "best": {"title": best[1].title, "profit": best[0]} if best and best[0] > 0 else None,
        "worst": {"title": worst[1].title, "profit": worst[0]} if worst and worst[0] < 0 else None,
        "streak": {"now": streak_now, "kind": streak_kind, "best_win": best_win_streak, "best_lose": best_lose_streak},
        "hedge_saved": sum(b.hedge_saved or 0 for b in settled if b.status == "hedged"),
        "hedged_count": sum(1 for b in settled if b.status == "hedged"),
    }


def bet_dict(b: TrackedBet) -> dict:
    return {
        "id": b.id, "title": b.title, "sport": b.sport, "league": b.league, "market": b.market,
        "stake": b.stake, "odds": b.odds, "status": b.status, "payout": b.payout,
        "hedge_saved": b.hedge_saved, "profit": bet_profit(b),
        "placed_at": _utc(b.placed_at).isoformat(),
        "settled_at": _utc(b.settled_at).isoformat() if b.settled_at else None,
    }


# ── приложение ───────────────────────────────────────────────────────────────
USER_KEYS = ("sub1", "subid", "sub_id", "sub", "click_id", "clickid", "tg_id", "user")
EVENT_KEYS = ("event", "action", "type", "goal", "status")
AMOUNT_KEYS = ("amount", "sum", "deposit", "payout", "value")
DEPOSIT_WORDS = ("dep", "ftd", "first_deposit", "firstdep", "deposit", "redep", "purchase", "sale")
REG_WORDS = ("reg", "registration", "signup", "lead")


def _pick(params: dict, keys: tuple[str, ...]) -> str | None:
    lower = {k.lower(): v for k, v in params.items()}
    for k in keys:
        if lower.get(k) not in (None, ""):
            return str(lower[k])
    return None


def build_app(cfg: Config, sessionmaker: async_sessionmaker[AsyncSession], notify=None) -> FastAPI:
    app = FastAPI(title="Hedge Terminal", docs_url=None, redoc_url=None, openapi_url=None)
    if cfg.apifootball_key:
        from app.web.apifootball import ApiFootballProvider

        oddspapi = None
        if cfg.oddspapi_key:
            from app.web.oddspapi import OddsPapiClient

            oddspapi = OddsPapiClient(cfg.oddspapi_key, sessionmaker)
        provider = ApiFootballProvider(cfg.apifootball_key, sessionmaker, leagues=list(cfg.apifootball_leagues) or None,
                                       plan=cfg.apifootball_plan, tz=cfg.timezone, oddspapi=oddspapi)
    else:
        provider = DemoProvider()
    app.state.provider = provider
    global CURRENT_PROVIDER
    CURRENT_PROVIDER = provider

    async def run(value):
        """Демо-провайдер синхронный, API — асинхронный: поддерживаем оба."""

        return await value if inspect.isawaitable(value) else value
    tokens = list(cfg.bot_tokens)

    async def get_session():
        async with sessionmaker() as session:
            yield session

    async def current_user(x_init_data: str = Header(default="")) -> TgUser:
        user = validate_init_data(x_init_data, tokens)
        if user is not None:
            return user
        if cfg.web_dev_user_id and not x_init_data:
            return TgUser(id=cfg.web_dev_user_id, first_name="Разработчик")
        raise HTTPException(status_code=401, detail="Откройте терминал из Telegram")

    async def profile_for(session: AsyncSession, user: TgUser) -> WebProfile:
        profile = await session.get(WebProfile, user.id)
        if profile is None:
            profile = WebProfile(tg_id=user.id)
            session.add(profile)
        profile.first_name = user.first_name or profile.first_name
        profile.username = user.username or profile.username
        profile.last_seen_at = datetime.now(timezone.utc)
        await session.commit()
        return profile

    async def hedge_quota(session: AsyncSession, profile: WebProfile) -> dict:
        limit = await settings_store.get_int(session, "hedge_free_per_week", 1)
        since = datetime.now(timezone.utc) - WEEK
        rows = (
            await session.scalars(
                select(HedgeCalc.created_at)
                .where(HedgeCalc.tg_id == profile.tg_id, HedgeCalc.created_at >= since)
                .order_by(HedgeCalc.created_at)
            )
        ).all()
        vip = profile.tier == "vip"
        return {
            "vip": vip,
            "limit": None if vip else limit,
            "used": len(rows),
            "remaining": None if vip else max(0, limit - len(rows)),
            "resets_at": (_utc(rows[0]) + WEEK).isoformat() if rows and not vip else None,
        }

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/me")
    async def me(user: TgUser = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
        profile = await profile_for(session, user)
        return {
            "id": user.id,
            "first_name": profile.first_name or "друг",
            "tier": profile.tier,
            "onewin_id": profile.onewin_id,
            "start_bank": profile.start_bank,
            "hedge": await hedge_quota(session, profile),
            "bookmaker": await settings_store.get(session, "bookmaker_name"),
            "ref_link": personal_link(await settings_store.get(session, "ref_link"), user.id),
            "vip_text": await settings_store.get(session, "vip_text"),
            "data_source": provider.name,
        }

    @app.post("/api/me/onewin")
    async def set_onewin(body: OnewinIn, user: TgUser = Depends(current_user),
                         session: AsyncSession = Depends(get_session)) -> dict:
        profile = await profile_for(session, user)
        profile.onewin_id = body.onewin_id.strip()
        await session.commit()
        return {"ok": True, "onewin_id": profile.onewin_id}

    @app.post("/api/me/bank")
    async def set_bank(body: BankIn, user: TgUser = Depends(current_user),
                       session: AsyncSession = Depends(get_session)) -> dict:
        profile = await profile_for(session, user)
        profile.start_bank = body.start_bank
        await session.commit()
        return {"ok": True}

    @app.get("/api/home")
    async def home(user: TgUser = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
        profile = await profile_for(session, user)
        bets = (await session.scalars(select(TrackedBet).where(TrackedBet.tg_id == user.id))).all()
        stats = bet_stats(list(bets), profile.start_bank)
        pending = sorted((b for b in bets if b.status == "pending"), key=lambda b: -b.stake * b.odds)
        matches = await run(provider.list_matches())
        return {
            "feed": await run(provider.feed()),
            "summary": {k: stats[k] for k in ("bank", "start_bank", "pending_count", "periods", "curve")},
            "pending": [bet_dict(b) for b in pending[:3]],
            "live": [m for m in matches if m["status"] == "live"],
            "top": [m for m in matches if m["status"] != "live"][:4],
        }

    @app.get("/api/matches")
    async def matches(_: TgUser = Depends(current_user)) -> dict:
        return {"matches": await run(provider.list_matches())}

    @app.get("/api/matches/{match_id}")
    async def match(match_id: int, _: TgUser = Depends(current_user)) -> dict:
        data = await run(provider.get_match(match_id))
        if data is None:
            raise HTTPException(404, "Матч не найден")
        return data

    @app.post("/api/hedge")
    async def calc_hedge(body: HedgeIn, user: TgUser = Depends(current_user),
                         session: AsyncSession = Depends(get_session)) -> JSONResponse:
        profile = await profile_for(session, user)
        quota = await hedge_quota(session, profile)
        if not quota["vip"] and quota["remaining"] == 0:
            return JSONResponse({"gate": True, "quota": quota,
                                 "text": await settings_store.get(session, "vip_text")}, status_code=402)
        if not quota["vip"] and body.mode != "equal":
            return JSONResponse({"gate": True, "quota": quota, "mode_locked": True,
                                 "text": "Режимы «Без риска» и «Свой %» доступны в VIP."}, status_code=402)
        result = hedge.calculate(payout=body.payout, stake=body.stake, odds=body.odds,
                                 mode=body.mode, ratio=body.ratio, cashout=body.cashout)
        session.add(HedgeCalc(tg_id=user.id, mode=body.mode, payout=body.payout, stake=body.stake,
                              odds=body.odds, cashout=body.cashout, hedge_amount=result.hedge_amount))
        await session.commit()
        return JSONResponse({"result": result.as_dict(), "quota": await hedge_quota(session, profile)})

    @app.get("/api/bets")
    async def bets(user: TgUser = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
        profile = await profile_for(session, user)
        rows = (
            await session.scalars(
                select(TrackedBet).where(TrackedBet.tg_id == user.id).order_by(TrackedBet.placed_at.desc())
            )
        ).all()
        return {"bets": [bet_dict(b) for b in rows], "stats": bet_stats(list(rows), profile.start_bank)}

    @app.post("/api/bets")
    async def add_bet(body: BetIn, user: TgUser = Depends(current_user),
                      session: AsyncSession = Depends(get_session)) -> dict:
        count = await session.scalar(select(func.count(TrackedBet.id)).where(TrackedBet.tg_id == user.id)) or 0
        if count >= 2000:
            raise HTTPException(400, "Слишком много ставок в трекере")
        bet = TrackedBet(tg_id=user.id, **body.model_dump())
        session.add(bet)
        await session.commit()
        await session.refresh(bet)
        return bet_dict(bet)

    async def own_bet(session: AsyncSession, user: TgUser, bet_id: int) -> TrackedBet:
        bet = await session.get(TrackedBet, bet_id)
        if bet is None or bet.tg_id != user.id:
            raise HTTPException(404, "Ставка не найдена")
        return bet

    @app.patch("/api/bets/{bet_id}")
    async def settle_bet(bet_id: int, body: BetSettle, user: TgUser = Depends(current_user),
                         session: AsyncSession = Depends(get_session)) -> dict:
        if body.status not in {"won", "lost", "void", "hedged", "pending"}:
            raise HTTPException(400, "Неизвестный статус")
        bet = await own_bet(session, user, bet_id)
        bet.status = body.status
        bet.payout = body.payout if body.status == "hedged" else None
        bet.hedge_saved = body.hedge_saved if body.status == "hedged" else None
        bet.settled_at = None if body.status == "pending" else datetime.now(timezone.utc)
        await session.commit()
        return bet_dict(bet)

    @app.delete("/api/bets/{bet_id}")
    async def delete_bet(bet_id: int, user: TgUser = Depends(current_user),
                         session: AsyncSession = Depends(get_session)) -> dict:
        bet = await own_bet(session, user, bet_id)
        await session.delete(bet)
        await session.commit()
        return {"ok": True}

    @app.get("/api/bonuses")
    async def bonuses(user: TgUser = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
        global_ref = await settings_store.get(session, "ref_link")
        promos = (await session.scalars(select(Promo).where(Promo.enabled.is_(True)).order_by(Promo.id.desc()))).all()
        bot_user = await session.scalar(select(User).where(User.tg_id == user.id))
        done: set[int] = set()
        if bot_user is not None:
            done = set((await session.scalars(
                select(JoinRequest.channel_id).where(JoinRequest.user_id == bot_user.id))).all())
        channels = (await session.scalars(
            select(Channel).where(Channel.enabled.is_(True), Channel.offer_in_menu.is_(True),
                                  Channel.invite_link.is_not(None))
            .order_by(Channel.sort_order, Channel.id))).all()
        return {
            "promos": [{"id": p.id, "title": p.title, "code": p.code, "description": p.description,
                        "link": personal_link(p.ref_link or global_ref, user.id)} for p in promos],
            "channels": [{"id": c.id, "title": c.title, "link": c.invite_link, "done": c.id in done,
                          "promo_title": c.promo.title if c.promo else None} for c in channels],
            "ref_link": personal_link(global_ref, user.id),
        }

    @app.api_route("/postback/{secret}", methods=["GET", "POST"])
    async def postback(secret: str, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
        """Постбек партнёрки 1win: регистрация или депозит игрока.

        В кабинете партнёрки укажите URL вида
        https://ваш-домен/postback/<POSTBACK_SECRET>?sub1={sub1}&event={event}&amount={amount}
        а в реф-ссылке передавайте sub1={tg_id} — бот подставит Telegram ID.
        """

        if not cfg.postback_secret or secret != cfg.postback_secret:
            raise HTTPException(404, "Not found")
        params = dict(request.query_params)
        if request.method == "POST":
            raw_body = (await request.body()).decode("utf-8", "ignore").strip()
            if raw_body.startswith("{"):
                try:
                    body = json.loads(raw_body)
                    if isinstance(body, dict):
                        params.update({k: str(v) for k, v in body.items()})
                except ValueError:
                    pass
            elif raw_body:
                params.update(dict(parse_qsl(raw_body, keep_blank_values=True)))

        raw_user = _pick(params, USER_KEYS)
        tg_id = int(raw_user) if raw_user and raw_user.lstrip("-").isdigit() else None
        event_raw = (_pick(params, EVENT_KEYS) or "").lower()
        amount = 0.0
        try:
            amount = float((_pick(params, AMOUNT_KEYS) or "0").replace(",", "."))
        except ValueError:
            pass
        event = ("deposit" if any(w in event_raw for w in DEPOSIT_WORDS) or (amount > 0 and not event_raw)
                 else "registration" if any(w in event_raw for w in REG_WORDS) else event_raw or "unknown")

        session.add(PartnerEvent(tg_id=tg_id, event=event, amount=amount, currency=params.get("currency"),
                                 player_id=params.get("player_id") or params.get("user_id"),
                                 raw=json.dumps(params, ensure_ascii=False)[:4000]))
        await session.commit()

        granted = False
        if tg_id and event == "deposit":
            threshold = await settings_store.get_int(session, "vip_deposit_threshold", 200000)
            total = await session.scalar(
                select(func.coalesce(func.sum(PartnerEvent.amount), 0.0))
                .where(PartnerEvent.tg_id == tg_id, PartnerEvent.event == "deposit")) or 0.0
            profile = await session.get(WebProfile, tg_id)
            if profile is None:
                profile = WebProfile(tg_id=tg_id)
                session.add(profile)
            if threshold > 0 and total >= threshold and profile.tier != "vip":
                profile.tier = "vip"
                granted = True
            await session.commit()
            if granted and notify is not None:
                try:
                    await notify(tg_id, await settings_store.get(session, "vip_granted_text"))
                except Exception:  # noqa: BLE001
                    pass
        return {"ok": True, "event": event, "vip_granted": granted}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "data_source": provider.name}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return app
