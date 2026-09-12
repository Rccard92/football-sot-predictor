"""Traduzione dei filtri tecnici Pattern Grid in etichette leggibili (italiano).

Solo presentazione: non cambia la logica del motore, serve a spiegare in
parole semplici cosa sta analizzando ogni pattern.
"""

from __future__ import annotations

from typing import Any

COLUMN_LABELS: dict[str, str] = {
    "pre_goal_v4_compat_offensive_production_class": "Produzione offensiva",
    "pre_goal_v4_compat_defensive_solidity_class": "Solidità difensiva",
    "pre_goal_v4_compat_match_tempo_class": "Ritmo della partita",
    "pre_goal_v4_compat_offensive_stability_class": "Stabilità offensiva",
    "pre_goal_v4_compat_final_class": "Intensità Goal complessiva",
    "pre_balance_f36_class": "Equilibrio strutturale (F36)",
    "pre_balance_dominance_class": "Convinzione del modello",
    "pre_balance_draw_credibility_class": "Credibilità del pareggio",
    "pre_balance_gap_coherence_class": "Coerenza del gap 1/2",
    "pre_purch_v36_class": "Acquistabilità",
    "pre_signal_active": "Segnale Cecchino",
}

VALUE_LABELS: dict[str, str] = {
    "very_low": "molto bassa",
    "very_high": "molto alta",
    "low": "bassa",
    "medium": "media",
    "high": "alta",
    "strong_balance": "equilibrio forte",
    "balance": "equilibrio",
    "transition": "transizione",
    "imbalance": "squilibrio",
    "strong_imbalance": "forte squilibrio",
    "true": "attivo",
}

MARKET_LABELS: dict[str, str] = {
    "HOME": "Segno 1",
    "DRAW": "Segno X",
    "AWAY": "Segno 2",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "12",
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
}


def humanize_value(value: str) -> str:
    return VALUE_LABELS.get(value.lower(), value)


def humanize_atom(column: str, value: str) -> str:
    if column == "pre_signal_active":
        return "Segnale Cecchino attivo"
    label = COLUMN_LABELS.get(column, column)
    return f"{label}: {humanize_value(value)}"


def humanize_combo(filters_json: list[dict[str, Any]]) -> str:
    return " + ".join(humanize_atom(f["column"], f["value"]) for f in filters_json)


def market_label(market_key: str) -> str:
    return MARKET_LABELS.get(market_key, market_key)
