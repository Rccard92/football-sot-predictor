"""Esame strato squadre v1 (docs/squadre/SQUADRE_V1_PREREGISTRAZIONE.md). Sola lettura, sul server.

Collega le partite storiche della V4 (giocatori, assenze) alle partite del Lab (quote, gol V3 run 11), calcola peso dei
giocatori, indice assenze del mattino (A) e indice formazione ufficiale (F), stima la correzione dei gol sullo sviluppo e
la verifica sulla 2025/26.
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
from sqlalchemy import text

from app.services.cecchino_v3.markets import market_probabilities
from app.services.cecchino_v5.league_map import _odds, _roi, outcome, season_label

logger = logging.getLogger(__name__)

EXAM_VERSION = "squadre_v1_20261024"
DEV = ("2023/24", "2024/25")
EXAM = "2025/26"
WINDOW = 10
MIN_TEAM_MATCHES = 3
PENALTY = 0.5
RULE_MARKETS = ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5")
Z90 = 1.645


def data_status(db) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT season_label, count(*) AS partite, count(players_fetched_at) AS con_giocatori
            FROM cecchino_v4_fixtures WHERE status IN ('FT','AET','PEN') GROUP BY 1 ORDER BY 1
            """
        )
    ).all()
    inj = {int(s): int(n) for s, n in db.execute(text("SELECT season, count(*) FROM cecchino_v4_injuries GROUP BY 1")).all()}
    return [{"season": s, "matches": int(n), "with_players": int(p), "injuries": inj.get(int(s[:4]), 0)} for s, n, p in rows]


def _load(db) -> dict[str, Any]:
    fixtures = [
        dict(r)
        for r in db.execute(
            text(
                """
                SELECT id, api_fixture_id, league_code, match_date, kickoff_at, home_team_api_id, away_team_api_id,
                       home_team_history, away_team_history
                FROM cecchino_v4_fixtures
                WHERE status IN ('FT','AET','PEN') AND players_fetched_at IS NOT NULL
                ORDER BY kickoff_at, id
                """
            )
        ).mappings()
    ]
    minutes: dict[int, list[tuple[int, int, int, bool, float | None]]] = defaultdict(list)
    for fid, team, player, mins, started, rating in db.execute(
        text("SELECT fixture_id, team_api_id, player_api_id, minutes, started, rating FROM cecchino_v4_player_minutes")
    ).all():
        minutes[int(fid)].append((int(team), int(player), int(mins or 0), bool(started), float(rating) if rating is not None else None))
    injuries: dict[tuple[int, int], set[int]] = defaultdict(set)
    for fx, team, player, kind in db.execute(
        text("SELECT fixture_api_id, team_api_id, player_api_id, kind FROM cecchino_v4_injuries")
    ).all():
        if team is not None and (kind or "").lower().startswith("missing"):
            injuries[(int(fx), int(team))].add(int(player))
    lab = {}
    for r in db.execute(
        text(
            """
            SELECT l.id, l.division_code, l.match_date, l.home_team, l.away_team, l.ft_home_goals, l.ft_away_goals,
                   l.bet365_home, l.bet365_draw, l.bet365_away, l.bet365_over_25, l.bet365_under_25,
                   p.lambda_home, p.lambda_away, p.rho, p.ht_share
            FROM cecchino_lab_matches l JOIN cecchino_v3_match_predictions p ON p.lab_match_id = l.id AND p.run_id = 11
            WHERE l.ft_home_goals IS NOT NULL
            """
        )
    ).mappings():
        lab[(r["division_code"], r["match_date"], r["home_team"], r["away_team"])] = dict(r)
    return {"fixtures": fixtures, "minutes": minutes, "injuries": injuries, "lab": lab}


def _indices(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per ogni partita collegata al Lab: indice assenze (A) e formazione (F) di casa e ospite, solo con dati precedenti."""
    history: dict[tuple[str, int], deque] = defaultdict(lambda: deque(maxlen=WINDOW))  # (stagione, squadra) -> partite
    out = []
    for fx in data["fixtures"]:
        season = season_label(fx["match_date"])
        rows = data["minutes"].get(int(fx["id"]), [])
        idx: dict[str, float | None] = {}
        for side, team in (("home", int(fx["home_team_api_id"])), ("away", int(fx["away_team_api_id"]))):
            past = history[(season, team)]
            if len(past) < MIN_TEAM_MATCHES:
                idx[f"A_{side}"] = idx[f"F_{side}"] = None
                continue
            mins: dict[int, int] = defaultdict(int)
            ratings: dict[int, list[float]] = defaultdict(list)
            for match in past:
                for player, m, r in match:
                    mins[player] += m
                    if r is not None and m > 0:
                        ratings[player].append(r)
            all_r = [r for rs in ratings.values() for r in rs]
            team_avg = sum(all_r) / len(all_r) if all_r else 6.7
            available = 90 * len(past)
            weight = {}
            for player, m in mins.items():
                rs = ratings.get(player, [])
                quality = (sum(rs) / len(rs) - team_avg) if len(rs) >= 3 else 0.0
                weight[player] = (m / available) * (1 + quality / 2)
            usual = sorted(mins, key=lambda p: -mins[p])[:11]
            base = sum(max(0.0, weight[p]) for p in usual)
            if base <= 0:
                idx[f"A_{side}"] = idx[f"F_{side}"] = None
                continue
            missing = data["injuries"].get((int(fx["api_fixture_id"]), team), set())
            idx[f"A_{side}"] = min(1.0, sum(max(0.0, weight[p]) for p in usual if p in missing) / base)
            starters = [p for t, p, m, s, r in rows if t == team and s]
            idx[f"F_{side}"] = min(1.0, max(0.0, 1 - sum(max(0.0, weight.get(p, 0.0)) for p in starters) / base)) if starters else None
        for side, team in (("home", int(fx["home_team_api_id"])), ("away", int(fx["away_team_api_id"]))):
            history[(season, team)].append([(p, m, r) for t, p, m, s, r in rows if t == team])
        lab = None
        for delta in (0, -1, 1):
            lab = data["lab"].get((fx["league_code"], fx["match_date"] + timedelta(days=delta), fx["home_team_history"], fx["away_team_history"]))
            if lab:
                break
        if lab is None or lab["lambda_home"] is None:
            continue
        out.append({"season": season, "lab": lab, **idx})
    return out


def _fit(rows: list[dict[str, Any]], kind: str) -> tuple[float, float]:
    use = [r for r in rows if r[f"{kind}_home"] is not None and r[f"{kind}_away"] is not None]
    if not use:
        return 0.0, 0.0
    lh = np.array([math.log(r["lab"]["lambda_home"]) for r in use])
    la = np.array([math.log(r["lab"]["lambda_away"]) for r in use])
    ih = np.array([r[f"{kind}_home"] for r in use])
    ia = np.array([r[f"{kind}_away"] for r in use])
    gh = np.array([r["lab"]["ft_home_goals"] for r in use])
    ga = np.array([r["lab"]["ft_away_goals"] for r in use])

    def nll(beta: np.ndarray) -> float:
        b_att, b_def = beta
        mh = lh + b_att * ih + b_def * ia
        ma = la + b_att * ia + b_def * ih
        return float(np.sum(np.exp(mh) - gh * mh) + np.sum(np.exp(ma) - ga * ma) + PENALTY * (b_att**2 + b_def**2))

    res = minimize(nll, np.zeros(2), method="BFGS")
    return float(res.x[0]), float(res.x[1])


def _probs(r: dict[str, Any], kind: str | None, beta: tuple[float, float]) -> dict[str, float]:
    lab = r["lab"]
    lh, la = lab["lambda_home"], lab["lambda_away"]
    if kind is not None and r[f"{kind}_home"] is not None and r[f"{kind}_away"] is not None:
        lh = lh * math.exp(beta[0] * r[f"{kind}_home"] + beta[1] * r[f"{kind}_away"])
        la = la * math.exp(beta[0] * r[f"{kind}_away"] + beta[1] * r[f"{kind}_home"])
    return market_probabilities(lh, la, float(lab["rho"] or 0.0), float(lab["ht_share"] or 0.45))


def _evaluate(rows: list[dict[str, Any]], kind: str, beta: tuple[float, float]) -> dict[str, Any]:
    use = [r for r in rows if r[f"{kind}_home"] is not None and r[f"{kind}_away"] is not None]
    diffs, plays_new, plays_old = [], [], []
    for r in use:
        lab = r["lab"]
        gh, ga = lab["ft_home_goals"], lab["ft_away_goals"]
        res = "HOME" if gh > ga else ("AWAY" if gh < ga else "DRAW")
        over = gh + ga > 2
        losses = []
        for which in (None, kind):
            p = _probs(r, which, beta)
            l1x2 = -math.log(max(1e-6, p[res]))
            lou = -math.log(max(1e-6, p["OVER_2_5"] if over else 1 - p["OVER_2_5"]))
            losses.append((l1x2 + lou) / 2)
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
        diffs.append(losses[0] - losses[1])  # positivo = la correzione sbaglia meno
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    half = Z90 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "matches": n,
        "logloss_gain": {"mean": round(mean, 6), "low": round(mean - half, 6), "high": round(mean + half, 6)},
        "roi_corrected": _roi(plays_new),
        "roi_v3": _roi(plays_old),
        "share_with_absences": round(sum(1 for r in use if (r[f"{kind}_home"] or 0) + (r[f"{kind}_away"] or 0) > 0.1) / n, 3) if n else None,
    }


def run_exam() -> dict[str, Any]:
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        status = data_status(db)
        data = _load(db)
    finally:
        gen.close()
    rows = _indices(data)
    dev = [r for r in rows if r["season"] in DEV]
    exam = [r for r in rows if r["season"] == EXAM]
    out: dict[str, Any] = {
        "exam": EXAM_VERSION,
        "preregistration": "docs/squadre/SQUADRE_V1_PREREGISTRAZIONE.md",
        "data_status": status,
        "linked_matches": {s: sum(1 for r in rows if r["season"] == s) for s in sorted({r["season"] for r in rows})},
    }
    for kind, name in (("A", "assenze del mattino"), ("F", "formazione ufficiale")):
        beta = _fit(dev, kind)
        ev = _evaluate(exam, kind, beta)
        checks = {
            "1_logloss_gain_ci_above_zero": ev["matches"] > 0 and ev["logloss_gain"]["low"] > 0,
            "2_own_absences_reduce_goals": beta[0] < 0,
            "3_roi_better_than_v3": (ev["roi_corrected"]["roi_pct"] or -999) > (ev["roi_v3"]["roi_pct"] or -999),
        }
        out[kind] = {"name": name, "beta_att": round(beta[0], 4), "beta_def": round(beta[1], 4), "exam": ev, "checks": checks, "passed": all(checks.values())}
    return out


_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def exam_state(start: bool = False) -> dict[str, Any]:
    with _lock:
        if start and _state.get("status") in ("idle", "failed", "done"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time()})

            def target() -> None:
                try:
                    result = run_exam()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("esame squadre fallito")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="squad-exam", daemon=True).start()
        return dict(_state)
