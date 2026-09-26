"""Реальные матчи из API-Football (api-sports.io).

Бесплатный тариф — 100 запросов в сутки, поэтому всё кэшируется в базе и
переживает перезапуск. Запросы делятся на обязательные (расписание, Live) и
дополнительные (форма, травмы, таблица) — дополнительные не делаются, когда
лимит на исходе. На платном тарифе (APIFOOTBALL_PLAN=pro) кэш короче.

Каждое обновление кэфов сохраняется снимком — из снимков строится график
движения линии. Если API недоступен, провайдер отдаёт то, что есть в кэше.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ApiCache, OddsSnapshot
from app.web import analytics, model

log = logging.getLogger("apifootball")

BASE_URL = "https://v3.football.api-sports.io"

LEAGUES_RU = {
    2: ("Лига чемпионов", "Европа"), 3: ("Лига Европы", "Европа"), 848: ("Лига конференций", "Европа"),
    39: ("АПЛ", "Англия"), 140: ("Ла Лига", "Испания"), 135: ("Серия А", "Италия"),
    78: ("Бундеслига", "Германия"), 61: ("Лига 1", "Франция"), 235: ("РПЛ", "Россия"),
    94: ("Примейра", "Португалия"), 88: ("Эредивизи", "Нидерланды"), 203: ("Суперлига", "Турция"),
}
DEFAULT_LEAGUES = [2, 39, 140, 135, 78, 61, 235]
# Предпочтительные букмекеры API-Football: Bet365, 1xBet, Pinnacle, Marathonbet, 10Bet
PREFERRED_BOOKMAKERS = [8, 11, 4, 2, 1]

LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}
DONE_STATUSES = {"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"}

# Время жизни кэша, секунды: (free, pro)
TTL = {
    "fixtures": (3 * 3600, 900),
    "live": (240, 60),
    "odds_today": (4 * 3600, 1200),
    "odds_later": (12 * 3600, 3 * 3600),
    "standings": (12 * 3600, 3 * 3600),
    "predictions": (12 * 3600, 6 * 3600),
    "injuries": (12 * 3600, 3 * 3600),
    "team_last": (12 * 3600, 6 * 3600),
    "fixture_live": (240, 60),
}
RESERVE = 20  # столько запросов держим в запасе под обязательные


def _f(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _short(name: str) -> str:
    letters = [w[0] for w in name.replace("-", " ").split() if w and w[0].isalpha()]
    if len(letters) >= 3:
        return "".join(letters[:3]).upper()
    return name.replace(" ", "")[:3].upper()


class ApiFootballProvider:
    name = "api-football"

    def __init__(self, key: str, sessionmaker: async_sessionmaker[AsyncSession], *,
                 leagues: list[int] | None = None, plan: str = "free", tz: str = "Europe/Moscow") -> None:
        self.key = key
        self.sm = sessionmaker
        self.leagues = leagues or DEFAULT_LEAGUES
        self.pro = plan.lower() != "free"
        self.tz = ZoneInfo(tz)
        self.remaining: int | None = None
        self.blocked_until: datetime | None = None
        self._mem: dict[str, tuple[datetime, object]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._http: aiohttp.ClientSession | None = None
        self._model_memo: dict[tuple, dict] = {}
        self._loaded: tuple[datetime, list[dict]] | None = None
        self._load_lock = asyncio.Lock()

    # ── HTTP и кэш ─────────────────────────────────────────────────────────
    def _ttl(self, kind: str) -> int:
        free, pro = TTL[kind]
        return pro if self.pro else free

    async def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(
                headers={"x-apisports-key": self.key}, timeout=aiohttp.ClientTimeout(total=20)
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.closed:
            await self._http.close()

    async def _cached(self, key: str) -> tuple[datetime, object] | None:
        if key in self._mem:
            return self._mem[key]
        async with self.sm() as s:
            row = await s.get(ApiCache, key)
        if row is None:
            return None
        ts = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
        item = (ts, json.loads(row.payload))
        self._mem[key] = item
        return item

    async def _store(self, key: str, data: object) -> None:
        now = datetime.now(timezone.utc)
        self._mem[key] = (now, data)
        async with self.sm() as s:
            row = await s.get(ApiCache, key)
            if row is None:
                s.add(ApiCache(key=key, payload=json.dumps(data), fetched_at=now))
            else:
                row.payload, row.fetched_at = json.dumps(data), now
            await s.commit()

    async def get(self, path: str, params: dict, kind: str, *, optional: bool = False,
                  cache_only: bool = False) -> list:
        """Запрос с кэшем. Возвращает поле response или [] / устаревший кэш при ошибке."""

        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = await self._cached(key)
            if cache_only:
                return cached[1] if cached else []  # type: ignore[return-value]
            now = datetime.now(timezone.utc)
            if cached and (now - cached[0]).total_seconds() < self._ttl(kind):
                return cached[1]  # type: ignore[return-value]
            if self.blocked_until and now < self.blocked_until:
                return cached[1] if cached else []  # type: ignore[return-value]
            if optional and self.remaining is not None and self.remaining <= RESERVE:
                return cached[1] if cached else []  # type: ignore[return-value]
            try:
                http = await self._session()
                async with http.get(BASE_URL + path, params=params) as resp:
                    rem = resp.headers.get("x-ratelimit-requests-remaining")
                    if rem is not None and rem.isdigit():
                        self.remaining = int(rem)
                    body = await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001
                log.warning("API-Football %s: %s", path, exc)
                return cached[1] if cached else []  # type: ignore[return-value]

            errors = body.get("errors") if isinstance(body, dict) else None
            if errors:
                log.warning("API-Football %s %s: %s", path, params, errors)
                text = json.dumps(errors, ensure_ascii=False).lower()
                if "limit" in text or "suspend" in text or "token" in text or "key" in text:
                    # лимит исчерпан или ключ неверный — не долбим API до конца суток / 10 минут
                    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
                    self.blocked_until = tomorrow if "limit" in text else now + timedelta(minutes=10)
                return cached[1] if cached else []  # type: ignore[return-value]
            data = body.get("response", []) if isinstance(body, dict) else []
            await self._store(key, data)
            return data

    # ── сборка матчей ──────────────────────────────────────────────────────
    def _local_date(self, days: int = 0) -> str:
        return (datetime.now(self.tz) + timedelta(days=days)).strftime("%Y-%m-%d")

    async def _fixtures(self) -> list[dict]:
        out: dict[int, dict] = {}
        for day in (0, 1):
            rows = await self.get("/fixtures", {"date": self._local_date(day), "timezone": "UTC"}, "fixtures")
            for r in rows:
                if r.get("league", {}).get("id") in self.leagues:
                    out[r["fixture"]["id"]] = r
        # Live-счёт свежее, чем расписание: если сейчас что-то идёт — обновляем
        now = datetime.now(timezone.utc)
        maybe_live = any(
            r["fixture"]["status"]["short"] in LIVE_STATUSES
            or (r["fixture"]["status"]["short"] == "NS"
                and now - timedelta(minutes=5) <= datetime.fromisoformat(r["fixture"]["date"]) <= now)
            for r in out.values()
        )
        if maybe_live:
            live = await self.get("/fixtures", {"live": "-".join(map(str, self.leagues))}, "live")
            for r in live:
                out[r["fixture"]["id"]] = r
        return list(out.values())

    async def _odds_for(self, rows: list[dict]) -> dict[int, dict]:
        """Кэфы до матча: одним запросом на лигу и день."""

        pairs = {(r["league"]["id"], r["league"]["season"], r["fixture"]["date"][:10]) for r in rows
                 if r["fixture"]["status"]["short"] == "NS"}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result: dict[int, dict] = {}
        for league, season, day in sorted(pairs):
            kind = "odds_today" if day == today else "odds_later"
            params = {"league": league, "season": season, "date": day}
            data = await self.get("/odds", params, kind)
            for item in data:
                fid = item.get("fixture", {}).get("id")
                odds = self._parse_odds(item.get("bookmakers") or [])
                if fid and odds:
                    result[fid] = odds
        return result

    @staticmethod
    def _parse_odds(bookmakers: list[dict]) -> dict | None:
        if not bookmakers:
            return None
        by_id = {b.get("id"): b for b in bookmakers}
        ordered = [by_id[i] for i in PREFERRED_BOOKMAKERS if i in by_id] + [
            b for b in bookmakers if b.get("id") not in PREFERRED_BOOKMAKERS]
        odds: dict = {}
        best: dict = {}
        for bm in ordered:
            for bet in bm.get("bets") or []:
                name = (bet.get("name") or "").lower()
                vals = {str(v.get("value")): _f(v.get("odd")) for v in bet.get("values") or []}
                found = {}
                if name in {"match winner", "fulltime result", "1x2"}:
                    found = {"home": vals.get("Home"), "draw": vals.get("Draw"), "away": vals.get("Away")}
                elif name in {"goals over/under", "over/under"}:
                    found = {"over25": vals.get("Over 2.5"), "under25": vals.get("Under 2.5")}
                elif name in {"both teams score", "both teams to score"}:
                    found = {"btts_yes": vals.get("Yes"), "btts_no": vals.get("No")}
                for k, v in found.items():
                    if not v or v <= 1:
                        continue
                    odds.setdefault(k, v)  # основной букмекер — первый в списке
                    if v > best.get(k, (0, ""))[0]:
                        best[k] = (v, bm.get("name", ""))
        if not all(odds.get(k) for k in ("home", "draw", "away")):
            return None
        odds["best"] = {k: {"odds": v, "bookmaker": n} for k, (v, n) in best.items()}
        odds["bookmaker"] = ordered[0].get("name")
        return odds

    async def _snapshot(self, odds_by_fixture: dict[int, dict]) -> dict[int, list[dict]]:
        """Сохраняем снимок, если кэф изменился, и возвращаем историю за 24 ч."""

        since = datetime.now(timezone.utc) - timedelta(hours=36)
        history: dict[int, list[dict]] = {}
        async with self.sm() as s:
            rows = (await s.scalars(
                select(OddsSnapshot).where(OddsSnapshot.fixture_id.in_(list(odds_by_fixture) or [0]),
                                           OddsSnapshot.taken_at >= since).order_by(OddsSnapshot.taken_at)
            )).all()
            for r in rows:
                history.setdefault(r.fixture_id, []).append(r)
            now = datetime.now(timezone.utc)
            for fid, o in odds_by_fixture.items():
                last = history.get(fid, [None])[-1]
                if last is None or (last.home, last.draw, last.away) != (o["home"], o["draw"], o["away"]):
                    snap = OddsSnapshot(fixture_id=fid, home=o["home"], draw=o["draw"], away=o["away"], taken_at=now)
                    s.add(snap)
                    history.setdefault(fid, []).append(snap)
            await s.commit()
        out = {}
        now = datetime.now(timezone.utc)
        for fid, snaps in history.items():
            pts = []
            for sn in snaps:
                ts = sn.taken_at if sn.taken_at.tzinfo else sn.taken_at.replace(tzinfo=timezone.utc)
                pts.append({"h": round((now - ts).total_seconds() / 3600, 1),
                            "home": sn.home, "draw": sn.draw, "away": sn.away})
            out[fid] = pts
        return out

    def _base(self, r: dict) -> dict:
        fx, lg, teams, goals = r["fixture"], r["league"], r["teams"], r.get("goals") or {}
        st = fx["status"]["short"]
        status = "live" if st in LIVE_STATUSES else "finished" if st in DONE_STATUSES else "scheduled"
        league, country = LEAGUES_RU.get(lg["id"], (lg.get("name"), lg.get("country")))
        m = {
            "id": fx["id"], "league": league, "country": country, "league_id": lg["id"], "season": lg.get("season"),
            "kickoff": fx["date"], "status": status,
            "home": {"id": teams["home"]["id"], "name": teams["home"]["name"], "short": _short(teams["home"]["name"]),
                     "logo": teams["home"].get("logo")},
            "away": {"id": teams["away"]["id"], "name": teams["away"]["name"], "short": _short(teams["away"]["name"]),
                     "logo": teams["away"].get("logo")},
            "referee_name": (fx.get("referee") or "").split(",")[0] or None,
            "odds": {}, "odds_history": [], "model": None,
        }
        if status != "scheduled":
            m["live"] = {"minute": fx["status"].get("elapsed") or 0, "score": f'{goals.get("home") or 0}:{goals.get("away") or 0}',
                         "status": st}
            m["score"] = m["live"]["score"]
        return m

    async def _load(self) -> list[dict]:
        async with self._load_lock:
            now = datetime.now(timezone.utc)
            if self._loaded and (now - self._loaded[0]).total_seconds() < 60:
                return self._loaded[1]
            data = await self._load_fresh()
            self._loaded = (now, data)
            return data

    async def _load_fresh(self) -> list[dict]:
        rows = await self._fixtures()
        odds = await self._odds_for(rows)
        history = await self._snapshot(odds) if odds else {}
        matches = []
        for r in rows:
            m = self._base(r)
            if m["status"] == "finished":
                continue
            o = odds.get(m["id"])
            if o:
                m["odds"] = {k: v for k, v in o.items() if k not in {"best", "bookmaker"}}
                m["best_odds"] = o.get("best")
                m["bookmaker"] = o.get("bookmaker")
                m["odds_history"] = history.get(m["id"], [])
                # модель без статистики команд: берём честные вероятности линии как опору,
                # λ подбираем по тоталу — детальная модель считается на экране матча
                # на платном тарифе прогноз по статистике есть у всех матчей,
                # на бесплатном — только у тех, что уже открывали
                pred = await self.get("/predictions", {"fixture": m["id"]}, "predictions",
                                      optional=True, cache_only=not self.pro or m["status"] != "scheduled")
                m["model"] = self._model_from_prediction(pred[0] if pred else None) or self._model_from_odds(m["odds"])
            matches.append(m)
        matches.sort(key=lambda m: (m["status"] != "live", m["kickoff"]))
        return matches

    @staticmethod
    def _model_from_prediction(pred: dict | None) -> dict | None:
        """Модель по статистике сезона: средние голы дома/в гостях."""

        if not pred:
            return None
        try:
            th, ta = pred["teams"]["home"], pred["teams"]["away"]
            h_for = _f(th["league"]["goals"]["for"]["average"]["home"])
            h_ag = _f(th["league"]["goals"]["against"]["average"]["home"])
            a_for = _f(ta["league"]["goals"]["for"]["average"]["away"])
            a_ag = _f(ta["league"]["goals"]["against"]["average"]["away"])
        except (KeyError, TypeError):
            return None
        if h_for + a_ag <= 0 or a_for + h_ag <= 0:
            return None
        return model.markets(max(0.2, (h_for + a_ag) / 2), max(0.2, (a_for + h_ag) / 2))

    def _model_from_odds(self, o: dict) -> dict | None:
        """Грубая модель из линии: λ, при которых Пуассон повторяет рынок."""

        if not (o.get("home") and o.get("draw") and o.get("away")):
            return None
        memo_key = (o["home"], o["draw"], o["away"], o.get("over25"), o.get("under25"))
        if memo_key in self._model_memo:
            return self._model_memo[memo_key]
        fair, _ = model.fair_probs([o["home"], o["draw"], o["away"]])
        over = model.fair_probs([o["over25"], o["under25"]])[0][0] if o.get("over25") and o.get("under25") else 0.52
        best, best_err = (1.4, 1.1), 9.0
        for i in range(8, 36):
            for j in range(4, 30):
                lh, la = i / 10, j / 10
                mk = model.markets(lh, la)
                err = (mk["home"] - fair[0]) ** 2 + (mk["away"] - fair[2]) ** 2 + (mk["over25"] - over) ** 2
                if err < best_err:
                    best, best_err = (lh, la), err
        self._model_memo[memo_key] = model.markets(*best)
        return self._model_memo[memo_key]

    # ── публичный интерфейс (как у DemoProvider) ─────────────────────────
    async def list_matches(self) -> list[dict]:
        return [analytics.summary(m) for m in await self._load()]

    async def feed(self) -> dict:
        return analytics.feed(await self._load(), None)

    async def get_match(self, match_id: int) -> dict | None:
        matches = await self._load()
        m = next((x for x in matches if x["id"] == match_id), None)
        if m is None:
            rows = await self.get("/fixtures", {"id": match_id}, "fixtures")
            if not rows:
                return None
            m = self._base(rows[0])
        await self._enrich(m)
        m["analysis"] = analytics.analysis(m)
        return m

    async def _enrich(self, m: dict) -> None:
        fid, home_id, away_id = m["id"], m["home"]["id"], m["away"]["id"]
        pred_rows, inj_rows, table_rows = await asyncio.gather(
            self.get("/predictions", {"fixture": fid}, "predictions", optional=True),
            self.get("/injuries", {"fixture": fid}, "injuries", optional=True),
            self.get("/standings", {"league": m["league_id"], "season": m["season"]}, "standings", optional=True),
        )
        pred = pred_rows[0] if pred_rows else None

        # модель по статистике сезона
        if pred:
            m["model"] = self._model_from_prediction(pred) or m.get("model")
            th, ta = pred["teams"]["home"], pred["teams"]["away"]
            m["h2h"] = [
                {"home": g["teams"]["home"]["name"], "away": g["teams"]["away"]["name"],
                 "score": f'{g["goals"]["home"]}:{g["goals"]["away"]}',
                 "season": str(g["league"].get("season", ""))}
                for g in (pred.get("h2h") or [])[:6] if g.get("goals", {}).get("home") is not None
            ]
            try:
                m["averages"] = {
                side: {
                    "goals": _f(t["league"]["goals"]["for"]["average"]["total"]),
                    "conceded": _f(t["league"]["goals"]["against"]["average"]["total"]),
                    "clean_sheets": (t["league"].get("clean_sheet") or {}).get("total"),
                    "failed_to_score": (t["league"].get("failed_to_score") or {}).get("total"),
                }
                for side, t in (("home", th), ("away", ta))
                }
            except (KeyError, TypeError):
                m["averages"] = None
            m["advice"] = (pred.get("predictions") or {}).get("advice")
        if m.get("model") is None and m.get("odds"):
            m["model"] = self._model_from_odds(m["odds"])

        # форма: последние 10 матчей каждой команды
        forms = {}
        for side, team_id in (("home", home_id), ("away", away_id)):
            rows = await self.get("/fixtures", {"team": team_id, "last": 10}, "team_last", optional=True)
            games = []
            for g in rows:
                gh, ga = g["goals"]["home"], g["goals"]["away"]
                if gh is None:
                    continue
                is_home = g["teams"]["home"]["id"] == team_id
                gf, gag = (gh, ga) if is_home else (ga, gh)
                opp = g["teams"]["away" if is_home else "home"]["name"]
                games.append({"opponent": opp, "home": is_home, "score": f"{gf}:{gag}",
                              "result": "W" if gf > gag else "D" if gf == gag else "L",
                              "goals_for": gf, "goals_against": gag, "date": g["fixture"]["date"]})
            games.sort(key=lambda x: x["date"], reverse=True)
            forms[side] = games
        m["form"] = forms

        m["injuries"] = [
            {"team": "home" if i["team"]["id"] == home_id else "away", "player": i["player"]["name"],
             "position": "", "reason": i["player"].get("reason") or i["player"].get("type") or "", "key": False}
            for i in inj_rows if i.get("team", {}).get("id") in (home_id, away_id)
        ]
        if table_rows:
            try:
                groups = table_rows[0]["league"]["standings"]
                group = next((g for g in groups if any(r["team"]["id"] in (home_id, away_id) for r in g)), groups[0])
                m["table"] = [
                    {"pos": r["rank"], "team": r["team"]["name"], "p": r["all"]["played"], "w": r["all"]["win"],
                     "d": r["all"]["draw"], "l": r["all"]["lose"], "gf": r["all"]["goals"]["for"],
                     "ga": r["all"]["goals"]["against"], "pts": r["points"]}
                    for r in group
                ]
            except (KeyError, IndexError, TypeError):
                m["table"] = []
        m["referee"] = {"name": m["referee_name"]} if m.get("referee_name") else None

        if m["status"] == "live":
            await self._enrich_live(m)

    async def _enrich_live(self, m: dict) -> None:
        fid = m["id"]
        stats_rows, events_rows, odds_rows = await asyncio.gather(
            self.get("/fixtures/statistics", {"fixture": fid}, "fixture_live"),
            self.get("/fixtures/events", {"fixture": fid}, "fixture_live"),
            self.get("/odds/live", {"fixture": fid}, "fixture_live", optional=True),
        )
        names = {
            "Ball Possession": "Владение, %", "expected_goals": "xG", "Total Shots": "Удары",
            "Shots on Goal": "В створ", "Corner Kicks": "Угловые", "Yellow Cards": "Жёлтые",
            "Fouls": "Фолы", "Offsides": "Офсайды",
        }
        by_team = {s["team"]["id"]: {x["type"]: x["value"] for x in s.get("statistics") or []} for s in stats_rows}
        hs, as_ = by_team.get(m["home"]["id"], {}), by_team.get(m["away"]["id"], {})
        stats = []
        for api_name, ru in names.items():
            if api_name in hs or api_name in as_:
                stats.append({"name": ru, "home": _f(hs.get(api_name)), "away": _f(as_.get(api_name))})
        live = m.setdefault("live", {})
        live["stats"] = stats
        live["events"] = [
            {"m": (e.get("time") or {}).get("elapsed") or 0,
             "type": "goal" if e.get("type") == "Goal" else "yellow" if e.get("detail") == "Yellow Card"
             else "red" if e.get("detail") == "Red Card" else "other",
             "team": "home" if e.get("team", {}).get("id") == m["home"]["id"] else "away",
             "player": (e.get("player") or {}).get("name")}
            for e in events_rows if e.get("type") in {"Goal", "Card"}
        ]
        live["momentum"] = None  # в API-Football нет графика давления
        lo = None
        if odds_rows:
            for bet in odds_rows[0].get("odds") or []:
                if (bet.get("name") or "").lower() in {"fulltime result", "match winner", "1x2"}:
                    vals = {str(v.get("value")).lower(): _f(v.get("odd")) for v in bet.get("values") or []}
                    if vals.get("home") and vals.get("draw") and vals.get("away"):
                        lo = {"home": vals["home"], "draw": vals["draw"], "away": vals["away"]}
                    break
        live["odds"] = lo or m.get("odds") or None
        if lo:
            fair, _ = model.fair_probs([lo["home"], lo["draw"], lo["away"]])
            live["probs"] = {"home": fair[0], "draw": fair[1], "away": fair[2]}
        else:
            live["probs"] = None

    async def status(self) -> dict:
        """Для проверки ключа: сколько запросов осталось сегодня."""

        http = await self._session()
        async with http.get(BASE_URL + "/status") as resp:
            return await resp.json(content_type=None)
