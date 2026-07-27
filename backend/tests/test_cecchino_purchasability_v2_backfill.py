"""Test backfill job purchasability v2 (dry-run / confirm / history guard)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import pytest

from app.jobs.backfill_purchasability_v2 import CONFIRM_TOKEN, main, run_backfill
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE


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
    assert called.get("apply") is False


def test_main_explicit_dry_run(monkeypatch):
    from app.jobs import backfill_purchasability_v2 as mod

    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {"errors": 0, "dry_run": True, "rows_seen": 0}

    monkeypatch.setattr(mod, "run_backfill", fake_run)
    rc = main(["--dry-run"])
    assert rc == 0
    assert called.get("dry_run") is True
    assert called.get("apply") is False


def test_apply_without_token_errors(monkeypatch):
    from app.jobs import backfill_purchasability_v2 as mod

    def fail_run(**kwargs):
        raise AssertionError("run_backfill non deve essere chiamato senza token")

    monkeypatch.setattr(mod, "run_backfill", fail_run)
    with pytest.raises(SystemExit):
        main(["--apply"])


def test_apply_wrong_token_errors(monkeypatch):
    from app.jobs import backfill_purchasability_v2 as mod

    def fail_run(**kwargs):
        raise AssertionError("run_backfill non deve essere chiamato con token errato")

    monkeypatch.setattr(mod, "run_backfill", fail_run)
    with pytest.raises(SystemExit):
        main(["--apply", "--confirm", "WRONG"])


def test_apply_with_correct_token_write_mode(monkeypatch):
    from app.jobs import backfill_purchasability_v2 as mod

    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {"errors": 0, "dry_run": False, "wrote": True, "rows_seen": 0}

    monkeypatch.setattr(mod, "run_backfill", fake_run)
    rc = main(["--apply", "--confirm", CONFIRM_TOKEN])
    assert rc == 0
    assert called.get("dry_run") is False
    assert called.get("apply") is True
    assert called.get("confirm") == CONFIRM_TOKEN


def test_dry_run_and_apply_together_argparse_error():
    with pytest.raises(SystemExit):
        main(["--dry-run", "--apply", "--confirm", CONFIRM_TOKEN])


def test_confirm_token_constant():
    assert CONFIRM_TOKEN == "WRITE_PURCHASABILITY_V2"


def test_run_backfill_dry_run_true_apply_true_does_not_write(monkeypatch):
    """dry_run=True vince sempre: write=False anche con apply+token."""
    from app.jobs import backfill_purchasability_v2 as mod

    profile = {
        "version": "cecchino_purchasability_v2_norm_profile_2026_07_26_v2",
        "hash": "abc123",
        "fixtures_seen": 0,
    }

    class FakeScalars:
        def yield_per(self, _n):
            return iter([])

    class FakeDB:
        def scalars(self, _stmt):
            return FakeScalars()

        def commit(self):
            raise AssertionError("commit non consentito in dry-run")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        "app.core.database.SessionLocal", lambda: FakeDB()
    )
    monkeypatch.setattr(
        mod,
        "build_normalization_profile_from_db",
        lambda db: profile,
        raising=False,
    )

    # Patch import inside run_backfill
    import app.services.cecchino.cecchino_purchasability_v2_normalization as norm_mod

    monkeypatch.setattr(
        norm_mod, "build_normalization_profile_from_db", lambda db, **kw: profile
    )

    report = run_backfill(
        dry_run=True,
        apply=True,
        confirm=CONFIRM_TOKEN,
    )
    assert report["wrote"] is False
    assert report["dry_run"] is True
    assert report["persisted"] == 0


def _valid_row(**overrides):
    snap = datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc)
    kick = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    base = {
        "id": 1,
        "local_fixture_id": 10,
        "provider_fixture_id": 100,
        "competition_id": 1,
        "scan_date": datetime(2026, 7, 20).date(),
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "kickoff": kick,
        "updated_at": datetime(2026, 7, 20, 19, 0, 0, tzinfo=timezone.utc),
        "odds_checked_at": None,
        "odds_snapshot_json": None,
        "kpi_panel_json": {
            "rows": [
                {
                    "market_key": "HOME",
                    "rating": 70,
                    "edge_pct": 5,
                    "vantaggio_prob": 0.02,
                    "prob_cecchino": 0.4,
                    "prob_book": 0.38,
                    "quota_book": 2.5,
                }
            ],
            "odds_meta": {"odds_fetched_at": snap.isoformat()},
        },
        "cecchino_output_json": {
            "purchasability_preview": {"candidate_version": "v1_1_keep_me", "score": 55},
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_backfill_db(monkeypatch, rows, *, profile_hash="hash_v2"):
    from app.jobs import backfill_purchasability_v2 as mod
    import app.services.cecchino.cecchino_purchasability_v2_normalization as norm_mod

    profile = {
        "version": "cecchino_purchasability_v2_norm_profile_2026_07_26_v2",
        "hash": profile_hash,
        "fixtures_seen": 1,
        "components": {},
    }

    commits = {"n": 0}
    flag_calls = {"n": 0}

    class FakeScalars:
        def yield_per(self, _n):
            return iter(rows)

    class FakeDB:
        def scalars(self, _stmt):
            return FakeScalars()

        def commit(self):
            commits["n"] += 1

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("app.core.database.SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        norm_mod, "build_normalization_profile_from_db", lambda db, **kw: profile
    )

    def fake_build(**kwargs):
        return (
            {},
            {
                "status": "available",
                "candidate_version": "cecchino_purchasability_v2_candidate_1",
                "snapshot_version": "cecchino_purchasability_snapshot_v2",
                "normalization_profile_hash": profile_hash,
                "items": [],
            },
        )

    monkeypatch.setattr(mod, "build_candidate_and_compact_snapshot_v2", fake_build)

    def fake_flag(obj, key):
        flag_calls["n"] += 1

    monkeypatch.setattr(
        "sqlalchemy.orm.attributes.flag_modified", fake_flag
    )
    return commits, flag_calls


def test_not_eligible_not_in_query_path(monkeypatch):
    """La query filtra eligible: righe non eligible non appaiono (rows_seen=0)."""
    commits, _ = _patch_backfill_db(monkeypatch, rows=[])
    report = run_backfill(dry_run=True)
    assert report["rows_seen"] == 0
    assert report["eligible_rows"] == 0
    assert commits["n"] == 0


def test_snapshot_unverified_skipped(monkeypatch):
    row = _valid_row(
        kpi_panel_json={"rows": [{"market_key": "HOME"}]},
        odds_checked_at=None,
        updated_at=datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
    )
    commits, flags = _patch_backfill_db(monkeypatch, rows=[row])
    report = run_backfill(dry_run=True)
    assert report["snapshot_unverified_skipped"] == 1
    assert report["would_persist"] == 0
    assert report["accepted_pre_match_rows"] == 0
    assert commits["n"] == 0
    assert flags["n"] == 0
    # updated_at non promoosso: cecchino_output invariato
    assert "purchasability_preview_v2" not in (row.cecchino_output_json or {})


def test_post_kickoff_skipped(monkeypatch):
    kick = datetime(2026, 7, 20, 18, 0, 0, tzinfo=timezone.utc)
    snap = datetime(2026, 7, 20, 19, 0, 0, tzinfo=timezone.utc)
    row = _valid_row(
        kickoff=kick,
        kpi_panel_json={
            "rows": [{"market_key": "HOME"}],
            "odds_meta": {"odds_fetched_at": snap.isoformat()},
        },
    )
    _patch_backfill_db(monkeypatch, rows=[row])
    report = run_backfill(dry_run=True)
    assert report["snapshot_not_before_kickoff_skipped"] == 1
    assert report["would_persist"] == 0


def test_kickoff_missing_skipped(monkeypatch):
    row = _valid_row(kickoff=None)
    _patch_backfill_db(monkeypatch, rows=[row])
    report = run_backfill(dry_run=True)
    assert report["kickoff_missing_skipped"] == 1
    assert report["would_persist"] == 0


def test_valid_fixture_would_persist_dry_run(monkeypatch):
    row = _valid_row()
    v11 = row.cecchino_output_json["purchasability_preview"]
    commits, flags = _patch_backfill_db(monkeypatch, rows=[row])
    report = run_backfill(dry_run=True)
    assert report["accepted_pre_match_rows"] == 1
    assert report["would_persist"] == 1
    assert report["persisted"] == 0
    assert report["wrote"] is False
    assert commits["n"] == 0
    assert flags["n"] == 0
    # nessuna scrittura sull'oggetto
    assert row.cecchino_output_json["purchasability_preview"] is v11
    assert "purchasability_preview_v2" not in row.cecchino_output_json


def test_apply_writes_only_v2_preserves_v11(monkeypatch):
    row = _valid_row()
    v11 = dict(row.cecchino_output_json["purchasability_preview"])
    commits, flags = _patch_backfill_db(monkeypatch, rows=[row])
    report = run_backfill(dry_run=False, apply=True, confirm=CONFIRM_TOKEN)
    assert report["wrote"] is True
    assert report["persisted"] == 1
    assert commits["n"] == 1
    assert flags["n"] == 1
    assert row.cecchino_output_json["purchasability_preview"] == v11
    assert "purchasability_preview_v2" in row.cecchino_output_json


def test_already_current_with_profile_hash(monkeypatch):
    row = _valid_row(
        cecchino_output_json={
            "purchasability_preview": {"keep": True},
            "purchasability_preview_v2": {
                "status": "available",
                "candidate_version": "cecchino_purchasability_v2_candidate_1",
                "snapshot_version": "cecchino_purchasability_snapshot_v2",
                "normalization_profile_hash": "hash_v2",
                "contract_version": "cecchino_purchasability_v2_contract",
                "feature_version": "cecchino_purchasability_v2_features_v1",
                "items": [],
            },
        }
    )
    from app.jobs import backfill_purchasability_v2 as mod

    monkeypatch.setattr(
        mod,
        "validate_purchasability_preview_v2_snapshot",
        lambda existing: {"ok": True},
    )
    _patch_backfill_db(monkeypatch, rows=[row], profile_hash="hash_v2")
    report = run_backfill(dry_run=True)
    assert report["already_current"] == 1
    assert report["would_persist"] == 0


def test_old_profile_hash_is_updatable(monkeypatch):
    row = _valid_row(
        cecchino_output_json={
            "purchasability_preview": {"keep": True},
            "purchasability_preview_v2": {
                "status": "available",
                "candidate_version": "cecchino_purchasability_v2_candidate_1",
                "snapshot_version": "cecchino_purchasability_snapshot_v2",
                "normalization_profile_hash": "hash_old_v1",
                "contract_version": "cecchino_purchasability_v2_contract",
                "feature_version": "cecchino_purchasability_v2_features_v1",
                "items": [],
            },
        }
    )
    from app.jobs import backfill_purchasability_v2 as mod

    monkeypatch.setattr(
        mod,
        "validate_purchasability_preview_v2_snapshot",
        lambda existing: {"ok": True},
    )
    _patch_backfill_db(monkeypatch, rows=[row], profile_hash="hash_v2")
    report = run_backfill(dry_run=True)
    assert report["already_current"] == 0
    assert report["would_persist"] == 1


def test_apply_without_confirm_raises():
    with pytest.raises(SystemExit):
        run_backfill(dry_run=False, apply=True, confirm="WRONG")
