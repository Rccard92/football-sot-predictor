"""Context builder deterministici per analisi AI mirate."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PredictiveFixturePrediction, PredictiveSimulationRun
from app.services.backtest.v31_pattern_analysis_buckets import is_non_extreme_high_dynamic
from app.services.backtest.v31_pattern_analysis_recommendations import TOP3_KEYS

AnalysisType = str

TOP3 = list(TOP3_KEYS)


def _row_dict(r: PredictiveFixturePrediction) -> dict[str, Any]:
    return {
        "fixture_id": r.fixture_id,
        "round_number": r.round_number,
        "match": f"{r.home_team_name} vs {r.away_team_name}".strip(" vs "),
        "strategy_key": r.strategy_key,
        "predicted_total_sot": r.predicted_total_sot,
        "actual_total_sot": r.actual_total_sot,
        "error": r.error,
        "abs_error": r.abs_error,
        "predicted_bucket": r.predicted_bucket,
        "actual_bucket": r.actual_bucket,
        "actual_bucket_dynamic": r.actual_bucket_dynamic,
        "win_quality": r.win_quality,
        "outcome_type": r.outcome_type,
        "reason_codes": r.reason_codes_json,
        "probable_reason": r.probable_reason,
        "boost_applied": r.boost_applied,
        "high_total_signal": r.high_total_signal,
        "feature_snapshot": r.feature_snapshot_json,
    }


def _load_predictions_by_fixture(
    db: Session,
    run_id: int,
    *,
    strategy_keys: list[str] | None = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    q = select(PredictiveFixturePrediction).where(PredictiveFixturePrediction.run_id == int(run_id))
    if strategy_keys:
        q = q.where(PredictiveFixturePrediction.strategy_key.in_(strategy_keys))
    rows = db.scalars(q).all()
    by_fixture: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        by_fixture[int(r.fixture_id)][r.strategy_key] = _row_dict(r)
    return dict(by_fixture)


def _pattern_context(run: PredictiveSimulationRun) -> dict[str, Any]:
    pattern = run.pattern_payload_json or {}
    summary = pattern.get("summary") or {}
    return {
        "actual_sot_distribution": summary.get("actual_sot_distribution") or {},
        "dynamic_bucket_thresholds": summary.get("dynamic_bucket_thresholds") or {},
        "top3_cluster_summary": summary.get("top3_cluster_summary") or {},
        "pattern_verdict": summary.get("pattern_verdict") or {},
    }


def build_context(
    db: Session,
    run_id: int,
    analysis_type: AnalysisType,
    *,
    fixture_id: int | None = None,
    strategy_key: str | None = None,
) -> dict[str, Any]:
    run = db.get(PredictiveSimulationRun, int(run_id))
    if run is None:
        return {"error": "RUN_NOT_FOUND"}

    if analysis_type == "missed_high_non_extreme":
        return _build_missed_high_non_extreme(db, run)
    if analysis_type == "false_high_predictions":
        return _build_false_high_predictions(db, run)
    if analysis_type == "top3_model_comparison":
        return _build_top3_comparison(db, run)
    if analysis_type == "single_fixture":
        if fixture_id is None:
            return {"error": "FIXTURE_ID_REQUIRED"}
        return _build_single_fixture(db, run, fixture_id, strategy_key or "v31_bias_dynamic_high_guard")
    return {"error": "UNKNOWN_ANALYSIS_TYPE"}


def _build_missed_high_non_extreme(db: Session, run: PredictiveSimulationRun) -> dict[str, Any]:
    pattern_ctx = _pattern_context(run)
    thresholds = pattern_ctx.get("dynamic_bucket_thresholds") or {}
    p75 = thresholds.get("p75")

    by_fixture = _load_predictions_by_fixture(db, run.id, strategy_keys=TOP3)
    high_non_extreme: list[dict[str, Any]] = []
    understated_by_model: dict[str, int] = {k: 0 for k in TOP3}

    for fid, models in by_fixture.items():
        bias = models.get("v31_bias_corrected")
        if not bias:
            continue
        dyn = bias.get("actual_bucket_dynamic")
        if not is_non_extreme_high_dynamic(dyn):
            continue

        actual = float(bias.get("actual_total_sot") or 0)
        preds = {
            k: float((models.get(k) or {}).get("predicted_total_sot") or 0)
            for k in TOP3
            if models.get(k)
        }
        if not preds:
            continue

        min_pred = min(preds.values())
        understated = actual > min_pred + 0.5 or any(
            (models.get(k) or {}).get("win_quality") == "UNDERSTATED_WIN" for k in TOP3 if models.get(k)
        )
        if not understated:
            continue

        for k in TOP3:
            row = models.get(k)
            if row and row.get("win_quality") == "UNDERSTATED_WIN":
                understated_by_model[k] += 1

        gap = actual - min_pred
        fixture_entry = {
            "fixture_id": fid,
            "round_number": bias.get("round_number"),
            "match": bias.get("match"),
            "actual_total_sot": actual,
            "actual_bucket_dynamic": dyn,
            "gap_vs_min_top3_pred": round(gap, 2),
            "models": {
                k: {
                    "predicted_total_sot": models[k].get("predicted_total_sot"),
                    "error": models[k].get("error"),
                    "abs_error": models[k].get("abs_error"),
                    "win_quality": models[k].get("win_quality"),
                    "boost_applied": models[k].get("boost_applied"),
                    "high_total_signal": models[k].get("high_total_signal"),
                    "reason_codes": models[k].get("reason_codes"),
                    "feature_snapshot": models[k].get("feature_snapshot"),
                }
                for k in TOP3
                if models.get(k)
            },
        }
        high_non_extreme.append(fixture_entry)

    high_non_extreme.sort(key=lambda x: float(x.get("gap_vs_min_top3_pred") or 0), reverse=True)
    total_high_ne = len(
        {
            fid
            for fid, models in by_fixture.items()
            if is_non_extreme_high_dynamic((models.get("v31_bias_corrected") or {}).get("actual_bucket_dynamic"))
        },
    )

    return {
        "analysis_type": "missed_high_non_extreme",
        "pattern_context": pattern_ctx,
        "aggregates": {
            "total_high_non_extreme_fixtures": total_high_ne,
            "understated_count": len(high_non_extreme),
            "understated_by_top3_model": understated_by_model,
            "p75_threshold": p75,
        },
        "top_fixtures": high_non_extreme[:20],
        "guiding_questions": [
            "Perché i modelli non riconoscono le partite alte ma non estreme?",
            "Quali segnali pre-match sembrano sottopesati?",
            "Quale esperimento concreto testare?",
        ],
    }


def _build_false_high_predictions(db: Session, run: PredictiveSimulationRun) -> dict[str, Any]:
    rows = db.scalars(
        select(PredictiveFixturePrediction).where(
            PredictiveFixturePrediction.run_id == run.id,
            PredictiveFixturePrediction.predicted_total_sot >= 9,
            PredictiveFixturePrediction.actual_total_sot <= 7,
        ),
    ).all()

    by_strategy: dict[str, int] = defaultdict(int)
    examples: list[dict[str, Any]] = []
    for r in rows:
        by_strategy[r.strategy_key] += 1
        examples.append(_row_dict(r))

    examples.sort(key=lambda x: float(x.get("abs_error") or 0), reverse=True)

    return {
        "analysis_type": "false_high_predictions",
        "pattern_context": _pattern_context(run),
        "aggregates": {
            "total_false_high_rows": len(rows),
            "count_by_strategy": dict(by_strategy),
        },
        "top_examples": examples[:15],
        "guiding_questions": [
            "Quali modelli generano più falsi positivi high?",
            "Quali segnali pre-match hanno innescato la sovrastima?",
            "Quali guardrail testare per ridurre i falsi positivi?",
        ],
    }


def _build_top3_comparison(db: Session, run: PredictiveSimulationRun) -> dict[str, Any]:
    pattern_ctx = _pattern_context(run)
    cluster_summary = pattern_ctx.get("top3_cluster_summary") or {}
    cluster_counts = cluster_summary.get("counts") or {}

    by_fixture = _load_predictions_by_fixture(db, run.id, strategy_keys=TOP3)
    target_clusters = (
        "dynamic_guard_improves_bias",
        "dynamic_guard_worsens_bias",
        "chaos_catches_high_non_extreme",
        "chaos_false_positive",
        "all_understate_high_non_extreme",
    )
    cluster_samples: dict[str, list[dict[str, Any]]] = {c: [] for c in target_clusters}

    mae_by_strategy: dict[str, list[float]] = {k: [] for k in TOP3}
    for fid, models in by_fixture.items():
        for k in TOP3:
            row = models.get(k)
            if row and row.get("abs_error") is not None:
                mae_by_strategy[k].append(float(row["abs_error"]))

        bias = models.get("v31_bias_corrected")
        hybrid = models.get("v31_bias_dynamic_high_guard")
        chaos = models.get("v31_chaos_game")
        if not (bias and hybrid and chaos):
            continue

        b_ae = float(bias.get("abs_error") or 999)
        h_ae = float(hybrid.get("abs_error") or 999)
        c_ae = float(chaos.get("abs_error") or 999)
        dyn = bias.get("actual_bucket_dynamic")
        chaos_pred = float(chaos.get("predicted_total_sot") or 0)

        cluster_key = None
        if is_non_extreme_high_dynamic(dyn) and h_ae < b_ae - 0.3:
            cluster_key = "dynamic_guard_improves_bias"
        elif is_non_extreme_high_dynamic(dyn) and h_ae > b_ae + 0.3:
            cluster_key = "dynamic_guard_worsens_bias"
        elif is_non_extreme_high_dynamic(dyn) and c_ae <= min(b_ae, h_ae) - 0.2:
            cluster_key = "chaos_catches_high_non_extreme"
        elif chaos_pred >= 10 and dyn in ("low_total", "normal_total"):
            cluster_key = "chaos_false_positive"
        elif is_non_extreme_high_dynamic(dyn) and all(
            (models.get(k) or {}).get("win_quality") == "UNDERSTATED_WIN" for k in TOP3
        ):
            cluster_key = "all_understate_high_non_extreme"

        if cluster_key and len(cluster_samples[cluster_key]) < 10:
            cluster_samples[cluster_key].append(
                {
                    "fixture_id": fid,
                    "match": bias.get("match"),
                    "actual_total_sot": bias.get("actual_total_sot"),
                    "actual_bucket_dynamic": dyn,
                    "models": {
                        k: {
                            "predicted_total_sot": models[k].get("predicted_total_sot"),
                            "error": models[k].get("error"),
                            "abs_error": models[k].get("abs_error"),
                            "win_quality": models[k].get("win_quality"),
                        }
                        for k in TOP3
                    },
                },
            )

    avg_mae = {
        k: round(sum(v) / len(v), 3) if v else None
        for k, v in mae_by_strategy.items()
    }

    return {
        "analysis_type": "top3_model_comparison",
        "pattern_context": pattern_ctx,
        "aggregates": {
            "cluster_counts": cluster_counts,
            "avg_abs_error_by_strategy": avg_mae,
        },
        "cluster_samples": cluster_samples,
        "guiding_questions": [
            "Quando dynamic_high_guard migliora bias_corrected?",
            "Quando dynamic_high_guard peggiora bias_corrected?",
            "Quando chaos_game vede meglio una partita alta?",
            "Quando chaos_game genera falso positivo?",
            "Quali regole possiamo prendere da chaos_game senza copiarlo tutto?",
        ],
    }


def _build_single_fixture(
    db: Session,
    run: PredictiveSimulationRun,
    fixture_id: int,
    strategy_key: str,
) -> dict[str, Any]:
    rows = db.scalars(
        select(PredictiveFixturePrediction).where(
            PredictiveFixturePrediction.run_id == run.id,
            PredictiveFixturePrediction.fixture_id == int(fixture_id),
            PredictiveFixturePrediction.strategy_key.in_(TOP3 + [strategy_key]),
        ),
    ).all()
    if not rows:
        return {"error": "FIXTURE_NOT_FOUND"}

    models = {r.strategy_key: _row_dict(r) for r in rows}
    primary = models.get(strategy_key) or models.get("v31_bias_corrected") or next(iter(models.values()))

    return {
        "analysis_type": "single_fixture",
        "fixture_id": fixture_id,
        "primary_strategy_key": strategy_key,
        "pattern_context": _pattern_context(run),
        "fixture": {
            "match": primary.get("match"),
            "round_number": primary.get("round_number"),
            "actual_total_sot_post_match_only": primary.get("actual_total_sot"),
            "actual_bucket_dynamic": primary.get("actual_bucket_dynamic"),
            "primary_prediction": primary,
        },
        "top3_predictions": {k: models[k] for k in TOP3 if k in models},
        "guiding_questions": [
            "Perché il modello ha sbagliato su questa partita?",
            "È un outlier o un pattern replicabile?",
            "Cosa testare nel modello per casi simili?",
        ],
    }
