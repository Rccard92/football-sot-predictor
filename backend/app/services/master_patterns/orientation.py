"""Mercati senza quota: un pattern che fa scendere la frequenza di "sopra la soglia"
si gioca come "sotto la soglia". Le statistiche salvate sono sempre quelle del
lato giocato (Over o Under), cosi' la pagina e il live leggono un solo verso."""

from __future__ import annotations

from typing import Any


def synthetic_market_label(target_label: str, threshold: float | None, direction: int) -> str:
    side = "Over" if direction >= 0 else "Under"
    return f"{target_label} {side} {threshold:g}" if threshold is not None else f"{target_label} {side}"


def orient_season(stats: dict[str, Any], direction: int) -> dict[str, Any]:
    """Statistiche di 'sopra soglia' -> statistiche del lato giocato."""
    if direction >= 0:
        return dict(stats)
    out = dict(stats)
    n = stats.get("n")
    wins = stats.get("wins")
    if n is not None and wins is not None:
        out["wins"] = int(n) - int(wins)
        out["losses"] = int(wins)
    for key in ("win_rate_pct", "baseline_win_rate_pct"):
        if stats.get(key) is not None:
            out[key] = round(100.0 - float(stats[key]), 3)
    if stats.get("deviation_pct") is not None:
        out["deviation_pct"] = round(-float(stats["deviation_pct"]), 3)
    return out
