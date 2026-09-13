"""Valutazione vettoriale dei pattern su un insieme di righe Run V2.

Una maschera booleana numpy per atomo, calcolata una volta sola e riusata:
la maschera di una combinazione e' l'AND di quelle dei suoi atomi. Su 27mila
pattern evita decine di milioni di confronti riga per riga.

Le statistiche replicano esattamente `run_v2_grid_engine._stats`:
- win rate su tutte le righe matchate
- ROI come media dei profitti disponibili (righe senza profitto escluse)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.services.cecchino_data_lab.run_v2_grid_dataset import RunV2GridRow
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import SIGNAL_ACTIVE_COLUMN, Atom

NULL_SAMPLES = 400
NULL_SEED = 20260913


class RowMatrix:
    def __init__(self, rows: list[RunV2GridRow]):
        self._rows = rows
        self.size = len(rows)
        self.won = np.fromiter((bool(r.won) for r in rows), dtype=bool, count=self.size)
        self.profit = np.fromiter(
            (r.profit_1u if r.profit_1u is not None else np.nan for r in rows),
            dtype=float,
            count=self.size,
        )
        self.quota = np.fromiter(
            (r.quota_book if r.quota_book is not None else np.nan for r in rows),
            dtype=float,
            count=self.size,
        )
        self._masks: dict[tuple[str, str], np.ndarray] = {}

    def atom_mask(self, atom: Atom) -> np.ndarray:
        key = (atom.column, atom.value)
        mask = self._masks.get(key)
        if mask is None:
            if atom.column == SIGNAL_ACTIVE_COLUMN:
                mask = np.fromiter(
                    (r.signal_active is True for r in self._rows), dtype=bool, count=self.size
                )
            else:
                mask = np.fromiter(
                    (r.categorical.get(atom.column) == atom.value for r in self._rows),
                    dtype=bool,
                    count=self.size,
                )
            self._masks[key] = mask
        return mask

    def combo_mask(self, combo: tuple[Atom, ...]) -> np.ndarray:
        mask = np.ones(self.size, dtype=bool)
        for atom in combo:
            mask &= self.atom_mask(atom)
        return mask

    def stats(self, mask: np.ndarray) -> dict[str, Any]:
        n = int(mask.sum())
        wins = int(self.won[mask].sum())
        profits = self.profit[mask]
        profits = profits[~np.isnan(profits)]
        quotes = self.quota[mask]
        quotes = quotes[~np.isnan(quotes)]
        return {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": round(wins / n * 100.0, 3) if n else None,
            "roi_pct": round(float(profits.mean()) * 100.0, 3) if profits.size else None,
            "profit_units": round(float(profits.sum()), 3) if profits.size else None,
            "avg_quota": round(float(quotes.mean()), 3) if quotes.size else None,
        }

    def baseline_win_rate_pct(self) -> float | None:
        return round(float(self.won.mean()) * 100.0, 3) if self.size else None


class NullModel:
    """Quanto spesso un sottoinsieme CASUALE di partite della stagione di
    verifica, grande quanto il pattern, passerebbe lo stesso criterio di
    conferma. E' il riferimento senza il quale una percentuale di
    riconferma non si puo' interpretare.

    Un'unica matrice di permutazioni casuali per insieme di righe: i suoi
    prefissi di lunghezza n sono campioni senza reinserimento di qualunque
    dimensione, quindi le probabilita' per ogni n si ottengono da somme
    cumulate in un solo passaggio.
    """

    def __init__(self, matrix: RowMatrix, *, deviation_threshold_pct: float):
        rng = np.random.default_rng(NULL_SEED)
        size = matrix.size
        self._size = size
        self._threshold = deviation_threshold_pct
        if size == 0:
            self._ok = False
            return
        self._ok = True
        perm = rng.permuted(np.tile(np.arange(size), (NULL_SAMPLES, 1)), axis=1)

        won = matrix.won[perm].astype(float)
        self._won_cum = np.cumsum(won, axis=1)

        profit = matrix.profit[perm]
        has_profit = ~np.isnan(profit)
        self._profit_cum = np.cumsum(np.where(has_profit, profit, 0.0), axis=1)
        self._profit_count_cum = np.cumsum(has_profit, axis=1)
        self._baseline = float(matrix.won.mean()) * 100.0

    def _col(self, n: int) -> int | None:
        if not self._ok or n <= 0:
            return None
        return min(n, self._size) - 1

    def p_roi_positive(self, n: int) -> float | None:
        c = self._col(n)
        if c is None:
            return None
        counts = self._profit_count_cum[:, c]
        valid = counts > 0
        if not valid.any():
            return None
        roi = self._profit_cum[valid, c] / counts[valid]
        return float((roi > 0).mean())

    def p_deviation(self, n: int, *, direction: int) -> float | None:
        c = self._col(n)
        if c is None:
            return None
        rate = self._won_cum[:, c] / (c + 1) * 100.0
        dev = rate - self._baseline
        if direction >= 0:
            return float((dev >= self._threshold).mean())
        return float((dev <= -self._threshold).mean())
