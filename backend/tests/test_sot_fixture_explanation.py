import pytest

from app.services.sot_prediction_service import WEIGHTS_BASELINE_V0_1
from app.services.sot_fixture_explanation_service import (
    _components_v01,
    _outcome_sot,
    _post_audit_judgment,
)


def test_outcome_sot_buckets():
    assert _outcome_sot(0.1) == "Centrata"
    assert _outcome_sot(0.5) == "Vicina"
    assert _outcome_sot(1.0) == "Da controllare"
    assert _outcome_sot(2.0) == "Errata"


def test_post_audit_judgment_buckets():
    assert _post_audit_judgment(0.4) == "Ottima"
    assert _post_audit_judgment(0.9) == "Vicina"
    assert _post_audit_judgment(1.2) == "Accettabile"
    assert _post_audit_judgment(2.0) == "Da analizzare"


def test_components_v01_length_and_contribution():
    raw = {
        "weights": dict(WEIGHTS_BASELINE_V0_1),
        "resolved_inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "inputs": {k: 4.0 for k in WEIGHTS_BASELINE_V0_1},
        "expected_sot": 4.0,
    }
    comps = _components_v01(raw, 4.0)
    assert len(comps) == len(WEIGHTS_BASELINE_V0_1)
    s = sum(float(c["contribution"]) for c in comps)
    assert s == pytest.approx(4.0, rel=1e-3)
