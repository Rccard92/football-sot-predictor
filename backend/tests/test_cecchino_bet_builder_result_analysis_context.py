"""BET-RESULTS-02 — analysis context endpoint read-only."""

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
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, ELIGIBILITY_EXCLUDED_CUP
from app.routes.cecchino_bet_builder import router
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_RESULT_ANALYSIS_CONTEXT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_bet_builder_result_analysis_context import (
    get_bet_builder_result_analysis_context,
)
from app.services.cecchino.cecchino_selection_keys import SEL_DRAW, SEL_HOME

KO = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
SCAN_DATE = date(2026, 8, 19)
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
        "signals_matrix": {},
    }
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
        scan_date=SCAN_DATE,
        odds_snapshot_json={"bookmakers": {"Betfair": {"HOME": 2.2, "DRAW": 3.5, "AWAY": 3.7}}},
        stats_snapshot_json={},
        kpi_panel_json=_kpi_panel(),
        cecchino_output_json=_output(),
        warnings_json=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _local_fixture():
    return SimpleNamespace(
        id=100,
        home_team_id=1,
        away_team_id=2,
        kickoff_at=KO,
        status="FT",
    )


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
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
        return_value={},
    ),
    patch(
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context.build_balance_identity_for_detail",
        return_value={"status": "consistent"},
    ),
    patch(
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context.evaluate_balance_v5_snapshot_meta",
        return_value={"mode": "historical_snapshot", "status": "verified"},
    ),
    patch(
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context.build_cecchino_balance_v5",
        return_value=_balance_v5_stub(),
    ),
    patch(
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context.rome_today",
        return_value=ROME_TODAY,
    ),
    patch(
        "app.services.cecchino.cecchino_bet_builder_result_analysis_context._resolve_kpi_panel_for_detail",
        side_effect=lambda row, db, snapshot_only=False: row.kpi_panel_json,
    ),
]


def _apply_patches(fn):
    for p in reversed(_CONTEXT_PATCHES):
        fn = p(fn)
    return fn


@_apply_patches
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
    assert payload["fixture"]["today_fixture_id"] == 42
    assert payload["fixture"]["home_team"] == "Home FC"


@_apply_patches
def test_fixture_missing_returns_none(*_args):
    row = _row()
    db = _mock_db(row)
    db.get.side_effect = lambda model, pk: None
    assert get_bet_builder_result_analysis_context(db, 999) is None


@_apply_patches
def test_fixture_not_eligible_returns_none(*_args):
    row = _row(eligibility_status=ELIGIBILITY_EXCLUDED_CUP)
    db = _mock_db(row)
    assert get_bet_builder_result_analysis_context(db, 42) is None


@_apply_patches
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


@_apply_patches
def test_kpi_balance_gi_present(*_args):
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


@_apply_patches
def test_unavailable_gi_adds_warning(*_args):
    row = _row()
    db = _mock_db(row, _local_fixture())
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5.build_today_payload",
        side_effect=RuntimeError("gi_failed"),
    ):
        payload = get_bet_builder_result_analysis_context(db, 42)
    assert payload["goal_intensity_v5"] is None
    assert any("goal_intensity" in w for w in payload["warnings"])


@_apply_patches
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


@_apply_patches
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


@_apply_patches
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


@_apply_patches
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


@_apply_patches
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


class TestAnalysisContextRoute:
    @_apply_patches
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
