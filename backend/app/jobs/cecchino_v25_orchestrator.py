"""Indice di Acquistabilita' V2.5 (orchestratore): esame e congelamento.

  python -m app.jobs.cecchino_v25_orchestrator --mode dev     # prova su 2022/23, 2023/24, 2024/25
  python -m app.jobs.cecchino_v25_orchestrator --mode final   # esame finale una sola volta su 2025/26
  python -m app.jobs.cecchino_v25_orchestrator --mode freeze  # parametri sulle stagioni tranne l'ultima (JSON)

Solo lettura del database. Stampa JSON su stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

import numpy as np
from threadpoolctl import threadpool_limits

from app.core.database import SessionLocal
from app.services.cecchino_v25.orchestrator import (
    ENGINE_FEATURES,
    FEATURES,
    MODULE_VERSION,
    ExamCriteria,
    exam_verdict,
    fit_market_matrix,
    season_report,
)
from app.services.cecchino_v25.orchestrator_data import MarketData, load_run_rows, v25_runs_by_season

ENGINE_COLS = [FEATURES.index(f) for f in ENGINE_FEATURES]


def _stack(parts: list[MarketData]) -> MarketData:
    return MarketData(
        x=np.vstack([p.x for p in parts]),
        probability=np.concatenate([p.probability for p in parts]),
        won=np.concatenate([p.won for p in parts]),
        quota=np.concatenate([p.quota for p in parts]),
        match_id=np.concatenate([p.match_id for p in parts]),
        match_day=np.concatenate([p.match_day for p in parts]),
    )


def _predict_season(train: list[dict[str, MarketData]], test: dict[str, MarketData]):
    """Allena per mercato sulle stagioni passate e stima la stagione di prova."""
    out: dict[str, list[np.ndarray]] = {"p_est": [], "p_engine": [], "base": [], "won": [], "quota": [], "day": []}
    coefs: dict[str, dict[str, float]] = {}
    for key, data in sorted(test.items()):
        parts = [season[key] for season in train if key in season]
        if not parts:
            continue
        tr = _stack(parts)
        model = fit_market_matrix(key, tr.x, tr.won)
        engine = fit_market_matrix(key, tr.x[:, ENGINE_COLS], tr.won, features=ENGINE_FEATURES)
        out["p_est"].append(model.predict_raw(data.x))
        out["p_engine"].append(engine.predict_raw(data.x[:, ENGINE_COLS]))
        out["base"].append(np.full(data.won.size, model.base_rate))
        out["won"].append(data.won)
        out["quota"].append(data.quota)
        out["day"].append(data.match_day)
        coefs[key] = {f: round(c, 4) for f, c in zip(("intercetta",) + FEATURES, model.coef)}
    return {k: np.concatenate(v) for k, v in out.items()}, coefs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dev", "final", "freeze"), required=True)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        runs = v25_runs_by_season(db)
        seasons = list(runs.keys())
        data = {s: load_run_rows(db, runs[s]) for s in seasons}
    finally:
        db.close()
    criteria = ExamCriteria()
    report: dict = {"module_version": MODULE_VERSION, "mode": args.mode, "runs": runs, "criteria": asdict(criteria)}
    with threadpool_limits(limits=1, user_api="blas"):
        if args.mode == "freeze":
            # l'ultima stagione resta fuori: e' l'esame finale, da usare una sola volta
            trained_on = seasons[:-1]
            models = {}
            for key in sorted(data[trained_on[-1]].keys()):
                tr = _stack([data[s][key] for s in trained_on if key in data[s]])
                models[key] = fit_market_matrix(key, tr.x, tr.won).to_dict()
            report["trained_on"] = trained_on
            report["held_out"] = seasons[-1:]
            report["models"] = models
        else:
            targets = seasons[1:-1] if args.mode == "dev" else seasons[-1:]
            per_season = {}
            pooled_parts = []
            for target in targets:
                train = [data[s] for s in seasons if s < target]
                arrays, coefs = _predict_season(train, data[target])
                per_season[target] = season_report(
                    arrays["p_est"], arrays["p_engine"], arrays["base"], arrays["won"], arrays["quota"], arrays["day"]
                )
                per_season[target]["coefficients"] = coefs
                pooled_parts.append(arrays)
            pooled = {k: np.concatenate([p[k] for p in pooled_parts]) for k in pooled_parts[0]}
            report["seasons"] = per_season
            report["pooled"] = season_report(pooled["p_est"], pooled["p_engine"], pooled["base"], pooled["won"], pooled["quota"], pooled["day"])
            report["verdict"] = exam_verdict(
                {s: {k: v for k, v in r.items() if k != "coefficients"} for s, r in per_season.items()},
                report["pooled"],
                criteria,
            )
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
