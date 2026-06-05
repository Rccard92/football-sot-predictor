from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TRANSIENT_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_BASE_S = 0.5


class ApiFootballError(Exception):
    """Errore chiamata API-Football (HTTP o payload)."""


class ApiFootballClient:
    """Client HTTP per API-Sports / API-Football v3."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.api_football_base_url).rstrip("/") + "/"
        self._api_key = api_key if api_key is not None else settings.api_football_key
        self._timeout = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self._api_key}

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not (self._api_key or "").strip():
            raise ApiFootballError("API_FOOTBALL_KEY non configurata")

        path = endpoint.lstrip("/")
        url = urljoin(self._base_url, path)
        query = {k: v for k, v in (params or {}).items() if v is not None}
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.get(url, params=query, headers=self._headers())
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "api_football GET %s status=%s ms=%s attempt=%s params=%s",
                    path,
                    resp.status_code,
                    elapsed_ms,
                    attempt,
                    list(query.keys()),
                )

                if resp.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
                    if resp.status_code == 429:
                        ra = resp.headers.get("Retry-After")
                        if ra and ra.isdigit():
                            wait = float(ra)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                errors = data.get("errors")
                if errors:
                    raise ApiFootballError(f"API errors: {errors}")
                return data
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response is not None and e.response.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
                    time.sleep(wait)
                    continue
                logger.warning(
                    "api_football HTTP error %s",
                    e.response.status_code if e.response else "?",
                )
                raise ApiFootballError(
                    f"HTTP {e.response.status_code if e.response else 'error'}",
                ) from e
            except httpx.RequestError as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                logger.exception("api_football request failed")
                raise ApiFootballError("Errore di rete verso API-Football") from e

        raise ApiFootballError("Ritentativi esauriti") from last_exc

    def get_all_pages(self, endpoint: str, params: dict[str, Any] | None = None) -> list[Any]:
        base_params = dict(params or {})
        page = int(base_params.pop("page", 1))
        merged: list[Any] = []

        while True:
            body = self.get(endpoint, {**base_params, "page": page})
            merged.extend(body.get("response") or [])
            paging = body.get("paging") or {}
            current = int(paging.get("current") or page)
            total = int(paging.get("total") or 1)
            if current >= total:
                break
            page = current + 1

        return merged

    def get_league(self, country: str, search: str, season: int) -> list[dict[str, Any]]:
        from app.services.competition_discover_helpers import build_leagues_query_params

        params = build_leagues_query_params(country, search, season)
        return self.get_all_pages("leagues", params)

    def get_teams(self, league_id: int, season: int) -> list[dict[str, Any]]:
        """GET /teams (singola richiesta; l'API non accetta paginazione `page`)."""
        body = self.get("teams", {"league": league_id, "season": season})
        return list(body.get("response") or [])

    def get_fixtures(self, league_id: int, season: int, status: str | None = None) -> list[dict[str, Any]]:
        """GET /fixtures (singola richiesta; senza parametro `page`)."""
        body = self.get("fixtures", {"league": league_id, "season": season, "status": status})
        return list(body.get("response") or [])

    def get_fixtures_by_date(
        self,
        date: str,
        timezone: str = "Europe/Rome",
    ) -> list[dict[str, Any]]:
        """GET /fixtures?date=YYYY-MM-DD — partite del giorno."""
        body = self.get("fixtures", {"date": date, "timezone": timezone})
        return list(body.get("response") or [])

    def get_fixture_by_id(self, api_fixture_id: int) -> dict[str, Any] | None:
        """GET /fixtures?id={api_fixture_id} — dettaglio singola partita."""
        body = self.get("fixtures", {"id": int(api_fixture_id)})
        items = body.get("response") or []
        if not items:
            return None
        first = items[0]
        return first if isinstance(first, dict) else None

    def get_fixture_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/statistics", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_fixture_events(self, fixture_id: int) -> list[dict[str, Any]]:
        """GET /fixtures/events — cartellini per squadra/giocatore."""
        body = self.get("fixtures/events", {"fixture": int(fixture_id)})
        return list(body.get("response") or [])

    def get_fixture_players(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/players", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_player_squads(self, team_api_id: int) -> list[dict[str, Any]]:
        """GET /players/squads — una o più entry {team, players}."""
        body = self.get("players/squads", {"team": team_api_id})
        return list(body.get("response") or [])

    def get_fixture_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/lineups", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_odds_bookmakers(self) -> list[dict[str, Any]]:
        """GET /odds/bookmakers — elenco bookmaker disponibili su API-Sports."""
        body = self.get("odds/bookmakers")
        return list(body.get("response") or [])

    def get_fixture_odds(
        self,
        api_fixture_id: int,
        bookmaker_id: int,
    ) -> list[dict[str, Any]]:
        """GET /odds — quote per fixture e bookmaker (API-Football)."""
        body = self.get(
            "odds",
            {"fixture": int(api_fixture_id), "bookmaker": int(bookmaker_id)},
        )
        return list(body.get("response") or [])

    def get_fixture_odds_by_fixture(self, api_fixture_id: int) -> list[dict[str, Any]]:
        """GET /odds — quote per fixture (tutti i bookmaker nel payload)."""
        body = self.get("odds", {"fixture": int(api_fixture_id)})
        return list(body.get("response") or [])

    @staticmethod
    def injuries_response_items(body: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        """Normalizza response injuries + eventuali errori nel body."""
        errs = body.get("errors")
        err_list: list[Any] = []
        if errs:
            if isinstance(errs, dict):
                err_list = [f"{k}: {v}" for k, v in errs.items()]
            elif isinstance(errs, list):
                err_list = list(errs)
            else:
                err_list = [str(errs)]
        items = body.get("response") or []
        if not isinstance(items, list):
            items = []
        return [x for x in items if isinstance(x, dict)], err_list

    def get_injuries(self, league: int, season: int) -> list[dict[str, Any]]:
        """league = API-Football api_league_id (es. 135 Serie A), non leagues.id interno."""
        body = self.get("injuries", {"league": league, "season": season})
        items, _ = self.injuries_response_items(body)
        return items

    def get_injuries_by_fixture(self, api_fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("injuries", {"fixture": int(api_fixture_id)})
        items, _ = self.injuries_response_items(body)
        return items

    def get_injuries_by_ids(
        self,
        api_fixture_ids: list[int],
        *,
        chunk_size: int = 20,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """GET injuries?ids=1-2-3 — batch fixture API ids. Ritorna (items, error_messages)."""
        ids = [int(x) for x in api_fixture_ids if x is not None]
        if not ids:
            return [], []
        out: list[dict[str, Any]] = []
        errors: list[str] = []
        for i in range(0, len(ids), int(chunk_size)):
            chunk = ids[i : i + int(chunk_size)]
            ids_param = "-".join(str(x) for x in chunk)
            try:
                body = self.get("injuries", {"ids": ids_param})
                items, errs = self.injuries_response_items(body)
                out.extend(items)
                errors.extend(errs)
            except ApiFootballError as exc:
                errors.append(str(exc)[:500])
        return out, errors

    def get_injuries_by_team(self, league: int, season: int, team: int) -> list[dict[str, Any]]:
        """league = api_league_id; team = api_team_id."""
        body = self.get("injuries", {"league": league, "season": season, "team": int(team)})
        items, _ = self.injuries_response_items(body)
        return items

    def get_sidelined_by_player(self, api_player_id: int) -> list[dict[str, Any]]:
        try:
            body = self.get("sidelined", {"player": int(api_player_id)})
            items, errs = self.injuries_response_items(body)
            if errs:
                logger.warning(
                    "sidelined player=%s parse warnings: %s",
                    api_player_id,
                    errs[:3],
                )
            return items if isinstance(items, list) else []
        except ApiFootballError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "get_sidelined_by_player player=%s failed: %s",
                api_player_id,
                exc,
            )
            return []

    def get_league_season_coverage(self, league_id: int, season: int) -> dict[str, Any]:
        """GET /leagues?id=&season= — league_id = api_league_id API-Football."""
        body = self.get("leagues", {"id": int(league_id), "season": int(season)})
        items = list(body.get("response") or [])
        if not items:
            return {}
        picked = items[0] if isinstance(items[0], dict) else {}
        seasons = picked.get("seasons") or []
        if not isinstance(seasons, list):
            return {}
        for s in seasons:
            if not isinstance(s, dict):
                continue
            if int(s.get("year") or 0) == int(season):
                cov = s.get("coverage")
                return dict(cov) if isinstance(cov, dict) else {}
        cov = picked.get("coverage")
        return dict(cov) if isinstance(cov, dict) else {}

    def get_head_to_head(self, team_a_api_id: int, team_b_api_id: int) -> list[dict[str, Any]]:
        h2h = f"{team_a_api_id}-{team_b_api_id}"
        body = self.get("fixtures/headtohead", {"h2h": h2h})
        return list(body.get("response") or [])

    def get_standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        body = self.get("standings", {"league": league_id, "season": season})
        errors = body.get("errors")
        if errors:
            raise ApiFootballError(f"API errors: {errors}")
        return list(body.get("response") or [])
