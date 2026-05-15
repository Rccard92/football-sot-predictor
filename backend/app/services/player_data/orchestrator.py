"""Orchestrazione ingest Player DB (rose + statistiche partita + profili)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Fixture, FixturePlayerStat
from app.schemas.ingestion import IngestionRunRead
from app.services.api_football_client import ApiFootballClient
from app.services.ingestion_service import IngestionService
from app.services.player_sot_profile_service import PlayerSotProfileService
from app.services.player_data.squads import sync_serie_a_player_squads


def run_player_db_update(
    db: Session,
    season_year: int,
    *,
    force: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """
    1) Sincronizza rose (`players/squads`).
    2) Se `force`, elimina `fixture_player_stats` della stagione e re-ingesta da API.
    3) Altrimenti ingest standard fixture/giocatore (merge su chiavi esistenti).
    4) Ricalcola `player_sot_profiles` solo da DB.
    """
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, season_year)

    squads_summary = sync_serie_a_player_squads(db, season_year, client=client)

    if force:
        fx_ids = db.scalars(select(Fixture.id).where(Fixture.season_id == season_row.id)).all()
        if fx_ids:
            db.execute(delete(FixturePlayerStat).where(FixturePlayerStat.fixture_id.in_(fx_ids)))
        db.commit()

    stats_run = ing.ingest_serie_a_player_stats(db, season_year, run_source="player_db_fixture_stats")
    stats_payload = IngestionRunRead.model_validate(stats_run).model_dump()
    if stats_run.status == "failed":
        return {
            "squads": squads_summary,
            "fixture_player_stats_ingestion": stats_payload,
            "profiles": {
                "status": "skipped",
                "message": "Profili non ricalcolati: ingestione fixture_player_stats fallita",
            },
        }

    profiles = PlayerSotProfileService().build_for_season(db, season_year)

    return {
        "squads": squads_summary,
        "fixture_player_stats_ingestion": stats_payload,
        "profiles": profiles,
    }
