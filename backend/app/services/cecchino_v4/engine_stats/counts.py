"""Conteggi delle statistiche per partita a partire da MatchRecord + MatchExtras."""

from __future__ import annotations

from app.services.cecchino_v3.data import MatchRecord

from app.services.cecchino_v4.constants import CARD_WEIGHT_RED, CARD_WEIGHT_YELLOW
from app.services.cecchino_v4.history.football_data import MatchExtras


def stat_pair(m: MatchRecord, extras: MatchExtras | None, stat: str) -> tuple[float | None, float | None]:
    """(casa, ospite) della statistica; None se manca uno dei due lati."""
    if stat == "shots":
        h, a = m.home_shots, m.away_shots
    elif stat == "sot":
        h, a = m.home_sot, m.away_sot
    elif stat == "fouls":
        h, a = m.home_fouls, m.away_fouls
    elif stat == "corners":
        if extras is None:
            return None, None
        h, a = extras.home_corners, extras.away_corners
    elif stat == "cards":
        if m.home_yellow is None or m.away_yellow is None:
            return None, None
        h = CARD_WEIGHT_YELLOW * m.home_yellow + CARD_WEIGHT_RED * (m.home_red or 0)
        a = CARD_WEIGHT_YELLOW * m.away_yellow + CARD_WEIGHT_RED * (m.away_red or 0)
        return float(h), float(a)
    else:
        raise ValueError(f"statistica sconosciuta: {stat!r}")
    if h is None or a is None:
        return None, None
    return float(h), float(a)
