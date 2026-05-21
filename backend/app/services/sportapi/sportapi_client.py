"""Client HTTP SportAPI7 su RapidAPI — isolato, non usato dal prediction engine."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings, sportapi_configured
from app.services.sportapi import sportapi_paths

logger = logging.getLogger(__name__)

TRANSIENT_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 2
BACKOFF_BASE_S = 0.5
DEFAULT_TIMEOUT_S = 30.0


class SportApiError(Exception):
    """Errore chiamata SportAPI (HTTP o payload)."""


class SportApiDisabledError(SportApiError):
    """SportAPI disabilitata o chiave assente."""


class SportApiClient:
    """Client RapidAPI per SportAPI7. Non invocare se SPORTAPI_ENABLED=false."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        host: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        force_enabled: bool = False,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.sportapi_base_url).rstrip("/") + "/"
        self._api_key = api_key if api_key is not None else settings.sportapi_rapidapi_key
        self._host = host if host is not None else settings.sportapi_rapidapi_host
        self._timeout = timeout_s
        self._force_enabled = force_enabled

    def _ensure_enabled(self) -> None:
        if self._force_enabled:
            return
        if not sportapi_configured():
            raise SportApiDisabledError(
                "SportAPI disabilitata (SPORTAPI_ENABLED=false) o SPORTAPI_RAPIDAPI_KEY assente",
            )
        if not (self._api_key or "").strip():
            raise SportApiDisabledError("SPORTAPI_RAPIDAPI_KEY non configurata")

    def _headers(self) -> dict[str, str]:
        return {
            "X-RapidAPI-Key": (self._api_key or "").strip(),
            "X-RapidAPI-Host": (self._host or "").strip(),
        }

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_enabled()
        rel = path.lstrip("/")
        url = urljoin(self._base_url, rel)
        query = {k: v for k, v in (params or {}).items() if v is not None}
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.get(url, params=query, headers=self._headers())
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.info(
                    "sportapi GET %s status=%s ms=%s attempt=%s",
                    rel,
                    resp.status_code,
                    elapsed_ms,
                    attempt,
                )

                if resp.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                    wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
                    if resp.status_code == 429:
                        ra = resp.headers.get("Retry-After")
                        if ra and str(ra).isdigit():
                            wait = float(ra)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response is not None and e.response.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                logger.warning(
                    "sportapi HTTP error %s path=%s",
                    e.response.status_code if e.response else "?",
                    rel,
                )
                raise SportApiError(
                    f"HTTP {e.response.status_code if e.response else 'error'}: {rel}",
                ) from e
            except httpx.RequestError as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                logger.exception("sportapi request failed path=%s", rel)
                raise SportApiError("Errore di rete verso SportAPI") from e

        raise SportApiError("Ritentativi SportAPI esauriti") from last_exc

    def get_scheduled_events(self, date: str) -> Any:
        """date: YYYY-MM-DD."""
        return self.get(sportapi_paths.scheduled_events_path(date))

    def get_event(self, event_id: int) -> Any:
        return self.get(sportapi_paths.event_path(event_id))

    def get_lineups(self, event_id: int) -> Any:
        return self.get(sportapi_paths.lineups_path(event_id))

    def get_event_odds(self, event_id: int, provider_id: int = 1) -> Any:
        """GET /api/v1/event/{event_id}/odds/{provider_id}/all"""
        path = sportapi_paths.event_odds_path(event_id, provider_id)
        try:
            return self.get(path)
        except SportApiError as exc:
            msg = str(exc)
            if "404" in msg:
                raise SportApiError(
                    f"Quote SportAPI non trovate per event_id={int(event_id)} provider_id={int(provider_id)}",
                ) from exc
            raise
