"""Resolver canonico condiviso per analisi tecnica Cecchino (KPI, Balance, GI, Signals).

Usato da get_today_fixture_detail e get_bet_builder_result_analysis_context
per garantire parity semantica su una sola source of truth.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture, Team
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
from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    build_expected_goal_engine_diagnostics_for_today_row,
)
from app.services.cecchino.cecchino_signal_consensus import build_matrix_signal_contract
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta
from app.services.datetime_utils import ensure_datetime_utc


def _resolve_local_fixture_context(
    db: Session,
    row: CecchinoTodayFixture,
) -> tuple[Fixture | None, str | None, str | None]:
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
    return local_fixture, local_home_name, local_away_name


def resolve_cecchino_technical_analysis_context(
    db: Session,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Risolve KPI, Balance v5, identity, snapshot meta, GI v5 e segnali (read-only)."""
    from app.services.cecchino.cecchino_today_service import (
        _resolve_kpi_panel_for_detail,
        rome_today,
    )

    output = row.cecchino_output_json or {}
    if not isinstance(output, dict):
        output = {}

    balance_mode = resolve_balance_detail_mode(row.scan_date, rome_today())
    snapshot_only = balance_mode == MODE_HISTORICAL
    kpi_panel = _resolve_kpi_panel_for_detail(row, db, snapshot_only=snapshot_only)

    expected_goal_engine_diagnostics = build_expected_goal_engine_diagnostics_for_today_row(
        db, row
    )

    local_fixture, local_home_name, local_away_name = _resolve_local_fixture_context(db, row)

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

    balance_v5_snapshot_meta = evaluate_balance_v5_snapshot_meta(
        mode=balance_mode,
        today_row=row,
        identity=fixture_identity_consistency,
        cecchino_output=output if isinstance(output, dict) else None,
        kpi_panel=kpi_panel if isinstance(kpi_panel, dict) else None,
        book_status=book_status,
        book_warnings=book_warnings,
    )

    kpi_for_balance = kpi_panel if isinstance(kpi_panel, dict) else None
    if balance_mode == MODE_HISTORICAL:
        kpi_for_balance = prepare_kpi_for_historical_balance(
            kpi_for_balance,
            book_status=book_status,
        )

    identity_for_balance = identity_for_balance_build(
        fixture_identity_consistency,
        balance_v5_snapshot_meta,
    )

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

    goal_intensity_v5: dict[str, Any] | None = None
    try:
        from app.services.cecchino.cecchino_goal_intensity_v5 import build_today_payload

        goal_intensity_v5 = build_today_payload(db, int(row.id))
    except Exception as exc:
        goal_intensity_v5 = {
            "status": "error",
            "error": "goal_intensity_v5_detail_failed",
            "message": str(exc)[:200],
            "operational_status": "preview_monitored",
            "operational_status_label_it": "Preview monitorata",
            "signals_integration_status": "blocked",
            "no_betting_signals": True,
        }

    goal_intensity_v5_preview = {
        **(goal_intensity_v5 or {}),
        "deprecated": True,
        "replacement": "goal_intensity_v5",
    }

    signals_matrix = output.get("signals_matrix") if isinstance(output, dict) else None
    signal_contract = build_matrix_signal_contract(
        signals_matrix if isinstance(signals_matrix, dict) else None,
    )

    return {
        "balance_mode": balance_mode,
        "cecchino_output": output,
        "kpi_panel": kpi_panel,
        "expected_goal_engine_diagnostics": expected_goal_engine_diagnostics,
        "fixture_identity_consistency": fixture_identity_consistency,
        "balance_v5_snapshot_meta": balance_v5_snapshot_meta,
        "balance_v5": balance_v5,
        "goal_intensity_v5": goal_intensity_v5,
        "goal_intensity_v5_preview": goal_intensity_v5_preview,
        "signals_matrix": signals_matrix,
        "signal_contract": signal_contract,
    }
