"""Vocabolario filtri atomici per la ricerca esaustiva Pattern Grid.

Le classi (es. "high"/"molto bassa"/...) non sono hard-coded: vengono lette
dai valori realmente osservati nei dati di ciascuno stadio, perché colonne
diverse (pilastri Goal vs pilastri Balance vs Acquistabilità) usano scale di
etichette diverse tra loro — indovinarle a mano rischierebbe di non trovare
mai un match.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.cecchino_data_lab.pattern_grid_dataset import GridRow

CATEGORICAL_COLUMNS: tuple[str, ...] = (
    "pre_goal_v4_compat_offensive_production_class",
    "pre_goal_v4_compat_defensive_solidity_class",
    "pre_goal_v4_compat_match_tempo_class",
    "pre_goal_v4_compat_offensive_stability_class",
    "pre_goal_v4_compat_final_class",
    "pre_balance_f36_class",
    "pre_balance_dominance_class",
    "pre_balance_draw_credibility_class",
    "pre_balance_gap_coherence_class",
    "pre_purch_v36_class",
)
SIGNAL_ACTIVE_COLUMN = "pre_signal_active"


@dataclass(frozen=True)
class Atom:
    column: str
    value: str


def build_atom_vocabulary(rows: list["GridRow"]) -> list[Atom]:
    """Valori distinti realmente osservati per ogni colonna categorica, più
    l'atomo speciale segnale-attivo. Non include valori vuoti/None."""
    seen: dict[str, set[str]] = {c: set() for c in CATEGORICAL_COLUMNS}
    has_signal_active = False
    for row in rows:
        for col in CATEGORICAL_COLUMNS:
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


def atom_holds(row: "GridRow", atom: Atom) -> bool:
    if atom.column == SIGNAL_ACTIVE_COLUMN:
        return row.signal_active is True
    return row.categorical.get(atom.column) == atom.value


def combo_holds(row: "GridRow", combo: tuple[Atom, ...]) -> bool:
    return all(atom_holds(row, a) for a in combo)


def enumerate_combos(atoms: list[Atom], size: int) -> list[tuple[Atom, ...]]:
    """Combinazioni di `size` atomi da colonne diverse (due valori della
    stessa colonna non possono valere insieme)."""
    out: list[tuple[Atom, ...]] = []
    for combo in combinations(atoms, size):
        cols = {a.column for a in combo}
        if len(cols) == size:
            out.append(combo)
    return out


def combo_text(combo: tuple[Atom, ...]) -> str:
    return " AND ".join(f"{a.column}={a.value}" for a in combo)


def combo_to_json(combo: tuple[Atom, ...]) -> list[dict[str, str]]:
    return [{"column": a.column, "value": a.value} for a in combo]
