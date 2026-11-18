"""Probabilita' senza margine e CLV senza margine (decisione di Giovanni, 18/11/2026).

CLV = quota presa x probabilita' di chiusura senza margine - 1. La probabilita' senza margine di un esito e'
1/quota divisa per la somma di 1/quota di tutti gli esiti dello stesso mercato, dello stesso bookmaker:
- 1-X-2 (anche del primo tempo): i tre esiti;
- over/under (gol, gol del primo tempo, statistiche "STAT:...:over:4.5"): la coppia della stessa linea;
- doppie chance: dalle probabilita' senza margine dell'1-X-2 (1X = 1 + X).
Se manca un esito del mercato non si calcola (None): meglio "n.d." che un numero con il margine dentro.
La vecchia formula (quota presa / quota di chiusura - 1) resta in una colonna a parte.
"""

from __future__ import annotations

from typing import Any

_ONE_X_TWO = ("HOME", "DRAW", "AWAY")
_ONE_X_TWO_PT = ("HOME_PT", "DRAW_PT", "AWAY_PT")
_DOUBLE = {"ONE_X": ("HOME", "DRAW"), "X_TWO": ("DRAW", "AWAY"), "ONE_TWO": ("HOME", "AWAY")}


def opposite_key(key: str) -> str | None:
    """L'altro esito di un over/under della stessa linea (UNDER_2_5 -> OVER_2_5, STAT:..:under:4.5 -> ..:over:4.5)."""
    if key.startswith("UNDER_"):
        return "OVER_" + key[len("UNDER_") :]
    if key.startswith("OVER_"):
        return "UNDER_" + key[len("OVER_") :]
    if ":under:" in key:
        return key.replace(":under:", ":over:")
    if ":over:" in key:
        return key.replace(":over:", ":under:")
    return None


def market_keys(key: str) -> tuple[str, ...] | None:
    """Tutti gli esiti del mercato del segno (None se non lo conosciamo)."""
    if key in _ONE_X_TWO:
        return _ONE_X_TWO
    if key in _ONE_X_TWO_PT:
        return _ONE_X_TWO_PT
    other = opposite_key(key)
    return (key, other) if other else None


def _probs(quotes: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float] | None:
    inv: dict[str, float] = {}
    for k in keys:
        try:
            q = float(quotes.get(k)) if quotes.get(k) is not None else 0.0
        except (TypeError, ValueError):
            q = 0.0
        if q <= 1.0:
            return None
        inv[k] = 1.0 / q
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()} if total > 0 else None


def novig_prob(quotes: dict[str, Any] | None, key: str) -> float | None:
    """Probabilita' senza margine del segno con le quote di un bookmaker (chiave -> quota)."""
    if not quotes:
        return None
    if key in _DOUBLE:
        p = _probs(quotes, _ONE_X_TWO)
        return round(sum(p[k] for k in _DOUBLE[key]), 4) if p else None
    keys = market_keys(key)
    if not keys:
        return None
    p = _probs(quotes, keys)
    return round(p[key], 4) if p else None


def clv_novig(taken: float | None, prob: float | None) -> float | None:
    if not taken or taken <= 1.0 or prob is None or prob <= 0:
        return None
    return round(float(taken) * float(prob) - 1.0, 4)
