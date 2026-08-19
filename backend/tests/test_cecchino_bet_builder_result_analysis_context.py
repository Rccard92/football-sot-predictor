"""BET-RESULTS-02 / 02.1 — analysis context endpoint read-only + parity Today."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_CUP,
    MATCH_FINISHED,
    MATCH_UPCOMING,
)
from app.routes.cecchino_bet_builder import router
from app.services.cecchino.cecchino_balance_v5_detail import META_BLOCKED, MODE_HISTORICAL
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_bet_builder_result_analysis_context import (
    get_bet_builder_result_analysis_context,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

KO = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
KO_BAD = datetime(2026, 8, 22, 20, 0, tzinfo=timezone.utc)
SCAN_DATE = date(2026, 8, 19)
SCAN_HISTORICAL = date(2026, 8, 18)
SCAN_TODAY = date(2026, 8, 20)
ROME_TODAY = date(2026, 8, 20)


def _kpi_panel():
    return {
        "version": "cecchino_kpi_v2_betfair",
        "bookmaker_status": "available",
        "rows": [
            {"market_key": SEL_HOME, "quota_cecchino": 2.1, "quota_book": 2.2, "segno": "1"},
            {"market_key": SEL_DRAW, "quota_cecchino": 3.4, "quota_book": 3.5, "segno": "X"},
        ],
    }


def _output(**extra):
    base = {
        "final": {
            "status": "available",
            "quota_1": 2.1,
            "quota_x": 3.4,
            "quota_2": 3.6,
            "prob_1": 0.42,
            "prob_x": 0.28,
            "prob_2": 0.30,
        },
        "goal_markets": {},
        "signals_matrix": {"version": "cecchino_signals_v2", "rows": []},
        "data_quality": {"leakage_check": {"target_kickoff": KO.isoformat()}},
    }
    if "target" in extra:
        target = extra.pop("target")
        base["data_quality"] = {"leakage_check": {"target_kickoff": target.isoformat()}}
    base.update(extra)
    return base


def _row(**kwargs):
    base = dict(
        id=42,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        local_fixture_id=100,
        provider_fixture_id=900042,
        competition_id=10,
        country_name="Iceland",
        league_name="2. Deild",
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=KO,
        fixture_status="FT",
        match_display_status="finished",
        goals_home=2,
        goals_away=1,
        score_fulltime_home=2,
        score_fulltime_away=1,
        scan_date=SCAN_HISTORICAL,
        odds_snapshot_json={"bookmakers": {"Betfair": {"HOME": 2.2, "DRAW": 3.5, "AWAY": 3.7}}},
        stats_snapshot_json={},
        kpi_panel_json=_kpi_panel(),
        cecchino_output_json=_output(),
        warnings_json=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _local_fixture(**kwargs):
    base = dict(
        id=100,
        api_fixture_id=900042,
        competition_id=10,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=KO,
        status="FT",
        status_long="Match Finished",
        goals_home=2,
        goals_away=1,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mock_db(row, local=None):
    home = SimpleNamespace(name="Home FC")
    away = SimpleNamespace(name="Away FC")
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row if int(pk) == int(row.id) else None
        if "Fixture" in name and "Today" not in name:
            return local
        if "Team" in name:
            return home if int(pk) == 1 else away
        return None

    db.get.side_effect = _get
    return db


def _balance_v5_stub():
    return {
        "status": "available",
        "equilibrium_index": 72,
        "pillars": [],
    }


def _gi_stub():
    return {
        "status": "available",
        "index": {"score_stored": 65.0},
        "operational_status": "preview_monitored",
    }


_CONTEXT_PATCHES = [
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.build_balance_identity_for_detail",
        return_value={"status": "consistent"},
    ),
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.evaluate_balance_v5_snapshot_meta",
        return_value={"mode": "historical_snapshot", "status": "verified"},
    ),
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.build_cecchino_balance_v5",
        return_value=_balance_v5_stub(),
    ),
    patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=ROME_TODAY),
    patch(
        "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
        side_effect=lambda row, db, snapshot_only=False: row.kpi_panel_json,
    ),
]


_PARITY_PATCHES = [
    patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"),
    patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={}),
    patch(
        "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
        return_value={"status": "unavailable", "error": "bundle_missing"},
    ),
    patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={}),
    patch("app.services.cecchino.cecchino_today_service.rome_today", return_value=ROME_TODAY),
]


def _apply_patches(fn, patches):
    for p in reversed(patches):
        fn = p(fn)
    return fn


def _apply_context_patches(fn):
    return _apply_patches(fn, _CONTEXT_PATCHES)


def _apply_parity_patches(fn):
    return _apply_patches(fn, _PARITY_PATCHES)


@_apply_context_patches
def test_fixture_existing_returns_200(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload is not None
    assert payload["contract_version"] == BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION
    assert payload["contract_version"] == "bet_builder_result_analysis_context_v2"
    assert payload["source"]["kind"] == "cecchino_today_canonical_detail"
    assert payload["source"]["today_fixture_id"] == 42
    assert payload["fixture"]["today_fixture_id"] == 42
    assert payload["fixture"]["home_team"] == "Home FC"


@_apply_context_patches
def test_fixture_missing_returns_none(*_args):
    row = _row()
    db = _mock_db(row)
    db.get.side_effect = lambda model, pk: None
    assert get_bet_builder_result_analysis_context(db, 999) is None


@_apply_context_patches
def test_fixture_not_eligible_returns_none(*_args):
    row = _row(eligibility_status=ELIGIBILITY_EXCLUDED_CUP)
    db = _mock_db(row)
    assert get_bet_builder_result_analysis_context(db, 42) is None


@_apply_context_patches
def test_finished_fixture_prematch_kpi_from_snapshot(*_args):
    row = _row(
        match_display_status="finished",
        kpi_panel_json=_kpi_panel(),
    )
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload["kpi_panel"] is not None
    assert payload["kpi_panel"]["version"] == "cecchino_kpi_v2_betfair"


@_apply_context_patches
def test_kpi_balance_gi_signals_present(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload["kpi_panel"] is not None
    assert payload["balance_v5"] is not None
    assert payload["goal_intensity_v5"] is not None
    assert payload["fixture_identity_consistency"] is not None
    assert payload["balance_v5_snapshot_meta"] is not None
    assert payload["signals_matrix"] is not None
    assert payload["signal_contract"] is not None


@_apply_context_patches
def test_unavailable_gi_adds_warning(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        side_effect=RuntimeError("gi_failed"),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload["goal_intensity_v5"] is not None
    assert payload["goal_intensity_v5"]["status"] == "error"
    assert any("goal_intensity" in w for w in payload["warnings"])


@_apply_context_patches
def test_no_db_write(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        get_bet_builder_result_analysis_context(db, 42)
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()


@_apply_context_patches
def test_no_provider_api(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ), patch(
        "app.services.cecchino.cecchino_today_service.load_betfair_odds_payload",
    ) as load_betfair:
        get_bet_builder_result_analysis_context(db, 42)
        load_betfair.assert_not_called()


@_apply_context_patches
def test_no_signal_sync_write(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ), patch(
        "app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations",
    ) as sync_signals:
        get_bet_builder_result_analysis_context(db, 42)
        sync_signals.assert_not_called()


@_apply_context_patches
def test_no_v31_v35_recompute(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ), patch(
        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v31_for_detail",
    ) as v31, patch(
        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v35_for_detail",
    ) as v35:
        get_bet_builder_result_analysis_context(db, 42)
        v31.assert_not_called()
        v35.assert_not_called()


@_apply_context_patches
def test_ft_result_does_not_change_kpi_snapshot(*_args):
    kpi = _kpi_panel()
    row = _row(
        match_display_status="finished",
        goals_home=5,
        goals_away=0,
        kpi_panel_json=kpi,
    )
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload["kpi_panel"]["rows"][0]["quota_cecchino"] == 2.1


def _bb_gi(detail: dict) -> dict | None:
    return detail.get("goal_intensity_v5") or detail.get("goal_intensity_v5_preview")


def _assert_technical_parity(today: dict, bb: dict) -> None:
    assert bb["kpi_panel"] == today.get("kpi_panel_v2") or today.get("kpi_panel")
    assert bb["balance_v5"] == today["balance_v5"]
    assert bb["fixture_identity_consistency"] == today["fixture_identity_consistency"]
    assert bb["balance_v5_snapshot_meta"] == today["balance_v5_snapshot_meta"]
    assert bb["goal_intensity_v5"] == _bb_gi(today)
    today_signals = today.get("signals_matrix")
    if today_signals is None and isinstance(today.get("cecchino_output"), dict):
        today_signals = today["cecchino_output"].get("signals_matrix")
    assert bb["signals_matrix"] == today_signals
    assert bb["signal_contract"] == today["signal_contract"]


@_apply_parity_patches
def test_parity_today_detail_vs_bb_context(*_args):
    row = _row(
        scan_date=SCAN_HISTORICAL,
        fixture_status="NS",
        match_display_status=MATCH_UPCOMING,
        goals_home=None,
        goals_away=None,
        score_fulltime_home=None,
        score_fulltime_away=None,
    )
    local = _local_fixture(status="FT", goals_home=2, goals_away=1)
    db = _mock_db(row, local)
    gi = _gi_stub()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=gi,
    ):
        today = get_today_fixture_detail(db, 42)
        bb = get_bet_builder_result_analysis_context(db, 42)
    assert today["status"] == "ok"
    assert bb is not None
    _assert_technical_parity(today, bb)


@_apply_parity_patches
def test_historical_finished_balance_not_blocked_by_score(*_args):
    row = _row(
        scan_date=SCAN_HISTORICAL,
        fixture_status="FT",
        match_display_status=MATCH_FINISHED,
        goals_home=0,
        goals_away=1,
        score_fulltime_home=0,
        score_fulltime_away=1,
    )
    local = _local_fixture(status="FT", goals_home=0, goals_away=1)
    db = _mock_db(row, local)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        bb = get_bet_builder_result_analysis_context(db, 42)
    meta = bb["balance_v5_snapshot_meta"]
    assert meta["mode"] == MODE_HISTORICAL
    assert meta["status"] in ("verified", "partial")
    assert bb["balance_v5"]["status"] == "ok"
    assert bb["fixture_identity_consistency"]["status"] == "consistent"


@_apply_parity_patches
def test_false_mismatch_post_match_historical_stays_valid(*_args):
    row = _row(
        scan_date=SCAN_HISTORICAL,
        fixture_status="FT",
        match_display_status=MATCH_FINISHED,
        goals_home=0,
        goals_away=1,
        score_fulltime_home=0,
        score_fulltime_away=1,
    )
    local = _local_fixture(status="NS", goals_home=None, goals_away=None)
    db = _mock_db(row, local)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        bb = get_bet_builder_result_analysis_context(db, 42)
    ident = bb["fixture_identity_consistency"]
    meta = bb["balance_v5_snapshot_meta"]
    assert meta["mode"] == MODE_HISTORICAL
    assert meta["status"] in ("verified", "partial")
    assert bb["balance_v5"]["status"] == "ok"
    assert ident["status"] == "consistent"
    assert ident["status_match"] is False
    assert ident["score_match"] is False


@_apply_parity_patches
def test_true_mismatch_provider_still_blocked(*_args):
    row = _row(scan_date=SCAN_HISTORICAL)
    local = _local_fixture(api_fixture_id=999999)
    db = _mock_db(row, local)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        bb = get_bet_builder_result_analysis_context(db, 42)
    meta = bb["balance_v5_snapshot_meta"]
    assert meta["status"] == META_BLOCKED
    assert bb["balance_v5"]["status"] == "unavailable"
    assert "provider_fixture_id_mismatch" in (meta["warnings"] or [])


@_apply_parity_patches
def test_true_mismatch_kickoff_still_blocked(*_args):
    row = _row(scan_date=SCAN_HISTORICAL)
    local = _local_fixture(kickoff_at=KO_BAD)
    db = _mock_db(row, local)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        return_value=_gi_stub(),
    ):
        bb = get_bet_builder_result_analysis_context(db, 42)
    meta = bb["balance_v5_snapshot_meta"]
    assert meta["status"] == META_BLOCKED
    assert bb["balance_v5"]["status"] == "unavailable"


class TestAnalysisContextRoute:
    @_apply_context_patches
    def test_api_200(self, *_args):
        row = _row()
        db = _mock_db(row, _local_fixture())
        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _ov():
            yield db

        app.dependency_overrides[get_db] = _ov
        client = TestClient(app)
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
            return_value=_gi_stub(),
        ):
            res = client.get("/api/cecchino/bet-builder/results/42/analysis-context")
        assert res.status_code == 200
        body = res.json()
        assert body["contract_version"] == BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION
        assert body["source"]["kind"] == "cecchino_today_canonical_detail"
        assert "signals_matrix" in body
        assert "signal_contract" in body

    def test_api_404(self):
        db = MagicMock()
        db.get.return_value = None
        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _ov():
            yield db

        app.dependency_overrides[get_db] = _ov
        client = TestClient(app)
        res = client.get("/api/cecchino/bet-builder/results/999/analysis-context")
        assert res.status_code == 404
