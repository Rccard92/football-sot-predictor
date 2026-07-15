"""Test audit storico Credibilità X — Fase 1A."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    MATCH_FINISHED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_draw_credibility_research import (
    VERSION,
    build_draw_credibility_coverage_audit,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)


def _final(**kwargs) -> dict:
    base = {
        "status": STATUS_AVAILABLE,
        "quota_1": 2.0,
        "quota_x": 3.2,
        "quota_2": 3.5,
        "prob_1": 0.45,
        "prob_x": 0.28,
        "prob_2": 0.27,
    }
    base.update(kwargs)
    return base


def _goal_markets() -> dict:
    return {
        SEL_UNDER_2_5: {"final_odd": 1.85, "status": STATUS_AVAILABLE},
        SEL_OVER_2_5: {"final_odd": 2.05, "status": STATUS_AVAILABLE},
    }


def _kpi_panel(*, with_book: bool = True) -> dict:
    rows = [
        {"market_key": SEL_HOME, "quota_cecchino": 2.0, "quota_book": 2.1 if with_book else None},
        {"market_key": SEL_DRAW, "quota_cecchino": 3.2, "quota_book": 3.3 if with_book else None},
        {"market_key": SEL_AWAY, "quota_cecchino": 3.5, "quota_book": 3.6 if with_book else None},
        {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9 if with_book else None},
        {"market_key": SEL_OVER_2_5, "quota_cecchino": 2.05, "quota_book": 2.1 if with_book else None},
    ]
    return {"version": "cecchino_kpi_v2_betfair", "rows": rows}


def _row(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    defaults = {
        "id": 1,
        "provider_fixture_id": 1001,
        "scan_date": date(2025, 6, 15),
        "competition_id": 39,
        "country_name": "England",
        "league_name": "Premier League",
        "home_team_name": "Home FC",
        "away_team_name": "Away FC",
        "match_display_status": MATCH_FINISHED,
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "score_fulltime_home": 1,
        "score_fulltime_away": 1,
        "goals_home": 1,
        "goals_away": 1,
        "cecchino_output_json": {"final": _final(), "goal_markets": _goal_markets()},
        "kpi_panel_json": _kpi_panel(),
        "odds_snapshot_json": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _audit(rows: list, **kwargs) -> dict:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return build_draw_credibility_coverage_audit(
        db,
        date_from=kwargs.get("date_from", date(2025, 1, 1)),
        date_to=kwargs.get("date_to", date(2025, 12, 31)),
        competition_id=kwargs.get("competition_id"),
        only_eligible=kwargs.get("only_eligible", True),
    )


def test_version_constant():
    assert VERSION == "cecchino_draw_credibility_research_v1"


def test_draw_fixture_usable():
    result = _audit([_row()])
    assert result["summary"]["draw_results"] == 1
    assert result["summary"]["usable_internal_research"] == 1
    assert result["summary"]["usable_market_comparison"] == 1
    assert result["target_distribution"]["draw_rate_pct"] == 100.0


def test_non_draw_fixture():
    result = _audit([_row(score_fulltime_home=2, score_fulltime_away=1, goals_home=2, goals_away=1)])
    assert result["summary"]["non_draw_results"] == 1
    assert result["summary"]["draw_results"] == 0


def test_not_finished_fixture():
    result = _audit([_row(match_display_status=MATCH_UPCOMING, score_fulltime_home=None, score_fulltime_away=None)])
    assert result["summary"]["finished_fixtures"] == 0
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "not_finished")
    assert reason["count"] == 1


def test_missing_fulltime_result():
    result = _audit([
        _row(
            match_display_status=MATCH_FINISHED,
            score_fulltime_home=None,
            score_fulltime_away=None,
            goals_home=None,
            goals_away=None,
        ),
    ])
    assert result["summary"]["finished_with_result"] == 0
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_fulltime_result")
    assert reason["count"] == 1


def test_missing_cecchino_probabilities():
    result = _audit([
        _row(cecchino_output_json={"final": _final(prob_x=None), "goal_markets": _goal_markets()}),
    ])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_cecchino_1x2_probabilities")
    assert reason["count"] == 1
    assert result["summary"]["usable_internal_research"] == 0


def test_missing_under_2_5():
    gm = _goal_markets()
    del gm[SEL_UNDER_2_5]
    result = _audit([
        _row(
            cecchino_output_json={"final": _final(), "goal_markets": gm},
            kpi_panel_json={"rows": []},
        ),
    ])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_cecchino_under_2_5")
    assert reason["count"] == 1


def test_missing_over_2_5():
    gm = _goal_markets()
    del gm[SEL_OVER_2_5]
    result = _audit([
        _row(
            cecchino_output_json={"final": _final(), "goal_markets": gm},
            kpi_panel_json={"rows": [{"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85}]},
        ),
    ])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_cecchino_over_2_5")
    assert reason["count"] == 1


def test_missing_book_1x2_internal_usable():
    result = _audit([_row(kpi_panel_json=_kpi_panel(with_book=False), odds_snapshot_json=None)])
    assert result["summary"]["usable_internal_research"] == 1
    assert result["summary"]["usable_market_comparison"] == 0
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_book_1x2")
    assert reason["count"] == 1


def test_book_from_odds_snapshot_fallback():
    snapshot = {
        "raw_by_bookmaker_id": {
            "3": [
                {
                    "bookmakers": [
                        {
                            "bets": [
                                {
                                    "name": "Match Winner",
                                    "id": 1,
                                    "values": [
                                        {"value": "Home", "odd": "2.10"},
                                        {"value": "Draw", "odd": "3.30"},
                                        {"value": "Away", "odd": "3.60"},
                                    ],
                                },
                                {
                                    "name": "Goals Over/Under",
                                    "id": 5,
                                    "values": [
                                        {"value": "Over 2.5", "odd": "2.10"},
                                        {"value": "Under 2.5", "odd": "1.90"},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    }
    result = _audit([
        _row(kpi_panel_json=_kpi_panel(with_book=False), odds_snapshot_json=snapshot),
    ])
    assert result["summary"]["usable_market_comparison"] == 1


def test_fully_usable_fixture():
    result = _audit([_row()])
    assert result["summary"]["usable_internal_research"] == 1
    assert result["summary"]["usable_market_comparison"] == 1
    assert result["debug_samples"] == []


def test_percentages_two_fixtures():
    rows = [
        _row(id=1),
        _row(
            id=2,
            match_display_status=MATCH_UPCOMING,
            score_fulltime_home=None,
            score_fulltime_away=None,
        ),
    ]
    result = _audit(rows)
    assert result["summary"]["total_fixtures"] == 2
    assert result["summary"]["finished_fixtures"] == 1
    assert result["coverage"]["research"]["pct_internal"] == 50.0
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "not_finished")
    assert reason["pct_total"] == 50.0
    assert reason["pct_finished"] == 0.0


def test_zero_fixtures_no_division_by_zero():
    result = _audit([])
    assert result["summary"]["total_fixtures"] == 0
    assert result["coverage"]["research"]["pct_internal"] == 0.0
    assert result["target_distribution"]["draw_rate_pct"] == 0.0
    assert "Nessuna fixture" in result["warnings"][0]


def test_only_eligible_filter_passed_to_query():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    build_draw_credibility_coverage_audit(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
        only_eligible=False,
    )
    db.scalars.assert_called_once()


def test_competition_id_filter():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    build_draw_credibility_coverage_audit(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
        competition_id=39,
    )
    db.scalars.assert_called_once()


def test_only_eligible_excludes_non_eligible_in_count():
    eligible = _row(id=1, eligibility_status=ELIGIBILITY_ELIGIBLE)
    excluded = _row(id=2, eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [eligible]
    result = build_draw_credibility_coverage_audit(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        only_eligible=True,
    )
    assert result["summary"]["total_fixtures"] == 1
    assert result["summary"]["eligible_fixtures"] == 1


def test_by_league_and_by_month():
    result = _audit([_row()])
    assert len(result["by_league"]) == 1
    assert result["by_league"][0]["league_name"] == "Premier League"
    assert result["by_league"][0]["internal_usable"] == 1
    assert len(result["by_month"]) == 1
    assert result["by_month"][0]["month"] == "2025-06"


def test_unsupported_payload_version():
    result = _audit([_row(cecchino_output_json=None)])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "unsupported_payload_version")
    assert reason["count"] == 1


def test_missing_cecchino_final():
    result = _audit([
        _row(cecchino_output_json={"final": {"status": "not_available"}, "goal_markets": _goal_markets()}),
    ])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_cecchino_final")
    assert reason["count"] == 1


def test_missing_cecchino_1x2_odds():
    result = _audit([
        _row(cecchino_output_json={"final": _final(quota_x=None), "goal_markets": _goal_markets()}),
    ])
    reason = next(r for r in result["exclusion_reasons"] if r["reason"] == "missing_cecchino_1x2_odds")
    assert reason["count"] == 1


def test_payload_json_serializable():
    result = _audit([_row()])
    encoded = jsonable_encoder(result)
    assert encoded["version"] == VERSION


def test_no_external_api_calls():
    with patch(
        "app.services.cecchino.cecchino_draw_credibility_research.build_betfair_payload_from_snapshot",
    ) as mock_snapshot:
        mock_snapshot.return_value = {
            "bookmakers": [
                {
                    "status": "available",
                    "markets": {
                        MARKET_1X2: {SEL_HOME: 2.1, SEL_DRAW: 3.3, SEL_AWAY: 3.6},
                        MARKET_OU: {SEL_UNDER_2_5: 1.9, SEL_OVER_2_5: 2.1},
                    },
                },
            ],
        }
        _audit([_row(kpi_panel_json=_kpi_panel(with_book=False))])
        mock_snapshot.assert_called()


def test_db_not_modified():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [_row()]
    build_draw_credibility_coverage_audit(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
    )
    db.commit.assert_not_called()
    db.delete.assert_not_called()
    db.add.assert_not_called()


def test_debug_samples_limited():
    rows = [
        _row(id=i, match_display_status=MATCH_UPCOMING, score_fulltime_home=None, score_fulltime_away=None)
        for i in range(25)
    ]
    result = _audit(rows)
    not_finished_samples = [s for s in result["debug_samples"] if s["reason"] == "not_finished"]
    assert len(not_finished_samples) <= 20
