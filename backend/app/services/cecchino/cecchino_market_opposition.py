"""Mappa canonica mercati opposti — research Indice di Acquistabilità.

Distingue comparatore statistico e complemento matematico.
Nessuna formula di acquistabilità; nessuna decisione betting.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

OPPOSITION_SUPPORTED = "supported"
OPPOSITION_UNSUPPORTED = "unsupported"

FAMILY_MATCH_WINNER = "match_winner"
FAMILY_DOUBLE_CHANCE = "double_chance"
FAMILY_OVER_UNDER = "over_under"
FAMILY_BTTS = "btts"

PERIOD_FT = "FT"
PERIOD_HT = "HT"

# Chiavi presenti nel Pannello KPI v2 Betfair (KPI_V2_ROW_DEFS).
PANEL_MARKET_KEYS: tuple[str, ...] = (
    SEL_HOME,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_AWAY,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
)

# Mercati teorici non presenti nel pannello.
ABSENT_FROM_PANEL: tuple[str, ...] = (
    "BTTS_YES",
    "BTTS_NO",
    "GG",
    "NO_GOAL",
    "HOME_PT",
    "AWAY_PT",
    "UNDER_1_5",
    "OVER_3_5",
    "UNDER_PT_0_5",
)

# Selezioni richieste per normalizzazione overround (solo esiti mutuamente esclusivi).
# Doppia Chance esclusa: 1X/X2/12 sono eventi sovrapposti.
MARKET_COMPLETE_SETS: dict[tuple[str, str, float | None], frozenset[str]] = {
    (FAMILY_MATCH_WINNER, PERIOD_FT, None): frozenset({SEL_HOME, SEL_DRAW, SEL_AWAY}),
    (FAMILY_OVER_UNDER, PERIOD_FT, 2.5): frozenset({SEL_OVER_2_5, SEL_UNDER_2_5}),
    (FAMILY_OVER_UNDER, PERIOD_HT, 1.5): frozenset({SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5}),
}

NORM_NOT_APPLICABLE_OVERLAPPING = "not_applicable_overlapping_outcomes"


def _entry(
    *,
    raw_market_code: str,
    canonical_market_family: str,
    period: str,
    line: float | None,
    selection: str,
    comparators: list[str],
    complement: str | None,
    opposition_status: str,
    reason: str | None = None,
    in_kpi_panel: bool = True,
) -> dict[str, Any]:
    return {
        "raw_market_code": raw_market_code,
        "canonical_market_family": canonical_market_family,
        "period": period,
        "line": line,
        "selection": selection,
        "comparator_selections": list(comparators),
        "complement_selection": complement,
        "opposition_status": opposition_status,
        "unsupported_reason": reason,
        "in_kpi_panel": in_kpi_panel,
    }


# Mappa statica verificata sul pannello KPI reale.
_OPPOSITION_MAP: dict[str, dict[str, Any]] = {
    SEL_HOME: _entry(
        raw_market_code=SEL_HOME,
        canonical_market_family=FAMILY_MATCH_WINNER,
        period=PERIOD_FT,
        line=None,
        selection=SEL_HOME,
        comparators=[SEL_AWAY],
        complement=SEL_X_TWO,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_DRAW: _entry(
        raw_market_code=SEL_DRAW,
        canonical_market_family=FAMILY_MATCH_WINNER,
        period=PERIOD_FT,
        line=None,
        selection=SEL_DRAW,
        comparators=[SEL_HOME, SEL_AWAY],
        complement=SEL_ONE_TWO,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_AWAY: _entry(
        raw_market_code=SEL_AWAY,
        canonical_market_family=FAMILY_MATCH_WINNER,
        period=PERIOD_FT,
        line=None,
        selection=SEL_AWAY,
        comparators=[SEL_HOME],
        complement=SEL_ONE_X,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_ONE_X: _entry(
        raw_market_code=SEL_ONE_X,
        canonical_market_family=FAMILY_DOUBLE_CHANCE,
        period=PERIOD_FT,
        line=None,
        selection=SEL_ONE_X,
        comparators=[SEL_AWAY],
        complement=SEL_AWAY,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_X_TWO: _entry(
        raw_market_code=SEL_X_TWO,
        canonical_market_family=FAMILY_DOUBLE_CHANCE,
        period=PERIOD_FT,
        line=None,
        selection=SEL_X_TWO,
        comparators=[SEL_HOME],
        complement=SEL_HOME,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_ONE_TWO: _entry(
        raw_market_code=SEL_ONE_TWO,
        canonical_market_family=FAMILY_DOUBLE_CHANCE,
        period=PERIOD_FT,
        line=None,
        selection=SEL_ONE_TWO,
        comparators=[SEL_DRAW],
        complement=SEL_DRAW,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_OVER_2_5: _entry(
        raw_market_code=SEL_OVER_2_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_FT,
        line=2.5,
        selection=SEL_OVER_2_5,
        comparators=[SEL_UNDER_2_5],
        complement=SEL_UNDER_2_5,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_UNDER_2_5: _entry(
        raw_market_code=SEL_UNDER_2_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_FT,
        line=2.5,
        selection=SEL_UNDER_2_5,
        comparators=[SEL_OVER_2_5],
        complement=SEL_OVER_2_5,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    # Coppia O/U presente solo a metà nel pannello → unsupported.
    SEL_OVER_1_5: _entry(
        raw_market_code=SEL_OVER_1_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_FT,
        line=1.5,
        selection=SEL_OVER_1_5,
        comparators=[],
        complement=None,
        opposition_status=OPPOSITION_UNSUPPORTED,
        reason="missing_under_1_5_in_kpi_panel",
    ),
    SEL_UNDER_3_5: _entry(
        raw_market_code=SEL_UNDER_3_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_FT,
        line=3.5,
        selection=SEL_UNDER_3_5,
        comparators=[],
        complement=None,
        opposition_status=OPPOSITION_UNSUPPORTED,
        reason="missing_over_3_5_in_kpi_panel",
    ),
    SEL_OVER_PT_1_5: _entry(
        raw_market_code=SEL_OVER_PT_1_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_HT,
        line=1.5,
        selection=SEL_OVER_PT_1_5,
        comparators=[SEL_UNDER_PT_1_5],
        complement=SEL_UNDER_PT_1_5,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_UNDER_PT_1_5: _entry(
        raw_market_code=SEL_UNDER_PT_1_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_HT,
        line=1.5,
        selection=SEL_UNDER_PT_1_5,
        comparators=[SEL_OVER_PT_1_5],
        complement=SEL_OVER_PT_1_5,
        opposition_status=OPPOSITION_SUPPORTED,
    ),
    SEL_OVER_PT_0_5: _entry(
        raw_market_code=SEL_OVER_PT_0_5,
        canonical_market_family=FAMILY_OVER_UNDER,
        period=PERIOD_HT,
        line=0.5,
        selection=SEL_OVER_PT_0_5,
        comparators=[],
        complement=None,
        opposition_status=OPPOSITION_UNSUPPORTED,
        reason="missing_under_pt_0_5_in_kpi_panel",
    ),
    SEL_DRAW_PT: _entry(
        raw_market_code=SEL_DRAW_PT,
        canonical_market_family=FAMILY_MATCH_WINNER,
        period=PERIOD_HT,
        line=None,
        selection=SEL_DRAW_PT,
        comparators=[],
        complement=None,
        opposition_status=OPPOSITION_UNSUPPORTED,
        reason="incomplete_1x2_first_half_in_kpi_panel",
    ),
}


def get_opposition(raw_market_code: str) -> dict[str, Any]:
    """Restituisce mapping canonico; unknown → unsupported."""
    key = (raw_market_code or "").strip().upper()
    if key in _OPPOSITION_MAP:
        return dict(_OPPOSITION_MAP[key])
    # Alias italiani / informali GG.
    if key in ("GG", "BTTS_YES", "BTTS", "BOTH_TEAMS_SCORE"):
        return _entry(
            raw_market_code=key,
            canonical_market_family=FAMILY_BTTS,
            period=PERIOD_FT,
            line=None,
            selection=key,
            comparators=[],
            complement=None,
            opposition_status=OPPOSITION_UNSUPPORTED,
            reason="btts_absent_from_kpi_panel",
            in_kpi_panel=False,
        )
    if key in ("NO_GOAL", "BTTS_NO", "NG", "NOGOAL"):
        return _entry(
            raw_market_code=key,
            canonical_market_family=FAMILY_BTTS,
            period=PERIOD_FT,
            line=None,
            selection=key,
            comparators=[],
            complement=None,
            opposition_status=OPPOSITION_UNSUPPORTED,
            reason="btts_absent_from_kpi_panel",
            in_kpi_panel=False,
        )
    return _entry(
        raw_market_code=key or "UNKNOWN",
        canonical_market_family="unknown",
        period=PERIOD_FT,
        line=None,
        selection=key or "UNKNOWN",
        comparators=[],
        complement=None,
        opposition_status=OPPOSITION_UNSUPPORTED,
        reason="unknown_market_code",
        in_kpi_panel=False,
    )


def list_opposition_map() -> list[dict[str, Any]]:
    """Tutte le entry panel + assenti documentati."""
    rows = [dict(v) for v in _OPPOSITION_MAP.values()]
    for absent in ABSENT_FROM_PANEL:
        if absent in _OPPOSITION_MAP:
            continue
        rows.append(get_opposition(absent))
    return rows


def is_supported(raw_market_code: str) -> bool:
    return get_opposition(raw_market_code)["opposition_status"] == OPPOSITION_SUPPORTED


def same_opposition_scope(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True solo se famiglia, periodo e linea coincidono."""
    return (
        a.get("canonical_market_family") == b.get("canonical_market_family")
        and a.get("period") == b.get("period")
        and a.get("line") == b.get("line")
    )


def required_selections_for_normalization(
    family: str, period: str, line: float | None
) -> frozenset[str] | None:
    """None se normalizzazione non definita (es. Doppia Chance overlapping)."""
    return MARKET_COMPLETE_SETS.get((family, period, line))


def normalization_status_for_family(family: str) -> str | None:
    """Se non None, status fisso senza tentare overround."""
    if family == FAMILY_DOUBLE_CHANCE:
        return NORM_NOT_APPLICABLE_OVERLAPPING
    return None


def comparators_valid_for_selection(
    selection_key: str, comparator_key: str
) -> bool:
    """Impedisce confronti cross-line / cross-period."""
    a = get_opposition(selection_key)
    b = get_opposition(comparator_key)
    if a["opposition_status"] != OPPOSITION_SUPPORTED:
        return False
    if not same_opposition_scope(a, b):
        return False
    return comparator_key in (a.get("comparator_selections") or [])
