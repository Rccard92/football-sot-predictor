"""Test preparazione dati analisi giornata (Step I)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.backtest.round_analysis_data_prep_service import RoundAnalysisDataPrepService


@patch("app.services.backtest.round_analysis_data_prep_service.SportApiUnavailableBackfillService")
@patch("app.services.backtest.round_analysis_data_prep_service.SportApiFixtureMappingBackfillService")
@patch("app.services.backtest.round_analysis_data_prep_service.BacktestFixtureDebugService")
def test_mapping_backfill_only_when_missing(mock_debug, mock_map_cls, mock_unav_cls):
    db = MagicMock()
    cand = MagicMock()
    cand.fixture_id = 100
    mock_debug.return_value.select_fixtures_for_mini_run.return_value = MagicMock(
        items=[cand],
    )

    svc = RoundAnalysisDataPrepService()
    calls = {"n": 0}

    def _preflight(_db, _fid):
        calls["n"] += 1
        if calls["n"] == 1:
            return MagicMock(has_lineup=True, has_mapping=False, unavailable_count=0, warnings=[])
        return MagicMock(has_lineup=True, has_mapping=True, unavailable_count=0, warnings=[])

    with patch.object(svc, "_preflight_fixture", side_effect=_preflight):
        mock_map_cls.return_value.backfill.return_value = MagicMock(model_dump=lambda: {"status": "ok"})
        mock_unav_cls.return_value.backfill.return_value = MagicMock(model_dump=lambda: {"status": "ok"})

        result = svc.prepare(db, competition_id=2, season_year=2025, round_number=36)

    mock_map_cls.return_value.backfill.assert_called_once()
    assert mock_map_cls.return_value.backfill.call_args.kwargs["dry_run"] is False
    mock_unav_cls.return_value.backfill.assert_called_once()
