from __future__ import annotations

from collections import defaultdict
import logging
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION, BASELINE_SOT_MODEL_VERSION_V02, FINISHED_STATUSES
from app.models import (
    Fixture,
    League,
    PlayerAvailabilityEvent,
    PlayerSotProfile,
    Season,
    StandingEntry,
    StandingsSnapshot,
    Team,
    TeamSotPrediction,
    TeamSotPredictionAdjustment,
)
from app.services.h2h_service import build_h2h_summary_for_fixture
from app.services.match_context_service import MatchContextService
from app.services.predictions_v02.adjustments_availability import compute_availability_adjustment
from app.services.predictions_v02.adjustments_h2h import compute_h2h_adjustment
from app.services.predictions_v02.adjustments_motivation import compute_motivation_adjustment
from app.services.predictions_v02.adjustments_player import compute_player_adjustment
from app.services.predictions_v02.math_utils import cap as _cap
from app.services.predictions_v02.math_utils import round2 as _round2
from app.services.predictions_v02.pipeline import generate_v02_for_upcoming_season as _generate_v02_for_upcoming_season
from app.services.predictions_v02.prediction_math import compute_adjusted_prediction, compute_confidence_v02

logger = logging.getLogger(__name__)


class SotPredictionV02Service:
    model_version = BASELINE_SOT_MODEL_VERSION_V02

    @staticmethod
    def _empty_partial_result() -> dict[str, Any]:
        return {
            "upcoming_fixtures_found": 0,
            "predictions_created_or_updated": 0,
            "errors": [],
        }

    def _error_result(
        self,
        *,
        failed_step: str,
        message: str,
        details: str | None = None,
        partial_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "failed_step": failed_step,
            "message": message,
            "details": details,
            "partial_result": partial_result or self._empty_partial_result(),
        }

    def _adjustments_table_exists(self, db: Session) -> bool:
        bind = db.get_bind()
        return bool(inspect(bind).has_table("team_sot_prediction_adjustments"))

    def _season_row(self, db: Session, season_year: int):
        league = db.scalar(
            select(League).where(League.api_league_id == 135).order_by(League.id.asc()),
        )
        if league is None:
            raise ValueError("league_not_found")
        season = db.scalar(
            select(Season).where(Season.league_id == league.id, Season.year == season_year),
        )
        if season is None:
            raise ValueError("season_not_found")
        return league, season

    def _top_profiles_for_team(self, db: Session, season_id: int, team_id: int, limit: int = 5) -> list[PlayerSotProfile]:
        return db.scalars(
            select(PlayerSotProfile)
            .where(PlayerSotProfile.season_id == season_id, PlayerSotProfile.team_id == team_id)
            .order_by(PlayerSotProfile.impact_score.desc().nulls_last())
            .limit(limit),
        ).all()

    def _league_avg_top5_impact(self, db: Session, season_id: int) -> float | None:
        rows = db.execute(
            select(PlayerSotProfile.team_id, func.avg(PlayerSotProfile.impact_score))
            .where(PlayerSotProfile.season_id == season_id)
            .group_by(PlayerSotProfile.team_id),
        ).all()
        vals = [float(avg) for _tid, avg in rows if avg is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def compute_player_adjustment(
        self,
        *,
        team_top5_avg_impact: float | None,
        league_avg_top5_impact: float | None,
    ) -> tuple[float, dict[str, Any]]:
        return compute_player_adjustment(
            team_top5_avg_impact=team_top5_avg_impact,
            league_avg_top5_impact=league_avg_top5_impact,
        )

    def compute_availability_adjustment(
        self,
        *,
        top_profiles: list[PlayerSotProfile],
        availability_events: list[PlayerAvailabilityEvent],
    ) -> tuple[float, dict[str, Any]]:
        return compute_availability_adjustment(
            top_profiles=top_profiles,
            availability_events=availability_events,
        )

    def compute_h2h_adjustment(
        self,
        *,
        baseline_expected_sot: float,
        h2h_summary: dict[str, Any],
        is_home: bool,
    ) -> tuple[float, dict[str, Any]]:
        return compute_h2h_adjustment(
            baseline_expected_sot=baseline_expected_sot,
            h2h_summary=h2h_summary,
            is_home=is_home,
        )

    def compute_motivation_adjustment(
        self,
        *,
        team_context: dict[str, Any] | None,
        opp_context: dict[str, Any] | None,
    ) -> tuple[float, dict[str, Any]]:
        return compute_motivation_adjustment(
            team_context=team_context,
            opp_context=opp_context,
        )

    def compute_confidence_v02(
        self,
        *,
        base_score: int,
        has_player_profiles: bool,
        h2h_matches_total: int,
        late_season_risk: bool,
        turnover_high_any: bool,
        availability_not_available: bool,
        abs_total_adjustment: float,
    ) -> tuple[int, str]:
        return compute_confidence_v02(
            base_score=base_score,
            has_player_profiles=has_player_profiles,
            h2h_matches_total=h2h_matches_total,
            late_season_risk=late_season_risk,
            turnover_high_any=turnover_high_any,
            availability_not_available=availability_not_available,
            abs_total_adjustment=abs_total_adjustment,
        )

    def compute_adjusted_prediction(
        self,
        *,
        baseline_expected_sot: float,
        player_adjustment: float,
        h2h_adjustment: float,
        motivation_adjustment: float,
        availability_adjustment: float,
    ) -> tuple[float, float]:
        return compute_adjusted_prediction(
            baseline_expected_sot=baseline_expected_sot,
            player_adjustment=player_adjustment,
            h2h_adjustment=h2h_adjustment,
            motivation_adjustment=motivation_adjustment,
            availability_adjustment=availability_adjustment,
        )

    def _upsert_adjustment_row(
        self,
        db: Session,
        *,
        prediction: TeamSotPrediction,
        fixture_id: int,
        team_id: int,
        baseline_expected_sot: float,
        player_adjustment: float,
        h2h_adjustment: float,
        motivation_adjustment: float,
        availability_adjustment: float,
        total_adjustment: float,
        adjusted_expected_sot: float,
        breakdown: dict[str, Any],
    ) -> None:
        row = db.scalar(
            select(TeamSotPredictionAdjustment).where(
                TeamSotPredictionAdjustment.fixture_id == fixture_id,
                TeamSotPredictionAdjustment.team_id == team_id,
                TeamSotPredictionAdjustment.model_version == self.model_version,
            ),
        )
        if row is None:
            row = TeamSotPredictionAdjustment(
                prediction_id=prediction.id,
                fixture_id=fixture_id,
                team_id=team_id,
                model_version=self.model_version,
                baseline_expected_sot=baseline_expected_sot,
                player_adjustment=player_adjustment,
                h2h_adjustment=h2h_adjustment,
                motivation_adjustment=motivation_adjustment,
                availability_adjustment=availability_adjustment,
                total_adjustment=total_adjustment,
                adjusted_expected_sot=adjusted_expected_sot,
                adjustment_breakdown=breakdown,
            )
            db.add(row)
        else:
            row.prediction_id = prediction.id
            row.baseline_expected_sot = baseline_expected_sot
            row.player_adjustment = player_adjustment
            row.h2h_adjustment = h2h_adjustment
            row.motivation_adjustment = motivation_adjustment
            row.availability_adjustment = availability_adjustment
            row.total_adjustment = total_adjustment
            row.adjusted_expected_sot = adjusted_expected_sot
            row.adjustment_breakdown = breakdown
        db.flush()

    def generate_v02_for_upcoming_season(self, db: Session, season_year: int) -> dict[str, Any]:
        return _generate_v02_for_upcoming_season(self, db, season_year)

    def v02_readiness(self, db: Session, season_year: int) -> dict[str, Any]:
        message: str | None = None
        try:
            _league, season = self._season_row(db, season_year)
        except ValueError:
            return {
                "season": season_year,
                "upcoming_fixtures": 0,
                "baseline_v01_upcoming_predictions": 0,
                "player_profiles_available": False,
                "standings_available": False,
                "adjustments_table_exists": self._adjustments_table_exists(db),
                "ready": False,
                "missing_requirements": ["season_not_found"],
                "message": f"Season Serie A {season_year} non trovata. Esegui prima il bootstrap.",
            }
        except Exception as exc:
            logger.exception("v02 readiness failed on season lookup")
            return {
                "season": season_year,
                "upcoming_fixtures": 0,
                "baseline_v01_upcoming_predictions": 0,
                "player_profiles_available": False,
                "standings_available": False,
                "adjustments_table_exists": False,
                "ready": False,
                "missing_requirements": ["readiness_lookup_failed"],
                "message": f"Readiness non disponibile: {exc.__class__.__name__}",
            }
        upcoming_fixtures = int(
            db.scalar(
                select(func.count())
                .select_from(Fixture)
                .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES)),
            )
            or 0
        )
        baseline_v01_upcoming_predictions = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(
                    Fixture.season_id == season.id,
                    ~Fixture.status.in_(FINISHED_STATUSES),
                    TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                ),
            )
            or 0
        )
        player_profiles_available = bool(
            db.scalar(
                select(func.count())
                .select_from(PlayerSotProfile)
                .where(PlayerSotProfile.season_id == season.id),
            )
            or 0
        )
        standings_available = bool(
            db.scalar(
                select(func.count())
                .select_from(StandingsSnapshot)
                .where(StandingsSnapshot.season_id == season.id),
            )
            or 0
        ) or bool(
            db.scalar(
                select(func.count())
                .select_from(StandingEntry)
                .where(StandingEntry.season_id == season.id),
            )
            or 0
        )
        adjustments_table_exists = self._adjustments_table_exists(db)
        missing_requirements: list[str] = []
        if upcoming_fixtures <= 0:
            missing_requirements.append("upcoming_fixtures_missing")
        if baseline_v01_upcoming_predictions < (upcoming_fixtures * 2):
            missing_requirements.append("baseline_v01_upcoming_predictions_insufficient")
        if not adjustments_table_exists:
            missing_requirements.append("adjustments_table_missing")
        if not player_profiles_available:
            missing_requirements.append("player_profiles_not_available")
        if not standings_available:
            missing_requirements.append("standings_not_available")
        if "season_not_found" in missing_requirements:
            message = f"Season Serie A {season_year} non trovata. Esegui prima il bootstrap."
        return {
            "season": season_year,
            "upcoming_fixtures": upcoming_fixtures,
            "baseline_v01_upcoming_predictions": baseline_v01_upcoming_predictions,
            "player_profiles_available": player_profiles_available,
            "standings_available": standings_available,
            "adjustments_table_exists": adjustments_table_exists,
            "ready": (
                upcoming_fixtures > 0
                and baseline_v01_upcoming_predictions >= (upcoming_fixtures * 2)
                and adjustments_table_exists
            ),
            "missing_requirements": missing_requirements,
            "message": message,
        }

    def upcoming_v02(self, db: Session, season_year: int, *, limit: int = 20, only_next_round: bool = True) -> dict[str, Any]:
        _league, season = self._season_row(db, season_year)
        fixtures = db.scalars(
            select(Fixture)
            .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()
        if only_next_round and fixtures:
            r0 = fixtures[0].round
            if r0:
                fixtures = [f for f in fixtures if f.round == r0]
        fixtures = fixtures[: max(1, min(limit, 100))]
        matches: list[dict[str, Any]] = []
        for fx in fixtures:
            home = db.get(Team, fx.home_team_id)
            away = db.get(Team, fx.away_team_id)
            home_pred = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == fx.id,
                    TeamSotPrediction.team_id == fx.home_team_id,
                    TeamSotPrediction.model_version == self.model_version,
                ),
            )
            away_pred = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == fx.id,
                    TeamSotPrediction.team_id == fx.away_team_id,
                    TeamSotPrediction.model_version == self.model_version,
                ),
            )
            home_adj = db.scalar(
                select(TeamSotPredictionAdjustment).where(
                    TeamSotPredictionAdjustment.fixture_id == fx.id,
                    TeamSotPredictionAdjustment.team_id == fx.home_team_id,
                    TeamSotPredictionAdjustment.model_version == self.model_version,
                ),
            )
            away_adj = db.scalar(
                select(TeamSotPredictionAdjustment).where(
                    TeamSotPredictionAdjustment.fixture_id == fx.id,
                    TeamSotPredictionAdjustment.team_id == fx.away_team_id,
                    TeamSotPredictionAdjustment.model_version == self.model_version,
                ),
            )
            def side_payload(pred: TeamSotPrediction | None, adj: TeamSotPredictionAdjustment | None) -> dict[str, Any] | None:
                if pred is None or adj is None:
                    return None
                breakdown = adj.adjustment_breakdown or {}
                conf = breakdown.get("confidence_v02") or {}
                return {
                    "baseline_expected_sot": _round2(adj.baseline_expected_sot),
                    "adjusted_expected_sot": _round2(adj.adjusted_expected_sot),
                    "total_adjustment": _round2(adj.total_adjustment),
                    "player_adjustment": _round2(adj.player_adjustment),
                    "h2h_adjustment": _round2(adj.h2h_adjustment),
                    "motivation_adjustment": _round2(adj.motivation_adjustment),
                    "availability_adjustment": _round2(adj.availability_adjustment),
                    "prediction_confidence_score_v0_2": int(conf.get("prediction_confidence_score_v0_2") or pred.confidence_score or 60),
                    "prediction_confidence_label_v0_2": str(conf.get("prediction_confidence_label_v0_2") or "Media"),
                    "adjustment_breakdown": breakdown,
                    "adjustments": {
                        "player": breakdown.get("player"),
                        "h2h": breakdown.get("h2h"),
                        "motivation": breakdown.get("motivation"),
                        "availability": breakdown.get("availability"),
                    },
                }
            hp = side_payload(home_pred, home_adj)
            ap = side_payload(away_pred, away_adj)
            matches.append(
                {
                    "fixture_id": fx.id,
                    "api_fixture_id": int(fx.api_fixture_id),
                    "round": fx.round,
                    "kickoff_at": fx.kickoff_at,
                    "status_short": fx.status,
                    "home_team": {"id": fx.home_team_id, "name": home.name if home else "", "logo_url": home.logo_url if home else None},
                    "away_team": {"id": fx.away_team_id, "name": away.name if away else "", "logo_url": away.logo_url if away else None},
                    "home_prediction_v02": hp,
                    "away_prediction_v02": ap,
                    "total_expected_sot_baseline": (_round2((hp or {}).get("baseline_expected_sot", 0) + (ap or {}).get("baseline_expected_sot", 0)) if hp and ap else None),
                    "total_expected_sot_v02": (_round2((hp or {}).get("adjusted_expected_sot", 0) + (ap or {}).get("adjusted_expected_sot", 0)) if hp and ap else None),
                },
            )
        return {
            "status": "success",
            "season": season_year,
            "model_version": self.model_version,
            "matches_count": len(matches),
            "matches": matches,
        }

    def v02_available_for_fixture_ids(self, db: Session, fixture_ids: list[int]) -> dict[int, bool]:
        if not fixture_ids:
            return {}
        rows = db.execute(
            select(
                TeamSotPrediction.fixture_id,
                func.count(),
            )
            .where(
                TeamSotPrediction.fixture_id.in_(fixture_ids),
                TeamSotPrediction.model_version == self.model_version,
            )
            .group_by(TeamSotPrediction.fixture_id),
        ).all()
        counts = {int(fid): int(n) for fid, n in rows}
        return {int(fid): counts.get(int(fid), 0) >= 2 for fid in fixture_ids}

    def dashboard_block(self, db: Session, season_year: int) -> dict[str, Any]:
        _league, season = self._season_row(db, season_year)
        rows = db.scalars(
            select(TeamSotPredictionAdjustment)
            .join(Fixture, Fixture.id == TeamSotPredictionAdjustment.fixture_id)
            .where(
                Fixture.season_id == season.id,
                TeamSotPredictionAdjustment.model_version == self.model_version,
                ~Fixture.status.in_(FINISHED_STATUSES),
            ),
        ).all()
        if not rows:
            return {
                "v02_predictions_upcoming": 0,
                "avg_total_adjustment": 0.0,
                "avg_player_adjustment": 0.0,
                "avg_h2h_adjustment": 0.0,
                "avg_motivation_adjustment": 0.0,
                "matches_with_context_warning": 0,
            }
        by_fixture: dict[int, list[TeamSotPredictionAdjustment]] = defaultdict(list)
        for r in rows:
            by_fixture[int(r.fixture_id)].append(r)
        warns = 0
        for fixture_rows in by_fixture.values():
            if any(bool((r.adjustment_breakdown or {}).get("motivation", {}).get("late_season_risk")) for r in fixture_rows):
                warns += 1
        n = len(rows)
        return {
            "v02_predictions_upcoming": n,
            "avg_total_adjustment": _round2(sum(float(r.total_adjustment or 0) for r in rows) / n),
            "avg_player_adjustment": _round2(sum(float(r.player_adjustment or 0) for r in rows) / n),
            "avg_h2h_adjustment": _round2(sum(float(r.h2h_adjustment or 0) for r in rows) / n),
            "avg_motivation_adjustment": _round2(sum(float(r.motivation_adjustment or 0) for r in rows) / n),
            "matches_with_context_warning": warns,
        }
