"""Backtest offline modelli pesi Cecchino A–F — formula V3 Decimal2 + consenso min-two (zero API-Football)."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    STATUS_AVAILABLE,
    format_model_weights_display,
    get_cecchino_weight_model,
    model_meta_for_key,
    model_weights_to_picchetto_map,
)
from app.services.cecchino.cecchino_engine import (
    compute_final_odds,
    picchetti_blocks_from_output_json,
)
from app.services.cecchino.cecchino_signal_aggregation import (
    DEFAULT_MONITORING_VERSION,
    _bucket_counts,
    _enrich_taken_odds_metrics,
    resolve_monitoring_version,
)
from app.services.cecchino.cecchino_signal_consensus import (
    ACQ_REJECTED_INSUFFICIENT,
    CURRENT_SIGNAL_FORMULA_VERSION,
    FORMULA_SOURCE_OFFLINE_WEIGHT,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    normalize_formula_version,
)
from app.services.cecchino.cecchino_signal_evaluation import evaluate_activations_for_fixture
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signal_value_gate import merge_sync_value_counters, SYNC_VALUE_COUNTER_KEYS
from app.services.cecchino.cecchino_signal_goal_refs import resolve_under_2_5_cecchino_odd_from_fixture
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix

logger = logging.getLogger(__name__)

_CONSENSUS_SYNC_COUNTER_KEYS: tuple[str, ...] = (
    "groups_consensus_passed",
    "groups_consensus_rejected",
    "single_formula_exempt_acquired",
    "raw_si_cells",
    "acquired_formula_cells",
    "draw_pt_blocked_by_consensus",
)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sample_from_stats(stats_snapshot: dict[str, Any] | None) -> int:
    if not stats_snapshot or not isinstance(stats_snapshot, dict):
        return 0
    block = (stats_snapshot.get("input_snapshot") or stats_snapshot).get("home_away") or {}
    home = int(block.get("home_sample_count") or block.get("home_sample") or 0)
    away = int(block.get("away_sample_count") or block.get("away_sample") or 0)
    return max(0, home + away)


def _fixtures_in_range(db: Session, date_from: date, date_to: date) -> list[CecchinoTodayFixture]:
    return list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date >= date_from,
                CecchinoTodayFixture.scan_date <= date_to,
            ),
        ).all(),
    )


def _has_picchetti_output(row: CecchinoTodayFixture) -> bool:
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return False
    picchetti = output.get("picchetti")
    return isinstance(picchetti, dict) and len(picchetti) > 0


def build_signals_matrix_for_model(row: CecchinoTodayFixture, model_key: str) -> dict[str, Any] | None:
    """Matrice corrente V3 + consensus ricostruita dai pesi del modello (in memoria)."""
    output = row.cecchino_output_json
    if not isinstance(output, dict):
        return None
    picchetti = picchetti_blocks_from_output_json(output)
    if not picchetti:
        return None
    weights = model_weights_to_picchetto_map(model_key)
    final = compute_final_odds(picchetti, weights=weights)
    if final.status != STATUS_AVAILABLE:
        return None
    return build_signals_matrix(
        q1=final.quota_1,
        qx=final.quota_x,
        q2=final.quota_2,
        sample_home_away_split=_sample_from_stats(row.stats_snapshot_json),
        prob_1=final.prob_1,
        prob_x=final.prob_x,
        prob_2=final.prob_2,
        under_2_5_cecchino_odd=resolve_under_2_5_cecchino_odd_from_fixture(row),
    )


def recompute_cecchino_signals_for_model(
    db: Session,
    today_fixture_id: int,
    model_key: str,
    *,
    evaluate_after: bool = True,
    min_book_odds: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    """Ricalcola segnali 1X2 per un modello pesi senza modificare cecchino_output_json.

    Consenso e activation sono scopati per model_key (separati tra A–F).
    """
    mk = str(model_key).upper()
    get_cecchino_weight_model(mk)

    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "skipped", "reason": "fixture_not_found", "model_key": mk}

    if not _has_picchetti_output(row):
        return {"status": "skipped", "reason": "missing_picchetti", "model_key": mk}

    signals_matrix = build_signals_matrix_for_model(row, mk)
    if not isinstance(signals_matrix, dict) or signals_matrix.get("status") != STATUS_AVAILABLE:
        return {"status": "skipped", "reason": "signals_matrix_unavailable", "model_key": mk}

    meta = model_meta_for_key(mk)
    sync_counts = sync_cecchino_signal_activations(
        db,
        int(today_fixture_id),
        model_key=mk,
        signals_matrix=signals_matrix,
        model_meta=meta,
        min_book_odds=min_book_odds,
        formula_source_mode=FORMULA_SOURCE_OFFLINE_WEIGHT,
        formula_version=CURRENT_SIGNAL_FORMULA_VERSION,
    )

    eval_counts: dict[str, int] = {}
    if evaluate_after:
        eval_counts = evaluate_activations_for_fixture(db, int(today_fixture_id))

    return {
        "status": "ok",
        "model_key": mk,
        "today_fixture_id": int(today_fixture_id),
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "formula_source_mode": FORMULA_SOURCE_OFFLINE_WEIGHT,
        **sync_counts,
        **eval_counts,
    }


def _load_model_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    model_key: str,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> list[CecchinoSignalActivation]:
    fv = normalize_formula_version(formula_version)
    return list(
        db.scalars(
            select(CecchinoSignalActivation).where(
                CecchinoSignalActivation.scan_date >= date_from,
                CecchinoSignalActivation.scan_date <= date_to,
                CecchinoSignalActivation.model_key == model_key,
                CecchinoSignalActivation.is_current.is_(True),
                CecchinoSignalActivation.signal_value.is_(True),
                CecchinoSignalActivation.signal_formula_version == fv,
            ),
        ).all(),
    )


def _unique_acquired_sign_count(rows: list[CecchinoSignalActivation]) -> int:
    keys = {
        (
            int(r.today_fixture_id),
            str(r.model_key or ""),
            normalize_formula_version(r.signal_formula_version),
            str(r.signal_group or ""),
            str(r.target_market_key or ""),
        )
        for r in rows
        if r.is_acquired
    }
    return len(keys)


def _rejected_consensus_group_count(rows: list[CecchinoSignalActivation]) -> int:
    keys: set[tuple] = set()
    for r in rows:
        status = str(r.acquisition_status or "")
        if status == ACQ_REJECTED_INSUFFICIENT or (
            r.consensus_passed is False and int(r.consensus_yes_count or 0) > 0
        ):
            keys.add((int(r.today_fixture_id), str(r.signal_group or "")))
    return len(keys)


def _model_bucket_from_activations(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    model_key: str,
    only_acquired: bool = True,
    formula_version: str = CURRENT_SIGNAL_FORMULA_VERSION,
) -> dict[str, Any]:
    """Bucket metriche per modello: default formula corrente + soli segni acquisiti."""
    rows = _load_model_activations(
        db,
        date_from=date_from,
        date_to=date_to,
        model_key=model_key,
        formula_version=formula_version,
    )
    formula_activations = len(rows)
    unique_acquired_signs = _unique_acquired_sign_count(rows)
    rejected_consensus_groups = _rejected_consensus_group_count(rows)

    scored = [r for r in rows if r.is_acquired] if only_acquired else list(rows)
    bucket = _bucket_counts(scored)
    bucket = _enrich_taken_odds_metrics(bucket, scored)
    bucket["formula_activations"] = formula_activations
    bucket["unique_acquired_signs"] = unique_acquired_signs
    bucket["rejected_consensus_groups"] = rejected_consensus_groups
    return bucket


def _merge_consensus_sync_counters(base: dict[str, int], other: dict[str, Any]) -> None:
    merge_sync_value_counters(base, other)
    for key in _CONSENSUS_SYNC_COUNTER_KEYS:
        base[key] = int(base.get(key, 0)) + int(other.get(key, 0) or 0)


def backtest_cecchino_weight_models(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    models: list[str] | None = None,
    force: bool = True,
    evaluate_after: bool = True,
    use_existing_bookmaker_odds: bool = True,
    refresh_bookmaker_odds: bool = False,
    min_book_odds: dict[str, Decimal] | None = None,
) -> dict[str, Any]:
    """Backtest offline modelli pesi su range date — zero API-Football.

    Per ogni model_key ricostruisce matrice corrente V3 e applica consenso min-two;
    activation V3; source mode = offline_weight_model_recompute.
    """
    if refresh_bookmaker_odds:
        logger.warning("backtest_models: refresh_bookmaker_odds ignored (offline backtest)")

    model_keys = [str(m).upper() for m in (models or list(CECCHINO_WEIGHT_MODEL_KEYS))]
    for mk in model_keys:
        get_cecchino_weight_model(mk)

    fixtures = _fixtures_in_range(db, date_from, date_to)
    warnings: list[str] = []
    by_model: list[dict[str, Any]] = []

    totals_created = 0
    totals_evaluated = 0
    value_totals = {key: 0 for key in SYNC_VALUE_COUNTER_KEYS}
    value_totals["missing_value_quote"] = 0
    for key in _CONSENSUS_SYNC_COUNTER_KEYS:
        value_totals[key] = 0

    for mk in model_keys:
        model_created = 0
        model_skipped = 0
        model_rejected_sync = 0
        for row in fixtures:
            if not _has_picchetti_output(row):
                model_skipped += 1
                continue
            result = recompute_cecchino_signals_for_model(
                db,
                int(row.id),
                mk,
                evaluate_after=evaluate_after,
                min_book_odds=min_book_odds,
            )
            if result.get("status") == "ok":
                model_created += int(result.get("created") or 0) + int(result.get("updated") or 0)
                _merge_consensus_sync_counters(value_totals, result)
                model_rejected_sync += int(result.get("groups_consensus_rejected") or 0)
            else:
                model_skipped += 1

        bucket = _model_bucket_from_activations(
            db,
            date_from=date_from,
            date_to=date_to,
            model_key=mk,
            only_acquired=True,
            formula_version=CURRENT_SIGNAL_FORMULA_VERSION,
        )
        won = int(bucket.get("won") or 0)
        lost = int(bucket.get("lost") or 0)
        settled = won + lost
        pending = int(bucket.get("pending") or 0)
        totals_created += int(bucket.get("formula_activations") or 0)
        totals_evaluated += settled

        by_model.append(
            {
                "model_key": mk,
                "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
                "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
                "formula_source_mode": FORMULA_SOURCE_OFFLINE_WEIGHT,
                "signals_created": int(bucket.get("activations") or 0),
                "formula_activations": int(bucket.get("formula_activations") or 0),
                "unique_acquired_signs": int(bucket.get("unique_acquired_signs") or 0),
                "rejected_consensus_groups": int(
                    bucket.get("rejected_consensus_groups") or model_rejected_sync or 0,
                ),
                "signals_evaluated": settled,
                "won": won,
                "lost": lost,
                "pending": pending,
                "win_rate": bucket.get("success_rate"),
                "avg_won_book_odds": bucket.get("avg_won_book_odds"),
                "quota_void": bucket.get("quota_void"),
                "taken_profit_indicator": bucket.get("taken_profit_indicator"),
                "fixtures_processed": len(fixtures) - model_skipped,
                "fixtures_skipped": model_skipped,
                "sync_operations": model_created,
            },
        )

    if not force:
        warnings.append("force=false: sync idempotente applicato comunque per fixture/modello")

    value_totals["missing_value_quote"] = (
        value_totals["missing_book_quote_skipped"] + value_totals["missing_cecchino_quote_skipped"]
    )

    db.commit()

    return {
        "status": "ok",
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "formula_source_mode": FORMULA_SOURCE_OFFLINE_WEIGHT,
        "fixtures_found": len(fixtures),
        "models_processed": model_keys,
        "by_model": by_model,
        "signals_created_total": totals_created,
        "signals_evaluated_total": totals_evaluated,
        **value_totals,
        "warnings": warnings,
    }


def build_models_summary(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    monitoring_version: str | None = None,
) -> dict[str, Any]:
    """Summary comparativo card A–F sulla coorte Monitoraggio V1/V2 (sola lettura).

    V1 → tutte le activation current V3 value-gated (anche rejected consensus).
    V2 → soltanto acquired canonical (comportamento pre-SIGNALS-MON-02.1).
    unique_acquired_signs resta conteggio acquired-canonical (strategia A).
    """
    resolved_mv, effective_af = resolve_monitoring_version(monitoring_version, None)
    only_acquired = effective_af == "acquired"
    models: list[dict[str, Any]] = []
    for mk in CECCHINO_WEIGHT_MODEL_KEYS:
        model = get_cecchino_weight_model(mk)
        bucket = _model_bucket_from_activations(
            db,
            date_from=date_from,
            date_to=date_to,
            model_key=mk,
            only_acquired=only_acquired,
            formula_version=CURRENT_SIGNAL_FORMULA_VERSION,
        )
        models.append(
            {
                "model_key": mk,
                "label": str(model["label"]),
                "short_label": str(model.get("short_label") or f"Modello {mk}"),
                "weights": format_model_weights_display(mk),
                "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
                "activations": int(bucket.get("activations") or 0),
                "formula_activations": int(bucket.get("formula_activations") or 0),
                "unique_acquired_signs": int(bucket.get("unique_acquired_signs") or 0),
                "rejected_consensus_groups": int(bucket.get("rejected_consensus_groups") or 0),
                "settled": int(bucket.get("settled") or 0),
                "won": int(bucket.get("won") or 0),
                "lost": int(bucket.get("lost") or 0),
                "pending": int(bucket.get("pending") or 0),
                "win_rate": bucket.get("success_rate"),
                "avg_won_book_odds": bucket.get("avg_won_book_odds"),
                "quota_void": bucket.get("quota_void"),
                "void_margin": bucket.get("void_margin"),
                "taken_profit_indicator": bucket.get("taken_profit_indicator"),
            },
        )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "default_model_key": CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "monitoring_version": resolved_mv or DEFAULT_MONITORING_VERSION,
        "acquisition_filter": effective_af,
        "models": models,
    }
