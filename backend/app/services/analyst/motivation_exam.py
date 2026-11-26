"""Prova storica degli avvisi di motivazione (Giovanni, 26/11/2026): "casa motivata" e "ipotesi 2" prima e dopo la
regola nuova su "senza obiettivi" (centro classifica deciso a piu' di 6 punti da entrambe le zone).

Dati: le stagioni complete del Lab (football-data, 16 campionati europei, 2021/22-2025/26) con la quota Bet365.
Per ogni gara delle ultime 8 giornate (a una delle due squadre restano 8 gare o meno) si ricostruisce la classifica
del giorno prima e le gare che restano a ogni squadra; le zone (Europa/promozione e retrocessione/playout) sono
quelle di oggi di ogni campionato, scritte qui sotto: nelle stagioni passate possono essere cambiate di un posto.
Il Belgio (B1) e' escluso: la stagione regolare finisce nei play-off e la classifica non e' una sola.
Segni: "casa motivata" = 1 alla quota Bet365 di apertura; "ipotesi 2" = 2. ROI a 1 unita'.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.analyst.motivation import LAST_ROUNDS, MIDDLE_NONE_GAP, fasce, motivation_alerts, team_status

logger = logging.getLogger(__name__)

# posti di Europa/promozione dall'alto e di retrocessione/playout dal basso (struttura attuale)
ZONES: dict[str, tuple[int, int]] = {
    "E0": (6, 3),
    "E1": (6, 3),
    "E2": (6, 4),
    "E3": (7, 2),
    "I1": (7, 3),
    "I2": (8, 5),
    "SP1": (7, 3),
    "SP2": (6, 4),
    "D1": (7, 3),
    "D2": (3, 3),
    "F1": (6, 3),
    "F2": (5, 3),
    "N1": (8, 3),
    "P1": (5, 3),
    "T1": (5, 3),
}
COMPLETE_SEASONS = ("2021/2022", "2022/2023", "2023/2024", "2024/2025", "2025/2026")
ALERTS = {"casa_motivata": "HOME", "ipotesi_2": "AWAY"}

_lock = threading.Lock()
_state: dict[str, Any] = {"status": "idle"}


def zone_descriptions(teams: int, goal: int, danger: int) -> dict[str, str]:
    out = {str(r): "Promotion / Europe" for r in range(1, goal + 1)}
    for r in range(teams - danger + 1, teams + 1):
        out[str(r)] = "Relegation"
    return out


def _table(points: dict[str, int], won: dict[str, int], gd: dict[str, int], gf: dict[str, int], teams: list[str]) -> list[dict[str, Any]]:
    order = sorted(teams, key=lambda t: (-points[t], -gd[t], -gf[t], t))
    return [{"rank": i + 1, "team_id": t, "points": points[t], "won": won[t]} for i, t in enumerate(order)]


def season_games(matches: list[Any], division: str) -> list[dict[str, Any]]:
    """Gare delle ultime 8 giornate di una stagione con le due motivazioni (regola del 24/11 e del 26/11)."""
    rows = [m for m in matches if m.match_date and m.home_team and m.away_team and m.ft_home_goals is not None and m.ft_away_goals is not None]
    rows.sort(key=lambda m: (m.match_date, m.id))
    teams = sorted({m.home_team for m in rows} | {m.away_team for m in rows})
    total = defaultdict(int)
    for m in rows:
        total[m.home_team] += 1
        total[m.away_team] += 1
    goal, danger = ZONES[division]
    desc = zone_descriptions(len(teams), goal, danger)
    zones = fasce(desc, len(teams))
    points, won, gd, gf, played = (defaultdict(int) for _ in range(5))
    out: list[dict[str, Any]] = []
    by_day: dict[date, list[Any]] = defaultdict(list)
    for m in rows:
        by_day[m.match_date].append(m)
    for day in sorted(by_day):
        games = by_day[day]
        table = _table(points, won, gd, gf, teams)
        left = {t: total[t] - played[t] for t in teams}
        for m in games:
            h, a = m.home_team, m.away_team
            if min(left[h], left[a]) > LAST_ROUNDS or not zones:
                continue
            qh, qa = m.bet365_home, m.bet365_away
            favorite = ("home" if qh < qa else "away" if qa < qh else None) if qh and qa else None
            row = {"home_goals": m.ft_home_goals, "away_goals": m.ft_away_goals, "q_home": float(qh) if qh else None, "q_away": float(qa) if qa else None}
            for rule, gap in (("old", None), ("new", MIDDLE_NONE_GAP)):
                hs = team_status(h, table, left, zones, descriptions=desc, middle_none_gap=gap)
                as_ = team_status(a, table, left, zones, descriptions=desc, middle_none_gap=gap)
                alerts = motivation_alerts(home=h, away=a, home_status=hs, away_status=as_, remaining=None, favorite=favorite, schedule=None)
                row[rule] = {x["code"] for x in alerts}
            out.append(row)
        for m in games:
            h, a, x, y = m.home_team, m.away_team, int(m.ft_home_goals), int(m.ft_away_goals)
            for t, f_, s_ in ((h, x, y), (a, y, x)):
                played[t] += 1
                gd[t] += f_ - s_
                gf[t] += f_
                if f_ > s_:
                    points[t] += 3
                    won[t] += 1
                elif f_ == s_:
                    points[t] += 1
    return out


def _roi(rows: list[dict[str, Any]], sign: str) -> dict[str, Any]:
    bets = []
    for r in rows:
        q = r["q_home"] if sign == "HOME" else r["q_away"]
        if not q:
            continue
        won = r["home_goals"] > r["away_goals"] if sign == "HOME" else r["away_goals"] > r["home_goals"]
        bets.append(q - 1 if won else -1.0)
    n = len(bets)
    return {
        "games": n,
        "won": sum(1 for b in bets if b > 0),
        "units": round(sum(bets), 2),
        "roi_pct": round(100 * sum(bets) / n, 1) if n else None,
    }


def summarize(games: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"games_last_rounds": len(games)}
    for code, sign in ALERTS.items():
        old = [g for g in games if code in g["old"]]
        new = [g for g in games if code in g["new"]]
        added = [g for g in games if code in g["new"] and code not in g["old"]]
        out[code] = {"sign": sign, "before": _roi(old, sign), "after": _roi(new, sign), "added": _roi(added, sign)}
    for code in ("senza_motivazioni", "p27"):
        out[code] = {"before": sum(1 for g in games if code in g["old"]), "after": sum(1 for g in games if code in g["new"])}
    return out


def run_exam() -> dict[str, Any]:
    from app.core.database import SessionLocal

    t0 = time.monotonic()
    db = SessionLocal()
    try:
        datasets = db.execute(
            select(CecchinoLabDataset).where(CecchinoLabDataset.division_code.in_(list(ZONES)), CecchinoLabDataset.season_label.in_(COMPLETE_SEASONS))
        ).scalars().all()
        games: list[dict[str, Any]] = []
        per_season = []
        for ds in datasets:
            matches = db.execute(select(CecchinoLabMatch).where(CecchinoLabMatch.dataset_id == ds.id)).scalars().all()
            rows = season_games(list(matches), str(ds.division_code))
            games += rows
            per_season.append({"division": ds.division_code, "season": ds.season_label, "games_last_rounds": len(rows)})
    finally:
        db.close()
    return {
        "seasons": len(per_season),
        "per_season": sorted(per_season, key=lambda x: (x["division"], x["season"])),
        "summary": summarize(games),
        "seconds": round(time.monotonic() - t0, 1),
    }


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
                    logger.exception("prova motivazione fallita")
                    with _lock:
                        _state.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})

            threading.Thread(target=target, name="diario-motivation-exam", daemon=True).start()
        return dict(_state)
