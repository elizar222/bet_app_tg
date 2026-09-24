"""Демо-данные матчей.

Пока не подключены платные API (API-Football, The Odds API), мини-апп
работает на правдоподобных сгенерированных матчах: у команд есть сила атаки
и обороны, из неё модель считает вероятности, а «букмекер» выставляет кэфы
со своей маржой и небольшой ошибкой. Данные стабильны в течение дня.

Чтобы подключить реальные данные, достаточно написать провайдер с теми же
методами (list_matches, get_match, feed) и выбрать его в .env.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from app.web import model

LEAGUES: dict[str, list[tuple[str, str, float, float]]] = {
    # команда, короткое имя, атака, оборона (меньше = надёжнее)
    "АПЛ": [
        ("Манчестер Сити", "МСИ", 1.45, 0.75), ("Арсенал", "АРС", 1.35, 0.70),
        ("Ливерпуль", "ЛИВ", 1.40, 0.80), ("Челси", "ЧЕЛ", 1.20, 0.90),
        ("Тоттенхэм", "ТОТ", 1.20, 1.05), ("Манчестер Юнайтед", "МЮ", 1.05, 1.00),
        ("Астон Вилла", "АСТ", 1.10, 0.95), ("Ньюкасл", "НЬЮ", 1.10, 0.90),
    ],
    "Ла Лига": [
        ("Реал Мадрид", "РМА", 1.45, 0.75), ("Барселона", "БАР", 1.50, 0.85),
        ("Атлетико", "АТМ", 1.15, 0.75), ("Жирона", "ЖИР", 1.15, 1.00),
        ("Атлетик", "АТЛ", 1.05, 0.85), ("Реал Сосьедад", "РСО", 0.95, 0.90),
        ("Севилья", "СЕВ", 0.95, 1.05), ("Вильярреал", "ВИЛ", 1.05, 1.10),
    ],
    "Серия А": [
        ("Интер", "ИНТ", 1.35, 0.70), ("Наполи", "НАП", 1.20, 0.80),
        ("Милан", "МИЛ", 1.20, 0.90), ("Ювентус", "ЮВЕ", 1.05, 0.75),
        ("Аталанта", "АТА", 1.25, 0.95), ("Рома", "РОМ", 1.05, 0.90),
        ("Лацио", "ЛАЦ", 1.00, 0.95), ("Фиорентина", "ФИО", 1.00, 1.00),
    ],
    "Бундеслига": [
        ("Бавария", "БАВ", 1.60, 0.85), ("Байер", "БАЙ", 1.35, 0.80),
        ("Боруссия Д", "БВБ", 1.30, 1.00), ("РБ Лейпциг", "РБЛ", 1.25, 0.95),
        ("Штутгарт", "ШТУ", 1.20, 1.05), ("Айнтрахт", "АЙН", 1.10, 1.05),
        ("Вольфсбург", "ВОЛ", 0.95, 1.10), ("Фрайбург", "ФРА", 0.95, 1.00),
    ],
    "РПЛ": [
        ("Зенит", "ЗЕН", 1.35, 0.70), ("Краснодар", "КРА", 1.25, 0.80),
        ("Спартак", "СПА", 1.15, 0.95), ("ЦСКА", "ЦСК", 1.05, 0.85),
        ("Динамо", "ДИН", 1.15, 1.00), ("Локомотив", "ЛОК", 1.10, 1.05),
        ("Ростов", "РОС", 0.95, 1.10), ("Рубин", "РУБ", 0.85, 1.00),
    ],
}

LEAGUE_COUNTRY = {
    "АПЛ": "Англия", "Ла Лига": "Испания", "Серия А": "Италия",
    "Бундеслига": "Германия", "РПЛ": "Россия",
}

REFEREES = [
    "М. Оливер", "Э. Тейлор", "Х. Гиль Мансано", "Д. Орсато", "Ф. Цвайер",
    "С. Карасёв", "К. Левников", "А. Мелер", "С. Винчич", "Ш. Марчиняк",
]

POSITIONS = ["нап.", "п/з", "защ.", "вр."]
INJURY_REASONS = ["травма колена", "травма бедра", "дисквалификация", "болезнь", "травма голеностопа"]
MARGIN = 0.065  # маржа демо-букмекера


def _team(league: str, idx: int) -> dict:
    name, short, att, dfn = LEAGUES[league][idx]
    return {"name": name, "short": short, "attack": att, "defense": dfn}


def _lambdas(home: dict, away: dict) -> tuple[float, float]:
    return 1.45 * home["attack"] * away["defense"], 1.15 * away["attack"] * home["defense"]


def _book_odds(probs: list[float], rng: random.Random, noise: float = 0.12) -> list[float]:
    """Букмекер ошибается на несколько процентов и добавляет маржу."""

    skewed = [max(0.02, p * (1 + rng.uniform(-noise, noise))) for p in probs]
    total = sum(skewed)
    return [round(max(1.02, 1 / (p / total * (1 + MARGIN))), 2) for p in skewed]


def _result_letter(gf: int, ga: int) -> str:
    return "W" if gf > ga else "D" if gf == ga else "L"


def _sim_score(lam_h: float, lam_a: float, rng: random.Random) -> tuple[int, int]:
    def draw(lam: float) -> int:
        # простая выборка из Пуассона
        l, k, p = pow(2.718281828, -lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= l:
                return k
            k += 1

    return draw(lam_h), draw(lam_a)


class DemoProvider:
    name = "demo"

    def __init__(self, tz: timezone | None = None) -> None:
        self._cache_day: date | None = None
        self._matches: list[dict] = []
        self._tables: dict[str, list[dict]] = {}
        self.tz = tz

    # ── генерация ──────────────────────────────────────────────────────────
    def _ensure(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self._cache_day == today:
            return
        self._cache_day = today
        rng = random.Random(today.toordinal())
        self._tables = {lg: self._make_table(lg, rng) for lg in LEAGUES}
        self._matches = []
        now = datetime.now(timezone.utc)
        mid = 0
        for league in LEAGUES:
            order = list(range(len(LEAGUES[league])))
            rng.shuffle(order)
            for pair in range(3 if league != "РПЛ" else 2):
                h, a = order[pair * 2], order[pair * 2 + 1]
                mid += 1
                if mid in (2, 7):
                    kickoff = now - timedelta(minutes=rng.randint(25, 80))
                else:
                    kickoff = (now + timedelta(hours=rng.randint(1, 30))).replace(
                        minute=rng.choice([0, 15, 30, 45]), second=0, microsecond=0
                    )
                self._matches.append(self._make_match(mid, league, h, a, kickoff, now, rng))
        self._matches.sort(key=lambda m: (m["status"] != "live", m["kickoff"]))

    def _make_table(self, league: str, rng: random.Random) -> list[dict]:
        rows = []
        for i, (name, short, att, dfn) in enumerate(LEAGUES[league]):
            played = 12
            strength = att / dfn
            w = min(played, max(0, round(played * (0.18 + 0.32 * (strength - 0.8)) + rng.randint(-1, 1))))
            d = min(played - w, rng.randint(1, 4))
            lose = played - w - d
            gf = round(played * 1.35 * att + rng.randint(-3, 3))
            ga = round(played * 1.25 * dfn + rng.randint(-3, 3))
            rows.append({"team": name, "short": short, "p": played, "w": w, "d": d, "l": lose,
                         "gf": gf, "ga": ga, "pts": w * 3 + d})
        rows.sort(key=lambda r: (-r["pts"], -(r["gf"] - r["ga"])))
        for pos, row in enumerate(rows, start=1):
            row["pos"] = pos
        return rows

    def _form(self, team: dict, league: str, rng: random.Random, n: int = 10) -> list[dict]:
        others = [t for t in LEAGUES[league] if t[0] != team["name"]]
        out = []
        for i in range(n):
            opp = rng.choice(others)
            opp_t = {"name": opp[0], "attack": opp[2], "defense": opp[3]}
            is_home = i % 2 == 0
            lh, la = _lambdas(team, opp_t) if is_home else _lambdas(opp_t, team)
            gh, ga = _sim_score(lh, la, rng)
            gf, gag = (gh, ga) if is_home else (ga, gh)
            xg_for = max(0.1, (lh if is_home else la) * rng.uniform(0.7, 1.3))
            xg_against = max(0.1, (la if is_home else lh) * rng.uniform(0.7, 1.3))
            out.append({
                "opponent": opp[0], "home": is_home, "score": f"{gf}:{gag}",
                "result": _result_letter(gf, gag),
                "xg_for": round(xg_for, 2), "xg_against": round(xg_against, 2),
                "days_ago": (i + 1) * 7 - rng.randint(0, 3),
            })
        return out

    def _make_match(self, mid: int, league: str, hi: int, ai: int, kickoff: datetime,
                    now: datetime, rng: random.Random) -> dict:
        home, away = _team(league, hi), _team(league, ai)
        lam_h, lam_a = _lambdas(home, away)
        mk = model.markets(lam_h, lam_a)

        o1x2 = _book_odds([mk["home"], mk["draw"], mk["away"]], rng)
        o_tot = _book_odds([mk["over25"], 1 - mk["over25"]], rng, 0.05)
        o_btts = _book_odds([mk["btts"], 1 - mk["btts"]], rng, 0.05)

        # история кэфа за 24 часа: линия «приезжает» к текущему значению
        drift = rng.choice([-1, -1, 0, 1]) * rng.uniform(0.04, 0.16)
        history = []
        for step in range(25):
            k = 1 - step / 24
            wobble = rng.uniform(-0.015, 0.015)
            history.append({
                "h": 24 - step,
                "home": round(o1x2[0] * (1 - drift * k + wobble), 2),
                "draw": round(o1x2[1] * (1 + drift * 0.3 * k + wobble / 2), 2),
                "away": round(o1x2[2] * (1 + drift * k - wobble), 2),
            })
        history[-1].update({"home": o1x2[0], "draw": o1x2[1], "away": o1x2[2]})

        form_h = self._form(home, league, rng)
        form_a = self._form(away, league, rng)
        h2h = []
        for i in range(5):
            swap = i % 2 == 1
            lh, la = (_lambdas(home, away) if not swap else _lambdas(away, home))
            gh, ga = _sim_score(lh, la, rng)
            h2h.append({
                "home": away["name"] if swap else home["name"],
                "away": home["name"] if swap else away["name"],
                "score": f"{gh}:{ga}", "years_ago": i // 2,
                "season": f"{2025 - i // 2}/{str(26 - i // 2).zfill(2)}",
            })

        def avg(team: dict, base: float, spread: float) -> float:
            return round(base * (team["attack"] / team["defense"]) ** 0.5 + rng.uniform(-spread, spread), 1)

        injuries = []
        for side, team in (("home", home), ("away", away)):
            for _ in range(rng.randint(0, 3)):
                injuries.append({
                    "team": side, "player": f"{rng.choice('АБВГДЕКЛМНПРСТ')}. {rng.choice(['Иванов','Родригес','Смит','Мюллер','Росси','Силва','Кейн','Петров','Гарсия','Фернандес','Томпсон','Коваль'])}",
                    "position": rng.choice(POSITIONS), "reason": rng.choice(INJURY_REASONS),
                    "key": rng.random() < 0.3,
                })

        status = "live" if kickoff <= now else "scheduled"
        match = {
            "id": mid,
            "league": league,
            "country": LEAGUE_COUNTRY[league],
            "kickoff": kickoff.isoformat(),
            "status": status,
            "home": {"name": home["name"], "short": home["short"]},
            "away": {"name": away["name"], "short": away["short"]},
            "odds": {
                "home": o1x2[0], "draw": o1x2[1], "away": o1x2[2],
                "over25": o_tot[0], "under25": o_tot[1],
                "btts_yes": o_btts[0], "btts_no": o_btts[1],
            },
            "odds_history": history,
            "model": mk,
            "form": {"home": form_h, "away": form_a},
            "h2h": h2h,
            "averages": {
                "home": {"goals": round(lam_h, 2), "corners": avg(home, 5.4, 0.8),
                         "cards": round(rng.uniform(1.4, 2.6), 1), "shots": avg(home, 13, 2),
                         "possession": round(50 + (home["attack"] - away["attack"]) * 25 + rng.uniform(-4, 4))},
                "away": {"goals": round(lam_a, 2), "corners": avg(away, 4.6, 0.8),
                         "cards": round(rng.uniform(1.5, 2.8), 1), "shots": avg(away, 11, 2)},
            },
            "referee": {
                "name": rng.choice(REFEREES), "matches": rng.randint(8, 16),
                "yellow": round(rng.uniform(3.2, 5.6), 1), "red": round(rng.uniform(0.05, 0.3), 2),
                "penalties": round(rng.uniform(0.15, 0.45), 2),
            },
            "injuries": injuries,
        }
        match["averages"]["away"]["possession"] = 100 - match["averages"]["home"]["possession"]
        if status == "live":
            match["live"] = self._make_live(match, lam_h, lam_a, now, kickoff, rng)
        return match

    def _make_live(self, match: dict, lam_h: float, lam_a: float, now: datetime,
                   kickoff: datetime, rng: random.Random) -> dict:
        minute = min(90, int((now - kickoff).total_seconds() // 60))
        frac = minute / 90
        gh, ga = _sim_score(lam_h * frac, lam_a * frac, rng)
        momentum = []
        level = 0.0
        for m in range(1, minute + 1):
            level = level * 0.8 + rng.uniform(-40, 40) + (lam_h - lam_a) * 8
            momentum.append({"m": m, "v": round(max(-100, min(100, level)))})
        events = []
        for side, goals in (("home", gh), ("away", ga)):
            for _ in range(goals):
                events.append({"m": rng.randint(3, max(4, minute)), "type": "goal", "team": side})
        for _ in range(rng.randint(1, 4)):
            events.append({"m": rng.randint(5, max(6, minute)), "type": "yellow",
                           "team": rng.choice(["home", "away"])})
        events.sort(key=lambda e: e["m"])

        # живые кэфы: пересчёт модели на оставшееся время с учётом счёта
        rest = max(0.02, 1 - frac)
        mk = model.markets(lam_h * rest, lam_a * rest)
        # сдвигаем распределение на текущий счёт
        p_home = p_draw = 0.0
        matrix = model.score_matrix(lam_h * rest, lam_a * rest)
        for i, row in enumerate(matrix):
            for j, p in enumerate(row):
                fh, fa = gh + i, ga + j
                if fh > fa:
                    p_home += p
                elif fh == fa:
                    p_draw += p
        total = sum(sum(r) for r in matrix)
        p_home, p_draw = p_home / total, p_draw / total
        p_away = max(0.01, 1 - p_home - p_draw)
        live_odds = _book_odds([max(0.01, p_home), max(0.01, p_draw), p_away], rng, 0.03)

        shots_h = round(minute / 90 * 13 * lam_h / 1.4 + rng.randint(0, 3))
        shots_a = round(minute / 90 * 11 * lam_a / 1.2 + rng.randint(0, 3))
        return {
            "minute": minute,
            "score": f"{gh}:{ga}",
            "momentum": momentum,
            "events": events,
            "odds": {"home": live_odds[0], "draw": live_odds[1], "away": live_odds[2]},
            "probs": {"home": p_home, "draw": p_draw, "away": p_away},
            "stats": [
                {"name": "Владение, %", "home": match["averages"]["home"]["possession"],
                 "away": match["averages"]["away"]["possession"]},
                {"name": "xG", "home": round(lam_h * frac * rng.uniform(0.7, 1.3), 2),
                 "away": round(lam_a * frac * rng.uniform(0.7, 1.3), 2)},
                {"name": "Удары", "home": shots_h, "away": shots_a},
                {"name": "В створ", "home": max(gh, round(shots_h * 0.38)), "away": max(ga, round(shots_a * 0.36))},
                {"name": "Угловые", "home": round(minute / 90 * 5.5 + rng.randint(-1, 2)),
                 "away": round(minute / 90 * 4.5 + rng.randint(-1, 2))},
                {"name": "Жёлтые", "home": sum(1 for e in events if e["type"] == "yellow" and e["team"] == "home"),
                 "away": sum(1 for e in events if e["type"] == "yellow" and e["team"] == "away")},
            ],
            "remaining_goals": {"home": round(lam_h * rest, 2), "away": round(lam_a * rest, 2),
                                "over_more": round(1 - mk["matrix"][0][0], 3)},
        }

    # ── публичные методы ─────────────────────────────────────────────────────
    def list_matches(self) -> list[dict]:
        self._ensure()
        return [self._summary(m) for m in self._matches]

    def get_match(self, match_id: int) -> dict | None:
        self._ensure()
        for m in self._matches:
            if m["id"] == match_id:
                full = dict(m)
                full["analysis"] = self._analysis(m)
                full["table"] = self._tables[m["league"]]
                return full
        return None

    def _summary(self, m: dict) -> dict:
        a = self._analysis(m)
        best = max(a["value"], key=lambda v: v["edge"])
        out = {k: m[k] for k in ("id", "league", "country", "kickoff", "status", "home", "away", "odds")}
        out["probs"] = a["fair"]
        out["best_value"] = best if best["edge"] > 0.03 else None
        out["odds_move"] = a["odds_move"]
        if m["status"] == "live":
            out["live"] = {"minute": m["live"]["minute"], "score": m["live"]["score"], "odds": m["live"]["odds"]}
        return out

    def _analysis(self, m: dict) -> dict:
        o = m["odds"]
        fair, margin = model.fair_probs([o["home"], o["draw"], o["away"]])
        mk = m["model"]
        labels = [("home", "П1"), ("draw", "X"), ("away", "П2")]
        value = [
            {"market": "1X2", "pick": lbl, "key": key, "odds": o[key], "model": mk[key],
             "fair": fair[i], "edge": model.edge(mk[key], o[key])}
            for i, (key, lbl) in enumerate(labels)
        ]
        value += [
            {"market": "Тотал", "pick": "ТБ 2.5", "key": "over25", "odds": o["over25"], "model": mk["over25"],
             "fair": model.fair_probs([o["over25"], o["under25"]])[0][0], "edge": model.edge(mk["over25"], o["over25"])},
            {"market": "Тотал", "pick": "ТМ 2.5", "key": "under25", "odds": o["under25"], "model": 1 - mk["over25"],
             "fair": model.fair_probs([o["over25"], o["under25"]])[0][1], "edge": model.edge(1 - mk["over25"], o["under25"])},
            {"market": "Обе забьют", "pick": "Да", "key": "btts_yes", "odds": o["btts_yes"], "model": mk["btts"],
             "fair": model.fair_probs([o["btts_yes"], o["btts_no"]])[0][0], "edge": model.edge(mk["btts"], o["btts_yes"])},
            {"market": "Обе забьют", "pick": "Нет", "key": "btts_no", "odds": o["btts_no"], "model": 1 - mk["btts"],
             "fair": model.fair_probs([o["btts_yes"], o["btts_no"]])[0][1], "edge": model.edge(1 - mk["btts"], o["btts_no"])},
        ]
        first, last = m["odds_history"][0], m["odds_history"][-1]
        moves = {k: (last[k] - first[k]) / first[k] for k in ("home", "draw", "away")}
        key = min(moves, key=lambda k: moves[k])
        return {
            "fair": {"home": fair[0], "draw": fair[1], "away": fair[2]},
            "margin": margin,
            "value": value,
            "odds_move": {"key": key, "pick": dict(labels)[key], "from": first[key], "to": last[key],
                          "change": moves[key]},
        }

    def feed(self) -> dict:
        self._ensure()
        values, drops, candidates = [], [], []
        for m in self._matches:
            a = self._analysis(m)
            title = f'{m["home"]["name"]} — {m["away"]["name"]}'
            for v in a["value"]:
                if v["edge"] > 0.03 and m["status"] != "live":
                    values.append({"match_id": m["id"], "title": title, "league": m["league"],
                                   "kickoff": m["kickoff"], **v})
                if m["status"] != "live" and 1.25 <= v["odds"] <= 1.9 and v["model"] >= 0.55:
                    candidates.append({"match_id": m["id"], "title": title, "league": m["league"],
                                       "kickoff": m["kickoff"], **v})
            mv = a["odds_move"]
            if mv["change"] <= -0.06:
                drops.append({"match_id": m["id"], "title": title, "league": m["league"],
                              "kickoff": m["kickoff"], "status": m["status"], **mv})
        values.sort(key=lambda v: -v["edge"])
        drops.sort(key=lambda d: d["change"])
        # экспресс дня: по одному событию с матча, самые вероятные
        candidates.sort(key=lambda v: -v["model"])
        express, used = [], set()
        for c in candidates:
            if c["match_id"] in used:
                continue
            express.append(c)
            used.add(c["match_id"])
            if len(express) == 4:
                break
        total_odds = 1.0
        total_prob = 1.0
        for e in express:
            total_odds *= e["odds"]
            total_prob *= e["model"]

        return {
            "value": values[:6],
            "drops": drops[:6],
            "express": {"picks": express, "odds": round(total_odds, 2), "prob": total_prob},
            "tipster": self._tipster(),
        }

    def _tipster(self) -> dict:
        """Статистика прогнозов канала за 30 дней (демо)."""

        rng = random.Random(self._cache_day.toordinal() * 7 if self._cache_day else 1)
        tips, bank = [], 0.0
        curve = []
        for day in range(30):
            odds = round(rng.uniform(1.55, 2.4), 2)
            won = rng.random() < 1 / odds + 0.06
            profit = (odds - 1) if won else -1
            bank += profit
            tips.append({"odds": odds, "won": won})
            curve.append(round(bank, 2))
        wins = sum(1 for t in tips if t["won"])
        return {
            "count": len(tips), "wins": wins, "win_rate": wins / len(tips),
            "roi": bank / len(tips), "profit_units": round(bank, 2),
            "avg_odds": round(sum(t["odds"] for t in tips) / len(tips), 2),
            "curve": curve, "last": [t["won"] for t in tips[-10:]],
        }
