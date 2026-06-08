"""Analisi Equilibrio vs Squilibrio — Cecchino Today Fase 29."""

from __future__ import annotations

from typing import Any

VERSION = "cecchino_balance_analysis_v1"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prob_to_percent(prob: float | None, prob_pct: float | None = None) -> float | None:
    if prob_pct is not None:
        return float(prob_pct)
    if prob is None:
        return None
    p = float(prob)
    if p <= 1.0:
        return p * 100.0
    return p


def _classify_f36(f36_abs: float, f36_signed: float) -> dict[str, Any]:
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


def _dominance_sides(probs_pct: dict[str, float]) -> tuple[str, str, float, float]:
    ordered = sorted(probs_pct.items(), key=lambda x: x[1], reverse=True)
    best_side, best_prob = ordered[0]
    second_side, second_prob = ordered[1]
    return best_side, second_side, best_prob, second_prob


def _classify_dominance(
    dominance_pp: float,
    probs_pct: dict[str, float],
) -> dict[str, Any]:
    best_side, second_side, best_prob, second_prob = _dominance_sides(probs_pct)

    if dominance_pp <= 3:
        label, stars, class_key = "Equilibrio estremo", 1, "extreme_balance"
    elif dominance_pp <= 8:
        label, stars, class_key = "Equilibrio forte", 2, "strong_balance"
    elif dominance_pp <= 15:
        label, stars, class_key = "Tendenza", 3, "trend"
    elif dominance_pp <= 25:
        label, stars, class_key = "Squilibrio", 4, "imbalance"
    else:
        label, stars, class_key = "Squilibrio forte", 5, "strong_imbalance"

    return {
        "value": round(dominance_pp, 2),
        "label": label,
        "stars": stars,
        "class_key": class_key,
        "best_side": best_side,
        "second_side": second_side,
        "best_probability": round(best_prob, 2),
        "second_probability": round(second_prob, 2),
    }


def _classify_draw(quota_x: float) -> dict[str, Any]:
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


def _cross_reading(f36_abs: float, dominance_pp: float) -> dict[str, str]:
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
        return {
            "label": "X possibile ma attenzione",
            "description": (
                "Il match è equilibrato tra 1 e 2, "
                "ma il modello inizia a mostrare una leggera preferenza."
            ),
        }
    if f36_low and dom_high:
        return {
            "label": "Falso equilibrio",
            "description": (
                "Le quote 1 e 2 sono vicine, ma la distribuzione delle "
                "probabilità indica una dominanza più marcata."
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
        return {
            "label": "Squilibrio confermato",
            "description": (
                "La distanza tra quota 1 e quota 2 e la dominanza del modello "
                "confermano una direzione netta."
            ),
        }
    if f36_mid:
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
) -> dict[str, Any]:
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

    if f36_abs < 0.75 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            1,
            "X molto forte",
            "Tipica partita da X / Under",
            "very_strong_draw_under",
            "positive",
        )
    if f36_abs < 0.75 and dominance_pp <= 5 and 3.50 < quota_x <= 4.20:
        return _result(
            2,
            "X possibile",
            "Under interessante",
            "possible_draw_under",
            "positive",
        )
    if f36_abs < 0.75 and dominance_pp <= 5 and quota_x > 4.20:
        return _result(
            3,
            "Equilibrio apparente",
            "X poco probabile",
            "apparent_balance_low_draw",
            "warning",
        )
    if f36_abs < 0.75 and 5 < dominance_pp <= 10 and quota_x <= 3.50:
        return _result(
            4,
            "X possibile",
            "Presente lieve tendenza verso un lato",
            "possible_draw_light_trend",
            "positive",
        )
    if f36_abs < 0.75 and 5 < dominance_pp <= 10 and quota_x > 3.50:
        return _result(
            5,
            "Equilibrio con tendenza",
            "Attenzione a direzione 1 o 2",
            "balance_with_trend",
            "warning",
        )
    if f36_abs < 0.75 and dominance_pp > 10:
        return _result(
            6,
            "Falso equilibrio",
            (
                "La vicinanza tra quota 1 e quota 2 non basta: "
                "il modello mostra dominanza."
            ),
            "false_balance",
            "negative",
        )
    if 0.75 <= f36_abs <= 1.50 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            7,
            "Equilibrata ma meno pulita",
            "X ancora possibile, ma il quadro è meno netto.",
            "balanced_less_clean",
            "warning",
        )
    if 0.75 <= f36_abs <= 1.50 and 5 < dominance_pp <= 10 and quota_x <= 3.50:
        return _result(
            8,
            "Zona grigia",
            "La partita ha segnali contrastanti.",
            "grey_zone",
            "warning",
        )
    if 0.75 <= f36_abs <= 1.50 and dominance_pp > 10:
        return _result(
            9,
            "Tendenza verso 1 o 2",
            "La partita non è più da leggere come equilibrio puro.",
            "trend_to_side",
            "neutral",
        )
    if f36_abs > 1.50 and dominance_pp <= 5 and quota_x <= 3.50:
        return _result(
            10,
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
            11,
            "Squilibrio moderato",
            "La partita mostra una direzione, ma senza dominanza estrema.",
            "moderate_imbalance",
            "neutral",
        )
    if f36_abs > 1.50 and dominance_pp > 10:
        return _result(
            12,
            "Squilibrio confermato",
            "Partita più orientata verso 1 o 2.",
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
    best_side: str,
) -> str:
    if f36_abs < 0.75 and dominance_pp <= 5:
        return "Nessuna direzione netta"
    if best_side == "1":
        return "Tendenza verso 1"
    if best_side == "X":
        return "Tendenza verso X"
    return "Tendenza verso 2"


def _build_summary(
    operational: dict[str, Any],
    cross_reading: dict[str, str],
    favorite_direction: str,
) -> dict[str, Any]:
    op_class = operational.get("class_key", "")
    is_draw_under = op_class in {
        "very_strong_draw_under",
        "possible_draw_under",
        "possible_draw_light_trend",
    }
    is_false_balance = (
        op_class == "false_balance"
        or cross_reading.get("label") == "Falso equilibrio"
    )
    is_confirmed_imbalance = op_class == "confirmed_imbalance"

    short_advice_map = {
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
    q1 = _num(quota_cecchino_1)
    qx = _num(quota_cecchino_x)
    q2 = _num(quota_cecchino_2)
    p1 = _prob_to_percent(_num(prob_cecchino_1))
    px = _prob_to_percent(_num(prob_cecchino_x))
    p2 = _prob_to_percent(_num(prob_cecchino_2))

    if None in (q1, qx, q2, p1, px, p2):
        return {
            "version": VERSION,
            "status": "insufficient_data",
            "warnings": ["missing_cecchino_1x2_inputs"],
        }

    f36_signed = q2 - q1
    f36_abs = abs(f36_signed)
    probs_pct = {"1": p1, "X": px, "2": p2}
    ordered = sorted(probs_pct.values(), reverse=True)
    dominance_pp = ordered[0] - ordered[1]

    f36 = _classify_f36(f36_abs, f36_signed)
    dominance = _classify_dominance(dominance_pp, probs_pct)
    draw = _classify_draw(qx)
    cross = _cross_reading(f36_abs, dominance_pp)
    operational = _operational_reading(f36_abs, dominance_pp, qx)
    favorite = _favorite_direction(f36_abs, dominance_pp, dominance["best_side"])
    summary = _build_summary(operational, cross, favorite)

    return {
        "version": VERSION,
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
        "dominance": dominance,
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
            "rule_id": operational.get("rule_id"),
            "operational_class_key": operational.get("class_key"),
        },
        "warnings": [],
    }


def build_balance_analysis_from_final(final: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(final, dict) or final.get("status") != "available":
        return {
            "version": VERSION,
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
