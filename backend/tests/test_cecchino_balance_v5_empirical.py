"""Test dataset empirico Balance v5 — Fase 2/3 Step 2A."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_balance_v5_evaluation import (
    EVAL_PENDING,
    EVAL_POSTPONED,
    EVAL_RESULT_MISSING,
    EVAL_SETTLED,
    OUTCOME_AWAY,
    OUTCOME_DRAW,
    OUTCOME_HOME,
    CecchinoBalanceV5Evaluation,
)
from app.services.cecchino.cecchino_balance_v5_empirical import (
    BALANCE_EMPIRICAL_DATASET_VERSION,
    BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN,
    BALANCE_EMPIRICAL_TARGET_CONTRACT_VERSION,
    _apply_settlement_fields,
    build_balance_empirical_record,
    build_balance_empirical_target_contract,
    compute_balance_snapshot_hash,
    settle_balance_empirical_record,
    sync_balance_empirical_dataset,
    upsert_balance_empirical_record,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    SCHEMA_CONTRACTS,
    build_module_analysis_pack_zip,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_HISTORICAL_DIAGNOSTIC,
    COHORT_PROSPECTIVE,
)


def _pre_match(**overrides):
    base = {
        "today_fixture_id": 1,
        "provider_fixture_id": 10,
        "local_fixture_id": 2,
        "balance_version": "cecchino_balance_v5_v2",
        "snapshot_version": "v1",
        "f36_index": 0.5,
        "f36_class": "balanced",
        "dominance_index": 0.6,
        "dominance_class": "home",
        "dominance_selection": "1",
        "draw_credibility_index": 0.2,
        "draw_credibility_class": "low",
        "gap_index": 0.1,
        "gap_class": "ok",
        "prob_1_norm": 0.45,
        "prob_x_norm": 0.25,
        "prob_2_norm": 0.3,
        "book_prob_1": 0.4,
        "book_prob_x": 0.3,
        "book_prob_2": 0.3,
        "source_snapshot_at": "2026-07-19T10:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_snapshot_hash_stable_and_excludes_settlement():
    a = compute_balance_snapshot_hash(_pre_match())
    b = compute_balance_snapshot_hash(_pre_match())
    assert a == b
    assert len(a) == 64
    with_result = _pre_match()
    with_result["ft_home"] = 2
    with_result["outcome_1x2"] = "HOME"
    assert compute_balance_snapshot_hash(with_result) == a


def test_target_contract_version():
    contract = build_balance_empirical_target_contract()
    assert contract["version"] == BALANCE_EMPIRICAL_TARGET_CONTRACT_VERSION
    assert "dominance_selection_hit" in contract["pillars"]["dominance"]["primary_targets"]
    assert "historical_diagnostic_can_promote" in contract["forbidden_interpretations"]


def test_settlement_home_draw_away_and_dominance_hit():
    fx = SimpleNamespace(
        match_status="FT",
        score_fulltime_home=2,
        score_fulltime_away=1,
        score_halftime_home=1,
        score_halftime_away=0,
    )
    home = _apply_settlement_fields({"dominance_selection": "1"}, fx)
    assert home["evaluation_status"] == EVAL_SETTLED
    assert home["outcome_1x2"] == OUTCOME_HOME
    assert home["is_draw"] is False
    assert home["total_goals"] == 3
    assert home["absolute_goal_difference"] == 1
    assert home["dominance_selection_hit"] is True

    fx.score_fulltime_home = 1
    fx.score_fulltime_away = 1
    draw = _apply_settlement_fields({"dominance_selection": "X"}, fx)
    assert draw["outcome_1x2"] == OUTCOME_DRAW
    assert draw["is_draw"] is True
    assert draw["dominance_selection_hit"] is True

    miss = _apply_settlement_fields({"dominance_selection": "1"}, fx)
    assert miss["dominance_selection_hit"] is False

    fx.score_fulltime_home = 0
    fx.score_fulltime_away = 2
    away = _apply_settlement_fields({"dominance_selection": "2"}, fx)
    assert away["outcome_1x2"] == OUTCOME_AWAY
    assert away["dominance_selection_hit"] is True


def test_settlement_pending_result_missing_postponed():
    pending = _apply_settlement_fields(
        {},
        SimpleNamespace(
            match_status="NS",
            score_fulltime_home=None,
            score_fulltime_away=None,
            score_halftime_home=None,
            score_halftime_away=None,
        ),
    )
    assert pending["evaluation_status"] == EVAL_PENDING

    missing = _apply_settlement_fields(
        {},
        SimpleNamespace(
            match_status="FT",
            score_fulltime_home=None,
            score_fulltime_away=None,
            score_halftime_home=None,
            score_halftime_away=None,
        ),
    )
    assert missing["evaluation_status"] == EVAL_RESULT_MISSING

    postponed = _apply_settlement_fields(
        {},
        SimpleNamespace(
            match_status="POSTPONED",
            score_fulltime_home=None,
            score_fulltime_away=None,
            score_halftime_home=None,
            score_halftime_away=None,
        ),
    )
    assert postponed["evaluation_status"] == EVAL_POSTPONED


def _resolved(cohort: str, *, verified: bool = True, selection: str = "1"):
    snap = "2026-07-19T10:00:00+00:00"
    return {
        "mode": "prospective_scan" if cohort == COHORT_PROSPECTIVE else "derived",
        "source_cohort": cohort,
        "payload": {
            "status": "ok",
            "balance_version": "cecchino_balance_v5_v2",
            "snapshot_version": "v1",
            "source_mode": "prospective_scan" if cohort == COHORT_PROSPECTIVE else "derived",
            "snapshot_timestamp": snap,
            "pre_match_verified": verified,
            "book_verified": verified,
            "f36_index": 0.5,
            "f36_class": "balanced",
            "dominance_index": 0.6,
            "dominance_class": "home",
            "dominance_selection": selection,
            "draw_credibility_index": 0.2,
            "draw_credibility_class": "low",
            "gap_index": 0.1,
            "gap_class": "ok",
            "prob_1_norm": 0.45,
            "prob_x_norm": 0.25,
            "prob_2_norm": 0.3,
            "book_prob_1": 0.4,
            "book_prob_x": 0.3,
            "book_prob_2": 0.3,
            "warning_codes": [],
        },
    }


def _fixture(**overrides):
    kick = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    base = dict(
        id=42,
        local_fixture_id=1,
        provider_fixture_id=100,
        competition_id=7,
        scan_date=date(2026, 7, 19),
        kickoff=kick,
        country_name="IT",
        league_name="Serie A",
        home_team_name="A",
        away_team_name="B",
        match_status="NS",
        score_fulltime_home=None,
        score_fulltime_away=None,
        score_halftime_home=None,
        score_halftime_away=None,
        cecchino_output_json={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_record_cohorts_promotion_eligible():
    fx = _fixture()
    prospective = build_balance_empirical_record(
        fx, resolved_snapshot=_resolved(COHORT_PROSPECTIVE, verified=True)
    )
    assert prospective is not None
    assert prospective["source_cohort"] == COHORT_PROSPECTIVE
    assert prospective["promotion_eligible"] is True
    assert prospective["empirical_dataset_version"] == BALANCE_EMPIRICAL_DATASET_VERSION

    diagnostic = build_balance_empirical_record(
        fx, resolved_snapshot=_resolved(COHORT_HISTORICAL_DIAGNOSTIC, verified=False)
    )
    assert diagnostic is not None
    assert diagnostic["source_cohort"] == COHORT_HISTORICAL_DIAGNOSTIC
    assert diagnostic["promotion_eligible"] is False


def test_upsert_idempotent_and_is_current_flip():
    fx = _fixture()
    resolved = _resolved(COHORT_PROSPECTIVE)
    added: list[CecchinoBalanceV5Evaluation] = []
    db = MagicMock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.add.side_effect = lambda obj: added.append(obj)

    with patch(
        "app.services.cecchino.cecchino_balance_v5_empirical.resolve_balance_v5_monitoring_snapshot",
        return_value=resolved,
    ):
        first = upsert_balance_empirical_record(db, fixture=fx, commit=False)
    assert first is not None
    assert len(added) == 1
    assert added[0].is_current is True
    first_hash = added[0].snapshot_hash

    # same hash → update existing, no second insert
    existing = added[0]
    db.scalar.return_value = existing
    with patch(
        "app.services.cecchino.cecchino_balance_v5_empirical.resolve_balance_v5_monitoring_snapshot",
        return_value=resolved,
    ):
        second = upsert_balance_empirical_record(db, fixture=fx, commit=False)
    assert second is existing
    assert len(added) == 1

    # new hash → deactivate old + insert
    resolved2 = _resolved(COHORT_PROSPECTIVE)
    resolved2["payload"] = {**resolved2["payload"], "f36_index": 0.9}
    old = SimpleNamespace(
        id=1,
        is_current=True,
        snapshot_hash=first_hash,
        balance_version="cecchino_balance_v5_v2",
        today_fixture_id=42,
    )
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = [old]
    with patch(
        "app.services.cecchino.cecchino_balance_v5_empirical.resolve_balance_v5_monitoring_snapshot",
        return_value=resolved2,
    ):
        third = upsert_balance_empirical_record(db, fixture=fx, commit=False)
    assert third is not None
    assert old.is_current is False
    assert len(added) == 2
    assert added[1].is_current is True
    assert added[1].snapshot_hash != first_hash


def test_settle_does_not_mutate_snapshot_hash():
    fx = _fixture(
        match_status="FT",
        score_fulltime_home=2,
        score_fulltime_away=0,
    )
    row = SimpleNamespace(
        today_fixture_id=42,
        is_current=True,
        snapshot_hash="abc123",
        dominance_selection="1",
        source_cohort=COHORT_PROSPECTIVE,
        balance_version="cecchino_balance_v5_v2",
        evaluation_status=EVAL_PENDING,
    )
    db = MagicMock()
    db.scalar.return_value = row
    out = settle_balance_empirical_record(db, fixture=fx, commit=False)
    assert out is row
    assert row.snapshot_hash == "abc123"
    assert row.evaluation_status == EVAL_SETTLED
    assert row.outcome_1x2 == OUTCOME_HOME
    assert row.dominance_selection_hit is True


def test_sync_dry_run_and_confirm_token():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch(
        "app.services.cecchino.cecchino_balance_v5_empirical._iter_source_fixtures",
        return_value=[],
    ):
        plan = sync_balance_empirical_dataset(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 20),
            dry_run=True,
            commit=False,
        )
    assert plan["dry_run"] is True
    assert plan["dataset_version"] == BALANCE_EMPIRICAL_DATASET_VERSION
    assert plan["source_fixtures"] == 0

    with pytest.raises(ValueError, match="invalid_confirm_token"):
        sync_balance_empirical_dataset(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 20),
            dry_run=False,
            commit=False,
            confirm="WRONG",
        )

    with patch(
        "app.services.cecchino.cecchino_balance_v5_empirical._iter_source_fixtures",
        return_value=[],
    ):
        run = sync_balance_empirical_dataset(
            db,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 20),
            dry_run=False,
            commit=True,
            confirm=BALANCE_EMPIRICAL_SYNC_CONFIRM_TOKEN,
        )
    assert run["dry_run"] is False


def test_migration_revision_chain_smoke():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260720120000_cecchino_balance_v5_evaluations.py"
    )
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("bal_emp_mig", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "20260720120000"
    assert mod.down_revision == "20260719190000"


def test_export_v6_includes_empirical_files(monkeypatch):
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v10"
    required = SCHEMA_CONTRACTS["balance-v5"]["required_files"]
    for name in (
        "empirical_dataset_rows.csv",
        "empirical_dataset_health.json",
        "empirical_target_contract.json",
        "empirical_cardinality.json",
        "empirical_source_cohorts.csv",
        "empirical_evaluation_status.csv",
    ):
        assert name in required

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_balance_export_files",
        lambda *a, **k: {
            "balance_rows.csv": b"\xef\xbb\xbfx\n",
            "f36_distribution.csv": b"\xef\xbb\xbfx\n",
            "dominance_distribution.csv": b"\xef\xbb\xbfx\n",
            "draw_credibility_distribution.csv": b"\xef\xbb\xbfx\n",
            "gap_distribution.csv": b"\xef\xbb\xbfx\n",
            "monthly_timeseries.csv": b"\xef\xbb\xbfx\n",
            "snapshot_health.json": b"{}",
            "source_cohort_distribution.json": b"{}",
            "version_definition.json": b"{}",
            "draw_credibility_research.json": b"{}",
        },
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_balance_module_overview",
        lambda *a, **k: {
            "version": "cecchino_balance_v5_v2",
            "warnings": [],
            "eligible_fixtures": 1,
            "prospective_persisted": 0,
            "legacy_derived_diagnostic": 1,
            "source_cohorts": {"historical_diagnostic": 1},
        },
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_balance_monitoring_rows",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_balance_empirical_health",
        lambda *a, **k: {"status": "ok", "readiness": "empirical_dataset_collecting"},
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.build_balance_empirical_cardinality",
        lambda *a, **k: {
            "by_source_cohort": {"historical_diagnostic": 2},
            "by_evaluation_status": {"pending": 1, "settled": 1},
        },
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_module_monitoring_exports.query_balance_empirical_rows",
        lambda *a, **k: {"items": [], "total": 0},
    )

    data, _filename = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="balance-v5",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 20),
        include_rows=True,
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    for name in required:
        assert name in names
    assert any("manifest" in n for n in names)
