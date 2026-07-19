"""Modulo CANONICO Balance v5 — Equilibrio vs Squilibrio.

Consolidamento finale di:
- A) Math canonico da research_candidates (formule identiche)
- B) Logica legacy completa da cecchino_balance_analysis (v4)
- C) Builder pubblico v5 con 4 pilastri (F36, Dominanza, Credibilità X, Gap)

Version string: cecchino_balance_v5_v2

Questo è l'unico modulo da usare per le analisi di Equilibrio vs Squilibrio.
Non chiamare i vecchi moduli preview/research_candidates per evitare duplicazioni.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)

# ============================================================================
# VERSIONI
# ============================================================================

VERSION = "cecchino_balance_v5_v2"
"""Versione ufficiale Balance v5."""

LEGACY_VERSION = "cecchino_balance_analysis_v4"
"""Versione legacy per compatibilità con codice esistente."""

PILLAR_ORDER = ["f36", "dominance", "draw_credibility", "gap_coherence"]
"""Ordine canonico dei 4 pilastri."""


# ============================================================================
# SEZIONE A) CANONICAL MATH (da research_candidates)
# ============================================================================
# Formule identiche a quelle già usate in cecchino_draw_credibility_dataset.
# Manteniamo gli alias per compatibilità dataset (*_candidate).
#
# Consumer di queste funzioni:
# - Dataset: conviction_index_candidate, gap_coherence_index_candidate
# - Signals: compute_dominance_pp (formula reusata per dominanza)
# - KPI/Debug: tutti gli indici research
# ============================================================================


def clamp_index(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp index in range [lo, hi], arrotondato a 2 decimali."""
    return round(max(lo, min(hi, value)), 2)


def classify_conviction(value: float | None) -> str | None:
    """Classifica conviction index in categorie standard."""
    if value is None:
        return None
    if value < 20:
        return "Molto Debole"
    if value < 40:
        return "Debole"
    if value < 60:
        return "Moderata"
    if value < 80:
        return "Forte"
    return "Molto Forte"


def classify_gap_coherence(value: float | None) -> str | None:
    """Classifica gap coherence index in categorie standard."""
    if value is None:
        return None
    if value < 20:
        return "Non Confermato"
    if value < 40:
        return "Debole"
    if value < 60:
        return "Parziale"
    if value < 80:
        return "Confermato"
    return "Fortemente Confermato"


def conviction_index(
    prob_1_norm: float | None,
    prob_x_norm: float | None,
    prob_2_norm: float | None,
) -> float | None:
    """100 * (max - second) / max — indice convinzione del modello.
    
    Formula identica al dataset research.
    Alias: conviction_index_candidate per compatibilità dataset.
    """
    if None in (prob_1_norm, prob_x_norm, prob_2_norm):
        return None
    ordered = sorted([float(prob_1_norm), float(prob_x_norm), float(prob_2_norm)], reverse=True)
    max_prob, second_prob = ordered[0], ordered[1]
    if max_prob <= 0:
        return None
    return clamp_index(100.0 * (max_prob - second_prob) / max_prob)


# Alias per compatibilità dataset
conviction_index_candidate = conviction_index


def probability_gap_1_2_pp(prob_1_norm: float | None, prob_2_norm: float | None) -> float | None:
    """Gap assoluto in punti percentuali tra probabilità 1 e 2."""
    if prob_1_norm is None or prob_2_norm is None:
        return None
    return round(abs(float(prob_1_norm) - float(prob_2_norm)), 2)


def probability_balance_index(prob_1_norm: float | None, prob_2_norm: float | None) -> float | None:
    """Indice equilibrio probabilistico: 100 * (1 - |p1-p2| / (p1+p2))."""
    if prob_1_norm is None or prob_2_norm is None:
        return None
    s = float(prob_1_norm) + float(prob_2_norm)
    if s <= 0:
        return None
    return clamp_index(100.0 * (1.0 - abs(float(prob_1_norm) - float(prob_2_norm)) / s))


def gap_coherence_index(
    f36_score: float | None,
    prob_balance: float | None,
) -> float | None:
    """100 - |f36_score - probability_balance_index| — coerenza gap.
    
    Formula identica al dataset research.
    Alias: gap_coherence_index_candidate per compatibilità dataset.
    """
    if f36_score is None or prob_balance is None:
        return None
    return clamp_index(100.0 - abs(float(f36_score) - float(prob_balance)))


# Alias per compatibilità dataset
gap_coherence_index_candidate = gap_coherence_index


def x_rank_from_probs(
    prob_1_norm: float | None,
    prob_x_norm: float | None,
    prob_2_norm: float | None,
) -> tuple[int | None, bool]:
    """Rank della X tra 1/X/2 e flag tied per parimerito.
    
    Returns:
        (rank, tied): rank 1-3, tied=True se ci sono ex-aequo al primo posto
    """
    if prob_x_norm is None:
        return None, False
    items = [
        ("1", prob_1_norm),
        ("X", prob_x_norm),
        ("2", prob_2_norm),
    ]
    valid = [(k, v) for k, v in items if v is not None]
    if len(valid) < 3:
        return None, False
    ordered = sorted(valid, key=lambda x: float(x[1]), reverse=True)
    max_prob = float(ordered[0][1])
    tied = sum(1 for _, v in ordered if float(v) == max_prob) > 1
    rank = next(i + 1 for i, (k, _) in enumerate(ordered) if k == "X")
    return rank, tied


def dominant_side_to_market_label(best_side: str | None) -> str | None:
    """Converte HOME/DRAW/AWAY o 1/X/2 in formato mercato standard 1/X/2."""
    if best_side is None:
        return None
    s = str(best_side).strip().upper()
    mapping = {
        "HOME": "1",
        "1": "1",
        "DRAW": "X",
        "X": "X",
        "AWAY": "2",
        "2": "2",
    }
    return mapping.get(s)


def research_candidates_from_probs(
    *,
    prob_1: float | None,
    prob_x: float | None,
    prob_2: float | None,
    f36_score: float | None,
) -> dict[str, Any]:
    """Bundle candidati research da probabilità normalizzate (punti percentuali).
    
    Restituisce dict con chiavi *_candidate per compatibilità dataset.
    """
    conviction = conviction_index_candidate(prob_1, prob_x, prob_2)
    gap_pp = probability_gap_1_2_pp(prob_1, prob_2)
    prob_bal = probability_balance_index(prob_1, prob_2)
    gap_coh = gap_coherence_index_candidate(f36_score, prob_bal)
    x_rank, x_tied = x_rank_from_probs(prob_1, prob_x, prob_2)
    return {
        "conviction_index_candidate": conviction,
        "conviction_class_candidate": classify_conviction(conviction),
        "probability_gap_1_2_pp": gap_pp,
        "probability_balance_index": prob_bal,
        "gap_coherence_index_candidate": gap_coh,
        "gap_coherence_class_candidate": classify_gap_coherence(gap_coh),
        "x_rank": x_rank,
        "x_tied_for_top": x_tied,
    }


# ============================================================================
# SEZIONE B) FULL LEGACY BALANCE ANALYSIS (copia esatta da cecchino_balance_analysis.py v4)
# ============================================================================
# Manteniamo TUTTA la logica legacy per compatibilità con:
# - ICM analysis (usa operational, summary, cross_reading)
# - Signals (usa compute_dominance_pp)
# - Dataset (usa conviction_index_candidate già definito sopra)
# - KPI/Debug (usa tutti i campi f36, dominance, draw, etc.)
#
# IMPORTANTE: Non modificare nulla qui, è legacy puro.
# ============================================================================

_SIDE_LABEL_TO_ENUM = {"1": "HOME", "X": "DRAW", "2": "AWAY"}
_SIDE_ENUM_TO_LABEL = {v: k for k, v in _SIDE_LABEL_TO_ENUM.items()}


def _num(value: Any) -> float | None:
    """Helper: converti valore in float, ritorna None se impossibile."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prob_to_percent(prob: float | None, prob_pct: float | None = None) -> float | None:
    """Converte probabilità in punti percentuali (0-100)."""
    if prob_pct is not None:
        return float(prob_pct)
    if prob is None:
        return None
    p = float(prob)
    if p <= 1.0:
        return p * 100.0
    return p


def _side_label_to_enum(label: str) -> str:
    """Converte label 1/X/2 in enum HOME/DRAW/AWAY."""
    return _SIDE_LABEL_TO_ENUM.get(label, label)


def _classify_f36(f36_abs: float, f36_signed: float) -> dict[str, Any]:
    """Classifica F36 abs in categorie e genera note direzionali."""
    if f36_abs <= 0.50:
        score, label, class_key = 100, "Equilibrio forte", "strong_balance"
    elif f36_abs <= 1.00:
        score, label, class_key = 80, "Equilibrio", "balance"
    elif f36_abs <= 1.50:
        score, label, class_key = 60, "Transizione", "transition"
    else:
        score, label, class_key = 40, "Squilibrio", "imbalance"

    if f36_signed > 0:
        direction_note = (
            "Quota 2 più alta della quota 1: il modello tende verso 1."
        )
    elif f36_signed < 0:
        direction_note = (
            "Quota 1 più alta della quota 2: il modello tende verso 2."
        )
    else:
        direction_note = "Quota 1 e quota 2 sono uguali: equilibrio perfetto tra i due lati."

    return {
        "signed": round(f36_signed, 4),
        "abs": round(f36_abs, 4),
        "score": score,
        "label": label,
        "class_key": class_key,
        "direction_note": direction_note,
    }


def compute_dominance_pp(
    prob_1: float | None,
    prob_x: float | None,
    prob_2: float | None,
) -> float | None:
    """Dominanza = prob_max - prob_seconda (punti percentuali).
    
    Formula canonica Equilibrio vs Squilibrio.
    Riusata da Signals e ICM per calcoli dominanza.
    """
    p1 = _prob_to_percent(_num(prob_1))
    px = _prob_to_percent(_num(prob_x))
    p2 = _prob_to_percent(_num(prob_2))
    if None in (p1, px, p2):
        return None
    ordered = sorted([p1, px, p2], reverse=True)
    return round(ordered[0] - ordered[1], 2)


def _dominance_sides(probs_pct: dict[str, float]) -> tuple[str, str, float, float]:
    """Identifica lato dominante e secondo lato da dict probs."""
    ordered = sorted(probs_pct.items(), key=lambda x: x[1], reverse=True)
    best_side, best_prob = ordered[0]
    second_side, second_prob = ordered[1]
    return best_side, second_side, best_prob, second_prob


def _classify_side_probability_gap(p1: float, p2: float) -> dict[str, Any]:
    """Classifica gap tra probabilità 1 e 2."""
    gap = abs(p1 - p2)
    if gap <= 3:
        label, class_key = "1 e 2 molto vicini", "side_balance_extreme"
    elif gap <= 8:
        label, class_key = "1 e 2 vicini", "side_balance"
    elif gap <= 15:
        label, class_key = "leggera distanza 1/2", "side_tendency"
    else:
        label, class_key = "forte distanza 1/2", "side_imbalance"
    return {
        "value": round(gap, 2),
        "label": label,
        "class_key": class_key,
    }


def _build_dominance_context(
    best_side_label: str,
    second_side_label: str,
    best_prob: float,
    second_prob: float,
    dominance_pp: float,
) -> dict[str, Any]:
    """Costruisce contesto dominanza con interpretation e effect_on_balance."""
    best_enum = _side_label_to_enum(best_side_label)
    second_enum = _side_label_to_enum(second_side_label)

    if best_enum == "DRAW":
        direction = "draw_dominance"
        if dominance_pp <= 3:
            label = "X leggermente dominante"
            interpretation = "La X è prima ma con vantaggio minimo: equilibrio aperto."
        elif dominance_pp <= 8:
            label = "X interessante"
            interpretation = "La X è prima con margine moderato: equilibrio rafforzato."
        elif dominance_pp <= 15:
            label = "X forte"
            interpretation = (
                "La X è lo scenario principale del modello: equilibrio confermato dalla X."
            )
        else:
            label = "X molto forte"
            interpretation = "Il modello vede una forte propensione al pareggio."
        effect = "reinforces_balance"
    elif best_enum == "HOME":
        direction = "home_dominance"
        label, interpretation, effect = _lateral_dominance_context(dominance_pp, "1")
    else:
        direction = "away_dominance"
        label, interpretation, effect = _lateral_dominance_context(dominance_pp, "2")

    return {
        "best_side": best_enum,
        "best_side_label": best_side_label,
        "best_probability": round(best_prob, 2),
        "second_side": second_enum,
        "second_side_label": second_side_label,
        "second_probability": round(second_prob, 2),
        "dominance_value": round(dominance_pp, 2),
        "dominance_direction": direction,
        "label": label,
        "interpretation": interpretation,
        "effect_on_balance": effect,
    }


def _lateral_dominance_context(
    dominance_pp: float,
    side_label: str,
) -> tuple[str, str, str]:
    """Genera label, interpretation, effect per dominanza laterale (1 o 2)."""
    if dominance_pp <= 3:
        return (
            "Dominanza laterale minima",
            "Il modello non mostra una direzione netta.",
            "neutral",
        )
    if dominance_pp <= 8:
        return (
            "Leggera tendenza laterale",
            (
                "Il modello inizia a preferire "
                f"{side_label}, ma senza rottura forte dell'equilibrio."
            ),
            "weakens_balance",
        )
    if dominance_pp <= 15:
        return (
            "Tendenza laterale",
            f"La Dominanza spinge verso {side_label}.",
            "weakens_balance",
        )
    if dominance_pp <= 25:
        return (
            "Squilibrio laterale",
            f"Il modello mostra una direzione forte verso {side_label}.",
            "confirms_imbalance",
        )
    return (
        "Squilibrio laterale forte",
        f"Il modello è fortemente orientato verso {side_label}.",
        "confirms_imbalance",
    )


def _classify_draw(quota_x: float) -> dict[str, Any]:
    """Classifica credibilità X da quota Cecchino."""
    if quota_x <= 3.20:
        label, class_key = "Pareggio forte", "strong_draw"
    elif quota_x <= 3.60:
        label, class_key = "Pareggio possibile", "possible_draw"
    elif quota_x <= 4.20:
        label, class_key = "Pareggio debole", "weak_draw"
    else:
        label, class_key = "Pareggio poco probabile", "unlikely_draw"

    return {
        "quota_x": round(quota_x, 2),
        "label": label,
        "class_key": class_key,
    }


def _cross_reading(
    f36_abs: float,
    dominance_pp: float,
    best_side_enum: str,
) -> dict[str, str]:
    """Cross reading tra F36 e dominanza."""
    f36_low = f36_abs <= 1.00
    f36_mid = 1.00 < f36_abs <= 1.50
    f36_high = f36_abs > 1.50
    dom_low = dominance_pp <= 5
    dom_mid = 5 < dominance_pp <= 10
    dom_high = dominance_pp > 10

    if f36_low and dom_low:
        return {
            "label": "X / Under molto interessanti",
            "description": (
                "Il modello vede equilibrio reale tra 1 e 2 "
                "e non mostra una dominanza netta."
            ),
        }
    if f36_low and dom_mid:
        if best_side_enum == "DRAW":
            return {
                "label": "X possibile ma attenzione",
                "description": (
                    "Il match è equilibrato tra 1 e 2; la X è in crescita nel modello."
                ),
            }
        return {
            "label": "X possibile ma attenzione",
            "description": (
                "Il match è equilibrato tra 1 e 2, "
                "ma il modello inizia a mostrare una leggera preferenza laterale."
            ),
        }
    if f36_low and dom_high:
        if best_side_enum == "DRAW":
            return {
                "label": "X forte / equilibrio rafforzato",
                "description": (
                    "Le quote 1 e 2 sono vicine e la X domina le probabilità: "
                    "equilibrio rafforzato dal pareggio."
                ),
            }
        return {
            "label": "Falso equilibrio",
            "description": (
                "Le quote 1 e 2 sono vicine, ma la distribuzione delle "
                "probabilità indica una dominanza laterale più marcata."
            ),
        }
    if f36_high and dom_low:
        return {
            "label": "Partita anomala",
            "description": (
                "La distanza tra quota 1 e quota 2 suggerisce squilibrio, "
                "ma la dominanza del modello resta bassa."
            ),
        }
    if f36_high and dom_high:
        if best_side_enum == "DRAW":
            return {
                "label": "Squilibrio quote con X dominante",
                "description": (
                    "F36 alto ma la X domina le probabilità: segnali misti da leggere con cautela."
                ),
            }
        return {
            "label": "Squilibrio confermato",
            "description": (
                "La distanza tra quota 1 e quota 2 e la dominanza laterale "
                "confermano una direzione netta."
            ),
        }
    if f36_mid:
        if best_side_enum == "DRAW":
            return {
                "label": "Zona di transizione con X in testa",
                "description": (
                    "La partita non è perfettamente equilibrata tra 1 e 2, "
                    "ma la X è forte nel modello."
                ),
            }
        return {
            "label": "Zona di transizione",
            "description": (
                "La partita non è né pienamente equilibrata né chiaramente squilibrata."
            ),
        }
    return {
        "label": "Zona di transizione",
        "description": (
            "La partita non è né pienamente equilibrata né chiaramente squilibrata."
        ),
    }


def _operational_reading(
    f36_abs: float,
    dominance_pp: float,
    quota_x: float,
    best_side_enum: str,
    effect_on_balance: str,
) -> dict[str, Any]:
    """Lettura operativa combinata F36 + dominanza + X."""
    def _result(
        rule_id: int,
        label: str,
        detail: str,
        class_key: str,
        severity: str,
    ) -> dict[str, Any]:
        return {
            "label": label,
            "detail": detail,
            "class_key": class_key,
            "severity": severity,
            "rule_id": rule_id,
        }

    if best_side_enum == "DRAW":
        if f36_abs < 0.75 and quota_x <= 3.50 and dominance_pp > 10:
            return _result(
                1,
                "X molto forte",
                (
                    "La Dominanza della X rafforza nettamente l'equilibrio: "
                    "tipica partita da X / Under."
                ),
                "very_strong_draw_balance",
                "positive",
            )
        if f36_abs < 0.75 and quota_x <= 3.50 and 5 < dominance_pp <= 10:
            return _result(
                2,
                "X molto interessante",
                "La X rafforza l'equilibrio tra 1 e 2.",
                "strong_draw_balance",
                "positive",
            )
        if 0.75 <= f36_abs <= 1.50 and quota_x <= 3.50:
            return _result(
                3,
                "X interessante",
                (
                    "La partita non è perfettamente equilibrata tra 1 e 2, "
                    "ma la X è forte nel modello."
                ),
                "interesting_draw",
                "positive",
            )
        if quota_x > 3.50 and quota_x <= 4.20:
            return _result(
                4,
                "X possibile",
                (
                    "La X domina il modello, ma la quota Cecchino non è "
                    "abbastanza bassa da considerarla forte."
                ),
                "possible_draw",
                "warning",
            )
        if quota_x > 4.20:
            return _result(
                5,
                "X prima ma poco affidabile",
                (
                    "La X è prima per probabilità relativa, "
                    "ma la quota X Cecchino resta alta."
                ),
                "draw_top_but_weak",
                "warning",
            )
        if f36_abs < 0.75 and dominance_pp <= 5 and quota_x <= 3.50:
            return _result(
                6,
                "X forte",
                "Equilibrio reale tra 1 e 2, X/Under interessante.",
                "strong_draw_balance",
                "positive",
            )

    if (
        f36_abs < 0.75
        and dominance_pp > 10
        and best_side_enum in ("HOME", "AWAY")
    ):
        side = "1" if best_side_enum == "HOME" else "2"
        return _result(
            7,
            "Falso equilibrio",
            (
                "Le quote 1 e 2 sono vicine, ma il modello è più orientato "
                f"verso {side}."
            ),
            "false_balance",
            "negative",
        )

    if f36_abs < 0.75 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            8,
            "X possibile",
            "Equilibrio tra 1 e 2 ancora pulito.",
            "possible_draw_light_trend",
            "positive",
        )
    if f36_abs < 0.75 and dominance_pp <= 5 and 3.50 < quota_x <= 4.20:
        return _result(
            9,
            "X possibile",
            "Under interessante",
            "possible_draw_under",
            "positive",
        )
    if f36_abs < 0.75 and dominance_pp <= 5 and quota_x > 4.20:
        return _result(
            10,
            "Equilibrio apparente",
            "X poco probabile",
            "apparent_balance_low_draw",
            "warning",
        )
    if f36_abs < 0.75 and 5 < dominance_pp <= 10 and quota_x <= 3.50:
        return _result(
            11,
            "X possibile",
            "Presente lieve tendenza verso un lato",
            "possible_draw_light_trend",
            "positive",
        )
    if f36_abs < 0.75 and 5 < dominance_pp <= 10 and quota_x > 3.50:
        return _result(
            12,
            "Equilibrio con tendenza",
            "Attenzione a direzione 1 o 2",
            "balance_with_trend",
            "warning",
        )
    if 0.75 <= f36_abs <= 1.50 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            13,
            "Equilibrata ma meno pulita",
            "X ancora possibile, ma il quadro è meno netto.",
            "balanced_less_clean",
            "warning",
        )
    if 0.75 <= f36_abs <= 1.50 and 5 < dominance_pp <= 10 and quota_x <= 3.50:
        return _result(
            14,
            "Zona grigia",
            "La partita ha segnali contrastanti.",
            "grey_zone",
            "warning",
        )
    if 0.75 <= f36_abs <= 1.50 and dominance_pp > 10:
        if effect_on_balance == "confirms_imbalance":
            return _result(
                15,
                "Tendenza verso 1 o 2",
                "La partita non è più da leggere come equilibrio puro.",
                "trend_to_side",
                "neutral",
            )
        return _result(
            16,
            "Zona grigia",
            "La partita ha segnali contrastanti.",
            "grey_zone",
            "warning",
        )
    if f36_abs > 1.50 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            17,
            "Partita anomala",
            (
                "Squilibrio tra 1 e 2 ma pareggio ancora basso: "
                "da verificare con attenzione."
            ),
            "anomaly",
            "warning",
        )
    if f36_abs > 1.50 and 5 < dominance_pp <= 10:
        return _result(
            18,
            "Squilibrio moderato",
            "La partita mostra una direzione, ma senza dominanza estrema.",
            "moderate_imbalance",
            "neutral",
        )
    if f36_abs > 1.50 and dominance_pp > 10:
        if best_side_enum == "DRAW":
            return _result(
                19,
                "Squilibrio quote con X dominante",
                "F36 alto ma la X domina le probabilità: segnali misti.",
                "anomaly_draw_dominant",
                "warning",
            )
        return _result(
            20,
            "Squilibrio confermato",
            "F36 e Dominanza spingono nella stessa direzione.",
            "confirmed_imbalance",
            "positive",
        )

    return _result(
        0,
        "Non classificata",
        "Dati insufficienti o combinazione non prevista.",
        "unknown",
        "neutral",
    )


def _favorite_direction(
    f36_abs: float,
    dominance_pp: float,
    best_side_label: str,
    best_side_enum: str,
) -> str:
    """Determina direzione favorita del modello."""
    if best_side_enum == "DRAW":
        if f36_abs < 0.75 and dominance_pp > 5:
            return "Tendenza verso X (equilibrio rafforzato)"
        return "Tendenza verso X"
    if f36_abs < 0.75 and dominance_pp <= 5:
        return "Nessuna direzione netta"
    if best_side_label == "1":
        return "Tendenza verso 1"
    if best_side_label == "X":
        return "Tendenza verso X"
    return "Tendenza verso 2"


def _build_summary(
    operational: dict[str, Any],
    cross_reading: dict[str, str],
    favorite_direction: str,
    best_side_enum: str,
) -> dict[str, Any]:
    """Costruisce summary da operational reading."""
    op_class = operational.get("class_key", "")
    is_x_dominance = best_side_enum == "DRAW"
    is_draw_under = op_class in {
        "very_strong_draw_balance",
        "strong_draw_balance",
        "interesting_draw",
        "very_strong_draw_under",
        "possible_draw_under",
        "possible_draw_light_trend",
    }
    is_false_balance = op_class == "false_balance" and not is_x_dominance
    is_confirmed_imbalance = op_class == "confirmed_imbalance"

    short_advice_map = {
        "very_strong_draw_balance": "Tipica partita da X / Under.",
        "strong_draw_balance": "X forte: equilibrio rafforzato dal pareggio.",
        "interesting_draw": "X interessante in zona di transizione.",
        "possible_draw": "X possibile ma quota non ottimale.",
        "draw_top_but_weak": "X prima ma quota alta: cautela.",
        "very_strong_draw_under": "Tipica partita da X / Under.",
        "possible_draw_under": "X e Under da valutare.",
        "possible_draw_light_trend": "X possibile con lieve tendenza laterale.",
        "false_balance": "Attenzione: equilibrio apparente nelle quote.",
        "confirmed_imbalance": "Partita orientata verso 1 o 2.",
        "anomaly": "Verificare X/Under solo se confermati dagli altri indicatori.",
        "grey_zone": "Segnali contrastanti: procedere con cautela.",
    }
    short_advice = short_advice_map.get(
        op_class,
        operational.get("detail", ""),
    )

    return {
        "main_label": operational.get("label"),
        "short_advice": short_advice,
        "favorite_direction": favorite_direction,
        "is_draw_under_candidate": is_draw_under,
        "is_false_balance": is_false_balance,
        "is_confirmed_imbalance": is_confirmed_imbalance,
        "is_x_dominance": is_x_dominance,
    }


def build_cecchino_balance_analysis(
    *,
    quota_cecchino_1: float | None,
    quota_cecchino_x: float | None,
    quota_cecchino_2: float | None,
    prob_cecchino_1: float | None,
    prob_cecchino_x: float | None,
    prob_cecchino_2: float | None,
) -> dict[str, Any]:
    """Costruisce analisi Balance legacy completa (v4).
    
    Consumer: ICM, Signals (compute_dominance_pp), dataset.
    """
    q1 = _num(quota_cecchino_1)
    qx = _num(quota_cecchino_x)
    q2 = _num(quota_cecchino_2)
    p1 = _prob_to_percent(_num(prob_cecchino_1))
    px = _prob_to_percent(_num(prob_cecchino_x))
    p2 = _prob_to_percent(_num(prob_cecchino_2))

    if None in (q1, qx, q2, p1, px, p2):
        return {
            "version": LEGACY_VERSION,
            "status": "insufficient_data",
            "warnings": ["missing_cecchino_1x2_inputs"],
        }

    f36_signed = q2 - q1
    f36_abs = abs(f36_signed)
    probs_pct = {"1": p1, "X": px, "2": p2}
    best_label, second_label, best_prob, second_prob = _dominance_sides(probs_pct)
    dominance_pp = compute_dominance_pp(prob_cecchino_1, prob_cecchino_x, prob_cecchino_2)
    assert dominance_pp is not None
    best_enum = _side_label_to_enum(best_label)
    second_enum = _side_label_to_enum(second_label)

    f36 = _classify_f36(f36_abs, f36_signed)
    side_gap = _classify_side_probability_gap(p1, p2)
    dominance_context = _build_dominance_context(
        best_label,
        second_label,
        best_prob,
        second_prob,
        dominance_pp,
    )
    dominance = {
        "value": round(dominance_pp, 2),
        "best_side": best_enum,
        "best_side_label": best_label,
        "best_probability": round(best_prob, 2),
        "second_side": second_enum,
        "second_side_label": second_label,
        "second_probability": round(second_prob, 2),
    }
    draw = _classify_draw(qx)
    cross = _cross_reading(f36_abs, dominance_pp, best_enum)
    operational = _operational_reading(
        f36_abs,
        dominance_pp,
        qx,
        best_enum,
        dominance_context["effect_on_balance"],
    )
    favorite = _favorite_direction(f36_abs, dominance_pp, best_label, best_enum)
    summary = _build_summary(operational, cross, favorite, best_enum)

    payload: dict[str, Any] = {
        "version": LEGACY_VERSION,
        "status": "available",
        "inputs": {
            "quota_1": round(q1, 2),
            "quota_x": round(qx, 2),
            "quota_2": round(q2, 2),
            "prob_1": round(p1, 2),
            "prob_x": round(px, 2),
            "prob_2": round(p2, 2),
        },
        "f36": f36,
        "side_probability_gap": side_gap,
        "dominance": dominance,
        "dominance_context": dominance_context,
        "draw": draw,
        "cross_reading": cross,
        "operational": {
            "label": operational["label"],
            "detail": operational["detail"],
            "class_key": operational["class_key"],
            "severity": operational["severity"],
        },
        "summary": summary,
        "technical": {
            "f36_formula": "F36_signed = quota_2 - quota_1; F36_abs = abs(F36_signed)",
            "dominance_formula": "dominanza = prob_max - prob_seconda (in punti percentuali)",
            "side_gap_formula": "gap_1_2_probability = abs(prob_1 - prob_2)",
            "rule_id": operational.get("rule_id"),
            "operational_class_key": operational.get("class_key"),
            "effect_on_balance": dominance_context.get("effect_on_balance"),
            "dominance_direction": dominance_context.get("dominance_direction"),
            "x_dominance_note": (
                "Se domina X, la Dominanza rafforza equilibrio e lettura X/Under."
            ),
            "lateral_dominance_note": (
                "Se domina 1 o 2, la Dominanza indebolisce equilibrio o conferma squilibrio."
            ),
            "legend_version": "balance_operational_legend_v4",
        },
        "warnings": [],
    }
    return payload


def build_balance_analysis_from_final(
    final: dict[str, Any],
) -> dict[str, Any]:
    """Builder legacy da cecchino_final dict."""
    if not isinstance(final, dict) or final.get("status") != "available":
        return {
            "version": LEGACY_VERSION,
            "status": "insufficient_data",
            "warnings": ["missing_cecchino_1x2_inputs"],
        }

    return build_cecchino_balance_analysis(
        quota_cecchino_1=_num(final.get("quota_1")),
        quota_cecchino_x=_num(final.get("quota_x")),
        quota_cecchino_2=_num(final.get("quota_2")),
        prob_cecchino_1=_num(final.get("prob_1_pct")) or _num(final.get("prob_1")),
        prob_cecchino_x=_num(final.get("prob_x_pct")) or _num(final.get("prob_x")),
        prob_cecchino_2=_num(final.get("prob_2_pct")) or _num(final.get("prob_2")),
    )


# Alias per compatibilità legacy
build_legacy_balance_analysis = build_cecchino_balance_analysis


# ============================================================================
# SEZIONE C) PUBLIC BALANCE V5 BUILDER
# ============================================================================
# Questo è il nuovo builder pubblico v5 che NON richiede balance_analysis come input.
# Estrae quote/probs da cecchino_final e computa i 4 pilastri direttamente.
#
# Output shape con 4 pilastri:
# - F36 (official): geometria quote laterali, lettura strutturale
# - Dominanza (official): conviction formula, no research badge
# - Credibilità X (descriptive_official): prob_x_norm, no Book nel pilastro
# - Gap (official): coherence formule, no research badge
#
# Plus: market_deviation (separato), structural_summary, identity mismatch handling.
# ============================================================================


def _component(
    key: str,
    label: str,
    value: Any,
    *,
    unit: str = "text",
    status: str = "available",
) -> dict[str, Any]:
    """Helper per creare componente pilastro."""
    if value is None and status == "available":
        status = "missing"
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
    }


def _kpi_row_map(kpi_panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Mappa KPI rows per market_key."""
    if not kpi_panel or not isinstance(kpi_panel, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in kpi_panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        mk = str(row.get("market_key") or "").strip().upper()
        if mk:
            out[mk] = row
    return out


def _goal_odds_from_markets(goal_markets: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Estrae quote Under/Over 2.5 dal blocco goal_markets (fratello di final)."""
    if not goal_markets or not isinstance(goal_markets, dict):
        return None, None
    under = None
    over = None
    u = goal_markets.get(SEL_UNDER_2_5) or goal_markets.get("under_2_5") or {}
    o = goal_markets.get(SEL_OVER_2_5) or goal_markets.get("over_2_5") or {}
    if isinstance(u, dict):
        under = _num(u.get("final_odd") or u.get("odd"))
    if isinstance(o, dict):
        over = _num(o.get("final_odd") or o.get("odd"))
    return under, over


def _goal_odds_from_final(final: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Fallback legacy: goal_markets annidati in final (non percorso principale)."""
    if not final or not isinstance(final, dict):
        return None, None
    nested = final.get("goal_markets")
    if isinstance(nested, dict):
        return _goal_odds_from_markets(nested)
    return None, None


def _goal_probs_from_odds(under: float | None, over: float | None) -> tuple[float | None, float | None]:
    """Calcola probabilità implicite da quote goal (solo display)."""
    if under is None or under <= 1:
        up = None
    else:
        up = round(100.0 / under, 2)
    if over is None or over <= 1:
        op = None
    else:
        op = round(100.0 / over, 2)
    return up, op


def _normalize_3way_probs(p1: float | None, px: float | None, p2: float | None) -> tuple[float | None, float | None, float | None]:
    """Normalizza probabilità 1X2 a somma 100 per market deviation."""
    if None in (p1, px, p2):
        return None, None, None
    total = float(p1) + float(px) + float(p2)
    if total <= 0:
        return None, None, None
    return (
        round(100.0 * float(p1) / total, 2),
        round(100.0 * float(px) / total, 2),
        round(100.0 * float(p2) / total, 2),
    )


def _normalize_2way_probs(pu: float | None, po: float | None) -> tuple[float | None, float | None]:
    """Normalizza probabilità Under/Over a somma 100 per market deviation."""
    if pu is None or po is None:
        return None, None
    total = float(pu) + float(po)
    if total <= 0:
        return None, None
    return (
        round(100.0 * float(pu) / total, 2),
        round(100.0 * float(po) / total, 2),
    )


def _f36_side_from_signed(signed: Any) -> str | None:
    """Determina direzione (1/2/None) da F36 signed.
    
    Convenzione produttiva: signed > 0 → struttura verso 1; < 0 → verso 2.
    """
    s = _num(signed)
    if s is None or s == 0:
        return None
    return "1" if s > 0 else "2"


def _f36_structural_reading_v5(f36: dict[str, Any]) -> str:
    """Lettura strutturale F36 per pilastro v5 (nessuna predizione, solo geometria)."""
    class_key = str(f36.get("class_key") or "")
    side = _f36_side_from_signed(f36.get("signed"))

    if class_key == "imbalance":
        if side:
            return (
                f"La distanza tra le quote laterali descrive una struttura "
                f"sbilanciata verso il lato {side}."
            )
        return "La distanza tra le quote laterali descrive una struttura sbilanciata."

    if class_key == "transition":
        if side:
            return (
                "Le quote laterali mostrano una distanza intermedia, "
                f"con inclinazione strutturale verso il lato {side}."
            )
        return "Le quote laterali mostrano una distanza intermedia tra equilibrio e squilibrio."

    # strong_balance / balance
    if side:
        return (
            "Le quote laterali risultano relativamente vicine, "
            f"con una lieve inclinazione verso il lato {side}."
        )
    return "Le quote laterali risultano vicine e la struttura della partita appare equilibrata."


def _pillar_f36_v5(
    quota_1: float | None,
    quota_2: float | None,
    f36_abs: float | None,
    f36_signed: float | None,
    f36_score: float | None,
    f36_label: str | None,
    f36_class_key: str | None = None,
) -> dict[str, Any]:
    """Pilastro F36 v5 (official)."""
    if None in (quota_1, quota_2, f36_abs, f36_signed, f36_score, f36_label):
        return {
            "key": "f36",
            "title": "Geometria della partita",
            "question": "Quanto è equilibrata la struttura della partita?",
            "status": "unavailable",
            "index": None,
            "class_label": None,
            "reading": "Dati F36 non disponibili.",
            "direction": None,
            "components": [],
            "warnings": ["f36_unavailable"],
        }

    direction = _f36_side_from_signed(f36_signed)
    reading = _f36_structural_reading_v5({
        "class_key": f36_class_key,
        "signed": f36_signed,
    })

    return {
        "key": "f36",
        "title": "Geometria della partita",
        "question": "Quanto è equilibrata la struttura della partita?",
        "status": "official",
        "index": f36_score,
        "class_label": f36_label,
        "reading": reading,
        "direction": direction,
        "components": [
            _component("quota_1", "Quota 1 Cecchino", quota_1, unit="quota"),
            _component("quota_2", "Quota 2 Cecchino", quota_2, unit="quota"),
            _component("f36_diff", "Differenza F36 |q1−q2|", f36_abs, unit="index"),
            _component("f36_class", "Classe", f36_label, unit="text"),
        ],
        "warnings": [],
    }


def _dominance_reading_v5(market_label: str | None, conviction: float | None, class_label: str | None) -> str:
    """Lettura dominanza pilastro v5 (NO research badge, official)."""
    side = market_label or "?"
    if conviction is None:
        return f"Il modello indica come scenario principale il segno {side}."
    intensity = (class_label or "moderata").lower()
    return f"Il modello mostra una preferenza {intensity} per il segno {side}."


def _pillar_dominance_v5(
    prob_1: float | None,
    prob_x: float | None,
    prob_2: float | None,
    best_side: str | None,
    dominance_pp: float | None,
) -> dict[str, Any]:
    """Pilastro Dominanza v5 (official, formula conviction senza badge research)."""
    market = dominant_side_to_market_label(best_side)
    conviction = conviction_index(prob_1, prob_x, prob_2)
    conv_class = classify_conviction(conviction)

    if conviction is not None:
        status = "official"
        index = conviction
        class_label = conv_class
    else:
        status = "unavailable"
        index = None
        class_label = None

    components = [
        _component("prob_1", "Probabilità 1", prob_1, unit="pct"),
        _component("prob_x", "Probabilità X", prob_x, unit="pct"),
        _component("prob_2", "Probabilità 2", prob_2, unit="pct"),
        _component("dominant_sign", "Segno dominante", market, unit="text"),
        _component("dominance_pp", "Dominanza pp", dominance_pp, unit="pp"),
        _component("conviction_index", "Indice convinzione", conviction, unit="index"),
    ]

    return {
        "key": "dominance",
        "title": "Convinzione del modello",
        "question": "Quanto il modello è convinto dello scenario principale?",
        "status": status,
        "index": index,
        "class_label": class_label,
        "reading": _dominance_reading_v5(market, conviction, conv_class),
        "direction": market,
        "components": components,
        "warnings": [] if status == "official" else ["dominance_unavailable"],
    }


def _pillar_draw_credibility_v5(
    prob_x: float | None,
    quota_x: float | None,
    x_rank: int | None,
    under_odd: float | None,
    over_odd: float | None,
    under_pct: float | None,
    over_pct: float | None,
    f36_label: str | None,
    dominant_sign: str | None,
) -> dict[str, Any]:
    """Pilastro Credibilità X v5 (descriptive_official).
    
    Index = prob_x normalizzata (0-100, stesso valore degli inputs).
    Class da quota X thresholds (_classify_draw).
    NO Book nel pilastro.
    NO frasi betting.
    Status: descriptive_official.
    Informational note: "Indice descrittivo interno, non ancora probabilità calibrata sull'esito reale."
    """
    if prob_x is None or quota_x is None:
        return {
            "key": "draw_credibility",
            "title": "Credibilità della X",
            "question": "Quanto il pareggio è credibile secondo il modello Cecchino?",
            "status": "unavailable",
            "index": None,
            "class_label": None,
            "reading": "Dati X non disponibili.",
            "direction": None,
            "components": [],
            "warnings": ["draw_credibility_unavailable"],
        }

    # Index = prob_x_norm come percentuale (già normalizzata negli inputs)
    index = prob_x
    draw_class_dict = _classify_draw(quota_x)
    class_label = draw_class_dict.get("label")

    # Normalizza Under/Over se disponibili entrambi
    if under_pct is not None and over_pct is not None:
        under_norm, over_norm = _normalize_2way_probs(under_pct, over_pct)
    else:
        under_norm, over_norm = under_pct, over_pct

    # Reading
    reading_parts = [
        f"La probabilità della X è {prob_x:.2f}%.",
    ]
    if x_rank:
        ordinal = {1: "prima", 2: "seconda", 3: "terza"}.get(x_rank, f"{x_rank}°")
        reading_parts.append(f"La X è {ordinal} per probabilità nel modello.")
    if dominant_sign and dominant_sign != "X":
        reading_parts.append(f"Il segno dominante è {dominant_sign}.")
    if under_norm is not None and over_norm is not None:
        reading_parts.append(f"Under 2.5: {under_norm:.2f}%, Over 2.5: {over_norm:.2f}%.")

    reading = " ".join(reading_parts)

    components = [
        _component("prob_x", "Probabilità X Cecchino", prob_x, unit="pct"),
        _component("quota_x", "Quota X Cecchino", quota_x, unit="quota"),
        _component("x_rank", "X rank", x_rank, unit="text"),
        _component("f36_class", "Classe F36", f36_label, unit="text"),
        _component("dominant_sign", "Segno dominante", dominant_sign, unit="text"),
    ]
    if under_odd is not None:
        components.append(_component("quota_under_2_5", "Under 2.5 Cecchino", under_odd, unit="quota"))
    if over_odd is not None:
        components.append(_component("quota_over_2_5", "Over 2.5 Cecchino", over_odd, unit="quota"))

    # Aggiungi Under/Over solo se disponibili (normalizzati)
    if under_norm is not None:
        components.append(_component("prob_under_2_5_norm", "Prob. Under 2.5 (norm)", under_norm, unit="pct"))
    if over_norm is not None:
        components.append(_component("prob_over_2_5_norm", "Prob. Over 2.5 (norm)", over_norm, unit="pct"))

    return {
        "key": "draw_credibility",
        "title": "Credibilità della X",
        "question": "Quanto il pareggio è credibile secondo il modello Cecchino?",
        "status": "descriptive_official",
        "index": index,
        "class_label": class_label,
        "reading": reading,
        "direction": None,
        "components": components,
        "warnings": [],
        "informational_note": "Indice descrittivo interno, non ancora probabilità calibrata sull'esito reale.",
    }


def _format_gap_pp_it(gap_pp: float | None) -> str:
    """Formatta gap pp con virgola italiana (solo presentazione)."""
    if gap_pp is None:
        return "n/d"
    text = f"{float(gap_pp):.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _gap_coherence_is_low(class_label: str | None) -> bool:
    """Controlla se gap coherence è basso/non confermato."""
    if not class_label:
        return False
    low = class_label.lower()
    return low in ("non confermato", "debole") or "non confermato" in low


def _gap_reading_v5(
    gap_coh: float | None,
    gap_class: str | None,
    gap_pp: float | None,
    f36_class_key: str | None,
) -> str:
    """Lettura gap coherence per pilastro v5 (official)."""
    if gap_coh is None:
        return (
            "La coerenza tra probabilità 1/2 e geometria F36 non è disponibile. "
            "I componenti disponibili sono mostrati senza indice aggregato."
        )
    if _gap_coherence_is_low(gap_class):
        return "Il gap probabilistico non conferma pienamente la geometria descritta da F36."

    gap_txt = _format_gap_pp_it(gap_pp)
    f36_key = str(f36_class_key or "")
    if f36_key == "imbalance":
        return f"Il gap probabilistico di {gap_txt} pp conferma lo squilibrio rilevato da F36."
    if f36_key in ("strong_balance", "balance"):
        return (
            f"Il gap probabilistico di {gap_txt} pp è coerente con la struttura "
            "equilibrata rilevata da F36."
        )
    if f36_key == "transition":
        return (
            f"Il gap probabilistico di {gap_txt} pp è coerente con la struttura "
            "di transizione rilevata da F36."
        )
    return f"Il gap probabilistico di {gap_txt} pp è coerente con la geometria descritta da F36."


def _pillar_gap_v5(
    prob_1: float | None,
    prob_2: float | None,
    gap_pp: float | None,
    f36_score: float | None,
    f36_class_key: str | None,
) -> dict[str, Any]:
    """Pilastro Gap v5 (official, formule identiche, no research badge)."""
    prob_bal = probability_balance_index(prob_1, prob_2)
    gap_coh = gap_coherence_index(f36_score, prob_bal)
    gap_class = classify_gap_coherence(gap_coh)

    if gap_coh is not None:
        status = "official"
        index = gap_coh
        class_label = gap_class
    else:
        status = "unavailable"
        index = None
        class_label = None

    return {
        "key": "gap_coherence",
        "title": "Coerenza matematica 1/2",
        "question": "Le probabilità confermano la geometria descritta da F36?",
        "status": status,
        "index": index,
        "class_label": class_label,
        "reading": _gap_reading_v5(gap_coh, gap_class, gap_pp, f36_class_key),
        "direction": None,
        "components": [
            _component("prob_1", "Probabilità 1", prob_1, unit="pct"),
            _component("prob_2", "Probabilità 2", prob_2, unit="pct"),
            _component("probability_gap_1_2_pp", "Gap 1/2", gap_pp, unit="pp"),
            _component("f36_score", "F36", f36_score, unit="index"),
            _component("gap_coherence_index", "Indice coerenza gap", gap_coh, unit="index"),
        ],
        "warnings": [] if status == "official" else ["gap_unavailable"],
    }


def _market_pair_v5(
    key: str,
    label: str,
    *,
    quota_cecchino: float | None,
    quota_book: float | None,
    prob_cecchino_norm: float | None = None,
    prob_book_norm: float | None = None,
) -> dict[str, Any]:
    """Market pair con signed/abs diff e label direzione."""
    signed_diff = None
    abs_diff = None
    direction_label = None

    if prob_cecchino_norm is not None and prob_book_norm is not None:
        signed_diff = round(float(prob_cecchino_norm) - float(prob_book_norm), 2)
        abs_diff = abs(signed_diff)
        if abs_diff < 0.5:
            direction_label = "Probabilità allineate"
        elif signed_diff > 0:
            direction_label = "Probabilità Cecchino maggiore"
        else:
            direction_label = "Probabilità Book maggiore"

    return {
        "key": key,
        "label": label,
        "quota_cecchino": quota_cecchino,
        "quota_book": quota_book,
        "prob_cecchino_norm": prob_cecchino_norm,
        "prob_book_norm": prob_book_norm,
        "signed_diff": signed_diff,
        "abs_diff": abs_diff,
        "direction_label": direction_label,
    }


def _build_market_deviation_v5(
    cecchino_1x2: tuple[float | None, float | None, float | None],
    book_1x2: tuple[float | None, float | None, float | None],
    cecchino_ou: tuple[float | None, float | None],
    book_ou: tuple[float | None, float | None],
    quota_1: float | None,
    quota_x: float | None,
    quota_2: float | None,
    quota_under: float | None,
    quota_over: float | None,
    quota_book_1: float | None,
    quota_book_x: float | None,
    quota_book_2: float | None,
    quota_book_under: float | None,
    quota_book_over: float | None,
) -> dict[str, Any]:
    """Market deviation v5: Cecchino 1X2 già normalizzato; Book 1X2 e O/U normalizzati qui."""
    # Cecchino 1X2: già normalizzato dal builder — non rinormalizzare
    p1_cn, px_cn, p2_cn = cecchino_1x2

    # Book 1X2: probabilità implicite grezze → normalizzare
    p1_b, px_b, p2_b = book_1x2
    p1_bn, px_bn, p2_bn = _normalize_3way_probs(p1_b, px_b, p2_b)

    # Normalize O/U
    pu_c, po_c = cecchino_ou
    pu_cn, po_cn = _normalize_2way_probs(pu_c, po_c)

    pu_b, po_b = book_ou
    pu_bn, po_bn = _normalize_2way_probs(pu_b, po_b)

    pairs = [
        _market_pair_v5(
            "1", "Segno 1",
            quota_cecchino=quota_1,
            quota_book=quota_book_1,
            prob_cecchino_norm=p1_cn,
            prob_book_norm=p1_bn,
        ),
        _market_pair_v5(
            "x", "Segno X",
            quota_cecchino=quota_x,
            quota_book=quota_book_x,
            prob_cecchino_norm=px_cn,
            prob_book_norm=px_bn,
        ),
        _market_pair_v5(
            "2", "Segno 2",
            quota_cecchino=quota_2,
            quota_book=quota_book_2,
            prob_cecchino_norm=p2_cn,
            prob_book_norm=p2_bn,
        ),
        _market_pair_v5(
            "under_2_5", "Under 2.5",
            quota_cecchino=quota_under,
            quota_book=quota_book_under,
            prob_cecchino_norm=pu_cn,
            prob_book_norm=pu_bn,
        ),
        _market_pair_v5(
            "over_2_5", "Over 2.5",
            quota_cecchino=quota_over,
            quota_book=quota_book_over,
            prob_cecchino_norm=po_cn,
            prob_book_norm=po_bn,
        ),
    ]

    has_any_book = any(p.get("quota_book") is not None for p in pairs)

    return {
        "title": "Scostamento dal mercato",
        "subtitle": "Distanza tra Cecchino e Book.",
        "status": "ok" if has_any_book else "unavailable",
        "pairs": pairs,
        "reading": (
            "Lo scostamento descrive la distanza tra Cecchino e mercato. "
            "Non stabilisce quale dei due abbia ragione e non modifica i quattro pilastri."
        ),
        "warnings": [] if has_any_book else ["book_odds_missing"],
    }


def _build_structural_summary_v5(
    f36_label: str | None,
    dominance_label: str | None,
    draw_label: str | None,
    gap_label: str | None,
) -> str:
    """Composizione deterministica da 4 pilastri, no aggregate score, no betting advice."""
    parts = []
    if f36_label:
        parts.append(f"F36: {f36_label}")
    if dominance_label:
        parts.append(f"Dominanza: {dominance_label}")
    if draw_label:
        parts.append(f"Credibilità X: {draw_label}")
    if gap_label:
        parts.append(f"Gap: {gap_label}")

    if not parts:
        return "Dati insufficienti per generare il sommario strutturale."

    summary = ". ".join(parts) + "."
    return summary


def build_cecchino_balance_v5(
    *,
    cecchino_final: dict[str, Any],
    goal_markets: dict[str, Any] | None = None,
    kpi_panel: dict[str, Any] | None = None,
    identity_consistency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builder pubblico Balance v5 — NON richiede balance_analysis come input.

    Estrae quote/probs da cecchino_final, normalizza 1X2 una sola volta per il
    dominio v5, e legge Goal Markets dal blocco fratello (non da final).
    """
    # Identity mismatch → unavailable
    if isinstance(identity_consistency, dict) and identity_consistency.get("status") == "inconsistent":
        warnings_identity = list(identity_consistency.get("warnings") or [])
        return {
            "status": "unavailable",
            "version": VERSION,
            "inputs": {},
            "pillars": {
                "f36": {"status": "unavailable", "warnings": warnings_identity},
                "dominance": {"status": "unavailable", "warnings": warnings_identity},
                "draw_credibility": {"status": "unavailable", "warnings": warnings_identity},
                "gap_coherence": {"status": "unavailable", "warnings": warnings_identity},
            },
            "pillar_order": PILLAR_ORDER,
            "market_deviation": {
                "status": "unavailable",
                "pairs": [],
                "reading": "Sezione non disponibile: identità fixture non allineata.",
                "warnings": warnings_identity,
            },
            "structural_summary": "Analisi non disponibile per mismatch di identità fixture.",
            "warnings": ["fixture_identity_mismatch"] + warnings_identity,
        }

    if not isinstance(cecchino_final, dict) or cecchino_final.get("status") != "available":
        return {
            "status": "unavailable",
            "version": VERSION,
            "inputs": {},
            "pillars": {
                "f36": {"status": "unavailable"},
                "dominance": {"status": "unavailable"},
                "draw_credibility": {"status": "unavailable"},
                "gap_coherence": {"status": "unavailable"},
            },
            "pillar_order": PILLAR_ORDER,
            "market_deviation": {"status": "unavailable", "pairs": [], "warnings": ["cecchino_final_unavailable"]},
            "structural_summary": "Dati cecchino_final non disponibili.",
            "warnings": ["cecchino_final_unavailable"],
        }

    quota_1 = _num(cecchino_final.get("quota_1"))
    quota_x = _num(cecchino_final.get("quota_x"))
    quota_2 = _num(cecchino_final.get("quota_2"))
    prob_1_raw = _prob_to_percent(
        _num(cecchino_final.get("prob_1")),
        _num(cecchino_final.get("prob_1_pct")),
    )
    prob_x_raw = _prob_to_percent(
        _num(cecchino_final.get("prob_x")),
        _num(cecchino_final.get("prob_x_pct")),
    )
    prob_2_raw = _prob_to_percent(
        _num(cecchino_final.get("prob_2")),
        _num(cecchino_final.get("prob_2_pct")),
    )
    prob_1_norm, prob_x_norm, prob_2_norm = _normalize_3way_probs(
        prob_1_raw, prob_x_raw, prob_2_raw
    )

    # Goal markets: percorso principale = argomento esplicito; fallback nested in final
    gm = goal_markets if isinstance(goal_markets, dict) else None
    under_odd, over_odd = _goal_odds_from_markets(gm)
    if under_odd is None and over_odd is None:
        under_odd, over_odd = _goal_odds_from_final(cecchino_final)
    under_pct, over_pct = _goal_probs_from_odds(under_odd, over_odd)

    rows = _kpi_row_map(kpi_panel)
    quota_book_1 = _num(rows.get(SEL_HOME, {}).get("quota_book"))
    quota_book_x = _num(rows.get(SEL_DRAW, {}).get("quota_book"))
    quota_book_2 = _num(rows.get(SEL_AWAY, {}).get("quota_book"))
    quota_book_under = _num(rows.get(SEL_UNDER_2_5, {}).get("quota_book"))
    quota_book_over = _num(rows.get(SEL_OVER_2_5, {}).get("quota_book"))

    def _implied_pct(q: float | None) -> float | None:
        if q is None or q <= 1:
            return None
        return round(100.0 / q, 2)

    prob_book_1 = _implied_pct(quota_book_1)
    prob_book_x = _implied_pct(quota_book_x)
    prob_book_2 = _implied_pct(quota_book_2)
    prob_book_under = _implied_pct(quota_book_under)
    prob_book_over = _implied_pct(quota_book_over)

    if None in (quota_1, quota_2):
        f36_signed = None
        f36_abs = None
        f36_dict: dict[str, Any] = {}
    else:
        f36_signed = quota_2 - quota_1
        f36_abs = abs(f36_signed)
        f36_dict = _classify_f36(f36_abs, f36_signed)

    # Dominanza / ranking / gap sul dominio v5: solo probabilità normalizzate
    if None in (prob_1_norm, prob_x_norm, prob_2_norm):
        best_side = None
        dominance_pp = None
    else:
        probs_pct = {"1": prob_1_norm, "X": prob_x_norm, "2": prob_2_norm}
        best_label, _, _, _ = _dominance_sides(probs_pct)
        best_side = _side_label_to_enum(best_label)
        dominance_pp = compute_dominance_pp(prob_1_norm, prob_x_norm, prob_2_norm)

    x_rank, _ = x_rank_from_probs(prob_1_norm, prob_x_norm, prob_2_norm)
    gap_pp = probability_gap_1_2_pp(prob_1_norm, prob_2_norm)

    pillar_f36 = _pillar_f36_v5(
        quota_1=quota_1,
        quota_2=quota_2,
        f36_abs=f36_abs,
        f36_signed=f36_signed,
        f36_score=f36_dict.get("score"),
        f36_label=f36_dict.get("label"),
        f36_class_key=f36_dict.get("class_key"),
    )

    pillar_dominance = _pillar_dominance_v5(
        prob_1=prob_1_norm,
        prob_x=prob_x_norm,
        prob_2=prob_2_norm,
        best_side=best_side,
        dominance_pp=dominance_pp,
    )

    dominant_sign = dominant_side_to_market_label(best_side)

    pillar_draw = _pillar_draw_credibility_v5(
        prob_x=prob_x_norm,
        quota_x=quota_x,
        x_rank=x_rank,
        under_odd=under_odd,
        over_odd=over_odd,
        under_pct=under_pct,
        over_pct=over_pct,
        f36_label=f36_dict.get("label"),
        dominant_sign=dominant_sign,
    )

    pillar_gap = _pillar_gap_v5(
        prob_1=prob_1_norm,
        prob_2=prob_2_norm,
        gap_pp=gap_pp,
        f36_score=f36_dict.get("score"),
        f36_class_key=f36_dict.get("class_key"),
    )

    market_deviation = _build_market_deviation_v5(
        cecchino_1x2=(prob_1_norm, prob_x_norm, prob_2_norm),
        book_1x2=(prob_book_1, prob_book_x, prob_book_2),
        cecchino_ou=(under_pct, over_pct),
        book_ou=(prob_book_under, prob_book_over),
        quota_1=quota_1,
        quota_x=quota_x,
        quota_2=quota_2,
        quota_under=under_odd,
        quota_over=over_odd,
        quota_book_1=quota_book_1,
        quota_book_x=quota_book_x,
        quota_book_2=quota_book_2,
        quota_book_under=quota_book_under,
        quota_book_over=quota_book_over,
    )

    structural_summary = _build_structural_summary_v5(
        f36_label=pillar_f36.get("class_label"),
        dominance_label=pillar_dominance.get("class_label"),
        draw_label=pillar_draw.get("class_label"),
        gap_label=pillar_gap.get("class_label"),
    )

    warnings: list[str] = []
    for p in [pillar_f36, pillar_dominance, pillar_draw, pillar_gap]:
        warnings.extend(p.get("warnings", []))
    if market_deviation.get("status") == "unavailable":
        warnings.extend(market_deviation.get("warnings", []))
    warnings = list(set(warnings))

    return {
        "status": "ok",
        "version": VERSION,
        "inputs": {
            "quota_1": quota_1,
            "quota_x": quota_x,
            "quota_2": quota_2,
            "prob_1": prob_1_raw,
            "prob_x": prob_x_raw,
            "prob_2": prob_2_raw,
            "prob_1_norm": prob_1_norm,
            "prob_x_norm": prob_x_norm,
            "prob_2_norm": prob_2_norm,
            "under_odd": under_odd,
            "over_odd": over_odd,
        },
        "pillars": {
            "f36": pillar_f36,
            "dominance": pillar_dominance,
            "draw_credibility": pillar_draw,
            "gap_coherence": pillar_gap,
        },
        "pillar_order": PILLAR_ORDER,
        "market_deviation": market_deviation,
        "structural_summary": structural_summary,
        "warnings": warnings,
    }
