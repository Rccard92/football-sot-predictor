"""Helper per merge/upsert parziale dei modelli in Round Analysis."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backtest_round_analysis import BacktestRoundAnalysis, BacktestRoundFixtureResult
from app.services.backtest.round_analysis_preflight import model_block_is_error, model_block_is_no_prediction


COMPLETED_STATUSES = ("completed", "completed_with_warnings")


def find_latest_completed_round_analysis(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    round_number: int,
) -> BacktestRoundAnalysis | None:
    return db.scalar(
        select(BacktestRoundAnalysis)
        .where(
            BacktestRoundAnalysis.competition_id == int(competition_id),
            BacktestRoundAnalysis.season_year == int(season_year),
            BacktestRoundAnalysis.round_number == int(round_number),
            BacktestRoundAnalysis.status.in_(COMPLETED_STATUSES),
        )
        .order_by(BacktestRoundAnalysis.analysis_version.desc())
        .limit(1),
    )


def load_fixtures_for_analysis(
    db: Session,
    *,
    analysis_id: int,
) -> list[BacktestRoundFixtureResult]:
    return db.scalars(
        select(BacktestRoundFixtureResult)
        .where(BacktestRoundFixtureResult.analysis_id == int(analysis_id))
        .order_by(BacktestRoundFixtureResult.id.asc()),
    ).all()


def selected_models_already_present(
    fixture_rows: list[BacktestRoundFixtureResult],
    *,
    selected_models: list[str],
) -> bool:
    """True se ogni fixture ok ha blocchi validi per tutti i selected_models.

    Consideriamo \"mancante\" un blocco assente o con status error/no_prediction.
    """
    if not selected_models:
        return False

    for row in fixture_rows:
        if str(row.status) != "ok":
            return False
        models_json = row.models_json if isinstance(row.models_json, dict) else {}
        for key in selected_models:
            block = models_json.get(key)
            if not isinstance(block, dict):
                return False
            if model_block_is_error(block) or model_block_is_no_prediction(block):
                return False
    return True


def preserved_model_keys_from_fixture(
    fixture: BacktestRoundFixtureResult,
    *,
    selected_models: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    models_json = fixture.models_json if isinstance(fixture.models_json, dict) else {}
    explanation_json = fixture.explanation_json if isinstance(fixture.explanation_json, dict) else {}

    preserved_models = {k: v for k, v in models_json.items() if k not in selected_models}
    preserved_explanations = {k: v for k, v in explanation_json.items() if k not in selected_models}
    return preserved_models, preserved_explanations

