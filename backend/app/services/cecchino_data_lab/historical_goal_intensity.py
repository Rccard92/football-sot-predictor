"""Intensità Goal storica Cecchino Lab — parità parziale (no bundle Today).

Usa le stesse 7 feature core e le funzioni pure TrainEcdf / _pillar_scores_from_pct.
ECDF progressivo solo su partite eligible_core precedenti dello stesso run.
xG assente nei CSV → missing, mai imputato a 0.
"""

from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    TrainEcdf,
    _pillar_scores_from_pct,
)
from app.services.cecchino.cecchino_goal_intensity_v5_dimension_registry import (
    GOAL_INTENSITY_V5_DIMENSION_REGISTRY,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import BUNDLE_FEATURE_KEYS
from app.services.cecchino_data_lab.historical_context_builder import (
    prior_proxies_strict,
    team_priors,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_goal_intensity_compatibility,
)

MODULE_VERSION = "cecchino_lab_goal_intensity_historical_v1"
FORMULA_VERSION = "cecchino_lab_goal_intensity_pillars_v1"
MIN_CORE_SAMPLE = 10
MIN_ECDF_TRAIN_N = 10

PILLAR_DISPLAY_KEYS = (
    ("offensive_production", "OP1_HOME_LONG_TERM", "OP1_HOME_LONG_TERM"),
    ("defensive_solidity", "defensive_solidity_display", "DV1_MEAN_CONCEDED"),
    ("match_tempo", "MT1_LONG_TERM", "MT1_LONG_TERM"),
    ("offensive_stability", "offensive_stability_display", "OV1_STD"),
)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _team_scored(priors: list[Any], team_id: int) -> list[float]:
    out: list[float] = []
    tid = int(team_id)
    for p in priors:
        if p.goals_home is None or p.goals_away is None:
            continue
        if int(p.home_team_id) == tid:
            out.append(float(p.goals_home))
        elif int(p.away_team_id) == tid:
            out.append(float(p.goals_away))
    return out


def _team_conceded(priors: list[Any], team_id: int) -> list[float]:
    out: list[float] = []
    tid = int(team_id)
    for p in priors:
        if p.goals_home is None or p.goals_away is None:
            continue
        if int(p.home_team_id) == tid:
            out.append(float(p.goals_away))
        elif int(p.away_team_id) == tid:
            out.append(float(p.goals_home))
    return out


def _combined_totals(fixtures: list[Any]) -> list[float]:
    out: list[float] = []
    for fx in fixtures:
        if fx.goals_home is None or fx.goals_away is None:
            continue
        out.append(float(fx.goals_home) + float(fx.goals_away))
    return out


def extract_bundle_features_from_proxies(
    *,
    competition_ordered: list[Any],
    target: Any,
) -> dict[str, Any]:
    """Ricostruisce le 7 BUNDLE_FEATURE_KEYS da prior Lab (anti-leakage)."""
    priors = prior_proxies_strict(competition_ordered, target)
    hid = int(getattr(target, "home_team_id", 0) or 0)
    aid = int(getattr(target, "away_team_id", 0) or 0)
    home_prior = team_priors(priors, hid)
    away_prior = team_priors(priors, aid)

    home_scored = _team_scored(home_prior, hid)
    away_scored = _team_scored(away_prior, aid)
    home_conc = _team_conceded(home_prior, hid)
    away_conc = _team_conceded(away_prior, aid)

    combined_ids: dict[int, Any] = {}
    for fx in home_prior + away_prior:
        combined_ids[int(fx.id)] = fx
    combined = sorted(
        combined_ids.values(),
        key=lambda f: (
            f.kickoff_at or datetime.min,
            int(f.id),
        ),
    )
    last5 = combined[-5:] if combined else []
    totals_all = _combined_totals(combined)
    totals5 = _combined_totals(last5)

    pair_scored_10 = (home_scored[-10:] if home_scored else []) + (
        away_scored[-10:] if away_scored else []
    )
    std_last10 = None
    if len(pair_scored_10) >= 2:
        std_last10 = round(statistics.pstdev(pair_scored_10), 6)

    features: dict[str, float | None] = {
        "home_goals_scored_avg": _avg(home_scored),
        "home_goals_scored_rolling_5": _avg(home_scored[-5:]) if home_scored else None,
        "home_goals_conceded_avg": _avg(home_conc),
        "away_goals_conceded_avg": _avg(away_conc),
        "total_goals_avg": _avg(totals_all),
        "total_goals_rolling_5": _avg(totals5),
        "goals_scored_std_last_10": std_last10,
        # diagnostici (non in BUNDLE ma utili)
        "away_goals_scored_avg": _avg(away_scored),
        "away_goals_scored_rolling_5": _avg(away_scored[-5:]) if away_scored else None,
    }
    sample_size = min(len(home_prior), len(away_prior)) if home_prior and away_prior else 0
    # Allineamento gate live: sample_size >= 10 e tutte le 7 chiavi
    pair_n = len(home_prior) + len(away_prior)
    return {
        "features": features,
        "sample_size": sample_size,
        "home_prior_n": len(home_prior),
        "away_prior_n": len(away_prior),
        "pair_prior_n": pair_n,
        "leakage_ok": True,
        "target_excluded": True,
    }


def _score_band(score: float | None) -> tuple[str | None, str | None]:
    if score is None:
        return None, None
    s = float(score)
    if s < 20:
        return "very_low", "Molto bassa"
    if s < 40:
        return "low", "Bassa"
    if s < 60:
        return "medium", "Media"
    if s < 80:
        return "high", "Alta"
    return "very_high", "Molto alta"


def _core_features_complete(features: dict[str, float | None]) -> bool:
    return all(features.get(k) is not None for k in BUNDLE_FEATURE_KEYS)


def fit_progressive_ecdfs(
    prior_feature_rows: list[dict[str, Any]],
) -> dict[str, TrainEcdf]:
    """Fit TrainEcdf sulle sole feature di partite precedenti (no target)."""
    ecdfs: dict[str, TrainEcdf] = {}
    for key in BUNDLE_FEATURE_KEYS:
        vals: list[float] = []
        for row in prior_feature_rows:
            feats = row.get("features") if isinstance(row, dict) else None
            if not isinstance(feats, dict):
                continue
            v = feats.get(key)
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            vals.append(fv)
        ecdfs[key] = TrainEcdf(vals)
    return ecdfs


def build_historical_goal_intensity(
    *,
    input_snapshot: dict[str, Any],
    contexts: Any | None,
    competition_ordered: list[Any],
    target: Any,
    prior_feature_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calcola pilastri storici quando scientificamente possibile."""
    compat = build_goal_intensity_compatibility(
        input_snapshot=input_snapshot,
        contexts=contexts,
        has_xg=False,
    )
    extracted = extract_bundle_features_from_proxies(
        competition_ordered=competition_ordered,
        target=target,
    )
    features = extracted["features"]
    sample_size = int(extracted["sample_size"] or 0)
    prior_rows = list(prior_feature_rows or [])
    missing_inputs: list[str] = [
        k for k in BUNDLE_FEATURE_KEYS if features.get(k) is None
    ]
    missing_inputs.append("xg")

    warnings: list[str] = [
        "parity_partial_no_production_bundle",
        "xg_missing_not_imputed",
        "ecdf_progressive_lab_only",
    ]

    core_ok = sample_size >= MIN_CORE_SAMPLE and _core_features_complete(features)
    train_n = len(prior_rows)
    ecdf_ok = train_n >= MIN_ECDF_TRAIN_N

    pillars: dict[str, Any] = {}
    pillar_metrics: dict[str, float | None] = {}
    execution_status = "computed"
    status = "ok"

    if not core_ok:
        execution_status = "insufficient_sample"
        status = "insufficient_sample"
        warnings.append("core_features_or_sample_insufficient")
    elif not ecdf_ok:
        execution_status = "insufficient_ecdf_train"
        status = "insufficient_ecdf_train"
        warnings.append("progressive_ecdf_train_below_minimum")
    else:
        ecdfs = fit_progressive_ecdfs(prior_rows)
        pct: dict[str, float | None] = {
            k: ecdfs[k].transform(features.get(k)) for k in BUNDLE_FEATURE_KEYS
        }
        # diagnostici simmetrici se disponibili
        for extra in ("away_goals_scored_avg", "away_goals_scored_rolling_5"):
            if extra in features and features[extra] is not None:
                # riusa ECDF della chiave home corrispondente se assente
                src = (
                    "home_goals_scored_avg"
                    if "avg" in extra
                    else "home_goals_scored_rolling_5"
                )
                if src in ecdfs:
                    pct[extra] = ecdfs[src].transform(features[extra])
        pillar_metrics = _pillar_scores_from_pct(pct)

        for key, score_key, raw_key in PILLAR_DISPLAY_KEYS:
            score = pillar_metrics.get(score_key)
            raw_value = features.get(
                {
                    "offensive_production": "home_goals_scored_avg",
                    "defensive_solidity": "home_goals_conceded_avg",
                    "match_tempo": "total_goals_avg",
                    "offensive_stability": "goals_scored_std_last_10",
                }[key]
            )
            class_key, label = _score_band(score if isinstance(score, (int, float)) else None)
            reg = GOAL_INTENSITY_V5_DIMENSION_REGISTRY.get(key) or {}
            pillars[key] = {
                "key": key,
                "raw_value": raw_value,
                "score": round(float(score), 4) if score is not None else None,
                "class_key": class_key,
                "label": label or reg.get("label_it"),
                "inputs": {
                    "score_metric": score_key,
                    "raw_metric": raw_key,
                    "pct_inputs": {
                        k: pct.get(k)
                        for k in BUNDLE_FEATURE_KEYS
                        if pct.get(k) is not None
                    },
                },
                "sample_size": sample_size,
                "warnings": list(warnings),
                "status": "ok" if score is not None else "unavailable",
                "formula_version": FORMULA_VERSION,
            }

    final_class = None
    composite = None
    if pillar_metrics:
        vals = [
            pillar_metrics.get("OP1_HOME_LONG_TERM"),
            pillar_metrics.get("DV1_MEAN_CONCEDED"),
            pillar_metrics.get("MT1_LONG_TERM"),
            pillar_metrics.get("OV1_STD"),
        ]
        present = [float(v) for v in vals if v is not None]
        if len(present) == 4:
            composite = round(sum(present) / 4.0, 4)
            ck, cl = _score_band(composite)
            final_class = {"key": ck, "label": cl, "score": composite, "source": "GI_A_STRICT_CORE"}

    payload = {
        **compat,
        "execution_status": execution_status,
        "parity_status": "partial",
        "module_version": MODULE_VERSION,
        "formula_version": FORMULA_VERSION,
        "status": status,
        "pillars": pillars,
        "final_class": final_class,
        "composite_gi_a_strict_core": composite,
        "inputs": {
            "bundle_features": {k: features.get(k) for k in BUNDLE_FEATURE_KEYS},
            "sample_size": sample_size,
            "home_prior_n": extracted["home_prior_n"],
            "away_prior_n": extracted["away_prior_n"],
            "ecdf_train_n": train_n,
            "xg_status": "missing",
            "xg_imputed_to_zero": False,
        },
        "missing_inputs": missing_inputs,
        "anti_leakage": {
            "target_result_excluded": True,
            "future_matches_excluded": True,
            "contemporaneous_excluded": True,
            "production_bundle_not_used": True,
            "only_prior_kickoff_strict": True,
            "prior_eligible_feature_rows_only": True,
        },
        "warnings": warnings,
        "feature_row_for_profile": {
            "features": {k: features.get(k) for k in BUNDLE_FEATURE_KEYS},
            "sample_size": sample_size,
        },
        # retrocompat: non dichiarare V5 completo
        "v5_score_not_executed": True,
        "v5_score": None,
        "historical_score_executed": execution_status == "computed",
    }
    # Rimuovi blocker obsoleto se abbiamo calcolato i pilastri
    blockers = list(payload.get("blockers_for_future_scientific_replay") or [])
    blockers = [b for b in blockers if b != "v5_score_not_executed_on_historical_lab"]
    blockers.append("parity_partial_no_live_v5_bundle")
    if "xg" in missing_inputs or "missing_xg" not in blockers:
        if "missing_xg" not in blockers:
            blockers.append("missing_xg")
    payload["blockers_for_future_scientific_replay"] = blockers
    fa = dict(payload.get("feature_availability") or {})
    fa["historical_pillars_computed"] = execution_status == "computed"
    fa["parity_status"] = "partial"
    payload["feature_availability"] = fa
    return payload
