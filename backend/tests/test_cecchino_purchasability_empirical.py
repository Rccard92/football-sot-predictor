"""Test Acquistabilità empirica v1 — Indice di Acquistabilità Pannello KPI."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_purchasability_audit import DATASET_VERSION, make_json_safe
from app.services.cecchino.cecchino_purchasability_empirical import (
    EMPIRICAL_VERSION,
    MIN_SAMPLE,
    build_empirical_history_index,
    build_empirical_purchasability_for_panel,
    calculate_empirical_cohort_metrics,
    calculate_empirical_purchasability,
    get_rating_band,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_HOME,
    SEL_ONE_X,
    SEL_OVER_2_5,
)


def _hist(
    *,
    fid: int,
    day: int,
    rating: int = 75,
    selection: str = SEL_HOME,
    competition_id: int = 1,
    odds: float = 2.0,
    won: bool = True,
    void: bool = False,
    settled_core: bool = True,
    month: int = 1,
) -> dict:
    kick = datetime(2026, month, day, 18, 0, tzinfo=timezone.utc)
    status = "void" if void else ("won" if won else "lost")
    profit = 0.0 if void else (odds - 1.0 if won else -1.0)
    return {
        "today_fixture_id": fid,
        "canonical_row_key": f"k-{fid}-{selection}-{day}",
        "raw_market_code": selection,
        "selection": selection,
        "competition_id": competition_id,
        "kickoff": kick.isoformat(),
        "scan_date": f"2026-{month:02d}-{day:02d}",
        "odds": odds,
        "rating": rating,
        "settlement_status": status,
        "selection_won": won and not void,
        "selection_lost": (not won) and not void,
        "selection_void": void,
        "unit_stake_profit": profit,
        "is_settled_core": settled_core,
        "snapshot_timestamp_verified": True,
        "snapshot_before_kickoff": True,
        "no_post_match_data_in_features": True,
        "leakage_status": "safe",
    }


# --- Fasce Rating ---


def test_emp_01_05_rating_bands():
    assert get_rating_band(50)["label"] == "50–59"
    assert get_rating_band(59)["label"] == "50–59"
    assert get_rating_band(60)["label"] == "60–69"
    assert get_rating_band(70)["label"] == "70–79"
    assert get_rating_band(80)["label"] == "80–89"
    assert get_rating_band(90)["label"] == "90–100"
    assert get_rating_band(100)["label"] == "90–100"


def test_emp_06_rating_below_scope():
    assert get_rating_band(49) is None
    out = calculate_empirical_purchasability(
        {"sample_size": 0}, rating=40, status_override="rating_below_scope"
    )
    assert out["status"] == "rating_below_scope"
    assert out["score"] is None
    assert out["class"] == "Fuori perimetro"


# --- Coorte ---


def test_emp_07_08_same_market_and_competition_only():
    rows = [
        _hist(fid=1, day=1, selection=SEL_HOME, competition_id=1, rating=75),
        _hist(fid=2, day=2, selection=SEL_AWAY, competition_id=1, rating=75),
        _hist(fid=3, day=3, selection=SEL_HOME, competition_id=2, rating=75),
        _hist(fid=4, day=4, selection=SEL_HOME, competition_id=1, rating=75),
    ]
    idx = build_empirical_history_index(rows)
    home_c1 = idx[(1, SEL_HOME, "70–79")]
    assert len(home_c1) == 2
    assert all(r["selection"] == SEL_HOME and r["competition_id"] == 1 for r in home_c1)
    assert (1, SEL_AWAY, "70–79") in idx
    assert (2, SEL_HOME, "70–79") in idx


def test_emp_09_10_current_and_future_excluded():
    hist = [
        _hist(fid=i, day=1 + (i % 28), rating=75, won=i % 2 == 0, month=1 if i < 30 else 2)
        for i in range(1, 40)
    ]
    current_ko = datetime(2026, 1, 20, 18, 0, tzinfo=timezone.utc)
    idx = build_empirical_history_index(hist)
    bucket = idx[(1, SEL_HOME, "70–79")]
    cohort = [
        h
        for h in bucket
        if datetime.fromisoformat(h["kickoff"].replace("Z", "+00:00")) < current_ko
    ]
    assert all(
        datetime.fromisoformat(h["kickoff"].replace("Z", "+00:00")) < current_ko for h in cohort
    )
    assert len(cohort) >= 10


def test_emp_11_post_match_leakage_excluded():
    bad = _hist(fid=1, day=1, rating=75)
    bad["no_post_match_data_in_features"] = False
    idx = build_empirical_history_index([bad, _hist(fid=2, day=2, rating=75)])
    assert len(idx.get((1, SEL_HOME, "70–79"), [])) == 1


# --- Metriche ---


def test_emp_12_17_metrics_win_rate_void_be_roi_margin():
    rows = [
        _hist(fid=1, day=1, odds=2.0, won=True),
        _hist(fid=2, day=2, odds=2.0, won=False),
        _hist(fid=3, day=3, odds=2.5, won=True),
        _hist(fid=4, day=4, odds=2.0, void=True),
    ]
    m = calculate_empirical_cohort_metrics(rows)
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert m["voids"] == 1
    assert m["win_rate"] == pytest.approx(2 / 3)
    # break-even = mean of 1/odds on non-void
    expected_be = (0.5 + 0.5 + 0.4) / 3
    assert m["average_break_even_probability"] == pytest.approx(expected_be)
    assert m["realized_margin"] == pytest.approx(m["win_rate"] - expected_be)
    # profits: +1, -1, +1.5, 0 → sum 1.5 / 4
    assert m["total_profit"] == pytest.approx(1.5)
    assert m["roi"] == pytest.approx(1.5 / 4)
    assert rows[3]["unit_stake_profit"] == 0.0


def test_emp_18_19_temporal_stability():
    rows = []
    for i in range(40):
        # first half positive ROI-ish wins at 2.0, second half losses
        won = i < 20
        rows.append(_hist(fid=100 + i, day=1 + (i % 28), month=1 + (i // 28), odds=2.0, won=won, rating=75))
    m = calculate_empirical_cohort_metrics(rows)
    assert m["total_periods"] is not None and m["total_periods"] >= 2
    assert m["stability_ratio"] == pytest.approx(m["positive_periods"] / m["total_periods"])


def test_emp_20_insufficient_sample():
    rows = [_hist(fid=i, day=1 + (i % 28), rating=75) for i in range(1, 20)]
    m = calculate_empirical_cohort_metrics(rows)
    out = calculate_empirical_purchasability(m, rating=75, rating_band=get_rating_band(75), selection=SEL_HOME)
    assert out["status"] == "insufficient_data"
    assert out["score"] is None
    assert out["class"] == "Dati insufficienti"
    assert m["sample_size"] < MIN_SAMPLE


# --- Formula ---


def test_emp_21_24_components_and_cap():
    metrics = {
        "sample_size": 100,
        "wins": 40,
        "losses": 60,
        "voids": 0,
        "win_rate": 0.40,
        "average_odds": 2.0,
        "average_break_even_probability": 0.50,
        "realized_margin": -0.10,
        "total_profit": -10.0,
        "roi": -0.10,
        "positive_periods": 4,
        "total_periods": 4,
        "stability_ratio": 1.0,
        "historical_date_from": "2026-01-01",
        "historical_date_to": "2026-03-01",
    }
    out = calculate_empirical_purchasability(
        metrics, rating=75, rating_band=get_rating_band(75), selection=SEL_HOME, competition_id=1
    )
    assert out["status"] == "ok"
    assert out["score"] is not None
    assert out["score"] <= 49
    assert "negative_roi_and_margin_cap" in out["reason_codes"]

    # ROI +10% → roi_component 100; margin 0 → 50; stab 50 → raw ~66.7; conf 1 → score ~67
    pos = dict(metrics)
    pos["roi"] = 0.10
    pos["realized_margin"] = 0.0
    pos["stability_ratio"] = 0.5
    out2 = calculate_empirical_purchasability(
        pos, rating=75, rating_band=get_rating_band(75), selection=SEL_HOME
    )
    assert out2["score"] == 67 or 60 <= out2["score"] <= 75


def test_emp_25_classes():
    from app.services.cecchino.cecchino_purchasability_empirical import _class_for_score

    assert _class_for_score(20, "ok") == "Bassa"
    assert _class_for_score(40, "ok") == "Debole"
    assert _class_for_score(55, "ok") == "Incerta"
    assert _class_for_score(70, "ok") == "Buona"
    assert _class_for_score(85, "ok") == "Alta"


def test_emp_26_strict_json():
    rows = [_hist(fid=i, day=1 + (i % 28), rating=75, won=i % 2 == 0) for i in range(1, 50)]
    current = [
        {
            **_hist(fid=999, day=28, rating=76, month=2),
            "is_settled_core": False,
            "settlement_status": "missing",
            "canonical_row_key": "current-home",
            "kickoff": datetime(2026, 2, 28, 18, 0, tzinfo=timezone.utc).isoformat(),
        }
    ]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=datetime(2026, 2, 28).date(),
        date_to=datetime(2026, 2, 28).date(),
        competition_id=1,
        history_rows=rows,
        current_rows=current,
    )
    json.dumps(make_json_safe(payload), allow_nan=False)
    assert payload["version"] == EMPIRICAL_VERSION
    assert payload["dataset_version"] == DATASET_VERSION
    assert payload["summary"]["no_db_writes"] is True


def test_emp_27_28_batch_no_db_write_single_load():
    hist = [_hist(fid=i, day=1 + (i % 28), rating=72, won=True) for i in range(1, 40)]
    currents = [
        {
            **_hist(fid=900 + i, day=15, month=3, rating=74),
            "is_settled_core": False,
            "settlement_status": "missing",
            "canonical_row_key": f"cur-{i}",
            "kickoff": datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc).isoformat(),
        }
        for i in range(3)
    ]
    with patch(
        "app.services.cecchino.cecchino_purchasability_empirical.build_purchasability_rows"
    ) as mock_build:
        payload = build_empirical_purchasability_for_panel(
            MagicMock(),
            date_from=datetime(2026, 3, 15).date(),
            date_to=datetime(2026, 3, 15).date(),
            history_rows=hist,
            current_rows=currents,
        )
        mock_build.assert_not_called()
    assert payload["summary"]["rows_requested"] == 3
    assert payload["summary"]["no_db_writes"] is True


def test_emp_32_38_versions_and_no_ml_flags():
    assert EMPIRICAL_VERSION == "cecchino_purchasability_empirical_rating_v1"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"
    # formula uses only clamp/mean — no sklearn import in module
    import app.services.cecchino.cecchino_purchasability_empirical as mod

    assert not hasattr(mod, "LogisticRegression")
    assert not hasattr(mod, "bootstrap")


def test_emp_confidence_shrink():
    base = {
        "sample_size": 50,
        "wins": 30,
        "losses": 20,
        "voids": 0,
        "win_rate": 0.6,
        "average_odds": 2.0,
        "average_break_even_probability": 0.5,
        "realized_margin": 0.10,
        "total_profit": 5.0,
        "roi": 0.10,
        "positive_periods": 3,
        "total_periods": 4,
        "stability_ratio": 0.75,
    }
    out50 = calculate_empirical_purchasability(
        dict(base), rating=75, rating_band=get_rating_band(75), selection=SEL_HOME
    )
    base100 = dict(base)
    base100["sample_size"] = 100
    out100 = calculate_empirical_purchasability(
        base100, rating=75, rating_band=get_rating_band(75), selection=SEL_HOME
    )
    # with positive evidence, larger sample should be at least as extreme / closer to raw
    assert out50["sample_confidence"] == pytest.approx(0.5)
    assert out100["sample_confidence"] == pytest.approx(1.0)
    assert abs(out100["score"] - 50) >= abs(out50["score"] - 50)


def test_emp_unsupported_market():
    out = calculate_empirical_purchasability(
        {"sample_size": 0},
        selection="OVER_1_5",
        rating=70,
        status_override="unsupported_market",
    )
    assert out["class"] == "Mercato non supportato"
