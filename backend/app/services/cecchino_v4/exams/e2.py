"""Esame E2: motore statistiche contro baseline ingenue e oltre il mercato.

Criteri fissati in docs/v4/PREREGISTRAZIONE_FASE_2.md §3 PRIMA del calcolo. Scrive
docs/v4/esami/E2.json e docs/v4/esami/E2.md.

Le quote Bet365 di chiusura entrano SOLO nella parte (b), come metro (regola 2).

Uso: python -m app.services.cecchino_v4.exams.e2
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.services.cecchino_v3.data import MatchRecord

from app.services.cecchino_v4.constants import JUDGE_SEASONS, STAT_LINES, STAT_SIDES, STATS
from app.services.cecchino_v4.engine_stats import distribution as dist
from app.services.cecchino_v4.engine_stats.config import ADOPTED_CONFIG, StatsConfig
from app.services.cecchino_v4.engine_stats.counts import stat_pair
from app.services.cecchino_v4.engine_stats.engine import StatPredictions, fit_history
from app.services.cecchino_v4.history.football_data import History, load_history

REPO = Path(__file__).resolve().parents[5]
OUT_DIR = REPO / "docs" / "v4" / "esami"
PREREG = "docs/v4/PREREGISTRAZIONE_FASE_2.md"

B1_MIN_MATCHES = 3
B2_LAST = 5
CALIBRATION_BINS = 10
CALIBRATION_MAX_GAP = 0.03
T_MIN = 2.0

SIDE_LABEL = {"home": "casa", "away": "ospite", "total": "totale"}


# --- Baseline ingenue (PREREGISTRAZIONE §3.1) --------------------------------------------------------


def naive_baselines(matches: list[MatchRecord], extras, stat: str) -> dict[int, tuple[float, float, float, float]]:
    """Per partita: (B1 casa, B1 ospite, B2 casa, B2 ospite). Solo partite strettamente precedenti,
    stesso campionato e stagione."""
    ordered = sorted(matches, key=lambda m: (m.day, m.competition, m.home_team))
    season_for: dict[tuple, list[float]] = defaultdict(list)  # (comp, season, team) -> fatti
    season_ag: dict[tuple, list[float]] = defaultdict(list)
    last_for: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=B2_LAST))
    last_ag: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=B2_LAST))
    div_sum: dict[tuple, float] = defaultdict(float)  # (comp, season) -> somma valori per squadra
    div_n: dict[tuple, int] = defaultdict(int)
    out: dict[int, tuple[float, float, float, float]] = {}

    def mean_or_div(values, key_div, min_n) -> float | None:
        if len(values) >= min_n and len(values) > 0:
            return float(np.mean(values))
        if div_n[key_div] > 0:
            return div_sum[key_div] / div_n[key_div]
        return None

    i = 0
    n = len(ordered)
    while i < n:
        today = ordered[i].day
        j = i
        while j < n and ordered[j].day == today:
            j += 1
        day_rows = ordered[i:j]
        for m in day_rows:
            kd = (m.competition, m.season_label)
            kh = (m.competition, m.season_label, m.home_team)
            ka = (m.competition, m.season_label, m.away_team)
            b1_h_for = mean_or_div(season_for[kh], kd, B1_MIN_MATCHES)
            b1_a_ag = mean_or_div(season_ag[ka], kd, B1_MIN_MATCHES)
            b1_a_for = mean_or_div(season_for[ka], kd, B1_MIN_MATCHES)
            b1_h_ag = mean_or_div(season_ag[kh], kd, B1_MIN_MATCHES)
            b2_h_for = mean_or_div(list(last_for[kh]), kd, 1)
            b2_a_ag = mean_or_div(list(last_ag[ka]), kd, 1)
            b2_a_for = mean_or_div(list(last_for[ka]), kd, 1)
            b2_h_ag = mean_or_div(list(last_ag[kh]), kd, 1)
            vals = (b1_h_for, b1_a_ag, b1_a_for, b1_h_ag, b2_h_for, b2_a_ag, b2_a_for, b2_h_ag)
            if all(v is not None for v in vals):
                out[m.lab_match_id] = (
                    0.5 * (b1_h_for + b1_a_ag),
                    0.5 * (b1_a_for + b1_h_ag),
                    0.5 * (b2_h_for + b2_a_ag),
                    0.5 * (b2_a_for + b2_h_ag),
                )
        for m in day_rows:
            h, a = stat_pair(m, extras.get(m.lab_match_id), stat)
            if h is None or a is None:
                continue
            kd = (m.competition, m.season_label)
            kh = (m.competition, m.season_label, m.home_team)
            ka = (m.competition, m.season_label, m.away_team)
            season_for[kh].append(h)
            season_ag[kh].append(a)
            season_for[ka].append(a)
            season_ag[ka].append(h)
            last_for[kh].append(h)
            last_ag[kh].append(a)
            last_for[ka].append(a)
            last_ag[ka].append(h)
            div_sum[kd] += h + a
            div_n[kd] += 2
        i = j
    return out


# --- Metro di mercato (solo qui) -------------------------------------------------------------------------


def market_features(extras) -> dict[int, tuple[float, float]]:
    """(dominio, totale) dalle quote Bet365 di chiusura: p normalizzate senza margine."""
    out: dict[int, tuple[float, float]] = {}
    for mid, ex in extras.items():
        oc = ex.odds_close
        if not all(k in oc for k in ("HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5")):
            continue
        inv = np.array([1.0 / oc["HOME"], 1.0 / oc["DRAW"], 1.0 / oc["AWAY"]])
        p = inv / inv.sum()
        io, iu = 1.0 / oc["OVER_2_5"], 1.0 / oc["UNDER_2_5"]
        out[mid] = (float(p[0] - p[2]), float(io / (io + iu)))
    return out


def ols(y: np.ndarray, x_cols: list[np.ndarray]) -> dict[str, Any]:
    x = np.column_stack([np.ones_like(y)] + x_cols)
    n, k = x.shape
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    rss = float(resid @ resid)
    tss = float(np.sum((y - y.mean()) ** 2))
    sigma2 = rss / max(n - k, 1)
    cov = sigma2 * np.linalg.pinv(x.T @ x)
    se = np.sqrt(np.maximum(np.diag(cov), 1e-18))
    return {"coef": beta, "t": beta / se, "r2": 1.0 - rss / tss if tss > 0 else 0.0, "n": int(n)}


# --- Esame ---------------------------------------------------------------------------------------------


def _f(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


def exam_stat(
    sp: StatPredictions, baselines: dict[int, tuple], market: dict[int, tuple[float, float]]
) -> dict[str, Any]:
    run = sp.run
    keys = np.array(run.keys, dtype=object)
    season = np.array(run.season, dtype=object)
    base_mask = run.usable & run.eligible & np.array([k in baselines for k in run.keys], dtype=bool)
    b = {k: baselines[k] for k in keys[base_mask]}
    b1_h = np.array([b[k][0] for k in keys[base_mask]])
    b1_a = np.array([b[k][1] for k in keys[base_mask]])
    b2_h = np.array([b[k][2] for k in keys[base_mask]])
    b2_a = np.array([b[k][3] for k in keys[base_mask]])
    base_by_side = {"home": (b1_h, b2_h), "away": (b1_a, b2_a), "total": (b1_h + b1_a, b2_h + b2_a)}

    result: dict[str, Any] = {"accuracy": {}, "beyond_market": {}, "calibration": {}}
    acc_pass = True
    bm_pass = True

    # (a) accuratezza
    for side in STAT_SIDES:
        mean, alpha, _ = sp.side(side)
        y_all = sp.realized(side)
        mean_b, alpha_b, y_b = mean[base_mask], alpha[base_mask], y_all[base_mask]
        b1, b2 = base_by_side[side]
        season_b = season[base_mask]
        result["accuracy"][side] = {}
        for s in JUDGE_SEASONS:
            m = season_b == s
            if not np.any(m):
                result["accuracy"][side][s] = {"n": 0, "pass": False}
                acc_pass = False
                continue
            row = {
                "n": int(m.sum()),
                "mae_model": _f(np.mean(np.abs(y_b[m] - mean_b[m]))),
                "mae_b1": _f(np.mean(np.abs(y_b[m] - b1[m]))),
                "mae_b2": _f(np.mean(np.abs(y_b[m] - b2[m]))),
                "crps_model": _f(np.mean(dist.crps(y_b[m], mean_b[m], alpha_b[m]))),
                "crps_b1": _f(np.mean(dist.crps(y_b[m], b1[m], 0.0))),
                "crps_b2": _f(np.mean(dist.crps(y_b[m], b2[m], 0.0))),
            }
            raw_mae = np.mean(np.abs(y_b[m] - mean_b[m]))
            raw_crps = np.mean(dist.crps(y_b[m], mean_b[m], alpha_b[m]))
            ok = (
                raw_mae < np.mean(np.abs(y_b[m] - b1[m]))
                and raw_mae < np.mean(np.abs(y_b[m] - b2[m]))
                and raw_crps < np.mean(dist.crps(y_b[m], b1[m], 0.0))
                and raw_crps < np.mean(dist.crps(y_b[m], b2[m], 0.0))
            )
            row["pass"] = bool(ok)
            acc_pass &= bool(ok)
            result["accuracy"][side][s] = row

    # calibrazione pooled: stagioni di giudizio, righe eleggibili, tutti i lati e tutte le linee
    judge_mask = run.usable & run.eligible & np.isin(season, list(JUDGE_SEASONS))
    lines = np.array(STAT_LINES[sp.stat], dtype=float)
    p_all: list[np.ndarray] = []
    o_all: list[np.ndarray] = []
    for side in STAT_SIDES:
        mean, alpha, _ = sp.side(side)
        y_all = sp.realized(side)
        p = dist.prob_over(lines[None, :], mean[judge_mask, None], alpha[judge_mask, None])
        o = (y_all[judge_mask, None] > lines[None, :]).astype(float)
        p_all.append(p.ravel())
        o_all.append(o.ravel())
    p_cat = np.concatenate(p_all)
    o_cat = np.concatenate(o_all)
    edges = np.linspace(0.0, 1.0, CALIBRATION_BINS + 1)
    idx = np.clip(np.digitize(p_cat, edges[1:-1]), 0, CALIBRATION_BINS - 1)
    bins = []
    gap_num = 0.0
    for k in range(CALIBRATION_BINS):
        m = idx == k
        cnt = int(m.sum())
        if cnt == 0:
            bins.append({"bin": k, "n": 0})
            continue
        pm, om = float(p_cat[m].mean()), float(o_cat[m].mean())
        bins.append({"bin": k, "lo": _f(edges[k], 2), "hi": _f(edges[k + 1], 2), "n": cnt, "p_mean": _f(pm), "obs": _f(om), "gap": _f(abs(pm - om))})
        gap_num += cnt * abs(pm - om)
    gap = gap_num / max(p_cat.size, 1)
    cal_pass = bool(gap <= CALIBRATION_MAX_GAP) and p_cat.size > 0
    result["calibration"] = {"gap": _f(gap), "n": int(p_cat.size), "pass": cal_pass, "bins": bins}

    # (b) oltre il mercato
    mkt_mask = run.usable & run.eligible & np.array([k in market for k in run.keys], dtype=bool)
    dom = np.array([market[k][0] if k in market else np.nan for k in run.keys])
    tot = np.array([market[k][1] if k in market else np.nan for k in run.keys])
    for side in STAT_SIDES:
        mean, _, _ = sp.side(side)
        y_all = sp.realized(side)
        sign = -1.0 if side == "away" else 1.0
        result["beyond_market"][side] = {}
        signs: list[float] = []
        for s in JUDGE_SEASONS:
            m = mkt_mask & (season == s)
            if m.sum() < 10:
                result["beyond_market"][side][s] = {"n": int(m.sum()), "pass": False}
                bm_pass = False
                continue
            full = ols(y_all[m], [mean[m], sign * dom[m], tot[m]])
            reduced = ols(y_all[m], [sign * dom[m], tot[m]])
            coef, t = full["coef"], full["t"]
            ok = bool(coef[1] > 0 and t[1] >= T_MIN)
            signs.append(float(np.sign(coef[1])))
            result["beyond_market"][side][s] = {
                "n": full["n"],
                "coef_model": _f(coef[1]),
                "t_model": _f(t[1], 2),
                "coef_dominance": _f(coef[2]),
                "t_dominance": _f(t[2], 2),
                "coef_total": _f(coef[3]),
                "t_total": _f(t[3], 2),
                "intercept": _f(coef[0]),
                "r2_with_model": _f(full["r2"]),
                "r2_without_model": _f(reduced["r2"]),
                "pass": ok,
            }
            bm_pass &= ok
        if signs and len(set(signs)) > 1:
            bm_pass = False

    result["accuracy_pass"] = bool(acc_pass)
    result["calibration_pass"] = cal_pass
    result["beyond_market_pass"] = bool(bm_pass)
    result["verdict"] = "superato" if (acc_pass and cal_pass and bm_pass) else "non_superato"
    result["hyper_by_season"] = {
        s: {"hyper": spec.hyper.key, "source_season": spec.source_season, "scores": {k: _f(v, 5) for k, v in spec.scores.items()}}
        for s, spec in sp.specs.items()
    }
    result["dispersion_by_season"] = {
        s: {comp: (None if a is None else _f(a, 4)) for comp, a in spec.alpha.items()} for s, spec in sp.specs.items()
    }
    return result


def run_exam(config: StatsConfig = ADOPTED_CONFIG, *, history: History | None = None, out_dir: Path = OUT_DIR) -> dict[str, Any]:
    t0 = time.time()
    history = history or load_history()
    preds = fit_history(history, config)
    t_fit = time.time() - t0
    market = market_features(history.extras)
    stats_result: dict[str, Any] = {}
    for stat in config.stats:
        baselines = naive_baselines(history.matches, history.extras, stat)
        stats_result[stat] = exam_stat(preds[stat], baselines, market)
    cfg = asdict(config)
    cfg["cache_dir"] = str(config.cache_dir) if config.cache_dir else None
    cfg["hyper_grid"] = [h.key for h in config.hyper_grid]
    cfg["default_hyper"] = config.default_hyper.key
    report = {
        "exam": "E2",
        "title": "Motore statistiche: accuratezza, calibrazione e test oltre il mercato",
        "preregistration": PREREG,
        "engine_version": config.version,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_seconds": {"fit": _f(t_fit, 1), "total": _f(time.time() - t0, 1)},
        "judge_seasons": list(JUDGE_SEASONS),
        "matches_loaded": len(history.matches),
        "config": cfg,
        "criteria": {
            "accuracy": "MAE e CRPS < B1 e B2 in ogni stagione di giudizio, per ogni lato",
            "calibration": f"divario medio pesato su {CALIBRATION_BINS} intervalli ≤ {CALIBRATION_MAX_GAP}",
            "beyond_market": f"coefficiente del modello > 0 con t ≥ {T_MIN} in ogni stagione, segno stabile, per ogni lato",
        },
        "stats": stats_result,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "E2.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "E2.md").write_text(render_markdown(report), encoding="utf-8")
    return report


# --- Rapporto leggibile ----------------------------------------------------------------------------------


def _fmt(v, nd=3) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "sì" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}".replace(".", ",")
    return str(v)


def render_markdown(report: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("# Esame E2: motore statistiche")
    L.append("")
    L.append(f"Calcolato il {report['computed_at']} secondo `{report['preregistration']}`. Motore `{report['engine_version']}`. "
             f"Partite caricate: {report['matches_loaded']}. Tempo: {_fmt(report['runtime_seconds']['total'], 0)} s "
             f"(stima {_fmt(report['runtime_seconds']['fit'], 0)} s).")
    L.append("")
    L.append("Le quote Bet365 di chiusura entrano solo nella parte (b) come metro; mai nel modello.")
    L.append("")
    L.append("## Verdetti")
    L.append("")
    L.append("| Statistica | (a) accuratezza | calibrazione (divario) | (b) oltre il mercato | Verdetto |")
    L.append("|---|---|---|---|---|")
    for stat, r in report["stats"].items():
        L.append(f"| {STATS[stat]} | {_fmt(r['accuracy_pass'])} | {_fmt(r['calibration_pass'])} ({_fmt(r['calibration']['gap'])}) | "
                 f"{_fmt(r['beyond_market_pass'])} | **{r['verdict'].replace('_', ' ')}** |")
    L.append("")
    for stat, r in report["stats"].items():
        L.append(f"## {STATS[stat].capitalize()} (`{stat}`): {r['verdict'].replace('_', ' ')}")
        L.append("")
        L.append("### (a) Accuratezza: MAE e CRPS contro le baseline")
        L.append("")
        L.append("| Lato | Stagione | n | MAE modello | MAE B1 | MAE B2 | CRPS modello | CRPS B1 | CRPS B2 | Passa |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for side, seasons in r["accuracy"].items():
            for s, row in seasons.items():
                if row.get("n", 0) == 0:
                    L.append(f"| {SIDE_LABEL[side]} | {s} | 0 | — | — | — | — | — | — | no |")
                    continue
                L.append(f"| {SIDE_LABEL[side]} | {s} | {row['n']} | {_fmt(row['mae_model'])} | {_fmt(row['mae_b1'])} | {_fmt(row['mae_b2'])} | "
                         f"{_fmt(row['crps_model'])} | {_fmt(row['crps_b1'])} | {_fmt(row['crps_b2'])} | {_fmt(row['pass'])} |")
        L.append("")
        cal = r["calibration"]
        L.append(f"### Calibrazione: divario medio {_fmt(cal['gap'])} su {cal['n']} coppie (soglia {_fmt(CALIBRATION_MAX_GAP, 2)}), passa: {_fmt(cal['pass'])}")
        L.append("")
        L.append("| Intervallo | n | P(over) media | Frequenza | Divario |")
        L.append("|---|---|---|---|---|")
        for b in cal["bins"]:
            if b.get("n", 0) == 0:
                continue
            L.append(f"| {_fmt(b['lo'], 1)}–{_fmt(b['hi'], 1)} | {b['n']} | {_fmt(b['p_mean'])} | {_fmt(b['obs'])} | {_fmt(b['gap'])} |")
        L.append("")
        L.append("### (b) Oltre il mercato: OLS della statistica reale su [1, modello, dominio, totale]")
        L.append("")
        L.append("| Lato | Stagione | n | coef. modello | t | coef. dominio | t | coef. totale | t | R² con | R² senza | Passa |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for side, seasons in r["beyond_market"].items():
            for s, row in seasons.items():
                if row.get("n", 0) < 10:
                    L.append(f"| {SIDE_LABEL[side]} | {s} | {row.get('n', 0)} | — | — | — | — | — | — | — | — | no |")
                    continue
                L.append(f"| {SIDE_LABEL[side]} | {s} | {row['n']} | {_fmt(row['coef_model'])} | {_fmt(row['t_model'], 1)} | "
                         f"{_fmt(row['coef_dominance'])} | {_fmt(row['t_dominance'], 1)} | {_fmt(row['coef_total'])} | {_fmt(row['t_total'], 1)} | "
                         f"{_fmt(row['r2_with_model'])} | {_fmt(row['r2_without_model'])} | {_fmt(row['pass'])} |")
        L.append("")
        L.append("### Iperparametri e dispersione adottati (scelti sulla stagione precedente)")
        L.append("")
        L.append("| Stagione | Iperparametro | Scelto su | Dispersione per divisione (None = Poisson) |")
        L.append("|---|---|---|---|")
        for s, h in r["hyper_by_season"].items():
            disp = r["dispersion_by_season"].get(s, {})
            disp_txt = ", ".join(f"{c}: {_fmt(a)}" for c, a in disp.items()) or "—"
            L.append(f"| {s} | `{h['hyper']}` | {h['source_season'] or 'default (rodaggio)'} | {disp_txt} |")
        L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    report = run_exam(ADOPTED_CONFIG)
    for stat, r in report["stats"].items():
        print(f"{stat:8s} {r['verdict']:14s} accuratezza={r['accuracy_pass']} calibrazione={r['calibration_pass']} ({r['calibration']['gap']}) oltre_mercato={r['beyond_market_pass']}")
    print(f"tempo totale {report['runtime_seconds']['total']} s; scritto in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
