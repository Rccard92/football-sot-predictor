"""Esame strato squadre v2 (docs/squadre/SQUADRE_V2_PREREGISTRAZIONE.md). Sola lettura, sul server.

Valore del giocatore con il plus-minus regolarizzato per partita: residuo della differenza reti rispetto ai gol attesi
della V3, diviso tra i giocatori in proporzione ai minuti (regressione ridge). Poi indici di formazione (F) e di assenze
del mattino (A) e correzione dei gol come nella v1.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import lsqr

from app.services.cecchino_v3.markets import market_probabilities
from app.services.cecchino_v5.league_map import _odds, _roi, outcome, season_label
from app.services.cecchino_v5.squad_exam import RULE_MARKETS, Z90, _load, data_status

logger = logging.getLogger(__name__)

EXAM_VERSION = "squadre_v2_20261106"
BETA_DEV = ("2022/23", "2023/24")
FIT_AB = "2024/25"
BETA_EXAM = ("2022/23", "2023/24", "2024/25")
EXAM = "2025/26"
LAMBDAS = (10.0, 30.0, 100.0, 300.0)
WINDOW = 10
MIN_TEAM_MATCHES = 3
PENALTY = 0.5


def _records(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Partite V4 collegate al Lab, in ordine di calcio d'inizio, con giocatori (minuti, titolare) e assenti."""
    out = []
    for fx in data["fixtures"]:
        lab = None
        for delta in (0, -1, 1):
            lab = data["lab"].get((fx["league_code"], fx["match_date"] + timedelta(days=delta), fx["home_team_history"], fx["away_team_history"]))
            if lab:
                break
        if lab is None or lab["lambda_home"] is None:
            continue
        rows = data["minutes"].get(int(fx["id"]), [])
        home, away = int(fx["home_team_api_id"]), int(fx["away_team_api_id"])
        out.append(
            {
                "season": season_label(fx["match_date"]),
                "lab": lab,
                "home": home,
                "away": away,
                "players": {
                    home: [(p, m, s) for t, p, m, s, _ in rows if t == home],
                    away: [(p, m, s) for t, p, m, s, _ in rows if t == away],
                },
                "missing": {
                    home: data["injuries"].get((int(fx["api_fixture_id"]), home), set()),
                    away: data["injuries"].get((int(fx["api_fixture_id"]), away), set()),
                },
                "residual": (lab["ft_home_goals"] - lab["ft_away_goals"]) - (lab["lambda_home"] - lab["lambda_away"]),
            }
        )
    return out


def fit_values(records: list[dict[str, Any]], seasons: tuple[str, ...], lam: float) -> dict[int, float]:
    """Plus-minus regolarizzato: residuo = somma(valore × minuti/90) casa − ospite, ridge con peso lam."""
    use = [r for r in records if r["season"] in seasons]
    index: dict[int, int] = {}
    rows, cols, vals, y = [], [], [], []
    for i, r in enumerate(use):
        for team, sign in ((r["home"], 1.0), (r["away"], -1.0)):
            for p, m, _ in r["players"][team]:
                if m <= 0:
                    continue
                j = index.setdefault(p, len(index))
                rows.append(i)
                cols.append(j)
                vals.append(sign * m / 90.0)
        y.append(r["residual"])
    if not index:
        return {}
    a = csr_matrix((vals, (rows, cols)), shape=(len(use), len(index)))
    beta = lsqr(a, np.array(y), damp=math.sqrt(lam))[0]
    return {p: float(beta[j]) for p, j in index.items()}


def _strength(players, values: dict[int, float]) -> float:
    return sum(values.get(p, 0.0) for p in players)


def attach_indices(records: list[dict[str, Any]], values: dict[int, float]) -> None:
    """Per ogni partita: F (titolari rispetto alla media delle ultime 10) e A (− valore degli abituali assenti)."""
    history: dict[tuple[str, int], deque] = defaultdict(lambda: deque(maxlen=WINDOW))
    for r in records:
        for side, team in (("home", r["home"]), ("away", r["away"])):
            past = history[(r["season"], team)]
            if len(past) < MIN_TEAM_MATCHES:
                r[f"F_{side}"] = r[f"A_{side}"] = None
                continue
            starters = [p for p, _, s in r["players"][team] if s]
            avg = sum(_strength(xi, values) for xi, _ in past) / len(past)
            r[f"F_{side}"] = (_strength(starters, values) - avg) if starters else None
            mins: dict[int, int] = defaultdict(int)
            for _, ms in past:
                for p, m in ms:
                    mins[p] += m
            usual = sorted(mins, key=lambda p: -mins[p])[:11]
            r[f"A_{side}"] = -sum(values.get(p, 0.0) for p in usual if p in r["missing"][team])
        for team in (r["home"], r["away"]):
            history[(r["season"], team)].append(
                ([p for p, _, s in r["players"][team] if s], [(p, m) for p, m, _ in r["players"][team]])
            )


def _usable(r: dict[str, Any], kind: str) -> bool:
    return r.get(f"{kind}_home") is not None and r.get(f"{kind}_away") is not None


def fit_ab(rows: list[dict[str, Any]], kind: str) -> tuple[float, float]:
    use = [r for r in rows if _usable(r, kind)]
    if not use:
        return 0.0, 0.0
    lh = np.log([r["lab"]["lambda_home"] for r in use])
    la = np.log([r["lab"]["lambda_away"] for r in use])
    ih = np.array([r[f"{kind}_home"] for r in use])
    ia = np.array([r[f"{kind}_away"] for r in use])
    gh = np.array([r["lab"]["ft_home_goals"] for r in use])
    ga = np.array([r["lab"]["ft_away_goals"] for r in use])

    def nll(x: np.ndarray) -> float:
        a, b = x
        mh = lh + a * ih + b * ia
        ma = la + a * ia + b * ih
        return float(np.sum(np.exp(mh) - gh * mh) + np.sum(np.exp(ma) - ga * ma) + PENALTY * (a * a + b * b))

    res = minimize(nll, np.zeros(2), method="BFGS")
    return float(res.x[0]), float(res.x[1])


def _probs(r: dict[str, Any], kind: str | None, ab: tuple[float, float]) -> dict[str, float]:
    lab = r["lab"]
    lh, la = lab["lambda_home"], lab["lambda_away"]
    if kind is not None and _usable(r, kind):
        lh *= math.exp(ab[0] * r[f"{kind}_home"] + ab[1] * r[f"{kind}_away"])
        la *= math.exp(ab[0] * r[f"{kind}_away"] + ab[1] * r[f"{kind}_home"])
    return market_probabilities(lh, la, float(lab["rho"] or 0.0), float(lab["ht_share"] or 0.45))


def evaluate(rows: list[dict[str, Any]], kind: str, ab: tuple[float, float]) -> dict[str, Any]:
    use = [r for r in rows if _usable(r, kind)]
    diffs, plays_new, plays_old = [], [], []
    for r in use:
        lab = r["lab"]
        gh, ga = lab["ft_home_goals"], lab["ft_away_goals"]
        res = "HOME" if gh > ga else ("AWAY" if gh < ga else "DRAW")
        over = gh + ga > 2
        losses = []
        for which in (None, kind):
            p = _probs(r, which, ab)
            losses.append((-math.log(max(1e-6, p[res])) - math.log(max(1e-6, p["OVER_2_5"] if over else 1 - p["OVER_2_5"]))) / 2)
            best = None
            for mk in RULE_MARKETS:
                q = _odds(lab, mk)
                o = outcome(mk, lab)
                if q is None or o is None or not (1.50 <= q <= 2.50):
                    continue
                score = p[mk] * q
                if score >= 1.05 and (best is None or score > best[0]):
                    best = (score, o, q)
            if best:
                (plays_old if which is None else plays_new).append((best[1], best[2]))
        diffs.append(losses[0] - losses[1])
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    half = Z90 * sd / math.sqrt(n) if n > 1 else 0.0
    spread = [abs(r[f"{kind}_home"]) + abs(r[f"{kind}_away"]) for r in use]
    return {
        "matches": n,
        "logloss_gain": {"mean": round(mean, 6), "low": round(mean - half, 6), "high": round(mean + half, 6)},
        "roi_corrected": _roi(plays_new),
        "roi_v3": _roi(plays_old),
        "index_mean_abs": round(sum(spread) / len(spread), 4) if spread else None,
    }


def _corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    return float(np.corrcoef(np.array(x), np.array(y))[0, 1])


def run_exam() -> dict[str, Any]:
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        status = data_status(db)
        data = _load(db)
    finally:
        gen.close()
    records = _records(data)
    del data

    # scelta di lambda: valori sul 2022/23-2023/24, correlazione forza titolari (casa - ospite) / residuo nel 2024/25
    lam_scores = {}
    for lam in LAMBDAS:
        values = fit_values(records, BETA_DEV, lam)
        xs, ys = [], []
        for r in records:
            if r["season"] != FIT_AB:
                continue
            sh = _strength([p for p, _, s in r["players"][r["home"]] if s], values)
            sa = _strength([p for p, _, s in r["players"][r["away"]] if s], values)
            xs.append(sh - sa)
            ys.append(r["residual"])
        lam_scores[lam] = _corr(xs, ys)
    lam = max(LAMBDAS, key=lambda k: lam_scores[k] if lam_scores[k] is not None else -9)

    values_dev = fit_values(records, BETA_DEV, lam)
    dev_rows = [r for r in records if r["season"] in BETA_DEV + (FIT_AB,)]
    attach_indices(dev_rows, values_dev)
    fit_rows = [r for r in dev_rows if r["season"] == FIT_AB]

    values_exam = fit_values(records, BETA_EXAM, lam)
    exam_rows = [r for r in records if r["season"] == EXAM]
    attach_indices(exam_rows, values_exam)

    top = sorted(values_exam.items(), key=lambda kv: -kv[1])[:5]
    out: dict[str, Any] = {
        "exam": EXAM_VERSION,
        "preregistration": "docs/squadre/SQUADRE_V2_PREREGISTRAZIONE.md",
        "data_status": status,
        "linked_matches": {s: sum(1 for r in records if r["season"] == s) for s in sorted({r["season"] for r in records})},
        "lambda_scores": {str(k): (round(v, 4) if v is not None else None) for k, v in lam_scores.items()},
        "lambda_chosen": lam,
        "players_valued_exam": len(values_exam),
        "top_player_values": [{"player_api_id": p, "value": round(v, 3)} for p, v in top],
    }
    for kind, name in (("A", "assenze del mattino"), ("F", "formazione ufficiale")):
        ab = fit_ab(fit_rows, kind)
        ev = evaluate(exam_rows, kind, ab)
        checks = {
            "1_logloss_gain_ci_above_zero": ev["matches"] > 0 and ev["logloss_gain"]["low"] > 0,
            "2_stronger_lineup_more_goals": ab[0] > 0,
            "3_roi_better_than_v3": (ev["roi_corrected"]["roi_pct"] or -999) > (ev["roi_v3"]["roi_pct"] or -999),
        }
        out[kind] = {"name": name, "a": round(ab[0], 4), "b": round(ab[1], 4), "exam": ev, "checks": checks, "passed": all(checks.values())}
    return out


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
                    logger.exception("esame squadre v2 fallito")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="squad-exam-v2", daemon=True).start()
        return dict(_state)
