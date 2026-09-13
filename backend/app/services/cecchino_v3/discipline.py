"""Specialista Disciplina: falli, cartellini e arbitro.

Tutto misurato rispetto alla media della divisione e solo con partite dei
giorni PRECEDENTI a quello da prevedere.

Squadre (partite della stagione in corso), con conteggio a priori di
DISCIPLINE_PSEUDO_MATCHES partite "nella media":
    indice(squadra) = log( (somma squadra + k * media) / ((partite + k) * media) )

Correzioni per il lato che attacca:
    fouls_attack  = indice falli di chi attacca
    fouls_defence = indice falli di chi difende (piu' falli -> piu' piazzati/rigori)
    cards_defence = indice cartellini di chi difende (giallo 1, rosso 2)
    referee_goals = gol nelle partite passate dell'arbitro rispetto ai gol attesi
                    dal modello (senza forma), con REFEREE_PSEUDO_GOALS a priori;
                    0 dove l'arbitro non e' nei dati (fuori dall'Inghilterra).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.services.cecchino_v3.constants import (
    DISCIPLINE_PRIOR_CARDS,
    DISCIPLINE_PRIOR_FOULS,
    DISCIPLINE_PSEUDO_MATCHES,
    REFEREE_PSEUDO_GOALS,
)
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.form import Expectation


@dataclass(frozen=True)
class DisciplineFeatures:
    adjust_home: dict[str, float]
    adjust_away: dict[str, float]
    detail: dict[str, float | str | None] = field(default_factory=dict)


@dataclass
class _Totals:
    fouls: float = 0.0
    fouls_n: int = 0
    cards: float = 0.0
    cards_n: int = 0


def _cards(yellow: int | None, red: int | None) -> float | None:
    if yellow is None or red is None:
        return None
    return float(yellow) + 2.0 * float(red)


def _index(total: float, n: int, average: float) -> float:
    k = DISCIPLINE_PSEUDO_MATCHES
    return math.log((total + k * average) / ((n + k) * average))


def _division_average(totals: _Totals, *, prior_fouls: float, prior_cards: float) -> tuple[float, float]:
    """Media per squadra-partita della divisione, partendo da un valore a priori
    che pesa come DISCIPLINE_PSEUDO_MATCHES partite."""
    k = DISCIPLINE_PSEUDO_MATCHES
    fouls = (totals.fouls + k * prior_fouls) / (totals.fouls_n + k)
    cards = (totals.cards + k * prior_cards) / (totals.cards_n + k)
    return fouls, cards


def compute_discipline(
    matches: list[MatchRecord], expectations: dict[int, Expectation]
) -> dict[int, DisciplineFeatures]:
    """Correzioni di disciplina per ogni partita (ordinate cronologicamente).
    I dati del giorno entrano nelle medie solo dopo aver previsto quel giorno."""
    division: dict[tuple[str, str], _Totals] = {}
    team: dict[tuple[str, str, str], _Totals] = {}
    referee: dict[tuple[str, str], list[float]] = {}  # (gruppo, arbitro) -> [gol, gol attesi]
    out: dict[int, DisciplineFeatures] = {}

    n = len(matches)
    i = 0
    while i < n:
        j = i
        while j < n and matches[j].day == matches[i].day:
            j += 1
        day = matches[i:j]

        for m in day:
            div = division.get((m.group, m.competition), _Totals())
            avg_fouls, avg_cards = _division_average(
                div, prior_fouls=DISCIPLINE_PRIOR_FOULS, prior_cards=DISCIPLINE_PRIOR_CARDS
            )
            home = team.get((m.group, m.season_label, m.home_team), _Totals())
            away = team.get((m.group, m.season_label, m.away_team), _Totals())
            fouls_home = _index(home.fouls, home.fouls_n, avg_fouls)
            fouls_away = _index(away.fouls, away.fouls_n, avg_fouls)
            cards_home = _index(home.cards, home.cards_n, avg_cards)
            cards_away = _index(away.cards, away.cards_n, avg_cards)

            ref_name = (m.referee or "").strip() or None
            ref_goals = 0.0
            if ref_name is not None:
                goals, expected = referee.get((m.group, ref_name), [0.0, 0.0])
                ref_goals = math.log((goals + REFEREE_PSEUDO_GOALS) / (expected + REFEREE_PSEUDO_GOALS))

            out[m.lab_match_id] = DisciplineFeatures(
                adjust_home={
                    "fouls_attack": fouls_home,
                    "fouls_defence": fouls_away,
                    "cards_defence": cards_away,
                    "referee_goals": ref_goals,
                },
                adjust_away={
                    "fouls_attack": fouls_away,
                    "fouls_defence": fouls_home,
                    "cards_defence": cards_home,
                    "referee_goals": ref_goals,
                },
                detail={
                    "fouls_index_home": round(fouls_home, 4),
                    "fouls_index_away": round(fouls_away, 4),
                    "cards_index_home": round(cards_home, 4),
                    "cards_index_away": round(cards_away, 4),
                    "referee": ref_name,
                    "referee_goals_index": round(ref_goals, 4),
                },
            )

        for m in day:
            div = division.setdefault((m.group, m.competition), _Totals())
            for side_team, fouls, cards in (
                (m.home_team, m.home_fouls, _cards(m.home_yellow, m.home_red)),
                (m.away_team, m.away_fouls, _cards(m.away_yellow, m.away_red)),
            ):
                totals = team.setdefault((m.group, m.season_label, side_team), _Totals())
                if fouls is not None:
                    totals.fouls += fouls
                    totals.fouls_n += 1
                    div.fouls += fouls
                    div.fouls_n += 1
                if cards is not None:
                    totals.cards += cards
                    totals.cards_n += 1
                    div.cards += cards
                    div.cards_n += 1
            ref_name = (m.referee or "").strip() or None
            exp = expectations.get(m.lab_match_id)
            if ref_name is not None and exp is not None:
                acc = referee.setdefault((m.group, ref_name), [0.0, 0.0])
                acc[0] += m.ft_home + m.ft_away
                acc[1] += exp.goals_home + exp.goals_away
        i = j
    return out
