"""Test performance read-path Today Detail + cache HR (PERF-01A)."""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.routes.cecchino_kpi_signals import router as kpi_signals_router
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_historical_reliability import (
    build_historical_reliability_for_panel,
)
from app.services.cecchino.cecchino_hr_history_cache import (
    clear_hr_history_cache,
    get_or_build_hr_history_context,
)
from app.services.cecchino.cecchino_today_service import get_today_fixture_detail

KO = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
SCAN = date(2026, 8, 19)


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


_DETAIL_PATCHES = [
    "app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations",
    "app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail",
    "app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis",
    "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    "app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row",
    "app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug",
    "app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary",
    "app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews",
]


def _detail_db(row):
    db = MagicMock()

    def _get(model, pk):
        name = getattr(model, "__name__", str(model))
        if "CecchinoTodayFixture" in name:
            return row
        return None

    db.get.side_effect = _get
    return db


@pytest.fixture(autouse=True)
def _clear_hr_cache():
    clear_hr_history_cache()
    yield
    clear_hr_history_cache()


@patch("app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews", return_value=({}, {}))
@patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={})
@patch(
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    return_value={"status": "unavailable"},
)
@patch(
    "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
    return_value={},
)
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations")
@patch("app.services.cecchino.cecchino_today_service.resolve_hr_by_market_for_fixture")
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v3_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v2_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail")
def test_detail_persisted_v31_skips_hr_rebuild(
    mock_kpi,
    _p1,
    _p2,
    _p3,
    mock_hr,
    _sync,
    *_rest,
):
    """Caso A — snapshot V3.1 persistito valido non invoca resolve_hr_by_market_for_fixture."""
    snapshot = _valid_v31_snapshot()
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v31": snapshot,
        },
    )
    mock_kpi.return_value = row.kpi_panel_json

    detail = get_today_fixture_detail(_detail_db(row), 21807)

    mock_hr.assert_not_called()
    assert detail["purchasability_preview_v31"]["source_mode"] == "persisted_pre_match_snapshot"
    assert detail["purchasability_preview_v31"]["items"][0]["score_v31"] == 72


@patch("app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews", return_value=({}, {}))
@patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={})
@patch(
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    return_value={"status": "unavailable"},
)
@patch(
    "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
    return_value={},
)
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations")
@patch("app.services.cecchino.cecchino_today_service.get_or_build_hr_history_context")
@patch("app.services.cecchino.cecchino_today_service.resolve_hr_by_market_for_fixture")
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v31_for_detail")
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v3_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v2_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail")
def test_detail_missing_v31_uses_hr_fallback(
    mock_kpi,
    _p1,
    _p2,
    _p3,
    mock_v31,
    mock_hr,
    mock_hr_ctx,
    _sync,
    *_rest,
):
    """Caso B — snapshot assente usa historical fallback."""
    row = _eligible_row()
    mock_kpi.return_value = row.kpi_panel_json
    mock_hr_ctx.return_value = {"history_rows": [], "local_index": {}, "global_index": {}}
    mock_hr.return_value = {"HOME": {"status": "ok", "score": 61}}
    mock_v31.return_value = {"status": "ok", "source_mode": "derived_read_only_from_stored_snapshot"}

    get_today_fixture_detail(_detail_db(row), 21807)

    mock_hr_ctx.assert_called_once()
    mock_hr.assert_called_once()
    assert mock_v31.call_args.kwargs["historical_by_market"] == {"HOME": {"status": "ok", "score": 61}}


@patch("app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews", return_value=({}, {}))
@patch("app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row", return_value={})
@patch(
    "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
    return_value={"status": "unavailable"},
)
@patch(
    "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row",
    return_value={},
)
@patch("app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis", return_value={})
@patch("app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations")
@patch("app.services.cecchino.cecchino_today_service.get_or_build_hr_history_context")
@patch("app.services.cecchino.cecchino_today_service.resolve_hr_by_market_for_fixture")
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v31_for_detail")
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v3_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v2_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_for_detail", return_value={})
@patch("app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail")
def test_detail_invalid_v31_uses_hr_fallback(
    mock_kpi,
    _p1,
    _p2,
    _p3,
    mock_v31,
    mock_hr,
    mock_hr_ctx,
    _sync,
    *_rest,
):
    """Caso C — snapshot invalido non usato come persisted."""
    invalid = {"snapshot_version": "wrong", "candidate_version": "wrong", "items": []}
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v31": invalid,
        },
    )
    mock_kpi.return_value = row.kpi_panel_json
    mock_hr_ctx.return_value = {"history_rows": [], "local_index": {}, "global_index": {}}
    mock_hr.return_value = {}
    mock_v31.return_value = {"status": "unavailable"}

    get_today_fixture_detail(_detail_db(row), 21807)

    mock_hr.assert_called_once()
    mock_hr_ctx.assert_called_once()


def test_hr_history_cache_miss_then_hit():
    """Caso D — prima richiesta cache miss, seconda cache hit con stesso risultato."""
    db = MagicMock()
    fake_rows = [{"market_key": "HOME", "scan_date": "2026-08-19"}]
    fake_local = {"k": "local"}
    fake_global = {"k": "global"}

    with patch(
        "app.services.cecchino.cecchino_hr_history_cache.build_hr_history_context",
    ) as mock_build:
        mock_build.return_value = {
            "history_rows": fake_rows,
            "local_index": fake_local,
            "global_index": fake_global,
            "date_to": SCAN,
        }

        ctx1 = get_or_build_hr_history_context(db, date_to=SCAN)
        ctx2 = get_or_build_hr_history_context(db, date_to=SCAN)

    assert mock_build.call_count == 1
    assert ctx1["history_rows"] == ctx2["history_rows"]
    assert ctx1["local_index"] == ctx2["local_index"]
    assert ctx1["global_index"] == ctx2["global_index"]


def test_hr_history_cache_clear_forces_rebuild():
    """Caso E — invalidation svuota cache."""
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_hr_history_cache.build_hr_history_context",
    ) as mock_build:
        mock_build.return_value = {
            "history_rows": [],
            "local_index": {},
            "global_index": {},
            "date_to": SCAN,
        }
        get_or_build_hr_history_context(db, date_to=SCAN)
        clear_hr_history_cache()
        get_or_build_hr_history_context(db, date_to=SCAN)
    assert mock_build.call_count == 2


def test_build_hr_panel_with_prebuilt_context_skips_rows_rebuild():
    """Verifica timing: history_rows pre-costruiti → build_purchasability_rows_ms = 0."""
    db = MagicMock()
    payload = build_historical_reliability_for_panel(
        db,
        date_from=SCAN,
        date_to=SCAN,
        competition_id=None,
        current_rows=[
            {
                "today_fixture_id": 1,
                "market_key": "HOME",
                "segno": "HOME",
                "rating": 65,
                "competition_id": 50,
                "scan_date": SCAN.isoformat(),
            }
        ],
        history_rows=[],
        local_index={},
        global_index={},
    )
    timing = payload["summary"]["timing_ms"]
    assert timing["build_purchasability_rows_ms"] == 0.0
    assert timing["build_local_index_ms"] == 0.0
    assert timing["build_global_index_ms"] == 0.0
    assert "total_ms" in timing


def test_hr_endpoint_uses_cached_context():
    """Endpoint historical-reliability passa history context cached."""
    app = FastAPI()
    app.include_router(kpi_signals_router, prefix="/api")

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    fake_ctx = {
        "history_rows": [{"x": 1}],
        "local_index": {"a": 1},
        "global_index": {"b": 2},
    }
    fake_payload = {
        "metric_kind": "historical_reliability",
        "version": "cecchino_historical_reliability_v1_1",
        "status": "ok",
        "items": {},
        "summary": {"elapsed_ms": 1.0, "timing_ms": {"total_ms": 1.0}},
    }

    with patch(
        "app.routes.cecchino_kpi_signals.get_or_build_hr_history_context",
        return_value=fake_ctx,
    ) as mock_ctx:
        with patch(
            "app.routes.cecchino_kpi_signals.build_historical_reliability_for_panel",
            return_value=fake_payload,
        ) as mock_build:
            res = client.get(
                "/api/cecchino/kpi-signals/historical-reliability",
                params={"date_from": "2026-08-19", "date_to": "2026-08-19"},
            )

    assert res.status_code == 200
    mock_ctx.assert_called_once()
    kwargs = mock_build.call_args.kwargs
    assert kwargs["history_rows"] == fake_ctx["history_rows"]
    assert kwargs["local_index"] == fake_ctx["local_index"]
    assert kwargs["global_index"] == fake_ctx["global_index"]


def test_benchmark_detail_persisted_skips_hr_timing():
    """Benchmark: detail con V3.1 persistita non invoca HR (misurazione mock)."""
    row = _eligible_row(
        cecchino_output_json={
            "final": {"status": "available"},
            "signals_matrix": {},
            "purchasability_preview_v31": _valid_v31_snapshot(),
        },
    )
    db = _detail_db(row)

    patches = {p: patch(p) for p in _DETAIL_PATCHES}
    started = time.perf_counter()
    with patches["app.services.cecchino.cecchino_today_service.sync_cecchino_signal_activations"]:
        with patches["app.services.cecchino.cecchino_today_service.build_bookmaker_odds_detail"] as m1:
            m1.return_value = {}
            with patches["app.services.cecchino.cecchino_today_service.build_cecchino_icm_analysis"] as m2:
                m2.return_value = {}
                with patches[
                    "app.services.cecchino.cecchino_technical_analysis_context.build_expected_goal_engine_diagnostics_for_today_row"
                ] as m3:
                    m3.return_value = {}
                    with patches[
                        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail"
                    ] as m4:
                        m4.return_value = {"status": "unavailable"}
                        with patches[
                            "app.services.cecchino.cecchino_today_service.build_goal_intensity_for_today_row"
                        ] as m5:
                            m5.return_value = {}
                            with patches[
                                "app.services.cecchino.cecchino_today_service.build_cecchino_picchetti_debug"
                            ] as m6:
                                m6.return_value = {}
                                with patches[
                                    "app.services.cecchino.cecchino_today_service.build_picchetti_debug_summary"
                                ] as m7:
                                    m7.return_value = {}
                                    with patches[
                                        "app.services.cecchino.cecchino_purchasability_observational.build_observational_maps_for_previews"
                                    ] as m8:
                                        m8.return_value = ({}, {})
                                        with patch(
                                            "app.services.cecchino.cecchino_today_service.resolve_hr_by_market_for_fixture"
                                        ) as mock_hr:
                                            with patch(
                                                "app.services.cecchino.cecchino_today_service._resolve_kpi_panel_for_detail",
                                                return_value=row.kpi_panel_json,
                                            ):
                                                with patch(
                                                    "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_for_detail",
                                                    return_value={},
                                                ):
                                                    with patch(
                                                        "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v2_for_detail",
                                                        return_value={},
                                                    ):
                                                        with patch(
                                                            "app.services.cecchino.cecchino_today_service.resolve_purchasability_preview_v3_for_detail",
                                                            return_value={},
                                                        ):
                                                            detail = get_today_fixture_detail(db, 21807)
    elapsed_ms = (time.perf_counter() - started) * 1000

    mock_hr.assert_not_called()
    assert detail["status"] == "ok"
    assert detail["purchasability_preview_v31"]["source_mode"] == "persisted_pre_match_snapshot"
    # Misurazione locale — non inventare numeri produzione; solo verifica path veloce.
    assert elapsed_ms < 5000
