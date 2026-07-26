"""Catalogo canonico campionati Cecchino Lab (Football-Data), isolato dalle competizioni operative."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LabCompetition:
    key: str
    display_name: str
    country: str
    division_code: str
    timezone: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_COMPETITIONS: tuple[LabCompetition, ...] = (
    LabCompetition(
        key="premier_league",
        display_name="Premier League",
        country="England",
        division_code="E0",
        timezone="Europe/London",
    ),
    LabCompetition(
        key="championship",
        display_name="Championship",
        country="England",
        division_code="E1",
        timezone="Europe/London",
    ),
    LabCompetition(
        key="league_one",
        display_name="League One",
        country="England",
        division_code="E2",
        timezone="Europe/London",
    ),
    LabCompetition(
        key="league_two",
        display_name="League Two",
        country="England",
        division_code="E3",
        timezone="Europe/London",
    ),
    LabCompetition(
        key="serie_a",
        display_name="Serie A",
        country="Italy",
        division_code="I1",
        timezone="Europe/Rome",
    ),
    LabCompetition(
        key="serie_b",
        display_name="Serie B",
        country="Italy",
        division_code="I2",
        timezone="Europe/Rome",
    ),
    LabCompetition(
        key="la_liga",
        display_name="La Liga",
        country="Spain",
        division_code="SP1",
        timezone="Europe/Madrid",
    ),
    LabCompetition(
        key="la_liga_2",
        display_name="La Liga 2",
        country="Spain",
        division_code="SP2",
        timezone="Europe/Madrid",
    ),
    LabCompetition(
        key="bundesliga",
        display_name="Bundesliga",
        country="Germany",
        division_code="D1",
        timezone="Europe/Berlin",
    ),
    LabCompetition(
        key="bundesliga_2",
        display_name="Bundesliga 2",
        country="Germany",
        division_code="D2",
        timezone="Europe/Berlin",
    ),
    LabCompetition(
        key="ligue_1",
        display_name="Ligue 1",
        country="France",
        division_code="F1",
        timezone="Europe/Paris",
    ),
    LabCompetition(
        key="ligue_2",
        display_name="Ligue 2",
        country="France",
        division_code="F2",
        timezone="Europe/Paris",
    ),
    LabCompetition(
        key="eredivisie",
        display_name="Eredivisie",
        country="Netherlands",
        division_code="N1",
        timezone="Europe/Amsterdam",
    ),
    LabCompetition(
        key="jupiler_pro_league",
        display_name="Jupiler Pro League",
        country="Belgium",
        division_code="B1",
        timezone="Europe/Brussels",
    ),
    LabCompetition(
        key="primeira_liga",
        display_name="Primeira Liga",
        country="Portugal",
        division_code="P1",
        timezone="Europe/Lisbon",
    ),
    LabCompetition(
        key="super_lig",
        display_name="Süper Lig",
        country="Turkey",
        division_code="T1",
        timezone="Europe/Istanbul",
    ),
)

_BY_KEY: dict[str, LabCompetition] = {c.key: c for c in _COMPETITIONS}


def get_competition(key: str) -> LabCompetition | None:
    if not key:
        return None
    return _BY_KEY.get(key.strip())


def list_competitions() -> list[LabCompetition]:
    return sorted(_COMPETITIONS, key=lambda c: (c.country.lower(), c.display_name.lower()))


def list_competitions_dicts() -> list[dict[str, Any]]:
    return [c.to_dict() for c in list_competitions()]
