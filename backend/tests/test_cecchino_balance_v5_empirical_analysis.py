"""Test analisi empirica Balance v5 Step 2B."""

from __future__ import annotations

from app.services.cecchino.cecchino_balance_v5_empirical_analysis import (
    BALANCE_EMPIRICAL_ANALYSIS_VERSION,
    BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION,
    MIN_SETTLED_GLOBAL,
    build_balance_pillar_evidence_status,
    build_statistical_policy_payload,
)
from app.services.cecchino.cecchino_balance_v5_empirical_analysis_stats import (
    benjamini_hochberg,
    brier_score,
    chi_square_independence,
    deterministic_seed_int,
    expected_calibration_error,
    kruskal_wallis,
    proportion_block,
    spearman_safe,
)
from app.services.cecchino.cecchino_balance_v5_empirical_registry import (
    resolve_class,
    build_class_registry_payload,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
)
from app.services.cecchino.cecchino_monitoring_cohorts import COHORT_HISTORICAL_DIAGNOSTIC


def test_policy_immutable_constants():
    pol = build_statistical_policy_payload()
    assert pol["version"] == BALANCE_EMPIRICAL_STATISTICAL_POLICY_VERSION
    assert pol["MIN_SETTLED_GLOBAL"] == MIN_SETTLED_GLOBAL
    assert pol["immutable"] is True


def test_registry_resolves_italian_labels():
    r = resolve_class("f36", "Squilibrio")
    assert r["canonical_key"] == "imbalance"
    assert r["is_registered"] is True
    unk = resolve_class("f36", "ClasseInesistenteXYZ")
    assert unk["is_registered"] is False
    assert "non registrata" in unk["label_it"].lower() or unk["label_it"] == "Classe non registrata"
    reg = build_class_registry_payload()
    assert "f36" in reg["pillars"]


def test_wilson_and_seed_deterministic():
    a = proportion_block(50, 100)
    assert a["rate_pct"] == 50.0
    assert a["ci95"]["lower_pct"] is not None
    s1 = deterministic_seed_int(
        analysis_version="v",
        policy_version="p",
        filters={"date_from": "2026-01-01"},
        pillar="f36",
        metric="m",
        group_key="g",
    )
    s2 = deterministic_seed_int(
        analysis_version="v",
        policy_version="p",
        filters={"date_from": "2026-01-01"},
        pillar="f36",
        metric="m",
        group_key="g",
    )
    assert s1 == s2


def test_chi_square_and_kruskal():
    chi = chi_square_independence([[30, 10, 10], [10, 30, 10], [10, 10, 30]])
    assert chi["status"] == "ok"
    assert chi["cramers_v"] is not None
    kw = kruskal_wallis([[1, 2, 3], [10, 11, 12], [20, 21, 22]])
    assert kw["status"] == "ok"
    assert kw["H"] is not None


def test_bh_and_calibration_brier():
    adj = benjamini_hochberg([0.01, 0.04, 0.03, None])
    assert adj[0] is not None
    assert adj[3] is None
    y = [0, 1, 0, 1, 1, 0, 1, 0, 1, 0] * 5
    p = [0.1, 0.9, 0.2, 0.8, 0.7, 0.3, 0.85, 0.15, 0.75, 0.25] * 5
    assert brier_score(y, p) is not None
    ece = expected_calibration_error(y, p, n_bins=5)
    assert ece["status"] == "ok"
    assert ece["ece"] is not None


def test_evidence_caps_historical_diagnostic():
    ev = build_balance_pillar_evidence_status(
        pillar="f36",
        sample_size=400,
        evidence_scope=COHORT_HISTORICAL_DIAGNOSTIC,
        primary_metric={"ok": True},
    )
    assert ev["status"] == "exploratory_evidence"
    assert ev["promotion_eligible"] is False
    assert ev["formula_change_recommended"] is False


def test_export_v7_requires_analysis_files():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v7"
    req = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    for name in (
        "balance_empirical_analysis_overview.json",
        "f36_empirical_summary.json",
        "dominance_empirical_summary.json",
        "draw_credibility_empirical_summary.json",
        "gap_empirical_summary.json",
        "pillar_evidence_status.json",
        "empirical_statistical_policy.json",
    ):
        assert name in req


def test_spearman_insufficient():
    assert spearman_safe([1, 2], [2, 1])["status"] == "insufficient_data"
