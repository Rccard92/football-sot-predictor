"""Indice di Acquistabilita' V3 come orchestratore dei moduli (stesso impianto della V2.5).

Fase A, nessuna quota: per ogni mercato una regressione logistica impara solo da "vinta / persa"
partendo dalla probabilita' V3 del mercato e da tutto quello che la V3 legge della partita:
gol attesi, specialisti (Forza, Gioco tiri e tiri in porta), forma, calendario e indici
(Equilibrio, Pareggio, Intensita' goal, Forma). Mai quote, distanza dal book o "livello".

Variante adottata (esame dev 15/09/2026): "engine", cioe' la sola probabilita' V3 ricalibrata sui
risultati. La variante con tutte le colonne dei moduli non ha passato E2 (l'orchestratore V3 le combina
gia' dentro la sua probabilita', rimetterle aggiunge rumore); la variante engine ha calibrazione e
scarto sulla frequenza normale migliori. Le colonne restano calcolate per trasparenza e nuove prove.

Punteggio, predizioni finali (>= 70) e "giocabile" (quota >= 1,50): identici alla V2.5
(`app/services/cecchino_v25/orchestrator.py`).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_v25.orchestrator import (
    PLAYABLE_MIN_QUOTA,
    PREDICTION_MIN_SCORE,
    MarketModel,
    _f,
    decision,
    logit,
)
from app.services.cecchino_v25.orchestrator_data import MarketData
from app.services.cecchino_v3.constants import MARKET_KEYS
from app.services.cecchino_v3.evaluator import book_probabilities
from app.services.cecchino_v3.market_data import CLOSING_ODDS_COLUMNS, _odds_by_match

MODULE_VERSION = "cecchino_v3_orchestrator_v1"
REFERENCE_RUN_ID = 11  # run finale V3 (walk-forward): stesse probabilita' del motore live
REQUIRED: tuple[str, ...] = ("logit_p", "lambda_home", "lambda_away", "forza_home", "forza_away", "sot_home", "sot_away", "shots_home", "shots_away")
FEATURES: tuple[str, ...] = REQUIRED + (
    "ht_share",
    "evidence_home",
    "evidence_away",
    "sot_volume_home",
    "sot_volume_away",
    "shots_volume_home",
    "shots_volume_away",
    "form_goals_home",
    "form_goals_away",
    "form_shots_home",
    "form_shots_away",
    "eq_value",
    "eq_gap_pp",
    "eq_percentile",
    "draw_prob",
    "draw_delta_pp",
    "draw_league_rate",
    "draw_percentile",
    "gi_total",
    "gi_ratio",
    "gi_league_goals",
    "gi_percentile",
    "forma_gioco_home",
    "forma_gioco_away",
    "forma_risultati_home",
    "forma_risultati_away",
    "rest_days_home",
    "rest_days_away",
    "final_phase",
)
ENGINE_FEATURES: tuple[str, ...] = ("logit_p",)
# Variante "engine": l'indice usa la sola probabilita' V3 (gia' orchestratore di specialisti, forma e
# calendario) ricalibrata sui risultati. Nell'esame dev la versione con tutti i moduli ha peggiorato la
# lettura (E2): la V3 li combina gia' dentro la sua probabilita'.
VARIANTS: dict[str, tuple[str, ...]] = {"modules": FEATURES, "engine": ENGINE_FEATURES}
_FROZEN_PATH = Path(__file__).with_name("frozen_purchasability_index.json")


def match_features(
    *,
    lambda_home: Any,
    lambda_away: Any,
    ht_share: Any,
    evidence_home: Any,
    evidence_away: Any,
    specialists: dict[str, Any] | None,
    indices: dict[str, Any] | None,
) -> dict[str, float | None]:
    """Colonne della partita (stessa forma in Lab e dal vivo), senza quote."""
    sp = specialists or {}
    idx = indices or {}
    forza, sot, shots = sp.get("forza") or {}, sp.get("sot") or {}, sp.get("shots") or {}
    form = sp.get("form") or {}
    cal = sp.get("calendar") or idx.get("calendario") or {}
    eq, draw, gi = idx.get("equilibrio") or {}, idx.get("pareggio") or {}, idx.get("intensita_goal") or {}
    forma = idx.get("forma") or {}
    fh, fa = forma.get("home") or {}, forma.get("away") or {}
    final_phase = cal.get("final_phase")
    return {
        "lambda_home": _f(lambda_home),
        "lambda_away": _f(lambda_away),
        "ht_share": _f(ht_share),
        "evidence_home": _f(evidence_home),
        "evidence_away": _f(evidence_away),
        "forza_home": _f(forza.get("home")),
        "forza_away": _f(forza.get("away")),
        "sot_home": _f(sot.get("home")),
        "sot_away": _f(sot.get("away")),
        "shots_home": _f(shots.get("home")),
        "shots_away": _f(shots.get("away")),
        "sot_volume_home": _f(sot.get("volume_home")),
        "sot_volume_away": _f(sot.get("volume_away")),
        "shots_volume_home": _f(shots.get("volume_home")),
        "shots_volume_away": _f(shots.get("volume_away")),
        "form_goals_home": _f(form.get("goals_home")),
        "form_goals_away": _f(form.get("goals_away")),
        "form_shots_home": _f(form.get("shots_home")),
        "form_shots_away": _f(form.get("shots_away")),
        "eq_value": _f(eq.get("value")),
        "eq_gap_pp": _f(eq.get("gap_pp")),
        "eq_percentile": _f(eq.get("percentile")),
        "draw_prob": _f(draw.get("prob")),
        "draw_delta_pp": _f(draw.get("delta_pp")),
        "draw_league_rate": _f(draw.get("league_draw_rate")),
        "draw_percentile": _f(draw.get("percentile")),
        "gi_total": _f(gi.get("total")),
        "gi_ratio": _f(gi.get("ratio")),
        "gi_league_goals": _f(gi.get("league_goals_avg")),
        "gi_percentile": _f(gi.get("percentile")),
        "forma_gioco_home": _f(fh.get("gioco")),
        "forma_gioco_away": _f(fa.get("gioco")),
        "forma_risultati_home": _f(fh.get("risultati")),
        "forma_risultati_away": _f(fa.get("risultati")),
        "rest_days_home": _f(cal.get("rest_days_home")),
        "rest_days_away": _f(cal.get("rest_days_away")),
        "final_phase": None if final_phase is None else (1.0 if final_phase else 0.0),
    }


def row_vector(match: dict[str, float | None], probability: float | None) -> list[float] | None:
    p = _f(probability)
    if p is None:
        return None
    row = {**match, "logit_p": logit(p)}
    if any(row.get(k) is None for k in REQUIRED):
        return None
    nan = float("nan")
    return [nan if row.get(k) is None else float(row[k]) for k in FEATURES]  # type: ignore[arg-type]


# --- dati del Lab ---------------------------------------------------------------------------


def latest_index_run(db: Session, source_run_id: int) -> int | None:
    return db.execute(
        text("SELECT max(id) FROM cecchino_v3_index_runs WHERE source_run_id = :r AND status = 'completed'"),
        {"r": source_run_id},
    ).scalar()


def load_lab_data(db: Session, run_id: int = REFERENCE_RUN_ID) -> tuple[dict[str, dict[str, MarketData]], dict[str, Any]]:
    """Per stagione e mercato: righe delle partite valutabili (entrambe le squadre con almeno 5 partite)."""
    index_run = latest_index_run(db, run_id)
    matches: dict[int, tuple[str, str, dict[str, float | None]]] = {}
    for r in db.execute(
        text(
            """
            SELECT mp.lab_match_id, mp.season_label, mp.kickoff_at, mp.lambda_home, mp.lambda_away, mp.ht_share,
                   mp.home_evidence, mp.away_evidence, mp.specialists_json, mi.indices_json
            FROM cecchino_v3_match_predictions mp
            LEFT JOIN cecchino_v3_match_indices mi ON mi.lab_match_id = mp.lab_match_id AND mi.index_run_id = :idx
            WHERE mp.run_id = :rid AND mp.eval_eligible
            """
        ),
        {"rid": run_id, "idx": index_run},
    ):
        matches[int(r.lab_match_id)] = (
            str(r.season_label),
            r.kickoff_at.date().isoformat() if r.kickoff_at else "",
            match_features(
                lambda_home=r.lambda_home,
                lambda_away=r.lambda_away,
                ht_share=r.ht_share,
                evidence_home=r.home_evidence,
                evidence_away=r.away_evidence,
                specialists=r.specialists_json,
                indices=r.indices_json,
            ),
        )
    quotes = {mid: book_probabilities(odds) for mid, odds in _odds_by_match(db, run_id, CLOSING_ODDS_COLUMNS).items()}
    buckets: dict[str, dict[str, dict[str, list]]] = {}
    for r in db.execute(
        text(
            """
            SELECT lab_match_id, market_key, probability, won
            FROM cecchino_v3_market_predictions
            WHERE run_id = :rid AND won IS NOT NULL AND market_key = ANY(:keys)
            """
        ),
        {"rid": run_id, "keys": list(MARKET_KEYS)},
    ):
        mid = int(r.lab_match_id)
        info = matches.get(mid)
        if info is None:
            continue
        season, day, feats = info
        vec = row_vector(feats, float(r.probability))
        if vec is None:
            continue
        quoted = (quotes.get(mid) or {}).get(str(r.market_key))
        b = buckets.setdefault(season, {}).setdefault(str(r.market_key), {k: [] for k in ("x", "p", "y", "q", "m", "d")})
        b["x"].append(vec)
        b["p"].append(float(r.probability))
        b["y"].append(1.0 if r.won else 0.0)
        b["q"].append(float(quoted[0]) if quoted else float("nan"))
        b["m"].append(mid)
        b["d"].append(day)
    data = {
        season: {
            key: MarketData(
                x=np.asarray(b["x"], dtype=float),
                probability=np.asarray(b["p"]),
                won=np.asarray(b["y"]),
                quota=np.asarray(b["q"]),
                match_id=np.asarray(b["m"]),
                match_day=np.asarray(b["d"]),
            )
            for key, b in markets.items()
        }
        for season, markets in buckets.items()
    }
    return data, {"v3_run": run_id, "index_run": index_run}


# --- dal vivo --------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def frozen_index() -> dict[str, Any]:
    payload = json.loads(_FROZEN_PATH.read_text(encoding="utf-8"))
    payload["_models"] = {k: MarketModel.from_dict(v) for k, v in (payload.get("models") or {}).items()}
    return payload


def purchasability_index_live(result: dict[str, Any], quotas: dict[str, float | None]) -> dict[str, Any]:
    """Indice V3 per una partita dal risultato del motore V3 estesa; la quota serve solo alla fine."""
    if not result.get("eligible"):
        return {"status": "early_season", "reason": "servono almeno 5 partite giocate per squadra"}
    frozen = frozen_index()
    models: dict[str, MarketModel] = frozen["_models"]
    match = match_features(
        lambda_home=result.get("lambda_home"),
        lambda_away=result.get("lambda_away"),
        ht_share=result.get("ht_share"),
        evidence_home=result.get("home_evidence"),
        evidence_away=result.get("away_evidence"),
        specialists=result.get("specialists"),
        indices=result.get("indices"),
    )
    markets: dict[str, Any] = {}
    for key, probability in (result.get("probabilities") or {}).items():
        model = models.get(key)
        vec = row_vector(match, probability)
        if model is None or vec is None:
            continue
        cols = [FEATURES.index(f) for f in model.features]
        p_est = float(model.predict_raw(np.asarray([vec])[:, cols])[0])
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
