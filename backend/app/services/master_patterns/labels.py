"""Testo in italiano delle condizioni dei pattern V3."""

from __future__ import annotations

from collections.abc import Sequence

COLUMN_LABELS: dict[str, str] = {
    "prob_v3": "Probabilita' V3",
    "v3_vs_book": "V3 rispetto al book",
    "quota": "Quota",
    "forma": "Forma casa rispetto a ospite",
    "equilibrio": "Equilibrio",
    "pareggio": "Credibilita' pareggio",
    "intensita_goal": "Intensita' goal",
    "segno_agenti": "Specialisti concordi sul segno",
    "riposo": "Riposo",
    "fase": "Fase",
    "livello": "Livello",
    "volume_atteso": "Volume atteso dagli agenti",
}

QUINTILE_LABELS: dict[str, str] = {
    "Q1": "molto basso",
    "Q2": "basso",
    "Q3": "medio",
    "Q4": "alto",
    "Q5": "molto alto",
}

VALUE_LABELS: dict[str, dict[str, str]] = {
    "equilibrio": {
        "molto_basso": "molto basso",
        "basso": "basso",
        "medio": "medio",
        "alto": "alto",
        "molto_alto": "molto alto",
    },
    "segno_agenti": {"3": "3 su 3", "2": "2 su 3", "0-1": "0 o 1 su 3"},
    "riposo": {
        "meno_riposo_casa": "casa con meno riposo",
        "piu_riposo_casa": "casa con piu' riposo",
        "pari": "riposo simile",
    },
    "fase": {"stagione": "stagione regolare", "finale": "ultime 5 giornate"},
    "livello": {"top": "prime divisioni", "lower": "divisioni inferiori"},
}
VALUE_LABELS["pareggio"] = VALUE_LABELS["equilibrio"]
VALUE_LABELS["intensita_goal"] = VALUE_LABELS["equilibrio"]

QUINTILE_COLUMNS = {"prob_v3", "v3_vs_book", "quota", "forma", "volume_atteso"}


def condition_label(column: str, value: str) -> str:
    if column in QUINTILE_COLUMNS:
        text = QUINTILE_LABELS.get(value, value)
    else:
        text = VALUE_LABELS.get(column, {}).get(value, value)
    return f"{COLUMN_LABELS.get(column, column)}: {text}"


def conditions_text(conditions: Sequence[dict[str, str]]) -> str:
    return " + ".join(condition_label(c["column"], c["value"]) for c in conditions)
