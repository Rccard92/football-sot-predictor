"""Confronto dei motori di previsione sullo stesso metro (audit, sola lettura, dal 20/10/2026).

Ogni motore viene ridotto a "giocate": partita, mercato, quota presa prima della partita, esito, probabilita'
stimata se c'e'. Poi le stesse misure per tutti: giocate concluse, vinte, ROI a 1 unita' con forbice al
90%, quota media e percentuale per andare in pari, e (dove c'e' la probabilita') quanto la stima e' realistica.

Motori (fonti nella mappa dati dell'audit):
- bet_builder: Bet Builder originale, una giocata principale per partita (Evidence Sort V2);
- v25_indice / v3_indice: predizioni dell'indice V2.5 / V3 (punteggio >= 70), registro live;
- v25_evidenza / v3_evidenza: la giocata in evidenza (piu' probabile con quota >= 1,41 e >= quota minima);
- combo: stesso mercato predetto da V2.5 e V3 senza pattern in contrasto;
- kpi_segnali: segnali KPI (rating >= 50), versione corrente;
- segnali_si: segnali del modello F acquisiti dal consenso, versione corrente;
- acquistabilita_v1: coorte prospettica dell'Acquistabilita' V1;
- v4: shortlist Cecchino V4 (giocate chiuse o regolate).
Quote: quelle registrate prima della partita (non di chiusura), tranne la V4 che misura anche il CLV.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.readonly import STATEMENT_TIMEOUT_MS
from app.services.cecchino.cecchino_bet_builder_results import quota_band, roi_stats

PLAYABLE_MIN_QUOTA = 1.41
INDEX_MIN_SCORE = 70.0


@dataclass
class Play:
    engine: str
    day: date
    league: str | None
    market: str
    quota: float
    won: bool
    probability: float | None = None
    clv: float | None = None


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _prob(v: Any) -> float | None:
    p = _f(v)
    if p is None:
        return None
    return p / 100.0 if p > 1.0 else p


def _plays_live_index(db: Session, d_from: date, d_to: date) -> list[Play]:
    rows = db.execute(
        text(
            """
            SELECT model, scan_date, league_name,
                   modules_json -> 'purchasability_index' AS idx,
                   result_json -> 'markets' AS res
            FROM cecchino_live_predictions
            WHERE scan_date BETWEEN :a AND :b AND model IN ('V2.5', 'V3') AND result_json IS NOT NULL
            """
        ),
        {"a": d_from, "b": d_to},
    ).all()
    out: list[Play] = []
    for model, day, league, idx, res in rows:
        if not isinstance(idx, dict) or idx.get("status") != "ok" or not isinstance(res, dict):
            continue
        prefix = "v25" if model == "V2.5" else "v3"
        preds = []
        for key, m in (idx.get("markets") or {}).items():
            score = _f((m or {}).get("score"))
            if score is None or score < INDEX_MIN_SCORE:
                continue
            won = (res.get(key) or {}).get("won")
            q = _f(m.get("quota"))
            if won is None or q is None or q <= 1.0:
                continue
            p = _prob(m.get("probability"))
            min_q = _f(m.get("min_quota"))
            preds.append((key, q, bool(won), p, min_q))
            out.append(Play(f"{prefix}_indice", day, league, key, q, bool(won), p))
        ok = [x for x in preds if x[3] is not None and x[4] is not None and x[1] >= PLAYABLE_MIN_QUOTA and x[1] >= x[4]]
        if ok:
            key, q, won, p, _ = max(ok, key=lambda x: x[3])
            out.append(Play(f"{prefix}_evidenza", day, league, key, q, won, p))
    return out


def _plays_combo(db: Session, d_from: date, d_to: date) -> list[Play]:
    from app.services.cecchino_live.bet_builder_v3 import bet_builder_v3

    payload = bet_builder_v3(db, date_from=d_from, date_to=d_to)
    out: list[Play] = []
    for item in payload.get("fixtures") or []:
        fx = item.get("fixture") or {}
        day = date.fromisoformat(fx["scan_date"]) if fx.get("scan_date") else d_from
        for c in item.get("combo") or []:
            q = _f(c.get("quota"))
            if c.get("won") is None or q is None or q <= 1.0:
                continue
            min_q = _f(c.get("min_quota"))
            out.append(Play("combo", day, fx.get("league"), c["market_key"], q, bool(c["won"]), (1.0 / min_q) if min_q else None))
    return out


def _plays_bet_builder(db: Session, d_from: date, d_to: date) -> list[Play]:
    from app.services.cecchino.cecchino_bet_builder_constants import BET_BUILDER_RESULTS_START_DATE
    from app.services.cecchino.cecchino_bet_builder_results import (
        OUTCOME_LOST,
        OUTCOME_WON,
        _fixture_entries_for_range,
        _primary_quota_book,
    )

    start = BET_BUILDER_RESULTS_START_DATE
    entries = _fixture_entries_for_range(db, d_from=max(d_from, start), d_to=d_to, start=start)
    out: list[Play] = []
    for e in entries:
        if not e["ranked"]:
            continue
        p = e["ranked"][0]
        outcome = p.get("prediction_outcome")
        q = _primary_quota_book(p)
        if outcome not in (OUTCOME_WON, OUTCOME_LOST) or q is None or q <= 1.0:
            continue
        fx = e["fixture"] or {}
        day = date.fromisoformat(fx["scan_date"]) if fx.get("scan_date") else d_from
        market = (p.get("market") or {}).get("market_key") or "?"
        out.append(Play("bet_builder", day, fx.get("league"), market, q, outcome == OUTCOME_WON))
    return out


def _plays_sql(engine: str, sql: str) -> Callable[[Session, date, date], list[Play]]:
    def load(db: Session, d_from: date, d_to: date) -> list[Play]:
        out: list[Play] = []
        for day, league, market, quota, status, prob in db.execute(text(sql), {"a": d_from, "b": d_to}).all():
            q = _f(quota)
            if q is None or q <= 1.0 or status not in ("won", "lost"):
                continue
            out.append(Play(engine, day, league, str(market or "?"), q, status == "won", _prob(prob)))
        return out

    return load


_plays_kpi = _plays_sql(
    "kpi_segnali",
    """
    SELECT scan_date, league_name, selection_key, quota_book, evaluation_status, prob_cecchino
    FROM cecchino_kpi_signal_activations
    WHERE is_current AND scan_date BETWEEN :a AND :b AND evaluation_status IN ('won', 'lost')
    """,
)

_plays_si = _plays_sql(
    "segnali_si",
    """
    SELECT a.scan_date, t.league_name, a.target_market_key, a.quota_book, a.evaluation_status, a.prob_cecchino
    FROM cecchino_signal_activations a
    LEFT JOIN cecchino_today_fixtures t ON t.id = a.today_fixture_id
    WHERE a.is_current AND a.model_key = 'F' AND a.is_acquired IS TRUE
      AND a.scan_date BETWEEN :a AND :b AND a.evaluation_status IN ('won', 'lost')
    """,
)

_plays_purch_v1 = _plays_sql(
    "acquistabilita_v1",
    """
    SELECT scan_date, league_name, market_key, quota_book, evaluation_status, prob_cecchino
    FROM cecchino_purchasability_evaluations
    WHERE is_current AND source_cohort = 'prospective_persisted'
      AND scan_date BETWEEN :a AND :b AND evaluation_status IN ('won', 'lost')
    """,
)


def _plays_v4(db: Session, d_from: date, d_to: date) -> list[Play]:
    rows = db.execute(
        text(
            """
            SELECT s.day, f.competition, si.market_key, si.quota, si.result, si.probability, si.clv
            FROM cecchino_v4_shortlist_items si
            JOIN cecchino_v4_shortlists s ON s.id = si.shortlist_id
            JOIN cecchino_v4_fixtures f ON f.id = si.fixture_id
            WHERE si.status <> 'provvisoria' AND s.day BETWEEN :a AND :b AND si.result IN ('vinta', 'persa')
            """
        ),
        {"a": d_from, "b": d_to},
    ).all()
    return [
        Play("v4", day, league, market, float(q), result == "vinta", _prob(p), _f(clv))
        for day, league, market, q, result, p, clv in rows
        if _f(q) is not None and float(q) > 1.0
    ]


ENGINES: dict[str, Callable[[Session, date, date], list[Play]]] = {
    "bet_builder": _plays_bet_builder,
    "live_index": _plays_live_index,  # v25/v3 indice + evidenza
    "combo": _plays_combo,
    "kpi_segnali": _plays_kpi,
    "segnali_si": _plays_si,
    "acquistabilita_v1": _plays_purch_v1,
    "v4": _plays_v4,
}

GROUPS: dict[str, Callable[[Play], tuple[str, ...]]] = {
    "engine": lambda p: (p.engine,),
    "engine_market": lambda p: (p.engine, p.market),
    "engine_band": lambda p: (p.engine, quota_band(p.quota)),
    "engine_month": lambda p: (p.engine, p.day.isoformat()[:7]),
    "engine_league": lambda p: (p.engine, p.league or "?"),
}


def _calibration(plays: list[Play]) -> dict[str, Any] | None:
    with_p = [p for p in plays if p.probability is not None]
    if len(with_p) < 20:
        return None
    predicted = sum(p.probability for p in with_p) / len(with_p)  # type: ignore[misc]
    actual = sum(1 for p in with_p if p.won) / len(with_p)
    brier = sum(((p.probability or 0.0) - (1.0 if p.won else 0.0)) ** 2 for p in with_p) / len(with_p)
    return {
        "plays_with_probability": len(with_p),
        "predicted_win_pct": round(100 * predicted, 1),
        "actual_win_pct": round(100 * actual, 1),
        "gap_pct": round(100 * (actual - predicted), 1),
        "brier": round(brier, 4),
    }


def compare_engines(db: Session, *, date_from: date, date_to: date, group_by: str = "engine", min_plays: int = 1) -> dict[str, Any]:
    if group_by not in GROUPS:
        raise ValueError(f"group_by non valido: {group_by}. Ammessi: {', '.join(GROUPS)}")
    plays: list[Play] = []
    errors: dict[str, str] = {}
    for name, loader in ENGINES.items():
        try:
            plays.extend(loader(db, date_from, date_to))
        except Exception as exc:  # noqa: BLE001 - un motore che fallisce non ferma gli altri
            errors[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
            # la transazione e' annullata: se ne apre una nuova, sempre in sola lettura e con timeout
            db.rollback()
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
    key_fn = GROUPS[group_by]
    buckets: dict[tuple[str, ...], list[Play]] = defaultdict(list)
    for p in plays:
        buckets[key_fn(p)].append(p)
    rows = []
    for key, ps in buckets.items():
        if len(ps) < min_plays:
            continue
        stats = roi_stats([(p.won, p.quota) for p in ps])
        clvs = [p.clv for p in ps if p.clv is not None]
        rows.append(
            {
                "group": list(key),
                **stats,
                "calibration": _calibration(ps),
                "avg_clv_pct": round(100 * sum(clvs) / len(clvs), 2) if clvs else None,
            }
        )
    rows.sort(key=lambda r: (r["group"][0], -(r["plays"] or 0)))
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "group_by": group_by,
        "rows": rows,
        "errors": errors,
        "notes": [
            "ROI a 1 unita' con forbice al 90%; quote prese prima della partita (non di chiusura), tranne la V4.",
            "Un motore con molte giocate per partita (kpi, segnali, indice) non e' confrontabile 1:1 con uno a una giocata per partita (bet_builder, evidenza, v4).",
            "calibration: probabilita' stimata media contro vinte reali; brier piu' basso = stime migliori.",
        ],
    }
