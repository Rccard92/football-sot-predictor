"""Test confidence e applicabilità candidati availability."""

from datetime import date, datetime, timezone

from app.models.player_availability import (
    SCOPE_PROVIDER_CURRENT,
    SCOPE_PROVIDER_DATE_RANGE,
)
from app.services.availability.providers.availability_confidence import (
    apply_confidence_scores,
    score_sidelined_candidate,
    split_applicable,
)
from app.services.availability.providers.base import SOURCE_API_FOOTBALL_SIDELINED
from app.services.availability.providers.types import NormalizedAvailabilityCandidate


def _sidelined_candidate(**kwargs) -> NormalizedAvailabilityCandidate:
    base = dict(
        fixture_id=1,
        api_fixture_id=100,
        season=2025,
        league_id=1,
        api_league_id=135,
        team_id=10,
        api_team_id=487,
        team_name="Home",
        player_id=None,
        api_player_id=99,
        player_name="Test Player",
        availability_status="injured",
        availability_type="injury",
        reason="Knee Injury",
        source=SOURCE_API_FOOTBALL_SIDELINED,
        source_detail="api_football_sidelined_player",
        record_scope="",
        confidence="LOW",
        applicability_status="candidate",
        applicability_reason=None,
        raw_json={},
    )
    base.update(kwargs)
    return NormalizedAvailabilityCandidate(**base)


def test_sidelined_date_range_high():
    c = _sidelined_candidate(
        start_date=date(2025, 5, 10),
        end_date=date(2025, 5, 20),
    )
    score_sidelined_candidate(c, kickoff=date(2025, 5, 15))
    assert c.confidence == "HIGH"
    assert c.record_scope == SCOPE_PROVIDER_DATE_RANGE
    assert c.applicability_status == "applied"


def test_sidelined_open_ended_medium():
    c = _sidelined_candidate(
        start_date=date(2025, 5, 1),
        end_date=None,
        raw_json={"type": "Still sidelined"},
    )
    score_sidelined_candidate(c, kickoff=date(2025, 5, 15))
    assert c.confidence == "MEDIUM"
    assert c.record_scope == SCOPE_PROVIDER_CURRENT


def test_sidelined_missing_dates_low():
    c = _sidelined_candidate(start_date=None, end_date=None)
    score_sidelined_candidate(c, kickoff=date(2025, 5, 15))
    assert c.confidence == "LOW"
    assert c.applicability_status == "not_applied"
    assert c.applicability_reason == "missing_date_window"


def test_split_applicable_only_high_medium():
    fx = type("Fx", (), {"kickoff_at": datetime(2025, 5, 15, 15, 0, tzinfo=timezone.utc)})()
    high = _sidelined_candidate(
        start_date=date(2025, 5, 10),
        end_date=date(2025, 5, 20),
    )
    low = _sidelined_candidate(start_date=None, end_date=None)
    apply_confidence_scores([high, low], fx_by_api_id={100: fx})
    applied, not_applied = split_applicable([high, low])
    assert len(applied) == 1
    assert len(not_applied) == 1
    assert applied[0].confidence == "HIGH"
