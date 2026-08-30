"""Registry canonico preset Pattern Lab — filtri scientifici congelati, read-only.

I `filters` descrivono solo il pattern. Le metriche economiche usano
`performance_quote_policy = real_only` (separato): selections = pattern,
ROI/profit/avg odds solo su quote Bet365 reali.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PRESET_REGISTRY_VERSION = "pattern_lab_presets_v1"
PERFORMANCE_QUOTE_POLICY_REAL_ONLY = "real_only"

# Default operativi Pattern Lab (non sono soglie di pattern).
_BASE_OPS: dict[str, Any] = {
    "eligibility": "eligible_core",
    "market_informative": True,
}


def _with_base(filters: dict[str, Any]) -> dict[str, Any]:
    out = dict(_BASE_OPS)
    out.update(filters)
    return out


PATTERN_LAB_PRESETS: list[dict[str, Any]] = [
    {
        "id": "P01",
        "label": "P01 · HOME — Stabilità offensiva HIGH",
        "description": (
            "HOME con goal.offensive_stability.class = high. "
            "Scoperto su 2021/22 e replicato su 2022/23."
        ),
        "status": "validated_2_seasons",
        "ui_badge": "Confermato 2 stagioni",
        "discovery_seasons": ["2021/2022"],
        "validation_seasons": ["2022/2023"],
        "first_oos_season": "2022/2023",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["HOME"],
                "goal_pillar_filters": {
                    "offensive_stability": {"class": "high"},
                },
            }
        ),
        "notes": (
            "Unico preset con vera replica OOS 21/22 → 22/23. "
            "performance_quote_policy=real_only non fa parte della formula scientifica."
        ),
    },
    {
        "id": "P02",
        "label": "P02 · HOME — Stability HIGH + V3.6",
        "description": (
            "HOME + offensive_stability high + purchasability_v36_status = score. "
            "Individuato guardando 2021/22 e 2022/23 insieme: NON validated OOS. "
            "Prima stagione OOS = 2023/24."
        ),
        "status": "candidate_oos_2023_24",
        "ui_badge": "Candidato · test OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": [],
        "first_oos_season": "2023/2024",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["HOME"],
                "goal_pillar_filters": {
                    "offensive_stability": {"class": "high"},
                },
                "purchasability_v36_status": "score",
            }
        ),
        "notes": (
            "Candidato: non dichiarare validato. Testare senza modifiche su 2023/24."
        ),
    },
    {
        "id": "P03",
        "label": "P03 · AWAY — Signal + Defensive Solidity MEDIUM",
        "description": (
            "AWAY con signal_active=true e goal.defensive_solidity.class = medium."
        ),
        "status": "candidate_oos_2023_24",
        "ui_badge": "Candidato · test OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": [],
        "first_oos_season": "2023/2024",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "signal_active": True,
                "goal_pillar_filters": {
                    "defensive_solidity": {"class": "medium"},
                },
            }
        ),
        "notes": "signal_active è filtro esplicito su pre_signal_active, non signals_count.",
    },
    {
        "id": "P04",
        "label": "P04 · DRAW — Final LOW + Stability VERY HIGH",
        "description": (
            "DRAW con goal_final_class=low e offensive_stability.class=very_high."
        ),
        "status": "candidate_oos_2023_24",
        "ui_badge": "Candidato · test OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": [],
        "first_oos_season": "2023/2024",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["DRAW"],
                "goal_final_class": "low",
                "goal_pillar_filters": {
                    "offensive_stability": {"class": "very_high"},
                },
            }
        ),
        "notes": "Candidato OOS 23/24.",
    },
    {
        "id": "P05",
        "label": "P05 · AWAY — V3.6 40–59",
        "description": (
            "AWAY con V3.6 status=score e score in [40, 60). "
            "Upper bound esclusivo via purchasability_v36_max_exclusive."
        ),
        "status": "candidate_oos_2023_24",
        "ui_badge": "Candidato · test OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": [],
        "first_oos_season": "2023/2024",
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "purchasability_v36_status": "score",
                "purchasability_v36_min": 40.0,
                "purchasability_v36_max": 60.0,
                "purchasability_v36_max_exclusive": True,
            }
        ),
        "notes": (
            "Fascia semantica [40,60): score>=40 e score<60. "
            "Non altera la semantica globale inclusiva di purchasability_v36_max."
        ),
    },
]


def list_pattern_lab_presets() -> dict[str, Any]:
    """Payload API: registry versionato, preset deep-copied (read-only)."""
    return {
        "registry_version": PRESET_REGISTRY_VERSION,
        "performance_quote_policy_default": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "presets": [deepcopy(p) for p in PATTERN_LAB_PRESETS],
    }


def get_pattern_lab_preset(preset_id: str) -> dict[str, Any] | None:
    for p in PATTERN_LAB_PRESETS:
        if p["id"] == preset_id:
            return deepcopy(p)
    return None


def preset_scientific_filters(preset: dict[str, Any]) -> dict[str, Any]:
    """Solo i filtri del pattern (nessun quote_type forzato)."""
    return deepcopy(preset.get("filters") or {})
