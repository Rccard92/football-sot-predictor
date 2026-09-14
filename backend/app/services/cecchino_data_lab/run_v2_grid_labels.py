"""Etichette leggibili per i filtri Pattern Insights (Run V2).

Riusa humanize_value/VALUE_LABELS di pattern_grid_labels.py (stessi valori
very_low..very_high, stesso "attivo" per il segnale) — qui serve solo la
tabella nomi-colonna, perche' i nomi tecnici di Run V2 sono diversi da
quelli del Pattern Grid originale (JSON diverso, stessi concetti).
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino_data_lab.pattern_grid_labels import humanize_value

COLUMN_LABELS: dict[str, str] = {
    "goal_offensive_production_class": "Produzione offensiva",
    "goal_defensive_solidity_class": "Solidità difensiva",
    "goal_match_tempo_class": "Ritmo della partita",
    "goal_offensive_stability_class": "Stabilità offensiva",
    "goal_final_class": "Intensità Goal complessiva",
    "balance_f36_class": "Equilibrio strutturale (F36)",
    "balance_dominance_class": "Convinzione del modello",
    "balance_draw_credibility_class": "Credibilità del pareggio",
    "balance_gap_coherence_class": "Coerenza del gap 1/2",
    "purchasability_class": "Acquistabilità",
    "pre_signal_active": "Segnale Cecchino",
    "home_shots_delta_class": "Tiri squadra 1 vs media lega",
    "away_shots_delta_class": "Tiri squadra 2 vs media lega",
    "home_sot_delta_class": "Tiri in porta squadra 1 vs media lega",
    "away_sot_delta_class": "Tiri in porta squadra 2 vs media lega",
    "home_corners_delta_class": "Corner squadra 1 vs media lega",
    "away_corners_delta_class": "Corner squadra 2 vs media lega",
    "home_fouls_delta_class": "Falli squadra 1 vs media lega",
    "away_fouls_delta_class": "Falli squadra 2 vs media lega",
    "home_yellow_cards_delta_class": "Cartellini gialli squadra 1 vs media lega",
    "away_yellow_cards_delta_class": "Cartellini gialli squadra 2 vs media lega",
    "home_red_cards_delta_class": "Cartellini rossi squadra 1 vs media lega",
    "away_red_cards_delta_class": "Cartellini rossi squadra 2 vs media lega",
    "referee_cards_avg_class": "Severità storica arbitro",
}

MARKET_LABELS: dict[str, str] = {
    "HOME": "Segno 1",
    "DRAW": "Segno X",
    "AWAY": "Segno 2",
    "HOME_PT": "Segno 1 primo tempo",
    "DRAW_PT": "Segno X primo tempo",
    "AWAY_PT": "Segno 2 primo tempo",
    "ONE_X": "1X",
    "X_TWO": "X2",
    "ONE_TWO": "12",
    "OVER_0_5": "Over 0.5",
    "UNDER_0_5": "Under 0.5",
    "OVER_1_5": "Over 1.5",
    "UNDER_1_5": "Under 1.5",
    "OVER_2_5": "Over 2.5",
    "UNDER_2_5": "Under 2.5",
    "OVER_3_5": "Over 3.5",
    "UNDER_3_5": "Under 3.5",
}

TARGET_LABELS: dict[str, str] = {
    "total_shots": "Tiri totali",
    "home_shots": "Tiri squadra 1",
    "away_shots": "Tiri squadra 2",
    "total_sot": "Tiri in porta totali",
    "home_sot": "Tiri in porta squadra 1",
    "away_sot": "Tiri in porta squadra 2",
    "total_corners": "Corner totali",
    "home_corners": "Corner squadra 1",
    "away_corners": "Corner squadra 2",
    "total_yellow_cards": "Cartellini gialli totali",
    "home_yellow_cards": "Cartellini gialli squadra 1",
    "away_yellow_cards": "Cartellini gialli squadra 2",
}


def humanize_atom(column: str, value: str) -> str:
    if column == "pre_signal_active":
        return "Segnale Cecchino attivo"
    label = COLUMN_LABELS.get(column, column)
    return f"{label}: {humanize_value(value)}"


def humanize_combo(filters_json: list[dict[str, Any]]) -> str:
    return " + ".join(humanize_atom(f["column"], f["value"]) for f in filters_json)


def target_label(target_key: str, threshold: float | None = None) -> str:
    if threshold is None:
        return MARKET_LABELS.get(target_key, target_key)
    base = TARGET_LABELS.get(target_key, target_key)
    return f"{base} Over {threshold}"
