"""Executor RUN V2.5: stesso impianto della RUN V2 (una stagione per run, stesso ordine
cronologico, stessi gruppi di kickoff, stesse quote, stesse statistiche extra, stessa
eleggibilita', stesse righe mercato e stesso audit anti-leakage), moduli V2.5.

Scrive nelle tabelle della RUN V2 con `run_version = cecchino_run_v25`: la pipeline dei
pattern legge le due versioni allo stesso modo. Nessuna funzione V2 viene modificata.
"""

from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cecchino_run_v2 import (
    RUN_V2_STATUS_CANCELLED,
    RUN_V2_STATUS_COMPLETED,
    RUN_V2_STATUS_COMPLETED_WITH_WARNINGS,
    RUN_V2_STATUS_FAILED,
    RUN_V2_STATUS_PENDING,
    RUN_V2_STATUS_RUNNING,
    SNAPSHOT_STATUS_PROCESSED,
    CecchinoRunV2MatchSnapshot,
    CecchinoRunV2Run,
)
from app.services.cecchino.cecchino_constants import PICCHETTO_KEY_HOME_AWAY
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    sha256_prematch_payload,
)
from app.services.cecchino_data_lab.historical_eligibility import (
    ELIGIBLE_CORE,
    evaluate_historical_eligibility,
)
from app.services.cecchino_data_lab.historical_kickoff_group import group_work_by_kickoff
from app.services.cecchino_data_lab.historical_rolling_state import GlobalRollingStateRegistry
from app.services.cecchino_data_lab.historical_scan_v4_ordering import stable_competition_id_v4
from app.services.cecchino_data_lab.run_v2.constants import (
    CORE_MARKET_BY_KEY,
    CORE_MARKETS,
    RUN_V2_COMMIT_EVERY_GROUPS,
    RUN_V2_EXTRA_STATS_VERSION,
    RUN_V2_QUOTE_POLICY_VERSION,
)
from app.services.cecchino_data_lab.run_v2.executor import (
    RunV2Progress,
    _already_processed_ids,
    _core_result_orm,
    _flush_progress,
    _is_cancelled,
    _load_work,
    _persist_error_snapshot,
    _season_start_year,
    _utcnow,
    _WorkItem,
    season_label_from_run,
    select_work_for_run,
)
from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry, build_actual_stats
from app.services.cecchino_data_lab.run_v2.leakage_audit import (
    RunLeakageAuditor,
    audit_history_window,
    audit_pre_match_payload,
)
from app.services.cecchino_data_lab.run_v2.market_rows import build_core_strict_market_rows
from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle
from app.services.cecchino_data_lab.run_v2.settlement import (
    evaluate_market_outcome_v2,
    match_result_from_lab_match,
)
from app.services.cecchino_v25 import scales
from app.services.cecchino_v25.balance import build_balance_v25
from app.services.cecchino_v25.constants import ENGINE_VERSION, RUN_V25_VERSION
from app.services.cecchino_v25.goal_intensity import build_goal_intensity_v25
from app.services.cecchino_v25.goals import compute_goal_markets_v25
from app.services.cecchino_v25.kpi import build_kpi_panel_v25
from app.services.cecchino_v25.league import LeagueCounts, build_reference, counts_from_matches
from app.services.cecchino_v25.picchetti import compute_cecchino_v25
from app.services.cecchino_v25.purchasability import PurchasabilityCalibrator, build_purchasability_v25
from app.services.cecchino_v25.signals import build_signals_v25

logger = logging.getLogger(__name__)

CANCEL_CHECK_INTERVAL_GROUPS = 20


def _previous_season_label(season_label: str) -> str | None:
    head = season_label[:4]
    if not head.isdigit():
        return None
    start = int(head) - 1
    return f"{start}/{start + 1}"


# --- stato progressivo V2.5 ---------------------------------------------------------------


@dataclass
class _CalibrationRow:
    family: str
    p_book: float
    p_cec: float
    won: bool
    lab_match_id: int


class V25State:
    """Riferimenti di campionato e calibrazione acquistabilita': vedono solo gruppi chiusi."""

    def __init__(self, proxies_by_key: dict[str, list[Any]], season_label: str) -> None:
        self.current: dict[str, LeagueCounts] = defaultdict(LeagueCounts)
        self.global_pool = LeagueCounts()
        prev = _previous_season_label(season_label)
        # stagione precedente completa: tutta anteriore all'inizio della stagione in corso
        self.previous: dict[str, LeagueCounts] = {}
        if prev:
            for key, proxies in proxies_by_key.items():
                competition, _, season = key.rpartition("::")
                if season == prev:
                    self.previous[competition] = counts_from_matches(proxies)
        self.calibrator = PurchasabilityCalibrator()

    def reference(self, competition: str, rolling_key: str):
        return build_reference(
            current=self.current[rolling_key],
            previous=self.previous.get(competition),
            global_pool=self.global_pool,
        )

    def commit(self, rolling_key: str, proxy: Any) -> None:
        self.current[rolling_key].add_match(proxy)
        self.global_pool.add_match(proxy)


def seed_calibrator_from_previous_run(db: Session, calibrator: PurchasabilityCalibrator, season_label: str) -> int | None:
    """Righe della RUN V2.5 completata della stagione precedente (tutte anteriori)."""
    prev = _previous_season_label(season_label)
    if prev is None:
        return None
    run_id = db.execute(
        text(
            """
            SELECT id FROM cecchino_run_v2_runs
            WHERE run_version = :v AND module_policy_json->>'season_label' = :s
              AND status IN ('completed', 'completed_with_warnings')
            ORDER BY id DESC LIMIT 1
            """
        ),
        {"v": RUN_V25_VERSION, "s": prev},
    ).scalar()
    if run_id is None:
        return None
    _add_stored_rows(db, calibrator, run_id=int(run_id), lab_match_ids=None)
    calibrator.refresh()
    return int(run_id)


def _add_stored_rows(db: Session, calibrator: PurchasabilityCalibrator, *, run_id: int, lab_match_ids: set[int] | None) -> None:
    rows = db.execute(
        text(
            """
            SELECT r.lab_match_id, r.market_key, r.prob_book_fair, r.probability, r.won
            FROM cecchino_run_v2_market_results r
            JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
            WHERE r.run_id = :rid AND s.eligibility_status = :elig
              AND r.prob_book_fair IS NOT NULL AND r.probability IS NOT NULL
              AND r.quota_book IS NOT NULL AND r.won IS NOT NULL
            ORDER BY s.kickoff_at, r.lab_match_id
            """
        ),
        {"rid": run_id, "elig": ELIGIBLE_CORE},
    )
    for mid, key, p_book, p_cec, won in rows:
        if lab_match_ids is not None and int(mid) not in lab_match_ids:
            continue
        calibrator.add(
            family=CORE_MARKET_BY_KEY[key].family,
            p_book=float(p_book),
            p_cec=float(p_cec),
            won=bool(won),
            lab_match_id=int(mid),
        )


# --- creazione run -------------------------------------------------------------------------


def create_run_v25(db: Session, *, season_label: str, source_git_commit: str | None = None) -> CecchinoRunV2Run:
    season = str(season_label or "").strip()
    if not season:
        raise ValueError("season_label obbligatorio per creare una RUN V2.5")
    run = CecchinoRunV2Run(
        run_version=RUN_V25_VERSION,
        status=RUN_V2_STATUS_PENDING,
        run_scope="full",
        max_matches=None,
        requested_at=_utcnow(),
        quote_policy_json={
            "quote_policy_version": RUN_V2_QUOTE_POLICY_VERSION,
            "same_quotes_as_run_v2": True,
        },
        module_policy_json={
            "engine_version": ENGINE_VERSION,
            "scales_version": scales.scales_version(),
            "extra_stats_version": RUN_V2_EXTRA_STATS_VERSION,
            "rolling_scope": "competition_season",
            "season_label": season,
            "season_scope": season,
            "run_scope": "full",
        },
        source_git_commit=source_git_commit,
        source_git_commit_source="cli" if source_git_commit else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# --- una partita ---------------------------------------------------------------------------


def compute_prematch_v25(
    *,
    item: _WorkItem,
    contexts: Any,
    league: Any,
    quote_bundle: dict[str, Any],
    calibrator: PurchasabilityCalibrator,
) -> dict[str, Any]:
    """Tutti i moduli V2.5 di una partita, solo con dati pre-partita."""
    match = item.match
    cecchino = compute_cecchino_v25(contexts, league)
    final = cecchino["final"]
    goals = compute_goal_markets_v25(contexts, league)

    probabilities: dict[str, float | None] = {m.key: goals.probability(m.key) for m in CORE_MARKETS}
    if final.get("prob_1") is not None:
        probabilities.update(
            {
                "HOME": final["prob_1"],
                "DRAW": final["prob_x"],
                "AWAY": final["prob_2"],
                "ONE_X": final["prob_1"] + final["prob_x"],
                "X_TWO": final["prob_x"] + final["prob_2"],
                "ONE_TWO": final["prob_1"] + final["prob_2"],
            }
        )
    else:
        for key in ("HOME", "DRAW", "AWAY", "ONE_X", "X_TWO", "ONE_TWO"):
            probabilities[key] = None

    strict_by_market = quote_bundle["strict_by_market"]
    kpi = build_kpi_panel_v25(probabilities=probabilities, strict_by_market=strict_by_market)
    balance = build_balance_v25(final, goals.lambda_home, goals.lambda_away)
    gi_payload = build_goal_intensity_v25(contexts, league, goals)
    purch = build_purchasability_v25(kpi_panel=kpi, calibrator=calibrator)

    under_block = goals.goal_markets.get("UNDER_2_5") or {}
    meta = contexts.sample_meta.get(PICCHETTO_KEY_HOME_AWAY) or {}
    sample_split = int(meta.get("home_sample_count") or 0) + int(meta.get("away_sample_count") or 0)
    if final.get("prob_1") is not None:
        signals, signal_index = build_signals_v25(
            final=final,
            under_2_5_odd=under_block.get("final_odd"),
            sample_home_away_split=sample_split,
        )
    else:
        signals, signal_index = {"status": "unavailable"}, {}
    cecchino["signals_matrix"] = signals.get("default_matrix")

    elig = evaluate_historical_eligibility(
        home_team=match.home_team,
        away_team=match.away_team,
        kickoff_at=match.kickoff_at,
        contexts=contexts,
        cecchino_output=cecchino,
    )
    return {
        "cecchino": cecchino,
        "goals": goals,
        "probabilities": probabilities,
        "kpi": kpi,
        "balance": balance,
        "gi": gi_payload,
        "purchasability": purch,
        "signals": signals,
        "signal_index": signal_index,
        "eligibility": elig,
    }


def _process_one_match(
    db: Session,
    *,
    run: CecchinoRunV2Run,
    item: _WorkItem,
    chronological_order: int,
    rolling: GlobalRollingStateRegistry,
    extra_stats: ExtraStatsRegistry,
    auditor: RunLeakageAuditor,
    state: V25State,
) -> tuple[int, bool, list[_CalibrationRow]]:
    match = item.match
    comp_state = rolling.get_competition(item.rolling_key)
    if comp_state is None:
        raise RuntimeError(f"rolling state mancante per {item.rolling_key}")

    contexts = comp_state.contexts_for(item.proxy)
    priors = comp_state.priors_for(item.proxy)
    audit = audit_history_window(
        lab_match_id=int(match.id),
        target_kickoff=match.kickoff_at,
        history_kickoffs=[p.kickoff_at for p in priors],
        history_ids=[int(p.id) for p in priors],
        context_builder_leakage_ok=bool(getattr(contexts, "leakage_ok", True)),
    )

    league = state.reference(item.competition, item.rolling_key)
    quote_bundle = build_run_v2_quote_bundle(match)
    pre = compute_prematch_v25(
        item=item,
        contexts=contexts,
        league=league,
        quote_bundle=quote_bundle,
        calibrator=state.calibrator,
    )
    goals = pre["goals"]
    elig = pre["eligibility"]
    final = pre["cecchino"]["final"]

    extra_prematch = extra_stats.build_prematch_features(
        competition=item.competition,
        season_label=item.season_label,
        home_team=match.home_team,
        away_team=match.away_team,
        referee=match.referee,
        target_kickoff=match.kickoff_at,
    )
    input_snapshot = build_input_snapshot(contexts)
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
        "league_reference": league.to_dict(),
        "cecchino_final": final,
        "probabilities": pre["probabilities"],
        "strict_quotes": {mk: q.get("value") for mk, q in quote_bundle["strict_by_market"].items()},
        "extra_stats_prematch": extra_prematch,
        "eligibility": {"status": elig.get("status"), "core_eligible": bool(elig.get("core_eligible"))},
        "versions": {"run_version": RUN_V25_VERSION, "engine_version": ENGINE_VERSION, "scales_version": scales.scales_version()},
    }
    violations = audit_pre_match_payload(pre_match_payload)
    if violations:
        audit.violations.extend(violations)
        audit.pre_match_cutoff_ok = False
    auditor.record(audit)
    payload_hash = sha256_prematch_payload(pre_match_payload)
    locked_at = _utcnow()

    # --- da qui dati post-partita: la previsione e' congelata ---
    match_result = match_result_from_lab_match(match)
    outcomes = {m.key: evaluate_market_outcome_v2(m.key, match_result) for m in CORE_MARKETS}
    actuals = build_actual_stats(match)
    core_rows = build_core_strict_market_rows(
        kpi_panel=pre["kpi"],
        goal_markets=goals.goal_markets,
        ou_05_markets=goals.ou_05_markets,
        ht_1x2_markets=goals.ht_1x2_markets,
        strict_by_market=quote_bundle["strict_by_market"],
        balance=pre["balance"],
        gi_payload=pre["gi"],
        purchasability=pre["purchasability"],
        outcomes=outcomes,
        signal_index=pre["signal_index"],
    )
    fair = pre["kpi"]["fair_probabilities"]
    calibration_rows: list[_CalibrationRow] = []
    core_eligible = bool(elig.get("core_eligible"))
    for row in core_rows:
        row["prob_book_fair"] = fair.get(row["market_key"])
        p_book, p_cec, won = row["prob_book_fair"], row.get("probability"), row.get("won")
        if core_eligible and p_book is not None and p_cec is not None and won is not None and row.get("quota_book"):
            calibration_rows.append(
                _CalibrationRow(
                    family=CORE_MARKET_BY_KEY[row["market_key"]].family,
                    p_book=float(p_book),
                    p_cec=float(p_cec),
                    won=bool(won),
                    lab_match_id=int(match.id),
                )
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
        cecchino_output_json=pre["cecchino"],
        goal_markets_json={
            "v25": goals.goal_markets,
            "ou_05_v25": goals.ou_05_markets,
            "ht_1x2_family_v25": goals.ht_1x2_markets,
            "lambda": {
                "ft_home": goals.lambda_home,
                "ft_away": goals.lambda_away,
                "ht_home": goals.ht_lambda_home,
                "ht_away": goals.ht_lambda_away,
                "reliability": goals.reliability,
            },
        },
        kpi_json=pre["kpi"],
        signals_json=pre["signals"],
        balance_v5_json=pre["balance"],
        goal_intensity_json=pre["gi"],
        purchasability_json=pre["purchasability"],
        quote_bundle_json={"strict_by_market": quote_bundle["strict_by_market"]},
        extra_stats_prematch_json=extra_prematch,
        actuals_json=actuals,
        result_attached_at=_utcnow(),
        leakage_audit_json=audit.to_dict(),
        history_count=audit.history_count,
        latest_history_kickoff_used=audit.latest_history_kickoff_used,
        pre_match_cutoff_ok=audit.pre_match_cutoff_ok,
        warnings_json=list(pre["cecchino"].get("warnings") or []) + list(extra_prematch.get("warnings") or []),
    )
    db.add(snapshot)
    db.flush()
    for row in core_rows:
        db.add(_core_result_orm(run.id, int(snapshot.id), match.id, row))
    return len(core_rows), core_eligible, calibration_rows


# --- run -----------------------------------------------------------------------------------


def execute_run_v25(run_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return _execute_body(db, run_id)
    finally:
        db.close()


def _execute_body(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoRunV2Run, int(run_id))
    if run is None or run.run_version != RUN_V25_VERSION:
        raise ValueError(f"run_v25 {run_id} inesistente")
    if not scales.scales_version():
        raise RuntimeError("scale V2.5 mancanti (frozen_scales.json): eseguire prima la calibrazione")

    run.status = RUN_V2_STATUS_RUNNING
    run.started_at = run.started_at or _utcnow()
    db.commit()
    progress = RunV2Progress()
    auditor = RunLeakageAuditor()
    try:
        season = season_label_from_run(run) or ""
        all_work, proxies_by_key = _load_work(db)
        work = select_work_for_run(run, all_work)
        progress.matches_total = len(work)
        run.matches_total = len(work)
        kickoffs = [w.match.kickoff_at for w in work if w.match.kickoff_at]
        run.min_kickoff_at = min(kickoffs) if kickoffs else None
        run.max_kickoff_at = max(kickoffs) if kickoffs else None

        state = V25State(proxies_by_key, season)
        seeded_from = seed_calibrator_from_previous_run(db, state.calibrator, season)
        policy = dict(run.module_policy_json or {})
        policy["purchasability_seeded_from_run_id"] = seeded_from
        policy["competitions_with_previous_season"] = len(state.previous)
        run.module_policy_json = policy
        db.commit()

        # ripresa: le partite gia' salvate rientrano negli stati progressivi al loro turno
        done_ids = _already_processed_ids(db, run_id=int(run.id))
        stored_rows = _stored_rows_by_match(db, int(run.id)) if done_ids else {}

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

            pending_calibration: list[_CalibrationRow] = []
            for item in group:
                chronological_order += 1
                if int(item.match.id) in done_ids:
                    pending_calibration.extend(stored_rows.get(int(item.match.id), []))
                    progress.matches_processed += 1
                    continue
                try:
                    rows, _eligible, calib = _process_one_match(
                        db,
                        run=run,
                        item=item,
                        chronological_order=chronological_order,
                        rolling=rolling,
                        extra_stats=extra_stats,
                        auditor=auditor,
                        state=state,
                    )
                    progress.matches_processed += 1
                    progress.market_rows_written += rows
                    pending_calibration.extend(calib)
                    run.current_competition = item.competition
                    run.current_lab_match_id = int(item.match.id)
                    if item.match.kickoff_at is not None:
                        run.last_processed_kickoff_at = item.match.kickoff_at
                except Exception as exc:  # noqa: BLE001 - una partita rotta non ferma la run
                    progress.matches_error += 1
                    logger.exception("run_v25 match %s fallito: %s", getattr(item.match, "id", None), exc)
                    db.rollback()
                    _persist_error_snapshot(db, run=run, item=item, exc=exc)

            # il gruppo kickoff diventa visibile solo ora, per tutti gli stati
            by_key: dict[str, list[Any]] = defaultdict(list)
            for item in group:
                by_key[item.rolling_key].append(item.proxy)
                state.commit(item.rolling_key, item.proxy)
                extra_stats.ingest_match(item.match, competition=item.competition, season_label=item.season_label)
            for key, proxies in by_key.items():
                comp = rolling.get_competition(key)
                if comp is not None:
                    comp.commit_group(proxies)
            for c in pending_calibration:
                state.calibrator.add(
                    family=c.family, p_book=c.p_book, p_cec=c.p_cec, won=c.won, lab_match_id=c.lab_match_id
                )
            state.calibrator.refresh()

            progress.groups_processed += 1
            if progress.groups_processed % RUN_V2_COMMIT_EVERY_GROUPS == 0:
                _flush_progress(db, run, progress, auditor)

        _flush_progress(db, run, progress, auditor)
        run.summary_json = _summary(db, run, progress, state)
        run.leakage_audit_json = auditor.to_dict()
        run.leakage_violations = auditor.violations_count
        run.completed_at = _utcnow()
        if not auditor.ok:
            run.status = RUN_V2_STATUS_FAILED
            run.error_json = {"code": "leakage_violations_detected", "leakage_violations": auditor.violations_count}
        elif progress.matches_error:
            run.status = RUN_V2_STATUS_COMPLETED_WITH_WARNINGS
        else:
            run.status = RUN_V2_STATUS_COMPLETED
        db.commit()
        return {"status": run.status, **progress.to_dict()}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(CecchinoRunV2Run, int(run_id))
        if run is not None:
            run.status = RUN_V2_STATUS_FAILED
            run.completed_at = _utcnow()
            run.error_json = {"code": "run_failed", "message": str(exc), "traceback": traceback.format_exc()[-4000:]}
            db.commit()
        raise


def _stored_rows_by_match(db: Session, run_id: int) -> dict[int, list[_CalibrationRow]]:
    out: dict[int, list[_CalibrationRow]] = defaultdict(list)
    rows = db.execute(
        text(
            """
            SELECT r.lab_match_id, r.market_key, r.prob_book_fair, r.probability, r.won
            FROM cecchino_run_v2_market_results r
            JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
            WHERE r.run_id = :rid AND s.eligibility_status = :elig
              AND r.prob_book_fair IS NOT NULL AND r.probability IS NOT NULL
              AND r.quota_book IS NOT NULL AND r.won IS NOT NULL
            """
        ),
        {"rid": run_id, "elig": ELIGIBLE_CORE},
    )
    for mid, key, p_book, p_cec, won in rows:
        out[int(mid)].append(
            _CalibrationRow(CORE_MARKET_BY_KEY[key].family, float(p_book), float(p_cec), bool(won), int(mid))
        )
    return out


def _summary(db: Session, run: CecchinoRunV2Run, progress: RunV2Progress, state: V25State) -> dict[str, Any]:
    counts = dict(
        db.execute(
            select(CecchinoRunV2MatchSnapshot.eligibility_status, func.count())
            .where(CecchinoRunV2MatchSnapshot.run_id == int(run.id))
            .group_by(CecchinoRunV2MatchSnapshot.eligibility_status)
        ).all()
    )
    return {
        "run_id": int(run.id),
        "run_version": RUN_V25_VERSION,
        "engine_version": ENGINE_VERSION,
        "scales_version": scales.scales_version(),
        "season_label": season_label_from_run(run),
        "progress": progress.to_dict(),
        "eligibility": {str(k): int(v) for k, v in counts.items()},
        "purchasability_models": {
            fam: state.calibrator.model(fam) for fam in ("FT_1X2", "DOUBLE_CHANCE", "HT_1X2", "FT_OVER_UNDER")
        },
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
