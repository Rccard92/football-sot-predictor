"""Eleggibilità storica Cecchino Lab (senza gate Betfair)."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE
from app.services.cecchino.cecchino_today_constants import (
    MIN_AWAY_CONTEXT,
    MIN_AWAY_TOTAL,
    MIN_HOME_CONTEXT,
    MIN_HOME_TOTAL,
    MIN_RECENT_CONTEXT_5,
    MIN_RECENT_TOTAL_6,
)
from app.services.cecchino_data_lab.historical_context_builder import LabPreMatchContexts

ELIGIBLE_CORE = "eligible_core"
EXCLUDED_INSUFFICIENT_HISTORY = "excluded_insufficient_history"
EXCLUDED_MISSING_RESULT_HISTORY = "excluded_missing_result_history"
EXCLUDED_LEAKAGE = "excluded_leakage"
EXCLUDED_MISSING_PICCHETTO = "excluded_missing_picchetto"
EXCLUDED_ZERO_PROBABILITY = "excluded_zero_probability"
EXCLUDED_CECCHINO_NOT_CALCULABLE = "excluded_cecchino_not_calculable"
EXCLUDED_INVALID_IDENTITY = "excluded_invalid_identity"
ELIGIBILITY_ERROR = "error"


def evaluate_historical_eligibility(
    *,
    home_team: str | None,
    away_team: str | None,
    kickoff_at: Any,
    contexts: LabPreMatchContexts | None,
    cecchino_output: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[str] = []

    if not home_team or not away_team:
        return {
            "status": EXCLUDED_INVALID_IDENTITY,
            "reason": "missing_teams",
            "blocking_reasons": ["missing_teams"],
            "core_eligible": False,
        }
    if kickoff_at is None:
        return {
            "status": EXCLUDED_INVALID_IDENTITY,
            "reason": "missing_kickoff",
            "blocking_reasons": ["missing_kickoff"],
            "core_eligible": False,
        }
    if contexts is None:
        return {
            "status": ELIGIBILITY_ERROR,
            "reason": "contexts_missing",
            "blocking_reasons": ["contexts_missing"],
            "core_eligible": False,
        }
    if not contexts.leakage_ok:
        return {
            "status": EXCLUDED_LEAKAGE,
            "reason": "leakage_detected",
            "blocking_reasons": ["leakage_detected"],
            "core_eligible": False,
        }

    samples = {
        "home_context": contexts.home_context.total,
        "away_context": contexts.away_context.total,
        "home_total": contexts.home_total.total,
        "away_total": contexts.away_total.total,
        "home_recent_context_5": contexts.home_recent_context_5.total,
        "away_recent_context_5": contexts.away_recent_context_5.total,
        "home_recent_total_6": contexts.home_recent_total_6.total,
        "away_recent_total_6": contexts.away_recent_total_6.total,
    }
    mins = {
        "home_context": MIN_HOME_CONTEXT,
        "away_context": MIN_AWAY_CONTEXT,
        "home_total": MIN_HOME_TOTAL,
        "away_total": MIN_AWAY_TOTAL,
        "home_recent_context_5": MIN_RECENT_CONTEXT_5,
        "away_recent_context_5": MIN_RECENT_CONTEXT_5,
        "home_recent_total_6": MIN_RECENT_TOTAL_6,
        "away_recent_total_6": MIN_RECENT_TOTAL_6,
    }
    for key, need in mins.items():
        if samples[key] < need:
            blockers.append(f"insufficient_sample:{key}:{samples[key]}<{need}")

    if blockers:
        return {
            "status": EXCLUDED_INSUFFICIENT_HISTORY,
            "reason": blockers[0],
            "blocking_reasons": blockers,
            "core_eligible": False,
            "samples": samples,
        }

    # Storico risultato: i prior devono avere FT
    for key, ids in (contexts.fixture_ids or {}).items():
        if key.endswith("_context") or key.endswith("_total") or "recent" in key:
            if samples.get(key.replace("home_", "home_").replace("away_", "away_"), 0) == 0:
                pass

    out = cecchino_output or {}
    final = out.get("final") or {}
    picchetti = out.get("picchetti") or {}
    if len(picchetti) < 4:
        return {
            "status": EXCLUDED_MISSING_PICCHETTO,
            "reason": "incomplete_picchetti",
            "blocking_reasons": ["incomplete_picchetti"],
            "core_eligible": False,
            "samples": samples,
        }

    for pk, block in picchetti.items():
        st = (block or {}).get("status")
        if st not in (STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE):
            blockers.append(f"picchetto_not_ok:{pk}:{st}")

    p1 = final.get("prob_1")
    px = final.get("prob_x")
    p2 = final.get("prob_2")
    q1 = final.get("quota_1")
    qx = final.get("quota_x")
    q2 = final.get("quota_2")

    if not all(isinstance(v, (int, float)) and v > 0 for v in (p1, px, p2)):
        return {
            "status": EXCLUDED_ZERO_PROBABILITY,
            "reason": "non_positive_probabilities",
            "blocking_reasons": ["non_positive_probabilities"],
            "core_eligible": False,
            "samples": samples,
        }
    if not all(isinstance(v, (int, float)) and v > 0 for v in (q1, qx, q2)):
        return {
            "status": EXCLUDED_CECCHINO_NOT_CALCULABLE,
            "reason": "missing_final_quotas",
            "blocking_reasons": ["missing_final_quotas"] + blockers,
            "core_eligible": False,
            "samples": samples,
        }
    if final.get("status") not in (STATUS_AVAILABLE, STATUS_PARTIAL_LOW_SAMPLE):
        return {
            "status": EXCLUDED_CECCHINO_NOT_CALCULABLE,
            "reason": f"final_status:{final.get('status')}",
            "blocking_reasons": [f"final_status:{final.get('status')}"] + blockers,
            "core_eligible": False,
            "samples": samples,
        }

    return {
        "status": ELIGIBLE_CORE,
        "reason": None,
        "blocking_reasons": blockers,
        "core_eligible": True,
        "samples": samples,
    }
