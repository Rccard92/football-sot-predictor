"""Orchestratore scansione storica Cecchino Lab (job resumibile, offline)."""

from __future__ import annotations

import logging
import subprocess
import threading
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
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    CecchinoLabHistoricalScanRun,
)
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_QUOTE_POLICY_VERSION,
    HISTORICAL_SCAN_CONFIRM_TOKEN,
    HISTORICAL_SCAN_VERSION,
    PARSER_VERSION,
    SCAN_BATCH_SIZE,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
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
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_goal_intensity_compatibility,
    build_historical_balance_v5,
    build_purchasability_compatibility,
    enrich_signals_with_quote_classes,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_scan_preflight import (
    STATUS_BLOCKED,
    run_historical_scan_preflight,
)
from app.services.cecchino_data_lab.historical_settlement import (
    empty_settlement_summary,
    settle_historical_markets,
    settlement_summary,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_threads: dict[int, threading.Thread] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except Exception:
        return None


def _run_scope_meta(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    return {
        "run_scope": policy.get("run_scope") or "full",
        "is_partial_run": bool(policy.get("is_partial_run")),
        "max_matches": policy.get("max_matches"),
        "module_policy": policy,
    }


def run_to_dict(run: CecchinoLabHistoricalScanRun) -> dict[str, Any]:
    meta = _run_scope_meta(run)
    return {
        "id": int(run.id),
        "season_label": run.season_label,
        "status": run.status,
        "scan_version": run.scan_version,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "current_dataset_id": run.current_dataset_id,
        "current_match_id": run.current_match_id,
        "current_competition": run.current_competition,
        "matches_total": int(run.matches_total or 0),
        "matches_processed": int(run.matches_processed or 0),
        "matches_eligible_core": int(run.matches_eligible_core or 0),
        "matches_excluded": int(run.matches_excluded or 0),
        "matches_error": int(run.matches_error or 0),
        "progress_pct": float(run.progress_pct) if run.progress_pct is not None else None,
        "preflight": run.preflight_json,
        "summary": run.summary_json,
        "error": run.error_json,
        "source_git_commit": run.source_git_commit,
        "cancel_requested": bool(run.cancel_requested),
        "run_scope": meta["run_scope"],
        "is_partial_run": meta["is_partial_run"],
        "max_matches": meta["max_matches"],
        "module_policy": meta["module_policy"],
    }


def list_historical_scans(db: Session, *, season_label: str | None = None) -> list[dict[str, Any]]:
    q = select(CecchinoLabHistoricalScanRun).order_by(CecchinoLabHistoricalScanRun.id.desc())
    if season_label:
        q = q.where(CecchinoLabHistoricalScanRun.season_label == season_label)
    return [run_to_dict(r) for r in db.scalars(q).all()]


def get_historical_scan(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    return run_to_dict(run)


def _normalize_max_matches(max_matches: Any) -> int | None:
    if max_matches is None or max_matches == "":
        return None
    try:
        value = int(max_matches)
    except (TypeError, ValueError) as exc:
        raise CecchinoLabImportError(
            "invalid_max_matches",
            "max_matches deve essere un intero positivo o null",
            status_code=400,
        ) from exc
    if value <= 0:
        raise CecchinoLabImportError(
            "invalid_max_matches",
            "max_matches deve essere un intero positivo o null",
            status_code=400,
        )
    return value


def start_historical_scan(
    db: Session,
    *,
    season_label: str,
    confirm: str | None,
    max_matches: int | None = None,
    background: bool = True,
) -> dict[str, Any]:
    if confirm != HISTORICAL_SCAN_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "confirm_required",
            f"Conferma richiesta: {HISTORICAL_SCAN_CONFIRM_TOKEN}",
            status_code=400,
        )

    normalized_max = _normalize_max_matches(max_matches)

    preflight = run_historical_scan_preflight(db, season_label=season_label)
    if preflight.get("status") == STATUS_BLOCKED:
        raise CecchinoLabImportError(
            "preflight_blocked",
            "Preflight bloccato: impossibile avviare la scansione",
            status_code=400,
            details=preflight,
        )

    active = db.scalars(
        select(CecchinoLabHistoricalScanRun).where(
            CecchinoLabHistoricalScanRun.season_label == season_label,
            CecchinoLabHistoricalScanRun.status.in_(tuple(ACTIVE_STATUSES)),
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Esiste già un run attivo (id={active.id}) per {season_label}",
            status_code=409,
            details={"active_run_id": int(active.id)},
        )

    datasets = list(
        db.scalars(
            select(CecchinoLabDataset).where(CecchinoLabDataset.season_label == season_label)
        ).all()
    )
    dataset_ids = [int(d.id) for d in datasets]
    season_match_count = (
        len(
            db.scalars(
                select(CecchinoLabMatch.id).where(CecchinoLabMatch.dataset_id.in_(dataset_ids))
            ).all()
        )
        if dataset_ids
        else 0
    )
    is_partial = normalized_max is not None
    matches_total = (
        min(season_match_count, normalized_max) if is_partial else season_match_count
    )

    run = CecchinoLabHistoricalScanRun(
        season_label=season_label,
        status=STATUS_PENDING,
        scan_version=HISTORICAL_SCAN_VERSION,
        requested_at=_utcnow(),
        matches_total=matches_total,
        quote_policy_json={
            "version": HISTORICAL_QUOTE_POLICY_VERSION,
            "bookmaker": "Bet365",
            "operational_today_bookmaker": "Betfair",
        },
        module_policy_json={
            "goal_intensity": "compatibility_only_features_export",
            "purchasability": "compatibility_only_inputs_export",
            "parser_version": PARSER_VERSION,
            "max_matches": normalized_max,
            "is_partial_run": is_partial,
            "run_scope": "pilot" if is_partial else "full",
            "season_matches_available": season_match_count,
            "note": (
                "Run parziale: non confondere con report stagione completa"
                if is_partial
                else "Run stagione completa"
            ),
        },
        preflight_json=preflight,
        source_git_commit=_git_commit(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if background:
        _spawn_worker(int(run.id))
    else:
        execute_historical_scan_run(int(run.id))
        db.refresh(run)

    return run_to_dict(run)


def resume_historical_scan(db: Session, run_id: int, *, background: bool = True) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    if run.status in (STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS):
        raise CecchinoLabImportError("run_already_completed", "Run già completato", status_code=400)
    if run.status == STATUS_CANCELLED:
        raise CecchinoLabImportError("run_cancelled", "Run cancellato", status_code=400)

    active = db.scalars(
        select(CecchinoLabHistoricalScanRun).where(
            CecchinoLabHistoricalScanRun.season_label == run.season_label,
            CecchinoLabHistoricalScanRun.status.in_(tuple(ACTIVE_STATUSES)),
            CecchinoLabHistoricalScanRun.id != run_id,
        )
    ).first()
    if active:
        raise CecchinoLabImportError(
            "duplicate_active_run",
            f"Altro run attivo sulla stagione (id={active.id})",
            status_code=409,
        )

    run.cancel_requested = False
    if run.status == STATUS_FAILED:
        run.status = STATUS_PENDING
    db.commit()

    if background:
        _spawn_worker(run_id)
    else:
        execute_historical_scan_run(run_id)
    db.refresh(run)
    return run_to_dict(run)


def cancel_historical_scan(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    run.cancel_requested = True
    if run.status in ACTIVE_STATUSES:
        run.status = STATUS_CANCELLED
        run.completed_at = _utcnow()
    db.commit()
    db.refresh(run)
    return run_to_dict(run)


def _spawn_worker(run_id: int) -> None:
    with _lock:
        t_existing = _active_threads.get(run_id)
        if t_existing and t_existing.is_alive():
            return
        t = threading.Thread(
            target=execute_historical_scan_run,
            args=(run_id,),
            name=f"cecchino-lab-hist-scan-{run_id}",
            daemon=True,
        )
        _active_threads[run_id] = t
        t.start()


def execute_historical_scan_run(run_id: int) -> None:
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

        batch_count = 0
        stop_for_pilot = False
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

            for order_idx, m in enumerate(matches):
                if int(m.id) in done_ids:
                    continue
                if max_matches_cap is not None and int(run.matches_processed or 0) >= max_matches_cap:
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

            db.commit()

        db.refresh(run)
        if run.cancel_requested or run.status == STATUS_CANCELLED:
            run.status = STATUS_CANCELLED
        else:
            summary = _build_run_summary(db, run_id)
            policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
            summary["run_scope"] = policy.get("run_scope") or "full"
            summary["is_partial_run"] = bool(policy.get("is_partial_run"))
            summary["max_matches"] = policy.get("max_matches")
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
        with _lock:
            _active_threads.pop(run_id, None)


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
    # 1) Contesti pre-match
    contexts = build_lab_prematch_contexts(
        competition_ordered=competition_ordered,
        target=target_proxy,
    )
    # 2) Cecchino + moduli (senza FT/HT target nei payload congelati)
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
    signals = enrich_signals_with_quote_classes(
        cecchino_output.get("signals_matrix") or {},
        quote_bundle,
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
    gi_compat = build_goal_intensity_compatibility(
        input_snapshot=input_snapshot,
        contexts=contexts,
    )
    purch_compat = build_purchasability_compatibility(
        kpi_panel=kpi, quote_bundle=quote_bundle
    )

    # 3) Eleggibilità
    elig = evaluate_historical_eligibility(
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
        contexts=contexts,
        cecchino_output=cecchino_output,
    )
    core_eligible = bool(elig.get("core_eligible"))

    # 4) Freeze snapshot pre-match (hash dopo tutti i moduli)
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
        "signals_matrix": signals,
        "balance_v5": balance,
        "goal_intensity": gi_compat,
        "purchasability": purch_compat,
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
            "goal_intensity_execution": gi_compat.get("execution_status"),
            "purchasability_execution": purch_compat.get("execution_status"),
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

    # 5) Dopo il lock: collega risultato
    result_json = {
        "fulltime": {"home": match.ft_home_goals, "away": match.ft_away_goals},
        "halftime": {"home": match.ht_home_goals, "away": match.ht_away_goals},
        "ft_result": match.ft_result,
        "ht_result": match.ht_result,
    }

    # 6) Settlement solo se core_eligible
    if core_eligible:
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
            **(quote_bundle.get("counts") or {}),
        },
        input_snapshot_json=input_snapshot,
        cecchino_output_json=cecchino_output,
        historical_kpi_json=kpi,
        signals_json=signals,
        balance_v5_json=balance,
        goal_intensity_compatibility_json=gi_compat,
        purchasability_compatibility_json=purch_compat,
        quote_sources_json=quote_bundle,
        pre_match_payload_sha256=payload_hash,
        pre_match_locked_at=locked_at,
        result_json=result_json,
        result_attached_at=_utcnow(),
        settlement_status=settlement_status,
        settlement_summary_json=sett_sum,
        warnings_json=warnings + list(cecchino_output.get("warnings") or []),
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


def _build_run_summary(db: Session, run_id: int) -> dict[str, Any]:
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
    markets = list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult).where(
                CecchinoLabHistoricalMarketResult.run_id == run_id
            )
        ).all()
    )
    real_p = sum(float(m.profit_1u_real or 0) for m in markets if m.profit_1u_real is not None)
    synth_p = sum(
        float(m.profit_1u_synthetic or 0) for m in markets if m.profit_1u_synthetic is not None
    )
    return {
        "matches": len(snaps),
        "eligibility_counts": by_elig,
        "eligible_core": by_elig.get(ELIGIBLE_CORE, 0),
        "markets_rows": len(markets),
        "real_profit_1u": round(real_p, 4),
        "synthetic_profit_1u": round(synth_p, 4),
        "note": "ROI reale e sintetico non vanno sommati",
    }


def list_run_matches(
    db: Session,
    run_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
    eligibility: str | None = None,
) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)
    q = (
        select(CecchinoLabHistoricalMatchSnapshot)
        .where(CecchinoLabHistoricalMatchSnapshot.run_id == run_id)
        .order_by(CecchinoLabHistoricalMatchSnapshot.chronological_order.asc().nulls_last())
    )
    if eligibility:
        q = q.where(
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == eligibility
        )
    rows = list(db.scalars(q.offset(offset).limit(limit)).all())
    return {
        "run_id": run_id,
        "items": [
            {
                "id": int(s.id),
                "lab_match_id": int(s.lab_match_id),
                "competition_name": s.competition_name,
                "kickoff_at": s.kickoff_at.isoformat() if s.kickoff_at else None,
                "home_team": s.home_team,
                "away_team": s.away_team,
                "eligibility": s.historical_eligibility_status,
                "reason": s.historical_eligibility_reason,
                "pre_match_payload_sha256": s.pre_match_payload_sha256,
                "settlement_summary": s.settlement_summary_json,
            }
            for s in rows
        ],
        "limit": limit,
        "offset": offset,
    }
