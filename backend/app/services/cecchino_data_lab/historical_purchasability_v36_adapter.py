"""Adapter storico Acquistabilità V3.6 (engine canonico V3.5 structural v2)."""

from __future__ import annotations

from typing import Any

from app.schemas.cecchino_purchasability_v35_v2 import PURCHASABILITY_V35_V2_FORMULA_VERSION
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_batch,
)

MODULE_VERSION = "cecchino_lab_purchasability_historical_v4"
PARITY_STATUS = "historical_bet365_v35_v2_canonical"


def build_historical_purchasability_v36(
    *,
    kpi_panel: dict[str, Any] | None,
    match: Any,
    season_label: str | None = None,
    competition_name: str | None = None,
) -> dict[str, Any]:
    """Calcolo per-match via engine canonico frozen — no profilo progressivo V2."""
    if not isinstance(kpi_panel, dict) or not kpi_panel.get("rows"):
        return {
            "module_version": MODULE_VERSION,
            "formula_version": PURCHASABILITY_V35_V2_FORMULA_VERSION,
            "display_policy": BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
            "execution_status": "unavailable",
            "parity_status": PARITY_STATUS,
            "status": "unavailable",
            "reason": "missing_kpi_panel",
            "markets": [],
            "does_not_affect_eligibility": True,
        }

    fixture_meta = {
        "today_fixture_id": int(getattr(match, "id", 0) or 0),
        "kickoff": match.kickoff_at.isoformat() if getattr(match, "kickoff_at", None) else None,
        "snapshot_at": match.kickoff_at.isoformat() if getattr(match, "kickoff_at", None) else None,
        "home_team": getattr(match, "home_team", None),
        "away_team": getattr(match, "away_team", None),
        "competition": competition_name,
        "season_label": season_label,
        "historical_lab_replay": True,
    }

    batch = calculate_purchasability_v35_v2_batch(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
    )

    items = batch.get("items") if isinstance(batch.get("items"), list) else []
    scored = [it for it in items if isinstance(it, dict) and it.get("status") == "score"]
    gate_failed = [it for it in items if isinstance(it, dict) and it.get("status") == "gate_failed"]

    if not items:
        execution_status = "unavailable"
    elif scored:
        execution_status = "computed"
    elif gate_failed:
        execution_status = "gate_failed_partial"
    else:
        execution_status = "not_calculable"

    markets_out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        mk = it.get("market_key")
        ref = it.get("reference") if isinstance(it.get("reference"), dict) else {}
        markets_out.append(
            {
                "market_key": mk,
                "score": ref.get("score"),
                "class": ref.get("class"),
                "status": it.get("status"),
                "gate_status": it.get("gate_status"),
                "formula_version": it.get("formula_version") or PURCHASABILITY_V35_V2_FORMULA_VERSION,
            }
        )

    return {
        "module_version": MODULE_VERSION,
        "formula_version": PURCHASABILITY_V35_V2_FORMULA_VERSION,
        "display_policy": BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
        "engine_batch": batch,
        "execution_status": execution_status,
        "parity_status": PARITY_STATUS,
        "status": batch.get("status") or execution_status,
        "markets": markets_out,
        "summary": batch.get("summary"),
        "pre_match_only": True,
        "contains_post_match_fields": False,
        "does_not_affect_eligibility": True,
        "anti_leakage": {
            "canonical_engine_no_formula_duplication": True,
            "verify_pre_match_snapshot": batch.get("pre_match_verified"),
            "post_match_fields_forbidden": True,
        },
    }
