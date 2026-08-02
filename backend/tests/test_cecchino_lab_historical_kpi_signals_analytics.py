"""Test analytics segnali KPI storici Cecchino Lab (read-only, STEP 4A)."""

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
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_kpi_signals_analytics import (
    HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
    LEAN_ROW_KEYS,
    MARKET_ORDER,
    RATING_BUCKETS,
    clear_historical_kpi_signals_cache,
    compute_metrics_for_rows,
    compute_summary_from_lean_rows,
    compute_timeline_from_lean_rows,
    get_kpi_signal_activations,
    get_kpi_signals_summary,
    get_kpi_signals_timeline,
    parse_kpi_signals_filters,
    rating_bucket_for,
    sample_class,
)


def _run(**kw):
    status = kw.pop("status", "completed")
    module_policy_json = kw.pop(
        "module_policy_json",
        {"run_scope": "full", "is_partial_run": False},
    )
    return SimpleNamespace(
        id=3,
        season_label="2021/2022",
        status=status,
        completed_at=datetime(2022, 6, 1, tzinfo=timezone.utc),
        requested_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        scan_version="v1",
        matches_total=100,
        matches_processed=100,
        matches_eligible_core=80,
        matches_excluded=20,
        matches_error=0,
        progress_pct=100,
        summary_json={},
        module_policy_json=module_policy_json,
        preflight_json=None,
        error_json=None,
        source_git_commit="abc",
        source_git_commit_source=None,
        source_revision_status=None,
        cancel_requested=False,
        current_dataset_id=None,
        current_match_id=None,
        current_competition=None,
        **kw,
    )


def _lean_row(**overrides):
    base = {
        "source_snapshot_id": 1,
        "lab_match_id": 101,
        "competition_name": "Serie A",
        "kickoff_at": datetime(2021, 9, 15, 15, 0, tzinfo=timezone.utc),
        "home_team": "Home",
        "away_team": "Away",
        "chronological_order": 1,
        "historical_eligibility_status": "eligible_core",
        "market_key": "HOME",
        "market_label": "1",
        "rating": 72,
        "is_real_book_quote": True,
        "is_derived_quote": False,
        "quota_book": 2.0,
        "won": True,
        "profit_1u_real": 1.0,
        "profit_1u_synthetic": None,
        "evaluation_status": "settled",
        "result_reason": None,
    }
    base.update(overrides)
    return {k: base.get(k) for k in LEAN_ROW_KEYS}


@pytest.fixture(autouse=True)
def _clear_kpi_cache():
    clear_historical_kpi_signals_cache()
    yield
    clear_historical_kpi_signals_cache()


# --- unit: rating_bucket_for / sample_class / parse ---


def test_rating_bucket_for_boundaries():
    assert rating_bucket_for(None) is None
    assert rating_bucket_for(49) is None
    assert rating_bucket_for(50) == "50-59"
    assert rating_bucket_for(59) == "50-59"
    assert rating_bucket_for(60) == "60-69"
    assert rating_bucket_for(99) == "90-99"
    assert rating_bucket_for(100) == "100"
    assert rating_bucket_for(150) == "100"


def test_sample_class_thresholds():
    assert sample_class(0) == "very_small"
    assert sample_class(9) == "very_small"
    assert sample_class(10) == "small"
    assert sample_class(29) == "small"
    assert sample_class(30) == "medium"
    assert sample_class(99) == "medium"
    assert sample_class(100) == "large"


def test_parse_kpi_signals_filters_defaults():
    f = parse_kpi_signals_filters()
    assert f["quote_type"] == "real"
    assert f["competition"] is None
    assert f["rating_bucket"] is None
    assert f["selection_key"] is None

    f2 = parse_kpi_signals_filters(quote_type="INVALID")
    assert f2["quote_type"] == "real"


# --- unit: compute_metrics_for_rows ---


def test_compute_metrics_real_win_loss_void_odds():
    rows = [
        _lean_row(won=True, profit_1u_real=0.9, quota_book=1.9),
        _lean_row(
            source_snapshot_id=2,
            won=False,
            profit_1u_real=-1.0,
            quota_book=2.1,
            kickoff_at=datetime(2021, 9, 16, 15, 0, tzinfo=timezone.utc),
        ),
        _lean_row(
            source_snapshot_id=3,
            won=None,
            profit_1u_real=None,
            quota_book=1.8,
            kickoff_at=datetime(2021, 9, 17, 15, 0, tzinfo=timezone.utc),
        ),
        _lean_row(
            source_snapshot_id=4,
            won=True,
            profit_1u_real=0.0,
            quota_book=2.0,
            kickoff_at=datetime(2021, 9, 18, 15, 0, tzinfo=timezone.utc),
        ),
    ]
    m = compute_metrics_for_rows(rows, "real")
    assert m["signals_count"] == 4
    assert m["evaluated_count"] == 3
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert m["pending_or_unsettled"] == 1
    assert m["void_or_zero_profit"] == 1
    assert m["stake_count"] == 3
    assert m["win_rate_pct"] == pytest.approx(66.7, abs=0.1)
    assert m["profit_units"] == pytest.approx(-0.1, abs=0.01)
    assert m["roi_pct"] == pytest.approx(-3.33, abs=0.1)
    assert m["average_odds_played"] == pytest.approx(2.0, abs=0.01)
    assert m["average_odds_won"] == pytest.approx(1.95, abs=0.01)
    assert m["average_odds_void"] == pytest.approx(1.5, abs=0.01)


def test_compute_metrics_derived_and_stake_zero():
    rows = [
        _lean_row(
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=0.5,
            won=True,
        ),
        _lean_row(
            source_snapshot_id=2,
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=None,
            won=None,
            kickoff_at=datetime(2021, 9, 16, 15, 0, tzinfo=timezone.utc),
        ),
    ]
    m = compute_metrics_for_rows(rows, "derived")
    assert m["signals_count"] == 2
    assert m["stake_count"] == 1
    assert m["profit_units"] == 0.5
    assert m["roi_pct"] == 50.0

    empty = compute_metrics_for_rows(
        [_lean_row(is_real_book_quote=False, profit_1u_real=None)], "real"
    )
    assert empty["stake_count"] == 0
    assert empty["profit_units"] is None
    assert empty["roi_pct"] is None
    assert empty["average_odds_void"] is None


def test_overall_all_separates_real_and_synthetic():
    rows = [
        _lean_row(
            is_real_book_quote=True,
            profit_1u_real=1.0,
            won=True,
            rating=70,
        ),
        _lean_row(
            source_snapshot_id=2,
            market_key="OVER_2_5",
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=2.0,
            won=True,
            rating=80,
            kickoff_at=datetime(2021, 9, 16, 15, 0, tzinfo=timezone.utc),
        ),
    ]
    run = _run()
    summary = compute_summary_from_lean_rows(
        run, rows, parse_kpi_signals_filters(quote_type="all")
    )
    overall = summary["overall"]
    assert "real" in overall and "synthetic" in overall
    assert overall["real"]["roi_pct"] == 100.0
    assert overall["synthetic"]["roi_pct"] == 200.0
    assert overall["real"]["profit_units"] != overall["synthetic"]["profit_units"]


# --- unit: compute_summary_from_lean_rows ---


def _universe_rows():
    """Righe su tutte le fasce rating e quote real/derived."""
    rows = []
    ratings = [55, 65, 75, 85, 95, 100]
    for i, r in enumerate(ratings):
        rows.append(
            _lean_row(
                source_snapshot_id=i + 1,
                lab_match_id=100 + i,
                rating=r,
                market_key="HOME",
                kickoff_at=datetime(2021, 9, 10 + i, 15, 0, tzinfo=timezone.utc),
                won=True,
                profit_1u_real=0.5,
                quota_book=1.5,
            )
        )
    rows.append(
        _lean_row(
            source_snapshot_id=10,
            lab_match_id=110,
            rating=72,
            market_key="DRAW",
            competition_name="Premier League",
            kickoff_at=datetime(2021, 10, 5, 15, 0, tzinfo=timezone.utc),
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=1.0,
            won=True,
        )
    )
    return rows


def test_compute_summary_structure_and_heatmap():
    rows = _universe_rows()
    run = _run()
    filters = parse_kpi_signals_filters(quote_type="real")
    out = compute_summary_from_lean_rows(run, rows, filters, query_count=3)

    assert out["schema_version"] == HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION
    assert out["run"]["run_id"] == 3
    assert out["run"]["scope"] == "full"
    assert len(out["by_rating_bucket"]) == len(RATING_BUCKETS)
    buckets = {b["rating_bucket"] for b in out["by_rating_bucket"]}
    assert buckets == set(RATING_BUCKETS)

    heatmap = out["heatmap"]
    assert heatmap["rating_buckets"] == list(RATING_BUCKETS)
    assert "HOME" in heatmap["selection_keys"]
    assert heatmap["cells"]
    cell = next(c for c in heatmap["cells"] if c["rating_bucket"] == "70-79" and c["selection_key"] == "HOME")
    assert cell["sample_class"] in ("very_small", "small", "medium", "large")
    assert out["resource_profile"]["full_orm_entities_loaded"] is False
    assert out["resource_profile"]["jsonb_payloads_loaded"] is False


def test_filters_applied_via_prefiltered_rows():
    rows = _universe_rows()
    run = _run()

    comp_filtered = [r for r in rows if r["competition_name"] == "Serie A"]
    out_comp = compute_summary_from_lean_rows(
        run, comp_filtered, parse_kpi_signals_filters(competition="Serie A")
    )
    assert out_comp["overall"]["real"]["signals_count"] == len(comp_filtered)

    date_filtered = [
        r
        for r in rows
        if isinstance(r["kickoff_at"], datetime)
        and r["kickoff_at"].date() >= date(2021, 9, 12)
        and r.get("is_real_book_quote")
    ]
    out_date = compute_summary_from_lean_rows(
        run,
        date_filtered,
        parse_kpi_signals_filters(date_from="2021-09-12"),
    )
    assert out_date["overall"]["real"]["signals_count"] == len(date_filtered)

    bucket_filtered = [r for r in rows if rating_bucket_for(r["rating"]) == "70-79"]
    out_bucket = compute_summary_from_lean_rows(
        run,
        bucket_filtered,
        parse_kpi_signals_filters(rating_bucket="70-79"),
    )
    assert all(b["rating_bucket"] != "70-79" or b["evaluated_count"] >= 0 for b in out_bucket["by_rating_bucket"])

    sel_filtered = [r for r in rows if r["market_key"] == "HOME"]
    out_sel = compute_summary_from_lean_rows(
        run,
        sel_filtered,
        parse_kpi_signals_filters(selection_key="HOME"),
    )
    assert out_sel["overall"]["real"]["signals_count"] == len(sel_filtered)


def test_partial_run_labeled_in_summary():
    run = _run(
        module_policy_json={
            "run_scope": "pilot",
            "is_partial_run": True,
            "not_full_season_report": True,
            "max_matches": 50,
            "pilot_strategy": "balanced",
        }
    )
    out = compute_summary_from_lean_rows(run, _universe_rows(), parse_kpi_signals_filters())
    assert out["run"]["is_partial_run"] is True
    assert out["run"]["scope"] == "pilot"
    assert out["run"].get("max_matches") == 50


# --- unit: compute_timeline_from_lean_rows ---


def test_timeline_date_week_matchday_cumulative_and_buckets():
    rows = [
        _lean_row(
            kickoff_at=datetime(2021, 9, 6, 15, 0, tzinfo=timezone.utc),
            profit_1u_real=1.0,
            won=True,
            rating=60,
        ),
        _lean_row(
            source_snapshot_id=2,
            kickoff_at=datetime(2021, 9, 7, 15, 0, tzinfo=timezone.utc),
            profit_1u_real=-1.0,
            won=False,
            rating=70,
            market_key="DRAW",
        ),
        _lean_row(
            source_snapshot_id=3,
            kickoff_at=datetime(2021, 9, 20, 15, 0, tzinfo=timezone.utc),
            profit_1u_real=0.5,
            won=True,
            rating=80,
        ),
    ]
    run = _run()
    filters = parse_kpi_signals_filters(quote_type="real")

    tl_date = compute_timeline_from_lean_rows(run, rows, filters, group_by="date")
    assert len(tl_date["points"]) == 3
    assert tl_date["points"][-1]["cumulative_profit_units"] == 0.5
    assert tl_date["points"][-1]["cumulative_roi_pct"] == pytest.approx(16.67, abs=0.1)
    assert tl_date["points"][0]["by_rating_bucket"]

    tl_week = compute_timeline_from_lean_rows(run, rows, filters, group_by="week")
    assert tl_week["effective_group_by"] == "week"
    assert len(tl_week["points"]) == 2
    assert tl_week["points"][0]["group_key"].startswith("2021-W")

    tl_md = compute_timeline_from_lean_rows(run, rows, filters, group_by="matchday")
    assert tl_md["group_by"] == "matchday"
    assert tl_md["effective_group_by"] == "date"
    assert tl_md["grouping_fallback"] == "date"


def test_timeline_all_quote_type_cumulative_split():
    rows = [
        _lean_row(profit_1u_real=1.0, won=True),
        _lean_row(
            source_snapshot_id=2,
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=2.0,
            won=True,
            kickoff_at=datetime(2021, 9, 16, 15, 0, tzinfo=timezone.utc),
        ),
    ]
    run = _run()
    tl = compute_timeline_from_lean_rows(
        run, rows, parse_kpi_signals_filters(quote_type="all"), group_by="date"
    )
    pt = tl["points"][-1]
    assert "real" in pt and "synthetic" in pt
    assert pt["cumulative_profit_units"]["real"] is not None
    assert pt["cumulative_profit_units"]["synthetic"] is not None


# --- service layer: get_kpi_signals_* ---


def test_get_kpi_signals_summary_run_not_found():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(CecchinoLabImportError) as exc:
        get_kpi_signals_summary(db, 999, parse_kpi_signals_filters())
    assert exc.value.code == "run_not_found"


def test_get_kpi_signals_summary_completed_run():
    run = _run()
    rows = _universe_rows()
    db = MagicMock()
    db.get.return_value = run

    with patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_lean_rows",
        side_effect=[(rows, 1), (rows, 1)],
    ) as fetch_mock, patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_diagnostics",
        return_value=({"rows_scanned": 10, "eligible_rows": 7}, 1),
    ) as diag_mock:
        out = get_kpi_signals_summary(db, 3, parse_kpi_signals_filters())

    assert out["schema_version"] == HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION
    assert fetch_mock.call_count == 2
    diag_mock.assert_called_once()
    assert not db.add.called
    assert not db.commit.called


def test_get_kpi_signals_summary_cache_hit():
    run = _run()
    rows = _universe_rows()
    db = MagicMock()
    db.get.return_value = run
    call_count = {"n": 0}

    def fetch_side_effect(*_a, **_k):
        call_count["n"] += 1
        return rows, 1

    with patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_lean_rows",
        side_effect=fetch_side_effect,
    ), patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_diagnostics",
        return_value=({"rows_scanned": 10}, 1),
    ):
        filters = parse_kpi_signals_filters()
        get_kpi_signals_summary(db, 3, filters)
        get_kpi_signals_summary(db, 3, filters)

    assert call_count["n"] == 2


def test_get_kpi_signals_timeline_cache_and_clear():
    run = _run()
    rows = _universe_rows()
    db = MagicMock()
    db.get.return_value = run
    call_count = {"n": 0}

    def fetch_side_effect(*_a, **_k):
        call_count["n"] += 1
        return rows, 1

    with patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_lean_rows",
        side_effect=fetch_side_effect,
    ):
        filters = parse_kpi_signals_filters()
        get_kpi_signals_timeline(db, 3, filters)
        get_kpi_signals_timeline(db, 3, filters)
        assert call_count["n"] == 1

        clear_historical_kpi_signals_cache()
        get_kpi_signals_timeline(db, 3, filters)
        assert call_count["n"] == 2


def test_get_kpi_signal_activations_pagination_and_ordering():
    base_ko = datetime(2021, 9, 15, 15, 0, tzinfo=timezone.utc)
    rows = []
    for i, mk in enumerate(["AWAY", "HOME", "DRAW"]):
        rows.append(
            _lean_row(
                source_snapshot_id=i + 1,
                market_key=mk,
                kickoff_at=base_ko.replace(day=15 + i),
                chronological_order=i + 1,
            )
        )
    for i in range(60):
        rows.append(
            _lean_row(
                source_snapshot_id=100 + i,
                lab_match_id=200 + i,
                kickoff_at=datetime(2021, 8, 1, 12, 0, tzinfo=timezone.utc),
            )
        )

    run = _run()
    db = MagicMock()
    db.get.return_value = run

    with patch(
        "app.services.cecchino_data_lab.historical_kpi_signals_analytics._fetch_lean_rows",
        return_value=(rows, 1),
    ):
        default_page = get_kpi_signal_activations(db, 3, parse_kpi_signals_filters())
        assert default_page["limit"] == 50
        assert default_page["total"] == len(rows)
        assert len(default_page["items"]) == 50

        capped = get_kpi_signal_activations(
            db, 3, parse_kpi_signals_filters(), limit=200
        )
        assert capped["limit"] == 100

        offset_page = get_kpi_signal_activations(
            db, 3, parse_kpi_signals_filters(), limit=10, offset=5
        )
        assert offset_page["offset"] == 5
        assert len(offset_page["items"]) == 10

        full = get_kpi_signal_activations(
            db, 3, parse_kpi_signals_filters(), limit=100, offset=0
        )
        kickoffs = [it["kickoff_at"] for it in full["items"]]
        assert kickoffs == sorted(kickoffs, reverse=True)

    rp = default_page["resource_profile"]
    assert rp["full_orm_entities_loaded"] is False
    assert rp["jsonb_payloads_loaded"] is False
    assert not db.add.called
    assert not db.commit.called


def test_market_order_constant_matches_kpi_defs():
    assert "HOME" in MARKET_ORDER
    assert len(RATING_BUCKETS) == 6


# --- API routes ---


def _api_client(db=None):
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    db = db or MagicMock()

    def override():
        yield db

    app.dependency_overrides[get_db] = override
    return TestClient(app), db


def test_api_kpi_signals_routes():
    client, db = _api_client()
    minimal_summary = {
        "schema_version": HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
        "run": {"run_id": 3},
        "overall": {"real": {}},
        "filters": {},
    }
    minimal_timeline = {
        "schema_version": HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION,
        "points": [],
        "filters": {},
    }
    minimal_activations = {"items": [], "total": 0, "limit": 50, "offset": 0, "filters": {}}

    with patch(
        "app.routes.cecchino_lab.get_kpi_signals_summary",
        return_value=minimal_summary,
    ) as m_sum:
        r = client.get("/api/cecchino-lab/historical-scans/3/kpi-signals/summary")
        assert r.status_code == 200
        assert r.json()["schema_version"] == HISTORICAL_KPI_SIGNALS_ANALYTICS_VERSION
        m_sum.assert_called_once()

    with patch(
        "app.routes.cecchino_lab.get_kpi_signals_timeline",
        return_value=minimal_timeline,
    ) as m_tl:
        r = client.get(
            "/api/cecchino-lab/historical-scans/3/kpi-signals/timeline?group_by=week"
        )
        assert r.status_code == 200
        m_tl.assert_called_once()

    with patch(
        "app.routes.cecchino_lab.get_kpi_signal_activations",
        return_value=minimal_activations,
    ) as m_act:
        r = client.get(
            "/api/cecchino-lab/historical-scans/3/kpi-signals/activations?limit=25&offset=2"
        )
        assert r.status_code == 200
        m_act.assert_called_once()

    assert not db.add.called
    assert not db.commit.called

    with patch(
        "app.routes.cecchino_lab.get_kpi_signals_summary",
        side_effect=CecchinoLabImportError("run_not_found", "x", status_code=404),
    ):
        r404 = client.get("/api/cecchino-lab/historical-scans/999/kpi-signals/summary")
        assert r404.status_code == 404
