"""Audit read-only formazioni ufficiali storiche e mapping giocatori (Step G2A)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.backtest.errors import raise_backtest_http
from app.core.constants import FINISHED_STATUSES
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixtureLineupPlayer,
    FixtureMissingPlayer,
    FixturePlayerStat,
    FixtureProviderLineup,
    FixtureProviderLineupPlayer,
    FixtureTeamStat,
    Player,
    PlayerProviderMapping,
    Team,
)
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.schemas.backtest_historical_lineup_audit import (
    HistoricalLineupAuditFixtureResponse,
    HistoricalLineupAuditRoundFixtureBrief,
    HistoricalLineupAuditRoundResponse,
    HistoricalLineupAuditRoundSummary,
    HistoricalLineupPlayerMappingSummary,
    HistoricalLineupPlayerPriorStats,
    HistoricalLineupSideAudit,
    HistoricalLineupSideCoverage,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.pit_leakage import pit_strict_kickoff_before
from app.services.sportapi.sportapi_lineup_present import classify_missing_group


@dataclass
class _RawPlayerRow:
    player_name: str
    provider_player_id: int | None
    api_player_id: int | None
    position: str | None
    is_starter: bool
    is_unavailable: bool = False
    absence_group: str | None = None


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100.0 * float(numerator) / float(denominator), 2)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _timestamp_audit(fetched_at: datetime | None) -> tuple[datetime | None, bool, str, list[str]]:
    warnings: list[str] = []
    if fetched_at is None:
        warnings.append("historical_official_xi_without_source_timestamp")
        return None, False, "missing", warnings
    return fetched_at, True, "safe", warnings


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

    def _load_sportapi_missing_by_side(
        self,
        db: Session,
        fixture_id: int,
    ) -> tuple[list[FixtureMissingPlayer], list[FixtureMissingPlayer]]:
        missing = list(
            db.scalars(
                select(FixtureMissingPlayer).where(
                    FixtureMissingPlayer.fixture_id == int(fixture_id),
                    FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
                ),
            ).all(),
        )
        home = [m for m in missing if m.team_side == "home"]
        away = [m for m in missing if m.team_side == "away"]
        return home, away

    def _resolve_api_football_side(
        self,
        db: Session,
        *,
        fixture_id: int,
        team_id: int,
    ) -> tuple[HistoricalLineupSideCoverage, list[_RawPlayerRow], list[_RawPlayerRow]] | None:
        lineup = db.scalar(
            select(FixtureLineup)
            .where(
                FixtureLineup.fixture_id == int(fixture_id),
                FixtureLineup.team_id == int(team_id),
                FixtureLineup.is_available.is_(True),
            ),
        )
        if lineup is None:
            return None

        players = db.scalars(
            select(FixtureLineupPlayer)
            .where(FixtureLineupPlayer.fixture_lineup_id == int(lineup.id))
            .order_by(FixtureLineupPlayer.is_starter.desc(), FixtureLineupPlayer.number.asc().nulls_last()),
        ).all()

        starters_raw = [p for p in players if p.is_starter]
        bench_raw = [p for p in players if p.is_substitute and not p.is_starter]
        if not starters_raw and not bench_raw:
            starters_raw = [p for p in players if not p.is_substitute]
            bench_raw = [p for p in players if p.is_substitute]

        if not starters_raw:
            return None

        ts, is_safe, ts_status, ts_warnings = _timestamp_audit(lineup.fetched_at)
        coverage = HistoricalLineupSideCoverage(
            has_official_xi=True,
            starters_count=len(starters_raw),
            bench_count=len(bench_raw),
            formation=lineup.formation,
            source_table="fixture_lineups",
            source_provider="api_football",
            source_timestamp=ts,
            is_timestamp_safe=is_safe,
            source_timestamp_status=ts_status,
            warnings=list(ts_warnings),
        )

        def _row(lp: FixtureLineupPlayer, *, starter: bool) -> _RawPlayerRow:
            apid = int(lp.api_player_id) if lp.api_player_id is not None else None
            return _RawPlayerRow(
                player_name=lp.player_name or str(apid or "?"),
                provider_player_id=None,
                api_player_id=apid,
                position=lp.position,
                is_starter=starter,
            )

        starters = [_row(p, starter=True) for p in starters_raw]
        bench = [_row(p, starter=False) for p in bench_raw]
        return coverage, starters, bench

    def _resolve_sportapi_side(
        self,
        db: Session,
        *,
        fixture_id: int,
        side: str,
        formation: str | None,
        fetched_at: datetime | None,
        missing_rows: list[FixtureMissingPlayer],
    ) -> tuple[HistoricalLineupSideCoverage, list[_RawPlayerRow], list[_RawPlayerRow], list[_RawPlayerRow]] | None:
        players = list(
            db.scalars(
                select(FixtureProviderLineupPlayer)
                .where(
                    FixtureProviderLineupPlayer.fixture_id == int(fixture_id),
                    FixtureProviderLineupPlayer.provider_name == PROVIDER_SPORTAPI,
                    FixtureProviderLineupPlayer.team_side == side,
                )
                .order_by(
                    FixtureProviderLineupPlayer.is_substitute,
                    FixtureProviderLineupPlayer.jersey_number,
                ),
            ).all(),
        )
        starters_raw = [p for p in players if not p.is_substitute]
        bench_raw = [p for p in players if p.is_substitute]
        if not starters_raw:
            return None

        ts, is_safe, ts_status, ts_warnings = _timestamp_audit(fetched_at)
        injured = suspended = unavailable = 0
        unavailable_rows: list[_RawPlayerRow] = []
        for m in missing_rows:
            grp = classify_missing_group(
                reason=m.reason,
                description=m.description,
                external_type=m.external_type,
            )
            if grp == "injured":
                injured += 1
            elif grp == "suspended":
                suspended += 1
            else:
                unavailable += 1
            unavailable_rows.append(
                _RawPlayerRow(
                    player_name=m.player_name or str(m.provider_player_id),
                    provider_player_id=int(m.provider_player_id),
                    api_player_id=None,
                    position=m.position,
                    is_starter=False,
                    is_unavailable=True,
                    absence_group=grp,
                ),
            )

        coverage = HistoricalLineupSideCoverage(
            has_official_xi=True,
            starters_count=len(starters_raw),
            bench_count=len(bench_raw),
            unavailable_count=len(missing_rows),
            injured_count=injured,
            suspended_count=suspended,
            formation=formation,
            source_table="fixture_provider_lineups",
            source_provider="sportapi",
            source_timestamp=ts,
            is_timestamp_safe=is_safe,
            source_timestamp_status=ts_status,
            warnings=list(ts_warnings),
        )

        def _row(p: FixtureProviderLineupPlayer, *, starter: bool) -> _RawPlayerRow:
            return _RawPlayerRow(
                player_name=p.player_name or str(p.provider_player_id),
                provider_player_id=int(p.provider_player_id),
                api_player_id=None,
                position=p.position,
                is_starter=starter,
            )

        starters = [_row(p, starter=True) for p in starters_raw]
        bench = [_row(p, starter=False) for p in bench_raw]
        return coverage, starters, bench, unavailable_rows

    def _resolve_side_lineup(
        self,
        db: Session,
        *,
        fixture: Fixture,
        team_id: int,
        side: str,
        missing_rows: list[FixtureMissingPlayer],
    ) -> tuple[HistoricalLineupSideCoverage, list[_RawPlayerRow], list[_RawPlayerRow], list[_RawPlayerRow]]:
        api_result = self._resolve_api_football_side(
            db,
            fixture_id=int(fixture.id),
            team_id=int(team_id),
        )
        if api_result is not None:
            coverage, starters, bench = api_result
            unavailable = self._missing_to_rows(missing_rows)
            coverage.unavailable_count = len(unavailable)
            coverage.injured_count = sum(1 for u in unavailable if u.absence_group == "injured")
            coverage.suspended_count = sum(1 for u in unavailable if u.absence_group == "suspended")
            return coverage, starters, bench, unavailable

        provider_lineup = db.scalar(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == int(fixture.id),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
                FixtureProviderLineup.confirmed.is_(True),
            ),
        )
        if provider_lineup is not None:
            formation = provider_lineup.home_formation if side == "home" else provider_lineup.away_formation
            sportapi_result = self._resolve_sportapi_side(
                db,
                fixture_id=int(fixture.id),
                side=side,
                formation=formation,
                fetched_at=provider_lineup.fetched_at,
                missing_rows=missing_rows,
            )
            if sportapi_result is not None:
                return sportapi_result

        unavailable = self._missing_to_rows(missing_rows)
        return (
            HistoricalLineupSideCoverage(
                unavailable_count=len(unavailable),
                injured_count=sum(1 for u in unavailable if u.absence_group == "injured"),
                suspended_count=sum(1 for u in unavailable if u.absence_group == "suspended"),
            ),
            [],
            [],
            unavailable,
        )

    def _missing_to_rows(self, missing_rows: list[FixtureMissingPlayer]) -> list[_RawPlayerRow]:
        rows: list[_RawPlayerRow] = []
        for m in missing_rows:
            grp = classify_missing_group(
                reason=m.reason,
                description=m.description,
                external_type=m.external_type,
            )
            rows.append(
                _RawPlayerRow(
                    player_name=m.player_name or str(m.provider_player_id),
                    provider_player_id=int(m.provider_player_id),
                    api_player_id=None,
                    position=m.position,
                    is_starter=False,
                    is_unavailable=True,
                    absence_group=grp,
                ),
            )
        return rows

    def _resolve_player_ids(
        self,
        db: Session,
        row: _RawPlayerRow,
    ) -> tuple[int | None, int | None, str, list[str]]:
        warnings: list[str] = []
        api_player_id = row.api_player_id
        internal_id: int | None = None
        status = "no_provider_id"

        if row.provider_player_id is None and api_player_id is None:
            return None, None, "no_provider_id", warnings

        if api_player_id is None and row.provider_player_id is not None:
            mappings = db.scalars(
                select(PlayerProviderMapping).where(
                    PlayerProviderMapping.sportapi_player_id == int(row.provider_player_id),
                ),
            ).all()
            if len(mappings) > 1:
                status = "ambiguous"
                warnings.append("ambiguous_player_provider_mapping")
            elif len(mappings) == 1 and mappings[0].api_sports_player_id is not None:
                api_player_id = int(mappings[0].api_sports_player_id)
                status = "matched"
            else:
                return int(row.provider_player_id), None, "no_internal_id", warnings

        if api_player_id is not None:
            players = db.scalars(
                select(Player).where(Player.api_player_id == int(api_player_id)),
            ).all()
            if len(players) > 1:
                status = "ambiguous"
                warnings.append("ambiguous_internal_player_id")
            elif len(players) == 1:
                internal_id = int(players[0].id)
                if status != "ambiguous":
                    status = "matched"
            elif status != "ambiguous":
                status = "no_internal_id"

        return row.provider_player_id, internal_id, status, warnings

    def _compute_prior_stats(
        self,
        db: Session,
        *,
        competition_id: int,
        team_id: int,
        cutoff: datetime,
        api_player_id: int | None,
        internal_player_id: int | None,
    ) -> dict[str, Any]:
        if api_player_id is None and internal_player_id is None:
            return {
                "prior_minutes": 0,
                "prior_shots_total": 0,
                "prior_shots_on": 0,
                "prior_matches_count": 0,
                "prior_sot_per90": None,
                "prior_shots_per90": None,
                "prior_team_sot_share": None,
                "latest_player_stat_fixture_used_at": None,
            }

        prior_fixtures = db.scalars(
            select(Fixture).where(
                Fixture.competition_id == int(competition_id),
                Fixture.status.in_(FINISHED_STATUSES),
                Fixture.kickoff_at < cutoff,
                or_(Fixture.home_team_id == int(team_id), Fixture.away_team_id == int(team_id)),
            ),
        ).all()
        prior_ids = [int(f.id) for f in prior_fixtures if f.kickoff_at and pit_strict_kickoff_before(f.kickoff_at, cutoff)]
        if not prior_ids:
            return {
                "prior_minutes": 0,
                "prior_shots_total": 0,
                "prior_shots_on": 0,
                "prior_matches_count": 0,
                "prior_sot_per90": None,
                "prior_shots_per90": None,
                "prior_team_sot_share": None,
                "latest_player_stat_fixture_used_at": None,
            }

        stat_clauses = [FixturePlayerStat.fixture_id.in_(prior_ids), FixturePlayerStat.team_id == int(team_id)]
        if internal_player_id is not None:
            stat_clauses.append(FixturePlayerStat.player_id == int(internal_player_id))
        elif api_player_id is not None:
            stat_clauses.append(FixturePlayerStat.api_player_id == int(api_player_id))

        stats = db.scalars(select(FixturePlayerStat).where(*stat_clauses)).all()
        kickoff_by_fx = {int(f.id): f.kickoff_at for f in prior_fixtures if f.kickoff_at}

        prior_minutes = prior_shots_total = prior_shots_on = 0
        prior_matches = 0
        player_sot_sum = 0
        team_sot_sum = 0
        latest_kickoff: datetime | None = None

        for st in stats:
            fx_id = int(st.fixture_id)
            fx_kick = kickoff_by_fx.get(fx_id)
            if fx_kick is None or not pit_strict_kickoff_before(fx_kick, cutoff):
                continue
            prior_matches += 1
            if st.minutes is not None:
                prior_minutes += int(st.minutes)
            if st.shots_total is not None:
                prior_shots_total += int(st.shots_total)
            if st.shots_on_target is not None:
                prior_shots_on += int(st.shots_on_target)
                player_sot_sum += int(st.shots_on_target)
            team_st = db.scalar(
                select(FixtureTeamStat).where(
                    FixtureTeamStat.fixture_id == fx_id,
                    FixtureTeamStat.team_id == int(team_id),
                ),
            )
            if team_st and team_st.shots_on_target is not None:
                team_sot_sum += int(team_st.shots_on_target)
            if fx_kick and (latest_kickoff is None or fx_kick > latest_kickoff):
                latest_kickoff = fx_kick

        prior_sot_per90 = None
        prior_shots_per90 = None
        if prior_minutes > 0:
            prior_sot_per90 = _round4(prior_shots_on / prior_minutes * 90.0)
            prior_shots_per90 = _round4(prior_shots_total / prior_minutes * 90.0)

        prior_team_sot_share = None
        if team_sot_sum > 0:
            prior_team_sot_share = _round4(player_sot_sum / team_sot_sum)

        return {
            "prior_minutes": prior_minutes,
            "prior_shots_total": prior_shots_total,
            "prior_shots_on": prior_shots_on,
            "prior_matches_count": prior_matches,
            "prior_sot_per90": prior_sot_per90,
            "prior_shots_per90": prior_shots_per90,
            "prior_team_sot_share": prior_team_sot_share,
            "latest_player_stat_fixture_used_at": latest_kickoff,
        }

    def _build_player_audit(
        self,
        db: Session,
        *,
        row: _RawPlayerRow,
        competition_id: int,
        team_id: int,
        cutoff: datetime,
    ) -> HistoricalLineupPlayerPriorStats:
        provider_id, internal_id, map_status, map_warnings = self._resolve_player_ids(db, row)
        api_id = row.api_player_id
        if api_id is None and internal_id is not None:
            player = db.get(Player, int(internal_id))
            if player and player.api_player_id is not None:
                api_id = int(player.api_player_id)

        prior = self._compute_prior_stats(
            db,
            competition_id=int(competition_id),
            team_id=int(team_id),
            cutoff=cutoff,
            api_player_id=api_id,
            internal_player_id=internal_id,
        )

        warnings = list(map_warnings)
        final_status = map_status
        if map_status in ("matched", "ambiguous") and prior["prior_matches_count"] == 0:
            final_status = "no_prior_stats"
        elif map_status == "matched" and prior["prior_matches_count"] > 0:
            final_status = "matched"

        latest = prior["latest_player_stat_fixture_used_at"]
        if latest is not None and latest >= cutoff:
            warnings.append("possible_player_stats_leakage")

        return HistoricalLineupPlayerPriorStats(
            player_name=row.player_name,
            provider_player_id=provider_id,
            internal_player_id=internal_id,
            api_player_id=api_id,
            role=row.position,
            is_starter=row.is_starter and not row.is_unavailable,
            prior_minutes=int(prior["prior_minutes"]),
            prior_shots_total=int(prior["prior_shots_total"]),
            prior_shots_on=int(prior["prior_shots_on"]),
            prior_sot_per90=prior["prior_sot_per90"],
            prior_shots_per90=prior["prior_shots_per90"],
            prior_team_sot_share=prior["prior_team_sot_share"],
            prior_matches_count=int(prior["prior_matches_count"]),
            latest_player_stat_fixture_used_at=latest,
            mapping_status=final_status,
            warnings=warnings,
        )

    def _build_mapping_summary(
        self,
        starters: list[HistoricalLineupPlayerPriorStats],
        bench: list[HistoricalLineupPlayerPriorStats],
        unavailable: list[HistoricalLineupPlayerPriorStats],
    ) -> HistoricalLineupPlayerMappingSummary:
        def _has_provider(p: HistoricalLineupPlayerPriorStats) -> bool:
            return p.provider_player_id is not None or p.api_player_id is not None

        starters_provider = sum(1 for p in starters if _has_provider(p))
        starters_internal = sum(1 for p in starters if p.internal_player_id is not None)
        starters_prior = sum(1 for p in starters if p.prior_matches_count > 0)
        starters_missing_prior = sum(
            1 for p in starters if p.internal_player_id is not None and p.prior_matches_count == 0
        )

        return HistoricalLineupPlayerMappingSummary(
            starters_with_provider_player_id=starters_provider,
            starters_with_internal_player_id=starters_internal,
            starters_matched_to_fixture_player_stats_prior=starters_prior,
            starters_missing_prior_stats=starters_missing_prior,
            bench_with_provider_player_id=sum(1 for p in bench if _has_provider(p)),
            unavailable_with_provider_player_id=sum(1 for p in unavailable if _has_provider(p)),
            mapping_coverage_pct=_pct(starters_provider, len(starters)),
            player_stats_prior_coverage_pct=_pct(starters_prior, len(starters)),
        )

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
        coverage, starters_raw, bench_raw, unavailable_raw = self._resolve_side_lineup(
            db,
            fixture=fixture,
            team_id=int(team_id),
            side=side,
            missing_rows=missing_rows,
        )
        starters = [
            self._build_player_audit(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in starters_raw
        ]
        bench = [
            self._build_player_audit(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in bench_raw
        ]
        unavailable = [
            self._build_player_audit(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff,
            )
            for r in unavailable_raw
        ]
        mapping = self._build_mapping_summary(starters, bench, unavailable)
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
        home_missing, away_missing = self._load_sportapi_missing_by_side(db, int(fixture.id))

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
            avg_starters_count_home=_mean([float(b.home_starters_count) for b in briefs]),
            avg_starters_count_away=_mean([float(b.away_starters_count) for b in briefs]),
            avg_mapping_coverage_pct=_mean(mapping_vals),
            avg_player_stats_prior_coverage_pct=_mean(prior_vals),
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
