"""Equilibrio vs Squilibrio V2.5: stessi 4 pilastri della V2, riscritti.

Difetti della V2 corretti:
- nella RUN V2 solo il pilastro F36 aveva una classe salvata: Convinzione, Credibilita'
  X e Coerenza erano vuoti per tutte le partite (i pattern non potevano usarli);
- F36 era la differenza tra QUOTE |q1 - q2| con soglie fisse 0,5/1/1,5: tra 1,50 e 2,00
  e tra 4,00 e 4,50 la differenza e' la stessa ma l'equilibrio no. In V2.5 e' la
  distanza tra le probabilita' 1 e 2;
- F36 veniva corretto con la quota X del BOOK: in V2.5 il modulo usa solo il Cecchino;
- la Coerenza confrontava F36 con un indice ricavato dalle stesse quote (sempre coerente
  con se stesso). In V2.5 confronta due motori diversi: i picchetti (vittorie/pareggi/
  sconfitte) e il modello gol (gol attesi delle due squadre). Se entrambi indicano lo
  stesso lato con la stessa forza, la lettura e' confermata;
- le soglie sono scale congelate (vedi scales.py), non valori fissi scelti a mano.
"""

from __future__ import annotations

from math import exp
from typing import Any

from app.services.cecchino_v25 import scales

MODULE_VERSION = "cecchino_v25_balance_v1"

SCALE_SIDE_GAP = "bal_side_gap"
SCALE_CONVICTION = "bal_conviction"
SCALE_DRAW = "bal_draw_probability"
SCALE_COHERENCE = "bal_engine_disagreement"

_GEOMETRY_CLASSES = (
    # percentile della distanza 1-2 (basso = equilibrio)
    (25.0, "strong_balance", "Equilibrio forte"),
    (50.0, "balance", "Equilibrio"),
    (75.0, "transition", "Transizione"),
    (100.01, "imbalance", "Squilibrio"),
)
_CONVICTION_KEYS = (
    ("very_weak", "Molto Debole"),
    ("weak", "Debole"),
    ("moderate", "Moderata"),
    ("strong", "Forte"),
    ("very_strong", "Molto Forte"),
)
_COHERENCE_KEYS = (
    ("not_confirmed", "Non Confermato"),
    ("weak", "Debole"),
    ("partial", "Parziale"),
    ("confirmed", "Confermato"),
    ("strongly_confirmed", "Fortemente Confermato"),
)


def _band(score_value: float | None, keys: tuple[tuple[str, str], ...]) -> tuple[str | None, str | None]:
    if score_value is None:
        return None, None
    return keys[min(4, int(score_value // 20))]


def _poisson(lam: float, kmax: int = 10) -> list[float]:
    out = [exp(-lam)]
    for k in range(1, kmax + 1):
        out.append(out[-1] * lam / k)
    return out


def goal_side_difference(lambda_home: float, lambda_away: float) -> float:
    """P(casa segna piu' dell'ospite) - P(ospite segna piu' della casa), gol indipendenti."""
    ph, pa = _poisson(lambda_home), _poisson(lambda_away)
    home = away = 0.0
    for i, a in enumerate(ph):
        for j, b in enumerate(pa):
            if i > j:
                home += a * b
            elif j > i:
                away += a * b
    return home - away


def raw_features(final: dict[str, Any], lambda_home: float | None, lambda_away: float | None) -> dict[str, float] | None:
    p1, px, p2 = final.get("prob_1"), final.get("prob_x"), final.get("prob_2")
    if None in (p1, px, p2):
        return None
    ordered = sorted([p1, px, p2], reverse=True)
    out = {
        "side_gap": abs(p1 - p2),
        "conviction": (ordered[0] - ordered[1]) / ordered[0],
        "draw_probability": px,
    }
    if lambda_home is not None and lambda_away is not None:
        out["engine_disagreement"] = abs((p1 - p2) - goal_side_difference(lambda_home, lambda_away))
    return out


def build_balance_v25(final: dict[str, Any], lambda_home: float | None, lambda_away: float | None) -> dict[str, Any]:
    feats = raw_features(final, lambda_home, lambda_away)
    if feats is None:
        return {"module_version": MODULE_VERSION, "status": "unavailable", "pillars": {}, "pillar_classes": {}}

    pillars: dict[str, Any] = {}
    gap_pct = scales.score(SCALE_SIDE_GAP, feats["side_gap"])
    geometry = next(((k, l) for cut, k, l in _GEOMETRY_CLASSES if gap_pct is not None and gap_pct < cut), (None, None))
    pillars["f36"] = {
        "key": "f36",
        "title": "Geometria della partita",
        "raw_value": round(feats["side_gap"], 6),
        "index": round(100.0 - gap_pct, 3) if gap_pct is not None else None,
        "class_key": geometry[0],
        "class_label": geometry[1],
        "direction": "1" if final["prob_1"] > final["prob_2"] else ("2" if final["prob_2"] > final["prob_1"] else None),
    }
    conv = scales.score(SCALE_CONVICTION, feats["conviction"])
    ck, cl = _band(conv, _CONVICTION_KEYS)
    probs = {"1": final["prob_1"], "X": final["prob_x"], "2": final["prob_2"]}
    pillars["dominance"] = {
        "key": "dominance",
        "title": "Convinzione del modello",
        "raw_value": round(feats["conviction"], 6),
        "index": round(conv, 3) if conv is not None else None,
        "class_key": ck,
        "class_label": cl,
        "direction": max(probs, key=probs.get),
    }
    draw = scales.score(SCALE_DRAW, feats["draw_probability"])
    dk, dl = scales.five_class(draw)
    pillars["draw_credibility"] = {
        "key": "draw_credibility",
        "title": "Credibilita' della X",
        "raw_value": round(feats["draw_probability"], 6),
        "index": round(draw, 3) if draw is not None else None,
        "class_key": dk,
        "class_label": dl,
    }
    if "engine_disagreement" in feats:
        dis = scales.score(SCALE_COHERENCE, feats["engine_disagreement"])
        coherence = 100.0 - dis if dis is not None else None
        gk, gl = _band(coherence, _COHERENCE_KEYS)
        pillars["gap_coherence"] = {
            "key": "gap_coherence",
            "title": "Coerenza tra picchetti e modello gol",
            "raw_value": round(feats["engine_disagreement"], 6),
            "index": round(coherence, 3) if coherence is not None else None,
            "class_key": gk,
            "class_label": gl,
        }
    pillar_classes = {k: v.get("class_key") for k, v in pillars.items()}
    return {
        "module_version": MODULE_VERSION,
        "scales_version": scales.scales_version(),
        "status": "ok" if all(pillar_classes.values()) and len(pillar_classes) == 4 else "partial",
        "pillars": pillars,
        "pillar_classes": pillar_classes,
        "structural_summary": {"state": geometry[1], "class_key": geometry[0]},
        "raw_features": {k: round(v, 6) for k, v in feats.items()},
    }
