"""Diario analisi (dal 30/10/2026): giocate, scheda pronostico, progressioni di cassa e report.

Chi vede cosa (decisione dell'utente, 30/10/2026): un analista vede e modifica solo le sue giocate e
progressioni; gli amministratori vedono tutto (in sola lettura per i diari degli altri).
Anche gli amministratori possono scrivere nel proprio diario (richiesta dell'utente, 30/10/2026): chi entra
con l'accesso di emergenza scrive a nome di un account amministratore con l'email di emergenza, creato al
primo salvataggio se non esiste ancora.
"""

from __future__ import annotations

import dataclasses
import io
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_control import require_principal
from app.core.config import get_settings
from app.core.database import get_db
from app.core.user_auth import KIND_EMERGENCY_ADMIN, Principal, generate_password, hash_password, normalize_email
from app.models.analyst_journal import (
    CYCLE_CLOSED,
    CYCLE_OPEN,
    ENTRY_PENDING,
    AnalystCycle,
    AnalystEntry,
    AnalystEntryReview,
    AnalystMatchNote,
)
from app.models.analyst_capitolato import PAPER_BLOCKED, PAPER_HYPOTHESIS_2, AnalystEntryChange, AnalystEntryPhoto
from app.models.app_user import ROLE_ADMIN, AppUser
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.analyst.paper import group_summary, link_exception, paper_codes, paper_plays, record as record_paper, settle_paper
from app.services.analyst.photos import ALLOWED_MIME, MAX_BYTES, MAX_PHOTOS, MIN_CAPTION, TOO_BIG, PhotoError, process_photo
from app.services.analyst.journal import (
    ANSWER_KEYS,
    ANSWER_VALUES,
    EXCEPTION_MIN,
    RISK_NOTE_MIN,
    clean_answers,
    CHECKLIST,
    MARKET_BY_KEY,
    MARKETS,
    SOURCES,
    build_report,
    checklist_hints,
    clean_checklist,
    cycle_entries,
    cycle_payload,
    entry_payload,
    fixture_fields,
    is_locked,
    kpi_row,
    odds_read_at,
    settle_entries,
    tool_snapshot,
)
from app.services.analyst.staking import DEFAULTS, MAX_BETS, METHOD_LABELS, METHODS, normalize_settings
from app.services.analyst.rules import (
    CODE_LABELS,
    MANUAL_TAGS,
    MATCH_TYPES,
    QUOTA_CODES,
    checklist_warning,
    clean_rules,
    entry_check,
    entry_codes,
    fixture_context,
    load_rules,
    quota_status,
    quota_warnings,
    rules_version,
    save_rules,
    uses_checklist,
)
from app.services.analyst.closing import refresh_clv
from app.services.analyst.form import alert_markets
from app.services.analyst.leagues import NOT_ADMITTED_REASON, league_admitted
from app.services.analyst.table import _quotes as _table_quotes
from app.services.analyst.table import day_rows, filter_rows, league_tables, row_for
from app.services.analyst.signs import STATE_BLOCKED, STATE_LABELS, evaluate_row, sign_of

router = APIRouter(prefix="/analyst-journal", tags=["analyst-journal"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope(principal: Principal, user_id: int | None) -> int | None:
    """Di chi sono i dati richiesti: l'analista vede solo i suoi; l'amministratore tutti o uno a scelta."""
    if principal.is_admin:
        return user_id
    if principal.user is None:
        raise HTTPException(status_code=403, detail="Serve un account")
    return principal.user.id


def _emergency_account(db: Session) -> AppUser | None:
    email = normalize_email(get_settings().emergency_admin_email)
    if "@" not in email:
        return None
    user = db.execute(select(AppUser).where(AppUser.email == email)).scalar_one_or_none()
    return user if user is None or user.is_active else None


def journal_principal(principal: Principal = Depends(require_principal), db: Session = Depends(get_db)) -> Principal:
    """L'accesso di emergenza usa l'account con l'email di emergenza, se esiste (per vedere e modificare il suo diario)."""
    if principal.kind == KIND_EMERGENCY_ADMIN and principal.user is None:
        user = _emergency_account(db)
        if user is not None:
            return dataclasses.replace(principal, user=user)
    return principal


def _writer(principal: Principal, db: Session) -> AppUser:
    if principal.user is not None:
        return principal.user
    if principal.kind == KIND_EMERGENCY_ADMIN:
        email = normalize_email(get_settings().emergency_admin_email)
        if "@" in email and db.execute(select(AppUser.id).where(AppUser.email == email)).first() is None:
            # Password a caso mai mostrata: si entra sempre con la password di emergenza
            # (o la si reimposta dal pannello utenti per farne un account normale).
            user = AppUser(
                email=email,
                first_name="Amministratore",
                last_name="(emergenza)",
                role=ROLE_ADMIN,
                password_hash=hash_password(generate_password()),
                must_change_password=True,
                is_active=True,
            )
            db.add(user)
            db.flush()
            return user
    raise HTTPException(status_code=403, detail="Per scrivere nel diario serve un account attivo")


def _own_entry(db: Session, principal: Principal, entry_id: int) -> AnalystEntry:
    entry = db.get(AnalystEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Giocata non trovata")
    if principal.user is None or entry.user_id != principal.user.id:
        raise HTTPException(status_code=403, detail="Puoi modificare solo le tue giocate")
    return entry


def _visible_entry(db: Session, principal: Principal, entry_id: int) -> AnalystEntry:
    entry = db.get(AnalystEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Giocata non trovata")
    if not principal.is_admin and (principal.user is None or entry.user_id != principal.user.id):
        raise HTTPException(status_code=403, detail="Giocata di un altro utente")
    return entry


def _own_cycle(db: Session, principal: Principal, cycle_id: int) -> AnalystCycle:
    cycle = db.get(AnalystCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Progressione non trovata")
    if principal.user is None or cycle.user_id != principal.user.id:
        raise HTTPException(status_code=403, detail="Puoi modificare solo le tue progressioni")
    return cycle


def _visible_cycle(db: Session, principal: Principal, cycle_id: int) -> AnalystCycle:
    cycle = db.get(AnalystCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Progressione non trovata")
    if not principal.is_admin and (principal.user is None or cycle.user_id != principal.user.id):
        raise HTTPException(status_code=403, detail="Progressione di un altro utente")
    return cycle


def _names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(select(AppUser.id, AppUser.first_name, AppUser.last_name).where(AppUser.id.in_(ids))).all()
    return {uid: f"{fn} {ln}" for uid, fn, ln in rows}


def _float(value: Any, field: str, *, minimum: float | None = None) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field}: numero non valido") from None
    if minimum is not None and out < minimum:
        raise HTTPException(status_code=400, detail=f"{field}: deve essere almeno {minimum:g}")
    return out


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _bookmaker(value: Any) -> str | None:
    text_value = " ".join(str(value or "").split())[:40]
    return text_value or None


def _entries_query(principal: Principal, *, user_id, date_from, date_to, cycle_id, outcome):
    q = select(AnalystEntry)
    scope = _scope(principal, user_id)
    if scope is not None:
        q = q.where(AnalystEntry.user_id == scope)
    if date_from:
        q = q.where(AnalystEntry.match_date >= date_from)
    if date_to:
        q = q.where(AnalystEntry.match_date <= date_to)
    if cycle_id:
        q = q.where(AnalystEntry.cycle_id == cycle_id)
    if outcome:
        q = q.where(AnalystEntry.outcome == outcome)
    return q.order_by(AnalystEntry.match_date.desc(), AnalystEntry.kickoff.desc().nulls_last(), AnalystEntry.id.desc())


# --- informazioni fisse ---------------------------------------------------------------------------


@router.get("/meta")
def meta(principal: Principal = Depends(journal_principal)) -> dict[str, Any]:
    return {
        "markets": MARKETS,
        "checklist": CHECKLIST,
        "sources": SOURCES,
        "methods": [
            {"key": m, "label": METHOD_LABELS[m], "defaults": DEFAULTS[m], "max_bets": MAX_BETS[m]} for m in METHODS
        ],
        "can_write": principal.user is not None or principal.kind == KIND_EMERGENCY_ADMIN,
        "is_admin": principal.is_admin,
        "user_id": principal.user.id if principal.user else None,
        "error_codes": CODE_LABELS,
        "review_tags": MANUAL_TAGS,
        "match_types": list(MATCH_TYPES),
        # capitolato del 24/11/2026
        "answers": ANSWER_KEYS,
        "answer_values": ANSWER_VALUES,
        "risk_note_min": RISK_NOTE_MIN,
        "exception_min": EXCEPTION_MIN,
        "photos": {"max": MAX_PHOTOS, "max_mb": MAX_BYTES // (1024 * 1024), "caption_min": MIN_CAPTION},
    }


@router.get("/analysts")
def analysts(principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Per l'amministratore: chi ha un diario (per il filtro)."""
    if not principal.is_admin:
        me = principal.user
        return {"analysts": [{"id": me.id, "name": f"{me.first_name} {me.last_name}"}] if me else []}
    ids = {uid for (uid,) in db.execute(select(AnalystEntry.user_id).distinct()).all()}
    ids |= {uid for (uid,) in db.execute(select(AnalystCycle.user_id).distinct()).all()}
    names = _names(db, ids)
    return {"analysts": sorted(({"id": i, "name": n} for i, n in names.items()), key=lambda x: x["name"])}


# --- tabella analisi (bozza di Giovanni, 05/11/2026) ----------------------------------------------

TABLE_PAGE_SIZE = 50


def _rome_today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Rome")).date()


@router.get("/table")
def match_table(
    day: date | None = None,
    upcoming: bool = True,
    country: str | None = None,
    league: str | None = None,
    q: str | None = None,
    page: int = 1,
    playable: bool = False,
    match_type: str | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Una riga per partita del giorno: forma, gol, gialli, equilibrio, quote e note. 50 righe per pagina.

    Dal 26/11/2026 (capitolato di Giovanni) ogni riga ha i segni con Q, stato e motivo ("evaluation"); filtri
    "solo con segni giocabili" (giocabili o da verificare) e tipo di partita."""
    day = day or _rome_today()
    now = _now()
    rows = day_rows(db, day)
    rules = load_rules(db)
    base = filter_rows(rows, now=now, upcoming_only=upcoming, country=None, league=None, query=None)
    countries = sorted({r["country"] for r in base if r["country"]})
    leagues = sorted({r["league"] for r in base if r["league"] and (not country or r["country"] == country)})
    match_types = sorted({r["match_type"] for r in base if r.get("match_type")})
    picked = filter_rows(rows, now=now, upcoming_only=upcoming, country=country, league=league, query=q)
    evaluations = {r["today_fixture_id"]: evaluate_row(rules, r) for r in picked}
    if match_type:
        picked = [r for r in picked if r.get("match_type") == match_type]
    if playable:
        picked = [r for r in picked if evaluations[r["today_fixture_id"]]["counts"]["playable"] + evaluations[r["today_fixture_id"]]["counts"]["check"] > 0]
    page = max(1, int(page))
    chunk = [dict(r) for r in picked[(page - 1) * TABLE_PAGE_SIZE : page * TABLE_PAGE_SIZE]]
    ids = [r["today_fixture_id"] for r in chunk]
    notes = db.execute(select(AnalystMatchNote).where(AnalystMatchNote.today_fixture_id.in_(ids))).scalars().all() if ids else []
    names = _names(db, {n.user_id for n in notes})
    me = principal.user.id if principal.user else None
    for r in chunk:
        r["evaluation"] = evaluations[r["today_fixture_id"]]
        # colori delle quote con le regole di acquisto di oggi (07/11/2026)
        r["quotes"] = [
            {
                **q,
                "status": quota_status(rules, q["key"], q["quota"], q.get("quota_cecchino"), r.get("match_type")),
                "warnings": [w["text"] for w in quota_warnings(rules, q["key"], q["quota"], q.get("quota_cecchino"), r.get("match_type"))],
                # "forma da gol" (09/11/2026) e primo tempo (18/11): avviso arancione, non cambia il colore della regola
                "goal_alert": q["key"] in alert_markets(r),
            }
            for q in r["quotes"]
        ]
        mine = [n for n in notes if n.today_fixture_id == r["today_fixture_id"] and n.user_id == me]
        r["my_note"] = mine[0].note if mine else ""
        # gli amministratori leggono anche le note degli altri (in sola lettura)
        r["other_notes"] = (
            [
                {"user_name": names.get(n.user_id), "note": n.note}
                for n in notes
                if n.today_fixture_id == r["today_fixture_id"] and n.user_id != me and n.note.strip()
            ]
            if principal.is_admin
            else []
        )
        r["started"] = bool(r["kickoff"] and datetime.fromisoformat(r["kickoff"]) <= now)
    return {
        "day": day.isoformat(),
        "total": len(picked),
        "total_day": len(rows),
        "page": page,
        "page_size": TABLE_PAGE_SIZE,
        "countries": countries,
        "leagues": leagues,
        "match_types": match_types,
        "rows": chunk,
        "can_write": principal.user is not None or principal.kind == KIND_EMERGENCY_ADMIN,
        "rules_version": rules_version(rules),
        # ora delle quote del mattino della pagina (la piu' recente delle righe)
        "odds_at": max((r.get("odds_checked_at") or "" for r in rows), default="") or None,
    }


@router.post("/table/notes/{today_fixture_id}")
def save_match_note(today_fixture_id: int, body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Nota dell'analista sulla partita: si salva da sola mentre scrive, anche dopo il calcio d'inizio."""
    user = _writer(principal, db)
    if db.get(CecchinoTodayFixture, today_fixture_id) is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    text = str((body or {}).get("note") or "")[:5000]
    note = db.execute(
        select(AnalystMatchNote).where(AnalystMatchNote.user_id == user.id, AnalystMatchNote.today_fixture_id == today_fixture_id)
    ).scalar_one_or_none()
    if note is None:
        note = AnalystMatchNote(user_id=user.id, today_fixture_id=today_fixture_id, note=text)
        db.add(note)
    else:
        note.note = text  # svuotata resta come riga vuota: niente si cancella
        note.updated_at = _now()
    db.commit()
    return {"today_fixture_id": today_fixture_id, "note": note.note}


@router.get("/table/standings/{today_fixture_id}")
def match_standings(today_fixture_id: int, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Classifica completa del campionato della partita: totale, casa e trasferta (06/11/2026)."""
    out = league_tables(db, today_fixture_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Classifica non disponibile per questa partita")
    return out


_moves_cache: dict[str, Any] = {}


@router.get("/odds-moves")
def odds_moves(principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Seconda lettura a 75' (18/11/2026, 8 settimane): per mercato quante volte il mercato va verso il Cecchino."""
    import time as _time

    from app.services.analyst.odds_reads import summary

    hit = _moves_cache.get("v")
    if hit and _time.monotonic() - hit[0] < 600:
        return hit[1]
    out = summary(db)
    _moves_cache["v"] = (_time.monotonic(), out)
    return out


# --- partita (per il dialogo "Aggiungi al diario") ------------------------------------------------


@router.get("/fixture/{today_fixture_id}")
def fixture_info(
    today_fixture_id: int,
    market_key: str | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    fx = db.get(CecchinoTodayFixture, today_fixture_id)
    if fx is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    fields = fixture_fields(fx)
    kickoff = fx.kickoff if fx.kickoff is None or fx.kickoff.tzinfo else fx.kickoff.replace(tzinfo=timezone.utc)
    markets = []
    for m in MARKETS:
        row = kpi_row(fx, m["key"]) or {}
        markets.append({**m, "quota_book": row.get("quota_book"), "prob_cecchino": row.get("prob_cecchino")})
    mine = []
    if principal.user is not None:
        mine = [
            entry_payload(e)
            for e in db.execute(
                select(AnalystEntry).where(
                    AnalystEntry.user_id == principal.user.id, AnalystEntry.today_fixture_id == today_fixture_id
                )
            ).scalars()
        ]
    return {
        "fixture": {
            **fields,
            "match_date": fields["match_date"].isoformat(),
            "kickoff": kickoff.isoformat() if kickoff else None,
            "started": bool(kickoff and kickoff <= _now()),
            # ora della quota del tool (09/11/2026): avviso se ha piu' di 6 ore
            "odds_checked_at": _iso(odds_read_at(fx)),
        },
        "markets": markets,
        "hints": checklist_hints(db, fx, market_key),
        "my_entries": mine,
    }


# --- regole di acquisto (07/11/2026) --------------------------------------------------------------


@router.get("/rules")
def get_rules(principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"rules": load_rules(db), "markets": MARKETS, "can_edit": principal.is_admin}


@router.post("/rules")
def update_rules(body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Solo gli amministratori cambiano le soglie; le giocate gia' salvate tengono il controllo di quel momento."""
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Solo gli amministratori cambiano le regole")
    try:
        rules = clean_rules((body or {}).get("rules"), set(MARKET_BY_KEY))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    user = _writer(principal, db)
    save_rules(db, rules, user.id)
    db.commit()
    return {"rules": load_rules(db)}


def _table_alerts(db: Session, fx: CecchinoTodayFixture | None, market_key: str) -> dict[str, Any]:
    """Avvisi della Tabella per una partita (09/11/2026): "forma da gol" e partita non editabile. Non bloccano.

    Dal 18/11/2026 il campionato non ammesso non si puo' aggiungere (decisione di Giovanni)."""
    if fx is not None and not league_admitted(fx.country_name, fx.league_name):
        return {"goal_form": None, "goal_alert": False, "editable": False, "not_editable_reason": NOT_ADMITTED_REASON}
    row = row_for(db, int(fx.id)) if fx is not None else None
    if row is None:
        return {"goal_form": None, "goal_alert": False, "editable": True, "not_editable_reason": None}
    form = row.get("goal_form")
    return {
        "goal_form": form,
        "pt_form": row.get("pt_form"),
        "goal_alert": market_key in alert_markets(row),
        "editable": bool(row.get("editable", True)),
        "not_editable_reason": row.get("not_editable_reason"),
    }


def _entry_check(db: Session, fx: CecchinoTodayFixture | None, market_key: str, quota: float) -> dict[str, Any]:
    check = entry_check(load_rules(db), fx, market_key, quota)
    try:
        alerts = _table_alerts(db, fx, market_key)
    except Exception:  # noqa: BLE001 - l'avviso non deve mai impedire di salvare la giocata
        alerts = None
    if alerts:
        check["goal_form"] = alerts["goal_form"]
        check["goal_alert"] = alerts["goal_alert"]
    return check


def _sign_context(db: Session, fx: CecchinoTodayFixture, market_key: str, rules: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Riga della Tabella, segno valutato (Q, stato, motivi) e avvisi della testata (modifica 17).

    Una gara fuori dalla Tabella (es. da Today con meno di 3 gare) si valuta con le quote del mattino e senza R2."""
    try:
        row = row_for(db, int(fx.id))
    except Exception:  # noqa: BLE001 - la valutazione non deve mai impedire di salvare
        row = None
    if row is None:
        ctx = fixture_context(fx, market_key)
        row = {"quotes": _table_quotes(fx), "odds_move": None, "odds_checked_at": _iso(odds_read_at(fx)), "match_type": ctx["match_type"], "blocks": {}}
    evaluation = evaluate_row(rules, row)
    alerts = header_alerts(row)
    return row, sign_of(evaluation, market_key), alerts


def header_alerts(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Avvisi di calendario e motivazione attivi (codice e testo), salvati con la giocata."""
    out = []
    if row.get("close_games"):
        out.append({"code": "ravvicinata", "text": f"{row['close_games']['label']} · {row['close_games']['text']}"})
    end = row.get("season_end") or {}
    if end:
        out.append({"code": "fine", "text": f"{end.get('label')} · {end.get('text')}"})
        out += [{"code": a["code"], "text": a["text"]} for a in end.get("alerts") or []]
    return out


QUOTA_GAP = 0.03


def quota_gap(quota: float | None, q: float | None) -> dict[str, Any] | None:
    """Quota presa diversa da Q oltre il 3% (modifica 8)."""
    if not quota or not q:
        return None
    diff = quota / q - 1
    if abs(diff) <= QUOTA_GAP:
        return None
    n = int(abs(diff) * 100 + 0.5)
    return {"pct": round(diff, 4), "text": f"La quota presa è diversa da quella del tool di {n}%: controlla"}


@router.post("/check")
def check_play(body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Avvisi per "Aggiungi al diario" mentre si sceglie segno e quota.

    Dal 26/11/2026 dice anche lo stato del segno (giocabile, da verificare, bloccato, fuori fascia) su Q."""
    body = body or {}
    try:
        fx = db.get(CecchinoTodayFixture, int(body.get("today_fixture_id")))
    except (TypeError, ValueError):
        fx = None
    if fx is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    market_key = str(body.get("market_key") or "")
    rules = load_rules(db)
    ctx = fixture_context(fx, market_key)
    quota = body.get("quota")
    try:
        quota = float(str(quota).replace(",", ".")) if quota not in (None, "") else None
    except ValueError:
        quota = None
    warnings = quota_warnings(rules, market_key, quota, ctx["quota_cecchino"], ctx["match_type"]) if market_key else []
    sign, alerts = None, []
    if market_key:
        _row, sign, alerts = _sign_context(db, fx, market_key, rules)
    return {
        **_table_alerts(db, fx, market_key),
        "match_type": ctx["match_type"],
        "quota_cecchino": ctx["quota_cecchino"],
        "warnings": warnings,
        "checklist_warning": None,
        "rule": (rules.get("markets") or {}).get(market_key),
        "sign": sign,
        "state_label": STATE_LABELS.get((sign or {}).get("state", ""), None),
        "quota_gap": quota_gap(quota, (sign or {}).get("q")),
        "alerts": alerts,
        "rules_version": rules_version(rules),
    }


# --- giocate --------------------------------------------------------------------------------------


@router.get("/entries")
def list_entries(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    cycle_id: int | None = None,
    outcome: str | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settle_entries(db, user_id=_scope(principal, user_id))
    rows = db.execute(
        _entries_query(principal, user_id=user_id, date_from=date_from, date_to=date_to, cycle_id=cycle_id, outcome=outcome).limit(2000)
    ).scalars().all()
    names = _names(db, {e.user_id for e in rows})
    now = _now()
    # note scritte dall'analista nella Tabella sulla stessa partita (06/11/2026): si vedono nell'elenco
    fixture_ids = {e.today_fixture_id for e in rows if e.today_fixture_id}
    table_notes = (
        {
            (n.user_id, n.today_fixture_id): n.note
            for n in db.execute(select(AnalystMatchNote).where(AnalystMatchNote.today_fixture_id.in_(fixture_ids))).scalars()
            if n.note.strip()
        }
        if fixture_ids
        else {}
    )
    # revisioni dopo la partita (07/11/2026): dell'analista e degli amministratori, con nome e data
    reviews: dict[int, list[AnalystEntryReview]] = {}
    if rows:
        for rv in db.execute(
            select(AnalystEntryReview)
            .where(AnalystEntryReview.entry_id.in_([e.id for e in rows]))
            .order_by(AnalystEntryReview.created_at.asc(), AnalystEntryReview.id.asc())
        ).scalars():
            reviews.setdefault(rv.entry_id, []).append(rv)
    names.update(_names(db, {rv.user_id for rs in reviews.values() for rv in rs} - set(names)))
    me = principal.user.id if principal.user else None
    rules = load_rules(db)
    _fill_rule_checks(db, rows, rules)
    return {
        "entries": [
            {
                **entry_payload(e, user_name=names.get(e.user_id), now=now),
                "table_note": table_notes.get((e.user_id, e.today_fixture_id)),
                "reviews": [_review_payload(rv, names, me) for rv in reviews.get(e.id, []) if rv.text.strip() or rv.user_id == me],
                **_rule_fields(e, rules, reviews.get(e.id, [])),
            }
            for e in rows
        ]
    }


def _fill_rule_checks(db: Session, rows: list[AnalystEntry], rules: dict[str, Any]) -> None:
    """Giocate salvate prima delle regole (07/11/2026): il controllo si fa una volta, con la quota salvata."""
    missing = [e for e in rows if e.rule_check_json is None]
    for e in missing:
        fx = db.get(CecchinoTodayFixture, e.today_fixture_id) if e.today_fixture_id else None
        check = entry_check(rules, fx, e.market_key, e.quota)
        qc = (e.tool_json or {}).get("quota_cecchino")
        if qc:  # la quota Cecchino del momento della scelta, se salvata
            check["quota_cecchino"] = qc
            check["warnings"] = quota_warnings(rules, e.market_key, e.quota, qc, check["match_type"])
        check["late"] = True
        e.rule_check_json = check
    if missing:
        db.commit()


def _rule_fields(e: AnalystEntry, rules: dict[str, Any], reviews: list[AnalystEntryReview]) -> dict[str, Any]:
    check = e.rule_check_json or {}
    tags = {t for rv in reviews for t in (rv.tags or [])}
    codes = entry_codes(e, rules, tags)
    warnings = [w for w in (check.get("warnings") or []) if isinstance(w, dict)]
    cl = checklist_warning(rules, e.checklist_json) if uses_checklist(e) else None
    return {
        "match_type": check.get("match_type"),
        "quota_cecchino": check.get("quota_cecchino"),
        "rule_warnings": warnings + ([cl] if cl else []),
        "out_of_rules": _is_exception(e, codes),
        "error_codes": sorted(codes),
        "to_review": e.outcome == "lost" and not any(rv.text.strip() for rv in reviews),
    }


def _review_payload(rv: AnalystEntryReview, names: dict[int, str], me: int | None) -> dict[str, Any]:
    updated = rv.updated_at or rv.created_at
    if updated is not None and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return {
        "user_id": rv.user_id,
        "user_name": names.get(rv.user_id),
        "text": rv.text,
        "tags": rv.tags or [],
        "updated_at": updated.isoformat() if updated else None,
        "mine": rv.user_id == me,
    }


@router.post("/entries/{entry_id}/review")
def save_entry_review(entry_id: int, body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Revisione della giocata dopo la partita: la scrivono l'analista e gli amministratori, anche a partita chiusa."""
    entry = _visible_entry(db, principal, entry_id)
    user = _writer(principal, db)
    text = str((body or {}).get("text") or "")[:5000]
    raw_tags = (body or {}).get("tags")
    tags = sorted({str(t) for t in raw_tags if str(t) in MANUAL_TAGS or str(t) in CODE_LABELS}) if isinstance(raw_tags, list) else None
    rv = db.execute(
        select(AnalystEntryReview).where(AnalystEntryReview.entry_id == entry.id, AnalystEntryReview.user_id == user.id)
    ).scalar_one_or_none()
    if rv is None:
        rv = AnalystEntryReview(entry_id=entry.id, user_id=user.id, text=text, tags=tags or None)
        db.add(rv)
    else:
        rv.text = text  # svuotata resta come riga vuota: niente si cancella
        if tags is not None:
            rv.tags = tags or None
        rv.updated_at = _now()
    db.commit()
    db.refresh(rv)
    return {"entry_id": entry.id, "review": _review_payload(rv, _names(db, {user.id}), user.id)}


def _photo_payload(p: AnalystEntryPhoto) -> dict[str, Any]:
    at = p.created_at if p.created_at is None or p.created_at.tzinfo else p.created_at.replace(tzinfo=timezone.utc)
    return {
        "id": p.id,
        "caption": p.caption,
        "uploaded_at": at.isoformat() if at else None,
        "after_kickoff": bool(p.after_kickoff),
        "width": p.width,
        "height": p.height,
        "url": f"/api/analyst-journal/entries/{p.entry_id}/photos/{p.id}",
    }


def _photos(db: Session, entry_id: int) -> list[AnalystEntryPhoto]:
    return list(
        db.execute(
            select(AnalystEntryPhoto)
            .where(AnalystEntryPhoto.entry_id == entry_id, AnalystEntryPhoto.removed_at.is_(None))
            .order_by(AnalystEntryPhoto.created_at.asc(), AnalystEntryPhoto.id.asc())
        ).scalars()
    )


@router.get("/entries/{entry_id}")
def get_entry(entry_id: int, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Una giocata con scheda tecnica, modifiche dopo il salvataggio e foto (anche per la lettura esterna, in GET)."""
    entry = _visible_entry(db, principal, entry_id)
    changes = db.execute(
        select(AnalystEntryChange).where(AnalystEntryChange.entry_id == entry.id).order_by(AnalystEntryChange.created_at.asc(), AnalystEntryChange.id.asc())
    ).scalars().all()
    names = _names(db, {entry.user_id})
    return {
        "entry": entry_payload(entry, user_name=names.get(entry.user_id)),
        "changes": [
            {"field": c.field, "old": c.old_value, "new": c.new_value, "after_kickoff": bool(c.after_kickoff), "at": _iso(c.created_at)}
            for c in changes
        ],
        "photos": [_photo_payload(p) for p in _photos(db, entry.id)],
    }


@router.post("/entries/{entry_id}/photos")
async def upload_photo(
    entry_id: int,
    file: UploadFile = File(...),
    caption: str = Form(""),
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Foto facoltativa della giocata (modifica 18): massimo 5, 5 MB l'una, con la didascalia."""
    entry = _own_entry(db, principal, entry_id)
    text_caption = " ".join(str(caption or "").split())[:200]
    if len(text_caption) < MIN_CAPTION:
        raise HTTPException(status_code=400, detail=f"Scrivi la didascalia della foto (almeno {MIN_CAPTION} caratteri)")
    if len(_photos(db, entry.id)) >= MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Al massimo {MAX_PHOTOS} foto per giocata")
    if (file.content_type or "").lower() not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato non ammesso: solo JPG, PNG o WEBP")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=400, detail=TOO_BIG)
    try:
        data, width, height = process_photo(raw)
    except PhotoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    photo = AnalystEntryPhoto(
        entry_id=entry.id,
        user_id=principal.user.id,
        caption=text_caption,
        mime="image/jpeg",
        width=width,
        height=height,
        size=len(data),
        data=data,
        after_kickoff=is_locked(entry),
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"photo": _photo_payload(photo)}


@router.get("/entries/{entry_id}/photos/{photo_id}")
def get_photo(entry_id: int, photo_id: int, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> Response:
    entry = _visible_entry(db, principal, entry_id)
    photo = db.get(AnalystEntryPhoto, photo_id)
    if photo is None or photo.entry_id != entry.id or photo.removed_at is not None:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    return Response(content=photo.data, media_type=photo.mime, headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/entries/{entry_id}/photos/{photo_id}")
def remove_photo(entry_id: int, photo_id: int, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Prima del via una foto si toglie (resta nell'archivio, non si mostra); dopo il via no (modifica 12)."""
    entry = _own_entry(db, principal, entry_id)
    photo = db.get(AnalystEntryPhoto, photo_id)
    if photo is None or photo.entry_id != entry.id or photo.removed_at is not None:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    if is_locked(entry) or photo.after_kickoff:
        raise HTTPException(status_code=400, detail="Dopo il via le foto non si tolgono né si sostituiscono")
    photo.removed_at = _now()
    db.commit()
    return {"removed": photo_id}


@router.get("/motivation-exam")
def motivation_exam(start: bool = False, principal: Principal = Depends(journal_principal)) -> dict[str, Any]:
    """Prova storica di "casa motivata" e "ipotesi 2" prima e dopo la regola del 26/11/2026 (in background)."""
    from app.services.analyst.motivation_exam import exam_state

    return exam_state(start=start)  # solo calcolo in memoria sui dati del Lab: non scrive niente


@router.post("/paper")
def paper_blocked(body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """L'analista ha scelto un segno bloccato (modifica 11): si salva sulla carta, senza puntata, con il suo esito.

    Se poi lo registra come eccezione, la giocata sulla carta resta collegata e non conta tra le "tolte"."""
    user = _writer(principal, db)
    body = body or {}
    try:
        fx = db.get(CecchinoTodayFixture, int(body.get("today_fixture_id")))
    except (TypeError, ValueError):
        fx = None
    if fx is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    kickoff = fx.kickoff if fx.kickoff is None or fx.kickoff.tzinfo else fx.kickoff.replace(tzinfo=timezone.utc)
    if kickoff is not None and kickoff <= _now():
        return {"saved": False}
    market_key = str(body.get("market_key") or "")
    if market_key not in MARKET_BY_KEY:
        raise HTTPException(status_code=400, detail="Pronostico non valido")
    _row, sign, alerts = _sign_context(db, fx, market_key, load_rules(db))
    if (sign or {}).get("state") != STATE_BLOCKED:
        return {"saved": False}
    play = record_paper(
        db,
        kind=PAPER_BLOCKED,
        fx=fx,
        market_key=market_key,
        quota=sign.get("q"),
        quota_cecchino=sign.get("quota_cecchino"),
        reasons=[{"code": r["code"], "rule": r.get("rule"), "text": r["text"]} for r in sign.get("reasons") or []],
        alerts=alerts,
        user_id=user.id,
    )
    db.commit()
    return {"saved": True, "id": play.id}


@router.post("/entries")
def create_entry(body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _writer(principal, db)
    body = body or {}
    try:
        fixture_id = int(body.get("today_fixture_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Partita mancante") from None
    fx = db.get(CecchinoTodayFixture, fixture_id)
    if fx is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    kickoff = fx.kickoff if fx.kickoff is None or fx.kickoff.tzinfo else fx.kickoff.replace(tzinfo=timezone.utc)
    if kickoff is not None and kickoff <= _now():
        raise HTTPException(status_code=400, detail="La partita è già iniziata: non si può più aggiungere al diario")
    # 18/11/2026 (Giovanni): i campionati non ammessi restano nel tool ma si tolgono dal Diario e dai pronostici
    if not league_admitted(fx.country_name, fx.league_name):
        raise HTTPException(status_code=400, detail=f"{NOT_ADMITTED_REASON}: {fx.country_name} · {fx.league_name}")
    market_key = str(body.get("market_key") or "")
    market = MARKET_BY_KEY.get(market_key)
    if market is None:
        raise HTTPException(status_code=400, detail="Pronostico non valido")
    source = str(body.get("source") or "today")
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail="Origine non valida")
    quota = _float(body.get("quota"), "Quota", minimum=1.01)
    if quota is None:
        raise HTTPException(status_code=400, detail="Inserisci la quota presa")
    # quota presa e CLV (09/11/2026): il bookmaker della quota presa e' obbligatorio
    bookmaker = _bookmaker(body.get("bookmaker"))
    if bookmaker is None:
        raise HTTPException(status_code=400, detail="Scrivi il bookmaker della quota presa")
    duplicate = db.execute(
        select(AnalystEntry.id).where(
            AnalystEntry.user_id == user.id,
            AnalystEntry.today_fixture_id == fixture_id,
            AnalystEntry.market_key == market_key,
        )
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Questo pronostico su questa partita è già nel tuo diario")
    cycle_id = body.get("cycle_id")
    if cycle_id:
        cycle = _own_cycle(db, principal, int(cycle_id))
        if cycle.status != CYCLE_OPEN:
            raise HTTPException(status_code=400, detail="La progressione è chiusa")
    # capitolato del 24/11/2026: tre domande e "cosa potrebbe smentire" (modifica 8), eccezione (modifica 4),
    # scheda tecnica salvata e non modificabile (modifica 12)
    answers = clean_answers(body.get("answers"))
    if len(answers) < len(ANSWER_KEYS):
        raise HTTPException(status_code=400, detail="Rispondi alle tre domande di «Prima di salvare» (sì, no o non verificato)")
    risk_note = " ".join(str(body.get("risk_note") or "").split())
    if len(risk_note) < RISK_NOTE_MIN:
        raise HTTPException(status_code=400, detail=f"Scrivi cosa potrebbe smentire questa giocata (almeno {RISK_NOTE_MIN} caratteri)")
    rules = load_rules(db)
    _row, sign, alerts = _sign_context(db, fx, market_key, rules)
    state = (sign or {}).get("state")
    exception = bool(body.get("exception"))
    exception_reason = " ".join(str(body.get("exception_reason") or "").split()) or None
    if state in (STATE_BLOCKED, "out"):
        motivo = "; ".join(r["text"] for r in (sign or {}).get("reasons") or []) or "fuori regola"
        if not exception:
            raise HTTPException(status_code=400, detail=f"Segno bloccato ({motivo}): si salva solo con «Registra eccezione»")
        if len(exception_reason or "") < EXCEPTION_MIN:
            raise HTTPException(status_code=400, detail=f"Scrivi perché la vuoi registrare lo stesso (almeno {EXCEPTION_MIN} caratteri)")
    else:
        exception, exception_reason = False, None
    check = _entry_check(db, fx, market_key, quota)
    have = {w.get("code") for w in check.get("warnings") or []}
    for reason in (sign or {}).get("reasons") or []:
        if state in (STATE_BLOCKED, "out") and reason["code"] not in have:
            check.setdefault("warnings", []).append({"code": reason["code"], "text": reason["text"]})
    tech = tech_sheet(fx, rules, sign, quota=quota, exception=exception, exception_reason=exception_reason, alerts=alerts)
    entry = AnalystEntry(
        user_id=user.id,
        cycle_id=int(cycle_id) if cycle_id else None,
        **fixture_fields(fx),
        source=source,
        market_key=market_key,
        market_label=market["label"],
        quota=quota,
        bookmaker=bookmaker,
        # la quota del tool (book di Today) resta salvata a parte, con l'ora in cui e' stata letta
        quota_tool=_float((kpi_row(fx, market_key) or {}).get("quota_book"), "Quota del tool"),
        quota_tool_at=odds_read_at(fx),
        stake=_float(body.get("stake"), "Puntata", minimum=0.01),
        stake_suggested=_float(body.get("stake_suggested"), "Puntata suggerita"),
        tool_json=tool_snapshot(fx, market_key, body.get("tool") if isinstance(body.get("tool"), dict) else None),
        checklist_json=clean_checklist(body.get("checklist")),
        analysis_note=(str(body.get("analysis_note") or "").strip() or None),
        notes=(str(body.get("notes") or "").strip() or None),
        minutes_spent=int(body["minutes_spent"]) if str(body.get("minutes_spent") or "").isdigit() else None,
        outcome=ENTRY_PENDING,
        # regole di acquisto (07/11/2026); dal 26/11 i segni bloccati entrano solo come eccezione
        rule_check_json=check,
        is_exception=exception,
        exception_reason=exception_reason,
        answers_json=answers,
        risk_note=risk_note,
        tech_json=tech,
    )
    db.add(entry)
    db.flush()
    if exception:
        link_exception(db, user_id=user.id, today_fixture_id=fixture_id, market_key=market_key, entry_id=entry.id)
    db.commit()
    db.refresh(entry)
    return {"entry": entry_payload(entry)}


def tech_sheet(
    fx: CecchinoTodayFixture,
    rules: dict[str, Any],
    sign: dict[str, Any] | None,
    *,
    quota: float,
    exception: bool,
    exception_reason: str | None,
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Scheda tecnica della giocata (modifica 12): si salva da sola e non si modifica piu'."""
    from app.services.cecchino.cecchino_constants import CECCHINO_1X2_VERSION

    s = sign or {}
    checked = ["fasce del sito"]
    if rules.get("under_no_squilibrio", True):
        checked.append("squilibrio: niente Under")
    if rules.get("r1_block", True):
        checked.append(f"R1 {int(rules.get('r1_pct', 10))}%")
    if rules.get("r2_home_block"):
        checked.append("R2 casa")
    if rules.get("r2_pt_block", True):
        checked.append("R2 PT")
    violated = [r for r in s.get("reasons") or [] if s.get("state") in (STATE_BLOCKED, "out")]
    return {
        "saved_at": _now().isoformat(),
        "quota": quota,
        "q": s.get("q"),
        "q_at": s.get("q_at"),
        "q_source": s.get("q_source"),
        "quota_cecchino": s.get("quota_cecchino"),
        "value": s.get("value"),
        "state": s.get("state"),
        "cecchino_version": CECCHINO_1X2_VERSION,
        "kpi_version": (fx.kpi_panel_json or {}).get("version") if isinstance(fx.kpi_panel_json, dict) else None,
        "rules_version": rules_version(rules),
        "rules_checked": checked,
        "violated": [r["code"] for r in violated],
        "violated_text": [r["text"] for r in violated],
        "notes": [n["text"] for n in s.get("notes") or []],
        "exception": exception,
        "exception_reason": exception_reason,
        "alerts": alerts,
    }


_TRACKED = (
    "market_key", "quota", "bookmaker", "stake", "stake_suggested", "cycle_id", "checklist_json", "analysis_note", "notes",
    "minutes_spent", "answers_json", "risk_note",
)


def _snapshot(entry: AnalystEntry) -> dict[str, str | None]:
    import json as _json

    out: dict[str, str | None] = {}
    for f in _TRACKED:
        v = getattr(entry, f, None)
        out[f] = None if v is None or v == {} else (_json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else str(v))
    return out


@router.patch("/entries/{entry_id}")
def update_entry(entry_id: int, body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    entry = _own_entry(db, principal, entry_id)
    body = body or {}
    locked = is_locked(entry)
    before = _snapshot(entry)
    if "answers" in body or "risk_note" in body:
        if locked:
            raise HTTPException(status_code=400, detail="La partita è iniziata: si possono cambiare solo le note")
        if "answers" in body:
            answers = clean_answers(body.get("answers"))
            if len(answers) < len(ANSWER_KEYS):
                raise HTTPException(status_code=400, detail="Rispondi alle tre domande (sì, no o non verificato)")
            entry.answers_json = answers
        if "risk_note" in body:
            risk = " ".join(str(body.get("risk_note") or "").split())
            if len(risk) < RISK_NOTE_MIN:
                raise HTTPException(status_code=400, detail=f"Cosa potrebbe smentire questa giocata: almeno {RISK_NOTE_MIN} caratteri")
            entry.risk_note = risk
    if "notes" in body:
        entry.notes = str(body.get("notes") or "").strip() or None
    if "minutes_spent" in body:
        raw = body.get("minutes_spent")
        entry.minutes_spent = int(raw) if str(raw or "").isdigit() else None
    pre_match = {"market_key", "quota", "bookmaker", "stake", "cycle_id", "checklist", "analysis_note", "stake_suggested"} & set(body)
    if pre_match and locked:
        raise HTTPException(status_code=400, detail="La partita è iniziata: si possono cambiare solo le note")
    if "market_key" in body:
        market = MARKET_BY_KEY.get(str(body["market_key"]))
        if market is None:
            raise HTTPException(status_code=400, detail="Pronostico non valido")
        if market["key"] != entry.market_key:
            # segno cambiato: la chiusura gia' letta non vale piu', il giro la rilegge
            entry.closing_quota = entry.closing_bookmaker = entry.closing_at = entry.closing_status = entry.closing_note = None
            entry.clv = entry.clv_ratio = entry.closing_prob = None
            fx_now = db.get(CecchinoTodayFixture, entry.today_fixture_id) if entry.today_fixture_id else None
            entry.quota_tool = _float((kpi_row(fx_now, market["key"]) or {}).get("quota_book"), "Quota del tool") if fx_now else None
        entry.market_key, entry.market_label = market["key"], market["label"]
    if "bookmaker" in body:
        bookmaker = _bookmaker(body.get("bookmaker"))
        if bookmaker is None:
            raise HTTPException(status_code=400, detail="Scrivi il bookmaker della quota presa")
        entry.bookmaker = bookmaker
    if "quota" in body:
        quota = _float(body["quota"], "Quota", minimum=1.01)
        if quota is None:
            raise HTTPException(status_code=400, detail="Inserisci la quota")
        entry.quota = quota
        refresh_clv(entry)
    if "stake" in body:
        entry.stake = _float(body["stake"], "Puntata", minimum=0.01)
    if "stake_suggested" in body:
        entry.stake_suggested = _float(body["stake_suggested"], "Puntata suggerita")
    if "cycle_id" in body:
        cycle_id = body.get("cycle_id")
        if cycle_id:
            cycle = _own_cycle(db, principal, int(cycle_id))
            if cycle.status != CYCLE_OPEN:
                raise HTTPException(status_code=400, detail="La progressione è chiusa")
        entry.cycle_id = int(cycle_id) if cycle_id else None
    if "checklist" in body:
        entry.checklist_json = clean_checklist(body.get("checklist"))
    if "analysis_note" in body:
        entry.analysis_note = str(body.get("analysis_note") or "").strip() or None
    if {"market_key", "quota"} & set(body):
        fx = db.get(CecchinoTodayFixture, entry.today_fixture_id) if entry.today_fixture_id else None
        if "market_key" in body and fx is not None and not uses_checklist(entry):
            # segno cambiato: lo stato si ricontrolla (un segno bloccato resta possibile solo come eccezione)
            _row, sign, _alerts = _sign_context(db, fx, entry.market_key, load_rules(db))
            if (sign or {}).get("state") in (STATE_BLOCKED, "out") and not entry.is_exception:
                raise HTTPException(status_code=400, detail="Il nuovo segno è bloccato: si registra solo come eccezione, con una nuova giocata")
        entry.rule_check_json = _entry_check(db, fx, entry.market_key, entry.quota)
    # modifica 12 (24/11/2026): ogni modifica lascia traccia, con ora e campo (la scheda tecnica resta com'era)
    after = _snapshot(entry)
    user_id = principal.user.id if principal.user else None
    for field in _TRACKED:
        if before[field] != after[field]:
            db.add(
                AnalystEntryChange(
                    entry_id=entry.id, user_id=user_id, field=field, old_value=before[field], new_value=after[field], after_kickoff=locked
                )
            )
    db.commit()
    return {"entry": entry_payload(entry)}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Solo prima del calcio d'inizio (per correggere un errore): dopo, la giocata resta nello storico."""
    entry = _own_entry(db, principal, entry_id)
    if is_locked(entry):
        raise HTTPException(status_code=400, detail="La partita è iniziata: la giocata resta nel diario")
    db.delete(entry)
    db.commit()
    return {"deleted": entry_id}


# --- progressioni ---------------------------------------------------------------------------------


@router.get("/cycles")
def list_cycles(
    user_id: int | None = None,
    status: str | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    scope = _scope(principal, user_id)
    settle_entries(db, user_id=scope)
    q = select(AnalystCycle).order_by(AnalystCycle.status.asc(), AnalystCycle.created_at.desc())
    if scope is not None:
        q = q.where(AnalystCycle.user_id == scope)
    if status:
        q = q.where(AnalystCycle.status == status)
    cycles = db.execute(q).scalars().all()
    names = _names(db, {c.user_id for c in cycles})
    return {"cycles": [{**cycle_payload(db, c), "user_name": names.get(c.user_id)} for c in cycles]}


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: int, quota: float | None = None, principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    cycle = _visible_cycle(db, principal, cycle_id)
    settle_entries(db, user_id=cycle.user_id)
    return {"cycle": cycle_payload(db, cycle, quota=quota), "entries": [entry_payload(e) for e in cycle_entries(db, cycle)]}


@router.post("/cycles")
def create_cycle(body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _writer(principal, db)
    body = body or {}
    method = str(body.get("method") or "")
    if method not in METHODS:
        raise HTTPException(status_code=400, detail="Metodo non valido")
    try:
        settings = normalize_settings(method, body.get("settings") if isinstance(body.get("settings"), dict) else {})
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    name = str(body.get("name") or "").strip()[:120] or f"{METHOD_LABELS[method]} {date.today().strftime('%d/%m/%Y')}"
    cycle = AnalystCycle(user_id=user.id, name=name, method=method, settings_json=settings, status=CYCLE_OPEN, notes=(str(body.get("notes") or "").strip() or None))
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return {"cycle": cycle_payload(db, cycle)}


@router.patch("/cycles/{cycle_id}")
def update_cycle(cycle_id: int, body: dict[str, Any], principal: Principal = Depends(journal_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    cycle = _own_cycle(db, principal, cycle_id)
    body = body or {}
    if "name" in body:
        cycle.name = str(body.get("name") or "").strip()[:120] or cycle.name
    if "notes" in body:
        cycle.notes = str(body.get("notes") or "").strip() or None
    if "settings" in body:
        if any(e.outcome != ENTRY_PENDING for e in cycle_entries(db, cycle)):
            raise HTTPException(status_code=400, detail="Le impostazioni non si cambiano dopo la prima giocata chiusa")
        try:
            cycle.settings_json = normalize_settings(cycle.method, body.get("settings") or {})
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    if "status" in body:
        status = str(body.get("status"))
        if status not in (CYCLE_OPEN, CYCLE_CLOSED):
            raise HTTPException(status_code=400, detail="Stato non valido")
        cycle.status = status
        cycle.closed_at = _now() if status == CYCLE_CLOSED else None
    db.commit()
    return {"cycle": cycle_payload(db, cycle)}


# --- report ed esportazione -----------------------------------------------------------------------


@router.get("/reports")
def reports(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    rule: str | None = None,
    alert: str | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    settle_entries(db, user_id=_scope(principal, user_id))
    rows = list(
        db.execute(
            _entries_query(principal, user_id=user_id, date_from=date_from, date_to=date_to, cycle_id=None, outcome=None)
        ).scalars().all()
    )
    rules = load_rules(db)
    _fill_rule_checks(db, rows, rules)
    tags: dict[int, set[str]] = {}
    if rows:
        for rv in db.execute(select(AnalystEntryReview).where(AnalystEntryReview.entry_id.in_([e.id for e in rows]))).scalars():
            tags.setdefault(rv.entry_id, set()).update(rv.tags or [])
    codes = {e.id: entry_codes(e, rules, tags.get(e.id)) for e in rows}
    out = build_report(rows, codes=codes, code_labels={**CODE_LABELS, **MANUAL_TAGS}, quota_codes=set(QUOTA_CODES))
    try:
        settle_paper(db)
    except Exception:  # noqa: BLE001 - il resoconto si mostra anche se la chiusura sulla carta non riesce
        db.rollback()
    out["rule_value"] = rule_value(
        db, rows, codes, scope=_scope(principal, user_id), date_from=date_from, date_to=date_to, rule=rule, alert=alert
    )
    return out


RULE_FILTERS = {
    "R1": {"r1"},
    "R2": {"r2_casa", "r2_pt"},
    "sito": {"sotto_minimo", "sopra_massimo", "segno_da_evitare", "under_squilibrio"},
}
ALERT_FILTERS = {
    "ravvicinata": "gara ravvicinata",
    "p27": "P27 · posizione decisa",
    "p27_senza": "P27 · senza obiettivi",
    "senza_motivazioni": "gara senza motivazioni",
    "turnover": "turnover",
    "ipotesi_2": "ipotesi 2",
    "casa_motivata": "casa motivata",
}


HYPOTHESIS_FROM = date(2026, 11, 26)
HYPOTHESIS_TARGET = 100


def _is_exception(e: AnalystEntry, codes: set[str]) -> bool:
    if getattr(e, "is_exception", None) is not None and not uses_checklist(e):
        return bool(e.is_exception)
    return bool(codes & set(QUOTA_CODES))  # giocate di prima: "fuori regola" = eccezione


def rule_value(
    db: Session,
    rows: list[AnalystEntry],
    codes: dict[int, set[str]],
    *,
    scope: int | None,
    date_from: date | None,
    date_to: date | None,
    rule: str | None,
    alert: str | None,
) -> dict[str, Any]:
    """Quanto vale ogni regola (modifica 11): dentro le regole, eccezioni, tolte dalle regole (sulla carta)."""
    want_rule = RULE_FILTERS.get(rule or "")
    want_alert = alert if alert in ALERT_FILTERS else None

    def alerts_of(e: AnalystEntry) -> set[str]:
        return {str(a.get("code")) for a in ((getattr(e, "tech_json", None) or {}).get("alerts") or []) if isinstance(a, dict)}

    # 26/11/2026 (Giovanni): i due casi di P27 su due righe separate, su tutte le giocate vere del periodo
    alert_rows = [
        {"key": code, "label": ALERT_FILTERS[code], **group_summary([e for e in rows if code in alerts_of(e)])} for code in ("p27", "p27_senza")
    ]
    # ipotesi 2: per il verdetto contano solo le gare sulla carta da oggi in poi (dal 26/11/2026), a 100 gare
    hypothesis_all = paper_plays(db, kind=PAPER_HYPOTHESIS_2, user_id=None, date_from=HYPOTHESIS_FROM, date_to=None)
    inside = [e for e in rows if not _is_exception(e, codes.get(e.id, set()))]
    exceptions = [e for e in rows if _is_exception(e, codes.get(e.id, set()))]
    removed = paper_plays(db, kind=PAPER_BLOCKED, user_id=scope, date_from=date_from, date_to=date_to)
    hypothesis = paper_plays(db, kind=PAPER_HYPOTHESIS_2, user_id=None, date_from=date_from, date_to=date_to)
    if want_rule:
        exceptions = [e for e in exceptions if codes.get(e.id, set()) & want_rule]
        removed = [p for p in removed if paper_codes(p)[0] & want_rule]
    if want_alert:
        inside = [e for e in inside if want_alert in alerts_of(e)]
        exceptions = [e for e in exceptions if want_alert in alerts_of(e)]
        removed = [p for p in removed if want_alert in paper_codes(p)[1]]
    groups = [
        {"key": "dentro", "label": "dentro le regole", **group_summary(inside)},
        {"key": "eccezioni", "label": "eccezioni (fuori regola)", **group_summary(exceptions)},
        {"key": "tolte", "label": "tolte dalle regole (sulla carta)", **group_summary(removed)},
    ]
    return {
        "groups": groups,
        "hypothesis": {"key": "ipotesi_2", "label": "ipotesi 2 · casa senza obiettivi, ospite in lotta (sulla carta)", **group_summary(hypothesis)},
        "hypothesis_verdict": {"from": HYPOTHESIS_FROM.isoformat(), "target": HYPOTHESIS_TARGET, **group_summary(hypothesis_all)},
        "alert_rows": alert_rows,
        "rule": rule if want_rule else None,
        "alert": want_alert,
        "rule_filters": list(RULE_FILTERS),
        "alert_filters": ALERT_FILTERS,
    }


_OUTCOME_XLS = {"won": "VINTA", "lost": "PERSA", "void": "NULLA", "pending": ""}


def _closing_label(e: AnalystEntry) -> str | None:
    if e.closing_status == "nd":
        return "n.d."
    if not e.closing_bookmaker:
        return None
    return e.closing_bookmaker + (" (recuperata)" if e.closing_note and "recuperata" in e.closing_note else "")


def _capitolato_cells(e: AnalystEntry) -> list[Any]:
    tech = e.tech_json or {}
    answers = e.answers_json or {}
    q_at = tech.get("q_at")
    try:
        from zoneinfo import ZoneInfo

        q_at_text = datetime.fromisoformat(q_at).astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m %H:%M") if q_at else None
    except ValueError:
        q_at_text = None
    return [
        ("SÌ" if e.is_exception else "NO") if e.is_exception is not None else None,
        e.exception_reason,
        tech.get("q"),
        q_at_text,
        tech.get("cecchino_version"),
        tech.get("rules_version"),
        " · ".join(tech.get("violated_text") or []) or None,
        " · ".join(a.get("text", "") for a in tech.get("alerts") or []) or None,
        *[ANSWER_VALUES.get(answers.get(a["key"], ""), None) for a in ANSWER_KEYS],
        e.risk_note,
    ]


@router.get("/export.xlsx")
def export_xlsx(
    date_from: date | None = None,
    date_to: date | None = None,
    user_id: int | None = None,
    principal: Principal = Depends(journal_principal),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Le giocate nello schema del foglio "GARE ATTUALE KW", piu' puntata, profitto e scheda."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    rows = list(
        db.execute(
            _entries_query(principal, user_id=user_id, date_from=date_from, date_to=date_to, cycle_id=None, outcome=None)
        ).scalars().all()
    )
    rows.reverse()  # dal piu' vecchio, come nel file
    names = _names(db, {e.user_id for e in rows})
    cycles = {c.id: c.name for c in db.execute(select(AnalystCycle)).scalars().all()} if rows else {}
    wb = Workbook()
    ws = wb.active
    ws.title = "GARE"
    headers = [
        "GARA", "DATA", "KW", "INCONTRO", "CAMPIONATO", "PRONOSTICO", "QUOTA PRESA", "BOOKMAKER", "QUOTA TOOL",
        "QUOTA CHIUSURA", "BOOK CHIUSURA", "PROB. CHIUSURA SENZA MARGINE %", "CLV %", "CLV QUOTA/CHIUSURA %",
        "RISULTATO PT", "RISULTATO FINALE",
        "ESITO", "VERSIONE SCELTA", "PUNTATA €", "PROFITTO €", "ORIGINE", "PROB. TOOL %", "MINUTI", "ANALISTA",
        "MODALITÀ DI INTERVENTO", "NOTE",
        # capitolato del 24/11/2026
        "ECCEZIONE", "MOTIVO ECCEZIONE", "QUOTA USATA DALLE REGOLE", "ORA QUOTA USATA", "VERSIONE CECCHINO", "VERSIONE REGOLE",
        "REGOLE VIOLATE", "AVVISI", *[a["label"].upper() for a in ANSWER_KEYS], "COSA POTREBBE SMENTIRLA",
    ] + [c["label"] for c in CHECKLIST]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2937")
    for i, e in enumerate(rows, start=1):
        prob = (e.tool_json or {}).get("probability", (e.tool_json or {}).get("prob_cecchino"))
        try:
            prob_pct = round(float(prob) * (100 if float(prob) <= 1 else 1), 1) if prob is not None else None
        except (TypeError, ValueError):
            prob_pct = None
        checklist = e.checklist_json or {}
        ws.append(
            [
                i,
                e.match_date,
                e.match_date.isocalendar()[1],
                f"{e.home_team} - {e.away_team}",
                e.league_name,
                e.market_label,
                e.quota,
                e.bookmaker,
                e.quota_tool,
                e.closing_quota,
                _closing_label(e),
                round(100.0 * e.closing_prob, 1) if e.closing_prob is not None else None,
                round(100.0 * e.clv, 1) if e.clv is not None else None,
                round(100.0 * e.clv_ratio, 1) if e.clv_ratio is not None else None,
                e.result_ht,
                e.result_ft,
                _OUTCOME_XLS.get(e.outcome, e.outcome),
                cycles.get(e.cycle_id) if e.cycle_id else None,
                e.stake,
                e.profit,
                SOURCES.get(e.source, e.source),
                prob_pct,
                e.minutes_spent,
                names.get(e.user_id),
                e.analysis_note,
                e.notes,
                *_capitolato_cells(e),
            ]
            + [
                " · ".join(x for x in ((checklist.get(c["key"]) or {}).get("value"), (checklist.get(c["key"]) or {}).get("note")) if x) or None
                for c in CHECKLIST
            ]
        )
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Arial")
        row[1].number_format = "DD/MM/YYYY"
    widths = (6, 11, 5, 34, 24, 13, 8, 13, 8, 10, 14, 7, 11, 13, 9, 18, 10, 11, 15, 11, 8, 18, 40, 40)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"diario_analisi_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
