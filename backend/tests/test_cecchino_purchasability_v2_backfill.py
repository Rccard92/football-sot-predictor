"""Test backfill job purchasability v2 (dry-run / confirm gate)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest

from app.jobs.backfill_purchasability_v2 import CONFIRM_TOKEN, main


def test_main_dry_run_default(monkeypatch):
    """Default CLI è dry-run: non richiede DB reale se mockiamo run_backfill."""
    from app.jobs import backfill_purchasability_v2 as mod

    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {"errors": 0, "dry_run": True, "rows_seen": 0}

    monkeypatch.setattr(mod, "run_backfill", fake_run)
    rc = main([])
    assert rc == 0
    assert called.get("dry_run") is True


def test_apply_requires_confirm(monkeypatch):
    from app.jobs import backfill_purchasability_v2 as mod

    with pytest.raises(SystemExit):
        mod.run_backfill(apply=True, confirm="WRONG", dry_run=False)


def test_confirm_token_constant():
    assert CONFIRM_TOKEN == "WRITE_PURCHASABILITY_V2"
