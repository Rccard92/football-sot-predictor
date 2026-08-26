"""Detail exposure Structural V2 — read-only statuses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    SNAPSHOT_OUTPUT_KEY,
    attach_purchasability_preview_v35_v2_to_output,
    resolve_purchasability_preview_v35_v2_for_detail,
)


def _valid_snap() -> dict:
    out: dict = {}
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=out,
        kpi_panel={
            "rows": [
                {
                    "market_key": mk,
                    "quota_book": 2.2,
                    "prob_cecchino": 0.55,
                    "rating": 70,
                    "book_source": "betfair_raw_match_winner",
                    "book_fallback_used": False,
                }
                for mk in PANEL_MARKET_KEYS
            ]
        },
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 1,
            "snapshot_at": "2026-08-19T10:00:00+00:00",
            "kickoff": "2026-08-19T15:00:00+00:00",
        },
        snapshot_info={
            "snapshot_at": "2026-08-19T10:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
    )
    return out[SNAPSHOT_OUTPUT_KEY]


def test_detail_statuses():
    assert (
        resolve_purchasability_preview_v35_v2_for_detail(
            row=SimpleNamespace(cecchino_output_json={})
        )["purchasability_v35_v2_snapshot_status"]
        == "absent"
    )
    snap = _valid_snap()
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch"
    ) as mocked:
        detail = resolve_purchasability_preview_v35_v2_for_detail(
            row=SimpleNamespace(cecchino_output_json={SNAPSHOT_OUTPUT_KEY: snap})
        )
        mocked.assert_not_called()
    assert detail["purchasability_v35_v2_snapshot_status"] == "valid"
    invalid = resolve_purchasability_preview_v35_v2_for_detail(
        row=SimpleNamespace(
            cecchino_output_json={SNAPSHOT_OUTPUT_KEY: {"snapshot_version": "x"}}
        )
    )
    assert invalid["purchasability_v35_v2_snapshot_status"] == "present_but_invalid"
