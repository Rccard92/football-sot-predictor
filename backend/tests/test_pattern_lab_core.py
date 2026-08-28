"""Test Pattern Lab — projection, filters, anti-leakage, export schema."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino_data_lab.pattern_lab_discovery_export import (
    EXPORT_ARROW_TYPE_NAMES,
    EXPORT_COLUMNS,
    assert_anti_leakage_schema,
    build_data_dictionary_rows,
    build_export_arrow_schema,
    column_role,
    table_from_export_batch,
)
from app.services.cecchino_data_lab.pattern_lab_filters import (
    parse_pattern_lab_filters,
    row_passes_filters,
)
from app.services.cecchino_data_lab.pattern_lab_projection import project_row
from app.services.cecchino_data_lab.pattern_lab_aggregations import accumulate_rows
from app.services.cecchino_data_lab.historical_bet_builder_projection import (
    bet_builder_meta_by_market,
    compare_opportunity_evidence_v36,
)


def _market(**kwargs):
    base = dict(
        id=1,
        run_id=15,
        match_snapshot_id=1,
        lab_match_id=100,
        market_key="HOME",
        market_label="1",
        period="FT",
        line=None,
        quota_cecchino=Decimal("2.10"),
        prob_cecchino=Decimal("0.45"),
        quota_book=Decimal("1.90"),
        prob_book_raw=Decimal("0.50"),
        prob_book_fair=Decimal("0.48"),
        quote_source_type="bet365",
        is_real_book_quote=True,
        is_derived_quote=False,
        derivation_method=None,
        edge_pct=Decimal("8.0"),
        vantaggio_prob=Decimal("0.04"),
        rating=72,
        signal_active=True,
        signal_sources_json={
            "sources": [{"source_column": "EXCEL_D"}, {"source_column": "EXCEL_F"}],
            "signal_family": "HOME",
            "active_signal_count": 2,
            "acquired_signal_count": 1,
            "consensus_yes_columns": ["D", "F"],
            "acquisition_status": "acquired",
            "consensus_yes_count": 2,
        },
        evaluation_status="settled",
        won=True,
        profit_1u_real=Decimal("0.90"),
        profit_1u_synthetic=None,
        result_reason=None,
        profit_category="actual_bet365",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _snap(**kwargs):
    base = dict(
        id=1,
        run_id=15,
        lab_match_id=100,
        competition_name="Serie A",
        season_label="2021/2022",
        kickoff_at=datetime(2021, 9, 12, 18, 0, tzinfo=timezone.utc),
        home_team="Inter",
        away_team="Milan",
        historical_eligibility_status="eligible_core",
        historical_kpi_json={
            "rows": [
                {
                    "market_key": "HOME",
                    "score_acquisto": 0.12,
                    "edge_pct": 8.0,
                    "rating": 72,
                    "vantaggio_prob": 0.04,
                    "prob_book": 0.5,
                    "prob_cecchino": 0.45,
                    "quota_book": 1.9,
                    "quota_cecchino": 2.1,
                    "rating_label": "buono",
                    "status": "ok",
                }
            ]
        },
        signals_json={"default_model_key": "F", "models": {}},
        balance_v5_json={
            "observation_status": "complete",
            "structural_summary": {"class": "equilibrio"},
            "pillars": {
                "f36": {"class_key": "equilibrio", "score": 40},
                "dominance": {"class_key": "media", "score": 50},
                "draw_credibility": {"class_key": "media", "score": 55},
                "gap_coherence": {"class_key": "alta", "score": 92},
            },
        },
        goal_intensity_compatibility_json={
            "execution_status": "computed",
            "composite_gi_a_strict_core": 61.0,
            "final_class": {"key": "offensive", "label": "Offensive", "score": 61},
            "pillars": {
                "offensive_production": {"class_key": "alta", "score": 70},
                "defensive_solidity": {"class_key": "media", "score": 50},
                "match_tempo": {"class_key": "alta", "score": 65},
                "offensive_stability": {"class_key": "media", "score": 45},
            },
        },
        purchasability_compatibility_json={
            "execution_status": "computed",
            "markets": [
                {"market_key": "HOME", "score": 62, "class": "acquistabile", "status": "score"}
            ],
        },
        quote_observations_json={
            "movements": [
                {
                    "market_key": "HOME",
                    "quota_closing": 1.75,
                    "implied_probability_closing": 0.571,
                    "delta_pct": -7.9,
                    "direction": "shorten",
                    "intensity": "medium",
                    "availability_horizon": "post_closing_observation",
                }
            ]
        },
        cecchino_output_json={"signals_matrix": None},
        result_json={
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
            "ft_result": "H",
        },
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_project_row_separates_pre_target_observational():
    row = project_row(_snap(), _market(), bb_meta={"active": True, "rank": 1, "reason": "test"})
    assert row["run_id"] == 15
    assert row["market_key"] == "HOME"
    assert row["pre_rating"] == 72
    assert row["pre_score_acquisto"] == 0.12
    assert row["pre_value_positive"] is True
    assert row["pre_purch_v36_score"] == 62
    assert row["pre_balance_geometry"] == 92
    assert row["pre_goal_v4_compat_final_class"] == "offensive"
    assert row["pre_signal_excel_d"] is True
    assert row["pre_pattern_lab_bet_builder_active"] is True
    assert row["target_won"] is True
    assert row["target_profit_1u"] == 0.9
    assert row["target_ft_home"] == 2
    assert row["observational_only_quota_closing"] == 1.75
    # no post-match inside pre_* names for this row's keys
    for k in row:
        if k.startswith("pre_"):
            assert "closing" not in k
            assert "profit" not in k
            assert not k.startswith("pre_target")


def test_anti_leakage_schema():
    assert_anti_leakage_schema()
    for col in EXPORT_COLUMNS:
        if col.startswith("pre_"):
            assert "closing" not in col.lower()
            assert "movement" not in col.lower()
            assert "profit" not in col.lower()


def test_parquet_schema_stable_across_null_then_valued_batches(tmp_path):
    """Batch1 tutto-NULL non deve fissare tipi null; batch2 float/string deve scrivere ok."""
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    schema = build_export_arrow_schema()
    assert set(schema.names) == set(EXPORT_COLUMNS)
    assert len(EXPORT_ARROW_TYPE_NAMES) == len(EXPORT_COLUMNS)

    float_col = "pre_goal_v4_compat_composite"
    string_col = "pre_goal_v4_compat_final_class"
    assert schema.field(float_col).type == pyarrow.float64()
    assert schema.field(string_col).type == pyarrow.string()

    batch1 = [{c: None for c in EXPORT_COLUMNS}]
    batch2 = [{c: None for c in EXPORT_COLUMNS}]
    batch2[0][float_col] = 1.5
    batch2[0][string_col] = "HIGH"
    batch2[0]["run_id"] = 15
    batch2[0]["lab_match_id"] = 1
    batch2[0]["snapshot_id"] = 1

    path = tmp_path / "pattern_lab_schema_stability.parquet"
    writer = pq.ParquetWriter(str(path), schema, compression="zstd")
    try:
        writer.write_table(table_from_export_batch(batch1, schema=schema))
        writer.write_table(table_from_export_batch(batch2, schema=schema))
    finally:
        writer.close()

    table = pq.read_table(str(path))
    assert table.num_rows == 2
    assert table.schema.equals(schema, check_metadata=False)
    assert table.schema.field(float_col).type == pyarrow.float64()
    assert table.schema.field(string_col).type == pyarrow.string()
    assert table.column(float_col)[0].as_py() is None
    assert table.column(float_col)[1].as_py() == pytest.approx(1.5)
    assert table.column(string_col)[1].as_py() == "HIGH"


def test_data_dictionary_observational_not_predictor():
    rows = build_data_dictionary_rows()
    obs = [r for r in rows if r["column"].startswith("observational_only_")]
    assert obs
    assert all(r["allowed_as_predictor"] is False for r in obs)
    targets = [r for r in rows if r["column"].startswith("target_")]
    assert targets
    assert all(r["allowed_as_predictor"] is False for r in targets)
    assert column_role("pre_rating") == "pre_feature"
    assert column_role("target_won") == "post_target"


def test_filters_combinable():
    row = project_row(_snap(), _market(), bb_meta={"active": True, "rank": 1})
    f = parse_pattern_lab_filters(
        {
            "rating_min": 60,
            "purchasability_v36_min": 50,
            "gap_coherence_score_min": 90,
            "signals_count_min": 1,
            "value": True,
            "bet_builder_active": True,
        }
    )
    assert row_passes_filters(row, f) is True
    f2 = parse_pattern_lab_filters({"purchasability_v36_min": 90})
    assert row_passes_filters(row, f2) is False


def test_accumulate_summary():
    row = project_row(_snap(), _market())
    agg = accumulate_rows([row, row])
    assert agg["summary"]["selections"] == 2
    assert agg["summary"]["wins"] == 2
    assert agg["summary"]["avg_rating"] == 72
    assert agg["summary"]["avg_purchasability_v36"] == 62
    assert agg["match_count"] == 1
    assert "module_insights" in agg
    assert agg["module_insights"]["kpi"]["rating_bands"]
    assert agg["module_insights"]["signals"]["excel_column_frequency"]["D"] == 2


def test_filters_date_and_score_acquisto():
    row = project_row(_snap(), _market())
    f = parse_pattern_lab_filters(
        {
            "date_from": "2021-09-01",
            "date_to": "2021-09-30",
            "score_acquisto_min": 0.1,
            "vantaggio_prob_min": 0.01,
        }
    )
    assert row_passes_filters(row, f) is True
    f2 = parse_pattern_lab_filters({"date_from": "2022-01-01"})
    assert row_passes_filters(row, f2) is False


def test_canonical_flags_require_full_v4_policy_revision_v36():
    from app.services.cecchino_data_lab.pattern_lab_canonical import evaluate_canonical_flags

    run = SimpleNamespace(
        status="completed",
        scan_version="cecchino_lab_historical_scan_v4",
        quote_policy_json={"version": "bet365_pre_reference_v1"},
        source_revision_status="resolved",
        module_policy_json={
            "run_scope": "full",
            "is_partial_run": False,
            "purchasability": "historical_v4_v35_v2_canonical",
        },
    )
    ok = evaluate_canonical_flags(run, has_v36=True, has_v36_scores=True)
    assert ok["is_canonical"] is True
    assert ok["incomplete_v36"] is False

    legacy_v3 = SimpleNamespace(
        status="completed",
        scan_version="cecchino_lab_historical_scan_v3",
        quote_policy_json={"version": "bet365_pre_reference_v1"},
        source_revision_status="resolved",
        module_policy_json={"run_scope": "full", "is_partial_run": False},
    )
    bad = evaluate_canonical_flags(legacy_v3, has_v36=False, has_v36_scores=False)
    assert bad["is_canonical"] is False
    assert bad["is_legacy"] is True

    no_v36 = evaluate_canonical_flags(run, has_v36=False, has_v36_scores=False)
    assert no_v36["is_canonical"] is False
    assert no_v36["canonical_checks"]["purchasability_v36_present"] is False

    # JSON presente ma score assenti → incomplete, non canonica
    incomplete = evaluate_canonical_flags(run, has_v36=True, has_v36_scores=False)
    assert incomplete["is_canonical"] is False
    assert incomplete["incomplete_v36"] is True
    assert incomplete["canonical_checks"]["purchasability_v36_present"] is True
    assert incomplete["canonical_checks"]["purchasability_v36_scores_present"] is False

    bad_policy = SimpleNamespace(
        status="completed",
        scan_version="cecchino_lab_historical_scan_v4",
        quote_policy_json={"version": "other_policy"},
        source_revision_status="resolved",
        module_policy_json={"run_scope": "full", "is_partial_run": False},
    )
    assert (
        evaluate_canonical_flags(bad_policy, has_v36=True, has_v36_scores=True)[
            "is_canonical"
        ]
        is False
    )

    unresolved = SimpleNamespace(
        status="completed",
        scan_version="cecchino_lab_historical_scan_v4",
        quote_policy_json={"version": "bet365_pre_reference_v1"},
        source_revision_status="unknown",
        module_policy_json={"run_scope": "full", "is_partial_run": False},
    )
    assert (
        evaluate_canonical_flags(unresolved, has_v36=True, has_v36_scores=True)[
            "is_canonical"
        ]
        is False
    )


def test_bet_builder_v36_sort_prefers_higher_score():
    a = {
        "market_key": "HOME",
        "origin": "price_and_signals",
        "purchasability_v36": {"score": 80},
        "signals": {"passed": True, "yes_count": 2},
        "price_value": {"rating": 70, "edge_pct": 5},
    }
    b = {
        "market_key": "DRAW",
        "origin": "price_and_signals",
        "purchasability_v36": {"score": 40},
        "signals": {"passed": True, "yes_count": 2},
        "price_value": {"rating": 90, "edge_pct": 10},
    }
    assert compare_opportunity_evidence_v36(a, b) < 0


def test_bet_builder_meta_from_snap_without_engine():
    snap = _snap(
        historical_kpi_json={
            "rows": [
                {
                    "market_key": "HOME",
                    "edge_pct": 10,
                    "vantaggio_prob": 0.05,
                    "rating": 70,
                    "quota_book": 2.0,
                    "quota_cecchino": 2.2,
                    "prob_book": 0.45,
                    "prob_cecchino": 0.5,
                    "score_acquisto": 0.1,
                    "status": "ok",
                }
            ]
        },
        purchasability_compatibility_json={
            "markets": [{"market_key": "HOME", "score": 70, "class": "alta", "status": "score"}]
        },
        cecchino_output_json={"signals_matrix": None},
    )
    meta = bet_builder_meta_by_market(snap)
    # May be empty if price gate fails without full kpi — just ensure no crash
    assert isinstance(meta, dict)
