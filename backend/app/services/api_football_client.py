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
        return self.get_all_pages(
            "leagues",
            {"country": country, "name": search, "season": season},
        )

    def get_teams(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get_all_pages(
            "teams",
            {"league": league_id, "season": season},
        )

    def get_fixtures(self, league_id: int, season: int, status: str | None = None) -> list[dict[str, Any]]:
        return self.get_all_pages(
            "fixtures",
            {"league": league_id, "season": season, "status": status},
        )

    def get_fixture_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/statistics", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_fixture_players(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/players", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_fixture_lineups(self, fixture_id: int) -> list[dict[str, Any]]:
        body = self.get("fixtures/lineups", {"fixture": fixture_id})
        return list(body.get("response") or [])

    def get_standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get_all_pages(
            "standings",
            {"league": league_id, "season": season},
        )
