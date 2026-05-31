"""Helper condivisi lineup/stats giocatore point-in-time (G2A audit + G2B player layer)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import (
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
)
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.schemas.backtest_historical_lineup_audit import (
    HistoricalLineupPlayerMappingSummary,
    HistoricalLineupPlayerPriorStats,
    HistoricalLineupSideCoverage,
)
from app.services.backtest.pit_leakage import pit_strict_kickoff_before
from app.services.sportapi.sportapi_lineup_present import classify_missing_group


@dataclass
class RawPlayerRow:
    player_name: str
    provider_player_id: int | None
    api_player_id: int | None
    position: str | None
    is_starter: bool
    is_unavailable: bool = False
    absence_group: str | None = None


def round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(100.0 * float(numerator) / float(denominator), 2)


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def timestamp_audit(fetched_at: datetime | None) -> tuple[datetime | None, bool, str, list[str]]:
    warnings: list[str] = []
    if fetched_at is None:
        warnings.append("historical_official_xi_without_source_timestamp")
        return None, False, "missing", warnings
    return fetched_at, True, "safe", warnings


def load_sportapi_missing_by_side(
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


def missing_to_rows(missing_rows: list[FixtureMissingPlayer]) -> list[RawPlayerRow]:
    rows: list[RawPlayerRow] = []
    for m in missing_rows:
        grp = classify_missing_group(
            reason=m.reason,
            description=m.description,
            external_type=m.external_type,
        )
        rows.append(
            RawPlayerRow(
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


def resolve_api_football_side(
    db: Session,
    *,
    fixture_id: int,
    team_id: int,
) -> tuple[HistoricalLineupSideCoverage, list[RawPlayerRow], list[RawPlayerRow]] | None:
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

    ts, is_safe, ts_status, ts_warnings = timestamp_audit(lineup.fetched_at)
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

    def _row(lp: FixtureLineupPlayer, *, starter: bool) -> RawPlayerRow:
        apid = int(lp.api_player_id) if lp.api_player_id is not None else None
        return RawPlayerRow(
            player_name=lp.player_name or str(apid or "?"),
            provider_player_id=None,
            api_player_id=apid,
            position=lp.position,
            is_starter=starter,
        )

    starters = [_row(p, starter=True) for p in starters_raw]
    bench = [_row(p, starter=False) for p in bench_raw]
    return coverage, starters, bench


def resolve_sportapi_side(
    db: Session,
    *,
    fixture_id: int,
    side: str,
    formation: str | None,
    fetched_at: datetime | None,
    missing_rows: list[FixtureMissingPlayer],
) -> tuple[HistoricalLineupSideCoverage, list[RawPlayerRow], list[RawPlayerRow], list[RawPlayerRow]] | None:
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

    ts, is_safe, ts_status, ts_warnings = timestamp_audit(fetched_at)
    injured = suspended = 0
    unavailable_rows: list[RawPlayerRow] = []
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
        unavailable_rows.append(
            RawPlayerRow(
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

    def _row(p: FixtureProviderLineupPlayer, *, starter: bool) -> RawPlayerRow:
        return RawPlayerRow(
            player_name=p.player_name or str(p.provider_player_id),
            provider_player_id=int(p.provider_player_id),
            api_player_id=None,
            position=p.position,
            is_starter=starter,
        )

    starters = [_row(p, starter=True) for p in starters_raw]
    bench = [_row(p, starter=False) for p in bench_raw]
    return coverage, starters, bench, unavailable_rows


def resolve_side_lineup(
    db: Session,
    *,
    fixture: Fixture,
    team_id: int,
    side: str,
    missing_rows: list[FixtureMissingPlayer],
) -> tuple[HistoricalLineupSideCoverage, list[RawPlayerRow], list[RawPlayerRow], list[RawPlayerRow]]:
    api_result = resolve_api_football_side(
        db,
        fixture_id=int(fixture.id),
        team_id=int(team_id),
    )
    if api_result is not None:
        coverage, starters, bench = api_result
        unavailable = missing_to_rows(missing_rows)
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
        sportapi_result = resolve_sportapi_side(
            db,
            fixture_id=int(fixture.id),
            side=side,
            formation=formation,
            fetched_at=provider_lineup.fetched_at,
            missing_rows=missing_rows,
        )
        if sportapi_result is not None:
            return sportapi_result

    unavailable = missing_to_rows(missing_rows)
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


def resolve_player_ids(
    db: Session,
    row: RawPlayerRow,
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


def compute_prior_stats(
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
        prior_sot_per90 = round4(prior_shots_on / prior_minutes * 90.0)
        prior_shots_per90 = round4(prior_shots_total / prior_minutes * 90.0)

    prior_team_sot_share = None
    if team_sot_sum > 0:
        prior_team_sot_share = round4(player_sot_sum / team_sot_sum)

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


def build_player_prior_stats(
    db: Session,
    *,
    row: RawPlayerRow,
    competition_id: int,
    team_id: int,
    cutoff: datetime,
) -> HistoricalLineupPlayerPriorStats:
    provider_id, internal_id, map_status, map_warnings = resolve_player_ids(db, row)
    api_id = row.api_player_id
    if api_id is None and internal_id is not None:
        player = db.get(Player, int(internal_id))
        if player and player.api_player_id is not None:
            api_id = int(player.api_player_id)

    prior = compute_prior_stats(
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


def build_mapping_summary(
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
        mapping_coverage_pct=pct(starters_provider, len(starters)),
        player_stats_prior_coverage_pct=pct(starters_prior, len(starters)),
    )
