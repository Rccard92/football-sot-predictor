"""Candidate research indices riusati da dataset Credibilità X e Preview v5.

Formule identiche a quelle già usate in cecchino_draw_credibility_dataset
(nessuna nuova formula).
"""

from __future__ import annotations

from typing import Any


def clamp_index(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, value)), 2)


def classify_conviction(value: float | None) -> str | None:
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


def conviction_index_candidate(
    prob_1_norm: float | None,
    prob_x_norm: float | None,
    prob_2_norm: float | None,
) -> float | None:
    """100 * (max - second) / max — stessa formula del dataset research."""
    if None in (prob_1_norm, prob_x_norm, prob_2_norm):
        return None
    ordered = sorted([float(prob_1_norm), float(prob_x_norm), float(prob_2_norm)], reverse=True)
    max_prob, second_prob = ordered[0], ordered[1]
    if max_prob <= 0:
        return None
    return clamp_index(100.0 * (max_prob - second_prob) / max_prob)


def probability_gap_1_2_pp(prob_1_norm: float | None, prob_2_norm: float | None) -> float | None:
    if prob_1_norm is None or prob_2_norm is None:
        return None
    return round(abs(float(prob_1_norm) - float(prob_2_norm)), 2)


def probability_balance_index(prob_1_norm: float | None, prob_2_norm: float | None) -> float | None:
    if prob_1_norm is None or prob_2_norm is None:
        return None
    s = float(prob_1_norm) + float(prob_2_norm)
    if s <= 0:
        return None
    return clamp_index(100.0 * (1.0 - abs(float(prob_1_norm) - float(prob_2_norm)) / s))


def gap_coherence_index_candidate(
    f36_score: float | None,
    prob_balance: float | None,
) -> float | None:
    """100 - |f36_score - probability_balance_index| — stessa formula del dataset."""
    if f36_score is None or prob_balance is None:
        return None
    return clamp_index(100.0 - abs(float(f36_score) - float(prob_balance)))


def x_rank_from_probs(
    prob_1_norm: float | None,
    prob_x_norm: float | None,
    prob_2_norm: float | None,
) -> tuple[int | None, bool]:
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
    """HOME/DRAW/AWAY o 1/X/2 → 1/X/2."""
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
    """Bundle candidati research da probabilità già normalizzate in punti percentuali."""
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
