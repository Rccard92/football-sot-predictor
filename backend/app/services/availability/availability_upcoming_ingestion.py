"""Ingestion operativa indisponibili: multi-source (ids batch + league filtrato + fixture)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import UPCOMING_EXCLUDED_STATUSES
from app.models import Fixture
from app.services.api_football_client import ApiFootballClient
from app.services.availability.availability_injuries_sources import (
    SOURCE_DETAIL_FIXTURE_DIRECT,
    SOURCE_DETAIL_IDS_BATCH,
    SOURCE_DETAIL_LEAGUE_SEASON_FILTERED,
    fetch_injuries_multi_source,
    item_api_fixture_id,
)
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.availability.availability_persist import (
    deactivate_fixture_injuries,
    upsert_fixture_injury_record,
)
from app.services.availability.availability_upcoming_run import persist_availability_upcoming_run
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

DEFAULT_DAYS_AHEAD = 14
MAX_UPCOMING_FIXTURES = 30

EMPTY_COVERAGE_WARNING = (
    "API-Football non ha restituito indisponibili associati alle fixture upcoming. "
    "Per copertura pre-match completa serve una fonte alternative injuries/suspensions o expected lineups."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kickoff_aware(ko: datetime) -> datetime:
    if ko.tzinfo is None:
        return ko.replace(tzinfo=timezone.utc)
    return ko


def _upcoming_fixtures(
    db: Session,
    *,
    season_row,
    days_ahead: int,
    fixture_id: int | None = None,
) -> list[Fixture]:
    now = _utc_now()
    horizon = now + timedelta(days=int(days_ahead))
    if fixture_id is not None:
        fx = db.scalar(
            select(Fixture)
            .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
            .where(Fixture.id == int(fixture_id), Fixture.season_id == int(season_row.id)),
        )
        return [fx] if fx is not None else []

    out: list[Fixture] = []
    fixtures = db.scalars(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(Fixture.season_id == int(season_row.id))
        .order_by(Fixture.kickoff_at.asc()),
    ).all()
    for fx in fixtures:
        st = (fx.status or "").strip().upper()
        if st in UPCOMING_EXCLUDED_STATUSES:
            continue
        ko = _kickoff_aware(fx.kickoff_at)
        if now <= ko <= horizon:
            out.append(fx)
    return out[:MAX_UPCOMING_FIXTURES]


def _fixture_label(fx: Fixture) -> str:
    home = fx.home_team.name if fx.home_team else "?"
    away = fx.away_team.name if fx.away_team else "?"
    return f"{home} - {away}"


def _sources_to_dict(sources: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, stats in sources.items():
        out[key] = {
            "called": stats.called,
            "results_total": stats.results_total,
            "records_matching_upcoming": stats.records_matching_upcoming,
            **({"error": stats.error} if stats.error else {}),
        }
    return out


def ingest_serie_a_availability_upcoming(
    db: Session,
    season_year: int,
    *,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    force: bool = False,
    fixture_id: int | None = None,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = ctx.league_internal_id
    api_league_id = ctx.api_league_id
    api = client or ApiFootballClient()

    target = _upcoming_fixtures(
        db,
        season_row=season_row,
        days_ahead=int(days_ahead),
        fixture_id=fixture_id,
    )
    if not target:
        empty = {
            "status": "success",
            "season": int(season_year),
            "api_league_id": api_league_id,
            "fixtures_checked": 0,
            "upcoming_api_fixture_ids": [],
            "sources": {},
            "records_saved": 0,
            "records_updated": 0,
            "fixtures_with_availability": [],
            "fixtures_without_availability": [],
            "provider_future_availability_coverage": "empty",
            "warnings": ["Nessuna fixture upcoming nel periodo selezionato."],
            "errors": [],
        }
        persist_availability_upcoming_run(db, int(season_year), empty)
        return empty

    upcoming_api_fixture_ids = [int(fx.api_fixture_id) for fx in target]
    fx_by_api_id: dict[int, Fixture] = {int(fx.api_fixture_id): fx for fx in target}

    if force:
        for api_fx_id in upcoming_api_fixture_ids:
            deactivate_fixture_injuries(
                db,
                season=int(season_year),
                league_id=league_internal_id,
                api_fixture_id=int(api_fx_id),
            )

    fetch_result = fetch_injuries_multi_source(
        api,
        api_league_id=api_league_id,
        season_year=int(season_year),
        upcoming_api_fixture_ids=upcoming_api_fixture_ids,
    )

    sources_dict = _sources_to_dict(fetch_result.sources)
    total_matching = sum(
        s.records_matching_upcoming for s in fetch_result.sources.values()
    )

    per_fixture_match: dict[int, dict[str, int]] = defaultdict(
        lambda: {
            "records_matching": 0,
            "records_saved": 0,
            "records_from_ids_batch": 0,
            "records_from_league_season_filtered": 0,
            "records_from_fixture_direct": 0,
        },
    )

    for item, source_detail in fetch_result.merged_items:
        api_fx = item_api_fixture_id(item)
        if api_fx is None:
            continue
        per_fixture_match[api_fx]["records_matching"] += 1
        if source_detail == SOURCE_DETAIL_IDS_BATCH:
            per_fixture_match[api_fx]["records_from_ids_batch"] += 1
        elif source_detail == SOURCE_DETAIL_LEAGUE_SEASON_FILTERED:
            per_fixture_match[api_fx]["records_from_league_season_filtered"] += 1
        elif source_detail == SOURCE_DETAIL_FIXTURE_DIRECT:
            per_fixture_match[api_fx]["records_from_fixture_direct"] += 1

    records_saved = 0
    records_updated = 0
    errors: list[dict[str, Any]] = []
    fetched_at = _utc_now()
    players_by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for item, source_detail in fetch_result.merged_items:
        api_fx = item_api_fixture_id(item)
        if api_fx is None or api_fx not in fx_by_api_id:
            continue
        fx = fx_by_api_id[api_fx]
        parsed = parse_injuries_item(item)
        if parsed is None or parsed.api_player_id is None:
            continue
        try:
            _row, _reg_ok, created = upsert_fixture_injury_record(
                db,
                fx=fx,
                season_year=int(season_year),
                league_internal_id=league_internal_id,
                parsed=parsed,
                fetched_at=fetched_at,
                source_detail=source_detail,
                api_league_id=api_league_id,
            )
            if created:
                records_saved += 1
            else:
                records_updated += 1
            per_fixture_match[api_fx]["records_saved"] += 1
            players_by_fixture[api_fx].append(
                {
                    "player_name": parsed.player_name,
                    "api_player_id": parsed.api_player_id,
                    "source_detail": source_detail,
                    "availability_status": parsed.availability_status,
                    "availability_type": parsed.availability_type,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "api_fixture_id": api_fx,
                    "api_player_id": parsed.api_player_id,
                    "error": "persist_failed",
                    "message": str(exc)[:300],
                },
            )

    with_availability: list[dict[str, Any]] = []
    without_availability: list[dict[str, Any]] = []

    for fx in target:
        api_fx = int(fx.api_fixture_id)
        saved_n = per_fixture_match[api_fx]["records_saved"]
        entry = {
            "fixture_id": int(fx.id),
            "fixture": _fixture_label(fx),
            "api_fixture_id": api_fx,
            "records_saved": saved_n,
            "players": players_by_fixture[api_fx][:20],
        }
        if saved_n > 0:
            with_availability.append(entry)
        else:
            without_availability.append(entry)

    warnings: list[str] = []
    coverage = "ok" if total_matching > 0 else "empty"
    if coverage == "empty":
        warnings.append(EMPTY_COVERAGE_WARNING)

    per_fixture_meta = {str(k): v for k, v in per_fixture_match.items()}

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        err_summary = {
            "status": "error",
            "season": int(season_year),
            "api_league_id": api_league_id,
            "fixtures_checked": len(target),
            "upcoming_api_fixture_ids": upcoming_api_fixture_ids,
            "sources": sources_dict,
            "records_saved": 0,
            "records_updated": 0,
            "fixtures_with_availability": with_availability,
            "fixtures_without_availability": without_availability,
            "provider_future_availability_coverage": coverage,
            "warnings": warnings,
            "errors": errors + [{"error": "commit_failed", "message": str(exc)[:500]}],
        }
        return err_summary

    status = "success"
    if errors and (records_saved + records_updated) > 0:
        status = "partial_success"
    elif errors:
        status = "partial_success"

    summary: dict[str, Any] = {
        "status": status,
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": api_league_id,
        "days_ahead": int(days_ahead),
        "force": bool(force),
        "fixtures_checked": len(target),
        "upcoming_api_fixture_ids": upcoming_api_fixture_ids,
        "sources": sources_dict,
        "records_saved": records_saved,
        "records_updated": records_updated,
        "api_calls": fetch_result.api_calls,
        "fixtures_with_availability": with_availability,
        "fixtures_without_availability": without_availability,
        "provider_future_availability_coverage": coverage,
        "warnings": warnings,
        "errors": errors,
        "per_fixture": per_fixture_meta,
    }

    try:
        persist_availability_upcoming_run(db, int(season_year), summary)
    except Exception:  # noqa: BLE001
        logger.exception("persist availability-upcoming run meta failed")

    return summary
