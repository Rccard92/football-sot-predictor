"""Bet Builder Results — analysis context read-only (BET-RESULTS-02).

Endpoint focused: KPI + Balance v5 + Goal Intensity v5 pre-match snapshots.
Nessuna write DB, nessuna API esterna, nessun ricalcolo purchasability/HR.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture, Team
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_balance_v5 import build_cecchino_balance_v5
from app.services.cecchino.cecchino_balance_v5_detail import (
    MODE_HISTORICAL,
    apply_market_deviation_book_gate,
    build_balance_identity_for_detail,
    classify_book_snapshot_status,
    evaluate_balance_v5_snapshot_meta,
    identity_for_balance_build,
    prepare_kpi_for_historical_balance,
    resolve_balance_detail_mode,
    _kpi_has_book_odds,
)
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    build_expected_goal_engine_diagnostics_for_today_row,
)
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta
from app.services.cecchino.cecchino_today_service import (
    _resolve_kpi_panel_for_detail,
    rome_today,
)
from app.services.datetime_utils import ensure_datetime_utc


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
    output = row.cecchino_output_json or {}
    if not isinstance(output, dict):
        output = {}

    balance_mode = resolve_balance_detail_mode(row.scan_date, rome_today())
    snapshot_only = balance_mode == MODE_HISTORICAL

    kpi_panel: dict[str, Any] | None = None
    try:
        kpi_panel = _resolve_kpi_panel_for_detail(row, db, snapshot_only=snapshot_only)
    except Exception as exc:
        warnings.append(f"kpi_panel_unavailable:{str(exc)[:120]}")

    local_fixture: Fixture | None = None
    local_home_name: str | None = None
    local_away_name: str | None = None
    if row.local_fixture_id:
        local_fixture = db.get(Fixture, int(row.local_fixture_id))
        if local_fixture is not None:
            home_team = (
                db.get(Team, int(local_fixture.home_team_id))
                if local_fixture.home_team_id
                else None
            )
            away_team = (
                db.get(Team, int(local_fixture.away_team_id))
                if local_fixture.away_team_id
                else None
            )
            local_home_name = home_team.name if home_team else None
            local_away_name = away_team.name if away_team else None

    expected_goal_engine_diagnostics: dict[str, Any] | None = None
    try:
        expected_goal_engine_diagnostics = build_expected_goal_engine_diagnostics_for_today_row(
            db, row
        )
    except Exception:
        expected_goal_engine_diagnostics = None

    fixture_identity_consistency: dict[str, Any] | None = None
    try:
        fixture_identity_consistency = build_balance_identity_for_detail(
            mode=balance_mode,
            today_row=row,
            local_fixture=local_fixture,
            cecchino_output=output if isinstance(output, dict) else None,
            expected_goal_diagnostics=expected_goal_engine_diagnostics
            if isinstance(expected_goal_engine_diagnostics, dict)
            else None,
            local_home_team_name=local_home_name,
            local_away_team_name=local_away_name,
        )
    except Exception as exc:
        warnings.append(f"fixture_identity_unavailable:{str(exc)[:120]}")

    kickoff_dt = None
    if row.kickoff:
        try:
            kickoff_dt = ensure_datetime_utc(row.kickoff, field_name="today.kickoff")
        except Exception:
            kickoff_dt = None

    odds_meta = read_odds_meta(
        row.odds_snapshot_json if isinstance(row.odds_snapshot_json, dict) else None
    )
    book_status, book_warnings = classify_book_snapshot_status(
        kickoff=kickoff_dt,
        odds_meta=odds_meta,
        has_book_odds=_kpi_has_book_odds(kpi_panel if isinstance(kpi_panel, dict) else None),
    )

    balance_v5_snapshot_meta: dict[str, Any] | None = None
    try:
        balance_v5_snapshot_meta = evaluate_balance_v5_snapshot_meta(
            mode=balance_mode,
            today_row=row,
            identity=fixture_identity_consistency,
            cecchino_output=output if isinstance(output, dict) else None,
            kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
            book_status=book_status,
            book_warnings=book_warnings,
        )
    except Exception as exc:
        warnings.append(f"balance_snapshot_meta_unavailable:{str(exc)[:120]}")

    kpi_for_balance = kpi_panel if isinstance(kpi_panel, dict) else None
    if balance_mode == MODE_HISTORICAL:
        kpi_for_balance = prepare_kpi_for_historical_balance(
            kpi_for_balance,
            book_status=book_status,
        )

    identity_for_balance = identity_for_balance_build(
        fixture_identity_consistency if isinstance(fixture_identity_consistency, dict) else {},
        balance_v5_snapshot_meta if isinstance(balance_v5_snapshot_meta, dict) else {},
    )

    balance_v5: dict[str, Any] | None = None
    try:
        balance_v5 = build_cecchino_balance_v5(
            cecchino_final=output.get("final") if isinstance(output, dict) else None,
            goal_markets=output.get("goal_markets") if isinstance(output, dict) else None,
            kpi_panel=kpi_for_balance,
            identity_consistency=identity_for_balance,
        )
        if balance_mode == MODE_HISTORICAL:
            balance_v5 = apply_market_deviation_book_gate(
                balance_v5,
                book_status=book_status,
                book_warnings=book_warnings,
            )
    except Exception as exc:
        warnings.append(f"balance_v5_unavailable:{str(exc)[:120]}")

    goal_intensity_v5: dict[str, Any] | None = None
    try:
        from app.services.cecchino.cecchino_goal_intensity_v5 import build_today_payload

        goal_intensity_v5 = build_today_payload(db, int(row.id))
    except Exception as exc:
        goal_intensity_v5 = None
        warnings.append(f"goal_intensity_v5_unavailable:{str(exc)[:120]}")

    if goal_intensity_v5 is not None and isinstance(goal_intensity_v5, dict):
        gi_status = goal_intensity_v5.get("status")
        if gi_status in ("error", "unavailable"):
            warnings.append(f"goal_intensity_v5_status:{gi_status}")

    return {
        "contract_version": BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
        "fixture": {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": int(row.provider_fixture_id),
            "competition_id": int(row.competition_id) if row.competition_id else None,
            "scan_date": row.scan_date.isoformat(),
            "kickoff": row.kickoff.isoformat() if row.kickoff else None,
            "country": row.country_name,
            "league": row.league_name,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
        },
        "kpi_panel": kpi_panel,
        "balance_v5": balance_v5,
        "fixture_identity_consistency": fixture_identity_consistency,
        "balance_v5_snapshot_meta": balance_v5_snapshot_meta,
        "goal_intensity_v5": goal_intensity_v5,
        "warnings": warnings,
    }
