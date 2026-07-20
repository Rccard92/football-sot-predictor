"""Registry canonico classi Balance v5 per analisi empirica Step 2B.

Fonte: cecchino_balance_v5.py (label IT + class_key).
I valori in cecchino_balance_v5_evaluations usano class_label italiane.
Classi sconosciute: mantenute, etichettate «Classe non registrata», warning.
"""

from __future__ import annotations

from typing import Any

UNKNOWN_CLASS_LABEL = "Classe non registrata"

# Palette grafici (violet / indigo / blue / slate)
_COLORS = {
    "f36": ["#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd"],
    "dominance": ["#4f46e5", "#6366f1", "#818cf8", "#a5b4fc", "#c7d2fe"],
    "draw_credibility": ["#2563eb", "#3b82f6", "#60a5fa", "#93c5fd"],
    "gap": ["#475569", "#64748b", "#94a3b8", "#cbd5e1", "#e2e8f0"],
}

PILLAR_META: dict[str, dict[str, Any]] = {
    "f36": {
        "canonical_key": "f36",
        "label_it": "Geometria F36",
        "role": "descriptive_structure",
        "meaning": "Descrive la geometria delle quote laterali",
        "index_field": "f36_index",
        "class_field": "f36_class",
        "primary_targets": [],
        "secondary_targets": [
            "outcome_1x2",
            "is_draw",
            "absolute_goal_difference",
            "total_goals",
            "dominance_selection_hit",
        ],
    },
    "dominance": {
        "canonical_key": "dominance",
        "label_it": "Dominanza",
        "role": "scenario_preference",
        "meaning": "Preferenza di scenario della selezione dominante",
        "index_field": "dominance_index",
        "class_field": "dominance_class",
        "primary_targets": ["dominance_selection_hit"],
        "secondary_targets": [
            "outcome_1x2",
            "is_draw",
            "absolute_goal_difference",
        ],
    },
    "draw_credibility": {
        "canonical_key": "draw_credibility",
        "label_it": "Credibilità X",
        "role": "draw_plausibility",
        "meaning": "Plausibilità empirica del pareggio",
        "index_field": "draw_credibility_index",
        "class_field": "draw_credibility_class",
        "primary_targets": ["is_draw"],
        "secondary_targets": ["outcome_1x2"],
    },
    "gap": {
        "canonical_key": "gap",
        "label_it": "Coerenza Gap",
        "role": "mathematical_coherence",
        "meaning": "Coerenza matematica tra geometria F36 e equilibrio probabilistico",
        "index_field": "gap_index",
        "class_field": "gap_class",
        "primary_targets": [],
        "secondary_targets": [
            "dominance_selection_hit",
            "is_draw",
            "absolute_goal_difference",
            "total_goals",
        ],
    },
}


def _cls(
    key: str,
    label_it: str,
    order: int,
    *,
    color: str,
    expected_direction: str | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    als = list(aliases or [])
    if key not in als:
        als.append(key)
    if label_it not in als:
        als.append(label_it)
    return {
        "canonical_key": key,
        "label_it": label_it,
        "order": order,
        "chart_color": color,
        "expected_direction": expected_direction,
        "aliases": als,
    }


BALANCE_CLASS_REGISTRY: dict[str, list[dict[str, Any]]] = {
    "f36": [
        _cls("strong_balance", "Equilibrio forte", 1, color=_COLORS["f36"][0]),
        _cls("balance", "Equilibrio", 2, color=_COLORS["f36"][1]),
        _cls("transition", "Transizione", 3, color=_COLORS["f36"][2]),
        _cls(
            "imbalance",
            "Squilibrio",
            4,
            color=_COLORS["f36"][3],
            expected_direction="lateral_concentration",
        ),
    ],
    "dominance": [
        _cls("very_weak", "Molto Debole", 1, color=_COLORS["dominance"][0]),
        _cls("weak", "Debole", 2, color=_COLORS["dominance"][1]),
        _cls("moderate", "Moderata", 3, color=_COLORS["dominance"][2]),
        _cls("strong", "Forte", 4, color=_COLORS["dominance"][3]),
        _cls(
            "very_strong",
            "Molto Forte",
            5,
            color=_COLORS["dominance"][4],
            expected_direction="higher_hit_rate",
        ),
    ],
    "draw_credibility": [
        _cls(
            "strong_draw",
            "Pareggio forte",
            1,
            color=_COLORS["draw_credibility"][0],
            expected_direction="higher_draw_rate",
        ),
        _cls(
            "possible_draw",
            "Pareggio possibile",
            2,
            color=_COLORS["draw_credibility"][1],
            expected_direction="higher_draw_rate",
        ),
        _cls(
            "weak_draw",
            "Pareggio debole",
            3,
            color=_COLORS["draw_credibility"][2],
        ),
        _cls(
            "unlikely_draw",
            "Pareggio poco probabile",
            4,
            color=_COLORS["draw_credibility"][3],
            expected_direction="lower_draw_rate",
        ),
    ],
    "gap": [
        _cls("not_confirmed", "Non Confermato", 1, color=_COLORS["gap"][0]),
        _cls("weak", "Debole", 2, color=_COLORS["gap"][1]),
        _cls("partial", "Parziale", 3, color=_COLORS["gap"][2]),
        _cls("confirmed", "Confermato", 4, color=_COLORS["gap"][3]),
        _cls(
            "strongly_confirmed",
            "Fortemente Confermato",
            5,
            color=_COLORS["gap"][4],
        ),
    ],
}


def _alias_index(pillar: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in BALANCE_CLASS_REGISTRY.get(pillar, []):
        for a in entry["aliases"]:
            out[str(a).strip().lower()] = entry
    return out


_ALIAS_INDEX = {p: _alias_index(p) for p in BALANCE_CLASS_REGISTRY}


def resolve_class(pillar: str, raw: str | None) -> dict[str, Any]:
    """Risolve una classe DB (label o key) al registry; sconosciute non droppate."""
    if raw is None or str(raw).strip() == "":
        return {
            "canonical_key": "missing",
            "label_it": "Assente",
            "order": 9998,
            "chart_color": "#94a3b8",
            "expected_direction": None,
            "aliases": [],
            "is_registered": False,
            "is_missing": True,
            "raw": raw,
        }
    key = str(raw).strip().lower()
    hit = _ALIAS_INDEX.get(pillar, {}).get(key)
    if hit:
        return {**hit, "is_registered": True, "is_missing": False, "raw": raw}
    return {
        "canonical_key": f"unknown:{raw}",
        "label_it": UNKNOWN_CLASS_LABEL,
        "order": 9999,
        "chart_color": "#64748b",
        "expected_direction": None,
        "aliases": [str(raw)],
        "is_registered": False,
        "is_missing": False,
        "raw": raw,
        "warning": "unregistered_class",
    }


def build_class_registry_payload() -> dict[str, Any]:
    return {
        "pillars": {
            k: {
                **PILLAR_META[k],
                "classes": BALANCE_CLASS_REGISTRY[k],
            }
            for k in PILLAR_META
        },
        "unknown_class_label": UNKNOWN_CLASS_LABEL,
        "notes": [
            "Classi canoniche da cecchino_balance_v5.py",
            "Valori DB tipicamente class_label italiane",
            "Classi sconosciute mantenute con warning",
        ],
    }
