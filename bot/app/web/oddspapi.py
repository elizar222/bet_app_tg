"""Кэфы из OddsPapi (oddspapi.io) — линия Pinnacle, самого точного букмекера.

Бесплатно — 250 запросов в месяц, поэтому:
  • один запрос /odds-by-tournaments отдаёт кэфы на все ближайшие матчи турнира;
  • турниры с матчами в ближайшие дни обновляются раз в сутки, остальные — раз в 3 дня;
  • названия команд (в ответе с кэфами только ID) берутся из /fixtures и хранятся месяц;
  • счётчик запросов за месяц хранится в базе, при приближении к лимиту новые не делаются.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ApiCache

log = logging.getLogger("oddspapi")

BASE_URL = "https://api.oddspapi.io/v4"
MONTHLY_LIMIT = 250
MONTHLY_RESERVE = 10

# ID лиги API-Football → ID турнира OddsPapi
TOURNAMENTS = {2: 7, 39: 17, 140: 8, 135: 23, 78: 35, 61: 34, 235: 203}

MARKET_1X2 = "101"
OUT_1X2 = {"101": "home", "102": "draw", "103": "away"}

_STRIP = re.compile(r"\b(fc|afc|cf|sc|ac|as|ssc|fk|pfc|cd|ud|rc|rcd|sv|vfb|vfl|tsg|bv|bsc|1\.|club|de|calcio)\b")


def norm(name: str) -> str:
    n = name.lower().replace("&", " and ")
    n = re.sub(r"[^a-z0-9а-яё ]", " ", n)
    n = _STRIP.sub(" ", n)
    return " ".join(n.split())


def parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def similar(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 0.95
    return difflib.SequenceMatcher(None, a, b).ratio()


class OddsPapiClient:
    def __init__(self, key: str, sessionmaker: async_sessionmaker[AsyncSession], bookmaker: str = "pinnacle") -> None:
        self.key = key
        self.sm = sessionmaker
        self.bookmaker = bookmaker
        self._http: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self.used_this_month: int | None = None

    async def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        return self._http

    # ── кэш и месячный счётчик ─────────────────────────────────────────────
    async def _read(self, key: str):
        async with self.sm() as s:
            row = await s.get(ApiCache, key)
        if row is None:
            return None
        ts = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
        return ts, json.loads(row.payload)

    async def _write(self, key: str, data) -> None:
        now = datetime.now(timezone.utc)
        async with self.sm() as s:
            row = await s.get(ApiCache, key)
            if row is None:
                s.add(ApiCache(key=key, payload=json.dumps(data), fetched_at=now))
            else:
                row.payload, row.fetched_at = json.dumps(data), now
            await s.commit()

    def _month_key(self) -> str:
        return "oddspapi:used:" + datetime.now(timezone.utc).strftime("%Y-%m")

    async def _spend(self) -> bool:
        item = await self._read(self._month_key())
        used = int(item[1]) if item else 0
        self.used_this_month = used
        if used >= MONTHLY_LIMIT - MONTHLY_RESERVE:
            return False
        await self._write(self._month_key(), used + 1)
        self.used_this_month = used + 1
        return True

    async def _get(self, path: str, params: dict, ttl: int):
        key = "oddspapi:" + path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        async with self._lock:
            cached = await self._read(key)
            if cached and (datetime.now(timezone.utc) - cached[0]).total_seconds() < ttl:
                return cached[1]
            if not await self._spend():
                log.warning("OddsPapi: месячный лимит почти исчерпан — берём кэш")
                return cached[1] if cached else None
            try:
                http = await self._session()
                async with http.get(BASE_URL + path, params={**params, "apiKey": self.key}) as r:
                    body = await r.json(content_type=None)
                    if r.status != 200:
                        log.warning("OddsPapi %s: HTTP %s %s", path, r.status, str(body)[:200])
                        return cached[1] if cached else None
            except Exception as exc:  # noqa: BLE001
                log.warning("OddsPapi %s: %s", path, exc)
                return cached[1] if cached else None
            await self._write(key, body)
            return body

    # ── данные ──────────────────────────────────────────────────────────────
    async def participants(self, tournament_id: int) -> dict[int, str]:
        """ID команды → название. Берётся из списка матчей турнира, хранится месяц."""

        data = await self._get("/fixtures", {"tournamentId": tournament_id}, ttl=30 * 86400)
        names: dict[int, str] = {}
        for f in data or []:
            if isinstance(f, dict):
                for side in ("1", "2"):
                    pid, name = f.get(f"participant{side}Id"), f.get(f"participant{side}Name")
                    if pid and name:
                        names[int(pid)] = name
        return names

    async def tournament_odds(self, tournament_id: int, active: bool) -> list[dict]:
        """Ближайшие матчи турнира с кэфами 1X2 и тоталом 2.5 (если есть)."""

        data = await self._get(
            "/odds-by-tournaments",
            {"bookmaker": self.bookmaker, "tournamentIds": tournament_id, "oddsFormat": "decimal"},
            ttl=86400 if active else 3 * 86400,
        )
        if not isinstance(data, list):
            return []
        names = await self.participants(tournament_id)
        out = []
        for f in data:
            odds = self._parse(f)
            if not odds:
                continue
            out.append({
                "fixture_id": f.get("fixtureId"),
                "start": f.get("startTime"),
                "home": names.get(f.get("participant1Id"), ""),
                "away": names.get(f.get("participant2Id"), ""),
                "odds": odds,
                "url": ((f.get("bookmakerOdds") or {}).get(self.bookmaker) or {}).get("fixturePath"),
            })
        return out

    def _parse(self, fixture: dict) -> dict | None:
        book = (fixture.get("bookmakerOdds") or {}).get(self.bookmaker) or {}
        markets = book.get("markets") or {}
        odds: dict = {}

        def price(outcome: dict) -> tuple[float, str, bool] | None:
            p = (outcome.get("players") or {}).get("0") or {}
            if not p.get("active", True) or not p.get("price"):
                return None
            return float(p["price"]), str(p.get("bookmakerOutcomeId") or ""), bool(p.get("mainLine"))

        m1x2 = markets.get(MARKET_1X2)
        if m1x2 and m1x2.get("marketActive", True):
            for oid, outcome in (m1x2.get("outcomes") or {}).items():
                pr = price(outcome)
                if pr and oid in OUT_1X2:
                    odds[OUT_1X2[oid]] = pr[0]
        if not all(odds.get(k) for k in ("home", "draw", "away")):
            return None

        # тотал 2.5: ищем среди рынков «totals» исход «2.5/over» и «2.5/under»
        for market in markets.values():
            if not str(market.get("bookmakerMarketId", "")).endswith("totals"):
                continue
            found = {}
            for outcome in (market.get("outcomes") or {}).values():
                pr = price(outcome)
                if pr and pr[1] in ("2.5/over", "2.5/under"):
                    found["over25" if pr[1].endswith("over") else "under25"] = pr[0]
            if len(found) == 2:
                odds.update(found)
                break
        return odds

    @staticmethod
    def match(fixtures: list[dict], rows: list[dict]) -> tuple[dict[int, dict], list[dict]]:
        """Сопоставляет матчи API-Football со строками OddsPapi по времени и названиям.

        Возвращает ({id матча: строка OddsPapi}, строки OddsPapi без пары).
        """

        paired: dict[int, dict] = {}
        used: set[str] = set()
        for f in fixtures:
            ko = datetime.fromisoformat(f["kickoff"])
            best, best_score = None, 0.0
            for r in rows:
                start = parse_time(r.get("start"))
                if start is None or abs((start - ko).total_seconds()) > 3 * 3600:
                    continue
                score = similar(f["home"]["name"], r["home"]) + similar(f["away"]["name"], r["away"])
                if score > best_score:
                    best, best_score = r, score
            if best and best_score >= 1.3:
                paired[f["id"]] = best
                used.add(best["fixture_id"])
        return paired, [r for r in rows if r["fixture_id"] not in used]

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()
