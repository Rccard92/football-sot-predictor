"""BET-RESULTS-01 — Bet Builder Outcome Monitor (read-only).

Ricostruisce opportunity post-kickoff dagli snapshot CecchinoTodayFixture,
seleziona primary con Evidence Sort V2, valuta WON/LOST via evaluate_market_selection.

Nessun freeze, nessun backfill, nessuna API esterna, nessuna migration.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_PRIMARY_SELECTION_VERSION,
    BET_BUILDER_RESULTS_CONTRACT_VERSION,
    BET_BUILDER_RESULTS_START_DATE,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
)
from app.services.cecchino.cecchino_bet_builder_markets import BET_BUILDER_MARKET_KEY_SET
from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import (
    _load_gi_payloads_batch,
    build_opportunities_for_rows,
)
from app.services.cecchino.cecchino_bet_builder_primary_selection import (
    primary_selection_version,
    sort_opportunities_by_evidence_strength,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    match_result_from_fixture,
)

ROME_TZ = ZoneInfo("Europe/Rome")

OUTCOME_WON = EVAL_WON
OUTCOME_LOST = EVAL_LOST
OUTCOME_PENDING = EVAL_PENDING
OUTCOME_RESULT_MISSING = EVAL_RESULT_MISSING
OUTCOME_NOT_EVALUABLE = EVAL_NOT_EVALUABLE

VALID_OUTCOMES = frozenset(
    {
        OUTCOME_WON,
        OUTCOME_LOST,
        OUTCOME_PENDING,
        OUTCOME_RESULT_MISSING,
        OUTCOME_NOT_EVALUABLE,
    }
)

SORT_RECENT = "recent"
SORT_KICKOFF_ASC = "kickoff_asc"
SORT_LOST_FIRST = "lost_first"
SORT_PURCHASABILITY_DESC = "purchasability_desc"
VALID_SORTS = frozenset(
    {SORT_RECENT, SORT_KICKOFF_ASC, SORT_LOST_FIRST, SORT_PURCHASABILITY_DESC}
)

MATCH_STATUS_CANONICAL = frozenset(
    {
        MATCH_UPCOMING,
        MATCH_LIVE,
        MATCH_FINISHED,
        MATCH_POSTPONED,
        MATCH_CANCELLED,
        "unknown",
    }
)


def clamp_results_date(value: date | None, *, today: date | None = None) -> date:
    """Normalizza una data al range [START, today Rome]."""
    today = today or datetime.now(ROME_TZ).date()
    start = BET_BUILDER_RESULTS_START_DATE
    if value is None:
        return today if today >= start else start
    if value < start:
        return start
    if value > today:
        return today
    return value


def normalize_match_status(row: CecchinoTodayFixture) -> str:
    status = str(row.match_display_status or "").strip().lower()
    if status in MATCH_STATUS_CANONICAL:
        return status
    if not status:
        return MATCH_UPCOMING
    return "unknown"


def evaluate_bet_builder_prediction_outcome(
    *,
    market_key: str,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Outcome prediction separato da match_status.

    cancelled/postponed → not_evaluable (mai LOST).
    upcoming / live senza score utile → pending.
    finished senza FT/HT → result_missing (via helper canonico).
    X PT può settlare su HT anche se LIVE.
    """
    match_status = normalize_match_status(row)

    if match_status in {MATCH_CANCELLED, MATCH_POSTPONED}:
        return {
            "prediction_outcome": OUTCOME_NOT_EVALUABLE,
            "evaluation_reason": f"match_{match_status}",
            "match_status": match_status,
        }

    match_result = match_result_from_fixture(row)
    ht = match_result.get("halftime") or {}
    ft = match_result.get("fulltime") or {}
    ht_ready = ht.get("home") is not None and ht.get("away") is not None
    ft_ready = ft.get("home") is not None and ft.get("away") is not None

    # X PT: HT disponibile → valuta anche in live
    from app.services.cecchino.cecchino_selection_keys import SEL_DRAW_PT

    if market_key == SEL_DRAW_PT:
        if ht_ready:
            ev = evaluate_market_selection(market_key, match_result)
            return {
                "prediction_outcome": ev.get("evaluation_status") or OUTCOME_NOT_EVALUABLE,
                "evaluation_reason": ev.get("evaluation_reason"),
                "match_status": match_status,
                "result_home_ht": ev.get("result_home_ht"),
                "result_away_ht": ev.get("result_away_ht"),
                "result_home_ft": row.score_fulltime_home,
                "result_away_ft": row.score_fulltime_away,
            }
        if match_status == MATCH_FINISHED:
            return {
                "prediction_outcome": OUTCOME_RESULT_MISSING,
                "evaluation_reason": "halftime_result_missing",
                "match_status": match_status,
            }
        return {
            "prediction_outcome": OUTCOME_PENDING,
            "evaluation_reason": "awaiting_halftime_result",
            "match_status": match_status,
        }

    # Mercati FT
    if ft_ready:
        ev = evaluate_market_selection(market_key, match_result)
        return {
            "prediction_outcome": ev.get("evaluation_status") or OUTCOME_NOT_EVALUABLE,
            "evaluation_reason": ev.get("evaluation_reason"),
            "match_status": match_status,
            "result_home_ft": ev.get("result_home_ft"),
            "result_away_ft": ev.get("result_away_ft"),
            "result_home_ht": ev.get("result_home_ht"),
            "result_away_ht": ev.get("result_away_ht"),
        }

    if match_status == MATCH_FINISHED:
        return {
            "prediction_outcome": OUTCOME_RESULT_MISSING,
            "evaluation_reason": "fulltime_result_missing",
            "match_status": match_status,
        }

    return {
        "prediction_outcome": OUTCOME_PENDING,
        "evaluation_reason": "awaiting_fulltime_result",
        "match_status": match_status,
        "result_home_ft": row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home,
        "result_away_ft": row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away,
        "result_home_ht": row.score_halftime_home,
        "result_away_ht": row.score_halftime_away,
    }


def _enrich_opportunity_with_outcome(
    opp: dict[str, Any],
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    market_key = str((opp.get("market") or {}).get("market_key") or "")
    evaluation = evaluate_bet_builder_prediction_outcome(market_key=market_key, row=row)
    enriched = dict(opp)
    enriched["prediction_outcome"] = evaluation["prediction_outcome"]
    enriched["evaluation_reason"] = evaluation.get("evaluation_reason")
    enriched["match_status"] = evaluation["match_status"]
    return enriched


def _score_payload(row: CecchinoTodayFixture) -> dict[str, Any]:
    ft_home = row.score_fulltime_home
    ft_away = row.score_fulltime_away
    if ft_home is None and ft_away is None:
        ft_home = row.goals_home
        ft_away = row.goals_away
    return {
        "goals_home": row.goals_home,
        "goals_away": row.goals_away,
        "fulltime_home": ft_home,
        "fulltime_away": ft_away,
        "halftime_home": row.score_halftime_home,
        "halftime_away": row.score_halftime_away,
    }


def _fixture_results_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": row.provider_fixture_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "country": row.country_name,
        "league": row.league_name,
        "home": {
            "name": row.home_team_name,
            "logo": row.home_team_logo_url,
        },
        "away": {
            "name": row.away_team_name,
            "logo": row.away_team_logo_url,
        },
        "match_status": normalize_match_status(row),
        "elapsed_minutes": row.elapsed_minutes,
        "score": _score_payload(row),
    }


def _primary_passes_filters(
    primary: dict[str, Any],
    *,
    outcome: str | None,
    market_key: str | None,
    origin: str | None,
    min_purchasability: float | None,
) -> bool:
    if outcome and primary.get("prediction_outcome") != outcome:
        return False
    if market_key:
        mk = (primary.get("market") or {}).get("market_key")
        if mk != market_key:
            return False
    if origin and primary.get("origin") != origin:
        return False
    if min_purchasability is not None:
        score = (primary.get("purchasability_v36") or {}).get("score")
        if score is None:
            return False
        try:
            if float(score) < float(min_purchasability):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _sort_fixture_results(
    fixtures: list[dict[str, Any]],
    sort: str,
) -> list[dict[str, Any]]:
    copy = list(fixtures)

    def kickoff_key(item: dict[str, Any]) -> str:
        return str((item.get("fixture") or {}).get("kickoff") or "")

    if sort == SORT_KICKOFF_ASC:
        # Null / empty kickoff last; valid ISO ASC (earliest first).
        def kickoff_asc_key(item: dict[str, Any]) -> tuple:
            raw = (item.get("fixture") or {}).get("kickoff")
            if raw is None or str(raw).strip() == "":
                return (1, "")
            return (0, str(raw))

        copy.sort(key=kickoff_asc_key)
        return copy

    if sort == SORT_LOST_FIRST:

        def lost_key(item: dict[str, Any]) -> tuple:
            outcome = (item.get("primary") or {}).get("prediction_outcome")
            is_lost = 0 if outcome == OUTCOME_LOST else 1
            return (is_lost, kickoff_key(item))

        copy.sort(key=lost_key, reverse=False)
        # Within same lost flag, more recent first → reverse kickoff within groups
        copy.sort(
            key=lambda item: (
                0 if (item.get("primary") or {}).get("prediction_outcome") == OUTCOME_LOST else 1,
                kickoff_key(item),
            ),
            reverse=False,
        )
        # Stable: first by lost, then by kickoff DESC
        copy.sort(key=kickoff_key, reverse=True)
        copy.sort(
            key=lambda item: 0
            if (item.get("primary") or {}).get("prediction_outcome") == OUTCOME_LOST
            else 1
        )
        return copy

    if sort == SORT_PURCHASABILITY_DESC:

        def purch_key(item: dict[str, Any]) -> tuple:
            score = (item.get("primary") or {}).get("purchasability_v36") or {}
            val = score.get("score")
            null = val is None
            try:
                num = -float(val) if val is not None else 0.0
            except (TypeError, ValueError):
                null = True
                num = 0.0
            return (1 if null else 0, num, kickoff_key(item))

        copy.sort(key=purch_key)
        return copy

    # Default: più recenti prima
    copy.sort(key=kickoff_key, reverse=True)
    return copy


def _primary_quota_book(primary: dict[str, Any]) -> float | None:
    """Quota Book della primary (price_value.quota_book). Nessun fallback Cecchino."""
    pv = primary.get("price_value")
    if not isinstance(pv, dict):
        return None
    raw = pv.get("quota_book")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value


def _build_summary(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """KPI solo sulle primary.

    Profitto/ROI: flat stake teorico 1u su primary WON/LOST con quota_book > 1.0.
    Book N/D esclusa da Profit/ROI ma non da Win Rate.
    """
    primary_predictions = len(fixtures)
    won = lost = pending = not_evaluable = result_missing = 0
    live_or_pending = 0
    priced_settled = priced_won = priced_lost = 0
    profit = Decimal("0")

    for item in fixtures:
        primary = item.get("primary") or {}
        outcome = primary.get("prediction_outcome")
        match_status = (item.get("fixture") or {}).get("match_status")
        if outcome == OUTCOME_WON:
            won += 1
        elif outcome == OUTCOME_LOST:
            lost += 1
        elif outcome == OUTCOME_PENDING:
            pending += 1
        elif outcome == OUTCOME_NOT_EVALUABLE:
            not_evaluable += 1
        elif outcome == OUTCOME_RESULT_MISSING:
            result_missing += 1

        if match_status == MATCH_LIVE or outcome == OUTCOME_PENDING:
            live_or_pending += 1

        if outcome in (OUTCOME_WON, OUTCOME_LOST):
            quota_book = _primary_quota_book(primary)
            if quota_book is not None and quota_book > 1.0:
                priced_settled += 1
                if outcome == OUTCOME_WON:
                    priced_won += 1
                    profit += Decimal(str(quota_book)) - Decimal("1")
                else:
                    priced_lost += 1
                    profit += Decimal("-1")

    settled = won + lost
    win_rate = round(won / settled, 4) if settled > 0 else None

    if priced_settled > 0:
        profit_units = float(round(profit, 4))
        roi_pct = float(round(profit / Decimal(priced_settled) * Decimal("100"), 4))
    else:
        profit_units = None
        roi_pct = None

    return {
        "primary_predictions": primary_predictions,
        "settled": settled,
        "won": won,
        "lost": lost,
        "pending": pending,
        "not_evaluable": not_evaluable,
        "result_missing": result_missing,
        "live_or_pending": live_or_pending,
        "win_rate": win_rate,
        "priced_settled": priced_settled,
        "priced_won": priced_won,
        "priced_lost": priced_lost,
        "profit_units": profit_units,
        "roi_pct": roi_pct,
    }


# --- Rapporti (richiesta di Giovanni, 13/10/2026) ---------------------------------------------
# Fasce di quota, contributo dell'Acquistabilita' a scalini, mese per mese e mappa mercato x fascia.
# Solo primary concluse (vinta/persa) con quota Bet365 > 1, come Profitto e ROI del riepilogo.
# Forbice di incertezza al 90% sul ROI (approssimazione normale sul profitto per giocata).

QUOTA_BANDS: tuple[tuple[str, float, float], ...] = (
    ("sotto 1,41", 0.0, 1.405),
    ("1,41-1,60", 1.405, 1.605),
    ("1,61-1,80", 1.605, 1.805),
    ("1,81-2,00", 1.805, 2.005),
    ("2,01-2,20", 2.005, 2.205),
    ("da 2,21", 2.205, 1e9),
)
INDEX_STEPS: tuple[float | None, ...] = (None, 50.0, 60.0, 70.0)
VALUE_MIN_PLAYS = 30
_Z90 = 1.645


def quota_band(q: float) -> str:
    for name, lo, hi in QUOTA_BANDS:
        if lo <= q < hi:
            return name
    return QUOTA_BANDS[-1][0]


def roi_stats(plays: list[tuple[bool, float]]) -> dict[str, Any]:
    """plays = (vinta, quota). ROI e forbice al 90% sul profitto medio per giocata da 1 unita'."""
    n = len(plays)
    if n == 0:
        return {"plays": 0, "won": 0, "win_pct": None, "break_even_pct": None, "avg_quota": None,
                "profit": 0.0, "roi_pct": None, "roi_low_pct": None, "roi_high_pct": None}
    profits = [(q - 1.0) if w else -1.0 for w, q in plays]
    mean = sum(profits) / n
    var = sum((p - mean) ** 2 for p in profits) / (n - 1) if n > 1 else 0.0
    half = _Z90 * (var ** 0.5) / (n ** 0.5) if n > 1 else None
    won = sum(1 for w, _ in plays if w)
    return {
        "plays": n,
        "won": won,
        "win_pct": round(100.0 * won / n, 1),
        "break_even_pct": round(100.0 * sum(1.0 / q for _, q in plays) / n, 1),
        "avg_quota": round(sum(q for _, q in plays) / n, 2),
        "profit": round(sum(profits), 2),
        "roi_pct": round(100.0 * mean, 1),
        "roi_low_pct": round(100.0 * (mean - half), 1) if half is not None else None,
        "roi_high_pct": round(100.0 * (mean + half), 1) if half is not None else None,
    }


def _settled_play(primary: dict[str, Any]) -> tuple[bool, float] | None:
    outcome = primary.get("prediction_outcome")
    if outcome not in (OUTCOME_WON, OUTCOME_LOST):
        return None
    q = _primary_quota_book(primary)
    if q is None or q <= 1.0:
        return None
    return outcome == OUTCOME_WON, q


def build_results_report(
    entries: list[dict[str, Any]],
    *,
    match_status: str | None,
    market_key: str | None,
    origin: str | None,
    min_purchasability: float | None,
) -> dict[str, Any]:
    def select_plays(*, market: str | None, min_p: float | None) -> list[tuple[dict[str, Any], dict[str, Any], tuple[bool, float]]]:
        out = []
        for entry in entries:
            if match_status and entry["match_status"] != match_status:
                continue
            ranked = entry["ranked"]
            if not ranked:
                continue
            primary = ranked[0]
            if not _primary_passes_filters(primary, outcome=None, market_key=market, origin=origin, min_purchasability=min_p):
                continue
            play = _settled_play(primary)
            if play is not None:
                out.append((entry, primary, play))
        return out

    current = select_plays(market=market_key, min_p=min_purchasability)
    without_index = select_plays(market=market_key, min_p=None)
    all_markets = select_plays(market=None, min_p=min_purchasability)

    bands = []
    for name, _lo, _hi in QUOTA_BANDS:
        bands.append({"band": name, **roi_stats([p for _, _, p in current if quota_band(p[1]) == name])})

    baseline = roi_stats([p for _, _, p in without_index])
    steps = []
    for step in INDEX_STEPS:
        chosen = []
        for _entry, primary, p in without_index:
            if step is None:
                chosen.append(p)
                continue
            score = (primary.get("purchasability_v36") or {}).get("score")
            try:
                if score is not None and float(score) >= step:
                    chosen.append(p)
            except (TypeError, ValueError):
                continue
        s = roi_stats(chosen)
        s["step"] = "senza indice" if step is None else f"indice da {int(step)}"
        s["roi_vs_baseline_pct"] = (
            round(s["roi_pct"] - baseline["roi_pct"], 1)
            if s["roi_pct"] is not None and baseline["roi_pct"] is not None
            else None
        )
        steps.append(s)

    by_month: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    for entry, _primary, p in current:
        month = str((entry["fixture"] or {}).get("scan_date") or "")[:7]
        if month:
            by_month[month].append(p)
    monthly = [{"month": m, **roi_stats(v)} for m, v in sorted(by_month.items())]

    cells: dict[tuple[str, str], list[tuple[bool, float]]] = defaultdict(list)
    labels: dict[str, str] = {}
    for _entry, primary, p in all_markets:
        market = primary.get("market") or {}
        mk = str(market.get("market_key") or "")
        labels[mk] = str(market.get("label") or mk)
        cells[(mk, quota_band(p[1]))].append(p)
    market_bands = []
    for (mk, band), plays in cells.items():
        s = roi_stats(plays)
        s.update(
            {
                "market_key": mk,
                "market_label": labels.get(mk, mk),
                "band": band,
                "value": bool(s["plays"] >= VALUE_MIN_PLAYS and (s["roi_low_pct"] or -1) > 0),
            }
        )
        market_bands.append(s)
    market_bands.sort(key=lambda c: (c["market_key"], [b[0] for b in QUOTA_BANDS].index(c["band"])))

    return {
        "summary": roi_stats([p for _, _, p in current]),
        "quota_bands": bands,
        "index_steps": steps,
        "monthly": monthly,
        "market_bands": market_bands,
        "value_rule": f"valore = almeno {VALUE_MIN_PLAYS} giocate e ROI positivo anche nel caso peggiore della forbice al 90%",
    }


# --- Memoria per partita (13/10/2026) -----------------------------------------------------------
# Prima ogni ricerca rileggeva tutte le partite del periodo con i loro dati pesanti e ricalcolava tutte
# le opportunity: circa 50 secondi su due mesi, a ogni cambio di filtro. Il risultato di una partita
# dipende solo dalla sua riga Today e dalla sua anteprima Intensita' Goal: si calcola una volta e si
# ricalcola solo quando una delle due cambia (updated_at della riga, istante dello snapshot GI, bundle
# attivo). Stessa logica e stessi numeri di prima; cambia solo quanto spesso si rifanno i conti.

_ENTRY_CACHE: dict[int, tuple[tuple[Any, ...], dict[str, Any]]] = {}
_ENTRY_CACHE_LOCK = threading.Lock()
_ENTRY_CACHE_MAX = 6000  # ~16 KB a partita: circa 100 MB al massimo
_ENTRY_BUILD_CHUNK = 200


def _gi_signatures(db: Session, ids: list[int]) -> tuple[Any, dict[int, Any]]:
    """Bundle GI attivo e istante dell'ultimo snapshot per partita (solo colonne leggere)."""
    from app.models.cecchino_goal_intensity_v5_preview import CecchinoGoalIntensityV5PreviewSnapshot
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_active_bundle

    bundle = get_active_bundle(db)
    if bundle is None or not ids:
        return None, {}
    snap = CecchinoGoalIntensityV5PreviewSnapshot
    out: dict[int, Any] = {}
    for start_i in range(0, len(ids), 1000):
        chunk = ids[start_i : start_i + 1000]
        for fid, a, b, c in db.execute(
            select(snap.today_fixture_id, snap.last_computed_at, snap.source_snapshot_at, snap.updated_at).where(
                snap.bundle_id == bundle.id, snap.today_fixture_id.in_(chunk)
            )
        ).all():
            out[int(fid)] = (a, b, c)
    return (bundle.id, getattr(bundle, "updated_at", None)), out


def _build_entries(db: Session, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Calcolo completo (come prima) per le sole partite nuove o cambiate, a blocchi."""
    out: dict[int, dict[str, Any]] = {}
    for start_i in range(0, len(ids), _ENTRY_BUILD_CHUNK):
        chunk = ids[start_i : start_i + _ENTRY_BUILD_CHUNK]
        wanted = set(chunk)
        rows = [
            r
            for r in db.scalars(select(CecchinoTodayFixture).where(CecchinoTodayFixture.id.in_(chunk))).all()
            if int(r.id) in wanted
        ]
        gi_by_fixture, _max_gi = _load_gi_payloads_batch(db, rows)
        all_opps, _max_v31 = build_opportunities_for_rows(
            rows,
            gi_by_fixture=gi_by_fixture,
            market_filter=None,
            origin_filter=None,
            freshness_scan_date=None,
        )
        by_fixture: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for opp in all_opps:
            fid = int((opp.get("fixture") or {}).get("today_fixture_id") or 0)
            if fid:
                by_fixture[fid].append(opp)
        for row in rows:
            opps = by_fixture.get(int(row.id), [])
            enriched = [_enrich_opportunity_with_outcome(o, row) for o in opps]
            out[int(row.id)] = {
                "match_status": normalize_match_status(row),
                "fixture": _fixture_results_block(row),
                "ranked": sort_opportunities_by_evidence_strength(enriched, row.scan_date),
            }
        # le righe complete non servono piu': si libera la sessione blocco per blocco
        for row in rows:
            db.expunge(row)
    return out


def _fixture_entries_for_range(db: Session, *, d_from: date, d_to: date, start: date) -> list[dict[str, Any]]:
    """Voci per partita nell'ordine di prima (kickoff decrescente), dalla memoria quando possibile."""
    light = db.execute(
        select(CecchinoTodayFixture.id, CecchinoTodayFixture.updated_at)
        .where(
            CecchinoTodayFixture.scan_date >= d_from,
            CecchinoTodayFixture.scan_date <= d_to,
            CecchinoTodayFixture.scan_date >= start,
            CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
        )
        .order_by(CecchinoTodayFixture.kickoff.desc().nullslast())
    ).all()
    ids = [int(r[0]) for r in light]
    bundle_sig, gi_sig = _gi_signatures(db, ids)
    signatures = {int(fid): (updated_at, bundle_sig, gi_sig.get(int(fid))) for fid, updated_at in light}

    with _ENTRY_CACHE_LOCK:
        stale = [fid for fid in ids if (_ENTRY_CACHE.get(fid) or (None,))[0] != signatures[fid]]
        if stale:
            built = _build_entries(db, stale)
            if len(_ENTRY_CACHE) + len(built) > _ENTRY_CACHE_MAX:
                _ENTRY_CACHE.clear()
            for fid, entry in built.items():
                _ENTRY_CACHE[fid] = (signatures[fid], entry)
        return [_ENTRY_CACHE[fid][1] for fid in ids if fid in _ENTRY_CACHE]


def warm_bet_builder_results_cache(days: int = 70) -> None:
    """Riempie la memoria all'avvio del backend, in background: la prima ricerca non attende."""
    from datetime import timedelta

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        today = datetime.now(ROME_TZ).date()
        d_from = max(BET_BUILDER_RESULTS_START_DATE, today - timedelta(days=days))
        _fixture_entries_for_range(db, d_from=d_from, d_to=today, start=BET_BUILDER_RESULTS_START_DATE)
    except Exception:  # noqa: BLE001 - la memoria e' un'ottimizzazione, mai un errore per l'app
        logging.getLogger(__name__).exception("bet builder results: riscaldamento memoria fallito")
    finally:
        db.close()


def aggregate_bet_builder_results(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    outcome: str | None = None,
    match_status: str | None = None,
    market_key: str | None = None,
    origin: str | None = None,
    min_purchasability: float | None = None,
    sort: str = SORT_RECENT,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read-model Results — solo dati persistiti, nessuna API esterna."""
    today = datetime.now(ROME_TZ).date()
    start = BET_BUILDER_RESULTS_START_DATE

    d_from = clamp_results_date(date_from, today=today)
    d_to = clamp_results_date(date_to, today=today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    # Mai interrogare prima di START
    if d_from < start:
        d_from = start
    if d_to < start:
        d_to = start

    outcome_filter = str(outcome).strip().lower() if outcome else None
    if outcome_filter and outcome_filter not in VALID_OUTCOMES:
        outcome_filter = None

    # BET-RESULTS-01.2 — asse match_status ortogonale a prediction outcome
    match_status_filter = str(match_status).strip().lower() if match_status else None
    if match_status_filter and match_status_filter not in MATCH_STATUS_CANONICAL:
        match_status_filter = None

    market_filter = str(market_key).strip().upper() if market_key else None
    if market_filter and market_filter not in BET_BUILDER_MARKET_KEY_SET:
        market_filter = None

    origin_filter = str(origin).strip().lower() if origin else None
    if origin_filter not in {
        ORIGIN_PRICE,
        ORIGIN_SIGNALS,
        ORIGIN_PRICE_AND_SIGNALS,
        None,
    }:
        origin_filter = None

    sort_key = str(sort or SORT_RECENT).strip().lower()
    if sort_key not in VALID_SORTS:
        sort_key = SORT_RECENT

    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    entries = _fixture_entries_for_range(db, d_from=d_from, d_to=d_to, start=start)

    fixture_results: list[dict[str, Any]] = []
    for entry in entries:
        if match_status_filter and entry["match_status"] != match_status_filter:
            continue
        ranked = entry["ranked"]
        primary = ranked[0] if ranked else None
        if primary is None:
            continue
        if not _primary_passes_filters(
            primary,
            outcome=outcome_filter,
            market_key=market_filter,
            origin=origin_filter,
            min_purchasability=min_purchasability,
        ):
            continue
        others = ranked[1:]
        fixture_results.append(
            {
                "fixture": entry["fixture"],
                "primary": primary,
                "other_opportunities": others,
                "primary_selection_version": primary_selection_version(
                    date.fromisoformat(entry["fixture"]["scan_date"]) if (entry.get("fixture") or {}).get("scan_date") else None
                ),
            }
        )

    fixture_results = _sort_fixture_results(fixture_results, sort_key)
    total = len(fixture_results)
    page = fixture_results[offset : offset + limit]
    summary = _build_summary(fixture_results)
    report = build_results_report(
        entries,
        match_status=match_status_filter,
        market_key=market_filter,
        origin=origin_filter,
        min_purchasability=min_purchasability,
    )

    return {
        "contract_version": BET_BUILDER_RESULTS_CONTRACT_VERSION,
        "available_from": start.isoformat(),
        "primary_selection_version": BET_BUILDER_PRIMARY_SELECTION_VERSION,
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "timezone": "Europe/Rome",
        "sort": sort_key,
        "limit": limit,
        "offset": offset,
        "total": total,
        "summary": summary,
        "report": report,
        "fixtures": page,
    }
