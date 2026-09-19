"""Ambiente locale Cecchino V4 senza database online e senza API-Football.

Crea un database SQLite con le sole tabelle V4 in backend/.runtime/v4/local.db, carica le partite
in programma dal file pubblico football-data (fixtures.csv) con le quote Bet365/Betfair dei mercati
classici, poi calcola previsioni, ragionamenti e shortlist con i motori V4.

Uso (da backend/):
    python scripts/v4_local_demo.py --reset          # ricrea il db e carica le partite
    python scripts/v4_local_demo.py --predict        # previsioni + ragionamenti + shortlist
    DATABASE_URL=sqlite:///.runtime/v4/local.db CECCHINO_V4_ENABLED=true uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DB_PATH = BACKEND / ".runtime" / "v4" / "local.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
os.environ.setdefault("API_FOOTBALL_KEY", "non-usata-in-locale")
os.environ.setdefault("CECCHINO_V4_ENABLED", "true")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Base  # noqa: E402
from app.models.cecchino_v4 import CecchinoV4Fixture, CecchinoV4OddsSnapshot, V4_TABLES  # noqa: E402
from app.services.cecchino_v4.constants import LEAGUE_BY_CODE  # noqa: E402
from app.services.cecchino_v4.history.fixtures_csv import load_upcoming  # noqa: E402


def _engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(os.environ["DATABASE_URL"])


def reset() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    engine = _engine()
    Base.metadata.create_all(engine, tables=list(V4_TABLES))
    Session = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    with Session() as db:
        fixtures = load_upcoming()
        for f in fixtures:
            league = LEAGUE_BY_CODE[f.league_code]
            row = CecchinoV4Fixture(
                api_fixture_id=f.synthetic_api_fixture_id,
                league_code=f.league_code,
                api_league_id=league.api_football_league_id,
                competition=f.competition,
                season_label=f.season_label,
                round="football-data/fixtures.csv",
                match_date=f.match_date,
                kickoff_at=f.kickoff_at,
                status="NS",
                home_team_api_id=0,
                away_team_api_id=0,
                home_team=f.home_team,
                away_team=f.away_team,
                home_team_history=f.home_team,
                away_team_history=f.away_team,
                referee=f.referee,
            )
            db.add(row)
            db.flush()
            for bookmaker_id, markets in f.odds.items():
                db.add(
                    CecchinoV4OddsSnapshot(
                        fixture_id=row.id,
                        bookmaker_id=bookmaker_id,
                        kind="mattina",
                        taken_at=now,
                        markets_json=markets,
                        created_at=now,
                    )
                )
        db.commit()
        n = db.scalar(select(CecchinoV4Fixture.id).order_by(CecchinoV4Fixture.id.desc()).limit(1))
    print(f"db creato: {DB_PATH} · partite in programma: {len(fixtures)} · ultimo id {n}")


def predict() -> None:
    from app.services.cecchino_v4.pipeline.day import build_days

    engine = _engine()
    Session = sessionmaker(bind=engine)
    with Session() as db:
        report = build_days(db)
    print(report)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--predict", action="store_true")
    args = ap.parse_args()
    if args.reset:
        reset()
    if args.predict:
        predict()
    if not (args.reset or args.predict):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
