from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT, FINISHED_STATUSES
from app.models import Fixture, League, Season, Team, TeamSotPrediction
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.predictions_v10.v10_prior_context import build_prior_context
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.predictions_v11.player_layer_feature_sources import (
    COMPONENT_KEY_PLAYER,
    PLAYER_LAYER_MODE_HISTORICAL,
    PLAYER_LAYER_MODE_LINEUP,
)
from app.services.predictions_v11.player_layer_lineup_helpers import fixture_both_lineups_available
from app.services.predictions_v11.xg_feature_sources import COMPONENT_KEY_XG
from app.services.sot_feature_registry import V11_ARCHITECTURE, V11_MODEL_STAGE


class SotPredictionV11BaselineSotService:
    """v1.1 stage 6: 6 componenti strict (incluso player layer da player_season_profiles)."""

    model_version = BASELINE_SOT_MODEL_VERSION_V11_SOT
    architecture = V11_ARCHITECTURE
    model_stage = V11_MODEL_STAGE

    def _season_row(self, db: Session, season_year: int) -> tuple[League, Season]:
        from app.core.config import get_settings
        from app.services.ingestion_service import IngestionService

        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            settings = get_settings()
            league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            raise ValueError("league_not_found")

        season = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season_year)))
        if season is None:
            raise ValueError("season_not_found")
        return league, season

    def generate_for_upcoming_season(
        self,
        db: Session,
        season_year: int,
        *,
        limit: int = 200,
        competition_id: int | None = None,
        fixture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        try:
            if competition_id is not None:
                _league, season = None, None
            else:
                _league, season = self._season_row(db, season_year)
        except Exception as exc:
            return {
                "status": "error",
                "failed_step": "load_season",
                "message": "Impossibile caricare league/season.",
                "details": str(exc),
                "partial_result": {
                    "upcoming_fixtures": 0,
                    "predictions_created_or_updated": 0,
                    "valid_predictions": 0,
                    "incomplete_predictions": 0,
                    "xg_available_predictions": 0,
                    "xg_missing_predictions": 0,
                    "errors": [],
                },
            }

        if fixture_ids:
            q = (
                select(Fixture)
                .where(Fixture.id.in_([int(x) for x in fixture_ids]))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
            )
            if competition_id is not None:
                q = q.where(Fixture.competition_id == competition_id)
            fixtures = db.scalars(q).all()
        elif competition_id is not None:
            fixtures = db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == competition_id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
        else:
            fixtures = db.scalars(
                select(Fixture).where(Fixture.season_id == season.id).order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
        upcoming = [f for f in fixtures if (f.status or "").upper() not in FINISHED_STATUSES][:limit]

        if not upcoming:
            return {
                "status": "error",
                "failed_step": "no_upcoming_fixtures",
                "message": "Nessuna fixture upcoming trovata per la stagione richiesta.",
                "details": f"season={int(season_year)}",
                "partial_result": {
                    "upcoming_fixtures": 0,
                    "predictions_created_or_updated": 0,
                    "valid_predictions": 0,
                    "incomplete_predictions": 0,
                    "xg_available_predictions": 0,
                    "xg_missing_predictions": 0,
                    "errors": [],
                },
            }

        valid_n = 0
        incomplete_n = 0
        created = 0
        xg_available_n = 0
        xg_missing_n = 0
        player_layer_available_n = 0
        player_layer_missing_n = 0
        lineup_adjusted_n = 0
        historical_player_layer_n = 0
        lineups_missing_n = 0
        missing_required_data: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
            if competition_id is not None and fx.competition_id != int(competition_id):
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "error": "guardrail_competition_id",
                        "message": f"Fixture competition_id={fx.competition_id} != {competition_id}",
                    },
                )
                continue
            opp_by_team = {
                int(fx.home_team_id): int(fx.away_team_id),
                int(fx.away_team_id): int(fx.home_team_id),
            }
            for team_id in (int(fx.home_team_id), int(fx.away_team_id)):
                try:
                    ctx = build_prior_context(
                        db,
                        fx,
                        team_id=int(team_id),
                        opponent_id=int(opp_by_team[int(team_id)]),
                        competition_id=competition_id,
                    )
                    result = compute_v11_side(db, ctx, ctx.team_prior_fixtures)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "computation_failed",
                            "message": str(exc)[:500],
                        },
                    )
                    continue

                merged = dict(result.raw_json)
                fq_stat = str(result.formula_quality_status or merged.get("formula_quality_status") or "")
                comps_m = merged.get("components") if isinstance(merged.get("components"), dict) else {}
                has_xg_comp = isinstance(comps_m.get(COMPONENT_KEY_XG), dict) or isinstance(
                    merged.get(COMPONENT_KEY_XG),
                    dict,
                )
                has_player_comp = isinstance(comps_m.get(COMPONENT_KEY_PLAYER), dict) or isinstance(
                    merged.get(COMPONENT_KEY_PLAYER),
                    dict,
                )
                if fq_stat == "ok" and has_xg_comp:
                    xg_available_n += 1
                elif fq_stat in ("insufficient_xg_sample", "missing_required_xg_league_baseline"):
                    xg_missing_n += 1
                player_comp_blob = comps_m.get(COMPONENT_KEY_PLAYER) if isinstance(
                    comps_m.get(COMPONENT_KEY_PLAYER),
                    dict,
                ) else merged.get(COMPONENT_KEY_PLAYER)
                if not isinstance(player_comp_blob, dict):
                    player_comp_blob = None

                if fq_stat == "ok" and has_player_comp:
                    player_layer_available_n += 1
                    pl_mode = str((player_comp_blob or {}).get("mode") or PLAYER_LAYER_MODE_HISTORICAL)
                    if pl_mode == PLAYER_LAYER_MODE_LINEUP:
                        lineup_adjusted_n += 1
                    elif pl_mode == PLAYER_LAYER_MODE_HISTORICAL:
                        historical_player_layer_n += 1
                        both_lu = fixture_both_lineups_available(
                            db,
                            fixture_id=int(fx.id),
                            home_team_id=int(fx.home_team_id),
                            away_team_id=int(fx.away_team_id),
                        )
                        if not both_lu:
                            lineups_missing_n += 1
                elif fq_stat in (
                    "insufficient_player_profile_sample",
                    "missing_required_player_league_baseline",
                ):
                    player_layer_missing_n += 1
                team_row = db.get(Team, int(team_id))
                tname = team_row.name if team_row is not None else str(team_id)
                merged = append_trace_to_raw_json(
                    merged,
                    model_version=self.model_version,
                    team_id=int(team_id),
                    team_name=tname,
                    audit_map={},
                    hours_to_kickoff=compute_hours_to_kickoff(fx.kickoff_at),
                    prediction_confidence=None,
                )

                existing = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == int(team_id),
                        TeamSotPrediction.model_version == self.model_version,
                    ),
                )
                if existing is None:
                    existing = TeamSotPrediction(
                        fixture_id=int(fx.id),
                        team_id=int(team_id),
                        model_version=self.model_version,
                    )
                    db.add(existing)

                if fx.competition_id is not None:
                    existing.competition_id = int(fx.competition_id)
                elif competition_id is not None:
                    existing.competition_id = int(competition_id)

                existing.raw_json = merged
                existing.explanation = (
                    "v1.1 stage 6: 25% produzione offensiva + 22% resistenza difensiva avversaria "
                    "+ 13% split casa/trasferta + 15% forma recente + 12% qualità occasioni / xG "
                    "+ 13% player layer (profili storici player_season_profiles; "
                    "solo dati reali, nessun fallback)."
                )

                if result.valid and result.expected_sot is not None:
                    existing.predicted_sot = float(result.expected_sot)
                    valid_n += 1
                else:
                    existing.predicted_sot = None
                    incomplete_n += 1
                    miss_keys = [m.get("feature_key") for m in result.missing_required_fields if m.get("feature_key")]
                    if miss_keys:
                        missing_required_data.append(
                            {
                                "fixture_id": int(fx.id),
                                "team_id": int(team_id),
                                "missing": miss_keys,
                                "formula_quality_status": result.formula_quality_status,
                            },
                        )

                created += 1
                try:
                    db.commit()
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "persist_failed",
                            "message": str(exc),
                        },
                    )

        status = "success"
        if incomplete_n > 0 and valid_n > 0:
            status = "partial_success"
        elif incomplete_n > 0 and valid_n == 0:
            status = "partial_success"

        return {
            "status": status,
            "season": int(season_year),
            "model_version": self.model_version,
            "model_stage": self.model_stage,
            "formula_terms_count": 6,
            "architecture": self.architecture,
            "upcoming_fixtures": len(upcoming),
            "predictions_created_or_updated": int(created),
            "valid_predictions": int(valid_n),
            "incomplete_predictions": int(incomplete_n),
            "xg_available_predictions": int(xg_available_n),
            "xg_missing_predictions": int(xg_missing_n),
            "player_layer_available_predictions": int(player_layer_available_n),
            "player_layer_missing_predictions": int(player_layer_missing_n),
            "lineup_adjusted_predictions": int(lineup_adjusted_n),
            "historical_player_layer_predictions": int(historical_player_layer_n),
            "lineups_missing_predictions": int(lineups_missing_n),
            "missing_required_data_count": len(missing_required_data),
            "missing_required_data": missing_required_data,
            "errors": errors,
        }

    def generate_for_competition(
        self,
        db: Session,
        competition_id: int,
        *,
        limit: int = 200,
        fixture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        from app.models import Competition

        comp = db.get(Competition, competition_id)
        if comp is None:
            return {"status": "error", "message": f"Competition {competition_id} non trovata"}
        result = self.generate_for_upcoming_season(
            db,
            comp.season,
            limit=limit,
            competition_id=comp.id,
            fixture_ids=fixture_ids,
        )
        result["competition_id"] = comp.id
        return result
