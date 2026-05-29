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
    FixtureProviderLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    PlayerSeasonProfile,
    TeamSotPrediction,
)
from app.services.sot_model_registry import get_model_display
from app.services.sportapi.sportapi_lineup_status import (
    competition_sportapi_lineup_confirmed_counts,
    next_round_sportapi_lineup_stats,
)
from app.services.next_round_selection import select_next_round_fixtures

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
        "sportapi_lineup_rows_count": int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderLineup)
                .where(FixtureProviderLineup.competition_id == cid)
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
    sportapi_confirmed = competition_sportapi_lineup_confirmed_counts(db, competition_id)
    counts["confirmed_lineups_count"] = sportapi_confirmed["confirmed_lineups_count"]
    counts["probable_lineups_count"] = sportapi_confirmed["probable_lineups_count"]

    all_upcoming = list(
        db.scalars(
            select(Fixture).where(
                Fixture.competition_id == competition_id,
                ~Fixture.status.in_(FINISHED_STATUSES),
            )
        ).all()
    )
    next_round_sel = select_next_round_fixtures(all_upcoming, limit=100, only_next_round=True)
    next_round_ids = [int(fx.id) for fx in next_round_sel.fixtures]
    next_round_stats = next_round_sportapi_lineup_stats(db, next_round_ids)
    next_round_lineup_coverage_pct = float(next_round_stats.get("next_round_coverage_pct") or 0.0)

    lineups_ready = (
        counts["sportapi_mappings_count"] > 0 and counts["sportapi_lineup_rows_count"] > 0
    )
    sportapi_total = int(sportapi_confirmed["sportapi_lineup_rows_count"])
    confirmed_n = int(sportapi_confirmed["confirmed_lineups_count"])
    lineups_probable_only = sportapi_total > 0 and confirmed_n == 0
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
        "lineups": counts["sportapi_lineup_rows_count"] > 0,
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
        "lineups_probable_only": lineups_probable_only,
        "confirmed_lineups_count": confirmed_n,
        "probable_lineups_count": int(sportapi_confirmed["probable_lineups_count"]),
        "next_round_lineup_coverage_pct": next_round_lineup_coverage_pct,
        "inputs_available": inputs_available,
        "counts": counts,
    }


def _model_label(model_version: str | None) -> str | None:
    if not model_version:
        return None
    display = get_model_display(str(model_version))
    return display.label if display else str(model_version)


def attach_model_selection_context(
    payload: dict[str, Any],
    ctx: dict[str, Any],
    *,
    selected_model_version: str | None = None,
    recommended_model_version: str | None = None,
) -> dict[str, Any]:
    """Merge contesto operativo e campi modello selezionato/raccomandato."""
    merged = dict(payload)
    recommended = recommended_model_version or merged.get("recommended_model_version")
    selected = selected_model_version or merged.get("selected_model_version")
    active = selected or recommended or merged.get("active_model_version")

    merged["recommended_model_version"] = recommended
    merged["recommended_model_label"] = _model_label(recommended)
    if selected:
        merged["selected_model_version"] = selected
        merged["selected_model_label"] = _model_label(selected)
    merged["active_model_version"] = active

    merged["competition_name"] = ctx.get("competition_name")
    merged["operating_mode"] = merged.get("operating_mode") or ctx["operating_mode"]
    merged["inputs_available"] = ctx["inputs_available"]
    merged["v20_operating_context"] = ctx
    merged["lineups_ready"] = ctx["lineups_ready"]
    merged["lineups_probable_only"] = ctx.get("lineups_probable_only")
    merged["confirmed_lineups_count"] = ctx.get("confirmed_lineups_count")
    merged["probable_lineups_count"] = ctx.get("probable_lineups_count")
    merged["next_round_lineup_coverage_pct"] = ctx.get("next_round_lineup_coverage_pct")
    merged.pop("global_model_version", None)
    merged.pop("global_model_label", None)
    return merged


def attach_global_v20_fields(payload: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Compat legacy: delega ad attach_model_selection_context."""
    recommended = payload.get("recommended_model_version")
    return attach_model_selection_context(
        payload,
        ctx,
        selected_model_version=payload.get("selected_model_version"),
        recommended_model_version=recommended,
    )


def operating_mode_message(mode: OperatingMode) -> str:
    if mode == "complete":
        return "v2.0 Lineup Impact (modalità completa)"
    if mode == "degraded_fallback":
        return "v2.0 senza lineups (degraded fallback)"
    return "v2.0 non pronto (input mancanti)"
