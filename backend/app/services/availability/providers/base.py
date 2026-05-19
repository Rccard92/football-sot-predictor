"""Interfaccia provider availability (predisposizione Sportmonks, ecc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models import Fixture
from app.services.availability.providers.types import NormalizedAvailabilityCandidate

SOURCE_API_FOOTBALL_INJURIES = "api_football_injuries"
SOURCE_API_FOOTBALL_SIDELINED = "api_football_sidelined"

PROVIDER_INJURIES = "api_football_injuries"
PROVIDER_SIDELINED = "api_football_sidelined"


@dataclass
class ProviderContext:
    db: Any
    season_year: int
    league_internal_id: int
    api_league_id: int
    upcoming_fixtures: list[Fixture]
    upcoming_api_fixture_ids: list[int]
    fx_by_api_id: dict[int, Fixture]
    api_client: Any = None
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProviderFetchResult:
    provider_name: str
    called: bool = True
    status: str = "success"
    candidates: list[NormalizedAvailabilityCandidate] = field(default_factory=list)
    api_calls: int = 0
    players_checked: int = 0
    raw_items_total: int = 0
    error: str | None = None


class AvailabilityProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_candidates(self, ctx: ProviderContext) -> ProviderFetchResult:
        """Recupera candidati normalizzati (non ancora filtrati per confidence)."""
