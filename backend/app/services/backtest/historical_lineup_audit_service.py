"""Audit read-only formazioni ufficiali storiche e mapping giocatori (Step G2A)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.backtest.errors import raise_backtest_http
from app.models import Competition, Fixture, FixtureMissingPlayer, Team
from app.schemas.backtest_historical_lineup_audit import (
    HistoricalLineupAuditFixtureResponse,
    HistoricalLineupAuditRoundFixtureBrief,
    HistoricalLineupAuditRoundResponse,
    HistoricalLineupAuditRoundSummary,
    HistoricalLineupSideAudit,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.pit_player_rolling_stats import (
    build_mapping_summary,
    build_player_prior_stats,
    load_sportapi_missing_by_side,
    mean,
    resolve_side_lineup,
)


class HistoricalLineupAuditService:
    def _load_fixture(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
    ) -> tuple[Competition, Fixture, Team, Team, str, str]:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        fixture = db.get(Fixture, int(fixture_id))
        if fixture is None:
            raise_backtest_http(404, "fixture_not_found", f"Fixture {fixture_id} not found")

        if fixture.competition_id is None or int(fixture.competition_id) != int(competition_id):
            raise_backtest_http(
                422,
                "fixture_competition_mismatch",
                f"Fixture {fixture_id} does not belong to competition {competition_id}",
                fixture_competition_id=fixture.competition_id,
            )

        if fixture.kickoff_at is None:
            raise_backtest_http(
                422,
                "fixture_kickoff_missing",
                f"Fixture {fixture_id} has no kickoff_at",
            )

        home_team = db.get(Team, int(fixture.home_team_id))
        away_team = db.get(Team, int(fixture.away_team_id))
        home_name = home_team.name if home_team else str(fixture.home_team_id)
        away_name = away_team.name if away_team else str(fixture.away_team_id)
        return comp, fixture, home_team, away_team, home_name, away_name

    def _build_side_audit(
        self,
        db: Session,
        *,
        fixture: Fixture,
        team_id: int,
        team_name: str,
        side: str,
        missing_rows: list[FixtureMissingPlayer],
        competition_id: int,
        cutoff: datetime,
    ) -> HistoricalLineupSideAudit:
        coverage, starters_raw, bench_raw, unavailable_raw = resolve_side_lineup(
            db,
            fixture=fixture,
            team_id=int(team_id),
            side=side,
            missing_rows=missing_rows,
        )
        starters = [
            build_player_prior_stats(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in starters_raw
        ]
        bench = [
            build_player_prior_stats(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in bench_raw
        ]
        unavailable = [
            build_player_prior_stats(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in unavailable_raw
        ]
        mapping = build_mapping_summary(starters, bench, unavailable)
        return HistoricalLineupSideAudit(
            team_id=int(team_id),
            team_name=team_name,
            coverage=coverage,
            mapping=mapping,
            starters=starters,
            bench=bench,
            unavailable=unavailable,
        )

    def audit_fixture(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
    ) -> HistoricalLineupAuditFixtureResponse:
        comp, fixture, _home, _away, home_name, away_name = self._load_fixture(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
        )
        cutoff = fixture.kickoff_at
        home_missing, away_missing = load_sportapi_missing_by_side(db, int(fixture.id))

        home_audit = self._build_side_audit(
            db,
            fixture=fixture,
            team_id=int(fixture.home_team_id),
            team_name=home_name,
            side="home",
            missing_rows=home_missing,
            competition_id=int(competition_id),
            cutoff=cutoff,
        )
        away_audit = self._build_side_audit(
            db,
            fixture=fixture,
            team_id=int(fixture.away_team_id),
            team_name=away_name,
            side="away",
            missing_rows=away_missing,
            competition_id=int(competition_id),
            cutoff=cutoff,
        )

        warnings: list[str] = []
        for side_audit in (home_audit, away_audit):
            warnings.extend(side_audit.coverage.warnings)
            for player in side_audit.starters + side_audit.bench + side_audit.unavailable:
                warnings.extend(player.warnings)
        warnings = list(dict.fromkeys(warnings))

        return HistoricalLineupAuditFixtureResponse(
            competition_id=int(competition_id),
            competition_name=str(comp.name),
            fixture_id=int(fixture_id),
            round=fixture.round,
            kickoff_at=cutoff,
            cutoff_time=cutoff,
            fixture_status=str(fixture.status),
            home_team=home_name,
            away_team=away_name,
            home_team_id=int(fixture.home_team_id),
            away_team_id=int(fixture.away_team_id),
            home=home_audit,
            away=away_audit,
            warnings=warnings,
            feature_snapshot_json={
                "audit_mode": BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
                "future_mode_hint": BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
                "cutoff_time": cutoff.isoformat(),
                "db_writes": False,
                "preview_only": True,
            },
        )

    def _fixture_to_round_brief(
        self,
        audit: HistoricalLineupAuditFixtureResponse,
    ) -> HistoricalLineupAuditRoundFixtureBrief:
        home = audit.home
        away = audit.away
        ts_statuses = {home.coverage.source_timestamp_status, away.coverage.source_timestamp_status}
        if "safe" in ts_statuses:
            combined_ts = "safe"
        elif home.coverage.has_official_xi or away.coverage.has_official_xi:
            combined_ts = "missing"
        else:
            combined_ts = "missing"

        unavailable_present = (
            home.coverage.unavailable_count > 0
            or away.coverage.unavailable_count > 0
            or len(home.unavailable) > 0
            or len(away.unavailable) > 0
        )

        return HistoricalLineupAuditRoundFixtureBrief(
            fixture_id=int(audit.fixture_id),
            match=f"{audit.home_team} vs {audit.away_team}",
            round=audit.round,
            kickoff_at=audit.kickoff_at,
            home_has_official_xi=home.coverage.has_official_xi,
            away_has_official_xi=away.coverage.has_official_xi,
            home_starters_count=home.coverage.starters_count,
            away_starters_count=away.coverage.starters_count,
            home_mapping_coverage_pct=home.mapping.mapping_coverage_pct,
            away_mapping_coverage_pct=away.mapping.mapping_coverage_pct,
            home_prior_stats_coverage_pct=home.mapping.player_stats_prior_coverage_pct,
            away_prior_stats_coverage_pct=away.mapping.player_stats_prior_coverage_pct,
            unavailable_data_present=unavailable_present,
            source_timestamp_status=combined_ts,
            warnings=list(audit.warnings),
        )

    def _aggregate_round_summary(
        self,
        briefs: list[HistoricalLineupAuditRoundFixtureBrief],
    ) -> HistoricalLineupAuditRoundSummary:
        if not briefs:
            return HistoricalLineupAuditRoundSummary()

        both_xi = sum(1 for b in briefs if b.home_has_official_xi and b.away_has_official_xi)
        partial = sum(
            1
            for b in briefs
            if (b.home_has_official_xi or b.away_has_official_xi)
            and not (b.home_has_official_xi and b.away_has_official_xi)
        )
        without = sum(1 for b in briefs if not b.home_has_official_xi and not b.away_has_official_xi)

        mapping_vals: list[float] = []
        prior_vals: list[float] = []
        for b in briefs:
            for pct in (b.home_mapping_coverage_pct, b.away_mapping_coverage_pct):
                if pct is not None:
                    mapping_vals.append(float(pct))
            for pct in (b.home_prior_stats_coverage_pct, b.away_prior_stats_coverage_pct):
                if pct is not None:
                    prior_vals.append(float(pct))

        return HistoricalLineupAuditRoundSummary(
            fixtures_processed=len(briefs),
            fixtures_with_official_xi_both_teams=both_xi,
            fixtures_with_partial_lineup=partial,
            fixtures_without_lineup=without,
            avg_starters_count_home=mean([float(b.home_starters_count) for b in briefs]),
            avg_starters_count_away=mean([float(b.away_starters_count) for b in briefs]),
            avg_mapping_coverage_pct=mean(mapping_vals),
            avg_player_stats_prior_coverage_pct=mean(prior_vals),
            fixtures_with_unavailable_data=sum(1 for b in briefs if b.unavailable_data_present),
            fixtures_with_injured_data=0,
            fixtures_with_suspended_data=0,
            timestamp_safe_count=sum(1 for b in briefs if b.source_timestamp_status == "safe"),
            timestamp_missing_count=sum(1 for b in briefs if b.source_timestamp_status == "missing"),
        )

    def audit_round(
        self,
        db: Session,
        *,
        competition_id: int,
        round_number: int,
        limit: int = 20,
        offset: int = 0,
    ) -> HistoricalLineupAuditRoundResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        selection = BacktestFixtureDebugService().select_fixtures_for_lineup_audit(
            db,
            competition_id=int(competition_id),
            round_number=int(round_number),
            limit=int(limit),
            offset=int(offset),
        )

        briefs: list[HistoricalLineupAuditRoundFixtureBrief] = []
        round_warnings: list[str] = []
        injured_fixtures = suspended_fixtures = 0

        for candidate in selection.items:
            audit = self.audit_fixture(
                db,
                competition_id=int(competition_id),
                fixture_id=int(candidate.fixture_id),
            )
            brief = self._fixture_to_round_brief(audit)
            briefs.append(brief)
            round_warnings.extend(brief.warnings)
            if audit.home.coverage.injured_count > 0 or audit.away.coverage.injured_count > 0:
                injured_fixtures += 1
            if audit.home.coverage.suspended_count > 0 or audit.away.coverage.suspended_count > 0:
                suspended_fixtures += 1

        summary = self._aggregate_round_summary(briefs)
        summary.fixtures_with_injured_data = injured_fixtures
        summary.fixtures_with_suspended_data = suspended_fixtures

        return HistoricalLineupAuditRoundResponse(
            competition_id=int(competition_id),
            competition_name=str(comp.name),
            round_number=int(round_number),
            limit=int(limit),
            offset=int(offset),
            summary=summary,
            fixtures=briefs,
            warnings=list(dict.fromkeys(round_warnings)),
        )
