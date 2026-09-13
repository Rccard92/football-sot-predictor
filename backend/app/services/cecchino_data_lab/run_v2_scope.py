"""Regole di perimetro condivise dalle analisi Pattern Insights.

- Divisioni: le leghe maggiori sono prezzate con piu' attenzione dai
  bookmaker, le inferiori meno. Le analisi le tengono sempre separate.
- Stagione sotto chiave: il 2025/26 e' l'unico test finale pulito. Nessuna
  scoperta, verifica o analisi di mercato puo' leggerlo finche' non viene
  sbloccato esplicitamente.
"""

from __future__ import annotations

TIER_TOP = "top"
TIER_LOWER = "lower"
TIERS = (TIER_TOP, TIER_LOWER)

TIER_LABELS = {
    TIER_TOP: "Prime divisioni",
    TIER_LOWER: "Divisioni inferiori",
}

TOP_TIER_COMPETITIONS = frozenset(
    {
        "Serie A",
        "Premier League",
        "La Liga",
        "Bundesliga",
        "Ligue 1",
        "Eredivisie",
        "Jupiler Pro League",
        "Primeira Liga",
        "Süper Lig",
    }
)

LOCKBOX_SEASON = "2025/2026"


def tier_of(competition: str | None) -> str:
    return TIER_TOP if competition in TOP_TIER_COMPETITIONS else TIER_LOWER


def is_lockbox_season(season_label: str | None) -> bool:
    return bool(season_label) and str(season_label) >= LOCKBOX_SEASON
