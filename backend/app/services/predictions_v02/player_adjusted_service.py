from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    FINISHED_STATUSES,
)
from app.models import Fixture, League, PlayerSotProfile, Season, Team, TeamSotPrediction, TeamSotPredictionAdjustment
from app.services.predictions_v02.adjustments_player import compute_player_adjustment
from app.services.predictions_v02.math_utils import round2 as _round2

logger = logging.getLogger(__name__)


def _cap(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def _profile_to_breakdown_row(p: PlayerSotProfile) -> dict[str, Any]:
    return {
        "player_id": int(p.player_id),
        "name": (p.player.name if getattr(p, "player", None) else None) or "",
        "impact_score": _round2(float(p.impact_score or 0.0)) if p.impact_score is not None else None,
        "shots_on_target_per90": _round2(float(p.shots_on_target_per90 or 0.0))
        if p.shots_on_target_per90 is not None
        else None,
        "total_minutes": int(p.total_minutes or 0),
        "appearances": int(p.appearances or 0),
        # Nel modello DB non esiste una colonna sample_warning: lo ricaviamo dai minuti.
        "sample_warning": bool((p.total_minutes or 0) < 300),
    }


def _select_top_profiles_for_team(team_profiles: list[PlayerSotProfile], limit: int = 5) -> tuple[list[PlayerSotProfile], bool]:
    """
    Selezione "preferibile" richiesta:
    - preferisci total_minutes >= 300 (quindi sample_warning False, se il campo esistesse)
    - poi completa con i rimanenti se non bastano
    Ordinamento: impact_score DESC (nulls last).
    """

    def score(p: PlayerSotProfile) -> float:
        return float(p.impact_score) if p.impact_score is not None else float("-inf")

    eligible = [p for p in team_profiles if int(p.total_minutes or 0) >= 300 and p.impact_score is not None]
    eligible_sorted = sorted(eligible, key=score, reverse=True)
    selected: list[PlayerSotProfile] = eligible_sorted[:limit]

    if len(selected) < limit:
        remaining = [p for p in team_profiles if p not in selected and p.impact_score is not None]
        remaining_sorted = sorted(remaining, key=score, reverse=True)
        selected.extend(remaining_sorted[: max(0, limit - len(selected))])

    used_low_sample = any(int(p.total_minutes or 0) < 300 for p in selected)
    return selected[:limit], used_low_sample


class SotPredictionV02PlayerAdjustedService:
    """
    Versione v0.2 "player adjusted" (solo player impact), costruita a partire da baseline v0.1.
    Non applica H2H, motivation context, availability, bookmaker.
    """

    model_version = BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED

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

    def _all_profiles_for_season(self, db: Session, season_id: int) -> list[PlayerSotProfile]:
        # Join su Player per avere il nome nel breakdown, ma senza cambiare la logica.
        return db.scalars(
            select(PlayerSotProfile)
            .where(PlayerSotProfile.season_id == season_id)
            .order_by(PlayerSotProfile.team_id.asc()),
        ).all()

    def _league_avg_top5_impact(self, db: Session, season_id: int) -> float | None:
        """
        Richiesta: media dei top5_avg_impact di tutte le squadre della stagione.
        Implementazione: calcoliamo in Python per rispettare filtri "preferibili" e top5.
        """
        profiles = self._all_profiles_for_season(db, season_id)
        by_team: dict[int, list[PlayerSotProfile]] = {}
        for p in profiles:
            by_team.setdefault(int(p.team_id), []).append(p)
        team_avgs: list[float] = []
        for team_id, team_profiles in by_team.items():
            top, _used_low_sample = _select_top_profiles_for_team(team_profiles, limit=5)
            vals = [float(p.impact_score) for p in top if p.impact_score is not None]
            if not vals:
                continue
            team_avgs.append(sum(vals) / len(vals))
        if not team_avgs:
            return None
        return sum(team_avgs) / len(team_avgs)

    def _upsert_adjustment_row(
        self,
        db: Session,
        *,
        prediction: TeamSotPrediction,
        fixture_id: int,
        team_id: int,
        baseline_expected_sot: float,
        player_adjustment: float,
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
                h2h_adjustment=0.0,
                motivation_adjustment=0.0,
                availability_adjustment=0.0,
                total_adjustment=total_adjustment,
                adjusted_expected_sot=adjusted_expected_sot,
                adjustment_breakdown=breakdown,
            )
            db.add(row)
        else:
            row.prediction_id = prediction.id
            row.baseline_expected_sot = baseline_expected_sot
            row.player_adjustment = player_adjustment
            row.h2h_adjustment = 0.0
            row.motivation_adjustment = 0.0
            row.availability_adjustment = 0.0
            row.total_adjustment = total_adjustment
            row.adjusted_expected_sot = adjusted_expected_sot
            row.adjustment_breakdown = breakdown
        db.flush()

    def generate_for_upcoming_season(self, db: Session, season_year: int) -> dict[str, Any]:
        partial = self._empty_partial_result()
        try:
            _league, season = self._season_row(db, season_year)
        except Exception as exc:
            logger.exception("v02 player-adjusted season load failed")
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

        fixtures = db.scalars(
            select(Fixture)
            .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
        ).all()
        partial["upcoming_fixtures_found"] = len(fixtures)

        if not fixtures:
            return {
                "status": "success",
                "season": season_year,
                "model_version": self.model_version,
                "upcoming_fixtures": 0,
                "predictions_created_or_updated": 0,
                "errors": [],
            }

        # Se manca baseline v0.1 per le upcoming, errore chiaro (come richiesto).
        expected_baseline_rows = len(fixtures) * 2
        baseline_rows = int(
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
            or 0,
        )
        if baseline_rows < expected_baseline_rows:
            return self._error_result(
                failed_step="load_baseline_v01_predictions",
                message="Missing baseline_v0_1 upcoming predictions. Run generate-upcoming first.",
                partial_result=partial,
            )

        # Precarico profili giocatore per stagione.
        season_profiles = self._all_profiles_for_season(db, season.id)
        profiles_by_team: dict[int, list[PlayerSotProfile]] = {}
        for p in season_profiles:
            profiles_by_team.setdefault(int(p.team_id), []).append(p)

        league_avg_top5_impact = self._league_avg_top5_impact(db, season.id)
        created = 0
        errors: list[dict[str, Any]] = []

        for fx in fixtures:
            for team_id in (int(fx.home_team_id), int(fx.away_team_id)):
                base_pred = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    ),
                )
                if base_pred is None:
                    # Non dovrebbe succedere dopo il check count, ma gestiamo comunque.
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": team_id,
                            "failed_step": "load_baseline_v01_predictions",
                            "message": "Missing baseline_v0_1 prediction for fixture/team. Run generate-upcoming first.",
                        },
                    )
                    continue

                baseline_expected = float(base_pred.predicted_sot or 0.0)
                team_profiles = profiles_by_team.get(team_id, [])
                top_profiles, used_low_sample = _select_top_profiles_for_team(team_profiles, limit=5)
                top_vals = [float(p.impact_score) for p in top_profiles if p.impact_score is not None]
                team_top5_avg = sum(top_vals) / len(top_vals) if top_vals else None

                if not top_profiles or league_avg_top5_impact is None:
                    player_adj = 0.0
                    player_bd = {
                        "applied": False,
                        "adjustment": 0,
                        "cap": 0.35,
                        "top_players_considered": [_profile_to_breakdown_row(p) for p in top_profiles],
                        "explanation": "Profili giocatore non sufficienti per calcolare la correzione player impact.",
                    }
                else:
                    player_adj, raw_bd = compute_player_adjustment(
                        team_top5_avg_impact=team_top5_avg,
                        league_avg_top5_impact=league_avg_top5_impact,
                    )
                    player_bd = {
                        "applied": raw_bd.get("status") == "applied",
                        "team_top5_avg_impact": raw_bd.get("team_top5_avg_impact"),
                        "league_avg_top5_impact": raw_bd.get("league_avg_top5_impact"),
                        "player_strength_ratio": raw_bd.get("player_strength_ratio"),
                        "adjustment": raw_bd.get("adjustment"),
                        "cap": 0.35,
                        "top_players_considered": [_profile_to_breakdown_row(p) for p in top_profiles],
                        "explanation": (
                            "La correzione misura quanto il parco giocatori della squadra è sopra o sotto la media "
                            "del campionato nella produzione di tiri in porta."
                        ),
                        "sample_warning": bool(used_low_sample),
                    }

                total_adj = _cap(float(player_adj), -0.35, 0.35)
                adjusted_expected = max(1.0, float(baseline_expected) + float(total_adj))
                adjusted_expected = _round2(adjusted_expected)
                total_adj = _round2(total_adj)

                breakdown = {
                    "player_adjustment": player_bd,
                    "h2h_adjustment": {"applied": False, "adjustment": 0},
                    "motivation_adjustment": {"applied": False, "adjustment": 0},
                    "availability_adjustment": {"applied": False, "adjustment": 0},
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
                                "player_adjustment": total_adj,
                                "h2h_adjustment": 0.0,
                                "motivation_adjustment": 0.0,
                                "availability_adjustment": 0.0,
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
                                confidence_score=int(base_pred.confidence_score or 60),
                                explanation="Previsione v0.2 player adjusted: baseline v0.1 + player impact prudente.",
                                recommendation="not_evaluated",
                                raw_json=raw,
                            )
                            db.add(row)
                        else:
                            row.predicted_sot = adjusted_expected
                            row.confidence_score = int(base_pred.confidence_score or 60)
                            row.explanation = "Previsione v0.2 player adjusted: baseline v0.1 + player impact prudente."
                            row.raw_json = raw
                        db.flush()

                        self._upsert_adjustment_row(
                            db,
                            prediction=row,
                            fixture_id=int(fx.id),
                            team_id=team_id,
                            baseline_expected_sot=_round2(baseline_expected),
                            player_adjustment=total_adj,
                            total_adjustment=total_adj,
                            adjusted_expected_sot=adjusted_expected,
                            breakdown=breakdown,
                        )
                    created += 1
                except Exception as exc:
                    logger.exception("v02 player-adjusted save failed for fixture %s team %s", fx.id, team_id)
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": team_id,
                            "failed_step": "save_v02_prediction",
                            "message": "Unable to save baseline_v0_2_player_adjusted prediction/breakdown.",
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

    def upcoming_player_adjusted(self, db: Session, season_year: int, *, limit: int = 20, only_next_round: bool = True) -> dict[str, Any]:
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

            def side_payload(adj: TeamSotPredictionAdjustment | None) -> dict[str, Any] | None:
                if adj is None:
                    return None
                bd = adj.adjustment_breakdown or {}
                player_bd = bd.get("player_adjustment")
                return {
                    "baseline_expected_sot": _round2(adj.baseline_expected_sot),
                    "adjusted_expected_sot": _round2(adj.adjusted_expected_sot),
                    "player_adjustment": _round2(adj.player_adjustment),
                    "total_adjustment": _round2(adj.total_adjustment),
                    "adjustment_breakdown": {
                        "player_adjustment": player_bd,
                        "h2h_adjustment": (bd.get("h2h_adjustment") or {"applied": False, "adjustment": 0}),
                        "motivation_adjustment": (bd.get("motivation_adjustment") or {"applied": False, "adjustment": 0}),
                        "availability_adjustment": (bd.get("availability_adjustment") or {"applied": False, "adjustment": 0}),
                    },
                }

            hp = side_payload(home_adj)
            ap = side_payload(away_adj)

            matches.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "round": fx.round,
                    "kickoff_at": fx.kickoff_at,
                    "status_short": fx.status,
                    "home_team": {
                        "id": int(fx.home_team_id),
                        "name": home.name if home else "",
                        "logo_url": home.logo_url if home else None,
                    },
                    "away_team": {
                        "id": int(fx.away_team_id),
                        "name": away.name if away else "",
                        "logo_url": away.logo_url if away else None,
                    },
                    "home": hp,
                    "away": ap,
                    "total_expected_sot_baseline": (
                        _round2(float((hp or {}).get("baseline_expected_sot", 0)) + float((ap or {}).get("baseline_expected_sot", 0)))
                        if hp and ap
                        else None
                    ),
                    "total_expected_sot_adjusted": (
                        _round2(float((hp or {}).get("adjusted_expected_sot", 0)) + float((ap or {}).get("adjusted_expected_sot", 0)))
                        if hp and ap
                        else None
                    ),
                },
            )

        return {
            "status": "success",
            "season": season_year,
            "model_version": self.model_version,
            "matches_count": len(matches),
            "matches": matches,
        }

