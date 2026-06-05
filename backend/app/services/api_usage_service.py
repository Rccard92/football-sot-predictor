"""Tracking e budget guard consumo API-Football."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.api_usage_event import PROVIDER_API_FOOTBALL, ApiUsageEvent
from app.services.api_usage_context import BudgetGuardStop

_SENSITIVE_PARAM_KEYS = frozenset({"key", "api_key", "x-apisports-key", "token"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_endpoint(path: str) -> str:
    p = path.lstrip("/").split("/")[0] if path else "unknown"
    if p == "fixtures" and "statistics" in path:
        return "fixtures/statistics"
    if p == "fixtures" and "events" in path:
        return "fixtures/events"
    if p == "fixtures" and "players" in path:
        return "fixtures/players"
    if p == "fixtures" and "lineups" in path:
        return "fixtures/lineups"
    return p


def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    out: dict[str, Any] = {}
    for k, v in params.items():
        if str(k).lower() in _SENSITIVE_PARAM_KEYS:
            continue
        out[str(k)] = v
    return out


def _params_hash(params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def record_api_usage_event(
    db: Session | None,
    *,
    endpoint: str,
    params: dict[str, Any] | None = None,
    status_code: int | None = None,
    duration_ms: int | None = None,
    provider_source: str = PROVIDER_API_FOOTBALL,
    scan_date: date | None = None,
    job_id: str | None = None,
    provider_fixture_id: int | None = None,
    provider_league_id: int | None = None,
    cache_hit: bool = False,
    negative_cache_hit: bool = False,
) -> None:
    if db is None:
        return
    clean = _sanitize_params(params)
    row = ApiUsageEvent(
        provider_source=provider_source,
        endpoint=_normalize_endpoint(endpoint),
        scan_date=scan_date,
        job_id=job_id,
        provider_fixture_id=provider_fixture_id,
        provider_league_id=provider_league_id,
        request_params_hash=_params_hash(clean) if clean else None,
        request_params_json=clean or None,
        status_code=status_code,
        duration_ms=duration_ms,
        cache_hit=cache_hit,
        negative_cache_hit=negative_cache_hit,
        created_at=_utcnow(),
    )
    db.add(row)
    try:
        db.flush()
    except Exception:
        db.rollback()


def count_api_calls_for_date(
    db: Session,
    *,
    usage_date: date,
    provider_source: str = PROVIDER_API_FOOTBALL,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ApiUsageEvent)
            .where(
                ApiUsageEvent.provider_source == provider_source,
                func.date(ApiUsageEvent.created_at) == usage_date,
                ApiUsageEvent.cache_hit.is_(False),
                ApiUsageEvent.negative_cache_hit.is_(False),
            ),
        )
        or 0,
    )


def count_job_api_calls(db: Session, job_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ApiUsageEvent)
            .where(
                ApiUsageEvent.job_id == job_id,
                ApiUsageEvent.cache_hit.is_(False),
                ApiUsageEvent.negative_cache_hit.is_(False),
            ),
        )
        or 0,
    )


def get_api_usage_summary(db: Session, *, usage_date: date) -> dict[str, Any]:
    settings = get_settings()
    daily_budget = int(settings.api_football_daily_budget)
    rows = list(
        db.scalars(
            select(ApiUsageEvent).where(func.date(ApiUsageEvent.created_at) == usage_date),
        ).all(),
    )
    by_endpoint: dict[str, int] = {}
    cache_hits = 0
    negative_cache_hits = 0
    real_calls = 0
    for row in rows:
        if row.cache_hit:
            cache_hits += 1
            continue
        if row.negative_cache_hit:
            negative_cache_hits += 1
            continue
        real_calls += 1
        ep = row.endpoint or "unknown"
        by_endpoint[ep] = by_endpoint.get(ep, 0) + 1

    by_job_rows = db.execute(
        select(
            ApiUsageEvent.job_id,
            func.count().label("calls"),
        )
        .where(
            func.date(ApiUsageEvent.created_at) == usage_date,
            ApiUsageEvent.job_id.isnot(None),
            ApiUsageEvent.cache_hit.is_(False),
            ApiUsageEvent.negative_cache_hit.is_(False),
        )
        .group_by(ApiUsageEvent.job_id)
        .order_by(func.count().desc()),
    ).all()
    by_job = [{"job_id": r.job_id, "calls": int(r.calls)} for r in by_job_rows if r.job_id]

    return {
        "date": usage_date.isoformat(),
        "total_calls": real_calls,
        "by_endpoint": {
            "odds": by_endpoint.get("odds", 0),
            "fixtures": by_endpoint.get("fixtures", 0),
            "teams": by_endpoint.get("teams", 0),
            **{k: v for k, v in by_endpoint.items() if k not in {"odds", "fixtures", "teams"}},
        },
        "by_job": by_job,
        "cache_hits": cache_hits,
        "negative_cache_hits": negative_cache_hits,
        "estimated_remaining_daily_budget": max(0, daily_budget - real_calls),
    }


def check_api_budget_before_scan(db: Session, *, usage_date: date | None = None) -> None:
    settings = get_settings()
    target = usage_date or _utcnow().date()
    used = count_api_calls_for_date(db, usage_date=target)
    remaining = int(settings.api_football_daily_budget) - used
    if remaining < int(settings.api_football_safe_stop_remaining):
        raise BudgetGuardStop(
            status="failed_budget_guard",
            message="Scansione interrotta per proteggere il budget API giornaliero.",
            api_calls_total=used,
            details={"remaining": remaining, "used_today": used},
        )


def check_api_budget_during_scan(
    db: Session,
    *,
    job_id: str | None,
    usage_date: date,
    job_calls: int,
) -> None:
    settings = get_settings()
    used_today = count_api_calls_for_date(db, usage_date=usage_date)
    remaining = int(settings.api_football_daily_budget) - used_today
    max_job = int(settings.api_football_cecchino_scan_max_calls)

    if job_calls >= max_job:
        raise BudgetGuardStop(
            status="partial_stopped_budget",
            message="Scansione interrotta per proteggere il budget API giornaliero.",
            api_calls_total=job_calls,
            details={"reason": "job_max_calls", "job_calls": job_calls, "max_job": max_job},
        )
    if remaining < int(settings.api_football_safe_stop_remaining):
        raise BudgetGuardStop(
            status="partial_stopped_budget",
            message="Scansione interrotta per proteggere il budget API giornaliero.",
            api_calls_total=job_calls,
            details={"reason": "daily_remaining", "remaining": remaining},
        )


def build_api_usage_debug_for_fixture(
    db: Session,
    *,
    provider_fixture_id: int,
    scan_date: date,
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(ApiUsageEvent)
            .where(
                ApiUsageEvent.scan_date == scan_date,
                ApiUsageEvent.provider_fixture_id == int(provider_fixture_id),
            )
            .order_by(ApiUsageEvent.created_at.desc())
            .limit(20),
        ).all(),
    )
    by_endpoint: dict[str, int] = {}
    for row in rows:
        if row.cache_hit or row.negative_cache_hit:
            continue
        ep = row.endpoint or "unknown"
        by_endpoint[ep] = by_endpoint.get(ep, 0) + 1
    return {
        "calls": len([r for r in rows if not r.cache_hit and not r.negative_cache_hit]),
        "cache_hits": sum(1 for r in rows if r.cache_hit),
        "negative_cache_hits": sum(1 for r in rows if r.negative_cache_hit),
        "by_endpoint": by_endpoint,
        "recent": [
            {
                "endpoint": r.endpoint,
                "cache_hit": r.cache_hit,
                "negative_cache_hit": r.negative_cache_hit,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows[:5]
        ],
    }
