"""Contesto operativo modelli globali — diagnostica input per competition (no formula)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
)
from app.models import (
    Fixture,
    FixtureLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    PlayerSeasonProfile,
    TeamSotPrediction,
)
from app.services.sot_model_registry import get_model_display

OperatingMode = str  # complete | degraded_fallback | not_ready


def _competition_input_counts(db: Session, competition_id: int) -> dict[str, int]:
    cid = int(competition_id)
    return {
        "team_stats_count": int(
            db.scalar(
                select(func.count())
                .select_from(FixtureTeamStat)
                .where(FixtureTeamStat.competition_id == cid)
            )
            or 0
        ),
        "player_profiles_count": int(
            db.scalar(
                select(func.count())
                .select_from(PlayerSeasonProfile)
                .where(PlayerSeasonProfile.competition_id == cid)
            )
            or 0
        ),
        "lineup_rows_count": int(
            db.scalar(
                select(func.count())
                .select_from(FixtureLineup)
                .where(FixtureLineup.competition_id == cid)
            )
            or 0
        ),
        "sportapi_mappings_count": int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderMapping)
                .where(FixtureProviderMapping.competition_id == cid)
            )
            or 0
        ),
        "upcoming_fixtures_count": int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(
                    Fixture.competition_id == cid,
                    ~Fixture.status.in_(FINISHED_STATUSES),
                )
            )
            or 0
        ),
        "v11_predictions_count": int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(
                    Fixture.competition_id == cid,
                    TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V11_SOT,
                )
            )
            or 0
        ),
        "v20_predictions_count": int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(
                    Fixture.competition_id == cid,
                    TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                )
            )
            or 0
        ),
    }


def resolve_operating_mode(
    *,
    lineups_ready: bool,
    v11_base_ready: bool,
    upcoming_fixtures_count: int,
) -> OperatingMode:
    if upcoming_fixtures_count <= 0 or not v11_base_ready:
        return "not_ready"
    if lineups_ready:
        return "complete"
    return "degraded_fallback"


def build_v20_operating_context(db: Session, comp: Any) -> dict[str, Any]:
    """
    Diagnostica v2.0 globale per una competition.
    Il model_version resta sempre baseline_v2_0_lineup_impact; cambia solo operating_mode.
    """
    competition_id = int(comp.id)
    counts = _competition_input_counts(db, competition_id)
    lineups_ready = counts["lineup_rows_count"] > 0 and counts["sportapi_mappings_count"] > 0
    v11_base_ready = counts["team_stats_count"] > 0 or counts["player_profiles_count"] > 0
    operating_mode = resolve_operating_mode(
        lineups_ready=lineups_ready,
        v11_base_ready=v11_base_ready,
        upcoming_fixtures_count=counts["upcoming_fixtures_count"],
    )

    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    inputs_available = {
        "team_stats": counts["team_stats_count"] > 0,
        "player_profiles": counts["player_profiles_count"] > 0,
        "lineups": counts["lineup_rows_count"] > 0,
        "sportapi_mappings": counts["sportapi_mappings_count"] > 0,
        "v11_base_ready": v11_base_ready,
        "upcoming_fixtures": counts["upcoming_fixtures_count"] > 0,
    }

    return {
        "global_model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        "global_model_label": display.label if display else BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        "competition_id": competition_id,
        "competition_name": getattr(comp, "name", None),
        "competition_key": getattr(comp, "key", None),
        "operating_mode": operating_mode,
        "lineups_ready": lineups_ready,
        "inputs_available": inputs_available,
        "counts": counts,
    }


def attach_global_v20_fields(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Merge campi globali v2.0 nel payload model-status."""
    merged = dict(payload)
    merged["global_model_version"] = ctx["global_model_version"]
    merged["global_model_label"] = ctx["global_model_label"]
    merged["competition_name"] = ctx.get("competition_name")
    merged["operating_mode"] = ctx["operating_mode"]
    merged["inputs_available"] = ctx["inputs_available"]
    merged["v20_operating_context"] = ctx
    merged["lineups_ready"] = ctx["lineups_ready"]
    return merged


def operating_mode_message(mode: OperatingMode) -> str:
    if mode == "complete":
        return "v2.0 Lineup Impact (modalità completa)"
    if mode == "degraded_fallback":
        return "v2.0 senza lineups (degraded fallback)"
    return "v2.0 non pronto (input mancanti)"
