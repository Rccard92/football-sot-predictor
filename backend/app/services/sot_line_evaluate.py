"""Valutazione euristica Over/Under su linea SOT (senza quote bookmaker)."""

from __future__ import annotations

from typing import Any, Literal


def evaluate_sot_line(expected_sot: float, line_value: float) -> dict[str, Any]:
    gap = round(float(expected_sot) - float(line_value), 2)
    suggestion: Literal["over", "under", "no_bet"]
    strength: Literal["forte", "interessante", "leggero", "neutro"]

    if gap > 1.25:
        suggestion, strength = "over", "forte"
    elif gap > 0.75:
        suggestion, strength = "over", "interessante"
    elif gap > 0.25:
        suggestion, strength = "over", "leggero"
    elif gap >= -0.25:
        suggestion, strength = "no_bet", "neutro"
    elif gap < -1.25:
        suggestion, strength = "under", "forte"
    elif gap < -0.75:
        suggestion, strength = "under", "interessante"
    else:
        suggestion, strength = "under", "leggero"

    if suggestion == "over":
        label = f"Over {line_value:g} valutabile"
        if strength == "forte":
            label = f"Over {line_value:g} con margine ampio"
        elif strength == "leggero":
            label = f"Over {line_value:g} a margine contenuto"
    elif suggestion == "under":
        label = f"Under {line_value:g} valutabile"
        if strength == "forte":
            label = f"Under {line_value:g} con margine ampio"
        elif strength == "leggero":
            label = f"Under {line_value:g} a margine contenuto"
    else:
        label = "Zona neutra rispetto alla linea"

    explanation = (
        "Questa analisi non usa le quote del bookmaker e non identifica value bet. "
        f"La previsione di tiri in porta è {expected_sot:.2f}, la linea è {line_value:g}: "
        f"differenza {gap:+.2f}. "
    )
    if strength == "neutro":
        explanation += (
            "Il modello è vicino alla linea: il segnale è debole e il contesto partita va valutato con prudenza."
        )
    elif suggestion == "over":
        explanation += (
            "Il modello indica più tiri in porta attesi rispetto alla linea; "
            "confronta sempre con quota, assenze e motivazione sportiva."
        )
    else:
        explanation += (
            "Il modello indica meno tiri in porta attesi rispetto alla linea; "
            "confronta sempre con quota e contesto."
        )

    return {
        "expected_sot": float(expected_sot),
        "line_value": float(line_value),
        "gap": gap,
        "suggestion": suggestion,
        "strength": strength,
        "label": label,
        "explanation": explanation,
    }
