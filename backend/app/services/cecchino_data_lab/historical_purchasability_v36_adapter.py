"""Adapter storico Acquistabilità V3.6 (engine canonico V3.5 structural v2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.schemas.cecchino_purchasability_v35_v2 import PURCHASABILITY_V35_V2_FORMULA_VERSION
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_batch,
)
from app.services.cecchino_data_lab.constants import (
    HISTORICAL_PRE_MATCH_EPOCH_LEAD_HOURS,
    HISTORICAL_PRE_MATCH_EPOCH_POLICY_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_QUOTE_REFERENCE_TIMING,
)

MODULE_VERSION = "cecchino_lab_purchasability_historical_v4"
PARITY_STATUS = "historical_bet365_v35_v2_canonical"
DEFAULT_SNAPSHOT_LEAD = timedelta(hours=HISTORICAL_PRE_MATCH_EPOCH_LEAD_HOURS)


def synthetic_pre_match_snapshot_at(
    kickoff: datetime,
    *,
    lead: timedelta = DEFAULT_SNAPSHOT_LEAD,
) -> datetime:
    """Epoch sintetico: kickoff − lead. Solo per contratto snapshot_at < kickoff."""
    return kickoff - lead


def historical_v36_snapshot_provenance() -> dict[str, Any]:
    """Provenance obbligatoria dell'epoch sintetico pre-match."""
    return {
        "snapshot_policy_version": HISTORICAL_PRE_MATCH_EPOCH_POLICY_VERSION,
        "synthetic_timestamp": True,
        "physical_capture_time_known": False,
        "does_not_claim_physical_capture": True,
        "quote_reference": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        "reference_timing": HISTORICAL_QUOTE_REFERENCE_TIMING,
        "inputs_exclude_closing": True,
        "lead_hours": HISTORICAL_PRE_MATCH_EPOCH_LEAD_HOURS,
        "epoch_rule": "kickoff_minus_synthetic_lead",
        "not_a_predictive_feature": True,
        "not_physical_bet365_capture": True,
        "not_quota_available_at_lead": True,
    }


def build_historical_purchasability_v36(
    *,
    kpi_panel: dict[str, Any] | None,
    match: Any,
    season_label: str | None = None,
    competition_name: str | None = None,
    snapshot_lead: timedelta | None = None,
) -> dict[str, Any]:
    """Calcolo per-match via engine canonico frozen — no profilo progressivo V2.

    ``snapshot_lead`` è solo per test di invarianza; default = policy −24h.
    """
    provenance = historical_v36_snapshot_provenance()
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
            "snapshot_provenance": provenance,
        }

    kickoff = getattr(match, "kickoff_at", None)
    lead = snapshot_lead if snapshot_lead is not None else DEFAULT_SNAPSHOT_LEAD
    snapshot_at = (
        synthetic_pre_match_snapshot_at(kickoff, lead=lead) if kickoff is not None else None
    )
    provenance = {
        **provenance,
        "lead_hours": lead.total_seconds() / 3600.0,
    }

    fixture_meta = {
        "today_fixture_id": int(getattr(match, "id", 0) or 0),
        "kickoff": kickoff.isoformat() if kickoff is not None else None,
        "snapshot_at": snapshot_at.isoformat() if snapshot_at is not None else None,
        "home_team": getattr(match, "home_team", None),
        "away_team": getattr(match, "away_team", None),
        "competition": competition_name,
        "season_label": season_label,
        "historical_lab_replay": True,
        **provenance,
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
        "snapshot_provenance": provenance,
        "anti_leakage": {
            "canonical_engine_no_formula_duplication": True,
            "verify_pre_match_snapshot": batch.get("pre_match_verified"),
            "post_match_fields_forbidden": True,
            "inputs_exclude_closing": True,
            **provenance,
        },
    }
