"""Общая аналитика поверх матчей любого источника (демо или API).

Матч — словарь с полями odds (1X2, тоталы, «обе забьют»), model (из model.markets)
и odds_history. Отсюда считаются честные вероятности, перевес, движение линии
и лента главной: value дня, падения кэфов, экспресс дня.
"""

from __future__ import annotations

from app.web import model

LABELS = [("home", "П1"), ("draw", "X"), ("away", "П2")]


def _pair(a: float | None, b: float | None) -> list[float] | None:
    return model.fair_probs([a, b])[0] if a and b else None


def analysis(m: dict) -> dict:
    o = m.get("odds") or {}
    mk = m.get("model")
    if not (o.get("home") and o.get("draw") and o.get("away")):
        return {"fair": None, "margin": None, "value": [], "odds_move": None}
    fair, margin = model.fair_probs([o["home"], o["draw"], o["away"]])
    value = []
    if mk:
        value = [
            {"market": "1X2", "pick": lbl, "key": key, "odds": o[key], "model": mk[key],
             "fair": fair[i], "edge": model.edge(mk[key], o[key])}
            for i, (key, lbl) in enumerate(LABELS)
        ]
        tot = _pair(o.get("over25"), o.get("under25"))
        if tot:
            value += [
                {"market": "Тотал", "pick": "ТБ 2.5", "key": "over25", "odds": o["over25"], "model": mk["over25"],
                 "fair": tot[0], "edge": model.edge(mk["over25"], o["over25"])},
                {"market": "Тотал", "pick": "ТМ 2.5", "key": "under25", "odds": o["under25"], "model": 1 - mk["over25"],
                 "fair": tot[1], "edge": model.edge(1 - mk["over25"], o["under25"])},
            ]
        btts = _pair(o.get("btts_yes"), o.get("btts_no"))
        if btts:
            value += [
                {"market": "Обе забьют", "pick": "Да", "key": "btts_yes", "odds": o["btts_yes"], "model": mk["btts"],
                 "fair": btts[0], "edge": model.edge(mk["btts"], o["btts_yes"])},
                {"market": "Обе забьют", "pick": "Нет", "key": "btts_no", "odds": o["btts_no"], "model": 1 - mk["btts"],
                 "fair": btts[1], "edge": model.edge(1 - mk["btts"], o["btts_no"])},
            ]

    move = None
    hist = m.get("odds_history") or []
    if len(hist) >= 2:
        first, last = hist[0], hist[-1]
        moves = {k: (last[k] - first[k]) / first[k] for k in ("home", "draw", "away") if first.get(k)}
        if moves:
            key = min(moves, key=lambda k: moves[k])
            move = {"key": key, "pick": dict(LABELS)[key], "from": first[key], "to": last[key], "change": moves[key]}
    return {"fair": {"home": fair[0], "draw": fair[1], "away": fair[2]}, "margin": margin,
            "value": value, "odds_move": move}


def summary(m: dict) -> dict:
    a = analysis(m)
    out = {k: m.get(k) for k in ("id", "league", "country", "kickoff", "status", "home", "away", "odds")}
    out["probs"] = a["fair"]
    best = max(a["value"], key=lambda v: v["edge"], default=None)
    out["best_value"] = best if best and best["edge"] > 0.03 else None
    out["odds_move"] = a["odds_move"]
    if m.get("status") == "live" and m.get("live"):
        out["live"] = {"minute": m["live"].get("minute"), "score": m["live"].get("score", "0:0"),
                       "odds": m["live"].get("odds") or m.get("odds")}
    return out


def feed(matches: list[dict], tipster: dict | None = None) -> dict:
    values, drops, candidates = [], [], []
    for m in matches:
        a = analysis(m)
        title = f'{m["home"]["name"]} — {m["away"]["name"]}'
        base = {"match_id": m["id"], "title": title, "league": m["league"], "kickoff": m["kickoff"]}
        for v in a["value"]:
            if m["status"] == "scheduled" and v["edge"] > 0.03:
                values.append({**base, **v})
            if m["status"] == "scheduled" and 1.25 <= v["odds"] <= 1.9 and v["model"] >= 0.55:
                candidates.append({**base, **v})
        mv = a["odds_move"]
        if mv and mv["change"] <= -0.06 and m["status"] != "finished":
            drops.append({**base, "status": m["status"], **mv})
    values.sort(key=lambda v: -v["edge"])
    drops.sort(key=lambda d: d["change"])
    candidates.sort(key=lambda v: -v["model"])
    express, used = [], set()
    for c in candidates:
        if c["match_id"] in used:
            continue
        express.append(c)
        used.add(c["match_id"])
        if len(express) == 4:
            break
    total_odds = total_prob = 1.0
    for e in express:
        total_odds *= e["odds"]
        total_prob *= e["model"]
    return {
        "value": values[:6],
        "drops": drops[:6],
        "express": {"picks": express, "odds": round(total_odds, 2), "prob": total_prob},
        "tipster": tipster,
    }
