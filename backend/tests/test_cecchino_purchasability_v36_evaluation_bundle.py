"""Test C1.3 bulk V3.6 evaluation bundle — read-only, population-driven."""

from __future__ import annotations

import copy
import csv
import io
import json
import os
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    MATCH_FINISHED,
    MATCH_UPCOMING,
)
from app.routes.cecchino_today import router
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_analysis_export import (
    COHORT_PROSPECTIVE,
    COHORT_TECHNICAL_SMOKE,
    PRIMARY_DIAGNOSTIC_COHORT,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    attach_purchasability_preview_v35_v2_to_output,
)
from app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle import (
    COMPARISON_CSV_COLUMNS,
    PANEL_SIZE,
    V36EvaluationBundleRangeError,
    build_v36_evaluation_bundle_zip,
    resolve_v31_pairability,
    validate_evaluation_bundle_date_range,
)

SNAP_AT = "2026-08-26T08:00:00+00:00"
KICKOFF = "2026-08-26T15:00:00+00:00"
NOW_BEFORE = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)


def _kpi_row(mk: str, *, quota: float = 2.2, rating: float = 60, prob: float = 0.55) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _build_v35_v2() -> tuple[dict, dict]:
    rows = [_kpi_row(mk) for mk in PANEL_MARKET_KEYS]
    panel = {"rows": rows}
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 1507044,
            "snapshot_at": SNAP_AT,
            "kickoff": KICKOFF,
        },
        snapshot_info={"snapshot_at": SNAP_AT, "snapshot_timestamp_verified": True},
    )
    attach_purchasability_preview_v35_v2_to_output(
        cecchino_output=output,
        kpi_panel=panel,
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 1507044,
            "snapshot_at": SNAP_AT,
            "kickoff": KICKOFF,
        },
        snapshot_info={
            "snapshot_at": SNAP_AT,
            "snapshot_timestamp_verified": True,
            "source_snapshot_before_kickoff": True,
        },
        now_utc=NOW_BEFORE,
    )
    return output["purchasability_preview_v35"], output[SNAPSHOT_OUTPUT_KEY]


def _minimal_v31(
    *,
    snap_at: str = SNAP_AT,
    pre_match_only: bool = True,
    before_kickoff: bool = True,
    align_inputs: bool = True,
) -> dict:
    items = []
    for mk in PANEL_MARKET_KEYS:
        items.append(
            {
                "market_key": mk,
                "status": "score",
                "score": 70,
                "raw_score": 70.5,
                "class": "BUY",
                "pre_match_only": True,
                "input": {
                    "execution_quote": 2.2 if align_inputs else 9.9,
                    "probability_cecchino": 0.55 if align_inputs else 0.1,
                    "fair_book_probability": round(1 / 2.2, 6) if align_inputs else 0.2,
                },
            }
        )
    return {
        "snapshot_version": PURCHASABILITY_V31_SNAPSHOT_VERSION,
        "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
        "status": "ok",
        "items": items,
        "pre_match_only": pre_match_only,
        "source_snapshot_before_kickoff": before_kickoff,
        "source_snapshot_at": snap_at,
        "generated_at": snap_at,
    }


def _fixture_row(
    *,
    fid: int = 1,
    provider_id: int = 1507044,
    scan_date: date | None = None,
    v35: dict | None = None,
    v36: dict | None = None,
    v31: dict | None = None,
    omit_v35: bool = False,
    omit_v31: bool = False,
    eligibility_status: str = ELIGIBILITY_ELIGIBLE,
    match_display_status: str = MATCH_FINISHED,
    goals_home: int | None = 2,
    goals_away: int | None = 1,
    kickoff: datetime | None = None,
) -> SimpleNamespace:
    if v35 is None or v36 is None:
        built_v35, built_v36 = _build_v35_v2()
        v35 = v35 or built_v35
        v36 = v36 or built_v36
    output: dict = {SNAPSHOT_OUTPUT_KEY: v36}
    if not omit_v35:
        output["purchasability_preview_v35"] = v35
    if not omit_v31:
        output["purchasability_preview_v31"] = v31 if v31 is not None else _minimal_v31()
    sd = scan_date or date(2026, 8, 26)
    ko = kickoff or datetime(sd.year, sd.month, sd.day, 15, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=provider_id,
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=ko,
        scan_date=sd,
        provider_season=2026,
        country_name="Italy",
        league_name="Serie A",
        eligibility_status=eligibility_status,
        fixture_status="FT" if match_display_status == MATCH_FINISHED else "NS",
        match_display_status=match_display_status,
        goals_home=goals_home,
        goals_away=goals_away,
        score_halftime_home=1 if goals_home is not None else None,
        score_halftime_away=0 if goals_away is not None else None,
        score_fulltime_home=goals_home,
        score_fulltime_away=goals_away,
        kpi_panel_json={"rows": [_kpi_row(mk) for mk in PANEL_MARKET_KEYS]},
        cecchino_output_json=output,
    )


def _mock_db(rows: list) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return db


def test_range_validation():
    with pytest.raises(V36EvaluationBundleRangeError):
        validate_evaluation_bundle_date_range(date(2026, 1, 1), date(2026, 3, 1))


def test_bundle_inclusive_five_days_same_zip():
    rows = [
        _fixture_row(fid=i, provider_id=1507000 + i, scan_date=date(2026, 8, d))
        for i, d in enumerate(range(26, 31), start=1)
    ]
    db = _mock_db(rows)
    zip_bytes, filename = build_v36_evaluation_bundle_zip(
        db, date_from=date(2026, 8, 26), date_to=date(2026, 8, 30)
    )
    assert filename == "cecchino-v36-analysis-2026-08-26_2026-08-30.zip"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "comparison_rows.csv" in names
        assert "fixture_summary.csv" in names
        assert "diagnostics/v36_holdout_diagnostics.json" in names
        assert "README.txt" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["date_from"] == "2026-08-26"
        assert manifest["date_to"] == "2026-08-30"
        assert manifest["range_inclusive"] is True
        assert manifest["recompute_used"] is False
        assert (
            manifest["formula_freeze_sha256_expected"] == EXPECTED_FORMULA_FREEZE_SHA256
        )
        summary = manifest["summary"]
        assert summary["snapshot_population_count"] == 5
        assert summary["valid_v36_snapshots"] == 5
        assert summary["comparison_rows_count"] == 5 * PANEL_SIZE
        assert summary["expected_comparison_rows_count"] == 5 * PANEL_SIZE
        assert summary["comparison_rows_complete"] is True
        assert summary["unique_fixture_summary_count"] == 5
        assert summary["fixture_summary_matches_population"] is True
        assert summary["panel_rows_exact_per_valid_v36"] is True
        assert summary["v35_population_partition_complete"] is True
        assert summary["v31_population_partition_complete"] is True
        assert summary["technical_smoke_fixture_count"] == 1
        assert summary["prospective_holdout_fixture_count"] == 4
        assert summary["PRIMARY_DIAGNOSTIC_COHORT"] == COHORT_PROSPECTIVE
        sc = manifest["self_check"]
        assert sc["comparison_rows_complete"] is True
        assert sc["fixture_summary_matches_population"] is True
        assert sc["panel_rows_exact_per_valid_v36"] is True
        assert sc["v35_population_partition_complete"] is True
        assert sc["v31_population_partition_complete"] is True
        days = manifest["days"]
        for d in ("2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30"):
            assert d in days
            assert days[d]["snapshot_population_count"] == 1
        assert days["2026-08-26"]["holdout_cohort"] == COHORT_TECHNICAL_SMOKE
        assert days["2026-08-27"]["holdout_cohort"] == COHORT_PROSPECTIVE

        reader = csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode()))
        assert set(reader.fieldnames or []) == set(COMPARISON_CSV_COLUMNS)
        csv_rows = list(reader)
        assert len(csv_rows) == 5 * PANEL_SIZE
        cohorts = {r["holdout_cohort"] for r in csv_rows}
        assert COHORT_TECHNICAL_SMOKE in cohorts
        assert COHORT_PROSPECTIVE in cohorts
        smoke = [r for r in csv_rows if r["scan_date"] == "2026-08-26"]
        assert all(r["holdout_cohort"] == COHORT_TECHNICAL_SMOKE for r in smoke)
        prosp = [r for r in csv_rows if r["scan_date"] == "2026-08-27"]
        assert all(r["holdout_cohort"] == COHORT_PROSPECTIVE for r in prosp)


def test_non_eligible_with_v2_key_included():
    row = _fixture_row(
        eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
        scan_date=date(2026, 8, 27),
    )
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["snapshot_population_count"] == 1
        assert manifest["summary"]["valid_v36_snapshots"] == 1
        assert len(list(csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode())))) == 19


def test_missing_v35_v31_do_not_drop_fixture():
    row = _fixture_row(omit_v35=True, omit_v31=True, scan_date=date(2026, 8, 28))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 28), date_to=date(2026, 8, 28)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["valid_v36_snapshots"] == 1
        assert manifest["summary"]["v35_missing_fixture_count"] == 1
        assert manifest["summary"]["v31_missing_fixture_count"] == 1
        rows = list(csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode())))
        assert len(rows) == 19
        assert all(r["v35_available"] in {"False", "false", ""} or r["v35_available"] == "False" for r in rows)
        assert all(r["v31_pairable"] in {"False", "false"} for r in rows)


def test_invalid_v36_marked_in_summary_not_comparison():
    _, v36 = _build_v35_v2()
    bad = copy.deepcopy(v36)
    bad["snapshot_version"] = "broken"
    row = _fixture_row(v36=bad, scan_date=date(2026, 8, 29))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 29), date_to=date(2026, 8, 29)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["snapshot_population_count"] == 1
        assert manifest["summary"]["invalid_v36_snapshots"] == 1
        assert manifest["summary"]["valid_v36_snapshots"] == 0
        assert manifest["summary"]["comparison_rows_count"] == 0
        assert manifest["summary"]["comparison_rows_complete"] is True
        assert manifest["summary"]["unique_fixture_summary_count"] == 1
        assert manifest["self_check"]["unique_fixture_summary_equals_population"] is True
        summary_rows = list(
            csv.DictReader(io.StringIO(zf.read("fixture_summary.csv").decode()))
        )
        assert len(summary_rows) == 1
        assert summary_rows[0]["v36_snapshot_status"] == "invalid"


def test_v31_pairable_requires_pre_match_evidence():
    row = _fixture_row(
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=_minimal_v31(
            snap_at="2026-08-27T08:00:00+00:00",
            pre_match_only=True,
            before_kickoff=False,
        ),
    )
    v36 = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    v36_item = v36["items"][0]
    result = resolve_v31_pairability(
        row=row,
        market_key=v36_item["market_key"],
        v36_item=v36_item,
        v31_snapshot=row.cecchino_output_json["purchasability_preview_v31"],
        v31_availability="available",
        v36_source_snapshot_at=v36.get("source_snapshot_at"),
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "v31_pre_match_not_verified"


def _aligned_v36_for_v31(*, snap_at: str = "2026-08-27T08:00:00+00:00"):
    v35, v36 = _build_v35_v2()
    v36["source_snapshot_at"] = snap_at
    for item in v36.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("input"), dict):
            item["input"]["execution_quote"] = 2.2
            item["input"]["probability_cecchino"] = 0.55
            item["input"]["fair_book_probability"] = round(1 / 2.2, 6)
    return v35, v36


def test_v31_pairable_true_when_same_timestamp():
    snap_at = "2026-08-27T08:00:00+00:00"
    v35, v36 = _aligned_v36_for_v31(snap_at=snap_at)
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=_minimal_v31(
            snap_at=snap_at,
            pre_match_only=True,
            before_kickoff=True,
            align_inputs=True,
        ),
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_by = {
        it["market_key"]: it
        for it in row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]["items"]
        if isinstance(it, dict)
    }
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_by[mk],
        v31_snapshot=row.cecchino_output_json["purchasability_preview_v31"],
        v31_availability="available",
        v36_source_snapshot_at=snap_at,
    )
    assert result["v31_pairable"] is True
    assert result["v31_alignment_reason"] is None


def test_v31_timestamp_mismatch():
    v35, v36 = _aligned_v36_for_v31(snap_at="2026-08-27T08:00:00+00:00")
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=_minimal_v31(snap_at="2026-08-27T09:00:00+00:00"),
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_item = next(
        it for it in v36["items"] if isinstance(it, dict) and it.get("market_key") == mk
    )
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_item,
        v31_snapshot=row.cecchino_output_json["purchasability_preview_v31"],
        v31_availability="available",
        v36_source_snapshot_at="2026-08-27T08:00:00+00:00",
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "snapshot_timestamp_mismatch"


def test_v31_post_kickoff_not_pairable():
    v35, v36 = _aligned_v36_for_v31(snap_at="2026-08-27T16:00:00+00:00")
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=_minimal_v31(snap_at="2026-08-27T16:00:00+00:00"),
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_item = next(
        it for it in v36["items"] if isinstance(it, dict) and it.get("market_key") == mk
    )
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_item,
        v31_snapshot=row.cecchino_output_json["purchasability_preview_v31"],
        v31_availability="available",
        v36_source_snapshot_at="2026-08-27T16:00:00+00:00",
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "v31_pre_match_not_verified"


def test_v31_missing_source_timestamp():
    v35, v36 = _aligned_v36_for_v31()
    v31 = _minimal_v31(snap_at="2026-08-27T08:00:00+00:00")
    v31["source_snapshot_at"] = None
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=v31,
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_item = next(
        it for it in v36["items"] if isinstance(it, dict) and it.get("market_key") == mk
    )
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_item,
        v31_snapshot=v31,
        v31_availability="available",
        v36_source_snapshot_at=v36.get("source_snapshot_at"),
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "v31_pre_match_not_verified"


def test_v31_provisional_not_strict_pairable():
    v35, v36 = _aligned_v36_for_v31(snap_at="2026-08-27T08:00:00+00:00")
    v31 = _minimal_v31(snap_at="2026-08-27T08:00:00+00:00")
    for item in v31["items"]:
        item["status"] = "score_provisional"
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=v31,
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_item = next(
        it for it in v36["items"] if isinstance(it, dict) and it.get("market_key") == mk
    )
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_item,
        v31_snapshot=v31,
        v31_availability="available",
        v36_source_snapshot_at="2026-08-27T08:00:00+00:00",
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "v31_provisional"
    assert result["v31_score"] is not None


def test_v31_input_context_mismatch():
    v35, v36 = _aligned_v36_for_v31(snap_at="2026-08-27T08:00:00+00:00")
    row = _fixture_row(
        v35=v35,
        v36=v36,
        scan_date=date(2026, 8, 27),
        kickoff=datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc),
        v31=_minimal_v31(
            snap_at="2026-08-27T08:00:00+00:00",
            align_inputs=False,
        ),
    )
    mk = PANEL_MARKET_KEYS[0]
    v36_item = next(
        it for it in v36["items"] if isinstance(it, dict) and it.get("market_key") == mk
    )
    result = resolve_v31_pairability(
        row=row,
        market_key=mk,
        v36_item=v36_item,
        v31_snapshot=row.cecchino_output_json["purchasability_preview_v31"],
        v31_availability="available",
        v36_source_snapshot_at="2026-08-27T08:00:00+00:00",
    )
    assert result["v31_pairable"] is False
    assert result["v31_alignment_reason"] == "input_context_mismatch"


def test_invalid_v35_no_top_no_strict_pair():
    v35, v36 = _build_v35_v2()
    bad_v35 = copy.deepcopy(v35)
    bad_v35["snapshot_version"] = "broken"
    row = _fixture_row(v35=bad_v35, v36=v36, scan_date=date(2026, 8, 28))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 28), date_to=date(2026, 8, 28)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["v35_invalid_fixture_count"] == 1
        assert manifest["summary"]["v35_missing_fixture_count"] == 0
        summary_rows = list(
            csv.DictReader(io.StringIO(zf.read("fixture_summary.csv").decode()))
        )
        assert summary_rows[0]["top_v35_market"] in {"", None}
        rows = list(csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode())))
        assert all(r["strict_paired"] in {"False", "false"} for r in rows)
        assert all(
            (r["v35_score_A"] in {"", None}) and (r["v35_status"] == "invalid")
            for r in rows
        )


def test_invalid_v31_no_top_no_pairability():
    v35, v36 = _build_v35_v2()
    bad_v31 = _minimal_v31()
    bad_v31["snapshot_version"] = "broken"
    row = _fixture_row(v35=v35, v36=v36, v31=bad_v31, scan_date=date(2026, 8, 28))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 28), date_to=date(2026, 8, 28)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["v31_invalid_fixture_count"] == 1
        summary_rows = list(
            csv.DictReader(io.StringIO(zf.read("fixture_summary.csv").decode()))
        )
        assert summary_rows[0]["top_v31_market"] in {"", None}
        rows = list(csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode())))
        assert all(r["v31_pairable"] in {"False", "false"} for r in rows)
        assert all(r["v31_alignment_reason"] == "v31_invalid" for r in rows)


def test_manifest_partition_available_missing_invalid():
    v35, v36 = _build_v35_v2()
    bad_v35 = copy.deepcopy(v35)
    bad_v35["snapshot_version"] = "broken"
    bad_v31 = _minimal_v31()
    bad_v31["snapshot_version"] = "broken"
    rows = [
        _fixture_row(fid=1, provider_id=1, scan_date=date(2026, 8, 26)),
        _fixture_row(
            fid=2, provider_id=2, scan_date=date(2026, 8, 26), omit_v35=True, omit_v31=True
        ),
        _fixture_row(
            fid=3,
            provider_id=3,
            scan_date=date(2026, 8, 26),
            v35=bad_v35,
            v36=v36,
            v31=bad_v31,
        ),
    ]
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=rows,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 26), date_to=date(2026, 8, 30)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        s = manifest["summary"]
        assert s["snapshot_population_count"] == 3
        assert (
            s["v35_available_fixture_count"]
            + s["v35_missing_fixture_count"]
            + s["v35_invalid_fixture_count"]
            == 3
        )
        assert (
            s["v31_available_fixture_count"]
            + s["v31_missing_fixture_count"]
            + s["v31_invalid_fixture_count"]
            == 3
        )
        assert s["v35_available_fixture_count"] == 1
        assert s["v35_missing_fixture_count"] == 1
        assert s["v35_invalid_fixture_count"] == 1
        assert s["v31_available_fixture_count"] == 1
        assert s["v31_missing_fixture_count"] == 1
        assert s["v31_invalid_fixture_count"] == 1
        sc = manifest["self_check"]
        assert sc["v35_population_partition_complete"] is True
        assert sc["v31_population_partition_complete"] is True
        days = manifest["days"]
        for d in ("2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30"):
            assert d in days
        assert days["2026-08-27"]["snapshot_population_count"] == 0
        assert days["2026-08-27"]["holdout_cohort"] == COHORT_PROSPECTIVE


def test_valid_v36_exact_panel_rows():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["self_check"]["panel_rows_exact_per_valid_v36"] is True
        rows = list(csv.DictReader(io.StringIO(zf.read("comparison_rows.csv").decode())))
        assert len(rows) == 19
        assert {r["market_key"] for r in rows} == set(PANEL_MARKET_KEYS)


def test_offline_comparison_csv_contract_fields():
    required = {
        "scan_date",
        "today_fixture_id",
        "provider_fixture_id",
        "holdout_cohort",
        "match_status",
        "current_eligibility_status",
        "market_key",
        "market_family",
        "execution_quote",
        "probability_cecchino",
        "fair_book_probability",
        "EV",
        "outcome",
        "profit_1u",
        "v36_score",
        "v36_raw_score",
        "v36_class",
        "V",
        "D",
        "R",
        "S",
        "Q",
        "VALUE_CORE",
        "ACQUISITION_CORE",
        "structural_factor",
        "quality_factor",
        "adjusted_confidence",
        "v36_source_snapshot_at",
        "v36_formula_freeze_sha256",
        "v35_score_A",
        "v35_raw_score_A",
        "v35_class_A",
        "v35_source_snapshot_at",
        "v35_available",
        "v35_status",
        "strict_paired",
        "v31_score",
        "v31_raw_score",
        "v31_class",
        "v31_candidate_version",
        "v31_source_snapshot_at",
        "v31_available",
        "v31_status",
        "v31_pairable",
        "v31_alignment_reason",
    }
    assert required.issubset(set(COMPARISON_CSV_COLUMNS))


def test_zero_recompute():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch",
        side_effect=AssertionError("v2_recompute_forbidden"),
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["recompute_used"] is False
        assert manifest["summary"]["valid_v36_snapshots"] == 1


def test_engine_v36_patched_bundle_still_works():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_item",
        side_effect=AssertionError("v36_engine_forbidden"),
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert json.loads(zf.read("manifest.json"))["recompute_used"] is False


def test_engine_v35_patched_bundle_still_works():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_candidate."
        "calculate_purchasability_v35_batch",
        side_effect=AssertionError("v35_engine_forbidden"),
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert json.loads(zf.read("manifest.json"))["recompute_used"] is False


def test_engine_v31_patched_bundle_still_works():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v31_candidate."
        "calculate_purchasability_v31_batch",
        side_effect=AssertionError("v31_engine_forbidden"),
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 27), date_to=date(2026, 8, 27)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert json.loads(zf.read("manifest.json"))["recompute_used"] is False


def test_formula_sha_and_route():
    rows = [
        _fixture_row(fid=i, provider_id=1507100 + i, scan_date=date(2026, 8, d))
        for i, d in enumerate(range(26, 31), start=1)
    ]
    db = _mock_db(rows)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    resp = client.get(
        "/api/cecchino/today/purchasability-v36-evaluation-bundle"
        "?date_from=2026-08-26&date_to=2026-08-30"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    cd = resp.headers.get("content-disposition", "")
    assert "cecchino-v36-analysis-2026-08-26_2026-08-30.zip" in cd
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert (
            manifest["formula_freeze_sha256_expected"]
            == "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
        )
        assert EXPECTED_FORMULA_FREEZE_SHA256 == (
            "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
        )
        assert PRIMARY_DIAGNOSTIC_COHORT == COHORT_PROSPECTIVE


def test_pending_fixture_still_exported():
    row = _fixture_row(
        scan_date=date(2026, 8, 30),
        match_display_status=MATCH_UPCOMING,
        goals_home=None,
        goals_away=None,
    )
    with patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v36_evaluation_bundle."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        zip_bytes, _ = build_v36_evaluation_bundle_zip(
            _mock_db([]), date_from=date(2026, 8, 30), date_to=date(2026, 8, 30)
        )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["summary"]["pending_fixture_count"] == 1
        assert manifest["summary"]["comparison_rows_count"] == 19
