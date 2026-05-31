"""Debug live unavailable SportAPI per fixture target (Step K.2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, FixtureProviderLineup
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.sportapi_unavailable_debug import (
    SportApiUnavailableDebugResponse,
    SportApiUnavailablePlayerSample,
)
from app.services.backtest.pit_unavailable_parsing import detect_raw_json_unavailable_keys
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_fixture_resolve import FIXTURE_NOT_FOUND_MSG, resolve_fixture_or_error
from app.services.sportapi.sportapi_unavailable_parser import (
    collect_detected_paths,
    parse_sportapi_unavailable_from_lineup_payload,
)
from app.services.sportapi.sportapi_unavailable_persist_service import SportApiUnavailablePersistService


class SportApiUnavailableDebugService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def debug_fixture(
        self,
        db: Session,
        *,
        fixture_id: int,
        competition_id: int,
        dry_run: bool = True,
        force_refresh: bool = False,
    ) -> SportApiUnavailableDebugResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiUnavailableDebugResponse(
                status="error",
                competition_id=int(competition_id),
                internal_fixture_id=int(fixture_id),
                source_fixture_id=int(fixture_id),
                mapping_status="competition_not_found",
                warnings=[f"Competition {competition_id} not found"],
            )

        fx, err = resolve_fixture_or_error(db, int(fixture_id))
        if fx is None:
            return SportApiUnavailableDebugResponse(
                status="error",
                competition_id=int(competition_id),
                internal_fixture_id=int(fixture_id),
                source_fixture_id=int(fixture_id),
                mapping_status="fixture_not_found",
                warnings=[str((err or {}).get("message") or FIXTURE_NOT_FOUND_MSG)],
            )

        internal_id = int(fx.id)
        if int(fx.competition_id or 0) != int(competition_id):
            return SportApiUnavailableDebugResponse(
                status="error",
                competition_id=int(competition_id),
                internal_fixture_id=internal_id,
                source_fixture_id=internal_id,
                mapping_status="competition_mismatch",
                warnings=[f"Fixture {internal_id} non appartiene a competition {competition_id}"],
            )

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == internal_id,
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        if mapping is None:
            return SportApiUnavailableDebugResponse(
                status="error",
                competition_id=int(competition_id),
                internal_fixture_id=internal_id,
                source_fixture_id=internal_id,
                mapping_status="mapping_missing",
                warnings=["Mapping SportAPI non trovato per la fixture"],
            )

        provider_event_id = int(mapping.provider_event_id)
        data_source = "cached"
        payload: dict | None = None

        lineup_row = db.scalar(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == internal_id,
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        )

        if force_refresh or lineup_row is None or not lineup_row.raw_payload:
            try:
                raw = self._client.get_lineups(provider_event_id)
                payload = raw if isinstance(raw, dict) else {"data": raw}
                data_source = "live"
            except SportApiDisabledError as exc:
                return SportApiUnavailableDebugResponse(
                    status="disabled",
                    competition_id=int(competition_id),
                    internal_fixture_id=internal_id,
                    provider_fixture_id=provider_event_id,
                    source_fixture_id=internal_id,
                    mapping_status="ok",
                    warnings=[str(exc)],
                )
            except SportApiError as exc:
                return SportApiUnavailableDebugResponse(
                    status="error",
                    competition_id=int(competition_id),
                    internal_fixture_id=internal_id,
                    provider_fixture_id=provider_event_id,
                    source_fixture_id=internal_id,
                    mapping_status="ok",
                    warnings=[str(exc)],
                )
        else:
            payload = lineup_row.raw_payload

        rows = parse_sportapi_unavailable_from_lineup_payload(
            payload,
            internal_fixture_id=internal_id,
            provider_event_id=provider_event_id,
            home_team_id=int(fx.home_team_id),
            away_team_id=int(fx.away_team_id),
            provider_home_team_id=mapping.provider_home_team_id,
            provider_away_team_id=mapping.provider_away_team_id,
        )

        home_count = sum(1 for r in rows if r.team_side == "home")
        away_count = sum(1 for r in rows if r.team_side == "away")
        raw_keys = detect_raw_json_unavailable_keys(payload) if payload else []

        persist_result = SportApiUnavailablePersistService().persist_rows(
            db,
            rows=rows,
            fixture_id=internal_id,
            competition_id=int(competition_id),
            provider_lineup_id=int(lineup_row.id) if lineup_row else None,
            dry_run=dry_run,
            force_refresh=False,
        )

        samples = [
            SportApiUnavailablePlayerSample(
                player_name=r.player_name,
                team_side=r.team_side,
                status=r.status,
                provider_player_id=r.provider_player_id,
                source_path=r.source_path,
                persistable=r.persistable,
            )
            for r in rows[:20]
        ]

        return SportApiUnavailableDebugResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            internal_fixture_id=internal_id,
            provider_fixture_id=provider_event_id,
            source_fixture_id=internal_id,
            mapping_status="ok",
            data_source=data_source,
            home_unavailable_count=home_count,
            away_unavailable_count=away_count,
            total_unavailable_found=len(rows),
            detected_paths=collect_detected_paths(rows),
            raw_json_keys_detected=raw_keys,
            sample_unavailable_players=samples,
            would_write_count=int(persist_result.get("would_write_count") or 0),
            skipped_missing_provider_player_id=int(
                persist_result.get("skipped_missing_provider_player_id") or 0,
            ),
        )
