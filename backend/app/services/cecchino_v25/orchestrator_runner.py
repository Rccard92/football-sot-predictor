"""Esame e congelamento dell'Indice di Acquistabilita' orchestratore, uguale per ogni motore.

Riceve per stagione e per mercato le righe (feature senza quote, esito, quota reale) e:
- dev: allena solo in avanti e prova le stagioni intermedie (tutte tranne la prima e l'ultima);
- final: allena su tutte tranne l'ultima e prova l'ultima (esame finale, una volta sola);
- freeze: parametri sulle stagioni tranne l'ultima.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np
from threadpoolctl import threadpool_limits

from app.services.cecchino_v25.orchestrator import ExamCriteria, exam_verdict, fit_market_matrix, season_report
from app.services.cecchino_v25.orchestrator_data import MarketData


def stack(parts: list[MarketData]) -> MarketData:
    return MarketData(
        x=np.vstack([p.x for p in parts]),
        probability=np.concatenate([p.probability for p in parts]),
        won=np.concatenate([p.won for p in parts]),
        quota=np.concatenate([p.quota for p in parts]),
        match_id=np.concatenate([p.match_id for p in parts]),
        match_day=np.concatenate([p.match_day for p in parts]),
    )


def _predict_season(
    train: list[dict[str, MarketData]],
    test: dict[str, MarketData],
    features: tuple[str, ...],
    engine_features: tuple[str, ...],
    data_features: tuple[str, ...],
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, float]]]:
    # le colonne di data.x seguono data_features: ogni modello prende solo le sue
    cols = [data_features.index(f) for f in features]
    engine_cols = [data_features.index(f) for f in engine_features]
    out: dict[str, list[np.ndarray]] = {"p_est": [], "p_engine": [], "base": [], "won": [], "quota": [], "day": []}
    coefs: dict[str, dict[str, float]] = {}
    for key, data in sorted(test.items()):
        parts = [season[key] for season in train if key in season]
        if not parts:
            continue
        tr = stack(parts)
        model = fit_market_matrix(key, tr.x[:, cols], tr.won, features=features)
        engine = fit_market_matrix(key, tr.x[:, engine_cols], tr.won, features=engine_features)
        out["p_est"].append(model.predict_raw(data.x[:, cols]))
        out["p_engine"].append(engine.predict_raw(data.x[:, engine_cols]))
        out["base"].append(np.full(data.won.size, model.base_rate))
        out["won"].append(data.won)
        out["quota"].append(data.quota)
        out["day"].append(data.match_day)
        coefs[key] = {f: round(c, 4) for f, c in zip(("intercetta",) + features, model.coef)}
    return {k: np.concatenate(v) for k, v in out.items()}, coefs


def run_mode(
    mode: str,
    data: dict[str, dict[str, MarketData]],
    *,
    features: tuple[str, ...],
    engine_features: tuple[str, ...],
    module_version: str,
    runs: dict[str, Any],
    data_features: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    data_features = tuple(data_features or features)
    cols = [data_features.index(f) for f in features]
    seasons = sorted(data)
    criteria = ExamCriteria()
    report: dict[str, Any] = {"module_version": module_version, "mode": mode, "runs": runs, "criteria": asdict(criteria)}
    with threadpool_limits(limits=1, user_api="blas"):
        if mode == "freeze":
            trained_on = seasons[:-1]
            models = {}
            for key in sorted(data[trained_on[-1]].keys()):
                tr = stack([data[s][key] for s in trained_on if key in data[s]])
                models[key] = fit_market_matrix(key, tr.x[:, cols], tr.won, features=features).to_dict()
            report["trained_on"] = trained_on
            report["held_out"] = seasons[-1:]
            report["models"] = models
            return report
        targets = seasons[1:-1] if mode == "dev" else seasons[-1:]
        per_season: dict[str, dict[str, Any]] = {}
        pooled_parts = []
        for target in targets:
            train = [data[s] for s in seasons if s < target]
            arrays, coefs = _predict_season(train, data[target], features, engine_features, data_features)
            per_season[target] = season_report(arrays["p_est"], arrays["p_engine"], arrays["base"], arrays["won"], arrays["quota"], arrays["day"])
            per_season[target]["coefficients"] = coefs
            pooled_parts.append(arrays)
        pooled = {k: np.concatenate([p[k] for p in pooled_parts]) for k in pooled_parts[0]}
        report["seasons"] = per_season
        report["pooled"] = season_report(pooled["p_est"], pooled["p_engine"], pooled["base"], pooled["won"], pooled["quota"], pooled["day"])
        report["verdict"] = exam_verdict(
            {s: {k: v for k, v in r.items() if k != "coefficients"} for s, r in per_season.items()}, report["pooled"], criteria
        )
        if tuple(features) == tuple(engine_features):
            # indice = sola probabilita' del motore ricalibrata: E2 non si applica (e' il riferimento stesso)
            report["verdict"]["E2"] = None
            report["verdict"]["passed"] = bool(all(report["verdict"][k] for k in ("E1", "E3", "E4", "E5")))
    return report
