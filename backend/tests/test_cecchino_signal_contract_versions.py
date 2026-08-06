"""Contratto versioni globale: una sola formula V3 operativa ovunque."""

from __future__ import annotations

from app.services.cecchino.cecchino_kpi_signals import KPI_SIGNAL_MARKET_DEFS
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    SIGNAL_AUDIT_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    get_current_signal_contract,
)
from app.services.cecchino.cecchino_signal_explanations import (
    AUDIT_VERSION,
    get_signal_formula_registry,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix
from app.services.cecchino_data_lab.historical_signal_models import MODULE_VERSION
from app.services.cecchino_data_lab.historical_settlement import _period_line


EXPECTED_FORMULA = "cecchino_signals_matrix_v3_draw_dfg_decimal2"
EXPECTED_CONSENSUS = "cecchino_signal_consensus_v1_min_two"
EXPECTED_AUDIT = "cecchino_signal_explanations_v3"


def test_canonical_version_constants():
    assert CURRENT_SIGNAL_FORMULA_VERSION == EXPECTED_FORMULA
    assert SIGNAL_CONSENSUS_POLICY_VERSION == EXPECTED_CONSENSUS
    assert SIGNAL_AUDIT_VERSION == EXPECTED_AUDIT
    assert AUDIT_VERSION == EXPECTED_AUDIT


def test_get_current_signal_contract_payload():
    c = get_current_signal_contract()
    assert c["formula_version"] == EXPECTED_FORMULA
    assert c["formula_label"] == "Formula corrente V3"
    assert c["consensus_policy_version"] == EXPECTED_CONSENSUS
    assert c["audit_version"] == EXPECTED_AUDIT
    assert c["decimal_policy"]["scope"] == "draw_formulas_only"
    assert c["decimal_policy"]["quantum"] == "0.01"
    assert c["decimal_policy"]["rounding"] == "ROUND_HALF_UP"
    assert c["operational_signal_semantics"] == "acquired_only"
    assert c["legacy_versions_operational"] is False


def test_build_signals_matrix_tags_current_versions():
    m = build_signals_matrix(
        q1=2.10,
        qx=3.20,
        q2=3.40,
        sample_home_away_split=20,
        under_2_5_cecchino_odd=1.85,
    )
    assert m["status"] == "available"
    assert m["formula_version"] == EXPECTED_FORMULA
    assert m["consensus_policy_version"] == EXPECTED_CONSENSUS


def test_formula_registry_matches_contract():
    reg = get_signal_formula_registry()
    assert reg["formula_version"] == EXPECTED_FORMULA
    assert reg["consensus_policy_version"] == EXPECTED_CONSENSUS
    assert reg["audit_version"] == EXPECTED_AUDIT
    contract = reg.get("signal_contract") or {}
    assert contract.get("formula_version") == EXPECTED_FORMULA
    entries = reg.get("entries") or []
    assert len(entries) == 26
    for e in entries:
        assert e["formula_version"] == EXPECTED_FORMULA
        assert e["consensus_policy_version"] == EXPECTED_CONSENSUS
        assert e["audit_version"] == EXPECTED_AUDIT


def test_kpi_registry_has_19_markets_with_period_line():
    assert len(KPI_SIGNAL_MARKET_DEFS) == 19
    keys = {d["selection_key"] for d in KPI_SIGNAL_MARKET_DEFS}
    for key in (
        "HOME",
        "DRAW",
        "AWAY",
        "HOME_PT",
        "DRAW_PT",
        "AWAY_PT",
        "ONE_X",
        "X_TWO",
        "ONE_TWO",
        "OVER_1_5",
        "UNDER_1_5",
        "OVER_2_5",
        "UNDER_2_5",
        "OVER_3_5",
        "UNDER_3_5",
        "OVER_PT_0_5",
        "UNDER_PT_0_5",
        "OVER_PT_1_5",
        "UNDER_PT_1_5",
    ):
        assert key in keys
        period, line = _period_line(key)
        assert period in ("FT", "HT")


def test_lab_signals_af_module_version_v2():
    assert MODULE_VERSION == "cecchino_lab_signals_af_v2_current_v3_consensus"
