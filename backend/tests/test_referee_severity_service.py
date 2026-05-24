"""Test classificazione severità arbitro."""

from __future__ import annotations

from app.core.referee_severity_constants import (
    SEVERITY_MEDIUM,
    SEVERITY_PERMISSIVE,
    SEVERITY_SEVERE,
)
from app.services.referee_severity_service import (
    _resolve_data_source,
    classify_severity,
    sample_quality_from_count,
)
from app.models.referee_fixture_card_summary import CARD_SOURCE_DB_TEAM_STATS, CARD_SOURCE_EVENTS


def test_classify_severity_permissive():
    label, _ = classify_severity(3.0, 0.1)
    assert label == SEVERITY_PERMISSIVE


def test_classify_severity_medium():
    label, _ = classify_severity(4.0, 0.1)
    assert label == SEVERITY_MEDIUM


def test_classify_severity_severe():
    label, _ = classify_severity(5.5, 0.0)
    assert label == SEVERITY_SEVERE


def test_classify_severity_red_note():
    _, notes = classify_severity(4.0, 0.35)
    assert notes.get("high_red_incidence") is True


def test_sample_quality_thresholds():
    assert sample_quality_from_count(3) == "low"
    assert sample_quality_from_count(10) == "medium"
    assert sample_quality_from_count(15) == "high"


def test_resolve_data_source():
    assert _resolve_data_source({CARD_SOURCE_DB_TEAM_STATS}) == "db_only"
    assert _resolve_data_source({CARD_SOURCE_EVENTS}) == "api_sports_fetched"
    assert _resolve_data_source({CARD_SOURCE_DB_TEAM_STATS, CARD_SOURCE_EVENTS}) == "mixed"
