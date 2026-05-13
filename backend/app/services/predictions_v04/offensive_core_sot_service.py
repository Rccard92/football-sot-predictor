from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    FINISHED_STATUSES,
)
from app.models import Fixture, FixtureTeamStat, League, Season, Team, TeamSotPrediction
from app.services.match_context_service import MatchContextService
from app.services.model_applied_variable_trace import append_trace_to_raw_json, compute_hours_to_kickoff
from app.services.sot_feature_math import fixture_key_before

logger = logging.getLogger(__name__)

# fallback prudenziali (non creare dati fake: solo protezione su missing/denom 0)
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


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


class SotPredictionV04OffensiveCoreSotService:
    """
    Modello v0.4: mantiene invariati i blocchi/pesi baseline (v0.1),
    sostituendo il segnale offensivo `avg_sot_for` con `offensive_production_component` (cap ±0.75).
    """

    model_version = BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT

    def _season_row(self, db: Session, season_year: int) -> tuple[League, Season]:
        """
        Lookup robusto (stesso intento degli altri servizi):
        - prova Serie A per nome (ingestion)
        - fallback su default_league_id da settings
        """
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
        # SUM/N per campi team (fatti)
        sot_sum = sot_n = 0
        shots_sum = shots_n = 0
        in_sum = in_n = 0
        out_sum = out_n = 0
        goals_sum = goals_n = 0

        for f in fixtures:
            st = stats_map.get((int(f.id), int(team_id)))
            if st and st.shots_on_target is not None:
                sot_sum += int(st.shots_on_target)
                sot_n += 1
            if st and st.total_shots is not None:
                shots_sum += int(st.total_shots)
                shots_n += 1
            if st and st.shots_inside_box is not None:
                in_sum += int(st.shots_inside_box)
                in_n += 1
            if st and st.shots_outside_box is not None:
                out_sum += int(st.shots_outside_box)
                out_n += 1

            if int(f.home_team_id) == int(team_id):
                gf = f.goals_home
            else:
                gf = f.goals_away
            if gf is not None:
                goals_sum += int(gf)
                goals_n += 1

        def mean(sum_: int, n: int) -> float | None:
            return (sum_ / n) if n > 0 else None

        return {
            "matches_count": len(fixtures),
            "sot_sum": sot_sum,
            "sot_n": sot_n,
            "sot_mean": mean(sot_sum, sot_n),
            "shots_sum": shots_sum,
            "shots_n": shots_n,
            "shots_mean": mean(shots_sum, shots_n),
            "inside_sum": in_sum,
            "inside_n": in_n,
            "inside_mean": mean(in_sum, in_n),
            "outside_sum": out_sum,
            "outside_n": out_n,
            "outside_mean": mean(out_sum, out_n),
            "goals_sum": goals_sum,
            "goals_n": goals_n,
            "goals_mean": mean(goals_sum, goals_n),
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

    def _compute_offensive_component(
        self,
        *,
        season_agg: dict[str, Any],
        last5_agg: dict[str, Any],
        last10_agg: dict[str, Any],
    ) -> dict[str, Any]:
        fallbacks_used: list[str] = []

        avg_sot_for_raw = _safe_float(season_agg.get("sot_mean"))
        avg_sot_for, fb = self._resolve_with_fallback(avg_sot_for_raw, PRUDENTIAL_FALLBACK_SOT, reason="avg_sot_for_missing")
        if fb.get("fallback_used"):
            fallbacks_used.append("avg_sot_for")

        avg_total_shots_for_raw = _safe_float(season_agg.get("shots_mean"))
        avg_total_shots_for, fb2 = self._resolve_with_fallback(
            avg_total_shots_for_raw,
            PRUDENTIAL_FALLBACK_SHOTS,
            reason="avg_total_shots_for_missing",
        )
        if fb2.get("fallback_used"):
            fallbacks_used.append("avg_total_shots_for")

        avg_inside_box_shots_for_raw = _safe_float(season_agg.get("inside_mean"))
        avg_outside_box_shots_for_raw = _safe_float(season_agg.get("outside_mean"))

        # accuracy: ratio of averages; fallback prudente se denom 0/missing
        shot_accuracy_raw = self._ratio(avg_sot_for_raw, avg_total_shots_for_raw)
        shot_accuracy_for, fb_acc = self._resolve_with_fallback(
            shot_accuracy_raw,
            PRUDENTIAL_FALLBACK_ACCURACY,
            reason="shot_accuracy_missing_or_zero_denom",
        )
        if fb_acc.get("fallback_used"):
            fallbacks_used.append("shot_accuracy_for")

        avg_goals_for_raw = _safe_float(season_agg.get("goals_mean"))
        avg_goals_for, fb_g = self._resolve_with_fallback(avg_goals_for_raw, 1.1, reason="avg_goals_for_missing")
        if fb_g.get("fallback_used"):
            fallbacks_used.append("avg_goals_for")

        # Signals in scala SOT attesi (prudente)
        total_shots_signal = avg_total_shots_for * shot_accuracy_for
        inside_box_signal = None if avg_inside_box_shots_for_raw is None else float(avg_inside_box_shots_for_raw) * shot_accuracy_for
        outside_box_signal = None if avg_outside_box_shots_for_raw is None else float(avg_outside_box_shots_for_raw) * shot_accuracy_for * 0.7

        # accuracy signal: piccolo correttivo su scala SOT
        acc_ratio = shot_accuracy_for / PRUDENTIAL_FALLBACK_ACCURACY if PRUDENTIAL_FALLBACK_ACCURACY else 1.0
        shot_accuracy_signal = _clamp(avg_sot_for * acc_ratio, avg_sot_for - 0.5, avg_sot_for + 0.5)

        goals_signal = avg_goals_for * PRUDENTIAL_SOT_PER_GOAL

        # trend: delta vs season (last5 & last10), mantenuto piccolo e su scala SOT
        last5_sot = _safe_float(last5_agg.get("sot_mean"))
        last10_sot = _safe_float(last10_agg.get("sot_mean"))
        d5 = (last5_sot - avg_sot_for_raw) if (last5_sot is not None and avg_sot_for_raw is not None) else 0.0
        d10 = (last10_sot - avg_sot_for_raw) if (last10_sot is not None and avg_sot_for_raw is not None) else 0.0
        trend_delta = float((d5 + d10) / 2.0)
        trend_delta = _clamp(trend_delta, -0.5, 0.5)
        offensive_trend_signal = _clamp(avg_sot_for + trend_delta, avg_sot_for - 0.5, avg_sot_for + 0.5)

        # pesi interni
        w = {
            "avg_sot_for": 0.35,
            "avg_total_shots_for": 0.25,
            "avg_inside_box_shots_for": 0.15,
            "avg_outside_box_shots_for": 0.05,
            "shot_accuracy_for": 0.10,
            "avg_goals_for": 0.05,
            "offensive_trend": 0.05,
        }

        # redistribuzione inside box se missing
        if inside_box_signal is None:
            fallbacks_used.append("avg_inside_box_shots_for_missing_redistribute")
            w["avg_sot_for"] += 0.10
            w["avg_total_shots_for"] += 0.05
            w["avg_inside_box_shots_for"] = 0.0

        # componente grezza come media pesata di segnali su scala SOT
        def contrib(val: float | None, weight: float) -> float:
            if val is None or weight <= 0:
                return 0.0
            return float(val) * float(weight)

        numerator = 0.0
        denom = 0.0
        numerator += contrib(avg_sot_for, w["avg_sot_for"])
        denom += w["avg_sot_for"]
        numerator += contrib(total_shots_signal, w["avg_total_shots_for"])
        denom += w["avg_total_shots_for"]
        numerator += contrib(inside_box_signal, w["avg_inside_box_shots_for"])
        denom += w["avg_inside_box_shots_for"]
        numerator += contrib(outside_box_signal, w["avg_outside_box_shots_for"])
        denom += w["avg_outside_box_shots_for"]
        numerator += contrib(shot_accuracy_signal, w["shot_accuracy_for"])
        denom += w["shot_accuracy_for"]
        numerator += contrib(goals_signal, w["avg_goals_for"])
        denom += w["avg_goals_for"]
        numerator += contrib(offensive_trend_signal, w["offensive_trend"])
        denom += w["offensive_trend"]

        raw_component = numerator / denom if denom > 0 else avg_sot_for
        capped_component = _clamp(raw_component, avg_sot_for - 0.75, avg_sot_for + 0.75)
        cap_applied = abs(capped_component - raw_component) > 1e-9

        # breakdown inputs: value, source, matches_count/sum, weight, contribution, status
        def mk_input(
            *,
            key: str,
            value: float | None,
            sum_key: str | None,
            n_key: str | None,
            weight: float,
            contribution: float,
            status: str,
        ) -> dict[str, Any]:
            return {
                "value": _round2(value),
                "source_table": "fixture_team_stats / fixtures",
                "matches_count": int(season_agg.get("matches_count") or 0),
                "sum": int(season_agg.get(sum_key) or 0) if sum_key else None,
                "weight": weight,
                "contribution": _round2(contribution),
                "status": status,
            }

        inputs = {
            "avg_sot_for": mk_input(
                key="avg_sot_for",
                value=avg_sot_for,
                sum_key="sot_sum",
                n_key="sot_n",
                weight=w["avg_sot_for"],
                contribution=avg_sot_for * w["avg_sot_for"],
                status="available" if avg_sot_for_raw is not None else "missing",
            ),
            "avg_total_shots_for": mk_input(
                key="avg_total_shots_for",
                value=avg_total_shots_for,
                sum_key="shots_sum",
                n_key="shots_n",
                weight=w["avg_total_shots_for"],
                contribution=total_shots_signal * w["avg_total_shots_for"],
                status="available" if avg_total_shots_for_raw is not None else "missing",
            ),
            "avg_inside_box_shots_for": mk_input(
                key="avg_inside_box_shots_for",
                value=avg_inside_box_shots_for_raw,
                sum_key="inside_sum",
                n_key="inside_n",
                weight=w["avg_inside_box_shots_for"],
                contribution=(inside_box_signal or 0.0) * w["avg_inside_box_shots_for"],
                status="available" if avg_inside_box_shots_for_raw is not None else "missing",
            ),
            "avg_outside_box_shots_for": mk_input(
                key="avg_outside_box_shots_for",
                value=avg_outside_box_shots_for_raw,
                sum_key="outside_sum",
                n_key="outside_n",
                weight=w["avg_outside_box_shots_for"],
                contribution=(outside_box_signal or 0.0) * w["avg_outside_box_shots_for"],
                status="available" if avg_outside_box_shots_for_raw is not None else "missing",
            ),
            "shot_accuracy_for": {
                "value": _round2(shot_accuracy_for),
                "source_table": "derived (fixture_team_stats)",
                "matches_count": int(season_agg.get("matches_count") or 0),
                "sum": None,
                "weight": w["shot_accuracy_for"],
                "contribution": _round2(shot_accuracy_signal * w["shot_accuracy_for"]),
                "status": "available" if shot_accuracy_raw is not None else "missing",
            },
            "avg_goals_for": {
                "value": _round2(avg_goals_for),
                "source_table": "fixtures",
                "matches_count": int(season_agg.get("matches_count") or 0),
                "sum": int(season_agg.get("goals_sum") or 0),
                "weight": w["avg_goals_for"],
                "contribution": _round2(goals_signal * w["avg_goals_for"]),
                "status": "available" if avg_goals_for_raw is not None else "missing",
            },
            "offensive_trend": {
                "value": _round2(trend_delta),
                "source_table": "derived (last5/last10 vs season)",
                "matches_count": int(season_agg.get("matches_count") or 0),
                "sum": None,
                "weight": w["offensive_trend"],
                "contribution": _round2(offensive_trend_signal * w["offensive_trend"]),
                "status": "available" if (last5_sot is not None or last10_sot is not None) else "missing",
            },
        }

        explanation = (
            "Componente offensiva in scala SOT: combina SOT medi, volume tiri, inside/outside box, precisione, goal e trend "
            "con cap prudente ±0.75 rispetto alla media SOT stagionale."
        )

        return {
            "value": _round2(capped_component),
            "inputs": inputs,
            "fallbacks_used": fallbacks_used,
            "cap_applied": cap_applied,
            "cap_bounds": {"min": _round2(avg_sot_for - 0.75), "max": _round2(avg_sot_for + 0.75)},
            "explanation": explanation,
            "debug": {"raw_value": _round2(raw_component)},
        }

    def _expected_sot_v04_from_baseline(
        self,
        *,
        baseline_inputs: dict[str, float],
        offensive_component_value: float,
    ) -> float:
        # baseline v0.1 (stessa struttura/pesi), sostituendo avg_sot_for con offensive component
        # baseline_expected_sot = 0.30*avg_sot_for + 0.25*avg_sot_conceded_opp + 0.15*avg_sot_for_split + 0.10*avg_sot_conceded_split_opp + 0.10*last5_sot_for + 0.10*last5_sot_conceded_opp
        return round(
            0.30 * float(offensive_component_value)
            + 0.25 * float(baseline_inputs["opp_avg_sot_conceded"])
            + 0.15 * float(baseline_inputs["team_split_avg_sot_for"])
            + 0.10 * float(baseline_inputs["opp_split_avg_sot_conceded"])
            + 0.10 * float(baseline_inputs["team_last5_avg_sot_for"])
            + 0.10 * float(baseline_inputs["opp_last5_avg_sot_conceded"]),
            2,
        )

    def generate_for_upcoming_season(self, db: Session, season_year: int, *, limit: int = 200) -> dict[str, Any]:
        try:
            league, season = self._season_row(db, season_year)
        except Exception as exc:
            return {
                "status": "error",
                "failed_step": "load_season",
                "message": "Impossibile caricare league/season.",
                "details": str(exc),
                "partial_result": {"upcoming_fixtures_found": 0, "predictions_created_or_updated": 0, "errors": []},
            }

        q = (
            select(Fixture)
            .where(Fixture.season_id == season.id)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )
        fixtures = db.scalars(q).all()
        upcoming = [f for f in fixtures if (f.status or "").upper() not in FINISHED_STATUSES][:limit]

        if not upcoming:
            return {
                "status": "error",
                "failed_step": "no_upcoming_fixtures",
                "message": "Nessuna fixture upcoming trovata per la stagione richiesta.",
                "details": f"season={int(season_year)} league_id={int(league.id)} season_id={int(season.id)}",
                "partial_result": {"upcoming_fixtures_found": 0, "predictions_created_or_updated": 0, "errors": []},
            }

        # Dipendenza: baseline v0.1 deve esistere per tutte le fixture/team upcoming.
        fx_ids = [int(f.id) for f in upcoming]
        required = len(upcoming) * 2
        baseline_count = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .where(
                    TeamSotPrediction.fixture_id.in_(fx_ids),
                    TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    TeamSotPrediction.predicted_sot.isnot(None),
                )
            )
            or 0
        )
        if baseline_count < required:
            return {
                "status": "error",
                "failed_step": "missing_v01_predictions",
                "message": "Prediction baseline v0.1 mancanti: genera v0.1 prima di v0.4.",
                "details": f"required={required} found={baseline_count}",
                "partial_result": {
                    "upcoming_fixtures_found": len(upcoming),
                    "predictions_created_or_updated": 0,
                    "errors": [
                        {
                            "error": "missing_v01_prediction",
                            "message": "Coverage baseline v0.1 insufficiente per upcoming.",
                            "required": required,
                            "found": baseline_count,
                        }
                    ],
                },
            }

        created = 0
        errors: list[dict[str, Any]] = []

        for fx in upcoming:
            for team_id in (int(fx.home_team_id), int(fx.away_team_id)):
                # richiede baseline v0.1 per confronto (come v0.3)
                v01 = db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == team_id,
                        TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION,
                    )
                )
                if v01 is None or v01.predicted_sot is None:
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "missing_v01_prediction",
                            "message": "Prediction baseline v0.1 mancante: genera v0.1 prima di v0.4.",
                        }
                    )
                    continue

                try:
                    mode = "pre_match"
                    prior = self._prior_completed_fixtures_for_team(
                        db,
                        season_id=season.id,
                        cutoff_kickoff=fx.kickoff_at,
                        cutoff_fixture_id=int(fx.id),
                        team_id=int(team_id),
                        mode=mode,
                    )
                    fx_ids = [int(f.id) for f in prior]
                    stats_map = self._team_stats_map(db, fx_ids)

                    season_agg = self._agg_for_team(fixtures=prior, stats_map=stats_map, team_id=int(team_id))
                    last5 = self._last_n(prior, 5)
                    last10 = self._last_n(prior, 10)
                    last5_agg = self._agg_for_team(fixtures=last5, stats_map=stats_map, team_id=int(team_id))
                    last10_agg = self._agg_for_team(fixtures=last10, stats_map=stats_map, team_id=int(team_id))

                    comp = self._compute_offensive_component(season_agg=season_agg, last5_agg=last5_agg, last10_agg=last10_agg)
                    comp_value = float(comp["value"] or PRUDENTIAL_FALLBACK_SOT)

                    # baseline other inputs: compute opponent conceded etc from same primitives (reuse minimal from v0.1 expectations)
                    # We rely on existing features from v0.1 prediction raw_json if available, else approximate from audit-style stats.
                    # To avoid surprises, fallback to v0.1 predicted_sot input components if present.
                    other = {
                        "opp_avg_sot_conceded": comp_value,  # placeholder overwritten below
                        "team_split_avg_sot_for": float(comp_value),
                        "opp_split_avg_sot_conceded": float(comp_value),
                        "team_last5_avg_sot_for": float(_safe_float(last5_agg.get("sot_mean")) or comp_value),
                        "opp_last5_avg_sot_conceded": float(comp_value),
                    }

                    # Try to read v0.1 breakdown values from stored v0.1 raw_json if present to keep other blocks identical.
                    raw = v01.raw_json if isinstance(v01.raw_json, dict) else None
                    bd = (raw or {}).get("calculation_breakdown") if isinstance(raw, dict) else None
                    if isinstance(bd, dict):
                        def get_num(k: str) -> float | None:
                            val = bd.get(k)
                            return float(val) if isinstance(val, (int, float)) else None

                        other["opp_avg_sot_conceded"] = float(get_num("opponent_season_avg_sot_conceded") or other["opp_avg_sot_conceded"])
                        other["team_split_avg_sot_for"] = float(get_num("team_home_away_avg_sot_for") or other["team_split_avg_sot_for"])
                        other["opp_split_avg_sot_conceded"] = float(get_num("opponent_home_away_avg_sot_conceded") or other["opp_split_avg_sot_conceded"])
                        other["team_last5_avg_sot_for"] = float(get_num("team_last5_avg_sot_for") or other["team_last5_avg_sot_for"])
                        other["opp_last5_avg_sot_conceded"] = float(get_num("opponent_last5_avg_sot_conceded") or other["opp_last5_avg_sot_conceded"])

                    expected_v04 = self._expected_sot_v04_from_baseline(
                        baseline_inputs=other,
                        offensive_component_value=comp_value,
                    )

                    raw_json = {
                        "model_version": self.model_version,
                        "offensive_production_component": {
                            "value": _round2(comp_value),
                            "weight_in_model": 0.30,
                            "inputs": comp["inputs"],
                            "fallbacks_used": comp["fallbacks_used"],
                            "cap_applied": comp["cap_applied"],
                            "explanation": comp["explanation"],
                        },
                        "debug": {
                            "baseline_other_inputs": {k: _round2(float(v)) for k, v in other.items()},
                            "raw_component_value": comp.get("debug", {}).get("raw_value"),
                            "cap_bounds": comp.get("cap_bounds"),
                        },
                    }
                    team_row = db.get(Team, int(team_id))
                    tname = team_row.name if team_row is not None else str(team_id)
                    raw_json = append_trace_to_raw_json(
                        raw_json,
                        model_version=self.model_version,
                        team_id=int(team_id),
                        team_name=tname,
                        audit_map={},
                        hours_to_kickoff=compute_hours_to_kickoff(fx.kickoff_at),
                        prediction_confidence=None,
                    )

                    # upsert prediction row
                    existing = db.scalar(
                        select(TeamSotPrediction).where(
                            TeamSotPrediction.fixture_id == fx.id,
                            TeamSotPrediction.team_id == int(team_id),
                            TeamSotPrediction.model_version == self.model_version,
                        )
                    )
                    if existing is None:
                        existing = TeamSotPrediction(
                            fixture_id=int(fx.id),
                            team_id=int(team_id),
                            model_version=self.model_version,
                        )
                        db.add(existing)
                    existing.predicted_sot = float(expected_v04)
                    existing.raw_json = raw_json
                    existing.explanation = "v0.4: core offensivo migliorato (componente offensiva cappata)."
                    created += 1
                    db.commit()
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    errors.append(
                        {
                            "fixture_id": int(fx.id),
                            "team_id": int(team_id),
                            "error": "compute_failed",
                            "message": "Errore durante calcolo v0.4.",
                            "details": str(exc),
                        }
                    )
                    continue

        return {
            "status": "success",
            "model_version": self.model_version,
            "season": int(season_year),
            "upcoming_fixtures_found": len(upcoming),
            "predictions_created_or_updated": int(created),
            "errors": errors,
        }

    def upcoming_v04(self, db: Session, season_year: int, *, limit: int = 50, only_next_round: bool = True) -> dict[str, Any]:
        league, season = self._season_row(db, season_year)
        q = (
            select(Fixture)
            .where(Fixture.season_id == season.id)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )
        xs = db.scalars(q).all()
        upcoming = [f for f in xs if (f.status or "").upper() not in FINISHED_STATUSES]
        fixtures = upcoming[:limit]

        ctx_svc = MatchContextService()
        matches: list[dict[str, Any]] = []
        for fx in fixtures:
            def read_pred(team_id: int, mv: str) -> TeamSotPrediction | None:
                return db.scalar(
                    select(TeamSotPrediction).where(
                        TeamSotPrediction.fixture_id == fx.id,
                        TeamSotPrediction.team_id == team_id,
                        TeamSotPrediction.model_version == mv,
                    )
                )

            h01 = read_pred(int(fx.home_team_id), BASELINE_SOT_MODEL_VERSION)
            a01 = read_pred(int(fx.away_team_id), BASELINE_SOT_MODEL_VERSION)
            h04 = read_pred(int(fx.home_team_id), self.model_version)
            a04 = read_pred(int(fx.away_team_id), self.model_version)

            def side_payload(p01: TeamSotPrediction | None, p04: TeamSotPrediction | None) -> dict[str, Any] | None:
                if p04 is None or p04.predicted_sot is None:
                    return None
                v04 = float(p04.predicted_sot)
                v01 = float(p01.predicted_sot) if (p01 and p01.predicted_sot is not None) else None
                raw = p04.raw_json if isinstance(p04.raw_json, dict) else {}
                comp = (raw or {}).get("offensive_production_component") if isinstance(raw, dict) else None
                return {
                    "expected_sot_v01": _round2(v01),
                    "expected_sot_v04": _round2(v04),
                    "difference_from_v01": _round2((v04 - v01) if v01 is not None else None),
                    "offensive_production_component": (comp or {}).get("value") if isinstance(comp, dict) else None,
                    "breakdown": raw,
                }

            context_payload = ctx_svc.build_match_context(db, int(fx.id))
            matches.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "kickoff_at": fx.kickoff_at,
                    "round": fx.round,
                    "status_short": fx.status,
                    "home_team_id": int(fx.home_team_id),
                    "away_team_id": int(fx.away_team_id),
                    "home": side_payload(h01, h04),
                    "away": side_payload(a01, a04),
                    "context_status": context_payload.get("context_status", "not_available"),
                    "match_context": context_payload.get("match_context"),
                    "home_team_context": context_payload.get("home_team_context"),
                    "away_team_context": context_payload.get("away_team_context"),
                    "season_phase_context": context_payload.get("season_phase_context"),
                }
            )

        return {"status": "success", "model_version": self.model_version, "season": int(season_year), "matches": matches}

