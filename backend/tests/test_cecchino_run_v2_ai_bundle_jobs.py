"""Test mirati: job AI bundle async, sidecar recoverable, SOURCE_RAW two-pass."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.cecchino_data_lab.run_v2 import ai_bundle_jobs as jobs
from app.services.cecchino_data_lab.run_v2.constants import RUN_V2_EXPORT_SCHEMA_VERSION
from app.services.cecchino_data_lab.run_v2.export import _flatten_raw


@pytest.fixture()
def export_dir(tmp_path, monkeypatch):
    root = tmp_path / "ai_exports"
    root.mkdir()
    monkeypatch.setattr(jobs, "RESULT_DIR", root)
    monkeypatch.setattr(jobs, "_jobs", {})
    monkeypatch.setattr(jobs, "_key_to_job", {})
    monkeypatch.setattr(jobs, "_executor", None)
    monkeypatch.setattr(jobs, "_initialized", False)
    return root


def test_recover_building_sidecar_marks_interrupted(export_dir):
    run_id = 42
    job_dir = export_dir / f"{run_id}__{RUN_V2_EXPORT_SCHEMA_VERSION}"
    job_dir.mkdir(parents=True)
    sidecar = {
        "job_id": "job-old",
        "run_id": run_id,
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "status": "building",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:01:00+00:00",
        "phase": "export_bundle",
        "progress_pct": 40,
    }
    (job_dir / "job.json").write_text(json.dumps(sidecar), encoding="utf-8")

    jobs._ensure_executor()
    recovered = jobs.get_job("job-old")
    assert recovered is not None
    assert recovered.status == "interrupted"
    assert recovered.retryable is True
    disk = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert disk["status"] == "interrupted"


def test_create_reuses_ready_zip(export_dir, monkeypatch):
    run_id = 7
    job_dir = export_dir / f"{run_id}__{RUN_V2_EXPORT_SCHEMA_VERSION}"
    job_dir.mkdir(parents=True)
    zip_path = job_dir / "ai_bundle.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    job_id = "ready-job"
    now = "2026-09-10T12:00:00+00:00"
    sidecar = {
        "job_id": job_id,
        "run_id": run_id,
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "status": "ready",
        "filename": "CECCHINO_RUN_V2_TEST_RUN_7_AI_BUNDLE.zip",
        "zip_bytes": zip_path.stat().st_size,
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
        "export_counts": {"full_rows": 3, "source_raw_columns": 10},
    }
    (job_dir / "job.json").write_text(json.dumps(sidecar), encoding="utf-8")

    class FakeRun:
        id = run_id
        status = "completed"

    class FakeSession:
        def get(self, _model, _pk):
            return FakeRun()

        def close(self):
            return None

    monkeypatch.setattr(jobs, "SessionLocal", lambda: FakeSession())

    jobs._ensure_executor()
    first = jobs.create_or_reuse_job(run_id)
    second = jobs.create_or_reuse_job(run_id)
    assert first.job_id == job_id
    assert second.job_id == job_id
    assert first.status == "ready"
    path, filename, size = jobs.resolve_download(run_id)
    assert path == zip_path
    assert "RUN_7" in filename
    assert size == zip_path.stat().st_size


def test_purge_expired_ready_only_under_cache(export_dir, monkeypatch):
    monkeypatch.setattr(jobs, "TTL_READY_SECONDS", 1)
    job_dir = export_dir / f"9__{RUN_V2_EXPORT_SCHEMA_VERSION}"
    job_dir.mkdir()
    (job_dir / "ai_bundle.zip").write_bytes(b"x")
    old = {
        "job_id": "expired",
        "run_id": 9,
        "export_schema_version": RUN_V2_EXPORT_SCHEMA_VERSION,
        "status": "ready",
        "created_at": "2020-01-01T00:00:00+00:00",
        "completed_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2020-01-01T00:00:00+00:00",
    }
    (job_dir / "job.json").write_text(json.dumps(old), encoding="utf-8")
    removed = jobs.purge_expired_cache(now=time.time())
    assert any("9__" in name for name in removed)
    assert not job_dir.exists()


def test_flatten_raw_nested_keys_stable():
    out: dict = {}
    _flatten_raw("", {"A": 1, "B": {"C": 2}}, out)
    assert out == {"A": 1, "B.C": 2}


def test_ai_bundle_zip_members_with_policy_season(monkeypatch, tmp_path):
    from app.services.cecchino_data_lab.run_v2 import ai_bundle as ai_mod
    import io
    import zipfile

    run = SimpleNamespace(
        id=99,
        module_policy_json={"season_label": "2021/2022"},
        run_scope="balanced_pilot",
        status="completed",
        run_version="cecchino_run_v2",
        matches_total=10,
    )

    def fake_bundle(db, *, run_id, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        files = {}
        for name, content in [
            ("FULL.csv", "a,b\n1,2\n"),
            ("core_markets_long.csv", "a,b\n1,2\n3,4\n"),
            ("SOURCE_RAW.csv", "lab_match_id,x\n1,y\n"),
            ("DATA_DICTIONARY.json", json.dumps({"ok": True})),
            ("run_summary.json", json.dumps({"matches": 10, "competitions": [], "leakage_audit": {}})),
        ]:
            p = output_dir / f"cecchino_run_v2_{run_id}_{name}"
            p.write_text(content, encoding="utf-8")
            files[name] = str(p)
        return {"files": files, "counts": {"full_rows": 1, "source_raw_columns": 1}}

    monkeypatch.setattr(ai_mod, "build_export_bundle", fake_bundle)

    class FakeDb:
        def get(self, model, pk):
            return run

    buf = io.BytesIO()
    filename, size = ai_mod.write_ai_bundle_zip(FakeDb(), 99, buf)
    assert "2021-2022" in filename
    assert size > 0
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        assert set(zf.namelist()) == set(ai_mod.ZIP_MEMBERS)
