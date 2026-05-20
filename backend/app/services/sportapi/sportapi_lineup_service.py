"""
Persistenza lineups/missingPlayers SportAPI — audit/debug only.

SportAPI lineups and missingPlayers are currently stored for audit/debug only and are
not used by the prediction model when USE_SPORTAPI_LINEUPS_IN_MODEL=false.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.fixture_missing_player import FixtureMissingPlayer
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.models.fixture_provider_lineup import FixtureProviderLineup
from app.models.fixture_provider_lineup_player import FixtureProviderLineupPlayer
from app.services.sportapi.sportapi_client import SportApiClient, SportApiDisabledError, SportApiError
from app.services.sportapi.sportapi_payload import (
    event_team_ids,
    event_tournament_info,
    lineups_block,
    missing_from_side,
    player_display_name,
    player_id_from_row,
    players_from_side,
    side_block,
)

logger = logging.getLogger(__name__)


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


class SportApiLineupService:
    def __init__(self, client: SportApiClient | None = None) -> None:
        self._client = client or SportApiClient()

    def confirm_mapping(
        self,
        db: Session,
        fixture_id: int,
        *,
        provider_event_id: int,
        confidence_score: float | None,
        matched_by: str | None,
        raw_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        row = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fixture_id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        payload = raw_payload or {}
        hi, ai = None, None
        if isinstance(payload, dict):
            hi, ai = event_team_ids(payload)
        info = event_tournament_info(payload) if isinstance(payload, dict) else {}

        match_date = None
        if isinstance(payload, dict):
            ts = payload.get("startTimestamp")
            if ts is not None:
                try:
                    match_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                except (OSError, ValueError):
                    pass

        if row is None:
            row = FixtureProviderMapping(
                fixture_id=int(fixture_id),
                provider_name=PROVIDER_SPORTAPI,
                provider_event_id=int(provider_event_id),
            )
            db.add(row)

        row.provider_event_id = int(provider_event_id)
        row.confidence_score = float(confidence_score) if confidence_score is not None else None
        row.matched_by = matched_by
        row.raw_payload = payload if isinstance(payload, dict) else None
        row.provider_league_id = _int_or_none(info.get("tournament_id"))
        row.provider_unique_tournament_id = _int_or_none(info.get("unique_tournament_id"))
        row.provider_season_id = _int_or_none(info.get("season_id"))
        row.provider_home_team_id = hi
        row.provider_away_team_id = ai
        row.match_date = match_date

        db.commit()
        db.refresh(row)
        return {
            "status": "success",
            "fixture_id": int(fixture_id),
            "provider_event_id": int(row.provider_event_id),
            "confidence_score": row.confidence_score,
            "matched_by": row.matched_by,
        }

    def fetch_and_persist_lineups(self, db: Session, fixture_id: int) -> dict[str, Any]:
        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fixture_id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        if mapping is None:
            return {
                "status": "error",
                "message": "Mapping SportAPI non trovato. Conferma il mapping prima del fetch lineups.",
                "fixture_id": int(fixture_id),
            }

        event_id = int(mapping.provider_event_id)
        try:
            raw = self._client.get_lineups(event_id)
        except SportApiDisabledError as exc:
            return {"status": "disabled", "message": str(exc), "fixture_id": int(fixture_id)}
        except SportApiError as exc:
            logger.warning("sportapi lineups fetch failed fixture=%s: %s", fixture_id, exc)
            return {"status": "error", "message": str(exc), "fixture_id": int(fixture_id)}

        lineups = lineups_block(raw)
        confirmed = bool(lineups.get("confirmed", False))
        home_side = side_block(lineups, "home")
        away_side = side_block(lineups, "away")
        home_formation = home_side.get("formation")
        away_formation = away_side.get("formation")
        if home_formation is not None:
            home_formation = str(home_formation)[:32]
        if away_formation is not None:
            away_formation = str(away_formation)[:32]

        now = datetime.now(timezone.utc)
        lineup_row = db.scalar(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == int(fixture_id),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        if lineup_row is None:
            lineup_row = FixtureProviderLineup(
                fixture_id=int(fixture_id),
                provider_name=PROVIDER_SPORTAPI,
                provider_event_id=event_id,
            )
            db.add(lineup_row)

        lineup_row.provider_event_id = event_id
        lineup_row.confirmed = confirmed
        lineup_row.home_formation = home_formation
        lineup_row.away_formation = away_formation
        lineup_row.fetched_at = now
        lineup_row.raw_payload = raw if isinstance(raw, dict) else {"data": raw}
        db.flush()

        db.execute(
            delete(FixtureProviderLineupPlayer).where(
                FixtureProviderLineupPlayer.fixture_id == int(fixture_id),
                FixtureProviderLineupPlayer.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        db.execute(
            delete(FixtureMissingPlayer).where(
                FixtureMissingPlayer.fixture_id == int(fixture_id),
                FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
            ),
        )

        n_players = 0
        n_missing = 0
        for side_key, side_data, team_id in (
            ("home", home_side, mapping.provider_home_team_id),
            ("away", away_side, mapping.provider_away_team_id),
        ):
            for p in players_from_side(side_data):
                pid = player_id_from_row(p)
                if pid is None:
                    continue
                substitute = bool(p.get("substitute") or p.get("isSubstitute"))
                db.add(
                    FixtureProviderLineupPlayer(
                        fixture_id=int(fixture_id),
                        provider_lineup_id=int(lineup_row.id),
                        provider_name=PROVIDER_SPORTAPI,
                        provider_player_id=pid,
                        provider_team_id=_int_or_none(team_id),
                        team_side=side_key,
                        player_name=player_display_name(p)[:255],
                        short_name=str(p.get("shortName") or "")[:128] or None,
                        position=str(p.get("position") or p.get("pos") or "")[:32] or None,
                        jersey_number=_int_or_none(p.get("jerseyNumber") or p.get("shirtNumber")),
                        is_substitute=substitute,
                        avg_rating=_float_or_none(p.get("avgRating") or p.get("rating")),
                        raw_payload=p,
                    ),
                )
                n_players += 1
            for m in missing_from_side(side_data):
                pid = player_id_from_row(m)
                if pid is None:
                    pid = _int_or_none(m.get("id"))
                if pid is None:
                    continue
                db.add(
                    FixtureMissingPlayer(
                        fixture_id=int(fixture_id),
                        provider_lineup_id=int(lineup_row.id),
                        provider_name=PROVIDER_SPORTAPI,
                        provider_player_id=pid,
                        provider_team_id=_int_or_none(team_id),
                        team_side=side_key,
                        player_name=player_display_name(m)[:255],
                        position=str(m.get("position") or "")[:32] or None,
                        jersey_number=_int_or_none(m.get("jerseyNumber")),
                        reason=str(m.get("reason") or m.get("type") or "")[:64] or None,
                        description=str(m.get("description") or "")[:512] or None,
                        external_type=str(m.get("externalType") or m.get("external_type") or "")[:64] or None,
                        expected_end_date=_parse_expected_end(
                            m.get("expectedEndDate") or m.get("expected_end_date"),
                        ),
                        raw_payload=m,
                    ),
                )
                n_missing += 1

        db.commit()
        return {
            "status": "success",
            "fixture_id": int(fixture_id),
            "provider_event_id": event_id,
            "confirmed": confirmed,
            "players_saved": n_players,
            "missing_players_saved": n_missing,
            "fetched_at": now.isoformat(),
            "note": "Dati salvati per audit/debug; non usati nel modello predittivo.",
        }

    def get_stored_lineups(
        self,
        db: Session,
        fixture_id: int,
        *,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fixture_id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        lineup = db.scalar(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == int(fixture_id),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        players = list(
            db.scalars(
                select(FixtureProviderLineupPlayer)
                .where(
                    FixtureProviderLineupPlayer.fixture_id == int(fixture_id),
                    FixtureProviderLineupPlayer.provider_name == PROVIDER_SPORTAPI,
                )
                .order_by(
                    FixtureProviderLineupPlayer.team_side,
                    FixtureProviderLineupPlayer.is_substitute,
                    FixtureProviderLineupPlayer.jersey_number,
                ),
            ).all(),
        )
        missing = list(
            db.scalars(
                select(FixtureMissingPlayer).where(
                    FixtureMissingPlayer.fixture_id == int(fixture_id),
                    FixtureMissingPlayer.provider_name == PROVIDER_SPORTAPI,
                ),
            ).all(),
        )

        def _pl_row(p: FixtureProviderLineupPlayer) -> dict[str, Any]:
            return {
                "provider_player_id": p.provider_player_id,
                "player_name": p.player_name,
                "short_name": p.short_name,
                "position": p.position,
                "jersey_number": p.jersey_number,
                "is_substitute": p.is_substitute,
                "avg_rating": p.avg_rating,
            }

        def _miss_row(m: FixtureMissingPlayer) -> dict[str, Any]:
            return {
                "provider_player_id": m.provider_player_id,
                "player_name": m.player_name,
                "position": m.position,
                "jersey_number": m.jersey_number,
                "reason": m.reason,
                "description": m.description,
                "external_type": m.external_type,
                "expected_end_date": m.expected_end_date.isoformat() if m.expected_end_date else None,
            }

        home_players = [_pl_row(p) for p in players if p.team_side == "home" and not p.is_substitute]
        away_players = [_pl_row(p) for p in players if p.team_side == "away" and not p.is_substitute]
        home_subs = [_pl_row(p) for p in players if p.team_side == "home" and p.is_substitute]
        away_subs = [_pl_row(p) for p in players if p.team_side == "away" and p.is_substitute]
        home_missing = [_miss_row(m) for m in missing if m.team_side == "home"]
        away_missing = [_miss_row(m) for m in missing if m.team_side == "away"]

        out: dict[str, Any] = {
            "status": "ok" if mapping else "not_found",
            "fixture_id": int(fixture_id),
            "mapping": None,
            "confirmed": lineup.confirmed if lineup else None,
            "home_formation": lineup.home_formation if lineup else None,
            "away_formation": lineup.away_formation if lineup else None,
            "fetched_at": lineup.fetched_at.isoformat() if lineup and lineup.fetched_at else None,
            "home": {"players": home_players, "substitutes": home_subs, "missing_players": home_missing},
            "away": {"players": away_players, "substitutes": away_subs, "missing_players": away_missing},
            "model_usage": {
                "used_in_prediction": False,
                "note": "Dati non usati nel modello",
            },
        }
        if mapping:
            out["mapping"] = {
                "provider_event_id": mapping.provider_event_id,
                "confidence_score": mapping.confidence_score,
                "matched_by": mapping.matched_by,
            }
        if include_raw and lineup and lineup.raw_payload:
            out["raw_payload"] = lineup.raw_payload
        return out


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
