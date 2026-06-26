"""Diagnostica read-only Cecchino Today — timeline API + DB se DATABASE_URL disponibile."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

BACKEND = "https://backend-production-5f140.up.railway.app"


def analyze_timeline_api() -> dict:
    url = f"{BACKEND}/api/cecchino/today/days?timezone=Europe/Rome"
    with urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    days = data.get("days") or []
    scanned = [d for d in days if d.get("is_scanned")]
    june = [d for d in days if str(d.get("date", "")).startswith("2026-06")]
    return {
        "today": data.get("today"),
        "timeline_days": len(days),
        "scanned_in_window": len(scanned),
        "scanned_days": [
            {
                "date": d["date"],
                "eligible": d.get("eligible_count"),
                "excluded": d.get("excluded_count"),
                "finished": d.get("finished_count"),
            }
            for d in scanned
        ],
        "june_not_scanned": [d["date"] for d in june if not d.get("is_scanned")],
        "june_scanned": [d["date"] for d in june if d.get("is_scanned")],
    }


def analyze_db() -> dict | None:
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import get_settings
    except Exception as exc:
        return {"error": f"import failed: {exc}"}

    try:
        url = get_settings().database_url
    except Exception as exc:
        return {"error": f"no DATABASE_URL: {exc}"}

    if not url:
        return {"error": "DATABASE_URL empty"}

    # Normalizza per SQLAlchemy
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_engine(url)
    out: dict = {"database_url_host": url.split("@")[-1].split("/")[0] if "@" in url else "hidden"}

    queries = {
        "fixtures_by_day_june": """
            SELECT scan_date AS day,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE eligibility_status = 'eligible') AS eligible
            FROM cecchino_today_fixtures
            WHERE scan_date >= '2026-06-01'
            GROUP BY scan_date ORDER BY day
        """,
        "eligibility_status_global": """
            SELECT eligibility_status, COUNT(*) AS cnt
            FROM cecchino_today_fixtures
            GROUP BY eligibility_status ORDER BY cnt DESC
        """,
        "activations_by_day_june": """
            SELECT scan_date AS day, COUNT(*) AS activations
            FROM cecchino_signal_activations
            WHERE scan_date >= '2026-06-01'
            GROUP BY scan_date ORDER BY day
        """,
        "fixtures_range": """
            SELECT MIN(scan_date) AS min_day, MAX(scan_date) AS max_day, COUNT(*) AS total_rows
            FROM cecchino_today_fixtures
        """,
        "rows_before_cutoff_7d": """
            SELECT COUNT(*) AS rows_before_cutoff
            FROM cecchino_today_fixtures
            WHERE scan_date < CURRENT_DATE - INTERVAL '7 days'
        """,
        "recent_cleanup_from_jobs": """
            SELECT scan_date, finished_at,
                   result_summary_json->'cleanup' AS cleanup
            FROM cecchino_today_scan_jobs
            WHERE status = 'completed'
              AND result_summary_json ? 'cleanup'
            ORDER BY finished_at DESC NULLS LAST
            LIMIT 10
        """,
    }

    with engine.connect() as conn:
        for name, sql in queries.items():
            rows = conn.execute(text(sql)).mappings().all()
            out[name] = [dict(r) for r in rows]

    today = date.today()
    cutoff = today - timedelta(days=7)
    out["theoretical_cutoff_utc_today"] = cutoff.isoformat()
    return out


def main() -> int:
    print("=== CECCHINO TODAY DIAGNOSTIC (read-only) ===\n")
    api = analyze_timeline_api()
    print("--- Timeline API (production) ---")
    print(json.dumps(api, indent=2, default=str))
    print()

    db = analyze_db()
    print("--- Database (local DATABASE_URL if set) ---")
    if db:
        print(json.dumps(db, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
