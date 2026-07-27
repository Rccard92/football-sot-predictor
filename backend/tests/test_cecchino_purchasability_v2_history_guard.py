"""Test history guard Acquistabilità v2 — senza database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_purchasability_v2_history_guard import (
    REASON_FIXTURE_NOT_ELIGIBLE,
    REASON_KICKOFF_MISSING,
    REASON_KPI_PANEL_MISSING,
    REASON_KPI_ROWS_MISSING,
    REASON_SNAPSHOT_NOT_BEFORE_KICKOFF,
    REASON_SNAPSHOT_TIMESTAMP_MISSING,
    REASON_SNAPSHOT_TIMESTAMP_UNVERIFIED,
    evaluate_purchasability_v2_historical_source,
)


def _kickoff(hours_ahead: float = 2.0) -> datetime:
    return datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc) + timedelta(
        hours=hours_ahead
    )


def _verified_panel(*, snap_at: datetime) -> dict:
    return {
        "rows": [{"market_key": "HOME", "rating": 70}],
        "odds_meta": {"odds_fetched_at": snap_at.isoformat()},
    }


def _fixture(**kwargs):
    base = {
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "kpi_panel_json": _verified_panel(
            snap_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc)
        ),
        "odds_snapshot_json": None,
        "odds_checked_at": None,
        "updated_at": datetime(2026, 7, 20, 19, 0, 0, tzinfo=timezone.utc),
        "kickoff": datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_accepted_eligible_verified_before_kickoff():
    snap = datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json=_verified_panel(snap_at=snap),
            kickoff=kick,
        )
    )
    assert result["accepted"] is True
    assert result["reason_code"] is None
    assert result["eligibility_verified"] is True
    assert result["kpi_rows_verified"] is True
    assert result["snapshot_timestamp_verified"] is True
    assert result["source_snapshot_before_kickoff"] is True
    assert result["snapshot_at"] is not None
    assert result["kickoff"] is not None


def test_rejected_not_eligible():
    result = evaluate_purchasability_v2_historical_source(
        _fixture(eligibility_status="excluded")
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_FIXTURE_NOT_ELIGIBLE
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_kpi_panel_missing():
    result = evaluate_purchasability_v2_historical_source(
        _fixture(kpi_panel_json=None)
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_KPI_PANEL_MISSING
    assert result["eligibility_verified"] is True
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_kpi_rows_empty():
    result = evaluate_purchasability_v2_historical_source(
        _fixture(kpi_panel_json={"rows": [], "odds_meta": {}})
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_KPI_ROWS_MISSING
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_updated_at_only():
    """Timestamp solo da updated_at → non verificato → rejected."""
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json={"rows": [{"market_key": "HOME"}]},
            odds_snapshot_json=None,
            odds_checked_at=None,
            updated_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
        )
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_SNAPSHOT_TIMESTAMP_UNVERIFIED
    assert result["snapshot_timestamp_verified"] is False
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_timestamp_missing():
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json={"rows": [{"market_key": "HOME"}]},
            odds_snapshot_json=None,
            odds_checked_at=None,
            updated_at=None,
        )
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_SNAPSHOT_TIMESTAMP_MISSING
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_kickoff_missing():
    result = evaluate_purchasability_v2_historical_source(_fixture(kickoff=None))
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_KICKOFF_MISSING
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_snapshot_equal_kickoff():
    ts = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json=_verified_panel(snap_at=ts),
            kickoff=ts,
        )
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_SNAPSHOT_NOT_BEFORE_KICKOFF
    assert result["source_snapshot_before_kickoff"] is False


def test_rejected_snapshot_after_kickoff():
    kick = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    snap = kick + timedelta(hours=1)
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json=_verified_panel(snap_at=snap),
            kickoff=kick,
        )
    )
    assert result["accepted"] is False
    assert result["reason_code"] == REASON_SNAPSHOT_NOT_BEFORE_KICKOFF
    assert result["source_snapshot_before_kickoff"] is False


def test_naive_datetime_treated_as_utc():
    """Datetime naive gestiti come UTC dagli helper esistenti."""
    snap_naive = datetime(2026, 7, 20, 16, 0, 0)  # naive
    kick_naive = datetime(2026, 7, 20, 18, 0, 0)  # naive
    result = evaluate_purchasability_v2_historical_source(
        _fixture(
            kpi_panel_json={
                "rows": [{"market_key": "HOME"}],
                "odds_meta": {"odds_fetched_at": snap_naive},
            },
            kickoff=kick_naive,
        )
    )
    assert result["accepted"] is True
    assert result["source_snapshot_before_kickoff"] is True


def test_reason_codes_are_distinct():
    codes = {
        REASON_FIXTURE_NOT_ELIGIBLE,
        REASON_KPI_PANEL_MISSING,
        REASON_KPI_ROWS_MISSING,
        REASON_SNAPSHOT_TIMESTAMP_UNVERIFIED,
        REASON_SNAPSHOT_TIMESTAMP_MISSING,
        REASON_KICKOFF_MISSING,
        REASON_SNAPSHOT_NOT_BEFORE_KICKOFF,
    }
    assert len(codes) == 7


def test_source_before_kickoff_never_true_on_reject():
    cases = [
        _fixture(eligibility_status="discovered"),
        _fixture(kpi_panel_json=None),
        _fixture(kpi_panel_json={"rows": []}),
        _fixture(
            kpi_panel_json={"rows": [{"market_key": "HOME"}]},
            odds_checked_at=None,
            updated_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
        ),
        _fixture(kickoff=None),
    ]
    for fx in cases:
        result = evaluate_purchasability_v2_historical_source(fx)
        assert result["accepted"] is False
        assert result["source_snapshot_before_kickoff"] is not True
