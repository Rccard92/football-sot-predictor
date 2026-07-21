"""Ricalcolo offline Cecchino Today con nuovi pesi — senza API-Football."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino.cecchino_betfair_odds_payload import (
    build_betfair_payload_from_snapshot,
)
from app.services.cecchino.cecchino_bookmaker_odds_service import load_betfair_odds_payload
from app.services.cecchino.cecchino_current_season_xg import maybe_ensure_xg_for_eligible_row
from app.services.cecchino.cecchino_fixture_history import build_goal_market_contexts
from app.services.cecchino.cecchino_goal_formulas import build_goal_market_cecchino_odds
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import build_cecchino_kpi_panel_v2_betfair
from app.services.cecchino.cecchino_purchasability_snapshot import (
    attach_purchasability_preview_to_output,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    attach_balance_v5_monitoring_to_output,
)
from app.services.cecchino.cecchino_service import calculate_and_persist_for_fixture
from app.services.cecchino.cecchino_signal_backfill import (
    _ensure_signals_matrix_on_row,
)
from app.services.cecchino.cecchino_signal_evaluation import evaluate_activations_for_fixture
from app.services.cecchino.cecchino_signal_goal_refs import (
    rebuild_signals_matrix_for_output,
    sample_home_away_split_from_stats,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_target_mapping import remap_under_over_activations_in_range
from app.services.cecchino.cecchino_today_betfair_refresh import refresh_betfair_odds_for_fixture
from app.services.cecchino.cecchino_today_final_eligibility import (
    validate_cecchino_today_final_eligibility,
)
from app.services.cecchino.cecchino_today_odds_meta import read_odds_meta

logger = logging.getLogger(__name__)


def _extract_leakage_status(stats_snapshot: dict[str, Any] | None) -> str:
    if not stats_snapshot:
        return "undefined"
    return str(stats_snapshot.get("leakage_status") or "undefined")


def _load_betfair_payload(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    use_existing: bool,
) -> dict[str, Any]:
    if not use_existing:
        return {"status": "not_available"}
    payload = build_betfair_payload_from_snapshot(
        row.odds_snapshot_json,
        source="cached_betfair_odds",
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
    )
    if payload.get("status") == "not_available" and row.competition_id and row.local_fixture_id:
        payload = load_betfair_odds_payload(
            db,
            competition_id=int(row.competition_id),
            fixture_id=int(row.local_fixture_id),
        )
    return payload


def recompute_today_fixture_offline(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    refresh_bookmaker_odds: bool = False,
    use_existing_bookmaker_odds: bool = True,
    force_remap_signals: bool = False,
    sync_signal_activations: bool = True,
    evaluate_signals_after: bool = True,
    ensure_xg: bool = True,
) -> dict[str, Any]:
    """Ricalcola output Cecchino per una riga Today usando solo dati DB."""
    result: dict[str, Any] = {
        "fixture_id": int(row.id),
        "recomputed": False,
        "kpi_recomputed": False,
        "signals_synced": 0,
        "signals_deactivated": 0,
        "signals_evaluated": 0,
        "warning": None,
        "xg_ensured": False,
    }

    if row.local_fixture_id is None or row.competition_id is None:
        result["warning"] = "missing_local_fixture_or_competition"
        return result

    if row.cecchino_output_json is None:
        result["warning"] = "missing_cecchino_output"
        return result

    comp = db.get(Competition, int(row.competition_id))
    local_fx = db.get(Fixture, int(row.local_fixture_id))
    if comp is None or local_fx is None:
        result["warning"] = "local_fixture_or_competition_not_found"
        return result

    if refresh_bookmaker_odds:
        refresh_result = refresh_betfair_odds_for_fixture(
            db,
            row,
            force=True,
            rebuild_kpi=False,
        )
        if refresh_result.get("status") not in ("ok",):
            result["warning"] = f"betfair_refresh_failed:{refresh_result.get('code')}"
            return result
        db.refresh(row)

    try:
        calc = calculate_and_persist_for_fixture(db, comp, local_fx, persist=False)
    except Exception as exc:
        logger.exception("Cecchino recompute calc failed fixture=%s", row.id)
        result["warning"] = f"calc_error:{exc!s}"[:200]
        return result

    if calc.get("status") != "ok":
        result["warning"] = str(calc.get("code") or calc.get("message") or "calculation_error")
        return result

    cecchino_output = dict(calc.get("output") or {})
    goal_ctx = build_goal_market_contexts(db, local_fx)
    cecchino_output["goal_markets"] = build_goal_market_cecchino_odds(
        db,
        local_fx,
        goal_ctx,
    )
    rebuilt = rebuild_signals_matrix_for_output(
        cecchino_output,
        sample_home_away_split=sample_home_away_split_from_stats(row.stats_snapshot_json),
    )
    if isinstance(rebuilt, dict) and rebuilt.get("status") == "available":
        cecchino_output["signals_matrix"] = rebuilt

    betfair_payload = _load_betfair_payload(
        db,
        row,
        use_existing=use_existing_bookmaker_odds or not refresh_bookmaker_odds,
    )
    kpi_panel = build_cecchino_kpi_panel_v2_betfair(
        final_odds=cecchino_output.get("final") or {},
        betfair_payload=betfair_payload,
        goal_markets=cecchino_output.get("goal_markets"),
    )
    meta = read_odds_meta(row.odds_snapshot_json)
    if meta:
        kpi_panel["odds_meta"] = meta

    existing_prev = None
    if isinstance(row.cecchino_output_json, dict):
        existing_prev = row.cecchino_output_json.get("purchasability_preview")
    snap_at = None
    snap_src = None
    snap_verified = False
    if isinstance(meta, dict):
        for fld in ("odds_fetched_at", "fetched_at", "snapshot_at"):
            if meta.get(fld):
                snap_at = meta.get(fld)
                snap_src = f"odds_meta.{fld}"
                snap_verified = True
                break
    attach_purchasability_preview_to_output(
        cecchino_output=cecchino_output,
        kpi_panel=kpi_panel,
        fixture_meta={
            "today_fixture_id": int(row.id),
            "local_fixture_id": row.local_fixture_id,
            "provider_fixture_id": row.provider_fixture_id,
            "competition_id": row.competition_id,
            "scan_date": row.scan_date,
            "kickoff": row.kickoff,
        },
        snapshot_info={
            "snapshot_at": snap_at,
            "snapshot_source": snap_src,
            "snapshot_fidelity": (
                "verified_panel_odds_meta" if snap_verified else "missing"
            ),
            "snapshot_timestamp_verified": snap_verified,
        },
        existing_preview=existing_prev if isinstance(existing_prev, dict) else None,
    )
    existing_bal = None
    if isinstance(row.cecchino_output_json, dict):
        existing_bal = row.cecchino_output_json.get("balance_v5_monitoring")
    attach_balance_v5_monitoring_to_output(
        cecchino_output=cecchino_output,
        kpi_panel=kpi_panel,
        fixture_meta={
            "today_fixture_id": int(row.id),
            "local_fixture_id": row.local_fixture_id,
            "provider_fixture_id": row.provider_fixture_id,
            "competition_id": row.competition_id,
            "scan_date": row.scan_date,
            "kickoff": row.kickoff,
        },
        snapshot_info={
            "snapshot_at": snap_at,
            "snapshot_source": snap_src,
            "snapshot_fidelity": (
                "verified_panel_odds_meta" if snap_verified else "missing"
            ),
            "snapshot_timestamp_verified": snap_verified,
        },
        existing_monitoring=existing_bal if isinstance(existing_bal, dict) else None,
    )

    leakage_status = _extract_leakage_status(row.stats_snapshot_json)
    combined_warnings: list[str] = list(row.warnings_json or [])
    for w in cecchino_output.get("warnings") or []:
        combined_warnings.append(str(w))
    for w in (cecchino_output.get("final") or {}).get("warnings") or []:
        combined_warnings.append(str(w))

    eligibility = validate_cecchino_today_final_eligibility(
        odds_snapshot=row.odds_snapshot_json,
        stats_snapshot=row.stats_snapshot_json,
        cecchino_output=cecchino_output,
        kpi_panel=kpi_panel,
        warnings=combined_warnings,
        leakage_status=leakage_status,
        calc_status=str(calc.get("calculation_status") or ""),
    )

    row.cecchino_output_json = cecchino_output
    row.kpi_panel_json = kpi_panel
    row.cecchino_status = str(calc.get("calculation_status") or "")
    row.eligibility_status = (
        ELIGIBILITY_ELIGIBLE if eligibility.is_eligible else eligibility.eligibility_status
    )
    row.eligibility_reason = eligibility.eligibility_reason
    row.blocking_reasons_json = eligibility.blocking_reasons
    row.warnings_json = eligibility.warnings
    row.stats_status = "ok" if eligibility.is_eligible else row.stats_status

    if eligibility.is_eligible and ensure_xg:
        maybe_ensure_xg_for_eligible_row(db, row)
        result["xg_ensured"] = True
    elif eligibility.is_eligible and not ensure_xg:
        result["warning"] = (result.get("warning") or "") + ";xg_skipped_no_external_api"
        result["warning"] = result["warning"].lstrip(";")

    result["recomputed"] = True
    result["kpi_recomputed"] = True

    if force_remap_signals:
        _ensure_signals_matrix_on_row(row, force_rebuild=True)

    if sync_signal_activations and eligibility.is_eligible:
        sync_counts = sync_cecchino_signal_activations(db, int(row.id))
        result["signals_synced"] = (
            sync_counts.get("created", 0)
            + sync_counts.get("updated", 0)
        )
        result["signals_deactivated"] = sync_counts.get("deactivated", 0)

    if evaluate_signals_after and eligibility.is_eligible:
        eval_counts = evaluate_activations_for_fixture(db, int(row.id))
        result["signals_evaluated"] = eval_counts.get("evaluated", 0)

    if eligibility.is_eligible:
        try:
            from app.services.cecchino.cecchino_purchasability_validation import (
                sync_purchasability_validation_for_fixture,
            )

            with db.begin_nested():
                sync_purchasability_validation_for_fixture(db, int(row.id))
        except Exception:
            logger.exception(
                "purchasability validation sync skipped fixture_id=%s", row.id
            )
        try:
            from app.services.cecchino.cecchino_balance_v5_empirical import (
                upsert_balance_empirical_record,
            )

            with db.begin_nested():
                upsert_balance_empirical_record(db, fixture=row, commit=False)
        except Exception:
            logger.exception(
                "balance empirical upsert skipped fixture_id=%s", row.id
            )

    return result


def recompute_cecchino_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    refresh_bookmaker_odds: bool = False,
    use_existing_bookmaker_odds: bool = True,
    force_remap_signals: bool = True,
    sync_signal_activations: bool = True,
    evaluate_signals_after: bool = True,
) -> dict[str, Any]:
    """Ricalcola tutte le fixture Cecchino Today nel range date."""
    rows = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
                CecchinoTodayFixture.cecchino_output_json.isnot(None),
            ),
        ).all(),
    )

    warnings: list[str] = []
    fixtures_recomputed = 0
    kpi_recomputed = 0
    signals_synced = 0
    signals_deactivated = 0
    signals_evaluated = 0

    for row in rows:
        item = recompute_today_fixture_offline(
            db,
            row,
            refresh_bookmaker_odds=refresh_bookmaker_odds,
            use_existing_bookmaker_odds=use_existing_bookmaker_odds,
            force_remap_signals=force_remap_signals,
            sync_signal_activations=sync_signal_activations,
            evaluate_signals_after=evaluate_signals_after,
        )
        if item.get("recomputed"):
            fixtures_recomputed += 1
        if item.get("kpi_recomputed"):
            kpi_recomputed += 1
        signals_synced += int(item.get("signals_synced") or 0)
        signals_deactivated += int(item.get("signals_deactivated") or 0)
        signals_evaluated += int(item.get("signals_evaluated") or 0)
        if item.get("warning"):
            warnings.append(f"fixture_{row.id}:{item['warning']}")

    if force_remap_signals:
        remap_under_over_activations_in_range(db, date_from=date_from, date_to=date_to)

    db.commit()

    try:
        from app.services.cecchino.cecchino_balance_v5_readiness import (
            BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING,
            safe_upsert_balance_readiness_daily_snapshot,
        )

        readiness_out = safe_upsert_balance_readiness_daily_snapshot(
            phase="after_recompute",
        )
        if readiness_out.get("status") == "skipped":
            code = str(
                readiness_out.get("warning_code")
                or BALANCE_READINESS_SNAPSHOT_FAILED_NON_BLOCKING
            )
            if code not in warnings:
                warnings.append(code)
    except Exception:
        logger.exception("balance readiness snapshot skipped after recompute")

    # ICM è derivato a read-time da kpi_panel + final: il ricalcolo KPI lo aggiorna implicitamente.
    return {
        "status": "ok",
        "fixtures_found": len(rows),
        "fixtures_recomputed": fixtures_recomputed,
        "kpi_recomputed": kpi_recomputed,
        "signals_synced": signals_synced,
        "signals_deactivated": signals_deactivated,
        "signals_evaluated": signals_evaluated,
        "warnings": warnings[:100],
        "icm_note": "ICM ricalcolato implicitamente al successivo GET quando recompute_kpi=true",
    }
