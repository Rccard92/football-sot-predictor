"""Verifica import modelli Backtest Engine (no circular import)."""


def test_backtest_models_tabulenames():
    from app.models import (
        BacktestPick,
        BacktestPrediction,
        BacktestRoundAnalysis,
        BacktestRoundFixtureResult,
        BacktestRun,
        BacktestRunMetric,
    )

    assert BacktestRun.__tablename__ == "backtest_runs"
    assert BacktestRoundAnalysis.__tablename__ == "backtest_round_analyses"
    assert BacktestRoundFixtureResult.__tablename__ == "backtest_round_fixture_results"
    assert BacktestPrediction.__tablename__ == "backtest_predictions"
    assert BacktestPick.__tablename__ == "backtest_picks"
    assert BacktestRunMetric.__tablename__ == "backtest_run_metrics"


def test_import_app_main_still_works():
    from app.main import app

    assert app.title
