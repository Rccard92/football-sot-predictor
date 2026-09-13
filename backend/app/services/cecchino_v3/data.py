"""Base comune pre-partita: partite storiche pulite e contesto di stagione.

La stagione sotto chiave non viene mai caricata. Il contesto di stagione
(partite gia' giocate, partite rimanenti) usa solo il calendario, che e'
noto prima della partita: non contiene risultati futuri.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_v3.constants import (
    FINAL_PHASE_MATCHES,
    LOCKBOX,
    MIN_MATCHES_PLAYED,
    PHASE_EARLY,
    PHASE_FINAL,
    PHASE_MID,
    group_of,
)

_EPOCH = date(2000, 1, 1)


@dataclass
class MatchRecord:
    lab_match_id: int
    competition: str
    group: str
    season_label: str
    match_date: date
    kickoff_at: datetime | None
    day: int
    home_team: str
    away_team: str
    ft_home: int
    ft_away: int
    ht_home: int | None
    ht_away: int | None
    home_shots: int | None = None
    away_shots: int | None = None
    home_sot: int | None = None  # tiri in porta
    away_sot: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None
    home_yellow: int | None = None
    away_yellow: int | None = None
    home_red: int | None = None
    away_red: int | None = None
    referee: str | None = None
    # contesto di stagione (stesso campionato)
    home_played: int = 0
    away_played: int = 0
    home_remaining: int = 0
    away_remaining: int = 0
    phase: str = PHASE_EARLY
    eval_eligible: bool = False


def load_matches(db: Session) -> list[MatchRecord]:
    """Tutte le partite con risultato delle stagioni precedenti alla chiave,
    in ordine cronologico."""
    rows = db.execute(
        select(
            CecchinoLabMatch.id,
            CecchinoLabDataset.competition_name,
            CecchinoLabDataset.season_label,
            CecchinoLabMatch.match_date,
            CecchinoLabMatch.kickoff_at,
            CecchinoLabMatch.home_team,
            CecchinoLabMatch.away_team,
            CecchinoLabMatch.ft_home_goals,
            CecchinoLabMatch.ft_away_goals,
            CecchinoLabMatch.ht_home_goals,
            CecchinoLabMatch.ht_away_goals,
            CecchinoLabMatch.home_shots,
            CecchinoLabMatch.away_shots,
            CecchinoLabMatch.home_shots_on_target,
            CecchinoLabMatch.away_shots_on_target,
            CecchinoLabMatch.home_fouls,
            CecchinoLabMatch.away_fouls,
            CecchinoLabMatch.home_yellow_cards,
            CecchinoLabMatch.away_yellow_cards,
            CecchinoLabMatch.home_red_cards,
            CecchinoLabMatch.away_red_cards,
            CecchinoLabMatch.referee,
        )
        .join(CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabMatch.dataset_id)
        .where(CecchinoLabDataset.season_label < LOCKBOX)
    ).all()

    matches: list[MatchRecord] = []
    for r in rows:
        if r.ft_home_goals is None or r.ft_away_goals is None or not r.home_team or not r.away_team:
            continue
        match_day = r.match_date or (r.kickoff_at.date() if r.kickoff_at else None)
        if match_day is None:
            continue
        matches.append(
            MatchRecord(
                lab_match_id=int(r.id),
                competition=r.competition_name,
                group=group_of(r.competition_name),
                season_label=r.season_label,
                match_date=match_day,
                kickoff_at=r.kickoff_at,
                day=(match_day - _EPOCH).days,
                home_team=r.home_team.strip(),
                away_team=r.away_team.strip(),
                ft_home=int(r.ft_home_goals),
                ft_away=int(r.ft_away_goals),
                ht_home=int(r.ht_home_goals) if r.ht_home_goals is not None else None,
                ht_away=int(r.ht_away_goals) if r.ht_away_goals is not None else None,
                home_shots=int(r.home_shots) if r.home_shots is not None else None,
                away_shots=int(r.away_shots) if r.away_shots is not None else None,
                home_sot=int(r.home_shots_on_target) if r.home_shots_on_target is not None else None,
                away_sot=int(r.away_shots_on_target) if r.away_shots_on_target is not None else None,
                home_fouls=_int_or_none(r.home_fouls),
                away_fouls=_int_or_none(r.away_fouls),
                home_yellow=_int_or_none(r.home_yellow_cards),
                away_yellow=_int_or_none(r.away_yellow_cards),
                home_red=_int_or_none(r.home_red_cards),
                away_red=_int_or_none(r.away_red_cards),
                referee=(r.referee or "").strip() or None,
            )
        )
    matches.sort(key=_chronological_key)
    annotate_season_context(matches)
    return matches


def _int_or_none(value: int | None) -> int | None:
    return int(value) if value is not None else None


def _chronological_key(m: MatchRecord) -> tuple:
    return (m.day, m.kickoff_at or datetime.min, m.lab_match_id)


def annotate_season_context(matches: list[MatchRecord]) -> None:
    """Partite giocate prima e rimanenti (inclusa questa) per ogni squadra,
    nello stesso campionato e stagione; poi fase e idoneita' alla valutazione."""
    by_team: dict[tuple[str, str, str], list[MatchRecord]] = {}
    for m in matches:
        by_team.setdefault((m.competition, m.season_label, m.home_team), []).append(m)
        by_team.setdefault((m.competition, m.season_label, m.away_team), []).append(m)

    position: dict[tuple[int, str], tuple[int, int]] = {}
    for (_, _, team), team_matches in by_team.items():
        team_matches.sort(key=_chronological_key)
        total = len(team_matches)
        for idx, m in enumerate(team_matches):
            position[(m.lab_match_id, team)] = (idx, total - idx)

    for m in matches:
        m.home_played, m.home_remaining = position[(m.lab_match_id, m.home_team)]
        m.away_played, m.away_remaining = position[(m.lab_match_id, m.away_team)]
        m.eval_eligible = min(m.home_played, m.away_played) >= MIN_MATCHES_PLAYED
        if not m.eval_eligible:
            m.phase = PHASE_EARLY
        elif min(m.home_remaining, m.away_remaining) <= FINAL_PHASE_MATCHES:
            m.phase = PHASE_FINAL
        else:
            m.phase = PHASE_MID


def group_matches(matches: list[MatchRecord]) -> dict[str, list[MatchRecord]]:
    out: dict[str, list[MatchRecord]] = {}
    for m in matches:
        out.setdefault(m.group, []).append(m)
    return out
