"""Test del modulo export ZIP autonomo del Replay Acquistabilità V3 (STEP 3C.1).

Copertura:
- schema version pubblico e contenuto delle 15 regole in `AI_INSTRUCTIONS_MD`
- validazione modalità (`analysis` / `full_archive`) e propagazione errori replay
  (non trovato / non completato) da `ensure_replay_ready_for_analytics`
- `write_purchasability_v3_replay_report_zip` con `analytics=`/`lean_rows=` iniettati
  (nessuno streaming DB reale): elenco file, manifest, report_index, conteggi righe
- differenze tra mode=analysis e mode=full_archive
- fallback quando `analytics`/`lean_rows` sono `None` (delega alle funzioni di lettura)
- `build_purchasability_v3_replay_report_zip_bytes` (bytes + filename)
- `build_purchasability_v3_replay_report_response` (StreamingResponse + headers)
- endpoint `GET /cecchino-lab/purchasability-v3-replays/{id}/report`
- invarianti di sola lettura (nessun ricalcolo formula, nessuna scrittura DB)
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
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
    PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION,
    REPLAY_NOT_COMPLETED_MSG,
    classify_calc_bucket,
    clear_purchasability_v3_analytics_cache,
    compute_analytics_from_lean_rows,
)
from app.services.cecchino_data_lab.historical_purchasability_v3_replay_export import (
    AI_INSTRUCTIONS_MD,
    ANALYSIS_CHECKLIST_MD,
    PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION,
    README_MD,
    SCHEMA_MD,
    build_purchasability_v3_replay_report_response,
    build_purchasability_v3_replay_report_zip_bytes,
    write_purchasability_v3_replay_report_zip,
)


# ---------------------------------------------------------------------------
# Helper di fixture (analoghi a test_..._analytics.py, file volutamente autonomo)
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
    family_ambiguity_penalty: float | None = 0.0,
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


def _gate_failed_row(**kw) -> dict:
    kw.setdefault("score", None)
    kw.setdefault("gate_status", "failed")
    kw.setdefault("gate_reason_codes_json", ["no_positive_edge"])
    kw.setdefault("profit_1u_real", None)
    kw.setdefault("profit_1u_synthetic", None)
    kw.setdefault("won", None)
    kw.setdefault("score_class", None)
    return _row(**kw)


def _replay_from_rows(rows: list[dict], **overrides) -> SimpleNamespace:
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


def _db_with_replay(replay: SimpleNamespace | None) -> MagicMock:
    db = MagicMock()
    db.get.return_value = replay
    return db


def _sample_rows() -> list[dict]:
    return [
        _row(source_snapshot_id=1, market_key="HOME", score=85, competition_name="Serie A"),
        _row(source_snapshot_id=1, market_key="OVER_2_5", score=70, competition_name="Serie A"),
        _gate_failed_row(source_snapshot_id=1, market_key="DRAW", competition_name="Serie A"),
        _row(
            source_snapshot_id=2,
            market_key="HOME",
            score=60,
            competition_name="Premier League",
            profit_1u_real=-1.0,
            won=False,
        ),
    ]


def _sample_analytics_and_rows(**replay_overrides):
    rows = _sample_rows()
    replay = _replay_from_rows(rows, **replay_overrides)
    analytics = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    return replay, analytics, rows


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_purchasability_v3_analytics_cache()
    yield
    clear_purchasability_v3_analytics_cache()


@pytest.fixture(autouse=True)
def _patch_resolve_code_revision(monkeypatch):
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as exp

    monkeypatch.setattr(
        exp,
        "resolve_code_revision",
        lambda: {"git_commit": "test", "git_commit_source": "test"},
    )
    yield


# ---------------------------------------------------------------------------
# Costanti / contenuto istruzioni AI
# ---------------------------------------------------------------------------


def test_export_schema_version_constant():
    assert PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION == "cecchino_lab_purchasability_v3_export_v2"


def test_ai_instructions_contains_all_16_rules():
    for n in range(1, 17):
        assert f"{n}. " in AI_INSTRUCTIONS_MD, f"regola {n} mancante in AI_INSTRUCTIONS_MD"


def test_ai_instructions_key_rules_content():
    assert "formula_recomputed=false" in AI_INSTRUCTIONS_MD
    assert "Gate failed" in AI_INSTRUCTIONS_MD
    assert "profit_1u_synthetic" in AI_INSTRUCTIONS_MD
    assert "not_a_real_bet365_quote" in AI_INSTRUCTIONS_MD
    assert "diagnostic_family_selection" in AI_INSTRUCTIONS_MD
    assert "technical_aggregate_only" in AI_INSTRUCTIONS_MD
    assert "esclusivamente Acquistabilità V3" in AI_INSTRUCTIONS_MD or "esclusivamente" in AI_INSTRUCTIONS_MD
    assert "v2_v3_comparison" not in AI_INSTRUCTIONS_MD
    assert "2022/2023" in AI_INSTRUCTIONS_MD


def test_static_docs_are_non_empty_and_distinct():
    docs = [AI_INSTRUCTIONS_MD, SCHEMA_MD, README_MD, ANALYSIS_CHECKLIST_MD]
    for d in docs:
        assert isinstance(d, str) and len(d.strip()) > 0
    assert len({id(d) for d in docs}) == 4


# ---------------------------------------------------------------------------
# Validazione modalità e propagazione errori replay
# ---------------------------------------------------------------------------


def test_write_zip_invalid_mode_raises_400():
    replay = _replay_from_rows(_sample_rows())
    db = _db_with_replay(replay)
    with pytest.raises(CecchinoLabImportError) as exc:
        write_purchasability_v3_replay_report_zip(db, 1, io.BytesIO(), mode="bogus")
    assert exc.value.code == "invalid_report_mode"
    assert exc.value.status_code == 400


def test_build_zip_bytes_invalid_mode_raises_400():
    replay = _replay_from_rows(_sample_rows())
    db = _db_with_replay(replay)
    with pytest.raises(CecchinoLabImportError) as exc:
        build_purchasability_v3_replay_report_zip_bytes(db, 1, mode="not-a-mode")
    assert exc.value.code == "invalid_report_mode"
    assert exc.value.status_code == 400


def test_write_zip_replay_not_found_raises_404():
    db = _db_with_replay(None)
    with pytest.raises(CecchinoLabImportError) as exc:
        write_purchasability_v3_replay_report_zip(db, 999, io.BytesIO())
    assert exc.value.code == "replay_not_found"
    assert exc.value.status_code == 404


def test_write_zip_replay_not_completed_raises_409():
    db = _db_with_replay(SimpleNamespace(id=1, status="running"))
    with pytest.raises(CecchinoLabImportError) as exc:
        write_purchasability_v3_replay_report_zip(db, 1, io.BytesIO())
    assert exc.value.code == "replay_not_completed"
    assert exc.value.status_code == 409
    assert exc.value.message == REPLAY_NOT_COMPLETED_MSG


def test_build_zip_bytes_replay_not_completed_raises_409():
    db = _db_with_replay(SimpleNamespace(id=1, status="failed"))
    with pytest.raises(CecchinoLabImportError) as exc:
        build_purchasability_v3_replay_report_zip_bytes(db, 1)
    assert exc.value.code == "replay_not_completed"


# ---------------------------------------------------------------------------
# write_purchasability_v3_replay_report_zip / build_..._zip_bytes — contenuto
# ---------------------------------------------------------------------------

_EXPECTED_JSON_FILES = (
    "summary.json",
    "reconciliation.json",
    "score_distribution.json",
    "gate_analysis.json",
    "performance_real.json",
    "performance_synthetic.json",
    "penalties.json",
    "value_quality_matrix.json",
    "family_decisions_summary.json",
    "temporal_stability.json",
    "competition_stability_summary.json",
    "manifest.json",
    "report_index.json",
)
_EXPECTED_JSONL_FILES = (
    "by_market.jsonl",
    "by_score_band.jsonl",
    "by_threshold.jsonl",
    "by_competition_market.jsonl",
    "family_decisions.jsonl",
    "replay_results_compact.jsonl",
)
_EXPECTED_MD_FILES = ("AI_INSTRUCTIONS.md", "SCHEMA.md", "README.md", "ANALYSIS_CHECKLIST.md")


def test_build_zip_bytes_analysis_mode_contains_all_expected_files():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)

    filename, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    assert filename == "cecchino-purchasability-v3-replay-1-analysis.zip"
    assert isinstance(data, bytes)
    assert len(data) > 0

    zf = zipfile.ZipFile(io.BytesIO(data))
    names = set(zf.namelist())
    for name in _EXPECTED_JSON_FILES + _EXPECTED_JSONL_FILES + _EXPECTED_MD_FILES:
        assert name in names, f"file mancante nello zip: {name}"
    assert "replay_results_full.jsonl" not in names


def test_write_zip_full_archive_mode_adds_full_jsonl():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    dest = io.BytesIO()

    filename, size = write_purchasability_v3_replay_report_zip(
        db, 1, dest, mode="full_archive", analytics=analytics, lean_rows=rows
    )
    assert filename == "cecchino-purchasability-v3-replay-1-full.zip"
    assert size == len(dest.getvalue())

    zf = zipfile.ZipFile(dest)
    names = set(zf.namelist())
    assert "replay_results_full.jsonl" in names
    full_lines = zf.read("replay_results_full.jsonl").decode("utf-8").strip().splitlines()
    assert len(full_lines) == len(rows)
    full_row = json.loads(full_lines[0])
    assert "gate_reason_codes_json" in full_row
    assert "formula_payload_sha256" in full_row
    assert "raw_score" in full_row


def test_manifest_json_fields():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(zf.read("manifest.json"))

    assert manifest["analytics_schema_version"] == PURCHASABILITY_V3_ANALYTICS_SCHEMA_VERSION
    assert manifest["export_schema_version"] == PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION
    assert manifest["replay_id"] == 1
    assert manifest["source_scan_run_id"] == 10
    assert manifest["replay_status"] == "completed"
    assert manifest["formula_version"] == "formula_v1"
    assert manifest["report_generator_git_commit"] == "test"
    assert manifest["report_generator_git_commit_source"] == "test"
    assert manifest["rows"] == len(rows)
    assert manifest["scored"] == analytics["universes"]["SCORED_EVALUATIONS"]
    assert manifest["gate_failed"] == analytics["universes"]["GATE_FAILED_EVALUATIONS"]
    assert manifest["unavailable"] == analytics["universes"]["UNAVAILABLE_EVALUATIONS"]
    assert manifest["formula_recomputed"] is False
    assert manifest["performance_real_and_synthetic_separated"] is True
    assert manifest["export_validity"] == "valid"
    assert manifest["no_old_v2_primary_file"] is True
    assert manifest["official_purchasability_version"] == "V3"
    assert manifest["official_source_type"] == "historical_replay"
    assert manifest["source_replay_id"] == 1
    assert manifest["legacy_purchasability_included"] is False
    assert manifest["legacy_purchasability_read"] is False
    assert manifest["legacy_fallback_allowed"] is False
    assert isinstance(manifest["file_row_counts"], dict)
    assert manifest["file_row_counts"]["replay_results_compact.jsonl"] == len(rows)
    for name in _EXPECTED_MD_FILES:
        assert name in manifest["files"]


def test_report_index_json_fields():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    report_index = json.loads(zf.read("report_index.json"))

    assert report_index["mode"] == "analysis"
    assert report_index["replay_id"] == 1
    assert report_index["source_scan_run_id"] == 10
    assert report_index["analytics_status"] == analytics["status"]
    assert report_index["reconciliation_status"] == analytics["reconciliation"]["status"]
    assert report_index["formula_recomputed"] is False
    assert report_index["recommended_for_chatgpt"] is True
    assert "manifest.json" in report_index["files"]


def test_report_index_recommended_for_chatgpt_false_for_full_archive():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="full_archive", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    report_index = json.loads(zf.read("report_index.json"))
    assert report_index["mode"] == "full_archive"
    assert report_index["recommended_for_chatgpt"] is False


def test_summary_json_excludes_family_decisions_rows_and_has_validity_flags():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    summary = json.loads(zf.read("summary.json"))

    assert "family_decisions_rows" not in summary
    assert summary["export_validity"] == "valid"
    assert summary["report_valid"] is True
    assert summary["status"] == analytics["status"]


def test_diagnostic_failed_analytics_marks_export_invalid():
    rows = _sample_rows()
    # Riconciliazione forzata a fallire: results_persisted incoerente coi conteggi bucket
    replay = _replay_from_rows(rows, results_persisted=len(rows) - 1)
    analytics = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    assert analytics["status"] == "blocked"

    replay_ok = _replay_from_rows(rows)  # replay "sano" solo per superare ensure_replay_ready
    db = _db_with_replay(replay_ok)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(zf.read("manifest.json"))
    summary = json.loads(zf.read("summary.json"))
    report_index = json.loads(zf.read("report_index.json"))

    assert manifest["export_validity"] == "diagnostic_failed"
    assert summary["export_validity"] == "diagnostic_failed"
    assert summary["report_valid"] is False
    assert report_index["analytics_status"] == "blocked"


def test_by_market_jsonl_rows_have_market_key():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    lines = zf.read("by_market.jsonl").decode("utf-8").strip().splitlines()
    assert len(lines) == 8  # otto mercati V3
    parsed = [json.loads(line) for line in lines]
    assert {"HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5", "ONE_X", "X_TWO", "ONE_TWO"} == {
        p["market_key"] for p in parsed
    }
    home = next(p for p in parsed if p["market_key"] == "HOME")
    assert "scored" in home and "evaluations_total" in home


def test_by_threshold_jsonl_rows_have_market_key_and_threshold():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    lines = zf.read("by_threshold.jsonl").decode("utf-8").strip().splitlines()
    assert len(lines) == 8 * 6  # 8 mercati * 6 soglie
    first = json.loads(lines[0])
    assert "market_key" in first
    assert "threshold" in first
    assert first["threshold"].startswith("score_ge_")


def test_by_competition_market_jsonl_rows_have_competition_name():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    lines = zf.read("by_competition_market.jsonl").decode("utf-8").strip().splitlines()
    parsed = [json.loads(line) for line in lines]
    assert any(p["competition_name"] == "Serie A" for p in parsed)
    assert any(p["competition_name"] == "Premier League" for p in parsed)
    for p in parsed:
        assert "market_key" in p


def test_family_decisions_jsonl_matches_analytics_rows():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    lines = zf.read("family_decisions.jsonl").decode("utf-8").strip().splitlines()
    assert len(lines) == len(analytics["family_decisions_rows"])


def test_replay_results_compact_jsonl_row_shape():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    lines = zf.read("replay_results_compact.jsonl").decode("utf-8").strip().splitlines()
    assert len(lines) == len(rows)
    compact = json.loads(lines[0])
    assert compact["replay_id"] == 1
    assert compact["market_key"] == "HOME"
    assert "gate_reason_codes_json" not in compact  # solo nel full archive


def test_ai_instructions_md_content_matches_constant_verbatim():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    content = zf.read("AI_INSTRUCTIONS.md").decode("utf-8")
    assert content == AI_INSTRUCTIONS_MD
    # Verifica robustezza UTF-8 su caratteri accentati italiani
    assert "Acquistabilità" in content


def test_json_files_use_ensure_ascii_false_for_italian_accents():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    raw = zf.read("report_index.json").decode("utf-8")
    assert "Acquistabilit\\u00e0" not in raw
    assert "Acquistabilità" in raw


# ---------------------------------------------------------------------------
# Fallback quando analytics=None / lean_rows=None
# ---------------------------------------------------------------------------


def test_write_zip_falls_back_to_get_analytics_when_none(monkeypatch):
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as exp

    rows = _sample_rows()
    replay = _replay_from_rows(rows)
    analytics = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    db = _db_with_replay(replay)

    calls = {"analytics": 0, "rows": 0}

    def fake_get_analytics(db_, replay_id):
        calls["analytics"] += 1
        return analytics

    def fake_iter_rows(db_, replay_id):
        calls["rows"] += 1
        return iter(rows)

    monkeypatch.setattr(exp, "get_purchasability_v3_replay_analytics", fake_get_analytics)
    monkeypatch.setattr(exp, "iter_lean_replay_result_rows", fake_iter_rows)

    filename, size = write_purchasability_v3_replay_report_zip(db, 1, io.BytesIO())
    assert calls["analytics"] == 1
    assert calls["rows"] == 1
    assert filename == "cecchino-purchasability-v3-replay-1-analysis.zip"
    assert size > 0


def test_write_zip_uses_injected_analytics_without_calling_get_analytics(monkeypatch):
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as exp

    rows = _sample_rows()
    replay = _replay_from_rows(rows)
    analytics = compute_analytics_from_lean_rows(replay=replay, rows=rows)
    db = _db_with_replay(replay)

    def boom(*_a, **_k):
        raise AssertionError("get_purchasability_v3_replay_analytics non deve essere chiamata")

    def boom_rows(*_a, **_k):
        raise AssertionError("iter_lean_replay_result_rows non deve essere chiamata")

    monkeypatch.setattr(exp, "get_purchasability_v3_replay_analytics", boom)
    monkeypatch.setattr(exp, "iter_lean_replay_result_rows", boom_rows)

    filename, size = write_purchasability_v3_replay_report_zip(
        db, 1, io.BytesIO(), analytics=analytics, lean_rows=rows
    )
    assert size > 0


# ---------------------------------------------------------------------------
# build_purchasability_v3_replay_report_response
# ---------------------------------------------------------------------------


def test_build_response_analysis_mode_headers(monkeypatch):
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as exp

    db = _db_with_replay(SimpleNamespace(id=1, status="completed"))

    def fake_write(
        db_, replay_id, dest, *, mode="analysis", analytics=None, lean_rows=None, filename_override=None
    ):
        dest.write(b"PK-fake-zip-bytes")
        return f"fake-{replay_id}-{mode}.zip", 17

    monkeypatch.setattr(exp, "write_purchasability_v3_replay_report_zip", fake_write)

    resp = build_purchasability_v3_replay_report_response(db, 1, mode="analysis")
    assert resp.media_type == "application/zip"
    headers = dict(resp.headers)
    assert headers["content-disposition"] == 'attachment; filename="fake-1-analysis.zip"'
    assert headers["x-report-mode"] == "analysis"
    assert headers["x-report-bytes"] == "17"
    assert headers["x-export-schema-version"] == PURCHASABILITY_V3_EXPORT_SCHEMA_VERSION
    assert "x-report-warning" not in headers


def test_build_response_invalid_mode_raises_before_touching_db():
    db = MagicMock()
    with pytest.raises(CecchinoLabImportError) as exc:
        build_purchasability_v3_replay_report_response(db, 1, mode="bogus")
    assert exc.value.code == "invalid_report_mode"
    assert exc.value.status_code == 400
    db.get.assert_not_called()


def test_build_response_replay_not_found_propagates_404():
    db = _db_with_replay(None)
    with pytest.raises(CecchinoLabImportError) as exc:
        build_purchasability_v3_replay_report_response(db, 999, mode="analysis")
    assert exc.value.code == "replay_not_found"
    assert exc.value.status_code == 404


def test_build_response_full_archive_warning_header_ascii(monkeypatch):
    """Header X-Report-Warning full_archive deve essere ASCII-safe (latin-1)."""
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as exp

    db = _db_with_replay(SimpleNamespace(id=1, status="completed"))

    def fake_write(
        db_, replay_id, dest, *, mode="analysis", analytics=None, lean_rows=None, filename_override=None
    ):
        dest.write(b"PK-fake-zip-bytes")
        return f"fake-{replay_id}-{mode}.zip", 17

    monkeypatch.setattr(exp, "write_purchasability_v3_replay_report_zip", fake_write)

    resp = build_purchasability_v3_replay_report_response(db, 1, mode="full_archive")
    warning = resp.headers.get("X-Report-Warning") or ""
    assert "analysis" in warning
    warning.encode("latin-1")


# ---------------------------------------------------------------------------
# Endpoint GET /cecchino-lab/purchasability-v3-replays/{id}/report
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(cecchino_lab.router)
    return app


def test_endpoint_report_200_analysis_mode_default(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def fake_response(db_, replay_id, *, mode="analysis"):
        from fastapi.responses import StreamingResponse

        assert mode == "analysis"

        def _iter():
            yield b"zip-bytes"

        return StreamingResponse(
            _iter(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="report.zip"',
                "X-Report-Mode": mode,
            },
        )

    monkeypatch.setattr(cecchino_lab, "build_purchasability_v3_replay_report_response", fake_response)

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/report")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["x-report-mode"] == "analysis"
    assert r.content == b"zip-bytes"


def test_endpoint_report_mode_query_param_forwarded(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    captured = {}

    def fake_response(db_, replay_id, *, mode="analysis"):
        from fastapi.responses import StreamingResponse

        captured["mode"] = mode
        return StreamingResponse(iter([b""]), media_type="application/zip")

    monkeypatch.setattr(cecchino_lab, "build_purchasability_v3_replay_report_response", fake_response)

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/report?mode=full_archive")
    assert r.status_code == 200
    assert captured["mode"] == "full_archive"


def test_endpoint_report_404_replay_not_found(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def boom(db_, replay_id, *, mode="analysis"):
        raise CecchinoLabImportError("replay_not_found", "non trovato", status_code=404)

    monkeypatch.setattr(cecchino_lab, "build_purchasability_v3_replay_report_response", boom)

    r = client.get("/cecchino-lab/purchasability-v3-replays/999/report")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_endpoint_report_409_replay_not_completed(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def boom(db_, replay_id, *, mode="analysis"):
        raise CecchinoLabImportError("replay_not_completed", REPLAY_NOT_COMPLETED_MSG, status_code=409)

    monkeypatch.setattr(cecchino_lab, "build_purchasability_v3_replay_report_response", boom)

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/report")
    assert r.status_code == 409
    assert r.json()["detail"] == REPLAY_NOT_COMPLETED_MSG


def test_endpoint_report_400_invalid_mode(monkeypatch):
    app = _make_app()
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def boom(db_, replay_id, *, mode="analysis"):
        raise CecchinoLabImportError("invalid_report_mode", "mode non supportata: bogus", status_code=400)

    monkeypatch.setattr(cecchino_lab, "build_purchasability_v3_replay_report_response", boom)

    r = client.get("/cecchino-lab/purchasability-v3-replays/1/report?mode=bogus")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Invarianti di sola lettura / niente ricalcolo formula
# ---------------------------------------------------------------------------


def test_no_formula_recalculation_call_in_export_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "calculate_purchasability_v3_batch" not in src


def test_no_db_writes_in_export_source():
    import app.services.cecchino_data_lab.historical_purchasability_v3_replay_export as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "db.commit(" not in src
    assert "db.add(" not in src
    assert "db.flush(" not in src
    assert "db.delete(" not in src


def test_write_zip_does_not_mutate_db_session():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    write_purchasability_v3_replay_report_zip(
        db, 1, io.BytesIO(), mode="analysis", analytics=analytics, lean_rows=rows
    )
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.delete.assert_not_called()


def test_zip_bytes_output_is_a_valid_reopenable_archive():
    replay, analytics, rows = _sample_analytics_and_rows()
    db = _db_with_replay(replay)
    _, data = build_purchasability_v3_replay_report_zip_bytes(
        db, 1, mode="analysis", analytics=analytics, lean_rows=rows
    )
    zf = zipfile.ZipFile(io.BytesIO(data))
    bad_file = zf.testzip()
    assert bad_file is None
