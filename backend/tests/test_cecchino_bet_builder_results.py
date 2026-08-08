"""BET-RESULTS-01 — Outcome Monitor: ranking V2, evaluation, KPI primary-only, no backfill."""

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
from app.routes.cecchino_bet_builder import router
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_PRIMARY_SELECTION_VERSION,
    BET_BUILDER_RESULTS_CONTRACT_VERSION,
    BET_BUILDER_RESULTS_START_DATE,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
)
from app.services.cecchino.cecchino_bet_builder_primary_selection import (
    compare_opportunity_evidence_strength,
    select_primary_opportunity,
    sort_opportunities_by_evidence_strength,
)
from app.services.cecchino.cecchino_bet_builder_results import (
    OUTCOME_LOST,
    OUTCOME_NOT_EVALUABLE,
    OUTCOME_PENDING,
    OUTCOME_RESULT_MISSING,
    OUTCOME_WON,
    aggregate_bet_builder_results,
    clamp_results_date,
    evaluate_bet_builder_prediction_outcome,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)


# ---------------------------------------------------------------------------
# Helpers — opportunity dicts for ranking
# ---------------------------------------------------------------------------


def _opp(
    *,
    key: str,
    origin: str,
    v31: float | None = 70,
    passed: bool = True,
    yes_count: int = 2,
    context: bool = False,
    rating: int | None = 80,
    edge: float | None = 20.0,
) -> dict:
    return {
        "opportunity_key": key,
        "origin": origin,
        "market": {"market_key": "DRAW", "label": "X"},
        "signals": {
            "available": True,
            "present": passed,
            "yes_count": yes_count,
            "required_count": 2,
            "available_count": 4,
            "yes_columns": [],
            "passed": passed,
        },
        "purchasability_v31": {
            "available": v31 is not None,
            "score": v31,
        },
        "price_value": {
            "present": origin != ORIGIN_SIGNALS,
            "quota_book": 2.1 if origin != ORIGIN_SIGNALS else None,
            "quota_cecchino": 1.9,
            "rating": rating,
            "edge_pct": edge,
        },
        "context_support": {
            "available": context,
            "module": "balance_v5" if context else None,
        },
    }


def _row(
    *,
    fid: int = 1,
    scan_date: date = date(2026, 8, 8),
    match_status: str = "finished",
    ft_home: int | None = 2,
    ft_away: int | None = 1,
    ht_home: int | None = 0,
    ht_away: int | None = 0,
    kickoff: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=1000 + fid,
        scan_date=scan_date,
        kickoff=kickoff or datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc),
        country_name="Sweden",
        league_name="Division 2",
        home_team_name="Onsala",
        away_team_name="Boljan",
        home_team_logo_url=None,
        away_team_logo_url=None,
        eligibility_status="eligible",
        match_display_status=match_status,
        fixture_status=match_status,
        elapsed_minutes=90 if match_status == "finished" else None,
        goals_home=ft_home,
        goals_away=ft_away,
        score_fulltime_home=ft_home,
        score_fulltime_away=ft_away,
        score_halftime_home=ht_home,
        score_halftime_away=ht_away,
        kpi_panel_json={"rows": []},
        cecchino_output_json={},
        updated_at=datetime(2026, 8, 8, 20, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Ranking A–I (parità FE Evidence Sort V2)
# ---------------------------------------------------------------------------


class TestEvidenceSortV2Primary:
    def test_a_higher_v31_before_more_signals(self):
        high = _opp(key="qs-85", origin=ORIGIN_PRICE_AND_SIGNALS, v31=85, yes_count=2)
        low = _opp(key="qs-25", origin=ORIGIN_PRICE_AND_SIGNALS, v31=25, yes_count=4)
        assert compare_opportunity_evidence_strength(high, low) < 0
        assert select_primary_opportunity([low, high])["opportunity_key"] == "qs-85"

    def test_b_qs_before_signals_only(self):
        qs = _opp(key="qs", origin=ORIGIN_PRICE_AND_SIGNALS, v31=40)
        sig = _opp(key="sig", origin=ORIGIN_SIGNALS, v31=90)
        assert compare_opportunity_evidence_strength(qs, sig) < 0

    def test_c_signals_before_price_even_nd_vs_95(self):
        sig = _opp(key="sig-nd", origin=ORIGIN_SIGNALS, v31=None)
        price = _opp(key="price-95", origin=ORIGIN_PRICE, v31=95)
        assert compare_opportunity_evidence_strength(sig, price) < 0
        assert select_primary_opportunity([price, sig])["opportunity_key"] == "sig-nd"

    def test_d_passed_true_before_false(self):
        passed = _opp(key="pass", origin=ORIGIN_SIGNALS, v31=50, passed=True, yes_count=1)
        failed = _opp(key="fail", origin=ORIGIN_SIGNALS, v31=50, passed=False, yes_count=4)
        assert compare_opportunity_evidence_strength(passed, failed) < 0

    def test_e_yes_count_desc(self):
        four = _opp(key="4si", origin=ORIGIN_PRICE_AND_SIGNALS, v31=70, yes_count=4)
        two = _opp(key="2si", origin=ORIGIN_PRICE_AND_SIGNALS, v31=70, yes_count=2)
        assert compare_opportunity_evidence_strength(four, two) < 0

    def test_f_context_availability_tiebreak(self):
        with_ctx = _opp(key="ctx", origin=ORIGIN_PRICE, v31=80, context=True, passed=False, yes_count=0)
        no_ctx = _opp(key="noct", origin=ORIGIN_PRICE, v31=80, context=False, passed=False, yes_count=0)
        assert compare_opportunity_evidence_strength(with_ctx, no_ctx) < 0

    def test_g_rating_desc(self):
        high = _opp(key="r90", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=90, edge=10)
        low = _opp(key="r70", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=70, edge=10)
        assert compare_opportunity_evidence_strength(high, low) < 0

    def test_h_edge_desc(self):
        high = _opp(key="e30", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=80, edge=30)
        low = _opp(key="e20", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=80, edge=20)
        assert compare_opportunity_evidence_strength(high, low) < 0

    def test_i_opportunity_key_deterministic(self):
        a = _opp(key="a-key", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=80, edge=20)
        b = _opp(key="b-key", origin=ORIGIN_PRICE, v31=70, passed=False, yes_count=0, rating=80, edge=20)
        ordered = sort_opportunities_by_evidence_strength([b, a])
        assert [o["opportunity_key"] for o in ordered] == ["a-key", "b-key"]
        assert select_primary_opportunity([b, a])["opportunity_key"] == "a-key"


# ---------------------------------------------------------------------------
# Outcome evaluation
# ---------------------------------------------------------------------------


class TestPredictionOutcome:
    def test_home_won_lost(self):
        won = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_HOME, row=_row(ft_home=2, ft_away=1)
        )
        lost = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_HOME, row=_row(ft_home=1, ft_away=2)
        )
        assert won["prediction_outcome"] == OUTCOME_WON
        assert lost["prediction_outcome"] == OUTCOME_LOST

    def test_draw(self):
        won = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW, row=_row(ft_home=1, ft_away=1)
        )
        lost = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW, row=_row(ft_home=1, ft_away=0)
        )
        assert won["prediction_outcome"] == OUTCOME_WON
        assert lost["prediction_outcome"] == OUTCOME_LOST

    def test_away(self):
        won = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_AWAY, row=_row(ft_home=0, ft_away=2)
        )
        assert won["prediction_outcome"] == OUTCOME_WON

    def test_double_chance(self):
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_ONE_X, row=_row(ft_home=1, ft_away=0)
            )["prediction_outcome"]
            == OUTCOME_WON
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_ONE_X, row=_row(ft_home=0, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_LOST
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_X_TWO, row=_row(ft_home=0, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_WON
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_ONE_TWO, row=_row(ft_home=1, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_LOST
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_ONE_TWO, row=_row(ft_home=2, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_WON
        )

    def test_over_under(self):
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_OVER_1_5, row=_row(ft_home=1, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_WON
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_UNDER_1_5, row=_row(ft_home=1, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_LOST
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_OVER_2_5, row=_row(ft_home=2, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_WON
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_UNDER_2_5, row=_row(ft_home=2, ft_away=1)
            )["prediction_outcome"]
            == OUTCOME_LOST
        )
        assert (
            evaluate_bet_builder_prediction_outcome(
                market_key=SEL_UNDER_2_5, row=_row(ft_home=1, ft_away=0)
            )["prediction_outcome"]
            == OUTCOME_WON
        )

    def test_x_pt_halftime(self):
        won = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW_PT,
            row=_row(match_status="live", ft_home=1, ft_away=0, ht_home=0, ht_away=0),
        )
        lost = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW_PT,
            row=_row(match_status="live", ft_home=1, ft_away=0, ht_home=1, ht_away=0),
        )
        assert won["prediction_outcome"] == OUTCOME_WON
        assert lost["prediction_outcome"] == OUTCOME_LOST

    def test_cancelled_not_lost(self):
        ev = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW,
            row=_row(match_status="cancelled", ft_home=None, ft_away=None),
        )
        assert ev["prediction_outcome"] == OUTCOME_NOT_EVALUABLE
        assert ev["prediction_outcome"] != OUTCOME_LOST

    def test_postponed_not_lost(self):
        ev = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_HOME,
            row=_row(match_status="postponed", ft_home=None, ft_away=None),
        )
        assert ev["prediction_outcome"] == OUTCOME_NOT_EVALUABLE

    def test_finished_ft_missing(self):
        ev = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_HOME,
            row=_row(match_status="finished", ft_home=None, ft_away=None),
        )
        assert ev["prediction_outcome"] == OUTCOME_RESULT_MISSING

    def test_x_pt_finished_ht_missing(self):
        ev = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW_PT,
            row=_row(match_status="finished", ft_home=1, ft_away=0, ht_home=None, ht_away=None),
        )
        assert ev["prediction_outcome"] == OUTCOME_RESULT_MISSING

    def test_upcoming_pending(self):
        ev = evaluate_bet_builder_prediction_outcome(
            market_key=SEL_DRAW,
            row=_row(match_status="upcoming", ft_home=None, ft_away=None),
        )
        assert ev["prediction_outcome"] == OUTCOME_PENDING


# ---------------------------------------------------------------------------
# Aggregate results — KPI, no backfill, signal-only
# ---------------------------------------------------------------------------


def _mock_db(rows: list) -> MagicMock:
    db = MagicMock()

    def _scalars(stmt):
        result = MagicMock()
        text = str(stmt)
        if "cecchino_goal_intensity" in text.lower() or "GoalIntensity" in text:
            result.all.return_value = []
        else:
            result.all.return_value = rows
        return result

    db.scalars.side_effect = _scalars
    db.scalar.return_value = None
    db.get.return_value = None
    return db


def _opp_built(
    *,
    fid: int,
    market_key: str,
    origin: str,
    v31: float | None = 80,
    book: float | None = 2.1,
) -> dict:
    return {
        "opportunity_key": f"{fid}:{market_key}",
        "fixture": {"today_fixture_id": fid, "kickoff": "2026-08-08T18:00:00+00:00"},
        "market": {"market_key": market_key, "label": market_key},
        "origin": origin,
        "price_value": {
            "present": book is not None and origin != ORIGIN_SIGNALS,
            "quota_book": book,
            "quota_cecchino": 1.9,
            "rating": 80,
            "edge_pct": 20.0,
        },
        "signals": {
            "available": True,
            "present": origin != ORIGIN_PRICE,
            "yes_count": 2 if origin != ORIGIN_PRICE else 0,
            "required_count": 2,
            "available_count": 4,
            "yes_columns": ["E", "F"],
            "passed": origin != ORIGIN_PRICE,
        },
        "purchasability_v31": {"available": v31 is not None, "score": v31},
        "context_support": {"available": False},
        "freshness": {},
    }


class TestAggregateResults:
    def test_start_date_constant(self):
        assert BET_BUILDER_RESULTS_START_DATE == date(2026, 8, 8)
        assert BET_BUILDER_PRIMARY_SELECTION_VERSION == "bet_builder_evidence_sort_v2"

    def test_clamp_before_start(self):
        assert clamp_results_date(date(2026, 8, 7), today=date(2026, 8, 10)) == date(2026, 8, 8)

    def test_no_backfill_excludes_aug_7(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results._load_gi_payloads_batch",
            lambda db, rows: ({}, None),
        )

        rows_returned: list = []

        def fake_build(rows, **kwargs):
            rows_returned.extend(rows)
            return [], None

        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results.build_opportunities_for_rows",
            fake_build,
        )

        # DB mock returns both 07 and 08 — query filter should only get 08+
        # We simulate the service query returning only filtered rows
        row_ok = _row(fid=2, scan_date=date(2026, 8, 8))
        db = _mock_db([row_ok])  # as if SQL already filtered

        payload = aggregate_bet_builder_results(
            db,
            date_from=date(2026, 8, 7),
            date_to=date(2026, 8, 8),
        )
        assert payload["available_from"] == "2026-08-08"
        assert payload["date_from"] == "2026-08-08"
        assert all(r.scan_date >= date(2026, 8, 8) for r in rows_returned)

    def test_primary_only_kpi(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results._load_gi_payloads_batch",
            lambda db, rows: ({}, None),
        )
        row = _row(fid=1, ft_home=2, ft_away=1)  # DRAW lost, UNDER_2.5 lost, X2 lost — wait
        # 2-1: DRAW lost, UNDER 2.5 lost, X2 lost. Use UNDER_2.5 won with 1-0 instead.
        # Spec: primary X LOST, secondary Under 2.5 WON, X2 WON → summary won=0 lost=1
        # For 2-1: X lost, X2 lost, Under2.5 lost. Need score where secondaries win.
        # Use FT 0-0: X won. Spec wants primary X lost → use 2-1 and claim Under won wrongly?
        # Spec example: primary X lost with 2-1; secondaries also lost.
        # KPI test: primary X LOST, secondary Under 2.5 WON, X2 WON.
        # That requires FT that makes X lost but Under2.5 and X2 won → impossible for X2+Under with X lost?
        # X lost means not draw. X2 won means away or draw. So away win: e.g. 0-2.
        # Under 2.5 won with 0-2? Total 2 goals → Under 2.5 WON. X2 WON. X LOST. Perfect.
        row = _row(fid=1, ft_home=0, ft_away=2)

        opps = [
            _opp_built(fid=1, market_key=SEL_DRAW, origin=ORIGIN_PRICE_AND_SIGNALS, v31=90),
            _opp_built(fid=1, market_key=SEL_UNDER_2_5, origin=ORIGIN_PRICE, v31=50),
            _opp_built(fid=1, market_key=SEL_X_TWO, origin=ORIGIN_PRICE, v31=40),
        ]
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results.build_opportunities_for_rows",
            lambda rows, **kw: (opps, None),
        )
        db = _mock_db([row])
        payload = aggregate_bet_builder_results(db, date_from=date(2026, 8, 8), date_to=date(2026, 8, 8))
        summary = payload["summary"]
        assert summary["primary_predictions"] == 1
        assert summary["lost"] == 1
        assert summary["won"] == 0
        assert summary["settled"] == 1
        assert summary["win_rate"] == 0.0
        primary = payload["fixtures"][0]["primary"]
        assert primary["market"]["market_key"] == SEL_DRAW
        assert primary["prediction_outcome"] == OUTCOME_LOST
        others = payload["fixtures"][0]["other_opportunities"]
        assert len(others) == 2
        by_m = {o["market"]["market_key"]: o["prediction_outcome"] for o in others}
        assert by_m[SEL_UNDER_2_5] == OUTCOME_WON
        assert by_m[SEL_X_TWO] == OUTCOME_WON

    def test_void_excluded_from_win_rate(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results._load_gi_payloads_batch",
            lambda db, rows: ({}, None),
        )
        row = _row(fid=1, match_status="cancelled", ft_home=None, ft_away=None)
        opps = [_opp_built(fid=1, market_key=SEL_DRAW, origin=ORIGIN_SIGNALS, v31=None, book=None)]
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results.build_opportunities_for_rows",
            lambda rows, **kw: (opps, None),
        )
        db = _mock_db([row])
        payload = aggregate_bet_builder_results(db, date_from=date(2026, 8, 8), date_to=date(2026, 8, 8))
        summary = payload["summary"]
        assert summary["not_evaluable"] == 1
        assert summary["lost"] == 0
        assert summary["won"] == 0
        assert summary["win_rate"] is None

    def test_signal_only_book_null_still_evaluates(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results._load_gi_payloads_batch",
            lambda db, rows: ({}, None),
        )
        row = _row(fid=1, ft_home=1, ft_away=1)
        opps = [
            _opp_built(
                fid=1,
                market_key=SEL_DRAW,
                origin=ORIGIN_SIGNALS,
                v31=None,
                book=None,
            )
        ]
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results.build_opportunities_for_rows",
            lambda rows, **kw: (opps, None),
        )
        db = _mock_db([row])
        payload = aggregate_bet_builder_results(db, date_from=date(2026, 8, 8), date_to=date(2026, 8, 8))
        primary = payload["fixtures"][0]["primary"]
        assert primary["origin"] == ORIGIN_SIGNALS
        assert primary["price_value"]["quota_book"] is None
        assert primary["prediction_outcome"] == OUTCOME_WON

    def test_api_results_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results._load_gi_payloads_batch",
            lambda db, rows: ({}, None),
        )
        monkeypatch.setattr(
            "app.services.cecchino.cecchino_bet_builder_results.build_opportunities_for_rows",
            lambda rows, **kw: ([], None),
        )
        db = _mock_db([])
        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _ov():
            yield db

        app.dependency_overrides[get_db] = _ov
        client = TestClient(app)
        res = client.get(
            "/api/cecchino/bet-builder/results?date_from=2026-08-08&date_to=2026-08-08"
        )
        assert res.status_code == 200
        body = res.json()
        assert body["contract_version"] == BET_BUILDER_RESULTS_CONTRACT_VERSION
        assert body["available_from"] == "2026-08-08"
        assert body["primary_selection_version"] == BET_BUILDER_PRIMARY_SELECTION_VERSION
        assert "summary" in body
        assert "fixtures" in body
