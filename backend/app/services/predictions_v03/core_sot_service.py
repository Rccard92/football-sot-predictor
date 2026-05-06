from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    FINISHED_STATUSES,
)
from app.models import Fixture, FixtureTeamStat, League, Season, TeamSotPrediction
from app.services.sot_feature_math import fixture_key_before
from app.services.match_context_service import MatchContextService

logger = logging.getLogger(__name__)


PRUDENTIAL_FALLBACK_SOT = 3.5
PRUDENTIAL_FALLBACK_SHOTS = 12.0
PRUDENTIAL_FALLBACK_ACCURACY = 0.32
PRUDENTIAL_SOT_PER_GOAL = 3.0


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _mean(xs: list[float | None]) -> float | None:
    vals = [float(x) for x in xs if x is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


class SotPredictionV03CoreSotService:
    model_version = BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT

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

    def _prior_completed_fixtures_for_team(
        self,
        db: Session,
        *,
        season_id: int,
        cutoff_kickoff: datetime,
        cutoff_fixture_id: int,
        team_id: int,
        mode: str,
    ) -> list[Fixture]:
        q = (
            select(Fixture)
            .where(
                Fixture.season_id == season_id,
                Fixture.status.in_(FINISHED_STATUSES),
                (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
            )
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )
        xs = db.scalars(q).all()
        if mode == "post_match":
            return list(xs)
        return [f for f in xs if fixture_key_before(f.kickoff_at, f.id, cutoff_kickoff, cutoff_fixture_id)]

    def _team_stats_map(self, db: Session, fixture_ids: list[int]) -> dict[tuple[int, int], FixtureTeamStat]:
        if not fixture_ids:
            return {}
        rows = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids))).all()
        return {(int(r.fixture_id), int(r.team_id)): r for r in rows}

    def _last_n(self, fixtures: list[Fixture], n: int) -> list[Fixture]:
        xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)[:n]
        return sorted(xs, key=lambda f: (f.kickoff_at, f.id))

    def _agg_for_team(
        self,
        *,
        fixtures: list[Fixture],
        stats_map: dict[tuple[int, int], FixtureTeamStat],
        team_id: int,
    ) -> dict[str, Any]:
        sot_for_sum = 0
        sot_for_n = 0
        shots_for_sum = 0
        shots_for_n = 0

        sot_against_sum = 0
        sot_against_n = 0
        shots_against_sum = 0
        shots_against_n = 0

        goals_for_sum = 0
        goals_for_n = 0
        goals_against_sum = 0
        goals_against_n = 0

        for f in fixtures:
            opp_id = int(f.away_team_id) if int(f.home_team_id) == team_id else int(f.home_team_id)
            st_team = stats_map.get((int(f.id), team_id))
            st_opp = stats_map.get((int(f.id), opp_id))

            if st_team and st_team.shots_on_target is not None:
                sot_for_sum += int(st_team.shots_on_target)
                sot_for_n += 1
            if st_team and st_team.total_shots is not None:
                shots_for_sum += int(st_team.total_shots)
                shots_for_n += 1

            if st_opp and st_opp.shots_on_target is not None:
                sot_against_sum += int(st_opp.shots_on_target)
                sot_against_n += 1
            if st_opp and st_opp.total_shots is not None:
                shots_against_sum += int(st_opp.total_shots)
                shots_against_n += 1

            if int(f.home_team_id) == team_id:
                gf = f.goals_home
                ga = f.goals_away
            else:
                gf = f.goals_away
                ga = f.goals_home
            if gf is not None:
                goals_for_sum += int(gf)
                goals_for_n += 1
            if ga is not None:
                goals_against_sum += int(ga)
                goals_against_n += 1

        def mean(sum_: int, n: int) -> float | None:
            return (sum_ / n) if n > 0 else None

        return {
            "matches_count": len(fixtures),
            "sot_for_sum": sot_for_sum,
            "sot_for_n": sot_for_n,
            "sot_for_mean": mean(sot_for_sum, sot_for_n),
            "shots_for_sum": shots_for_sum,
            "shots_for_n": shots_for_n,
            "shots_for_mean": mean(shots_for_sum, shots_for_n),
            "sot_against_sum": sot_against_sum,
            "sot_against_n": sot_against_n,
            "sot_against_mean": mean(sot_against_sum, sot_against_n),
            "shots_against_sum": shots_against_sum,
            "shots_against_n": shots_against_n,
            "shots_against_mean": mean(shots_against_sum, shots_against_n),
            "goals_for_sum": goals_for_sum,
            "goals_for_n": goals_for_n,
            "goals_for_mean": mean(goals_for_sum, goals_for_n),
            "goals_against_sum": goals_against_sum,
            "goals_against_n": goals_against_n,
            "goals_against_mean": mean(goals_against_sum, goals_against_n),
        }

    def _resolve_with_fallback(self, raw: float | None, fallback: float, *, reason: str) -> tuple[float, dict[str, Any]]:
        if raw is None or (isinstance(raw, float) and raw != raw):  # NaN
            return float(fallback), {"fallback_used": True, "fallback_value": fallback, "reason": reason}
        return float(raw), {"fallback_used": False}

    def _ratio(self, num: float | None, den: float | None) -> float | None:
        if num is None or den is None:
            return None
        if den == 0:
            return None
        return float(num) / float(den)

    def _compute_team_v03(
        self,
        db: Session,
        *,
        season_id: int,
        fixture: Fixture,
        team_id: int,
        opponent_id: int,
        is_home: bool,
        mode: str,
    ) -> tuple[float, dict[str, Any]]:
        team_priors = self._prior_completed_fixtures_for_team(
            db,
            season_id=season_id,
            cutoff_kickoff=fixture.kickoff_at,
            cutoff_fixture_id=int(fixture.id),
            team_id=team_id,
            mode=mode,
        )
        opp_priors = self._prior_completed_fixtures_for_team(
            db,
            season_id=season_id,
            cutoff_kickoff=fixture.kickoff_at,
            cutoff_fixture_id=int(fixture.id),
            team_id=opponent_id,
            mode=mode,
        )

        # Stats map over union of fixture ids for both sets
        union_ids = sorted({int(f.id) for f in team_priors} | {int(f.id) for f in opp_priors})
        stats_map = self._team_stats_map(db, union_ids)

        # Splits and last windows
        team_split = [f for f in team_priors if int(f.home_team_id) == team_id] if is_home else [f for f in team_priors if int(f.away_team_id) == team_id]
        opp_split = [f for f in opp_priors if int(f.away_team_id) == opponent_id] if is_home else [f for f in opp_priors if int(f.home_team_id) == opponent_id]

        team_last5 = self._last_n(team_priors, 5)
        team_last10 = self._last_n(team_priors, 10)
        opp_last5 = self._last_n(opp_priors, 5)
        opp_last10 = self._last_n(opp_priors, 10)

        team_season = self._agg_for_team(fixtures=team_priors, stats_map=stats_map, team_id=team_id)
        opp_season = self._agg_for_team(fixtures=opp_priors, stats_map=stats_map, team_id=opponent_id)
        team_split_agg = self._agg_for_team(fixtures=team_split, stats_map=stats_map, team_id=team_id)
        opp_split_agg = self._agg_for_team(fixtures=opp_split, stats_map=stats_map, team_id=opponent_id)

        team_last5_agg = self._agg_for_team(fixtures=team_last5, stats_map=stats_map, team_id=team_id)
        team_last10_agg = self._agg_for_team(fixtures=team_last10, stats_map=stats_map, team_id=team_id)
        opp_last5_agg = self._agg_for_team(fixtures=opp_last5, stats_map=stats_map, team_id=opponent_id)
        opp_last10_agg = self._agg_for_team(fixtures=opp_last10, stats_map=stats_map, team_id=opponent_id)

        fallbacks: dict[str, Any] = {}
        inputs: dict[str, Any] = {}
        resolved: dict[str, Any] = {}

        # Core SOT inputs
        inputs["season_avg_sot_for"] = _safe_float(team_season["sot_for_mean"])
        inputs["opponent_season_avg_sot_conceded"] = _safe_float(opp_season["sot_against_mean"])
        inputs["split_avg_sot_for"] = _safe_float(team_split_agg["sot_for_mean"])
        inputs["opponent_split_avg_sot_conceded"] = _safe_float(opp_split_agg["sot_against_mean"])

        resolved["season_avg_sot_for"], fallbacks["season_avg_sot_for"] = self._resolve_with_fallback(
            inputs["season_avg_sot_for"],
            PRUDENTIAL_FALLBACK_SOT,
            reason="SOT season mean missing",
        )
        resolved["opponent_season_avg_sot_conceded"], fallbacks["opponent_season_avg_sot_conceded"] = self._resolve_with_fallback(
            inputs["opponent_season_avg_sot_conceded"],
            PRUDENTIAL_FALLBACK_SOT,
            reason="Opponent SOT conceded season mean missing",
        )
        resolved["split_avg_sot_for"], fallbacks["split_avg_sot_for"] = self._resolve_with_fallback(
            inputs["split_avg_sot_for"],
            resolved["season_avg_sot_for"],
            reason="SOT split mean missing; fallback to season_avg_sot_for",
        )
        resolved["opponent_split_avg_sot_conceded"], fallbacks["opponent_split_avg_sot_conceded"] = self._resolve_with_fallback(
            inputs["opponent_split_avg_sot_conceded"],
            resolved["opponent_season_avg_sot_conceded"],
            reason="Opponent SOT conceded split mean missing; fallback to opponent season",
        )

        core_sot = _mean(
            [
                resolved["season_avg_sot_for"],
                resolved["opponent_season_avg_sot_conceded"],
                resolved["split_avg_sot_for"],
                resolved["opponent_split_avg_sot_conceded"],
            ],
        ) or PRUDENTIAL_FALLBACK_SOT

        # Volume shots + accuracy_for
        inputs["season_avg_shots_for"] = _safe_float(team_season["shots_for_mean"])
        inputs["opponent_season_avg_shots_conceded"] = _safe_float(opp_season["shots_against_mean"])
        inputs["split_avg_shots_for"] = _safe_float(team_split_agg["shots_for_mean"])
        inputs["opponent_split_avg_shots_conceded"] = _safe_float(opp_split_agg["shots_against_mean"])

        resolved["season_avg_shots_for"], fallbacks["season_avg_shots_for"] = self._resolve_with_fallback(
            inputs["season_avg_shots_for"],
            PRUDENTIAL_FALLBACK_SHOTS,
            reason="Shots season mean missing",
        )
        resolved["opponent_season_avg_shots_conceded"], fallbacks["opponent_season_avg_shots_conceded"] = self._resolve_with_fallback(
            inputs["opponent_season_avg_shots_conceded"],
            PRUDENTIAL_FALLBACK_SHOTS,
            reason="Opponent shots conceded season mean missing",
        )
        resolved["split_avg_shots_for"], fallbacks["split_avg_shots_for"] = self._resolve_with_fallback(
            inputs["split_avg_shots_for"],
            resolved["season_avg_shots_for"],
            reason="Shots split mean missing; fallback to season_avg_shots_for",
        )
        resolved["opponent_split_avg_shots_conceded"], fallbacks["opponent_split_avg_shots_conceded"] = self._resolve_with_fallback(
            inputs["opponent_split_avg_shots_conceded"],
            resolved["opponent_season_avg_shots_conceded"],
            reason="Opponent shots conceded split mean missing; fallback to opponent season",
        )

        shots_context = _mean(
            [
                resolved["season_avg_shots_for"],
                resolved["opponent_season_avg_shots_conceded"],
                resolved["split_avg_shots_for"],
                resolved["opponent_split_avg_shots_conceded"],
            ],
        ) or PRUDENTIAL_FALLBACK_SHOTS

        raw_accuracy_for = self._ratio(inputs["season_avg_sot_for"], inputs["season_avg_shots_for"])
        resolved["shot_accuracy_for"], fallbacks["shot_accuracy_for"] = self._resolve_with_fallback(
            raw_accuracy_for,
            PRUDENTIAL_FALLBACK_ACCURACY,
            reason="shot_accuracy_for missing/invalid",
        )
        shot_volume_component = shots_context * resolved["shot_accuracy_for"]

        # Accuracy component: blend team ratio and opponent allowed ratio, scale by team shots
        raw_opp_allowed_ratio = self._ratio(_safe_float(opp_season["sot_against_mean"]), _safe_float(opp_season["shots_against_mean"]))
        resolved["opponent_sot_allowed_ratio"], fallbacks["opponent_sot_allowed_ratio"] = self._resolve_with_fallback(
            raw_opp_allowed_ratio,
            PRUDENTIAL_FALLBACK_ACCURACY,
            reason="opponent_sot_allowed_ratio missing/invalid",
        )
        accuracy_context = _mean([resolved["shot_accuracy_for"], resolved["opponent_sot_allowed_ratio"]]) or PRUDENTIAL_FALLBACK_ACCURACY
        shot_accuracy_component = resolved["season_avg_shots_for"] * accuracy_context

        # Recent form (SOT scale)
        inputs["last5_avg_sot_for"] = _safe_float(team_last5_agg["sot_for_mean"])
        inputs["opponent_last5_avg_sot_conceded"] = _safe_float(opp_last5_agg["sot_against_mean"])
        inputs["last10_avg_sot_for"] = _safe_float(team_last10_agg["sot_for_mean"])
        inputs["opponent_last10_avg_sot_conceded"] = _safe_float(opp_last10_agg["sot_against_mean"])

        resolved["last5_avg_sot_for"], fallbacks["last5_avg_sot_for"] = self._resolve_with_fallback(
            inputs["last5_avg_sot_for"],
            resolved["season_avg_sot_for"],
            reason="last5_avg_sot_for missing; fallback to season_avg_sot_for",
        )
        resolved["opponent_last5_avg_sot_conceded"], fallbacks["opponent_last5_avg_sot_conceded"] = self._resolve_with_fallback(
            inputs["opponent_last5_avg_sot_conceded"],
            resolved["opponent_season_avg_sot_conceded"],
            reason="opponent_last5_avg_sot_conceded missing; fallback to opponent season conceded",
        )
        resolved["last10_avg_sot_for"], fallbacks["last10_avg_sot_for"] = self._resolve_with_fallback(
            inputs["last10_avg_sot_for"],
            resolved["season_avg_sot_for"],
            reason="last10_avg_sot_for missing; fallback to season_avg_sot_for",
        )
        resolved["opponent_last10_avg_sot_conceded"], fallbacks["opponent_last10_avg_sot_conceded"] = self._resolve_with_fallback(
            inputs["opponent_last10_avg_sot_conceded"],
            resolved["opponent_season_avg_sot_conceded"],
            reason="opponent_last10_avg_sot_conceded missing; fallback to opponent season conceded",
        )

        recent_form_component = _mean(
            [
                resolved["last5_avg_sot_for"],
                resolved["opponent_last5_avg_sot_conceded"],
                resolved["last10_avg_sot_for"],
                resolved["opponent_last10_avg_sot_conceded"],
            ],
        ) or _mean([resolved["last5_avg_sot_for"], resolved["opponent_last5_avg_sot_conceded"]]) or PRUDENTIAL_FALLBACK_SOT

        # Goals context → SOT scale (prudential)
        inputs["season_avg_goals_for"] = _safe_float(team_season["goals_for_mean"])
        inputs["opponent_season_avg_goals_conceded"] = _safe_float(opp_season["goals_against_mean"])
        resolved["season_avg_goals_for"], fallbacks["season_avg_goals_for"] = self._resolve_with_fallback(
            inputs["season_avg_goals_for"],
            1.0,
            reason="goals_for mean missing",
        )
        resolved["opponent_season_avg_goals_conceded"], fallbacks["opponent_season_avg_goals_conceded"] = self._resolve_with_fallback(
            inputs["opponent_season_avg_goals_conceded"],
            1.0,
            reason="opponent goals conceded mean missing",
        )
        goals_mean = _mean([resolved["season_avg_goals_for"], resolved["opponent_season_avg_goals_conceded"]]) or 1.0
        goals_context_component = goals_mean * PRUDENTIAL_SOT_PER_GOAL

        # Final mix
        expected_v03 = (
            0.55 * core_sot
            + 0.20 * shot_volume_component
            + 0.10 * shot_accuracy_component
            + 0.10 * recent_form_component
            + 0.05 * goals_context_component
        )
        expected_v03 = max(0.0, float(expected_v03))

        breakdown = {
            "model_version": self.model_version,
            "mode": mode,
            "fixture_id": int(fixture.id),
            "team_id": int(team_id),
            "opponent_id": int(opponent_id),
            "weights": {
                "core_sot_component": 0.55,
                "shot_volume_component": 0.20,
                "shot_accuracy_component": 0.10,
                "recent_form_component": 0.10,
                "goals_context_component": 0.05,
            },
            "inputs": inputs,
            "resolved_inputs": resolved,
            "fallbacks": fallbacks,
            "components": {
                "core_sot_component": {
                    "formula": "mean(season_avg_sot_for, opponent_season_avg_sot_conceded, split_avg_sot_for, opponent_split_avg_sot_conceded)",
                    "value": _round2(core_sot),
                },
                "shot_volume_component": {
                    "formula": "shots_context * shot_accuracy_for",
                    "shots_context": _round2(shots_context),
                    "shot_accuracy_for": round(float(resolved["shot_accuracy_for"]), 4),
                    "value": _round2(shot_volume_component),
                },
                "shot_accuracy_component": {
                    "formula": "season_avg_shots_for * mean(shot_accuracy_for, opponent_sot_allowed_ratio)",
                    "season_avg_shots_for": _round2(resolved["season_avg_shots_for"]),
                    "accuracy_context": round(float(accuracy_context), 4),
                    "value": _round2(shot_accuracy_component),
                },
                "recent_form_component": {
                    "formula": "mean(last5_for, opp_last5_conceded, last10_for, opp_last10_conceded)",
                    "value": _round2(recent_form_component),
                },
                "goals_context_component": {
                    "formula": "mean(goals_for, opp_goals_conceded) * sot_per_goal",
                    "sot_per_goal": PRUDENTIAL_SOT_PER_GOAL,
                    "value": _round2(goals_context_component),
                },
            },
            "expected_sot_v03": _round2(expected_v03),
            "meta": {
                "team_priors_matches_count": int(len(team_priors)),
                "opponent_priors_matches_count": int(len(opp_priors)),
            },
        }
        return expected_v03, breakdown

    def generate_for_upcoming_season(self, db: Session, season_year: int) -> dict[str, Any]:
        partial = self._empty_partial_result()
        try:
            _league, season = self._season_row(db, season_year)
        except Exception as exc:
            logger.exception("v03 season load failed")
            return self._error_result(
                failed_step="load_season",
                message=f"Season {season_year} non trovata o non valida.",
                details=str(exc),
                partial_result=partial,
            )

        try:
            fixtures = db.scalars(
                select(Fixture)
                .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
        except Exception as exc:
            logger.exception("v03 fixtures load failed")
            return self._error_result(
                failed_step="load_upcoming_fixtures",
                message="Impossibile caricare le fixture upcoming.",
                details=str(exc),
                partial_result=partial,
            )

        partial["upcoming_fixtures_found"] = len(fixtures)
        created = 0
        errors: list[dict[str, Any]] = []

        for fx in fixtures:
            # v0.1 dependency (user choice): require stored baseline_v0_1 for both teams
            try:
                home_v01 = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == fx.home_team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    ),
                )
                away_v01 = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == fx.away_team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    ),
                )
            except Exception as exc:
                logger.exception("v03 baseline load failed for fixture %s", fx.id)
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "failed_step": "load_baseline_v01_predictions",
                        "message": "Impossibile caricare baseline_v0_1.",
                        "details": str(exc),
                    },
                )
                continue

            if home_v01 is None or away_v01 is None:
                errors.append(
                    {
                        "fixture_id": int(fx.id),
                        "failed_step": "load_baseline_v01_predictions",
                        "message": "Manca baseline_v0_1 per fixture/team. Esegui prima generate-upcoming v0.1.",
                    },
                )
                continue

            for team_id, opp_id, is_home in (
                (int(fx.home_team_id), int(fx.away_team_id), True),
                (int(fx.away_team_id), int(fx.home_team_id), False),
            ):
                try:
                    expected_v03, bd = self._compute_team_v03(
                        db,
                        season_id=int(season.id),
                        fixture=fx,
                        team_id=team_id,
                        opponent_id=opp_id,
                        is_home=is_home,
                        mode="pre_match",
                    )
                    # load baseline value for reference
                    base = home_v01 if is_home else away_v01
                    expected_v01 = float(base.predicted_sot or 0.0)
                    bd["expected_sot_v01_loaded"] = _round2(expected_v01)
                    bd["difference_from_v01"] = _round2(expected_v03 - expected_v01)

                    row = db.scalar(
                        select(TeamSotPrediction).where(
                            TeamSotPrediction.fixture_id == fx.id,
                            TeamSotPrediction.team_id == team_id,
                            TeamSotPrediction.model_version == self.model_version,
                        ),
                    )
                    if row is None:
                        row = TeamSotPrediction(
                            fixture_id=int(fx.id),
                            team_id=team_id,
                            model_version=self.model_version,
                            predicted_sot=_round2(expected_v03),
                            raw_json=bd,
                            explanation="Baseline v0.3 core SOT (componenti auditabili).",
                        )
                        db.add(row)
                    else:
                        row.predicted_sot = _round2(expected_v03)
                        row.raw_json = bd
                        row.explanation = "Baseline v0.3 core SOT (componenti auditabili)."
                    db.flush()
                    created += 1
                except Exception as exc:
                    logger.exception("v03 compute failed for fixture %s team %s", fx.id, team_id)
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "failed_step": "compute_and_save_v03",
                            "message": "Errore durante calcolo/salvataggio v0.3.",
                            "details": str(exc),
                        },
                    )
                    continue

        try:
            db.commit()
        except Exception as exc:
            logger.exception("v03 commit failed")
            db.rollback()
            return self._error_result(
                failed_step="commit",
                message="Errore durante il salvataggio su database.",
                details=str(exc),
                partial_result={**partial, "predictions_created_or_updated": created, "errors": errors},
            )

        return {
            "status": "success" if not errors else "partial_success",
            "model_version": self.model_version,
            "upcoming_fixtures_found": partial["upcoming_fixtures_found"],
            "predictions_created_or_updated": created,
            "errors": errors,
        }

    def upcoming_v03(
        self,
        db: Session,
        season_year: int,
        *,
        limit: int = 20,
        only_next_round: bool = True,
    ) -> dict[str, Any]:
        try:
            _league, season = self._season_row(db, season_year)
        except Exception as exc:
            return self._error_result(
                failed_step="load_season",
                message=f"Season {season_year} non trovata o non valida.",
                details=str(exc),
            )

        try:
            fixtures = db.scalars(
                select(Fixture)
                .where(Fixture.season_id == season.id, ~Fixture.status.in_(FINISHED_STATUSES))
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
            ).all()
        except Exception as exc:
            return self._error_result(
                failed_step="load_upcoming_fixtures",
                message="Impossibile caricare le fixture upcoming.",
                details=str(exc),
            )

        if only_next_round and fixtures:
            next_round = fixtures[0].round
            fixtures = [f for f in fixtures if f.round == next_round]
        fixtures = fixtures[:limit]

        fixture_ids = [int(f.id) for f in fixtures]
        preds_v03 = db.scalars(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id.in_(fixture_ids),
                TeamSotPrediction.model_version == self.model_version,
            ),
        ).all()
        by_fx_team: dict[tuple[int, int], TeamSotPrediction] = {(int(p.fixture_id), int(p.team_id)): p for p in preds_v03}

        preds_v01 = db.scalars(
            select(TeamSotPrediction).where(
                TeamSotPrediction.fixture_id.in_(fixture_ids),
                TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
            ),
        ).all()
        by_fx_team_v01: dict[tuple[int, int], TeamSotPrediction] = {(int(p.fixture_id), int(p.team_id)): p for p in preds_v01}

        matches: list[dict[str, Any]] = []
        ctx_svc = MatchContextService()
        for fx in fixtures:
            h_v03 = by_fx_team.get((int(fx.id), int(fx.home_team_id)))
            a_v03 = by_fx_team.get((int(fx.id), int(fx.away_team_id)))
            h_v01 = by_fx_team_v01.get((int(fx.id), int(fx.home_team_id)))
            a_v01 = by_fx_team_v01.get((int(fx.id), int(fx.away_team_id)))

            def side_payload(team_id: int, v01: TeamSotPrediction | None, v03: TeamSotPrediction | None) -> dict[str, Any] | None:
                if v03 is None:
                    return None
                bd = v03.raw_json if isinstance(v03.raw_json, dict) else None
                comps = (bd or {}).get("components") if isinstance(bd, dict) else None
                return {
                    "team_id": int(team_id),
                    "expected_sot_v01": _round2(float(v01.predicted_sot)) if v01 and v01.predicted_sot is not None else None,
                    "expected_sot_v03": _round2(float(v03.predicted_sot)) if v03.predicted_sot is not None else None,
                    "difference_from_v01": (bd or {}).get("difference_from_v01") if isinstance(bd, dict) else None,
                    "core_sot_component": ((comps or {}).get("core_sot_component") or {}).get("value") if isinstance(comps, dict) else None,
                    "shot_volume_component": ((comps or {}).get("shot_volume_component") or {}).get("value") if isinstance(comps, dict) else None,
                    "shot_accuracy_component": ((comps or {}).get("shot_accuracy_component") or {}).get("value") if isinstance(comps, dict) else None,
                    "recent_form_component": ((comps or {}).get("recent_form_component") or {}).get("value") if isinstance(comps, dict) else None,
                    "goals_context_component": ((comps or {}).get("goals_context_component") or {}).get("value") if isinstance(comps, dict) else None,
                    "breakdown": bd,
                }

            context_payload = ctx_svc.build_match_context(db, int(fx.id))
            matches.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "kickoff_at": fx.kickoff_at,
                    "round": fx.round,
                    "status_short": fx.status,
                    "home": side_payload(int(fx.home_team_id), h_v01, h_v03),
                    "away": side_payload(int(fx.away_team_id), a_v01, a_v03),
                    "context_status": context_payload.get("context_status", "not_available"),
                    "match_context": context_payload.get("match_context"),
                    "home_team_context": context_payload.get("home_team_context"),
                    "away_team_context": context_payload.get("away_team_context"),
                    "season_phase_context": context_payload.get("season_phase_context"),
                }
            )

        return {"status": "success", "model_version": self.model_version, "matches": matches}

