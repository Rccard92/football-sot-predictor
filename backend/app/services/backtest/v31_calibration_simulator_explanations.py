"""Spiegazioni leggibili in italiano per simulatore v3.1."""

from __future__ import annotations

_REASON_IT: dict[str, str] = {
    "V31_OVER_6_5_PROB_OK": "la probabilità stimata su Over 6.5 supera la soglia",
    "V31_OVER_7_5_PREMIUM": "Over 7.5 risulta preferibile per probabilità e margine",
    "V31_OVER_8_5_PREMIUM": "Over 8.5 è supportato da previsione alta e probabilità adeguata",
    "V31_MARGIN_OK": "il margine tra previsione e linea è sufficiente",
    "V31_CONFIDENCE_HIGH": "la confidenza sui dati pre-match è alta",
    "V31_CONFIDENCE_MEDIUM": "la confidenza è media ma accettabile",
    "V31_DATA_QUALITY_OK": "i dati pre-match sono completi e senza warning rilevanti",
    "V31_PROBABILITY_BELOW_THRESHOLD": "la probabilità stimata non supera la soglia minima",
    "V31_LOW_CONFIDENCE": "la confidenza sui dati o sul segnale è troppo bassa",
    "V31_LINE_TOO_RISKY": "la linea richiesta è troppo alta rispetto alla previsione",
    "V31_DATA_QUALITY_WEAK": "la qualità dei dati pre-match è debole",
    "V31_MARGIN_TOO_LOW": "il margine tra previsione e linea è troppo basso",
    "V31_BORDERLINE_SIGNAL": "il segnale è borderline: probabilità o margine appena sufficienti",
    "V31_MISSING_FEATURES": "alcune feature pre-match non sono disponibili",
}


def build_human_explanation(
    *,
    decision: str,
    selected_line: float | None,
    reason_codes: list[str],
    predicted_total: float | None,
    prob_pct: float | None,
    home_name: str,
    away_name: str,
) -> str:
    if decision == "GIOCA" and selected_line is not None and predicted_total is not None:
        prob_txt = f" del {prob_pct:.0f}%" if prob_pct is not None else ""
        parts = [
            f"La v3.1 consiglia Over {selected_line} perché la previsione totale è {predicted_total} SOT"
            f", con una probabilità stimata{prob_txt}.",
            "La base statistica è sostenuta dalla produzione SOT delle due squadre e dallo split casa/trasferta.",
        ]
    elif decision == "BORDERLINE":
        parts = [
            f"La v3.1 valuta {home_name}–{away_name} come caso borderline: "
            "il segnale c'è ma non è abbastanza netto per una giocata piena.",
        ]
    else:
        parts = [
            f"La v3.1 non consiglia la giocata su {home_name}–{away_name} perché, "
            "pur avendo una previsione vicina alla linea, la probabilità stimata non supera la soglia minima "
            "o il margine è basso.",
        ]

    extras = [_REASON_IT.get(c, "") for c in reason_codes if c in _REASON_IT]
    if extras:
        parts.append(" ".join(e for e in extras if e) + ".")

    return " ".join(parts)
