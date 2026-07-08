"""Riferimenti quota goal Cecchino per formule matrice segnali (es. Under 2.5 → D39)."""

from __future__ import annotations

import math
from typing import Any

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_goal_formulas import goal_market_kpi_entry
from app.services.cecchino.cecchino_selection_keys import SEL_UNDER_2_5
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_odd(odd: float | None) -> bool:
    return odd is not None and math.isfinite(odd) and odd > 0


def _kpi_panel_under_odd(kpi_panel: dict | None) -> float | None:
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return None
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("market_key") == SEL_UNDER_2_5:
            odd = _num(row.get("quota_cecchino"))
            if _valid_odd(odd):
                return odd
        label = str(row.get("segno") or row.get("label") or "").strip().lower()
        if label in ("under 2.5", "under2.5", "u2.5"):
            odd = _num(row.get("quota_cecchino"))
            if _valid_odd(odd):
                return odd
    return None


def resolve_under_2_5_cecchino_odd(
    *,
    kpi_panel: dict | None = None,
    goal_markets: dict | None = None,
) -> float | None:
    """Quota Cecchino Under 2.5: kpi_panel (quota_cecchino) poi goal_markets (final_odd)."""
    odd = _kpi_panel_under_odd(kpi_panel)
    if _valid_odd(odd):
        return odd
    if isinstance(goal_markets, dict):
        q, _, _ = goal_market_kpi_entry(goal_markets, SEL_UNDER_2_5)
        if _valid_odd(q):
            return q
    return None


def resolve_under_2_5_cecchino_odd_from_fixture(row: CecchinoTodayFixture) -> float | None:
    kpi = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else None
    goal_markets = (output or {}).get("goal_markets")
    return resolve_under_2_5_cecchino_odd(kpi_panel=kpi, goal_markets=goal_markets)


def _sample_from_stats(stats_snapshot: dict[str, Any] | None) -> int:
    if not stats_snapshot or not isinstance(stats_snapshot, dict):
        return 0
    block = (stats_snapshot.get("input_snapshot") or stats_snapshot).get("home_away") or {}
    home = int(block.get("home_sample_count") or block.get("home_sample") or 0)
    away = int(block.get("away_sample_count") or block.get("away_sample") or 0)
    return max(0, home + away)


def sample_home_away_split_from_stats(stats_snapshot: dict[str, Any] | None) -> int:
    return _sample_from_stats(stats_snapshot)


def rebuild_signals_matrix_for_output(
    output: dict[str, Any],
    *,
    sample_home_away_split: int,
    kpi_panel: dict | None = None,
) -> dict[str, Any] | None:
    """Ricalcola signals_matrix con quote finali, prob e quota Under 2.5 opzionale."""
    if not isinstance(output, dict):
        return None
    final = output.get("final") or {}
    if not isinstance(final, dict) or final.get("status") != STATUS_AVAILABLE:
        return None
    q1 = _num(final.get("quota_1"))
    qx = _num(final.get("quota_x"))
    q2 = _num(final.get("quota_2"))
    if q1 is None or qx is None or q2 is None:
        return None
    under_odd = resolve_under_2_5_cecchino_odd(
        kpi_panel=kpi_panel,
        goal_markets=output.get("goal_markets"),
    )
    return build_signals_matrix(
        q1=q1,
        qx=qx,
        q2=q2,
        sample_home_away_split=sample_home_away_split,
        prob_1=_num(final.get("prob_1")),
        prob_x=_num(final.get("prob_x")),
        prob_2=_num(final.get("prob_2")),
        under_2_5_cecchino_odd=under_odd,
    )
