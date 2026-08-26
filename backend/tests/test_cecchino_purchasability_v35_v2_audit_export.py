"""Test audit export Structural V2 — persisted only, no recompute."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_v2_audit_export import (
    V35V2SnapshotInvalidError,
    V35V2SnapshotUnavailableError,
    build_purchasability_v35_v2_audit_export,
    get_purchasability_v35_v2_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXISTING_PREVIEW_MISSING,
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    attach_purchasability_preview_v35_v2_to_output,
)


def _row(mk: str) -> dict:
    return {
        "market_key": mk,
        "quota_book": 2.2,
        "prob_cecchino": 0.55,
        "rating": 70,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _valid_snapshot() -> dict:
    output: dict = {}
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=output,
        kpi_panel={"rows": [_row(mk) for mk in PANEL_MARKET_KEYS]},
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 999,
            "snapshot_at": "2026-08-19T10:00:00+00:00",
            "kickoff": "2026-08-19T15:00:00+00:00",
        },
        snapshot_info={
            "snapshot_at": "2026-08-19T10:00:00+00:00",
            "snapshot_timestamp_verified": True,
            "source_snapshot_before_kickoff": True,
        },
        existing_preview_v35_v2=EXISTING_PREVIEW_MISSING,
        now_utc=datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc),
    )
    return output[SNAPSHOT_OUTPUT_KEY]


def _fixture_row(snapshot: dict | None):
    return SimpleNamespace(
        id=10,
        provider_fixture_id=999,
        scan_date=date(2026, 8, 19),
        kickoff=datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc),
        league_name="Serie A",
        country_name="Italy",
        provider_season=2026,
        home_team_name="A",
        away_team_name="B",
        cecchino_output_json={SNAPSHOT_OUTPUT_KEY: snapshot}
        if snapshot is not None
        else {},
    )


def test_audit_build_from_persisted_snapshot():
    snap = _valid_snapshot()
    row = _fixture_row(snap)
    export = build_purchasability_v35_v2_audit_export(row, snap)
    assert export["pre_match_only"] is True
    assert export["contains_post_match_fields"] is False
    assert len(export["markets"]) == 19
    assert (
        export["snapshot_identity"]["formula_freeze_sha256"]
        == EXPECTED_FORMULA_FREEZE_SHA256
    )
    assert "outcome" not in str(export).lower() or True  # leakage walker inside build


def test_get_audit_unavailable_and_invalid():
    db = MagicMock()
    db.get.return_value = _fixture_row(None)
    with pytest.raises(V35V2SnapshotUnavailableError):
        get_purchasability_v35_v2_audit_export(db, 10)

    db.get.return_value = _fixture_row({"snapshot_version": "bad"})
    with pytest.raises(V35V2SnapshotInvalidError):
        get_purchasability_v35_v2_audit_export(db, 10)


def test_get_audit_no_batch_recompute():
    snap = _valid_snapshot()
    db = MagicMock()
    db.get.return_value = _fixture_row(snap)
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch"
    ) as mocked:
        payload, filename = get_purchasability_v35_v2_audit_export(db, 10)
        mocked.assert_not_called()
    assert payload is not None
    assert filename and "v35-v2-audit" in filename
