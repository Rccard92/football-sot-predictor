"""Valutatore di mercato (Passo 3): l'unico punto in cui entrano le quote.

Funzioni pure, senza database:
- probabilita' senza margine del book per ogni mercato;
- probabilita' del valutatore = regressione logistica walk-forward che unisce
  book e V3 (misura se la V3 sa qualcosa che la quota non contiene);
- esame I (informazione), regole no-bet di fase finale, scelta delle giocate,
  rendiconto ROI alla quota ed esame G (giocabilita').
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from app.services.cecchino_v3.constants import (
    EVALUATOR_L2,
    EVALUATOR_MAX_ODDS,
    EVALUATOR_MAX_PLAYS_PER_DAY,
    EVALUATOR_MIN_EDGE,
    EVALUATOR_MIN_ODDS,
    EVALUATOR_MIN_PLAYS,
    EVALUATOR_MIN_TRAIN_ROWS,
    EVALUATOR_PROB_CLIP,
    MARKET_FAMILY,
)

FINAL_RULE_MIN_ROWS = 200
ODDS_BANDS: tuple[tuple[float, float], ...] = ((1.30, 1.80), (1.80, 2.50), (2.50, 3.50), (3.50, 5.00))


# --- quote e probabilita' del book --------------------------------------------------------


def _inv(odds: float | None) -> float | None:
    return 1.0 / odds if odds is not None and odds > 1.0 else None


def book_probabilities(odds: dict[str, float | None]) -> dict[str, tuple[float, float]]:
    """Per ogni mercato con quota: (quota giocabile, probabilita' senza margine).

    Chiavi attese in `odds`: home, draw, away, over_25, under_25, over_05, under_05,
    over_15, under_15, over_35, under_35, ht_home, ht_draw, ht_away, dc_1x, dc_x2, dc_12.
    """
    out: dict[str, tuple[float, float]] = {}

    def triple(keys: tuple[str, str, str], markets: tuple[str, str, str]) -> tuple[float, float, float] | None:
        inv = [_inv(odds.get(k)) for k in keys]
        if any(v is None for v in inv):
            return None
        total = sum(inv)  # type: ignore[arg-type]
        fair = tuple(v / total for v in inv)  # type: ignore[operator]
        for k, m, p in zip(keys, markets, fair):
            out[m] = (float(odds[k]), p)  # type: ignore[arg-type]
        return fair  # type: ignore[return-value]

    ft = triple(("home", "draw", "away"), ("HOME", "DRAW", "AWAY"))
    triple(("ht_home", "ht_draw", "ht_away"), ("HOME_PT", "DRAW_PT", "AWAY_PT"))

    for suffix in ("05", "15", "25", "35"):
        o, u = _inv(odds.get(f"over_{suffix}")), _inv(odds.get(f"under_{suffix}"))
        if o is None or u is None:
            continue
        line = f"{suffix[0]}_{suffix[1]}"
        out[f"OVER_{line}"] = (float(odds[f"over_{suffix}"]), o / (o + u))  # type: ignore[arg-type]
        out[f"UNDER_{line}"] = (float(odds[f"under_{suffix}"]), u / (o + u))  # type: ignore[arg-type]

    if ft is not None:
        h, d, a = ft
        raw = {k: _inv(odds.get(k)) for k in ("home", "draw", "away")}
        for market, column, fair, pair in (
            ("ONE_X", "dc_1x", h + d, ("home", "draw")),
            ("X_TWO", "dc_x2", d + a, ("draw", "away")),
            ("ONE_TWO", "dc_12", h + a, ("home", "away")),
        ):
            quoted = odds.get(column)
            if quoted is None or quoted <= 1.0:
                quoted = 1.0 / (raw[pair[0]] + raw[pair[1]])  # type: ignore[operator]
            out[market] = (float(quoted), fair)
    return out


@dataclass
class MarketRow:
    lab_match_id: int
    season_label: str
    competition: str
    tier: str
    match_date: date
    phase: str
    eligible: bool
    home_team: str
    away_team: str
    market_key: str
    p_v3: float
    p_book: float
    odds: float
    won: bool

    @property
    def family(self) -> str:
        return MARKET_FAMILY[self.market_key]


# --- regressione logistica -----------------------------------------------------------------


def _clip(p: np.ndarray | float) -> np.ndarray | float:
    return np.clip(p, EVALUATOR_PROB_CLIP, 1.0 - EVALUATOR_PROB_CLIP)


def _logit(p: np.ndarray) -> np.ndarray:
    p = _clip(p)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def design(p_book: np.ndarray, p_v3: np.ndarray) -> np.ndarray:
    lb = _logit(p_book)
    return np.column_stack([np.ones_like(lb), lb, _logit(p_v3) - lb])


@dataclass
class LogisticFit:
    coef: np.ndarray  # a, b, c
    cov: np.ndarray  # robusta per partita
    n: int

    def predict(self, x: np.ndarray) -> np.ndarray:
        return _sigmoid(x @ self.coef)

    def summary(self) -> dict[str, Any]:
        se = np.sqrt(np.maximum(np.diag(self.cov), 0.0))
        return {
            "n": self.n,
            "a": round(float(self.coef[0]), 5),
            "b": round(float(self.coef[1]), 5),
            "c": round(float(self.coef[2]), 5),
            "c_se": round(float(se[2]), 5),
            "c_low": round(float(self.coef[2] - 1.96 * se[2]), 5),
            "c_high": round(float(self.coef[2] + 1.96 * se[2]), 5),
        }


def fit_logistic(x: np.ndarray, y: np.ndarray, clusters: np.ndarray, *, iterations: int = 50) -> LogisticFit:
    """Massima verosimiglianza con piccola penalita' verso (0, 1, 0) = "il book
    ha ragione". Covarianza robusta raggruppando le righe della stessa partita."""
    prior = np.array([0.0, 1.0, 0.0])
    beta = prior.copy()
    lam = EVALUATOR_L2
    eye = np.eye(x.shape[1])
    for _ in range(iterations):
        p = _sigmoid(x @ beta)
        grad = x.T @ (y - p) - lam * (beta - prior)
        hess = (x * (p * (1.0 - p))[:, None]).T @ x + lam * eye
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    p = _sigmoid(x @ beta)
    hess = (x * (p * (1.0 - p))[:, None]).T @ x + lam * eye
    bread = np.linalg.inv(hess)
    scores = x * (y - p)[:, None]
    _, inverse = np.unique(clusters, return_inverse=True)
    summed = np.zeros((inverse.max() + 1 if inverse.size else 0, x.shape[1]))
    np.add.at(summed, inverse, scores)
    meat = summed.T @ summed
    return LogisticFit(coef=beta, cov=bread @ meat @ bread, n=int(y.size))


def _arrays(rows: Sequence[MarketRow]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = design(np.array([r.p_book for r in rows]), np.array([r.p_v3 for r in rows]))
    y = np.array([float(r.won) for r in rows])
    clusters = np.array([r.lab_match_id for r in rows])
    return x, y, clusters


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = _clip(p)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


# --- probabilita' del valutatore (walk-forward) --------------------------------------------


@dataclass
class Combination:
    probability: dict[tuple[int, str], float]
    models: list[dict[str, Any]]


def combine_walk_forward(rows: Sequence[MarketRow]) -> Combination:
    """Per la stagione S e il mercato k: modello stimato sulle partite idonee
    delle stagioni precedenti. Senza abbastanza storico: nessuna probabilita'."""
    seasons = sorted({r.season_label for r in rows})
    by_key_season: dict[tuple[str, str], list[MarketRow]] = defaultdict(list)
    for r in rows:
        by_key_season[(r.market_key, r.season_label)].append(r)
    keys = sorted({r.market_key for r in rows})

    probability: dict[tuple[int, str], float] = {}
    models: list[dict[str, Any]] = []
    for idx, season in enumerate(seasons):
        if idx == 0:
            continue
        for key in keys:
            train = [r for s in seasons[:idx] for r in by_key_season.get((key, s), []) if r.eligible]
            target = by_key_season.get((key, season), [])
            if len(train) < EVALUATOR_MIN_TRAIN_ROWS or not target:
                continue
            fit = fit_logistic(*_arrays(train))
            x, _, _ = _arrays(target)
            for r, p in zip(target, fit.predict(x)):
                probability[(r.lab_match_id, key)] = float(p)
            models.append({"season": season, "market_key": key, "trained_on": seasons[:idx], **fit.summary()})
    return Combination(probability=probability, models=models)


# --- esame I: informazione oltre il mercato ------------------------------------------------


def information_table(
    rows: Sequence[MarketRow],
    combined: dict[tuple[int, str], float],
    groups: dict[str, tuple[str, ...]],
    seasons: tuple[str, ...],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, keys in groups.items():
        for season in seasons:
            subset = [
                r
                for r in rows
                if r.eligible and r.season_label == season and r.market_key in keys
                and (r.lab_match_id, r.market_key) in combined
            ]
            if len(subset) < 50:
                out.append({"group": name, "season": season, "n": len(subset)})
                continue
            x, y, clusters = _arrays(subset)
            p_book = np.array([r.p_book for r in subset])
            p_v3 = np.array([r.p_v3 for r in subset])
            p_comb = np.array([combined[(r.lab_match_id, r.market_key)] for r in subset])
            ll_book, ll_v3, ll_comb = log_loss(p_book, y), log_loss(p_v3, y), log_loss(p_comb, y)
            fit = fit_logistic(x, y, clusters).summary()
            out.append(
                {
                    "group": name,
                    "season": season,
                    "n": len(subset),
                    "ll_book": round(ll_book, 6),
                    "ll_v3": round(ll_v3, 6),
                    "ll_valutatore": round(ll_comb, 6),
                    "gain_pct": round((ll_book - ll_comb) / ll_book * 100.0, 4),
                    "c": fit["c"],
                    "c_low": fit["c_low"],
                    "c_high": fit["c_high"],
                    "b": fit["b"],
                }
            )
    return out


def information_exam(table: list[dict[str, Any]], families: Iterable[str], seasons: tuple[str, ...]) -> list[dict[str, Any]]:
    exams = []
    for family in families:
        rows = {r["season"]: r for r in table if r["group"] == family}
        complete = all(s in rows and "ll_book" in rows[s] for s in seasons)
        i1 = complete and all(rows[s]["ll_valutatore"] < rows[s]["ll_book"] for s in seasons)
        i2 = complete and all(rows[s]["c_low"] > 0 for s in seasons)
        exams.append({"family": family, "I1": bool(i1), "I2": bool(i2), "passed": bool(i1 and i2)})
    return exams


# --- regola no-bet di fase finale ----------------------------------------------------------


def final_phase_rules(
    rows: Sequence[MarketRow], combined: dict[tuple[int, str], float], seasons: tuple[str, ...]
) -> dict[tuple[str, str], dict[str, Any]]:
    """(stagione, famiglia) -> fase finale esclusa? Deciso sulle stagioni
    precedenti che hanno la probabilita' del valutatore."""
    families = sorted({r.family for r in rows})
    all_seasons = sorted({r.season_label for r in rows})
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for season in seasons:
        previous = {s for s in all_seasons if s < season}
        for family in families:
            history = [
                r
                for r in rows
                if r.season_label in previous and r.family == family and r.eligible and r.phase == "final"
                and (r.lab_match_id, r.market_key) in combined
            ]
            if len(history) < FINAL_RULE_MIN_ROWS:
                out[(season, family)] = {"excluded": False, "n": len(history), "gain": None}
                continue
            y = np.array([float(r.won) for r in history])
            gain = log_loss(np.array([r.p_book for r in history]), y) - log_loss(
                np.array([combined[(r.lab_match_id, r.market_key)] for r in history]), y
            )
            out[(season, family)] = {"excluded": bool(gain <= 0.0), "n": len(history), "gain": round(float(gain), 6)}
    return out


# --- giocate -------------------------------------------------------------------------------


@dataclass
class Play:
    strategy: str
    row: MarketRow
    probability: float
    p_eval: float | None
    edge: float

    @property
    def profit(self) -> float:
        return self.row.odds - 1.0 if self.row.won else -1.0


def select_plays(
    strategy: str,
    rows: Sequence[MarketRow],
    probability_of: dict[tuple[int, str], float],
    combined: dict[tuple[int, str], float],
    universe: Iterable[str],
    final_rules: dict[tuple[str, str], dict[str, Any]],
    seasons: tuple[str, ...],
    *,
    min_edge: float = EVALUATOR_MIN_EDGE,
) -> list[Play]:
    allowed = set(universe)
    best_per_match: dict[int, Play] = {}
    for r in rows:
        if not r.eligible or r.season_label not in seasons or r.market_key not in allowed:
            continue
        if not (EVALUATOR_MIN_ODDS <= r.odds <= EVALUATOR_MAX_ODDS):
            continue
        if r.phase == "final" and final_rules.get((r.season_label, r.family), {}).get("excluded"):
            continue
        p = probability_of.get((r.lab_match_id, r.market_key))
        if p is None:
            continue
        edge = p * r.odds - 1.0
        if edge < min_edge:
            continue
        play = Play(strategy, r, p, combined.get((r.lab_match_id, r.market_key)), edge)
        current = best_per_match.get(r.lab_match_id)
        if current is None or (edge, r.market_key) > (current.edge, current.row.market_key):
            best_per_match[r.lab_match_id] = play

    by_day: dict[date, list[Play]] = defaultdict(list)
    for play in best_per_match.values():
        by_day[play.row.match_date].append(play)
    selected: list[Play] = []
    for day in sorted(by_day):
        ranked = sorted(by_day[day], key=lambda p: (-p.edge, p.row.lab_match_id))
        selected.extend(ranked[:EVALUATOR_MAX_PLAYS_PER_DAY])
    return selected


# --- rendiconto ----------------------------------------------------------------------------


def summarize(plays: Sequence[Play]) -> dict[str, Any]:
    n = len(plays)
    if n == 0:
        return {"n": 0}
    profits = np.array([p.profit for p in plays])
    roi = float(profits.mean())
    se = float(profits.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    return {
        "n": n,
        "won": int(sum(p.row.won for p in plays)),
        "hit_rate": round(float(np.mean([p.row.won for p in plays])), 4),
        "mean_probability": round(float(np.mean([p.probability for p in plays])), 4),
        "mean_book_probability": round(float(np.mean([p.row.p_book for p in plays])), 4),
        "mean_odds": round(float(np.mean([p.row.odds for p in plays])), 3),
        "profit": round(float(profits.sum()), 2),
        "roi": round(roi, 5),
        "roi_se": round(se, 5) if n > 1 else None,
        "roi_low": round(roi - 1.96 * se, 5) if n > 1 else None,
        "roi_high": round(roi + 1.96 * se, 5) if n > 1 else None,
    }


def _grouped(plays: Sequence[Play], key) -> list[dict[str, Any]]:
    groups: dict[Any, list[Play]] = defaultdict(list)
    for p in plays:
        groups[key(p)].append(p)
    return [{"key": k, **summarize(v)} for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))]


def odds_band(odds: float) -> str:
    for low, high in ODDS_BANDS:
        if low <= odds < high or (high == ODDS_BANDS[-1][1] and odds == high):
            return f"{low:.2f}-{high:.2f}"
    return "fuori"


def strategy_report(plays: Sequence[Play]) -> dict[str, Any]:
    days = defaultdict(int)
    for p in plays:
        days[p.row.match_date] += 1
    return {
        "total": summarize(plays),
        "by_season": _grouped(plays, lambda p: p.row.season_label),
        "by_family": _grouped(plays, lambda p: p.row.family),
        "by_market": _grouped(plays, lambda p: p.row.market_key),
        "by_tier": _grouped(plays, lambda p: p.row.tier),
        "by_competition": _grouped(plays, lambda p: p.row.competition),
        "by_odds_band": _grouped(plays, lambda p: odds_band(p.row.odds)),
        "by_phase": _grouped(plays, lambda p: p.row.phase),
        "days_with_plays": len(days),
        "plays_per_day": round(len(plays) / len(days), 2) if days else 0.0,
    }


def playability_exam(plays: Sequence[Play], seasons: tuple[str, ...]) -> dict[str, Any]:
    by_season = {s: summarize([p for p in plays if p.row.season_label == s]) for s in seasons}
    total = summarize(plays)
    g1 = all(by_season[s].get("n", 0) > 0 and by_season[s]["roi"] > 0 for s in seasons)
    g2 = total.get("n", 0) > 1 and total["roi_low"] is not None and total["roi_low"] > 0
    g3 = total.get("n", 0) >= EVALUATOR_MIN_PLAYS
    return {
        "G1": bool(g1),
        "G2": bool(g2),
        "G3": bool(g3),
        "passed": bool(g1 and g2 and g3),
        "by_season": [{"season": s, **by_season[s]} for s in seasons],
        "total": total,
    }
