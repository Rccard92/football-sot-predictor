"""Vocabolario filtri atomici per Pattern Insights (Run V2).

Stessa filosofia del Pattern Grid originale (pattern_grid_vocabulary.py):
nessuna soglia scelta a mano, i valori/classi vengono letti dai dati
realmente osservati. Qui il vocabolario e' piu' ampio perche' Run V2
porta, oltre ai pilastri Goal/Balance/Acquistabilita' gia' noti, anche
statistiche pre-partita (tiri, tiri in porta, corner, cartellini, arbitro)
gia' aggregate come medie mobili e scarto dalla media di campionato.

Le feature continue (es. "scarto tiri in porta squadra 1 vs media lega")
vengono divise in quintili calcolati sui dati osservati in questa chiamata
(mai soglie fisse), riusando lo stesso principio del resto del progetto.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.cecchino_data_lab.pattern_grid_vocabulary import (
    SIGNAL_ACTIVE_COLUMN,
    Atom,
    atom_holds,
    combo_holds,
    combo_text,
    combo_to_json,
    enumerate_combos,
)

if TYPE_CHECKING:
    from app.services.cecchino_data_lab.run_v2_grid_dataset import RunV2GridRow

__all__ = [
    "Atom",
    "atom_holds",
    "combo_holds",
    "combo_text",
    "combo_to_json",
    "enumerate_combos",
    "CATEGORICAL_COLUMNS",
    "CONTINUOUS_FEATURE_COLUMNS",
    "SIGNAL_ACTIVE_COLUMN",
    "QuantileBinner",
    "bin_continuous_features",
    "build_atom_vocabulary",
]

# Stessi 4 pilastri Goal + finale, stessi 4 pilastri Balance, acquistabilita'
# per il mercato specifico: identici concettualmente al Pattern Grid v1,
# incapsulati pero' in una struttura JSON diversa (vedi run_v2_grid_dataset.py
# per l'estrazione dal JSON grezzo).
CATEGORICAL_COLUMNS: tuple[str, ...] = (
    "goal_offensive_production_class",
    "goal_defensive_solidity_class",
    "goal_match_tempo_class",
    "goal_offensive_stability_class",
    "goal_final_class",
    "balance_f36_class",
    "balance_dominance_class",
    "balance_draw_credibility_class",
    "balance_gap_coherence_class",
    "purchasability_class",
)
# SIGNAL_ACTIVE_COLUMN e' importato da pattern_grid_vocabulary: atom_holds()
# di quel modulo lo confronta internamente, quindi va riusato lo stesso nome
# di colonna ("pre_signal_active"), non un valore nuovo a piacere.

# Feature continue pre-partita nuove (da extra_stats_prematch_json): per ogni
# statistica, lo scarto della squadra rispetto alla media del proprio
# campionato ("competition_delta_for") - il singolo numero piu' informativo
# per confrontare squadre di leghe diverse sulla stessa scala.
_STAT_KEYS = ("shots", "sot", "corners", "fouls", "yellow_cards", "red_cards")
CONTINUOUS_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    f"{side}_{stat}_delta_class" for side in ("home", "away") for stat in _STAT_KEYS
) + ("referee_cards_avg_class",)

# Stessi valori del Pattern Grid originale (very_low..very_high), cosi'
# pattern_grid_labels.humanize_value() li traduce gia' senza bisogno di una
# tabella nuova.
_BIN_LABELS = ("very_low", "low", "medium", "high", "very_high")


@dataclass(frozen=True)
class QuantileBinner:
    """Confini di quintile calcolati su valori osservati; classifica un
    valore continuo in una delle 5 classi standard del progetto."""

    edges: tuple[float, ...]  # 4 confini interni -> 5 bucket

    def label_for(self, value: float) -> str:
        for i, edge in enumerate(self.edges):
            if value <= edge:
                return _BIN_LABELS[i]
        return _BIN_LABELS[-1]

    @staticmethod
    def from_values(values: list[float]) -> "QuantileBinner | None":
        if len(values) < 20:
            return None
        quantiles = statistics.quantiles(values, n=5, method="inclusive")
        return QuantileBinner(edges=tuple(quantiles))


def bin_continuous_features(
    raw_by_column: dict[str, list[float]],
) -> dict[str, QuantileBinner]:
    """Un binner per colonna continua, calcolato sui valori osservati
    passati (tipicamente tutte le righe eleggibili di una singola run)."""
    binners: dict[str, QuantileBinner] = {}
    for col, values in raw_by_column.items():
        binner = QuantileBinner.from_values(values)
        if binner is not None:
            binners[col] = binner
    return binners


def build_atom_vocabulary(rows: list["RunV2GridRow"]) -> list[Atom]:
    """Stessa logica di pattern_grid_vocabulary.build_atom_vocabulary, ma
    sul set di colonne (categoriche + continue gia' binnate) di Run V2."""
    all_columns = CATEGORICAL_COLUMNS + CONTINUOUS_FEATURE_COLUMNS
    seen: dict[str, set[str]] = {c: set() for c in all_columns}
    has_signal_active = False
    for row in rows:
        for col in all_columns:
            v = row.categorical.get(col)
            if v:
                seen[col].add(str(v))
        if row.signal_active:
            has_signal_active = True

    atoms: list[Atom] = []
    for col, values in seen.items():
        for v in sorted(values):
            atoms.append(Atom(col, v))
    if has_signal_active:
        atoms.append(Atom(SIGNAL_ACTIVE_COLUMN, "true"))
    return atoms
