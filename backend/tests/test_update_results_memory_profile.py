"""Test profiler memoria update-results (gated, no json.dumps JSONB)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from app.services.cecchino import update_results_memory_profile as mod


def test_stage_sample_indices_small():
    assert mod.stage_sample_indices(0) == set()
    assert mod.stage_sample_indices(1) == {0}
    assert mod.stage_sample_indices(3) == {0, 1, 2}
    assert mod.stage_sample_indices(10) == {0, 1, 2, 5, 9}


def test_profiler_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE", raising=False)
    mod.clear_last_profile()
    with mod.profile_update_results_memory() as prof:
        assert prof.enabled is False
        prof.mark("after_rows_query")
        prof.set_counter("fixtures_total", 99)
        prof.begin_stage_sample(fixture_index=0, fixture_id=1)
        prof.mark_stage("after_apply_result")
        prof.end_stage_sample()
    assert mod.get_last_profile() is None
    assert prof.checkpoints == {}
    assert prof.counters == {}
    assert prof.stage_samples == []


def test_profiler_checkpoints_and_uow_when_enabled(monkeypatch):
    monkeypatch.setenv("CECCHINO_UPDATE_RESULTS_MEMORY_PROFILE", "true")
    mod.clear_last_profile()

    db = MagicMock()
    db.identity_map = {1: object(), 2: object()}
    db.new = set()
    db.dirty = {object()}
    db.deleted = set()

    with mod.profile_update_results_memory(db=db) as prof:
        assert prof.enabled is True
        prof.set_sample_indices(mod.stage_sample_indices(5))
        prof.mark("after_rows_query", db=db)
        assert "after_rows_query" in prof.checkpoints
        uow = prof.checkpoints["after_rows_query"]["uow"]
        assert uow["identity_map"] == 2
        assert uow["dirty"] == 1
        assert uow["new"] == 0
        assert uow["deleted"] == 0

        # Campione: solo begin/mark_stage quando attivo
        prof.begin_stage_sample(fixture_index=0, fixture_id=42)
        prof.mark_stage("after_signals_evaluation", db=db)
        prof.mark_stage("after_balance_settlement", db=db)
        prof.end_stage_sample()
        # Fuori campione: touch_peak non crea checkpoint stage
        prof.touch_peak(db=db)
        prof.set_counter("fixtures_processed", 5)

    stored = mod.get_last_profile()
    assert stored is not None
    assert stored["label"] == "update_today_fixture_results"
    assert stored["counters"]["fixtures_processed"] == 5
    assert len(stored["stage_samples"]) == 1
    assert stored["stage_samples"][0]["fixture_id"] == 42
    assert "after_signals_evaluation" in stored["stage_samples"][0]["stages"]
    assert stored["uow_peak"]["identity_map"] == 2
    assert stored["uow_peak"]["dirty"] == 1


def test_no_json_dumps_path_in_module_source():
    """Guardrail: il modulo profiler non deve serializzare JSONB in-process."""
    from pathlib import Path

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "json.dumps" not in src
    assert "jsonb_approx_bytes" not in src
