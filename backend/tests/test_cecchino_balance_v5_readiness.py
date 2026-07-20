"""Test readiness/governance Balance v5 — Fase 2/3 Step 2C."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.cecchino.cecchino_balance_v5_readiness import (
    build_balance_decision_contract,
    build_balance_prospective_progress,
    build_balance_readiness_decision,
    build_balance_readiness_dossier_files,
    build_balance_scientific_gates,
    compute_readiness_hash,
    record_balance_governance_decision,
)
from app.services.cecchino.cecchino_balance_v5_readiness_policy import (
    BALANCE_GOVERNANCE_CONFIRM_TOKEN,
    BALANCE_READINESS_POLICY_VERSION,
    MIN_PROSPECTIVE_SETTLED_GLOBAL,
    build_balance_readiness_policy_payload,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
)


def _empty_eval_query():
    q = MagicMock()
    q.filter.return_value = q
    q.count.return_value = 0
    q.all.return_value = []
    q.limit.return_value = q
    q.group_by.return_value = q
    q.having.return_value = q
    q.order_by.return_value = q
    q.one_or_none.return_value = None
    return q


def test_policy_immutable_and_thresholds():
    pol = build_balance_readiness_policy_payload()
    assert pol["version"] == BALANCE_READINESS_POLICY_VERSION
    assert pol["immutable"] is True
    assert pol["MIN_PROSPECTIVE_SETTLED_GLOBAL"] == MIN_PROSPECTIVE_SETTLED_GLOBAL == 1500
    assert pol["MIN_PROSPECTIVE_CALENDAR_DAYS"] == 90
    assert pol["MIN_TEMPORAL_FOLDS"] == 3


def test_decision_contract_blocks_signals():
    c = build_balance_decision_contract()
    assert "continue_monitoring" in c["allowed_now"]
    assert "freeze_as_descriptive" in c["allowed_now"]
    assert "request_formula_review" in c["allowed_now"]
    blocked = c["blocked_until_separate_implementation"]
    assert "manual_signal_integration_approved" in blocked
    assert c["decisions"]["manual_signal_integration_approved"]["allowed"] is False


def test_baseline_zero_prospective_decision():
    db = MagicMock()
    db.query.return_value = _empty_eval_query()

    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_technical_gates",
        return_value={"gates": [{"status": "pass", "promotion_blocking": True}]},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_scientific_gates",
        return_value={"gates": [{"status": "wait", "promotion_blocking": True}], "prospective_settled": 0},
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_prospective_progress",
        return_value={
            "ratios": {
                "prospective_settled": {"numerator": 0, "denominator": 1500},
            },
            "earliest_theoretical_review_at": None,
        },
    ):
        decision = build_balance_readiness_decision(
            db, filters={"date_from": date(2026, 1, 1), "date_to": date(2026, 7, 1)}
        )

    assert decision["operational_status"] == "official_descriptive_monitored"
    assert decision["scientific_maturity"] == "prospective_not_started"
    assert decision["manual_review_status"] == "not_eligible"
    assert decision["signals_integration_status"] == "blocked"
    assert decision["current_decision"] == "continue_monitoring"
    assert decision["earliest_theoretical_review_at"] is None


def test_scientific_gates_wait_below_sample():
    db = MagicMock()
    rows = [MagicMock(competition_id=1, f36_class="a", dominance_class="a",
                      draw_credibility_class="a", gap_class="a",
                      scan_date=date(2026, 1, 1), kickoff=None) for _ in range(1499)]
    q = MagicMock()
    q.all.return_value = rows
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._prospective_settled_q",
        return_value=q,
    ):
        sci = build_balance_scientific_gates(
            db, filters={"date_from": None, "date_to": None, "competition_id": None}
        )
    sample_gate = next(g for g in sci["gates"] if g["key"] == "minimum_prospective_settled")
    assert sample_gate["status"] == "wait"
    assert sample_gate["numerator"] == 1499
    assert sample_gate["denominator"] == 1500


def test_scientific_gates_pass_at_threshold():
    db = MagicMock()
    rows = [MagicMock(competition_id=1, f36_class="a", dominance_class="a",
                      draw_credibility_class="a", gap_class="a",
                      scan_date=date(2026, 1, 1), kickoff=None) for _ in range(1500)]
    q = MagicMock()
    q.all.return_value = rows
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._prospective_settled_q",
        return_value=q,
    ):
        sci = build_balance_scientific_gates(
            db, filters={"date_from": None, "date_to": None, "competition_id": None}
        )
    sample_gate = next(g for g in sci["gates"] if g["key"] == "minimum_prospective_settled")
    assert sample_gate["status"] == "pass"
    assert sample_gate["numerator"] == 1500


def test_historical_does_not_increment_progress_ratios():
    db = MagicMock()
    # Only historical rows would appear if prospective query returns empty
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness._base_q",
        return_value=_empty_eval_query(),
    ):
        progress = build_balance_prospective_progress(
            db, filters={"date_from": None, "date_to": None, "competition_id": None}
        )
    assert progress["ratios"]["prospective_settled"]["numerator"] == 0
    assert progress["earliest_theoretical_review_at"] is None


def test_readiness_hash_excludes_timestamps():
    a = compute_readiness_hash(
        {
            "snapshot_date": "2026-07-20",
            "prospective_settled": 0,
            "created_at": "x",
            "updated_at": "y",
        }
    )
    b = compute_readiness_hash(
        {
            "snapshot_date": "2026-07-20",
            "prospective_settled": 0,
            "created_at": "different",
            "updated_at": "also",
        }
    )
    assert a == b


def test_governance_token_and_signal_rejection():
    db = MagicMock()
    rejected = record_balance_governance_decision(
        db,
        decision="manual_signal_integration_approved",
        confirm_token=BALANCE_GOVERNANCE_CONFIRM_TOKEN,
        commit=False,
    )
    assert rejected["status"] == "rejected"
    assert rejected["http_status"] == 422
    assert rejected["error"] == "signal_integration_requires_separate_explicit_implementation"

    bad_token = record_balance_governance_decision(
        db,
        decision="continue_monitoring",
        confirm_token="WRONG",
        commit=False,
    )
    assert bad_token["status"] == "rejected"
    assert bad_token["error"] == "invalid_confirm_token"


def test_export_v9_includes_readiness_files():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v9"
    req = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    for name in (
        "balance_readiness_overview.json",
        "balance_readiness_policy.json",
        "balance_readiness_gates.csv",
        "balance_pillar_readiness.json",
        "balance_prospective_progress.json",
        "balance_current_decision.json",
        "balance_decision_contract.json",
        "balance_prospective_collection_health.json",
        "balance_governance_decisions.csv",
    ):
        assert name in req


def test_dossier_files_shape():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.build_balance_readiness_full_report",
        return_value={
            "overview": {"current_decision": "continue_monitoring"},
            "technical_gates": {"gates": []},
            "scientific_gates": {"gates": []},
            "pillars": {},
            "prospective_progress": {},
            "current_decision": {"decision": "continue_monitoring"},
            "decision_contract": build_balance_decision_contract(),
            "prospective_collection_health": {"status": "not_started"},
            "policy": build_balance_readiness_policy_payload(),
        },
    ), patch(
        "app.services.cecchino.cecchino_balance_v5_readiness.list_balance_readiness_history",
        return_value={"items": [], "count": 0},
    ):
        files = build_balance_readiness_dossier_files(db)
    assert "README.md" in files
    assert "balance_readiness_overview.json" in files
    assert b"Balance v5 Readiness" in files["README.md"]
