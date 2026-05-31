"""Snapshot ufficiale XI/panchina/indisponibili dalla fixture target esatta (Step J/K)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureLineup, FixtureProviderLineup
from app.models.fixture_provider_mapping import FixtureProviderMapping, PROVIDER_SPORTAPI
from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureOfficialSnapshot,
    HistoricalFixtureSideSnapshot,
    HistoricalSnapshotPlayerRow,
)
from app.services.backtest.pit_player_rolling_stats import (
    RawPlayerRow,
    load_sportapi_missing_by_side,
    resolve_side_lineup,
)
from app.services.backtest.pit_unavailable_parsing import parse_unavailable_from_payload
from app.services.sportapi.sportapi_unavailable_parser import (
    normalized_rows_to_raw_players,
    parse_sportapi_unavailable_from_lineup_payload,
)


def snapshot_row_to_raw(row: HistoricalSnapshotPlayerRow) -> RawPlayerRow:
    return RawPlayerRow(
        player_name=row.player_name,
        provider_player_id=row.provider_player_id,
        api_player_id=row.api_player_id,
        position=row.position,
        is_starter=row.is_starter,
        is_unavailable=row.is_unavailable,
        absence_group=row.absence_group,
    )


def side_starters_raw(side: HistoricalFixtureSideSnapshot) -> list[RawPlayerRow]:
    return [snapshot_row_to_raw(r) for r in side.starters]


def side_bench_raw(side: HistoricalFixtureSideSnapshot) -> list[RawPlayerRow]:
    return [snapshot_row_to_raw(r) for r in side.bench]


def side_unavailable_raw(side: HistoricalFixtureSideSnapshot) -> list[RawPlayerRow]:
    return [snapshot_row_to_raw(r) for r in side.unavailable]


def _row_to_snapshot(row: RawPlayerRow) -> HistoricalSnapshotPlayerRow:
    return HistoricalSnapshotPlayerRow(
        player_name=row.player_name,
        provider_player_id=row.provider_player_id,
        api_player_id=row.api_player_id,
        position=row.position,
        is_starter=row.is_starter,
        is_unavailable=row.is_unavailable,
        absence_group=row.absence_group,
    )


def _split_unavailable_groups(
    unavailable: list[RawPlayerRow],
) -> tuple[list[HistoricalSnapshotPlayerRow], list[HistoricalSnapshotPlayerRow], list[HistoricalSnapshotPlayerRow]]:
    injured: list[HistoricalSnapshotPlayerRow] = []
    suspended: list[HistoricalSnapshotPlayerRow] = []
    other: list[HistoricalSnapshotPlayerRow] = []
    for row in unavailable:
        snap = _row_to_snapshot(row)
        grp = (row.absence_group or "other").lower()
        if grp == "injured":
            injured.append(snap)
        elif grp == "suspended":
            suspended.append(snap)
        else:
            other.append(snap)
    all_rows = injured + suspended + other
    return all_rows, injured, suspended


class HistoricalFixtureSnapshotService:
    def get_fixture_official_snapshot(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
    ) -> HistoricalFixtureOfficialSnapshot:
        fixture = db.get(Fixture, int(fixture_id))
        if fixture is None:
            empty_side = HistoricalFixtureSideSnapshot(
                team_id=0,
                side="home",
                status="missing",
                warnings=["target_fixture_lineup_missing"],
            )
            return HistoricalFixtureOfficialSnapshot(
                fixture_id=int(fixture_id),
                competition_id=int(competition_id),
                home_team_id=0,
                away_team_id=0,
                cutoff_time=datetime.now(timezone.utc),
                home=empty_side,
                away=empty_side.model_copy(update={"side": "away"}),
                warnings=["target_fixture_lineup_missing"],
            )

        if int(fixture.competition_id) != int(competition_id):
            empty_side = HistoricalFixtureSideSnapshot(
                team_id=int(fixture.home_team_id),
                side="home",
                status="missing",
                warnings=["competition_id_mismatch"],
            )
            return HistoricalFixtureOfficialSnapshot(
                fixture_id=int(fixture_id),
                competition_id=int(competition_id),
                home_team_id=int(fixture.home_team_id),
                away_team_id=int(fixture.away_team_id),
                cutoff_time=fixture.kickoff_at,  # type: ignore[arg-type]
                home=empty_side,
                away=empty_side.model_copy(
                    update={"team_id": int(fixture.away_team_id), "side": "away"},
                ),
                warnings=["competition_id_mismatch"],
            )

        cutoff = fixture.kickoff_at
        home_missing, away_missing = load_sportapi_missing_by_side(db, int(fixture_id))
        global_warnings: list[str] = []

        def _build_side(team_id: int, side: str, missing_rows: list) -> HistoricalFixtureSideSnapshot:
            coverage, starters, bench, unavailable = resolve_side_lineup(
                db,
                fixture=fixture,
                team_id=int(team_id),
                side=side,
                missing_rows=missing_rows,
            )
            unavailable_source = "provider_missing" if unavailable else "none"

            if not unavailable:
                provider_row = db.scalar(
                    select(FixtureProviderLineup).where(
                        FixtureProviderLineup.fixture_id == int(fixture_id),
                        FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
                    ),
                )
                if provider_row and provider_row.raw_payload:
                    mapping = db.scalar(
                        select(FixtureProviderMapping).where(
                            FixtureProviderMapping.fixture_id == int(fixture_id),
                            FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                        ),
                    )
                    provider_event_id = (
                        int(provider_row.provider_event_id)
                        if provider_row.provider_event_id is not None
                        else int(mapping.provider_event_id) if mapping else 0
                    )
                    parsed_rows = parse_sportapi_unavailable_from_lineup_payload(
                        provider_row.raw_payload,
                        internal_fixture_id=int(fixture_id),
                        provider_event_id=provider_event_id,
                        home_team_id=int(fixture.home_team_id),
                        away_team_id=int(fixture.away_team_id),
                        provider_home_team_id=mapping.provider_home_team_id if mapping else None,
                        provider_away_team_id=mapping.provider_away_team_id if mapping else None,
                    )
                    side_parsed = normalized_rows_to_raw_players(parsed_rows, team_side=side)
                    if side_parsed:
                        unavailable = side_parsed
                        unavailable_source = "provider_raw_payload"

            if not unavailable and coverage.source_table == "fixture_lineups":
                lineup_row = db.scalar(
                    select(FixtureLineup).where(
                        FixtureLineup.fixture_id == int(fixture_id),
                        FixtureLineup.team_id == int(team_id),
                    ).limit(1),
                )
                if lineup_row and lineup_row.raw_json:
                    parsed = parse_unavailable_from_payload(lineup_row.raw_json)
                    if parsed:
                        unavailable = parsed
                        unavailable_source = "raw_json"

            all_unavail, injured, suspended = _split_unavailable_groups(unavailable)
            side_warnings = list(coverage.warnings)

            if not coverage.has_official_xi or not starters:
                side_warnings.append("target_fixture_lineup_missing")
                return HistoricalFixtureSideSnapshot(
                    team_id=int(team_id),
                    side=side,
                    status="missing",
                    formation=coverage.formation,
                    coverage=coverage,
                    starters=[_row_to_snapshot(r) for r in starters],
                    bench=[_row_to_snapshot(r) for r in bench],
                    unavailable=all_unavail,
                    injured=injured,
                    suspended=suspended,
                    source_table=coverage.source_table,
                    source_provider=coverage.source_provider,
                    source_timestamp_status=coverage.source_timestamp_status,
                    unavailable_source=unavailable_source,
                    warnings=side_warnings,
                )

            return HistoricalFixtureSideSnapshot(
                team_id=int(team_id),
                side=side,
                status="available",
                formation=coverage.formation,
                coverage=coverage,
                starters=[_row_to_snapshot(r) for r in starters],
                bench=[_row_to_snapshot(r) for r in bench],
                unavailable=all_unavail,
                injured=injured,
                suspended=suspended,
                source_table=coverage.source_table,
                source_provider=coverage.source_provider,
                source_timestamp_status=coverage.source_timestamp_status,
                unavailable_source=unavailable_source,
                warnings=side_warnings,
            )

        home = _build_side(int(fixture.home_team_id), "home", home_missing)
        away = _build_side(int(fixture.away_team_id), "away", away_missing)
        if home.status == "missing":
            global_warnings.append("target_fixture_lineup_missing")
        if away.status == "missing":
            global_warnings.append("target_fixture_lineup_missing")

        return HistoricalFixtureOfficialSnapshot(
            fixture_id=int(fixture_id),
            competition_id=int(competition_id),
            home_team_id=int(fixture.home_team_id),
            away_team_id=int(fixture.away_team_id),
            cutoff_time=cutoff,  # type: ignore[arg-type]
            home=home,
            away=away,
            warnings=list(dict.fromkeys(global_warnings)),
        )
