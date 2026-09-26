"""Проверка ключей API: python -m app.check_apis (или check.bat).

Показывает тариф и остаток запросов API-Football, сколько матчей сегодня в
наших лигах, есть ли кэфы, и сохраняет сырые ответы OddsPapi в
data/check/ — по ним подключается второй источник кэфов.
Отчёт пишется в data/check/report.txt — его можно переслать разработчику.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

from app.config import BASE_DIR, load_config

OUT = BASE_DIR / "data" / "check"
lines: list[str] = []


def say(text: str = "") -> None:
    print(text)
    lines.append(text)


def _trim(data, n: int = 25):
    """Большие списки режем, чтобы файл оставался валидным JSON и небольшим."""

    if isinstance(data, list):
        return [_trim(x, n) for x in data[:n]]
    if isinstance(data, dict):
        return {k: _trim(v, n) for k, v in data.items()}
    return data


def dump(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_trim(data), ensure_ascii=False, indent=1), encoding="utf-8")


async def probe(http: aiohttp.ClientSession, name: str, url: str, params: dict, headers: dict | None = None):
    """Пробный запрос: сохраняем ответ и пишем в отчёт, что вернулось."""

    try:
        async with http.get(url, params=params, headers=headers or {}) as r:
            status = r.status
            body = await r.json(content_type=None)
    except Exception as exc:  # noqa: BLE001
        say(f"  {name}: не удалось — {exc}")
        return None
    dump(f"{name}.json", body)
    if isinstance(body, dict) and body.get("errors"):
        say(f"  {name}: ОШИБКА {body['errors']}")
    elif isinstance(body, dict) and "response" in body:
        say(f"  {name}: OK, результатов {body.get('results')}")
    else:
        size = len(body) if isinstance(body, (list, dict)) else 0
        say(f"  {name}: HTTP {status}, элементов {size}")
    return body


async def check_apifootball(http: aiohttp.ClientSession, key: str, leagues: tuple[int, ...]) -> None:
    from app.web.apifootball import BASE_URL, DEFAULT_LEAGUES

    say("=== API-Football ===")
    if not key:
        say("Ключ не задан (APIFOOTBALL_KEY) — мини-апп работает на демо-данных.")
        return
    headers = {"x-apisports-key": key}
    try:
        async with http.get(BASE_URL + "/status", headers=headers) as r:
            st = await r.json(content_type=None)
        dump("apifootball_status.json", st)
        if st.get("errors"):
            say(f"ОШИБКА: {st['errors']}")
            return
        resp = st.get("response") or {}
        sub = resp.get("subscription") or {}
        req = resp.get("requests") or {}
        say(f"Ключ рабочий. Тариф: {sub.get('plan')}, активен: {sub.get('active')}, до {sub.get('end')}")
        say(f"Запросов сегодня: {req.get('current')} из {req.get('limit_day')}")

        day = datetime.now().strftime("%Y-%m-%d")
        async with http.get(BASE_URL + "/fixtures", headers=headers, params={"date": day}) as r:
            fx = await r.json(content_type=None)
        dump("apifootball_fixtures_today.json", fx)
        if fx.get("errors"):
            say(f"Матчи: ОШИБКА {fx['errors']}")
            return
        ours = [x for x in fx.get("response", []) if x["league"]["id"] in (leagues or DEFAULT_LEAGUES)]
        say(f"Матчей сегодня всего: {len(fx.get('response', []))}, в наших лигах: {len(ours)}")
        for x in ours[:5]:
            say(f"  {x['fixture']['date'][11:16]} {x['league']['name']}: {x['teams']['home']['name']} — {x['teams']['away']['name']} ({x['fixture']['status']['short']})")
        if ours:
            lg = ours[0]["league"]
            async with http.get(BASE_URL + "/odds", headers=headers,
                                params={"league": lg["id"], "season": lg["season"], "date": day}) as r:
                od = await r.json(content_type=None)
            dump("apifootball_odds_sample.json", od)
            if od.get("errors"):
                say(f"Кэфы: ОШИБКА {od['errors']}")
            else:
                n = len(od.get("response", []))
                bms = {b["name"] for it in od.get("response", []) for b in it.get("bookmakers", [])}
                say(f"Кэфы: {n} матчей, букмекеры: {', '.join(sorted(bms)[:8]) or 'нет'}")

        say("Проверка ограничений бесплатного тарифа (EPL):")
        season = datetime.now().year if datetime.now().month >= 7 else datetime.now().year - 1
        nxt = await probe(http, "af_next", BASE_URL + "/fixtures", {"league": 39, "season": season, "next": 5}, headers)
        await probe(http, "af_standings", BASE_URL + "/standings", {"league": 39, "season": season}, headers)
        await probe(http, "af_team_last", BASE_URL + "/fixtures", {"team": 42, "last": 5}, headers)
        await probe(http, "af_odds_league", BASE_URL + "/odds", {"league": 39, "season": season}, headers)
        fid = (nxt or {}).get("response", [{}])[0].get("fixture", {}).get("id") if (nxt or {}).get("response") else None
        if fid:
            await probe(http, "af_predictions", BASE_URL + "/predictions", {"fixture": fid}, headers)
            await probe(http, "af_odds_fixture", BASE_URL + "/odds", {"fixture": fid}, headers)
    except Exception as exc:  # noqa: BLE001
        say(f"Не удалось связаться с API-Football: {exc}")


async def check_oddspapi(http: aiohttp.ClientSession, key: str) -> None:
    say()
    say("=== OddsPapi ===")
    if not key:
        say("Ключ не задан (ODDSPAPI_KEY).")
        return
    base = "https://api.oddspapi.io/v4"
    for name, path, params in [
        ("sports", "/sports", {}),
        ("tournaments", "/tournaments", {"sportId": 10}),
    ]:
        try:
            async with http.get(base + path, params={**params, "apiKey": key}) as r:
                status = r.status
                body = await r.json(content_type=None)
            dump(f"oddspapi_{name}.json", body)
            size = len(body) if isinstance(body, list) else len(body.keys()) if isinstance(body, dict) else 0
            say(f"{path}: HTTP {status}, элементов: {size}")
        except Exception as exc:  # noqa: BLE001
            say(f"{path}: не удалось — {exc}")
    say("Пробные запросы кэфов (АПЛ, tournamentId=17):")
    fx = await probe(http, "op_fixtures", base + "/fixtures", {"tournamentId": 17, "apiKey": key})
    if not (isinstance(fx, list) and fx):
        fx = await probe(http, "op_fixtures_sport", base + "/fixtures", {"sportId": 10, "tournamentId": 17, "apiKey": key})
    await probe(http, "op_odds_by_tournaments", base + "/odds-by-tournaments",
                {"bookmaker": "pinnacle", "tournamentIds": "17", "oddsFormat": "decimal", "apiKey": key})
    fixture_id = None
    if isinstance(fx, list) and fx and isinstance(fx[0], dict):
        fixture_id = fx[0].get("fixtureId") or fx[0].get("id")
    if fixture_id:
        await probe(http, "op_odds_fixture", base + "/odds", {"fixtureId": fixture_id, "oddsFormat": "decimal", "apiKey": key})
    await probe(http, "op_bookmakers", base + "/bookmakers", {"apiKey": key})
    say("Сырые ответы сохранены в data/check/ — пришлите папку разработчику.")


async def main() -> None:
    cfg = load_config()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as http:
        await check_apifootball(http, cfg.apifootball_key, cfg.apifootball_leagues)
        await check_oddspapi(http, cfg.oddspapi_key)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    say()
    say(f"Отчёт: {OUT / 'report.txt'}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
