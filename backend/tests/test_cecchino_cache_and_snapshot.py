"""Test cache Cecchino v0.2 e completezza input_snapshot."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cecchino.cecchino_constants import (
    CECCHINO_VERSION,
    INPUT_SNAPSHOT_CONTEXT_KEYS,
    LEAKAGE_PASSED,
)
from app.services.cecchino.cecchino_service import (
    _stored_row_is_usable,
    input_snapshot_is_complete,
)


def _legacy_snapshot() -> dict:
    """Formato Fase 1 (coppie picchetto, senza wdl per contesto)."""
    return {
        "home_away": {"home": {"wins": 1, "draws": 0, "losses": 0}, "away": {"wins": 0, "draws": 1, "losses": 0}},
        "totals": {"home": {"wins": 2, "draws": 0, "losses": 0}, "away": {"wins": 1, "draws": 0, "losses": 1}},
    }


def _v02_snapshot() -> dict:
    snap: dict = {}
    for key in INPUT_SNAPSHOT_CONTEXT_KEYS:
        snap[key] = {
            "key": key,
            "label": key,
            "wdl": {"wins": 3, "draws": 1, "losses": 2},
            "sample_count": 6,
            "target_sample": 5 if "recent" in key else None,
            "status": "available",
            "fixture_ids": [1, 2, 3],
        }
    return snap


def test_input_snapshot_is_complete_v02():
    assert input_snapshot_is_complete(_v02_snapshot()) is True


def test_input_snapshot_incomplete_legacy():
    assert input_snapshot_is_complete(None) is False
    assert input_snapshot_is_complete(_legacy_snapshot()) is False
    assert input_snapshot_is_complete({}) is False


def test_stored_row_not_usable_with_legacy_snapshot():
    row = SimpleNamespace(
        output_json={
            "final": {"quota_1": 2.0},
            "data_quality": {"leakage_check": {"status": LEAKAGE_PASSED}},
        },
        input_snapshot_json=_legacy_snapshot(),
    )
    assert _stored_row_is_usable(row) is False


def test_stored_row_v02_without_signals_not_usable():
    """Cache v0.2 senza signals_matrix.available → ricalcolo."""
    row = SimpleNamespace(
        output_json={
            "final": {"quota_1": 2.0},
            "data_quality": {
                "leakage_check": {
                    "status": LEAKAGE_PASSED,
                    "target_kickoff": "2025-06-15T15:00:00+00:00",
                    "max_source_fixture_date": "2025-06-01T12:00:00+00:00",
                    "checked_at": "2025-06-04T10:00:00+00:00",
                },
            },
        },
        input_snapshot_json=_v02_snapshot(),
    )
    assert _stored_row_is_usable(row) is False


def test_cecchino_version_is_v03():
    assert CECCHINO_VERSION == "cecchino_v0_3_signals_matrix"


def test_stored_row_not_usable_without_signals_matrix():
    row = SimpleNamespace(
        output_json={
            "final": {"quota_1": 2.0},
            "data_quality": {"leakage_check": {"status": LEAKAGE_PASSED}},
            "signals_matrix": {"status": "pending_formula_extraction"},
        },
        input_snapshot_json=_v02_snapshot(),
    )
    assert _stored_row_is_usable(row) is False


def test_stored_row_usable_v03_with_signals():
    row = SimpleNamespace(
        output_json={
            "final": {"quota_1": 2.0},
            "data_quality": {"leakage_check": {"status": LEAKAGE_PASSED}},
            "signals_matrix": {
                "status": "available",
                "rows": [{"key": "draw"}],
            },
        },
        input_snapshot_json=_v02_snapshot(),
    )
    assert _stored_row_is_usable(row) is True
