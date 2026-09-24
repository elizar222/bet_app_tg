"""Модель матча: распределение Пуассона по ожидаемым голам.

По силе атаки и обороны считаем ожидаемые голы каждой команды (λ), дальше —
вероятность любого счёта, а из неё 1X2, тоталы, «обе забьют» и самый
вероятный счёт. Отдельно из кэфов букмекера убираем маржу — получаем
«честные» вероятности линии и сравниваем их с моделью (value).
"""

from __future__ import annotations

import math

MAX_GOALS = 6


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def score_matrix(lam_home: float, lam_away: float, max_goals: int = MAX_GOALS) -> list[list[float]]:
    home = [poisson(i, lam_home) for i in range(max_goals + 1)]
    away = [poisson(j, lam_away) for j in range(max_goals + 1)]
    return [[home[i] * away[j] for j in range(max_goals + 1)] for i in range(max_goals + 1)]


def markets(lam_home: float, lam_away: float) -> dict:
    m = score_matrix(lam_home, lam_away)
    n = len(m)
    total = sum(sum(row) for row in m)  # чуть меньше 1 из-за обрезки на 6 голах
    p_home = sum(m[i][j] for i in range(n) for j in range(n) if i > j) / total
    p_draw = sum(m[i][i] for i in range(n)) / total
    p_away = 1 - p_home - p_draw

    def over(line: float) -> float:
        return sum(m[i][j] for i in range(n) for j in range(n) if i + j > line) / total

    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n)) / total
    best = max(((i, j) for i in range(n) for j in range(n)), key=lambda ij: m[ij[0]][ij[1]])

    return {
        "lambda_home": round(lam_home, 2),
        "lambda_away": round(lam_away, 2),
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "over15": over(1.5),
        "over25": over(2.5),
        "over35": over(3.5),
        "btts": btts,
        "likely_score": f"{best[0]}:{best[1]}",
        "likely_score_prob": m[best[0]][best[1]] / total,
        "matrix": [[round(m[i][j] / total, 4) for j in range(5)] for i in range(5)],
    }


def fair_probs(odds: list[float]) -> tuple[list[float], float]:
    """Кэфы → вероятности без маржи. Возвращает (вероятности, маржа)."""

    implied = [1 / o for o in odds]
    book = sum(implied)
    return [p / book for p in implied], book - 1


def edge(model_prob: float, odds: float) -> float:
    """Перевес ставки: сколько в среднем приносит 1 ₽ (0.05 = +5%)."""

    return model_prob * odds - 1
