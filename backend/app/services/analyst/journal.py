"""Diario analisi (dal 30/10/2026): mercati, scheda pronostico, chiusura automatica delle giocate,
suggerimenti dai dati del tool, progressioni e report.

La chiusura usa la stessa regola del registro live (`evaluate_market_outcome_v2`): una giocata del diario e una
previsione del tool sulla stessa partita e mercato hanno sempre lo stesso esito.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.analyst_journal import (
    ENTRY_LOST,
    ENTRY_PENDING,
    ENTRY_VOID,
    ENTRY_WON,
    AnalystCycle,
    AnalystEntry,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.analyst.staking import METHOD_LABELS, SettledBet, cycle_state, suggest_stake

# --- mercati (stesse chiavi di Today, Bet Builder e V3) -------------------------------------------

MARKETS: list[dict[str, str]] = [
    {"key": "HOME", "label": "1", "group": "Fisse"},
    {"key": "DRAW", "label": "X", "group": "Fisse"},
    {"key": "AWAY", "label": "2", "group": "Fisse"},
    {"key": "ONE_X", "label": "1X", "group": "Doppie chance"},
    {"key": "X_TWO", "label": "X2", "group": "Doppie chance"},
    {"key": "ONE_TWO", "label": "12", "group": "Doppie chance"},
    {"key": "UNDER_0_5", "label": "Under 0.5", "group": "Under"},
    {"key": "UNDER_1_5", "label": "Under 1.5", "group": "Under"},
    {"key": "UNDER_2_5", "label": "Under 2.5", "group": "Under"},
    {"key": "UNDER_3_5", "label": "Under 3.5", "group": "Under"},
    {"key": "OVER_0_5", "label": "Over 0.5", "group": "Over"},
    {"key": "OVER_1_5", "label": "Over 1.5", "group": "Over"},
    {"key": "OVER_2_5", "label": "Over 2.5", "group": "Over"},
    {"key": "OVER_3_5", "label": "Over 3.5", "group": "Over"},
    {"key": "HOME_PT", "label": "1 PT", "group": "Primo tempo · Fisse"},
    {"key": "DRAW_PT", "label": "X PT", "group": "Primo tempo · Fisse"},
    {"key": "AWAY_PT", "label": "2 PT", "group": "Primo tempo · Fisse"},
    {"key": "UNDER_PT_0_5", "label": "Under PT 0.5", "group": "Primo tempo · Under"},
    {"key": "UNDER_PT_1_5", "label": "Under PT 1.5", "group": "Primo tempo · Under"},
    {"key": "OVER_PT_0_5", "label": "Over PT 0.5", "group": "Primo tempo · Over"},
    {"key": "OVER_PT_1_5", "label": "Over PT 1.5", "group": "Primo tempo · Over"},
]
MARKET_BY_KEY = {m["key"]: m for m in MARKETS}
MARKET_GROUPS = list(dict.fromkeys(m["group"] for m in MARKETS))

SOURCES = {"today": "Cecchino Today", "bet_builder": "Bet Builder", "bet_builder_v3": "Bet Builder V3"}

# --- scheda pronostico (foglio "SCHEDA PRONOSTICO") ------------------------------------------------

CHECKLIST: list[dict[str, str]] = [
    {"key": "classifica", "label": "Punti in classifica delle due squadre: contro chi sono stati fatti"},
    {"key": "forma", "label": "Stato di forma (salente o scendente), attenzione a partite ravvicinate"},
    {"key": "testa_a_testa", "label": "Testa a testa tra le due squadre, attenzione ai rapporti societari"},
    {"key": "meteo", "label": "Condizioni atmosferiche: se il campo è pesante, pochi goal"},
    {"key": "assenze", "label": "Squalificati e infortunati: verificare le assenze pesanti"},
    {"key": "ultima_gara", "label": "Ultima gara giocata: attenzione se è stata persa o a un cambio di rotta"},
    {"key": "goal", "label": "Goal fatti e subiti: contro chi e come (valore delle squadre affrontate)"},
    {"key": "allenatore", "label": "Attenzione se è avvenuto un cambio allenatore"},
    {"key": "pietre_inciampo", "label": "Possibili pietre d'inciampo?"},
    {"key": "falli", "label": "Squadre fallose: pochi goal anche se l'intensità di gioco è alta"},
    {"key": "motivazioni", "label": "Stato psico-motivazionale (perché vincere?)"},
    {"key": "quota_statistica", "label": "Quota statistica contro quota dei bookmaker (confronto)"},
    {"key": "quota_rumors", "label": "Valore quota dei bookmaker: effetto rumors"},
    {"key": "pause", "label": "Lunghe pause: forma fisica falsata"},
    {"key": "serie", "label": "Punto di rottura dopo una lunga serie di vittorie o sconfitte"},
    {"key": "fine_campionato", "label": "Ultime gare di campionato: salta l'equilibrio"},
]
CHECKLIST_KEYS = {c["key"] for c in CHECKLIST}
CHECKLIST_VALUES = ("favorevole", "neutro", "contrario")

SETTLE_AFTER = timedelta(minutes=110)  # una partita non si chiude prima di ~2 ore dal calcio d'inizio
POSTPONED_GIVE_UP = timedelta(days=7)  # rinviata senza nuova data per una settimana: nulla
_POSTPONED = {"PST", "SUSP", "INT"}
_CANCELLED = {"CANC", "ABD", "AWD", "WO"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_locked(entry: AnalystEntry, now: datetime | None = None) -> bool:
    """Bloccata al calcio d'inizio (decisione 30/10/2026): da li' cambiano solo le note."""
    if entry.outcome != ENTRY_PENDING:
        return True
    kickoff = _aware(entry.kickoff)
    return kickoff is not None and kickoff <= (now or _now())


def iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def clean_checklist(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for key, item in raw.items():
        if key not in CHECKLIST_KEYS or not isinstance(item, dict):
            continue
        value = item.get("value")
        note = str(item.get("note") or "").strip()[:500]
        if value not in CHECKLIST_VALUES:
            value = None
        if value or note:
            out[key] = {"value": value, "note": note or None}
    return out


def entry_payload(entry: AnalystEntry, *, user_name: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    market = MARKET_BY_KEY.get(entry.market_key, {})
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "user_name": user_name,
        "cycle_id": entry.cycle_id,
        "today_fixture_id": entry.today_fixture_id,
        "provider_fixture_id": entry.provider_fixture_id,
        "match_date": entry.match_date.isoformat(),
        "week": iso_week(entry.match_date),
        "kickoff": _aware(entry.kickoff).isoformat() if entry.kickoff else None,
        "league_name": entry.league_name,
        "country_name": entry.country_name,
        "home_team": entry.home_team,
        "away_team": entry.away_team,
        "source": entry.source,
        "source_label": SOURCES.get(entry.source, entry.source),
        "market_key": entry.market_key,
        "market_label": entry.market_label,
        "market_group": market.get("group"),
        "quota": entry.quota,
        "stake": entry.stake,
        "stake_suggested": entry.stake_suggested,
        "tool": entry.tool_json or {},
        "checklist": entry.checklist_json or {},
        "analysis_note": entry.analysis_note,
        "notes": entry.notes,
        "minutes_spent": entry.minutes_spent,
        "outcome": entry.outcome,
        "result_ht": entry.result_ht,
        "result_ft": entry.result_ft,
        "profit": entry.profit,
        "profit_units": entry.profit_units,
        "settled_at": _aware(entry.settled_at).isoformat() if entry.settled_at else None,
        "locked": is_locked(entry, now),
        "created_at": _aware(entry.created_at).isoformat() if entry.created_at else None,
    }


def fixture_fields(fx: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": fx.id,
        "provider_fixture_id": fx.provider_fixture_id,
        "match_date": fx.scan_date,
        "kickoff": fx.kickoff,
        "league_name": fx.league_name,
        "country_name": fx.country_name,
        "home_team": fx.home_team_name or "Casa",
        "away_team": fx.away_team_name or "Trasferta",
    }


def kpi_row(fx: CecchinoTodayFixture, market_key: str) -> dict[str, Any] | None:
    rows = ((fx.kpi_panel_json or {}).get("rows")) or []
    for row in rows:
        if isinstance(row, dict) and row.get("market_key") == market_key:
            return row
    return None


def tool_snapshot(fx: CecchinoTodayFixture, market_key: str, client: dict[str, Any] | None) -> dict[str, Any]:
    """Cosa diceva il tool quando l'analista ha scelto la giocata: dati della pagina + pannello KPI di Today."""
    snap: dict[str, Any] = {}
    for key in ("probability", "index_score", "engine", "label", "quota_tool", "origin"):
        if client and client.get(key) is not None:
            snap[key] = client[key]
    row = kpi_row(fx, market_key)
    if row:
        for key in ("prob_cecchino", "quota_cecchino", "quota_book", "prob_book", "rating", "bookmaker_name"):
            if row.get(key) is not None:
                snap[key] = row[key]
    snap["saved_at"] = _now().isoformat()
    return snap


# --- chiusura automatica --------------------------------------------------------------------------


def _score(home: Any, away: Any) -> str | None:
    return f"{home}-{away}" if home is not None and away is not None else None


def _settle_one(db: Session, entry: AnalystEntry, now: datetime) -> bool:
    from app.services.cecchino_data_lab.run_v2.settlement import evaluate_market_outcome_v2

    fx = db.get(CecchinoTodayFixture, entry.today_fixture_id) if entry.today_fixture_id else None
    if fx is None:
        return False
    status = (fx.fixture_status or "").upper()
    display = (fx.match_display_status or "").lower()
    if display == "cancelled":
        status = status if status in _CANCELLED else "CANC"
    elif display == "postponed" and status not in _CANCELLED:
        status = status if status in _POSTPONED else "PST"
    if status in _POSTPONED or status in _CANCELLED:
        # partita spostata: se esiste la riga del nuovo giorno si segue quella
        moved = db.execute(
            select(CecchinoTodayFixture)
            .where(
                CecchinoTodayFixture.provider_fixture_id == fx.provider_fixture_id,
                CecchinoTodayFixture.id != fx.id,
                CecchinoTodayFixture.scan_date > fx.scan_date,
            )
            .order_by(CecchinoTodayFixture.scan_date.desc())
        ).scalars().first()
        if moved is not None:
            entry.today_fixture_id = moved.id
            entry.kickoff = moved.kickoff
            entry.match_date = moved.scan_date
            return True
        kickoff = _aware(entry.kickoff)
        if status in _CANCELLED or (kickoff is not None and now - kickoff > POSTPONED_GIVE_UP):
            _apply(entry, ENTRY_VOID, None, None, now)
            return True
        return False
    if status not in FINISHED_STATUSES:
        return False
    home = fx.score_fulltime_home if fx.score_fulltime_home is not None else fx.goals_home
    away = fx.score_fulltime_away if fx.score_fulltime_away is not None else fx.goals_away
    if home is None or away is None:
        return False
    result = {
        "fulltime": {"home": home, "away": away},
        "halftime": {"home": fx.score_halftime_home, "away": fx.score_halftime_away},
    }
    evaluation = evaluate_market_outcome_v2(entry.market_key, result)
    won = evaluation.get("won")
    if won is None:
        return False  # es. primo tempo senza risultato del primo tempo: si riprova al prossimo aggiornamento
    _apply(
        entry,
        ENTRY_WON if won else ENTRY_LOST,
        _score(fx.score_halftime_home, fx.score_halftime_away),
        _score(home, away),
        now,
    )
    return True


def _apply(entry: AnalystEntry, outcome: str, ht: str | None, ft: str | None, now: datetime) -> None:
    entry.outcome = outcome
    entry.result_ht = ht
    entry.result_ft = ft
    entry.settled_at = now
    if outcome == ENTRY_WON:
        entry.profit_units = round(entry.quota - 1, 4)
        entry.profit = round(entry.stake * (entry.quota - 1), 2) if entry.stake else None
    elif outcome == ENTRY_LOST:
        entry.profit_units = -1.0
        entry.profit = round(-entry.stake, 2) if entry.stake else None
    else:
        entry.profit_units = 0.0
        entry.profit = 0.0 if entry.stake else None


def settle_entries(db: Session, *, user_id: int | None = None, now: datetime | None = None) -> int:
    """Chiude le giocate aperte con partita finita (o annullata). Ritorna quante ne ha toccate."""
    now = now or _now()
    q = select(AnalystEntry).where(AnalystEntry.outcome == ENTRY_PENDING, AnalystEntry.kickoff <= now - SETTLE_AFTER)
    if user_id is not None:
        q = q.where(AnalystEntry.user_id == user_id)
    touched = 0
    for entry in db.execute(q).scalars().all():
        if _settle_one(db, entry, now):
            touched += 1
    if touched:
        db.commit()
    return touched


# --- suggerimenti per la scheda pronostico --------------------------------------------------------


def _wdl(block: Any) -> str | None:
    wdl = (block or {}).get("wdl") if isinstance(block, dict) else None
    if not isinstance(wdl, dict):
        return None
    w, d, l = wdl.get("wins"), wdl.get("draws"), wdl.get("losses")
    if w is None and d is None and l is None:
        return None
    return f"{w or 0}V {d or 0}N {l or 0}P"


def checklist_hints(db: Session, fx: CecchinoTodayFixture, market_key: str | None) -> dict[str, str]:
    """Dati che il tool ha gia' per alcune voci della scheda. Solo informazioni: la scelta resta all'analista."""
    from app.models.cecchino_live_prediction import CecchinoLivePrediction

    hints: dict[str, str] = {}
    snap = ((fx.stats_snapshot_json or {}).get("input_snapshot")) or {}
    home5, away5 = _wdl(snap.get("home_recent_context_5")), _wdl(snap.get("away_recent_context_5"))
    if home5 or away5:
        hints["forma"] = f"Ultime 5 · {fx.home_team_name} in casa: {home5 or '—'} · {fx.away_team_name} fuori: {away5 or '—'}"
    try:
        pred = db.execute(
            select(CecchinoLivePrediction)
            .where(CecchinoLivePrediction.today_fixture_id == fx.id, CecchinoLivePrediction.model == "V3")
            .order_by(CecchinoLivePrediction.frozen_at.desc())
        ).scalars().first()
    except Exception:  # noqa: BLE001 - i suggerimenti non devono mai bloccare la scheda
        pred = None
    indices = ((pred.modules_json or {}).get("indices") or {}) if pred is not None else {}
    cal = indices.get("calendario") or {}
    if cal.get("rest_days_home") is not None or cal.get("rest_days_away") is not None:
        text = f"Giorni di riposo: {fx.home_team_name} {cal.get('rest_days_home', '—')}, {fx.away_team_name} {cal.get('rest_days_away', '—')}"
        hints["pause"] = text
        if cal.get("final_phase"):
            hints["fine_campionato"] = "Il tool segna questa gara nella fase finale del campionato"
    goals = indices.get("intensita_goal") or {}
    if goals.get("total") is not None:
        hints["goal"] = (
            f"Goal attesi dal tool: {goals.get('home')} - {goals.get('away')} (totale {goals.get('total')}"
            + (f", media campionato {goals.get('league_goals_avg')}" if goals.get("league_goals_avg") else "")
            + ")"
        )
    if indices.get("disciplina"):
        hints["falli"] = "Il tool ha dati di disciplina per questa gara: vedi il pannello V3 della partita"
    if market_key:
        row = kpi_row(fx, market_key)
        if row and row.get("quota_cecchino") and row.get("quota_book"):
            hints["quota_statistica"] = (
                f"Quota del tool {float(row['quota_cecchino']):.2f} contro book {float(row['quota_book']):.2f}"
                + (f" (probabilità del tool {float(row['prob_cecchino']) * 100:.0f}%)" if row.get("prob_cecchino") else "")
            )
    if fx.local_fixture_id:
        try:
            from app.models.fixture_missing_player import FixtureMissingPlayer

            missing = db.execute(
                select(FixtureMissingPlayer).where(FixtureMissingPlayer.fixture_id == int(fx.local_fixture_id))
            ).scalars().all()
        except Exception:  # noqa: BLE001
            missing = []
        if missing:
            by_side: dict[str, list[str]] = defaultdict(list)
            for m in missing:
                by_side[str(m.team_side or "?")].append(str(m.player_name or "?"))
            hints["assenze"] = " · ".join(f"{side}: {', '.join(names[:6])}" for side, names in by_side.items())
    return hints


# --- progressioni ---------------------------------------------------------------------------------


def cycle_entries(db: Session, cycle: AnalystCycle) -> list[AnalystEntry]:
    return list(
        db.execute(
            select(AnalystEntry)
            .where(AnalystEntry.cycle_id == cycle.id)
            .order_by(AnalystEntry.kickoff.asc().nulls_last(), AnalystEntry.id.asc())
        ).scalars().all()
    )


def cycle_payload(db: Session, cycle: AnalystCycle, *, quota: float | None = None) -> dict[str, Any]:
    entries = cycle_entries(db, cycle)
    settled = [
        SettledBet(stake=float(e.stake or 0.0), quota=float(e.quota), outcome=e.outcome)
        for e in entries
        if e.outcome in (ENTRY_WON, ENTRY_LOST, ENTRY_VOID) and e.stake
    ]
    state = cycle_state(cycle.method, cycle.settings_json, settled)
    pending = [e for e in entries if e.outcome == ENTRY_PENDING]
    out = {
        "id": cycle.id,
        "user_id": cycle.user_id,
        "name": cycle.name,
        "method": cycle.method,
        "method_label": METHOD_LABELS.get(cycle.method, cycle.method),
        "status": cycle.status,
        "notes": cycle.notes,
        "created_at": _aware(cycle.created_at).isoformat() if cycle.created_at else None,
        "closed_at": _aware(cycle.closed_at).isoformat() if cycle.closed_at else None,
        "state": state.payload(),
        "entries_total": len(entries),
        "pending": len(pending),
        "pending_stake": round(sum(e.stake or 0.0 for e in pending), 2),
        "settled_count": len(settled),
    }
    if quota is not None:
        out["suggestion"] = suggest_stake(state, quota)
        if pending:
            out["suggestion"]["note"] = (
                f"{len(pending)} giocate di questa progressione sono ancora in corso: la puntata è calcolata "
                "sulle sole giocate già chiuse."
            )
    return out


# --- report ---------------------------------------------------------------------------------------


def _bucket() -> dict[str, Any]:
    return {"entries": 0, "settled": 0, "won": 0, "lost": 0, "void": 0, "staked": 0.0, "profit": 0.0, "units": 0.0, "minutes": 0, "quota_sum": 0.0, "prob_sum": 0.0, "prob_n": 0}


def _add(b: dict[str, Any], e: AnalystEntry) -> None:
    b["entries"] += 1
    b["minutes"] += int(e.minutes_spent or 0)
    if e.outcome == ENTRY_PENDING:
        return
    if e.outcome == ENTRY_VOID:
        b["void"] += 1
        return
    b["settled"] += 1
    b["won" if e.outcome == ENTRY_WON else "lost"] += 1
    b["quota_sum"] += float(e.quota)
    b["units"] += float(e.profit_units or 0.0)
    if e.stake:
        b["staked"] += float(e.stake)
        b["profit"] += float(e.profit or 0.0)
    prob = (e.tool_json or {}).get("probability")
    if prob is None:
        prob = (e.tool_json or {}).get("prob_cecchino")
    try:
        p = float(prob) if prob is not None else None
    except (TypeError, ValueError):
        p = None
    if p is not None:
        b["prob_sum"] += p / 100.0 if p > 1 else p
        b["prob_n"] += 1


def _finish(b: dict[str, Any]) -> dict[str, Any]:
    n = b["settled"]
    hours = b["minutes"] / 60.0
    return {
        "entries": b["entries"],
        "settled": n,
        "won": b["won"],
        "lost": b["lost"],
        "void": b["void"],
        "win_pct": round(100.0 * b["won"] / n, 1) if n else None,
        "avg_quota": round(b["quota_sum"] / n, 2) if n else None,
        "breakeven_pct": round(100.0 * n / b["quota_sum"], 1) if b["quota_sum"] else None,
        "profit_units": round(b["units"], 2),
        "roi_units_pct": round(100.0 * b["units"] / n, 1) if n else None,
        "staked": round(b["staked"], 2),
        "profit": round(b["profit"], 2),
        "roi_pct": round(100.0 * b["profit"] / b["staked"], 1) if b["staked"] else None,
        "hours": round(hours, 1),
        "profit_per_hour": round(b["profit"] / hours, 2) if hours else None,
        "tool_prob_pct": round(100.0 * b["prob_sum"] / b["prob_n"], 1) if b["prob_n"] else None,
    }


def build_report(entries: list[AnalystEntry]) -> dict[str, Any]:
    """Report come nel file (segni per mese e gruppo, gestione cassa) + confronto con il tool e scheda."""
    total = _bucket()
    by_month: dict[str, dict[str, Any]] = defaultdict(_bucket)
    by_month_group: dict[tuple[str, str], dict[str, Any]] = defaultdict(_bucket)
    by_market: dict[str, dict[str, Any]] = defaultdict(_bucket)
    by_source: dict[str, dict[str, Any]] = defaultdict(_bucket)
    by_week: dict[str, dict[str, Any]] = defaultdict(_bucket)
    checklist: dict[tuple[str, str], dict[str, Any]] = defaultdict(_bucket)
    for e in entries:
        month = e.match_date.strftime("%Y-%m")
        group = MARKET_BY_KEY.get(e.market_key, {}).get("group", "Altro")
        for b in (total, by_month[month], by_month_group[(month, group)], by_market[e.market_key], by_source[e.source], by_week[iso_week(e.match_date)]):
            _add(b, e)
        for key, item in (e.checklist_json or {}).items():
            if isinstance(item, dict) and item.get("value") in CHECKLIST_VALUES:
                _add(checklist[(key, item["value"])], e)
    labels = {c["key"]: c["label"] for c in CHECKLIST}
    return {
        "total": _finish(total),
        "months": [{"month": m, **_finish(b)} for m, b in sorted(by_month.items(), reverse=True)],
        "weeks": [{"week": w, **_finish(b)} for w, b in sorted(by_week.items(), reverse=True)],
        "month_groups": [
            {"month": m, "group": g, **_finish(b)} for (m, g), b in sorted(by_month_group.items(), key=lambda x: (x[0][0], MARKET_GROUPS.index(x[0][1]) if x[0][1] in MARKET_GROUPS else 99), reverse=False)
        ],
        "markets": [
            {"market_key": k, "label": MARKET_BY_KEY.get(k, {}).get("label", k), "group": MARKET_BY_KEY.get(k, {}).get("group"), **_finish(b)}
            for k, b in sorted(by_market.items(), key=lambda x: -x[1]["entries"])
        ],
        "sources": [{"source": s, "label": SOURCES.get(s, s), **_finish(b)} for s, b in by_source.items()],
        "checklist": [
            {"key": k, "label": labels.get(k, k), "value": v, **_finish(b)}
            for (k, v), b in sorted(checklist.items(), key=lambda x: (list(labels).index(x[0][0]) if x[0][0] in labels else 99, x[0][1]))
        ],
        "groups": MARKET_GROUPS,
    }
