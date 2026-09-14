"""Taratura una tantum della V2.5 sulla sola stagione 2021/22 (stagione di scoperta).

Due compiti, nessuna scrittura sul database:
1. scale congelate (`frozen_scales.json`): percentili dei valori PRE-PARTITA delle partite
   eleggibili 2021/22 (Intensita' Goal, Equilibrio, quote per i segnali). Nessun risultato
   entra nelle scale;
2. scelta delle costanti di correzione (partite virtuali di campionato) confrontando la
   precisione (Brier / log loss) sulle partite 2021/22 per alcune combinazioni, insieme
   alla RUN V2 della stessa stagione come riferimento.

Le stagioni 2022/23 in avanti non vengono lette.
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.historical_eligibility import evaluate_historical_eligibility
from app.services.cecchino_data_lab.historical_kickoff_group import group_work_by_kickoff
from app.services.cecchino_data_lab.historical_rolling_state import GlobalRollingStateRegistry
from app.services.cecchino_data_lab.run_v2.executor import _load_work
from app.services.cecchino_v25 import balance as balance_mod
from app.services.cecchino_v25 import goal_intensity as gi_mod
from app.services.cecchino_v25.goals import GoalParams, compute_goal_markets_v25
from app.services.cecchino_v25.picchetti import compute_cecchino_v25
from app.services.cecchino_v25.scales import _SCALES_FILE, quantile_knots, reload_scales

CALIBRATION_SEASON = "2021/2022"
SCALE_POINTS = 20
SIGNAL_POINTS = 100

PICCHETTI_GRID = (0.5, 2.0, 4.0, 8.0, 12.0)
GOAL_GRID = (
    GoalParams(rate_prior=2.0, hit_prior=2.0, reliability_prior=3.0),
    GoalParams(rate_prior=5.0, hit_prior=5.0, reliability_prior=6.0),
    GoalParams(rate_prior=8.0, hit_prior=8.0, reliability_prior=10.0),
    GoalParams(rate_prior=12.0, hit_prior=12.0, reliability_prior=16.0),
)
_GOAL_EVAL = ("OVER_0_5", "OVER_1_5", "OVER_2_5", "OVER_3_5", "OVER_PT_0_5", "OVER_PT_1_5")


def _outcomes(match: Any) -> dict[str, float] | None:
    gh, ga = match.ft_home_goals, match.ft_away_goals
    if gh is None or ga is None:
        return None
    t = gh + ga
    out = {
        "HOME": float(gh > ga), "DRAW": float(gh == ga), "AWAY": float(gh < ga),
        "OVER_0_5": float(t > 0.5), "OVER_1_5": float(t > 1.5), "OVER_2_5": float(t > 2.5), "OVER_3_5": float(t > 3.5),
    }
    if match.ht_home_goals is not None and match.ht_away_goals is not None:
        ht = match.ht_home_goals + match.ht_away_goals
        out["OVER_PT_0_5"] = float(ht > 0.5)
        out["OVER_PT_1_5"] = float(ht > 1.5)
    return out


def _logloss(p: float, y: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


class _Acc:
    def __init__(self) -> None:
        self.n = defaultdict(int)
        self.brier = defaultdict(float)
        self.ll = defaultdict(float)

    def add(self, name: str, brier: float, ll: float) -> None:
        self.n[name] += 1
        self.brier[name] += brier
        self.ll[name] += ll

    def report(self) -> dict[str, Any]:
        return {
            k: {"n": self.n[k], "brier": round(self.brier[k] / self.n[k], 5), "log_loss": round(self.ll[k] / self.n[k], 5)}
            for k in sorted(self.n)
        }


def _v2_reference(db: Session, v2_run_id: int) -> dict[int, dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT s.lab_match_id,
                   (s.cecchino_output_json->'final'->>'quota_1')::float q1,
                   (s.cecchino_output_json->'final'->>'quota_x')::float qx,
                   (s.cecchino_output_json->'final'->>'quota_2')::float q2,
                   (s.goal_markets_json->'v1_lab'->'UNDER_2_5'->>'final_odd')::float u25
            FROM cecchino_run_v2_match_snapshots s
            WHERE s.run_id = :rid AND s.eligibility_status = 'eligible_core' AND s.season_label = :season
            """
        ),
        {"rid": v2_run_id, "season": CALIBRATION_SEASON},
    )
    return {int(r[0]): {"q1": r[1], "qx": r[2], "q2": r[3], "u25": r[4]} for r in rows}


def _v2_market_probabilities(db: Session, v2_run_id: int) -> dict[tuple[int, str], float]:
    rows = db.execute(
        text(
            """
            SELECT r.lab_match_id, r.market_key, r.probability
            FROM cecchino_run_v2_market_results r
            JOIN cecchino_run_v2_match_snapshots s ON s.id = r.match_snapshot_id
            WHERE r.run_id = :rid AND s.eligibility_status = 'eligible_core' AND r.probability IS NOT NULL
            """
        ),
        {"rid": v2_run_id},
    )
    return {(int(m), str(k)): float(p) for m, k, p in rows}


def run_calibration(db: Session, *, v2_run_id: int, write_scales: bool = False) -> dict[str, Any]:
    from app.services.cecchino_v25.executor import V25State

    started = time.perf_counter()
    all_work, proxies_by_key = _load_work(db)
    work = [w for w in all_work if w.season_label == CALIBRATION_SEASON]
    state = V25State(proxies_by_key, CALIBRATION_SEASON)
    rolling = GlobalRollingStateRegistry()
    for key, proxies in proxies_by_key.items():
        if key.endswith(f"::{CALIBRATION_SEASON}"):
            rolling.register_competition(key, proxies)

    v2_quotas = _v2_reference(db, v2_run_id)
    v2_probs = _v2_market_probabilities(db, v2_run_id)

    features: dict[str, list[float]] = defaultdict(list)
    pic_acc = {k: _Acc() for k in PICCHETTI_GRID}
    goal_acc = {i: _Acc() for i in range(len(GOAL_GRID))}
    v2_acc = _Acc()
    v2_common_acc = _Acc()  # V2.5 (costanti di default) sulle stesse partite eleggibili V2
    eligible = 0

    for group in group_work_by_kickoff(work, kickoff_at_getter=lambda w: w.match.kickoff_at):
        for item in group:
            comp = rolling.get_competition(item.rolling_key)
            contexts = comp.contexts_for(item.proxy)
            league = state.reference(item.competition, item.rolling_key)
            base = compute_cecchino_v25(contexts, league)
            elig = evaluate_historical_eligibility(
                home_team=item.match.home_team,
                away_team=item.match.away_team,
                kickoff_at=item.match.kickoff_at,
                contexts=contexts,
                cecchino_output=base,
            )
            if not elig.get("core_eligible"):
                continue
            eligible += 1
            y = _outcomes(item.match)
            mid = int(item.match.id)

            for k in PICCHETTI_GRID:
                final = compute_cecchino_v25(contexts, league, prior_matches=k)["final"]
                if y is None or final.get("prob_1") is None:
                    continue
                probs = (final["prob_1"], final["prob_x"], final["prob_2"])
                outs = (y["HOME"], y["DRAW"], y["AWAY"])
                pic_acc[k].add("1X2", sum((p - o) ** 2 for p, o in zip(probs, outs)), -math.log(max(1e-6, sum(p * o for p, o in zip(probs, outs)))))

            goal_outputs = [compute_goal_markets_v25(contexts, league, params=params) for params in GOAL_GRID]
            for i, g in enumerate(goal_outputs):
                for key in _GOAL_EVAL:
                    p = g.probability(key)
                    if y is None or p is None or key not in y:
                        continue
                    goal_acc[i].add(key, (p - y[key]) ** 2, _logloss(p, y[key]))

            if y is not None and all((mid, k) in v2_probs for k in ("HOME", "DRAW", "AWAY")):
                pv2 = [v2_probs[(mid, k)] for k in ("HOME", "DRAW", "AWAY")]
                outs = (y["HOME"], y["DRAW"], y["AWAY"])
                v2_acc.add("1X2_raw", sum((p - o) ** 2 for p, o in zip(pv2, outs)), 0.0)
                s = sum(pv2)
                pn = [p / s for p in pv2]
                v2_acc.add("1X2_normalized", sum((p - o) ** 2 for p, o in zip(pn, outs)), -math.log(max(1e-6, sum(p * o for p, o in zip(pn, outs)))))
                fin = base["final"]
                v2_common_acc.add(
                    "1X2",
                    sum((p - o) ** 2 for p, o in zip((fin["prob_1"], fin["prob_x"], fin["prob_2"]), outs)),
                    -math.log(max(1e-6, sum(p * o for p, o in zip((fin["prob_1"], fin["prob_x"], fin["prob_2"]), outs)))),
                )
            for key in _GOAL_EVAL:
                if y is not None and key in y and (mid, key) in v2_probs:
                    p = v2_probs[(mid, key)]
                    v2_acc.add(key, (p - y[key]) ** 2, _logloss(p, y[key]))
                    p25 = goal_outputs[1].probability(key)
                    if p25 is not None:
                        v2_common_acc.add(key, (p25 - y[key]) ** 2, _logloss(p25, y[key]))

            # valori pre-partita per le scale (costanti di default)
            goals = goal_outputs[1]
            gi = gi_mod.raw_features(contexts, league, goals)
            if gi is not None:
                features[gi_mod.SCALE_ATTACK].append(gi["attack_ratio"])
                features[gi_mod.SCALE_DEFENCE].append(gi["defence_ratio"])
                features[gi_mod.SCALE_TEMPO].append(gi["tempo_ratio"])
                features[gi_mod.SCALE_CONSISTENCY].append(gi["scoring_consistency"])
                if gi["over_2_5_probability"] == gi["over_2_5_probability"]:
                    features[gi_mod.SCALE_FINAL].append(gi["over_2_5_probability"])
            bal = balance_mod.raw_features(base["final"], goals.lambda_home, goals.lambda_away)
            if bal is not None:
                features[balance_mod.SCALE_SIDE_GAP].append(bal["side_gap"])
                features[balance_mod.SCALE_CONVICTION].append(bal["conviction"])
                features[balance_mod.SCALE_DRAW].append(bal["draw_probability"])
                if "engine_disagreement" in bal:
                    features[balance_mod.SCALE_COHERENCE].append(bal["engine_disagreement"])
            fin = base["final"]
            features["sig_v25_q1"].append(fin["quota_1"])
            features["sig_v25_qx"].append(fin["quota_x"])
            features["sig_v25_q2"].append(fin["quota_2"])
            u = (goals.goal_markets.get("UNDER_2_5") or {}).get("final_odd")
            if u is not None:
                features["sig_v25_under_2_5"].append(u)

        # gruppo chiuso: visibile alle partite successive
        by_key: dict[str, list[Any]] = defaultdict(list)
        for item in group:
            by_key[item.rolling_key].append(item.proxy)
            state.commit(item.rolling_key, item.proxy)
        for key, proxies in by_key.items():
            rolling.get_competition(key).commit_group(proxies)

    for name, src in (("sig_v2_q1", "q1"), ("sig_v2_qx", "qx"), ("sig_v2_q2", "q2"), ("sig_v2_under_2_5", "u25")):
        features[name] = [v[src] for v in v2_quotas.values() if v[src] is not None]

    scales_payload = {
        "version": f"v25_scales_{CALIBRATION_SEASON.replace('/', '_')}_v1",
        "season": CALIBRATION_SEASON,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sizes": {k: len(v) for k, v in features.items()},
        "scales": {
            k: quantile_knots(v, SIGNAL_POINTS if k.startswith("sig_") else SCALE_POINTS)
            for k, v in sorted(features.items())
        },
    }
    if write_scales:
        _SCALES_FILE.write_text(json.dumps(scales_payload, indent=1), encoding="utf-8")
        reload_scales()
    return {
        "season": CALIBRATION_SEASON,
        "eligible_matches": eligible,
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "picchetti_grid": {str(k): acc.report() for k, acc in pic_acc.items()},
        "goal_grid": {
            f"rate{p.rate_prior}_hit{p.hit_prior}_rel{p.reliability_prior}": goal_acc[i].report()
            for i, p in enumerate(GOAL_GRID)
        },
        "v2_same_matches": v2_acc.report(),
        "v25_default_on_v2_eligible": v2_common_acc.report(),
        "scales": scales_payload,
    }
