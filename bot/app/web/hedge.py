"""Математика хеджирования.

W — выплата по купону, S — сумма исходной ставки, K — кэф на противоположный
исход, C — сколько букмекер предлагает за выкуп (Cash Out).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

MODES = ("equal", "zero", "custom")


@dataclass
class HedgeResult:
    mode: str
    hedge_amount: float
    profit_if_bet_wins: float  # купон зашёл, хедж сгорел
    profit_if_hedge_wins: float  # купон не зашёл, хедж выиграл
    guaranteed: float  # минимальный результат из двух
    cash_in_hand_equal: float  # сколько на руках при Equal Profit
    fair_cashout: float  # честная цена выкупа без маржи БК
    cashout: float | None
    vs_cashout: float | None  # (минимум на руках при хедже) − выкуп
    implied_prob_bet: float  # вероятность, что купон зайдёт, по линии БК

    def as_dict(self) -> dict:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def equal_amount(payout: float, odds: float) -> float:
    return payout / odds


def zero_risk_amount(stake: float, odds: float) -> float:
    return stake / (odds - 1)


def calculate(
    *,
    payout: float,
    stake: float,
    odds: float,
    mode: str = "equal",
    ratio: float = 0.6,
    cashout: float | None = None,
) -> HedgeResult:
    if payout <= 0 or stake <= 0:
        raise ValueError("Выплата и ставка должны быть больше нуля")
    if odds <= 1.0:
        raise ValueError("Кэф должен быть больше 1")
    if mode not in MODES:
        raise ValueError("Неизвестный режим")

    equal = equal_amount(payout, odds)
    if mode == "equal":
        amount = equal
    elif mode == "zero":
        amount = zero_risk_amount(stake, odds)
    else:
        amount = equal * max(0.0, min(ratio, 1.5))

    win_bet = payout - stake - amount
    win_hedge = amount * (odds - 1) - stake
    in_hand_equal = payout * (1 - 1 / odds)
    in_hand_min = min(payout - amount, amount * odds)

    return HedgeResult(
        mode=mode,
        hedge_amount=amount,
        profit_if_bet_wins=win_bet,
        profit_if_hedge_wins=win_hedge,
        guaranteed=min(win_bet, win_hedge),
        cash_in_hand_equal=in_hand_equal,
        fair_cashout=in_hand_equal,
        cashout=cashout,
        vs_cashout=(in_hand_min - cashout) if cashout else None,
        implied_prob_bet=1 - 1 / odds,
    )
