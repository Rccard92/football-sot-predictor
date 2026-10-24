"""Esame V3.2 sulla stagione 2025 fuori dai 16 campionati (docs/v3/V32_ESAME_PREREGISTRAZIONE.md).

Gira sul server in un thread (sola lettura): per ogni campionato una sola previsione walk-forward del motore V3 estesa,
poi le 8 combinazioni cambiano solo il passo finale (fattore R e rho). Risultato in memoria.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

from sqlalchemy import select

from app.models import Competition
from app.services.cecchino.cecchino_fixture_history import MAJOR_LEAGUE_API_IDS
from app.services.cecchino_v3_live.engine import MIN_MATCHES_WITH_STATS, build_records, predict_records
from app.services.cecchino_v3_live.params import load_params
from app.services.cecchino_v3_live.v32 import corrected, league_factors

logger = logging.getLogger(__name__)

EXAM_VERSION = "v32_exam_v1_20261024"
SEASON = 2025
K_VALUES: tuple[float | None, ...] = (None, 20.0, 50.0, 100.0)
RHO_ZERO: tuple[bool, ...] = (False, True)
CANDIDATES = [(k, r) for k in K_VALUES for r in RHO_ZERO]
CURRENT = (None, False)
MAX_1X2_WORSENING = 0.002
MAX_CALIBRATION_GAP = 1.5  # punti percentuali
Z90 = 1.645
EPS = 1e-6

_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def _ll(p: float, outcome: bool) -> float:
    p = min(1.0 - EPS, max(EPS, p))
    return -math.log(p if outcome else 1.0 - p)


def _name(c: tuple[float | None, bool]) -> str:
    k, r = c
    return f"K={'spento' if k is None else int(k)} · rho={'0' if r else 'stimato'}"


def _summary(rows: list[dict[str, Any]], c: tuple[float | None, bool]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"candidate": _name(c), "n": 0}
    ou = sum(r["ou"][c] for r in rows) / n
    x12 = sum(r["x12"][c] for r in rows) / n
    pred = 100 * sum(r["o25"][c] for r in rows) / n
    real = 100 * sum(r["o25_real"] for r in rows) / n
    return {
        "candidate": _name(c),
        "n": n,
        "logloss_ou": round(ou, 5),
        "logloss_1x2": round(x12, 5),
        "over25_predicted_pct": round(pred, 2),
        "over25_real_pct": round(real, 2),
        "over25_gap_pct": round(real - pred, 2),
    }


def _paired(rows: list[dict[str, Any]], c: tuple[float | None, bool]) -> dict[str, Any]:
    diffs = [r["ou"][CURRENT] - r["ou"][c] for r in rows]  # positivo = la combinazione sbaglia meno
    n = len(diffs)
    if n < 2:
        return {"n": n}
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    half = Z90 * sd / math.sqrt(n)
    return {"n": n, "mean": round(mean, 6), "low": round(mean - half, 6), "high": round(mean + half, 6)}


def _match_rows(comp: Competition, params) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        built = build_records(db, comp, set())
    finally:
        db.close()
    info = {"league": int(comp.provider_league_id), "competition_id": int(comp.id), "stats_current": built.stats_current}
    if built.stats_current < MIN_MATCHES_WITH_STATS:
        return [], {**info, "skipped": "statistiche insufficienti"}
    finals = predict_records(built.records, params)
    factors = {k: league_factors(built.records, finals, k) for k in K_VALUES}
    rows: list[dict[str, Any]] = []
    for m in built.records:
        fin = finals.get(m.lab_match_id)
        if fin is None or m.season_label != str(SEASON) or not m.eval_eligible:
            continue
        total = m.ft_home + m.ft_away
        res = "H" if m.ft_home > m.ft_away else ("A" if m.ft_home < m.ft_away else "D")
        row: dict[str, Any] = {"ou": {}, "x12": {}, "o25": {}, "o25_real": total > 2}
        for c in CANDIDATES:
            k, rho0 = c
            p = corrected(fin, factors[k].get(m.lab_match_id, 1.0), rho0)["probabilities"]
            row["ou"][c] = (_ll(p["OVER_1_5"], total > 1) + _ll(p["OVER_2_5"], total > 2) + _ll(p["OVER_3_5"], total > 3)) / 3
            p1x2 = {"H": p["HOME"], "D": p["DRAW"], "A": p["AWAY"]}
            row["x12"][c] = -math.log(min(1.0 - EPS, max(EPS, p1x2[res])))
            row["o25"][c] = p["OVER_2_5"]
        rows.append(row)
    return rows, {**info, "matches": len(rows)}


def run_exam() -> dict[str, Any]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        params = load_params(db)
        comps = list(
            db.scalars(
                select(Competition)
                .where(Competition.season == SEASON, Competition.provider_league_id.not_in(tuple(MAJOR_LEAGUE_API_IDS)))
                .order_by(Competition.provider_league_id)
            ).all()
        )
        for c in comps:
            db.expunge(c)
    finally:
        db.close()
    dev: list[dict[str, Any]] = []
    ver: list[dict[str, Any]] = []
    leagues: list[dict[str, Any]] = []
    for i, comp in enumerate(comps):
        with _lock:
            _state["progress"] = f"{i + 1}/{len(comps)}"
        try:
            rows, info = _match_rows(comp, params)
        except Exception as exc:  # noqa: BLE001 - un campionato che fallisce non ferma l'esame
            logger.exception("esame V3.2: campionato %s fallito", comp.id)
            leagues.append({"league": int(comp.provider_league_id), "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        leagues.append(info)
        (dev if int(comp.provider_league_id) % 2 == 0 else ver).extend(rows)

    dev_current = _summary(dev, CURRENT)
    allowed = [c for c in CANDIDATES if dev and _summary(dev, c)["logloss_1x2"] <= dev_current["logloss_1x2"] + MAX_1X2_WORSENING]
    chosen = min(allowed, key=lambda c: _summary(dev, c)["logloss_ou"]) if allowed else CURRENT

    ver_current = _summary(ver, CURRENT)
    ver_chosen = _summary(ver, chosen)
    paired = _paired(ver, chosen)
    checks = {
        "1_logloss_ou_ci_above_zero": chosen != CURRENT and paired.get("low") is not None and paired["low"] > 0,
        "2_logloss_1x2_not_worse": ver_chosen.get("logloss_1x2", 9) <= ver_current.get("logloss_1x2", 0) + MAX_1X2_WORSENING,
        "3_over25_calibration": abs(ver_chosen.get("over25_gap_pct", 99)) <= MAX_CALIBRATION_GAP
        and abs(ver_chosen.get("over25_gap_pct", 99)) < abs(ver_current.get("over25_gap_pct", 0)),
    }
    return {
        "exam": EXAM_VERSION,
        "preregistration": "docs/v3/V32_ESAME_PREREGISTRAZIONE.md",
        "season": SEASON,
        "leagues_total": len(comps),
        "leagues_used": sum(1 for x in leagues if x.get("matches")),
        "development": {"matches": len(dev), "candidates": [_summary(dev, c) for c in CANDIDATES]},
        "chosen": _name(chosen),
        "verification": {
            "matches": len(ver),
            "current": ver_current,
            "chosen": ver_chosen,
            "paired_logloss_ou_current_minus_chosen": paired,
            "all_candidates": [_summary(ver, c) for c in CANDIDATES],
        },
        "checks": checks,
        "passed": all(checks.values()),
        "leagues": leagues,
    }


def exam_state(start: bool = False) -> dict[str, Any]:
    """Stato dell'esame; con `start` lo avvia in sottofondo se non e' gia' partito."""
    with _lock:
        if start and _state.get("status") in ("idle", "failed"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time(), "progress": "0"})

            def target() -> None:
                try:
                    result = run_exam()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("esame V3.2 fallito")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="v32-exam", daemon=True).start()
        return dict(_state)
