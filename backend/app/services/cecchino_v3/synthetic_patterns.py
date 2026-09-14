"""Ricerca pattern V3 sui mercati senza quota (tiri, tiri in porta, corner, gialli),
con le stesse regole della ricerca V2 senza quota. Funzioni pure, senza database.

- scoperta sul 2021/22: 1-2 condizioni, almeno 20 partite, frequenza lontana dalla
  media della stagione di almeno 15 punti; raffinamento a 3 condizioni sui 15
  migliori pattern a 2 condizioni;
- verifica stagione per stagione: almeno 20 partite; confermato se lo scostamento
  e' di almeno 5 punti nella stessa direzione, attenuato se piu' debole;
- caso: probabilita' che un gruppo casuale di partite della stagione, grande
  uguale, abbia lo stesso scostamento.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from typing import Any

import numpy as np

from app.services.cecchino_v3.patterns import (
    MatchContext,
    agents_value,
    quintile_edges,
    quintile_value,
    rest_value,
)
from app.services.master_patterns.constants import (
    DISCOVERY_SEASON,
    MIN_SAMPLE,
    NULL_SAMPLES,
    NULL_SEED,
    REFINEMENT_BASES,
    SYNTHETIC_DISCOVERY_DEVIATION_PCT,
    VERDICT_INSUFFICIENT,
)
from app.services.master_patterns.scoring import synthetic_verdict

SYNTHETIC_COLUMNS: tuple[str, ...] = (
    "volume_atteso",
    "forma",
    "equilibrio",
    "pareggio",
    "intensita_goal",
    "segno_agenti",
    "riposo",
    "fase",
    "livello",
)
# Volume atteso dallo specialista Gioco: solo per le statistiche che stima.
VOLUME_SOURCE: dict[str, tuple[str, str] | None] = {
    "total_shots": ("shots", "total"),
    "home_shots": ("shots", "home"),
    "away_shots": ("shots", "away"),
    "total_sot": ("sot", "total"),
    "home_sot": ("sot", "home"),
    "away_sot": ("sot", "away"),
    "total_corners": None,
    "home_corners": None,
    "away_corners": None,
    "total_yellow_cards": None,
    "home_yellow_cards": None,
    "away_yellow_cards": None,
}


@dataclass
class SyntheticRow:
    lab_match_id: int
    season_label: str
    competition: str
    tier: str
    match_date: date
    phase: str
    eligible: bool
    home_team: str
    away_team: str
    actuals: dict[str, float | None]
    volumes: dict[str, float | None]  # "shots_home", "shots_away", "sot_home", "sot_away"


def expected_volume(row: SyntheticRow, stat_key: str) -> float | None:
    source = VOLUME_SOURCE.get(stat_key)
    if source is None:
        return None
    stat, side = source
    home, away = row.volumes.get(f"{stat}_home"), row.volumes.get(f"{stat}_away")
    if side == "home":
        return home
    if side == "away":
        return away
    return home + away if home is not None and away is not None else None


def synthetic_edges(rows: Sequence[SyntheticRow], contexts: dict[int, MatchContext], stat_keys: Sequence[str]) -> dict[str, dict[str, list[float]]]:
    """Quintili congelati sulla stagione di scoperta, per statistica."""
    out: dict[str, dict[str, list[float]]] = {}
    disc = [r for r in rows if r.season_label == DISCOVERY_SEASON and r.eligible]
    forma = [contexts[r.lab_match_id].form_diff for r in disc if r.lab_match_id in contexts]
    forma_edges = quintile_edges([v for v in forma if v is not None])
    for key in stat_keys:
        volumes = [expected_volume(r, key) for r in disc if r.actuals.get(key) is not None]
        out[key] = {"volume_atteso": quintile_edges([v for v in volumes if v is not None]), "forma": forma_edges}
    return out


def synthetic_conditions(
    row: SyntheticRow, ctx: MatchContext | None, stat_key: str, edges: dict[str, dict[str, list[float]]]
) -> dict[str, str | None]:
    e = edges.get(stat_key, {})
    return {
        "volume_atteso": quintile_value(expected_volume(row, stat_key), e.get("volume_atteso", [])),
        "forma": quintile_value(ctx.form_diff if ctx else None, e.get("forma", [])),
        "equilibrio": ctx.equilibrio if ctx else None,
        "pareggio": ctx.pareggio if ctx else None,
        "intensita_goal": ctx.intensita_goal if ctx else None,
        "segno_agenti": agents_value(ctx.agents_agree) if ctx else None,
        "riposo": rest_value(ctx.rest_diff) if ctx else None,
        "fase": "finale" if row.phase == "final" else "stagione",
        "livello": row.tier,
    }


@dataclass
class StatMatrix:
    stat_key: str
    seasons: np.ndarray
    match_ids: np.ndarray
    values: np.ndarray
    codes: np.ndarray
    vocab: list[list[str]]
    row_index: list[SyntheticRow] = field(repr=False, default_factory=list)

    def season_mask(self, season: str) -> np.ndarray:
        return self.seasons == season

    def combo_mask(self, combo: Sequence[tuple[int, int]]) -> np.ndarray:
        mask = np.ones(self.values.size, dtype=bool)
        for c, v in combo:
            mask &= self.codes[:, c] == v
        return mask

    def describe(self, combo: Sequence[tuple[int, int]]) -> list[dict[str, str]]:
        return [{"column": SYNTHETIC_COLUMNS[c], "value": self.vocab[c][v]} for c, v in combo]

    def combo_from_conditions(self, conditions: Sequence[dict[str, str]]) -> tuple[tuple[int, int], ...]:
        combo = []
        for cond in conditions:
            c = SYNTHETIC_COLUMNS.index(cond["column"])
            combo.append((c, self.vocab[c].index(cond["value"]) if cond["value"] in self.vocab[c] else -2))
        return tuple(combo)


def build_stat_matrix(
    rows: Sequence[SyntheticRow],
    contexts: dict[int, MatchContext],
    stat_key: str,
    edges: dict[str, dict[str, list[float]]],
) -> StatMatrix:
    kept = [r for r in rows if r.eligible and r.actuals.get(stat_key) is not None]
    vocab_maps: list[dict[str, int]] = [{} for _ in SYNTHETIC_COLUMNS]
    codes = np.full((len(kept), len(SYNTHETIC_COLUMNS)), -1, dtype=np.int16)
    for i, r in enumerate(kept):
        cond = synthetic_conditions(r, contexts.get(r.lab_match_id), stat_key, edges)
        for c, col in enumerate(SYNTHETIC_COLUMNS):
            value = cond[col]
            if value is not None:
                codes[i, c] = vocab_maps[c].setdefault(value, len(vocab_maps[c]))
    return StatMatrix(
        stat_key=stat_key,
        seasons=np.array([r.season_label for r in kept]),
        match_ids=np.array([r.lab_match_id for r in kept]),
        values=np.array([float(r.actuals[stat_key]) for r in kept]),
        codes=codes,
        vocab=[[v for v, _ in sorted(m.items(), key=lambda kv: kv[1])] for m in vocab_maps],
        row_index=kept,
    )


def _rate(won: np.ndarray, mask: np.ndarray) -> tuple[int, int, float | None]:
    n = int(mask.sum())
    wins = int(won[mask].sum()) if n else 0
    return n, wins, (wins / n * 100.0 if n else None)


@dataclass
class SyntheticPattern:
    stat_key: str
    threshold: float
    combo: tuple[tuple[int, int], ...]
    conditions: list[dict[str, str]]
    direction: int
    seasons: dict[str, dict[str, Any]] = field(default_factory=dict)


def discover_synthetic(matrix: StatMatrix, threshold: float) -> list[SyntheticPattern]:
    disc = matrix.season_mask(DISCOVERY_SEASON)
    if not disc.any():
        return []
    won = matrix.values > threshold
    baseline = float(won[disc].mean() * 100.0)
    atoms = [
        (c, v)
        for c in range(len(SYNTHETIC_COLUMNS))
        for v in range(len(matrix.vocab[c]))
        if (matrix.codes[disc, c] == v).any()
    ]
    masks = {a: (matrix.codes[:, a[0]] == a[1]) & disc for a in atoms}
    found: list[tuple[SyntheticPattern, float]] = []
    seen: set[frozenset] = set()

    def consider(combo: tuple[tuple[int, int], ...], mask: np.ndarray) -> float | None:
        key = frozenset(combo)
        if key in seen:
            return None
        seen.add(key)
        n, wins, rate = _rate(won, mask)
        if n < MIN_SAMPLE or rate is None or abs(rate - baseline) < SYNTHETIC_DISCOVERY_DEVIATION_PCT:
            return None
        deviation = rate - baseline
        pattern = SyntheticPattern(
            stat_key=matrix.stat_key,
            threshold=threshold,
            combo=combo,
            conditions=matrix.describe(combo),
            direction=1 if deviation >= 0 else -1,
        )
        pattern.seasons[DISCOVERY_SEASON] = {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": round(rate, 3),
            "baseline_win_rate_pct": round(baseline, 3),
            "deviation_pct": round(deviation, 3),
            "verdict": "discovery",
            "null_p": None,
        }
        found.append((pattern, abs(deviation)))
        return abs(deviation)

    for a in atoms:
        consider((a,), masks[a])
    two: list[tuple[SyntheticPattern, float]] = []
    for a, b in combinations(atoms, 2):
        if a[0] == b[0]:
            continue
        score = consider((a, b), masks[a] & masks[b])
        if score is not None:
            two.append((found[-1][0], score))
    two.sort(key=lambda item: (-item[1], item[0].combo))
    for base, _ in two[:REFINEMENT_BASES]:
        used = {c for c, _ in base.combo}
        base_mask = masks[base.combo[0]] & masks[base.combo[1]]
        for a in atoms:
            if a[0] in used:
                continue
            consider(tuple(sorted(base.combo + (a,))), base_mask & masks[a])
    return [p for p, _ in found]


class DeviationNull:
    """Probabilita' che un gruppo casuale di n partite della stagione abbia uno
    scostamento dalla media >= soglia nella direzione indicata."""

    def __init__(self, won: np.ndarray, seed_offset: int = 0) -> None:
        self.size = int(won.size)
        self.baseline = float(won.mean() * 100.0) if self.size else 0.0
        if self.size == 0:
            self._cum = np.zeros((0, 0))
            return
        rng = np.random.default_rng(NULL_SEED + seed_offset)
        perm = rng.permuted(np.tile(np.arange(self.size), (NULL_SAMPLES, 1)), axis=1)
        self._cum = np.cumsum(won[perm].astype(np.float32), axis=1)

    def p_deviation(self, n: int, direction: int, threshold_pct: float) -> float | None:
        if n <= 0 or n > self.size:
            return None
        dev = self._cum[:, n - 1] / n * 100.0 - self.baseline
        return float((dev * direction >= threshold_pct).mean())


def validate_synthetic(
    matrix: StatMatrix, patterns: Sequence[SyntheticPattern], seasons: Sequence[str], confirm_pct: float
) -> None:
    by_threshold: dict[float, list[SyntheticPattern]] = defaultdict(list)
    for p in patterns:
        by_threshold[p.threshold].append(p)
    for t_idx, (threshold, group) in enumerate(sorted(by_threshold.items())):
        won = matrix.values > threshold
        for s_idx, season in enumerate(seasons):
            smask = matrix.season_mask(season)
            null = DeviationNull(won[smask], seed_offset=100 * t_idx + s_idx)
            for p in group:
                n, wins, rate = _rate(won, matrix.combo_mask(p.combo) & smask)
                deviation = rate - null.baseline if rate is not None else None
                verdict = synthetic_verdict(n, deviation, p.direction)
                p.seasons[season] = {
                    "n": n,
                    "wins": wins,
                    "losses": n - wins,
                    "win_rate_pct": round(rate, 3) if rate is not None else None,
                    "baseline_win_rate_pct": round(null.baseline, 3),
                    "deviation_pct": round(deviation, 3) if deviation is not None else None,
                    "verdict": verdict,
                    "null_p": (
                        null.p_deviation(n, p.direction, confirm_pct) if verdict != VERDICT_INSUFFICIENT else None
                    ),
                }


def matched_rows(matrix: StatMatrix, combo: Sequence[tuple[int, int]]) -> list[SyntheticRow]:
    mask = matrix.combo_mask(combo)
    return [matrix.row_index[i] for i in np.flatnonzero(mask)]

