"""Test export analysis Structural V2 — persisted-only + holdout diagnostics."""

from __future__ import annotations

import copy
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
)
from app.routes.cecchino_today import router
from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_ANALYSIS_MANIFEST_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    attach_purchasability_preview_v35_to_output,
    engine_payload_sha256_v35,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_analysis_export import (
    COHORT_PROSPECTIVE,
    COHORT_TECHNICAL_SMOKE,
    PRIMARY_DIAGNOSTIC_COHORT,
    build_purchasability_v35_v2_analysis_export,
    holdout_cohort_for_scan_date,
    holdout_market_family,
    resolve_analysis_ev,
    resolve_paired_v1_a,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_holdout_diagnostics import (
    MIN_N_FOR_TERTILES,
    build_holdout_diagnostics,
    build_quantile_report,
    build_ranking_quality,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export import (
    CSV_COLUMNS,
    V35V2AnalysisRangeError,
    _count_current_eligible_without_v2_key,
    _load_v2_snapshot_population_range,
    _strict_paired_market_items,
    _top_v1_strict_paired_from_analysis,
    _top_v2_strict_paired_from_analysis,
    build_range_purchasability_v35_v2_analysis_manifest_and_files,
    build_range_purchasability_v35_v2_analysis_zip,
    validate_v2_analysis_date_range,
)
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    compute_profit_1u_from_quote,
)
from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    SNAPSHOT_OUTPUT_KEY,
    attach_purchasability_preview_v35_v2_to_output,
)
from app.services.cecchino.cecchino_selection_keys import SEL_HOME, SEL_OVER_2_5

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


def _build_paired_snapshots() -> tuple[dict, dict]:
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


def _fixture_row(
    *,
    fid: int = 24891,
    provider_id: int = 1507044,
    scan_date: date | None = None,
    v1: dict | None = None,
    v2: dict | None = None,
    eligibility_status: str = ELIGIBILITY_ELIGIBLE,
    match_display_status: str = MATCH_FINISHED,
    goals_home: int | None = 2,
    goals_away: int | None = 1,
    omit_v2_key: bool = False,
) -> SimpleNamespace:
    if omit_v2_key:
        if v1 is None:
            built_v1, _ = _build_paired_snapshots()
            v1 = built_v1
        output = {"purchasability_preview_v35": v1}
    else:
        if v1 is None or v2 is None:
            built_v1, built_v2 = _build_paired_snapshots()
            v1 = v1 or built_v1
            v2 = v2 or built_v2
        output = {
            "purchasability_preview_v35": v1,
            SNAPSHOT_OUTPUT_KEY: v2,
        }
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=provider_id,
        home_team_name="Home FC",
        away_team_name="Away FC",
        kickoff=datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
        scan_date=scan_date or date(2026, 8, 26),
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


def _mock_db_population(rows: list) -> MagicMock:
    """Population loader + eligible-without-v2 diagnostic both use db.scalars."""
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows
    return db


def test_formula_freeze_sha_intact():
    _, v2 = _build_paired_snapshots()
    assert v2["formula_freeze_sha256"] == EXPECTED_FORMULA_FREEZE_SHA256
    assert EXPECTED_FORMULA_FREEZE_SHA256 == (
        "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
    )


def test_cohort_labels():
    assert holdout_cohort_for_scan_date(date(2026, 8, 26)) == COHORT_TECHNICAL_SMOKE
    assert holdout_cohort_for_scan_date(date(2026, 8, 27)) == COHORT_PROSPECTIVE
    assert PRIMARY_DIAGNOSTIC_COHORT == COHORT_PROSPECTIVE


def test_holdout_market_families():
    assert holdout_market_family(SEL_HOME) == "FT_1X2"
    assert holdout_market_family(SEL_OVER_2_5) == "FT_Goals"


def test_ev_frozen_gate_primary():
    item = {
        "gate": {"expected_value": 0.12},
        "input": {"probability_cecchino": 0.5, "execution_quote": 2.0},
    }
    ev = resolve_analysis_ev(item)
    assert ev["EV"] == pytest.approx(0.12)
    assert ev["ev_source"] == "frozen_gate"


def test_ev_derived_fallback_only_when_absent():
    item = {
        "gate": {},
        "input": {"probability_cecchino": 0.5, "execution_quote": 2.2},
    }
    ev = resolve_analysis_ev(item)
    assert ev["ev_source"] == "derived_analysis_fallback"
    assert ev["EV"] == pytest.approx(0.5 * 2.2 - 1.0)


def test_persisted_only_no_v2_recompute():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch",
        side_effect=AssertionError("v2_recompute_forbidden"),
    ):
        analysis = build_purchasability_v35_v2_analysis_export(row, snap)
    assert analysis["snapshot_integrity"]["formula_freeze_ok"] is True
    assert "evaluation" in next(iter(analysis["markets"].values()))
    # outcome is only on evaluation, not in pre_match markets
    for mk, item in analysis["pre_match"]["markets"].items():
        assert "evaluation" not in item
        assert "outcome" not in item


def test_no_outcome_leakage_in_pre_match():
    row = _fixture_row()
    snap = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    analysis = build_purchasability_v35_v2_analysis_export(row, snap)
    dumped = json.dumps(analysis["pre_match"])
    assert '"outcome"' not in dumped
    assert '"profit_1u"' not in dumped


def test_paired_v1_v2_join():
    row = _fixture_row()
    snap = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    analysis = build_purchasability_v35_v2_analysis_export(row, snap)
    paired_count = 0
    strict_count = 0
    for mk, item in analysis["markets"].items():
        if item.get("status") != "score":
            continue
        paired = item.get("paired_v1")
        if paired:
            paired_count += 1
            assert paired["pair_key"] == f"{row.id}::{mk}"
            assert paired["paired"] is True
            assert "v1_score_A" in paired
            assert "v1_raw_score_A" in paired
            assert "v1_class_A" in paired
            assert "strict_paired" in paired
            assert "pair_input_alignment" in paired
            if paired.get("strict_paired") is True:
                strict_count += 1
                assert paired.get("pair_alignment_reason") is None
    assert paired_count >= 1
    assert strict_count >= 1


def _rehash_v1(v1: dict) -> dict:
    v1 = copy.deepcopy(v1)
    v1["engine_payload_sha256"] = engine_payload_sha256_v35(v1)
    return v1


def _first_scored_market_key(snap: dict) -> str:
    for item in snap.get("items") or []:
        if isinstance(item, dict) and item.get("status") == "score":
            return str(item["market_key"])
    raise AssertionError("no scored market")


def test_strict_paired_identical_common_inputs():
    row = _fixture_row()
    snap = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    mk = _first_scored_market_key(snap)
    v2_item = next(i for i in snap["items"] if i.get("market_key") == mk)
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired is not None
    assert paired["paired"] is True
    assert paired["strict_paired"] is True
    assert paired["pair_alignment_reason"] is None
    assert all(paired["pair_input_alignment"].values())


def test_soft_pair_candidate_a_missing():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    v1 = copy.deepcopy(row.cecchino_output_json["purchasability_preview_v35"])
    mk = _first_scored_market_key(snap)
    for item in v1["items"]:
        if item.get("market_key") == mk:
            item["candidates"] = {}
            break
    row.cecchino_output_json["purchasability_preview_v35"] = _rehash_v1(v1)
    v2_item = next(i for i in snap["items"] if i.get("market_key") == mk)
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired is not None
    assert paired["paired"] is True
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "v1_score_missing"


def test_soft_pair_timestamp_mismatch():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    snap["source_snapshot_at"] = "2026-08-26T09:00:00+00:00"
    mk = _first_scored_market_key(snap)
    v2_item = next(i for i in snap["items"] if i.get("market_key") == mk)
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired is not None
    assert paired["paired"] is True
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "snapshot_timestamp_mismatch"


def test_soft_pair_quote_mismatch_is_input_context():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    mk = _first_scored_market_key(snap)
    v2_item = copy.deepcopy(next(i for i in snap["items"] if i.get("market_key") == mk))
    v2_item["input"] = dict(v2_item.get("input") or {})
    v2_item["input"]["execution_quote"] = float(v2_item["input"]["execution_quote"]) + 0.05
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired is not None
    assert paired["paired"] is True
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "input_context_mismatch"
    assert "execution_quote" in paired["input_mismatch_fields"]


def test_soft_pair_p_cec_mismatch():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    mk = _first_scored_market_key(snap)
    v2_item = copy.deepcopy(next(i for i in snap["items"] if i.get("market_key") == mk))
    v2_item["input"] = dict(v2_item.get("input") or {})
    v2_item["input"]["probability_cecchino"] = 0.11
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "input_context_mismatch"
    assert "probability_cecchino" in paired["input_mismatch_fields"]


def test_soft_pair_p_fair_mismatch():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    mk = _first_scored_market_key(snap)
    v2_item = copy.deepcopy(next(i for i in snap["items"] if i.get("market_key") == mk))
    v2_item["input"] = dict(v2_item.get("input") or {})
    v2_item["input"]["fair_book_probability"] = 0.22
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "input_context_mismatch"
    assert "fair_book_probability" in paired["input_mismatch_fields"]


def test_soft_pair_v1_not_scored():
    row = _fixture_row()
    snap = copy.deepcopy(row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY])
    v1 = copy.deepcopy(row.cecchino_output_json["purchasability_preview_v35"])
    mk = _first_scored_market_key(snap)
    for item in v1["items"]:
        if item.get("market_key") == mk:
            item["status"] = "gate_failed"
            break
    row.cecchino_output_json["purchasability_preview_v35"] = _rehash_v1(v1)
    v2_item = next(i for i in snap["items"] if i.get("market_key") == mk)
    paired = resolve_paired_v1_a(
        row=row, market_key=mk, v2_snapshot=snap, v2_item=v2_item
    )
    assert paired["paired"] is True
    assert paired["strict_paired"] is False
    assert paired["pair_alignment_reason"] == "v1_not_scored"


def test_auc_strict_paired_identical_pair_keys():
    rows = []
    for i in range(12):
        rows.append(
            {
                "pair_key": f"f{i}::home",
                "strict_paired": True,
                "paired": True,
                "outcome": EVAL_WON if i % 2 == 0 else EVAL_LOST,
                "v2_raw_score": float(10 + i),
                "v1_raw_score_A": float(5 + i),
                "v1_score_A": float(5 + i),
            }
        )
    # Extra non-strict row must not enter primary AUC set
    rows.append(
        {
            "pair_key": "noise::home",
            "strict_paired": False,
            "paired": True,
            "outcome": EVAL_WON,
            "v2_raw_score": 99.0,
            "v1_raw_score_A": 99.0,
            "v1_score_A": 99.0,
        }
    )
    rq = build_ranking_quality(rows)
    assert rq["n_strict_paired_settled"] == 12
    keys = set(rq["strict_paired_pair_keys"])
    assert keys == {f"f{i}::home" for i in range(12)}
    assert "noise::home" not in keys
    assert rq["roc_auc_v2_strict_paired"] is not None
    assert rq["roc_auc_v1_A_strict_paired"] is not None
    assert rq["delta_auc_v2_minus_v1_strict_paired"] is not None
    assert rq["roc_auc_v2_all_settled"] == rq["roc_auc_v2_raw_score"]


def test_top_strict_paired_same_market_universe():
    row = _fixture_row(scan_date=date(2026, 8, 27))
    snap = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    analysis = build_purchasability_v35_v2_analysis_export(row, snap)
    universe = {mk for mk, _, _ in _strict_paired_market_items(analysis)}
    assert len(universe) >= 1
    top_v2 = _top_v2_strict_paired_from_analysis(analysis)
    top_v1 = _top_v1_strict_paired_from_analysis(analysis)
    assert top_v2 is not None and top_v1 is not None
    assert top_v2["market_key"] in universe
    assert top_v1["market_key"] in universe
    assert top_v2["selection_basis"] == "strict_paired_v2_raw_score"
    assert top_v1["selection_basis"] == "strict_paired_v1_A_score"


def test_model_specific_execution_quote_profit():
    assert compute_profit_1u_from_quote(
        execution_quote=2.5, execution_quote_real=True, outcome=EVAL_WON
    ) == pytest.approx(1.5)
    assert compute_profit_1u_from_quote(
        execution_quote=2.5, execution_quote_real=True, outcome=EVAL_LOST
    ) == -1.0
    # Distinct model quotes produce distinct profits even with same outcome
    p_v1 = compute_profit_1u_from_quote(
        execution_quote=2.0, execution_quote_real=True, outcome=EVAL_WON
    )
    p_v2 = compute_profit_1u_from_quote(
        execution_quote=3.0, execution_quote_real=True, outcome=EVAL_WON
    )
    assert p_v1 != p_v2


def test_top_market_selected_before_outcome():
    row = _fixture_row()
    snap = row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY]
    analysis = build_purchasability_v35_v2_analysis_export(row, snap)
    top = analysis["top_v2_market"]
    assert top is not None
    assert top["selection_basis"] == "pre_match_status_score_raw_score"
    assert top["market_key"] in PANEL_MARKET_KEYS
    assert "outcome" in top


def test_quantiles_mutually_exclusive_and_top10_cutoff():
    rows = []
    for i in range(40):
        rows.append(
            {
                "today_fixture_id": i,
                "market_key": PANEL_MARKET_KEYS[i % len(PANEL_MARKET_KEYS)],
                "v2_raw_score": float(i),
                "v2_score": i,
                "execution_quote": 2.0,
                "outcome": "won" if i % 2 == 0 else "lost",
                "profit_1u": 1.0 if i % 2 == 0 else -1.0,
            }
        )
    # Map to EVAL constants used in diagnostics
    from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON

    for r in rows:
        r["outcome"] = EVAL_WON if r["outcome"] == "won" else EVAL_LOST

    rep = build_quantile_report(rows)
    assert rep["status"] == "ok"
    ids = set()
    for key in ("Q1_bottom_25", "Q2_25_50", "Q3_50_75", "Q4_top_25"):
        # Reconstruct exclusivity via n sum
        assert rep[key]["n"] >= 0
        ids.add(key)
    assert sum(rep[k]["n"] for k in ids) == 40
    top = rep["top_10_pct"]
    assert top["requested_fraction"] == 0.10
    assert top["n_selected"] == 4
    assert top["cutoff_raw_score"] is not None
    assert top["n"] == 4


def test_odds_bucket_insufficient_sample():
    rows = [
        {
            "today_fixture_id": i,
            "market_key": SEL_HOME,
            "v2_raw_score": float(i),
            "v2_score": i,
            "execution_quote": 1.6,
            "outcome": "won",
            "profit_1u": 0.6,
            "holdout_cohort": COHORT_PROSPECTIVE,
            "holdout_market_family": "FT_1X2",
            "probability_cecchino": 0.5,
            "fair_book_probability": 0.45,
            "EV": 0.1,
            "V": 50,
            "D": 50,
            "R": 50,
            "S": 50,
            "Q": 50,
            "paired": False,
        }
        for i in range(5)
    ]
    from app.models.cecchino_signal_activation import EVAL_WON

    for r in rows:
        r["outcome"] = EVAL_WON
    diag = build_holdout_diagnostics(rows)
    odds = diag["all_cohorts"]["odds_controlled"]["1.50_1.79"]
    assert odds["status"] == "insufficient_sample"
    assert odds["n"] < MIN_N_FOR_TERTILES


def test_range_zip_and_route():
    v1, v2 = _build_paired_snapshots()
    row = _fixture_row(v1=v1, v2=v2, scan_date=date(2026, 8, 26))

    db = _mock_db_population([row])

    zip_bytes, filename = build_range_purchasability_v35_v2_analysis_zip(
        db, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
    )
    assert filename.startswith("purchasability-v35-v2-analysis-")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "analysis_rows.csv" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert (
            manifest["contract_version"]
            == PURCHASABILITY_V35_V2_ANALYSIS_MANIFEST_CONTRACT_VERSION
        )
        assert manifest["contract_version"].endswith("_analysis_manifest_v2")
        assert manifest["PRIMARY_DIAGNOSTIC_COHORT"] == COHORT_PROSPECTIVE
        assert "holdout_diagnostics" in manifest
        assert (
            manifest["formula_freeze_sha256_expected"] == EXPECTED_FORMULA_FREEZE_SHA256
        )
        summary = manifest["summary"]
        assert summary["population_inclusion_basis"] == "persisted_v2_snapshot_key"
        assert summary["snapshot_population_count"] == 1
        assert summary["valid_v2_snapshots"] == 1
        assert summary["invalid_v2_snapshots"] == 0
        assert summary["analysis_included_count"] == 1
        assert summary["snapshot_population_count"] == (
            summary["valid_v2_snapshots"] + summary["invalid_v2_snapshots"]
        )
        assert summary["eligible_fixtures"] == 1
        assert summary["valid_current_eligible_count"] == 1
        # eligible_fixtures is metadata count within population, not alias of pop size
        assert "current_eligibility_status" in manifest["fixtures"][0]
        csv_text = zf.read("analysis_rows.csv").decode("utf-8")
        header = csv_text.splitlines()[0].split(",")
        for col in (
            "v2_raw_score",
            "EV",
            "ev_source",
            "R",
            "base_rate_reliability",
            "v1_score_A",
            "strict_paired",
            "pair_alignment_reason",
            "v1_execution_quote",
            "v2_execution_quote",
            "holdout_cohort",
            "current_eligibility_status",
            "formula_freeze_sha256",
        ):
            assert col in header
        assert set(CSV_COLUMNS) == set(header)
        smoke = manifest["holdout_diagnostics"]["technical_smoke_cohort"]
        assert "paired_count" in smoke
        assert "strict_paired_count" in smoke
        assert "pair_alignment_failures" in smoke
        rq = smoke["ranking_quality"]
        assert "roc_auc_v2_strict_paired" in rq
        assert "n_strict_paired_settled" in rq
        assert "top_v2_all_markets_per_fixture" in smoke
        assert "top_v2_strict_paired_per_fixture" in smoke
        assert "top_v1_strict_paired_per_fixture" in smoke
        assert "paired_top_delta" in smoke

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    resp = client.get(
        "/api/cecchino/today/purchasability-v35-v2-analysis-export"
        "?date_from=2026-08-26&date_to=2026-08-26"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")


def test_range_validation():
    with pytest.raises(V35V2AnalysisRangeError):
        validate_v2_analysis_date_range(date(2026, 1, 1), date(2026, 3, 1))


def test_c12b_a_valid_eligible_included():
    row = _fixture_row(fid=1, eligibility_status=ELIGIBILITY_ELIGIBLE)
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        manifest, _, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["fixtures"][0]["analysis_status"] == "included"
    assert manifest["fixtures"][0]["current_eligibility_status"] == ELIGIBILITY_ELIGIBLE


def test_c12b_b_valid_noneligible_included():
    row = _fixture_row(
        fid=2,
        eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    )
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        manifest, files, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["fixtures"][0]["analysis_status"] == "included"
    assert manifest["summary"]["valid_current_noneligible_count"] == 1
    assert any("1507044" in name or str(row.provider_fixture_id) in name for name in files)


def test_c12b_c_eligibility_flip_still_included():
    row = _fixture_row(
        fid=3,
        eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
    )
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        manifest, _, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["fixtures"][0]["analysis_status"] == "included"


def test_c12b_d_eligible_without_v2_key_not_in_population():
    eligible_no_v2 = _fixture_row(fid=99, omit_v2_key=True)
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=1,
    ):
        manifest, files, csv_rows = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["summary"]["snapshot_population_count"] == 0
    assert manifest["summary"]["current_eligible_without_v2_key_count"] == 1
    assert manifest["fixtures"] == []
    assert files == {}
    assert csv_rows == []
    # loader filter itself
    db = MagicMock()
    db.scalars.return_value.all.return_value = [eligible_no_v2]
    assert _load_v2_snapshot_population_range(
        db, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
    ) == []
    assert (
        _count_current_eligible_without_v2_key(
            db, date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
        == 1
    )


def test_c12b_e_invalid_snapshot_in_population_no_recompute():
    bad = {"snapshot_version": "wrong"}
    row = _fixture_row(fid=4, v2=bad)
    # ensure key present with invalid dict
    row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY] = bad
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch",
        side_effect=AssertionError("v2_recompute_forbidden"),
    ):
        manifest, files, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["summary"]["snapshot_population_count"] == 1
    assert manifest["summary"]["invalid_v2_snapshots"] == 1
    assert manifest["summary"]["analysis_included_count"] == 0
    assert manifest["fixtures"][0]["analysis_status"] == "snapshot_invalid"
    assert "current_eligibility_status" in manifest["fixtures"][0]
    assert files == {}


def test_c12b_f_key_present_none_reported_invalid():
    row = _fixture_row(fid=5)
    row.cecchino_output_json[SNAPSHOT_OUTPUT_KEY] = None
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        manifest, _, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    fx = manifest["fixtures"][0]
    assert fx["analysis_status"] == "snapshot_invalid"
    assert fx["snapshot_invalid_reason"] == "not_a_dict"
    assert fx["current_eligibility_status"] == ELIGIBILITY_ELIGIBLE
    assert manifest["summary"]["invalid_v2_snapshots"] == 1


def test_c12b_g_noneligible_outcome_join():
    row = _fixture_row(
        fid=6,
        eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
        match_display_status=MATCH_FINISHED,
        goals_home=2,
        goals_away=1,
    )
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ):
        _, _, csv_rows = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    outcomes = {r.get("outcome") for r in csv_rows if r.get("status") == "score"}
    assert outcomes & {EVAL_WON, EVAL_LOST}
    assert all(
        r.get("current_eligibility_status") == ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS
        for r in csv_rows
    )


def test_c12b_h_engine_fail_export_still_works():
    row = _fixture_row(fid=7)
    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=[row],
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=0,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_engine."
        "calculate_purchasability_v35_v2_batch",
        side_effect=RuntimeError("engine_must_not_run"),
    ):
        manifest, files, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )
    assert manifest["summary"]["analysis_included_count"] == 1
    assert files


def test_c12b_i_cohorts_unchanged():
    assert holdout_cohort_for_scan_date(date(2026, 8, 26)) == COHORT_TECHNICAL_SMOKE
    assert holdout_cohort_for_scan_date(date(2026, 8, 27)) == COHORT_PROSPECTIVE
    assert PRIMARY_DIAGNOSTIC_COHORT == COHORT_PROSPECTIVE


def test_c12b_j_max_range_31_unchanged():
    validate_v2_analysis_date_range(date(2026, 8, 1), date(2026, 8, 31))
    with pytest.raises(V35V2AnalysisRangeError):
        validate_v2_analysis_date_range(date(2026, 8, 1), date(2026, 9, 1))


def test_c12b_k_formula_freeze_sha():
    assert EXPECTED_FORMULA_FREEZE_SHA256 == (
        "3488f0d8e97f52b3db126ff96758c51adef0acfc8fd98f953b2443e629cd0bfe"
    )


def test_c12b_regression_set_level_22_17_5():
    """Production C1.2A case: 22 valid (17 eligible + 5 non-eligible) all included."""
    v1, v2 = _build_paired_snapshots()
    eligible_ids = list(range(1000, 1017))
    noneligible_ids = [2001, 2002, 2003, 2004, 2005]
    rows = []
    for i, fid in enumerate(eligible_ids):
        rows.append(
            _fixture_row(
                fid=fid,
                provider_id=5000 + i,
                v1=copy.deepcopy(v1),
                v2=copy.deepcopy(v2),
                eligibility_status=ELIGIBILITY_ELIGIBLE,
            )
        )
    for i, fid in enumerate(noneligible_ids):
        rows.append(
            _fixture_row(
                fid=fid,
                provider_id=6000 + i,
                v1=copy.deepcopy(v1),
                v2=copy.deepcopy(v2),
                eligibility_status=ELIGIBILITY_EXCLUDED_INSUFFICIENT_STATS,
            )
        )
    assert len(rows) == 22

    with patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_load_v2_snapshot_population_range",
        return_value=rows,
    ), patch(
        "app.services.cecchino.cecchino_purchasability_v35_v2_range_analysis_export."
        "_count_current_eligible_without_v2_key",
        return_value=7,
    ):
        manifest, files, _ = build_range_purchasability_v35_v2_analysis_manifest_and_files(
            MagicMock(), date_from=date(2026, 8, 26), date_to=date(2026, 8, 26)
        )

    summary = manifest["summary"]
    P = {int(f["today_fixture_id"]) for f in manifest["fixtures"]}
    I = {
        int(f["today_fixture_id"])
        for f in manifest["fixtures"]
        if f.get("analysis_status") == "included"
    }
    NE = {
        int(f["today_fixture_id"])
        for f in manifest["fixtures"]
        if f.get("analysis_status") == "included"
        and f.get("current_eligibility_status") != ELIGIBILITY_ELIGIBLE
    }

    assert len(P) == 22
    assert len(I) == 22
    assert P == I
    assert len(NE) == 5
    assert NE.issubset(I)
    assert NE == set(noneligible_ids)

    assert summary["snapshot_population_count"] == 22
    assert summary["valid_v2_snapshots"] == 22
    assert summary["invalid_v2_snapshots"] == 0
    assert summary["analysis_included_count"] == 22
    assert summary["snapshot_population_count"] == (
        summary["valid_v2_snapshots"] + summary["invalid_v2_snapshots"]
    )
    assert summary["valid_current_eligible_count"] == 17
    assert summary["valid_current_noneligible_count"] == 5
    assert summary["current_eligibility_counts"]["eligible"] == 17
    assert (
        summary["current_eligibility_counts"]["excluded_insufficient_stats"] == 5
    )
    assert summary["eligible_fixtures"] == 17
    assert summary["eligible_fixtures"] != summary["snapshot_population_count"]
    assert summary["population_inclusion_basis"] == "persisted_v2_snapshot_key"
    assert summary["current_eligible_without_v2_key_count"] == 7
    assert len(files) == 22
    for fx in manifest["fixtures"]:
        assert "current_eligibility_status" in fx
