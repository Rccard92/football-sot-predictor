"""Test esposizione read-only snapshot V3.5 nel Today Detail (V35-05A)."""

from __future__ import annotations

import copy
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
    validate_purchasability_preview_v35_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import SEL_HOME
from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

KO = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
SCAN = date(2026, 8, 19)
SNAP_AT = "2026-08-19T10:00:00+00:00"
KICKOFF = "2026-08-19T15:00:00+00:00"


def _valid_v31_snapshot(**overrides) -> dict:
    base = {
        "snapshot_version": PURCHASABILITY_V31_SNAPSHOT_VERSION,
        "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
        "formula_version": "cecchino_purchasability_v31_fixed_discount_empirical_v2",
        "status": "ok",
        "items": [
            {
                "market_key": "HOME",
                "status": "score",
                "score_v31": 72,
            }
        ],
    }
    base.update(overrides)
    return base


def _row(mk: str, *, rating: float = 60, prob: float = 0.55, quota_book: float = 2.2) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota_book,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _kpi_panel() -> dict:
    return {"rows": [_row(mk) for mk in PANEL_MARKET_KEYS]}


def _fixture_meta() -> dict:
    return {
        "today_fixture_id": 21807,
        "provider_fixture_id": 1549713,
        "snapshot_at": SNAP_AT,
        "kickoff": KICKOFF,
    }


def _snapshot_info() -> dict:
    return {
        "snapshot_at": SNAP_AT,
        "snapshot_timestamp_verified": True,
        "source_snapshot_before_kickoff": True,
    }


def _valid_v35_snapshot() -> dict:
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=_kpi_panel(),
        fixture_meta=_fixture_meta(),
        snapshot_info=_snapshot_info(),
    )
    snap = output["purchasability_preview_v35"]
    check = validate_purchasability_preview_v35_snapshot(snap)
    assert check["ok"] is True
    return snap


def _eligible_row(**kwargs):
    base = dict(
        id=21807,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        local_fixture_id=None,
        provider_fixture_id=1549713,
        competition_id=50,
        country_name="Colombia",
        league_name="Primera A",
        home_team_name="Águilas Doradas",
        away_team_name="Llaneros",
        kickoff=KO,
        fixture_status="NS",
        match_display_status="scheduled",
        goals_home=None,
        goals_away=None,
        scan_date=SCAN,
        odds_snapshot_json={},
        stats_snapshot_json={},
        kpi_panel_json={"rows": [{"market_key": "HOME", "segno": "1", "rating": 65}]},
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
        },
        warnings_json=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _detail_db(row):
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        return None

    db.get.side_effect = _get
    return db


_DETAIL_PATCHES = [
    patch(
        "app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews",
        return_value=({}, {}),
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
        return_value={"status": "unavailable"},
    ),
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail",
        return_value={},
    ),
    patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"),
    patch(
        "app.services.cecchino.cecchino_today_service.resolve_hr_by_market_for_fixture",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v3_for_detail",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v2_for_detail",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_for_detail",
        return_value={},
    ),
]


@pytest.fixture
def detail_patches():
    mocks = []
    for p in _DETAIL_PATCHES:
        mocks.append(p.start())
    yield mocks
    for p in reversed(_DETAIL_PATCHES):
        p.stop()


def test_detail_v35_persisted_valid_exposed(detail_patches):
    """A — snapshot valido persistito esposto top-level."""
    snap = _valid_v35_snapshot()
    v31 = _valid_v31_snapshot()
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
            "purchasability_preview_v31": v31,
        },
    )
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    assert detail["purchasability_v35_snapshot_status"] == "valid"
    assert detail["purchasability_v35_snapshot_reason"] is None
    assert detail["purchasability_preview_v35"] is not None
    assert detail["purchasability_preview_v35"]["input_fingerprint_sha256"] == snap[
        "input_fingerprint_sha256"
    ]
    assert detail["purchasability_preview_v35"]["engine_payload_sha256"] == snap[
        "engine_payload_sha256"
    ]


def test_detail_v35_absent_unavailable(detail_patches):
    """B — snapshot assente → unavailable."""
    row = _eligible_row()
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    assert detail["purchasability_preview_v35"] is None
    assert detail["purchasability_v35_snapshot_status"] == "unavailable"
    assert detail["purchasability_v35_snapshot_reason"] == "snapshot_unavailable"


def test_detail_v35_invalid_items_count(detail_patches):
    """C — snapshot invalido → null + invalid + reason."""
    snap = copy.deepcopy(_valid_v35_snapshot())
    snap["items"] = snap["items"][:18]
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
        },
    )
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    assert detail["purchasability_preview_v35"] is None
    assert detail["purchasability_v35_snapshot_status"] == "invalid"
    assert detail["purchasability_v35_snapshot_reason"] == "items_count_mismatch"


def test_detail_v35_tampered_hash_invalid(detail_patches):
    """D — hash tampered → invalid."""
    snap = copy.deepcopy(_valid_v35_snapshot())
    home = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    home["candidates"]["A"]["score"] = 999
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
        },
    )
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    assert detail["purchasability_preview_v35"] is None
    assert detail["purchasability_v35_snapshot_status"] == "invalid"
    assert detail["purchasability_v35_snapshot_reason"] == "engine_payload_sha256_mismatch"


def test_detail_v31_payload_unchanged_with_v35(detail_patches):
    """E — payload V3.1 invariato."""
    snap = _valid_v35_snapshot()
    v31 = _valid_v31_snapshot()
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
            "purchasability_preview_v31": v31,
        },
    )
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    assert detail["purchasability_preview_v31"]["source_mode"] == "persisted_pre_match_snapshot"
    assert detail["purchasability_preview_v31"]["items"][0]["score_v31"] == 72


def test_detail_v35_engine_not_called(detail_patches):
    """F — calculate_purchasability_v35_batch NOT CALLED."""
    snap = _valid_v35_snapshot()
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
        },
    )
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_snapshot.calculate_purchasability_v35_batch",
        side_effect=AssertionError("must not recompute V35 on detail GET"),
    ) as spy:
        detail = get_today_fixture_detail(_detail_db(row), 21807)

    spy.assert_not_called()
    assert detail["purchasability_v35_snapshot_status"] == "valid"


def test_detail_v35_no_db_write(detail_patches):
    """G — nessuna write V3.5 nel GET."""
    snap = _valid_v35_snapshot()
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v35": snap,
        },
    )
    db = _detail_db(row)
    with patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        return_value=row.kpi_panel_json,
    ):
        get_today_fixture_detail(db, 21807)

    db.commit.assert_not_called()
    db.add.assert_not_called()
