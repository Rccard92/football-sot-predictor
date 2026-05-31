"""Audit read-only indisponibili storici su storage fixture target (Step JK.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, FixtureLineup, FixtureMissingPlayer, FixtureProviderLineup, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.schemas.backtest_historical_unavailable_audit import (
    HistoricalUnavailableAuditFixtureSample,
    HistoricalUnavailableAuditPlayerSample,
    HistoricalUnavailableAuditResponse,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.pit_unavailable_parsing import (
    detect_raw_json_unavailable_keys,
    parse_unavailable_from_payload,
)
from app.services.sportapi.sportapi_lineup_present import classify_missing_group

_STORAGE_CHECKED = [
    "fixture_missing_players",
    "fixture_lineups.raw_json (injured, suspended, unavailable, missing)",
    "fixture_provider_lineups.raw_payload",
]

_SAMPLE_LIMIT = 10


@dataclass
class _SideUnavailableCounts:
    total: int = 0
    injured: int = 0
    suspended: int = 0
    source_paths: set[str] = field(default_factory=set)
    players: list[HistoricalUnavailableAuditPlayerSample] = field(default_factory=list)


@dataclass
class _FixtureUnavailableScan:
    fixture_id: int
    round: str | None
    home_team: str
    away_team: str
    home: _SideUnavailableCounts = field(default_factory=_SideUnavailableCounts)
    away: _SideUnavailableCounts = field(default_factory=_SideUnavailableCounts)
    raw_json_keys: set[str] = field(default_factory=set)

    @property
    def total_unavailable(self) -> int:
        return self.home.total + self.away.total

    @property
    def has_injured(self) -> bool:
        return self.home.injured > 0 or self.away.injured > 0

    @property
    def has_suspended(self) -> bool:
        return self.home.suspended > 0 or self.away.suspended > 0

    @property
    def source_paths(self) -> set[str]:
        return self.home.source_paths | self.away.source_paths


class HistoricalUnavailableAuditService:
    def _add_missing_players(
        self,
        scan: _FixtureUnavailableScan,
        *,
        missing_rows: list[FixtureMissingPlayer],
    ) -> None:
        for row in missing_rows:
            side = row.team_side if row.team_side in ("home", "away") else "unknown"
            if side == "unknown":
                continue
            counts = scan.home if side == "home" else scan.away
            grp = classify_missing_group(
                reason=row.reason,
                description=row.description,
                external_type=row.external_type,
            )
            counts.total += 1
            counts.source_paths.add("fixture_missing_players")
            if grp == "injured":
                counts.injured += 1
            elif grp == "suspended":
                counts.suspended += 1
            name = row.player_name or str(row.provider_player_id)
            counts.players.append(
                HistoricalUnavailableAuditPlayerSample(
                    player_name=str(name),
                    absence_group=str(grp),
                    side=side,
                ),
            )

    def _add_parsed_rows(
        self,
        scan: _FixtureUnavailableScan,
        *,
        side: str,
        rows: list,
        source_path: str,
    ) -> None:
        if not rows:
            return
        counts = scan.home if side == "home" else scan.away
        counts.source_paths.add(source_path)
        for row in rows:
            counts.total += 1
            grp = row.absence_group or "other"
            if grp == "injured":
                counts.injured += 1
            elif grp == "suspended":
                counts.suspended += 1
            counts.players.append(
                HistoricalUnavailableAuditPlayerSample(
                    player_name=str(row.player_name),
                    absence_group=str(grp),
                    side=side,
                ),
            )

    def _scan_fixture(
        self,
        db: Session,
        *,
        fixture: Fixture,
        home_name: str,
        away_name: str,
    ) -> _FixtureUnavailableScan:
        fid = int(fixture.id)
        scan = _FixtureUnavailableScan(
            fixture_id=fid,
            round=fixture.round,
            home_team=home_name,
            away_team=away_name,
        )

        missing_rows = db.scalars(
            select(FixtureMissingPlayer).where(FixtureMissingPlayer.fixture_id == fid),
        ).all()
        self._add_missing_players(scan, missing_rows=list(missing_rows))

        lineup_rows = db.scalars(
            select(FixtureLineup).where(FixtureLineup.fixture_id == fid),
        ).all()
        for lineup_row in lineup_rows:
            if lineup_row.raw_json:
                scan.raw_json_keys.update(detect_raw_json_unavailable_keys(lineup_row.raw_json))
                side = "home" if int(lineup_row.team_id) == int(fixture.home_team_id) else "away"
                parsed = parse_unavailable_from_payload(lineup_row.raw_json)
                self._add_parsed_rows(
                    scan,
                    side=side,
                    rows=parsed,
                    source_path="fixture_lineups.raw_json",
                )

        provider_row = db.scalar(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == fid,
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        if provider_row and provider_row.raw_payload:
            scan.raw_json_keys.update(detect_raw_json_unavailable_keys(provider_row.raw_payload))
            payload = provider_row.raw_payload
            for side_key, side in (("home", "home"), ("away", "away")):
                block = payload.get(side_key) if isinstance(payload, dict) else None
                if isinstance(block, dict):
                    parsed = parse_unavailable_from_payload(block)
                    self._add_parsed_rows(
                        scan,
                        side=side,
                        rows=parsed,
                        source_path="fixture_provider_lineups.raw_payload",
                    )
            if isinstance(payload, dict):
                top_parsed = parse_unavailable_from_payload(payload)
                if top_parsed:
                    self._add_parsed_rows(
                        scan,
                        side="home",
                        rows=top_parsed,
                        source_path="fixture_provider_lineups.raw_payload",
                    )

        return scan

    def _to_sample(self, scan: _FixtureUnavailableScan) -> HistoricalUnavailableAuditFixtureSample:
        players = scan.home.players + scan.away.players
        return HistoricalUnavailableAuditFixtureSample(
            fixture_id=scan.fixture_id,
            round=scan.round,
            home_team=scan.home_team,
            away_team=scan.away_team,
            home_unavailable_count=scan.home.total,
            away_unavailable_count=scan.away.total,
            home_injured_count=scan.home.injured,
            away_injured_count=scan.away.injured,
            home_suspended_count=scan.home.suspended,
            away_suspended_count=scan.away.suspended,
            source_paths=sorted(scan.source_paths),
            players=players[:20],
        )

    def audit(
        self,
        db: Session,
        *,
        competition_id: int,
        round_number: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> HistoricalUnavailableAuditResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            from app.backtest.errors import raise_backtest_http

            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        selection = BacktestFixtureDebugService().select_fixtures_for_mini_run(
            db,
            competition_id=int(competition_id),
            limit=int(limit),
            offset=int(offset),
            round_number=round_number,
        )

        scans: list[_FixtureUnavailableScan] = []
        all_source_paths: set[str] = set()
        all_raw_keys: set[str] = set()

        for candidate in selection.items:
            fixture = db.get(Fixture, int(candidate.fixture_id))
            if fixture is None:
                continue
            home = db.get(Team, int(fixture.home_team_id))
            away = db.get(Team, int(fixture.away_team_id))
            scan = self._scan_fixture(
                db,
                fixture=fixture,
                home_name=home.name if home else str(fixture.home_team_id),
                away_name=away.name if away else str(fixture.away_team_id),
            )
            scans.append(scan)
            all_source_paths.update(scan.source_paths)
            all_raw_keys.update(scan.raw_json_keys)

        fixtures_with_unavailable = sum(1 for s in scans if s.total_unavailable > 0)
        fixtures_with_injured = sum(1 for s in scans if s.has_injured)
        fixtures_with_suspended = sum(1 for s in scans if s.has_suspended)
        total_unavailable = sum(s.total_unavailable for s in scans)
        total_injured = sum(s.home.injured + s.away.injured for s in scans)
        total_suspended = sum(s.home.suspended + s.away.suspended for s in scans)

        samples = sorted(
            [s for s in scans if s.total_unavailable > 0],
            key=lambda s: s.total_unavailable,
            reverse=True,
        )[:_SAMPLE_LIMIT]

        verdict = (
            "unavailable_found_in_storage"
            if fixtures_with_unavailable > 0
            else "unavailable_not_found_in_current_storage"
        )

        return HistoricalUnavailableAuditResponse(
            competition_id=int(competition_id),
            competition_name=comp.name,
            round_number=round_number,
            limit=int(limit),
            offset=int(offset),
            fixtures_scanned=len(scans),
            fixtures_with_unavailable=fixtures_with_unavailable,
            fixtures_with_injured=fixtures_with_injured,
            fixtures_with_suspended=fixtures_with_suspended,
            total_unavailable_players=total_unavailable,
            total_injured_players=total_injured,
            total_suspended_players=total_suspended,
            sample_fixtures_with_unavailable=[self._to_sample(s) for s in samples],
            source_paths_found=sorted(all_source_paths),
            raw_json_keys_detected=sorted(all_raw_keys),
            storage_checked=list(_STORAGE_CHECKED),
            verdict=verdict,
        )
