"""Persistenza indisponibili SportAPI in fixture_missing_players (Step K.2/K.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
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
                "skipped_duplicate_count": 0,
            }

        if force_refresh:
            db.execute(
                delete(FixtureMissingPlayer).where(
                    FixtureMissingPlayer.fixture_id == fid,
                    FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
                ),
            )

        existing_rows = list(
            db.scalars(
                select(FixtureMissingPlayer).where(
                    FixtureMissingPlayer.fixture_id == fid,
                    FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
                ),
            ).all(),
        )
        existing_by_key: dict[tuple[int, str, int], FixtureMissingPlayer] = {}
        for ex in existing_rows:
            existing_by_key[(int(ex.fixture_id), str(ex.team_side), int(ex.provider_player_id))] = ex

        written = 0
        skipped_duplicate = 0
        for row in persistable:
            payload = _payload_with_meta(row)
            key = (fid, row.team_side, int(row.provider_player_id))  # type: ignore[arg-type]
            ex = existing_by_key.get(key)
            if ex is not None and not force_refresh:
                ex_status = str(ex.external_type or ex.reason or "")
                ex_path = ""
                if isinstance(ex.raw_payload, dict):
                    ex_path = str(ex.raw_payload.get("_source_path") or "")
                if ex_status == row.status and ex_path == row.source_path:
                    skipped_duplicate += 1
                    continue
                ex.player_name = row.player_name[:255]
                ex.position = row.position
                ex.jersey_number = row.jersey_number
                ex.reason = row.reason
                ex.description = row.description
                ex.external_type = row.external_type or row.status
                ex.expected_end_date = _parse_expected_end(row.expected_end_date)
                ex.raw_payload = payload
                if provider_lineup_id is not None:
                    ex.provider_lineup_id = int(provider_lineup_id)
                if competition_id is not None:
                    ex.competition_id = int(competition_id)
                written += 1
                continue

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
                raw_payload=payload,
            )
            if competition_id is not None:
                miss_row.competition_id = int(competition_id)
            db.add(miss_row)
            existing_by_key[key] = miss_row
            written += 1

        return {
            "would_write_count": len(persistable),
            "skipped_missing_provider_player_id": skipped,
            "written_count": written,
            "skipped_duplicate_count": skipped_duplicate,
        }
