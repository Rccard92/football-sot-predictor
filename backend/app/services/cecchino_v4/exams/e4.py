"""Esame E4: la regola di selezione V4 sui mercati classici con le quote di chiusura Bet365 dello storico.

Criteri e precisazioni in docs/v4/PREREGISTRAZIONE_FASE_4.md (scritti prima del calcolo).
Esecuzione (da backend/): python -m app.services.cecchino_v4.exams.e4
Scrive docs/v4/esami/E4.json e E4.md.
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.services.cecchino_v4.constants import EXAMS_DOCS_DIR, EXAMS_DATA_DIR, JUDGE_SEASONS, LEAGUE_BY_COMPETITION
from app.services.cecchino_v4.engine_goals.baseline_v3 import run_v3_phase4_full
from app.services.cecchino_v4.engine_goals.cache import matches_digest
from app.services.cecchino_v4.engine_goals.config import ADOPTED_CONFIG as GOALS_CONFIG
from app.services.cecchino_v4.engine_goals.config import V4GoalsConfig
from app.services.cecchino_v4.engine_goals.engine import compute_strength_params, predict_history_full
from app.services.cecchino_v4.engine_stats.config import ADOPTED_CONFIG as STATS_CONFIG
from app.services.cecchino_v4.engine_stats.engine import load_exam_verdicts
from app.services.cecchino_v4.engine_stats.engine import predict_history as stats_predict_history
from app.services.cecchino_v4.history.football_data import History, MatchExtras, load_history
from app.services.cecchino_v4.measure.metrics import block_bootstrap_ci, roi
from app.services.cecchino_v4.selection.labels import ah_market_key, market_family
from app.services.cecchino_v4.selection.rules import evaluate_fixture, best_play
from app.services.cecchino_v4.selection.settlement import profit_units, settle
from app.services.cecchino_v4.selection.shortlist import build_shortlist

DOCS = EXAMS_DOCS_DIR.parent
OUT_JSON = DOCS / "esami" / "E4.json"
OUT_MD = DOCS / "esami" / "E4.md"
PREREG = "docs/v4/PREREGISTRAZIONE_FASE_4.md"
SEED = 20260920
BOOTSTRAP_N = 2000
NULL_N = 200
MIN_PLAYS = 300
MAX_LEAGUE_SHARE = 0.40


def closing_odds(ex: MatchExtras) -> dict[str, float]:
    odds: dict[str, float] = {}
    for k in ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5"):
        v = ex.odds_close.get(k)
        if v and v > 1.0:
            odds[k] = float(v)
    if ex.ah_line_close is not None:
        h, a = ex.odds_close.get("AH_HOME"), ex.odds_close.get("AH_AWAY")
        if h and h > 1.0:
            odds[ah_market_key("home", ex.ah_line_close)] = float(h)
        if a and a > 1.0:
            odds[ah_market_key("away", -ex.ah_line_close)] = float(a)
    return odds


def match_stats_json(m, ex: MatchExtras) -> dict[str, Any]:
    return {
        "home": {"shots": m.home_shots, "sot": m.home_sot, "corners": ex.home_corners, "yellow": m.home_yellow, "red": m.home_red, "fouls": m.home_fouls},
        "away": {"shots": m.away_shots, "sot": m.away_sot, "corners": ex.away_corners, "yellow": m.away_yellow, "red": m.away_red, "fouls": m.away_fouls},
    }


def match_result(m) -> dict[str, Any]:
    return {"ft_home": m.ft_home, "ft_away": m.ft_away, "ht_home": m.ht_home, "ht_away": m.ht_away}


def select_plays(history: History, goals: dict[int, dict], stats: dict[int, dict]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Applica la regola giornata per giornata (data di calendario, tutti i campionati). Ritorna le giocate e i motivi di astensione."""
    by_id = history.by_id()
    per_day: dict[date, list] = defaultdict(list)
    abstentions: dict[str, int] = defaultdict(int)
    for m in history.matches:
        if m.season_label not in JUDGE_SEASONS or not m.eval_eligible:
            continue
        g = goals.get(m.lab_match_id)
        if g is None:
            continue
        ex = history.extras[m.lab_match_id]
        odds = closing_odds(ex)
        if not odds:
            abstentions["non_quotato"] += 1
            continue
        rows = evaluate_fixture(g, stats.get(m.lab_match_id), {8: odds}, m.home_team, m.away_team, "ufficiali", allow_classic=True)
        rows = [r for r in rows if not r.market_key.startswith("STAT:")]  # E4: solo mercati classici con quota
        play = best_play(rows)
        if play is None:
            reasons = [r.verdict for r in rows if r.quota_used]
            abstentions[max(set(reasons), key=reasons.count) if reasons else "non_quotato"] += 1
            continue
        meta = {"fixture_id": m.lab_match_id, "home_team": m.home_team, "away_team": m.away_team, "league_code": LEAGUE_BY_COMPETITION[m.competition].code}
        per_day[m.match_date].append((meta, play))
    plays: list[dict[str, Any]] = []
    for day in sorted(per_day):
        sl = build_shortlist(day, per_day[day])
        for it in sl.to_dict()["items"]:
            m = by_id[int(it["fixture_id"])]
            ex = history.extras[m.lab_match_id]
            outcome = settle(it["market_key"], match_result(m), match_stats_json(m, ex))
            plays.append(
                {
                    "match_id": m.lab_match_id,
                    "day": day.isoformat(),
                    "block": f"{m.competition}|{day.isoformat()}",
                    "season": m.season_label,
                    "competition": m.competition,
                    "league_code": LEAGUE_BY_COMPETITION[m.competition].code,
                    "market_key": it["market_key"],
                    "market_family": market_family(it["market_key"]),
                    "p": it["p"],
                    "p_prudent": it["p_prudent"],
                    "quota_used": it["quota_used"],
                    "expected_profit": it["expected_profit"],
                    "outcome": outcome,
                    "profit_units": profit_units(outcome, it["quota_used"]) if outcome else None,
                }
            )
    return plays, dict(abstentions)


def null_distribution(history: History, plays: list[dict[str, Any]], n: int, seed: int) -> list[float]:
    """Nullo di procedura: permuta gli esiti (risultato, primo tempo, statistiche) tra le partite dello stesso
    campionato nella stessa data e riregola le stesse giocate."""
    by_id = history.by_id()
    groups: dict[tuple[str, date], list[int]] = defaultdict(list)
    for m in history.matches:
        if m.season_label in JUDGE_SEASONS:
            groups[(m.competition, m.match_date)].append(m.lab_match_id)
    outcomes_of = {mid: (match_result(by_id[mid]), match_stats_json(by_id[mid], history.extras[mid])) for mids in groups.values() for mid in mids}
    rng = random.Random(seed)
    profits: list[float] = []
    for _ in range(n):
        permuted: dict[int, tuple[dict, dict]] = {}
        for mids in groups.values():
            shuffled = list(mids)
            rng.shuffle(shuffled)
            for src, dst in zip(mids, shuffled):
                permuted[dst] = outcomes_of[src]
        total = 0.0
        for pl in plays:
            res, st = permuted[pl["match_id"]]
            out = settle(pl["market_key"], res, st)
            pu = profit_units(out, pl["quota_used"]) if out else None
            if pu is not None:
                total += pu
        profits.append(total)
    return profits


def _table(plays: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list] = defaultdict(list)
    for p in plays:
        groups[str(p[key])].append(p)
    out = []
    for k in sorted(groups):
        r = roi(groups[k])
        out.append({key: k, **r})
    return out


def _md(result: dict[str, Any]) -> str:
    c = result["criteria"]
    L = [
        "# Esame E4: selezione V4 sui mercati classici, quote di chiusura Bet365",
        "",
        f"Calcolato il {result['computed_at']}. Pre-registrazione: `{PREREG}`. Verdetto: **{'SUPERATO' if result['passed'] else 'NON SUPERATO'}**.",
        "",
        "| Criterio | Valore | Soglia | Esito |",
        "|---|---|---|---|",
        f"| E4.1 ROI e intervallo 90% | {result['roi']['roi']:+.4f} ({result['roi_ci'][0]:+.4f} · {result['roi_ci'][1]:+.4f}) | bordo inferiore > 0 | {'✓' if c['E4.1'] else '✗'} |",
        f"| E4.2 giocate | {result['roi']['plays']} | ≥ {MIN_PLAYS} | {'✓' if c['E4.2'] else '✗'} |",
        f"| E4.3 nullo di procedura | profitto {result['roi']['profit_units']:+.2f} contro 95° percentile {result['null']['p95']:+.2f} (mediana {result['null']['median']:+.2f}) | osservato > p95 | {'✓' if c['E4.3'] else '✗'} |",
        f"| E4.4 concentrazione | {result['league_share']['share']:.0%} ({result['league_share']['league']}) | ≤ 40% | {'✓' if c['E4.4'] else '✗'} |",
        "",
        "## Per stagione",
        "",
        "| Stagione | Giocate | Profitto | ROI |",
        "|---|---|---|---|",
    ]
    for r in result["by_season"]:
        L.append(f"| {r['season']} | {r['plays']} | {r['profit_units']:+.2f} | {r['roi']:+.4f} |" if r["roi"] is not None else f"| {r['season']} | 0 | – | – |")
    L += ["", "## Per famiglia", "", "| Famiglia | Giocate | Profitto | ROI |", "|---|---|---|---|"]
    for r in result["by_family"]:
        L.append(f"| {r['market_family']} | {r['plays']} | {r['profit_units']:+.2f} | {r['roi']:+.4f} |" if r["roi"] is not None else f"| {r['market_family']} | 0 | – | – |")
    L += ["", "## Per campionato", "", "| Campionato | Giocate | Profitto | ROI |", "|---|---|---|---|"]
    for r in result["by_league"]:
        L.append(f"| {r['competition']} | {r['plays']} | {r['profit_units']:+.2f} | {r['roi']:+.4f} |" if r["roi"] is not None else f"| {r['competition']} | 0 | – | – |")
    L += ["", "## Astensioni (partite idonee senza giocata)", ""]
    for k, v in sorted(result["abstentions"].items(), key=lambda kv: -kv[1]):
        L.append(f"- {k}: {v}")
    L += [
        "",
        "## Lettura",
        "",
        result["reading"],
        "",
        "## Conseguenze",
        "",
        "Se non superato: la shortlist resta visibile, le famiglie classiche portano `advised = false` e la vista Shortlist mostra il banner "
        "\"Esame E4 non superato: giocate classiche in osservazione, non consigliate\". Nessuna soglia viene cambiata.",
    ]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    t0 = time.monotonic()
    history = load_history()
    matches = history.matches
    cache_key = "full_" + matches_digest(matches)
    print(f"[E4] {len(matches)} partite; previsioni gol (configurazione adottata da E1)…")
    cfg = V4GoalsConfig(**GOALS_CONFIG) if isinstance(GOALS_CONFIG, dict) else GOALS_CONFIG
    baseline = run_v3_phase4_full(matches, cache_key=cache_key)
    hypers = set(baseline.chosen_forza.values()) | {baseline.next_forza}
    params = compute_strength_params(matches, hypers, cache_key=cache_key)
    goals = predict_history_full(history, cfg, baseline=baseline, params=params, cache_key=cache_key).payloads
    print(f"[E4] gol pronte ({len(goals)}) in {time.monotonic() - t0:.0f} s; statistiche…")
    stats = stats_predict_history(history, STATS_CONFIG, exam=load_exam_verdicts())
    print(f"[E4] statistiche pronte ({len(stats)}) in {time.monotonic() - t0:.0f} s; selezione…")

    plays, abstentions = select_plays(history, goals, stats)
    settled = [p for p in plays if p["profit_units"] is not None]
    r = roi(settled)
    lo, hi = block_bootstrap_ci(settled, block_key="block", n=BOOTSTRAP_N, seed=SEED)
    print(f"[E4] giocate {r['plays']} · ROI {r['roi']} · IC90 ({lo}, {hi}); nullo…")
    null = null_distribution(history, settled, NULL_N, SEED)
    p95 = float(np.percentile(null, 95)) if null else float("nan")
    by_league = _table(settled, "competition")
    positives = [x for x in by_league if x["profit_units"] > 0]
    total_pos = sum(x["profit_units"] for x in positives) or 0.0
    top = max(positives, key=lambda x: x["profit_units"]) if positives else None
    share = (top["profit_units"] / total_pos) if top and total_pos > 0 else 0.0

    criteria = {
        "E4.1": bool(lo is not None and lo > 0),
        "E4.2": bool(r["plays"] >= MIN_PLAYS),
        "E4.3": bool(null and r["profit_units"] > p95),
        "E4.4": bool(share <= MAX_LEAGUE_SHARE),
    }
    passed = all(criteria.values())
    if r["roi"] is None or r["roi"] <= 0:
        reading = (
            "Alla chiusura Bet365 la regola del profitto, applicata alle probabilita' V4 (che coincidono con la V3 Fase 4, "
            "esame E1 non superato), non produce un profitto: e' lo stesso esito del valutatore V3. Le giocate classiche "
            "restano visibili ma in osservazione. Il giudizio sui mercati speciali e' solo prospettico (G6)."
        )
    elif not passed:
        reading = "Profitto positivo ma non abbastanza robusto rispetto ai criteri pre-registrati: giocate classiche in osservazione."
    else:
        reading = "La regola supera tutti i criteri pre-registrati sui mercati classici: le giocate classiche sono consigliate."

    result: dict[str, Any] = {
        "code": "E4",
        "title": "Selezione sui mercati classici con quote di chiusura",
        "preregistration": PREREG,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": passed,
        "criteria": criteria,
        "roi": r,
        "roi_ci": [lo, hi],
        "null": {"n": len(null), "p95": p95, "median": float(np.median(null)) if null else None, "mean": float(np.mean(null)) if null else None},
        "league_share": {"league": top["competition"] if top else None, "share": share},
        "by_season": _table(settled, "season"),
        "by_family": _table(settled, "market_family"),
        "by_league": by_league,
        "abstentions": abstentions,
        "unsettled": len(plays) - len(settled),
        "goals_config": GOALS_CONFIG if isinstance(GOALS_CONFIG, dict) else GOALS_CONFIG.__dict__,
        "reading": reading,
        "runtime_s": round(time.monotonic() - t0, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    EXAMS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (EXAMS_DATA_DIR / OUT_JSON.name).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(_md(result), encoding="utf-8")
    print(f"[E4] {'SUPERATO' if passed else 'NON SUPERATO'} · {criteria} · {result['runtime_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
