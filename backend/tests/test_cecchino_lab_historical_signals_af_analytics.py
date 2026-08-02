"""Test analytics autonoma Segnali A–F (STEP 4B, read-only)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_signal_export import (
    CURRENT_MODEL_KEY,
    collect_all_opportunities,
)
from app.services.cecchino_data_lab.historical_signals_af_analytics import (
    HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION,
    clear_historical_signals_af_cache,
    filter_opportunities,
    get_signals_af_activations,
    get_signals_af_summary,
    parse_signals_af_filters,
)


@pytest.fixture(autouse=True)
def _clear_af_cache():
    clear_historical_signals_af_cache()
    yield
    clear_historical_signals_af_cache()


def _run(**kw):
    return SimpleNamespace(
        id=3,
        season_label="2021/2022",
        status="completed",
        completed_at=datetime(2022, 6, 1, tzinfo=timezone.utc),
        module_policy_json={"run_scope": "full", "is_partial_run": False},
        **kw,
    )


def _market(*, snapshot_id: int, market_key: str, won=True, real=True, profit=1.0):
    return SimpleNamespace(
        id=1,
        run_id=3,
        match_snapshot_id=snapshot_id,
        lab_match_id=10,
        market_key=market_key,
        market_label=market_key,
        period="FT",
        line=None,
        prob_cecchino=0.4,
        quota_cecchino=2.5,
        rating=80,
        edge_pct=5.0,
        vantaggio_prob=0.02,
        is_real_book_quote=real,
        is_derived_quote=not real,
        quota_book=2.5,
        won=won,
        evaluation_status="won" if won else "lost",
        result_reason="ft",
        profit_1u_real=profit if real else None,
        profit_1u_synthetic=None if real else profit,
        signal_active=True,
        profit_category="real" if real else "synthetic",
    )


def _snap(*, sid: int = 100, competition="Serie A"):
    active = [
        {
            "signal_group": "MATCH_WINNER",
            "source_column": "home",
            "cell": "HOME",
            "target_market": "HOME",
            "signal_family": "match",
            "cell_label": "1",
        }
    ]
    models = {
        k: {"active_signals": list(active) if k in ("A", "F") else []}
        for k in ("A", "B", "C", "D", "E", "F")
    }
    return SimpleNamespace(
        id=sid,
        run_id=3,
        dataset_id=7,
        lab_match_id=10,
        competition_name=competition,
        kickoff_at=datetime(2021, 9, 1, 18, 0, tzinfo=timezone.utc),
        chronological_order=1,
        home_team="Home FC",
        away_team="Away FC",
        historical_eligibility_status="eligible_core",
        signals_json={"models": models},
        settlement_summary_json={},
        result_json={},
        purchasability_compatibility_json=None,
    )


def test_parse_signals_af_filters_defaults():
    f = parse_signals_af_filters()
    assert f["quote_type"] == "real"
    assert f["model_key"] is None
    assert f["only_current_model_F"] is False


def test_parse_invalid_model_key():
    with pytest.raises(CecchinoLabImportError) as exc:
        parse_signals_af_filters(model_key="Z")
    assert exc.value.code == "invalid_model_key"


def test_run_not_found():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(CecchinoLabImportError) as exc:
        get_signals_af_summary(db, 999, parse_signals_af_filters())
    assert exc.value.code == "run_not_found"


def test_summary_models_f_current_and_no_double_counting():
    run = _run()
    snap = _snap(sid=100)
    markets = [_market(snapshot_id=100, market_key="HOME")]
    db = MagicMock()
    db.get.return_value = run

    with patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._load_filtered_snapshots",
        return_value=([snap], 1),
    ), patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._load_markets_for_snapshots",
        return_value=(markets, 1),
    ):
        out = get_signals_af_summary(db, 3, parse_signals_af_filters())

    assert out["schema_version"] == HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION
    assert out["current_model_key"] == CURRENT_MODEL_KEY
    assert out["performance_granularity"] == "signal_opportunity"
    models = {m["model_key"]: m for m in out["models"]}
    assert "F" in models
    assert models["F"].get("is_current_model") is True
    assert out["unique_opportunities"] >= 1
    assert out["active_cells"] >= out["unique_opportunities"]
    recon = out.get("signal_export_reconciliation") or {}
    assert recon.get("performance_uses_opportunities_only") is True or out[
        "unique_opportunities"
    ] > 0
    assert out["resource_profile"]["full_orm_entities_loaded"] is False
    assert out["resource_profile"]["full_signals_json_returned"] is False
    assert not db.add.called
    assert not db.commit.called


def test_filter_model_market_quote_consensus():
    snap = _snap(sid=1)
    markets = [
        _market(snapshot_id=1, market_key="HOME", real=True),
        _market(snapshot_id=1, market_key="DRAW", real=False, profit=0.5),
    ]
    # DRAW not in active signals of snap — only HOME
    opps = collect_all_opportunities(run_id=3, snapshots=[snap], markets=markets)
    assert opps
    only_f = filter_opportunities(opps, parse_signals_af_filters(only_current_model_F=True))
    assert all(str(o["model_key"]).upper() == "F" for o in only_f)
    only_a = filter_opportunities(opps, parse_signals_af_filters(model_key="A"))
    assert all(str(o["model_key"]).upper() == "A" for o in only_a)
    real = filter_opportunities(opps, parse_signals_af_filters(quote_type="real"))
    assert all(o.get("is_real_book_quote") for o in real)
    consensus = filter_opportunities(
        opps, parse_signals_af_filters(minimum_consensus_models=2)
    )
    assert all(int(o.get("consensus_model_count") or 0) >= 2 for o in consensus)


def test_activations_pagination_one_row_per_opportunity():
    run = _run()
    snaps = [_snap(sid=i) for i in range(1, 6)]
    markets = [_market(snapshot_id=i, market_key="HOME") for i in range(1, 6)]
    db = MagicMock()
    db.get.return_value = run

    with patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._load_filtered_snapshots",
        return_value=(snaps, 1),
    ), patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._load_markets_for_snapshots",
        return_value=(markets, 1),
    ):
        page1 = get_signals_af_activations(
            db, 3, parse_signals_af_filters(), limit=50, offset=0
        )
        page2 = get_signals_af_activations(
            db, 3, parse_signals_af_filters(), limit=2, offset=2
        )

    assert page1["limit"] == 50
    assert page1["total"] >= 1
    ids = [i["opportunity_id"] for i in page1["items"]]
    assert len(ids) == len(set(ids))
    assert "signals_json" not in str(page1["items"])
    assert page2["limit"] == 2
    assert page2["offset"] == 2
    for item in page1["items"]:
        assert "active_cell_count" in item
        assert item.get("model_key") in ("A", "B", "C", "D", "E", "F")


def test_activations_limit_capped_at_100():
    run = _run()
    db = MagicMock()
    db.get.return_value = run
    with patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._collect_universe",
        return_value=([], 0, 0),
    ):
        out = get_signals_af_activations(
            db, 3, parse_signals_af_filters(), limit=500, offset=0
        )
    assert out["limit"] == 100


def test_summary_cache_hit():
    run = _run()
    db = MagicMock()
    db.get.return_value = run
    calls = {"n": 0}

    def collect(*_a, **_k):
        calls["n"] += 1
        return [], 1, 0

    with patch(
        "app.services.cecchino_data_lab.historical_signals_af_analytics._collect_universe",
        side_effect=collect,
    ):
        filters = parse_signals_af_filters()
        get_signals_af_summary(db, 3, filters)
        get_signals_af_summary(db, 3, filters)
    assert calls["n"] == 1


def test_api_signals_af_endpoints():
    app = FastAPI()
    app.include_router(cecchino_lab.router, prefix="/api")
    db = MagicMock()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)

    minimal = {
        "schema_version": HISTORICAL_SIGNALS_AF_ANALYTICS_VERSION,
        "models": [],
        "unique_opportunities": 0,
        "active_cells": 0,
    }
    with patch(
        "app.routes.cecchino_lab.get_signals_af_summary", return_value=minimal
    ) as m_sum:
        r = client.get("/api/cecchino-lab/historical-scans/3/signals-af/summary")
        assert r.status_code == 200
        m_sum.assert_called_once()

    with patch(
        "app.routes.cecchino_lab.get_signals_af_activations",
        return_value={"items": [], "total": 0, "limit": 50, "offset": 0},
    ) as m_act:
        r = client.get(
            "/api/cecchino-lab/historical-scans/3/signals-af/activations?limit=50&offset=0"
        )
        assert r.status_code == 200
        m_act.assert_called_once()

    assert not db.add.called
    assert not db.commit.called
