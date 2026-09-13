"""Ricerca pattern V3 con lo stesso protocollo della V2 (Passo 3c) e test del
movimento del mercato verso la V3 (Passo 3b). Funzioni pure, senza database.

Protocollo pattern (identico alla V2):
- scoperta sul 2021/22: 1-2 condizioni, almeno 20 giocate, ROI > 0, piu'
  raffinamento a 3 condizioni sui 15 migliori pattern a 2 condizioni;
- verifica stagione per stagione: almeno 20 giocate, confermato se ROI > 0,
  contro la probabilita' che un gruppo casuale di pari dimensione abbia ROI > 0;
- test congelato sul 2024/25 dei pattern confermati nelle due stagioni prima.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any

import numpy as np

from app.services.cecchino_v3.constants import (
    JUDGE_SEASONS,
    MOVE_MARKETS,
    PATTERN_DISCOVERY_SEASON,
    PATTERN_FROZEN_FROM,
    PATTERN_FROZEN_SEASON,
    PATTERN_MIN_LIFT,
    PATTERN_MIN_PERSISTENCE_LIFT,
    PATTERN_MIN_SAMPLE,
    PATTERN_NULL_SAMPLES,
    PATTERN_NULL_SEED,
    PATTERN_QUANTILES,
    PATTERN_REFINEMENT_BASES,
)
from app.services.cecchino_v3.evaluator import MarketRow, select_plays, summarize

# Colonne delle condizioni, nell'ordine in cui compaiono nei testi.
QUINTILE_COLUMNS: tuple[str, ...] = ("prob_v3", "v3_vs_book", "quota", "forma")
CATEGORY_COLUMNS: tuple[str, ...] = (
    "equilibrio",
    "pareggio",
    "intensita_goal",
    "segno_agenti",
    "riposo",
    "fase",
    "livello",
)
PATTERN_COLUMNS: tuple[str, ...] = QUINTILE_COLUMNS + CATEGORY_COLUMNS

VERDICT_CONFIRMED = "confirmed"
VERDICT_REJECTED = "rejected"
VERDICT_INSUFFICIENT = "insufficient_sample"


# --- righe e condizioni --------------------------------------------------------------------


@dataclass
class MatchContext:
    """Informazioni pre-partita degli agenti (dagli indici), per partita."""

    equilibrio: str | None
    pareggio: str | None
    intensita_goal: str | None
    agents_agree: int | None
    form_diff: float | None
    rest_diff: int | None


def agents_value(agree: int | None) -> str | None:
    if agree is None:
        return None
    return "3" if agree >= 3 else "2" if agree == 2 else "0-1"


def rest_value(diff: int | None) -> str | None:
    if diff is None:
        return None
    return "meno_riposo_casa" if diff < -1 else "piu_riposo_casa" if diff > 1 else "pari"


def quintile_edges(values: Sequence[float]) -> list[float]:
    arr = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if arr.size < PATTERN_QUANTILES:
        return []
    qs = np.quantile(arr, [k / PATTERN_QUANTILES for k in range(1, PATTERN_QUANTILES)])
    return [float(q) for q in qs]


def quintile_value(value: float | None, edges: list[float]) -> str | None:
    if value is None or not edges or not math.isfinite(value):
        return None
    k = int(np.searchsorted(np.asarray(edges), value, side="right"))
    return f"Q{k + 1}"


def _raw_quintile_inputs(row: MarketRow, ctx: MatchContext | None) -> dict[str, float | None]:
    return {
        "prob_v3": row.p_v3,
        "v3_vs_book": row.p_v3 - row.p_book,
        "quota": row.odds,
        "forma": ctx.form_diff if ctx else None,
    }


def build_edges(rows: Sequence[MarketRow], contexts: dict[int, MatchContext]) -> dict[str, dict[str, list[float]]]:
    """Quintili per mercato, calcolati SOLO sulla stagione di scoperta."""
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.season_label != PATTERN_DISCOVERY_SEASON or not r.eligible:
            continue
        for col, v in _raw_quintile_inputs(r, contexts.get(r.lab_match_id)).items():
            if v is not None:
                values[r.market_key][col].append(v)
    return {market: {col: quintile_edges(vals) for col, vals in cols.items()} for market, cols in values.items()}


def row_conditions(
    row: MarketRow, ctx: MatchContext | None, edges: dict[str, dict[str, list[float]]]
) -> dict[str, str | None]:
    market_edges = edges.get(row.market_key, {})
    raw = _raw_quintile_inputs(row, ctx)
    out: dict[str, str | None] = {col: quintile_value(raw[col], market_edges.get(col, [])) for col in QUINTILE_COLUMNS}
    out["equilibrio"] = ctx.equilibrio if ctx else None
    out["pareggio"] = ctx.pareggio if ctx else None
    out["intensita_goal"] = ctx.intensita_goal if ctx else None
    out["segno_agenti"] = agents_value(ctx.agents_agree) if ctx else None
    out["riposo"] = rest_value(ctx.rest_diff) if ctx else None
    out["fase"] = "finale" if row.phase == "final" else "stagione"
    out["livello"] = row.tier
    return out


# --- matrice per mercato ---------------------------------------------------------------------


@dataclass
class MarketMatrix:
    market_key: str
    seasons: np.ndarray  # stringhe
    match_ids: np.ndarray
    profit: np.ndarray
    codes: np.ndarray  # (righe, colonne) interi, -1 = non disponibile
    values: list[list[str]]  # per colonna: valore di ogni codice

    def season_mask(self, season: str) -> np.ndarray:
        return self.seasons == season

    def atom_mask(self, atom: tuple[int, int]) -> np.ndarray:
        return self.codes[:, atom[0]] == atom[1]

    def combo_mask(self, combo: Sequence[tuple[int, int]]) -> np.ndarray:
        mask = np.ones(self.profit.size, dtype=bool)
        for atom in combo:
            mask &= self.atom_mask(atom)
        return mask

    def describe(self, combo: Sequence[tuple[int, int]]) -> list[dict[str, str]]:
        return [{"column": PATTERN_COLUMNS[c], "value": self.values[c][v]} for c, v in combo]


def build_matrices(
    rows: Sequence[MarketRow], contexts: dict[int, MatchContext], edges: dict[str, dict[str, list[float]]]
) -> dict[str, MarketMatrix]:
    by_market: dict[str, list[MarketRow]] = defaultdict(list)
    for r in rows:
        if r.eligible:
            by_market[r.market_key].append(r)
    out: dict[str, MarketMatrix] = {}
    for market, market_rows in sorted(by_market.items()):
        vocab: list[dict[str, int]] = [{} for _ in PATTERN_COLUMNS]
        codes = np.full((len(market_rows), len(PATTERN_COLUMNS)), -1, dtype=np.int16)
        for i, r in enumerate(market_rows):
            conditions = row_conditions(r, contexts.get(r.lab_match_id), edges)
            for c, col in enumerate(PATTERN_COLUMNS):
                value = conditions[col]
                if value is None:
                    continue
                codes[i, c] = vocab[c].setdefault(value, len(vocab[c]))
        values = [[v for v, _ in sorted(vc.items(), key=lambda kv: kv[1])] for vc in vocab]
        out[market] = MarketMatrix(
            market_key=market,
            seasons=np.array([r.season_label for r in market_rows]),
            match_ids=np.array([r.lab_match_id for r in market_rows]),
            profit=np.array([r.odds - 1.0 if r.won else -1.0 for r in market_rows]),
            codes=codes,
            values=values,
        )
    return out


# --- scoperta ---------------------------------------------------------------------------------


@dataclass
class Pattern:
    market_key: str
    combo: tuple[tuple[int, int], ...]
    conditions: list[dict[str, str]]
    discovery: dict[str, Any]
    seasons: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.combo)

    @property
    def label(self) -> str:
        return " + ".join(f"{c['column']}={c['value']}" for c in self.conditions)


def _stats(profit: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "roi": None, "won": 0}
    p = profit[mask]
    return {"n": n, "roi": float(p.mean()), "won": int((p > 0).sum())}


def discover(matrix: MarketMatrix) -> list[Pattern]:
    disc = matrix.season_mask(PATTERN_DISCOVERY_SEASON)
    if not disc.any():
        return []
    atoms = [
        (c, v)
        for c in range(len(PATTERN_COLUMNS))
        for v in range(len(matrix.values[c]))
        if (matrix.codes[disc, c] == v).any()
    ]
    masks = {a: matrix.atom_mask(a) & disc for a in atoms}
    found: list[Pattern] = []

    def consider(combo: tuple[tuple[int, int], ...], mask: np.ndarray) -> Pattern | None:
        s = _stats(matrix.profit, mask)
        if s["n"] < PATTERN_MIN_SAMPLE or s["roi"] is None or s["roi"] <= 0:
            return None
        pattern = Pattern(matrix.market_key, combo, matrix.describe(combo), s)
        found.append(pattern)
        return pattern

    for a in atoms:
        consider((a,), masks[a])
    two: list[Pattern] = []
    for a, b in combinations(atoms, 2):
        if a[0] == b[0]:
            continue
        p = consider((a, b), masks[a] & masks[b])
        if p is not None:
            two.append(p)

    seen = {frozenset(p.combo) for p in found}
    two.sort(key=lambda p: (-p.discovery["roi"], p.combo))
    for base in two[:PATTERN_REFINEMENT_BASES]:
        used = {c for c, _ in base.combo}
        base_mask = masks[base.combo[0]] & masks[base.combo[1]]
        for a in atoms:
            if a[0] in used:
                continue
            combo = tuple(sorted(base.combo + (a,)))
            if frozenset(combo) in seen:
                continue
            seen.add(frozenset(combo))
            consider(combo, base_mask & masks[a])
    return found


# --- verifica fuori campione ------------------------------------------------------------------


class NullModel:
    """Probabilita' che un gruppo casuale di n righe della stagione abbia ROI > 0."""

    def __init__(self, profit: np.ndarray, seed_offset: int = 0) -> None:
        self.size = int(profit.size)
        if self.size == 0:
            self._positive = np.zeros(0)
            return
        rng = np.random.default_rng(PATTERN_NULL_SEED + seed_offset)
        perm = rng.permuted(np.tile(np.arange(self.size), (PATTERN_NULL_SAMPLES, 1)), axis=1)
        cumulative = np.cumsum(profit[perm], axis=1)
        self._positive = (cumulative > 0).mean(axis=0)  # indice n-1

    def p_roi_positive(self, n: int) -> float | None:
        if n <= 0 or n > self.size:
            return None
        return float(self._positive[n - 1])


def validate(matrix: MarketMatrix, patterns: list[Pattern], seasons: Sequence[str]) -> None:
    for idx, season in enumerate(seasons):
        smask = matrix.season_mask(season)
        null = NullModel(matrix.profit[smask], seed_offset=idx)
        for p in patterns:
            s = _stats(matrix.profit, matrix.combo_mask(p.combo) & smask)
            if s["n"] < PATTERN_MIN_SAMPLE:
                verdict, null_p = VERDICT_INSUFFICIENT, None
            else:
                verdict = VERDICT_CONFIRMED if s["roi"] > 0 else VERDICT_REJECTED
                null_p = null.p_roi_positive(s["n"])
            p.seasons[season] = {**s, "verdict": verdict, "null_p": null_p}


def validation_tally(patterns: Sequence[Pattern], seasons: Sequence[str]) -> dict[str, Any]:
    per_season = []
    total_confirmed = 0
    total_expected = 0.0
    for season in seasons:
        tested = [p for p in patterns if p.seasons.get(season, {}).get("verdict") not in (None, VERDICT_INSUFFICIENT)]
        confirmed = sum(1 for p in tested if p.seasons[season]["verdict"] == VERDICT_CONFIRMED)
        expected = sum(p.seasons[season]["null_p"] or 0.0 for p in tested)
        total_confirmed += confirmed
        total_expected += expected
        per_season.append(_rate_row(season, len(tested), confirmed, expected))

    all_tested = [
        p for p in patterns
        if all(p.seasons.get(s, {}).get("verdict") not in (None, VERDICT_INSUFFICIENT) for s in seasons)
    ]
    confirmed_all = sum(1 for p in all_tested if all(p.seasons[s]["verdict"] == VERDICT_CONFIRMED for s in seasons))
    expected_all = sum(math.prod(p.seasons[s]["null_p"] or 0.0 for s in seasons) for p in all_tested)
    return {
        "discovered": len(patterns),
        "per_season": per_season,
        "overall_lift": round(total_confirmed / total_expected, 3) if total_expected > 0 else None,
        "persistence": _rate_row("tutte", len(all_tested), confirmed_all, expected_all),
    }


def _rate_row(season: str, tested: int, confirmed: int, expected: float) -> dict[str, Any]:
    return {
        "season": season,
        "tested": tested,
        "confirmed": confirmed,
        "expected": round(expected, 1),
        "confirmed_rate_pct": round(confirmed / tested * 100.0, 2) if tested else None,
        "expected_rate_pct": round(expected / tested * 100.0, 2) if tested else None,
        "lift": round(confirmed / expected, 3) if expected > 0 else None,
    }


def frozen_test(
    matrices: dict[str, MarketMatrix],
    patterns: Sequence[Pattern],
    *,
    from_seasons: Sequence[str] = PATTERN_FROZEN_FROM,
    target_season: str = PATTERN_FROZEN_SEASON,
) -> dict[str, Any]:
    """Pattern confermati in tutte le stagioni `from_seasons`, giocati sulla
    stagione `target_season`: una giocata per partita per mercato."""
    frozen = [
        p for p in patterns if all(p.seasons.get(s, {}).get("verdict") == VERDICT_CONFIRMED for s in from_seasons)
    ]
    by_market: dict[str, list[Pattern]] = defaultdict(list)
    for p in frozen:
        by_market[p.market_key].append(p)
    rows = []
    total_profit = 0.0
    total_bets = 0
    pooled_n = 0
    pooled_profit = 0.0
    for market, market_patterns in sorted(by_market.items()):
        m = matrices[market]
        tmask = m.season_mask(target_season)
        union = np.zeros(m.profit.size, dtype=bool)
        for p in market_patterns:
            pmask = m.combo_mask(p.combo) & tmask
            union |= pmask
            pooled_n += int(pmask.sum())
            pooled_profit += float(m.profit[pmask].sum())
        bets = int(union.sum())
        profit = float(m.profit[union].sum())
        total_bets += bets
        total_profit += profit
        rows.append(
            {
                "market_key": market,
                "patterns": len(market_patterns),
                "bets": bets,
                "profit": round(profit, 2),
                "roi_pct": round(profit / bets * 100.0, 3) if bets else None,
            }
        )
    return {
        "from_seasons": list(from_seasons),
        "target_season": target_season,
        "patterns": len(frozen),
        "bets": total_bets,
        "profit": round(total_profit, 2),
        "roi_pct": round(total_profit / total_bets * 100.0, 3) if total_bets else None,
        "pooled_pattern_bets": pooled_n,
        "pooled_roi_pct": round(pooled_profit / pooled_n * 100.0, 3) if pooled_n else None,
        "by_market": rows,
    }


def pattern_exam(tally: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    per_season = tally["per_season"]
    p1 = (
        bool(per_season)
        and all(r["tested"] > 0 and r["confirmed"] > r["expected"] for r in per_season)
        and (tally["overall_lift"] or 0.0) >= PATTERN_MIN_LIFT
    )
    persistence = tally["persistence"]
    p2 = persistence["expected"] > 0 and persistence["confirmed"] > PATTERN_MIN_PERSISTENCE_LIFT * persistence["expected"]
    p3 = frozen["bets"] > 0 and (frozen["roi_pct"] or 0.0) > 0
    return {"P1": bool(p1), "P2": bool(p2), "P3": bool(p3), "passed": bool(p1 and p2 and p3)}


# --- Passo 3b: movimento del mercato ---------------------------------------------------------


@dataclass
class OpeningQuote:
    odds: float
    p_book: float


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def ols_cluster(x: np.ndarray, y: np.ndarray, clusters: np.ndarray) -> dict[str, float]:
    design = np.column_stack([np.ones_like(x), x])
    xtx_inv = np.linalg.inv(design.T @ design)
    beta = xtx_inv @ design.T @ y
    resid = y - design @ beta
    _, inverse = np.unique(clusters, return_inverse=True)
    summed = np.zeros((inverse.max() + 1, 2))
    np.add.at(summed, inverse, design * resid[:, None])
    cov = xtx_inv @ (summed.T @ summed) @ xtx_inv
    se = math.sqrt(max(cov[1, 1], 0.0))
    return {
        "alpha": round(float(beta[0]), 6),
        "beta": round(float(beta[1]), 5),
        "beta_se": round(se, 5),
        "beta_low": round(float(beta[1] - 1.96 * se), 5),
        "beta_high": round(float(beta[1] + 1.96 * se), 5),
    }


def market_move_analysis(
    rows: Sequence[MarketRow], opening: dict[tuple[int, str], OpeningQuote], seasons: Sequence[str] = JUDGE_SEASONS
) -> dict[str, Any]:
    table = []
    for family, keys in MOVE_MARKETS.items():
        for season in seasons:
            subset = [
                r for r in rows
                if r.eligible and r.season_label == season and r.market_key in keys
                and (r.lab_match_id, r.market_key) in opening
            ]
            if len(subset) < 50:
                table.append({"family": family, "season": season, "n": len(subset)})
                continue
            op = [opening[(r.lab_match_id, r.market_key)].p_book for r in subset]
            move = np.array([_logit(r.p_book) - _logit(o) for r, o in zip(subset, op)])
            distance = np.array([_logit(r.p_v3) - _logit(o) for r, o in zip(subset, op)])
            fit = ols_cluster(distance, move, np.array([r.lab_match_id for r in subset]))
            table.append(
                {
                    "family": family,
                    "season": season,
                    "n": len(subset),
                    "mean_abs_move": round(float(np.mean(np.abs(move))), 5),
                    "mean_abs_distance": round(float(np.mean(np.abs(distance))), 5),
                    **fit,
                }
            )
    exam = []
    for family in MOVE_MARKETS:
        rows_f = [t for t in table if t["family"] == family]
        ok = len(rows_f) == len(seasons) and all("beta_low" in t and t["beta_low"] > 0 for t in rows_f)
        exam.append({"family": family, "passed": bool(ok)})
    return {"table": table, "exam": exam, "passed": all(e["passed"] for e in exam)}


def opening_plays_report(
    rows: Sequence[MarketRow], opening: dict[tuple[int, str], OpeningQuote], seasons: Sequence[str] = JUDGE_SEASONS
) -> dict[str, Any]:
    """Giocate V3 alla quota di apertura con le regole del valutatore."""
    universe = tuple(k for keys in MOVE_MARKETS.values() for k in keys) + ("UNDER_2_5",)
    open_rows: list[MarketRow] = []
    close_by_key: dict[tuple[int, str], float] = {}
    for r in rows:
        q = opening.get((r.lab_match_id, r.market_key))
        if q is None or r.market_key not in universe:
            continue
        close_by_key[(r.lab_match_id, r.market_key)] = r.odds
        open_rows.append(replace(r, odds=q.odds, p_book=q.p_book))
    probability = {(r.lab_match_id, r.market_key): r.p_v3 for r in open_rows}
    plays = select_plays("V3_APERTURA", open_rows, probability, {}, universe, {}, seasons)
    gains = [p.row.odds / close_by_key[(p.row.lab_match_id, p.row.market_key)] - 1.0 for p in plays]
    at_close = [
        (close_by_key[(p.row.lab_match_id, p.row.market_key)] - 1.0) if p.row.won else -1.0 for p in plays
    ]
    by_season = []
    for s in seasons:
        idx = [i for i, p in enumerate(plays) if p.row.season_label == s]
        by_season.append(
            {
                "season": s,
                **summarize([plays[i] for i in idx]),
                "mean_odds_gain": round(float(np.mean([gains[i] for i in idx])), 5) if idx else None,
                "roi_at_close": round(float(np.mean([at_close[i] for i in idx])), 5) if idx else None,
            }
        )
    return {
        "total": {
            **summarize(plays),
            "mean_odds_gain": round(float(np.mean(gains)), 5) if gains else None,
            "roi_at_close": round(float(np.mean(at_close)), 5) if at_close else None,
        },
        "by_season": by_season,
    }
