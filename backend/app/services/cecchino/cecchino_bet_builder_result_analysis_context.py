"""Bet Builder Results — analysis context read-only (BET-RESULTS-02 / 02.1).

Endpoint focused: KPI + Balance v5 + Goal Intensity v5 + Signals pre-match snapshots.
Nessuna write DB, nessuna API esterna, nessun ricalcolo purchasability/HR.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_technical_analysis_context import (
    resolve_cecchino_technical_analysis_context,
)


def get_bet_builder_result_analysis_context(
    db: Session,
    today_fixture_id: int,
) -> dict[str, Any] | None:
    """Read-only analysis context for Bet Builder Results drawer."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return None
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return None

    warnings: list[str] = []

    try:
        technical = resolve_cecchino_technical_analysis_context(db, row)
    except Exception as exc:
        warnings.append(f"technical_analysis_unavailable:{str(exc)[:120]}")
        return {
            "contract_version": BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
            "source": {
                "kind": "cecchino_today_canonical_detail",
                "today_fixture_id": int(row.id),
            },
            "fixture": _fixture_block(row),
            "kpi_panel": None,
            "balance_v5": None,
            "fixture_identity_consistency": None,
            "balance_v5_snapshot_meta": None,
            "goal_intensity_v5": None,
            "signals_matrix": None,
            "signal_contract": None,
            "warnings": warnings,
        }

    goal_intensity_v5 = technical.get("goal_intensity_v5")
    if goal_intensity_v5 is not None and isinstance(goal_intensity_v5, dict):
        gi_status = goal_intensity_v5.get("status")
        if gi_status in ("error", "unavailable"):
            warnings.append(f"goal_intensity_v5_status:{gi_status}")

    return {
        "contract_version": BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
        "source": {
            "kind": "cecchino_today_canonical_detail",
            "today_fixture_id": int(row.id),
        },
        "fixture": _fixture_block(row),
        "kpi_panel": technical.get("kpi_panel"),
        "balance_v5": technical.get("balance_v5"),
        "fixture_identity_consistency": technical.get("fixture_identity_consistency"),
        "balance_v5_snapshot_meta": technical.get("balance_v5_snapshot_meta"),
        "goal_intensity_v5": goal_intensity_v5,
        "signals_matrix": technical.get("signals_matrix"),
        "signal_contract": technical.get("signal_contract"),
        "warnings": warnings,
    }


def _fixture_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "competition_id": int(row.competition_id) if row.competition_id else None,
        "scan_date": row.scan_date.isoformat(),
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "country": row.country_name,
        "league": row.league_name,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
    }
