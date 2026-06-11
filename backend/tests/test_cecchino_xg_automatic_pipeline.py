"""Test hook pipeline xG automatico — Cecchino Fase 53."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_recompute_service import recompute_today_fixture_offline
from app.services.cecchino.cecchino_today_service import (
    _persist_post_calc_snapshot,
    revalidate_cecchino_today_day,
)


def test_persist_post_calc_snapshot_calls_xg_ensure_when_eligible():
    db = MagicMock()
    row = MagicMock()
    row.id = 99
    row.eligibility_status = ELIGIBILITY_ELIGIBLE

    with patch(
        "app.services.cecchino.cecchino_today_service._upsert_today_snapshot",
        return_value=row,
    ), patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as val_mock, patch(
        "app.services.cecchino.cecchino_today_service.maybe_ensure_xg_for_eligible_row",
    ) as ensure_mock:
        val_mock.return_value = MagicMock(
            is_eligible=True,
            eligibility_status=ELIGIBILITY_ELIGIBLE,
            eligibility_reason="ok",
            blocking_reasons=[],
            warnings=[],
        )
        _persist_post_calc_snapshot(
            db,
            scan_date=MagicMock(),
            api_item={"fixture": {"id": 1}, "league": {}, "teams": {"home": {}, "away": {}}},
            local_fixture_id=10,
            competition_id=1,
            odds_snapshot={},
            stats_snapshot={},
            cecchino_output={},
            kpi_panel={},
            row_warnings=[],
            calc={"status": "ok", "calculation_status": "ok"},
            leakage_status="ok",
        )
        ensure_mock.assert_called_once_with(db, row)


def test_revalidate_calls_xg_ensure_for_eligible_rows():
    db = MagicMock()
    row = MagicMock()
    row.cecchino_output_json = {"final": {}}
    row.stats_snapshot_json = {}
    row.odds_snapshot_json = {}
    row.kpi_panel_json = {}
    row.warnings_json = []
    row.cecchino_status = "ok"
    row.eligibility_status = ELIGIBILITY_ELIGIBLE

    db.scalars.return_value.all.return_value = [row]

    with patch(
        "app.services.cecchino.cecchino_today_service.validate_cecchino_today_final_eligibility",
    ) as val_mock, patch(
        "app.services.cecchino.cecchino_today_service.maybe_ensure_xg_for_eligible_row",
    ) as ensure_mock:
        val_mock.return_value = MagicMock(
            is_eligible=True,
            eligibility_status=ELIGIBILITY_ELIGIBLE,
            eligibility_reason="ok",
            blocking_reasons=[],
            warnings=[],
        )
        out = revalidate_cecchino_today_day(db, scan_date=MagicMock())
        ensure_mock.assert_called_once_with(db, row)
        assert out["kept_eligible"] == 1


def test_recompute_calls_xg_ensure_when_eligible():
    db = MagicMock()
    row = MagicMock()
    row.id = 42
    row.local_fixture_id = 10
    row.competition_id = 1
    row.provider_fixture_id = 900
    row.stats_snapshot_json = {}
    row.odds_snapshot_json = {}
    row.warnings_json = []
    row.cecchino_status = "ok"
    row.cecchino_output_json = {"final": {}}
    fixture = MagicMock()
    comp = MagicMock()

    def _get(model, pk):
        if pk == 1:
            return comp
        if pk == 10:
            return fixture
        return None

    db.get.side_effect = _get

    with patch(
        "app.services.cecchino.cecchino_recompute_service.calculate_and_persist_for_fixture",
        return_value={"status": "ok", "calculation_status": "ok", "output": {"final": {}, "warnings": []}},
    ), patch(
        "app.services.cecchino.cecchino_recompute_service.build_goal_market_contexts",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_recompute_service.build_goal_market_cecchino_odds",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_recompute_service.build_cecchino_kpi_panel_v2_betfair",
        return_value={},
    ), patch(
        "app.services.cecchino.cecchino_recompute_service.validate_cecchino_today_final_eligibility",
    ) as val_mock, patch(
        "app.services.cecchino.cecchino_recompute_service.maybe_ensure_xg_for_eligible_row",
    ) as ensure_mock, patch(
        "app.services.cecchino.cecchino_recompute_service._load_betfair_payload",
        return_value={"status": "ok"},
    ), patch(
        "app.services.cecchino.cecchino_recompute_service.read_odds_meta",
        return_value=None,
    ):
        val_mock.return_value = MagicMock(
            is_eligible=True,
            eligibility_status=ELIGIBILITY_ELIGIBLE,
            eligibility_reason="ok",
            blocking_reasons=[],
            warnings=[],
        )
        recompute_today_fixture_offline(db, row, sync_signal_activations=False, evaluate_signals_after=False)
        ensure_mock.assert_called_once_with(db, row)
