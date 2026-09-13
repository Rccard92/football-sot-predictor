"""Specialista Calendario: riposo delle squadre e fase della stagione.

Usa solo il calendario (date delle partite), noto prima del calcio d'inizio:
nessun risultato entra in queste correzioni.

Riposo = giorni dall'ultima partita della squadra nella stessa piramide,
limitato tra REST_FLOOR_DAYS e REST_CAP_DAYS (10 giorni o una pausa estiva
valgono uguale). In scala logaritmica rispetto a una settimana:
    riposo(d) = log(clamp(d) / REST_REFERENCE_DAYS)

Correzioni per il lato che attacca (casa o ospite):
    rest_attack  = riposo della squadra che attacca
    rest_defence = riposo della squadra che difende
    final_phase  = 1 nelle ultime FINAL_PHASE_MATCHES giornate, altrimenti 0

Limite noto: nel database ci sono solo le partite di campionato, quindi coppe e
partite europee non accorciano il riposo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.cecchino_v3.constants import (
    PHASE_FINAL,
    REST_CAP_DAYS,
    REST_FLOOR_DAYS,
    REST_REFERENCE_DAYS,
)
from app.services.cecchino_v3.data import MatchRecord


@dataclass(frozen=True)
class CalendarFeatures:
    rest_days_home: int | None  # None = nessuna partita precedente nel dataset
    rest_days_away: int | None
    final_phase: bool
    adjust_home: dict[str, float]
    adjust_away: dict[str, float]


def rest_score(days: int | None) -> float:
    """Riposo in scala logaritmica; senza partita precedente vale il massimo."""
    effective = REST_CAP_DAYS if days is None else min(max(days, REST_FLOOR_DAYS), REST_CAP_DAYS)
    return math.log(effective / REST_REFERENCE_DAYS)


def compute_calendar(matches: list[MatchRecord]) -> dict[int, CalendarFeatures]:
    """Correzioni di calendario per ogni partita (ordinate cronologicamente)."""
    last_day: dict[tuple[str, str], int] = {}
    out: dict[int, CalendarFeatures] = {}
    for m in matches:
        home_prev = last_day.get((m.group, m.home_team))
        away_prev = last_day.get((m.group, m.away_team))
        rest_home = m.day - home_prev if home_prev is not None else None
        rest_away = m.day - away_prev if away_prev is not None else None
        final = 1.0 if m.phase == PHASE_FINAL else 0.0
        out[m.lab_match_id] = CalendarFeatures(
            rest_days_home=rest_home,
            rest_days_away=rest_away,
            final_phase=bool(final),
            adjust_home={
                "rest_attack": rest_score(rest_home),
                "rest_defence": rest_score(rest_away),
                "final_phase": final,
            },
            adjust_away={
                "rest_attack": rest_score(rest_away),
                "rest_defence": rest_score(rest_home),
                "final_phase": final,
            },
        )
        # una squadra non gioca due volte nello stesso giorno: aggiornare subito e' sicuro
        last_day[(m.group, m.home_team)] = m.day
        last_day[(m.group, m.away_team)] = m.day
    return out
