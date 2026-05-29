"""Test selezione prossimo turno basata su fixture future eleggibili."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models.fixture import Fixture
from app.services.next_round_selection import (
    FALLBACK_ROUND_WARNING,
    select_next_round_fixtures,
)


def _fx(
    fx_id: int,
    *,
    status: str,
    kickoff: datetime,
    round_label: str | None,
) -> Fixture:
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.status = status
    fx.kickoff_at = kickoff
    fx.round = round_label
    fx.raw_json = None
    return fx


def test_select_next_round_picks_round_of_first_future_not_stale_non_ft():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=90)
    future = now + timedelta(days=5)

    stale_round4 = _fx(1, status="PST", kickoff=past, round_label="Regular Season - 4")
    future_r18_a = _fx(10, status="NS", kickoff=future, round_label="Regular Season - 18")
    future_r18_b = _fx(11, status="NS", kickoff=future + timedelta(hours=2), round_label="Regular Season - 18")

    result = select_next_round_fixtures(
        [stale_round4, future_r18_a, future_r18_b],
        limit=100,
        only_next_round=True,
    )

    assert result.future_fixtures_count == 2
    assert result.final_round == "Regular Season - 18"
    assert result.final_next_round_fixtures_count == 2
    assert {int(f.id) for f in result.fixtures} == {10, 11}
    assert result.first_future_fixture_id == 10
    assert result.error_code is None


def test_select_next_round_fallback_batch_when_round_empty():
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=3)
    fixtures = [
        _fx(i, status="NS", kickoff=future + timedelta(hours=i), round_label=None)
        for i in range(1, 6)
    ]

    result = select_next_round_fixtures(fixtures, limit=100, only_next_round=True)

    assert result.future_fixtures_count == 5
    assert result.final_next_round_fixtures_count == 5
    assert result.fallback_used is True
    assert FALLBACK_ROUND_WARNING in result.warnings


def test_select_next_round_empty_pool_returns_no_future_fixtures():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=30)
    fixtures = [_fx(1, status="PST", kickoff=past, round_label="Regular Season - 4")]

    result = select_next_round_fixtures(fixtures, only_next_round=True)

    assert result.fixtures == []
    assert result.error_code == "no_future_fixtures"
    assert result.future_fixtures_count == 0


def test_select_next_round_only_next_round_false_returns_limited_pool():
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=2)
    fixtures = [
        _fx(1, status="NS", kickoff=future, round_label="R1"),
        _fx(2, status="NS", kickoff=future + timedelta(days=7), round_label="R2"),
    ]

    result = select_next_round_fixtures(fixtures, limit=1, only_next_round=False)

    assert len(result.fixtures) == 1
    assert int(result.fixtures[0].id) == 1
