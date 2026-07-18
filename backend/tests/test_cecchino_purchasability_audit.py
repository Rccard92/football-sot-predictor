"""Test Fase 1.1 Indice di Acquistabilità — integrità temporale e core."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import math
import pytest

from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _compute_rating
from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    NORM_NOT_APPLICABLE_OVERLAPPING,
    OPPOSITION_SUPPORTED,
    MARKET_COMPLETE_SETS,
    get_opposition,
    normalization_status_for_family,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    AUDIT_VERSION,
    DATASET_VERSION,
    FEATURE_CANDIDATE_KEYS,
    FIDELITY_FALLBACK,
    FIDELITY_PANEL,
    TARGET_KEYS,
    _input_redundancy,
    _midranks,
    _normalize_book_probs,
    _spearman,
    build_purchasability_audit,
    build_purchasability_dataset,
    build_purchasability_rows,
    resolve_purchasability_snapshot_timestamp,
    resolve_selection_key,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino import cecchino_kpi_signals as kpi_mod


def _panel_row(key: str, book: float, cec: float | None, *, book_source: str = "betfair_raw"):
    if cec is None:
        return {
            "market_key": key,
            "segno": key,
            "label": key,
            "quota_book": book,
            "quota_cecchino": None,
            "prob_book": round(1.0 / book, 4),
            "prob_cecchino": None,
            "vantaggio_prob": None,
            "edge_pct": None,
            "score_acquisto": None,
            "rating": None,
            "status": "book_only",
            "book_source": book_source,
        }
    prob_c = round(1.0 / cec, 4)
    prob_b = round(1.0 / book, 4)
    vant = round(prob_c - prob_b, 4)
    edge = round((book / cec - 1.0) * 100.0, 2)
    score = round(prob_c * edge / 100.0, 4)
    rating = _compute_rating(prob_c, vant, edge)
    return {
        "market_key": key,
        "segno": key,
        "label": key,
        "quota_book": book,
        "quota_cecchino": cec,
        "prob_book": prob_b,
        "prob_cecchino": prob_c,
        "vantaggio_prob": vant,
        "edge_pct": edge,
        "score_acquisto": score,
        "rating": rating,
        "status": "available",
        "book_source": book_source,
    }


def _full_rows(**kwargs):
    src = kwargs.pop("book_source", "betfair_raw_match_winner")
    return [
        _panel_row(SEL_HOME, 2.2, 2.0, book_source=src),
        _panel_row(SEL_DRAW, 3.4, 3.2, book_source=src),
        _panel_row(SEL_AWAY, 3.5, 3.8, book_source=src),
        _panel_row(SEL_ONE_X, 1.4, 1.35, book_source="derived_from_betfair_1x2"),
        _panel_row(SEL_X_TWO, 1.7, 1.75, book_source="derived_from_betfair_1x2"),
        _panel_row(SEL_ONE_TWO, 1.3, 1.28, book_source="derived_from_betfair_1x2"),
        _panel_row(SEL_OVER_2_5, 1.9, 1.85, book_source="betfair_raw_over_under"),
        _panel_row(SEL_UNDER_2_5, 2.0, 2.05, book_source="betfair_raw_over_under"),
    ]


def _fixture(
    *,
    fid: int = 1,
    kickoff: datetime | None = None,
    updated_at: datetime | None = None,
    odds_checked_at: datetime | None = None,
    panel_odds_meta: dict | None = None,
    snapshot_odds_meta: dict | None = None,
    panel_rows: list | None = None,
    ft: tuple[int, int] | None = (2, 1),
    ht: tuple[int, int] | None = (1, 0),
):
    ko = kickoff or datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)
    pre = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
    meta = panel_odds_meta if panel_odds_meta is not None else {
        "last_betfair_refresh_at": "2026-07-10T08:00:00Z",
        "odds_updated_at": "2026-07-10T08:00:00Z",
        "odds_fetched_at": "2026-07-10T07:55:00Z",
    }
    rows = panel_rows if panel_rows is not None else _full_rows()
    return SimpleNamespace(
        id=fid,
        local_fixture_id=100 + fid,
        provider_fixture_id=9000 + fid,
        competition_id=39,
        league_name="Premier",
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=ko,
        scan_date=date(2026, 7, 10),
        updated_at=updated_at or datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
        odds_checked_at=odds_checked_at,
        score_fulltime_home=ft[0] if ft else None,
        score_fulltime_away=ft[1] if ft else None,
        score_halftime_home=ht[0] if ht else None,
        score_halftime_away=ht[1] if ht else None,
        match_display_status="finished",
        fixture_status="FT",
        kpi_panel_json={
            "version": "cecchino_kpi_v2_betfair",
            "bookmaker": {
                "name": "Betfair",
                "provider_bookmaker_id": 11,
                "provider_source": "api_football",
            },
            "odds_meta": meta,
            "rows": rows,
        },
        odds_snapshot_json={
            "odds_meta": snapshot_odds_meta or {},
        },
    )


def _db_with(fixtures: list):
    db = MagicMock()
    db.scalars.return_value.all.return_value = fixtures
    db.add = MagicMock()
    db.commit = MagicMock()
    return db


# --- Timestamp ---


def test_updated_at_post_kickoff_but_odds_meta_pre_match_valid():
    fx = _fixture(
        updated_at=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
        panel_odds_meta={"last_betfair_refresh_at": "2026-07-10T08:00:00Z"},
    )
    snap = resolve_purchasability_snapshot_timestamp(fx)
    assert snap["snapshot_fidelity"] == FIDELITY_PANEL
    assert snap["snapshot_timestamp_verified"] is True
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["is_pre_match"] is True
    assert home["is_core"] is True
    assert home["no_post_match_data_in_features"] is True


def test_only_updated_at_not_core():
    fx = _fixture(
        panel_odds_meta={},
        snapshot_odds_meta={},
        odds_checked_at=None,
        updated_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
    )
    snap = resolve_purchasability_snapshot_timestamp(fx)
    assert snap["snapshot_fidelity"] == FIDELITY_FALLBACK
    assert snap["snapshot_timestamp_verified"] is False
    rows = build_purchasability_rows(_db_with([fx]))
    assert all(not r["is_core"] for r in rows)
    assert any("snapshot_timestamp_not_verifiable" in r["exclusion_reason_codes"] for r in rows)
    assert all(r["no_post_match_data_in_features"] is False for r in rows)


def test_odds_meta_post_kickoff_excluded_leakage():
    fx = _fixture(
        panel_odds_meta={"last_betfair_refresh_at": "2026-07-10T19:00:00Z"},
        updated_at=datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc),
    )
    rows = build_purchasability_rows(_db_with([fx]))
    assert any(r["leakage_status"] == "excluded_leakage" for r in rows)
    assert all(not r["is_core"] for r in rows)


# --- Bookmaker ---


def test_odds_source_from_row():
    fx = _fixture()
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["odds_source"] == "betfair_raw_match_winner"
    assert home["bookmaker_name"] == "Betfair"
    assert home["bookmaker_provider_id"] == 11
    assert not isinstance(home["bookmaker_name"], dict)


def test_book_source_filter_does_not_overwrite():
    fx = _fixture()
    rows = build_purchasability_rows(_db_with([fx]), book_source="Betfair")
    assert rows
    assert all(r["bookmaker_name"] == "Betfair" for r in rows)
    # odds_source rimane quello della riga, non "Betfair"
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["odds_source"] == "betfair_raw_match_winner"


def test_bookmaker_dict_not_stringified():
    fx = _fixture()
    rows = build_purchasability_rows(_db_with([fx]))
    for r in rows:
        assert r["bookmaker_name"] == "Betfair"
        assert "{" not in str(r["bookmaker_name"])


# --- Core ---


def test_book_only_not_core():
    rows_panel = [
        _panel_row(SEL_HOME, 2.2, None),
        _panel_row(SEL_DRAW, 3.4, 3.2),
        _panel_row(SEL_AWAY, 3.5, 3.8),
    ]
    fx = _fixture(panel_rows=rows_panel)
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["is_core"] is False
    assert home["model_probability"] is None


def test_missing_model_probability_not_core():
    r = _panel_row(SEL_HOME, 2.2, 2.0)
    r["prob_cecchino"] = None
    r["vantaggio_prob"] = None
    r["edge_pct"] = None
    r["score_acquisto"] = None
    r["rating"] = None
    fx = _fixture(panel_rows=[r, _panel_row(SEL_DRAW, 3.4, 3.2), _panel_row(SEL_AWAY, 3.5, 3.8)])
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(x for x in rows if x["selection"] == SEL_HOME)
    assert home["is_core"] is False


def test_low_rating_complete_enters_core():
    # force low rating via high book / low cecchino edge negative-ish
    low = _panel_row(SEL_HOME, 1.15, 2.5)
    assert (low.get("rating") or 0) < 50
    fx = _fixture(
        panel_rows=[
            low,
            _panel_row(SEL_DRAW, 3.4, 3.2),
            _panel_row(SEL_AWAY, 3.5, 3.8),
        ]
    )
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["rating"] is not None and home["rating"] < 50
    assert home["is_core"] is True


def test_negative_edge_complete_enters_core():
    # book < cecchino → edge negativo
    neg = _panel_row(SEL_HOME, 1.8, 2.2)
    assert (neg.get("edge_pct") or 0) < 0
    fx = _fixture(
        panel_rows=[
            neg,
            _panel_row(SEL_DRAW, 3.4, 3.2),
            _panel_row(SEL_AWAY, 3.5, 3.8),
        ]
    )
    rows = build_purchasability_rows(_db_with([fx]))
    home = next(r for r in rows if r["selection"] == SEL_HOME)
    assert home["edge"] < 0
    assert home["is_core"] is True


# --- Normalization ---


def test_double_chance_not_normalized():
    assert (FAMILY_DOUBLE_CHANCE, "FT", None) not in MARKET_COMPLETE_SETS
    assert normalization_status_for_family(FAMILY_DOUBLE_CHANCE) == NORM_NOT_APPLICABLE_OVERLAPPING
    fx = _fixture()
    rows = build_purchasability_rows(_db_with([fx]))
    dc = [r for r in rows if r["selection"] in (SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO)]
    assert dc
    assert all(
        r["book_probability_normalization_status"] == NORM_NOT_APPLICABLE_OVERLAPPING for r in dc
    )
    assert all(r["normalized_book_probability"] is None for r in dc)
    # DC can still be core
    assert any(r["is_core"] for r in dc)


def test_1x2_normalized():
    odds = {SEL_HOME: 2.0, SEL_DRAW: 3.5, SEL_AWAY: 4.0}
    req = MARKET_COMPLETE_SETS[("match_winner", "FT", None)]
    norm, overround, status = _normalize_book_probs(odds, req)
    assert status == "ok"
    assert overround is not None and overround > 0
    assert norm is not None and abs(sum(norm.values()) - 1.0) < 1e-9


def test_ou_same_line_normalized():
    odds = {SEL_OVER_2_5: 1.9, SEL_UNDER_2_5: 2.0}
    req = MARKET_COMPLETE_SETS[("over_under", "FT", 2.5)]
    norm, overround, status = _normalize_book_probs(odds, req)
    assert status == "ok"
    assert norm is not None


# --- Redundancy ---


def test_negative_correlation_detected():
    rows = []
    for i in range(20):
        rows.append({"odds": float(i + 1), "model_probability": float(20 - i), "raw_book_implied_probability": 1.0 / (i + 2),
                     "probability_advantage": 0.01 * i, "edge": float(i), "score": 0.1 * i, "rating": 40 + i})
    red = _input_redundancy(rows)
    high = red["high_correlation_pairs"]
    assert any(
        (p.get("pearson") is not None and abs(p["pearson"]) >= 0.9)
        or (p.get("spearman") is not None and abs(p["spearman"]) >= 0.9)
        for p in high
    )


def test_spearman_midrank_ties():
    xs = [1.0, 2.0, 2.0, 3.0]
    ranks = _midranks(xs)
    assert ranks[1] == ranks[2] == 2.5
    ys = [3.0, 2.0, 2.0, 1.0]
    s = _spearman(xs, ys)
    assert s is not None


def test_exact_duplicates_detected():
    row = {
        "odds": 2.0,
        "model_probability": 0.5,
        "raw_book_implied_probability": 0.5,
        "probability_advantage": 0.1,
        "edge": 5.0,
        "score": 0.025,
        "rating": 50,
    }
    red = _input_redundancy([row, dict(row), dict(row)])
    assert red["exact_duplicates_detected"] is True
    assert red["exact_duplicate_count"] >= 1


def test_missing_overlap_computed():
    rows = [
        {"odds": 2.0, "model_probability": None, "raw_book_implied_probability": 0.5,
         "probability_advantage": None, "edge": 1.0, "score": None, "rating": 40},
        {"odds": None, "model_probability": 0.4, "raw_book_implied_probability": None,
         "probability_advantage": 0.1, "edge": None, "score": 0.1, "rating": None},
    ]
    red = _input_redundancy(rows)
    assert red["missing_overlap"]
    assert any(m["a_missing"] >= 0 for m in red["missing_overlap"])


# --- Readiness / dataset ---


def test_readiness_not_phase2_without_settled():
    fx = _fixture(ft=None, ht=None)
    audit = build_purchasability_audit(_db_with([fx]))
    assert "no_settled_core_rows" in audit["phase_2_readiness"]["blocking_issues"]
    assert audit["phase_2_readiness"]["recommended_next_step"] == "resolve_data_gaps"


def test_no_target_in_features():
    for t in TARGET_KEYS:
        assert t not in FEATURE_CANDIDATE_KEYS


def test_dataset_batch_pagination_stable():
    fixtures = [_fixture(fid=i) for i in range(1, 6)]
    db = _db_with(fixtures)
    p1 = build_purchasability_dataset(db, status="core", limit=3, offset=0)
    p2 = build_purchasability_dataset(db, status="core", limit=3, offset=3)
    assert p1["total"] == p2["total"]
    assert len(p1["items"]) == 3
    keys1 = {r["canonical_row_key"] for r in p1["items"]}
    keys2 = {r["canonical_row_key"] for r in p2["items"]}
    assert keys1.isdisjoint(keys2)
    assert p1["version"] == DATASET_VERSION


def test_selection_alias_over_25():
    assert resolve_selection_key({"segno": "Over 2.5"}) == SEL_OVER_2_5
    assert resolve_selection_key({"label": "1"}) == SEL_HOME


def test_panel_rows_accepts_dict_normalize():
    fx = _fixture()
    rows = build_purchasability_rows(_db_with([fx]))
    assert len(rows) >= 8


def test_no_db_writes():
    db = _db_with([_fixture()])
    build_purchasability_audit(db)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_versions_v1_1():
    assert AUDIT_VERSION == "cecchino_purchasability_audit_v1_1"
    assert DATASET_VERSION == "cecchino_purchasability_dataset_v1_1"


def test_opposition_home():
    o = get_opposition(SEL_HOME)
    assert o["opposition_status"] == OPPOSITION_SUPPORTED
    assert o["comparator_selections"] == [SEL_AWAY]


# --- Regression ---


def test_rating_formula_unchanged():
    assert _compute_rating(0.5, 0.05, 10.0) == 45


def test_kpi_min_rating_unchanged():
    assert kpi_mod.MIN_KPI_RATING == 50


def test_no_betting_in_audit():
    audit = build_purchasability_audit(_db_with([_fixture()]))
    assert audit["no_purchasability_formula"] is True
    assert "value_bet" not in str(audit).lower()


# --- Hotfix JSON-safe VIF ---


def test_vif_perfect_multicollinearity_null():
    from app.services.cecchino.cecchino_purchasability_audit import _vif_status

    # raw_book_implied = 1/odds → collinearità deterministica con odds (e clone)
    rows = []
    for i in range(30):
        odds = 1.5 + i * 0.05
        rows.append(
            {
                "odds": odds,
                "model_probability": 0.3 + i * 0.01,
                "raw_book_implied_probability": 1.0 / odds,
                "probability_advantage": 0.02 * i,
                "edge": float(i),
                "score": 0.01 * i,
                "rating": 40 + i,
            }
        )
    keys = [
        "odds",
        "model_probability",
        "raw_book_implied_probability",
        "probability_advantage",
        "edge",
        "score",
        "rating",
    ]
    out = _vif_status(rows, keys)
    assert out["status"] == "perfect_multicollinearity_detected"
    assert out["infinite_variables"]
    for name in out["infinite_variables"]:
        assert out["vif"][name] is None
    for v in out["vif"].values():
        if v is not None:
            assert math.isfinite(v)


def test_audit_payload_strict_json_no_nonfinite():
    import json
    import math as math_mod

    from fastapi.encoders import jsonable_encoder

    from app.services.cecchino.cecchino_purchasability_audit import make_json_safe

    audit = build_purchasability_audit(_db_with([_fixture()]))
    encoded = jsonable_encoder(audit)
    dumped = json.dumps(encoded, allow_nan=False)

    def _walk(obj):
        if isinstance(obj, float):
            assert math_mod.isfinite(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(json.loads(dumped))
    # sanitizer nest
    dirty = {"a": float("inf"), "b": [float("nan"), {"c": float("-inf")}], "d": (1.0, float("inf"))}
    clean = make_json_safe(dirty)
    assert clean["a"] is None
    assert clean["b"][0] is None
    assert clean["b"][1]["c"] is None
    assert clean["d"][0] == 1.0
    assert clean["d"][1] is None
    try:
        import numpy as np

        assert make_json_safe(np.float64(float("inf"))) is None
        assert make_json_safe(np.float64(1.5)) == 1.5
    except ImportError:
        pass


def test_vif_finite_values_remain_numeric():
    from app.services.cecchino.cecchino_purchasability_audit import _vif_status

    rows = []
    for i in range(30):
        rows.append(
            {
                "odds": 1.5 + i * 0.1,
                "model_probability": 0.2 + (i % 7) * 0.03,
                "raw_book_implied_probability": 0.4 + (i % 5) * 0.02,
                "probability_advantage": -0.1 + i * 0.01,
                "edge": -5.0 + i * 0.5,
                "score": 0.001 * (i + 1),
                "rating": 30 + (i % 11),
            }
        )
    keys = list(rows[0].keys())
    out = _vif_status(rows, keys)
    if out["status"] == "ok":
        assert out["infinite_variables"] == []
        assert all(isinstance(v, float) and math.isfinite(v) for v in out["vif"].values())
