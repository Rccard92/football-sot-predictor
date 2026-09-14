"""Verdetti, totali e confronto con il caso per la Master Pattern (logica pura)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.services.master_patterns.constants import (
    ALL_SEASONS,
    MIN_SAMPLE,
    SYNTHETIC_CONFIRM_DEVIATION_PCT,
    TARGET_MARKET,
    VERDICT_ATTENUATED,
    VERDICT_CONFIRMED,
    VERDICT_INSUFFICIENT,
    VERDICT_REJECTED,
    VERIFY_SEASONS,
)


def market_verdict(n: int, roi_pct: float | None) -> str:
    if n < MIN_SAMPLE or roi_pct is None:
        return VERDICT_INSUFFICIENT
    return VERDICT_CONFIRMED if roi_pct > 0 else VERDICT_REJECTED


def synthetic_verdict(n: int, deviation_pct: float | None, direction: int) -> str:
    if n < MIN_SAMPLE or deviation_pct is None:
        return VERDICT_INSUFFICIENT
    signed = deviation_pct * direction
    if signed >= SYNTHETIC_CONFIRM_DEVIATION_PCT:
        return VERDICT_CONFIRMED
    if signed > 0:
        return VERDICT_ATTENUATED
    return VERDICT_REJECTED


def is_tested_all(seasons: dict[str, dict[str, Any]]) -> bool:
    return all(
        seasons.get(s, {}).get("verdict") not in (None, VERDICT_INSUFFICIENT) for s in VERIFY_SEASONS
    )


def is_winner(seasons: dict[str, dict[str, Any]]) -> bool:
    return all(seasons.get(s, {}).get("verdict") == VERDICT_CONFIRMED for s in VERIFY_SEASONS)


def chance_probability(seasons: dict[str, dict[str, Any]]) -> float:
    """Probabilita' che un gruppo casuale passi tutte e 4 le verifiche (stagioni indipendenti)."""
    return math.prod(float(seasons.get(s, {}).get("null_p") or 0.0) for s in VERIFY_SEASONS)


def totals(seasons: dict[str, dict[str, Any]], target_type: str) -> dict[str, Any]:
    """Totali sulle 5 stagioni (scoperta compresa)."""
    rows = [seasons[s] for s in ALL_SEASONS if s in seasons and seasons[s].get("n")]
    n = sum(int(r["n"]) for r in rows)
    wins = sum(int(r.get("wins") or 0) for r in rows)
    out: dict[str, Any] = {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate_pct": round(wins / n * 100.0, 2) if n else None,
    }
    if target_type == TARGET_MARKET:
        priced = [r for r in rows if r.get("profit_units") is not None and r.get("n_priced")]
        n_priced = sum(int(r["n_priced"]) for r in priced)
        profit = sum(float(r["profit_units"]) for r in priced)
        quota_weight = sum(float(r["avg_quota"]) * int(r["n_priced"]) for r in priced if r.get("avg_quota"))
        out.update(
            {
                "profit_units": round(profit, 2),
                "roi_pct": round(profit / n_priced * 100.0, 2) if n_priced else None,
                "avg_quota": round(quota_weight / n_priced, 3) if n_priced else None,
            }
        )
    else:
        devs = [float(r["deviation_pct"]) for r in rows if r.get("deviation_pct") is not None]
        out["avg_deviation_pct"] = round(sum(devs) / len(devs), 2) if devs else None
    return out


def tally(patterns: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """patterns: dizionari con chiave 'seasons'."""
    tested = 0
    winners = 0
    expected = 0.0
    for p in patterns:
        seasons = p["seasons"]
        if not is_tested_all(seasons):
            continue
        tested += 1
        expected += chance_probability(seasons)
        winners += int(is_winner(seasons))
    return {
        "tested_all_seasons": tested,
        "winners": winners,
        "expected_by_chance": round(expected, 1),
        "lift": round(winners / expected, 2) if expected > 0 else None,
    }
