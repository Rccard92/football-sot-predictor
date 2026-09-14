"""Pannello KPI V2.5: stessa formula del rating V2, input corretti.

In V2 il "vantaggio" era probabilita' Cecchino - 1/quota book, cioe' contro una
probabilita' che contiene il margine del bookmaker, e l'edge era quota book / quota
Cecchino - 1. In V2.5:
- vantaggio = probabilita' Cecchino - probabilita' del book SENZA margine;
- edge = valore atteso reale della giocata: probabilita' Cecchino x quota book - 1.
Rating = probabilita' x 0,5 + vantaggio x 2 + edge (in punti), limitato a 0-100, come in V2.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import rating_label
from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS

FORMULA_VERSION = "cecchino_v25_kpi_v1"

_FAMILIES_EXCLUSIVE: tuple[tuple[str, ...], ...] = (
    ("HOME", "DRAW", "AWAY"),
    ("HOME_PT", "DRAW_PT", "AWAY_PT"),
    ("OVER_0_5", "UNDER_0_5"),
    ("OVER_1_5", "UNDER_1_5"),
    ("OVER_2_5", "UNDER_2_5"),
    ("OVER_3_5", "UNDER_3_5"),
)


def _odd(entry: dict[str, Any] | None) -> float | None:
    if not isinstance(entry, dict):
        return None
    v = entry.get("value")
    try:
        f = float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
    return f if f is not None and f > 1.0 else None


def fair_probabilities(strict_by_market: dict[str, dict[str, Any]]) -> dict[str, float]:
    """Probabilita' del book senza margine, famiglia per famiglia (solo famiglie complete).

    Doppia chance: dalle sue stesse quote quando la terna e' completa (somma delle
    probabilita' riportata a 2); solo se manca un lato, dalla terna 1X2. Nei file storici
    1X2 e doppia chance sono rilevati in momenti diversi: ricavare la DC dall'1X2 creava
    un valore atteso fittizio.
    """
    out: dict[str, float] = {}
    for family in _FAMILIES_EXCLUSIVE:
        odds = [_odd(strict_by_market.get(k)) for k in family]
        if any(o is None for o in odds):
            continue
        inv = [1.0 / o for o in odds]  # type: ignore[operator]
        total = sum(inv)
        for k, v in zip(family, inv):
            out[k] = v / total
    dc_keys = ("ONE_X", "X_TWO", "ONE_TWO")
    dc_odds = [_odd(strict_by_market.get(k)) for k in dc_keys]
    dc_real = all(o is not None and not (strict_by_market.get(k) or {}).get("is_derived") for k, o in zip(dc_keys, dc_odds))
    if dc_real:
        inv = [1.0 / o for o in dc_odds]  # type: ignore[operator]
        total = sum(inv)
        for k, v in zip(dc_keys, inv):
            out[k] = 2.0 * v / total
    elif all(k in out for k in ("HOME", "DRAW", "AWAY")):
        out["ONE_X"] = out["HOME"] + out["DRAW"]
        out["X_TWO"] = out["DRAW"] + out["AWAY"]
        out["ONE_TWO"] = out["HOME"] + out["AWAY"]
    return out


def rating(p_cec: float | None, vantaggio: float | None, edge_pct: float | None) -> int | None:
    if p_cec is None or vantaggio is None or edge_pct is None:
        return None
    raw = p_cec * 100.0 * 0.5 + vantaggio * 100.0 * 2.0 + edge_pct
    return int(round(max(0.0, min(100.0, raw))))


def build_kpi_panel_v25(
    *,
    probabilities: dict[str, float | None],
    strict_by_market: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fair = fair_probabilities(strict_by_market)
    rows: list[dict[str, Any]] = []
    for market in CORE_MARKETS:
        key = market.key
        p = probabilities.get(key)
        quota_book = _odd(strict_by_market.get(key))
        p_fair = fair.get(key)
        vantaggio = round(p - p_fair, 6) if p is not None and p_fair is not None else None
        edge = round((p * quota_book - 1.0) * 100.0, 3) if p is not None and quota_book is not None else None
        r = rating(p, vantaggio, edge)
        rows.append(
            {
                "market_key": key,
                "label": market.label,
                "prob_cecchino": round(p, 6) if p is not None else None,
                "quota_cecchino": round(1.0 / p, 4) if p else None,
                "quota_book": quota_book,
                "quota_book_derived": bool((strict_by_market.get(key) or {}).get("is_derived")),
                "prob_book_fair": round(p_fair, 6) if p_fair is not None else None,
                "vantaggio_prob": vantaggio,
                "edge_pct": edge,
                "rating": r,
                "rating_label": rating_label(r),
            }
        )
    return {"version": FORMULA_VERSION, "rows": rows, "fair_probabilities": {k: round(v, 6) for k, v in fair.items()}}
