"""Registry canonico preset Pattern Lab — filtri scientifici congelati, read-only.

I `filters` descrivono solo il pattern. Le metriche economiche usano
`performance_quote_policy = real_only` (separato): selections = pattern,
ROI/profit/avg odds solo su quote Bet365 reali.

`scientific_filters_sha256` fingerprinta solo i filters (non status/history).
`status_group` NON è persistito: derivarlo da `status` via derive_preset_status_group.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

PRESET_REGISTRY_VERSION = "pattern_lab_presets_v3"
PERFORMANCE_QUOTE_POLICY_REAL_ONLY = "real_only"

# Default operativi Pattern Lab (non sono soglie di pattern).
_BASE_OPS: dict[str, Any] = {
    "eligibility": "eligible_core",
    "market_informative": True,
}

# Hash congelati dei soli filters (JSON canonico) — non ritoccare senza nuovo ID.
FROZEN_SCIENTIFIC_FILTERS_SHA256: dict[str, str] = {
    "P01": "2eb34534af8c41f6de4298de963750fd46d9841bfd05d3d8515d95c5e6ad6cf5",
    "P02": "ad80af9b12a905b7944b0a45fd219897d04a1c992ab81e2011aa74e63e99de0d",
    "P03": "22c4c7cc4617e65f1a1ea4cbe1dcc2e6ca66adecf658784e5f1e1e6d5e63d699",
    "P04": "a43ec4a3294788c4574543ae253de9bf3a8e50e8817c6d23332698286a2ff9bc",
    "P05": "7c2f6cb27c500f252df96dea053edfb35cece9846456a8a00365da859af55a83",
    "P06": "7e504028cedaeb18694e895e9c9f835b033db948936863b9a7a6f1b2bee06b31",
    "P07": "b980c0ee9a60add603ce4c6861e06f4333fc968107063faa07c91675060790b9",
    "P08": "117e9687936c05d6f0df0b1065a1547b06aa3dee0cf8afb97616c59351094cdb",
    "P09": "01706c7e10fceefdbc51a474ce0533b42e47e5e557fb0fb37d5c5fbec8a51b3e",
    "P10": "75abb73216884f03d1618c407a7a9df0750c4b36f97e17732cbea13611d22983",
    "P11": "0829c96517eff33aa3bfebcff613b26b8a5e199a0445dc92d4e61433959fb49d",
    "P12": "47ff21fe980f963b66f963fbf726ad672ce1e3abc869ecbf79c935a4107eba21",
}


def _with_base(filters: dict[str, Any]) -> dict[str, Any]:
    out = dict(_BASE_OPS)
    out.update(filters)
    return out


def _canonical_filters_json(filters: dict[str, Any]) -> str:
    return json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scientific_filters_sha256(filters: dict[str, Any]) -> str:
    """SHA-256 deterministico dei soli filtri scientifici."""
    return hashlib.sha256(_canonical_filters_json(filters).encode("utf-8")).hexdigest()


def derive_preset_status_group(status: str | None) -> str:
    """Raggruppamento visuale derivato da status (non persistito nel registry)."""
    s = (status or "").strip()
    if s == "positive_oos_weakened":
        return "positive_weak"
    if s == "initial_replica_followup_negative":
        return "mixed"
    if s.startswith("failed_oos"):
        return "failed_oos"
    if s.startswith("candidate_oos"):
        return "candidate_new"
    if s.startswith("validated"):
        return "positive_weak"
    return "mixed"


PATTERN_LAB_PRESETS: list[dict[str, Any]] = [
    {
        "id": "P01",
        "label": "P01 · HOME — Stabilità offensiva HIGH",
        "description": (
            "HOME con goal.offensive_stability.class = high. "
            "Scoperto su 2021/22, replicato OOS 2022/23, follow-up 2023/24 negativo."
        ),
        "status": "initial_replica_followup_negative",
        "ui_badge": "Replica iniziale, follow-up negativo",
        "discovery_seasons": ["2021/2022"],
        "validation_seasons": ["2022/2023", "2023/2024"],
        "first_oos_season": "2022/2023",
        "validation_history": [
            {
                "season": "2022/2023",
                "phase": "oos",
                "result": "positive",
                "roi_pct": 17.7,
            },
            {
                "season": "2023/2024",
                "phase": "follow_up_oos",
                "result": "negative",
                "roi_pct": -9.0,
            },
        ],
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
            "Replica OOS 21/22→22/23 (+14.7→+17.7); follow-up 23/24 negativo (−9.0). "
            "performance_quote_policy=real_only non fa parte della formula scientifica."
        ),
    },
    {
        "id": "P02",
        "label": "P02 · HOME — Stability HIGH + V3.6",
        "description": (
            "HOME + offensive_stability high + purchasability_v36_status = score. "
            "Individuato guardando 2021/22 e 2022/23 insieme. "
            "Primo vero OOS 2023/24 fallito."
        ),
        "status": "failed_oos_2023_24",
        "ui_badge": "Fallito OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": ["2023/2024"],
        "first_oos_season": "2023/2024",
        "validation_history": [
            {
                "season": "2023/2024",
                "phase": "oos",
                "result": "negative",
                "roi_pct": -26.9,
            },
        ],
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
            "Discovery +64.6% / +50.4%; OOS 23/24 −26.9%. "
            "Preservato nel registro scientifico come fallito OOS."
        ),
    },
    {
        "id": "P03",
        "label": "P03 · AWAY — Signal + Defensive Solidity MEDIUM",
        "description": (
            "AWAY con signal_active=true e goal.defensive_solidity.class = medium."
        ),
        "status": "positive_oos_weakened",
        "ui_badge": "OOS positivo indebolito",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": ["2023/2024"],
        "first_oos_season": "2023/2024",
        "validation_history": [
            {
                "season": "2023/2024",
                "phase": "oos",
                "result": "positive_weakened",
                "roi_pct": 2.2,
            },
        ],
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
        "notes": (
            "signal_active è filtro esplicito su pre_signal_active, non signals_count. "
            "OOS 23/24 positivo ma indebolito (+19.8→+17.3→+2.2). Formula non modificata."
        ),
    },
    {
        "id": "P04",
        "label": "P04 · DRAW — Final LOW + Stability VERY HIGH",
        "description": (
            "DRAW con goal_final_class=low e offensive_stability.class=very_high."
        ),
        "status": "failed_oos_2023_24",
        "ui_badge": "Fallito OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": ["2023/2024"],
        "first_oos_season": "2023/2024",
        "validation_history": [
            {
                "season": "2023/2024",
                "phase": "oos",
                "result": "negative",
                "roi_pct": -11.8,
            },
        ],
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
        "notes": "Discovery +22.6% / +16.3%; OOS 23/24 −11.8%. Fallito OOS, resta nel registro.",
    },
    {
        "id": "P05",
        "label": "P05 · AWAY — V3.6 40–59",
        "description": (
            "AWAY con V3.6 status=score e score in [40, 60). "
            "Upper bound esclusivo via purchasability_v36_max_exclusive."
        ),
        "status": "failed_oos_2023_24",
        "ui_badge": "Fallito OOS 23/24",
        "discovery_seasons": ["2021/2022", "2022/2023"],
        "validation_seasons": ["2023/2024"],
        "first_oos_season": "2023/2024",
        "validation_history": [
            {
                "season": "2023/2024",
                "phase": "oos",
                "result": "negative",
                "roi_pct": -28.6,
            },
        ],
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
            "Discovery +8.1% / +6.7%; OOS 23/24 −28.6%. "
            "Non altera la semantica globale inclusiva di purchasability_v36_max."
        ),
    },
    {
        "id": "P06",
        "label": "P06 · DRAW — Production LOW + V3.6 30–39",
        "description": (
            "DRAW con offensive_production=low e V3.6 score in [30, 40). "
            "Scoperto su 2021/22–2023/24. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["DRAW"],
                "goal_pillar_filters": {
                    "offensive_production": {"class": "low"},
                },
                "purchasability_v36_status": "score",
                "purchasability_v36_min": 30.0,
                "purchasability_v36_max": 40.0,
                "purchasability_v36_max_exclusive": True,
            }
        ),
        "notes": (
            "Discovery indicativa: N≈188, ROI≈+25.4%. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P07",
        "label": "P07 · AWAY — Production MEDIUM + Tempo VERY LOW",
        "description": (
            "AWAY con offensive_production=medium e match_tempo=very_low. "
            "Scoperto su 2021/22–2023/24. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "goal_pillar_filters": {
                    "offensive_production": {"class": "medium"},
                    "match_tempo": {"class": "very_low"},
                },
            }
        ),
        "notes": (
            "Discovery indicativa: N≈169, ROI≈+27.4%. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P08",
        "label": "P08 · AWAY — Signal + Tempo HIGH",
        "description": (
            "AWAY con signal_active=true e match_tempo=high. "
            "Scoperto su 2021/22–2023/24. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "signal_active": True,
                "goal_pillar_filters": {
                    "match_tempo": {"class": "high"},
                },
            }
        ),
        "notes": (
            "Discovery indicativa: N≈164, ROI≈+16.7%. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P09",
        "label": "P09 · DRAW — Production MEDIUM + Tempo LOW",
        "description": (
            "DRAW con offensive_production=medium e match_tempo=low. "
            "Scoperto su 2021/22–2023/24. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["DRAW"],
                "goal_pillar_filters": {
                    "offensive_production": {"class": "medium"},
                    "match_tempo": {"class": "low"},
                },
            }
        ),
        "notes": (
            "Discovery indicativa: N≈213, ROI≈+23.4%. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P10",
        "label": "P10 · AWAY — Final HIGH + Tempo MEDIUM",
        "description": (
            "AWAY con goal_final_class=high e match_tempo=medium. "
            "High variance / longshot. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "flags": {
            "high_variance": True,
            "longshot_pattern": True,
        },
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "goal_final_class": "high",
                "goal_pillar_filters": {
                    "match_tempo": {"class": "medium"},
                },
            }
        ),
        "notes": (
            "high_variance=true; longshot_pattern=true. "
            "Discovery N≈184 ROI≈+47% ma ad alta varianza — non presentare come migliore per ROI. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P11",
        "label": "P11 · HOME — Final LOW + Production VERY LOW",
        "description": (
            "HOME con goal_final_class=low e offensive_production=very_low. "
            "Candidato secondario. NON validato: prima OOS = 2024/25."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["HOME"],
                "goal_final_class": "low",
                "goal_pillar_filters": {
                    "offensive_production": {"class": "very_low"},
                },
            }
        ),
        "notes": (
            "Candidato secondario. Discovery indicativa N≈200 ROI≈+13.8%. "
            "Vietato modificare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
    {
        "id": "P12",
        "label": "P12 · AWAY — Signal + Defensive Solidity MEDIUM + Tempo HIGH",
        "description": (
            "Refinement di P03: AWAY + signal_active + defensive_solidity=medium "
            "+ match_tempo=high. Low-sample refinement candidate — first OOS 2024/25. "
            "NON sostituisce P03."
        ),
        "status": "candidate_oos_2024_25",
        "ui_badge": "Candidato · prima OOS 24/25",
        "discovery_seasons": ["2021/2022", "2022/2023", "2023/2024"],
        "validation_seasons": [],
        "first_oos_season": "2024/2025",
        "validation_history": [],
        "flags": {
            "low_sample": True,
            "refinement_pattern": True,
            "derived_from": "P03",
        },
        "performance_quote_policy": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "filters": _with_base(
            {
                "market_keys": ["AWAY"],
                "signal_active": True,
                "goal_pillar_filters": {
                    "defensive_solidity": {"class": "medium"},
                    "match_tempo": {"class": "high"},
                },
            }
        ),
        "notes": (
            "low_sample + refinement_pattern; derived_from=P03. "
            "Discovery indicativa: Run17 N=23 ROI≈+34.7%; Run19 N=24 ROI≈+32.2%; "
            "Run20 N=36 ROI≈+15.3%. NON modifica P03. "
            "Vietato ritoccare dopo aver osservato 2024/25; variante = nuovo ID."
        ),
    },
]


def _enrich_preset(preset: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy + fingerprint filtri; status_group derivato (non persistito)."""
    out = deepcopy(preset)
    filters = out.get("filters") or {}
    out["scientific_filters_sha256"] = scientific_filters_sha256(filters)
    out["status_group"] = derive_preset_status_group(out.get("status"))
    return out


def list_pattern_lab_presets() -> dict[str, Any]:
    """Payload API: registry versionato, preset deep-copied (read-only)."""
    return {
        "registry_version": PRESET_REGISTRY_VERSION,
        "performance_quote_policy_default": PERFORMANCE_QUOTE_POLICY_REAL_ONLY,
        "presets": [_enrich_preset(p) for p in PATTERN_LAB_PRESETS],
    }


def get_pattern_lab_preset(preset_id: str) -> dict[str, Any] | None:
    for p in PATTERN_LAB_PRESETS:
        if p["id"] == preset_id:
            return _enrich_preset(p)
    return None


def preset_scientific_filters(preset: dict[str, Any]) -> dict[str, Any]:
    """Solo i filtri del pattern (nessun quote_type forzato)."""
    return deepcopy(preset.get("filters") or {})
