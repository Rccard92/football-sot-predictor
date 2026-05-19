"""Log e lettura ultimo run availability-upcoming."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestionRun
from app.services.ingestion_service import IngestionService

RUN_SOURCE = "serie_a_availability_upcoming"


def persist_availability_upcoming_run(
    db: Session,
    season_year: int,
    summary: dict[str, Any],
) -> IngestionRun | None:
    """Salva summary in ingestion_runs.meta per debug audit."""
    status = str(summary.get("status") or "unknown")
    success = status in ("success", "partial_success")
    ing = IngestionService()
    run = ing._begin_run(db, RUN_SOURCE, meta={"season": int(season_year)})
    records = int(summary.get("records_saved") or 0) + int(summary.get("records_updated") or 0)
    ing._finish_run(
        db,
        run,
        success=success,
        records_processed=records,
        error=None if success else str(summary.get("message") or "")[:500] or None,
        meta_merge=summary,
    )
    return run


def get_last_availability_upcoming_run(db: Session, season_year: int) -> dict[str, Any] | None:
    row = db.scalar(
        select(IngestionRun)
        .where(
            IngestionRun.source == RUN_SOURCE,
        )
        .order_by(IngestionRun.completed_at.desc().nullslast(), IngestionRun.id.desc())
        .limit(1),
    )
    if row is None or row.meta is None:
        return None
    meta = dict(row.meta)
    if meta.get("season") is not None and int(meta.get("season")) != int(season_year):
        return None
    meta["last_run_at"] = (
        row.completed_at.isoformat() if row.completed_at is not None else row.started_at.isoformat()
        if row.started_at is not None
        else None
    )
    meta["ingestion_run_id"] = int(row.id)
    meta["ingestion_run_status"] = row.status
    return meta


def fixture_stats_from_run_meta(
    run_meta: dict[str, Any] | None,
    api_fixture_id: int,
) -> dict[str, Any]:
    if not run_meta:
        return {
            "last_run_at": None,
            "sources": {},
            "upcoming_api_fixture_ids": [],
            "records_matching_this_fixture": 0,
            "records_saved_this_fixture": 0,
            "records_from_ids_batch": 0,
            "records_from_league_season_filtered": 0,
            "records_from_fixture_direct": 0,
            "note": "Nessun run availability-upcoming registrato per questa stagione.",
        }

    api_fx = int(api_fixture_id)
    upcoming_ids = run_meta.get("upcoming_api_fixture_ids") or []
    in_upcoming = api_fx in {int(x) for x in upcoming_ids}

    per_fixture = run_meta.get("per_fixture") or {}
    fx_block = per_fixture.get(str(api_fx)) or per_fixture.get(api_fx) or {}

    return {
        "last_run_at": run_meta.get("last_run_at"),
        "sources": run_meta.get("sources") or {},
        "upcoming_api_fixture_ids": upcoming_ids,
        "records_matching_this_fixture": int(fx_block.get("records_matching") or 0),
        "records_saved_this_fixture": int(fx_block.get("records_saved") or 0),
        "records_from_ids_batch": int(fx_block.get("records_from_ids_batch") or 0),
        "records_from_league_season_filtered": int(
            fx_block.get("records_from_league_season_filtered") or 0,
        ),
        "records_from_fixture_direct": int(fx_block.get("records_from_fixture_direct") or 0),
        "in_last_upcoming_set": in_upcoming,
        "provider_future_availability_coverage": run_meta.get("provider_future_availability_coverage"),
        "provider_candidates": {
            "candidates_from_injuries": fx_block.get("candidates_from_injuries") or [],
            "candidates_from_sidelined": fx_block.get("candidates_from_sidelined") or [],
            "candidates_applied": fx_block.get("candidates_applied") or [],
            "candidates_not_applied": fx_block.get("candidates_not_applied") or [],
        },
    }
