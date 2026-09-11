"""Motore di scoperta Pattern walk-forward (albero decisionale + validazione out-of-sample).

Metodologia (vincolante, da documentazione Segnali Cecchino):
- niente soglie scelte a mano: le soglie nascono dal fit dell'albero sul solo
  fold di training;
- Pattern prima, Formula dopo: ogni foglia dell'albero è un Pattern (una
  configurazione osservata nei dati); la sua traduzione in regola
  campo/operatore/soglia è la Formula;
- congelamento prima della validazione: la regola appresa in training viene
  applicata, invariata, al fold di validazione successivo (mai visto);
- Win Rate è il criterio primario di selezione, ROI/profitto e numerosità
  sono controlli secondari — non il contrario;
- una Formula è promossa solo se il limite inferiore del CI95 sul win rate
  out-of-sample resta sopra il pareggio implicito dalla quota media a cui
  scatta (lega "funziona" a "è profittevole", non solo "indovina spesso").

Le foglie di un singolo albero sono per costruzione mutuamente esclusive
(partizionano lo spazio delle feature): non serve un controllo di ridondanza
tra le formule dello stesso fold.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.tree import DecisionTreeClassifier, _tree

from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    CI_MIN_SAMPLE,
    mean_profit_ci95,
    wilson_ci95,
)
from app.services.cecchino_data_lab.pattern_discovery_dataset import FEATURE_NAMES, MarketRow

MAX_FORMULAS_PER_FOLD = 4
FORMULA_SLOTS = ("D", "E", "F", "G")
TREE_MAX_DEPTH = 3
MIN_LEAF_FLOOR = CI_MIN_SAMPLE  # 30 — stessa soglia di robustezza usata per i CI95 esistenti


@dataclass(frozen=True)
class Condition:
    feature: str
    op: str  # "<=" oppure ">"
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "op": self.op, "threshold": round(self.threshold, 4)}

    def holds(self, value: float | None) -> bool:
        if value is None:
            return False
        return value <= self.threshold if self.op == "<=" else value > self.threshold


@dataclass(frozen=True)
class CandidatePattern:
    fold_index: int
    train_seasons: list[str]
    validation_season: str
    conditions: list[Condition]
    imputation: dict[str, float]
    train_n: int
    train_wins: int
    train_win_rate_pct: float
    train_avg_profit_1u: float | None
    formula_slot: str | None = None

    def rule_text(self) -> str:
        return " AND ".join(f"{c.feature} {c.op} {c.threshold:.2f}" for c in self.conditions)

    def matches(self, features: dict[str, float | None]) -> bool:
        for c in self.conditions:
            v = features.get(c.feature)
            if v is None:
                v = self.imputation.get(c.feature)
            if not c.holds(v):
                return False
        return True


def _impute_medians(rows: list[MarketRow]) -> dict[str, float]:
    medians: dict[str, float] = {}
    for name in FEATURE_NAMES:
        vals = [r.features[name] for r in rows if r.features.get(name) is not None]
        medians[name] = float(statistics.median(vals)) if vals else 0.0
    return medians


def _build_matrix(rows: list[MarketRow], medians: dict[str, float]) -> np.ndarray:
    X = np.empty((len(rows), len(FEATURE_NAMES)), dtype=np.float64)
    for i, row in enumerate(rows):
        for j, name in enumerate(FEATURE_NAMES):
            v = row.features.get(name)
            X[i, j] = v if v is not None else medians[name]
    return X


def _extract_leaf_conditions(tree_: Any, feature_names: tuple[str, ...]) -> dict[int, list[Condition]]:
    rules: dict[int, list[Condition]] = {}

    def recurse(node: int, path: list[Condition]) -> None:
        if tree_.feature[node] != _tree.TREE_UNDEFINED:
            name = feature_names[tree_.feature[node]]
            threshold = float(tree_.threshold[node])
            recurse(tree_.children_left[node], path + [Condition(name, "<=", threshold)])
            recurse(tree_.children_right[node], path + [Condition(name, ">", threshold)])
        else:
            rules[node] = path

    recurse(0, [])
    return rules


def discover_patterns_for_fold(
    *,
    fold_index: int,
    train_seasons: list[str],
    validation_season: str,
    train_rows: list[MarketRow],
) -> list[CandidatePattern]:
    """Addestra l'albero sul fold di training e ritorna fino a 4 Pattern candidati
    (uno per foglia selezionata), ordinati e già etichettati D/E/F/G.

    Un Pattern è candidato solo se il suo win rate di training supera il win
    rate incondizionato del fold (deve battere il "non fare nulla").
    """
    n_train = len(train_rows)
    if n_train < MIN_LEAF_FLOOR * 2:
        return []

    baseline_win_rate = sum(1 for r in train_rows if r.won) / n_train

    medians = _impute_medians(train_rows)
    X = _build_matrix(train_rows, medians)
    y = np.array([1 if r.won else 0 for r in train_rows], dtype=np.int64)

    min_samples_leaf = max(MIN_LEAF_FLOOR, round(0.01 * n_train))
    clf = DecisionTreeClassifier(
        max_depth=TREE_MAX_DEPTH,
        min_samples_leaf=min_samples_leaf,
        random_state=0,
    )
    clf.fit(X, y)

    leaf_conditions = _extract_leaf_conditions(clf.tree_, FEATURE_NAMES)
    leaf_ids = clf.apply(X)

    scored: list[tuple[float, float, int, int, list[Condition], float | None]] = []
    for leaf_id, conditions in leaf_conditions.items():
        mask = leaf_ids == leaf_id
        n = int(mask.sum())
        if n < MIN_LEAF_FLOOR:
            continue
        wins = int(y[mask].sum())
        win_rate = wins / n
        if win_rate <= baseline_win_rate:
            continue
        profits = [train_rows[i].profit_1u for i in np.nonzero(mask)[0] if train_rows[i].profit_1u is not None]
        avg_profit = statistics.fmean(profits) if profits else None
        scored.append((win_rate, avg_profit if avg_profit is not None else -999.0, n, wins, conditions, avg_profit))

    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    top = scored[:MAX_FORMULAS_PER_FOLD]

    patterns: list[CandidatePattern] = []
    for slot, (win_rate, _, n, wins, conditions, avg_profit) in zip(FORMULA_SLOTS, top):
        patterns.append(
            CandidatePattern(
                fold_index=fold_index,
                train_seasons=list(train_seasons),
                validation_season=validation_season,
                conditions=conditions,
                imputation=medians,
                train_n=n,
                train_wins=wins,
                train_win_rate_pct=round(win_rate * 100.0, 3),
                train_avg_profit_1u=round(avg_profit, 4) if avg_profit is not None else None,
                formula_slot=slot,
            )
        )
    return patterns


@dataclass(frozen=True)
class OosResult:
    n: int
    wins: int
    win_rate_pct: float | None
    win_rate_ci_low_pct: float | None
    win_rate_ci_high_pct: float | None
    avg_profit_1u: float | None
    avg_profit_ci_low: float | None
    avg_profit_ci_high: float | None
    avg_quota_book: float | None
    breakeven_win_rate_pct: float | None
    promoted: bool
    promotion_reason: str


def validate_pattern_out_of_sample(
    pattern: CandidatePattern,
    validation_rows: list[MarketRow],
) -> OosResult:
    """Applica la regola congelata (appresa in training) al fold di validazione
    mai visto durante la scoperta, e calcola le statistiche out-of-sample."""
    matched = [r for r in validation_rows if pattern.matches(r.features)]
    n = len(matched)
    wins = sum(1 for r in matched if r.won)
    win_rate_pct = round(wins / n * 100.0, 3) if n else None
    ci_low, ci_high = wilson_ci95(wins, n)

    profits = [r.profit_1u for r in matched if r.profit_1u is not None]
    mean_p, p_low, p_high = mean_profit_ci95(profits) if profits else (None, None, None)

    quotes = [r.quota_book for r in matched if r.quota_book is not None]
    avg_quota = statistics.fmean(quotes) if quotes else None
    breakeven = round(100.0 / avg_quota, 3) if avg_quota and avg_quota > 0 else None

    if n < CI_MIN_SAMPLE:
        promoted = False
        reason = f"campione out-of-sample insufficiente (n={n} < {CI_MIN_SAMPLE})"
    elif ci_low is None or breakeven is None:
        promoted = False
        reason = "CI95 o quota media non calcolabili"
    elif ci_low > breakeven:
        promoted = True
        reason = (
            f"limite inferiore CI95 win rate ({ci_low:.1f}%) supera il pareggio "
            f"implicito dalla quota media ({breakeven:.1f}%)"
        )
    else:
        promoted = False
        reason = (
            f"limite inferiore CI95 win rate ({ci_low:.1f}%) non supera il pareggio "
            f"implicito dalla quota media ({breakeven:.1f}%)"
        )

    return OosResult(
        n=n,
        wins=wins,
        win_rate_pct=win_rate_pct,
        win_rate_ci_low_pct=ci_low,
        win_rate_ci_high_pct=ci_high,
        avg_profit_1u=mean_p,
        avg_profit_ci_low=p_low,
        avg_profit_ci_high=p_high,
        avg_quota_book=round(avg_quota, 3) if avg_quota else None,
        breakeven_win_rate_pct=breakeven,
        promoted=promoted,
        promotion_reason=reason,
    )
