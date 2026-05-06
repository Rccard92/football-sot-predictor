from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED, FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat, PlayerSotProfile, Team, TeamSotPrediction, TeamSotPredictionAdjustment
from app.schemas.match_analysis import (
    AuditCalculationBlock,
    AuditDataPolicyBlock,
    AuditFixtureBlock,
    AuditSampleRow,
    AuditSection,
    AuditTeamBlock,
    AuditVariable,
    ModelInputsSummary,
    MatchVariablesAuditResponse,
)
from app.services.sot_feature_math import fixture_key_before

logger = logging.getLogger(__name__)

AuditMode = Literal["pre_match", "post_match"]


@dataclass(frozen=True)
class TeamContext:
    team_id: int
    team_name: str
    is_home: bool
    opponent_id: int
    opponent_name: str


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _section_quality(vars_: list[AuditVariable]) -> tuple[int, int, float]:
    available = sum(1 for v in vars_ if v.status == "available")
    missing = sum(1 for v in vars_ if v.status == "missing")
    total = len(vars_) or 1
    pct = round((available / total) * 100.0, 2)
    return available, missing, pct


class MatchVariableAuditService:
    """Servizio read-only per audit variabili (no scritture DB)."""

    unit_sot = "tiri in porta"
    unit_shots = "tiri"
    unit_goals = "goal"

    def _fixture_block(self, db: Session, fixture_id: int) -> AuditFixtureBlock:
        fx = db.get(Fixture, fixture_id)
        if fx is None:
            raise ValueError(f"Fixture {fixture_id} non trovata")
        home = db.get(Team, fx.home_team_id)
        away = db.get(Team, fx.away_team_id)
        return AuditFixtureBlock(
            fixture_id=int(fx.id),
            api_fixture_id=int(fx.api_fixture_id),
            round=fx.round,
            kickoff_at=fx.kickoff_at,
            status_short=fx.status,
            home_team=AuditTeamBlock(id=int(fx.home_team_id), name=home.name if home else "", logo_url=home.logo_url if home else None),
            away_team=AuditTeamBlock(id=int(fx.away_team_id), name=away.name if away else "", logo_url=away.logo_url if away else None),
        )

    def _prior_completed_fixtures(
        self,
        db: Session,
        *,
        season_id: int,
        cutoff_kickoff: datetime,
        cutoff_fixture_id: int,
        mode: AuditMode,
    ) -> list[Fixture]:
        q = (
            select(Fixture)
            .where(Fixture.season_id == season_id, Fixture.status.in_(FINISHED_STATUSES))
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )
        completed = db.scalars(q).all()
        if mode == "post_match":
            return list(completed)
        # pre_match anti-leakage
        return [f for f in completed if fixture_key_before(f.kickoff_at, f.id, cutoff_kickoff, cutoff_fixture_id)]

    def _team_stats_map(self, db: Session, fixture_ids: list[int]) -> dict[tuple[int, int], FixtureTeamStat]:
        if not fixture_ids:
            return {}
        rows = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids))).all()
        return {(int(r.fixture_id), int(r.team_id)): r for r in rows}

    def _sample_rows_for_team(
        self,
        *,
        fixtures: list[Fixture],
        stats_map: dict[tuple[int, int], FixtureTeamStat],
        team_ctx: TeamContext,
        limit: int | None,
    ) -> list[AuditSampleRow]:
        # fixtures already ordered asc → pick tail for latest
        src = fixtures[-limit:] if limit is not None else fixtures
        out: list[AuditSampleRow] = []
        for f in src:
            st_team = stats_map.get((int(f.id), team_ctx.team_id))
            st_opp = stats_map.get((int(f.id), team_ctx.opponent_id))
            # goals for/against from fixture by side
            if f.home_team_id == team_ctx.team_id:
                gf = f.goals_home
                ga = f.goals_away
                side: Literal["home", "away"] = "home"
                opp_name = team_ctx.opponent_name
            else:
                gf = f.goals_away
                ga = f.goals_home
                side = "away"
                opp_name = team_ctx.opponent_name

            out.append(
                AuditSampleRow(
                    fixture_id=int(f.id),
                    date=f.kickoff_at,
                    home_team=str(db.get(Team, f.home_team_id).name if db.get(Team, f.home_team_id) else ""),
                    away_team=str(db.get(Team, f.away_team_id).name if db.get(Team, f.away_team_id) else ""),
                    team=team_ctx.team_name,
                    team_id=team_ctx.team_id,
                    opponent=opp_name,
                    opponent_id=team_ctx.opponent_id,
                    side=side,
                    shots_on_target=int(st_team.shots_on_target) if st_team and st_team.shots_on_target is not None else None,
                    total_shots=int(st_team.total_shots) if st_team and st_team.total_shots is not None else None,
                    goals_for=int(gf) if gf is not None else None,
                    goals_against=int(ga) if ga is not None else None,
                )
            )
        return out

    def _agg_for_team(
        self,
        *,
        fixtures: list[Fixture],
        stats_map: dict[tuple[int, int], FixtureTeamStat],
        team_ctx: TeamContext,
    ) -> dict[str, Any]:
        # Aggregate pre-match: for team stats, use team row for FOR metrics and opponent row for AGAINST metrics.
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
            st_team = stats_map.get((int(f.id), team_ctx.team_id))
            st_opp = stats_map.get((int(f.id), team_ctx.opponent_id))

            if st_team and st_team.shots_on_target is not None:
                sot_for_sum += int(st_team.shots_on_target)
                sot_for_n += 1
            if st_team and st_team.total_shots is not None:
                shots_for_sum += int(st_team.total_shots)
                shots_for_n += 1

            # conceded: from opponent team_stat row in same fixture (as per rule)
            if st_opp and st_opp.shots_on_target is not None:
                sot_against_sum += int(st_opp.shots_on_target)
                sot_against_n += 1
            if st_opp and st_opp.total_shots is not None:
                shots_against_sum += int(st_opp.total_shots)
                shots_against_n += 1

            # goals: from fixture score by side
            if f.home_team_id == team_ctx.team_id:
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
            return round(sum_ / n, 4) if n > 0 else None

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

    def _trend_vs_season(self, last5_mean: float | None, season_mean: float | None) -> str:
        if last5_mean is None or season_mean is None:
            return "missing"
        if season_mean == 0:
            return "in_linea"
        ratio = last5_mean / season_mean
        if ratio >= 1.05:
            return "sopra_media"
        if ratio <= 0.95:
            return "sotto_media"
        return "in_linea"

    def _var(
        self,
        *,
        key: str,
        label: str,
        team_ctx: TeamContext | None,
        value: float | None,
        unit: str | None,
        status: str,
        impl_status: str,
        applied_to_model: bool,
        weight: float | None,
        weight_label: str | None,
        source_table: str | None,
        source_description: str | None,
        calculation: AuditCalculationBlock | None,
        sample_rows: list[AuditSampleRow],
        notes: str | None,
    ) -> AuditVariable:
        return AuditVariable(
            key=key,
            label=label,
            team_id=team_ctx.team_id if team_ctx else None,
            team_name=team_ctx.team_name if team_ctx else None,
            value=value,
            unit=unit,
            status=status,  # type: ignore[arg-type]
            implementation_status=impl_status,  # type: ignore[arg-type]
            applied_to_model=applied_to_model,
            weight=weight,
            weight_label=weight_label,
            source_table=source_table,
            source_description=source_description,
            calculation=calculation,
            sample_rows=sample_rows,
            notes=notes,
        )

    def build_fixture_variables_shots_on_target(
        self,
        db: Session,
        fixture_id: int,
        *,
        mode: AuditMode = "pre_match",
    ) -> MatchVariablesAuditResponse:
        fixture = db.get(Fixture, fixture_id)
        if fixture is None:
            raise ValueError(f"Fixture {fixture_id} non trovata")
        home = db.get(Team, fixture.home_team_id)
        away = db.get(Team, fixture.away_team_id)
        if home is None or away is None:
            raise ValueError("Team non trovati per la fixture")

        fx_block = self._fixture_block(db, fixture_id)

        completed_priors = self._prior_completed_fixtures(
            db,
            season_id=int(fixture.season_id),
            cutoff_kickoff=fixture.kickoff_at,
            cutoff_fixture_id=int(fixture.id),
            mode=mode,
        )
        prior_ids = [int(f.id) for f in completed_priors]
        stats_map = self._team_stats_map(db, prior_ids)

        # Build per-team contexts (opponent fixed to the fixture opponent)
        home_ctx = TeamContext(team_id=int(home.id), team_name=home.name, is_home=True, opponent_id=int(away.id), opponent_name=away.name)
        away_ctx = TeamContext(team_id=int(away.id), team_name=away.name, is_home=False, opponent_id=int(home.id), opponent_name=home.name)

        # Filter priors by team involvement
        home_team_priors = [f for f in completed_priors if int(f.home_team_id) == home_ctx.team_id or int(f.away_team_id) == home_ctx.team_id]
        away_team_priors = [f for f in completed_priors if int(f.home_team_id) == away_ctx.team_id or int(f.away_team_id) == away_ctx.team_id]

        # Home/away splits
        home_as_home = [f for f in home_team_priors if int(f.home_team_id) == home_ctx.team_id]
        away_as_away = [f for f in away_team_priors if int(f.away_team_id) == away_ctx.team_id]

        # Last 5/10 (by kickoff desc, id desc)
        def last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
            xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)
            xs = xs[:n]
            return sorted(xs, key=lambda f: (f.kickoff_at, f.id))

        home_last5 = last_n(home_team_priors, 5)
        home_last10 = last_n(home_team_priors, 10)
        away_last5 = last_n(away_team_priors, 5)
        away_last10 = last_n(away_team_priors, 10)

        # Aggregates
        home_season = self._agg_for_team(fixtures=home_team_priors, stats_map=stats_map, team_ctx=home_ctx)
        away_season = self._agg_for_team(fixtures=away_team_priors, stats_map=stats_map, team_ctx=away_ctx)
        home_last5_agg = self._agg_for_team(fixtures=home_last5, stats_map=stats_map, team_ctx=home_ctx)
        home_last10_agg = self._agg_for_team(fixtures=home_last10, stats_map=stats_map, team_ctx=home_ctx)
        away_last5_agg = self._agg_for_team(fixtures=away_last5, stats_map=stats_map, team_ctx=away_ctx)
        away_last10_agg = self._agg_for_team(fixtures=away_last10, stats_map=stats_map, team_ctx=away_ctx)

        # Splits aggregates
        home_home_split = self._agg_for_team(fixtures=home_as_home, stats_map=stats_map, team_ctx=home_ctx)
        away_away_split = self._agg_for_team(fixtures=away_as_away, stats_map=stats_map, team_ctx=away_ctx)

        # Helper to build variable quickly
        def mean_var(
            *,
            key: str,
            label: str,
            team_ctx: TeamContext,
            value: float | None,
            unit: str,
            source_table: str,
            source_description: str,
            formula: str,
            meta: dict[str, Any],
            sample: list[AuditSampleRow],
            applied_to_model: bool,
            weight: float | None = None,
            weight_label: str | None = None,
            notes: str | None = None,
        ) -> AuditVariable:
            st = "available" if value is not None else "missing"
            calc = AuditCalculationBlock(formula=formula, meta=meta, result=value)
            return self._var(
                key=key,
                label=label,
                team_ctx=team_ctx,
                value=value,
                unit=unit,
                status=st,
                impl_status="implemented",
                applied_to_model=applied_to_model,
                weight=weight,
                weight_label=weight_label,
                source_table=source_table,
                source_description=source_description,
                calculation=calc,
                sample_rows=sample,
                notes=notes,
            )

        # Weights for baseline v0.1 SOT (only for SOT variables currently in formula)
        # Keep aligned with docs: 0.30 season_avg_sot_for, 0.25 opponent_season_avg_sot_conceded, 0.15 home_away_avg_sot_for, 0.10 opponent_home_away_avg_sot_conceded, 0.10 last5_avg_sot_for, 0.10 opponent_last5_avg_sot_conceded
        w_season_for = 0.30
        w_opp_season_conc = 0.25
        w_homeaway_for = 0.15
        w_opp_homeaway_conc = 0.10
        w_last5_for = 0.10
        w_opp_last5_conc = 0.10

        # Base match data section
        base_vars: list[AuditVariable] = [
            self._var(
                key="fixture_id",
                label="Fixture ID",
                team_ctx=None,
                value=float(fx_block.fixture_id),
                unit=None,
                status="available",
                impl_status="implemented",
                applied_to_model=False,
                weight=None,
                weight_label=None,
                source_table="fixtures",
                source_description="Tabella fixtures.",
                calculation=AuditCalculationBlock(formula="identity", meta=None, result=float(fx_block.fixture_id)),
                sample_rows=[],
                notes=None,
            ),
        ]

        # Offensive production sections (home/away) — season & last5/10
        def build_offense(team_ctx: TeamContext, season: dict[str, Any], last5: dict[str, Any], last10: dict[str, Any], team_priors: list[Fixture]) -> list[AuditVariable]:
            sample_season = self._sample_rows_for_team(fixtures=team_priors, stats_map=stats_map, team_ctx=team_ctx, limit=10)
            sample_last5 = self._sample_rows_for_team(fixtures=last_n(team_priors, 5), stats_map=stats_map, team_ctx=team_ctx, limit=None)
            sample_last10 = self._sample_rows_for_team(fixtures=last_n(team_priors, 10), stats_map=stats_map, team_ctx=team_ctx, limit=10)
            return [
                mean_var(
                    key="season_avg_sot_for",
                    label=f"Media stagionale tiri in porta fatti – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["sot_for_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Statistiche squadra (partite concluse) precedenti alla fixture analizzata.",
                    formula="sum(shots_on_target) / matches_count",
                    meta={"sum": season["sot_for_sum"], "matches_count": season["sot_for_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=True,
                    weight=w_season_for,
                    weight_label="30%",
                    notes="Usa solo fixture precedenti (anti-leakage).",
                ),
                mean_var(
                    key="season_total_sot_for",
                    label=f"Totale tiri in porta fatti stagione (pre-match) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["sot_for_sum"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Somma SOT fatti sulle fixture concluse pre-match.",
                    formula="sum(shots_on_target)",
                    meta={"sum": season["sot_for_sum"], "matches_count": season["sot_for_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="season_matches_count",
                    label=f"Partite considerate (stagione) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["matches_count"]),
                    unit="partite",
                    source_table="fixtures",
                    source_description="Numero fixture concluse pre-match in cui la squadra è presente.",
                    formula="count(fixtures)",
                    meta={"matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="season_avg_shots_for",
                    label=f"Media tiri totali fatti – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["shots_for_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Statistiche squadra (tiri totali) pre-match.",
                    formula="sum(total_shots) / matches_count",
                    meta={"sum": season["shots_for_sum"], "matches_count": season["shots_for_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes="Auditabile; non entra nella formula SOT v0.1.",
                ),
                mean_var(
                    key="season_total_shots_for",
                    label=f"Totale tiri totali fatti stagione – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["shots_for_sum"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Somma tiri totali pre-match.",
                    formula="sum(total_shots)",
                    meta={"sum": season["shots_for_sum"], "matches_count": season["shots_for_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="season_avg_goals_for",
                    label=f"Media goal fatti – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["goals_for_mean"]),
                    unit=self.unit_goals,
                    source_table="fixtures",
                    source_description="Goal da tabella fixtures (goals_home/goals_away) pre-match.",
                    formula="sum(goals_for) / matches_count",
                    meta={"sum": season["goals_for_sum"], "matches_count": season["goals_for_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="last5_avg_sot_for",
                    label=f"Media tiri in porta ultime 5 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last5["sot_for_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Ultime 5 fixture concluse pre-match.",
                    formula="mean(shots_on_target over last 5)",
                    meta={"sum": last5["sot_for_sum"], "matches_count": last5["sot_for_n"], "fixtures_count": len(sample_last5)},
                    sample=sample_last5,
                    applied_to_model=True,
                    weight=w_last5_for,
                    weight_label="10%",
                    notes=None,
                ),
                mean_var(
                    key="last5_avg_shots_for",
                    label=f"Media tiri totali ultime 5 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last5["shots_for_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Ultime 5 fixture concluse pre-match.",
                    formula="mean(total_shots over last 5)",
                    meta={"sum": last5["shots_for_sum"], "matches_count": last5["shots_for_n"], "fixtures_count": len(sample_last5)},
                    sample=sample_last5,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="last10_avg_sot_for",
                    label=f"Media tiri in porta ultime 10 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last10["sot_for_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Ultime 10 fixture concluse pre-match.",
                    formula="mean(shots_on_target over last 10)",
                    meta={"sum": last10["sot_for_sum"], "matches_count": last10["sot_for_n"], "fixtures_count": len(sample_last10)},
                    sample=sample_last10,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="last10_avg_shots_for",
                    label=f"Media tiri totali ultime 10 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last10["shots_for_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Ultime 10 fixture concluse pre-match.",
                    formula="mean(total_shots over last 10)",
                    meta={"sum": last10["shots_for_sum"], "matches_count": last10["shots_for_n"], "fixtures_count": len(sample_last10)},
                    sample=sample_last10,
                    applied_to_model=False,
                    notes=None,
                ),
            ]

        home_off_vars = build_offense(home_ctx, home_season, home_last5_agg, home_last10_agg, home_team_priors)
        away_off_vars = build_offense(away_ctx, away_season, away_last5_agg, away_last10_agg, away_team_priors)

        # Defensive concession sections (conceded derived from opponent row)
        def build_concession(team_ctx: TeamContext, season: dict[str, Any], last5: dict[str, Any], team_priors: list[Fixture]) -> list[AuditVariable]:
            sample_season = self._sample_rows_for_team(fixtures=team_priors, stats_map=stats_map, team_ctx=team_ctx, limit=10)
            sample_last5 = self._sample_rows_for_team(fixtures=last_n(team_priors, 5), stats_map=stats_map, team_ctx=team_ctx, limit=None)
            return [
                mean_var(
                    key="opponent_season_avg_sot_conceded",
                    label=f"Media stagionale tiri in porta concessi – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["sot_against_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Concessi: SOT della riga avversaria nella stessa fixture.",
                    formula="sum(opponent.shots_on_target) / matches_count",
                    meta={"sum": season["sot_against_sum"], "matches_count": season["sot_against_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=True,
                    weight=w_opp_season_conc,
                    weight_label="25%",
                    notes="Concessi calcolati dalla riga avversaria (stessa fixture).",
                ),
                mean_var(
                    key="season_total_sot_conceded",
                    label=f"Totale tiri in porta concessi stagione (pre-match) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["sot_against_sum"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Somma SOT concessi pre-match (da riga avversaria).",
                    formula="sum(opponent.shots_on_target)",
                    meta={"sum": season["sot_against_sum"], "matches_count": season["sot_against_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="season_avg_shots_conceded",
                    label=f"Media tiri totali concessi – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["shots_against_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Tiri totali concessi (da riga avversaria).",
                    formula="sum(opponent.total_shots) / matches_count",
                    meta={"sum": season["shots_against_sum"], "matches_count": season["shots_against_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="season_avg_goals_conceded",
                    label=f"Media goal concessi – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(season["goals_against_mean"]),
                    unit=self.unit_goals,
                    source_table="fixtures",
                    source_description="Goal concessi da fixtures (goals_home/goals_away) pre-match.",
                    formula="sum(goals_against) / matches_count",
                    meta={"sum": season["goals_against_sum"], "matches_count": season["goals_against_n"], "total_matches_count": season["matches_count"]},
                    sample=sample_season,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key="opponent_last5_avg_sot_conceded",
                    label=f"Media tiri in porta concessi ultime 5 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last5["sot_against_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description="Ultime 5 (concessi da riga avversaria).",
                    formula="mean(opponent.shots_on_target over last 5)",
                    meta={"sum": last5["sot_against_sum"], "matches_count": last5["sot_against_n"], "fixtures_count": len(sample_last5)},
                    sample=sample_last5,
                    applied_to_model=True,
                    weight=w_opp_last5_conc,
                    weight_label="10%",
                    notes=None,
                ),
                mean_var(
                    key="last5_avg_shots_conceded",
                    label=f"Media tiri totali concessi ultime 5 – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(last5["shots_against_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description="Ultime 5 (tiri concessi da riga avversaria).",
                    formula="mean(opponent.total_shots over last 5)",
                    meta={"sum": last5["shots_against_sum"], "matches_count": last5["shots_against_n"], "fixtures_count": len(sample_last5)},
                    sample=sample_last5,
                    applied_to_model=False,
                    notes=None,
                ),
            ]

        home_conc_vars = build_concession(home_ctx, home_season, home_last5_agg, home_team_priors)
        away_conc_vars = build_concession(away_ctx, away_season, away_last5_agg, away_team_priors)

        # Split home/away section variables
        def build_split(team_ctx: TeamContext, split: dict[str, Any], fixtures: list[Fixture], label_side: str, applied_for_weight: float, applied_for_label: str) -> list[AuditVariable]:
            sample = self._sample_rows_for_team(fixtures=fixtures, stats_map=stats_map, team_ctx=team_ctx, limit=10)
            return [
                mean_var(
                    key=f"{label_side}_avg_sot_for",
                    label=f"Media tiri in porta fatti ({label_side}) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(split["sot_for_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description=f"Split {label_side}: solo fixture pre-match nello stesso lato.",
                    formula="mean(shots_on_target over split)",
                    meta={"sum": split["sot_for_sum"], "matches_count": split["sot_for_n"], "total_matches_count": split["matches_count"]},
                    sample=sample,
                    applied_to_model=True,
                    weight=applied_for_weight,
                    weight_label=applied_for_label,
                    notes=None,
                ),
                mean_var(
                    key=f"{label_side}_avg_shots_for",
                    label=f"Media tiri totali fatti ({label_side}) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(split["shots_for_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description=f"Split {label_side}: tiri totali.",
                    formula="mean(total_shots over split)",
                    meta={"sum": split["shots_for_sum"], "matches_count": split["shots_for_n"], "total_matches_count": split["matches_count"]},
                    sample=sample,
                    applied_to_model=False,
                    notes=None,
                ),
                mean_var(
                    key=f"{label_side}_avg_sot_conceded",
                    label=f"Media tiri in porta concessi ({label_side}) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(split["sot_against_mean"]),
                    unit=self.unit_sot,
                    source_table="fixture_team_stats",
                    source_description=f"Split {label_side}: concessi da riga avversaria.",
                    formula="mean(opponent.shots_on_target over split)",
                    meta={"sum": split["sot_against_sum"], "matches_count": split["sot_against_n"], "total_matches_count": split["matches_count"]},
                    sample=sample,
                    applied_to_model=True,
                    weight=w_opp_homeaway_conc,
                    weight_label="10%",
                    notes=None,
                ),
                mean_var(
                    key=f"{label_side}_avg_shots_conceded",
                    label=f"Media tiri totali concessi ({label_side}) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=_safe_float(split["shots_against_mean"]),
                    unit=self.unit_shots,
                    source_table="fixture_team_stats",
                    source_description=f"Split {label_side}: concessi da riga avversaria.",
                    formula="mean(opponent.total_shots over split)",
                    meta={"sum": split["shots_against_sum"], "matches_count": split["shots_against_n"], "total_matches_count": split["matches_count"]},
                    sample=sample,
                    applied_to_model=False,
                    notes=None,
                ),
            ]

        split_vars = []
        split_vars += build_split(home_ctx, home_home_split, home_as_home, "home", w_homeaway_for, "15%")
        split_vars += build_split(away_ctx, away_away_split, away_as_away, "away", w_homeaway_for, "15%")

        # Recent form section: last5 list + trend flags
        def recent_form_vars(team_ctx: TeamContext, season: dict[str, Any], last5: dict[str, Any], last5_fixtures: list[Fixture]) -> list[AuditVariable]:
            sample_last5 = self._sample_rows_for_team(fixtures=last5_fixtures, stats_map=stats_map, team_ctx=team_ctx, limit=None)
            trend_for = self._trend_vs_season(_safe_float(last5["sot_for_mean"]), _safe_float(season["sot_for_mean"]))
            trend_against = self._trend_vs_season(_safe_float(last5["sot_against_mean"]), _safe_float(season["sot_against_mean"]))
            return [
                self._var(
                    key="last5_fixtures",
                    label=f"Ultime 5 partite (elenco) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=float(len(sample_last5)),
                    unit="fixture",
                    status="available",
                    impl_status="implemented",
                    applied_to_model=False,
                    weight=None,
                    weight_label=None,
                    source_table="fixtures",
                    source_description="Elenco fixture ultime 5 pre-match.",
                    calculation=AuditCalculationBlock(formula="list(last5 fixtures)", meta={"fixtures_count": len(sample_last5)}, result=float(len(sample_last5))),
                    sample_rows=sample_last5,
                    notes="Espone tutte e 5 le fixture quando disponibili.",
                ),
                self._var(
                    key="trend_last5_vs_season_sot_for",
                    label=f"Trend ultime 5 vs media stagione (SOT fatti) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=None,
                    unit=None,
                    status="available" if _safe_float(last5["sot_for_mean"]) is not None and _safe_float(season["sot_for_mean"]) is not None else "missing",
                    impl_status="implemented",
                    applied_to_model=False,
                    weight=None,
                    weight_label=None,
                    source_table="derived",
                    source_description="Confronto last5 vs media stagione con soglia ±5%.",
                    calculation=AuditCalculationBlock(
                        formula="trend = sopra_media if last5>=1.05*season; sotto_media if last5<=0.95*season; else in_linea",
                        meta={"last5_mean": last5.get("sot_for_mean"), "season_mean": season.get("sot_for_mean"), "trend": trend_for},
                        result=None,
                    ),
                    sample_rows=sample_last5,
                    notes=trend_for,
                ),
                self._var(
                    key="trend_last5_vs_season_sot_against",
                    label=f"Trend ultime 5 vs media stagione (SOT concessi) – {team_ctx.team_name}",
                    team_ctx=team_ctx,
                    value=None,
                    unit=None,
                    status="available" if _safe_float(last5["sot_against_mean"]) is not None and _safe_float(season["sot_against_mean"]) is not None else "missing",
                    impl_status="implemented",
                    applied_to_model=False,
                    weight=None,
                    weight_label=None,
                    source_table="derived",
                    source_description="Confronto last5 vs media stagione con soglia ±5%.",
                    calculation=AuditCalculationBlock(
                        formula="trend = sopra_media if last5>=1.05*season; sotto_media if last5<=0.95*season; else in_linea",
                        meta={"last5_mean": last5.get("sot_against_mean"), "season_mean": season.get("sot_against_mean"), "trend": trend_against},
                        result=None,
                    ),
                    sample_rows=sample_last5,
                    notes=trend_against,
                ),
            ]

        recent_vars = []
        recent_vars += recent_form_vars(home_ctx, home_season, home_last5_agg, home_last5)
        recent_vars += recent_form_vars(away_ctx, away_season, away_last5_agg, away_last5)

        # Player impact section: top 5 profiles
        season_id = int(fixture.season_id)
        prof_q = (
            select(PlayerSotProfile)
            .where(PlayerSotProfile.season_id == season_id)
            .order_by(PlayerSotProfile.impact_score.desc().nulls_last(), PlayerSotProfile.shots_on_target_per90.desc().nulls_last())
        )
        profiles = db.scalars(prof_q).all()

        def top5_for_team(team_id: int) -> list[PlayerSotProfile]:
            xs = [p for p in profiles if int(p.team_id) == team_id]
            return xs[:5]

        def player_block(team_ctx: TeamContext) -> AuditVariable:
            top = top5_for_team(team_ctx.team_id)
            # sample_rows for this variable: map player records into calculation.meta, leave sample_rows empty (they are match rows)
            meta_players = [
                {
                    "player_id": int(p.player_id),
                    "name": p.player_name,
                    "shots_on_target_per90": _safe_float(p.shots_on_target_per90),
                    "total_minutes": int(p.total_minutes),
                    "appearances": int(p.appearances),
                    "reliability_score": int(p.reliability_score),
                    "team_sot_share_pct": _safe_float(p.team_sot_share_pct),
                    "impact_score": _safe_float(p.impact_score),
                }
                for p in top
            ]
            return self._var(
                key="top5_players_by_impact",
                label=f"Top 5 giocatori per impact_score – {team_ctx.team_name}",
                team_ctx=team_ctx,
                value=float(len(meta_players)),
                unit="giocatori",
                status="available" if meta_players else "missing",
                impl_status="implemented",
                applied_to_model=False,
                weight=None,
                weight_label=None,
                source_table="player_sot_profiles",
                source_description="Profili giocatore aggregati stagione (SOT).",
                calculation=AuditCalculationBlock(
                    formula="top 5 by impact_score",
                    meta={"top_players": meta_players},
                    result=float(len(meta_players)),
                ),
                sample_rows=[],
                notes="Misura forza rosa/offensiva; non implica formazione ufficiale.",
            )

        player_vars = [player_block(home_ctx), player_block(away_ctx)]

        # Player adjustment (v0.2 player adjusted) if exists in adjustments table for this fixture
        def player_adjustment_var(team_ctx: TeamContext) -> AuditVariable:
            adj = db.scalar(
                select(TeamSotPredictionAdjustment).where(
                    TeamSotPredictionAdjustment.fixture_id == fixture.id,
                    TeamSotPredictionAdjustment.team_id == team_ctx.team_id,
                    TeamSotPredictionAdjustment.model_version == BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
                )
            )
            val = _safe_float(adj.player_adjustment) if adj else None
            return self._var(
                key="player_adjustment",
                label=f"Player adjustment (v0.2 player adjusted) – {team_ctx.team_name}",
                team_ctx=team_ctx,
                value=val,
                unit=self.unit_sot,
                status="available" if val is not None else "missing",
                impl_status="implemented",
                applied_to_model=bool(val is not None),
                weight=None,
                weight_label=None,
                source_table="team_sot_prediction_adjustments",
                source_description="Tabella adjustments v0.2 player adjusted (se generata).",
                calculation=AuditCalculationBlock(
                    formula="lookup adjustment row (no recomputation)",
                    meta={"model_version": BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED},
                    result=val,
                ),
                sample_rows=[],
                notes="Solo lettura; non genera prediction.",
            )

        player_vars += [player_adjustment_var(home_ctx), player_adjustment_var(away_ctx)]

        # model_inputs_summary: read existing predictions if present (no generation)
        def read_predicted(team_id: int, model_version: str) -> float | None:
            row = db.scalar(
                select(TeamSotPrediction).where(
                    TeamSotPrediction.fixture_id == fixture.id,
                    TeamSotPrediction.team_id == team_id,
                    TeamSotPrediction.model_version == model_version,
                )
            )
            return _safe_float(row.predicted_sot) if row else None

        summary = ModelInputsSummary(
            home_team_expected_sot_v01=read_predicted(home_ctx.team_id, BASELINE_SOT_MODEL_VERSION),
            away_team_expected_sot_v01=read_predicted(away_ctx.team_id, BASELINE_SOT_MODEL_VERSION),
            home_team_expected_sot_v02=read_predicted(home_ctx.team_id, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED),
            away_team_expected_sot_v02=read_predicted(away_ctx.team_id, BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED),
        )

        # Build sections and compute quality fields
        def mk_section(id_: str, title: str, vars_: list[AuditVariable]) -> AuditSection:
            av, ms, pct = _section_quality(vars_)
            return AuditSection(id=id_, title=title, variables=vars_, variables_available=av, variables_missing=ms, completeness_pct=pct)

        sections = [
            mk_section("base_match_data", "Dati base partita", base_vars),
            mk_section("home_team_offensive_production", "Produzione offensiva squadra casa", [v for v in home_off_vars if v.team_id == home_ctx.team_id]),
            mk_section("away_team_offensive_production", "Produzione offensiva squadra trasferta", [v for v in away_off_vars if v.team_id == away_ctx.team_id]),
            mk_section("home_team_defensive_concession", "Quanto concede la squadra casa", [v for v in home_conc_vars if v.team_id == home_ctx.team_id]),
            mk_section("away_team_defensive_concession", "Quanto concede la squadra trasferta", [v for v in away_conc_vars if v.team_id == away_ctx.team_id]),
            mk_section("home_away_split", "Rendimento casa/trasferta", split_vars),
            mk_section("recent_form", "Forma recente", recent_vars),
            mk_section("player_impact", "Impatto giocatori", player_vars),
        ]

        data_policy = AuditDataPolicyBlock(
            no_data_leakage=(mode == "pre_match"),
            included_matches_rule="Solo fixture concluse con kickoff_at precedente alla fixture analizzata." if mode == "pre_match" else "Include fixture concluse dell’intera stagione (audit post-match).",
        )

        return MatchVariablesAuditResponse(
            fixture=fx_block,
            market="shots_on_target",
            mode=mode,  # type: ignore[arg-type]
            data_policy=data_policy,
            sections=sections,
            model_inputs_summary=summary,
        )

