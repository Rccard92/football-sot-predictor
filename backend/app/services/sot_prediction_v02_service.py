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

logger = logging.getLogger(__name__)


def _round2(v: float) -> float:
    return round(float(v), 2)


def _cap(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


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

    def compute_player_adjustment(self, *, team_top5_avg_impact: float | None, league_avg_top5_impact: float | None) -> tuple[float, dict[str, Any]]:
        if team_top5_avg_impact is None or league_avg_top5_impact is None or league_avg_top5_impact <= 0:
            return 0.0, {
                "status": "not_available",
                "explanation": "Profili giocatore non sufficienti per calcolare adjustment.",
            }
        ratio = team_top5_avg_impact / league_avg_top5_impact
        if ratio >= 1.25:
            adj = 0.35
        elif ratio >= 1.10:
            adj = 0.20
        elif ratio <= 0.75:
            adj = -0.35
        elif ratio <= 0.90:
            adj = -0.20
        else:
            adj = 0.0
        adj = _cap(adj, -0.35, 0.35)
        return _round2(adj), {
            "status": "applied",
            "team_top5_avg_impact": _round2(team_top5_avg_impact),
            "league_avg_top5_impact": _round2(league_avg_top5_impact),
            "player_strength_ratio": round(ratio, 4),
            "adjustment": _round2(adj),
            "explanation": "Adjustment player impact applicato con regole prudenti e cap ±0.35.",
        }

    def compute_availability_adjustment(
        self,
        *,
        top_profiles: list[PlayerSotProfile],
        availability_events: list[PlayerAvailabilityEvent],
    ) -> tuple[float, dict[str, Any]]:
        if not availability_events:
            return 0.0, {"status": "not_available", "availability_status": "not_available"}
        if not top_profiles:
            return 0.0, {
                "status": "not_reliable",
                "availability_status": "not_reliable",
                "reliability_note": "Nessun top player disponibile per matching affidabile.",
            }
        penalties = 0.0
        matched: list[dict[str, Any]] = []
        top_by_rank = sorted(top_profiles, key=lambda p: float(p.impact_score or 0), reverse=True)
        for ev in availability_events:
            matched_profile = None
            for idx, p in enumerate(top_by_rank[:3], start=1):
                if (ev.player_id is not None and ev.player_id == p.player_id) or (
                    ev.player_name and p.player and ev.player_name.lower() in p.player.name.lower()
                ):
                    matched_profile = (idx, p)
                    break
            if matched_profile is None:
                continue
            rank, profile = matched_profile
            if rank == 1:
                pen = -0.35
            else:
                pen = -0.25
            penalties += pen
            matched.append(
                {
                    "player_id": profile.player_id,
                    "player_name": ev.player_name,
                    "rank_in_top": rank,
                    "penalty": pen,
                },
            )
        penalties = _cap(penalties, -0.45, 0.0)
        return _round2(penalties), {
            "status": "applied" if matched else "not_reliable",
            "availability_status": "available" if matched else "not_reliable",
            "unavailable_players_considered": len(availability_events),
            "matched_top_players": matched,
            "penalty": _round2(penalties),
            "reliability_note": (
                "Penalità applicata solo su matching affidabile con top player."
                if matched
                else "Eventi availability presenti ma matching top player non affidabile."
            ),
        }

    def compute_h2h_adjustment(self, *, baseline_expected_sot: float, h2h_summary: dict[str, Any], is_home: bool) -> tuple[float, dict[str, Any]]:
        if not h2h_summary or h2h_summary.get("h2h_fetch_ok") is not True:
            return 0.0, {"status": "not_available"}
        if not h2h_summary.get("h2h_sot_available"):
            return 0.0, {"status": "not_available", "explanation": "SOT H2H non disponibile."}
        matches_total = int(h2h_summary.get("matches_total") or 0)
        sample_limited = bool(h2h_summary.get("h2h_sample_limited"))
        if matches_total < 5:
            return 0.0, {"status": "not_reliable", "h2h_matches_total": matches_total}
        team_avg = h2h_summary.get("avg_home_sot") if is_home else h2h_summary.get("avg_away_sot")
        if team_avg is None:
            return 0.0, {"status": "not_available", "h2h_matches_total": matches_total}
        h2h_diff = float(team_avg) - float(baseline_expected_sot)
        adj = h2h_diff * 0.10
        if sample_limited:
            adj = _cap(adj, -0.10, 0.10)
        else:
            adj = _cap(adj, -0.20, 0.20)
        return _round2(adj), {
            "status": "applied",
            "h2h_matches_total": matches_total,
            "h2h_team_avg_sot": _round2(float(team_avg)),
            "h2h_diff": _round2(h2h_diff),
            "h2h_adjustment": _round2(adj),
            "h2h_sample_limited": sample_limited,
            "explanation": "Adjustment H2H prudente (10% del diff) con cap.",
        }

    def compute_motivation_adjustment(self, *, team_context: dict[str, Any] | None, opp_context: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
        if not team_context:
            return 0.0, {"status": "not_available"}
        motivation = str(team_context.get("motivation_level") or "incerta")
        objective = str(team_context.get("competition_objective") or "incerto")
        turnover = str(team_context.get("turnover_risk") or "incerto")
        late = bool(team_context.get("late_season_risk"))
        opp_motivation = str((opp_context or {}).get("motivation_level") or "incerta")
        adj = 0.0
        if motivation == "alta" and opp_motivation == "bassa":
            adj += 0.15
        if motivation == "bassa" and turnover == "alto":
            adj -= 0.20
        if objective in ("gia_campione", "nessun_obiettivo_chiaro") and turnover == "alto":
            adj -= 0.20
        if objective in ("champions", "salvezza") and motivation == "alta":
            adj += 0.15
        elif objective in ("champions", "salvezza"):
            adj += 0.10
        if late and motivation == "incerta":
            adj += 0.0
        adj = _cap(adj, -0.25, 0.25)
        return _round2(adj), {
            "status": "applied",
            "motivation_level": motivation,
            "competition_objective": objective,
            "turnover_risk": turnover,
            "late_season_risk": late,
            "adjustment": _round2(adj),
            "explanation": "Adjustment motivation/context prudente con cap ±0.25.",
        }

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
        s = int(base_score)
        if has_player_profiles:
            s += 3
        if h2h_matches_total >= 5:
            s += 2
        if late_season_risk:
            s -= 8
        if turnover_high_any:
            s -= 8
        if availability_not_available and late_season_risk:
            s -= 10
        if abs_total_adjustment > 0.60:
            s -= 10
        s = int(_cap(s, 40, 85))
        if s >= 80:
            return s, "Alta"
        if s >= 60:
            return s, "Media"
        return s, "Bassa"

    def compute_adjusted_prediction(
        self,
        *,
        baseline_expected_sot: float,
        player_adjustment: float,
        h2h_adjustment: float,
        motivation_adjustment: float,
        availability_adjustment: float,
    ) -> tuple[float, float]:
        total = _cap(
            player_adjustment + h2h_adjustment + motivation_adjustment + availability_adjustment,
            -0.90,
            0.90,
        )
        adjusted = max(1.0, float(baseline_expected_sot) + total)
        return _round2(total), _round2(adjusted)

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
        partial = self._empty_partial_result()
        try:
            _league, season = self._season_row(db, season_year)
        except Exception as exc:
            logger.exception("v02 season load failed")
            return self._error_result(
                failed_step="load_season",
                message=f"Season {season_year} not found or invalid.",
                details=str(exc),
                partial_result=partial,
            )

        if not self._adjustments_table_exists(db):
            return self._error_result(
                failed_step="check_adjustments_table",
                message="Missing table team_sot_prediction_adjustments. Run alembic upgrade head.",
                partial_result=partial,
            )

        try:
            fixtures = db.scalars(
                select(Fixture)
                .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
        except Exception as exc:
            logger.exception("v02 fixtures load failed")
            return self._error_result(
                failed_step="load_upcoming_fixtures",
                message="Unable to load upcoming fixtures.",
                details=str(exc),
                partial_result=partial,
            )

        partial["upcoming_fixtures_found"] = len(fixtures)
        league_avg_top5_impact = self._league_avg_top5_impact(db, season.id)
        ctx_service = MatchContextService()
        created = 0
        errors: list[dict[str, Any]] = []

        for fx in fixtures:
            try:
                home_base = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == fx.home_team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    ),
                )
                away_base = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == fx.away_team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    ),
                )
            except Exception as exc:
                logger.exception("v02 baseline load failed for fixture %s", fx.id)
                errors.append(
                    {
                        "fixture_id": fx.id,
                        "failed_step": "load_baseline_v01_predictions",
                        "message": "Unable to load baseline_v0_1 predictions.",
                        "details": str(exc),
                    },
                )
                continue

            if home_base is None or away_base is None:
                errors.append(
                    {
                        "fixture_id": fx.id,
                        "failed_step": "load_baseline_v01_predictions",
                        "message": "Missing baseline_v0_1 prediction for fixture/team. Run generate-upcoming first.",
                    },
                )
                continue

            try:
                h2h = build_h2h_summary_for_fixture(db, fx.id, exclude_api_fixture_id=int(fx.api_fixture_id))
            except Exception:
                logger.exception("v02 h2h failed for fixture %s", fx.id)
                h2h = {"status": "not_available", "h2h_fetch_ok": False}

            try:
                ctx = ctx_service.build_match_context(db, fx.id)
            except Exception:
                logger.exception("v02 context failed for fixture %s", fx.id)
                ctx = {"context_status": "not_available"}

            for base_pred, team_id, is_home in (
                (home_base, fx.home_team_id, True),
                (away_base, fx.away_team_id, False),
            ):
                baseline_expected = float(base_pred.predicted_sot or 0.0)
                try:
                    top_profiles = self._top_profiles_for_team(db, season.id, team_id, limit=5)
                    top_impact_vals = [
                        float(p.impact_score or 0.0) for p in top_profiles if p.impact_score is not None
                    ]
                    team_top5_avg = sum(top_impact_vals) / len(top_impact_vals) if top_impact_vals else None
                    player_adj, player_bd = self.compute_player_adjustment(
                        team_top5_avg_impact=team_top5_avg,
                        league_avg_top5_impact=league_avg_top5_impact,
                    )
                    player_bd["top_players_considered"] = len(top_profiles)
                except Exception as exc:
                    logger.exception("v02 player adjustment failed for fixture %s team %s", fx.id, team_id)
                    player_adj = 0.0
                    player_bd = {
                        "status": "not_available",
                        "adjustment": 0.0,
                        "explanation": "Player profiles non disponibili.",
                        "details": str(exc),
                    }

                team_ctx = ctx.get("home_team_context") if is_home else ctx.get("away_team_context")
                opp_ctx = ctx.get("away_team_context") if is_home else ctx.get("home_team_context")
                try:
                    motivation_adj, motivation_bd = self.compute_motivation_adjustment(
                        team_context=team_ctx,
                        opp_context=opp_ctx,
                    )
                except Exception as exc:
                    logger.exception("v02 motivation adjustment failed for fixture %s team %s", fx.id, team_id)
                    motivation_adj = 0.0
                    motivation_bd = {
                        "status": "not_available",
                        "adjustment": 0.0,
                        "explanation": "Match context non disponibile.",
                        "details": str(exc),
                    }

                try:
                    h2h_adj, h2h_bd = self.compute_h2h_adjustment(
                        baseline_expected_sot=baseline_expected,
                        h2h_summary=h2h,
                        is_home=is_home,
                    )
                except Exception as exc:
                    logger.exception("v02 h2h adjustment failed for fixture %s team %s", fx.id, team_id)
                    h2h_adj = 0.0
                    h2h_bd = {
                        "status": "not_available",
                        "h2h_adjustment": 0.0,
                        "details": str(exc),
                    }

                try:
                    availability_events = db.scalars(
                        select(PlayerAvailabilityEvent).where(
                            PlayerAvailabilityEvent.season_id == season.id,
                            PlayerAvailabilityEvent.team_id == team_id,
                        ),
                    ).all()
                    availability_adj, availability_bd = self.compute_availability_adjustment(
                        top_profiles=top_profiles,
                        availability_events=availability_events,
                    )
                except Exception as exc:
                    logger.exception("v02 availability adjustment failed for fixture %s team %s", fx.id, team_id)
                    availability_adj = 0.0
                    availability_bd = {
                        "status": "not_available",
                        "availability_status": "not_available",
                        "penalty": 0.0,
                        "details": str(exc),
                    }

                total_adj, adjusted_expected = self.compute_adjusted_prediction(
                    baseline_expected_sot=baseline_expected,
                    player_adjustment=player_adj,
                    h2h_adjustment=h2h_adj,
                    motivation_adjustment=motivation_adj,
                    availability_adjustment=availability_adj,
                )
                conf_score, conf_label = self.compute_confidence_v02(
                    base_score=int(base_pred.confidence_score or 60),
                    has_player_profiles=bool(top_profiles),
                    h2h_matches_total=int(h2h_bd.get("h2h_matches_total") or 0),
                    late_season_risk=bool((team_ctx or {}).get("late_season_risk")),
                    turnover_high_any=(
                        str((team_ctx or {}).get("turnover_risk")) == "alto"
                        or str((opp_ctx or {}).get("turnover_risk")) == "alto"
                    ),
                    availability_not_available=availability_bd.get("availability_status") == "not_available",
                    abs_total_adjustment=abs(total_adj),
                )
                breakdown = {
                    "player": player_bd,
                    "h2h": h2h_bd,
                    "motivation": motivation_bd,
                    "availability": availability_bd,
                    "confidence_v02": {
                        "prediction_confidence_score_v0_2": conf_score,
                        "prediction_confidence_label_v0_2": conf_label,
                    },
                }

                try:
                    with db.begin_nested():
                        raw = dict(base_pred.raw_json or {})
                        raw.update(
                            {
                                "baseline_model_version": BASELINE_SOT_MODEL_VERSION,
                                "baseline_expected_sot": _round2(baseline_expected),
                                "adjusted_expected_sot": adjusted_expected,
                                "total_adjustment": total_adj,
                                "player_adjustment": player_adj,
                                "h2h_adjustment": h2h_adj,
                                "motivation_adjustment": motivation_adj,
                                "availability_adjustment": availability_adj,
                                "prediction_confidence_score_v0_2": conf_score,
                                "prediction_confidence_label_v0_2": conf_label,
                                "adjustment_breakdown": breakdown,
                            },
                        )
                        row = db.scalar(
                            select(TeamSotPrediction).where(
                                TeamSotPrediction.fixture_id == fx.id,
                                TeamSotPrediction.team_id == team_id,
                                TeamSotPrediction.model_version == self.model_version,
                            ),
                        )
                        if row is None:
                            row = TeamSotPrediction(
                                fixture_id=fx.id,
                                team_id=team_id,
                                model_version=self.model_version,
                                predicted_sot=adjusted_expected,
                                actual_sot=None,
                                confidence_score=conf_score,
                                explanation="Previsione v0.2: baseline + adjustment contestuali prudenti.",
                                recommendation="not_evaluated",
                                raw_json=raw,
                            )
                            db.add(row)
                        else:
                            row.predicted_sot = adjusted_expected
                            row.confidence_score = conf_score
                            row.explanation = "Previsione v0.2: baseline + adjustment contestuali prudenti."
                            row.raw_json = raw
                        db.flush()
                        self._upsert_adjustment_row(
                            db,
                            prediction=row,
                            fixture_id=fx.id,
                            team_id=team_id,
                            baseline_expected_sot=_round2(baseline_expected),
                            player_adjustment=player_adj,
                            h2h_adjustment=h2h_adj,
                            motivation_adjustment=motivation_adj,
                            availability_adjustment=availability_adj,
                            total_adjustment=total_adj,
                            adjusted_expected_sot=adjusted_expected,
                            breakdown=breakdown,
                        )
                    created += 1
                except Exception as exc:
                    logger.exception("v02 save failed for fixture %s team %s", fx.id, team_id)
                    errors.append(
                        {
                            "fixture_id": fx.id,
                            "team_id": team_id,
                            "failed_step": "save_v02_prediction",
                            "message": "Unable to save v0.2 prediction/breakdown.",
                            "details": str(exc),
                        },
                    )
                    continue

        partial["predictions_created_or_updated"] = created
        partial["errors"] = errors
        db.commit()
        return {
            "status": "success",
            "season": season_year,
            "model_version": self.model_version,
            "upcoming_fixtures": len(fixtures),
            "predictions_created_or_updated": created,
            "errors": errors,
        }

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
