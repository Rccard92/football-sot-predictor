"""Liste sigillate della V5 dal vivo (docs/v5/LIVE_REGOLE.md): una per specialista e giorno, e il loro regolamento.

Gira dentro i job della V4 dopo le previsioni: legge le partite V4 del giorno (ora di Roma) non ancora iniziate,
le previsioni gol V4 gia' salvate e le ultime istantanee Bet365/Betfair non di chiusura. Una giocata inserita
non si modifica piu' (solo esito, chiusura e CLV); le partite nuove entrano finche' c'e' posto nel massimo
giornaliero dello specialista.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_v4 import CecchinoV4Fixture, CecchinoV4OddsSnapshot, CecchinoV4Prediction
from app.models.cecchino_v5 import CecchinoV5Play
from app.services.cecchino_v4.measure.metrics import clv as clv_value
from app.services.cecchino_v4.selection.labels import market_label
from app.services.cecchino_v4.selection.settlement import LOST, VOID, WON, profit_units, settle
from app.services.cecchino_v5.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKERS,
    COMBO_FROM,
    COMBO_KEY,
    LEAGUE_LEADS,
    LEAGUE_LEADS_FROM,
    MIN_EDGE,
    STAT_MAX_PER_DAY,
    STAT_MAX_QUOTA,
    STAT_MIN_QUOTA,
    STAT_PRUDENCE,
    STAT_SPECIALISTS,
    STATUS_OBSERVATION,
    VALID_LINES,
    VALORE_CALIBRATION,
    VALORE_KEY,
    VALORE_MARKETS,
    VALORE_MAX_PER_DAY,
    VALORE_MAX_QUOTA,
    VALORE_MIN_QUOTA,
    VALORE_SMOOTH,
    VERSION,
    StatSpecialist,
)
from app.services.cecchino_v5.model import History, expected_counts, load_history, nb_prob_over

logger = logging.getLogger(__name__)

ROME = ZoneInfo("Europe/Rome")
BOOKMAKER_NAMES = {8: "Bet365", 3: "Betfair", 0: "prodotto delle singole", -1: "senza quote"}
CANCELLED_STATUSES = {"PST", "CANC", "ABD", "AWD", "WO"}
# Si regola solo a partita finita (31/10/2026): durante la partita ft_home/ft_away contengono i gol del
# momento (normalize_fixture), e fino ad allora le giocate venivano chiuse con il punteggio parziale.
FINISHED_STATUSES = {"FT", "AET", "PEN"}
# una partita rinviata o annullata diventa void dopo questi giorni (il recupero e' un'altra partita)
CANCELLED_VOID_AFTER_DAYS = 2
# prima ora (Roma) in cui si creano giocate: dopo il job delle 08:00 che legge le quote del mattino
FIRST_LIST_HOUR = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=ROME) if dt.tzinfo is None else dt


@dataclass
class Candidate:
    fixture: CecchinoV4Fixture
    market_key: str
    expected: float | None
    probability: float
    prob_prudent: float
    quota: float
    bookmaker_id: int
    taken_at: datetime | None

    @property
    def score(self) -> float:
        return self.prob_prudent * self.quota


def latest_pre_odds(
    db: Session, fixture_ids: list[int], day: date | None = None
) -> dict[int, dict[int, tuple[dict[str, float], datetime]]]:
    """Per partita e book: l'ultima istantanea non di chiusura (mercati, orario); con `day`, solo quelle lette
    in quel giorno (ora di Roma), cosi' una lista non usa le quote della sera prima."""
    if not fixture_ids:
        return {}
    out: dict[int, dict[int, tuple[dict[str, float], datetime]]] = {}
    for snap in db.execute(
        select(CecchinoV4OddsSnapshot)
        .where(
            CecchinoV4OddsSnapshot.fixture_id.in_(fixture_ids),
            CecchinoV4OddsSnapshot.bookmaker_id.in_(BOOKMAKERS),
            CecchinoV4OddsSnapshot.kind != "chiusura",
        )
        .order_by(CecchinoV4OddsSnapshot.taken_at)
    ).scalars():
        taken = snap.taken_at if snap.taken_at.tzinfo else snap.taken_at.replace(tzinfo=timezone.utc)
        if day is not None and taken.astimezone(ROME).date() != day:
            continue
        out.setdefault(snap.fixture_id, {})[snap.bookmaker_id] = (dict(snap.markets_json or {}), snap.taken_at)
    return out


def _best_quota(
    books: dict[int, tuple[dict[str, float], datetime]], market_key: str, lo: float, hi: float
) -> tuple[float, int, datetime] | None:
    """Quota migliore tra Bet365 e Betfair dentro [lo, hi]; a parita' vince Bet365 (ordine di BOOKMAKERS)."""
    best: tuple[float, int, datetime] | None = None
    for bk in BOOKMAKERS:
        hit = books.get(bk)
        if hit is None:
            continue
        q = hit[0].get(market_key)
        try:
            q = float(q) if q is not None else None
        except (TypeError, ValueError):
            q = None
        if q is None or q < lo or q > hi:
            continue
        if best is None or q > best[0]:
            best = (q, bk, hit[1])
    return best


def _parse_stat_key(key: str) -> tuple[str, str, str, float] | None:
    """"STAT:sot:home:over:4.5" -> ("sot", "home", "over", 4.5)."""
    parts = key.split(":")
    if len(parts) != 5 or parts[0] != "STAT":
        return None
    try:
        return parts[1], parts[2], parts[3], float(parts[4])
    except ValueError:
        return None


def stat_candidates(
    spec: StatSpecialist,
    history: History,
    fixture: CecchinoV4Fixture,
    goals: dict[str, Any] | None,
    books: dict[int, tuple[dict[str, float], datetime]],
) -> list[Candidate]:
    """Tutte le linee giocabili della partita per lo specialista (gia' filtrate per quota e margine)."""
    home, away = fixture.home_team_history, fixture.away_team_history
    if not home or not away or not books:
        return []
    exp = expected_counts(
        history,
        spec,
        division=fixture.league_code,
        day=fixture.match_date,
        home=home,
        away=away,
        lambda_home=(goals or {}).get("lambda_home"),
        lambda_away=(goals or {}).get("lambda_away"),
        referee=fixture.referee,
    )
    if exp is None:
        return []
    keys = {k for markets, _ in books.values() for k in markets if k.startswith(f"STAT:{spec.stat}:")}
    out: list[Candidate] = []
    for key in sorted(keys):
        parsed = _parse_stat_key(key)
        if parsed is None:
            continue
        _, side, direction, line = parsed
        bounds = VALID_LINES.get((spec.stat, side))
        if bounds is None or not (bounds[0] <= line <= bounds[1]) or direction not in ("over", "under"):
            continue
        mean = {"home": exp.home, "away": exp.away, "total": exp.total}[side]
        r = spec.r_total if side == "total" else spec.r_team
        p_over = nb_prob_over(mean, r, line)
        p = p_over if direction == "over" else 1.0 - p_over
        p_prud = 0.5 + STAT_PRUDENCE * (p - 0.5)
        best = _best_quota(books, key, STAT_MIN_QUOTA, STAT_MAX_QUOTA)
        if best is None or p_prud * best[0] < MIN_EDGE:
            continue
        out.append(Candidate(fixture, key, round(mean, 3), round(p, 4), round(p_prud, 4), best[0], best[1], best[2]))
    return out


def valore_probability(market: str, p: float) -> tuple[float, float] | None:
    """(tarata, prudente) dalla fascia della probabilita' V3; None se la fascia non ha storico."""
    bins = VALORE_CALIBRATION.get(market)
    if not bins:
        return None
    b = min(19, max(0, int(p / 0.05)))
    hit = bins.get(b)
    if hit is None:
        return None
    n, w = hit
    center = 0.05 * b + 0.025
    cal = (w + VALORE_SMOOTH * center) / (n + VALORE_SMOOTH)
    se = math.sqrt(cal * (1.0 - cal) / (n + VALORE_SMOOTH))
    return cal, cal - se


def valore_candidates(
    fixture: CecchinoV4Fixture, goals: dict[str, Any] | None, books: dict[int, tuple[dict[str, float], datetime]]
) -> list[Candidate]:
    markets = (goals or {}).get("markets") or {}
    out: list[Candidate] = []
    for market in VALORE_MARKETS:
        raw = (markets.get(market) or {}).get("p")
        if raw is None:
            continue
        probs = valore_probability(market, float(raw))
        if probs is None:
            continue
        cal, prud = probs
        best = _best_quota(books, market, VALORE_MIN_QUOTA, VALORE_MAX_QUOTA)
        if best is None or prud * best[0] < MIN_EDGE:
            continue
        out.append(Candidate(fixture, market, None, round(cal, 4), round(prud, 4), best[0], best[1], best[2]))
    return out


@dataclass
class V5Report:
    day: str
    fixtures: int
    created: dict[str, int]
    settled: int
    errors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"day": self.day, "fixtures": self.fixtures, "created": self.created, "settled": self.settled, "errors": self.errors}


def _insert(db: Session, specialist: str, status: str, c: Candidate, now: datetime) -> None:
    f = c.fixture
    db.add(
        CecchinoV5Play(
            day=f.match_date,
            specialist=specialist,
            status=status,
            version=VERSION,
            fixture_id=f.id,
            league_code=f.league_code,
            market_key=c.market_key,
            label=market_label(c.market_key, f.home_team, f.away_team)[:160],
            expected=c.expected,
            probability=c.probability,
            prob_prudent=c.prob_prudent,
            quota=c.quota,
            bookmaker_id=c.bookmaker_id,
            taken_at=c.taken_at,
            created_at=now,
        )
    )


def build_plays(db: Session, *, now: datetime | None = None, history: History | None = None) -> V5Report:
    """Aggiunge alle liste di oggi le giocate delle partite non ancora iniziate, nei limiti giornalieri."""
    now = now or _now()
    today = now.astimezone(ROME).date()
    fixtures = [
        f
        for f in db.execute(select(CecchinoV4Fixture).where(CecchinoV4Fixture.match_date == today)).scalars()
        if (_aware(f.kickoff_at) or now) > now and (f.status or "NS") not in CANCELLED_STATUSES
    ]
    report = V5Report(day=today.isoformat(), fixtures=len(fixtures), created={}, settled=0, errors=[])
    existing = list(db.execute(select(CecchinoV5Play).where(CecchinoV5Play.day == today)).scalars())
    taken = {(p.specialist, p.fixture_id) for p in existing}
    used: dict[str, int] = {}
    for p in existing:
        used[p.specialist] = used.get(p.specialist, 0) + 1
    # la prima lista esce con le quote del mattino: prima delle 08:00 (il job di mezzanotte) non si crea nulla
    if not fixtures or now.astimezone(ROME).hour < FIRST_LIST_HOUR:
        return report

    ids = [f.id for f in fixtures]
    goals = {
        p.fixture_id: p.payload_json or {}
        for p in db.execute(
            select(CecchinoV4Prediction).where(CecchinoV4Prediction.fixture_id.in_(ids), CecchinoV4Prediction.kind == "goals")
        ).scalars()
    }
    odds = latest_pre_odds(db, ids, day=today)

    def place(specialist: str, status: str, per_fixture: list[Candidate], cap: int) -> None:
        free = cap - used.get(specialist, 0)
        fresh = [c for c in per_fixture if (specialist, c.fixture.id) not in taken]
        fresh.sort(key=lambda c: c.score, reverse=True)
        n = 0
        for c in fresh[: max(0, free)]:
            _insert(db, specialist, status, c, now)
            n += 1
        report.created[specialist] = n

    try:
        hist = history or load_history(db)
    except Exception as exc:  # noqa: BLE001 - senza storico restano solo le giocate Valore
        logger.exception("storico V5 non caricato")
        report.errors.append(f"storico: {exc.__class__.__name__}: {exc}"[:300])
        hist = None
    if hist is not None:
        for spec in STAT_SPECIALISTS:
            best: list[Candidate] = []
            for f in fixtures:
                try:
                    cands = stat_candidates(spec, hist, f, goals.get(f.id), odds.get(f.id, {}))
                except Exception as exc:  # noqa: BLE001 - una partita sbagliata non ferma la lista
                    report.errors.append(f"{spec.key} {f.id}: {exc.__class__.__name__}: {exc}"[:300])
                    continue
                if cands:
                    best.append(max(cands, key=lambda c: c.score))
            place(spec.key, spec.status, best, STAT_MAX_PER_DAY)

    best_valore: list[Candidate] = []
    for f in fixtures:
        cands = valore_candidates(f, goals.get(f.id), odds.get(f.id, {}))
        if cands:
            best_valore.append(max(cands, key=lambda c: c.score))
    place(VALORE_KEY, STATUS_OBSERVATION, best_valore, VALORE_MAX_PER_DAY)

    # piste dei campionati (docs/campionati/PISTE_V1_PREREGISTRAZIONE.md): solo Bet365, nessun massimo giornaliero
    for lead in LEAGUE_LEADS if today >= LEAGUE_LEADS_FROM else ():
        lead_cands: list[Candidate] = []
        for f in fixtures:
            rate = lead.leagues.get(f.league_code)
            hit = (odds.get(f.id) or {}).get(BOOKMAKER_BET365_ID)
            if rate is None or hit is None:
                continue
            try:
                q = float(hit[0].get(lead.market))
            except (TypeError, ValueError):
                continue
            lo, hi = lead.quota_range(f.league_code)
            if lo <= q <= hi:
                lead_cands.append(Candidate(f, lead.market, None, rate, rate, q, BOOKMAKER_BET365_ID, hit[1]))
        place(lead.key, STATUS_OBSERVATION, lead_cands, len(lead_cands) + 1000)

    # combo sulla stessa partita (docs/combo/COMBO_V1_*.md): una per partita, in osservazione
    if hist is not None and today >= COMBO_FROM:
        report.created[COMBO_KEY] = _place_combos(db, fixtures, goals, odds, hist, taken, now)
    db.commit()
    return report


def _place_combos(db: Session, fixtures, goals, odds, hist, taken, now: datetime) -> int:
    from app.services.cecchino_v5.combo import COMBO_VERSION, combo_dict, fixture_combos, pick

    n = 0
    for f in fixtures:
        if (COMBO_KEY, f.id) in taken:
            continue
        c = pick(fixture_combos(hist, f, goals.get(f.id)))
        if c is None:
            continue
        info = combo_dict(c, f.home_team, f.away_team)
        books = odds.get(f.id, {})
        quotes, times = [], []
        for leg in info["legs"]:
            best = _best_quota(books, leg["key"], 1.01, 100.0)
            if best is None:
                break
            quotes.append(best[0])
            times.append(best[2])
        if len(quotes) == len(info["legs"]):
            quota, bookmaker, taken_at = round(math.prod(quotes), 3), 0, max(times)
        else:
            quota, bookmaker, taken_at = info["fair_quota"], -1, None
        db.add(
            CecchinoV5Play(
                day=f.match_date,
                specialist=COMBO_KEY,
                status=STATUS_OBSERVATION,
                version=COMBO_VERSION,
                fixture_id=f.id,
                league_code=f.league_code,
                market_key=f"COMBO:{c.scenario}"[:64],
                label=info["label"][:160],
                expected=None,
                probability=info["probability"],
                prob_prudent=info["probability"],
                quota=quota,
                bookmaker_id=bookmaker,
                taken_at=taken_at,
                legs_json={**info, "leg_quotes": quotes if bookmaker == 0 else None},
                created_at=now,
            )
        )
        n += 1
    return n


def _settle_combo(play: CecchinoV5Play, f: CecchinoV4Fixture, closing: dict[tuple[int, int], dict[str, float]]) -> str | None:
    """Combo vinta se tutte le giocate sono vinte, persa se una e' persa; None se manca un dato."""
    legs = (play.legs_json or {}).get("legs") or []
    result = {"ft_home": f.ft_home, "ft_away": f.ft_away, "ht_home": f.ht_home, "ht_away": f.ht_away}
    outcomes = [settle(leg["key"], result, f.stats_json) for leg in legs]
    if play.bookmaker_id == 0 and play.closing_quota is None:
        closes = []
        for leg in legs:
            q = max(((closing.get((f.id, bk)) or {}).get(leg["key"]) or 0.0) for bk in BOOKMAKERS)
            closes.append(q)
        if closes and all(q > 1.0 for q in closes):
            play.closing_quota = round(math.prod(closes), 3)
            play.clv = clv_value(play.quota, play.closing_quota)
    if LOST in outcomes:
        return LOST
    if outcomes and all(o == WON for o in outcomes):
        return WON
    return None


def _finished(f: CecchinoV4Fixture) -> bool:
    return (f.status or "") in FINISHED_STATUSES and f.ft_home is not None and f.ft_away is not None


def settle_plays(db: Session, *, now: datetime | None = None) -> int:
    """Esito, chiusura e CLV delle giocate aperte. Ritorna quante giocate ha chiuso."""
    now = now or _now()
    rows = db.execute(
        select(CecchinoV5Play, CecchinoV4Fixture)
        .join(CecchinoV4Fixture, CecchinoV4Fixture.id == CecchinoV5Play.fixture_id)
        .where(CecchinoV5Play.settled_at.is_(None), CecchinoV5Play.day <= now.astimezone(ROME).date())
    ).all()
    if not rows:
        return 0
    closing: dict[tuple[int, int], dict[str, float]] = {}
    for snap in db.execute(
        select(CecchinoV4OddsSnapshot).where(
            CecchinoV4OddsSnapshot.fixture_id.in_({f.id for _, f in rows}), CecchinoV4OddsSnapshot.kind == "chiusura"
        )
    ).scalars():
        closing[(snap.fixture_id, snap.bookmaker_id)] = snap.markets_json or {}
    done = 0
    for play, f in rows:
        if play.specialist == COMBO_KEY:
            outcome = _settle_combo(play, f, closing) if _finished(f) else None
            if outcome is None and (f.status or "") in CANCELLED_STATUSES and play.day <= (now.astimezone(ROME).date() - timedelta(days=CANCELLED_VOID_AFTER_DAYS)):
                outcome = VOID
            if outcome is not None:
                play.result = outcome
                play.profit_units = profit_units(outcome, play.quota) if play.bookmaker_id >= 0 else None
                play.settled_at = now
                done += 1
            continue
        if play.closing_quota is None:
            cq = (closing.get((f.id, play.bookmaker_id)) or {}).get(play.market_key)
            if cq is not None:
                play.closing_quota = float(cq)
                play.clv = clv_value(play.quota, play.closing_quota)
        outcome = None
        if _finished(f):
            result = {"ft_home": f.ft_home, "ft_away": f.ft_away, "ht_home": f.ht_home, "ht_away": f.ht_away}
            outcome = settle(play.market_key, result, f.stats_json)
        elif (f.status or "") in CANCELLED_STATUSES and play.day <= (now.astimezone(ROME).date() - timedelta(days=CANCELLED_VOID_AFTER_DAYS)):
            outcome = VOID
        if outcome is None:
            continue
        play.result = outcome
        play.profit_units = profit_units(outcome, play.quota)
        play.settled_at = now
        done += 1
    db.commit()
    return done


def run(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Passo "v5" dei job V4: nuove giocate di oggi, poi regolamento."""
    report = build_plays(db, now=now)
    report.settled = settle_plays(db, now=now)
    return report.as_dict()


def plays_for_day(db: Session, day: date) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CecchinoV5Play, CecchinoV4Fixture)
        .join(CecchinoV4Fixture, CecchinoV4Fixture.id == CecchinoV5Play.fixture_id)
        .where(CecchinoV5Play.day == day)
        .order_by(CecchinoV4Fixture.kickoff_at, CecchinoV5Play.specialist)
    ).all()
    out = []
    for p, f in rows:
        out.append(
            {
                "id": p.id,
                "specialist": p.specialist,
                "status": p.status,
                "fixture_id": f.id,
                "league_code": p.league_code,
                "competition": f.competition,
                "kickoff_at": _aware(f.kickoff_at).isoformat() if f.kickoff_at else None,
                "home_team": f.home_team,
                "away_team": f.away_team,
                "market_key": p.market_key,
                "label": p.label,
                "expected": p.expected,
                "probability": p.probability,
                "prob_prudent": p.prob_prudent,
                "quota": p.quota,
                "bookmaker": BOOKMAKER_NAMES.get(p.bookmaker_id, str(p.bookmaker_id)),
                "taken_at": p.taken_at.isoformat() if p.taken_at else None,
                "closing_quota": p.closing_quota,
                "clv": p.clv,
                "result": p.result,
                "profit_units": p.profit_units,
                "score": f"{f.ft_home}-{f.ft_away}" if f.ft_home is not None else None,
                "combo": p.legs_json,
            }
        )
    return out

