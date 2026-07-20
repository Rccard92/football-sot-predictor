"""Policy immutabile readiness Intensità Goal Avanzata v5.

Riusa MINIMUM_PROSPECTIVE_MATCHES e gate del motore preview/candidate.
Niente soglie divergenti; immutable: true.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    MINIMUM_PROSPECTIVE_MATCHES,
    PRIMARY_ID,
    CHALLENGER_ID,
    BENCHMARK_ID,
    DIAGNOSTIC_ID,
)

GOAL_INTENSITY_V5_MONITORING_VERSION = "cecchino_goal_intensity_v5_monitoring_v1"
GOAL_INTENSITY_V5_READINESS_VERSION = "cecchino_goal_intensity_v5_readiness_v1"
GOAL_INTENSITY_V5_READINESS_POLICY_VERSION = (
    "cecchino_goal_intensity_v5_readiness_policy_v1"
)
GOAL_INTENSITY_V5_EXPORT_VERSION = "cecchino_goal_intensity_v5_export_v1"

# Alias espliciti — stessi valori del motore frozen
MIN_PROSPECTIVE_COMPLETED = MINIMUM_PROSPECTIVE_MATCHES
MIN_PAIRED_COMPARISON_N = 5

CANDIDATE_PRIMARY = PRIMARY_ID
CANDIDATE_CHALLENGER = CHALLENGER_ID
CANDIDATE_BENCHMARK = BENCHMARK_ID
CANDIDATE_DIAGNOSTIC = DIAGNOSTIC_ID


def build_goal_intensity_v5_readiness_policy_payload() -> dict[str, Any]:
    return {
        "version": GOAL_INTENSITY_V5_READINESS_POLICY_VERSION,
        "readiness_version": GOAL_INTENSITY_V5_READINESS_VERSION,
        "monitoring_version": GOAL_INTENSITY_V5_MONITORING_VERSION,
        "export_version": GOAL_INTENSITY_V5_EXPORT_VERSION,
        "immutable": True,
        "MINIMUM_PROSPECTIVE_MATCHES": MIN_PROSPECTIVE_COMPLETED,
        "MIN_PAIRED_COMPARISON_N": MIN_PAIRED_COMPARISON_N,
        "primary_candidate": CANDIDATE_PRIMARY,
        "challenger_candidate": CANDIDATE_CHALLENGER,
        "benchmark_candidate": CANDIDATE_BENCHMARK,
        "diagnostic_candidate": CANDIDATE_DIAGNOSTIC,
        "signals_integration_default": "blocked",
        "default_decision": "continue_monitoring",
        "notes": [
            "Soglie allineate al motore preview/candidate; non overrideabili da FE/query/env",
            "Pending non incrementa completed",
            "Storico research non incrementa campione prospettico",
            "Signals integration = active richiede implementazione separata",
        ],
    }
