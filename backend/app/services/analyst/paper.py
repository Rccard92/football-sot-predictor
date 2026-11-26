"""Giocate sulla carta del Diario (capitolato del 24/11/2026, modifiche 11 e 17): senza puntata, con il loro esito.

- "bloccato": l'analista ha scelto un segno bloccato (R1, R2, regole del sito) e non l'ha registrato come
  eccezione. Serve a sapere cosa avrebbero fatto le giocate che le regole tolgono: se restano in perdita, la
  regola sta lavorando. Una per analista, gara e segno; se poi diventa un'eccezione resta collegata e non conta qui.
- "ipotesi_2": ogni gara con "casa senza obiettivi, ospite in lotta" si salva con il segno 2 (ipotesi in prova,
  +8,9% su 380 gare storiche, non provata).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.analyst_capitolato import PAPER_BLOCKED, PAPER_HYPOTHESIS_2, AnalystPaperPlay
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.analyst.journal import MARKET_BY_KEY, POSTPONED_GIVE_UP, SETTLE_AFTER, _CANCELLED, _POSTPONED

KIND_LABELS = {PAPER_BLOCKED: "tolte dalle regole (sulla carta)", PAPER_HYPOTHESIS_2: "ipotesi 2 (sulla carta)"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record(
    db: Session,
    *,
    kind: str,
    fx: CecchinoTodayFixture,
    market_key: str,
    quota: float | None,
    quota_cecchino: float | None,
    reasons: list[dict[str, Any]] | None,
    alerts: list[dict[str, Any]] | None,
    user_id: int | None,
) -> AnalystPaperPlay:
    """Una giocata sulla carta (se c'e' gia' la stessa si ritorna quella)."""
    q = select(AnalystPaperPlay).where(
        AnalystPaperPlay.kind == kind, AnalystPaperPlay.today_fixture_id == int(fx.id), AnalystPaperPlay.market_key == market_key
    )
    q = q.where(AnalystPaperPlay.user_id == user_id) if user_id is not None else q.where(AnalystPaperPlay.user_id.is_(None))
    found = db.execute(q).scalars().first()
    if found is not None:
        return found
    play = AnalystPaperPlay(
        kind=kind,
        user_id=user_id,
        today_fixture_id=int(fx.id),
        provider_fixture_id=fx.provider_fixture_id,
        match_date=fx.scan_date if isinstance(fx.scan_date, date) else date.fromisoformat(str(fx.scan_date)),
        kickoff=fx.kickoff,
        league_name=fx.league_name,
        home_team=fx.home_team_name or "Casa",
        away_team=fx.away_team_name or "Trasferta",
        market_key=market_key,
        market_label=(MARKET_BY_KEY.get(market_key) or {}).get("label", market_key),
        quota=quota,
        quota_cecchino=quota_cecchino,
        reasons_json=reasons or None,
        alerts_json=alerts or None,
        outcome="pending",
    )
    db.add(play)
    db.flush()
    return play


def link_exception(db: Session, *, user_id: int, today_fixture_id: int, market_key: str, entry_id: int) -> None:
    """Il segno bloccato e' stato registrato come eccezione: la giocata sulla carta non conta piu' tra le tolte."""
    for p in db.execute(
        select(AnalystPaperPlay).where(
            AnalystPaperPlay.kind == PAPER_BLOCKED,
            AnalystPaperPlay.user_id == user_id,
            AnalystPaperPlay.today_fixture_id == today_fixture_id,
            AnalystPaperPlay.market_key == market_key,
        )
    ).scalars():
        p.entry_id = entry_id


def settle_paper(db: Session, now: datetime | None = None) -> int:
    """Chiude le giocate sulla carta con la stessa regola delle giocate vere."""
    from app.services.cecchino_data_lab.run_v2.settlement import evaluate_market_outcome_v2

    now = now or _now()
    touched = 0
    for p in db.execute(
        select(AnalystPaperPlay).where(AnalystPaperPlay.outcome == "pending", AnalystPaperPlay.kickoff <= now - SETTLE_AFTER)
    ).scalars():
        fx = db.get(CecchinoTodayFixture, p.today_fixture_id)
        if fx is None:
            continue
        status = (fx.fixture_status or "").upper()
        kickoff = _aware(p.kickoff)
        if status in _CANCELLED or (status in _POSTPONED and kickoff is not None and now - kickoff > POSTPONED_GIVE_UP):
            p.outcome, p.profit_units, p.settled_at = "void", 0.0, now
            touched += 1
            continue
        if status not in FINISHED_STATUSES:
            continue
        home = fx.score_fulltime_home if fx.score_fulltime_home is not None else fx.goals_home
        away = fx.score_fulltime_away if fx.score_fulltime_away is not None else fx.goals_away
        if home is None or away is None:
            continue
        won = evaluate_market_outcome_v2(
            p.market_key,
            {"fulltime": {"home": home, "away": away}, "halftime": {"home": fx.score_halftime_home, "away": fx.score_halftime_away}},
        ).get("won")
        if won is None:
            continue
        p.outcome = "won" if won else "lost"
        p.profit_units = round(float(p.quota) - 1, 4) if won and p.quota else (-1.0 if not won else 0.0)
        p.result_ft = f"{home}-{away}"
        if fx.score_halftime_home is not None and fx.score_halftime_away is not None:
            p.result_ht = f"{fx.score_halftime_home}-{fx.score_halftime_away}"
        p.settled_at = now
        touched += 1
    if touched:
        db.commit()
    return touched


def record_hypotheses(db: Session, client: Any = None, now: datetime | None = None) -> dict[str, int]:
    """Giro del Diario: ogni gara di oggi e domani con "casa senza obiettivi, ospite in lotta" si salva sulla carta
    con il segno 2 alla quota usata dalle regole (prima del via)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from app.services.analyst.signs import used_quotes
    from app.services.analyst.table import day_rows

    now = now or _now()
    today = now.astimezone(ZoneInfo("Europe/Rome")).date()
    out = {"rows": 0, "saved": 0}
    for day in (today, today + timedelta(days=1)):
        for r in day_rows(db, day):
            out["rows"] += 1
            alerts = ((r.get("season_end") or {}).get("alerts")) or []
            if not any(a.get("code") == "ipotesi_2" for a in alerts):
                continue
            if not r.get("kickoff") or datetime.fromisoformat(r["kickoff"]) <= now:
                continue
            fx = db.get(CecchinoTodayFixture, int(r["today_fixture_id"]))
            if fx is None:
                continue
            used = used_quotes(r.get("quotes") or [], r.get("odds_move"), r.get("odds_checked_at")).get("AWAY") or {}
            qc = next((q.get("quota_cecchino") for q in r.get("quotes") or [] if q["key"] == "AWAY"), None)
            before = db.execute(
                select(AnalystPaperPlay.id).where(AnalystPaperPlay.kind == PAPER_HYPOTHESIS_2, AnalystPaperPlay.today_fixture_id == int(fx.id))
            ).first()
            if before is None:
                record(db, kind=PAPER_HYPOTHESIS_2, fx=fx, market_key="AWAY", quota=used.get("q"), quota_cecchino=qc, reasons=None, alerts=alerts, user_id=None)
                out["saved"] += 1
    db.commit()
    out["settled"] = settle_paper(db, now)
    return out


def paper_plays(db: Session, *, kind: str, user_id: int | None, date_from: date | None, date_to: date | None) -> list[AnalystPaperPlay]:
    q = select(AnalystPaperPlay).where(AnalystPaperPlay.kind == kind)
    if kind == PAPER_BLOCKED:
        q = q.where(AnalystPaperPlay.entry_id.is_(None))
        if user_id is not None:
            q = q.where(AnalystPaperPlay.user_id == user_id)
    if date_from:
        q = q.where(AnalystPaperPlay.match_date >= date_from)
    if date_to:
        q = q.where(AnalystPaperPlay.match_date <= date_to)
    return list(db.execute(q.order_by(AnalystPaperPlay.match_date.desc())).scalars().all())


def paper_codes(p: AnalystPaperPlay) -> tuple[set[str], set[str]]:
    rules = {str(r.get("code")) for r in (p.reasons_json or []) if isinstance(r, dict)}
    alerts = {str(a.get("code")) for a in (p.alerts_json or []) if isinstance(a, dict)}
    return rules, alerts


def group_summary(plays: list[Any]) -> dict[str, Any]:
    """Giocate, vinte, perse e unita' (giocate vere o sulla carta: serve outcome e profit_units)."""
    settled = [p for p in plays if p.outcome in ("won", "lost")]
    return {
        "entries": len(plays),
        "settled": len(settled),
        "won": sum(1 for p in settled if p.outcome == "won"),
        "lost": sum(1 for p in settled if p.outcome == "lost"),
        "units": round(sum(float(p.profit_units or 0) for p in settled), 2),
    }
