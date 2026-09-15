"""Dati per l'Indice di Acquistabilita' V2.5 (orchestratore): righe mercato delle RUN V2.5.

Solo lettura. Dalle tabelle RUN si leggono i moduli pre-partita, la probabilita' Cecchino
del mercato, il segnale, l'esito e la quota reale (la quota serve solo per il guadagno).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2.constants import LAYER_CORE_STRICT
from app.services.cecchino_v25.constants import RUN_V25_VERSION
from app.services.cecchino_v25.orchestrator import (
    FEATURES,
    PLAYABLE_MIN_QUOTA,
    PREDICTION_MIN_SCORE,
    MarketModel,
    decision,
    match_features_from_modules,
    row_features,
)


@dataclass
class MarketData:
    """Righe di un mercato in una stagione, in array (feature nell'ordine di FEATURES, NaN se mancano)."""

    x: np.ndarray
    probability: np.ndarray
    won: np.ndarray
    quota: np.ndarray  # NaN se la quota reale manca
    match_id: np.ndarray
    match_day: np.ndarray


def v25_runs_by_season(db: Session, engine_version: str | None = None) -> dict[str, int]:
    """Ultima RUN V2.5 completata per stagione."""
    rows = db.execute(
        text(
            """
            SELECT id, module_policy_json->>'season_label' AS season
            FROM cecchino_run_v2_runs
            WHERE run_version = :v AND status IN ('completed', 'completed_with_warnings')
            ORDER BY id
            """
        ),
        {"v": RUN_V25_VERSION},
    ).all()
    out: dict[str, int] = {}
    for run_id, season in rows:
        if season:
            out[str(season)] = int(run_id)
    return dict(sorted(out.items()))


def load_run_rows(db: Session, run_id: int) -> dict[str, MarketData]:
    result = db.execute(
        text(
            """
            SELECT mr.market_key, mr.lab_match_id, s.kickoff_at, mr.probability, mr.won, mr.signal_active,
                   CASE WHEN mr.is_real_quote THEN mr.quota_book END AS quota,
                   s.cecchino_output_json->'final' AS final,
                   s.goal_markets_json->'lambda' AS lambdas,
                   s.balance_v5_json AS balance,
                   s.goal_intensity_json AS gi
            FROM cecchino_run_v2_market_results mr
            JOIN cecchino_run_v2_match_snapshots s ON s.id = mr.match_snapshot_id
            WHERE mr.run_id = :rid
              AND mr.observation_layer = :layer
              AND s.eligibility_status = 'eligible_core'
              AND mr.won IS NOT NULL
              AND mr.probability IS NOT NULL
            ORDER BY s.kickoff_at, mr.lab_match_id
            """
        ),
        {"rid": int(run_id), "layer": LAYER_CORE_STRICT},
    )
    match_cache: dict[int, dict[str, float | None]] = {}
    buckets: dict[str, dict[str, list]] = {}
    nan = float("nan")
    for market_key, match_id, kickoff, probability, won, signal_active, quota, final, lambdas, balance, gi in result:
        mid = int(match_id)
        match = match_cache.get(mid)
        if match is None:
            match = match_features_from_modules(final=final, lambdas=lambdas, balance=balance, goal_intensity=gi)
            match_cache[mid] = match
        feats = row_features(match, float(probability), bool(signal_active))
        if feats is None:
            continue
        b = buckets.setdefault(str(market_key), {k: [] for k in ("x", "p", "y", "q", "m", "d")})
        b["x"].append([nan if feats[k] is None else float(feats[k]) for k in FEATURES])  # type: ignore[arg-type]
        b["p"].append(float(probability))
        b["y"].append(1.0 if won else 0.0)
        b["q"].append(float(quota) if quota is not None else nan)
        b["m"].append(mid)
        b["d"].append(kickoff.date().isoformat() if kickoff else "")
    return {
        key: MarketData(
            x=np.asarray(b["x"], dtype=float),
            probability=np.asarray(b["p"]),
            won=np.asarray(b["y"]),
            quota=np.asarray(b["q"]),
            match_id=np.asarray(b["m"]),
            match_day=np.asarray(b["d"]),
        )
        for key, b in buckets.items()
    }


def live_rows_from_pre(pre: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Righe per mercato dai moduli V2.5 calcolati dal vivo (stessa forma della RUN)."""
    goals = pre.get("goals")
    lambdas = {
        "ft_home": getattr(goals, "lambda_home", None),
        "ft_away": getattr(goals, "lambda_away", None),
        "ht_home": getattr(goals, "ht_lambda_home", None),
        "ht_away": getattr(goals, "ht_lambda_away", None),
        "reliability": getattr(goals, "reliability", None),
    }
    match = match_features_from_modules(
        final=(pre.get("cecchino") or {}).get("final"),
        lambdas=lambdas,
        balance=pre.get("balance"),
        goal_intensity=pre.get("gi"),
    )
    signal_index = pre.get("signal_index") or {}
    out: dict[str, dict[str, float | None]] = {}
    for key, probability in (pre.get("probabilities") or {}).items():
        feats = row_features(match, probability, bool((signal_index.get(key) or {}).get("signal_active")))
        if feats is not None:
            out[str(key)] = feats
    return out


# --- dal vivo --------------------------------------------------------------------------------

_FROZEN_PATH = Path(__file__).with_name("frozen_orchestrator.json")


@lru_cache(maxsize=1)
def frozen_orchestrator() -> dict[str, Any]:
    """Parametri congelati (allenati sulle RUN V2.5 2021/22-2024/25; 2025/26 tenuta fuori)."""
    payload = json.loads(_FROZEN_PATH.read_text(encoding="utf-8"))
    payload["_models"] = {k: MarketModel.from_dict(v) for k, v in (payload.get("models") or {}).items()}
    return payload


def purchasability_index_live(pre: dict[str, Any], quotas: dict[str, float | None]) -> dict[str, Any]:
    """Indice di Acquistabilita' V2.5 (orchestratore) per una partita: moduli -> stima -> punteggio.
    `quotas` serve solo alla fine per quota minima e "giocabile"."""
    frozen = frozen_orchestrator()
    models: dict[str, MarketModel] = frozen["_models"]
    rows = live_rows_from_pre(pre)
    markets: dict[str, Any] = {}
    for key, feats in rows.items():
        model = models.get(key)
        if model is None:
            continue
        p_est = float(model.predict([feats])[0])
        markets[key] = decision(p_est, model.base_rate, quotas.get(key))
    predictions = sorted((k for k, d in markets.items() if d["is_prediction"]), key=lambda k: -markets[k]["score"])
    return {
        "status": "ok" if markets else "unavailable",
        "module_version": frozen.get("module_version"),
        "trained_on": frozen.get("trained_on"),
        "prediction_min_score": PREDICTION_MIN_SCORE,
        "playable_min_quota": PLAYABLE_MIN_QUOTA,
        "markets": markets,
        "predictions": predictions,
    }
