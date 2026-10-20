"""Audit di infrastruttura e salute dei dati (sola lettura): tabelle, consumo API, job, risultati fermi."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.readonly import json_value


def _rows(db: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    result = db.execute(text(sql), params)
    cols = list(result.keys())
    return [{c: json_value(v) for c, v in zip(cols, r)} for r in result.fetchall()]


def database_tables(db: Session) -> dict[str, Any]:
    """Peso di ogni tabella (dati + indici + TOAST), righe stimate, uso (scan) e ultima manutenzione."""
    tables = _rows(
        db,
        """
        SELECT s.relname AS table,
               pg_total_relation_size(s.relid) AS total_bytes,
               pg_relation_size(s.relid) AS table_bytes,
               pg_indexes_size(s.relid) AS index_bytes,
               COALESCE(pg_total_relation_size(c.reltoastrelid), 0) AS toast_bytes,
               s.n_live_tup AS rows_estimate,
               s.n_dead_tup AS dead_rows,
               s.seq_scan, s.idx_scan,
               s.n_tup_ins AS inserted, s.n_tup_upd AS updated, s.n_tup_del AS deleted,
               s.last_autovacuum, s.last_autoanalyze
        FROM pg_stat_user_tables s
        JOIN pg_class c ON c.oid = s.relid
        ORDER BY pg_total_relation_size(s.relid) DESC
        """,
    )
    total = db.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
    for t in tables:
        t["total_mb"] = round((t["total_bytes"] or 0) / 1_048_576, 1)
        t["unused_since_stats_reset"] = (t["seq_scan"] or 0) + (t["idx_scan"] or 0) == 0
    stats_reset = db.execute(text("SELECT stats_reset FROM pg_stat_database WHERE datname = current_database()")).scalar()
    return {
        "database_mb": round(total / 1_048_576, 1),
        "stats_since": json_value(stats_reset),
        "tables": tables,
        "note": "seq_scan/idx_scan contano le letture dall'ultimo azzeramento delle statistiche: 0 = nessuno la legge.",
    }


def table_columns(db: Session, table: str) -> list[dict[str, Any]]:
    return _rows(
        db,
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t
        ORDER BY ordinal_position
        """,
        t=table,
    )


def api_usage(db: Session, days: int = 14) -> dict[str, Any]:
    """Chiamate API-Football registrate per giorno ed endpoint (cache escluse)."""
    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    by_day = _rows(
        db,
        """
        SELECT (created_at AT TIME ZONE 'UTC')::date AS day, endpoint, count(*) AS calls
        FROM api_usage_events
        WHERE created_at >= :since AND cache_hit = false AND negative_cache_hit = false
        GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC
        """,
        since=since,
    )
    totals: dict[str, int] = {}
    for r in by_day:
        totals[r["day"]] = totals.get(r["day"], 0) + int(r["calls"])
    return {
        "days": int(days),
        "per_day_total": [{"day": d, "calls": c} for d, c in sorted(totals.items(), reverse=True)],
        "per_day_endpoint": by_day,
        "note": "Solo le chiamate registrate in api_usage_events; il contatore ufficiale e' nella result_summary.provider_quota dei job di scansione.",
    }


def recent_jobs(db: Session, days: int = 7) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    today_jobs = _rows(
        db,
        """
        SELECT job_id, scan_date, status, current_step, fixtures_found, fixtures_checked, eligible_count,
               excluded_count, started_at, finished_at,
               EXTRACT(EPOCH FROM (finished_at - started_at))::int AS duration_s,
               result_summary_json -> 'api_calls_total' AS api_calls_total,
               result_summary_json -> 'provider_quota' AS provider_quota,
               result_summary_json -> 'post_scan_api_calls' AS post_scan_api_calls,
               result_summary_json -> 'auto_scan' ->> 'execution_slot' AS slot,
               errors_json
        FROM cecchino_today_scan_jobs
        WHERE created_at >= :since
        ORDER BY created_at DESC
        """,
        since=since,
    )
    v4_jobs = _rows(
        db,
        """
        SELECT name, status, step, api_calls, error_message, created_at, finished_at,
               EXTRACT(EPOCH FROM (finished_at - created_at))::int AS duration_s
        FROM cecchino_v4_jobs
        WHERE created_at >= :since
        ORDER BY created_at DESC
        LIMIT 300
        """,
        since=since,
    )
    return {"days": int(days), "today_scan_jobs": today_jobs, "v4_jobs": v4_jobs}


def data_health(db: Session, days: int = 30) -> dict[str, Any]:
    """Giornate e partite che non tornano: eleggibili ferme, giorni senza scansione, previsioni aperte."""
    since = date.today() - timedelta(days=int(days))
    per_day = _rows(
        db,
        """
        SELECT scan_date,
               count(*) FILTER (WHERE eligibility_status = 'eligible') AS eligible,
               count(*) FILTER (WHERE eligibility_status <> 'eligible') AS excluded,
               count(*) FILTER (WHERE eligibility_status = 'eligible' AND match_display_status = 'finished') AS finished,
               count(*) FILTER (WHERE eligibility_status = 'eligible' AND match_display_status IN ('upcoming', 'live')
                                AND kickoff < now() - interval '3 hours') AS stale,
               max(updated_at) AS last_update
        FROM cecchino_today_fixtures
        WHERE scan_date >= :since
        GROUP BY scan_date ORDER BY scan_date DESC
        """,
        since=since,
    )
    scanned = {r["scan_date"] for r in per_day}
    missing_days = [
        (since + timedelta(days=i)).isoformat()
        for i in range(int(days))
        if (since + timedelta(days=i)).isoformat() not in scanned and since + timedelta(days=i) < date.today()
    ]
    open_live = _rows(
        db,
        """
        SELECT model, count(*) AS open_predictions, min(kickoff) AS oldest_kickoff
        FROM cecchino_live_predictions
        WHERE status = 'open' AND kickoff < now() - interval '6 hours'
        GROUP BY model ORDER BY model
        """,
    )
    return {
        "days": int(days),
        "per_day": per_day,
        "days_without_scan": missing_days,
        "stale_eligible_total": sum(int(r["stale"] or 0) for r in per_day),
        "live_registry_open_past_kickoff": open_live,
    }


def overview(db: Session) -> dict[str, Any]:
    db_mb = db.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
    counts = _rows(
        db,
        """
        SELECT 'cecchino_today_fixtures' AS table, count(*) AS rows FROM cecchino_today_fixtures
        UNION ALL SELECT 'cecchino_live_predictions', count(*) FROM cecchino_live_predictions
        UNION ALL SELECT 'cecchino_v4_fixtures', count(*) FROM cecchino_v4_fixtures
        UNION ALL SELECT 'fixtures', count(*) FROM fixtures
        UNION ALL SELECT 'fixture_team_stats', count(*) FROM fixture_team_stats
        UNION ALL SELECT 'api_usage_events', count(*) FROM api_usage_events
        """,
    )
    last_scan = _rows(
        db,
        """
        SELECT scan_date, status, eligible_count, finished_at,
               result_summary_json -> 'provider_quota' AS provider_quota
        FROM cecchino_today_scan_jobs ORDER BY created_at DESC LIMIT 1
        """,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_mb": round(db_mb / 1_048_576, 1),
        "row_counts": counts,
        "last_scan": last_scan[0] if last_scan else None,
    }
