"""Supporto ai test della pipeline live V4: campioni JSON registrati, client finto, tabella eventi d'uso su SQLite.

Nessun test qui: solo helper importati dai `test_live_*.py`.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.services.api_football_client import ApiFootballQuotaExhausted
from app.services.api_usage_context import ApiUsageContext
from app.services.api_usage_service import record_api_usage_event

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures_api"

# 20 settembre 2026, 10:00 UTC = 12:00 a Roma (istantanea "pomeriggio").
NOW = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)

HISTORY_NAMES: dict[str, set[str]] = {
    "I1": {"Milan", "Inter", "Juventus", "Napoli", "Roma", "Lazio", "Atalanta", "Verona"},
    "E0": {"Man City", "Man United", "Arsenal", "Liverpool", "Nott'm Forest", "Wolves"},
}

USAGE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_source VARCHAR(32) NOT NULL,
    endpoint VARCHAR(64) NOT NULL,
    scan_date DATE,
    job_id VARCHAR(36),
    provider_fixture_id BIGINT,
    provider_league_id BIGINT,
    request_params_hash VARCHAR(64),
    request_params_json TEXT,
    status_code INTEGER,
    duration_ms INTEGER,
    cache_hit BOOLEAN NOT NULL,
    negative_cache_hit BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL
)
"""


def load_sample(name: str) -> dict[str, Any]:
    with (FIXTURES_DIR / f"{name}.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def create_usage_table(db) -> None:
    """`api_usage_events` ha una colonna JSONB (PostgreSQL): su SQLite la creiamo a mano con TEXT."""
    db.execute(text(USAGE_TABLE_SQL))
    db.commit()


def seed_usage_events(db, n: int, *, when: datetime | None = None) -> None:
    """Inserisce `n` chiamate API-Football gia' fatte (per simulare il contatore del giorno; default: adesso, ora reale)."""
    stamp = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for i in range(n):
        db.execute(
            text(
                "INSERT INTO api_usage_events (provider_source, endpoint, cache_hit, negative_cache_hit, created_at) "
                "VALUES ('api_football', 'fixtures', 0, 0, :ts)"
            ),
            {"ts": stamp.replace(tzinfo=None)},
        )
    db.commit()


class FakeClient:
    """Stessi nomi di metodo di `ApiFootballClient`, risposte dai campioni JSON, nessuna rete.

    Registra ogni chiamata in `calls` e, come il client vero, un evento d'uso quando ha una sessione.
    """

    def __init__(self, *, fail_after: int | None = None, odds_pages: list[dict[str, Any]] | None = None) -> None:
        self.samples = {
            "fixtures": load_sample("fixtures_by_date"),
            "statistics": load_sample("fixture_statistics"),
            "events": load_sample("fixture_events"),
            "players": load_sample("fixture_players"),
            "lineups": load_sample("fixture_lineups"),
            "injuries": load_sample("injuries"),
            "standings": load_sample("standings"),
            "odds_fixture": load_sample("odds_by_fixture"),
            "odds_league": load_sample("odds_by_league_date"),
            "bookmakers": load_sample("bookmakers"),
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.contexts: list[ApiUsageContext] = []
        self._db = None
        self._ctx = ApiUsageContext(record_events=False)
        self.fail_after = fail_after
        self.odds_pages = odds_pages

    # --- come ApiFootballClient ---
    def set_usage_db(self, db) -> None:
        self._db = db

    def set_usage_context(self, ctx: ApiUsageContext | None) -> None:
        self._ctx = ctx or ApiUsageContext(record_events=False)

    def _record(self, endpoint: str, params: dict[str, Any]) -> None:
        self.calls.append((endpoint, dict(params)))
        self.contexts.append(self._ctx)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise ApiFootballQuotaExhausted("quota finita (finto)", endpoint=endpoint, status_code=429)
        if self._db is not None and self._ctx.record_events:
            record_api_usage_event(
                self._db,
                endpoint=endpoint,
                params=params,
                status_code=200,
                duration_ms=5,
                scan_date=self._ctx.scan_date,
                job_id=self._ctx.job_id,
                provider_fixture_id=self._ctx.provider_fixture_id,
                provider_league_id=self._ctx.provider_league_id,
            )

    def _response(self, key: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.samples[key]["response"])

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        self._record(endpoint, params)
        if endpoint == "odds":
            if self.odds_pages is not None:
                return copy.deepcopy(self.odds_pages[int(params.get("page", 1)) - 1])
            body = copy.deepcopy(self.samples["odds_league"])
            wanted = params.get("bookmaker")
            if wanted is not None:
                for item in body["response"]:
                    item["bookmakers"] = [b for b in item["bookmakers"] if int(b["id"]) == int(wanted)]
            return body
        raise AssertionError(f"endpoint non previsto dal finto: {endpoint}")

    def get_fixtures_by_date(self, date: str, timezone: str = "Europe/Rome") -> list[dict[str, Any]]:
        self._record("fixtures", {"date": date, "timezone": timezone})
        return self._response("fixtures")

    def get_fixtures(self, league_id: int, season: int, status: str | None = None) -> list[dict[str, Any]]:
        self._record("fixtures", {"league": league_id, "season": season, "status": status})
        return [it for it in self._response("fixtures") if int(it["league"]["id"]) == int(league_id)]

    def get_fixture_by_id(self, api_fixture_id: int) -> dict[str, Any] | None:
        self._record("fixtures", {"id": api_fixture_id})
        for it in self._response("fixtures"):
            if int(it["fixture"]["id"]) == int(api_fixture_id):
                return it
        return None

    def get_fixture_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        self._record("fixtures/statistics", {"fixture": fixture_id})
        return self._response("statistics")

    def get_fixture_events(self, fixture_id: int) -> list[dict[str, Any]]:
        self._record("fixtures/events", {"fixture": fixture_id})
        return self._response("events")

    def get_fixture_players(self, fixture_id: int) -> list[dict[str, Any]]:
        self._record("fixtures/players", {"fixture": fixture_id})
        return self._response("players")

    # il campione formazioni e' di Milan-Inter (1001); per Juventus-Napoli (1003) rimappiamo le squadre
    _LINEUP_TEAM_REMAP = {1003: {489: 496, 505: 492}}

    def get_fixture_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        self._record("fixtures/lineups", {"fixture": fixture_id})
        items = self._response("lineups")
        remap = self._LINEUP_TEAM_REMAP.get(int(fixture_id))
        if remap:
            for it in items:
                it["team"]["id"] = remap.get(int(it["team"]["id"]), it["team"]["id"])
        return items

    def get_injuries(self, league: int, season: int) -> list[dict[str, Any]]:
        self._record("injuries", {"league": league, "season": season})
        return self._response("injuries")

    def get_standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        self._record("standings", {"league": league_id, "season": season})
        return self._response("standings")

    def get_fixture_odds_by_fixture(self, api_fixture_id: int) -> list[dict[str, Any]]:
        self._record("odds", {"fixture": api_fixture_id})
        items = self._response("odds_fixture")
        for it in items:
            it["fixture"]["id"] = int(api_fixture_id)
        return items

    def get_odds_bookmakers(self) -> list[dict[str, Any]]:
        self._record("odds/bookmakers", {})
        return self._response("bookmakers")

    # --- comodita' per i test ---
    def endpoints(self) -> list[str]:
        return [e for e, _ in self.calls]
