"""Spiegazioni leggibili in italiano per simulatore v3.1."""

from __future__ import annotations

from typing import Any

_REASON_IT: dict[str, str] = {
    "stable_sot_production": "entrambe le squadre mostrano una produzione SOT stabile",
    "strong_offensive_macro": "gli indici di produzione offensiva sono sopra la media",
    "home_away_split_supports": "lo split casa/trasferta conferma il volume offensivo atteso",
    "recent_form_positive": "la forma recente sostiene il volume di tiri in porta",
    "player_layer_ok": "il layer giocatori non segnala cali rilevanti",
    "absences_light": "le assenze offensive non risultano abbastanza pesanti da abbassare la previsione",
    "line_65_best_margin": "la linea 6.5 offre il miglior margine rispetto al totale previsto",
    "line_75_excluded_margin": "la linea 7.5 viene esclusa perché il margine non è sufficiente",
    "line_85_excluded": "la linea 8.5 è troppo alta rispetto al totale atteso",
    "prob_over_65_sufficient": "la probabilità stimata su Over 6.5 supera la soglia richiesta",
    "prob_over_75_sufficient": "la probabilità su Over 7.5 è sufficiente per una giocata più aperta",
    "data_quality_ok": "la qualità dei dati pre-match è accettabile",
    "data_quality_weak": "la qualità dei dati è debole",
    "warnings_high": "troppi warning sui dati pre-match",
    "confidence_high": "il livello di confidenza del modello è alto",
    "confidence_low": "la confidenza del modello è bassa",
    "no_bet_quality": "si preferisce non giocare per cautela sulla qualità del dato",
    "no_bet_probability": "la probabilità stimata non giustifica una giocata",
    "borderline_probability": "il segnale è borderline: margine o probabilità appena sufficienti",
    "missing_features": "alcune feature pre-match non sono disponibili",
    "conservative_threshold": "la strategia conservativa richiede segnali più netti",
    "balanced_opens_75": "la strategia bilanciata ammette Over 7.5 con margine adeguato",
}


def build_human_explanation(
    *,
    decision: str,
    selected_line: float | None,
    reason_codes: list[str],
    predicted_total: float | None,
    home_name: str,
    away_name: str,
) -> str:
    parts: list[str] = []
    if decision == "GIOCA" and selected_line is not None and predicted_total is not None:
        parts.append(
            f"Il modello consiglia Over {selected_line} su {home_name}–{away_name} "
            f"con totale SOT previsto intorno a {predicted_total}."
        )
    elif decision == "BORDERLINE":
        parts.append(
            f"Il modello valuta {home_name}–{away_name} come caso borderline: "
            "il segnale c'è ma non è abbastanza netto per una giocata piena."
        )
    else:
        parts.append(
            f"Il modello non consiglia giocata su {home_name}–{away_name} "
            "in questa configurazione."
        )

    reasons = [_REASON_IT.get(c, c.replace("_", " ")) for c in reason_codes[:6]]
    if reasons:
        parts.append(" ".join(r.capitalize() if r == reasons[0] else r for r in reasons) + ".")

    return " ".join(parts)
