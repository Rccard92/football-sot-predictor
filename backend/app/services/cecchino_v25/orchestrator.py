"""Indice di Acquistabilita' V2.5 come orchestratore dei moduli.

Regola dell'utente: l'obiettivo e' vincere, non battere il bookmaker.

Fase A - lettura dei moduli, NESSUNA quota del book:
  per ogni mercato una regressione logistica stima quante volte su 100 la giocata vince,
  partendo dalla probabilita' Cecchino V2.5 del mercato e da tutti i moduli della partita
  (picchetti 1X2, gol attesi, Equilibrio, Intensita' Goal, segnale acceso). Impara solo da
  "vinta / persa" nelle stagioni gia' giocate. Prob. book, acquistabilita' V2.5, rating ed edge
  del Pannello KPI non entrano mai.

Punteggio 0-100 = forza della predizione dei moduli, SENZA quota:
  quanto la probabilita' stimata supera la frequenza normale del mercato nello storico.
  50 = frequenza normale, +2,5 punti per ogni punto percentuale in piu' (70 = +8 punti).
  Predizioni finali dell'indice: punteggio >= 70 (anche piu' di una per partita).

Solo alla fine la quota, come "vale la pena?": giocabile se la quota Bet365 e' almeno 1,50.
La quota non sceglie mai le partite. (La v1 usava probabilita' x quota - 1 come punteggio:
premiava le quote alte rispetto ai moduli, cioe' la caccia al valore, ed e' stata scartata.)

Funzioni pure (numpy), senza database: dati in `orchestrator_data.py`, job in
`app/jobs/cecchino_v25_orchestrator.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

MODULE_VERSION = "cecchino_v25_orchestrator_v2"

# Colonne della partita, tutte senza quote del bookmaker.
MATCH_FEATURES: tuple[str, ...] = (
    "p1",
    "px",
    "p2",
    "lambda_home",
    "lambda_away",
    "lambda_ht_home",
    "lambda_ht_away",
    "goals_reliability",
    "bal_f36",
    "bal_dominance",
    "bal_draw_credibility",
    "bal_gap_coherence",
    "gi_offensive_production",
    "gi_defensive_solidity",
    "gi_match_tempo",
    "gi_offensive_stability",
    "gi_final",
)
# Colonne del mercato.
MARKET_FEATURES: tuple[str, ...] = ("logit_p", "signal_active")
# Colonne che possono mancare (Intensita' Goal con storico corto): media di allenamento + flag.
OPTIONAL_FEATURES: frozenset[str] = frozenset(
    {"gi_offensive_production", "gi_defensive_solidity", "gi_match_tempo", "gi_offensive_stability", "gi_final"}
)
FEATURES: tuple[str, ...] = MARKET_FEATURES + MATCH_FEATURES + ("gi_missing",)

L2 = 2.0
PROB_EPS = 1e-4
SCORE_BASE = 50.0
SCORE_POINTS_PER_PT = 2.5  # ogni punto percentuale sopra la frequenza normale del mercato
PREDICTION_MIN_SCORE = 70.0  # da qui una giocata entra tra le predizioni finali dell'indice
PLAYABLE_MIN_QUOTA = 1.50  # "vale la pena": sotto questa quota non si investe


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def logit(p: float) -> float:
    p = min(1.0 - PROB_EPS, max(PROB_EPS, p))
    return math.log(p / (1.0 - p))


def match_features_from_modules(
    *,
    final: dict[str, Any] | None,
    lambdas: dict[str, Any] | None,
    balance: dict[str, Any] | None,
    goal_intensity: dict[str, Any] | None,
) -> dict[str, float | None]:
    """Colonne della partita dai JSON dei moduli V2.5 (stessa forma in RUN e in live)."""
    final = final or {}
    lambdas = lambdas or {}
    pillars = (balance or {}).get("pillars") or {}
    gi = goal_intensity or {}
    gi_pillars = gi.get("pillars") or {}

    def pillar_index(key: str) -> float | None:
        v = _f((pillars.get(key) or {}).get("index"))
        return None if v is None else v / 100.0

    def gi_score(key: str) -> float | None:
        v = _f((gi_pillars.get(key) or {}).get("score"))
        return None if v is None else v / 100.0

    gi_final = _f((gi.get("final_class") or {}).get("score"))
    return {
        "p1": _f(final.get("prob_1")),
        "px": _f(final.get("prob_x")),
        "p2": _f(final.get("prob_2")),
        "lambda_home": _f(lambdas.get("ft_home")),
        "lambda_away": _f(lambdas.get("ft_away")),
        "lambda_ht_home": _f(lambdas.get("ht_home")),
        "lambda_ht_away": _f(lambdas.get("ht_away")),
        "goals_reliability": _f(lambdas.get("reliability")),
        "bal_f36": pillar_index("f36"),
        "bal_dominance": pillar_index("dominance"),
        "bal_draw_credibility": pillar_index("draw_credibility"),
        "bal_gap_coherence": pillar_index("gap_coherence"),
        "gi_offensive_production": gi_score("offensive_production"),
        "gi_defensive_solidity": gi_score("defensive_solidity"),
        "gi_match_tempo": gi_score("match_tempo"),
        "gi_offensive_stability": gi_score("offensive_stability"),
        "gi_final": None if gi_final is None else gi_final / 100.0,
    }


def row_features(match: dict[str, float | None], probability: float | None, signal_active: bool) -> dict[str, float | None] | None:
    """Riga completa per un mercato; None se manca un dato obbligatorio."""
    p = _f(probability)
    if p is None:
        return None
    out: dict[str, float | None] = {"logit_p": logit(p), "signal_active": 1.0 if signal_active else 0.0}
    gi_missing = False
    for key in MATCH_FEATURES:
        value = match.get(key)
        if value is None:
            if key not in OPTIONAL_FEATURES:
                return None
            gi_missing = True
        out[key] = value
    out["gi_missing"] = 1.0 if gi_missing else 0.0
    return out


# --- modello --------------------------------------------------------------------------------


@dataclass
class MarketModel:
    market_key: str
    features: tuple[str, ...]
    means: list[float]
    scales: list[float]
    impute: dict[str, float]
    coef: list[float]  # intercetta + una per feature (feature standardizzate)
    n: int
    base_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_key": self.market_key,
            "features": list(self.features),
            "means": [round(v, 8) for v in self.means],
            "scales": [round(v, 8) for v in self.scales],
            "impute": {k: round(v, 8) for k, v in self.impute.items()},
            "coef": [round(v, 8) for v in self.coef],
            "n": self.n,
            "base_rate": round(self.base_rate, 6),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MarketModel":
        return cls(
            market_key=d["market_key"],
            features=tuple(d["features"]),
            means=list(d["means"]),
            scales=list(d["scales"]),
            impute=dict(d["impute"]),
            coef=list(d["coef"]),
            n=int(d["n"]),
            base_rate=float(d["base_rate"]),
        )

    def predict_raw(self, raw: np.ndarray) -> np.ndarray:
        """raw: righe x feature del modello, NaN dove il dato manca."""
        if raw.shape[0] == 0:
            return np.empty(0)
        x = raw.copy()
        for j, key in enumerate(self.features):
            col = x[:, j]
            col[np.isnan(col)] = self.impute.get(key, 0.0)
        x = (x - np.asarray(self.means)) / np.asarray(self.scales)
        return _sigmoid(np.hstack([np.ones((x.shape[0], 1)), x]) @ np.asarray(self.coef))

    def predict(self, rows: Sequence[dict[str, float | None]]) -> np.ndarray:
        return self.predict_raw(rows_to_matrix(rows, self.features))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35.0, 35.0)))


def rows_to_matrix(rows: Sequence[dict[str, float | None]], features: tuple[str, ...]) -> np.ndarray:
    x = np.full((len(rows), len(features)), np.nan)
    for i, row in enumerate(rows):
        for j, key in enumerate(features):
            v = row.get(key)
            if v is not None:
                x[i, j] = v
    return x


def fit_market_model(
    market_key: str,
    rows: Sequence[dict[str, float | None]],
    won: Sequence[bool],
    *,
    features: tuple[str, ...] = FEATURES,
    l2: float = L2,
) -> MarketModel:
    y = np.asarray([1.0 if w else 0.0 for w in won])
    return fit_market_matrix(market_key, rows_to_matrix(rows, features), y, features=features, l2=l2)


def fit_market_matrix(
    market_key: str,
    raw_in: np.ndarray,
    y: np.ndarray,
    *,
    features: tuple[str, ...] = FEATURES,
    l2: float = L2,
    iterations: int = 60,
) -> MarketModel:
    """Regressione logistica con penalita' L2 (intercetta libera) su feature standardizzate.
    raw_in: righe x feature, NaN dove il dato manca (sostituito dalla media di allenamento)."""
    raw = raw_in.copy()
    impute: dict[str, float] = {}
    for j, key in enumerate(features):
        col = raw[:, j]
        missing = np.isnan(col)
        mean_present = float(col[~missing].mean()) if (~missing).any() else 0.0
        if missing.any():
            impute[key] = mean_present
            col[missing] = mean_present
    means = raw.mean(axis=0)
    scales = raw.std(axis=0)
    scales[scales < 1e-9] = 1.0
    x = np.hstack([np.ones((raw.shape[0], 1)), (raw - means) / scales])
    beta = np.zeros(x.shape[1])
    base = float(y.mean()) if y.size else 0.5
    beta[0] = logit(base)
    penalty = np.full(x.shape[1], l2)
    penalty[0] = 0.0
    for _ in range(iterations):
        p = _sigmoid(x @ beta)
        grad = x.T @ (y - p) - penalty * beta
        hess = (x * (p * (1.0 - p))[:, None]).T @ x + np.diag(penalty) + 1e-9 * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    return MarketModel(
        market_key=market_key,
        features=features,
        means=[float(v) for v in means],
        scales=[float(v) for v in scales],
        impute=impute,
        coef=[float(v) for v in beta],
        n=int(y.size),
        base_rate=base,
    )




# --- punteggio e decisione ---------------------------------------------------------------------


def strength_score(p_est: float, base_rate: float) -> float:
    """Forza della predizione dei moduli: 50 = frequenza normale del mercato, nessuna quota."""
    return max(0.0, min(100.0, SCORE_BASE + SCORE_POINTS_PER_PT * (p_est - base_rate) * 100.0))


def decision(p_est: float, base_rate: float, quota: float | None) -> dict[str, Any]:
    """Predizione dell'indice per un mercato: punteggio dai moduli, poi la quota solo come "vale la pena"."""
    score = strength_score(p_est, base_rate)
    is_prediction = score >= PREDICTION_MIN_SCORE
    return {
        "probability": round(p_est, 6),
        "base_rate": round(base_rate, 6),
        "score": round(score, 2),
        "is_prediction": is_prediction,
        "quota": quota,
        "min_quota": round(1.0 / p_est, 4) if p_est > 0 else None,
        "playable": bool(is_prediction and quota is not None and quota >= PLAYABLE_MIN_QUOTA),
    }


# --- esame -------------------------------------------------------------------------------------

SCORE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("sotto 50", -1.0, 50.0),
    ("50-60", 50.0, 60.0),
    ("60-70", 60.0, 70.0),
    ("70 e oltre", 70.0, 101.0),
)

ENGINE_FEATURES: tuple[str, ...] = ("logit_p",)


@dataclass
class ExamCriteria:
    """Criteri dichiarati PRIMA di vedere i risultati della v2 (15/09/2026)."""

    calibration_max_pt: float = 3.0
    lift_min_pt: float = 5.0
    profit_positive_seasons: int = 2
    notes: list[str] = field(
        default_factory=lambda: [
            "Allenamento solo in avanti: per ogni stagione di prova si impara sulle stagioni precedenti.",
            "E1 calibrazione: nelle 10 fasce di probabilita' stimata la % reale di vittorie si discosta in media (pesata) al massimo di 3 punti, in ogni stagione.",
            "E2 moduli utili: log-loss dell'indice minore di quella della sola probabilita' Cecchino ricalibrata, in ogni stagione (nessuna quota).",
            "E3 predizioni vincono di piu': punteggio >= 70 con % reale di vittorie almeno 5 punti sopra la frequenza normale di quei mercati, in ogni stagione.",
            "E4 profitto: predizioni (punteggio >= 70) con quota >= 1,50 con ROI > 0 in almeno 2 stagioni su 3 e nel complessivo.",
            "E5 ordine: scarto tra vittorie reali e frequenza normale crescente con le fasce di punteggio (sotto 50, 50-60, 60-70, 70+), sul complessivo.",
            "Volume: predizioni giocabili medie per giornata, solo riportato.",
        ]
    )


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, PROB_EPS, 1.0 - PROB_EPS)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def calibration_gap_pt(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    if p.size == 0:
        return float("nan")
    total = 0.0
    for c in np.array_split(np.argsort(p), bins):
        if c.size:
            total += abs(float(p[c].mean()) - float(y[c].mean())) * c.size
    return total / p.size * 100.0


def scores_array(p_est: np.ndarray, base: np.ndarray) -> np.ndarray:
    return np.clip(SCORE_BASE + SCORE_POINTS_PER_PT * (p_est - base) * 100.0, 0.0, 100.0)


def outcome_block(won: np.ndarray, base: np.ndarray, quota: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    """Vittorie rispetto alla frequenza normale e, dove c'e' la quota reale, il ROI."""
    n = int(mask.sum())
    if n == 0:
        return {"rows": 0, "won_pct": None, "base_pct": None, "lift_pt": None, "plays": 0, "roi_pct": None, "avg_quota": None}
    w = won[mask]
    b = base[mask]
    q = quota[mask]
    priced = ~np.isnan(q)
    plays = int(priced.sum())
    roi = None
    avg_q = None
    if plays:
        roi = round(float(np.sum(np.where(w[priced] > 0.5, q[priced] - 1.0, -1.0))) / plays * 100.0, 2)
        avg_q = round(float(q[priced].mean()), 3)
    return {
        "rows": n,
        "won_pct": round(float(w.mean()) * 100.0, 2),
        "base_pct": round(float(b.mean()) * 100.0, 2),
        "lift_pt": round(float(w.mean() - b.mean()) * 100.0, 2),
        "plays": plays,
        "roi_pct": roi,
        "avg_quota": avg_q,
    }


def season_report(
    p_est: np.ndarray, p_engine: np.ndarray, base: np.ndarray, won: np.ndarray, quota: np.ndarray, day: np.ndarray
) -> dict[str, Any]:
    score = scores_array(p_est, base)
    predictions = score >= PREDICTION_MIN_SCORE
    playable = predictions & ~np.isnan(quota) & (np.nan_to_num(quota, nan=0.0) >= PLAYABLE_MIN_QUOTA)
    days = len(set(day.tolist())) if day.size else 0
    return {
        "rows": int(won.size),
        "calibration_gap_pt": round(calibration_gap_pt(p_est, won), 3),
        "log_loss_index": round(log_loss(p_est, won), 6),
        "log_loss_engine": round(log_loss(p_engine, won), 6),
        "predictions": outcome_block(won, base, quota, predictions),
        "playable": outcome_block(won, base, quota, playable),
        "playable_per_day": round(float(playable.sum()) / days, 2) if days else None,
        "bands": {label: outcome_block(won, base, quota, (score >= lo) & (score < hi)) for label, lo, hi in SCORE_BANDS},
    }


def exam_verdict(per_season: dict[str, dict[str, Any]], pooled: dict[str, Any], criteria: ExamCriteria) -> dict[str, Any]:
    seasons = list(per_season.values())
    e1 = all(s["calibration_gap_pt"] <= criteria.calibration_max_pt for s in seasons)
    e2 = all(s["log_loss_index"] < s["log_loss_engine"] for s in seasons)
    e3 = all((s["predictions"]["lift_pt"] or -99.0) >= criteria.lift_min_pt for s in seasons)
    positive = sum(1 for s in seasons if (s["playable"]["roi_pct"] or -1.0) > 0)
    e4 = bool(positive >= criteria.profit_positive_seasons and (pooled["playable"]["roi_pct"] or -1.0) > 0)
    lifts = [pooled["bands"][label]["lift_pt"] for label, _, _ in SCORE_BANDS if pooled["bands"][label]["rows"]]
    e5 = all(a <= b for a, b in zip(lifts, lifts[1:]))
    return {"E1": e1, "E2": e2, "E3": e3, "E4": e4, "E5": e5, "passed": bool(e1 and e2 and e3 and e4 and e5)}
