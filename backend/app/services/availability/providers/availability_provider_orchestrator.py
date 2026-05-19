"""Orchestrazione provider availability per fixture upcoming."""

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
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_persist import (
    deactivate_fixture_api_availability,
    upsert_availability_candidate,
)
from app.services.availability.availability_upcoming_run import persist_availability_upcoming_run
from app.services.availability.providers.api_football_injuries_provider import (
    ApiFootballInjuriesProvider,
)
from app.services.availability.providers.api_football_sidelined_provider import (
    ApiFootballSidelinedProvider,
)
from app.services.availability.providers.availability_confidence import (
    apply_confidence_scores,
    split_applicable,
)
from app.services.availability.providers.base import (
    PROVIDER_INJURIES,
    PROVIDER_SIDELINED,
    ProviderContext,
)
from app.services.availability.providers.types import NormalizedAvailabilityCandidate
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

DEFAULT_DAYS_AHEAD = 14
MAX_UPCOMING_FIXTURES = 30

EMPTY_COVERAGE_WARNING = (
    "API-Football non ha restituito indisponibili applicabili alle fixture upcoming "
    "(injuries + sidelined). Per copertura pre-match completa serve una fonte alternativa."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _kickoff_aware(ko: datetime) -> datetime:
    if ko.tzinfo is None:
        return ko.replace(tzinfo=timezone.utc)
    return ko


def resolve_upcoming_fixtures(
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


def _serialize_candidate_lists(
    applied: list[NormalizedAvailabilityCandidate],
    not_applied: list[NormalizedAvailabilityCandidate],
) -> dict[str, Any]:
    from_injuries = [c for c in applied + not_applied if c.source == "api_football_injuries"]
    from_sidelined = [c for c in applied + not_applied if c.source == "api_football_sidelined"]
    return {
        "candidates_from_injuries": [c.to_debug_dict() for c in from_injuries[:30]],
        "candidates_from_sidelined": [c.to_debug_dict() for c in from_sidelined[:30]],
        "candidates_applied": [c.to_debug_dict() for c in applied[:30]],
        "candidates_not_applied": [c.to_debug_dict() for c in not_applied[:30]],
    }


def run_availability_upcoming_orchestrator(
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
    league_ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = league_ctx.league_internal_id
    api_league_id = league_ctx.api_league_id
    api = client or ApiFootballClient()

    target = resolve_upcoming_fixtures(
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
            "providers": {},
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
    fx_by_api_id = {int(fx.api_fixture_id): fx for fx in target}

    if force:
        for api_fx_id in upcoming_api_fixture_ids:
            deactivate_fixture_api_availability(
                db,
                season=int(season_year),
                league_id=league_internal_id,
                api_fixture_id=int(api_fx_id),
            )

    pctx = ProviderContext(
        db=db,
        season_year=int(season_year),
        league_internal_id=league_internal_id,
        api_league_id=api_league_id,
        upcoming_fixtures=target,
        upcoming_api_fixture_ids=upcoming_api_fixture_ids,
        fx_by_api_id=fx_by_api_id,
        api_client=api,
    )

    injuries_provider = ApiFootballInjuriesProvider()
    sidelined_provider = ApiFootballSidelinedProvider()

    inj_result = injuries_provider.fetch_candidates(pctx)
    side_result = sidelined_provider.fetch_candidates(pctx)

    all_candidates = inj_result.candidates + side_result.candidates
    apply_confidence_scores(all_candidates, fx_by_api_id=fx_by_api_id)
    applied, not_applied = split_applicable(all_candidates)

    per_fixture_debug: dict[str, dict[str, Any]] = defaultdict(
        lambda: _serialize_candidate_lists([], []),
    )
    for c in applied + not_applied:
        key = str(c.api_fixture_id)
        if key not in per_fixture_debug:
            per_fixture_debug[key] = _serialize_candidate_lists([], [])
    applied_by_fx: dict[int, list] = defaultdict(list)
    not_applied_by_fx: dict[int, list] = defaultdict(list)
    for c in applied:
        applied_by_fx[int(c.api_fixture_id)].append(c)
    for c in not_applied:
        not_applied_by_fx[int(c.api_fixture_id)].append(c)
    for api_fx in upcoming_api_fixture_ids:
        per_fixture_debug[str(api_fx)] = _serialize_candidate_lists(
            applied_by_fx.get(api_fx, []),
            not_applied_by_fx.get(api_fx, []),
        )

    records_saved = 0
    records_updated = 0
    errors = list(pctx.errors)
    fetched_at = _utc_now()
    players_by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)
    per_fixture_saved: dict[int, int] = defaultdict(int)

    for cand in applied:
        try:
            _row, _reg, created = upsert_availability_candidate(
                db,
                candidate=cand,
                fetched_at=fetched_at,
            )
            if created:
                records_saved += 1
            else:
                records_updated += 1
            api_fx = int(cand.api_fixture_id)
            per_fixture_saved[api_fx] += 1
            players_by_fixture[api_fx].append(
                {
                    "player_name": cand.player_name,
                    "api_player_id": cand.api_player_id,
                    "source": cand.source,
                    "source_detail": cand.source_detail,
                    "confidence": cand.confidence,
                    "availability_status": cand.availability_status,
                },
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "api_fixture_id": cand.api_fixture_id,
                    "api_player_id": cand.api_player_id,
                    "error": "persist_failed",
                    "message": str(exc)[:300],
                },
            )

    with_availability: list[dict[str, Any]] = []
    without_availability: list[dict[str, Any]] = []

    for fx in target:
        api_fx = int(fx.api_fixture_id)
        saved_n = per_fixture_saved[api_fx]
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

    total_candidates = len(applied) + len(not_applied)
    coverage = "ok" if len(applied) > 0 else "empty"
    warnings: list[str] = []
    if coverage == "empty":
        warnings.append(EMPTY_COVERAGE_WARNING)

    providers_report = {
        PROVIDER_INJURIES: {
            "called": inj_result.called,
            "candidates_total": len(inj_result.candidates),
            "applicable_saved": sum(1 for c in applied if c.source == "api_football_injuries"),
            "candidate_not_applied": sum(
                1 for c in not_applied if c.source == "api_football_injuries"
            ),
            "api_calls": inj_result.api_calls,
            **({"error": inj_result.error} if inj_result.error else {}),
        },
        PROVIDER_SIDELINED: {
            "called": side_result.called,
            "players_checked": side_result.players_checked,
            "candidates_total": len(side_result.candidates),
            "applicable_saved": sum(1 for c in applied if c.source == "api_football_sidelined"),
            "candidate_not_applied": sum(
                1 for c in not_applied if c.source == "api_football_sidelined"
            ),
            "api_calls": side_result.api_calls,
            **({"error": side_result.error} if side_result.error else {}),
        },
    }

    per_fixture_meta: dict[str, Any] = {}
    for api_fx in upcoming_api_fixture_ids:
        meta = {
            "records_saved": per_fixture_saved.get(api_fx, 0),
            "records_matching": len(applied_by_fx.get(api_fx, [])) + len(not_applied_by_fx.get(api_fx, [])),
        }
        meta.update(per_fixture_debug.get(str(api_fx), {}))
        per_fixture_meta[str(api_fx)] = meta

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {
            "status": "error",
            "season": int(season_year),
            "message": str(exc)[:500],
            "errors": errors,
        }

    status = "success"
    if errors and (records_saved + records_updated) > 0:
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
        "providers": providers_report,
        "records_saved": records_saved,
        "records_updated": records_updated,
        "api_calls": inj_result.api_calls + side_result.api_calls,
        "fixtures_with_availability": with_availability,
        "fixtures_without_availability": without_availability,
        "provider_future_availability_coverage": coverage,
        "warnings": warnings,
        "errors": errors,
        "per_fixture": per_fixture_meta,
        "sources": {
            "ids_batch": {"called": inj_result.called},
            "league_season_filtered": {"called": inj_result.called},
            "fixture_direct": {"called": inj_result.called},
        },
    }

    try:
        persist_availability_upcoming_run(db, int(season_year), summary)
    except Exception:  # noqa: BLE001
        logger.exception("persist availability-upcoming run meta failed")

    return summary
