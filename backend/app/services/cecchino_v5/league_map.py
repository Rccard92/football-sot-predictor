"""Mappa dei 16 campionati e modelli dedicati (docs/campionati/MAPPA_V1_PREREGISTRAZIONE.md).

Sola lettura: storico football-data del Lab e probabilita' V3 run 11. Famiglia R (regole campionato x mercato x fascia
di quota), famiglia M (ritaratura della V3 per campionato), scheda descrittiva. Gira in un thread sul server.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import text

logger = logging.getLogger(__name__)

MAP_VERSION = "mappa_campionati_v1_20261024"
RUN_ID = 11
DEV_SEASONS = ("2021/22", "2022/23", "2023/24", "2024/25")
EXAM_SEASON = "2025/26"
CHECK_SEASON = "2026/27"

# mercato -> colonna della quota Bet365 prima della partita
ODDS_COLUMNS = {
    "HOME": "bet365_home", "DRAW": "bet365_draw", "AWAY": "bet365_away",
    "ONE_X": "bet365_dc_1x", "ONE_TWO": "bet365_dc_12", "X_TWO": "bet365_dc_x2",
    "OVER_1_5": "bet365_over_15", "UNDER_1_5": "bet365_under_15",
    "OVER_2_5": "bet365_over_25", "UNDER_2_5": "bet365_under_25",
    "OVER_3_5": "bet365_over_35", "UNDER_3_5": "bet365_under_35",
    "HOME_PT": "bet365_ht_home", "DRAW_PT": "bet365_ht_draw", "AWAY_PT": "bet365_ht_away",
}
MARKETS = tuple(ODDS_COLUMNS)  # 15 selezioni dei 12 mercati della preregistrazione (1X2, DC, O/U x3, 1X2 PT)
CHECK_MARKETS = ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5")
BANDS = ((1.40, 1.70, "1,40-1,69"), (1.70, 2.00, "1,70-1,99"), (2.00, 2.50, "2,00-2,49"), (2.50, 3.50, "2,50-3,49"))
R_MIN_DEV = 20
R_MIN_EXAM = 20
R_MIN_CHECK = 10
M_PENALTY = 50.0
M_MIN_Q, M_MAX_Q, M_MIN_EDGE = 1.50, 2.50, 1.05
M_MIN_EXAM_PLAYS = 30
FAIR_GROUPS = (("HOME", "DRAW", "AWAY"), ("OVER_1_5", "UNDER_1_5"), ("OVER_2_5", "UNDER_2_5"), ("OVER_3_5", "UNDER_3_5"), ("HOME_PT", "DRAW_PT", "AWAY_PT"))


def season_label(d: date) -> str:
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}/{str(y + 1)[2:]}"


def outcome(market: str, m: dict[str, Any]) -> bool | None:
    if market.endswith("_PT"):
        h, a = m["ht_home_goals"], m["ht_away_goals"]
    else:
        h, a = m["ft_home_goals"], m["ft_away_goals"]
    if h is None or a is None:
        return None
    if market.startswith("HOME"):
        return h > a
    if market.startswith("DRAW"):
        return h == a
    if market.startswith("AWAY"):
        return h < a
    if market == "ONE_X":
        return h >= a
    if market == "ONE_TWO":
        return h != a
    if market == "X_TWO":
        return h <= a
    line = int(market[-3])  # OVER_2_5 -> 2
    return (h + a > line) if market.startswith("OVER") else (h + a <= line)


def _band(q: float) -> str | None:
    for lo, hi, name in BANDS:
        if lo <= q < hi:
            return name
    return None


def _roi(plays: list[tuple[bool, float]]) -> dict[str, Any]:
    n = len(plays)
    if n == 0:
        return {"n": 0, "won": 0, "roi_pct": None, "profit": 0.0, "avg_quota": None, "low_pct": None, "high_pct": None}
    profits = [(q - 1.0) if w else -1.0 for w, q in plays]
    mean = sum(profits) / n
    sd = math.sqrt(sum((p - mean) ** 2 for p in profits) / (n - 1)) if n > 1 else 0.0
    half = 1.645 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "won": sum(1 for w, _ in plays if w),
        "win_pct": round(100 * sum(1 for w, _ in plays if w) / n, 1),
        "avg_quota": round(sum(q for _, q in plays) / n, 2),
        "profit": round(sum(profits), 2),
        "roi_pct": round(100 * mean, 1),
        "low_pct": round(100 * (mean - half), 1),
        "high_pct": round(100 * (mean + half), 1),
    }


def binom_tail(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) con X ~ Binomiale(n, p)."""
    if n <= 0:
        return 1.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 0.01, 0.99)
    return np.log(p / (1 - p))


def fit_recalibration(p_v3: np.ndarray, y: np.ndarray, penalty: float = M_PENALTY) -> tuple[float, float]:
    """Regressione logistica logit(p) = a + b logit(p_V3) con penalita' verso (0, 1); Newton."""
    if len(y) == 0:
        return 0.0, 1.0
    x = _logit(p_v3)
    a, b = 0.0, 1.0
    for _ in range(25):
        z = a + b * x
        mu = 1 / (1 + np.exp(-z))
        w = mu * (1 - mu)
        ga = float(np.sum(mu - y)) + penalty * a
        gb = float(np.sum((mu - y) * x)) + penalty * (b - 1)
        haa = float(np.sum(w)) + penalty
        hab = float(np.sum(w * x))
        hbb = float(np.sum(w * x * x)) + penalty
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) < 1e-8 and abs(db) < 1e-8:
            break
    return float(a), float(b)


def _apply(a: float, b: float, p: float) -> float:
    z = a + b * float(_logit(np.array([p]))[0])
    return 1 / (1 + math.exp(-z))


def load(db) -> tuple[list[dict[str, Any]], dict[int, dict[str, float]]]:
    cols = ", ".join(sorted(set(ODDS_COLUMNS.values())))
    rows = db.execute(
        text(
            f"""
            SELECT id, division_code, match_date, ft_home_goals, ft_away_goals, ht_home_goals, ht_away_goals,
                   home_shots_on_target, away_shots_on_target, home_corners, away_corners,
                   home_yellow_cards, away_yellow_cards, home_red_cards, away_red_cards, {cols}
            FROM cecchino_lab_matches
            WHERE ft_home_goals IS NOT NULL AND ft_away_goals IS NOT NULL
            ORDER BY match_date, id
            """
        )
    ).mappings().all()
    matches = [dict(r) for r in rows]
    for m in matches:
        m["season"] = season_label(m["match_date"])
    probs: dict[int, dict[str, float]] = defaultdict(dict)
    for mid, key, p in db.execute(
        text(
            "SELECT lab_match_id, market_key, probability FROM cecchino_v3_market_predictions "
            "WHERE run_id = :r AND market_key = ANY(:k)"
        ),
        {"r": RUN_ID, "k": list(MARKETS)},
    ).all():
        if p is not None:
            probs[int(mid)][str(key)] = float(p)
    return matches, dict(probs)


def _odds(m: dict[str, Any], market: str) -> float | None:
    q = m.get(ODDS_COLUMNS[market])
    try:
        q = float(q)
    except (TypeError, ValueError):
        return None
    return q if q > 1.0 else None


def family_r(matches: list[dict[str, Any]]) -> dict[str, Any]:
    plays: dict[tuple[str, str, str, str], list[tuple[bool, float]]] = defaultdict(list)
    for m in matches:
        for market in MARKETS:
            q = _odds(m, market)
            o = outcome(market, m)
            band = _band(q) if q else None
            if band is None or o is None:
                continue
            plays[(m["division_code"], market, band, m["season"])].append((o, q))
    rules = sorted({(d, mk, b) for d, mk, b, _ in plays})
    candidates, passed, confirmed = [], [], []
    for d, mk, b in rules:
        dev = {s: _roi(plays.get((d, mk, b, s), [])) for s in DEV_SEASONS}
        if not all(x["n"] >= R_MIN_DEV and (x["roi_pct"] or 0) > 0 for x in dev.values()):
            continue
        exam = _roi(plays.get((d, mk, b, EXAM_SEASON), []))
        check = _roi(plays.get((d, mk, b, CHECK_SEASON), [])) if mk in CHECK_MARKETS else None
        rule = {"league": d, "market": mk, "band": b, "dev": dev, "exam": exam, "check": check}
        candidates.append(rule)
        if exam["n"] >= R_MIN_EXAM and (exam["roi_pct"] or 0) > 0:
            passed.append(rule)
            if check is None or check["n"] < R_MIN_CHECK:
                rule["status"] = "passa (controllo 2026/27 non disponibile)"
            elif (check["roi_pct"] or 0) > 0:
                rule["status"] = "confermata"
                confirmed.append(rule)
            else:
                rule["status"] = "passa, smentita nel 2026/27"
        else:
            rule["status"] = "non passa"
    with_exam = [c for c in candidates if c["exam"]["n"] >= R_MIN_EXAM]
    positive = sum(1 for c in with_exam if (c["exam"]["roi_pct"] or 0) > 0)
    p_value = binom_tail(positive, len(with_exam))
    return {
        "rules_tested": len(rules),
        "candidates": len(candidates),
        "candidates_with_exam": len(with_exam),
        "positive_in_exam": positive,
        "binomial_p": round(p_value, 4),
        "credible": p_value < 0.05,
        "passed": len(passed),
        "confirmed": len(confirmed),
        "rules": candidates,
    }


def family_m(matches: list[dict[str, Any]], probs: dict[int, dict[str, float]]) -> dict[str, Any]:
    by_league: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in matches:
        if m["id"] in probs and m["season"] in DEV_SEASONS + (EXAM_SEASON,):
            by_league[m["division_code"]].append(m)
    leagues_out = []
    for league in sorted(by_league):
        ms = by_league[league]
        params: dict[str, dict[str, tuple[float, float]]] = {}  # stagione valutata -> mercato -> (a, b)
        for target in DEV_SEASONS[1:] + (EXAM_SEASON,):
            train_seasons = [s for s in DEV_SEASONS if s < target]
            params[target] = {}
            for market in MARKETS:
                xs, ys = [], []
                for m in ms:
                    if m["season"] not in train_seasons:
                        continue
                    p, o = probs[m["id"]].get(market), outcome(market, m)
                    if p is None or o is None:
                        continue
                    xs.append(p)
                    ys.append(1.0 if o else 0.0)
                params[target][market] = fit_recalibration(np.array(xs), np.array(ys))
        plays = {("ded", "dev"): [], ("ded", "exam"): [], ("com", "dev"): [], ("com", "exam"): []}
        ll = {"ded": defaultdict(list), "com": defaultdict(list)}
        picked_markets: dict[str, int] = defaultdict(int)
        for m in ms:
            if m["season"] not in params:
                continue
            phase = "exam" if m["season"] == EXAM_SEASON else "dev"
            pv = probs[m["id"]]
            best = {"ded": None, "com": None}
            for market in MARKETS:
                p_c = pv.get(market)
                o = outcome(market, m)
                if p_c is None or o is None:
                    continue
                a, b = params[m["season"]][market]
                p_d = _apply(a, b, p_c)
                if phase == "exam":
                    for kind, p in (("ded", p_d), ("com", p_c)):
                        pc = min(0.99, max(0.01, p))
                        ll[kind][market].append(-math.log(pc if o else 1 - pc))
                q = _odds(m, market)
                if q is None or not (M_MIN_Q <= q <= M_MAX_Q):
                    continue
                for kind, p in (("ded", p_d), ("com", p_c)):
                    score = p * q
                    if score >= M_MIN_EDGE and (best[kind] is None or score > best[kind][0]):
                        best[kind] = (score, o, q, market)
            for kind in ("ded", "com"):
                if best[kind] is not None:
                    plays[(kind, phase)].append((best[kind][1], best[kind][2]))
                    if kind == "ded" and phase == "exam":
                        picked_markets[best[kind][3]] += 1
        res = {k: _roi(v) for k, v in plays.items()}
        ll_mean = {
            kind: (sum(sum(v) / len(v) for v in d.values()) / len(d)) if d else None for kind, d in ll.items()
        }
        checks = {
            "1_dev_roi_positive": (res[("ded", "dev")]["roi_pct"] or -1) > 0,
            "2_exam_roi_positive": res[("ded", "exam")]["n"] >= M_MIN_EXAM_PLAYS and (res[("ded", "exam")]["roi_pct"] or -1) > 0,
            "3_exam_not_worse_than_common": (res[("ded", "exam")]["roi_pct"] or -999) >= (res[("com", "exam")]["roi_pct"] or -999),
            "4_logloss_not_worse": ll_mean["ded"] is not None and ll_mean["com"] is not None and ll_mean["ded"] <= ll_mean["com"],
        }
        exam_params = {mk: {"a": round(a, 3), "b": round(b, 3)} for mk, (a, b) in params[EXAM_SEASON].items()}
        leagues_out.append(
            {
                "league": league,
                "dedicated_dev": res[("ded", "dev")],
                "dedicated_exam": res[("ded", "exam")],
                "common_dev": res[("com", "dev")],
                "common_exam": res[("com", "exam")],
                "logloss_exam": {"dedicated": round(ll_mean["ded"], 5) if ll_mean["ded"] else None, "common": round(ll_mean["com"], 5) if ll_mean["com"] else None},
                "exam_markets": dict(sorted(picked_markets.items(), key=lambda kv: -kv[1])),
                "checks": checks,
                "passed": all(checks.values()),
                "params_exam": exam_params,
            }
        )
    positive = sum(1 for x in leagues_out if x["dedicated_exam"]["n"] >= M_MIN_EXAM_PLAYS and (x["dedicated_exam"]["roi_pct"] or -1) > 0)
    eligible = sum(1 for x in leagues_out if x["dedicated_exam"]["n"] >= M_MIN_EXAM_PLAYS)
    p_value = binom_tail(positive, eligible)
    return {
        "leagues": leagues_out,
        "leagues_with_exam": eligible,
        "positive_in_exam": positive,
        "binomial_p": round(p_value, 4),
        "credible": p_value < 0.05,
        "passed": [x["league"] for x in leagues_out if x["passed"]],
    }


def league_cards(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for m in matches:
        if m["season"] in DEV_SEASONS:
            groups[(m["division_code"], "sviluppo 2021/22-2024/25")].append(m)
        elif m["season"] in (EXAM_SEASON, CHECK_SEASON):
            groups[(m["division_code"], m["season"])].append(m)

    def avg(ms: list[dict[str, Any]], f) -> float | None:
        vals = [v for v in (f(m) for m in ms) if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def tot(a: Any, b: Any) -> float | None:
        return None if a is None or b is None else float(a) + float(b)

    out = []
    for (league, period), ms in sorted(groups.items()):
        n = len(ms)
        markets = {}
        for group in FAIR_GROUPS:
            fair_sum: dict[str, list[float]] = defaultdict(list)
            real: dict[str, list[int]] = defaultdict(list)
            for m in ms:
                qs = [_odds(m, k) for k in group]
                if any(q is None for q in qs):
                    continue
                inv = [1 / q for q in qs]  # type: ignore[operator]
                s = sum(inv)
                for k, v in zip(group, inv):
                    o = outcome(k, m)
                    if o is None:
                        continue
                    fair_sum[k].append(v / s)
                    real[k].append(1 if o else 0)
            for k in group:
                if real[k]:
                    markets[k] = {
                        "n": len(real[k]),
                        "book_fair_pct": round(100 * sum(fair_sum[k]) / len(fair_sum[k]), 1),
                        "real_pct": round(100 * sum(real[k]) / len(real[k]), 1),
                    }
        out.append(
            {
                "league": league,
                "period": period,
                "matches": n,
                "home_pct": round(100 * sum(1 for m in ms if m["ft_home_goals"] > m["ft_away_goals"]) / n, 1),
                "draw_pct": round(100 * sum(1 for m in ms if m["ft_home_goals"] == m["ft_away_goals"]) / n, 1),
                "away_pct": round(100 * sum(1 for m in ms if m["ft_home_goals"] < m["ft_away_goals"]) / n, 1),
                "goals_avg": avg(ms, lambda m: m["ft_home_goals"] + m["ft_away_goals"]),
                "over25_pct": round(100 * sum(1 for m in ms if m["ft_home_goals"] + m["ft_away_goals"] > 2) / n, 1),
                "sot_avg": avg(ms, lambda m: tot(m["home_shots_on_target"], m["away_shots_on_target"])),
                "corners_avg": avg(ms, lambda m: tot(m["home_corners"], m["away_corners"])),
                "cards_avg": avg(
                    ms,
                    lambda m: None
                    if m["home_yellow_cards"] is None or m["away_yellow_cards"] is None
                    else m["home_yellow_cards"] + m["away_yellow_cards"] + 2 * ((m["home_red_cards"] or 0) + (m["away_red_cards"] or 0)),
                ),
                "markets": markets,
            }
        )
    return out


def run_map() -> dict[str, Any]:
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        matches, probs = load(db)
    finally:
        gen.close()
    return {
        "map": MAP_VERSION,
        "preregistration": "docs/campionati/MAPPA_V1_PREREGISTRAZIONE.md",
        "matches": len(matches),
        "matches_with_v3": sum(1 for m in matches if m["id"] in probs),
        "family_r": family_r(matches),
        "family_m": family_m(matches, probs),
        "cards": league_cards(matches),
    }


_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def map_state(start: bool = False) -> dict[str, Any]:
    with _lock:
        if start and _state.get("status") in ("idle", "failed"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time()})

            def target() -> None:
                try:
                    result = run_map()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("mappa campionati fallita")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="league-map", daemon=True).start()
        return dict(_state)
