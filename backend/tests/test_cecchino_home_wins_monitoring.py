"""Test coorte Monitoraggio Segno 1 — esito reale 1, snapshot-only."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_CUP,
    MATCH_FINISHED,
    MATCH_UPCOMING,
)
from app.services.cecchino import cecchino_home_wins_monitoring as hw
from app.services.cecchino.cecchino_home_wins_monitoring import (
    DATASET_VERSION,
    SELECTION_CONTRACT,
    build_home_win_detail_record,
    build_home_wins_export_files,
    build_home_wins_export_zip,
    classify_finished_home_win,
    get_home_win_detail,
    list_home_wins,
    row_in_home_wins_cohort,
)


def _row(**kwargs):
    base = dict(
        id=1001,
        provider_fixture_id=90001,
        local_fixture_id=501,
        competition_id=10,
        scan_date=date(2026, 7, 10),
        kickoff=datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc),
        country_name="Italy",
        league_name="Serie A",
        home_team_name="Juventus",
        away_team_name="Inter",
        match_display_status=MATCH_FINISHED,
        fixture_status="FT",
        goals_home=None,
        goals_away=None,
        score_fulltime_home=2,
        score_fulltime_away=1,
        score_halftime_home=1,
        score_halftime_away=0,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        eligibility_reason=None,
        odds_snapshot_json={"odds_meta": {"odds_fetched_at": "2026-07-10T10:00:00+00:00"}},
        stats_snapshot_json={"shots": 10},
        cecchino_output_json={
            "version": "cecchino_v1",
            "final": {"quota_1": 2.1, "quota_x": 3.2, "quota_2": 3.5, "prob_1": 0.4, "prob_x": 0.3, "prob_2": 0.3},
            "signals_matrix": {
                "status": "available",
                "rows": [{"key": "one", "label": "1", "signals": {"excel_d": "NO"}}],
            },
            "balance_v5_monitoring": {
                "status": "ok",
                "snapshot_version": "balance_monitoring_v1",
                "f36_index": 0.5,
                "f36_class": "Equilibrio",
                "dominance_index": 0.4,
                "dominance_class": "Leggero",
                "dominance_selection": "1",
                "draw_credibility_index": 0.3,
                "draw_credibility_class": "Media",
                "gap_index": 0.2,
                "gap_class": "Coerente",
                "prob_1_norm": 0.4,
                "prob_x_norm": 0.3,
                "prob_2_norm": 0.3,
                "book_prob_1": 0.38,
                "book_prob_x": 0.31,
                "book_prob_2": 0.31,
                "book_verified": True,
                "pre_match_verified": True,
                "source_mode": "prospective_scan",
                "warning_codes": [],
            },
            "purchasability_preview": {
                "items": [
                    {"market_key": "HOME", "score": 40, "class": "Media", "status": "available"},
                    {"market_key": "DRAW", "score": 20, "class": "Bassa", "status": "available"},
                    {"market_key": "AWAY", "score": 10, "class": "Bassa", "status": "available"},
                ]
            },
        },
        kpi_panel_json={
            "version": "cecchino_kpi_v2_betfair",
            "rows": [
                {
                    "market_key": "HOME",
                    "segno": "1",
                    "quota_book": 2.2,
                    "quota_cecchino": 2.1,
                    "prob_book": 0.45,
                    "prob_cecchino": 0.48,
                    "vantaggio_prob": 0.03,
                    "edge_pct": 4.5,
                    "score_acquisto": 0.02,
                    "rating": 3,
                    "rating_label": "Buono",
                    "status": "ok",
                },
                {
                    "market_key": "DRAW",
                    "segno": "X",
                    "quota_book": 3.3,
                    "quota_cecchino": 3.2,
                    "prob_book": 0.3,
                    "prob_cecchino": 0.31,
                    "vantaggio_prob": 0.01,
                    "edge_pct": 1.0,
                    "score_acquisto": 0.01,
                    "rating": 2,
                    "rating_label": "Discreto",
                    "status": "ok",
                },
                {
                    "market_key": "AWAY",
                    "segno": "2",
                    "quota_book": 3.6,
                    "quota_cecchino": 3.5,
                    "prob_book": 0.28,
                    "prob_cecchino": 0.29,
                    "vantaggio_prob": 0.01,
                    "edge_pct": 1.0,
                    "score_acquisto": 0.01,
                    "rating": 2,
                    "rating_label": "Discreto",
                    "status": "ok",
                },
            ],
        },
        xg_profiles_json={"home": {"xg": 1.2}},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


# --- Inclusion / exclusion ---


def test_finished_2_1_included():
    assert classify_finished_home_win(_row(score_fulltime_home=2, score_fulltime_away=1)) is not None


def test_finished_1_0_included():
    out = classify_finished_home_win(_row(score_fulltime_home=1, score_fulltime_away=0))
    assert out is not None
    assert out["outcome_1x2"] == "1"
    assert out["goal_difference"] == 1


def test_finished_1_1_excluded():
    assert classify_finished_home_win(_row(score_fulltime_home=1, score_fulltime_away=1)) is None


def test_finished_0_2_excluded():
    assert classify_finished_home_win(_row(score_fulltime_home=0, score_fulltime_away=2)) is None


def test_upcoming_2_1_excluded():
    assert (
        classify_finished_home_win(
            _row(match_display_status=MATCH_UPCOMING, score_fulltime_home=2, score_fulltime_away=1)
        )
        is None
    )


def test_finished_without_score_excluded():
    assert (
        classify_finished_home_win(
            _row(
                score_fulltime_home=None,
                score_fulltime_away=None,
                goals_home=None,
                goals_away=None,
            )
        )
        is None
    )


def test_goals_fallback_traced():
    out = classify_finished_home_win(
        _row(
            score_fulltime_home=None,
            score_fulltime_away=None,
            goals_home=3,
            goals_away=1,
        )
    )
    assert out is not None
    assert out["result_source"] == "goals_fallback"
    assert out["ft_home"] == 3


def test_signal_1_active_not_required():
    row = _row()
    row.cecchino_output_json["signals_matrix"]["rows"][0]["signals"]["excel_d"] = "SI"
    assert row_in_home_wins_cohort(row)


def test_signal_1_inactive_still_included():
    row = _row()
    row.cecchino_output_json["signals_matrix"]["rows"][0]["signals"]["excel_d"] = "NO"
    assert row_in_home_wins_cohort(row)
    detail = build_home_win_detail_record(row)
    assert detail["observational"]["signal_1_was_active"] is False
    assert detail["selection_contract"]["signal_1_used_for_selection"] is False


def test_eligibility_not_used_as_filter():
    row = _row(eligibility_status=ELIGIBILITY_EXCLUDED_CUP)
    assert row_in_home_wins_cohort(row)
    detail = build_home_win_detail_record(row)
    assert detail["identity"]["eligibility_status"] == ELIGIBILITY_EXCLUDED_CUP


def test_partial_record_included_and_marked():
    row = _row(
        kpi_panel_json=None,
        cecchino_output_json={"signals_matrix": {}, "final": {}},
        odds_snapshot_json=None,
        stats_snapshot_json=None,
        xg_profiles_json=None,
    )
    detail = build_home_win_detail_record(row)
    assert detail is not None
    assert detail["source_integrity"]["completeness_status"] == "partial"
    assert detail["pre_match_snapshot"]["balance_v5_monitoring"]["status"] == "unavailable"
    assert (
        detail["pre_match_snapshot"]["balance_v5_monitoring"]["reason"]
        == "persisted_balance_snapshot_missing"
    )
    assert (
        detail["pre_match_snapshot"]["goal_intensity_v5_preview"]["reason"]
        == "persisted_goal_intensity_v5_snapshot_missing"
    )


def test_balance_missing_not_rebuilt():
    row = _row()
    row.cecchino_output_json = {"final": {"quota_1": 2.0, "prob_1": 0.4}}
    with patch(
        "app.services.cecchino.cecchino_balance_v5_monitoring.build_balance_v5_from_stored_row",
        side_effect=AssertionError("must not rebuild"),
    ), patch(
        "app.services.cecchino.cecchino_balance_v5.build_cecchino_balance_v5",
        side_effect=AssertionError("must not rebuild"),
    ):
        detail = build_home_win_detail_record(row)
    assert detail["pre_match_snapshot"]["balance_v5_monitoring"]["status"] == "unavailable"


def test_goal_intensity_missing_not_rebuilt():
    row = _row()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
        side_effect=AssertionError("must not call get_preview_detail"),
    ):
        detail = build_home_win_detail_record(row, gi_snap=None)
    assert detail["pre_match_snapshot"]["goal_intensity_v5_preview"]["status"] == "unavailable"


def _db_with_rows(rows: list):
    db = MagicMock()

    def get_side_effect(_model, pk):
        for r in rows:
            if int(r.id) == int(pk):
                return r
        return None

    db.get.side_effect = get_side_effect
    db.scalars.return_value.all.return_value = []
    return db


def test_list_pagination_and_sort():
    r1 = _row(id=1, kickoff=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc))
    r2 = _row(id=2, kickoff=datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc))
    r3 = _row(id=3, kickoff=datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc))
    # fetch returns already sorted kickoff DESC, id DESC
    ordered = [r3, r2, r1]
    db = _db_with_rows(ordered)
    with patch.object(hw, "fetch_home_win_rows", return_value=ordered), patch.object(
        hw, "_load_gi_snapshots_bulk", return_value={}
    ):
        page1 = list_home_wins(db, page=1, page_size=2)
        page2 = list_home_wins(db, page=2, page_size=2)
    assert page1["total"] == 3
    assert [i["today_fixture_id"] for i in page1["items"]] == [3, 2]
    assert [i["today_fixture_id"] for i in page2["items"]] == [1]
    assert page1["selection_contract"]["signal_1_used_for_selection"] is False


def test_list_filters_completeness():
    gi_ok = MagicMock()
    gi_ok.id = 1
    gi_ok.bundle_id = 1
    gi_ok.preview_status = "ok"
    gi_ok.snapshot_status = "locked"
    gi_ok.primary_candidate_score = 50.0
    gi_ok.challenger_candidate_score = 45.0
    gi_ok.benchmark_score = 40.0
    gi_ok.diagnostic_score = 35.0
    gi_ok.history_sample_size = 20
    gi_ok.xg_status = "ok"
    gi_ok.source_snapshot_at = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)
    gi_ok.kickoff = datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)
    gi_ok.no_target_used_in_score = True
    gi_ok.feature_status = "ok"
    gi_ok.candidate_scores_payload = {}
    gi_ok.pillar_scores_payload = {}
    gi_ok.calibrated_predictions_payload = {
        "GI_A_STRICT_CORE": {
            "expected_total_goals": 2.4,
            "probability_goals_ge_2": 0.6,
            "probability_goals_ge_3": 0.35,
            "probability_btts": 0.5,
        }
    }
    gi_ok.feature_payload = {}
    gi_ok.diagnostic_reason_codes = []

    full = _row(id=1, country_name="Italy")
    partial = _row(
        id=2,
        country_name="Italy",
        kpi_panel_json=None,
        cecchino_output_json={"final": {}},
        odds_snapshot_json=None,
        stats_snapshot_json=None,
    )
    with patch.object(hw, "fetch_home_win_rows", return_value=[full, partial]), patch.object(
        hw,
        "_load_gi_snapshots_bulk",
        return_value={1: gi_ok},
    ):
        db = MagicMock()
        out = list_home_wins(db, completeness="partial", page=1, page_size=50)
        out_complete = list_home_wins(db, completeness="complete", page=1, page_size=50)
    assert out["total"] == 1
    assert out["items"][0]["completeness_status"] == "partial"
    assert out_complete["total"] == 1
    assert out_complete["items"][0]["today_fixture_id"] == 1


def test_detail_uses_persisted_payloads_only():
    row = _row()
    detail = build_home_win_detail_record(row)
    assert detail["pre_match_snapshot"]["kpi_panel"]["version"] == "cecchino_kpi_v2_betfair"
    assert detail["pre_match_snapshot"]["balance_v5_monitoring"]["f36_index"] == 0.5
    assert detail["post_match_outcome"]["outcome_1x2"] == "1"
    bal_dump = json.dumps(detail["pre_match_snapshot"]["balance_v5_monitoring"])
    assert "ft_home" not in bal_dump


def test_export_contains_expected_files_and_stable_csv():
    rows = [_row(id=10), _row(id=11, provider_fixture_id=90002)]
    db = MagicMock()
    with patch.object(hw, "fetch_home_win_rows", return_value=rows), patch.object(
        hw, "_load_gi_snapshots_bulk", return_value={}
    ):
        files = build_home_wins_export_files(db)
        zip_bytes, filename = build_home_wins_export_zip(db)
    assert filename.startswith("SOT_CECCHINO_HOME_WINS_DATASET_")
    assert set(files) == {
        "manifest.json",
        "schema.json",
        "quality_report.json",
        "home_wins_features.csv",
        "home_wins_full.jsonl",
    }
    manifest = json.loads(files["manifest.json"])
    assert manifest["signal_1_used_for_selection"] is False
    assert manifest["record_count"] == 2
    assert manifest["dataset_version"] == DATASET_VERSION

    csv_text = files["home_wins_features.csv"].decode("utf-8-sig")
    header = csv_text.splitlines()[0].split(",")
    assert header[0] == "today_fixture_id"
    assert "kpi_1_quota_book" in header
    assert "gi_v5_primary_candidate_score" in header

    for line in files["home_wins_full.jsonl"].decode("utf-8").strip().splitlines():
        obj = json.loads(line)
        dumped = json.dumps(obj, allow_nan=False)
        assert "NaN" not in dumped
        assert "Infinity" not in dumped
        assert obj["selection_contract"] == SELECTION_CONTRACT

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert set(zf.namelist()) == set(files)


def test_export_not_limited_to_page():
    rows = [_row(id=i, provider_fixture_id=80000 + i) for i in range(1, 6)]
    db = MagicMock()
    with patch.object(hw, "fetch_home_win_rows", return_value=rows), patch.object(
        hw, "_load_gi_snapshots_bulk", return_value={}
    ):
        listed = list_home_wins(db, page=1, page_size=2)
        files = build_home_wins_export_files(db)
    assert listed["total"] == 5
    assert len(listed["items"]) == 2
    assert json.loads(files["manifest.json"])["record_count"] == 5
    assert files["home_wins_full.jsonl"].decode("utf-8").count("\n") == 5


def test_no_duplicate_today_fixture_id_in_export():
    row = _row(id=42)
    db = MagicMock()
    with patch.object(hw, "fetch_home_win_rows", return_value=[row, row]), patch.object(
        hw, "_load_gi_snapshots_bulk", return_value={}
    ):
        files = build_home_wins_export_files(db)
    assert json.loads(files["manifest.json"])["record_count"] == 1


def test_builders_monkeypatched_raise_still_works():
    row = _row()
    db = MagicMock()
    db.get.return_value = row
    with (
        patch(
            "app.services.cecchino.cecchino_balance_v5.build_cecchino_balance_v5",
            side_effect=RuntimeError("rebuild forbidden"),
        ),
        patch(
            "app.services.cecchino.cecchino_balance_v5_monitoring.build_balance_v5_from_stored_row",
            side_effect=RuntimeError("rebuild forbidden"),
        ),
        patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_preview_detail",
            side_effect=RuntimeError("rebuild forbidden"),
        ),
        patch(
            "app.services.cecchino.cecchino_today_service.get_today_fixture_detail",
            side_effect=RuntimeError("rebuild forbidden"),
        ),
        patch.object(hw, "fetch_home_win_rows", return_value=[row]),
        patch.object(hw, "_load_gi_snapshots_bulk", return_value={}),
    ):
        listed = list_home_wins(db)
        detail = get_home_win_detail(db, 1001)
        files = build_home_wins_export_files(db)
    assert listed["status"] == "ok"
    assert detail["status"] == "ok"
    assert "manifest.json" in files


def test_update_results_then_cohort_includes_fixture():
    """Flusso automatico: dopo apply display finished 2-1 → coorte (senza Segnale 1)."""
    from app.services.cecchino.cecchino_today_display import apply_display_from_api

    row = MagicMock()
    row.id = 777
    row.match_display_status = MATCH_UPCOMING
    row.fixture_status = "NS"
    row.goals_home = None
    row.goals_away = None
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.score_halftime_home = None
    row.score_halftime_away = None
    row.elapsed_minutes = None
    row.country_flag_url = None
    row.league_logo_url = None
    row.home_team_logo_url = None
    row.away_team_logo_url = None
    row.cecchino_output_json = {
        "signals_matrix": {
            "status": "available",
            "rows": [{"key": "one", "label": "1", "signals": {"excel_d": "NO"}}],
        }
    }

    api_item = {
        "fixture": {"id": 555, "status": {"short": "FT", "elapsed": 90}},
        "goals": {"home": 2, "away": 1},
        "score": {
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
        },
        "league": {
            "flag": "https://f.png",
            "logo": "https://l.png",
            "country": "Italy",
            "name": "Serie A",
        },
        "teams": {"home": {"logo": "https://h.png"}, "away": {"logo": "https://a.png"}},
    }
    apply_display_from_api(row, api_item)
    assert row.match_display_status == MATCH_FINISHED
    assert row.score_fulltime_home == 2
    assert row.score_fulltime_away == 1
    assert row_in_home_wins_cohort(row)
    assert classify_finished_home_win(row)["outcome_1x2"] == "1"
    assert row.cecchino_output_json["signals_matrix"]["rows"][0]["signals"]["excel_d"] == "NO"
