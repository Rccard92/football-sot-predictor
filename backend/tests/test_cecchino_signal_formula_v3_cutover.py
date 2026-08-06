"""Test versioning V3 e cutover sync current-only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_signal_activation import CecchinoSignalActivation
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_signal_aggregation import (
    SignalFormulaVersionNotAllowed,
    resolve_operational_signal_formula_version,
)
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    LEGACY_SIGNAL_FORMULA_VERSION,
    PREVIOUS_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    is_current_signal_matrix,
    normalize_formula_version,
)
from app.services.cecchino.cecchino_signal_sync import sync_cecchino_signal_activations
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def test_builder_produces_v3():
    matrix = build_signals_matrix(q1=2.5, qx=3.2, q2=2.9, sample_home_away_split=16)
    assert matrix["formula_version"] == CURRENT_SIGNAL_FORMULA_VERSION
    assert matrix["formula_version"] == "cecchino_signals_matrix_v3_draw_dfg_decimal2"
    assert matrix["consensus_policy_version"] == SIGNAL_CONSENSUS_POLICY_VERSION


def test_normalize_formula_version_aliases():
    assert normalize_formula_version(None) == LEGACY_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version("current") == CURRENT_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version("v3") == CURRENT_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version("v2") == PREVIOUS_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version(PREVIOUS_SIGNAL_FORMULA_VERSION) == PREVIOUS_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version("legacy") == LEGACY_SIGNAL_FORMULA_VERSION
    assert normalize_formula_version("v1") == LEGACY_SIGNAL_FORMULA_VERSION


@pytest.mark.parametrize(
    ("matrix", "expected"),
    [
        (None, False),
        ({}, False),
        ({"status": "available"}, False),
        ({"status": "available", "formula_version": None}, False),
        ({"status": "available", "formula_version": LEGACY_SIGNAL_FORMULA_VERSION}, False),
        ({"status": "available", "formula_version": PREVIOUS_SIGNAL_FORMULA_VERSION}, False),
        ({"status": "insufficient_data", "formula_version": CURRENT_SIGNAL_FORMULA_VERSION}, False),
        ({"status": "available", "formula_version": CURRENT_SIGNAL_FORMULA_VERSION}, True),
    ],
)
def test_is_current_signal_matrix(matrix, expected: bool):
    assert is_current_signal_matrix(matrix) is expected


@pytest.mark.parametrize(
    "raw",
    ["all", "legacy", "v1", "v2", PREVIOUS_SIGNAL_FORMULA_VERSION, "unknown_v9"],
)
def test_operational_filter_rejects_non_current(raw: str):
    with pytest.raises(SignalFormulaVersionNotAllowed):
        resolve_operational_signal_formula_version(raw)


@pytest.mark.parametrize(
    "raw",
    ["current", "v3", CURRENT_SIGNAL_FORMULA_VERSION, None, ""],
)
def test_operational_filter_accepts_current(raw):
    assert resolve_operational_signal_formula_version(raw) == CURRENT_SIGNAL_FORMULA_VERSION


def _fixture_with_matrix(formula_version: str | None) -> MagicMock:
    matrix = {
        "status": STATUS_AVAILABLE,
        "formula_version": formula_version,
        "consensus_policy_version": SIGNAL_CONSENSUS_POLICY_VERSION,
        "inputs": {"q1": 2.5, "qx": 3.2, "q2": 2.9, "avg_q": 2.87, "diff_1_2": 0.4},
        "rows": [
            {
                "key": "draw",
                "label": "SEGNO X",
                "signals": {"excel_d": "SI", "excel_e": "SI", "excel_f": "NO", "excel_g": "NO"},
                "consensus": {
                    "consensus_yes_count": 2,
                    "consensus_required_count": 2,
                    "consensus_passed": True,
                    "is_acquired": True,
                    "acquisition_status": "acquired_consensus",
                    "consensus_yes_columns": ["EXCEL_D", "EXCEL_E"],
                },
            },
        ],
    }
    row = MagicMock()
    row.id = 1
    row.scan_date = date(2026, 8, 6)
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.home_team_name = "Home"
    row.away_team_name = "Away"
    row.kickoff_utc = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
    row.league_name = "Serie A"
    row.country_name = "Italy"
    row.provider_fixture_id = 1001
    row.cecchino_output_json = {"signals_matrix": matrix, "final": {"status": STATUS_AVAILABLE}}
    row.kpi_panel_json = {
        "rows": [
            {
                "market_key": "1X2_X",
                "quota_book": 3.2,
                "quota_cecchino": 3.0,
                "status": "available",
            },
        ],
    }
    row.ft_home_goals = None
    row.ft_away_goals = None
    row.ht_home_goals = None
    row.ht_away_goals = None
    return row


def test_sync_rejects_missing_version():
    db = MagicMock()
    row = _fixture_with_matrix(None)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    counts = sync_cecchino_signal_activations(db, 1)
    assert counts["skipped_non_current_formula_matrix"] == 1
    assert counts["created"] == 0


def test_sync_rejects_v1():
    db = MagicMock()
    row = _fixture_with_matrix(LEGACY_SIGNAL_FORMULA_VERSION)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    counts = sync_cecchino_signal_activations(db, 1)
    assert counts["skipped_non_current_formula_matrix"] == 1


def test_sync_rejects_v2_does_not_rename():
    db = MagicMock()
    row = _fixture_with_matrix(PREVIOUS_SIGNAL_FORMULA_VERSION)
    db.get.return_value = row
    db.scalars.return_value.all.return_value = []
    counts = sync_cecchino_signal_activations(db, 1)
    assert counts["skipped_non_current_formula_matrix"] == 1
    assert counts["created"] == 0
    # matrice invariata
    assert row.cecchino_output_json["signals_matrix"]["formula_version"] == PREVIOUS_SIGNAL_FORMULA_VERSION


def test_sync_v3_does_not_deactivate_v2(monkeypatch):
    db = MagicMock()
    row = _fixture_with_matrix(CURRENT_SIGNAL_FORMULA_VERSION)
    db.get.return_value = row

    v2_act = MagicMock(spec=CecchinoSignalActivation)
    v2_act.model_key = "F"
    v2_act.signal_group = "DRAW"
    v2_act.source_column = "EXCEL_D"
    v2_act.signal_formula_version = PREVIOUS_SIGNAL_FORMULA_VERSION
    v2_act.is_current = True

    # Query existing solo V3 → lista vuota (V2 non in scope)
    db.scalars.return_value.all.return_value = []

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_sync.signal_has_value_from_kpi_context",
        lambda *a, **k: (True, "ok", {}),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_signal_sync.resolve_kpi_odds_for_activation",
        lambda *a, **k: {
            "quota_book": Decimal("3.2"),
            "quota_cecchino": Decimal("3.0"),
            "edge_pct": Decimal("6.0"),
            "rating": Decimal("1"),
        },
    )

    counts = sync_cecchino_signal_activations(db, 1, min_book_odds={"1X2_X": Decimal("1.01")})
    assert counts["skipped_non_current_formula_matrix"] == 0
    # V2 non toccato
    assert v2_act.is_current is True
