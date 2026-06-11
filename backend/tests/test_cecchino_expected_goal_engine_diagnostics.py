"""Test Expected Goal Engine diagnostics — Cecchino Fase 50."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_expected_goal_engine_diagnostics import (
    VERSION,
    _VARIABLE_SPECS,
    _confidence,
    build_expected_goal_engine_diagnostics,
    build_expected_goal_engine_diagnostics_for_today_row,
)


def _var(key: str, status: str = "available") -> dict:
    spec = next(s for s in _VARIABLE_SPECS if s["key"] == key)
    return {
        "key": key,
        "label": spec["label"],
        "block": spec["block"],
        "weight": spec.get("weight"),
        "required": spec["required"],
        "role": spec["role"],
        "available": status == "available",
        "availability_status": status,
        "value": 1.0 if status == "available" else None,
        "source": "test" if status == "available" else None,
        "source_field": "test.field" if status == "available" else None,
        "sample_size": 10 if status == "available" else None,
        "warnings": [],
    }


def test_version_and_catalog_counts():
    block_a = [s for s in _VARIABLE_SPECS if s["block"] == "production_goal"]
    block_b = [s for s in _VARIABLE_SPECS if s["block"] == "temporal_distribution"]
    block_c = [s for s in _VARIABLE_SPECS if s["block"] == "advanced_correctors"]
    assert len(block_a) == 8
    assert len(block_b) == 7
    assert len(block_c) == 5
    assert sum(s["weight"] for s in block_a) == pytest.approx(1.0)
    assert sum(s["weight"] for s in block_b) == pytest.approx(1.0)


def test_required_and_advanced_totals():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 100
    fixture.home_team_id = 1
    fixture.away_team_id = 2

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_variables",
        return_value={s["key"]: _var(s["key"], "missing") for s in _VARIABLE_SPECS},
    ):
        result = build_expected_goal_engine_diagnostics(db, fixture)

    assert result["version"] == VERSION
    assert result["version"] == "expected_goal_engine_diagnostics_v1"
    assert result["coverage"]["required_total"] == 15
    assert result["coverage"]["advanced_total"] == 5
    assert len(result["blocks"]["production_goal"]) == 8
    assert len(result["blocks"]["temporal_distribution"]) == 7
    assert len(result["blocks"]["advanced_correctors"]) == 5


def test_missing_variables_not_available():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 101

    missing_vars = {s["key"]: _var(s["key"], "missing") for s in _VARIABLE_SPECS}
    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_variables",
        return_value=missing_vars,
    ):
        result = build_expected_goal_engine_diagnostics(db, fixture)

    for block_rows in result["blocks"].values():
        for row in block_rows:
            if row["availability_status"] == "missing":
                assert row["available"] is False


@pytest.mark.parametrize(
    ("available_count", "expected_confidence"),
    [
        (12, "high"),
        (9, "medium"),
        (6, "partial"),
        (3, "insufficient"),
    ],
)
def test_confidence_thresholds(available_count: int, expected_confidence: str):
    assert _confidence(available_count, 15) == expected_confidence


def test_production_goal_ready_with_five_available():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 102

    vars_map = {s["key"]: _var(s["key"], "missing") for s in _VARIABLE_SPECS}
    prod_keys = [s["key"] for s in _VARIABLE_SPECS if s["block"] == "production_goal"][:5]
    for key in prod_keys:
        vars_map[key] = _var(key, "available")
    vars_map["rolling_avg_goals_last_10"] = _var("rolling_avg_goals_last_10", "available")

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_variables",
        return_value=vars_map,
    ):
        result = build_expected_goal_engine_diagnostics(db, fixture)

    assert result["engine_readiness"]["production_goal_ready"] is True


def test_temporal_distribution_ready_with_four_available():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 103

    vars_map = {s["key"]: _var(s["key"], "missing") for s in _VARIABLE_SPECS}
    temp_keys = [s["key"] for s in _VARIABLE_SPECS if s["block"] == "temporal_distribution"][:4]
    for key in temp_keys:
        vars_map[key] = _var(key, "available")

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_variables",
        return_value=vars_map,
    ):
        result = build_expected_goal_engine_diagnostics(db, fixture)

    assert result["engine_readiness"]["temporal_distribution_ready"] is True


def test_available_variables_have_source():
    db = MagicMock()
    fixture = MagicMock()
    fixture.id = 104

    vars_map = {s["key"]: _var(s["key"], "available") for s in _VARIABLE_SPECS}

    with patch(
        "app.services.cecchino.cecchino_expected_goal_engine_diagnostics._resolve_variables",
        return_value=vars_map,
    ):
        result = build_expected_goal_engine_diagnostics(db, fixture)

    for block_rows in result["blocks"].values():
        for row in block_rows:
            if row["availability_status"] == "available":
                assert row["source"] is not None
                assert row["source_field"] is not None


def test_today_row_missing_fixture():
    row = MagicMock()
    row.local_fixture_id = None
    result = build_expected_goal_engine_diagnostics_for_today_row(MagicMock(), row)
    assert result["status"] == "insufficient_data"
    assert "missing_local_fixture_id" in result["warnings"]


def test_detail_includes_diagnostics_key():
    import inspect

    from app.services.cecchino import cecchino_today_service

    source = inspect.getsource(cecchino_today_service)
    assert "expected_goal_engine_diagnostics" in source
    assert "build_expected_goal_engine_diagnostics_for_today_row" in source
