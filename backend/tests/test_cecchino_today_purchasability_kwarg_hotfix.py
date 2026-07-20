"""Hotfix: typo existing_prev → existing_preview in run_scan + job API counters."""

from __future__ import annotations

import inspect
import os
from contextlib import ExitStack
from datetime import date, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_today_scan_job import (
    JOB_STATUS_FAILED,
    CecchinoTodayScanJob,
)
from app.services.cecchino.cecchino_purchasability_candidate import (
    PURCHASABILITY_CANDIDATE_V2_VERSION,
    calculate_purchasability_candidate_batch,
)
from app.services.cecchino.cecchino_purchasability_snapshot import (
    attach_purchasability_preview_to_output,
    build_purchasability_preview_snapshot,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME
from app.services.cecchino import cecchino_today_service as today_svc
from app.services.cecchino.cecchino_today_scan_job_service import _run_scan_job_thread
from app.services.cecchino.cecchino_today_service import run_scan

TARGET_DATE = date(2026, 6, 5)


def _candidate_item(market_key: str, *, edge: float = 12.0, pc: float = 0.42) -> dict:
    return {
        "market_key": market_key,
        "selection": market_key,
        "feature_status": "ready",
        "status": "not_calculated",
        "phase_1_value": {
            "status": "available",
            "inputs": {
                "prob_cecchino": pc,
                "edge_pct": edge,
                "rating": 70,
                "score_acquisto": 0.01,
            },
        },
        "phase_2_quality": {
            "status": "available",
            "model_context_probability": pc,
            "opposition_pressure_model": 0.28,
            "opposition_pressure_book": 0.30,
            "favourite_alignment": "aligned",
            "favourite_intensity_book": 0.40,
            "book_favourite": {"selection": SEL_HOME, "implied_prob": 0.40},
            "comparator_selections": [SEL_HOME, SEL_DRAW],
            "absolute_model_book_gap": 0.12,
            "model_book_gap": 0.12,
            "gap_direction": "positive",
        },
        "data_quality": {
            "today_fixture_id": 1,
            "snapshot_at": "2026-03-15T12:00:00+00:00",
            "snapshot_timestamp_verified": True,
            "snapshot_before_kickoff": True,
            "pre_match_only": True,
            "contains_settlement_fields": False,
            "contains_result_fields": False,
        },
        "reason_codes": [],
        "context_hooks": {},
    }


def test_attach_signature_rejects_existing_prev_kwarg():
    sig = inspect.signature(attach_purchasability_preview_to_output)
    assert "existing_preview" in sig.parameters
    assert "existing_prev" not in sig.parameters
    with pytest.raises(TypeError, match="existing_prev"):
        attach_purchasability_preview_to_output(
            cecchino_output={},
            kpi_panel={},
            fixture_meta={},
            existing_prev={},
        )


def test_attach_accepts_existing_preview_kwarg():
    output: dict = {}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel={"rows": []},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2020-01-01T12:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-01-01T12:00:00+00:00",
            "snapshot_source": "x",
            "snapshot_fidelity": "verified_panel_odds_meta",
            "snapshot_timestamp_verified": True,
        },
        existing_preview=None,
    )
    assert "purchasability_preview" not in output


def test_run_scan_source_uses_existing_preview_kwarg():
    src = inspect.getsource(today_svc.run_scan)
    assert "existing_preview=" in src
    assert "existing_prev=" not in src


def test_attach_preserves_existing_preview_post_kickoff():
    existing = build_purchasability_preview_snapshot(
        calculate_purchasability_candidate_batch(
            {"today_fixture_id": 1, "items": [_candidate_item(SEL_AWAY)]}
        )
    )
    output: dict = {}
    attach_purchasability_preview_to_output(
        cecchino_output=output,
        kpi_panel={"rows": []},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2020-01-01T12:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-01-01T12:00:00+00:00",
            "snapshot_source": "x",
            "snapshot_fidelity": "verified_panel_odds_meta",
            "snapshot_timestamp_verified": True,
        },
        existing_preview=existing,
    )
    assert output["purchasability_preview"]["candidate_version"] == (
        PURCHASABILITY_CANDIDATE_V2_VERSION
    )
    assert output["purchasability_preview"]["full_candidate_payload_sha256"] == (
        existing["full_candidate_payload_sha256"]
    )


def test_run_scan_calls_attach_with_existing_preview_not_typeerror():
    api_item = {
        "fixture": {
            "id": 42,
            "date": "2026-06-05T18:00:00+00:00",
            "status": {"short": "NS"},
        },
        "league": {
            "id": 135,
            "name": "Serie A",
            "country": "Italy",
            "season": 2025,
            "logo": "",
        },
        "teams": {
            "home": {"name": "Home", "logo": ""},
            "away": {"name": "Away", "logo": ""},
        },
    }
    db = MagicMock()
    db.is_active = True
    db.commit = MagicMock()
    local_fx = MagicMock(id=10, competition_id=3, kickoff="2026-06-05T18:00:00+00:00")
    comp = MagicMock(id=3)
    db.scalar.return_value = local_fx
    db.get.return_value = comp

    client = MagicMock()
    client.get_fixtures_by_date.return_value = [api_item]
    client.set_usage_db = MagicMock()
    client.set_usage_context = MagicMock()

    attach_kwargs: list[dict] = []

    def _capture_attach(**kwargs):
        attach_kwargs.append(kwargs)
        out = kwargs.get("cecchino_output")
        if isinstance(out, dict):
            out["purchasability_preview"] = {"ok": True}
        return out

    patches = [
        ("ZoneInfo", {"return_value": timezone.utc}),
        ("is_cecchino_allowed_competition", {"return_value": (True, None)}),
        ("is_fixture_not_started", {"return_value": True}),
        (
            "fetch_fixture_odds_for_cecchino_bookmakers",
            {"return_value": ({"Betfair": {}}, [], "cached", False)},
        ),
        (
            "verify_complete_1x2_odds",
            {"return_value": (True, {"bookmakers": {}}, None, [])},
        ),
        ("attach_scan_odds_meta", {"side_effect": lambda snap, **_k: snap}),
        (
            "build_calculation_input_for_fixture",
            {"return_value": MagicMock(data_quality={"leakage_check": {"status": "ok"}})},
        ),
        ("build_fixture_contexts", {"return_value": {}}),
        (
            "check_cecchino_today_stats_eligible",
            {"return_value": (True, {"ok": True}, None)},
        ),
        ("sync_today_bookmaker_odds", {}),
        (
            "calculate_and_persist_for_fixture",
            {"return_value": {"output": {"final": {}}, "status": "ok"}},
        ),
        ("build_goal_market_contexts", {"return_value": {}}),
        ("build_goal_market_cecchino_odds", {"return_value": {}}),
        (
            "rebuild_signals_matrix_for_output",
            {"return_value": {"status": "unavailable"}},
        ),
        (
            "build_betfair_payload_from_raw",
            {"return_value": {"status": "ok", "odds": {}}},
        ),
        (
            "build_cecchino_kpi_panel_v2_betfair",
            {
                "return_value": {
                    "rows": [],
                    "odds_meta": {"odds_fetched_at": "2026-06-05T10:00:00+00:00"},
                }
            },
        ),
        (
            "read_odds_meta",
            {"return_value": {"odds_fetched_at": "2026-06-05T10:00:00+00:00"}},
        ),
        (
            "attach_purchasability_preview_to_output",
            {"side_effect": _capture_attach},
        ),
        ("attach_balance_v5_monitoring_to_output", {}),
        (
            "_persist_post_calc_snapshot",
            {"return_value": (MagicMock(), "eligible")},
        ),
        ("_upsert_today_snapshot", {"return_value": MagicMock()}),
        ("cleanup_cecchino_today_snapshots", {"return_value": {}}),
        ("sync_signals_for_scan_date", {"return_value": {"fixtures": 0}}),
        ("get_api_usage_summary", {"return_value": {"total_calls": 1}}),
        ("check_api_budget_during_scan", {}),
    ]
    with ExitStack() as stack:
        for name, kwargs in patches:
            stack.enter_context(
                patch(f"app.services.cecchino.cecchino_today_service.{name}", **kwargs)
            )
        report = run_scan(db, scan_date=TARGET_DATE, client=client, force_rescan=True)

    assert report["status"] == "ok"
    assert attach_kwargs, "attach_purchasability_preview_to_output non chiamata"
    call = attach_kwargs[0]
    assert "existing_preview" in call
    assert "existing_prev" not in call
    assert not any("unexpected keyword" in str(e) for e in (report.get("errors") or []))


def test_job_thread_failed_propagates_api_calls_total():
    db = MagicMock()
    job = CecchinoTodayScanJob(
        job_id="fail-api",
        scan_date=TARGET_DATE,
        timezone="Europe/Rome",
        force_rescan=True,
        status="queued",
    )

    def _boom(_db, **kwargs):
        metrics = kwargs.get("metrics")
        if metrics is not None:
            metrics.api_calls["fixtures"] = 3
            metrics.api_calls["odds"] = 2
            metrics.sync_api_calls_total()
        raise RuntimeError("simulated scan failure")

    with patch(
        "app.services.cecchino.cecchino_today_scan_job_service.SessionLocal",
        return_value=db,
    ):
        with patch(
            "app.services.cecchino.cecchino_today_scan_job_service.get_scan_job",
            return_value=job,
        ):
            with patch(
                "app.services.cecchino.cecchino_today_scan_job_service.run_scan_day",
                side_effect=_boom,
            ):
                _run_scan_job_thread("fail-api")

    assert job.status == JOB_STATUS_FAILED
    assert job.finished_at is not None
    summary = job.result_summary_json or {}
    assert summary.get("api_calls_total") == 5
    assert summary.get("api_calls", {}).get("fixtures") == 3
    assert summary.get("api_calls", {}).get("odds") == 2
    assert any("simulated scan failure" in e for e in (job.errors_json or []))
