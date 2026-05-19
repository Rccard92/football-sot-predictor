from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION, FINISHED_STATUSES
from app.models import Fixture, Team, TeamSotPrediction
from app.services.h2h_service import build_h2h_summary_for_fixture
from app.services.match_context_service import MatchContextService
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.predictions_v02.math_utils import round2 as _round2

logger = logging.getLogger(__name__)


def generate_v02_for_upcoming_season(service: Any, db: Session, season_year: int) -> dict[str, Any]:
    """
    Orchestrazione generazione v0.2 upcoming.

    Nota: questo modulo è un refactor "safe": la logica rimane nella forma originale,
    delegando a `service` i metodi di calcolo, query helper e salvataggio.
    """

    partial = service._empty_partial_result()
    try:
        _league, season = service._season_row(db, season_year)
    except Exception as exc:
        logger.exception("v02 season load failed")
        return service._error_result(
            failed_step="load_season",
            message=f"Season {season_year} not found or invalid.",
            details=str(exc),
            partial_result=partial,
        )

    if not service._adjustments_table_exists(db):
        return service._error_result(
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
        return service._error_result(
            failed_step="load_upcoming_fixtures",
            message="Unable to load upcoming fixtures.",
            details=str(exc),
            partial_result=partial,
        )

    partial["upcoming_fixtures_found"] = len(fixtures)
    league_avg_top5_impact = service._league_avg_top5_impact(db, season.id)
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
                top_profiles = service._top_profiles_for_team(db, season.id, team_id, limit=5)
                top_impact_vals = [float(p.impact_score or 0.0) for p in top_profiles if p.impact_score is not None]
                team_top5_avg = sum(top_impact_vals) / len(top_impact_vals) if top_impact_vals else None
                player_adj, player_bd = service.compute_player_adjustment(
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
                motivation_adj, motivation_bd = service.compute_motivation_adjustment(
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
                h2h_adj, h2h_bd = service.compute_h2h_adjustment(
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

            availability_adj = 0.0
            availability_bd = {
                "status": "disabled",
                "availability_status": "disabled",
                "applied": False,
                "penalty": 0.0,
                "note": "Componente indisponibili disattivata: dati API non affidabili.",
            }

            total_adj, adjusted_expected = service.compute_adjusted_prediction(
                baseline_expected_sot=baseline_expected,
                player_adjustment=player_adj,
                h2h_adjustment=h2h_adj,
                motivation_adjustment=motivation_adj,
                availability_adjustment=availability_adj,
            )
            conf_score, conf_label = service.compute_confidence_v02(
                base_score=int(base_pred.confidence_score or 60),
                has_player_profiles=bool(top_profiles),
                h2h_matches_total=int(h2h_bd.get("h2h_matches_total") or 0),
                late_season_risk=bool((team_ctx or {}).get("late_season_risk")),
                turnover_high_any=(
                    str((team_ctx or {}).get("turnover_risk")) == "alto"
                    or str((opp_ctx or {}).get("turnover_risk")) == "alto"
                ),
                availability_not_available=True,
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
                    raw.setdefault("model_version", service.model_version)
                    team_row = db.get(Team, int(team_id))
                    tname = team_row.name if team_row is not None else str(team_id)
                    raw = append_trace_to_raw_json(
                        raw,
                        model_version=service.model_version,
                        team_id=int(team_id),
                        team_name=tname,
                        audit_map={},
                        hours_to_kickoff=compute_hours_to_kickoff(fx.kickoff_at),
                        prediction_confidence=int(conf_score),
                    )
                    row = db.scalar(
                        select(TeamSotPrediction).where(
                            TeamSotPrediction.fixture_id == fx.id,
                            TeamSotPrediction.team_id == team_id,
                            TeamSotPrediction.model_version == service.model_version,
                        ),
                    )
                    if row is None:
                        row = TeamSotPrediction(
                            fixture_id=fx.id,
                            team_id=team_id,
                            model_version=service.model_version,
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
                    service._upsert_adjustment_row(
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
        "model_version": service.model_version,
        "upcoming_fixtures": len(fixtures),
        "predictions_created_or_updated": created,
        "errors": errors,
    }

