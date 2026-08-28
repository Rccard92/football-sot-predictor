"""Executor scansione storica Cecchino Lab V3 — congelato, invariato semanticamente.

Run #1/#2/#3 e resume su scan_version v3 usano esclusivamente questo modulo.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_RUNNING,
    CecchinoLabHistoricalScanRun,
)
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
    HISTORICAL_SCAN_VERSION,
    PARSER_VERSION,
    SCAN_BATCH_SIZE,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import build_match_quote_bundle
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    build_lab_prematch_contexts,
    compute_cecchino_from_contexts,
    compute_goal_markets_from_contexts,
    lab_match_to_proxy,
    match_sort_key,
    sha256_prematch_payload,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_eligibility import (
    ELIGIBLE_CORE,
    evaluate_historical_eligibility,
)
from app.services.cecchino_data_lab.historical_goal_intensity import (
    MODULE_VERSION as GI_MODULE_VERSION,
    build_historical_goal_intensity,
)
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_historical_balance_v5,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_purchasability import (
    FORMULA_VERSION as PURCH_FORMULA_VERSION,
    build_historical_purchasability,
)
from app.services.cecchino_data_lab.historical_settlement import (
    empty_settlement_summary,
    settle_historical_markets,
    settlement_summary,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    build_historical_signal_models,
)

logger = logging.getLogger(__name__)


def _rating_band_for_summary(rating: Any) -> str | None:
    from app.services.cecchino_data_lab.historical_analytics_agg import rating_band_dashboard

    if rating is None:
        return None
    band = rating_band_dashboard(rating)
    return None if band == "unavailable" else band


def _purch_band_for_summary(score: Any) -> str | None:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s < 20:
        return "0-19"
    if s < 40:
        return "20-39"
    if s < 60:
        return "40-59"
    if s < 80:
        return "60-79"
    return "80-100"


def _empty_profit_bucket() -> dict[str, Any]:
    return {
        "sample_size": 0,
        "real_quote_count": 0,
        "derived_quote_count": 0,
        "real_profit_1u": 0.0,
        "synthetic_profit_1u": 0.0,
    }


def _finalize_profit_bucket(b: dict[str, Any]) -> dict[str, Any]:
    real_n = int(b["real_quote_count"])
    der_n = int(b["derived_quote_count"])
    real_p = round(float(b["real_profit_1u"]), 4)
    synth_p = round(float(b["synthetic_profit_1u"]), 4)
    return {
        "sample_size": int(b["sample_size"]),
        "real_quote_count": real_n,
        "derived_quote_count": der_n,
        "real_profit_1u": real_p,
        "synthetic_profit_1u": synth_p,
        "real_roi_pct": round(100.0 * real_p / real_n, 2) if real_n else None,
        "synthetic_roi_pct": round(100.0 * synth_p / der_n, 2) if der_n else None,
    }


def _bump_profit_bucket(b: dict[str, Any], *, real: float | None, synthetic: float | None) -> None:
    b["sample_size"] += 1
    if real is not None:
        b["real_quote_count"] += 1
        b["real_profit_1u"] += float(real)
    if synthetic is not None:
        b["derived_quote_count"] += 1
        b["synthetic_profit_1u"] += float(synthetic)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_prior_module_rows(
    db: Session,
    *,
    run_id: int,
    before_kickoff: datetime | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Carica feature GI e KPI delle eligible_core precedenti (deterministico su resume)."""
    q = (
        select(CecchinoLabHistoricalMatchSnapshot)
        .where(
            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == ELIGIBLE_CORE,
        )
        .order_by(
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc(),
            CecchinoLabHistoricalMatchSnapshot.lab_match_id.asc(),
        )
    )
    snaps = list(db.scalars(q).all())
    gi_rows: list[dict[str, Any]] = []
    kpi_panels: list[dict[str, Any]] = []
    for s in snaps:
        if before_kickoff is not None and s.kickoff_at is not None:
            if not (s.kickoff_at < before_kickoff):
                continue
        gi = s.goal_intensity_compatibility_json if isinstance(s.goal_intensity_compatibility_json, dict) else {}
        feat_row = gi.get("feature_row_for_profile")
        if isinstance(feat_row, dict) and feat_row.get("features"):
            gi_rows.append(feat_row)
        kpi = s.historical_kpi_json if isinstance(s.historical_kpi_json, dict) else None
        if kpi:
            kpi_panels.append(kpi)
    return gi_rows, kpi_panels


def _signals_prematch_for_hash(signals: dict[str, Any]) -> dict[str, Any]:
    """Esclude settlement/won/profit dall'hash pre-match."""
    if not isinstance(signals, dict):
        return {}
    models_out: dict[str, Any] = {}
    for key, block in (signals.get("models") or {}).items():
        if not isinstance(block, dict):
            continue
        models_out[key] = {
            "meta": block.get("meta"),
            "weights": block.get("weights"),
            "final": block.get("final"),
            "matrix": block.get("matrix"),
            "active_signals": block.get("active_signals"),
        }
    return {
        "default_model_key": signals.get("default_model_key"),
        "default_matrix": signals.get("default_matrix"),
        "models": models_out,
    }


def execute_historical_scan_run_v3(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        if not run:
            return
        if run.cancel_requested:
            run.status = STATUS_CANCELLED
            run.completed_at = _utcnow()
            db.commit()
            return

        run.status = STATUS_RUNNING
        run.started_at = run.started_at or _utcnow()
        db.commit()

        season_label = run.season_label
        datasets = list(
            db.scalars(
                select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season_label)
            ).all()
        )
        ds_by_id = {int(d.id): d for d in datasets}
        competitions = sorted({d.competition_name for d in datasets})

        done_ids = set(
            db.scalars(
                select(CecchinoLabHistoricalMatchSnapshot.lab_match_id).where(
                    CecchinoLabHistoricalMatchSnapshot.run_id == run_id
                )
            ).all()
        )

        policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
        max_matches_cap = policy.get("max_matches")
        try:
            max_matches_cap = int(max_matches_cap) if max_matches_cap is not None else None
        except (TypeError, ValueError):
            max_matches_cap = None
        pilot_strategy = policy.get("pilot_strategy")
        eligible_per_comp = policy.get("eligible_per_competition")
        try:
            eligible_per_comp = int(eligible_per_comp) if eligible_per_comp is not None else None
        except (TypeError, ValueError):
            eligible_per_comp = None

        is_balanced = pilot_strategy == HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP
        competitions_total = len(competitions)
        competitions_completed = 0
        batch_count = 0
        stop_for_pilot = False

        def _write_progress(
            *,
            current_comp: str | None,
            eligible_in_comp: int,
            comps_done: int,
        ) -> dict[str, Any]:
            if is_balanced and eligible_per_comp:
                eligible_target = int(eligible_per_comp) * competitions_total
                eligible_collected = int(run.matches_eligible_core or 0)
            else:
                eligible_target = int(run.matches_total or 0)
                eligible_collected = int(run.matches_eligible_core or 0)
            detail = {
                "competitions_completed": comps_done,
                "competitions_total": competitions_total,
                "eligible_collected": eligible_collected,
                "eligible_target": eligible_target,
                "matches_processed": int(run.matches_processed or 0),
                "matches_excluded": int(run.matches_excluded or 0),
                "matches_error": int(run.matches_error or 0),
                "current_competition": current_comp,
                "eligible_in_current_competition": (
                    None if current_comp is None else eligible_in_comp
                ),
                "eligible_per_competition_target": eligible_per_comp,
            }
            pol = dict(run.module_policy_json or {})
            pol["progress_detail"] = detail
            run.module_policy_json = pol
            return detail

        for comp in competitions:
            if stop_for_pilot or _is_cancelled(db, run_id):
                break
            comp_datasets = [d for d in datasets if d.competition_name == comp]
            comp_ds_ids = [int(d.id) for d in comp_datasets]
            matches = list(
                db.scalars(
                    select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id.in_(comp_ds_ids))
                ).all()
            )
            matches.sort(key=match_sort_key)
            competition_id = abs(hash(comp)) % (10**9) + 1
            proxies = sort_proxies(
                [lab_match_to_proxy(m, competition_id=competition_id) for m in matches]
            )
            proxy_by_id = {int(p.id): p for p in proxies}

            existing_comp_snaps = list(
                db.scalars(
                    select(CecchinoLabHistoricalMatchSnapshot).where(
                        CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
                        CecchinoLabHistoricalMatchSnapshot.competition_name == comp,
                    )
                ).all()
            )
            eligible_in_comp = sum(
                1
                for s in existing_comp_snaps
                if s.historical_eligibility_status == ELIGIBLE_CORE
            )

            for order_idx, m in enumerate(matches):
                if int(m.id) in done_ids:
                    continue
                if (
                    is_balanced
                    and eligible_per_comp is not None
                    and eligible_in_comp >= eligible_per_comp
                ):
                    break
                if (
                    max_matches_cap is not None
                    and not is_balanced
                    and int(run.matches_processed or 0) >= max_matches_cap
                ):
                    stop_for_pilot = True
                    break
                if _is_cancelled(db, run_id):
                    break
                try:
                    _process_one_match(
                        db,
                        run=run,
                        match=m,
                        dataset=ds_by_id[int(m.dataset_id)],
                        competition_name=comp,
                        competition_ordered=proxies,
                        target_proxy=proxy_by_id[int(m.id)],
                        chronological_order=order_idx,
                    )
                    done_ids.add(int(m.id))
                    last = db.scalars(
                        select(CecchinoLabHistoricalMatchSnapshot)
                        .where(
                            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
                            CecchinoLabHistoricalMatchSnapshot.lab_match_id == int(m.id),
                        )
                        .limit(1)
                    ).first()
                    if last and last.historical_eligibility_status == ELIGIBLE_CORE:
                        eligible_in_comp += 1
                except Exception as exc:
                    logger.exception("historical scan match error run=%s match=%s", run_id, m.id)
                    _persist_error_snapshot(
                        db,
                        run=run,
                        match=m,
                        dataset=ds_by_id[int(m.dataset_id)],
                        competition_name=comp,
                        chronological_order=order_idx,
                        error=exc,
                    )
                    run.matches_error = int(run.matches_error or 0) + 1

                run.matches_processed = int(run.matches_processed or 0) + 1
                run.current_match_id = int(m.id)
                run.current_dataset_id = int(m.dataset_id)
                run.current_competition = comp

                _write_progress(
                    current_comp=comp,
                    eligible_in_comp=eligible_in_comp,
                    comps_done=competitions_completed,
                )

                if is_balanced:
                    target_elig = max(int(run.matches_total or 0), 1)
                    collected = int(run.matches_eligible_core or 0)
                    run.progress_pct = Decimal(
                        str(round(100.0 * min(collected, target_elig) / target_elig, 1))
                    )
                else:
                    total = max(int(run.matches_total or 0), 1)
                    run.progress_pct = Decimal(
                        str(round(100.0 * int(run.matches_processed) / total, 1))
                    )
                batch_count += 1
                if batch_count >= SCAN_BATCH_SIZE:
                    db.commit()
                    batch_count = 0
                    db.refresh(run)
                    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
                    max_matches_cap = policy.get("max_matches")
                    try:
                        max_matches_cap = (
                            int(max_matches_cap) if max_matches_cap is not None else None
                        )
                    except (TypeError, ValueError):
                        max_matches_cap = None

            competition_done = False
            if is_balanced and eligible_per_comp is not None and eligible_in_comp >= eligible_per_comp:
                competition_done = True
            elif not is_balanced:
                competition_done = True

            if competition_done:
                competitions_completed += 1
                _write_progress(
                    current_comp=None,
                    eligible_in_comp=0,
                    comps_done=competitions_completed,
                )
                run.current_competition = None

            db.commit()

        db.refresh(run)
        if run.cancel_requested or run.status == STATUS_CANCELLED:
            run.status = STATUS_CANCELLED
        else:
            final_detail = _write_progress(
                current_comp=None,
                eligible_in_comp=0,
                comps_done=competitions_total,
            )
            if is_balanced:
                final_detail["competitions_completed"] = competitions_total
                final_detail["eligible_collected"] = int(run.matches_eligible_core or 0)
                pol = dict(run.module_policy_json or {})
                pol["progress_detail"] = final_detail
                run.module_policy_json = pol
            run.current_competition = None

            summary = build_run_summary_v3(db, run_id)
            policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
            summary["run_scope"] = policy.get("run_scope") or "full"
            summary["is_partial_run"] = bool(policy.get("is_partial_run"))
            summary["not_full_season_report"] = bool(policy.get("not_full_season_report"))
            summary["max_matches"] = policy.get("max_matches")
            summary["pilot_strategy"] = policy.get("pilot_strategy")
            summary["eligible_per_competition"] = policy.get("eligible_per_competition")
            summary["progress_detail"] = policy.get("progress_detail")
            summary["source_git_commit"] = run.source_git_commit
            summary["source_git_commit_source"] = getattr(run, "source_git_commit_source", None)
            summary["source_revision_status"] = getattr(run, "source_revision_status", None)
            run.summary_json = summary
            run.status = (
                STATUS_COMPLETED_WITH_WARNINGS
                if int(run.matches_error or 0) > 0
                else STATUS_COMPLETED
            )
        run.completed_at = _utcnow()
        run.progress_pct = Decimal("100.0") if run.status != STATUS_CANCELLED else run.progress_pct
        db.commit()
    except Exception as exc:
        logger.exception("historical scan run failed id=%s", run_id)
        try:
            run = db.get(CecchinoLabHistoricalScanRun, run_id)
            if run:
                run.status = STATUS_FAILED
                run.error_json = {"message": str(exc)[:500], "type": type(exc).__name__}
                run.completed_at = _utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _is_cancelled(db: Session, run_id: int) -> bool:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    return bool(run and (run.cancel_requested or run.status == STATUS_CANCELLED))


def _process_one_match(
    db: Session,
    *,
    run: CecchinoLabHistoricalScanRun,
    match: CecchinoLabMatch,
    dataset: CecchinoLabDataset,
    competition_name: str,
    competition_ordered: list,
    target_proxy: Any,
    chronological_order: int,
) -> None:
    warnings: list[str] = []
    contexts = build_lab_prematch_contexts(
        competition_ordered=competition_ordered,
        target=target_proxy,
    )
    cecchino_output = compute_cecchino_from_contexts(contexts)
    goal_markets = compute_goal_markets_from_contexts(contexts)
    under_odd = None
    under_block = (goal_markets or {}).get("UNDER_2_5") or {}
    if under_block.get("final_odd") is not None:
        under_odd = float(under_block["final_odd"])
        from app.services.cecchino.cecchino_constants import PICCHETTO_KEY_HOME_AWAY

        meta = contexts.sample_meta.get(PICCHETTO_KEY_HOME_AWAY) or {}
        sample_split = int(meta.get("home_sample_count") or 0) + int(
            meta.get("away_sample_count") or 0
        )
        cecchino_output["signals_matrix"] = rebuild_signals_with_under(
            final=cecchino_output.get("final") or {},
            sample_home_away_split=sample_split,
            under_2_5_cecchino_odd=under_odd,
        )

    quote_bundle = build_match_quote_bundle(match)
    final = cecchino_output.get("final") or {}
    kpi = build_historical_kpi_panel_bet365(
        final_odds=final,
        match=match,
        goal_markets=goal_markets,
        quote_bundle=quote_bundle,
    )
    balance = build_historical_balance_v5(
        cecchino_final=final,
        goal_markets=goal_markets,
        kpi_panel=kpi,
        identity={
            "home_team": match.home_team,
            "away_team": match.away_team,
            "competition": competition_name,
            "season_label": run.season_label,
        },
    )
    input_snapshot = build_input_snapshot(contexts)

    prior_gi_rows, prior_kpi_panels = _load_prior_module_rows(
        db, run_id=int(run.id), before_kickoff=match.kickoff_at
    )
    gi_payload = build_historical_goal_intensity(
        input_snapshot=input_snapshot,
        contexts=contexts,
        competition_ordered=competition_ordered,
        target=target_proxy,
        prior_feature_rows=prior_gi_rows,
    )
    purch_payload = build_historical_purchasability(
        kpi_panel=kpi,
        quote_bundle=quote_bundle,
        prior_kpi_panels=prior_kpi_panels,
        cutoff=match.kickoff_at.isoformat() if match.kickoff_at else None,
    )

    signals = build_historical_signal_models(
        cecchino_output=cecchino_output,
        quote_bundle=quote_bundle,
        under_2_5_cecchino_odd=under_odd,
        contexts=contexts,
        match=None,
        settle=False,
    )

    elig = evaluate_historical_eligibility(
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
        contexts=contexts,
        cecchino_output=cecchino_output,
    )
    core_eligible = bool(elig.get("core_eligible"))

    pre_match_payload = {
        "identity": {
            "lab_match_id": int(match.id),
            "competition_name": competition_name,
            "season_label": run.season_label,
            "kickoff_at": match.kickoff_at.isoformat() if match.kickoff_at else None,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "chronological_order": chronological_order,
        },
        "input_snapshot": input_snapshot,
        "cecchino_output": {
            "picchetti": cecchino_output.get("picchetti"),
            "final": final,
            "status": cecchino_output.get("status"),
            "warnings": cecchino_output.get("warnings"),
        },
        "goal_markets": {
            k: {
                "final_odd": (v or {}).get("final_odd"),
                "status": (v or {}).get("status"),
                "formula_version": (v or {}).get("formula_version"),
            }
            for k, v in (goal_markets or {}).items()
        },
        "historical_kpi": kpi,
        "signals_matrix": _signals_prematch_for_hash(signals),
        "balance_v5": balance,
        "goal_intensity": gi_payload,
        "purchasability": purch_payload,
        "quote_sources": {
            "counts": quote_bundle.get("counts"),
            "family_1x2": quote_bundle.get("family_1x2"),
            "family_ou25": quote_bundle.get("family_ou25"),
            "quotes": {
                mk: {
                    "value": (qv or {}).get("value"),
                    "source_type": (qv or {}).get("source_type"),
                    "is_real_book_quote": (qv or {}).get("is_real_book_quote"),
                    "is_derived": (qv or {}).get("is_derived"),
                    "derivation_method": (qv or {}).get("derivation_method"),
                }
                for mk, qv in (quote_bundle.get("quotes") or {}).items()
            },
        },
        "module_versions": {
            "scan_version": HISTORICAL_SCAN_VERSION,
            "parser_version": PARSER_VERSION,
            "kpi_version": (kpi or {}).get("version") if isinstance(kpi, dict) else None,
            "goal_intensity_module": GI_MODULE_VERSION,
            "goal_intensity_execution": gi_payload.get("execution_status"),
            "goal_intensity_parity": gi_payload.get("parity_status"),
            "purchasability_module": PURCH_FORMULA_VERSION,
            "purchasability_execution": purch_payload.get("execution_status"),
            "purchasability_parity": purch_payload.get("parity_status"),
            "purchasability_profile_hash": (purch_payload.get("normalization_profile") or {}).get(
                "hash"
            ),
            "signal_models": "A-F",
            "source_git_commit": run.source_git_commit,
            "source_revision_status": getattr(run, "source_revision_status", None),
        },
        "eligibility": {
            "status": elig.get("status"),
            "core_eligible": core_eligible,
            "reason": elig.get("reason"),
            "blocking_reasons": elig.get("blocking_reasons") or [],
        },
        "scan_version": HISTORICAL_SCAN_VERSION,
    }
    assert "result" not in pre_match_payload
    assert "fulltime" not in pre_match_payload
    assert "settlement" not in pre_match_payload
    payload_hash = sha256_prematch_payload(pre_match_payload)
    locked_at = _utcnow()

    result_json = {
        "fulltime": {"home": match.ft_home_goals, "away": match.ft_away_goals},
        "halftime": {"home": match.ht_home_goals, "away": match.ht_away_goals},
        "ft_result": match.ft_result,
        "ht_result": match.ht_result,
    }

    if core_eligible:
        signals = build_historical_signal_models(
            cecchino_output=cecchino_output,
            quote_bundle=quote_bundle,
            under_2_5_cecchino_odd=under_odd,
            contexts=contexts,
            match=match,
            settle=True,
        )
        market_rows = settle_historical_markets(
            match=match,
            kpi_panel=kpi,
            quote_bundle=quote_bundle,
            signals_json=signals,
        )
        sett_sum = settlement_summary(market_rows)
        settlement_status = "settled"
        run.matches_eligible_core = int(run.matches_eligible_core or 0) + 1
    else:
        market_rows = []
        sett_sum = empty_settlement_summary()
        settlement_status = "excluded"
        run.matches_excluded = int(run.matches_excluded or 0) + 1

    rev_warn = list((run.module_policy_json or {}).get("revision_warnings") or [])
    warnings = warnings + list(cecchino_output.get("warnings") or []) + rev_warn

    snap = CecchinoLabHistoricalMatchSnapshot(
        run_id=int(run.id),
        dataset_id=int(dataset.id),
        lab_match_id=int(match.id),
        competition_name=competition_name,
        season_label=run.season_label,
        kickoff_at=match.kickoff_at,
        home_team=match.home_team,
        away_team=match.away_team,
        chronological_order=chronological_order,
        historical_eligibility_status=elig["status"],
        historical_eligibility_reason=elig.get("reason"),
        blocking_reasons_json=elig.get("blocking_reasons") or [],
        module_availability_json={
            "core_eligible": core_eligible,
            "kpi_1x2_real_available": quote_bundle.get("kpi_1x2_real_available"),
            "kpi_ou25_real_available": quote_bundle.get("kpi_ou25_real_available"),
            "goal_intensity_execution": gi_payload.get("execution_status"),
            "goal_intensity_observation": gi_payload.get("parity_status")
            or gi_payload.get("execution_status"),
            "purchasability_execution": purch_payload.get("execution_status"),
            "purchasability_observation": purch_payload.get("parity_status")
            or purch_payload.get("execution_status"),
            "balance_observation": (
                balance.get("observation_status") if isinstance(balance, dict) else None
            ),
            "signals_observation": (
                signals.get("observation_status") if isinstance(signals, dict) else None
            ),
            "modules_do_not_block_eligibility": True,
            **(quote_bundle.get("counts") or {}),
        },
        input_snapshot_json=input_snapshot,
        cecchino_output_json=cecchino_output,
        historical_kpi_json=kpi,
        signals_json=signals,
        balance_v5_json=balance,
        goal_intensity_compatibility_json=gi_payload,
        purchasability_compatibility_json=purch_payload,
        quote_sources_json=quote_bundle,
        pre_match_payload_sha256=payload_hash,
        pre_match_locked_at=locked_at,
        result_json=result_json,
        result_attached_at=_utcnow(),
        settlement_status=settlement_status,
        settlement_summary_json=sett_sum,
        warnings_json=warnings,
    )
    db.add(snap)
    db.flush()

    for row in market_rows:
        db.add(
            CecchinoLabHistoricalMarketResult(
                run_id=int(run.id),
                match_snapshot_id=int(snap.id),
                lab_match_id=int(match.id),
                market_key=row["market_key"],
                market_label=row.get("market_label"),
                period=row.get("period"),
                line=row.get("line"),
                quota_cecchino=row.get("quota_cecchino"),
                prob_cecchino=row.get("prob_cecchino"),
                quota_book=row.get("quota_book"),
                prob_book_raw=row.get("prob_book_raw"),
                prob_book_fair=row.get("prob_book_fair"),
                quote_source_type=row.get("quote_source_type"),
                is_real_book_quote=bool(row.get("is_real_book_quote")),
                is_derived_quote=bool(row.get("is_derived_quote")),
                derivation_method=row.get("derivation_method"),
                edge_pct=row.get("edge_pct"),
                vantaggio_prob=row.get("vantaggio_prob"),
                rating=row.get("rating"),
                signal_active=bool(row.get("signal_active")),
                signal_sources_json=row.get("signal_sources_json"),
                evaluation_status=row.get("evaluation_status"),
                won=row.get("won"),
                profit_1u_real=row.get("profit_1u_real"),
                profit_1u_synthetic=row.get("profit_1u_synthetic"),
                result_reason=row.get("result_reason"),
                profit_category=row.get("profit_category"),
            )
        )


def _persist_error_snapshot(
    db: Session,
    *,
    run: CecchinoLabHistoricalScanRun,
    match: CecchinoLabMatch,
    dataset: CecchinoLabDataset,
    competition_name: str,
    chronological_order: int,
    error: Exception,
) -> None:
    snap = CecchinoLabHistoricalMatchSnapshot(
        run_id=int(run.id),
        dataset_id=int(dataset.id),
        lab_match_id=int(match.id),
        competition_name=competition_name,
        season_label=run.season_label,
        kickoff_at=match.kickoff_at,
        home_team=match.home_team,
        away_team=match.away_team,
        chronological_order=chronological_order,
        historical_eligibility_status="error",
        historical_eligibility_reason=type(error).__name__,
        blocking_reasons_json=[str(error)[:300]],
        error_json={
            "type": type(error).__name__,
            "message": str(error)[:500],
            "traceback": traceback.format_exc()[-1500:],
        },
        settlement_status="error",
    )
    db.add(snap)


def build_run_summary_v3(db: Session, run_id: int) -> dict[str, Any]:
    snaps = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id == run_id
            )
        ).all()
    )
    by_elig: dict[str, int] = {}
    for s in snaps:
        by_elig[s.historical_eligibility_status] = (
            by_elig.get(s.historical_eligibility_status, 0) + 1
        )

    analysis_snap_ids: set[int] = {
        int(s.id) for s in snaps if s.historical_eligibility_status == ELIGIBLE_CORE
    }

    markets = list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult).where(
                CecchinoLabHistoricalMarketResult.run_id == run_id
            )
        ).all()
    )
    analysis_markets = [m for m in markets if int(m.match_snapshot_id) in analysis_snap_ids]

    real_p = sum(
        float(m.profit_1u_real or 0) for m in analysis_markets if m.profit_1u_real is not None
    )
    synth_p = sum(
        float(m.profit_1u_synthetic or 0)
        for m in analysis_markets
        if m.profit_1u_synthetic is not None
    )

    by_market: dict[str, dict[str, Any]] = {}
    by_rating: dict[str, dict[str, Any]] = {}
    by_purch: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}

    snap_by_id = {int(s.id): s for s in snaps}
    for m in analysis_markets:
        mk = str(m.market_key)
        if mk not in by_market:
            by_market[mk] = _empty_profit_bucket()
        _bump_profit_bucket(
            by_market[mk],
            real=float(m.profit_1u_real) if m.profit_1u_real is not None else None,
            synthetic=(
                float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
            ),
        )
        rb = _rating_band_for_summary(m.rating)
        if rb:
            if rb not in by_rating:
                by_rating[rb] = _empty_profit_bucket()
            _bump_profit_bucket(
                by_rating[rb],
                real=float(m.profit_1u_real) if m.profit_1u_real is not None else None,
                synthetic=(
                    float(m.profit_1u_synthetic) if m.profit_1u_synthetic is not None else None
                ),
            )
        s = snap_by_id.get(int(m.match_snapshot_id))
        if s:
            purch = (
                s.purchasability_compatibility_json
                if isinstance(s.purchasability_compatibility_json, dict)
                else {}
            )
            for mk_row in purch.get("markets") or []:
                if not isinstance(mk_row, dict):
                    continue
                if mk_row.get("market_key") != m.market_key:
                    continue
                pb = _purch_band_for_summary(mk_row.get("score"))
                if pb:
                    if pb not in by_purch:
                        by_purch[pb] = _empty_profit_bucket()
                    _bump_profit_bucket(
                        by_purch[pb],
                        real=float(m.profit_1u_real) if m.profit_1u_real is not None else None,
                        synthetic=(
                            float(m.profit_1u_synthetic)
                            if m.profit_1u_synthetic is not None
                            else None
                        ),
                    )
            sigs = s.signals_json if isinstance(s.signals_json, dict) else {}
            for model_key, mblock in (sigs.get("models") or {}).items():
                if not isinstance(mblock, dict):
                    continue
                for sett in mblock.get("settlements") or []:
                    if not isinstance(sett, dict):
                        continue
                    if sett.get("target_market") != m.market_key:
                        continue
                    key = str(model_key)
                    if key not in by_model:
                        by_model[key] = _empty_profit_bucket()
                    _bump_profit_bucket(
                        by_model[key],
                        real=(
                            float(sett["real_profit_1u"])
                            if sett.get("real_profit_1u") is not None
                            else None
                        ),
                        synthetic=(
                            float(sett["synthetic_profit_1u"])
                            if sett.get("synthetic_profit_1u") is not None
                            else None
                        ),
                    )

    return {
        "matches": len(snaps),
        "eligibility_counts": by_elig,
        "eligible_core": by_elig.get(ELIGIBLE_CORE, 0),
        "markets_rows": len(analysis_markets),
        "profit_by_market": {k: _finalize_profit_bucket(v) for k, v in sorted(by_market.items())},
        "profit_by_model_A_F": {k: _finalize_profit_bucket(v) for k, v in sorted(by_model.items())},
        "profit_by_rating_band": {
            k: _finalize_profit_bucket(v) for k, v in sorted(by_rating.items())
        },
        "profit_by_purchasability_band": {
            k: _finalize_profit_bucket(v) for k, v in sorted(by_purch.items())
        },
        "technical_sum_across_all_independent_market_rows": {
            "real_profit_1u": round(real_p, 4),
            "synthetic_profit_1u": round(synth_p, 4),
            "not_a_betting_strategy": True,
            "note": (
                "Somma tecnica di righe mercato indipendenti (HOME+DRAW+AWAY+OU…); "
                "non è profitto del Cecchino né una strategia giocabile"
            ),
        },
        "note": (
            "Nessun totale globale presentato come rendimento del Cecchino. "
            "Usare profit_by_market / profit_by_model_A_F / fasce."
        ),
    }
