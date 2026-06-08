"""Delta Forza / Linearità Match — Cecchino Today Fase 36."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import (
    CECCHINO_DELTA_LINEAR_THRESHOLD,
    CECCHINO_DELTA_STRONG_THRESHOLD,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME

VERSION = "cecchino_delta_force_v1"

_SIDE_META = {
    SEL_HOME: {"segno": "1", "side": "HOME", "tie_rank": 0},
    SEL_DRAW: {"segno": "X", "side": "DRAW", "tie_rank": 1},
    SEL_AWAY: {"segno": "2", "side": "AWAY", "tie_rank": 2},
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _edge_pct(book: float | None, cecchino: float | None) -> float | None:
    b, c = _num(book), _num(cecchino)
    if b is None or c is None or c <= 0:
        return None
    return round((b / c - 1.0) * 100.0, 2)


def classify_delta_forza(delta_abs: float) -> dict[str, Any]:
    d = abs(float(delta_abs))
    if d < CECCHINO_DELTA_LINEAR_THRESHOLD:
        return {
            "class_key": "linear_statistical",
            "label": "Partita statistica",
            "subtitle": "Lettura lineare",
            "severity": "positive",
            "description": (
                "La distanza tra quota Cecchino e quota Betfair è contenuta: "
                "il match è leggibile in modo lineare."
            ),
        }
    if d < CECCHINO_DELTA_STRONG_THRESHOLD:
        return {
            "class_key": "non_linear",
            "label": "Partita non statistica",
            "subtitle": "Lettura non lineare",
            "severity": "warning",
            "description": (
                "La distanza tra quota Cecchino e quota Betfair è significativa: "
                "attenzione agli esiti fissi, meglio valutare doppie chance o mercati goal."
            ),
        }
    return {
        "class_key": "strong_distortion",
        "label": "Forte favorita / forte distorsione",
        "subtitle": "Non lineare forte",
        "severity": "negative",
        "description": (
            "Il book si discosta molto dalla quota matematica: "
            "il match presenta una forte distorsione da analizzare con cautela."
        ),
    }


def _row_direction(edge_pct: float | None) -> dict[str, str]:
    if edge_pct is None:
        return {
            "direction": "unknown",
            "direction_label": "—",
        }
    if edge_pct > 0:
        return {
            "direction": "book_higher",
            "direction_label": "Betfair più alta della quota Cecchino",
        }
    if edge_pct < 0:
        return {
            "direction": "book_lower",
            "direction_label": "Betfair comprime la quota",
        }
    return {
        "direction": "aligned",
        "direction_label": "Quote allineate",
    }


def _responsible_direction(edge_pct: float | None) -> dict[str, str]:
    if edge_pct is None:
        return {
            "responsible_direction": "unknown",
            "responsible_direction_label": "—",
            "meaning": "",
        }
    if edge_pct > 0:
        return {
            "responsible_direction": "quota_book_higher_than_cecchino",
            "responsible_direction_label": "Quota Betfair più alta della quota Cecchino",
            "meaning": "Possibile value, ma anche disallineamento da verificare",
        }
    if edge_pct < 0:
        return {
            "responsible_direction": "quota_book_lower_than_cecchino",
            "responsible_direction_label": "Quota Betfair più bassa della quota Cecchino",
            "meaning": "Il book comprime la quota rispetto al modello",
        }
    return {
        "responsible_direction": "aligned",
        "responsible_direction_label": "Quote allineate",
        "meaning": "Quote allineate tra book e modello",
    }


def _extract_1x2_rows(kpi_panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return {}
    by_key: dict[str, dict[str, Any]] = {}
    for row in kpi_panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        key = row.get("market_key")
        if key in _SIDE_META:
            by_key[str(key)] = row
    return by_key


def _build_row_analysis(market_key: str, row: dict[str, Any]) -> dict[str, Any] | None:
    meta = _SIDE_META[market_key]
    quota_book = _num(row.get("quota_book"))
    quota_cecchino = _num(row.get("quota_cecchino"))
    if quota_book is None or quota_cecchino is None:
        return None
    edge = _edge_pct(quota_book, quota_cecchino)
    if edge is None:
        return None
    delta_abs = round(abs(edge), 2)
    classification = classify_delta_forza(delta_abs)
    direction = _row_direction(edge)
    return {
        "market_key": market_key,
        "segno": meta["segno"],
        "quota_book": round(quota_book, 2),
        "quota_cecchino": round(quota_cecchino, 2),
        "edge_pct": edge,
        "delta_forza_abs": delta_abs,
        "class_key": classification["class_key"],
        "label": classification["label"],
        "direction": direction["direction"],
        "direction_label": direction["direction_label"],
    }


def build_cecchino_delta_force_analysis(kpi_panel: dict[str, Any] | None) -> dict[str, Any]:
    thresholds = {
        "linear_max_pct": CECCHINO_DELTA_LINEAR_THRESHOLD,
        "strong_distortion_min_pct": CECCHINO_DELTA_STRONG_THRESHOLD,
    }
    by_key = _extract_1x2_rows(kpi_panel)
    if not all(key in by_key for key in (SEL_HOME, SEL_DRAW, SEL_AWAY)):
        return {
            "version": VERSION,
            "status": "insufficient_data",
            "thresholds": thresholds,
            "warnings": ["missing_delta_force_inputs"],
        }

    rows: list[dict[str, Any]] = []
    for market_key in (SEL_HOME, SEL_DRAW, SEL_AWAY):
        row_analysis = _build_row_analysis(market_key, by_key[market_key])
        if row_analysis is None:
            return {
                "version": VERSION,
                "status": "insufficient_data",
                "thresholds": thresholds,
                "warnings": ["missing_delta_force_inputs"],
            }
        rows.append(row_analysis)

    best = max(
        rows,
        key=lambda r: (
            r["delta_forza_abs"],
            -_SIDE_META[r["market_key"]]["tie_rank"],
        ),
    )
    match_delta = best["delta_forza_abs"]
    match_class = classify_delta_forza(match_delta)
    resp_dir = _responsible_direction(best["edge_pct"])
    meta = _SIDE_META[best["market_key"]]

    return {
        "version": VERSION,
        "status": "available",
        "thresholds": thresholds,
        "match": {
            "delta_forza_abs": match_delta,
            "label": match_class["label"],
            "subtitle": match_class["subtitle"],
            "class_key": match_class["class_key"],
            "severity": match_class["severity"],
            "responsible_side": meta["side"],
            "responsible_side_label": meta["segno"],
            "responsible_edge_pct": best["edge_pct"],
            "responsible_direction": resp_dir["responsible_direction"],
            "responsible_direction_label": resp_dir["responsible_direction_label"],
            "meaning": resp_dir["meaning"],
            "description": match_class["description"],
        },
        "rows": rows,
        "warnings": [],
    }


def delta_force_embed(balance_delta_force: dict[str, Any] | None) -> dict[str, Any] | None:
    if not balance_delta_force or balance_delta_force.get("status") != "available":
        return None
    return {
        "match": balance_delta_force.get("match"),
        "rows": balance_delta_force.get("rows"),
        "thresholds": balance_delta_force.get("thresholds"),
    }
