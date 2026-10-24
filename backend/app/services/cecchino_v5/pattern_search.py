"""Ricerca ampia dei pattern con contesto di partita (docs/campionati/PATTERN_V1_PREREGISTRAZIONE.md). Sola lettura, sul server."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any

import numpy as np
from sqlalchemy import text

from app.services.cecchino_v5.league_map import (
    BANDS,
    CHECK_MARKETS,
    CHECK_SEASON,
    DEV_SEASONS,
    EXAM_SEASON,
    MARKETS,
    ODDS_COLUMNS,
    _band,
    _odds,
    _roi,
    binom_tail,
    outcome,
    season_label,
)

logger = logging.getLogger(__name__)

SEARCH_VERSION = "pattern_v1_20261024"
FEATURES = ("F1 forma casa", "F2 forma ospite", "F3 attacco casa", "F4 attacco ospite", "F5 difesa casa", "F6 difesa ospite", "F7 dominio tiri in porta", "F8 distanza classifica", "F9 fase stagione")
LEVELS = {
    0: ("bassa", "media", "alta"), 1: ("bassa", "media", "alta"), 2: ("basso", "medio", "alto"), 3: ("basso", "medio", "alto"),
    4: ("pochi subiti", "medi", "molti subiti"), 5: ("pochi subiti", "medi", "molti subiti"),
    6: ("ospite domina", "equilibrio", "casa domina"), 7: ("ospite sopra", "vicine", "casa sopra"), 8: ("ago-ott", "nov-mar", "apr-giu"),
}
MIN_DEV, MIN_EXAM, MIN_CHECK = 20, 20, 10
OVERLAP_MAX = 0.8
SEASONS = DEV_SEASONS + (EXAM_SEASON, CHECK_SEASON)


def _bin(x: float | None, lo: float, hi: float) -> int:
    if x is None:
        return -1
    return 0 if x < lo else (2 if x > hi else 1)


def load_matches(db) -> list[dict[str, Any]]:
    cols = ", ".join(sorted(set(ODDS_COLUMNS.values())))
    rows = db.execute(
        text(
            f"""
            SELECT id, division_code, match_date, home_team, away_team, ft_home_goals, ft_away_goals, ht_home_goals, ht_away_goals,
                   home_shots_on_target, away_shots_on_target, {cols}
            FROM cecchino_lab_matches
            WHERE ft_home_goals IS NOT NULL AND ft_away_goals IS NOT NULL
            ORDER BY match_date, id
            """
        )
    ).mappings().all()
    out = []
    for r in rows:
        m = dict(r)
        m["season"] = season_label(m["match_date"])
        out.append(m)
    return out


def compute_features(matches: list[dict[str, Any]]) -> np.ndarray:
    """Le 9 caratteristiche per partita (-1 = non definita), solo con partite precedenti dello stesso campionato e stagione."""
    feats = np.full((len(matches), 9), -1, dtype=np.int8)
    by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, m in enumerate(matches):
        by_key[(m["division_code"], m["season"])].append(i)
    for idxs in by_key.values():
        last: dict[str, deque] = defaultdict(lambda: deque(maxlen=5))  # (punti, gf, gs, tiri fatti, tiri subiti)
        season_pts: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
        league = [0.0, 0]  # gol, partite-squadra
        by_day: dict[Any, list[int]] = defaultdict(list)
        for i in idxs:
            by_day[matches[i]["match_date"]].append(i)
        for day in sorted(by_day):
            today = by_day[day]
            avg = league[0] / league[1] if league[1] >= 20 else None
            for i in today:
                m = matches[i]
                h, a = last[m["home_team"]], last[m["away_team"]]
                f = feats[i]
                if len(h) >= 3:
                    f[0] = _bin(sum(x[0] for x in h) / len(h), 1.0, 1.8)
                    if avg:
                        f[2] = _bin(sum(x[1] for x in h) / len(h) / avg, 0.8, 1.2)
                        f[4] = _bin(sum(x[2] for x in h) / len(h) / avg, 0.8, 1.2)
                if len(a) >= 3:
                    f[1] = _bin(sum(x[0] for x in a) / len(a), 1.0, 1.8)
                    if avg:
                        f[3] = _bin(sum(x[1] for x in a) / len(a) / avg, 0.8, 1.2)
                        f[5] = _bin(sum(x[2] for x in a) / len(a) / avg, 0.8, 1.2)
                hs = [x[3] - x[4] for x in h if x[3] is not None]
                as_ = [x[3] - x[4] for x in a if x[3] is not None]
                if len(hs) >= 3 and len(as_) >= 3:
                    f[6] = _bin(sum(hs) / len(hs) - sum(as_) / len(as_), -2.0, 2.0)
                sh, sa = season_pts[m["home_team"]], season_pts[m["away_team"]]
                if sh[1] >= 3 and sa[1] >= 3:
                    f[7] = _bin(sh[0] / sh[1] - sa[0] / sa[1], -0.5, 0.5)
                month = m["match_date"].month
                f[8] = 0 if month in (7, 8, 9, 10) else (1 if month in (11, 12, 1, 2, 3) else 2)
            for i in today:
                m = matches[i]
                gh, ga = m["ft_home_goals"], m["ft_away_goals"]
                ph = 3 if gh > ga else (1 if gh == ga else 0)
                pa = 3 if ga > gh else (1 if gh == ga else 0)
                sot_h, sot_a = m["home_shots_on_target"], m["away_shots_on_target"]
                ok = sot_h is not None and sot_a is not None
                last[m["home_team"]].append((ph, gh, ga, sot_h if ok else None, sot_a if ok else None))
                last[m["away_team"]].append((pa, ga, gh, sot_a if ok else None, sot_h if ok else None))
                season_pts[m["home_team"]][0] += ph
                season_pts[m["home_team"]][1] += 1
                season_pts[m["away_team"]][0] += pa
                season_pts[m["away_team"]][1] += 1
                league[0] += gh + ga
                league[1] += 2
    return feats


def _conditions() -> list[tuple[tuple[int, int], ...]]:
    singles = [((f, l),) for f in range(9) for l in range(3)]
    pairs = [((f1, l1), (f2, l2)) for f1 in range(9) for f2 in range(f1 + 1, 9) for l1 in range(3) for l2 in range(3)]
    return [()] + singles + pairs


def describe(cond: tuple[tuple[int, int], ...]) -> str:
    if not cond:
        return "senza condizioni"
    return " e ".join(f"{FEATURES[f]} {LEVELS[f][l]}" for f, l in cond)


def run_search() -> dict[str, Any]:
    from app.services.audit.readonly import readonly_session

    gen = readonly_session()
    db = next(gen)
    try:
        matches = load_matches(db)
    finally:
        gen.close()
    feats = compute_features(matches)
    season_idx = {s: i for i, s in enumerate(SEASONS)}
    conds = _conditions()
    candidates: list[dict[str, Any]] = []
    bases = 0
    for league in sorted({m["division_code"] for m in matches}):
        lidx = [i for i, m in enumerate(matches) if m["division_code"] == league and m["season"] in season_idx]
        for market in MARKETS:
            rows = []
            for i in lidx:
                q = _odds(matches[i], market)
                o = outcome(market, matches[i])
                b = _band(q) if q else None
                if b is None or o is None:
                    continue
                rows.append((i, q, o, b))
            for _, _, band_name in BANDS:
                sel = [r for r in rows if r[3] == band_name]
                if not sel:
                    continue
                bases += 1
                idx = np.array([r[0] for r in sel])
                q = np.array([r[1] for r in sel])
                won = np.array([r[2] for r in sel], dtype=bool)
                profit = np.where(won, q - 1.0, -1.0)
                seas = np.array([season_idx[matches[i]["season"]] for i in idx])
                f = feats[idx]
                level_mask = {(fi, l): f[:, fi] == l for fi in range(9) for l in range(3)}
                dev_masks = [seas == k for k in range(4)]
                for cond in conds:
                    mask = np.ones(len(idx), dtype=bool)
                    for key in cond:
                        mask &= level_mask[key]
                    ok = True
                    for dm in dev_masks:
                        mm = mask & dm
                        if mm.sum() < MIN_DEV or profit[mm].sum() <= 0:
                            ok = False
                            break
                    if not ok:
                        continue
                    sl = {}
                    for s, k in season_idx.items():
                        mm = mask & (seas == k)
                        sl[s] = list(zip(won[mm].tolist(), q[mm].tolist()))
                    candidates.append(
                        {
                            "league": league,
                            "market": market,
                            "band": band_name,
                            "condition": describe(cond),
                            "matches": set(idx[mask & (seas <= season_idx[EXAM_SEASON])].tolist()),
                            "seasons": sl,
                        }
                    )
    # pattern quasi uguali: stessa base e oltre l'80% delle stesse partite -> resta quello con piu' giocate nello sviluppo
    candidates.sort(key=lambda c: -sum(len(c["seasons"][s]) for s in DEV_SEASONS))
    kept: list[dict[str, Any]] = []
    for c in candidates:
        dup = False
        for k in kept:
            if (k["league"], k["market"], k["band"]) != (c["league"], c["market"], c["band"]):
                continue
            inter = len(c["matches"] & k["matches"])
            if inter > OVERLAP_MAX * min(len(c["matches"]), len(k["matches"])):
                dup = True
                break
        if not dup:
            kept.append(c)
    out_rules = []
    positive = with_exam = passed = confirmed = 0
    for c in kept:
        dev = {s: _roi(c["seasons"][s]) for s in DEV_SEASONS}
        exam = _roi(c["seasons"][EXAM_SEASON])
        check = _roi(c["seasons"][CHECK_SEASON]) if c["market"] in CHECK_MARKETS else None
        status = "senza esame (meno di 20 giocate nella 2025/26)"
        if exam["n"] >= MIN_EXAM:
            with_exam += 1
            if (exam["roi_pct"] or 0) > 0:
                positive += 1
                passed += 1
                if check is None or check["n"] < MIN_CHECK:
                    status = "passa (controllo 2026/27 non disponibile)"
                elif (check["roi_pct"] or 0) > 0:
                    status = "confermato"
                    confirmed += 1
                else:
                    status = "passa, smentito nel 2026/27"
            else:
                status = "non passa"
        out_rules.append({k: c[k] for k in ("league", "market", "band", "condition")} | {"dev": dev, "exam": exam, "check": check, "status": status})
    p_value = binom_tail(positive, with_exam)
    order = {"confermato": 0, "passa (controllo 2026/27 non disponibile)": 1, "passa, smentito nel 2026/27": 2}
    out_rules.sort(key=lambda r: (order.get(r["status"], 3), -(r["exam"]["roi_pct"] or -999)))
    return {
        "search": SEARCH_VERSION,
        "preregistration": "docs/campionati/PATTERN_V1_PREREGISTRAZIONE.md",
        "matches": len(matches),
        "bases": bases,
        "patterns_tested": bases * len(conds),
        "candidates_before_dedup": len(candidates),
        "candidates": len(kept),
        "candidates_with_exam": with_exam,
        "positive_in_exam": positive,
        "binomial_p": round(p_value, 4),
        "credible": p_value < 0.05,
        "passed": passed,
        "confirmed": confirmed,
        "rules": out_rules[:300],
    }


_state: dict[str, Any] = {"status": "idle"}
_lock = threading.Lock()


def search_state(start: bool = False) -> dict[str, Any]:
    with _lock:
        if start and _state.get("status") in ("idle", "failed"):
            _state.clear()
            _state.update({"status": "running", "started_at": time.time()})

            def target() -> None:
                try:
                    result = run_search()
                    with _lock:
                        _state.update({"status": "done", "result": result, "finished_at": time.time()})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("ricerca pattern fallita")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="pattern-search", daemon=True).start()
        return dict(_state)
