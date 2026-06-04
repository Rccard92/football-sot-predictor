"""Test recupero dati Cecchino — PIT, competition scope, sample parziale."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_constants import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    WARNING_LOW_SAMPLE,
)
from app.services.cecchino.cecchino_engine import compute_picchetto
from app.services.cecchino.cecchino_fixture_history import (
    LEAKAGE_FAILED,
    LEAKAGE_PASSED,
    audit_leakage,
    take_last_n,
    wdl_from_fixtures,
)
from app.services.sot_feature_math import fixture_key_before


def _fx(
    fid: int,
    kickoff: datetime,
    *,
    home: int,
    away: int,
    competition_id: int = 1,
    status: str = "FT",
    goals_home: int = 1,
    goals_away: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=fid,
        kickoff_at=kickoff,
        home_team_id=home,
        away_team_id=away,
        competition_id=competition_id,
        status=status,
        goals_home=goals_home,
        goals_away=goals_away,
        season_id=10,
    )


def _target_future() -> SimpleNamespace:
    return _fx(
        100,
        datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc),
        home=10,
        away=20,
        status="NS",
    )


def test_only_fixtures_before_kickoff():
    target = _target_future()
    prior_ok = _fx(
        1,
        datetime(2025, 6, 1, tzinfo=timezone.utc),
        home=10,
        away=99,
    )
    prior_same_ko_later_id = _fx(
        101,
        datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc),
        home=10,
        away=98,
    )
    prior_after = _fx(
        3,
        datetime(2025, 6, 16, tzinfo=timezone.utc),
        home=10,
        away=97,
    )

    assert fixture_key_before(prior_ok.kickoff_at, int(prior_ok.id), target.kickoff_at, int(target.id))
    assert not fixture_key_before(
        prior_same_ko_later_id.kickoff_at,
        int(prior_same_ko_later_id.id),
        target.kickoff_at,
        int(target.id),
    )
    assert not fixture_key_before(
        prior_after.kickoff_at,
        int(prior_after.id),
        target.kickoff_at,
        int(target.id),
    )

    check, reasons = audit_leakage([prior_ok], target)
    assert check == LEAKAGE_PASSED
    assert reasons == []

    check2, _ = audit_leakage([prior_after], target)
    assert check2 == LEAKAGE_FAILED


def test_excludes_future_and_non_finished_fixtures():
    target = _target_future()
    future_ns = _fx(
        50,
        datetime(2025, 7, 1, tzinfo=timezone.utc),
        home=10,
        away=20,
        status="NS",
    )
    live = _fx(
        51,
        datetime(2025, 5, 1, tzinfo=timezone.utc),
        home=10,
        away=20,
        status="1H",
    )
    check, reasons = audit_leakage([future_ns, live], target)
    assert check == LEAKAGE_FAILED
    assert any("not_finished" in r or "live_or_scheduled" in r for r in reasons)


def test_excludes_other_competition():
    target = _target_future()
    other_comp = _fx(
        60,
        datetime(2025, 5, 1, tzinfo=timezone.utc),
        home=10,
        away=20,
        competition_id=99,
    )
    check, reasons = audit_leakage([other_comp], target)
    assert check == LEAKAGE_FAILED
    assert any("competition_mismatch" in r for r in reasons)


def test_recent_5_and_6_ordered_by_date():
    team_home = 10
    fixtures = [
        _fx(i, datetime(2025, 1, i, tzinfo=timezone.utc), home=team_home, away=90 + i)
        for i in range(1, 11)
    ]
    last5 = take_last_n(fixtures, 5)
    last6 = take_last_n(fixtures, 6)
    assert [int(f.id) for f in last5] == [6, 7, 8, 9, 10]
    assert [int(f.id) for f in last6] == [5, 6, 7, 8, 9, 10]
    wdl5 = wdl_from_fixtures(last5, team_home)
    assert wdl5.total == 5


def test_low_sample_warns_not_blocks():
    from app.services.cecchino.cecchino_engine import WDLRecord

    home = WDLRecord(1, 0, 1)
    away = WDLRecord(0, 1, 0)
    block = compute_picchetto(
        "last5_home_away",
        home,
        away,
        home_sample_count=2,
        away_sample_count=2,
        home_target_sample=5,
        away_target_sample=5,
    )
    assert block.status == STATUS_PARTIAL_LOW_SAMPLE
    assert block.outcome_1.quota is not None
    assert any(WARNING_LOW_SAMPLE in w for w in block.warnings)


def test_zero_sample_insufficient():
    from app.services.cecchino.cecchino_engine import WDLRecord

    empty = WDLRecord(0, 0, 0)
    block = compute_picchetto("home_away", empty, empty)
    assert block.status == STATUS_INSUFFICIENT_DATA
    assert block.outcome_1 is None or block.outcome_1.quota is None
