"""Executor Historical Scan V4 — stream cronologico globale, order-independent."""

from __future__ import annotations

import contextvars
import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
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
from app.services.cecchino.cecchino_balance_v5 import VERSION as BALANCE_V5_VERSION
from app.services.cecchino.cecchino_constants import (
    CECCHINO_KPI_V2_VERSION,
    CECCHINO_VERSION,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_VERSION
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    get_current_signal_contract,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_FEATURE_CONTRACT_V4,
    HISTORICAL_KPI_VERSION,
    HISTORICAL_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_QUOTE_REFERENCE_TIMING,
    HISTORICAL_SCAN_VERSION_V4,
    PARSER_VERSION,
    resolve_scan_batch_size,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import build_match_quote_bundle
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    compute_cecchino_from_contexts,
    compute_goal_markets_from_contexts,
    lab_match_to_proxy,
    match_sort_key,
    sha256_prematch_payload,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE, evaluate_historical_eligibility
from app.services.cecchino_data_lab.historical_goal_intensity import (
    FORMULA_VERSION_V4,
    MIN_ECDF_TRAIN_N,
    MODULE_VERSION_V4,
    build_historical_goal_intensity,
)
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_historical_balance_v5,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    MODULE_VERSION as PURCH_V4_MODULE,
    build_historical_purchasability_v36,
)
from app.services.cecchino_data_lab.historical_quote_observations import build_quote_observations
from app.services.cecchino_data_lab.historical_kickoff_group import (
    classify_kickoff_groups,
    group_work_by_kickoff,
    purge_partial_kickoff_snapshots,
    recompute_run_counters_from_snapshots,
    snapshot_ids_grouped_by_kickoff,
)
from app.services.cecchino_data_lab.historical_rolling_state import (
    CACHE_STRATEGY_VERSION,
    GlobalRollingStateRegistry,
)
from app.services.cecchino_data_lab.historical_scan_v4_ordering import (
    global_sort_key_v4,
    stable_competition_id_v4,
)
from app.services.cecchino_data_lab.historical_scan_v3_executor import build_run_summary_v3
from app.services.cecchino_data_lab.historical_settlement import (
    empty_settlement_summary,
    settle_historical_markets,
    settlement_summary,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    MODULE_VERSION as SIGNALS_MODULE_VERSION,
    attach_historical_signal_settlements,
    build_historical_signal_models,
)

logger = logging.getLogger(__name__)

CANCEL_CHECK_INTERVAL = 5


@dataclass
class ProcessMatchResult:
    eligibility_status: str
    core_eligible: bool
    snapshot_id: int | None = None
    deferred_gi_feature_row: dict[str, Any] | None = None
    deferred_kpi_panel: dict[str, Any] | None = None


@dataclass
class PerformanceProfile:
    elapsed_total_seconds: float = 0.0
    context_build_seconds: float = 0.0
    cecchino_seconds: float = 0.0
    kpi_seconds: float = 0.0
    balance_seconds: float = 0.0
    goal_seconds: float = 0.0
    purchasability_seconds: float = 0.0
    signals_seconds: float = 0.0
    settlement_seconds: float = 0.0
    persistence_seconds: float = 0.0
    cache_rebuild_seconds: float = 0.0
    processed_matches: int = 0
    eligible_matches: int = 0
    batch_size: int = 0
    cache_strategy_version: str = CACHE_STRATEGY_VERSION
    db_query_count_total: int = 0
    db_query_count_per_match_avg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        avg_ms = (
            1000.0 * self.elapsed_total_seconds / self.processed_matches
            if self.processed_matches
            else 0.0
        )
        return {
            "elapsed_total_seconds": round(self.elapsed_total_seconds, 3),
            "avg_ms_per_match": round(avg_ms, 2),
            "context_build_seconds": round(self.context_build_seconds, 3),
            "cecchino_seconds": round(self.cecchino_seconds, 3),
            "kpi_seconds": round(self.kpi_seconds, 3),
            "balance_seconds": round(self.balance_seconds, 3),
            "goal_seconds": round(self.goal_seconds, 3),
            "purchasability_seconds": round(self.purchasability_seconds, 3),
            "signals_seconds": round(self.signals_seconds, 3),
            "settlement_seconds": round(self.settlement_seconds, 3),
            "persistence_seconds": round(self.persistence_seconds, 3),
            "cache_rebuild_seconds": round(self.cache_rebuild_seconds, 3),
            "processed_matches": self.processed_matches,
            "eligible_matches": self.eligible_matches,
            "batch_size": self.batch_size,
            "cache_strategy_version": self.cache_strategy_version,
            "db_query_count_total": self.db_query_count_total,
            "db_query_count_per_match_avg": round(self.db_query_count_per_match_avg, 2),
        }


@dataclass
class _QueryCounter:
    count: int = 0


_query_counter_ctx: contextvars.ContextVar[_QueryCounter | None] = contextvars.ContextVar(
    "historical_scan_v4_query_counter",
    default=None,
)
_query_counter_listener_registered = False


def _ensure_v4_query_counter_listener() -> None:
    global _query_counter_listener_registered
    if _query_counter_listener_registered:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _count_v4_scan_query(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        counter = _query_counter_ctx.get()
        if counter is not None:
            counter.count += 1

    _query_counter_listener_registered = True


class _V4QueryCounterScope:
    """Conta solo query SQL eseguite nel thread/contesto del run V4 attivo."""

    def __init__(self) -> None:
        self.counter = _QueryCounter()
        self._token: contextvars.Token[_QueryCounter | None] | None = None

    def __enter__(self) -> _QueryCounter:
        _ensure_v4_query_counter_listener()
        self._token = _query_counter_ctx.set(self.counter)
        return self.counter

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _query_counter_ctx.reset(self._token)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonicalize_no_book_quote_markets_lists(signals: dict[str, Any]) -> None:
    """Ordine deterministico per no_book_quote_markets (insieme, ordine non semantico). V4-only."""

    def _sort_matrix(matrix: dict[str, Any] | None) -> None:
        if not isinstance(matrix, dict):
            return
        qc = matrix.get("quote_classification")
        if not isinstance(qc, dict):
            return
        vals = qc.get("no_book_quote_markets")
        if isinstance(vals, list):
            qc["no_book_quote_markets"] = sorted(vals)

    _sort_matrix(signals.get("default_matrix"))
    for block in (signals.get("models") or {}).values():
        if isinstance(block, dict):
            _sort_matrix(block.get("matrix"))


def _signals_prematch_for_hash(signals: dict[str, Any]) -> dict[str, Any]:
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


def _event_stats_from_match(match: CecchinoLabMatch) -> dict[str, Any]:
    return {
        "home_shots": match.home_shots,
        "away_shots": match.away_shots,
        "home_sot": match.home_shots_on_target,
        "away_sot": match.away_shots_on_target,
        "home_corners": match.home_corners,
        "away_corners": match.away_corners,
        "home_fouls": match.home_fouls,
        "away_fouls": match.away_fouls,
        "home_yellow": match.home_yellow_cards,
        "away_yellow": match.away_yellow_cards,
        "home_red": match.home_red_cards,
        "away_red": match.away_red_cards,
    }


def _group_by_kickoff(
    items: list[tuple[CecchinoLabMatch, str, CecchinoLabDataset, Any]],
) -> list[list[tuple[CecchinoLabMatch, str, CecchinoLabDataset, Any]]]:
    return group_work_by_kickoff(items, kickoff_at_getter=lambda row: row[0].kickoff_at)


def _is_cancelled(db: Session, run_id: int) -> bool:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    return bool(run and (run.cancel_requested or run.status == STATUS_CANCELLED))


def _process_one_match_v4(
    db: Session,
    *,
    run: CecchinoLabHistoricalScanRun,
    match: CecchinoLabMatch,
    dataset: CecchinoLabDataset,
    competition_name: str,
    target_proxy: Any,
    chronological_order: int,
    rolling: GlobalRollingStateRegistry,
    perf: PerformanceProfile,
    defer_rolling_updates: bool = False,
) -> ProcessMatchResult:
    t0 = time.perf_counter()
    comp_state = rolling.get_competition(competition_name)
    if comp_state is None:
        raise RuntimeError(f"missing rolling state for competition {competition_name}")

    t_ctx = time.perf_counter()
    contexts = comp_state.contexts_for(target_proxy)
    perf.context_build_seconds += time.perf_counter() - t_ctx

    t_cec = time.perf_counter()
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
    perf.cecchino_seconds += time.perf_counter() - t_cec

    quote_bundle = build_match_quote_bundle(match, policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4)
    quote_observations = build_quote_observations(match)

    t_kpi = time.perf_counter()
    final = cecchino_output.get("final") or {}
    kpi = build_historical_kpi_panel_bet365(
        final_odds=final,
        match=match,
        goal_markets=goal_markets,
        quote_bundle=quote_bundle,
    )
    perf.kpi_seconds += time.perf_counter() - t_kpi

    t_bal = time.perf_counter()
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
    perf.balance_seconds += time.perf_counter() - t_bal

    input_snapshot = build_input_snapshot(contexts)
    prior_gi_rows = rolling.prior_cache.gi_rows_before(match.kickoff_at)
    prefitted = rolling.gi_ecdf.ecdfs() if rolling.gi_ecdf.train_n() >= MIN_ECDF_TRAIN_N else None

    t_gi = time.perf_counter()
    gi_payload = build_historical_goal_intensity(
        input_snapshot=input_snapshot,
        contexts=contexts,
        competition_ordered=comp_state.all_proxies,
        target=target_proxy,
        prior_feature_rows=prior_gi_rows,
        prefitted_ecdfs=prefitted,
        module_version=MODULE_VERSION_V4,
        formula_version=FORMULA_VERSION_V4,
    )
    perf.goal_seconds += time.perf_counter() - t_gi

    t_purch = time.perf_counter()
    purch_payload = build_historical_purchasability_v36(
        kpi_panel=kpi,
        match=match,
        season_label=run.season_label,
        competition_name=competition_name,
    )
    perf.purchasability_seconds += time.perf_counter() - t_purch

    t_sig = time.perf_counter()
    signals = build_historical_signal_models(
        cecchino_output=cecchino_output,
        quote_bundle=quote_bundle,
        under_2_5_cecchino_odd=under_odd,
        contexts=contexts,
        match=None,
        settle=False,
    )
    _canonicalize_no_book_quote_markets_lists(signals)
    perf.signals_seconds += time.perf_counter() - t_sig

    elig = evaluate_historical_eligibility(
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
        contexts=contexts,
        cecchino_output=cecchino_output,
    )
    core_eligible = bool(elig.get("core_eligible"))
    signal_contract = get_current_signal_contract()

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
            "scan_version": HISTORICAL_SCAN_VERSION_V4,
            "feature_contract_version": HISTORICAL_FEATURE_CONTRACT_V4,
            "parser_version": PARSER_VERSION,
            "source_git_commit": run.source_git_commit,
            "source_revision_status": getattr(run, "source_revision_status", None),
            "cecchino_engine_version": CECCHINO_VERSION,
            "kpi_engine_version": KPI_V2_VERSION or CECCHINO_KPI_V2_VERSION,
            "kpi_lab_wrapper_version": HISTORICAL_KPI_VERSION,
            "signal_contract_version": signal_contract.get("version") if isinstance(signal_contract, dict) else None,
            "signal_formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
            "signal_module_version": SIGNALS_MODULE_VERSION,
            "balance_engine_version": balance.get("formula_version") if isinstance(balance, dict) else BALANCE_V5_VERSION,
            "goal_intensity_module_version": MODULE_VERSION_V4,
            "goal_intensity_formula_version": FORMULA_VERSION_V4,
            "goal_intensity_execution": gi_payload.get("execution_status"),
            "goal_intensity_parity": gi_payload.get("parity_status"),
            "purchasability_engine_version": purch_payload.get("formula_version"),
            "purchasability_module_version": PURCH_V4_MODULE,
            "purchasability_display_policy": purch_payload.get("display_policy"),
            "purchasability_execution": purch_payload.get("execution_status"),
            "quote_policy_version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        },
        "eligibility": {
            "status": elig.get("status"),
            "core_eligible": core_eligible,
            "reason": elig.get("reason"),
            "blocking_reasons": elig.get("blocking_reasons") or [],
        },
        "scan_version": HISTORICAL_SCAN_VERSION_V4,
    }
    assert "result" not in pre_match_payload
    assert "fulltime" not in pre_match_payload
    assert "settlement" not in pre_match_payload
    assert "quote_observations" not in pre_match_payload
    assert "movement_features" not in pre_match_payload
    payload_hash = sha256_prematch_payload(pre_match_payload)

    result_json = {
        "fulltime": {"home": match.ft_home_goals, "away": match.ft_away_goals},
        "halftime": {"home": match.ht_home_goals, "away": match.ht_away_goals},
        "ft_result": match.ft_result,
        "ht_result": match.ht_result,
        "event_stats": _event_stats_from_match(match),
    }

    t_settle = time.perf_counter()
    if core_eligible:
        signals = attach_historical_signal_settlements(
            signals,
            match=match,
            quote_bundle=quote_bundle,
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
        perf.eligible_matches += 1
    else:
        market_rows = []
        sett_sum = empty_settlement_summary()
        settlement_status = "excluded"
        run.matches_excluded = int(run.matches_excluded or 0) + 1
    perf.settlement_seconds += time.perf_counter() - t_settle

    warnings: list[str] = list(cecchino_output.get("warnings") or [])
    warnings.extend(list((run.module_policy_json or {}).get("revision_warnings") or []))

    t_persist = time.perf_counter()
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
            "purchasability_execution": purch_payload.get("execution_status"),
            "balance_observation": balance.get("observation_status") if isinstance(balance, dict) else None,
            "signals_observation": signals.get("observation_status") if isinstance(signals, dict) else None,
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
        quote_observations_json=quote_observations,
        pre_match_payload_sha256=payload_hash,
        pre_match_locked_at=_utcnow(),
        result_json=result_json,
        result_attached_at=_utcnow(),
        settlement_status=settlement_status,
        settlement_summary_json=sett_sum,
        warnings_json=warnings,
    )
    db.add(snap)
    db.flush()
    snap_id = int(snap.id)

    for row in market_rows:
        db.add(
            CecchinoLabHistoricalMarketResult(
                run_id=int(run.id),
                match_snapshot_id=snap_id,
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

    deferred_gi: dict[str, Any] | None = None
    deferred_kpi: dict[str, Any] | None = None
    if core_eligible:
        feat_row = gi_payload.get("feature_row_for_profile")
        gi_row = feat_row if isinstance(feat_row, dict) else None
        if defer_rolling_updates:
            deferred_gi = gi_row
            deferred_kpi = kpi if isinstance(kpi, dict) else None
        else:
            rolling.prior_cache.append_eligible(
                kickoff_at=match.kickoff_at,
                lab_match_id=int(match.id),
                gi_feature_row=gi_row,
                kpi_panel=kpi,
            )
            if isinstance(gi_row, dict):
                rolling.gi_ecdf.ingest_feature_row(gi_row)

    perf.persistence_seconds += time.perf_counter() - t_persist
    perf.processed_matches += 1
    _ = t0
    return ProcessMatchResult(
        eligibility_status=str(elig["status"]),
        core_eligible=core_eligible,
        snapshot_id=snap_id,
        deferred_gi_feature_row=deferred_gi,
        deferred_kpi_panel=deferred_kpi,
    )


def execute_historical_scan_run_v4(run_id: int) -> None:
    db = SessionLocal()
    perf = PerformanceProfile(batch_size=resolve_scan_batch_size())
    run_start = time.perf_counter()
    with _V4QueryCounterScope() as query_counter:
        _execute_historical_scan_run_v4_body(
            run_id,
            db=db,
            perf=perf,
            run_start=run_start,
            query_counter=query_counter,
        )


def _execute_historical_scan_run_v4_body(
    run_id: int,
    *,
    db: Session,
    perf: PerformanceProfile,
    run_start: float,
    query_counter: _QueryCounter,
) -> None:
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
        comp_proxies: dict[str, list] = {}
        competitions = sorted({d.competition_name for d in datasets})
        for comp in competitions:
            comp_ds_ids = [int(d.id) for d in datasets if d.competition_name == comp]
            matches = list(
                db.scalars(
                    select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id.in_(comp_ds_ids))
                ).all()
            )
            cid = stable_competition_id_v4(comp)
            comp_proxies[comp] = sort_proxies(
                [lab_match_to_proxy(m, competition_id=cid) for m in matches]
            )

        all_work: list[tuple[CecchinoLabMatch, str, CecchinoLabDataset, Any]] = []
        for comp in competitions:
            comp_ds_ids = [int(d.id) for d in datasets if d.competition_name == comp]
            matches = list(
                db.scalars(
                    select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id.in_(comp_ds_ids))
                ).all()
            )
            matches.sort(key=match_sort_key)
            cid = stable_competition_id_v4(comp)
            proxy_by_id = {
                int(m.id): lab_match_to_proxy(m, competition_id=cid) for m in matches
            }
            for m in matches:
                all_work.append((m, comp, ds_by_id[int(m.dataset_id)], proxy_by_id[int(m.id)]))

        all_work.sort(key=global_sort_key_v4)

        snapshot_by_kickoff = snapshot_ids_grouped_by_kickoff(db, run_id=run_id)
        complete_done_ids, partial_ids = classify_kickoff_groups(all_work, snapshot_by_kickoff)
        if partial_ids:
            purge_partial_kickoff_snapshots(
                db,
                run_id=run_id,
                partial_lab_match_ids=partial_ids,
            )
            counters = recompute_run_counters_from_snapshots(db, run_id=run_id)
            run.matches_processed = counters["matches_processed"]
            run.matches_eligible_core = counters["matches_eligible_core"]
            run.matches_excluded = counters["matches_excluded"]
            run.matches_error = counters["matches_error"]
            db.commit()
            snapshot_by_kickoff = snapshot_ids_grouped_by_kickoff(db, run_id=run_id)
            complete_done_ids, _partial = classify_kickoff_groups(all_work, snapshot_by_kickoff)

        t_cache = time.perf_counter()
        rolling = GlobalRollingStateRegistry.from_resume(
            db,
            run_id=run_id,
            comp_proxies=comp_proxies,
            complete_lab_match_ids=complete_done_ids,
        )
        for comp, proxies in comp_proxies.items():
            rolling.register_competition(comp, proxies)
        perf.cache_rebuild_seconds = time.perf_counter() - t_cache

        done_ids = set(complete_done_ids)

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
        eligible_per_comp_counts: dict[str, int] = {c: 0 for c in competitions}
        for comp in competitions:
            eligible_per_comp_counts[comp] = sum(
                1
                for s in db.scalars(
                    select(CecchinoLabHistoricalMatchSnapshot).where(
                        CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
                        CecchinoLabHistoricalMatchSnapshot.competition_name == comp,
                        CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status
                        == ELIGIBLE_CORE,
                    )
                ).all()
            )

        pending = [w for w in all_work if int(w[0].id) not in done_ids]
        groups = _group_by_kickoff(pending)
        stop_for_pilot = False
        counters = recompute_run_counters_from_snapshots(db, run_id=run_id)
        global_order = int(counters["next_chronological_order"])

        for group in groups:
            if stop_for_pilot or _is_cancelled(db, run_id):
                break
            if (
                max_matches_cap is not None
                and not is_balanced
                and int(run.matches_processed or 0) >= max_matches_cap
            ):
                stop_for_pilot = True
                break

            savepoint = db.begin_nested()
            try:
                group_proxies_by_comp: dict[str, list] = {}
                group_processed_ids: set[int] = set()
                deferred_eligible: list[tuple[Any, int, dict[str, Any] | None, dict[str, Any] | None]] = []

                for m, comp, dataset, proxy in group:
                    if int(m.id) in done_ids:
                        continue
                    if (
                        is_balanced
                        and eligible_per_comp is not None
                        and eligible_per_comp_counts.get(comp, 0) >= eligible_per_comp
                    ):
                        continue
                    try:
                        result = _process_one_match_v4(
                            db,
                            run=run,
                            match=m,
                            dataset=dataset,
                            competition_name=comp,
                            target_proxy=proxy,
                            chronological_order=global_order,
                            rolling=rolling,
                            perf=perf,
                            defer_rolling_updates=True,
                        )
                        group_processed_ids.add(int(m.id))
                        if result.core_eligible:
                            eligible_per_comp_counts[comp] = (
                                eligible_per_comp_counts.get(comp, 0) + 1
                            )
                        if result.core_eligible and isinstance(result.deferred_gi_feature_row, dict):
                            deferred_eligible.append(
                                (
                                    m.kickoff_at,
                                    int(m.id),
                                    result.deferred_gi_feature_row,
                                    result.deferred_kpi_panel,
                                )
                            )
                    except Exception as exc:
                        logger.exception(
                            "historical scan v4 match error run=%s match=%s", run_id, m.id
                        )
                        _persist_error_snapshot_v4(
                            db,
                            run=run,
                            match=m,
                            dataset=dataset,
                            competition_name=comp,
                            chronological_order=global_order,
                            error=exc,
                        )
                        group_processed_ids.add(int(m.id))
                        run.matches_error = int(run.matches_error or 0) + 1

                    run.matches_processed = int(run.matches_processed or 0) + 1
                    run.current_match_id = int(m.id)
                    run.current_dataset_id = int(m.dataset_id)
                    run.current_competition = comp
                    global_order += 1

                    total = max(int(run.matches_total or 0), 1)
                    run.progress_pct = Decimal(
                        str(round(100.0 * int(run.matches_processed) / total, 1))
                    )

                for m, comp, _, proxy in group:
                    if int(m.id) not in group_processed_ids:
                        continue
                    group_proxies_by_comp.setdefault(comp, []).append(proxy)

                for comp, proxies in group_proxies_by_comp.items():
                    state = rolling.get_competition(comp)
                    if state:
                        state.commit_group(proxies)

                for kickoff_at, lab_match_id, gi_row, kpi_panel in deferred_eligible:
                    rolling.prior_cache.append_eligible(
                        kickoff_at=kickoff_at,
                        lab_match_id=lab_match_id,
                        gi_feature_row=gi_row,
                        kpi_panel=kpi_panel,
                    )
                    rolling.gi_ecdf.ingest_feature_row(gi_row)

                for mid in group_processed_ids:
                    done_ids.add(mid)

                savepoint.commit()
                db.commit()
                db.refresh(run)
            except KeyboardInterrupt:
                savepoint.rollback()
                db.rollback()
                raise
            except Exception:
                savepoint.rollback()
                db.rollback()
                raise

            if stop_for_pilot:
                break

        db.refresh(run)
        perf.elapsed_total_seconds = time.perf_counter() - run_start
        processed = int(run.matches_processed or 0)
        perf.db_query_count_total = query_counter.count
        perf.db_query_count_per_match_avg = (
            query_counter.count / processed if processed else 0.0
        )
        if run.cancel_requested or run.status == STATUS_CANCELLED:
            run.status = STATUS_CANCELLED
        elif not stop_for_pilot or int(run.matches_processed or 0) > 0:
            summary = build_run_summary_v3(db, run_id)
            policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
            summary["run_scope"] = policy.get("run_scope") or "full"
            summary["is_partial_run"] = bool(policy.get("is_partial_run"))
            summary["not_full_season_report"] = bool(policy.get("not_full_season_report"))
            summary["max_matches"] = policy.get("max_matches")
            summary["pilot_strategy"] = policy.get("pilot_strategy")
            summary["eligible_per_competition"] = policy.get("eligible_per_competition")
            summary["source_git_commit"] = run.source_git_commit
            summary["source_git_commit_source"] = getattr(run, "source_git_commit_source", None)
            summary["source_revision_status"] = getattr(run, "source_revision_status", None)
            summary["scan_version"] = HISTORICAL_SCAN_VERSION_V4
            summary["performance_profile"] = perf.to_dict()
            run.summary_json = summary
            run.status = (
                STATUS_COMPLETED_WITH_WARNINGS
                if int(run.matches_error or 0) > 0
                else STATUS_COMPLETED
            )
        run.completed_at = _utcnow()
        if run.status != STATUS_CANCELLED:
            run.progress_pct = Decimal("100.0")
        db.commit()
    except Exception as exc:
        logger.exception("historical scan v4 run failed id=%s", run_id)
        try:
            run = db.get(CecchinoLabHistoricalScanRun, run_id)
            if run:
                perf.elapsed_total_seconds = time.perf_counter() - run_start
                processed = int(run.matches_processed or 0)
                perf.db_query_count_total = query_counter.count
                perf.db_query_count_per_match_avg = (
                    query_counter.count / processed if processed else 0.0
                )
                run.status = STATUS_FAILED
                run.error_json = {"message": str(exc)[:500], "type": type(exc).__name__}
                run.completed_at = _utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _persist_error_snapshot_v4(
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
