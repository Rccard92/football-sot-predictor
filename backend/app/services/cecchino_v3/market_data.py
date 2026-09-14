"""Caricamento condiviso di previsioni V3 e quote per mercato (una riga per partita e mercato)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.run_v2_scope import tier_of
from app.services.cecchino_v3.constants import LOCKBOX, MARKET_KEYS
from app.services.cecchino_v3.data import MatchRecord, load_matches
from app.services.cecchino_v3.evaluator import MarketRow, book_probabilities
from app.services.cecchino_v3.markets import market_outcomes
from app.services.cecchino_v3.patterns import OpeningQuote

# Quota di chiusura per 1X2 e Over/Under 2.5; per gli altri mercati l'ultima quota rilevata.
CLOSING_ODDS_COLUMNS: dict[str, str] = {
    "home": "bet365_closing_home",
    "draw": "bet365_closing_draw",
    "away": "bet365_closing_away",
    "over_25": "bet365_closing_over_25",
    "under_25": "bet365_closing_under_25",
    "over_05": "bet365_over_05",
    "under_05": "bet365_under_05",
    "over_15": "bet365_over_15",
    "under_15": "bet365_under_15",
    "over_35": "bet365_over_35",
    "under_35": "bet365_under_35",
    "ht_home": "bet365_ht_home",
    "ht_draw": "bet365_ht_draw",
    "ht_away": "bet365_ht_away",
    "dc_1x": "bet365_dc_1x",
    "dc_x2": "bet365_dc_x2",
    "dc_12": "bet365_dc_12",
}
OPENING_ODDS_COLUMNS: dict[str, str] = {
    "home": "bet365_home",
    "draw": "bet365_draw",
    "away": "bet365_away",
    "over_25": "bet365_over_25",
    "under_25": "bet365_under_25",
}
OPENING_MARKETS: tuple[str, ...] = ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5")


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _odds_by_match(db: Session, run_id: int, columns: dict[str, str]) -> dict[int, dict[str, float | None]]:
    select_list = ", ".join(f"m.{col} AS {key}" for key, col in columns.items())
    out: dict[int, dict[str, float | None]] = {}
    for r in db.execute(
        text(
            f"""
            SELECT m.id, {select_list}
            FROM cecchino_lab_matches m
            JOIN cecchino_v3_match_predictions mp ON mp.lab_match_id = m.id AND mp.run_id = :run_id
            """
        ),
        {"run_id": run_id},
    ):
        data = dict(r._mapping)
        out[int(data.pop("id"))] = {k: _float(v) for k, v in data.items()}
    return out


def load_market_rows(
    db: Session,
    run_id: int,
    *,
    include_lockbox: bool = False,
    market_keys: Sequence[str] | None = None,
    matches: dict[int, MatchRecord] | None = None,
) -> list[MarketRow]:
    """Righe partita x mercato con probabilita' V3, quota e probabilita' del book senza margine."""
    if matches is None:
        matches = {m.lab_match_id: m for m in load_matches(db, include_lockbox=include_lockbox)}
    keys = tuple(market_keys) if market_keys is not None else MARKET_KEYS
    probabilities: dict[int, dict[str, float]] = {}
    for r in db.execute(
        text(
            """
            SELECT mk.lab_match_id, mk.market_key, mk.probability
            FROM cecchino_v3_market_predictions mk
            WHERE mk.run_id = :run_id AND mk.market_key = ANY(:keys)
            """
        ),
        {"run_id": run_id, "keys": list(keys)},
    ):
        probabilities.setdefault(int(r.lab_match_id), {})[r.market_key] = float(r.probability)

    odds_by_match = _odds_by_match(db, run_id, CLOSING_ODDS_COLUMNS)
    rows: list[MarketRow] = []
    for mid in sorted(probabilities):
        m = matches.get(mid)
        odds = odds_by_match.get(mid)
        if m is None or odds is None or m.season_label > LOCKBOX or (m.season_label == LOCKBOX and not include_lockbox):
            continue
        book = book_probabilities(odds)
        outcomes = market_outcomes(m.ft_home, m.ft_away, m.ht_home, m.ht_away)
        tier = tier_of(m.competition)
        for key in keys:
            p_v3 = probabilities[mid].get(key)
            won = outcomes.get(key)
            if p_v3 is None or won is None or key not in book:
                continue
            quoted, p_book = book[key]
            rows.append(
                MarketRow(
                    lab_match_id=mid,
                    season_label=m.season_label,
                    competition=m.competition,
                    tier=tier,
                    match_date=m.match_date,
                    phase=m.phase,
                    eligible=m.eval_eligible,
                    home_team=m.home_team,
                    away_team=m.away_team,
                    market_key=key,
                    p_v3=p_v3,
                    p_book=p_book,
                    odds=quoted,
                    won=bool(won),
                )
            )
    rows.sort(key=lambda r: (r.match_date, r.lab_match_id, r.market_key))
    return rows


def load_opening(db: Session, run_id: int) -> dict[tuple[int, str], OpeningQuote]:
    """(partita, mercato) -> quota di apertura e probabilita' di apertura senza margine."""
    out: dict[tuple[int, str], OpeningQuote] = {}
    for mid, odds in _odds_by_match(db, run_id, OPENING_ODDS_COLUMNS).items():
        for market, (quoted, p_book) in book_probabilities(odds).items():
            if market in OPENING_MARKETS:
                out[(mid, market)] = OpeningQuote(odds=quoted, p_book=p_book)
    return out
