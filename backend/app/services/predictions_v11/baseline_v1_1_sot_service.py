from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V11_SOT, FINISHED_STATUSES
from app.models import Fixture, League, Season, Team, TeamSotPrediction
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.predictions_v10.v10_prior_context import build_prior_context
from app.services.predictions_v11.offensive_production_strict import compute_v11_side
from app.services.sot_feature_registry import V11_ARCHITECTURE, V11_MODEL_STAGE


class SotPredictionV11BaselineSotService:
    """v1.1 stage 3: 45% offensiva + 35% difensiva + 20% split casa/trasferta (strict)."""

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

    def generate_for_upcoming_season(self, db: Session, season_year: int, *, limit: int = 200) -> dict[str, Any]:
        try:
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
                    "errors": [],
                },
            }

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
                    "errors": [],
                },
            }

        valid_n = 0
        incomplete_n = 0
        created = 0
        missing_required_data: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
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

                existing.raw_json = merged
                existing.explanation = (
                    "v1.1 stage 3: 45% produzione offensiva + 35% resistenza difensiva avversaria "
                    "+ 20% split casa/trasferta (solo dati reali, nessun fallback)."
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
            "formula_terms_count": 3,
            "architecture": self.architecture,
            "upcoming_fixtures": len(upcoming),
            "predictions_created_or_updated": int(created),
            "valid_predictions": int(valid_n),
            "incomplete_predictions": int(incomplete_n),
            "missing_required_data_count": len(missing_required_data),
            "missing_required_data": missing_required_data,
            "errors": errors,
        }
