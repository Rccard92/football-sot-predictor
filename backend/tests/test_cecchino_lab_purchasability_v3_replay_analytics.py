"""Test del modulo analytics read-only del Replay Acquistabilità V3 (STEP 3C.1).

Copertura:
- costanti e schema pubblico
- classificazione bucket (`classify_calc_bucket`) e bande (`score_band_for`)
- statistiche descrittive e intervalli di confidenza (`wilson_ci95`, `mean_profit_ci95`,
  `build_performance_stats`, `competition_sample_flag`)
- guardia di completamento replay (`ensure_replay_ready_for_analytics`)
- aggregazione end-to-end (`compute_analytics_from_lean_rows`) con riconciliazione,
  blockers, gate analysis, penalità, matrice value/quality, family decisions,
  stabilità temporale/per campionato e confronto diagnostico V2/V3
- selezione famiglie (`build_family_decisions`) e split temporale (`build_temporal_halves_by_competition`)
- cache in-memory (`_cache_key`, `_cache_set`, `_cache_get`, `clear_purchasability_v3_analytics_cache`)
- endpoint `GET /cecchino-lab/purchasability-v3-replays/{id}/analytics`
- invarianti di sola lettura (nessun ricalcolo formula, nessuna scrittura DB)
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes import cecchino_lab
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics import (
    CACHE_KIND_SUMMARY,
    FAMILY_DOUBLE_CHANCE,
    FAMILY_GOALS_FT_2_5,
    FAMILY_MATCH_WINNER_FT,
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
    REPLAY_NOT_COMPLETED_MSG,
    SCORE_BANDS,
    THRESHOLDS,
    V3_MARKET_ORDER,
    VQ_BANDS,
    _cache_get,
    _cache_key,
    _cache_set,
    build_family_decisions,
    build_performance_stats,
    build_temporal_halves_by_competition,
    classify_calc_bucket,
    clear_purchasability_v3_analytics_cache,
    competition_sample_flag,
    compute_analytics_from_lean_rows,
    ensure_replay_ready_for_analytics,
    mean_profit_ci95,
    score_band_for,
    wilson_ci95,
)


# ---------------------------------------------------------------------------
# Helper di fixture
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)


def _row(
    *,
    replay_run_id: int = 1,
    source_scan_run_id: int = 10,
    source_snapshot_id: int = 1,
    lab_match_id: int | None = None,
    competition_name: str = "Serie A",
    kickoff_at: datetime | None = None,
    chronological_order: int | None = None,
    market_key: str = "HOME",
    market_family: str | None = None,
    quote_source: str = "bet365_closing",
    quote_quality: str = "real",
    performance_type: str = "real",
    is_real_book_quote: bool = True,
    is_derived_quote: bool = False,
    derivation_method: str | None = None,
    quota_book: float | None = 2.0,
    quota_cecchino: float | None = 2.1,
    prob_book_fair: float | None = 0.50,
    prob_cecchino: float | None = 0.52,
    edge_pct: float | None = 8.0,
    vantaggio_prob: float | None = 0.04,
    calculation_status: str = "available",
    gate_status: str | None = "passed",
    gate_reason_codes_json: list[str] | None = None,
    score: int | None = 85,
    raw_score: float | None = None,
    score_class: str | None = "molto_alta",
    value_score: float | None = 70.0,
    quality_score: float | None = 80.0,
    total_penalty: float | None = 5.0,
    probability_risk_penalty: float | None = 0.0,
    opposite_market_pressure_penalty: float | None = 0.0,
    extreme_divergence_penalty: float | None = 0.0,
    family_ambiguity_penalty: float | None = 5.0,
    quote_quality_penalty: float | None = 0.0,
    opposite_market_key: str | None = None,
    selected_is_family_edge_leader: bool | None = True,
    family_edge_gap_or_deficit: float | None = 0.0,
    won: bool | None = True,
    profit_1u_real: float | None = 0.9,
    profit_1u_synthetic: float | None = None,
    performance_evaluation_status: str = "settled",
    result_reason: str | None = "ft",
    pre_match_only: bool = True,
    post_match_fields_excluded: bool = True,
    formula_payload_sha256: str | None = "sha-formula-default",
    source_pre_match_payload_sha256: str | None = "sha-prematch-default",
    source_pre_match_locked_at: datetime | None = None,
    formula_payload_fields_json: dict | None = None,
    reason_codes_json: list | None = None,
    warnings_json: list | None = None,
) -> dict:
    """Costruisce una riga "lean" compatibile con LEAN_COLUMNS / classify_calc_bucket."""
    kickoff_at = kickoff_at or _utcnow()
    if chronological_order is None:
        chronological_order = source_snapshot_id
    if lab_match_id is None:
        lab_match_id = 1000 + source_snapshot_id
    return {
        "replay_run_id": replay_run_id,
        "replay_id": replay_run_id,
        "source_scan_run_id": source_scan_run_id,
        "source_snapshot_id": source_snapshot_id,
        "lab_match_id": lab_match_id,
        "competition_name": competition_name,
        "kickoff_at": kickoff_at,
        "chronological_order": chronological_order,
        "market_key": market_key,
        "market_family": market_family,
        "quote_source": quote_source,
        "quote_quality": quote_quality,
        "performance_type": performance_type,
        "is_real_book_quote": is_real_book_quote,
        "is_derived_quote": is_derived_quote,
        "derivation_method": derivation_method,
        "quota_book": quota_book,
        "quota_cecchino": quota_cecchino,
        "prob_book_fair": prob_book_fair,
        "prob_cecchino": prob_cecchino,
        "edge_pct": edge_pct,
        "vantaggio_prob": vantaggio_prob,
        "calculation_status": calculation_status,
        "gate_status": gate_status,
        "gate_reason_codes_json": gate_reason_codes_json if gate_reason_codes_json is not None else [],
        "score": score,
        "raw_score": raw_score,
        "score_class": score_class,
        "value_score": value_score,
        "quality_score": quality_score,
        "total_penalty": total_penalty,
        "probability_risk_penalty": probability_risk_penalty,
        "opposite_market_pressure_penalty": opposite_market_pressure_penalty,
        "extreme_divergence_penalty": extreme_divergence_penalty,
        "family_ambiguity_penalty": family_ambiguity_penalty,
        "quote_quality_penalty": quote_quality_penalty,
        "opposite_market_key": opposite_market_key,
        "selected_is_family_edge_leader": selected_is_family_edge_leader,
        "family_edge_gap_or_deficit": family_edge_gap_or_deficit,
        "won": won,
        "profit_1u_real": profit_1u_real,
        "profit_1u_synthetic": profit_1u_synthetic,
        "performance_evaluation_status": performance_evaluation_status,
        "result_reason": result_reason,
        "pre_match_only": pre_match_only,
        "post_match_fields_excluded": post_match_fields_excluded,
        "formula_payload_sha256": formula_payload_sha256,
        "source_pre_match_payload_sha256": source_pre_match_payload_sha256,
        "source_pre_match_locked_at": source_pre_match_locked_at,
        "formula_payload_fields_json": formula_payload_fields_json if formula_payload_fields_json is not None else {},
        "reason_codes_json": reason_codes_json if reason_codes_json is not None else [],
        "warnings_json": warnings_json if warnings_json is not None else [],
    }


def _scored_row(**kw) -> dict:
    kw.setdefault("score", 85)
    kw.setdefault("gate_status", "passed")
    kw.setdefault("calculation_status", "available")
    return _row(**kw)


def _gate_failed_row(**kw) -> dict:
    kw.setdefault("score", None)
    kw.setdefault("gate_status", "failed")
    kw.setdefault("calculation_status", "available")
    kw.setdefault("gate_reason_codes_json", ["no_positive_edge"])
    kw.setdefault("edge_pct", -5.0)
    kw.setdefault("vantaggio_prob", -0.02)
    kw.setdefault("profit_1u_real", None)
    kw.setdefault("profit_1u_synthetic", None)
    kw.setdefault("won", None)
    kw.setdefault("score_class", None)
    return _row(**kw)


def _unavailable_row(**kw) -> dict:
    kw.setdefault("score", None)
    kw.setdefault("gate_status", None)
    kw.setdefault("calculation_status", "unavailable")
    kw.setdefault("quote_quality", "unavailable")
    kw.setdefault("is_real_book_quote", False)
    kw.setdefault("is_derived_quote", False)
    kw.setdefault("quota_book", None)
    kw.setdefault("formula_payload_sha256", None)
    kw.setdefault("profit_1u_real", None)
    kw.setdefault("profit_1u_synthetic", None)
    kw.setdefault("won", None)
    kw.setdefault("score_class", None)
    return _row(**kw)


def _replay_from_rows(rows: list[dict], **overrides) -> SimpleNamespace:
    """Replay coerente con `rows`: i contatori derivano da `classify_calc_bucket`
    così i controlli di riconciliazione passano di default, salvo override espliciti
    usati per testare i blockers.
    """
    buckets = Counter(classify_calc_bucket(r) for r in rows)
    real_quote = 0
    derived_quote = 0
    for r in rows:
        qq = str(r.get("quote_quality") or "")
        if qq == "real" or (r.get("is_real_book_quote") and not r.get("is_derived_quote")):
            real_quote += 1
        elif qq == "derived" or r.get("is_derived_quote"):
            derived_quote += 1
    unavailable_quote = len(rows) - real_quote - derived_quote

    defaults = dict(
        id=1,
        source_scan_run_id=10,
        status="completed",
        replay_schema_version="replay_schema_v1",
        replay_engine_version="replay_engine_v1",
        candidate_version="candidate_v1",
        formula_version="formula_v1",
        audit_version="audit_v1",
        preflight_schema_version="preflight_v1",
        integrity_policy_version="integrity_v1",
        source_scan_git_commit="scan-git-abc",
        runtime_git_commit="runtime-git-def",
        completed_at=_utcnow(),
        evaluations_total=len(rows),
        results_persisted=len(rows),
        scored_count=buckets.get("scored", 0),
        gate_failed_count=buckets.get("gate_failed", 0),
        unavailable_count=buckets.get("unavailable", 0),
        not_applicable_count=buckets.get("not_applicable", 0),
        error_count=buckets.get("error", 0),
        unclassified_count=buckets.get("unclassified", 0),
        real_quote_count=real_quote,
        derived_quote_count=derived_quote,
        unavailable_quote_count=unavailable_quote,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_purchasability_v3_analytics_cache()
    yield
    clear_purchasability_v3_analytics_cache()


# ---------------------------------------------------------------------------
# Costanti e schema pubblico
# ---------------------------------------------------------------------------


def test_schema_version_and_message_constants():
    assert PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION == "cecchino_lab_purchasability_v3_analytics_v1"
    assert REPLAY_NOT_COMPLETED_MSG == (
        "Il replay deve essere completato prima di generare analytics o report."
    )
    assert CACHE_KIND_SUMMARY == "summary"


def test_market_family_and_threshold_constants():
    assert V3_MARKET_ORDER == (
        "HOME",
        "DRAW",
        "AWAY",
        "OVER_2_5",
        "UNDER_2_5",
        "ONE_X",
        "X_TWO",
        "ONE_TWO",
    )
    assert FAMILY_MATCH_WINNER_FT == "MATCH_WINNER_FT"
    assert FAMILY_GOALS_FT_2_5 == "GOALS_FT_2_5"
    assert FAMILY_DOUBLE_CHANCE == "DOUBLE_CHANCE"
    assert THRESHOLDS == (20, 40, 60, 70, 80, 90)
    assert SCORE_BANDS == ("0-19", "20-39", "40-59", "60-79", "80-89", "90-100")
    assert len(VQ_BANDS) == 5


# ---------------------------------------------------------------------------
# classify_calc_bucket
# ---------------------------------------------------------------------------


def test_classify_calc_bucket_error_has_priority():
    row = {"calculation_status": "error", "gate_status": "passed", "score": 90}
    assert classify_calc_bucket(row) == "error"


def test_classify_calc_bucket_unavailable_statuses():
    assert classify_calc_bucket({"calculation_status": "unavailable"}) == "unavailable"
    assert classify_calc_bucket({"calculation_status": "source_not_replayable"}) == "unavailable"


def test_classify_calc_bucket_gate_failed_requires_score_none():
    row = {"calculation_status": "available", "gate_status": "failed", "score": None}
    assert classify_calc_bucket(row) == "gate_failed"
    # Gate fallito ma con reason codes non vuoti resta gate_failed
    row2 = {
        "calculation_status": "available",
        "gate_status": "rejected_multiple_non_positive_components",
        "score": None,
    }
    assert classify_calc_bucket(row2) == "gate_failed"


def test_classify_calc_bucket_scored_has_priority_over_gate_when_score_present():
    """Se lo score è valorizzato, il bucket è "scored" anche con gate_status non-passed:
    la classificazione aggregata dà priorità allo score effettivo (edge-case documentato)."""
    row = {"calculation_status": "available", "gate_status": "passed", "score": 85}
    assert classify_calc_bucket(row) == "scored"
    row2 = {"calculation_status": "available", "gate_status": "failed", "score": 85}
    assert classify_calc_bucket(row2) == "scored"


def test_classify_calc_bucket_not_applicable_and_unclassified():
    na = {"calculation_status": "not_applicable", "gate_status": "", "score": None}
    assert classify_calc_bucket(na) == "not_applicable"

    avail_no_score = {"calculation_status": "available", "gate_status": "", "score": None}
    assert classify_calc_bucket(avail_no_score) == "unavailable"

    partial_no_score = {"calculation_status": "partial", "gate_status": "", "score": None}
    assert classify_calc_bucket(partial_no_score) == "unavailable"

    weird = {"calculation_status": "weird_unknown", "gate_status": "", "score": None}
    assert classify_calc_bucket(weird) == "unclassified"

    empty = {}
    assert classify_calc_bucket(empty) == "unclassified"


# ---------------------------------------------------------------------------
# score_band_for
# ---------------------------------------------------------------------------


def test_score_band_for_boundaries():
    assert score_band_for(None) is None
    assert score_band_for(0) == "0-19"
    assert score_band_for(19) == "0-19"
    assert score_band_for(20) == "20-39"
    assert score_band_for(39) == "20-39"
    assert score_band_for(40) == "40-59"
    assert score_band_for(59) == "40-59"
    assert score_band_for(60) == "60-79"
    assert score_band_for(79) == "60-79"
    assert score_band_for(80) == "80-89"
    assert score_band_for(89) == "80-89"
    assert score_band_for(90) == "90-100"
    assert score_band_for(100) == "90-100"


# ---------------------------------------------------------------------------
# wilson_ci95 / mean_profit_ci95 / competition_sample_flag
# ---------------------------------------------------------------------------


def test_wilson_ci95_below_min_sample_returns_none():
    assert wilson_ci95(15, 29) == (None, None)
    assert wilson_ci95(0, 0) == (None, None)


def test_wilson_ci95_at_min_sample_matches_expected_values():
    low, high = wilson_ci95(15, 30)
    assert (low, high) == (33.1539, 66.8461)

    low0, high0 = wilson_ci95(0, 30)
    assert (low0, high0) == (0.0, 11.3517)

    low100, high100 = wilson_ci95(30, 30)
    assert (low100, high100) == (88.6483, 100.0)


def test_mean_profit_ci95_below_min_sample_returns_all_none():
    assert mean_profit_ci95([]) == (None, None, None)
    assert mean_profit_ci95([2.0]) == (None, None, None)
    assert mean_profit_ci95([1.0] * 29) == (None, None, None)


def test_mean_profit_ci95_zero_variance_collapses_ci():
    mean, low, high = mean_profit_ci95([1.0] * 30)
    assert mean == 1.0
    assert low == 1.0
    assert high == 1.0


def test_mean_profit_ci95_with_variance():
    profits = [1.0 if i % 2 == 0 else -1.0 for i in range(30)]
    mean, low, high = mean_profit_ci95(profits)
    assert mean == 0.0
    assert low == -0.363963
    assert high == 0.363963
    assert low < mean < high


def test_competition_sample_flag_boundaries():
    assert competition_sample_flag(0) == "insufficient"
    assert competition_sample_flag(29) == "insufficient"
    assert competition_sample_flag(30) == "small"
    assert competition_sample_flag(99) == "small"
    assert competition_sample_flag(100) == "medium"
    assert competition_sample_flag(299) == "medium"
    assert competition_sample_flag(300) == "large"
    assert competition_sample_flag(1000) == "large"


# ---------------------------------------------------------------------------
# build_performance_stats
# ---------------------------------------------------------------------------


def test_build_performance_stats_empty_rows():
    stats = build_performance_stats([], profit_field="profit_1u_real")
    assert stats["stake_count"] == 0
    assert stats["profit_units"] is None
    assert stats["roi_pct"] is None
    assert stats["wins"] == 0
    assert stats["losses"] == 0
    assert stats["hit_rate_pct"] is None
    assert stats["ci_method"] is None
    assert stats["ci_null_reason"] == "insufficient_sample"


def test_build_performance_stats_below_ci_threshold():
    rows = [
        {"profit_1u_real": 1.0, "quota_book": 2.0, "score": 80, "value_score": 70, "quality_score": 90, "total_penalty": 5, "won": True},
        {"profit_1u_real": -1.0, "quota_book": 1.5, "score": 60, "value_score": 50, "quality_score": 60, "total_penalty": 10, "won": False},
        {"profit_1u_real": 0.0, "quota_book": 3.0, "score": 70, "value_score": 40, "quality_score": 70, "total_penalty": 0, "won": None},
    ]
    stats = build_performance_stats(rows, profit_field="profit_1u_real")
    assert stats["stake_count"] == 3
    assert stats["profit_units"] == 0.0
    assert stats["roi_pct"] == 0.0
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["void_or_zero_profit"] == 1
    assert stats["won_null"] == 1
    assert stats["hit_rate_pct"] == 50.0
    assert stats["average_odds"] == pytest.approx(2.166667)
    assert stats["median_odds"] == 2.0
    assert stats["average_score"] == 70.0
    assert stats["average_value_score"] == pytest.approx(53.333333)
    assert stats["average_quality_score"] == pytest.approx(73.333333)
    assert stats["average_total_penalty"] == 5.0
    # Campione < CI_MIN_SAMPLE(30): CI sempre nulli
    assert stats["ci_method"] is None
    assert stats["roi_ci95_low"] is None
    assert stats["roi_ci95_high"] is None
    assert stats["hit_rate_ci95_low"] is None
    assert stats["hit_rate_ci95_high"] is None
    assert stats["ci_null_reason"] == "insufficient_sample"


def test_build_performance_stats_at_ci_threshold_populates_ci():
    rows = [
        {"profit_1u_real": 0.9 if i % 2 == 0 else -1.0, "quota_book": 2.0, "won": i % 2 == 0}
        for i in range(30)
    ]
    stats = build_performance_stats(rows, profit_field="profit_1u_real")
    assert stats["stake_count"] == 30
    assert stats["ci_method"] == "wilson_hit_rate_and_normal_mean_profit"
    assert stats["ci_null_reason"] is None
    assert stats["roi_ci95_low"] is not None
    assert stats["roi_ci95_high"] is not None
    assert stats["roi_ci95_low"] < stats["roi_pct"] < stats["roi_ci95_high"]
    assert stats["hit_rate_ci95_low"] is not None
    assert stats["hit_rate_ci95_high"] is not None
    assert 0.0 <= stats["hit_rate_ci95_low"] <= stats["hit_rate_pct"] <= stats["hit_rate_ci95_high"] <= 100.0


def test_build_performance_stats_ignores_rows_without_profit_field():
    rows = [{"profit_1u_real": None}, {"other": 1}]
    stats = build_performance_stats(rows, profit_field="profit_1u_real")
    assert stats["stake_count"] == 0


# ---------------------------------------------------------------------------
# ensure_replay_ready_for_analytics
# ---------------------------------------------------------------------------


def test_ensure_replay_ready_raises_404_when_not_found():
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(CecchinoLabImportError) as exc:
        ensure_replay_ready_for_analytics(db, 999)
    assert exc.value.code == "replay_not_found"
    assert exc.value.status_code == 404


def test_ensure_replay_ready_raises_409_when_not_completed():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=1, status="running")
    with pytest.raises(CecchinoLabImportError) as exc:
        ensure_replay_ready_for_analytics(db, 1)
    assert exc.value.code == "replay_not_completed"
    assert exc.value.status_code == 409
    assert exc.value.message == REPLAY_NOT_COMPLETED_MSG
    assert exc.value.details == {"replay_id": 1, "status": "running"}


@pytest.mark.parametrize("status", ["completed", "completed_with_warnings"])
def test_ensure_replay_ready_returns_replay_when_completed(status):
    db = MagicMock()
    replay = SimpleNamespace(id=1, status=status)
    db.get.return_value = replay
    result = ensure_replay_ready_for_analytics(db, 1)
    assert result is replay


def test_ensure_replay_ready_does_not_write_to_db():
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=1, status="completed")
    ensure_replay_ready_for_analytics(db, 1)
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.delete.assert_not_called()


# ---------------------------------------------------------------------------
# compute_analytics_from_lean_rows — riconciliazione, blockers, stato
# ---------------------------------------------------------------------------


def _mixed_universe() -> list[dict]:
    """Un piccolo universo con tutti e otto i mercati V3 su uno snapshot,
    con un caso scored / gate_failed / unavailable per varietà."""
    rows = [
        _scored_row(source_snapshot_id=1, market_key="HOME", score=85, competition_name="Serie A"),
        _gate_failed_row(source_snapshot_id=1, market_key="DRAW", competition_name="Serie A"),
        _unavailable_row(source_snapshot_id=1, market_key="AWAY", competition_name="Serie A"),
        _scored_row(source_snapshot_id=1, market_key="OVER_2_5", score=70, competition_name="Serie A"),
        _scored_row(source_snapshot_id=1, market_key="UNDER_2_5", score=60, competition_name="Serie A"),
        _scored_row(
            source_snapshot_id=1,
            market_key="ONE_X",
            score=50,
            is_real_book_quote=False,
            is_derived_quote=True,
            quote_quality="derived",
            profit_1u_real=None,
            profit_1u_synthetic=0.5,
            competition_name="Serie A",
        ),
        _scored_row(
            source_snapshot_id=1,
            market_key="X_TWO",
            score=40,
            is_real_book_quote=False,
            is_derived_quote=True,
            quote_quality="derived",
            profit_1u_real=None,
            profit_1u_synthetic=-0.5,
            competition_name="Serie A",
        ),
        _scored_row(
            source_snapshot_id=1,
            market_key="ONE_TWO",
            score=90,
            is_real_book_quote=False,
            is_derived_quote=True,
            quote_quality="derived",
            profit_1u_real=None,
            profit_1u_synthetic=0.9,
            competition_name="Serie A",
        ),
    ]
    return rows


def test_compute_analytics_ready_status_and_reconciliation_ok():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    assert out["schema_version"] == PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION
    assert out["status"] == "ready"
    assert out["blockers"] == []
    assert out["warnings"] == []
    assert out["reconciliation"]["status"] == "ok"
    for check in out["reconciliation"]["checks"]:
        assert check["ok"] is True, check


def test_compute_analytics_universes_counts():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    universes = out["universes"]
    assert universes["ALL_EVALUATIONS"] == 8
    assert universes["SCORED_EVALUATIONS"] == 6
    assert universes["GATE_FAILED_EVALUATIONS"] == 1
    assert universes["UNAVAILABLE_EVALUATIONS"] == 1
    assert universes["REAL_PERFORMANCE_UNIVERSE"] == 3
    assert universes["SYNTHETIC_PERFORMANCE_UNIVERSE"] == 3


def test_compute_analytics_metadata_and_resource_profile():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(
        replay=replay, rows=rows, duration_ms=42, snapshot_batches=1, v2_snapshot_batches=0
    )
    meta = out["metadata"]
    assert meta["formula_recomputed"] is False
    assert meta["analytics_reads_persisted_replay"] is True
    assert meta["source_replay_id"] == 1
    assert meta["source_replay_immutable"] is True
    assert meta["performance_real_and_synthetic_separated"] is True
    assert meta["report_valid"] is True

    rp = out["resource_profile"]
    assert rp["strategy"] == "sql_aggregates_and_keyset_streaming"
    assert rp["rows_read"] == 8
    assert rp["duration_ms"] == 42
    assert rp["snapshot_batches"] == 1
    assert rp["formula_recomputed"] is False


@pytest.mark.parametrize(
    "override_field",
    ["replay_schema_version", "formula_version"],
)
def test_compute_analytics_blocked_when_replay_version_missing(override_field):
    rows = _mixed_universe()
    replay = _replay_from_rows(rows, **{override_field: ""})
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert out["status"] == "blocked"
    codes = {b["code"] for b in out["blockers"]}
    assert f"missing_{override_field}" in codes
    assert out["metadata"]["report_valid"] is False


def test_compute_analytics_blocked_when_results_persisted_mismatch():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows, results_persisted=len(rows) - 1)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert out["status"] == "blocked"
    codes = {b["code"] for b in out["blockers"]}
    assert "results_persisted_mismatch" in codes


def test_compute_analytics_blocked_when_error_count_nonzero():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows, error_count=1)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert out["status"] == "blocked"
    codes = {b["code"] for b in out["blockers"]}
    assert "error_count_nonzero" in codes


def test_compute_analytics_blocked_when_unclassified_count_nonzero():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows, unclassified_count=1)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert out["status"] == "blocked"
    codes = {b["code"] for b in out["blockers"]}
    assert "unclassified_count_nonzero" in codes


def test_compute_analytics_blocked_when_rows_read_mismatch():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)  # evaluations_total/results_persisted == len(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows[:-1])
    assert out["status"] == "blocked"
    codes = {b["code"] for b in out["blockers"]}
    assert "rows_read_mismatch" in codes


def test_compute_analytics_ready_with_warnings_when_replay_completed_with_warnings():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows, status="completed_with_warnings")
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert out["status"] == "ready_with_warnings"
    assert "replay_completed_with_warnings" in out["warnings"]
    assert out["metadata"]["report_valid"] is True


# ---------------------------------------------------------------------------
# compute_analytics_from_lean_rows — dettagli per mercato / soglie / bande
# ---------------------------------------------------------------------------


def test_compute_analytics_by_market_shape_and_counts():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    for mk in V3_MARKET_ORDER:
        assert mk in out["by_market"]

    home = out["by_market"]["HOME"]
    assert home["evaluations_total"] == 1
    assert home["scored"] == 1
    assert home["gate_failed"] == 0
    assert home["unavailable"] == 0
    assert home["quote_type"] == "real"
    assert home["diagnostic_only_if_derived"] is False
    assert home["exclude_from_real_roi"] is False

    one_x = out["by_market"]["ONE_X"]
    assert one_x["quote_type"] == "derived"
    assert one_x["diagnostic_only_if_derived"] is True
    assert one_x["exclude_from_real_roi"] is True
    assert one_x["not_a_real_bet365_quote"] is True

    draw = out["by_market"]["DRAW"]
    assert draw["gate_failed"] == 1
    assert draw["scored"] == 0

    away = out["by_market"]["AWAY"]
    assert away["unavailable"] == 1


def test_compute_analytics_by_threshold_structure():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    thr_home = out["by_threshold"]["HOME"]
    for thr in THRESHOLDS:
        key = f"score_ge_{thr}"
        assert key in thr_home
        entry = thr_home[key]
        assert "eligible_scored_rows" in entry
        assert "real" in entry and "synthetic" in entry
        assert "first_half_real" in entry and "second_half_real" in entry
        assert "competitions_positive" in entry

    # HOME score=85 -> eligibile per tutte le soglie <= 85, non per 90
    assert thr_home["score_ge_20"]["eligible_scored_rows"] == 1
    assert thr_home["score_ge_80"]["eligible_scored_rows"] == 1
    assert thr_home["score_ge_90"]["eligible_scored_rows"] == 0


def test_compute_analytics_gate_analysis_reason_codes():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    gate = out["gate_analysis"]
    assert gate["gate_passed"] == 6
    assert gate["gate_failed"] == 1
    assert gate["gate_pass_rate"] == pytest.approx(85.714286, rel=1e-4)
    assert gate["reason_codes"] == {"no_positive_edge": 1}
    assert gate["reason_codes_by_market"] == {"DRAW": {"no_positive_edge": 1}}
    assert gate["edge_non_positive"] == 1
    assert gate["vantaggio_non_positive"] == 1
    assert gate["both_non_positive"] == 1
    assert gate["gate_failed_not_score_zero"] is True
    assert "HOME" in gate["gate_failed_performance_diagnostic"]["by_market"]


def test_compute_analytics_score_distribution_and_by_score_band():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    dist = out["score_distribution"]
    assert dist["scored"] == 6
    assert dist["gate_failed"] == 1
    assert dist["unavailable"] == 1
    assert dist["gate_failed_not_mapped_to_0_19"] is True
    assert set(out["by_score_band"].keys()) == set(SCORE_BANDS)
    # HOME score 85 -> banda 80-89
    assert out["by_score_band"]["80-89"]["n"] >= 1


def test_compute_analytics_penalties_structure():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    penalties = out["penalties"]
    assert penalties["descriptive_observational_analysis"] is True
    assert set(penalties["fields"].keys()) == {
        "probability_risk_penalty",
        "opposite_market_pressure_penalty",
        "extreme_divergence_penalty",
        "family_ambiguity_penalty",
        "quote_quality_penalty",
    }
    fam_amb = penalties["fields"]["family_ambiguity_penalty"]
    # Tutte le righe scored hanno family_ambiguity_penalty = 5.0 (default fixture)
    assert fam_amb["count_available"] == 6
    assert fam_amb["count_applied"] == 6
    assert fam_amb["application_rate"] == 100.0
    assert fam_amb["mean"] == 5.0
    assert fam_amb["bands"].get(">0-5") == 6
    assert isinstance(penalties["total_penalty_bands"], dict)


def test_compute_analytics_value_quality_matrix_has_25_cells():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    vq = out["value_quality_matrix"]
    assert len(vq) == len(VQ_BANDS) * len(VQ_BANDS)
    for key, cell in vq.items():
        assert cell["not_an_automatic_strategy"] is True
        assert "n" in cell and "real" in cell and "synthetic" in cell


def test_compute_analytics_family_decisions_integration():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    fam_block = out["family_decisions"]
    assert set(fam_block["summary"].keys()) == {
        FAMILY_MATCH_WINNER_FT,
        FAMILY_GOALS_FT_2_5,
        FAMILY_DOUBLE_CHANCE,
    }
    assert fam_block["diagnostic_family_selection"] is True
    assert fam_block["not_operational_strategy"] is True
    assert fam_block["do_not_sum_across_families"] is True
    assert fam_block["decision_count"] == len(out["family_decisions_rows"])

    mw = fam_block["summary"][FAMILY_MATCH_WINNER_FT]
    assert mw["snapshot_decisions"] == 1
    assert mw["selections"] == 1
    assert mw["selected_market_distribution"] == {"HOME": 1}
    assert mw["diagnostic_family_selection"] is True

    dc = fam_block["summary"][FAMILY_DOUBLE_CHANCE]
    # DOUBLE_CHANCE usa il profitto sintetico, mai quello reale
    assert dc["performance"]["stake_count"] >= 0


def test_compute_analytics_temporal_and_competition_stability_present():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows)

    temporal = out["temporal_stability"]
    assert temporal["split_rule"] == "per_competition_snapshot_floor_n_over_2"
    for mk in V3_MARKET_ORDER:
        assert mk in temporal
        assert "direction_consistency" in temporal[mk]

    comp_stability = out["competition_stability"]
    for mk in V3_MARKET_ORDER:
        assert mk in comp_stability
        if "Serie A" in comp_stability[mk]:
            entry = comp_stability[mk]["Serie A"]
            assert "sample_flag" in entry
            assert entry["sample_flag"] == "insufficient"  # 1 sola riga per mercato


def test_compute_analytics_v2_v3_comparison_structure_without_v2_data():
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows, v2_markets_by_snapshot=None)
    cmp = out["v2_v3_comparison"]
    assert cmp["diagnostic_only"] is True
    assert cmp["formula_recomputed"] is False
    assert cmp["join_coverage"]["v2_entries"] == 0
    assert cmp["join_coverage"]["missing_v2"] == len(rows)
    assert cmp["transition_matrix"] == {"unavailable": len(rows)}
    assert "Non dichiarare V3 migliore" in cmp["warning"]


def test_compute_analytics_v2_v3_comparison_transitions():
    rows = [
        _scored_row(source_snapshot_id=1, market_key="HOME", score=85),
        _gate_failed_row(source_snapshot_id=2, market_key="HOME"),
    ]
    replay = _replay_from_rows(rows)
    v2_map = {
        1: [
            {
                "market_key": "HOME",
                "status": "available",
                "score": 40,
                "positive_value_gate": {"status": "passed", "reason_codes": []},
                "class": "bassa",
            }
        ],
        2: [
            {
                "market_key": "HOME",
                "status": "available",
                "score": None,
                "positive_value_gate": {"status": "failed", "reason_codes": ["no_positive_edge"]},
            }
        ],
    }
    out = compute_analytics_from_lean_rows(replay=replay, rows=rows, v2_markets_by_snapshot=v2_map)
    cmp = out["v2_v3_comparison"]
    assert cmp["join_coverage"]["joined"] == 2
    assert cmp["join_coverage"]["missing_v2"] == 0
    assert cmp["transition_matrix"]["gate_to_gate"] == 1
    # V2 score 40 (banda 40-59) -> V3 score 85 (banda 80-89): salita di banda
    assert cmp["transition_matrix"]["score_band_up"] == 1


# ---------------------------------------------------------------------------
# build_family_decisions
# ---------------------------------------------------------------------------


def test_build_family_decisions_picks_best_by_score_then_tiebreak():
    rows = [
        _scored_row(source_snapshot_id=1, market_key="HOME", score=85, quality_score=80, value_score=70, edge_pct=8),
        _scored_row(source_snapshot_id=1, market_key="DRAW", score=60, quality_score=80, value_score=70, edge_pct=8),
        _scored_row(source_snapshot_id=1, market_key="AWAY", score=85, quality_score=80, value_score=70, edge_pct=8),
    ]
    decisions = build_family_decisions(rows)
    mw = next(d for d in decisions if d["family"] == FAMILY_MATCH_WINNER_FT)
    # HOME e AWAY pareggiano su tutto: vince l'ordine canonico (HOME prima di AWAY)
    assert mw["selected_market"] == "HOME"
    assert mw["tie_count"] == 1
    assert mw["tie_break_used"] == (
        "score_desc;quality_score_desc;value_score_desc;edge_pct_desc;canonical_market_order"
    )
    assert mw["candidates_available"] == 3
    assert mw["diagnostic_family_selection"] is True
    assert mw["not_operational_strategy"] is True


def test_build_family_decisions_no_selection_when_all_gate_failed():
    rows = [
        _gate_failed_row(source_snapshot_id=2, market_key="HOME"),
        _gate_failed_row(source_snapshot_id=2, market_key="DRAW"),
        _gate_failed_row(source_snapshot_id=2, market_key="AWAY"),
    ]
    decisions = build_family_decisions(rows)
    mw = next(d for d in decisions if d["family"] == FAMILY_MATCH_WINNER_FT)
    assert mw["selected_market"] is None
    assert mw["no_selection_reason"] == "no_scored_candidates"
    assert mw["candidates_available"] == 0


def test_build_family_decisions_skips_family_absent_from_snapshot():
    rows = [
        _scored_row(source_snapshot_id=3, market_key="OVER_2_5", score=70),
        _scored_row(source_snapshot_id=3, market_key="UNDER_2_5", score=60),
    ]
    decisions = build_family_decisions(rows)
    families_present = {d["family"] for d in decisions}
    assert families_present == {FAMILY_GOALS_FT_2_5}


def test_build_family_decisions_double_chance_uses_synthetic_profit_only():
    rows = [
        _scored_row(
            source_snapshot_id=4,
            market_key="ONE_X",
            score=75,
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=0.8,
        ),
        _scored_row(
            source_snapshot_id=4,
            market_key="X_TWO",
            score=60,
            is_real_book_quote=False,
            is_derived_quote=True,
            profit_1u_real=None,
            profit_1u_synthetic=-0.2,
        ),
    ]
    decisions = build_family_decisions(rows)
    dc = next(d for d in decisions if d["family"] == FAMILY_DOUBLE_CHANCE)
    assert dc["selected_market"] == "ONE_X"
    assert dc["profit_1u_real"] is None
    assert dc["profit_1u_synthetic"] == 0.8


def test_build_family_decisions_ignores_non_family_markets():
    rows = [_scored_row(source_snapshot_id=5, market_key="HOME", score=85)]
    decisions = build_family_decisions(rows)
    families_present = {d["family"] for d in decisions}
    assert FAMILY_GOALS_FT_2_5 not in families_present
    assert FAMILY_DOUBLE_CHANCE not in families_present


# ---------------------------------------------------------------------------
# build_temporal_halves_by_competition
# ---------------------------------------------------------------------------


def test_build_temporal_halves_floor_split_per_competition():
    base = _utcnow()
    rows = [
        {"competition_name": "A", "source_snapshot_id": 1, "kickoff_at": base, "chronological_order": 1},
        {"competition_name": "A", "source_snapshot_id": 2, "kickoff_at": base + timedelta(days=1), "chronological_order": 2},
        {"competition_name": "A", "source_snapshot_id": 3, "kickoff_at": base + timedelta(days=2), "chronological_order": 3},
    ]
    halves = build_temporal_halves_by_competition(rows)
    # floor(3/2) = 1 -> solo il primo snapshot in first_half
    assert halves["A"] == {1: "first_half", 2: "second_half", 3: "second_half"}


def test_build_temporal_halves_independent_per_competition():
    base = _utcnow()
    rows = [
        {"competition_name": "A", "source_snapshot_id": 1, "kickoff_at": base, "chronological_order": 1},
        {"competition_name": "A", "source_snapshot_id": 2, "kickoff_at": base + timedelta(days=1), "chronological_order": 2},
        {"competition_name": "B", "source_snapshot_id": 10, "kickoff_at": base, "chronological_order": 1},
        {"competition_name": "B", "source_snapshot_id": 11, "kickoff_at": base + timedelta(days=1), "chronological_order": 2},
        {"competition_name": "B", "source_snapshot_id": 12, "kickoff_at": base + timedelta(days=2), "chronological_order": 3},
    ]
    halves = build_temporal_halves_by_competition(rows)
    # floor(2/2) = 1 -> il primo snapshot cronologico va in first_half
    assert halves["A"] == {1: "first_half", 2: "second_half"}
    assert halves["B"] == {10: "first_half", 11: "second_half", 12: "second_half"}


def test_build_temporal_halves_deduplicates_same_snapshot_id():
    base = _utcnow()
    rows = [
        {"competition_name": "A", "source_snapshot_id": 1, "kickoff_at": base, "chronological_order": 1},
        {"competition_name": "A", "source_snapshot_id": 1, "kickoff_at": base, "chronological_order": 1},
        {"competition_name": "A", "source_snapshot_id": 2, "kickoff_at": base + timedelta(days=1), "chronological_order": 2},
    ]
    halves = build_temporal_halves_by_competition(rows)
    assert len(halves["A"]) == 2


# ---------------------------------------------------------------------------
# Cache in-memory (_cache_key, _cache_set, _cache_get, clear)
# ---------------------------------------------------------------------------


def test_cache_get_returns_none_when_absent():
    assert _cache_get("missing-key") is None


def test_cache_set_and_get_round_trip():
    _cache_set("my-key", {"a": 1}, ttl=60)
    assert _cache_get("my-key") == {"a": 1}


def test_cache_expires_after_ttl():
    _cache_set("expiring-key", "value", ttl=-1)
    assert _cache_get("expiring-key") is None


def test_clear_purchasability_v3_analytics_cache_empties_cache():
    _cache_set("k1", "v1", ttl=60)
    _cache_set("k2", "v2", ttl=60)
    clear_purchasability_v3_analytics_cache()
    assert _cache_get("k1") is None
    assert _cache_get("k2") is None


def test_cache_key_is_deterministic_and_sensitive_to_inputs():
    base_kwargs = dict(
        replay_id=1,
        kind=CACHE_KIND_SUMMARY,
        completed_at=_utcnow(),
        formula_version="v1",
        runtime_commit="abc",
    )
    key1 = _cache_key(**base_kwargs)
    key2 = _cache_key(**base_kwargs)
    assert key1 == key2

    assert _cache_key(**{**base_kwargs, "replay_id": 2}) != key1
    assert _cache_key(**{**base_kwargs, "kind": "export_full"}) != key1
    assert _cache_key(**{**base_kwargs, "completed_at": _utcnow() + timedelta(seconds=1)}) != key1
    assert _cache_key(**{**base_kwargs, "formula_version": "v2"}) != key1
    assert _cache_key(**{**base_kwargs, "runtime_commit": "def"}) != key1


def test_cache_key_handles_none_completed_at_and_versions():
    key = _cache_key(
        replay_id=1,
        kind=CACHE_KIND_SUMMARY,
        completed_at=None,
        formula_version=None,
        runtime_commit=None,
    )
    assert isinstance(key, str)
    assert key.startswith("1|summary|")


# ---------------------------------------------------------------------------
# Endpoint GET /cecchino-lab/purchasability-v3-replays/{id}/analytics
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(cecchino_lab.router)
    return app


def test_endpoint_analytics_200(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    fake_payload = {"schema_version": PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION, "status": "ready"}
    monkeypatch.setattr(
        cecchino_lab, "get_purchasability_v3_replay_analytics", lambda db_, rid: fake_payload
    )

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/analytics")
    assert r.status_code == 200
    assert r.json() == fake_payload


def test_endpoint_analytics_404_replay_not_found(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def boom(db_, rid):
        raise CecchinoLabImportError("replay_not_found", "non trovato", status_code=404)

    monkeypatch.setattr(cecchino_lab, "get_purchasability_v3_replay_analytics", boom)

    r = client.get("/cecchino-lab/purchasability-v3-replays/999/analytics")
    assert r.status_code == 404
    body = r.json()
    assert body["status"] == "error"
    assert body["error"] == "replay_not_found"


def test_endpoint_analytics_409_replay_not_completed(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def boom(db_, rid):
        raise CecchinoLabImportError(
            "replay_not_completed", REPLAY_NOT_COMPLETED_MSG, status_code=409, details={"replay_id": rid}
        )

    monkeypatch.setattr(cecchino_lab, "get_purchasability_v3_replay_analytics", boom)

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/analytics")
    assert r.status_code == 409
    body = r.json()
    assert body["status"] == "error"
    assert body["error"] == "replay_not_completed"
    assert body["message"] == REPLAY_NOT_COMPLETED_MSG


# ---------------------------------------------------------------------------
# Invarianti di sola lettura / niente ricalcolo formula
# ---------------------------------------------------------------------------


def test_no_formula_recalculation_call_in_analytics_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "calculate_purchasability_v3_batch" not in src


def test_no_db_writes_in_analytics_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_analytics as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "db.commit(" not in src
    assert "db.add(" not in src
    assert "db.flush(" not in src
    assert "db.delete(" not in src


def test_compute_analytics_from_lean_rows_is_pure_no_db_argument_needed():
    """compute_analytics_from_lean_rows non riceve/usa una sessione DB: è puro sui dati lean."""
    rows = _mixed_universe()
    replay = _replay_from_rows(rows)
    out1 = compute_analytics_from_lean_rows(replay=replay, rows=list(rows))
    out2 = compute_analytics_from_lean_rows(replay=replay, rows=list(rows))
    assert out1["universes"] == out2["universes"]
    assert out1["reconciliation"] == out2["reconciliation"]
