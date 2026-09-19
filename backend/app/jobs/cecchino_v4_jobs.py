"""CLI dei job Cecchino V4.

    python -m app.jobs.cecchino_v4_jobs <job> [--date YYYY-MM-DD] [--league I1] [--season 2024] [--limit N] [--days N]

Job: fixtures, post_match, lineups, injuries, standings, odds_snapshot, odds_closing, coverage_scan, backfill.
Usa il database dell'applicazione e il client API-Football reale; ogni chiamata e' registrata in
`api_usage_events` con il job_id e la V4 si ferma da sola alla soglia del giorno (docs/v4/REGOLE.md, regola 6).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from app.services.cecchino_v4.live.jobs import JOBS, JobAlreadyRunning, UnknownJob, job_to_dict, run_job


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cecchino_v4_jobs", description="Job della pipeline live Cecchino V4")
    parser.add_argument("job", choices=sorted(JOBS), help="nome del job")
    parser.add_argument("--date", dest="date", default=None, help="data di partenza YYYY-MM-DD (fixtures)")
    parser.add_argument("--league", dest="league_code", default=None, help="codice campionato football-data (es. I1)")
    parser.add_argument("--season", dest="season", type=int, default=None, help="stagione API-Football (es. 2024 per 2024/25)")
    parser.add_argument("--limit", dest="limit", type=int, default=None, help="massimo partite da elaborare")
    parser.add_argument("--days", dest="days", type=int, default=None, help="giorni di orizzonte (fixtures, odds_snapshot, coverage_scan)")
    parser.add_argument("--no-lineups", dest="no_lineups", action="store_true", help="backfill/post_match senza formazioni")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def _params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.date:
        params["date"] = args.date
    if args.league_code:
        params["league_code"] = args.league_code
    if args.season is not None:
        params["season"] = int(args.season)
    if args.limit is not None:
        params["limit"] = int(args.limit)
    if args.days is not None:
        params["days"] = int(args.days)
    if args.no_lineups:
        params["with_lineups"] = False
    return params


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from app.core.database import SessionLocal
    from app.services.cecchino_v4.live.client import V4ApiClient

    db = SessionLocal()
    try:
        client = V4ApiClient(db=db)
        job = run_job(db, args.job, client=client, params=_params(args))
    except (JobAlreadyRunning, UnknownJob) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    finally:
        db.close()

    print(json.dumps(job_to_dict(job), ensure_ascii=False, indent=2, default=str))
    return 0 if job.status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
