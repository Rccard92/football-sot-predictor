"""Test contesto osservazionale Acquistabilità (sample/ROI read-only)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_purchasability_evaluation import EVAL_LOST, EVAL_WON
from app.services.cecchino.cecchino_purchasability_observational import (
    OBS_MIN_SAMPLE,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT,
    STATUS_NOT_EVALUATED,
    build_purchasability_observational_by_market,
)


def _eval(
    *,
    market_key: str = "HOME",
    score: int = 65,
    status: str = EVAL_WON,
    profit: float = 1.5,
    odds: float = 2.5,
):
    return SimpleNamespace(
        market_key=market_key,
        purchasability_score=score,
        evaluation_status=status,
        today_fixture_id=1,
        quota_book=odds,
        profit_units=profit,
        phase_1_score=50,
        phase_2_score=50,
    )


def _db_with_rows(rows: list):
    db = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    db.scalars.return_value = scalars
    return db


def test_available_when_sample_sufficient():
    rows = [
        _eval(status=EVAL_WON, profit=1.5)
        for _ in range(OBS_MIN_SAMPLE)
    ]
    db = _db_with_rows(rows)
    out = build_purchasability_observational_by_market(
        db,
        items=[{"market_key": "HOME", "score": 65}],
        candidate_version="cecchino_purchasability_v1_preview_candidate_2",
    )
    assert "HOME" in out
    assert out["HOME"]["status"] == STATUS_AVAILABLE
    assert out["HOME"]["sample_size"] == OBS_MIN_SAMPLE
    assert out["HOME"]["score_band"] == "60-79"
    assert out["HOME"]["roi_pct"] is not None


def test_insufficient_when_sample_small():
    rows = [_eval(status=EVAL_LOST, profit=-1.0) for _ in range(5)]
    db = _db_with_rows(rows)
    out = build_purchasability_observational_by_market(
        db,
        items=[{"market_key": "HOME", "score": 62}],
        candidate_version="cand",
    )
    assert out["HOME"]["status"] == STATUS_INSUFFICIENT
    assert out["HOME"]["sample_size"] == 5


def test_not_evaluated_when_no_settled():
    db = _db_with_rows([])
    out = build_purchasability_observational_by_market(
        db,
        items=[{"market_key": "AWAY", "score": 70}],
        candidate_version="cand",
    )
    assert out["AWAY"]["status"] == STATUS_NOT_EVALUATED
    assert out["AWAY"]["sample_size"] == 0
    assert out["AWAY"]["roi_pct"] is None


def test_not_evaluated_when_score_missing():
    db = _db_with_rows([_eval() for _ in range(40)])
    out = build_purchasability_observational_by_market(
        db,
        items=[{"market_key": "HOME", "score": None, "status": "unavailable"}],
        candidate_version="cand",
    )
    assert out["HOME"]["status"] == STATUS_NOT_EVALUATED


def test_empty_items_returns_empty():
    db = _db_with_rows([])
    assert (
        build_purchasability_observational_by_market(
            db, items=[], candidate_version="cand"
        )
        == {}
    )


def test_score_band_mismatch_not_evaluated():
    """Score 10 (band 1-19) non matcha evaluation in band 60-79."""
    rows = [_eval(score=65, status=EVAL_WON) for _ in range(40)]
    db = _db_with_rows(rows)
    out = build_purchasability_observational_by_market(
        db,
        items=[{"market_key": "HOME", "score": 10}],
        candidate_version="cand",
    )
    assert out["HOME"]["status"] == STATUS_NOT_EVALUATED
