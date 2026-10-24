"""Scheda V5 di una partita di Cecchino Today (dettaglio partita, accanto a V2, V2.5 e V3).

Mostra cosa vede ogni specialista: valori attesi, probabilita' delle linee principali (senza quote), poi le quote
lette dalla V4 e le linee che passerebbero la regola di decisione, e le giocate gia' in lista sigillata.
Solo lettura: non crea giocate (le crea il passo "v5" dei job V4, docs/v5/LIVE_REGOLE.md).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.cecchino_v4 import CecchinoV4Fixture, CecchinoV4Prediction
from app.models.cecchino_v5 import CecchinoV5Play
from app.services.cecchino_v4.selection.labels import market_label
from app.services.cecchino_v5.constants import (
    MIN_EDGE,
    STAT_MAX_QUOTA,
    STAT_MIN_QUOTA,
    STAT_PRUDENCE,
    STAT_SPECIALISTS,
    STATUS_OBSERVATION,
    VALID_LINES,
    VALORE_KEY,
    VALORE_LABEL,
    VALORE_MARKETS,
    VALORE_MAX_QUOTA,
    VALORE_MIN_QUOTA,
    VERSION,
    StatSpecialist,
)
from app.services.cecchino_v5.model import History, expected_counts, load_history, nb_prob_over
from app.services.cecchino_v5.pipeline import (
    BOOKMAKER_NAMES,
    Candidate,
    _best_quota,
    latest_pre_odds,
    stat_candidates,
    valore_candidates,
    valore_probability,
)

ROME = ZoneInfo("Europe/Rome")
HISTORY_TTL_SECONDS = 6 * 3600  # lo storico del Lab si aggiorna a mano 1-2 volte a settimana
LINES_TOTAL = 3
LINES_SIDE = 2

_history: tuple[float, History] | None = None
_history_lock = threading.Lock()


def cached_history(db: Session) -> History:
    global _history
    with _history_lock:
        if _history is not None and time.time() - _history[0] < HISTORY_TTL_SECONDS:
            return _history[1]
        hist = load_history(db)
        _history = (time.time(), hist)
        return hist


def _book(bk: int | None) -> str | None:
    return BOOKMAKER_NAMES.get(bk, str(bk)) if bk is not None else None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=ROME)).isoformat()


def _nearest_lines(mean: float, bounds: tuple[float, float], n: int) -> list[float]:
    lines = [bounds[0] + i for i in range(int(bounds[1] - bounds[0]) + 1)]
    return sorted(sorted(lines, key=lambda x: abs(x - mean))[:n])


def _candidate_dict(c: Candidate, f: CecchinoV4Fixture) -> dict[str, Any]:
    return {
        "market_key": c.market_key,
        "label": market_label(c.market_key, f.home_team, f.away_team),
        "probability": c.probability,
        "prob_prudent": c.prob_prudent,
        "quota": c.quota,
        "bookmaker": _book(c.bookmaker_id),
        "score": round(c.score, 3),
    }


def _stat_block(
    spec: StatSpecialist, hist: History, f: CecchinoV4Fixture, goals: dict[str, Any] | None, books: dict
) -> dict[str, Any]:
    base = {"key": spec.key, "label": spec.label, "status": spec.status}
    if not f.home_team_history or not f.away_team_history:
        return {**base, "expected": None, "reason": "Squadre non collegate allo storico del Lab.", "lines": [], "playable": []}
    exp = expected_counts(
        hist,
        spec,
        division=f.league_code,
        day=f.match_date,
        home=f.home_team_history,
        away=f.away_team_history,
        lambda_home=(goals or {}).get("lambda_home"),
        lambda_away=(goals or {}).get("lambda_away"),
        referee=f.referee,
    )
    if exp is None:
        return {**base, "expected": None, "reason": "Storico del campionato insufficiente.", "lines": [], "playable": []}
    lines = []
    for side, mean, n in (("total", exp.total, LINES_TOTAL), ("home", exp.home, LINES_SIDE), ("away", exp.away, LINES_SIDE)):
        r = spec.r_total if side == "total" else spec.r_team
        for line in _nearest_lines(mean, VALID_LINES[(spec.stat, side)], n):
            p_over = nb_prob_over(mean, r, line)
            row: dict[str, Any] = {"side": side, "line": line, "p_over": round(p_over, 4), "p_under": round(1.0 - p_over, 4)}
            for direction in ("over", "under"):
                key = f"STAT:{spec.stat}:{side}:{direction}:{line:.1f}"
                best = _best_quota(books, key, 1.01, 100.0)
                row[f"quota_{direction}"] = best[0] if best else None
                row[f"book_{direction}"] = _book(best[1]) if best else None
            lines.append(row)
    playable = sorted(stat_candidates(spec, hist, f, goals, books), key=lambda c: c.score, reverse=True)
    return {
        **base,
        "expected": {"home": round(exp.home, 2), "away": round(exp.away, 2), "total": round(exp.total, 2)},
        "reason": None,
        "lines": lines,
        "playable": [_candidate_dict(c, f) for c in playable[:3]],
    }


def _valore_block(f: CecchinoV4Fixture, goals: dict[str, Any] | None, books: dict) -> dict[str, Any]:
    markets = (goals or {}).get("markets") or {}
    rows = []
    for market in VALORE_MARKETS:
        raw = (markets.get(market) or {}).get("p")
        if raw is None:
            continue
        probs = valore_probability(market, float(raw))
        best = _best_quota(books, market, 1.01, 100.0)
        rows.append(
            {
                "market_key": market,
                "label": market_label(market, f.home_team, f.away_team),
                "p_model": round(float(raw), 4),
                "p_calibrated": round(probs[0], 4) if probs else None,
                "p_prudent": round(probs[1], 4) if probs else None,
                "quota": best[0] if best else None,
                "bookmaker": _book(best[1]) if best else None,
                "in_band": bool(best and VALORE_MIN_QUOTA <= best[0] <= VALORE_MAX_QUOTA),
            }
        )
    playable = sorted(valore_candidates(f, goals, books), key=lambda c: c.score, reverse=True)
    return {
        "key": VALORE_KEY,
        "label": VALORE_LABEL,
        "status": STATUS_OBSERVATION,
        "expected": None,
        "reason": None if rows else "Nessuna previsione gol V4 per questa partita.",
        "markets": rows,
        "playable": [_candidate_dict(c, f) for c in playable[:3]],
    }


def fixture_view(db: Session, today_fixture_id: int) -> dict[str, Any]:
    today = db.get(CecchinoTodayFixture, today_fixture_id)
    if today is None:
        return {"status": "not_found", "message": "Partita non trovata."}
    f = db.execute(
        select(CecchinoV4Fixture).where(CecchinoV4Fixture.api_fixture_id == today.provider_fixture_id)
    ).scalar_one_or_none()
    if f is None:
        return {
            "status": "fuori_perimetro",
            "message": "La V5 lavora solo sulle partite dei 16 campionati principali (gli stessi della V4).",
            "version": VERSION,
        }
    goals = db.execute(
        select(CecchinoV4Prediction.payload_json).where(
            CecchinoV4Prediction.fixture_id == f.id, CecchinoV4Prediction.kind == "goals"
        )
    ).scalar_one_or_none()
    odds = latest_pre_odds(db, [f.id]).get(f.id, {})
    taken = max((t for _, t in odds.values()), default=None)
    hist = cached_history(db)
    plays = db.execute(select(CecchinoV5Play).where(CecchinoV5Play.fixture_id == f.id).order_by(CecchinoV5Play.id)).scalars()
    return {
        "status": "ok",
        "version": VERSION,
        "fixture": {
            "v4_fixture_id": f.id,
            "competition": f.competition,
            "home_team": f.home_team,
            "away_team": f.away_team,
            "kickoff_at": _iso(f.kickoff_at),
            "referee": f.referee,
            "lambda_home": (goals or {}).get("lambda_home"),
            "lambda_away": (goals or {}).get("lambda_away"),
        },
        "odds_taken_at": _iso(taken),
        "rules": {
            "prudence": STAT_PRUDENCE,
            "min_edge": MIN_EDGE,
            "stat_quota": [STAT_MIN_QUOTA, STAT_MAX_QUOTA],
            "valore_quota": [VALORE_MIN_QUOTA, VALORE_MAX_QUOTA],
        },
        "specialists": [_stat_block(s, hist, f, goals, odds) for s in STAT_SPECIALISTS] + [_valore_block(f, goals, odds)],
        "plays": [
            {
                "specialist": p.specialist,
                "status": p.status,
                "label": p.label,
                "quota": p.quota,
                "bookmaker": _book(p.bookmaker_id),
                "probability": p.probability,
                "prob_prudent": p.prob_prudent,
                "expected": p.expected,
                "taken_at": _iso(p.taken_at),
                "closing_quota": p.closing_quota,
                "clv": p.clv,
                "result": p.result,
                "profit_units": p.profit_units,
            }
            for p in plays
        ],
    }
