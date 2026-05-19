"""Orchestrazione provider availability per fixture upcoming."""

from __future__ import annotations

import logging
import traceback
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
    ProviderFetchResult,
)
from app.services.availability.providers.types import NormalizedAvailabilityCandidate
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

LOG_PREFIX = "[availability-upcoming]"
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


def _traceback_tail(exc: BaseException, *, lines: int = 4) -> str:
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tail = "".join(tb[-lines:]).strip()
    return tail[:800]


def _error_entry(phase: str, exc: BaseException) -> dict[str, Any]:
    return {
        "phase": phase,
        "type": exc.__class__.__name__,
        "message": str(exc)[:500],
        "traceback_tail": _traceback_tail(exc),
    }


def _skipped_sidelined_result() -> ProviderFetchResult:
    return ProviderFetchResult(
        provider_name=PROVIDER_SIDELINED,
        called=False,
        status="skipped",
    )


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


def _run_injuries_provider(ctx: ProviderContext) -> ProviderFetchResult:
    logger.info("%s injuries provider start", LOG_PREFIX)
    try:
        result = ApiFootballInjuriesProvider().fetch_candidates(ctx)
        if result.error and result.status == "success":
            result.status = "error"
        logger.info(
            "%s injuries provider done candidates=%s status=%s",
            LOG_PREFIX,
            len(result.candidates),
            result.status,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s injuries provider error", LOG_PREFIX)
        return ProviderFetchResult(
            provider_name=PROVIDER_INJURIES,
            called=True,
            status="error",
            error=str(exc)[:500],
        )


def _run_sidelined_provider(ctx: ProviderContext) -> ProviderFetchResult:
    logger.info("%s sidelined provider start", LOG_PREFIX)
    try:
        result = ApiFootballSidelinedProvider().fetch_candidates(ctx)
        if result.error and result.status == "success":
            result.status = "error"
        logger.info(
            "%s sidelined provider done candidates=%s players_checked=%s status=%s",
            LOG_PREFIX,
            len(result.candidates),
            result.players_checked,
            result.status,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s sidelined provider error", LOG_PREFIX)
        return ProviderFetchResult(
            provider_name=PROVIDER_SIDELINED,
            called=True,
            status="error",
            error=str(exc)[:500],
        )


def _build_providers_report(
    inj_result: ProviderFetchResult,
    side_result: ProviderFetchResult,
    *,
    applied: list[NormalizedAvailabilityCandidate],
    not_applied: list[NormalizedAvailabilityCandidate],
) -> dict[str, Any]:
    inj_block: dict[str, Any] = {
        "called": inj_result.called,
        "status": inj_result.status,
        "candidates_total": len(inj_result.candidates),
        "applicable_saved": sum(1 for c in applied if c.source == "api_football_injuries"),
        "candidate_not_applied": sum(
            1 for c in not_applied if c.source == "api_football_injuries"
        ),
        "api_calls": inj_result.api_calls,
    }
    if inj_result.error:
        inj_block["error"] = inj_result.error

    side_block: dict[str, Any] = {
        "called": side_result.called,
        "status": side_result.status,
        "players_checked": side_result.players_checked,
        "candidates_total": len(side_result.candidates),
        "applicable_saved": sum(1 for c in applied if c.source == "api_football_sidelined"),
        "candidate_not_applied": sum(
            1 for c in not_applied if c.source == "api_football_sidelined"
        ),
        "api_calls": side_result.api_calls,
    }
    if side_result.error:
        side_block["error"] = side_result.error

    return {PROVIDER_INJURIES: inj_block, PROVIDER_SIDELINED: side_block}


def _finalize_status(
    *,
    base_status: str,
    errors: list[dict[str, Any]],
    inj_result: ProviderFetchResult,
    side_result: ProviderFetchResult,
    records_saved: int,
    records_updated: int,
) -> str:
    provider_failed = inj_result.status in ("error", "not_available") or side_result.status in (
        "error",
        "not_available",
    )
    if base_status == "error":
        return "error"
    if provider_failed:
        if records_saved + records_updated > 0 or base_status == "partial_success":
            return "partial_error"
        return "partial_error"
    if errors and (records_saved + records_updated) > 0:
        return "partial_success"
    if errors:
        return "partial_success"
    return base_status


def run_availability_upcoming_orchestrator(
    db: Session,
    season_year: int,
    *,
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    force: bool = False,
    fixture_id: int | None = None,
    client: ApiFootballClient | None = None,
    use_sidelined: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    phase = "start"
    logger.info(
        "%s start season=%s days_ahead=%s use_sidelined=%s dry_run=%s",
        LOG_PREFIX,
        season_year,
        days_ahead,
        use_sidelined,
        dry_run,
    )

    try:
        ing = IngestionService()
        season_row = ing._serie_a_season_row(db, int(season_year))
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s load season failed", LOG_PREFIX)
        return {
            "status": "error",
            "phase": "load_season",
            "message": str(exc)[:500],
            "season": int(season_year),
            "dry_run": bool(dry_run),
            "use_sidelined": bool(use_sidelined),
            "providers": {},
            "errors": [_error_entry("load_season", exc)],
        }

    phase = "resolve_league"
    try:
        league_ctx = resolve_serie_a_league_context(db, int(season_year))
        league_internal_id = league_ctx.league_internal_id
        api_league_id = league_ctx.api_league_id
        logger.info("%s api_league_id=%s", LOG_PREFIX, api_league_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s resolve league failed", LOG_PREFIX)
        return {
            "status": "error",
            "phase": phase,
            "message": str(exc)[:500],
            "season": int(season_year),
            "dry_run": bool(dry_run),
            "use_sidelined": bool(use_sidelined),
            "providers": {},
            "errors": [_error_entry(phase, exc)],
        }

    api = client or ApiFootballClient()

    phase = "load_fixtures"
    try:
        target = resolve_upcoming_fixtures(
            db,
            season_row=season_row,
            days_ahead=int(days_ahead),
            fixture_id=fixture_id,
        )
        logger.info("%s fixtures loaded count=%s", LOG_PREFIX, len(target))
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s load fixtures failed", LOG_PREFIX)
        return {
            "status": "error",
            "phase": phase,
            "message": str(exc)[:500],
            "season": int(season_year),
            "dry_run": bool(dry_run),
            "use_sidelined": bool(use_sidelined),
            "providers": {},
            "errors": [_error_entry(phase, exc)],
        }

    if not target:
        empty = {
            "status": "success",
            "phase": "done",
            "message": "Nessuna fixture upcoming nel periodo selezionato.",
            "season": int(season_year),
            "api_league_id": api_league_id,
            "dry_run": bool(dry_run),
            "use_sidelined": bool(use_sidelined),
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
        if not dry_run:
            try:
                persist_availability_upcoming_run(db, int(season_year), empty)
            except Exception:  # noqa: BLE001
                logger.exception("%s persist run meta failed (empty)", LOG_PREFIX)
        return empty

    upcoming_api_fixture_ids = [int(fx.api_fixture_id) for fx in target]
    fx_by_api_id = {int(fx.api_fixture_id): fx for fx in target}

    if force and not dry_run:
        try:
            for api_fx_id in upcoming_api_fixture_ids:
                deactivate_fixture_api_availability(
                    db,
                    season=int(season_year),
                    league_id=league_internal_id,
                    api_fixture_id=int(api_fx_id),
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(_error_entry("deactivate_fixture", exc))
            logger.exception("%s deactivate failed", LOG_PREFIX)

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

    phase = "api_football_injuries_provider"
    inj_result = _run_injuries_provider(pctx)
    if inj_result.status == "error":
        errors.append(
            {
                "phase": phase,
                "type": "ProviderError",
                "message": inj_result.error or "injuries provider failed",
            },
        )

    if use_sidelined:
        phase = "api_football_sidelined_provider"
        side_result = _run_sidelined_provider(pctx)
        if side_result.status == "error":
            errors.append(
                {
                    "phase": phase,
                    "type": "ProviderError",
                    "message": side_result.error or "sidelined provider failed",
                },
            )
    else:
        side_result = _skipped_sidelined_result()
        logger.info("%s sidelined provider skipped (use_sidelined=false)", LOG_PREFIX)

    phase = "normalize_confidence"
    applied: list[NormalizedAvailabilityCandidate] = []
    not_applied: list[NormalizedAvailabilityCandidate] = []
    try:
        all_candidates = inj_result.candidates + side_result.candidates
        apply_confidence_scores(all_candidates, fx_by_api_id=fx_by_api_id)
        applied, not_applied = split_applicable(all_candidates)
        logger.info(
            "%s normalize done applied=%s not_applied=%s",
            LOG_PREFIX,
            len(applied),
            len(not_applied),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s normalize failed", LOG_PREFIX)
        errors.append(_error_entry(phase, exc))

    applied_by_fx: dict[int, list] = defaultdict(list)
    not_applied_by_fx: dict[int, list] = defaultdict(list)
    for c in applied:
        applied_by_fx[int(c.api_fixture_id)].append(c)
    for c in not_applied:
        not_applied_by_fx[int(c.api_fixture_id)].append(c)

    per_fixture_debug: dict[str, dict[str, Any]] = {}
    for api_fx in upcoming_api_fixture_ids:
        per_fixture_debug[str(api_fx)] = _serialize_candidate_lists(
            applied_by_fx.get(api_fx, []),
            not_applied_by_fx.get(api_fx, []),
        )

    records_saved = 0
    records_updated = 0
    errors.extend(list(pctx.errors))
    fetched_at = _utc_now()
    players_by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)
    per_fixture_saved: dict[int, int] = defaultdict(int)

    phase = "save"
    if dry_run:
        logger.info("%s save skipped dry_run=true would_save=%s", LOG_PREFIX, len(applied))
        for cand in applied:
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
    else:
        logger.info("%s save start records=%s", LOG_PREFIX, len(applied))
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
                        "phase": "save",
                        "api_fixture_id": cand.api_fixture_id,
                        "api_player_id": cand.api_player_id,
                        "type": exc.__class__.__name__,
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

    coverage = "ok" if len(applied) > 0 else "empty"
    warnings: list[str] = []
    if coverage == "empty":
        warnings.append(EMPTY_COVERAGE_WARNING)
    if dry_run:
        warnings.append("dry_run=true: nessun record salvato su DB.")
    if side_result.status == "skipped":
        warnings.append("use_sidelined=false: provider sidelined non eseguito.")

    providers_report = _build_providers_report(
        inj_result,
        side_result,
        applied=applied,
        not_applied=not_applied,
    )

    per_fixture_meta: dict[str, Any] = {}
    for api_fx in upcoming_api_fixture_ids:
        meta = {
            "records_saved": per_fixture_saved.get(api_fx, 0),
            "records_matching": len(applied_by_fx.get(api_fx, []))
            + len(not_applied_by_fx.get(api_fx, [])),
        }
        meta.update(per_fixture_debug.get(str(api_fx), {}))
        per_fixture_meta[str(api_fx)] = meta

    base_status = "success"
    if not dry_run:
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("%s commit failed", LOG_PREFIX)
            return {
                "status": "error",
                "phase": "commit",
                "message": str(exc)[:500],
                "season": int(season_year),
                "dry_run": bool(dry_run),
                "use_sidelined": bool(use_sidelined),
                "providers": providers_report,
                "errors": errors + [_error_entry("commit", exc)],
            }

    status = _finalize_status(
        base_status=base_status,
        errors=errors,
        inj_result=inj_result,
        side_result=side_result,
        records_saved=records_saved,
        records_updated=records_updated,
    )

    message = "Completato."
    if status == "partial_error":
        message = "Completato con errori su uno o più provider."
    elif status == "partial_success":
        message = "Completato con alcuni errori di persistenza."

    summary: dict[str, Any] = {
        "status": status,
        "phase": "done",
        "message": message,
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": api_league_id,
        "days_ahead": int(days_ahead),
        "force": bool(force),
        "dry_run": bool(dry_run),
        "use_sidelined": bool(use_sidelined),
        "fixtures_checked": len(target),
        "upcoming_api_fixture_ids": upcoming_api_fixture_ids,
        "providers": providers_report,
        "records_saved": records_saved if not dry_run else 0,
        "records_updated": records_updated if not dry_run else 0,
        "records_would_save": len(applied) if dry_run else None,
        "api_calls": inj_result.api_calls + side_result.api_calls,
        "fixtures_with_availability": with_availability,
        "fixtures_without_availability": without_availability,
        "provider_future_availability_coverage": coverage,
        "warnings": warnings,
        "errors": errors,
        "per_fixture": per_fixture_meta,
        "sources": {
            "ids_batch": {"called": inj_result.called, "status": inj_result.status},
            "league_season_filtered": {"called": inj_result.called, "status": inj_result.status},
            "fixture_direct": {"called": inj_result.called, "status": inj_result.status},
        },
    }

    if not dry_run:
        try:
            persist_availability_upcoming_run(db, int(season_year), summary)
        except Exception:  # noqa: BLE001
            logger.exception("%s persist run meta failed", LOG_PREFIX)

    logger.info("%s done status=%s", LOG_PREFIX, status)
    return summary
