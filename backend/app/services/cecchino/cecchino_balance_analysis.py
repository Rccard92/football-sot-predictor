"""Analisi Equilibrio vs Squilibrio — Cecchino Today Fase 29/30."""

from __future__ import annotations

from typing import Any

VERSION = "cecchino_balance_analysis_v2"

_SIDE_LABEL_TO_ENUM = {"1": "HOME", "X": "DRAW", "2": "AWAY"}
_SIDE_ENUM_TO_LABEL = {v: k for k, v in _SIDE_LABEL_TO_ENUM.items()}


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


def _side_label_to_enum(label: str) -> str:
    return _SIDE_LABEL_TO_ENUM.get(label, label)


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


def _classify_side_probability_gap(p1: float, p2: float) -> dict[str, Any]:
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
        if f36_abs < 0.75 and quota_x <= 3.50 and dominance_pp > 5:
            return _result(
                2,
                "X forte",
                (
                    "La partita è equilibrata tra 1 e 2 e la X è lo scenario "
                    "dominante del modello."
                ),
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
                "X molto forte",
                "Tipica partita da X / Under",
                "very_strong_draw_balance",
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
            "X molto forte",
            "Tipica partita da X / Under",
            "very_strong_draw_under",
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
    best_label, second_label, best_prob, second_prob = _dominance_sides(probs_pct)
    ordered = sorted(probs_pct.values(), reverse=True)
    dominance_pp = ordered[0] - ordered[1]
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
