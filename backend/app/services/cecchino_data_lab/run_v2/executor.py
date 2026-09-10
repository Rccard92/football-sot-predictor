"""Executor RUN V2: replay storico su tutto il dataset Cecchino Lab.

Riusa senza modificarli i moduli V1 (contesti, Cecchino, KPI, Signals,
Balance, Goal Intensity, Acquistabilita) e vi affianca:

- i mercati CORE che la V1 non copriva (FT O/U 0.5);
- il layer ECONOMIC BENCHMARK sulle quote near-closing;
- il layer BLOCCO 2 di statistiche extra;
- l'audit anti-leakage esplicito per ogni match.

Il rolling state e per (competizione, stagione), come nella V1, e viene
aggiornato solo a fine gruppo kickoff: due partite con lo stesso orario non
possono vedersi a vicenda.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.models.cecchino_run_v2 import (
    RUN_V2_STATUS_CANCELLED,
    RUN_V2_STATUS_COMPLETED,
    RUN_V2_STATUS_COMPLETED_WITH_WARNINGS,
    RUN_V2_STATUS_FAILED,
    RUN_V2_STATUS_PENDING,
    RUN_V2_STATUS_RUNNING,
    SNAPSHOT_STATUS_PROCESSED,
    CecchinoRunV2MarketResult,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino.cecchino_constants import PICCHETTO_KEY_HOME_AWAY
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    PARSER_VERSION,
)
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    compute_cecchino_from_contexts,
    compute_goal_markets_from_contexts,
    lab_match_to_proxy,
    sha256_prematch_payload,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_eligibility import (
    evaluate_historical_eligibility,
)
from app.services.cecchino_data_lab.historical_goal_intensity import (
    MIN_ECDF_TRAIN_N,
    build_historical_goal_intensity,
)
from app.services.cecchino_data_lab.historical_kickoff_group import group_work_by_kickoff
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_historical_balance_v5,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    build_historical_purchasability_v36,
)
from app.services.cecchino_data_lab.historical_rolling_state import (
    GlobalRollingStateRegistry,
)
from app.services.cecchino_data_lab.historical_scan_v4_ordering import (
    match_sort_key_v4,
    stable_competition_id_v4,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    build_historical_signal_models,
)
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKETS,
    LAYER_CORE_STRICT,
    LAYER_ECONOMIC,
    RUN_V2_COMMIT_EVERY_GROUPS,
    RUN_V2_EXTRA_STATS_VERSION,
    RUN_V2_FEATURE_CONTRACT_VERSION,
    RUN_V2_QUOTE_POLICY_VERSION,
    RUN_V2_VERSION,
)
from app.services.cecchino_data_lab.run_v2.economic_observation import (
    build_economic_benchmark_rows,
    summarize_economic_benchmark,
)
from app.services.cecchino_data_lab.run_v2.extra_stats import (
    ExtraStatsRegistry,
    build_actual_stats,
)
from app.services.cecchino_data_lab.run_v2.goal_markets_ext import (
    compute_ht_1x2_markets,
    compute_ou_05_markets,
)
from app.services.cecchino_data_lab.run_v2.leakage_audit import (
    RunLeakageAuditor,
    audit_history_window,
    audit_pre_match_payload,
)
from app.services.cecchino_data_lab.run_v2.market_rows import (
    build_core_strict_market_rows,
    frozen_probabilities,
)
from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle
from app.services.cecchino_data_lab.run_v2.settlement import (
    evaluate_market_outcome_v2,
    match_result_from_lab_match,
)

logger = logging.getLogger(__name__)

CANCEL_CHECK_INTERVAL_GROUPS = 20
PROGRESS_LOG_INTERVAL = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _rolling_key(competition: str, season_label: str) -> str:
    """Chiave rolling per (competizione, stagione).

    Coincide con il perimetro storico della V1, che gira su una stagione alla
    volta: mantenerla garantisce contesti identici a quelli V1.
    """
    return f"{competition}::{season_label}"


def _season_start_year(season_label: str | None) -> int | None:
    if not season_label:
        return None
    head = str(season_label).strip()[:4]
    return int(head) if head.isdigit() else None


@dataclass
class RunV2Progress:
    matches_total: int = 0
    matches_processed: int = 0
    matches_error: int = 0
    market_rows_written: int = 0
    groups_processed: int = 0
    started_at: float = field(default_factory=time.perf_counter)

    def to_dict(self) -> dict[str, Any]:
        elapsed = time.perf_counter() - self.started_at
        return {
            "matches_total": self.matches_total,
            "matches_processed": self.matches_processed,
            "matches_error": self.matches_error,
            "market_rows_written": self.market_rows_written,
            "groups_processed": self.groups_processed,
            "elapsed_seconds": round(elapsed, 2),
            "avg_ms_per_match": (
                round(1000.0 * elapsed / self.matches_processed, 2)
                if self.matches_processed
                else None
            ),
        }


# --- creazione run ---------------------------------------------------------


def season_label_from_run(run: CecchinoRunV2Run) -> str | None:
    """Stagione persistita nello scope della RUN (`module_policy_json`)."""
    policy = run.module_policy_json if isinstance(run.module_policy_json, dict) else {}
    raw = policy.get("season_label") or policy.get("season")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def create_run_v2(
    db: Session,
    *,
    season_label: str,
    max_matches: int | None = None,
    source_git_commit: str | None = None,
    run_scope: str = "full",
) -> CecchinoRunV2Run:
    season = str(season_label or "").strip()
    if not season:
        raise ValueError("season_label obbligatorio per creare una RUN V2")

    run = CecchinoRunV2Run(
        run_version=RUN_V2_VERSION,
        status=RUN_V2_STATUS_PENDING,
        run_scope=run_scope,
        max_matches=max_matches,
        requested_at=_utcnow(),
        quote_policy_json={
            "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
            "strict_policy_version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
            "strict_layer": "bet365 pre-closing reference, unico input ammesso",
            "economic_layer": "bet365 *_last_seen, mai input, solo benchmark",
            "no_closing_fallback": True,
        },
        module_policy_json={
            "feature_contract_version": RUN_V2_FEATURE_CONTRACT_VERSION,
            "extra_stats_version": RUN_V2_EXTRA_STATS_VERSION,
            "parser_version": PARSER_VERSION,
            "core_formula_freeze": True,
            "rolling_scope": "competition_season",
            # Scope stagione esplicito: storico, resume ed export restano allineati.
            "season_label": season,
            "season_scope": season,
            "run_scope": run_scope,
            "max_matches": max_matches,
        },
        source_git_commit=source_git_commit,
        source_git_commit_source="cli" if source_git_commit else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def select_work_for_run(
    run: CecchinoRunV2Run,
    work: list[_WorkItem],
) -> list[_WorkItem]:
    """Archivio globale → filtro stagione → ordine cronologico → max_matches (pilot).

    L'ordinamento e' riusato esplicitamente dopo il filtro, cosi' il pilot 50
    prende i primi N match della stagione selezionata e non dell'archivio globale.
    """
    season = season_label_from_run(run)
    if not season:
        raise ValueError(
            f"run_v2 {run.id}: season_label assente in module_policy_json"
        )

    filtered = [w for w in work if w.season_label == season]
    filtered.sort(
        key=lambda w: match_sort_key_v4(
            w.match,
            competition_name=w.rolling_key,
            dataset_id=int(w.dataset.id),
        )
    )
    if run.max_matches:
        filtered = filtered[: int(run.max_matches)]
    return filtered


# --- preload ---------------------------------------------------------------


@dataclass
class _WorkItem:
    match: CecchinoLabMatch
    dataset: CecchinoLabDataset
    competition: str
    season_label: str
    rolling_key: str
    proxy: Any


def _load_work(db: Session) -> tuple[list[_WorkItem], dict[str, list[Any]]]:
    """Carica dataset e match una volta sola, senza query per match."""
    datasets = list(db.scalars(select(CecchinoLabDataset)).all())
    ds_by_id = {int(d.id): d for d in datasets}
    if not datasets:
        return [], {}

    matches = list(db.scalars(select(CecchinoLabMatch)).all())

    by_rolling_key: dict[str, list[CecchinoLabMatch]] = {}
    meta_by_key: dict[str, tuple[str, str]] = {}
    for m in matches:
        dataset = ds_by_id.get(int(m.dataset_id or 0))
        if dataset is None:
            continue
        competition = str(dataset.competition_name or "")
        season_label = str(dataset.season_label or "")
        key = _rolling_key(competition, season_label)
        by_rolling_key.setdefault(key, []).append(m)
        meta_by_key[key] = (competition, season_label)

    proxies_by_key: dict[str, list[Any]] = {}
    work: list[_WorkItem] = []
    for key, group in by_rolling_key.items():
        competition, season_label = meta_by_key[key]
        cid = stable_competition_id_v4(key)
        proxy_by_id = {int(m.id): lab_match_to_proxy(m, competition_id=cid) for m in group}
        proxies_by_key[key] = sort_proxies(list(proxy_by_id.values()))
        for m in group:
            dataset = ds_by_id[int(m.dataset_id)]
            work.append(
                _WorkItem(
                    match=m,
                    dataset=dataset,
                    competition=competition,
                    season_label=season_label,
                    rolling_key=key,
                    proxy=proxy_by_id[int(m.id)],
                )
            )

    work.sort(
        key=lambda w: match_sort_key_v4(
            w.match,
            competition_name=w.rolling_key,
            dataset_id=int(w.dataset.id),
        )
    )
    return work, proxies_by_key


# --- processing per match ---------------------------------------------------


def _process_one_match(
    db: Session,
    *,
    run: CecchinoRunV2Run,
    item: _WorkItem,
    chronological_order: int,
    rolling: GlobalRollingStateRegistry,
    extra_stats: ExtraStatsRegistry,
    auditor: RunLeakageAuditor,
) -> tuple[int, int]:
    """Un match: prediction congelata, benchmark economico, label reali."""
    match = item.match
    comp_state = rolling.get_competition(item.rolling_key)
    if comp_state is None:
        raise RuntimeError(f"rolling state mancante per {item.rolling_key}")

    # 1. Contesti pre-match: solo partite strettamente precedenti.
    contexts = comp_state.contexts_for(item.proxy)
    priors = comp_state.priors_for(item.proxy)

    audit = audit_history_window(
        lab_match_id=int(match.id),
        target_kickoff=match.kickoff_at,
        history_kickoffs=[p.kickoff_at for p in priors],
        history_ids=[int(p.id) for p in priors],
        context_builder_leakage_ok=bool(getattr(contexts, "leakage_ok", True)),
    )

    # 2. Moduli CORE V1, invocati senza alcuna variazione.
    cecchino_output = compute_cecchino_from_contexts(contexts)
    goal_markets = compute_goal_markets_from_contexts(contexts)

    under_odd = None
    under_block = (goal_markets or {}).get("UNDER_2_5") or {}
    if under_block.get("final_odd") is not None:
        under_odd = float(under_block["final_odd"])
        meta = contexts.sample_meta.get(PICCHETTO_KEY_HOME_AWAY) or {}
        sample_split = int(meta.get("home_sample_count") or 0) + int(
            meta.get("away_sample_count") or 0
        )
        cecchino_output["signals_matrix"] = rebuild_signals_with_under(
            final=cecchino_output.get("final") or {},
            sample_home_away_split=sample_split,
            under_2_5_cecchino_odd=under_odd,
        )

    # 3. Mercati che la V1-lab non produce, calcolati con funzioni V1 invariate.
    ou_05_markets = compute_ou_05_markets(contexts, priors)
    ht_1x2_markets = compute_ht_1x2_markets(contexts, priors)

    # 4. Quote: STRICT (input ammesso) ed ECONOMIC (mai input).
    quote_bundle = build_run_v2_quote_bundle(match)
    strict_v1_bundle = quote_bundle["strict_v1_bundle"]

    final = cecchino_output.get("final") or {}
    kpi = build_historical_kpi_panel_bet365(
        final_odds=final,
        match=match,
        goal_markets=goal_markets,
        quote_bundle=strict_v1_bundle,
    )
    balance = build_historical_balance_v5(
        cecchino_final=final,
        goal_markets=goal_markets,
        kpi_panel=kpi,
        identity={
            "home_team": match.home_team,
            "away_team": match.away_team,
            "competition": item.competition,
            "season_label": item.season_label,
        },
    )

    input_snapshot = build_input_snapshot(contexts)
    prior_gi_rows = rolling.prior_cache.gi_rows_before(match.kickoff_at)
    prefitted = rolling.gi_ecdf.ecdfs() if rolling.gi_ecdf.train_n() >= MIN_ECDF_TRAIN_N else None
    gi_payload = build_historical_goal_intensity(
        input_snapshot=input_snapshot,
        contexts=contexts,
        competition_ordered=comp_state.all_proxies,
        target=item.proxy,
        prior_feature_rows=prior_gi_rows,
        prefitted_ecdfs=prefitted,
    )
    purch_payload = build_historical_purchasability_v36(
        kpi_panel=kpi,
        match=match,
        season_label=item.season_label,
        competition_name=item.competition,
    )
    signals = build_historical_signal_models(
        cecchino_output=cecchino_output,
        quote_bundle=strict_v1_bundle,
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

    # 5. BLOCCO 2: feature costruite dallo storico gia ingerito, mai dal target.
    extra_prematch = extra_stats.build_prematch_features(
        competition=item.competition,
        season_label=item.season_label,
        home_team=match.home_team,
        away_team=match.away_team,
        referee=match.referee,
        target_kickoff=match.kickoff_at,
    )

    # 6. Freeze del payload pre-match.
    pre_match_payload = {
        "identity": {
            "lab_match_id": int(match.id),
            "competition": item.competition,
            "season_label": item.season_label,
            "kickoff_at": match.kickoff_at.isoformat() if match.kickoff_at else None,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "chronological_order": chronological_order,
        },
        "input_snapshot": input_snapshot,
        "cecchino_final": final,
        "goal_markets": {
            k: {"final_odd": (v or {}).get("final_odd"), "status": (v or {}).get("status")}
            for k, v in (goal_markets or {}).items()
        },
        "goal_markets_ou_05": {
            k: {"final_odd": (v or {}).get("final_odd"), "status": (v or {}).get("status")}
            for k, v in (ou_05_markets or {}).items()
        },
        "goal_markets_ht_1x2": {
            k: {"final_odd": (v or {}).get("final_odd"), "status": (v or {}).get("status")}
            for k, v in (ht_1x2_markets or {}).items()
        },
        "strict_quotes": {
            mk: {
                "value": q.get("value"),
                "quote_source": q.get("quote_source"),
                "is_real_quote": q.get("is_real_quote"),
                "is_derived": q.get("is_derived"),
            }
            for mk, q in quote_bundle["strict_by_market"].items()
        },
        "extra_stats_prematch": extra_prematch,
        "eligibility": {
            "status": elig.get("status"),
            "core_eligible": bool(elig.get("core_eligible")),
        },
        "versions": {
            "run_version": RUN_V2_VERSION,
            "feature_contract_version": RUN_V2_FEATURE_CONTRACT_VERSION,
            "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
            "extra_stats_version": RUN_V2_EXTRA_STATS_VERSION,
        },
    }
    payload_violations = audit_pre_match_payload(pre_match_payload)
    if payload_violations:
        audit.violations.extend(payload_violations)
        audit.pre_match_cutoff_ok = False
    auditor.record(audit)

    payload_hash = sha256_prematch_payload(pre_match_payload)
    locked_at = _utcnow()

    # 7. Da qui in poi si leggono i dati post-match: la prediction e congelata.
    match_result = match_result_from_lab_match(match)
    outcomes = {
        m.key: evaluate_market_outcome_v2(m.key, match_result) for m in CORE_MARKETS
    }
    actuals = build_actual_stats(match)

    core_rows = build_core_strict_market_rows(
        kpi_panel=kpi,
        goal_markets=goal_markets,
        ou_05_markets=ou_05_markets,
        ht_1x2_markets=ht_1x2_markets,
        strict_by_market=quote_bundle["strict_by_market"],
        balance=balance,
        gi_payload=gi_payload,
        purchasability=purch_payload,
        outcomes=outcomes,
    )
    economic_rows = build_economic_benchmark_rows(
        economic_bundle=quote_bundle["economic"],
        frozen_probabilities=frozen_probabilities(core_rows),
        outcomes=outcomes,
    )

    snapshot = CecchinoRunV2MatchSnapshot(
        run_id=int(run.id),
        dataset_id=int(item.dataset.id),
        lab_match_id=int(match.id),
        competition_name=item.competition,
        competition_id=stable_competition_id_v4(item.rolling_key),
        division_code=getattr(match, "division_code", None),
        season_label=item.season_label,
        season_start_year=_season_start_year(item.season_label),
        kickoff_at=match.kickoff_at,
        home_team=match.home_team,
        away_team=match.away_team,
        referee=match.referee,
        chronological_order=chronological_order,
        status=SNAPSHOT_STATUS_PROCESSED,
        eligibility_status=elig.get("status"),
        eligibility_reason=elig.get("reason"),
        pre_match_payload_json=pre_match_payload,
        pre_match_payload_sha256=payload_hash,
        pre_match_locked_at=locked_at,
        input_snapshot_json=input_snapshot,
        cecchino_output_json=cecchino_output,
        # Blocchi tenuti separati: il DRAW_PT della V1-lab e quello della
        # famiglia HT normalizzata sono due valori diversi e restano entrambi
        # ispezionabili invece di sovrascriversi.
        goal_markets_json={
            "v1_lab": goal_markets,
            "ou_05_v2": ou_05_markets,
            "ht_1x2_family_v2": ht_1x2_markets,
        },
        kpi_json=kpi,
        signals_json=signals,
        balance_v5_json=balance,
        goal_intensity_json=gi_payload,
        purchasability_json=purch_payload,
        quote_bundle_json=quote_bundle,
        extra_stats_prematch_json=extra_prematch,
        actuals_json=actuals,
        result_attached_at=_utcnow(),
        leakage_audit_json=audit.to_dict(),
        history_count=audit.history_count,
        latest_history_kickoff_used=audit.latest_history_kickoff_used,
        pre_match_cutoff_ok=audit.pre_match_cutoff_ok,
        warnings_json=list(cecchino_output.get("warnings") or [])
        + list(extra_prematch.get("warnings") or []),
    )
    db.add(snapshot)
    db.flush()
    snapshot_id = int(snapshot.id)

    rows_written = 0
    for row in core_rows:
        db.add(_core_result_orm(run.id, snapshot_id, match.id, row))
        rows_written += 1
    for row in economic_rows:
        db.add(_economic_result_orm(run.id, snapshot_id, match.id, row))
        rows_written += 1

    # 8. Aggiornamento GI differito: applicato solo a fine gruppo kickoff.
    gi_row = gi_payload.get("feature_row_for_profile")
    deferred_gi = gi_row if isinstance(gi_row, dict) else None
    if deferred_gi is not None and bool(elig.get("core_eligible")):
        item.__dict__["_deferred_gi"] = (deferred_gi, kpi)

    return snapshot_id, rows_written


def _core_result_orm(
    run_id: int,
    snapshot_id: int,
    lab_match_id: int,
    row: dict[str, Any],
) -> CecchinoRunV2MarketResult:
    return CecchinoRunV2MarketResult(
        run_id=int(run_id),
        match_snapshot_id=snapshot_id,
        lab_match_id=int(lab_match_id),
        market_key=row["market_key"],
        market_label=row.get("market_label"),
        market_family=row.get("market_family"),
        period=row.get("period"),
        line=row.get("line"),
        observation_layer=LAYER_CORE_STRICT,
        prediction=row.get("prediction"),
        probability=row.get("probability"),
        confidence=row.get("confidence"),
        quota_cecchino=row.get("quota_cecchino"),
        kpi_rating=row.get("kpi_rating"),
        edge_pct=row.get("edge_pct"),
        vantaggio_prob=row.get("vantaggio_prob"),
        signal_active=False,
        buyability_score=row.get("buyability_score"),
        buyability_class=row.get("buyability_class"),
        equilibrium_state=row.get("equilibrium_state"),
        goal_intensity_score=row.get("goal_intensity_score"),
        market_available=bool(row.get("market_available")),
        market_quote_available=bool(row.get("market_quote_available")),
        quota_book=row.get("quota_book"),
        prob_book_raw=row.get("prob_book_raw"),
        prob_book_fair=row.get("prob_book_fair"),
        is_real_quote=bool(row.get("is_real_quote")),
        is_derived_quote=bool(row.get("is_derived_quote")),
        derivation_method=row.get("derivation_method"),
        quote_source=row.get("quote_source"),
        quote_type=row.get("quote_type"),
        source_column=row.get("source_column"),
        quote_snapshot_type=row.get("quote_snapshot_type"),
        pre_match_input_safe=bool(row.get("pre_match_input_safe")),
        used_for_prediction=bool(row.get("used_for_prediction")),
        outcome=row.get("outcome"),
        won=row.get("won"),
        flat_stake_profit=row.get("flat_stake_profit"),
        result_reason=row.get("result_reason"),
        economic_observation_only=False,
    )


def _economic_result_orm(
    run_id: int,
    snapshot_id: int,
    lab_match_id: int,
    row: dict[str, Any],
) -> CecchinoRunV2MarketResult:
    from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKET_BY_KEY

    market = CORE_MARKET_BY_KEY.get(row["market_key"])
    return CecchinoRunV2MarketResult(
        run_id=int(run_id),
        match_snapshot_id=snapshot_id,
        lab_match_id=int(lab_match_id),
        market_key=row["market_key"],
        market_label=market.label if market else None,
        market_family=market.family if market else None,
        period=market.period if market else None,
        line=market.line if market else None,
        observation_layer=LAYER_ECONOMIC,
        # Nessuna prediction in questo layer: la probabilita e solo quella
        # congelata dal CORE, riportata per rendere leggibile il confronto.
        prediction=None,
        probability=row.get("frozen_probability"),
        market_available=True,
        market_quote_available=bool(row.get("market_quote_available")),
        quota_book=row.get("quota_book"),
        prob_book_raw=row.get("prob_book_raw"),
        prob_book_fair=row.get("prob_book_fair"),
        is_real_quote=bool(row.get("is_real_quote")),
        is_derived_quote=False,
        quote_source=row.get("quote_source"),
        quote_type=LAYER_ECONOMIC,
        source_column=row.get("source_column"),
        quote_snapshot_type=row.get("quote_snapshot_type"),
        pre_match_input_safe=False,
        used_for_prediction=False,
        signal_active=False,
        outcome=row.get("outcome"),
        won=row.get("won"),
        flat_stake_profit=None,
        result_reason=row.get("result_reason"),
        economic_benchmark_value=row.get("economic_benchmark_value"),
        economic_benchmark_profit=row.get("economic_benchmark_profit"),
        economic_benchmark_roi=row.get("economic_benchmark_roi"),
        economic_observation_only=True,
    )


# --- run -------------------------------------------------------------------


def execute_run_v2(run_id: int) -> dict[str, Any]:
    """Esegue la RUN V2. Apre e chiude una propria sessione."""
    db = SessionLocal()
    try:
        return _execute_body(db, run_id)
    finally:
        db.close()


def _execute_body(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None:
        raise ValueError(f"run_v2 {run_id} inesistente")

    run.status = RUN_V2_STATUS_RUNNING
    run.started_at = _utcnow()
    db.commit()

    progress = RunV2Progress()
    auditor = RunLeakageAuditor()

    try:
        work, proxies_by_key = _load_work(db)
        # Scope: archivio globale → season → cronologico → max_matches (solo pilot).
        work = select_work_for_run(run, work)

        progress.matches_total = len(work)
        run.matches_total = len(work)
        kickoffs = [w.match.kickoff_at for w in work if w.match.kickoff_at]
        run.min_kickoff_at = min(kickoffs) if kickoffs else None
        run.max_kickoff_at = max(kickoffs) if kickoffs else None
        db.commit()

        # Run ripartibile: si riparte dai soli gruppi kickoff gia completi.
        done_ids = _already_processed_ids(db, run_id=int(run.id))

        rolling = GlobalRollingStateRegistry()
        for key, proxies in proxies_by_key.items():
            rolling.register_competition(key, proxies)
        extra_stats = ExtraStatsRegistry()

        groups = group_work_by_kickoff(work, kickoff_at_getter=lambda w: w.match.kickoff_at)
        chronological_order = 0

        for group_index, group in enumerate(groups):
            if group_index % CANCEL_CHECK_INTERVAL_GROUPS == 0 and _is_cancelled(db, int(run.id)):
                run.status = RUN_V2_STATUS_CANCELLED
                run.completed_at = _utcnow()
                db.commit()
                return {"status": RUN_V2_STATUS_CANCELLED, **progress.to_dict()}

            for item in group:
                chronological_order += 1
                if int(item.match.id) in done_ids:
                    continue
                try:
                    _, rows = _process_one_match(
                        db,
                        run=run,
                        item=item,
                        chronological_order=chronological_order,
                        rolling=rolling,
                        extra_stats=extra_stats,
                        auditor=auditor,
                    )
                    progress.matches_processed += 1
                    progress.market_rows_written += rows
                except Exception as exc:  # noqa: BLE001 - un match rotto non ferma la run
                    progress.matches_error += 1
                    logger.exception(
                        "run_v2 match %s fallito: %s", getattr(item.match, "id", None), exc
                    )
                    db.rollback()
                    _persist_error_snapshot(db, run=run, item=item, exc=exc)

            _commit_group_state(group, rolling=rolling, extra_stats=extra_stats)
            progress.groups_processed += 1

            if progress.groups_processed % RUN_V2_COMMIT_EVERY_GROUPS == 0:
                _flush_progress(db, run, progress, auditor)

            if progress.matches_processed and progress.matches_processed % PROGRESS_LOG_INTERVAL == 0:
                logger.info("run_v2 %s: %s match processati", run.id, progress.matches_processed)

        _flush_progress(db, run, progress, auditor)
        summary = _build_summary(db, run=run, progress=progress, auditor=auditor)

        run.summary_json = summary
        run.leakage_audit_json = auditor.to_dict()
        run.leakage_violations = auditor.violations_count
        run.completed_at = _utcnow()

        if not auditor.ok:
            # Violazione anti-leakage: la run non e utilizzabile.
            run.status = RUN_V2_STATUS_FAILED
            run.error_json = {
                "code": "leakage_violations_detected",
                "leakage_violations": auditor.violations_count,
                "matches_with_violation": auditor.matches_with_violation,
            }
        elif progress.matches_error:
            run.status = RUN_V2_STATUS_COMPLETED_WITH_WARNINGS
        else:
            run.status = RUN_V2_STATUS_COMPLETED
        db.commit()

        return {"status": run.status, "summary": summary, **progress.to_dict()}

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(CecchinoRunV2Run, int(run_id))
        if run is not None:
            run.status = RUN_V2_STATUS_FAILED
            run.completed_at = _utcnow()
            run.error_json = {
                "code": "run_failed",
                "message": str(exc),
                "traceback": traceback.format_exc()[-4000:],
            }
            db.commit()
        raise


def _already_processed_ids(db: Session, *, run_id: int) -> set[int]:
    rows = db.execute(
        select(CecchinoRunV2MatchSnapshot.lab_match_id).where(
            CecchinoRunV2MatchSnapshot.run_id == run_id
        )
    ).all()
    return {int(r[0]) for r in rows}


def _is_cancelled(db: Session, run_id: int) -> bool:
    run = db.get(CecchinoRunV2Run, run_id)
    return bool(run and (run.cancel_requested or run.status == RUN_V2_STATUS_CANCELLED))


def _commit_group_state(
    group: list[_WorkItem],
    *,
    rolling: GlobalRollingStateRegistry,
    extra_stats: ExtraStatsRegistry,
) -> None:
    """Rende visibile il gruppo kickoff appena chiuso, mai prima."""
    by_key: dict[str, list[Any]] = {}
    for item in group:
        by_key.setdefault(item.rolling_key, []).append(item.proxy)

        deferred = item.__dict__.pop("_deferred_gi", None)
        if deferred is not None:
            gi_row, kpi_panel = deferred
            rolling.prior_cache.append_eligible(
                kickoff_at=item.match.kickoff_at,
                lab_match_id=int(item.match.id),
                gi_feature_row=gi_row,
                kpi_panel=kpi_panel,
            )
            rolling.gi_ecdf.ingest_feature_row(gi_row)

        extra_stats.ingest_match(
            item.match,
            competition=item.competition,
            season_label=item.season_label,
        )

    for key, proxies in by_key.items():
        state = rolling.get_competition(key)
        if state is not None:
            state.commit_group(proxies)


def _persist_error_snapshot(
    db: Session,
    *,
    run: CecchinoRunV2Run,
    item: _WorkItem,
    exc: Exception,
) -> None:
    try:
        db.add(
            CecchinoRunV2MatchSnapshot(
                run_id=int(run.id),
                dataset_id=int(item.dataset.id),
                lab_match_id=int(item.match.id),
                competition_name=item.competition,
                season_label=item.season_label,
                season_start_year=_season_start_year(item.season_label),
                kickoff_at=item.match.kickoff_at,
                home_team=item.match.home_team,
                away_team=item.match.away_team,
                status="error",
                pre_match_cutoff_ok=True,
                error_json={
                    "message": str(exc),
                    "traceback": traceback.format_exc()[-4000:],
                },
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def _flush_progress(
    db: Session,
    run: CecchinoRunV2Run,
    progress: RunV2Progress,
    auditor: RunLeakageAuditor,
) -> None:
    run.matches_processed = progress.matches_processed
    run.matches_error = progress.matches_error
    run.market_rows_written = progress.market_rows_written
    run.leakage_violations = auditor.violations_count
    if progress.matches_total:
        run.progress_pct = round(
            100.0 * (progress.matches_processed + progress.matches_error) / progress.matches_total,
            1,
        )
    db.commit()


def _build_summary(
    db: Session,
    *,
    run: CecchinoRunV2Run,
    progress: RunV2Progress,
    auditor: RunLeakageAuditor,
) -> dict[str, Any]:
    from app.services.cecchino_data_lab.run_v2.summary import build_run_summary

    return build_run_summary(db, run=run, progress=progress.to_dict(), auditor=auditor)
