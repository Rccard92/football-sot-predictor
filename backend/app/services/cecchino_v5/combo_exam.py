"""Esame combo v1 sullo storico dei 16 campionati (docs/combo/COMBO_V1_PREREGISTRAZIONE.md). Sola lettura, sul server."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import text

from app.services.cecchino_v5.combo import VARS, SCENARIO_LABELS, actual_hit, match_combos, nearest_psd_corr, pick, pit_z, simulate
from app.services.cecchino_v5.constants import STAT_SPECIALIST_BY_KEY
from app.services.cecchino_v5.league_map import season_label
from app.services.cecchino_v5.model import expected_counts, load_history

logger = logging.getLogger(__name__)

EXAM_VERSION = "combo_exam_v1_20261024"
DEV = ("2022/23", "2023/24", "2024/25")
EXAM = "2025/26"
CHECK = "2026/27"
MAX_GAP = 2.5


def _load(db) -> tuple[list[dict[str, Any]], dict[int, tuple[float, float]]]:
    rows = db.execute(
        text(
            """
            SELECT id, division_code, match_date, home_team, away_team, referee, ft_home_goals, ft_away_goals,
                   home_shots_on_target, away_shots_on_target, home_corners, away_corners
            FROM cecchino_lab_matches
            WHERE ft_home_goals IS NOT NULL AND match_date >= '2022-07-01'
            ORDER BY match_date, id
            """
        )
    ).mappings().all()
    lambdas = {
        int(mid): (float(lh), float(la))
        for mid, lh, la in db.execute(
            text("SELECT lab_match_id, lambda_home, lambda_away FROM cecchino_v3_match_predictions WHERE run_id = 11 AND lambda_home IS NOT NULL")
        ).all()
    }
    return [dict(r) for r in rows], lambdas


def _means(hist, m: dict[str, Any], lam: tuple[float, float] | None) -> dict[str, float] | None:
    lh, la = lam if lam else (None, None)
    out: dict[str, float] = {}
    for key, prefix in (("tiri_porta", "s"), ("angoli", "c")):
        e = expected_counts(
            hist, STAT_SPECIALIST_BY_KEY[key], division=m["division_code"], day=m["match_date"],
            home=m["home_team"], away=m["away_team"], lambda_home=lh, lambda_away=la, referee=m["referee"],
        )
        if e is None:
            return None
        out[prefix + "h"], out[prefix + "a"] = e.home, e.away
    out["gh"], out["ga"] = (lh, la) if lam else (1.35, 1.10)  # senza gol V3 (2026/27) le combo sui gol si escludono
    return out


def _actual(m: dict[str, Any]) -> dict[str, float | None]:
    return {
        "gh": m["ft_home_goals"], "ga": m["ft_away_goals"],
        "sh": m["home_shots_on_target"], "sa": m["away_shots_on_target"],
        "ch": m["home_corners"], "ca": m["away_corners"],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    p = sum(r["p"] for r in rows) / n
    pi = sum(r["p_ind"] for r in rows) / n
    real = sum(1 for r in rows if r["hit"]) / n
    return {
        "n": n,
        "predicted_pct": round(100 * p, 2),
        "predicted_independent_pct": round(100 * pi, 2),
        "real_pct": round(100 * real, 2),
        "gap_pct": round(100 * (real - p), 2),
        "breakeven_quota": round(1 / real, 2) if real > 0 else None,
    }


def run_exam() -> dict[str, Any]:
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        matches, lambdas = _load(db)
    finally:
        gen.close()
    gen = readonly_session()
    db = next(gen)
    try:
        hist = load_history(db, since=date(2021, 7, 1))
    finally:
        gen.close()

    prepared = []
    for m in matches:
        s = season_label(m["match_date"])
        if s not in DEV + (EXAM, CHECK):
            continue
        lam = lambdas.get(int(m["id"]))
        if lam is None and s != CHECK:
            continue
        actual = _actual(m)
        if any(actual[v] is None for v in VARS):
            continue
        means = _means(hist, m, lam)
        if means is None:
            continue
        prepared.append((m, s, means, actual, lam is not None))

    # legami tra le statistiche: solo sviluppo
    rng = np.random.default_rng(20261024)
    zs = np.array([pit_z(means, actual, rng) for _, s, means, actual, _ in prepared if s in DEV])
    corr = nearest_psd_corr(np.corrcoef(zs.T))
    chol = np.linalg.cholesky(corr)

    picked: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_exam: list[tuple[float, float, bool]] = []
    per_scenario: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    per_day: dict[tuple[str, date], int] = defaultdict(int)
    for m, s, means, actual, has_goals in prepared:
        sims = simulate(means, chol, seed=int(m["id"]))
        cands = match_combos(sims, allow_goals=has_goals and s != CHECK)
        group = "sviluppo" if s in DEV else s
        if s == EXAM:
            for c in cands:
                hits = [actual_hit(leg, actual) for leg in c.legs]
                if None not in hits:
                    all_exam.append((c.p, c.p_independent, all(hits)))
        c = pick(cands)
        if c is None:
            continue
        hits = [actual_hit(leg, actual) for leg in c.legs]
        if None in hits:
            continue
        row = {"p": c.p, "p_ind": c.p_independent, "hit": all(hits), "scenario": c.scenario, "legs": len(c.legs)}
        picked[group].append(row)
        per_scenario[(group, c.scenario)].append(row)
        per_day[(group, m["match_date"])] += 1

    brier = None
    if all_exam:
        b_cop = sum((p - (1.0 if h else 0.0)) ** 2 for p, _, h in all_exam) / len(all_exam)
        b_ind = sum((pi - (1.0 if h else 0.0)) ** 2 for _, pi, h in all_exam) / len(all_exam)
        brier = {"candidates": len(all_exam), "copula": round(b_cop, 5), "independent": round(b_ind, 5)}
    exam_sel = _summary(picked.get(EXAM, []))
    checks = {
        "1_calibration_within_2_5": exam_sel.get("n", 0) > 0 and abs(exam_sel["gap_pct"]) <= MAX_GAP,
        "2_brier_better_than_independent": brier is not None and brier["copula"] < brier["independent"],
    }
    days = defaultdict(list)
    for (group, _), n in per_day.items():
        days[group].append(n)
    return {
        "exam": EXAM_VERSION,
        "preregistration": "docs/combo/COMBO_V1_PREREGISTRAZIONE.md",
        "matches_prepared": len(prepared),
        "correlation_vars": list(VARS),
        "correlation": [[round(float(x), 3) for x in row] for row in corr],
        "selected": {g: _summary(rows) for g, rows in picked.items()},
        "selected_by_scenario": {
            f"{g} · {SCENARIO_LABELS[sc]}": _summary(rows) for (g, sc), rows in sorted(per_scenario.items())
        },
        "selected_by_legs": {
            f"{g} · {k} giocate": _summary([r for r in rows if r["legs"] == k]) for g, rows in picked.items() for k in (2, 3)
        },
        "brier_exam_all_candidates": brier,
        "combos_per_matchday": {g: round(sum(v) / len(v), 1) for g, v in days.items()},
        "checks": checks,
        "passed": all(checks.values()),
    }


_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def exam_state(start: bool = False) -> dict[str, Any]:
    with _lock:
        if start and _state.get("status") in ("idle", "failed"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time()})

            def target() -> None:
                try:
                    result = run_exam()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("esame combo fallito")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="combo-exam", daemon=True).start()
        return dict(_state)
