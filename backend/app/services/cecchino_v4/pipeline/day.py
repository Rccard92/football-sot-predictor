"""Calcolo del giorno: dalle partite in tabella alle previsioni, ai sei blocchi e alla shortlist.

Ordine per ogni giornata:
1. storico come input walk-forward (giudizio + lockbox + stagione in corso: solo lettura, nessuna stima);
2. previsioni gol e statistiche per i bersagli (mai dentro le finestre);
3. quote piu' recenti dal registro (chiusura se c'e', altrimenti l'ultima istantanea);
4. righe di mercato, scheda, ragionamento (strato 3: qui e solo qui entra il prezzo);
5. shortlist provvisoria del giorno (non tocca una lista gia' sigillata);
6. regolamento delle voci con partita finita e blocco "Come e' andata".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_v4 import (
    CecchinoV4Explanation,
    CecchinoV4Fixture,
    CecchinoV4OddsSnapshot,
    CecchinoV4Prediction,
    CecchinoV4Shortlist,
    CecchinoV4ShortlistItem,
)
from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKER_BETFAIR_ID,
    FIXTURE_HORIZON_DAYS,
    SHORTLIST_PROVISIONAL,
    SHORTLIST_WITHDRAWN,
)
from app.services.cecchino_v4.explain.blocks import build_explanation, fixture_card
from app.services.cecchino_v4.history.football_data import History, load_history
from app.services.cecchino_v4.selection.rules import MarketRow, best_play, evaluate_fixture, no_play_reason, rows_to_dicts
from app.services.cecchino_v4.selection.settlement import settle
from app.services.cecchino_v4.selection.shortlist import (
    abstention_summary,
    build_shortlist,
    get_shortlist,
    list_items,
    save_provisional,
    settle_item,
)

logger = logging.getLogger(__name__)

ROME = ZoneInfo("Europe/Rome")
FINISHED_STATUSES = {"FT", "AET", "PEN"}
EXAMS_DIR = Path(__file__).resolve().parents[4] / "docs" / "v4" / "esami"
CLASSIC_FAMILIES = ("FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2", "AH")

# Firme dei motori (docs/v4/ROADMAP.md, Fase 1 e 2): storico + bersagli -> payload per chiave bersaglio.
GoalsPredictor = Callable[[list, list, Any], dict[str, dict]]
StatsPredictor = Callable[[History, list, Any], dict[str, dict]]

_HISTORY_CACHE: History | None = None


def live_history() -> History:
    """Storico letto una volta per processo: giudizio, lockbox e stagione in corso, solo come input."""
    global _HISTORY_CACHE
    if _HISTORY_CACHE is None:
        _HISTORY_CACHE = load_history(include_lockbox=True, include_current=True)
    return _HISTORY_CACHE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_goals_predictor() -> GoalsPredictor:
    from app.services.cecchino_v4.engine_goals.config import ADOPTED_CONFIG
    from app.services.cecchino_v4.engine_goals.live import TargetMatch, predict_targets

    def run(history_matches: list, targets: list, _config: Any = None) -> dict[str, dict]:
        tm = [TargetMatch(**t) for t in targets]
        return predict_targets(history_matches, tm, ADOPTED_CONFIG)

    return run


def _default_stats_predictor() -> StatsPredictor:
    from app.services.cecchino_v4.engine_stats.config import ADOPTED_CONFIG
    from app.services.cecchino_v4.engine_stats.engine import Target, load_exam_verdicts, predict_targets

    def run(history: History, targets: list, _config: Any = None) -> dict[str, dict]:
        tg = [Target(**t) for t in targets]
        return predict_targets(history, tg, ADOPTED_CONFIG, extras=history.extras, exam=load_exam_verdicts())

    return run


def exam_passed(code: str) -> bool | None:
    """Esito di un esame dal file docs/v4/esami/<code>.json (None se non ancora calcolato)."""
    path = EXAMS_DIR / f"{code}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for key in ("passed", "superato"):
        if isinstance(data.get(key), bool):
            return bool(data[key])
    verdict = data.get("verdict") or data.get("verdetto")
    if isinstance(verdict, str):
        return verdict.lower() in {"superato", "passed", "pass"}
    return None


def advised_families() -> dict[str, bool]:
    """Le famiglie classiche sono consigliate solo se l'esame E4 e' superato; le statistiche seguono E2 via `exam`."""
    e4 = exam_passed("E4")
    return {fam: bool(e4) for fam in CLASSIC_FAMILIES}


@dataclass
class DayReport:
    days: list[str]
    fixtures: int
    predicted: int
    plays: int
    shortlists: int
    settled: int
    errors: list[str]

    def __str__(self) -> str:
        return (
            f"giorni {', '.join(self.days) or '-'} · partite {self.fixtures} · previste {self.predicted} · "
            f"giocate {self.plays} · shortlist {self.shortlists} · regolate {self.settled}"
            + (f" · errori {len(self.errors)}" if self.errors else "")
        )


def _target_dicts(fixtures: Iterable[CecchinoV4Fixture]) -> list[dict[str, Any]]:
    out = []
    for f in fixtures:
        out.append(
            {
                "key": str(f.id),
                "competition": f.competition,
                "season_label": f.season_label,
                "match_date": f.match_date,
                "home_team": f.home_team_history or f.home_team,
                "away_team": f.away_team_history or f.away_team,
            }
        )
    return out


def latest_odds(db: Session, fixture_ids: list[int]) -> dict[int, dict[int, dict[str, float]]]:
    """Per partita e bookmaker: la chiusura se esiste, altrimenti l'istantanea piu' recente."""
    if not fixture_ids:
        return {}
    rows = db.execute(
        select(CecchinoV4OddsSnapshot)
        .where(CecchinoV4OddsSnapshot.fixture_id.in_(fixture_ids))
        .order_by(CecchinoV4OddsSnapshot.taken_at)
    ).scalars()
    out: dict[int, dict[int, dict[str, float]]] = {}
    closing_seen: set[tuple[int, int]] = set()
    for snap in rows:
        key = (snap.fixture_id, snap.bookmaker_id)
        if key in closing_seen:
            continue
        out.setdefault(snap.fixture_id, {})[snap.bookmaker_id] = dict(snap.markets_json or {})
        if snap.kind == "chiusura":
            closing_seen.add(key)
    return out


def _replace_prediction(db: Session, fixture: CecchinoV4Fixture, kind: str, payload: dict, now: datetime) -> None:
    for old in db.execute(
        select(CecchinoV4Prediction).where(CecchinoV4Prediction.fixture_id == fixture.id, CecchinoV4Prediction.kind == kind)
    ).scalars():
        db.delete(old)
    db.add(
        CecchinoV4Prediction(
            fixture_id=fixture.id,
            kind=kind,
            payload_json=payload,
            computed_at=now,
            lineups_status=fixture.lineups_status,
        )
    )


def _result(f: CecchinoV4Fixture) -> dict[str, Any] | None:
    if f.ft_home is None or f.ft_away is None:
        return None
    return {"ft_home": f.ft_home, "ft_away": f.ft_away, "ht_home": f.ht_home, "ht_away": f.ht_away}


def kickoff_iso(dt: datetime | None) -> str | None:
    """SQLite perde il fuso: un orario senza fuso e' in ora italiana (cosi' lo scrive il caricatore locale)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ROME)
    return dt.isoformat()


def fixture_meta(f: CecchinoV4Fixture) -> dict[str, Any]:
    return {
        "id": f.id,
        "fixture_id": f.id,
        "api_fixture_id": f.api_fixture_id,
        "league_code": f.league_code,
        "competition": f.competition,
        "season_label": f.season_label,
        "kickoff_at": kickoff_iso(f.kickoff_at),
        "home_team": f.home_team,
        "away_team": f.away_team,
        "status": f.status,
        "lineups_status": f.lineups_status,
    }


def _context(f: CecchinoV4Fixture, goals: dict | None) -> dict[str, Any]:
    cal = ((goals or {}).get("specialists") or {}).get("calendar") or {}
    ctx: dict[str, Any] = {"lineups": {"status": f.lineups_status, "absences": []}}
    if cal.get("rest_days_home") is not None or cal.get("rest_days_away") is not None:
        ctx["rest"] = {"home_days": cal.get("rest_days_home"), "away_days": cal.get("rest_days_away")}
    if f.referee:
        ctx["referee"] = {"name": f.referee}
    return ctx


def _aftermath(f: CecchinoV4Fixture, rows: list[MarketRow]) -> dict[str, Any] | None:
    result = _result(f)
    if result is None:
        return None
    play = best_play(rows)
    outcome = settle(play.market_key, result, f.stats_json) if play is not None else None
    return {"result": result, "stats": f.stats_json, "play": play.to_dict() if play else None, "outcome": outcome}


def _save_explanation(db: Session, f: CecchinoV4Fixture, payload: dict, now: datetime) -> None:
    rec = db.execute(select(CecchinoV4Explanation).where(CecchinoV4Explanation.fixture_id == f.id)).scalar_one_or_none()
    if rec is None:
        db.add(CecchinoV4Explanation(fixture_id=f.id, payload_json=payload, computed_at=now))
    else:
        rec.payload_json = payload
        rec.computed_at = now


def fixtures_for_days(db: Session, days: list[date]) -> list[CecchinoV4Fixture]:
    return list(
        db.execute(
            select(CecchinoV4Fixture).where(CecchinoV4Fixture.match_date.in_(days)).order_by(CecchinoV4Fixture.kickoff_at)
        ).scalars()
    )


def default_days(now: datetime | None = None) -> list[date]:
    today = (now or _now()).astimezone(ROME).date()
    return [today + timedelta(days=i) for i in range(FIXTURE_HORIZON_DAYS + 1)]


def build_days(
    db: Session,
    *,
    days: list[date] | None = None,
    now: datetime | None = None,
    goals_predictor: GoalsPredictor | None = None,
    stats_predictor: StatsPredictor | None = None,
    history: History | None = None,
    recompute_predictions: bool = True,
) -> DayReport:
    now = now or _now()
    days = days or default_days(now)
    fixtures = fixtures_for_days(db, days)
    report = DayReport(days=[d.isoformat() for d in days], fixtures=len(fixtures), predicted=0, plays=0, shortlists=0, settled=0, errors=[])
    if not fixtures:
        return report

    hist = history or live_history()
    goals_payloads: dict[str, dict] = {}
    stats_payloads: dict[str, dict] = {}
    if recompute_predictions:
        targets = _target_dicts(fixtures)
        try:
            goals_payloads = (goals_predictor or _default_goals_predictor())(hist.matches, targets, None)
        except Exception as exc:  # noqa: BLE001 - il giorno deve uscire anche se un motore fallisce
            logger.exception("motore gol V4 fallito")
            report.errors.append(f"gol: {exc.__class__.__name__}: {exc}"[:300])
        try:
            stats_payloads = (stats_predictor or _default_stats_predictor())(hist, targets, None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("motore statistiche V4 fallito")
            report.errors.append(f"statistiche: {exc.__class__.__name__}: {exc}"[:300])
        for f in fixtures:
            g = goals_payloads.get(str(f.id))
            s = stats_payloads.get(str(f.id))
            if g is not None:
                _replace_prediction(db, f, "goals", g, now)
            if s is not None:
                _replace_prediction(db, f, "stats", s, now)
            if g is not None or s is not None:
                report.predicted += 1
        db.flush()
    else:
        for f in fixtures:
            for p in db.execute(select(CecchinoV4Prediction).where(CecchinoV4Prediction.fixture_id == f.id)).scalars():
                (goals_payloads if p.kind == "goals" else stats_payloads)[str(f.id)] = p.payload_json
        report.predicted = len({k for k in goals_payloads} | {k for k in stats_payloads})

    odds = latest_odds(db, [f.id for f in fixtures])
    families = advised_families()
    per_day: dict[date, list[tuple[dict[str, Any], MarketRow]]] = {d: [] for d in days}
    without_play: dict[date, list[dict[str, Any]]] = {d: [] for d in days}

    for f in fixtures:
        g = goals_payloads.get(str(f.id))
        s = stats_payloads.get(str(f.id))
        rows = evaluate_fixture(g, s, odds.get(f.id), f.home_team, f.away_team, f.lineups_status, advised_families=families)
        meta = fixture_meta(f)
        card = fixture_card(meta, g, rows, lineups_status=f.lineups_status, result=_result(f))
        blocks = build_explanation(meta, g, s, rows, context=_context(f, g), aftermath=_aftermath(f, rows))
        _save_explanation(db, f, {"card": card, "blocks": blocks, "rows": rows_to_dicts(rows), "computed_at": now.isoformat()}, now)
        play = best_play(rows)
        if play is not None and f.status not in FINISHED_STATUSES:
            per_day[f.match_date].append(({**meta, "fixture_id": f.id}, play))
            report.plays += 1
        elif f.status not in FINISHED_STATUSES:
            without_play[f.match_date].append({"home_team": f.home_team, "away_team": f.away_team, "no_play_reason": no_play_reason(rows)})

    for d in days:
        candidates = per_day[d]
        if not candidates and not without_play[d]:
            continue
        advised = all(row.advised for _, row in candidates) if candidates else True
        shortlist = build_shortlist(d, candidates, advised=advised, abstentions=abstention_summary(without_play[d]))
        try:
            save_provisional(db, shortlist, now=now)
            report.shortlists += 1
        except ValueError as exc:  # lista gia' sigillata: si lascia com'e'
            logger.info("shortlist %s non sostituita: %s", d, exc)
    db.commit()

    report.settled = settle_finished(db, now=now)
    return report


def settle_finished(db: Session, *, now: datetime | None = None) -> int:
    """Regola le voci di shortlist con partita finita; CLV dalla quota di chiusura registrata."""
    now = now or _now()
    items = db.execute(
        select(CecchinoV4ShortlistItem, CecchinoV4Fixture)
        .join(CecchinoV4Fixture, CecchinoV4Fixture.id == CecchinoV4ShortlistItem.fixture_id)
        .where(CecchinoV4ShortlistItem.settled_at.is_(None), CecchinoV4Fixture.ft_home.is_not(None))
    ).all()
    if not items:
        return 0
    closing = {}
    for snap in db.execute(
        select(CecchinoV4OddsSnapshot).where(
            CecchinoV4OddsSnapshot.fixture_id.in_([f.id for _, f in items]), CecchinoV4OddsSnapshot.kind == "chiusura"
        )
    ).scalars():
        closing[(snap.fixture_id, snap.bookmaker_id)] = snap.markets_json or {}
    done = 0
    for item, f in items:
        result = _result(f)
        outcome = None if item.status == SHORTLIST_WITHDRAWN else settle(item.market_key, result, f.stats_json)
        closing_quota = (closing.get((f.id, item.bookmaker_id)) or {}).get(item.market_key)
        if outcome is None and closing_quota is None and item.status != SHORTLIST_WITHDRAWN:
            continue
        settle_item(db, item.id, outcome, closing_quota=closing_quota, now=now)
        done += 1
    db.commit()
    return done


def shortlist_status(db: Session, day: date) -> str | None:
    rec = get_shortlist(db, day)
    return rec.status if rec else None


__all__ = [
    "DayReport",
    "build_days",
    "settle_finished",
    "live_history",
    "latest_odds",
    "fixture_meta",
    "fixtures_for_days",
    "default_days",
    "advised_families",
    "exam_passed",
    "shortlist_status",
    "SHORTLIST_PROVISIONAL",
    "BOOKMAKER_BET365_ID",
    "BOOKMAKER_BETFAIR_ID",
    "list_items",
    "CecchinoV4Shortlist",
]
