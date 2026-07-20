"""Hardening Monitoraggio — persistence, Balance resolve, ZIP v2."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_MONITORING_KEY,
    BALANCE_MONITORING_SNAPSHOT_VERSION,
    attach_balance_v5_monitoring_to_output,
    compact_balance_v5_monitoring_snapshot,
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_module_monitoring_exports import (
    MONITORING_EXPORT_VERSION,
    build_module_analysis_pack_zip,
    build_module_export_status,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    attach_purchasability_preview_to_output,
)


def test_monitoring_export_version_v6():
    assert MONITORING_EXPORT_VERSION == "cecchino_module_monitoring_exports_v6"


def test_attach_purchasability_writes_preview_on_dict_copy(monkeypatch):
    """Pipeline: attach → assign su nuova copia dict (simula commit)."""
    from app.services.cecchino import cecchino_purchasability_snapshot as snap

    fake_snapshot = {
        "status": "available",
        "snapshot_version": PURCHASABILITY_SNAPSHOT_VERSION,
        "candidate_version": PURCHASABILITY_CANDIDATE_VERSION,
        "feature_version": PURCHASABILITY_FEATURE_VERSION,
        "source_snapshot_verified": True,
        "source_snapshot_before_kickoff": True,
        "source_snapshot_at": "2026-07-19T10:00:00+00:00",
        "items": [{"market_key": "HOME", "status": "available", "score": 55}],
    }

    monkeypatch.setattr(
        snap,
        "build_candidate_and_compact_snapshot",
        lambda **kw: ({}, fake_snapshot),
    )

    output = {"final": {"quota_1": 2.0, "quota_x": 3.0, "quota_2": 4.0}}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel={"rows": [{"market_key": "HOME"}]},
        fixture_meta={
            "today_fixture_id": 1,
            "kickoff": datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc),
            "scan_date": date(2026, 7, 19),
        },
        snapshot_info={
            "snapshot_at": datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            "snapshot_timestamp_verified": True,
        },
    )
    # Simula ORM: nuova copia assegnata
    persisted = dict(output)
    preview = persisted.get("purchasability_preview")
    assert isinstance(preview, dict)
    assert preview["candidate_version"] == PURCHASABILITY_CANDIDATE_VERSION
    assert preview["feature_version"] == PURCHASABILITY_FEATURE_VERSION
    assert preview["source_snapshot_verified"] is True
    assert preview["source_snapshot_before_kickoff"] is True


def test_health_blocking_reason_only_legacy(monkeypatch):
    from app.services.cecchino import cecchino_purchasability_validation as val

    fx = MagicMock()
    fx.scan_date = date(2026, 6, 1)
    fx.kpi_panel_json = {"rows": [{"market_key": "HOME"}]}
    fx.cecchino_output_json = {}  # no preview → only_derived

    class _Scalars:
        def all(self):
            return [fx]

    db = MagicMock()
    db.scalars.side_effect = [
        _Scalars(),  # fixtures
        _Scalars(),  # evals empty via second call - need empty list
    ]

    # second scalars for evaluations
    class _Empty:
        def all(self):
            return []

    calls = {"n": 0}

    def _scalars(_q):
        calls["n"] += 1
        return _Scalars() if calls["n"] == 1 else _Empty()

    db.scalars.side_effect = _scalars

    out = val.build_purchasability_validation_health(
        db, date_from=date(2026, 1, 1), date_to=date(2026, 7, 1)
    )
    assert out["fixtures_only_derived"] == 1
    assert out["fixtures_with_persisted_preview"] == 0
    assert out["persistence_blocking_reason"] in (
        "only_legacy_derived_available",
        "no_post_deploy_scan_detected",
    )


def test_resolve_balance_derived_from_final(monkeypatch):
    from app.services.cecchino import cecchino_balance_v5_monitoring as mon

    fake_bal = {
        "status": "ok",
        "version": "cecchino_balance_v5_v2",
        "inputs": {
            "prob_1_norm": 40.0,
            "prob_x_norm": 30.0,
            "prob_2_norm": 30.0,
        },
        "pillars": {
            "f36": {"index": 1.0, "class_label": "A"},
            "dominance": {"index": 2.0, "class_label": "B", "direction": "1"},
            "draw_credibility": {"index": 30.0, "class_label": "C"},
            "gap_coherence": {"index": 3.0, "class_label": "D"},
        },
        "warnings": [],
    }
    monkeypatch.setattr(mon, "build_cecchino_balance_v5", lambda **kw: fake_bal)

    row = SimpleNamespace(
        cecchino_output_json={"final": {"quota_1": 2.1, "quota_x": 3.2, "quota_2": 3.5}},
        kpi_panel_json={"rows": []},
        odds_snapshot_json={},
        scan_date=date(2026, 7, 1),
        kickoff=None,
        score_fulltime_home=1,
        score_fulltime_away=0,
        id=10,
        provider_fixture_id=99,
        local_fixture_id=5,
        competition_id=1,
        league_name="Test",
        home_team_name="H",
        away_team_name="A",
    )
    resolved = resolve_balance_v5_monitoring_snapshot(row)
    assert resolved["mode"] == "derived_read_only_from_stored_inputs_unverified_timestamp"
    assert resolved["source_cohort"] == "historical_diagnostic"
    assert resolved["payload"]["f36_index"] == 1.0


def test_resolve_balance_persisted_monitoring_key():
    compact = {
        "status": "ok",
        "snapshot_version": BALANCE_MONITORING_SNAPSHOT_VERSION,
        "f36_index": 2.5,
        "prob_1_norm": 45.0,
    }
    row = SimpleNamespace(
        cecchino_output_json={BALANCE_MONITORING_KEY: compact},
        kpi_panel_json={},
        odds_snapshot_json={},
        scan_date=date(2026, 7, 1),
        kickoff=None,
    )
    resolved = resolve_balance_v5_monitoring_snapshot(row)
    assert resolved["mode"] == "persisted"
    assert resolved["source_cohort"] == "historical_diagnostic"


def test_attach_balance_monitoring_to_output(monkeypatch):
    from app.services.cecchino import cecchino_balance_v5_monitoring as mon

    monkeypatch.setattr(
        mon,
        "build_cecchino_balance_v5",
        lambda **kw: {
            "status": "ok",
            "version": "cecchino_balance_v5_v2",
            "inputs": {"prob_1_norm": 50, "prob_x_norm": 25, "prob_2_norm": 25},
            "pillars": {
                "f36": {"index": 1, "class_label": "eq"},
                "dominance": {"index": 1, "class_label": "d", "direction": "1"},
                "draw_credibility": {"index": 25, "class_label": "x"},
                "gap_coherence": {"index": 1, "class_label": "g"},
            },
            "warnings": [],
        },
    )
    output = {"final": {"quota_1": 2.0}}
    attach_balance_v5_monitoring_to_output(
        cecchino_output=output,
        kpi_panel={"rows": []},
        fixture_meta={"scan_date": date(2026, 7, 19), "kickoff": None},
        snapshot_info={"snapshot_timestamp_verified": True, "snapshot_at": "2026-07-19T10:00:00Z"},
    )
    snap = output[BALANCE_MONITORING_KEY]
    assert snap["snapshot_version"] == BALANCE_MONITORING_SNAPSHOT_VERSION
    assert "ft_home" not in snap
    assert snap.get("prob_1_norm") == 50


def test_balance_pack_contains_rows_and_distributions(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    files_payload = {
        "balance_rows.csv": b"\xef\xbb\xbftoday_fixture_id\n1\n",
        "f36_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
        "dominance_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
        "draw_credibility_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
        "gap_distribution.csv": b"\xef\xbb\xbfclass,count,share\n",
        "monthly_timeseries.csv": b"\xef\xbb\xbfmonth,fixtures\n",
        "snapshot_health.json": b'{"covered_rows":1}',
        "source_cohort_distribution.json": b'{"legacy_derived_diagnostic":1}',
        "version_definition.json": b'{"balance_version":"cecchino_balance_v5_v2"}',
        "draw_credibility_research.json": b'{"status":"unavailable"}',
    }
    monkeypatch.setattr(
        mon,
        "_build_balance_files",
        lambda *a, **k: (
            dict(files_payload),
            {
                "versions": {"balance": "cecchino_balance_v5_v2"},
                "source_cohorts": {"legacy_derived_diagnostic": 1},
                "primary_rows": 1,
                "completeness": "partial",
                "blocking_reasons": [],
                "warnings": [],
                "include_rows_effective": True,
                "module_version": "cecchino_balance_v5_v2",
                "status": "official_monitored",
                "metrics": {},
            },
        ),
    )
    # Force inventory path through real zip builder with monkeypatched balance
    data, filename = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="balance-v5",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        include_rows=True,
    )
    assert "balance-v5" in filename
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "balance_rows.csv" in names
        assert "f36_distribution.csv" in names
        assert "manifest.json" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest.get("export_version") == MONITORING_EXPORT_VERSION or manifest.get(
            "schema_version"
        )
        assert any(f.get("sha256") for f in manifest.get("files") or [])
        assert zf.read("balance_rows.csv").startswith(b"\xef\xbb\xbf")


def test_goal_pack_includes_six_exports(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_goal_files",
        lambda *a, **k: (
            {
                "preview_summary.json": b"{}",
                "preview_snapshots.csv": b"\xef\xbb\xbfid\n",
                "preview_completed_results.csv": b"\xef\xbb\xbfid\n",
                "preview_candidate_monitoring.csv": b"\xef\xbb\xbfid\n",
                "preview_calibration.json": b"{}",
                "preview_bundle_definition.json": b'{"version":"bundle_v_exact"}',
                "prospective_progress.json": b"{}",
                "data_health.json": b"{}",
                "health.json": b"{}",
                "summary.json": b"{}",
                "warnings.json": b'{"warnings":[]}',
            },
            {
                "versions": {"goal_intensity": "bundle_v_exact"},
                "source_cohorts": {},
                "primary_rows": 0,
                "completeness": "partial",
                "blocking_reasons": [],
                "warnings": [],
                "include_rows_effective": True,
                "module_version": "bundle_v_exact",
                "status": "preview_research",
                "metrics": {},
            },
        ),
    )
    data, _ = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="goal-intensity-v5",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in (
            "preview_summary.json",
            "preview_snapshots.csv",
            "preview_completed_results.csv",
            "preview_candidate_monitoring.csv",
            "preview_calibration.json",
            "preview_bundle_definition.json",
            "prospective_progress.json",
            "data_health.json",
        ):
            assert name in zf.namelist()


def test_signals_pack_has_activations_rows(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_signals_files",
        lambda *a, **k: (
            {
                "activations_rows.csv": b"\xef\xbb\xbfData,Match\n2026-01-01,A-B\n",
                "by_signal.csv": b"\xef\xbb\xbfsignal,count\n",
                "by_column.csv": b"\xef\xbb\xbfcolumn,count\n",
                "by_signal_and_column.csv": b"\xef\xbb\xbfsignal,column\n",
                "monthly_timeseries.csv": b"\xef\xbb\xbfmonth,activations\n",
                "overall.json": b'{"activations":1,"settled_activations":1,"distinct_fixtures":1}',
                "version_definition.json": b'{"signals":"signals_lab"}',
                "health.json": b"{}",
                "summary.json": b"{}",
                "warnings.json": b'{"warnings":[]}',
            },
            {
                "versions": {"signals": "signals_lab"},
                "source_cohorts": {"activations": 1},
                "primary_rows": 1,
                "completeness": "partial",
                "blocking_reasons": [],
                "warnings": [],
                "include_rows_effective": True,
                "module_version": "signals_lab",
                "status": "operational",
                "metrics": {
                    "distinct_fixtures": 1,
                    "settled_activations": 1,
                    "activations": 1,
                },
            },
        ),
    )
    data, _ = build_module_analysis_pack_zip(
        MagicMock(),
        module_key="signals",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert "activations_rows.csv" in zf.namelist()
        assert "monthly_timeseries.csv" in zf.namelist()
        assert zf.read("activations_rows.csv").startswith(b"\xef\xbb\xbf")


def test_export_status_shape(monkeypatch):
    from app.services.cecchino import cecchino_module_monitoring_exports as mon

    monkeypatch.setattr(
        mon,
        "_build_module_inventory",
        lambda *a, **k: (
            {"health.json": b"{}"},
            {
                "files": [
                    {
                        "name": "health.json",
                        "kind": "json",
                        "row_count": None,
                        "size_bytes": 2,
                        "sha256": "abc",
                        "empty": False,
                        "schema_version": "v",
                    }
                ]
            },
            {
                "primary_rows": 0,
                "source_cohorts": {},
                "completeness": "empty",
                "blocking_reasons": ["no_rows"],
                "warnings": ["test"],
            },
        ),
    )
    st = build_module_export_status(
        MagicMock(),
        module_key="purchasability",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
    )
    assert st["completeness"] == "empty"
    assert "files_expected" in st
    assert "estimated_size_bytes" in st


def test_compact_snapshot_excludes_ft():
    bal = {
        "status": "ok",
        "version": "cecchino_balance_v5_v2",
        "inputs": {"prob_1_norm": 1, "prob_x_norm": 1, "prob_2_norm": 1},
        "pillars": {
            "f36": {"index": 0},
            "dominance": {"index": 0},
            "draw_credibility": {"index": 0},
            "gap_coherence": {"index": 0},
        },
        "warnings": [],
    }
    compact = compact_balance_v5_monitoring_snapshot(
        bal, scan_date=date(2026, 1, 1), kickoff=None
    )
    assert "score_fulltime_home" not in compact
    assert "ft_home" not in compact
    assert compact["snapshot_version"] == BALANCE_MONITORING_SNAPSHOT_VERSION
