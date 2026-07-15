"""Test dataset storico Credibilità X — Fase 1B."""

from __future__ import annotations

from datetime import date, datetime, timezone
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
from app.services.cecchino.cecchino_draw_credibility_dataset import (
    CSV_COLUMNS,
    VERSION,
    build_draw_credibility_historical_dataset,
    dataset_csv_filename,
    rows_for_selected_cohort,
    stream_draw_credibility_dataset_csv,
    _sanitize_csv_value,
)
from app.services.cecchino.cecchino_draw_credibility_research_common import (
    COHORT_ALL_USABLE_SENSITIVITY,
    COHORT_ELIGIBLE_PRIMARY,
    COHORT_MARKET_SUBSET,
    LEAKAGE_SAFE,
    LEAKAGE_UNSAFE,
    LEAKAGE_UNKNOWN,
    classify_leakage,
    extract_final_weight_fields,
    normalize_prob_triple,
    num,
    prob_to_percent,
    resolve_cecchino_final_version,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME, SEL_OVER_2_5, SEL_UNDER_2_5


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
        SEL_UNDER_2_5: {"final_odd": 1.85, "status": STATUS_AVAILABLE, "probability": 0.52},
        SEL_OVER_2_5: {"final_odd": 2.05, "status": STATUS_AVAILABLE, "probability": 0.48},
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
    kickoff = datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc)
    created = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
    defaults = {
        "id": 1,
        "provider_fixture_id": 9001,
        "local_fixture_id": 501,
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
        "kickoff": kickoff,
        "created_at": created,
        "cecchino_output_json": {"version": "cecchino_v1", "final": _final(), "goal_markets": _goal_markets()},
        "kpi_panel_json": _kpi_panel(),
        "odds_snapshot_json": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _dataset(rows: list, **kwargs) -> dict:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return build_draw_credibility_historical_dataset(
        db,
        date_from=kwargs.get("date_from", date(2025, 1, 1)),
        date_to=kwargs.get("date_to", date(2025, 12, 31)),
        competition_id=kwargs.get("competition_id"),
        cohort=kwargs.get("cohort", COHORT_ELIGIBLE_PRIMARY),
        page=kwargs.get("page", 1),
        page_size=kwargs.get("page_size", 100),
    )


def test_version_constant():
    assert VERSION == "cecchino_draw_credibility_dataset_v1_1"


def test_one_row_per_provider_fixture_id():
    rows = [
        _row(id=1, scan_date=date(2025, 6, 14)),
        _row(id=2, scan_date=date(2025, 6, 16), score_fulltime_home=2, score_fulltime_away=0, goals_home=2, goals_away=0),
    ]
    result = _dataset(rows)
    assert result["primary_summary"]["final_dataset_rows"] == 1
    assert result["deduplication"]["duplicates_collapsed"] == 1


def test_duplicate_scan_dates_collapsed():
    rows = [_row(id=i, scan_date=date(2025, 6, 15)) for i in range(1, 4)]
    result = _dataset(rows)
    assert result["deduplication"]["raw_rows"] == 3
    assert result["primary_summary"]["final_dataset_rows"] == 1


def test_pre_match_snapshot_selected():
    early = _row(id=1, created_at=datetime(2025, 6, 14, 8, 0, tzinfo=timezone.utc))
    late = _row(
        id=2,
        created_at=datetime(2025, 6, 15, 17, 0, tzinfo=timezone.utc),
        cecchino_output_json={"final": _final(quota_x=2.9), "goal_markets": _goal_markets()},
    )
    result = _dataset([early, late])
    assert result["rows"][0]["today_fixture_id_feature"] == 2
    assert result["rows"][0]["quota_cecchino_x"] == 2.9


def test_post_kickoff_snapshot_excluded_from_cohort():
    post = _row(
        id=1,
        created_at=datetime(2025, 6, 15, 19, 0, tzinfo=timezone.utc),
        kickoff=datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc),
    )
    result = _dataset([post])
    assert result["primary_summary"]["final_dataset_rows"] == 0
    assert result["anti_leakage"]["unsafe"] >= 0


def test_leakage_unknown_when_kickoff_missing():
    row = _row(kickoff=None)
    status, before, _ = classify_leakage(row.created_at, None)
    assert status == LEAKAGE_UNKNOWN
    assert before is None


def test_target_from_different_row():
    feature = _row(
        id=1,
        match_display_status=MATCH_UPCOMING,
        score_fulltime_home=None,
        score_fulltime_away=None,
        scan_date=date(2025, 6, 14),
        created_at=datetime(2025, 6, 14, 10, 0, tzinfo=timezone.utc),
    )
    target = _row(
        id=2,
        scan_date=date(2025, 6, 16),
        created_at=datetime(2025, 6, 16, 22, 0, tzinfo=timezone.utc),
        score_fulltime_home=1,
        score_fulltime_away=1,
    )
    result = _dataset([feature, target])
    assert result["rows"][0]["today_fixture_id_feature"] == 1
    assert result["rows"][0]["today_fixture_id_target"] == 2
    assert result["rows"][0]["draw_ft"] == 1


def test_draw_result():
    result = _dataset([_row()])
    assert result["rows"][0]["draw_ft"] == 1
    assert result["rows"][0]["result_1x2"] == "X"


def test_non_draw_result():
    result = _dataset([_row(score_fulltime_home=2, score_fulltime_away=1, goals_home=2, goals_away=1)])
    assert result["rows"][0]["draw_ft"] == 0
    assert result["rows"][0]["result_1x2"] == "1"


def test_primary_cohort_requires_eligible():
    result = _dataset([_row(eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)])
    assert result["primary_summary"]["final_dataset_rows"] == 0
    assert result["sensitivity_summary"]["final_dataset_rows"] == 1


def test_sensitivity_cohort_includes_non_eligible():
    result = _dataset(
        [_row(eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)],
        cohort="all_usable_sensitivity",
    )
    assert result["sensitivity_summary"]["final_dataset_rows"] == 1


def test_market_subset():
    result = _dataset([_row()], cohort=COHORT_MARKET_SUBSET)
    assert result["market_summary"]["final_dataset_rows"] == 1
    assert result["rows"][0]["has_market_features"] is True


def test_market_subset_excludes_missing_book():
    result = _dataset([_row(kpi_panel_json=_kpi_panel(with_book=False))], cohort=COHORT_MARKET_SUBSET)
    assert result["market_summary"]["final_dataset_rows"] == 0
    assert result["sensitivity_summary"]["final_dataset_rows"] == 1


def test_legacy_payload_excluded():
    result = _dataset([_row(cecchino_output_json=None)])
    assert result["primary_summary"]["final_dataset_rows"] == 0


def test_book_missing_does_not_exclude_internal():
    result = _dataset([_row(kpi_panel_json=_kpi_panel(with_book=False))])
    assert result["primary_summary"]["final_dataset_rows"] == 1


def test_prob_normalization_0_1():
    probs = normalize_prob_triple(prob_1=0.45, prob_x=0.28, prob_2=0.27)
    assert probs["prob_1_pct"] == pytest.approx(45.0, abs=0.1)
    assert probs["probability_normalization_applied"] is False


def test_prob_normalization_0_100():
    probs = normalize_prob_triple(prob_1=45, prob_x=28, prob_2=27)
    assert probs["prob_x_norm"] == pytest.approx(28.0, abs=0.1)


def test_prob_normalization_renormalizes():
    probs = normalize_prob_triple(prob_1=40, prob_x=30, prob_2=20)
    assert probs["probability_normalization_applied"] is True
    assert probs["prob_1_norm"] + probs["prob_x_norm"] + probs["prob_2_norm"] == pytest.approx(100.0, abs=0.1)


def test_x_rank_first():
    result = _dataset([_row()])
    assert result["rows"][0]["x_rank"] in (1, 2, 3)


def test_x_tied_for_top():
    result = _dataset([
        _row(cecchino_output_json={
            "final": _final(prob_1=0.33, prob_x=0.34, prob_2=0.33),
            "goal_markets": _goal_markets(),
        }),
    ])
    assert isinstance(result["rows"][0]["x_tied_for_top"], bool)


def test_dominance_pp_present():
    result = _dataset([_row()])
    assert result["rows"][0]["dominance_pp"] is not None


def test_conviction_index_candidate():
    result = _dataset([_row()])
    val = result["rows"][0]["conviction_index_candidate"]
    assert val is None or (0 <= val <= 100)


def test_probability_balance_index():
    result = _dataset([_row()])
    assert result["rows"][0]["probability_balance_index"] is not None


def test_gap_coherence_index_candidate():
    result = _dataset([_row()])
    val = result["rows"][0]["gap_coherence_index_candidate"]
    assert val is None or (0 <= val <= 100)


def test_goal_direct_probability():
    result = _dataset([_row()])
    assert result["rows"][0]["goal_probability_source"] == "direct_probability"


def test_goal_from_odds_when_no_direct_prob():
    gm = _goal_markets()
    gm[SEL_UNDER_2_5] = {"final_odd": 1.85, "status": STATUS_AVAILABLE}
    gm[SEL_OVER_2_5] = {"final_odd": 2.05, "status": STATUS_AVAILABLE}
    result = _dataset([_row(cecchino_output_json={"final": _final(), "goal_markets": gm})])
    assert result["rows"][0]["goal_probability_source"] == "normalized_from_cecchino_odds"


def test_book_normalization():
    result = _dataset([_row()])
    row = result["rows"][0]
    assert row["prob_book_x_norm"] is not None
    assert row["prob_book_under_2_5_norm"] is not None


def test_market_deviation():
    result = _dataset([_row()])
    assert result["rows"][0]["deviation_x_pp"] is not None
    assert result["rows"][0]["market_deviation_mean_pp"] is not None


def test_version_distribution():
    result = _dataset([_row()])
    assert "cecchino_output" in result["version_distribution"]
    assert len(result["version_distribution"]["cecchino_output"]) >= 1


def test_pagination():
    rows = [_row(id=i, provider_fixture_id=9000 + i) for i in range(5)]
    result = _dataset(rows, page=1, page_size=2)
    assert len(result["rows"]) == 2
    assert result["pagination"]["total_rows"] == 5
    assert result["pagination"]["total_pages"] == 3


def test_csv_stream_complete():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [_row()]
    chunks = list(stream_draw_credibility_dataset_csv(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        cohort=COHORT_ELIGIBLE_PRIMARY,
    ))
    text = "".join(chunks)
    assert text.startswith("\ufeff")
    assert "provider_fixture_id" in text
    assert "draw_ft" in text


def test_csv_injection_sanitized():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [_row(home_team_name="=CMD()")]
    text = "".join(stream_draw_credibility_dataset_csv(
        db, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31),
    ))
    assert "'=CMD()" in text or ";'=CMD()" in text


def test_zero_rows():
    result = _dataset([])
    assert result["primary_summary"]["final_dataset_rows"] == 0
    assert result["target_distribution"]["draw_rate_pct"] == 0.0


def test_no_external_api_calls():
    with patch(
        "app.services.cecchino.cecchino_draw_credibility_research_common.build_betfair_payload_from_snapshot",
    ) as mock_snapshot:
        mock_snapshot.return_value = {"bookmakers": [], "status": "not_available"}
        _dataset([_row(kpi_panel_json=_kpi_panel(with_book=False))])
        mock_snapshot.assert_called()


def test_db_not_modified():
    db = MagicMock()
    db.scalars.return_value.all.return_value = [_row()]
    build_draw_credibility_historical_dataset(
        db, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31),
    )
    db.commit.assert_not_called()
    db.delete.assert_not_called()


def test_payload_json_serializable():
    result = _dataset([_row()])
    encoded = jsonable_encoder(result)
    assert encoded["version"] == VERSION


def test_prob_to_percent_helper():
    assert prob_to_percent(0.5) == 50.0
    assert prob_to_percent(None, 33.0) == 33.0


def test_leakage_unsafe_classification():
    feat = datetime(2025, 6, 15, 19, 0, tzinfo=timezone.utc)
    kick = datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc)
    status, before, _ = classify_leakage(feat, kick)
    assert status == LEAKAGE_UNSAFE
    assert before is False


def test_consistency_checks_present():
    result = _dataset([_row()])
    cc = result["consistency_checks"]
    assert "expected_primary_from_audit" in cc
    assert "difference_primary_vs_audit" in cc
    assert "cohort_consistency" in result
    assert len(result["cohort_consistency"]) == 3


def test_global_pipeline_separate_from_cohort():
    rows = [_row(id=i, provider_fixture_id=9000 + i) for i in range(3)]
    result = _dataset(rows)
    gp = result["global_pipeline"]
    cs = result["selected_cohort_summary"]
    assert gp["raw_database_rows"] == 3
    assert gp["global_duplicates_collapsed"] == 0
    assert cs["unique_provider_fixtures"] == 3
    assert cs["final_dataset_rows"] == 3


def test_selected_cohort_summary_uses_cohort_metrics_not_global():
    rows = [_row(id=i, provider_fixture_id=9000 + i) for i in range(2)]
    result = _dataset(rows, cohort=COHORT_ELIGIBLE_PRIMARY)
    summary = result["selected_cohort_summary"]
    assert summary["unique_provider_fixtures"] == 2
    assert summary["final_dataset_rows"] == 2
    assert summary["unique_provider_fixtures"] != result["global_pipeline"]["unique_provider_fixtures"] or (
        result["global_pipeline"]["unique_provider_fixtures"] == 2
    )


def test_anti_leakage_selected_primary_vs_global():
    eligible = _row(id=1, provider_fixture_id=9001)
    non_eligible = _row(
        id=2,
        provider_fixture_id=9002,
        eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER,
    )
    result = _dataset([eligible, non_eligible], cohort=COHORT_ELIGIBLE_PRIMARY)
    assert result["anti_leakage_selected"]["safe"] == 1
    assert result["anti_leakage_global"]["safe"] == 2


def test_version_distribution_selected_matches_cohort_size():
    rows = [_row(id=i, provider_fixture_id=9000 + i) for i in range(3)]
    result = _dataset(rows, cohort=COHORT_ELIGIBLE_PRIMARY)
    total = sum(v["count"] for v in result["version_distribution_selected"]["balance_analysis"])
    assert total == 3
    assert result["version_distribution"]["balance_analysis"][0]["count"] == 3


def test_csv_cohort_primary():
    text = _csv_text([_row()], cohort=COHORT_ELIGIBLE_PRIMARY)
    lines = text.strip().split("\n")
    assert "eligible_primary" in lines[1]


def test_csv_cohort_sensitivity():
    text = _csv_text(
        [_row(eligibility_status=ELIGIBILITY_EXCLUDED_MISSING_BOOKMAKER)],
        cohort=COHORT_ALL_USABLE_SENSITIVITY,
    )
    assert "all_usable_sensitivity" in text


def test_csv_cohort_market():
    text = _csv_text([_row()], cohort=COHORT_MARKET_SUBSET)
    assert "market_subset" in text


def test_csv_negative_float_without_apostrophe():
    row = _row(
        cecchino_output_json={
            "final": _final(quota_1=2.5, quota_2=2.0, prob_1=0.40, prob_x=0.30, prob_2=0.30),
            "goal_markets": _goal_markets(),
        },
    )
    text = _csv_text([row])
    assert "'-" not in text.split("\n")[1]


def test_sanitize_csv_negative_float():
    assert _sanitize_csv_value(-1.5603) == "-1.5603"
    assert _sanitize_csv_value(-3) == "-3"


def test_sanitize_csv_injection_string():
    assert _sanitize_csv_value("-cmd") == "'-cmd"
    assert _sanitize_csv_value("=SUM(A1)") == "'=SUM(A1)"


def test_csv_all_columns_present():
    import csv
    import io

    text = _csv_text([_row()])
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    assert reader.fieldnames == list(CSV_COLUMNS)


def test_csv_numeric_fields_parseable():
    import csv
    import io

    text = _csv_text([_row()])
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    row = next(reader)
    assert row["f36_signed"] == "" or float(row["f36_signed"]) or row["f36_signed"] == "0"


def test_dataset_csv_filename_primary():
    name = dataset_csv_filename(
        cohort=COHORT_ELIGIBLE_PRIMARY,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 15),
    )
    assert name == "cecchino_draw_credibility_eligible_primary_2026-01-01_2026-07-15.csv"


def test_dataset_csv_filename_market():
    name = dataset_csv_filename(
        cohort=COHORT_MARKET_SUBSET,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 7, 15),
    )
    assert "market_subset" in name


def test_global_exclusions_breakdown_present():
    result = _dataset([_row(cecchino_output_json=None), _row()])
    assert "global_exclusions" in result
    assert result["global_exclusions"]["first_blocking_reason"] is True


def test_cohort_consistency_per_cohort_explanation():
    result = _dataset([_row()])
    primary = next(c for c in result["cohort_consistency"] if c["cohort"] == COHORT_ELIGIBLE_PRIMARY)
    assert "expected_from_audit" in primary
    assert "duplicates_removed_within_cohort" in primary


def test_rows_for_selected_cohort_does_not_mutate_source():
    built = _dataset([_row()])
    source_cohort = built["rows"][0]["cohort"]
    assert source_cohort == COHORT_ELIGIBLE_PRIMARY


def test_deduplication_within_cohort_from_audit_delta():
    rows = [
        _row(id=1, scan_date=date(2025, 6, 14)),
        _row(id=2, scan_date=date(2025, 6, 16), score_fulltime_home=2, score_fulltime_away=0, goals_home=2, goals_away=0),
    ]
    result = _dataset(rows)
    summary = result["cohort_summaries"][COHORT_ELIGIBLE_PRIMARY]
    assert summary["final_dataset_rows"] == 1
    assert summary["candidate_rows_before_dedup"] >= 1
    assert summary["duplicates_removed_within_cohort"] == max(
        0, summary["candidate_rows_before_dedup"] - summary["final_dataset_rows"]
    )


def test_legacy_fields_still_present():
    result = _dataset([_row()])
    assert "primary_summary" in result
    assert "anti_leakage" in result
    assert "version_distribution" in result
    assert "consistency_checks" in result


def _csv_text(rows: list, *, cohort: str = COHORT_ELIGIBLE_PRIMARY) -> str:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    chunks = list(stream_draw_credibility_dataset_csv(
        db,
        date_from=date(2025, 1, 1),
        date_to=date(2025, 12, 31),
        cohort=cohort,
    ))
    return "".join(chunks)


def test_cecchino_final_version_reads_version_not_weights():
    final = {
        "version": "cecchino_final_v3",
        "weights": {"totals": 0.4, "home_away": 0.6},
    }
    assert resolve_cecchino_final_version(final) == "cecchino_final_v3"


def test_cecchino_final_version_formula_fallback():
    final = {"formula_version": "formula_x", "weights": {"totals": 1.0}}
    assert resolve_cecchino_final_version(final) == "formula_x"


def test_cecchino_final_version_null_when_only_weights():
    final = {"weights": {"totals": 0.5, "home_away": 0.5}}
    assert resolve_cecchino_final_version(final) is None


def test_extract_final_weight_fields_maps_known_keys():
    final = {
        "weights": {
            "totals": 0.25,
            "home_away": 0.35,
            "last6_totals": 0.2,
            "last5_home_away": 0.2,
            "unknown_key": 99,
        }
    }
    weights = extract_final_weight_fields(final)
    assert weights["final_weight_totals"] == 0.25
    assert weights["final_weight_home_away"] == 0.35
    assert weights["final_weight_last6_totals"] == 0.2
    assert weights["final_weight_last5_home_away"] == 0.2


def test_dataset_row_includes_final_version_and_weight_columns():
    result = _dataset([
        _row(cecchino_output_json={
            "version": "cecchino_v1",
            "final": {
                "version": "cecchino_final_v2",
                "weights": {"totals": 0.3, "home_away": 0.7},
                **_final(),
            },
            "goal_markets": _goal_markets(),
        }),
    ])
    row = result["rows"][0]
    assert row["cecchino_final_version"] == "cecchino_final_v2"
    assert row["final_weight_totals"] == 0.3
    assert row["final_weight_home_away"] == 0.7
    for col in (
        "final_weight_totals",
        "final_weight_home_away",
        "final_weight_last6_totals",
        "final_weight_last5_home_away",
    ):
        assert col in CSV_COLUMNS


def test_csv_includes_final_weight_columns():
    text = _csv_text([
        _row(cecchino_output_json={
            "version": "cecchino_v1",
            "final": {
                "version": "cecchino_final_v2",
                "weights": {"totals": 0.4},
                **_final(),
            },
            "goal_markets": _goal_markets(),
        }),
    ])
    header = text.splitlines()[0]
    assert "final_weight_totals" in header
    assert "cecchino_final_version" in header

