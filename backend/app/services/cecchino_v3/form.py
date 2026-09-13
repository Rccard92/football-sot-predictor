"""Specialista Forma: rendimento recente rispetto a quanto atteso.

Per ogni squadra, le ultime FORM_MATCHES partite della stagione in corso
giocate in giorni PRECEDENTI a quello da prevedere. Per ciascuna si confronta
il risultato con l'attesa calcolata prima di quella partita (quindi gia'
corretta per l'avversario), senza la forma stessa: nessun circolo.

    rapporto = (fatto + c) / (atteso + c)     c = conteggio a priori

In scala logaritmica: 0 = in linea con le attese, positivo = sopra le attese.
Per la squadra di casa:
    correzione gol = log rapporto gol fatti (casa) + log rapporto gol subiti (ospite)
cioe' attacco in forma di chi segna e difesa in crisi di chi subisce.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

from app.services.cecchino_v3.constants import FORM_MATCHES, FORM_PSEUDO_COUNT
from app.services.cecchino_v3.data import MatchRecord


@dataclass(frozen=True)
class Expectation:
    """Attese pre-partita (senza forma) per una partita gia' prevista."""

    goals_home: float
    goals_away: float
    shots_home: float | None
    shots_away: float | None


@dataclass(frozen=True)
class FormFeatures:
    goals_home: float  # correzione logaritmica sui gol attesi di casa
    goals_away: float
    shots_home: float
    shots_away: float
    matches_home: int  # partite usate per la forma
    matches_away: int
    # dettaglio per squadra (log rapporti), per la lettura partita per partita
    detail: dict[str, float] = field(default_factory=dict)


@dataclass
class _Entry:
    goals_for: float
    goals_expected_for: float
    goals_against: float
    goals_expected_against: float
    shots_for: float | None
    shots_expected_for: float | None
    shots_against: float | None
    shots_expected_against: float | None


def _log_ratio(done: float, expected: float, pseudo: float) -> float:
    return math.log((done + pseudo) / (expected + pseudo))


@dataclass(frozen=True)
class _TeamForm:
    attack_goals: float
    defence_goals: float  # positivo = subisce piu' del previsto
    attack_shots: float
    defence_shots: float
    matches: int


def _team_form(history: deque[_Entry]) -> _TeamForm:
    pg, ps = FORM_PSEUDO_COUNT["goals"], FORM_PSEUDO_COUNT["shots"]
    gf = sum(e.goals_for for e in history)
    gef = sum(e.goals_expected_for for e in history)
    ga = sum(e.goals_against for e in history)
    gea = sum(e.goals_expected_against for e in history)
    with_shots = [e for e in history if e.shots_for is not None]
    sf = sum(e.shots_for or 0.0 for e in with_shots)
    sef = sum(e.shots_expected_for or 0.0 for e in with_shots)
    sa = sum(e.shots_against or 0.0 for e in with_shots)
    sea = sum(e.shots_expected_against or 0.0 for e in with_shots)
    return _TeamForm(
        attack_goals=_log_ratio(gf, gef, pg),
        defence_goals=_log_ratio(ga, gea, pg),
        attack_shots=_log_ratio(sf, sef, ps),
        defence_shots=_log_ratio(sa, sea, ps),
        matches=len(history),
    )


def compute_form(
    matches: list[MatchRecord], expectations: dict[int, Expectation]
) -> dict[int, FormFeatures]:
    """Forma per ogni partita (ordinate cronologicamente). Le partite dello
    stesso giorno non entrano l'una nella forma dell'altra."""
    histories: dict[tuple[str, str, str], deque[_Entry]] = {}
    out: dict[int, FormFeatures] = {}

    def history(m: MatchRecord, team: str) -> deque[_Entry]:
        key = (m.group, m.season_label, team)
        if key not in histories:
            histories[key] = deque(maxlen=FORM_MATCHES)
        return histories[key]

    n = len(matches)
    i = 0
    while i < n:
        j = i
        while j < n and matches[j].day == matches[i].day:
            j += 1
        day = matches[i:j]

        for m in day:
            home = _team_form(history(m, m.home_team))
            away = _team_form(history(m, m.away_team))
            out[m.lab_match_id] = FormFeatures(
                goals_home=home.attack_goals + away.defence_goals,
                goals_away=away.attack_goals + home.defence_goals,
                shots_home=home.attack_shots + away.defence_shots,
                shots_away=away.attack_shots + home.defence_shots,
                matches_home=home.matches,
                matches_away=away.matches,
                detail={
                    "home_attack_goals": round(home.attack_goals, 4),
                    "home_defence_goals": round(home.defence_goals, 4),
                    "away_attack_goals": round(away.attack_goals, 4),
                    "away_defence_goals": round(away.defence_goals, 4),
                    "home_attack_shots": round(home.attack_shots, 4),
                    "home_defence_shots": round(home.defence_shots, 4),
                    "away_attack_shots": round(away.attack_shots, 4),
                    "away_defence_shots": round(away.defence_shots, 4),
                },
            )

        # solo ora i risultati del giorno entrano nella storia
        for m in day:
            exp = expectations.get(m.lab_match_id)
            if exp is None:
                continue
            shots_ok = (
                m.home_shots is not None
                and m.away_shots is not None
                and exp.shots_home is not None
                and exp.shots_away is not None
            )
            history(m, m.home_team).append(
                _Entry(
                    goals_for=float(m.ft_home),
                    goals_expected_for=exp.goals_home,
                    goals_against=float(m.ft_away),
                    goals_expected_against=exp.goals_away,
                    shots_for=float(m.home_shots) if shots_ok else None,
                    shots_expected_for=exp.shots_home if shots_ok else None,
                    shots_against=float(m.away_shots) if shots_ok else None,
                    shots_expected_against=exp.shots_away if shots_ok else None,
                )
            )
            history(m, m.away_team).append(
                _Entry(
                    goals_for=float(m.ft_away),
                    goals_expected_for=exp.goals_away,
                    goals_against=float(m.ft_home),
                    goals_expected_against=exp.goals_home,
                    shots_for=float(m.away_shots) if shots_ok else None,
                    shots_expected_for=exp.shots_away if shots_ok else None,
                    shots_against=float(m.home_shots) if shots_ok else None,
                    shots_expected_against=exp.shots_home if shots_ok else None,
                )
            )
        i = j
    return out
