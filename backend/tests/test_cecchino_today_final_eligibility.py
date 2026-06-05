"""Test validatore finale eleggibilità Cecchino Today — Fase 11."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE,
    ELIGIBILITY_EXCLUDED_MISSING_1X2,
    ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO,
    ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_constants import (
    KEY_HOME_RECENT_CONTEXT_5,
    LEAKAGE_PASSED,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    WARNING_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino.cecchino_today_final_eligibility import (
    partition_scan_warnings,
    validate_cecchino_today_final_eligibility,
)
from app.services.cecchino.cecchino_today_service import (
    list_eligible_today,
    list_excluded_today_enriched,
    revalidate_cecchino_today_day,
)


def _pic_block(*, status: str = STATUS_AVAILABLE, warnings: list[str] | None = None) -> dict:
    return {
        "status": status,
        "warnings": warnings or [],
        "outcome_1": {"quota": 2.1},
        "outcome_x": {"quota": 3.2},
        "outcome_2": {"quota": 4.5},
    }


def _stats_snapshot(**overrides: int) -> dict:
    defaults = {
        "home_context": 3,
        "away_context": 3,
        "home_total": 6,
        "away_total": 6,
        "home_recent_context_5": 3,
        "away_recent_context_5": 3,
        "home_recent_total_6": 5,
        "away_recent_total_6": 5,
    }
    defaults.update(overrides)
    input_snapshot = {
        key: {"sample_count": n} for key, n in defaults.items()
    }
    return {"input_snapshot": input_snapshot, "leakage_status": LEAKAGE_PASSED}


def _odds_snapshot(*, missing_book: str | None = None, missing_sel: tuple[str, str] | None = None) -> dict:
    books = {
        "Bet365": {"HOME": 2.0, "DRAW": 3.2, "AWAY": 4.0},
        "Betfair": {"HOME": 2.0, "DRAW": 3.2, "AWAY": 4.0},
        "Pinnacle": {"HOME": 2.0, "DRAW": 3.2, "AWAY": 4.0},
    }
    if missing_book:
        books.pop(missing_book, None)
    if missing_sel:
        bm, sel = missing_sel
        if bm in books:
            books[bm][sel] = None  # type: ignore[index]
    return {"bookmakers": books, "raw_by_bookmaker_id": {"8": []}}


def _cecchino_output(**final_overrides) -> dict:
    final = {
        "status": STATUS_AVAILABLE,
        "quota_1": 2.1,
        "quota_x": 3.2,
        "quota_2": 4.5,
        "prob_1": 0.45,
        "prob_x": 0.30,
        "prob_2": 0.25,
        "warnings": [],
    }
    final.update(final_overrides)
    return {
        "status": STATUS_AVAILABLE,
        "warnings": [],
        "picchetti": {
            PICCHETTO_KEY_HOME_AWAY: _pic_block(),
            PICCHETTO_KEY_TOTALS: _pic_block(),
            PICCHETTO_KEY_LAST5_HOME_AWAY: _pic_block(),
            PICCHETTO_KEY_LAST6_TOTALS: _pic_block(),
        },
        "final": final,
    }


def _kpi_panel(**row_overrides) -> dict:
    def row(key: str, label: str, cec: float, book: float) -> dict:
        base = {
            "market_key": key,
            "label": label,
            "cecchino": cec,
            "book": book,
            "edge": round((book / cec - 1) * 100, 2),
            "status": "available",
        }
        base.update(row_overrides.get(key, {}))
        return base

    return {
        "bookmaker_status": "available",
        "rows": [
            row(SEL_HOME, "1", 2.1, 2.0),
            row(SEL_DRAW, "X", 3.2, 3.1),
            row(SEL_AWAY, "2", 4.5, 4.4),
        ],
        "warnings": [],
    }


def _eligible_baseline() -> dict:
    return {
        "odds_snapshot": _odds_snapshot(),
        "stats_snapshot": _stats_snapshot(),
        "cecchino_output": _cecchino_output(),
        "kpi_panel": _kpi_panel(),
        "warnings": [],
        "leakage_status": LEAKAGE_PASSED,
    }


def test_complete_pipeline_eligible():
    b = _eligible_baseline()
    result = validate_cecchino_today_final_eligibility(**b)
    assert result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert result.blocking_reasons == []


def test_missing_bookmaker_excluded():
    b = _eligible_baseline()
    b["odds_snapshot"] = _odds_snapshot(missing_book="Bet365")
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER
    assert any("missing_bookmaker:Bet365" in r for r in result.blocking_reasons)


def test_missing_1x2_market_excluded():
    b = _eligible_baseline()
    b["odds_snapshot"] = _odds_snapshot(missing_sel=("Bet365", "DRAW"))
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_1X2


def test_low_sample_recent_context_excluded():
    b = _eligible_baseline()
    b["stats_snapshot"] = _stats_snapshot(**{KEY_HOME_RECENT_CONTEXT_5: 2})
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
    assert any("low_sample:home_recent_context_5" in r for r in result.blocking_reasons)


def test_missing_picchetto_quotas_excluded():
    b = _eligible_baseline()
    output = _cecchino_output()
    output["final"] = {
        "status": STATUS_INSUFFICIENT_DATA,
        "warnings": ["missing_picchetto_quotas:totals"],
    }
    b["cecchino_output"] = output
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_MISSING_PICCHETTO


def test_zero_probability_x_excluded():
    b = _eligible_baseline()
    b["warnings"] = [f"{WARNING_ZERO_PROBABILITY}:X"]
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY


def test_final_odds_insufficient_data_excluded():
    b = _eligible_baseline()
    b["cecchino_output"] = _cecchino_output(status=STATUS_INSUFFICIENT_DATA, quota_1=None, prob_1=None)
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE


def test_kpi_panel_1x2_insufficient_excluded():
    b = _eligible_baseline()
    b["kpi_panel"] = _kpi_panel(**{SEL_DRAW: {"cecchino": None, "book": 3.1, "edge": None}})
    result = validate_cecchino_today_final_eligibility(**b)
    assert not result.is_eligible
    assert result.eligibility_status == ELIGIBILITY_EXCLUDED_KPI_NOT_CALCULABLE


def test_fixtures_ft_imported_not_blocking_warning():
    import_info, blocking, non_blocking = partition_scan_warnings(["fixtures_ft_imported:45", "leakage_check:undefined"])
    assert import_info == ["fixtures_ft_imported:45"]
    assert blocking == []
    assert "leakage_check:undefined" in non_blocking

    b = _eligible_baseline()
    b["warnings"] = ["fixtures_ft_imported:45"]
    result = validate_cecchino_today_final_eligibility(**b)
    assert result.is_eligible
    assert result.import_info == ["fixtures_ft_imported:45"]
    assert "fixtures_ft_imported:45" not in result.warnings


def test_revalidate_day_moves_eligible_to_excluded():
    row = MagicMock(spec=CecchinoTodayFixture)
    row.cecchino_output_json = _cecchino_output(status=STATUS_INSUFFICIENT_DATA, quota_x=None, prob_x=None)
    row.kpi_panel_json = _kpi_panel()
    row.odds_snapshot_json = _odds_snapshot()
    row.stats_snapshot_json = _stats_snapshot()
    row.warnings_json = []
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.cecchino_status = STATUS_INSUFFICIENT_DATA

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    report = revalidate_cecchino_today_day(db, scan_date=date(2026, 6, 4))
    assert report["moved_to_excluded"] == 1
    assert row.eligibility_status == ELIGIBILITY_EXCLUDED_CECCHINO_NOT_CALCULABLE
    db.commit.assert_called_once()


def test_list_eligible_only_returns_eligible():
    eligible_row = MagicMock(spec=CecchinoTodayFixture)
    eligible_row.eligibility_status = ELIGIBILITY_ELIGIBLE
    eligible_row.kickoff = None
    eligible_row.kpi_panel_json = {}
    eligible_row.cecchino_output_json = {}
    eligible_row.country_name = "Italy"
    eligible_row.league_name = "Serie A"
    eligible_row.country_flag_url = None
    eligible_row.league_logo_url = None
    eligible_row.home_team_name = "A"
    eligible_row.away_team_name = "B"
    eligible_row.id = 1
    eligible_row.provider_fixture_id = 1
    eligible_row.local_fixture_id = 1
    eligible_row.competition_id = 1
    eligible_row.home_team_logo_url = None
    eligible_row.away_team_logo_url = None
    eligible_row.match_display_status = "upcoming"
    eligible_row.fixture_status = "NS"
    eligible_row.goals_home = None
    eligible_row.goals_away = None
    eligible_row.score_fulltime_home = None
    eligible_row.score_fulltime_away = None
    eligible_row.elapsed_minutes = None

    db = MagicMock()
    db.scalars.return_value.all.return_value = [eligible_row]

    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": True, "eligible_count": 1, "excluded_count": 0, "last_scan_at": None},
    ):
        payload = list_eligible_today(db, scan_date=date(2026, 6, 4))
    assert payload["total"] == 1
    assert payload["summary"]["eligible_count"] == 1


def test_list_excluded_includes_blocking_reasons():
    row = MagicMock(spec=CecchinoTodayFixture)
    row.id = 2
    row.provider_fixture_id = 2
    row.home_team_name = "H"
    row.away_team_name = "A"
    row.league_name = "L"
    row.country_name = "C"
    row.kickoff = None
    row.eligibility_status = ELIGIBILITY_EXCLUDED_ZERO_PROBABILITY
    row.eligibility_reason = "zero"
    row.blocking_reasons_json = [f"{WARNING_ZERO_PROBABILITY}:X"]
    row.odds_snapshot_json = _odds_snapshot()
    row.stats_snapshot_json = _stats_snapshot()
    row.cecchino_output_json = _cecchino_output()
    row.kpi_panel_json = _kpi_panel()
    row.warnings_json = []
    row.bookmaker_status = "ok"
    row.stats_status = "insufficient"
    row.fixture_status = "NS"
    row.raw_fixture_json = {}

    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]

    with patch(
        "app.services.cecchino.cecchino_today_service.get_day_scan_meta",
        return_value={"has_scan": True, "eligible_count": 0, "excluded_count": 1, "last_scan_at": None},
    ):
        payload = list_excluded_today_enriched(db, scan_date=date(2026, 6, 4))
    assert payload["total"] == 1
    fx = payload["fixtures"][0]
    assert fx["blocking_reasons"] == [f"{WARNING_ZERO_PROBABILITY}:X"]
    assert fx["cecchino_debug"]["final_odds_status"] == STATUS_AVAILABLE
