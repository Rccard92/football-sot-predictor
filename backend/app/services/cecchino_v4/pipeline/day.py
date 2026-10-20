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

from app.services.cecchino_v4.constants import EXAMS_DATA_DIR

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
    BOOKMAKERS,
    SHORTLIST_CONFIRMED,
    VERDICT_LABELS,
    VERDICT_PLAYABLE,
    FIXTURE_HORIZON_DAYS,
    SHORTLIST_PROVISIONAL,
    SHORTLIST_WITHDRAWN,
)
from app.services.cecchino_v4.explain.blocks import build_explanation, fixture_card
from app.services.cecchino_v4.history.football_data import History, load_history
from app.services.cecchino_v4.selection.rules import MarketRow, best_play, evaluate_fixture, no_play_reason, rows_to_dicts
from app.services.cecchino_v4.selection.settlement import settle
from app.services.cecchino_v4.selection.labels import market_family
from app.services.cecchino_v4.selection.shortlist import (
    abstention_summary,
    build_shortlist,
    get_shortlist,
    list_items,
    reference_price,
    save_provisional,
    seal_shortlist,
    settle_item,
)

logger = logging.getLogger(__name__)

ROME = ZoneInfo("Europe/Rome")
FINISHED_STATUSES = {"FT", "AET", "PEN"}
EXAMS_DIR = EXAMS_DATA_DIR
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
    from app.services.cecchino_v4.engine_goals.cache import matches_digest
    from app.services.cecchino_v4.engine_goals.config import ADOPTED_CONFIG, V4GoalsConfig
    from app.services.cecchino_v4.engine_goals.live import TargetMatch, predict_targets

    config = V4GoalsConfig(**ADOPTED_CONFIG) if isinstance(ADOPTED_CONFIG, dict) else ADOPTED_CONFIG

    def run(history_matches: list, targets: list, _config: Any = None) -> dict[str, dict]:
        tm = [TargetMatch(**t) for t in targets]
        # gli oggetti "live" (walk-forward sulle stagioni precedenti) sono in cache per storico identico
        return predict_targets(history_matches, tm, config, cache_key="live_" + matches_digest(history_matches))

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
        ODDS_TAKEN_AT[key] = (snap.taken_at, snap.kind)
        if snap.kind == "chiusura":
            closing_seen.add(key)
    return out


# (partita, bookmaker) -> (orario di lettura, tipo di istantanea) dell'ultima `latest_odds`
ODDS_TAKEN_AT: dict[tuple[int, int], tuple[datetime, str]] = {}


def odds_age_sentence(fixture_id: int, bookmaker_id: int | None, bookmaker_name: str | None) -> str | None:
    """Frase per il blocco Perche': quando e' stata letta la quota e l'invito a controllare il prezzo attuale."""
    if bookmaker_id is None:
        return None
    hit = ODDS_TAKEN_AT.get((fixture_id, bookmaker_id))
    if not hit:
        return None
    taken_at, kind = hit
    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(tzinfo=timezone.utc)
    when = taken_at.astimezone(ROME).strftime("%H:%M")
    quale = "di chiusura" if kind == "chiusura" else "del mattino" if kind == "mattina" else f"({kind})"
    return (
        f"Quota {bookmaker_name or 'del book'} letta alle {when} ({quale}) tramite API-Football, che non e' in tempo reale: "
        "prima di giocare controlla il prezzo attuale e usa la soglia indicata sotto."
    )


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


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=ROME) if dt.tzinfo is None else dt


def _row_from_item(item: CecchinoV4ShortlistItem) -> MarketRow:
    """Ricostruisce la riga di mercato da una voce salvata: la giocata resta quella pubblicata, con la sua quota."""
    bk = item.bookmaker_id or BOOKMAKER_BET365_ID
    return MarketRow(
        market_key=item.market_key,
        family=market_family(item.market_key),
        label=item.label,
        p=item.probability,
        lo=item.prob_low,
        hi=item.prob_high,
        p_prudent=item.prob_prudent,
        quota_bet365=item.quota if bk == BOOKMAKER_BET365_ID else None,
        quota_betfair=item.quota if bk == BOOKMAKER_BETFAIR_ID else None,
        quota_used=item.quota,
        bookmaker_used=BOOKMAKERS.get(bk),
        bookmaker_id=bk,
        expected_profit=item.expected_profit,
        verdict=VERDICT_PLAYABLE,
        verdict_label=VERDICT_LABELS[VERDICT_PLAYABLE],
        advised=True,
    )


def _frozen_candidates(db: Session, day: date, started_ids: set[int], fixtures_by_id: dict[int, CecchinoV4Fixture]):
    """Voci gia' pubblicate di partite iniziate: non si ricalcolano e non si perdono (base della misura)."""
    record = get_shortlist(db, day)
    if record is None:
        return [], {}
    candidates = []
    frozen: dict[tuple[int, str], CecchinoV4ShortlistItem] = {}
    for item in list_items(db, record.id):
        if item.fixture_id not in started_ids:
            continue
        f = fixtures_by_id.get(item.fixture_id)
        meta = {
            "fixture_id": item.fixture_id,
            "home_team": f.home_team if f else "?",
            "away_team": f.away_team if f else "?",
            "kickoff_at": kickoff_iso(f.kickoff_at) if f else None,
            "league_code": f.league_code if f else None,
            "reason": item.reason_json,
        }
        candidates.append((meta, _row_from_item(item)))
        frozen[(item.fixture_id, item.market_key)] = item
    return candidates, frozen


def _restore_frozen_fields(db: Session, day: date, frozen: dict[tuple[int, str], CecchinoV4ShortlistItem]) -> None:
    """Dopo la riscrittura della lista, le voci congelate riprendono stato, esito, profitto e chiusura."""
    if not frozen:
        return
    record = get_shortlist(db, day)
    if record is None:
        return
    for item in list_items(db, record.id):
        old = frozen.get((item.fixture_id, item.market_key))
        if old is None:
            continue
        item.status = old.status if old.status != "provvisoria" else SHORTLIST_CONFIRMED
        item.withdraw_reason = old.withdraw_reason
        item.closing_quota = old.closing_quota
        item.clv = old.clv
        if old.published_quota is not None:  # la prima quota pubblicata non cambia (base del CLV)
            item.published_quota = old.published_quota
            item.published_bookmaker_id = old.published_bookmaker_id
            item.published_at = old.published_at
        item.result = old.result
        item.profit_units = old.profit_units
        item.settled_at = old.settled_at
    db.flush()


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
        if g is None and s is None:
            # nessuna previsione (partita gia' passata o motore fallito): resta la scheda minima "in attesa di calcolo"
            without_play[f.match_date].append({"home_team": f.home_team, "away_team": f.away_team, "no_play_reason": "in_attesa_calcolo"})
            continue
        rows = evaluate_fixture(g, s, odds.get(f.id), f.home_team, f.away_team, f.lineups_status, advised_families=families)
        meta = fixture_meta(f)
        card = fixture_card(meta, g, rows, lineups_status=f.lineups_status, result=_result(f))
        blocks = build_explanation(meta, g, s, rows, context=_context(f, g), aftermath=_aftermath(f, rows))
        play_for_age = best_play(rows)
        if play_for_age is not None and isinstance(blocks.get("why"), dict):
            age = odds_age_sentence(f.id, play_for_age.bookmaker_id, play_for_age.bookmaker_used)
            if age:
                blocks["why"].setdefault("sentences", []).append(age)
                card_play = card.get("best_play")
                if isinstance(card_play, dict):
                    card_play["quota_taken_at"] = ODDS_TAKEN_AT[(f.id, play_for_age.bookmaker_id)][0].isoformat()
        _save_explanation(db, f, {"card": card, "blocks": blocks, "rows": rows_to_dicts(rows), "computed_at": now.isoformat()}, now)
        play = best_play(rows)
        started = (_aware(f.kickoff_at) or now) <= now
        if play is not None and not started:
            per_day[f.match_date].append(({**meta, "fixture_id": f.id}, play))
            report.plays += 1
        elif not started:
            without_play[f.match_date].append({"home_team": f.home_team, "away_team": f.away_team, "no_play_reason": no_play_reason(rows)})

    fixtures_by_id = {f.id: f for f in fixtures}
    for d in days:
        day_fixtures = [f for f in fixtures if f.match_date == d]
        started_ids = {f.id for f in day_fixtures if (_aware(f.kickoff_at) or now) <= now}
        existing = get_shortlist(db, d)
        if existing is not None and existing.status != SHORTLIST_PROVISIONAL:
            continue  # lista sigillata o regolata: non si tocca
        frozen_candidates, frozen = _frozen_candidates(db, d, started_ids, fixtures_by_id)
        candidates = frozen_candidates + per_day[d]
        if not candidates and not without_play[d] and existing is None:
            continue
        advised = all(row.advised for _, row in candidates) if candidates else True
        shortlist = build_shortlist(d, candidates, advised=advised, abstentions=abstention_summary(without_play[d]))
        try:
            save_provisional(db, shortlist, now=now)
            _restore_frozen_fields(db, d, frozen)
            report.shortlists += 1
            # tutte le partite con giocata sono iniziate: la lista si sigilla da sola (impronta e stato confermata)
            if candidates and not per_day[d]:
                seal_shortlist(db, d, sealed_at=now)
        except ValueError as exc:  # lista gia' sigillata: si lascia com'e'
            logger.info("shortlist %s non sostituita: %s", d, exc)
    db.commit()

    report.settled = settle_finished(db, now=now)
    return report


def settle_finished(db: Session, *, now: datetime | None = None) -> int:
    """Regola le voci di shortlist con partita finita; CLV = prima quota pubblicata / chiusura registrata - 1."""
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
        # chiusura dello stesso book della prima quota pubblicata (il CLV si misura su quella, non su `quota`)
        _, reference_bk = reference_price(item)
        closing_quota = (closing.get((f.id, reference_bk)) or {}).get(item.market_key)
        if outcome is None and closing_quota is None and item.status != SHORTLIST_WITHDRAWN:
            continue
        settle_item(db, item.id, outcome, closing_quota=closing_quota, now=now)
        done += 1
    db.commit()
    return done


def recover_missing_shortlists(db: Session, *, days_back: int = 30, now: datetime | None = None) -> int:
    """Giornate passate con partite finite e lista vuota (bug delle versioni fino al 12/10/2026): ricostruisce
    le giocate dalla scheda salvata di ogni partita (giocata migliore con la sua quota), sigilla e lascia
    il regolamento a `settle_finished`. Ritorna quante giornate ha recuperato."""
    now = now or _now()
    today = now.astimezone(ROME).date()
    recovered = 0
    for i in range(1, days_back + 1):
        d = today - timedelta(days=i)
        record = get_shortlist(db, d)
        if record is not None and list_items(db, record.id):
            continue
        fixtures = [f for f in fixtures_for_days(db, [d]) if f.ft_home is not None]
        if not fixtures:
            continue
        expl = {
            e.fixture_id: e.payload_json
            for e in db.execute(select(CecchinoV4Explanation).where(CecchinoV4Explanation.fixture_id.in_([f.id for f in fixtures]))).scalars()
        }
        candidates = []
        for f in fixtures:
            play = ((expl.get(f.id) or {}).get("card") or {}).get("best_play")
            if not play or play.get("verdict") != VERDICT_PLAYABLE or not play.get("quota_used"):
                continue
            row = MarketRow(
                market_key=play["market_key"],
                family=play.get("family") or market_family(play["market_key"]),
                label=play.get("label") or play["market_key"],
                p=float(play["p"]),
                lo=play.get("lo"),
                hi=play.get("hi"),
                p_prudent=float(play.get("p_prudent") or play["p"]),
                quota_bet365=play.get("quota_bet365"),
                quota_betfair=play.get("quota_betfair"),
                quota_used=float(play["quota_used"]),
                bookmaker_used=play.get("bookmaker_used"),
                bookmaker_id=play.get("bookmaker_id") or BOOKMAKER_BET365_ID,
                expected_profit=float(play.get("expected_profit") or 0.0),
                verdict=VERDICT_PLAYABLE,
                verdict_label=VERDICT_LABELS[VERDICT_PLAYABLE],
                advised=bool(play.get("advised", True)),
            )
            candidates.append(({**fixture_meta(f), "fixture_id": f.id, "reason": {"recuperata": True}}, row))
        if not candidates:
            continue
        shortlist = build_shortlist(d, candidates, advised=all(r.advised for _, r in candidates))
        if record is not None and record.status != SHORTLIST_PROVISIONAL:
            continue
        save_provisional(db, shortlist, now=now)
        seal_shortlist(db, d, sealed_at=now)
        recovered += 1
    db.commit()
    return recovered


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
