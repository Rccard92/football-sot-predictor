"""Refresh SportAPI singola fixture: mapping + lineups (riuso logica batch turno)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService

logger = logging.getLogger(__name__)

AUTO_MAPPING_MIN_CONFIDENCE = 90.0


def has_sportapi_mapping(db: Session, fixture_id: int) -> bool:
    return (
        db.scalar(
            select(FixtureProviderMapping.id).where(
                FixtureProviderMapping.fixture_id == int(fixture_id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        is not None
    )


def ensure_sportapi_mapping(
    db: Session,
    fixture_id: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Tenta mapping AUTO_SAFE >= 90 tramite scheduled-events."""
    if not force and has_sportapi_mapping(db, fixture_id):
        return {"mapping_ok": True, "status": "existing"}

    match_svc = SportApiMatchingService()
    lineup_svc = SportApiLineupService()
    debug = match_svc.debug_match_fixture(db, int(fixture_id))
    api_calls = int(debug.get("api_calls") or 1)
    best = debug.get("best_candidate") if isinstance(debug.get("best_candidate"), dict) else None
    if best and debug.get("recommendation") == "AUTO_SAFE":
        conf = float(best.get("confidence_score") or 90)
        if conf >= AUTO_MAPPING_MIN_CONFIDENCE:
            out_map = lineup_svc.confirm_mapping(
                db,
                int(fixture_id),
                provider_event_id=int(best["provider_event_id"]),
                confidence_score=conf,
                matched_by="auto_timestamp_teams",
                raw_payload=best,
            )
            if out_map.get("status") != "error":
                return {"mapping_ok": True, "status": "created", "api_calls": api_calls}
    return {
        "mapping_ok": False,
        "status": "mapping_failed",
        "message": str(debug.get("message") or "Nessun candidato AUTO_SAFE"),
        "api_calls": api_calls,
    }


def fetch_sportapi_lineups_for_fixture(
    db: Session,
    fixture_id: int,
    *,
    skip_recent_minutes: float | None = None,
) -> dict[str, Any]:
    """Fetch e persist lineups SportAPI. skip_recent_minutes=None → sempre fetch."""
    if not has_sportapi_mapping(db, fixture_id):
        return {"status": "error", "message": "Mapping SportAPI assente"}

    if skip_recent_minutes is not None:
        from app.services.sportapi.sportapi_lineup_status import lineup_row_for_fixture
        from datetime import datetime, timezone

        lu = lineup_row_for_fixture(db, int(fixture_id))
        if lu and lu.fetched_at:
            now = datetime.now(timezone.utc)
            ft = lu.fetched_at
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=timezone.utc)
            age_min = (now - ft.astimezone(timezone.utc)).total_seconds() / 60.0
            if age_min < skip_recent_minutes:
                return {
                    "status": "skipped_recent",
                    "confirmed": bool(lu.confirmed),
                    "fetched_at": lu.fetched_at.isoformat() if lu.fetched_at else None,
                }

    lineup_svc = SportApiLineupService()
    out = lineup_svc.fetch_and_persist_lineups(db, int(fixture_id))
    return out


def refresh_fixture_sportapi_pre_match(
    db: Session,
    fixture_id: int,
    *,
    force_mapping: bool = False,
) -> dict[str, Any]:
    """Mapping (se serve) + fetch lineups per job pre-match."""
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"status": "error", "message": "Fixture non trovata", "fixture_id": fixture_id}

    home = db.get(Team, int(fx.home_team_id))
    away = db.get(Team, int(fx.away_team_id))
    match_name = f"{home.name if home else 'Casa'} – {away.name if away else 'Trasferta'}"

    row: dict[str, Any] = {
        "fixture_id": int(fixture_id),
        "match_name": match_name,
        "mapping_ok": has_sportapi_mapping(db, fixture_id),
        "lineups_ok": False,
        "confirmed": None,
        "fetched_at": None,
        "status": "ok",
        "error": None,
    }

    if not row["mapping_ok"] or force_mapping:
        map_out = ensure_sportapi_mapping(db, fixture_id, force=force_mapping)
        row["mapping_ok"] = bool(map_out.get("mapping_ok"))
        if not row["mapping_ok"]:
            row["status"] = "mapping_failed"
            row["error"] = str(map_out.get("message") or "mapping fallito")
            return row

    fetch_out = fetch_sportapi_lineups_for_fixture(db, fixture_id, skip_recent_minutes=None)
    if fetch_out.get("status") == "success":
        row["lineups_ok"] = True
        row["confirmed"] = fetch_out.get("confirmed")
        row["fetched_at"] = fetch_out.get("fetched_at")
        row["status"] = "updated"
    elif fetch_out.get("status") == "skipped_recent":
        row["lineups_ok"] = True
        row["confirmed"] = fetch_out.get("confirmed")
        row["fetched_at"] = fetch_out.get("fetched_at")
        row["status"] = "unchanged"
    else:
        row["status"] = "lineups_failed"
        row["error"] = str(fetch_out.get("message") or "fetch lineups fallito")

    return row
