"""Test export analysis Acquistabilità V3.5 — frozen + post-match + evaluation read-only."""

from __future__ import annotations

import copy
import io
import json
import os
import time
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_FINISHED
from app.routes.cecchino_today import router
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION,
    PURCHASABILITY_V35_ANALYSIS_MANIFEST_CONTRACT_VERSION,
    PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    compute_profit_1u,
    evaluate_v35_market_outcome,
)
from app.services.cecchino.cecchino_purchasability_v35_analysis_export import (
    build_purchasability_v35_analysis_export,
)
from app.services.cecchino.cecchino_purchasability_v35_audit_export import (
    build_purchasability_v35_audit_export,
    get_purchasability_v35_audit_export,
)
from app.services.cecchino.cecchino_purchasability_v35_range_analysis_export import (
    CSV_COLUMNS,
    V35AnalysisRangeError,
    build_range_purchasability_v35_analysis_zip,
    validate_analysis_date_range,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_today_constants import DEFAULT_RETENTION_DAYS

SNAP_AT = "2026-08-20T10:00:00+00:00"
KICKOFF = "2026-08-20T15:00:00+00:00"

EXPECTED_FT21_HT10 = {
    SEL_HOME: EVAL_WON,
    SEL_DRAW: EVAL_LOST,
    SEL_AWAY: EVAL_LOST,
    SEL_HOME_PT: EVAL_WON,
    SEL_DRAW_PT: EVAL_LOST,
    SEL_AWAY_PT: EVAL_LOST,
    SEL_ONE_X: EVAL_WON,
    SEL_X_TWO: EVAL_LOST,
    SEL_ONE_TWO: EVAL_WON,
    SEL_OVER_1_5: EVAL_WON,
    SEL_OVER_2_5: EVAL_WON,
    SEL_OVER_3_5: EVAL_LOST,
    SEL_UNDER_1_5: EVAL_LOST,
    SEL_UNDER_2_5: EVAL_LOST,
    SEL_UNDER_3_5: EVAL_WON,
    SEL_OVER_PT_0_5: EVAL_WON,
    SEL_OVER_PT_1_5: EVAL_LOST,
    SEL_UNDER_PT_0_5: EVAL_LOST,
    SEL_UNDER_PT_1_5: EVAL_WON,
}


def _row(mk: str, *, quota: float = 2.2, rating: float = 60, prob: float = 0.55) -> dict:
    return {
        "market_key": mk,
        "quota_book": quota,
        "prob_cecchino": prob,
        "rating": rating,
        "book_source": "betfair_raw_match_winner",
        "book_fallback_used": False,
    }


def _build_v35_snapshot(*, quota: float = 2.2) -> dict:
    rows = [_row(mk, quota=quota) for mk in PANEL_MARKET_KEYS]
    output: dict = {}
    attach_purchasability_preview_v35_to_output(
        cecchino_output=output,
        kpi_panel={"rows": rows},
        fixture_meta={
            "today_fixture_id": 1,
            "provider_fixture_id": 555,
            "snapshot_at": SNAP_AT,
            "kickoff": KICKOFF,
        },
        snapshot_info={
            "snapshot_at": SNAP_AT,
            "snapshot_timestamp_verified": True,
        },
    )
    return output["purchasability_preview_v35"]


def _fixture_row(
    *,
    fid: int = 7,
    provider_id: int = 555,
    v35_snapshot: dict | None = None,
    scan_date: date | None = None,
    match_display_status: str = MATCH_FINISHED,
    ht_home: int | None = 1,
    ht_away: int | None = 0,
    ft_home: int | None = 2,
    ft_away: int | None = 1,
) -> SimpleNamespace:
    snap = v35_snapshot if v35_snapshot is not None else _build_v35_snapshot()
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=provider_id,
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc),
        scan_date=scan_date or date(2026, 8, 20),
        provider_season=2026,
        country_name="Italy",
        league_name="Serie A",
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        fixture_status="FT",
        match_display_status=match_display_status,
        goals_home=ft_home,
        goals_away=ft_away,
        score_halftime_home=ht_home,
        score_halftime_away=ht_away,
        score_fulltime_home=ft_home,
        score_fulltime_away=ft_away,
        kpi_panel_json={"rows": [_row(mk) for mk in PANEL_MARKET_KEYS]},
        cecchino_output_json={"purchasability_preview_v35": snap},
    )


@pytest.mark.parametrize("market_key,expected", list(EXPECTED_FT21_HT10.items()))
def test_19_markets_settlement_ft21_ht10(market_key: str, expected: str):
    row = _fixture_row()
    outcome = evaluate_v35_market_outcome(market_key, row)
    assert outcome["outcome"] == expected


def test_profit_formula_won_lost():
    snap = _build_v35_snapshot()
    home_item = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    home_item["status"] = "score"
    home_item["input"]["execution_quote"] = 2.20
    home_item["input"]["execution_quote_real"] = True

    assert compute_profit_1u(home_item, EVAL_WON) == pytest.approx(1.20)
    assert compute_profit_1u(home_item, EVAL_LOST) == -1.0


def test_profit_formula_null_cases():
    snap = _build_v35_snapshot()
    item = next(it for it in snap["items"] if it["market_key"] == SEL_HOME)
    item["status"] = "gate_failed"
    item["input"]["execution_quote"] = 2.20
    item["input"]["execution_quote_real"] = True
    assert compute_profit_1u(item, EVAL_WON) is None

    item["status"] = "score"
    item["input"]["execution_quote_real"] = False
    assert compute_profit_1u(item, EVAL_WON) is None

    item["input"]["execution_quote_real"] = True
    assert compute_profit_1u(item, EVAL_PENDING) is None


def test_candidate_top_picks_divergent():
    snap = _build_v35_snapshot()
    by_mk = {it["market_key"]: it for it in snap["items"]}
    for mk in by_mk:
        by_mk[mk]["status"] = "score"
        for ck in ("A", "B", "C", "D"):
            by_mk[mk]["candidates"][ck] = {
                "score": 50,
                "raw_score": 50.0,
                "class": "Media",
            }
    by_mk[SEL_HOME]["candidates"]["A"]["score"] = 80
    by_mk[SEL_OVER_2_5]["candidates"]["B"]["score"] = 75
    by_mk[SEL_HOME]["candidates"]["C"]["score"] = 70
    by_mk[SEL_UNDER_3_5]["candidates"]["D"]["score"] = 85

    row = _fixture_row(v35_snapshot=snap)
    analysis = build_purchasability_v35_analysis_export(row, snap)
    picks = analysis["candidate_top_picks"]
    assert picks["A"]["market_key"] == SEL_HOME
    assert picks["B"]["market_key"] == SEL_OVER_2_5
    assert picks["C"]["market_key"] == SEL_HOME
    assert picks["D"]["market_key"] == SEL_UNDER_3_5


def test_snapshot_immutability_after_analysis():
    snap = _build_v35_snapshot()
    snap_copy = copy.deepcopy(snap)
    engine_before = snap["engine_payload_sha256"]
    input_before = snap["input_fingerprint_sha256"]
    home_before = snap["items"][0]["candidates"]["A"]["score"]

    row = _fixture_row(v35_snapshot=snap, ft_home=2, ft_away=2)
    build_purchasability_v35_analysis_export(row, snap)

    assert snap == snap_copy
    assert snap["engine_payload_sha256"] == engine_before
    assert snap["input_fingerprint_sha256"] == input_before
    assert snap["items"][0]["candidates"]["A"]["score"] == home_before


def test_hash_proof_unchanged_in_export():
    snap = _build_v35_snapshot()
    row = _fixture_row(v35_snapshot=snap)
    analysis = build_purchasability_v35_analysis_export(row, snap)
    integrity = analysis["snapshot_integrity"]
    assert integrity["engine_payload_sha256"] == snap["engine_payload_sha256"]
    assert integrity["input_fingerprint_sha256"] == snap["input_fingerprint_sha256"]


def test_pre_match_no_post_match_leakage():
    row = _fixture_row()
    snap = row.cecchino_output_json["purchasability_preview_v35"]
    analysis = build_purchasability_v35_analysis_export(row, snap)
    pre = json.dumps(analysis["pre_match"])
    assert "profit_1u" not in pre
    assert "outcome" not in pre
    assert analysis["post_match"]["fulltime"]["home"] == 2


def test_range_zip_structure():
    row = _fixture_row()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    zip_bytes, filename = build_range_purchasability_v35_analysis_zip(
        db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
    )
    assert filename == "purchasability-v35-analysis-2026-08-20_2026-08-20.zip"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "analysis_rows.csv" in names
        assert any(n.startswith("days/2026-08-20/") for n in names)
        manifest = json.loads(zf.read("manifest.json"))
        csv_text = zf.read("analysis_rows.csv").decode("utf-8")
    assert manifest["contract_version"] == PURCHASABILITY_V35_ANALYSIS_MANIFEST_CONTRACT_VERSION
    assert manifest["summary"]["valid_v35_snapshots"] == 1
    assert csv_text.count("\n") >= 20


def test_manifest_analysis_ready_semantics():
    finished = _fixture_row(match_display_status=MATCH_FINISHED)
    pending = _fixture_row(
        fid=8,
        provider_id=556,
        match_display_status="upcoming",
        ft_home=None,
        ft_away=None,
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [finished, pending]
    zip_bytes, _ = build_range_purchasability_v35_analysis_zip(
        db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["summary"]["analysis_ready"] is False


def test_csv_row_count():
    rows = [_fixture_row(fid=i, provider_id=500 + i) for i in range(3)]
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    zip_bytes, _ = build_range_purchasability_v35_analysis_zip(
        db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 26)
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_text = zf.read("analysis_rows.csv").decode("utf-8")
    data_lines = [ln for ln in csv_text.strip().split("\n") if ln and not ln.startswith("scan_date")]
    assert len(data_lines) == 3 * 19


def test_csv_header_complete():
    assert "execution_quote" in CSV_COLUMNS
    assert "score_A" in CSV_COLUMNS
    assert "profit_1u" in CSV_COLUMNS
    assert len(CSV_COLUMNS) >= 40


def test_analysis_api_route_static_before_dynamic():
    row = _fixture_row()
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override_db():
        db = MagicMock()
        db.scalars.return_value.all.return_value = [row]
        yield db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    resp = client.get(
        "/api/cecchino/today/purchasability-v35-analysis-export",
        params={"date_from": "2026-08-20", "date_to": "2026-08-26"},
    )
    assert resp.status_code == 200
    assert "purchasability-v35-analysis-2026-08-20_2026-08-26.zip" in resp.headers["content-disposition"]


def test_audit_export_unchanged():
    row = _fixture_row()
    snap = row.cecchino_output_json["purchasability_preview_v35"]
    audit = build_purchasability_v35_audit_export(row, snap)
    assert audit["contract_version"] == PURCHASABILITY_V35_AUDIT_EXPORT_CONTRACT_VERSION
    assert audit["pre_match_only"] is True
    assert "post_match" not in audit


def test_no_db_writes_during_analysis_export():
    row = _fixture_row()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    build_range_purchasability_v35_analysis_zip(
        db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
    )
    db.commit.assert_not_called()
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_no_v35_recalculation_on_analysis():
    row = _fixture_row()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [row]
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_candidate.calculate_purchasability_v35_batch",
        side_effect=AssertionError("batch must not run on analysis export"),
    ):
        build_range_purchasability_v35_analysis_zip(
            db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
        )
    db = MagicMock()
    db.get.return_value = row
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_candidate.calculate_purchasability_v35_batch",
        side_effect=AssertionError("batch must not run on audit GET"),
    ):
        payload, _ = get_purchasability_v35_audit_export(db, 7)
    assert payload is not None


def test_validate_date_range_errors():
    with pytest.raises(V35AnalysisRangeError):
        validate_analysis_date_range(date(2026, 8, 26), date(2026, 8, 20))
    with pytest.raises(V35AnalysisRangeError):
        validate_analysis_date_range(date(2026, 1, 1), date(2026, 2, 15))


def test_default_retention_days_is_14():
    assert DEFAULT_RETENTION_DAYS == 14


def test_performance_50x19_benchmark(capsys):
    fixtures = [
        _fixture_row(fid=i, provider_id=1000 + i, scan_date=date(2026, 8, 20))
        for i in range(50)
    ]
    db = MagicMock()
    db.scalars.return_value.all.return_value = fixtures
    t0 = time.perf_counter()
    zip_bytes, _ = build_range_purchasability_v35_analysis_zip(
        db, date_from=date(2026, 8, 20), date_to=date(2026, 8, 20)
    )
    elapsed = time.perf_counter() - t0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_lines = zf.read("analysis_rows.csv").decode("utf-8").count("\n")
    print(f"BENCHMARK_50x19 elapsed_sec={elapsed:.3f} csv_lines={csv_lines} zip_bytes={len(zip_bytes)}")
    assert len(zip_bytes) > 0


def test_analysis_contract_version():
    row = _fixture_row()
    snap = row.cecchino_output_json["purchasability_preview_v35"]
    analysis = build_purchasability_v35_analysis_export(row, snap)
    assert analysis["contract_version"] == PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION


def test_not_evaluable_cancelled():
    row = _fixture_row(match_display_status="cancelled")
    outcome = evaluate_v35_market_outcome(SEL_HOME, row)
    assert outcome["outcome"] == EVAL_NOT_EVALUABLE


def test_pt_market_live_with_ht():
    row = _fixture_row(
        match_display_status="live",
        ft_home=None,
        ft_away=None,
        ht_home=1,
        ht_away=0,
    )
    outcome = evaluate_v35_market_outcome(SEL_HOME_PT, row)
    assert outcome["outcome"] == EVAL_WON
