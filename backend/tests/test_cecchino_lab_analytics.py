"""Test analytics Cecchino Lab — helper puri + endpoint + export."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import cecchino_lab
from app.core.database import get_db
from app.services.cecchino_data_lab.analytics_service import (
    build_metric,
    flat_roi_from_results,
    get_analytics_overview,
    margin_pct,
    movement_pct,
    normalized_implied,
    unique_favorite,
    unique_longest,
    _build_insights,
)
from app.services.cecchino_data_lab.query_service import export_data_quality_issues


# ---------------------------------------------------------------------------
# Helper puri
# ---------------------------------------------------------------------------


def test_build_metric_percentage_and_null_safe():
    m = build_metric(3, 10)
    assert m["count"] == 3
    assert m["denominator"] == 10
    assert m["percentage"] == 30.0
    empty = build_metric(0, 0)
    assert empty["percentage"] is None


def test_unique_favorite_and_tie_excluded():
    assert unique_favorite(1.5, 4.0, 7.0) == "H"
    assert unique_favorite(7.0, 4.0, 1.4) == "A"
    assert unique_favorite(3.0, 2.5, 4.0) == "D"
    assert unique_favorite(2.0, 2.0, 3.0) is None  # parità
    assert unique_favorite(None, 2.0, 3.0) is None
    assert unique_favorite(0, 2.0, 3.0) is None


def test_unique_longest():
    assert unique_longest(1.5, 4.0, 8.0) == "A"
    assert unique_longest(5.0, 5.0, 3.0) is None


def test_normalized_implied_sums_to_one():
    probs = normalized_implied(2.0, 3.5, 4.0)
    assert probs is not None
    assert abs(sum(probs.values()) - 1.0) < 1e-9
    assert probs["H"] > probs["D"] > probs["A"]
    assert normalized_implied(None, 2.0, 3.0) is None


def test_margin_and_movement():
    m = margin_pct(2.0, 3.5, 4.0)
    assert m is not None and m > 0
    assert round(movement_pct(1.8, 2.0), 2) == -10.0  # shortened
    assert round(movement_pct(2.2, 2.0), 2) == 10.0  # lengthened
    assert movement_pct(None, 2.0) is None
    assert movement_pct(2.0, None) is None


def test_flat_roi():
    # win @2.0 → +1; lose → -1; ROI = 0%
    profit, roi, n = flat_roi_from_results([1.0, -1.0])
    assert n == 2
    assert profit == 0.0
    assert roi == 0.0
    # all wins @3.0 → profit 2+2=4, ROI 200%
    profit2, roi2, n2 = flat_roi_from_results([2.0, 2.0])
    assert n2 == 2
    assert profit2 == 4.0
    assert roi2 == 200.0
    assert flat_roi_from_results([]) == (None, None, 0)


def test_calibration_gap_formula():
    # actual 60%, implied 50% → gap +10 pp
    actual = 0.60
    implied = 0.50
    gap = round((actual - implied) * 100.0, 1)
    assert gap == 10.0


def test_insights_require_min_sample():
    small = [
        {
            "competition_name": "Tiny",
            "country": "X",
            "matches": 50,
            "home_win_pct": 90.0,
            "draw_pct": 5.0,
            "away_win_pct": 5.0,
            "over_25_pct": 80.0,
            "under_25_pct": 20.0,
            "average_goals": 4.0,
            "favorite_hit_pct": 90.0,
            "average_pre_margin_pct": 2.0,
        }
    ]
    big = [
        {
            "competition_name": "Big League",
            "country": "Y",
            "matches": 200,
            "home_win_pct": 55.0,
            "draw_pct": 25.0,
            "away_win_pct": 20.0,
            "over_25_pct": 60.0,
            "under_25_pct": 40.0,
            "average_goals": 2.8,
            "favorite_hit_pct": 70.0,
            "average_pre_margin_pct": 5.0,
        }
    ]
    outs = {
        "home": {"flat_roi_pct": 1.5, "sample_size": 200},
        "draw": {"flat_roi_pct": -8.0, "sample_size": 200},
        "away": {"flat_roi_pct": -5.0, "sample_size": 200},
    }
    insights_small = _build_insights(
        league_rows=small,
        outcomes=outs,
        over_roi=2.0,
        under_roi=-3.0,
        over_n=50,
        under_n=50,
        longest={"count": 0, "percentage": None, "sample_size": 0},
        odds_movement={"average_winner_movement_pct": None, "sample_size": 0},
        margins={},
        best_roi={"label": "1 (casa)", "roi": 1.5, "sample_size": 200},
    )
    # campionato sotto soglia: nessun insight "most_*" di league; può restare best_flat_roi
    league_keys = [i["key"] for i in insights_small if i.get("competition_name") == "Tiny"]
    assert league_keys == []

    insights_big = _build_insights(
        league_rows=big,
        outcomes=outs,
        over_roi=2.0,
        under_roi=-3.0,
        over_n=200,
        under_n=200,
        longest={"count": 5, "percentage": 2.1, "sample_size": 200, "top_competition": None},
        odds_movement={"average_winner_movement_pct": -1.5, "sample_size": 180},
        margins={},
        best_roi={"label": "1 (casa)", "roi": 1.5, "sample_size": 200},
    )
    assert len(insights_big) <= 8
    assert any(i["key"] == "most_home_wins" for i in insights_big)
    assert all("Storicamente" in i["description"] or "periodo analizzato" in i["description"].lower() or "Nel periodo" in i["description"] for i in insights_big)


def _mock_chain(rows):
    chain = MagicMock()
    chain.join.return_value = chain
    chain.filter.return_value = chain
    chain.distinct.return_value = chain
    chain.group_by.return_value = chain
    chain.order_by.return_value = chain
    chain.outerjoin.return_value = chain
    chain.all.return_value = rows
    chain.count.return_value = len(rows)
    return chain


def test_get_analytics_overview_1x2_ou_btts_ht_roi_filters():
    """Dataset minimale in-memory via mock query — verifica metriche chiave."""
    # Colonne lean come in analytics_service
    # Match A: 2-1 H, odds 1.50/4.00/6.00, closing 1.40/4.20/7.00, O2.5=1.80 U=2.00, HT 1-0
    # Match B: 0-0 D, odds 2.10/3.20/3.50, no closing, no OU, HT 0-0
    # Match C: 1-3 A, odds 2.20/3.30/3.10 (=tie fav? 2.20 vs 3.10 — H is fav), O=1.90 U=1.95, HT 0-1
    # Match D: tie favorite 2.0/2.0/3.5 → esclusa da favorite; 3-1 H
    rows = [
        (
            1, date(2024, 8, 10), "HomeA", "AwayA",
            2, 1, "H", 1, 0, "H",
            1.50, 4.00, 6.00, 1.80, 2.00, 1.40, 4.20, 7.00,
            True, True, True, True, True, "complete", 1, "Premier League", "England", "2024/2025",
        ),
        (
            2, date(2024, 8, 11), "HomeB", "AwayB",
            0, 0, "D", 0, 0, "D",
            2.10, 3.20, 3.50, None, None, None, None, None,
            True, False, False, True, True, "complete", 1, "Premier League", "England", "2024/2025",
        ),
        (
            3, date(2024, 8, 12), "HomeC", "AwayC",
            1, 3, "A", 0, 1, "A",
            2.20, 3.30, 3.10, 1.90, 1.95, 2.10, 3.40, 3.20,
            True, True, True, True, True, "complete", 2, "Serie A", "Italy", "2024/2025",
        ),
        (
            4, date(2024, 8, 13), "HomeD", "AwayD",
            3, 1, "H", 1, 1, "D",
            2.00, 2.00, 3.50, 1.70, 2.10, 1.95, 2.05, 3.60,
            True, True, True, True, True, "partial", 2, "Serie A", "Italy", "2023/2024",
        ),
    ]

    db = MagicMock()
    call_n = {"i": 0}

    def query_side_effect(*args, **kwargs):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return _mock_chain(
                [
                    ("2024/2025", "England", "Premier League"),
                    ("2024/2025", "Italy", "Serie A"),
                    ("2023/2024", "Italy", "Serie A"),
                ]
            )
        if call_n["i"] == 2:
            return _mock_chain(rows)
        return _mock_chain([])

    db.query.side_effect = query_side_effect

    payload = get_analytics_overview(db)
    assert payload["is_empty"] is False
    assert payload["summary"]["matches_total"] == 4
    assert payload["summary"]["competitions_count"] == 2
    assert payload["summary"]["seasons_count"] == 2

    # 1X2: H=2, D=1, A=1
    assert payload["outcomes_1x2"]["home"]["count"] == 2
    assert payload["outcomes_1x2"]["draw"]["count"] == 1
    assert payload["outcomes_1x2"]["away"]["count"] == 1
    assert payload["outcomes_1x2"]["home"]["percentage"] == 50.0

    # Goals: over 2.5 = matches with tg>=3 → A(3), C(4), D(4) = 3; B(0)=under
    assert payload["goals"]["over_25"]["count"] == 3
    assert payload["goals"]["under_25"]["count"] == 1
    assert payload["goals"]["btts_yes"]["count"] == 3  # A,C,D
    assert payload["goals"]["score_0_0"]["count"] == 1
    assert payload["goals"]["over_15"]["count"] == 3

    # HT
    assert payload["first_half"]["sample_size"] == 4
    assert payload["first_half"]["draw"]["count"] == 2  # B 0-0, D 1-1
    assert payload["first_half"]["score_0_0"]["count"] == 1

    # Favorite: A H@1.5 win; B H@2.1 lose; C H@2.2 lose; D tie excluded → unique=3, wins=1
    assert payload["favorite"]["unique_count"] == 3
    assert payload["favorite"]["wins"] == 1
    assert payload["favorite"]["hit_rate"] == 33.3

    # ROI home: bet all 4 with home odds; wins on A (1.5-1=0.5) and D (2-1=1); loses B,C → profit 0.5+1-1-1=-0.5
    assert payload["outcomes_1x2"]["home"]["sample_size"] == 4
    assert payload["outcomes_1x2"]["home"]["flat_profit_units"] == -0.5
    assert payload["outcomes_1x2"]["home"]["flat_roi_pct"] == -12.5

    # NULL odds excluded from OU denominators: only A,C,D have OU
    assert payload["goals"]["over_25"]["sample_size"] == 3

    # Margins / movement present for A and C (and D)
    assert payload["margins"]["sample_size_pre"] >= 3
    assert payload["odds_movement"]["sample_size"] >= 2

    # Longest odds univoca: A,B,C,D tutte eleggibili
    assert payload["longest_odds_hit"]["sample_size"] == 4

    # League rows
    assert len(payload["leagues"]) == 2

    # Filter by country
    call_n["i"] = 0

    def query_italy(*args, **kwargs):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return _mock_chain([("2024/2025", "Italy", "Serie A"), ("2023/2024", "Italy", "Serie A")])
        if call_n["i"] == 2:
            return _mock_chain([r for r in rows if r[26] == "Italy"])
        return _mock_chain([])

    db.query.side_effect = query_italy
    it = get_analytics_overview(db, country="Italy")
    assert it["summary"]["matches_total"] == 2
    assert it["applied_filters"]["country"] == "Italy"

    # Filter competition
    call_n["i"] = 0

    def query_pl(*args, **kwargs):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return _mock_chain([("2024/2025", "England", "Premier League")])
        if call_n["i"] == 2:
            return _mock_chain([r for r in rows if r[25] == "Premier League"])
        return _mock_chain([])

    db.query.side_effect = query_pl
    pl = get_analytics_overview(db, competition="Premier League")
    assert pl["summary"]["matches_total"] == 2

    # Filter season
    call_n["i"] = 0

    def query_season(*args, **kwargs):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return _mock_chain([("2023/2024", "Italy", "Serie A")])
        if call_n["i"] == 2:
            return _mock_chain([r for r in rows if r[27] == "2023/2024"])
        return _mock_chain([])

    db.query.side_effect = query_season
    s = get_analytics_overview(db, season_label="2023/2024")
    assert s["summary"]["matches_total"] == 1


def test_favorite_buckets_and_null_odds_excluded_from_roi():
    # Solo partita senza quote: outcomes ROI sample 0
    rows = [
        (
            1, date(2024, 1, 1), "H", "A",
            1, 0, "H", 0, 0, "D",
            None, None, None, None, None, None, None, None,
            False, False, False, True, True, "partial", 1, "Ligue 1", "France", "2024/2025",
        ),
    ]
    db = MagicMock()
    call_n = {"i": 0}

    def q(*args, **kwargs):
        call_n["i"] += 1
        if call_n["i"] == 1:
            return _mock_chain([("2024/2025", "France", "Ligue 1")])
        if call_n["i"] == 2:
            return _mock_chain(rows)
        return _mock_chain([])

    db.query.side_effect = q
    p = get_analytics_overview(db)
    assert p["outcomes_1x2"]["home"]["count"] == 1
    assert p["outcomes_1x2"]["home"]["sample_size"] == 0
    assert p["outcomes_1x2"]["home"]["flat_roi_pct"] is None
    assert p["favorite"]["unique_count"] == 0
    assert all(b["matches"] == 0 for b in p["favorite"]["buckets"])


def test_analytics_endpoint():
    client_app = FastAPI()
    client_app.include_router(cecchino_lab.router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    client_app.dependency_overrides[get_db] = override
    client = TestClient(client_app)

    fake = {"is_empty": False, "summary": {"matches_total": 10}, "applied_filters": {}}
    with patch(
        "app.routes.cecchino_lab.get_analytics_overview",
        return_value=fake,
    ) as mocked:
        res = client.get(
            "/api/cecchino-lab/analytics/overview",
            params={"season_label": "2024/2025", "country": "Italy"},
        )
        assert res.status_code == 200
        assert res.json()["summary"]["matches_total"] == 10
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        assert kwargs["season_label"] == "2024/2025"
        assert kwargs["country"] == "Italy"


def test_export_csv_bom_delimiter_and_json_no_pagination():
    issue = SimpleNamespace(
        id=99,
        severity="warning",
        issue_code="odds_missing",
        message="Quota assente",
        field_name="bet365_home",
        raw_value=None,
        source_row_number=12,
        match_id=5,
        import_id=3,
        details_json={"note": "x"},
        created_at=datetime(2024, 8, 1, tzinfo=timezone.utc),
    )
    imp = SimpleNamespace(dataset_id=7, source_filename="E0.csv", id=3)
    ds = SimpleNamespace(
        competition_name="Premier League",
        country="England",
        season_label="2024/2025",
        division_code="E0",
    )
    match = SimpleNamespace(
        match_date=date(2024, 8, 10),
        home_team="Arsenal",
        away_team="Wolves",
    )

    db = MagicMock()
    chain = _mock_chain([(issue, imp, ds, match)])
    db.query.return_value = chain

    content, media, filename = export_data_quality_issues(db, format="csv", scope="all")
    assert content.startswith("\ufeff")
    assert ";" in content.splitlines()[0]
    assert "issue_id" in content
    assert "99" in content
    assert "note" in content
    assert filename.endswith(".csv")
    assert "text/csv" in media
    # no page/limit in export path — all rows returned once
    assert chain.all.call_count >= 1

    content_j, media_j, filename_j = export_data_quality_issues(
        db, format="json", scope="filtered", severity="warning"
    )
    payload = json.loads(content_j)
    assert payload["count"] == 1
    assert payload["items"][0]["issue_id"] == 99
    assert "raw_json" not in payload["items"][0]
    assert filename_j.endswith(".json")
    assert "application/json" in media_j
    assert payload["filters"]["scope"] == "filtered"
    assert payload["filters"]["severity"] == "warning"


def test_export_endpoint_streaming():
    client_app = FastAPI()
    client_app.include_router(cecchino_lab.router, prefix="/api")
    db = MagicMock()

    def override():
        yield db

    client_app.dependency_overrides[get_db] = override
    client = TestClient(client_app)

    with patch(
        "app.routes.cecchino_lab.export_data_quality_issues",
        return_value=('{"count":0,"items":[]}', "application/json; charset=utf-8", "cecchino_lab_quality_test.json"),
    ):
        res = client.get("/api/cecchino-lab/data-quality/issues/export?format=json&scope=all")
        assert res.status_code == 200
        assert res.headers.get("content-disposition", "").endswith('filename="cecchino_lab_quality_test.json"')
        assert res.json()["count"] == 0
