"""Persistenza indisponibili SportAPI in fixture_missing_players (Step K.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.fixture_missing_player import FixtureMissingPlayer
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI
from app.services.sportapi.sportapi_unavailable_parser import NormalizedUnavailableRow


def _parse_expected_end(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(val, str) and val.strip():
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _payload_with_meta(row: NormalizedUnavailableRow) -> dict[str, Any]:
    payload = dict(row.raw_json)
    payload["_source_path"] = row.source_path
    payload["_normalized_status"] = row.status
    payload["_source_fixture_id"] = int(row.source_fixture_id)
    return payload


class SportApiUnavailablePersistService:
    def persist_rows(
        self,
        db: Session,
        *,
        rows: list[NormalizedUnavailableRow],
        fixture_id: int,
        competition_id: int | None,
        provider_lineup_id: int | None,
        dry_run: bool = False,
        force_refresh: bool = True,
    ) -> dict[str, Any]:
        fid = int(fixture_id)
        persistable = [r for r in rows if r.persistable and r.provider_player_id is not None]
        skipped = len(rows) - len(persistable)

        if dry_run:
            return {
                "would_write_count": len(persistable),
                "skipped_missing_provider_player_id": skipped,
                "written_count": 0,
            }

        if force_refresh:
            db.execute(
                delete(FixtureMissingPlayer).where(
                    FixtureMissingPlayer.fixture_id == fid,
                    FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
                ),
            )

        written = 0
        for row in persistable:
            miss_row = FixtureMissingPlayer(
                fixture_id=fid,
                provider_lineup_id=provider_lineup_id,
                provider_name=PROVIDER_SPORTAPI,
                provider_player_id=int(row.provider_player_id),  # type: ignore[arg-type]
                provider_team_id=row.provider_team_id,
                team_side=row.team_side,
                player_name=row.player_name[:255],
                position=row.position,
                jersey_number=row.jersey_number,
                reason=row.reason,
                description=row.description,
                external_type=row.external_type or row.status,
                expected_end_date=_parse_expected_end(row.expected_end_date),
                raw_payload=_payload_with_meta(row),
            )
            if competition_id is not None:
                miss_row.competition_id = int(competition_id)
            db.add(miss_row)
            written += 1

        return {
            "would_write_count": len(persistable),
            "skipped_missing_provider_player_id": skipped,
            "written_count": written,
        }
