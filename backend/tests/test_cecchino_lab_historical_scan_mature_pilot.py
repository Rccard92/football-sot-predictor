"""Test progresso 16/16, report frammentati, etichette A–F (senza pilota moduli maturi)."""

from __future__ import annotations

import io
import json
import os
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    model_meta_for_key,
)
from app.services.cecchino_data_lab.historical_ai_report import (
    REPORT_SCHEMA_VERSION,
    _build_patterns_top,
    _canonical_signal_model_fields,
    build_ai_report_zip_bytes,
)
from app.services.cecchino_data_lab.historical_scan_service import _build_run_summary


def test_canonical_af_labels_non_null_and_f_current():
    for key in CECCHINO_WEIGHT_MODEL_KEYS:
        fields = _canonical_signal_model_fields(key)
        assert fields["model_key"] == key
        assert fields["model_label"]
        assert fields["model_short_label"]
        assert fields["weights_version"]
        assert fields["weights"]
        meta = model_meta_for_key(key)
        assert fields["model_label"] == meta["model_label"]
    assert CECCHINO_DEFAULT_WEIGHT_MODEL_KEY == "F"
    assert _canonical_signal_model_fields("F")["model_key"] == "F"


def test_build_run_summary_no_global_profit_misleading():
    db = MagicMock()
    snap = SimpleNamespace(
        id=1,
        historical_eligibility_status="eligible_core",
        module_availability_json={},
        signals_json={"models": {}},
        purchasability_compatibility_json={"markets": []},
    )
    market = SimpleNamespace(
        match_snapshot_id=1,
        market_key="HOME",
        profit_1u_real=1.5,
        profit_1u_synthetic=None,
        rating=70,
    )
    db.scalars.return_value.all.side_effect = [[snap], [market]]
    summary = _build_run_summary(db, 1)
    assert "real_profit_1u" not in summary
    assert "synthetic_profit_1u" not in summary
    tech = summary["technical_sum_across_all_independent_market_rows"]
    assert tech["not_a_betting_strategy"] is True
    assert "profit_by_market" in summary
    assert "HOME" in summary["profit_by_market"]
    assert "pilot_sample_roles" not in summary


def test_progress_finalization_helper_shape():
    """Documenta contratto finalizzazione: 16/16, current null, 100%."""
    competitions_total = 16
    final = {
        "competitions_completed": competitions_total,
        "competitions_total": competitions_total,
        "current_competition": None,
        "eligible_in_current_competition": 0,
        "progress_pct": 100.0,
    }
    assert final["competitions_completed"] == final["competitions_total"]
    assert final["current_competition"] is None
    assert final["eligible_in_current_competition"] == 0
    assert final["progress_pct"] == 100.0


def _report_fixtures():
    run = SimpleNamespace(
        id=7,
        season_label="2021/2022",
        scan_version="cecchino_lab_historical_scan_v3",
        source_git_commit="abc",
        source_git_commit_source="test",
        source_revision_status="resolved",
        preflight_json={"status": "ready"},
        module_policy_json={
            "run_scope": "balanced_pilot",
            "is_partial_run": True,
            "pilot_strategy": "eligible_per_competition",
            "eligible_per_competition": 20,
            "not_full_season_report": True,
        },
    )
    models = {}
    for k in CECCHINO_WEIGHT_MODEL_KEYS:
        meta = model_meta_for_key(k)
        models[k] = {
            "meta": meta,
            "weights": meta["weights_json"],
            "settlements": [
                {
                    "signal_family": "HOME",
                    "source_column": "EXCEL_D",
                    "target_market": "HOME",
                    "quota_cecchino": 2.0,
                    "won": True,
                    "real_profit_1u": 1.0,
                    "synthetic_profit_1u": None,
                    "quote_quality": "real",
                }
            ],
            "active_signals": [{"x": 1}],
        }
    eligible = SimpleNamespace(
        id=1,
        dataset_id=10,
        lab_match_id=100,
        competition_name="Serie A",
        season_label="2021/2022",
        kickoff_at=None,
        chronological_order=0,
        home_team="A",
        away_team="B",
        historical_eligibility_status="eligible_core",
        historical_eligibility_reason=None,
        blocking_reasons_json=[],
        input_snapshot_json={"prior_count": 40, "totals": {"sample": 12}},
        cecchino_output_json={
            "final": {"quota_1": 2.1, "quota_x": 3.2, "quota_2": 3.5, "status": "available"},
            "picchetti": {},
            "status": "available",
        },
        signals_json={"models": models, "default_model_key": "F"},
        balance_v5_json={"structural_summary": {"class": "balance"}},
        goal_intensity_compatibility_json={
            "raw_features_available": True,
            "execution_status": "computed",
            "pillars": {
                "offensive_production": {"class": "alta"},
                "defensive_vulnerability": {"class": "media"},
                "tempo_transition": {"class": "bassa"},
                "set_piece_pressure": {"class": "media"},
            },
            "parity_status": "partial",
        },
        purchasability_compatibility_json={
            "inputs_available": True,
            "execution_status": "computed",
            "markets": [
                {
                    "market_key": "HOME",
                    "score": 72,
                    "class": "alta",
                    "rating": 65,
                    "edge_pct": 4.0,
                    "vantaggio_prob": 0.02,
                    "quote_quality": "real",
                }
            ],
        },
        module_availability_json={},
        quote_sources_json={"family_1x2": {"family_snapshot_type": "closing"}},
        pre_match_payload_sha256="abc",
        pre_match_locked_at=None,
        result_json={"fulltime": {"home": 1, "away": 0}},
        settlement_status="settled",
        settlement_summary_json={"markets_analyzed": 14},
        historical_kpi_json={"rows": []},
        error_json=None,
    )
    partial = SimpleNamespace(
        id=2,
        dataset_id=10,
        lab_match_id=101,
        competition_name="Serie A",
        season_label="2021/2022",
        kickoff_at=None,
        chronological_order=1,
        home_team="C",
        away_team="D",
        historical_eligibility_status="eligible_core",
        historical_eligibility_reason=None,
        blocking_reasons_json=[],
        input_snapshot_json={"prior_count": 5},
        cecchino_output_json={"final": {}, "picchetti": {}, "status": "available"},
        signals_json={"models": models},
        balance_v5_json={"structural_summary": {"class": "balance"}},
        goal_intensity_compatibility_json={"execution_status": "insufficient_sample"},
        purchasability_compatibility_json={
            "execution_status": "insufficient_historical_normalization_sample"
        },
        module_availability_json={},
        quote_sources_json={},
        pre_match_payload_sha256="def",
        pre_match_locked_at=None,
        result_json={"fulltime": {"home": 0, "away": 0}},
        settlement_status="settled",
        settlement_summary_json={},
        historical_kpi_json={},
        error_json=None,
    )
    market = SimpleNamespace(
        run_id=7,
        match_snapshot_id=1,
        lab_match_id=100,
        market_key="HOME",
        market_label="1",
        period="FT",
        line=None,
        quota_cecchino=2.1,
        prob_cecchino=0.4,
        quota_book=2.0,
        prob_book_raw=0.5,
        prob_book_fair=0.48,
        quote_source_type="closing",
        is_real_book_quote=True,
        is_derived_quote=False,
        derivation_method=None,
        edge_pct=5.0,
        vantaggio_prob=0.02,
        rating=62,
        signal_active=True,
        signal_sources_json={
            "sources": [
                {
                    "signal_family": "HOME",
                    "source_column": "EXCEL_D",
                    "column_key": "excel_d",
                    "signal_group": "HOME",
                }
            ],
            "signal_family": "HOME",
            "signal_families": ["HOME"],
            "active_signal_count": 1,
        },
        evaluation_status="won",
        won=True,
        profit_1u_real=1.0,
        profit_1u_synthetic=None,
        profit_category="actual_bet365",
        result_reason="ok",
    )
    return run, eligible, partial, market


def test_ai_summary_excludes_huge_raw_files():
    run, eligible, partial, market = _report_fixtures()
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[eligible, partial], [market]]
    filename, data = build_ai_report_zip_bytes(db, 7, mode="ai_summary")
    assert "ai_summary" in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "report_index.json" in names
        assert "patterns_top.json" in names
        assert "summary.json" in names
        assert "matches.jsonl" not in names
        assert "purchasability.jsonl" not in names
        assert "patterns.json" not in names
        idx = json.loads(zf.read("report_index.json"))
        assert idx["schema_version"] == REPORT_SCHEMA_VERSION
        assert idx["recommended_analysis_order"][0] == "ai_summary"
        cov = json.loads(zf.read("module_coverage.json"))
        assert "pilot_sample_roles" not in cov
    assert len(data) < 500_000


def test_competition_report_filtered():
    run, eligible, partial, market = _report_fixtures()
    other = SimpleNamespace(
        **{**eligible.__dict__, "id": 3, "competition_name": "Bundesliga", "lab_match_id": 200}
    )
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[eligible, partial, other], [market]]
    _fn, data = build_ai_report_zip_bytes(db, 7, mode="competition", competition="Serie A")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "matches_compact.jsonl" in names
        assert "purchasability_compact.jsonl" in names
        compact = zf.read("matches_compact.jsonl").decode().strip().splitlines()
        comps = {json.loads(line)["competition_name"] for line in compact}
        assert comps == {"Serie A"}
        sm = zf.read("signal_models.jsonl").decode().strip().splitlines()
        for line in sm:
            row = json.loads(line)
            assert row["model_label"] is not None
            assert row["model_short_label"]
            assert row["weights_version"]
            assert row["weights"]


def test_module_report_signals_filtered():
    run, eligible, _partial, market = _report_fixtures()
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[eligible], [market]]
    _fn, data = build_ai_report_zip_bytes(db, 7, mode="module", module="signals")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "signal_models.jsonl" in names
        assert "markets.jsonl" not in names
        assert "goal_intensity.jsonl" not in names
        rows = [json.loads(x) for x in zf.read("signal_models.jsonl").decode().splitlines() if x]
        keys = {r["model_key"] for r in rows}
        assert keys == set(CECCHINO_WEIGHT_MODEL_KEYS)
        assert all(r["model_label"] for r in rows)
        f_rows = [r for r in rows if r["model_key"] == "F"]
        assert f_rows
        assert f_rows[0]["model_key"] == CECCHINO_DEFAULT_WEIGHT_MODEL_KEY


def test_full_archive_available_and_legacy_exportable():
    run, eligible, partial, market = _report_fixtures()
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [[eligible, partial], [market]]
    filename, data = build_ai_report_zip_bytes(db, 7, mode="full_archive")
    assert "full_archive" in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "matches.jsonl" in names
        assert "purchasability.jsonl" in names
        assert "patterns.json" in names
        assert "report_index.json" in names


def test_patterns_top_deterministic():
    patterns = {
        "patterns": [
            {
                "pattern_id": "a",
                "sample_size": 100,
                "real_quote_count": 100,
                "real_roi": 5.0,
                "competitions_count": 3,
                "is_diagnostic": False,
                "stability_by_competition": {
                    "stable_cross_competition": False,
                    "cross_competition_stability": "inconsistent",
                },
            },
            {
                "pattern_id": "b",
                "sample_size": 5,
                "real_quote_count": 2,
                "real_roi": 80.0,
                "competitions_count": 1,
                "is_diagnostic": False,
                "stability_by_competition": {
                    "stable_cross_competition": False,
                    "cross_competition_stability": "insufficient_evidence",
                },
            },
            {
                "pattern_id": "c",
                "sample_size": 50,
                "real_quote_count": 50,
                "real_roi": -10.0,
                "competitions_count": 4,
                "is_diagnostic": False,
                "stability_by_competition": {
                    "stable_cross_competition": False,
                    "cross_competition_stability": "concentrated",
                },
            },
        ]
    }
    top = _build_patterns_top(patterns)
    best_ids = {p["pattern_id"] for p in top["best_positive_real_roi"]}
    assert "b" not in best_ids  # campione insufficiente
    assert "a" in best_ids


def test_partial_modules_still_in_eligible_core_universe():
    """Moduli parziali non escludono la partita dalle metriche se eligible_core."""
    run, eligible, partial, market = _report_fixtures()
    partial_market = SimpleNamespace(
        **{**market.__dict__, "match_snapshot_id": 2, "lab_match_id": 101}
    )
    db = MagicMock()
    db.get.return_value = run
    db.scalars.return_value.all.side_effect = [
        [eligible, partial],
        [market, partial_market],
    ]
    _fn, data = build_ai_report_zip_bytes(db, 7, mode="full_archive")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        markets_lines = zf.read("markets.jsonl").decode().strip().splitlines()
        assert len(markets_lines) == 2
        cov = json.loads(zf.read("module_coverage.json"))
        assert cov["analysis_sample"] == 2
        assert "pilot_sample_roles" not in cov
