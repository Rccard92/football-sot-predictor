"""Motore v1.1 Round Analysis — stesso percorso di SotPredictionV11BaselineSotService."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext, build_prior_context
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.predictions_v11.v11_side_result import V11SideResult


def build_v11_prior_context(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
    competition_id: int,
) -> V10PriorContext:
    """Contesto prior identico al generate v1.1 produzione (no flag PIT)."""
    return build_prior_context(
        db,
        fixture,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
        competition_id=int(competition_id),
    )


def predict_v11_side_for_team(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
    competition_id: int,
) -> tuple[V11SideResult, V10PriorContext]:
    """Esegue compute_v11_side con contesto produzione per un lato."""
    ctx = build_v11_prior_context(
        db,
        fixture,
        team_id=team_id,
        opponent_id=opponent_id,
        competition_id=competition_id,
    )
    result = compute_v11_side(db, ctx, ctx.team_prior_fixtures)
    return result, ctx
