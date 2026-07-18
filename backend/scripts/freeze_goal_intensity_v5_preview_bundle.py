"""Congela il bundle Preview Intensità Goal v5 (Fase 2A).

Uso:
  cd backend && python -m scripts.freeze_goal_intensity_v5_preview_bundle \\
    --date-from 2026-06-19 --date-to 2026-07-19 \\
    --minimum-history-sample 10 --bootstrap-iterations 1000

Richiede DATABASE_URL. Non crea bundle attivo se readiness/hash falliscono.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_DATE_FROM = date(2026, 6, 19)
DEFAULT_DATE_TO = date(2026, 7, 19)


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, _, raw = value.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = raw.strip().strip("'").strip('"')


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze Intensità Goal v5 Preview bundle")
    parser.add_argument("--date-from", type=date.fromisoformat, default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", type=date.fromisoformat, default=DEFAULT_DATE_TO)
    parser.add_argument("--competition-id", type=int, default=None)
    parser.add_argument("--minimum-history-sample", type=int, default=10)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument(
        "--skip-hash-enforcement",
        action="store_true",
        help="Solo diagnostica: non usare in produzione",
    )
    args = parser.parse_args()

    _load_dotenv()
    if not os.environ.get("DATABASE_URL"):
        print(json.dumps({"status": "error", "error": "DATABASE_URL_missing"}, indent=2))
        return 2

    from app.core.database import SessionLocal
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import freeze_preview_bundle

    db = SessionLocal()
    try:
        report = freeze_preview_bundle(
            db,
            date_from=args.date_from,
            date_to=args.date_to,
            competition_id=args.competition_id,
            minimum_history_sample=args.minimum_history_sample,
            bootstrap_iterations=args.bootstrap_iterations,
            random_seed=args.random_seed,
            enforce_expected_hashes=not args.skip_hash_enforcement,
        )
        print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
        return 0 if report.get("status") == "ok" else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
