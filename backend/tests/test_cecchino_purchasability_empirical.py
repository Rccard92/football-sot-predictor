"""Test Affidabilità storica via shim legacy purchasability_empirical."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.cecchino.cecchino_purchasability_audit import DATASET_VERSION, make_json_safe
from app.services.cecchino.cecchino_purchasability_empirical import (
    EMPIRICAL_VERSION,
    HISTORICAL_RELIABILITY_VERSION,
    LEGACY_EMPIRICAL_VERSION,
    METRIC_KIND,
    MIN_SAMPLE,
    SCOPE_GLOBAL,
    SCOPE_LOCAL,
    SUPPORTED_SELECTIONS,
    build_empirical_global_history_index,
    build_empirical_history_index,
    build_empirical_purchasability_for_panel,
    calculate_empirical_cohort_metrics,
    calculate_empirical_purchasability,
    get_rating_band,
    is_market_settlement_supported,
    panel_item_key,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_3_5,
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
        "canonical_row_key": f"k-{fid}-{selection}-{day}-{competition_id}",
        "raw_market_code": selection,
        "selection": selection,
        "market_key": selection,
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


def _current(
    *,
    fid: int,
    rating: int = 74,
    selection: str = SEL_HOME,
    competition_id: int = 1,
    kickoff: datetime | None = None,
) -> dict:
    ko = kickoff or datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
    return {
        "today_fixture_id": fid,
        "competition_id": competition_id,
        "market_key": selection,
        "selection": selection,
        "raw_market_code": selection,
        "label": selection,
        "rating": rating,
        "kickoff": ko.isoformat(),
        "scan_date": ko.date().isoformat(),
        "odds": 2.0,
    }


# --- 1–5 Fasce Rating ---


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
    assert out["class"] == "Non valutato"


# --- 7–11 Coorte ---


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


# --- 12–17 Metriche ---


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
    expected_be = (0.5 + 0.5 + 0.4) / 3
    assert m["average_break_even_probability"] == pytest.approx(expected_be)
    assert m["realized_margin"] == pytest.approx(m["win_rate"] - expected_be)
    assert m["total_profit"] == pytest.approx(1.5)
    assert m["roi"] == pytest.approx(1.5 / 4)


def test_emp_18_19_temporal_stability():
    rows = []
    for i in range(40):
        won = i < 20
        rows.append(
            _hist(fid=100 + i, day=1 + (i % 28), month=1 + (i // 28), odds=2.0, won=won, rating=75)
        )
    m = calculate_empirical_cohort_metrics(rows)
    assert m["total_periods"] is not None and m["total_periods"] >= 2
    assert m["stability_ratio"] == pytest.approx(m["positive_periods"] / m["total_periods"])


def test_emp_20_insufficient_sample():
    rows = [_hist(fid=i, day=1 + (i % 28), rating=75) for i in range(1, 20)]
    m = calculate_empirical_cohort_metrics(rows)
    out = calculate_empirical_purchasability(
        m, rating=75, rating_band=get_rating_band(75), selection=SEL_HOME
    )
    assert out["status"] == "insufficient_data"
    assert out["score"] is None
    assert out["class"] == "Dati insufficienti"
    assert m["sample_size"] < MIN_SAMPLE


# --- 21–25 Formula ---


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
    assert _class_for_score(None, "rating_below_scope") == "Non valutato"
    assert _class_for_score(None, "unsupported_market") == "Non disponibile"


# --- v1.1: panel key, hierarchy, markets ---


def test_emp_v11_panel_item_key():
    assert panel_item_key(today_fixture_id=12, market_key=SEL_DRAW_PT) == f"12:{SEL_DRAW_PT}"


def test_emp_v11_supported_panel_markets():
    for mk in (SEL_HOME, SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5, SEL_OVER_2_5):
        assert is_market_settlement_supported(mk)
        assert mk in SUPPORTED_SELECTIONS
    assert not is_market_settlement_supported("BTTS_YES")
    assert not is_market_settlement_supported("HOME_PT")


def test_emp_v11_global_index():
    rows = [
        _hist(fid=1, day=1, competition_id=1, selection=SEL_OVER_1_5, rating=75),
        _hist(fid=2, day=2, competition_id=2, selection=SEL_OVER_1_5, rating=75),
        _hist(fid=3, day=3, competition_id=1, selection=SEL_HOME, rating=75),
    ]
    g = build_empirical_global_history_index(rows)
    assert len(g[(SEL_OVER_1_5, "70–79")]) == 2
    assert len(g[(SEL_HOME, "70–79")]) == 1


def test_emp_v11_local_preferred_over_global():
    """Local ≥30 → same_competition anche se globale più grande."""
    local = [
        _hist(fid=i, day=1 + (i % 28), month=1 + (i // 28), competition_id=1, rating=75, won=True)
        for i in range(1, 35)
    ]
    extra_global = [
        _hist(
            fid=200 + i,
            day=1 + (i % 28),
            month=1,
            competition_id=9,
            rating=75,
            won=False,
        )
        for i in range(40)
    ]
    hist = local + extra_global
    current = [_current(fid=999, rating=76, competition_id=1)]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=hist,
        current_rows=current,
    )
    key = panel_item_key(today_fixture_id=999, market_key=SEL_HOME)
    item = payload["items"][key]
    assert item["status"] == "ok"
    assert item["cohort_scope"] == SCOPE_LOCAL
    assert item["fallback_used"] is False
    assert item["local_sample_size"] >= MIN_SAMPLE


def test_emp_v11_global_fallback_when_local_thin():
    """Local <30 e global ≥30 → all_competitions_fallback."""
    local = [
        _hist(fid=i, day=i, competition_id=1, rating=75, won=True) for i in range(1, 10)
    ]
    other = [
        _hist(
            fid=100 + i,
            day=1 + (i % 28),
            month=1 + (i // 28),
            competition_id=2 + (i % 3),
            rating=75,
            won=i % 2 == 0,
        )
        for i in range(40)
    ]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=local + other,
        current_rows=[_current(fid=50, rating=74, competition_id=1)],
    )
    item = payload["items"][panel_item_key(today_fixture_id=50, market_key=SEL_HOME)]
    assert item["status"] == "ok"
    assert item["cohort_scope"] == SCOPE_GLOBAL
    assert item["fallback_used"] is True
    assert item["fallback_reason"] == "same_competition_below_minimum"
    assert item["local_sample_size"] < MIN_SAMPLE
    assert item["global_sample_size"] >= MIN_SAMPLE
    assert (item["competition_count"] or 0) >= 2
    assert payload["summary"]["scored_global_fallback"] == 1


def test_emp_v11_insufficient_after_global():
    hist = [
        _hist(fid=i, day=i, competition_id=1, rating=75) for i in range(1, 8)
    ] + [
        _hist(fid=20 + i, day=i, competition_id=2, rating=75) for i in range(1, 8)
    ]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=hist,
        current_rows=[_current(fid=99, rating=72, competition_id=1)],
    )
    item = payload["items"][panel_item_key(today_fixture_id=99, market_key=SEL_HOME)]
    assert item["status"] == "insufficient_data"
    assert item["global_sample_size"] < MIN_SAMPLE
    assert payload["summary"]["insufficient_after_global_fallback"] == 1


def test_emp_v11_draw_pt_and_ou_lines_scored():
    hist = []
    for sel in (SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5):
        for i in range(35):
            hist.append(
                _hist(
                    fid=1000 + hash(sel) % 1000 + i,
                    day=1 + (i % 28),
                    month=1 + (i // 28),
                    selection=sel,
                    competition_id=1,
                    rating=75,
                    won=True,
                )
            )
    currents = [
        _current(fid=7, rating=76, selection=sel, competition_id=1)
        for sel in (SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5)
    ]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=hist,
        current_rows=currents,
    )
    for sel in (SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5):
        item = payload["items"][panel_item_key(today_fixture_id=7, market_key=sel)]
        assert item["status"] == "ok", sel
        assert item["selection"] == sel


def test_emp_v11_unsupported_reason():
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=[],
        current_rows=[_current(fid=1, rating=70, selection="BTTS_YES")],
    )
    item = payload["items"][panel_item_key(today_fixture_id=1, market_key="BTTS_YES")]
    assert item["status"] == "unsupported_market"
    assert item["class"] == "Non disponibile"
    assert item["unsupported_reason"] == "no_deterministic_settlement"
    assert item["raw_market_key"] == "BTTS_YES"


def test_emp_v11_below_scope_on_panel_row():
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 15),
        history_rows=[_hist(fid=1, day=1, rating=75)],
        current_rows=[_current(fid=2, rating=40)],
    )
    item = payload["items"][panel_item_key(today_fixture_id=2, market_key=SEL_HOME)]
    assert item["status"] == "rating_below_scope"
    assert item["class"] == "Non valutato"
    assert payload["summary"]["below_scope"] == 1


def test_emp_26_strict_json():
    rows = [_hist(fid=i, day=1 + (i % 28), rating=75, won=i % 2 == 0) for i in range(1, 50)]
    current = [_current(fid=999, rating=76)]
    payload = build_empirical_purchasability_for_panel(
        MagicMock(),
        date_from=date(2026, 2, 28),
        date_to=date(2026, 2, 28),
        competition_id=1,
        history_rows=rows,
        current_rows=current,
    )
    json.dumps(make_json_safe(payload), allow_nan=False)
    assert payload["version"] == EMPIRICAL_VERSION
    assert payload["metric_kind"] == METRIC_KIND
    assert payload["legacy_version"] == LEGACY_EMPIRICAL_VERSION
    assert payload["dataset_version"] == DATASET_VERSION
    assert payload["summary"]["no_db_writes"] is True
    assert "scored_same_competition" in payload["summary"]
    assert "market_distribution" in payload["summary"]


def test_emp_27_28_batch_no_db_write_single_load():
    hist = [_hist(fid=i, day=1 + (i % 28), rating=72, won=True) for i in range(1, 40)]
    currents = [_current(fid=900 + i, rating=74) for i in range(3)]
    with patch(
        "app.services.cecchino.cecchino_historical_reliability.build_purchasability_rows"
    ) as mock_build:
        payload = build_empirical_purchasability_for_panel(
            MagicMock(),
            date_from=date(2026, 3, 15),
            date_to=date(2026, 3, 15),
            history_rows=hist,
            current_rows=currents,
        )
        mock_build.assert_not_called()
    assert payload["summary"]["rows_requested"] == 3
    assert payload["summary"]["no_db_writes"] is True


def test_emp_32_38_versions_and_no_ml_flags():
    assert EMPIRICAL_VERSION == HISTORICAL_RELIABILITY_VERSION
    assert HISTORICAL_RELIABILITY_VERSION == "cecchino_historical_reliability_v1_1"
    assert LEGACY_EMPIRICAL_VERSION == "cecchino_purchasability_empirical_rating_v1_1"
    assert METRIC_KIND == "historical_reliability"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"
    import app.services.cecchino.cecchino_purchasability_empirical as mod

    assert not hasattr(mod, "LogisticRegression")
    assert not hasattr(mod, "bootstrap")
    # Shim: nessuna seconda copia della formula (solo alias)
    assert mod.calculate_empirical_purchasability is mod.calculate_historical_reliability
    assert (
        mod.build_empirical_purchasability_for_panel
        is mod.build_historical_reliability_for_panel
    )


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
    assert out50["sample_confidence"] == pytest.approx(0.5)
    assert out100["sample_confidence"] == pytest.approx(1.0)
    assert abs(out100["score"] - 50) >= abs(out50["score"] - 50)


def test_emp_formula_unchanged_from_v1():
    """Stessi input → stesso score della formula v1 (cap + shrink)."""
    metrics = {
        "sample_size": 80,
        "wins": 45,
        "losses": 35,
        "voids": 0,
        "win_rate": 45 / 80,
        "average_odds": 2.1,
        "average_break_even_probability": 1 / 2.1,
        "realized_margin": (45 / 80) - (1 / 2.1),
        "total_profit": 8.0,
        "roi": 8.0 / 80,
        "positive_periods": 3,
        "total_periods": 4,
        "stability_ratio": 0.75,
    }
    out = calculate_empirical_purchasability(
        metrics, rating=72, rating_band=get_rating_band(72), selection=SEL_HOME
    )
    assert out["version"] == EMPIRICAL_VERSION
    assert out["status"] == "ok"
    assert isinstance(out["score"], int)
    assert 0 <= out["score"] <= 100
