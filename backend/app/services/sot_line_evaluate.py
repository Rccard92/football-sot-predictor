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


def evaluate_match_sot_line(
    home_expected_sot: float,
    away_expected_sot: float,
    line_value: float,
    *,
    home_adjusted_expected_sot: float | None = None,
    away_adjusted_expected_sot: float | None = None,
    use_adjusted: bool = False,
    odds: float | None,
    bookmaker: str,
    market_type: str,
) -> dict[str, Any]:
    """Valutazione Over/Under sulla somma dei tiri in porta attesi (stesse soglie di `evaluate_sot_line`)."""
    baseline_total_expected_sot = round(float(home_expected_sot) + float(away_expected_sot), 2)
    adjusted_total_expected_sot = None
    if home_adjusted_expected_sot is not None and away_adjusted_expected_sot is not None:
        adjusted_total_expected_sot = round(
            float(home_adjusted_expected_sot) + float(away_adjusted_expected_sot),
            2,
        )
    total_expected_sot = (
        float(adjusted_total_expected_sot)
        if use_adjusted and adjusted_total_expected_sot is not None
        else float(baseline_total_expected_sot)
    )
    model_used = "baseline_v0_2_context_player" if use_adjusted and adjusted_total_expected_sot is not None else "baseline_v0_1"
    line_f = float(line_value)
    ev = evaluate_sot_line(total_expected_sot, line_f)
    suggestion = ev["suggestion"]
    strength = ev["strength"]
    gap = float(ev["gap"])

    if suggestion == "over":
        label = f"Over {line_f:g} tiri in porta totali valutabile"
        if strength == "interessante":
            label = f"Over {line_f:g} tiri in porta totali interessante"
        elif strength == "leggero":
            label = f"Over {line_f:g} tiri in porta totali a margine contenuto"
    elif suggestion == "under":
        label = f"Under {line_f:g} tiri in porta totali valutabile"
        if strength == "interessante":
            label = f"Under {line_f:g} tiri in porta totali interessante"
        elif strength == "leggero":
            label = f"Under {line_f:g} tiri in porta totali a margine contenuto"
    else:
        label = "Nessun margine chiaro sulla linea (tiri in porta totali)"

    implied_probability: float | None = None
    if odds is not None and float(odds) > 0:
        implied_probability = round(100.0 / float(odds), 2)

    parts = [
        f"Il modello stima {total_expected_sot:.2f} tiri in porta totali contro una linea bookmaker di {line_f:g}.",
        f"Il margine è {gap:+.2f} tiri in porta.",
    ]
    if implied_probability is not None:
        parts.append(
            f"La quota implica una probabilità indicativa di circa {implied_probability:g}%.",
        )
    parts.append(
        "Questa versione non considera ancora formazioni ufficiali, assenze e una quota equa calcolata dal modello.",
    )
    explanation = " ".join(parts)
    baseline_gap = round(baseline_total_expected_sot - line_f, 2)
    adjusted_gap = (
        round(adjusted_total_expected_sot - line_f, 2) if adjusted_total_expected_sot is not None else None
    )
    warning = None
    if adjusted_gap is not None and abs(adjusted_gap - baseline_gap) >= 0.4:
        warning = "Differenza significativa tra baseline e v0.2: usare prudenza nell'interpretazione."

    return {
        "market_type": market_type,
        "bookmaker": bookmaker.strip(),
        "line_value": line_f,
        "odds": float(odds) if odds is not None else None,
        "home_expected_sot": round(float(home_expected_sot), 2),
        "away_expected_sot": round(float(away_expected_sot), 2),
        "total_expected_sot": total_expected_sot,
        "gap": gap,
        "suggestion": suggestion,
        "strength": strength,
        "label": label,
        "implied_probability": implied_probability,
        "explanation": explanation,
        "model_used": model_used,
        "baseline_total_expected_sot": baseline_total_expected_sot,
        "adjusted_total_expected_sot": adjusted_total_expected_sot,
        "baseline_gap": baseline_gap,
        "adjusted_gap": adjusted_gap,
        "warning": warning,
    }
