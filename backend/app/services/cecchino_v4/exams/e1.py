"""Esame E1 del motore gol V4 (docs/v4/PREREGISTRAZIONE_FASE_1.md).

    python -m app.services.cecchino_v4.exams.e1        (da backend/)

Carica lo storico (2021/22 rodaggio, 2022/23-2024/25 giudizio), calcola il
termine di paragone (V3 Fase 4) e le novita' in ablazione nell'ordine
pre-registrato (a, b, c, d, e), adotta ognuna solo se supera la sua regola,
scrive docs/v4/esami/E1.json e E1.md, aggiorna `ADOPTED_CONFIG` in
engine_goals/config.py e stampa il verdetto. Nessuna quota del book entra qui.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.services.cecchino_v3.markets import market_outcomes

from app.services.cecchino_v4.constants import CLASSIC_MARKETS, JUDGE_SEASONS, MARKET_FAMILY, WARMUP_SEASON
from app.services.cecchino_v4.engine_goals.baseline_v3 import run_v3_phase4_full
from app.services.cecchino_v4.engine_goals.cache import matches_digest
from app.services.cecchino_v4.engine_goals.config import LEVEL_HIGH, LEVEL_LOW, LEVEL_MEDIUM, LEVELS, V4GoalsConfig
from app.services.cecchino_v4.engine_goals.engine import MatchRow, V4Run, compute_strength_params, predict_history_full
from app.services.cecchino_v4.history.football_data import History, load_history

DOCS_DIR = Path(__file__).resolve().parents[5] / "docs" / "v4" / "esami"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "engine_goals" / "config.py"
PREREGISTRATION = "docs/v4/PREREGISTRAZIONE_FASE_1.md"

FAMILIES: tuple[str, ...] = ("FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2")
CALIBRATION_FAMILIES: tuple[str, ...] = ("FT_1X2", "FT_OVER_UNDER")
TOLERANCE = 0.001  # +0,1% relativo
MIN_LEVEL_SHARE = 0.15
BINS = 10
_EPS = 1e-6

ADDITIONS: tuple[tuple[str, str, str], ...] = (
    ("a", "team_home_advantage", "vantaggio casa per squadra"),
    ("b", "division_rho", "rho Dixon-Coles per divisione"),
    ("c", "division_dispersion", "binomiale negativa per divisione"),
    ("d", "uncertainty", "incertezza (livelli e intervalli)"),
    ("e", "isotonic_calibration", "calibrazione isotonica per mercato"),
)


# --- misure -----------------------------------------------------------------------------------------


def _family_arrays(rows: dict[int, MatchRow], season: str, family: str, *, baseline: bool = False) -> tuple[np.ndarray, np.ndarray]:
    keys = [k for k in CLASSIC_MARKETS if MARKET_FAMILY[k] == family]
    p: list[float] = []
    y: list[float] = []
    for r in rows.values():
        if r.season != season or not r.eval_eligible:
            continue
        outcomes = market_outcomes(r.ft_home, r.ft_away, r.ht_home, r.ht_away)
        probs = r.baseline_probs if baseline else r.probs
        for k in keys:
            won = outcomes[k]
            if won is None:
                continue
            p.append(probs[k])
            y.append(1.0 if won else 0.0)
    return np.asarray(p, dtype=float), np.asarray(y, dtype=float)


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2)) if p.size else float("nan")


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    q = np.clip(p, _EPS, 1.0 - _EPS)
    return float(-np.mean(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))) if p.size else float("nan")


def calibration_error_pct(p: np.ndarray, y: np.ndarray) -> float:
    if not p.size:
        return float("nan")
    b = np.minimum((p * BINS).astype(int), BINS - 1)
    total = 0.0
    for k in range(BINS):
        sel = b == k
        if sel.any():
            total += sel.sum() * abs(float(p[sel].mean()) - float(y[sel].mean()))
    return total / p.size * 100.0


def metrics_table(rows: dict[int, MatchRow], *, baseline: bool = False) -> dict[str, dict[str, dict[str, float]]]:
    """{famiglia: {stagione: {brier, log_loss, n}}} sulle stagioni di giudizio."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for fam in FAMILIES:
        out[fam] = {}
        for s in JUDGE_SEASONS:
            p, y = _family_arrays(rows, s, fam, baseline=baseline)
            out[fam][s] = {"brier": brier(p, y), "log_loss": log_loss(p, y), "n": int(p.size)}
    return out


def calibration_table(rows: dict[int, MatchRow], *, baseline: bool = False) -> dict[str, float]:
    out: dict[str, float] = {}
    for fam in CALIBRATION_FAMILIES:
        ps, ys = [], []
        for s in JUDGE_SEASONS:
            p, y = _family_arrays(rows, s, fam, baseline=baseline)
            ps.append(p)
            ys.append(y)
        out[fam] = calibration_error_pct(np.concatenate(ps), np.concatenate(ys))
    return out


def excess_brier_by_level(rows: dict[int, MatchRow]) -> dict[str, dict[str, dict[str, float]]]:
    """{stagione: {livello: {excess, share, n}}} sull'1X2 delle partite idonee."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for s in JUDGE_SEASONS:
        acc: dict[str, list[float]] = {lvl: [] for lvl in LEVELS}
        for r in rows.values():
            if r.season != s or not r.eval_eligible:
                continue
            ph, pd, pa = r.probs["HOME"], r.probs["DRAW"], r.probs["AWAY"]
            y = (float(r.ft_home > r.ft_away), float(r.ft_home == r.ft_away), float(r.ft_home < r.ft_away))
            realized = ((ph - y[0]) ** 2 + (pd - y[1]) ** 2 + (pa - y[2]) ** 2) / 3.0
            expected = (1.0 - (ph * ph + pd * pd + pa * pa)) / 3.0
            acc.setdefault(r.level, []).append(realized - expected)
        total = sum(len(v) for v in acc.values())
        out[s] = {
            lvl: {
                "excess": float(np.mean(v)) if v else float("nan"),
                "share": len(v) / total if total else 0.0,
                "n": len(v),
            }
            for lvl, v in acc.items()
        }
    return out


# --- regole ---------------------------------------------------------------------------------------------


def _pct(new: float, ref: float) -> float:
    return (new - ref) / ref * 100.0 if ref else float("nan")


def accuracy_rule(
    new: dict[str, dict[str, dict[str, float]]], ref: dict[str, dict[str, dict[str, float]]]
) -> dict[str, Any]:
    """E1.1 (tolleranza +0,1% in ogni famiglia e stagione) ed E1.2 (media piu' bassa in ogni famiglia)."""
    families: dict[str, Any] = {}
    for fam in FAMILIES:
        seasons = {}
        for s in JUDGE_SEASONS:
            b_new, b_ref = new[fam][s]["brier"], ref[fam][s]["brier"]
            seasons[s] = {
                "brier": b_new,
                "brier_reference": b_ref,
                "change_pct": _pct(b_new, b_ref),
                "log_loss": new[fam][s]["log_loss"],
                "log_loss_reference": ref[fam][s]["log_loss"],
                "passed": bool(b_new <= b_ref * (1.0 + TOLERANCE)),
            }
        mean_new = float(np.mean([new[fam][s]["brier"] for s in JUDGE_SEASONS]))
        mean_ref = float(np.mean([ref[fam][s]["brier"] for s in JUDGE_SEASONS]))
        families[fam] = {
            "seasons": seasons,
            "mean_brier": mean_new,
            "mean_brier_reference": mean_ref,
            "mean_change_pct": _pct(mean_new, mean_ref),
            "e1_1": all(v["passed"] for v in seasons.values()),
            "e1_2": bool(mean_new < mean_ref),
        }
    return {
        "families": families,
        "e1_1": all(f["e1_1"] for f in families.values()),
        "e1_2": all(f["e1_2"] for f in families.values()),
    }


def calibration_rule(new: dict[str, float], ref: dict[str, float]) -> dict[str, Any]:
    fams = {fam: {"error_pct": new[fam], "error_pct_reference": ref[fam], "passed": bool(new[fam] <= ref[fam])} for fam in CALIBRATION_FAMILIES}
    return {"families": fams, "e1_3": all(v["passed"] for v in fams.values())}


def uncertainty_rule(table: dict[str, dict[str, dict[str, float]]]) -> dict[str, Any]:
    seasons: dict[str, Any] = {}
    for s, levels in table.items():
        hi, mid, lo = levels[LEVEL_HIGH]["excess"], levels[LEVEL_MEDIUM]["excess"], levels[LEVEL_LOW]["excess"]
        decreasing = bool(hi > mid > lo) if all(not math.isnan(v) for v in (hi, mid, lo)) else False
        shares_ok = all(levels[lvl]["share"] >= MIN_LEVEL_SHARE for lvl in LEVELS)
        seasons[s] = {"levels": levels, "decreasing": decreasing, "shares_ok": shares_ok, "passed": decreasing and shares_ok}
    return {"seasons": seasons, "e1_4": all(v["passed"] for v in seasons.values())}


# --- esecuzione -------------------------------------------------------------------------------------------


def _run(history: History, cfg: V4GoalsConfig, baseline, params, cache_key: str) -> V4Run:
    return predict_history_full(history, cfg, baseline=baseline, params=params, cache_key=cache_key, compute_intervals=False)


def _step_report(letter: str, name: str, label: str, cfg: V4GoalsConfig, run: V4Run, ref_rows: dict[int, MatchRow]) -> tuple[dict[str, Any], bool]:
    new_m, ref_m = metrics_table(run.rows), metrics_table(ref_rows)
    acc = accuracy_rule(new_m, ref_m)
    report: dict[str, Any] = {
        "step": letter,
        "addition": name,
        "label": label,
        "config": cfg.as_dict(),
        "seconds": run.timings.get("v4_additions"),
        "accuracy_vs_previous": acc,
    }
    if name == "uncertainty":
        unc = uncertainty_rule(excess_brier_by_level(run.rows))
        report["uncertainty"] = unc
        report["season_cuts"] = {s: info["uncertainty_cuts"] for s, info in run.season_info.items()}
        passed = unc["e1_4"]
    else:
        passed = acc["e1_1"] and acc["e1_2"]
        if name == "isotonic_calibration":
            cal = calibration_rule(calibration_table(run.rows), calibration_table(ref_rows))
            report["calibration_vs_previous"] = cal
            passed = passed and cal["e1_3"]
    if name == "division_dispersion":
        report["dispersion_by_season"] = {s: info["dispersion"] for s, info in run.season_info.items()}
    report["adopted"] = bool(passed)
    return report, bool(passed)


def _write_adopted_config(cfg: V4GoalsConfig) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    body = json.dumps(cfg.as_dict(), indent=4, ensure_ascii=False)
    body = body.replace("true", "True").replace("false", "False")
    new = re.sub(r"ADOPTED_CONFIG: dict\[str, Any\] = \{.*?\n\}\n", f"ADOPTED_CONFIG: dict[str, Any] = {body}\n", text, flags=re.S)
    if new == text and body not in text:
        raise RuntimeError("blocco ADOPTED_CONFIG non trovato in config.py")
    CONFIG_PATH.write_text(new, encoding="utf-8")


def _fmt(v: float | None, nd: int = 5) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/d"
    return f"{v:.{nd}f}".replace(".", ",")


def _pct_fmt(v: float) -> str:
    return ("+" if v >= 0 else "") + f"{v:.3f}".replace(".", ",") + "%"


def _markdown(result: dict[str, Any]) -> str:
    L: list[str] = []
    verdict = "SUPERATO" if result["passed"] else "NON SUPERATO"
    L.append("# Esame E1: motore gol V4 contro V3 Fase 4")
    L.append("")
    L.append(f"Calcolato il {result['computed_at']} in {result['runtime_seconds']:.0f} secondi. Pre-registrazione: `{PREREGISTRATION}`. Verdetto: **{verdict}**.")
    L.append("")
    L.append(f"Partite: {result['matches']} (idonee {result['eligible']}), stagioni di giudizio {', '.join(JUDGE_SEASONS)}, rodaggio {WARMUP_SEASON}.")
    L.append("")
    L.append("## Ablazione (ogni novita' sopra la configurazione adottata fino a quel momento)")
    L.append("")
    L.append("| Passo | Novita' | Esito | 1X2 media | Doppia chance media | Over/Under media | 1X2 primo tempo media |")
    L.append("|---|---|---|---|---|---|---|")
    for st in result["ablation"]:
        fams = st["accuracy_vs_previous"]["families"]
        cells = [_pct_fmt(fams[f]["mean_change_pct"]) for f in FAMILIES]
        esito = "adottata" if st["adopted"] else "non adottata"
        if st["addition"] == "uncertainty":
            esito += " (E1.4 " + ("ok" if st["uncertainty"]["e1_4"] else "fallito") + ")"
        L.append(f"| {st['step']} | {st['label']} | {esito} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("Le variazioni sono di Brier medio sulle tre stagioni di giudizio rispetto alla configurazione precedente (negativo = meglio).")
    L.append("")
    L.append("## Configurazione adottata contro V3 Fase 4")
    L.append("")
    L.append("| Famiglia | Stagione | Brier V3 | Brier V4 | Variazione | Log-loss V3 | Log-loss V4 | E1.1 |")
    L.append("|---|---|---|---|---|---|---|---|")
    fams = result["final"]["accuracy"]["families"]
    for f in FAMILIES:
        for s in JUDGE_SEASONS:
            r = fams[f]["seasons"][s]
            L.append(
                f"| {f} | {s} | {_fmt(r['brier_reference'])} | {_fmt(r['brier'])} | {_pct_fmt(r['change_pct'])} | "
                f"{_fmt(r['log_loss_reference'])} | {_fmt(r['log_loss'])} | {'ok' if r['passed'] else 'no'} |"
            )
        L.append(f"| {f} | media | {_fmt(fams[f]['mean_brier_reference'])} | {_fmt(fams[f]['mean_brier'])} | {_pct_fmt(fams[f]['mean_change_pct'])} | | | E1.2 {'ok' if fams[f]['e1_2'] else 'no'} |")
    L.append("")
    cal = result["final"]["calibration"]["families"]
    L.append("## Calibrazione (stagioni di giudizio insieme, punti percentuali)")
    L.append("")
    L.append("| Famiglia | V3 | V4 | E1.3 |")
    L.append("|---|---|---|---|")
    for f in CALIBRATION_FAMILIES:
        L.append(f"| {f} | {_fmt(cal[f]['error_pct_reference'], 3)} | {_fmt(cal[f]['error_pct'], 3)} | {'ok' if cal[f]['passed'] else 'no'} |")
    L.append("")
    L.append("## Incertezza: errore in eccesso 1X2 per livello (E1.4)")
    L.append("")
    L.append("| Stagione | Alta | Media | Bassa | Quote alta/media/bassa | Decrescente | Quote >= 15% |")
    L.append("|---|---|---|---|---|---|---|")
    for s, r in result["final"]["uncertainty"]["seasons"].items():
        lv = r["levels"]
        L.append(
            f"| {s} | {_fmt(lv[LEVEL_HIGH]['excess'])} | {_fmt(lv[LEVEL_MEDIUM]['excess'])} | {_fmt(lv[LEVEL_LOW]['excess'])} | "
            f"{lv[LEVEL_HIGH]['share']*100:.0f}% / {lv[LEVEL_MEDIUM]['share']*100:.0f}% / {lv[LEVEL_LOW]['share']*100:.0f}% | "
            f"{'si' if r['decreasing'] else 'no'} | {'si' if r['shares_ok'] else 'no'} |"
        )
    L.append("")
    L.append("## Criteri")
    L.append("")
    for code, ok in result["criteria"].items():
        L.append(f"- {code}: {'superato' if ok else 'non superato'}")
    L.append("")
    L.append("## Configurazione adottata")
    L.append("")
    L.append("```json")
    L.append(json.dumps(result["adopted_config"], indent=2, ensure_ascii=False))
    L.append("```")
    L.append("")
    L.append("Iperparametri Forza scelti per stagione: " + ", ".join(f"{s}: {k}" for s, k in result["chosen_hyper_forza"].items()) + ".")
    L.append("")
    if result.get("deviations"):
        L.append("## Scostamenti dalla pre-registrazione")
        L.append("")
        for d in result["deviations"]:
            L.append(f"- {d}")
        L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    t0 = time.monotonic()
    history = load_history()
    matches = history.matches
    cache_key = "full_" + matches_digest(matches)
    print(f"[E1] {len(matches)} partite, {sum(m.eval_eligible for m in matches)} idonee")

    baseline = run_v3_phase4_full(matches, cache_key=cache_key)
    print(f"[E1] termine di paragone V3 Fase 4 pronto ({baseline.timings})")
    hypers = set(baseline.chosen_forza.values()) | {baseline.next_forza}
    params = compute_strength_params(matches, hypers, cache_key=cache_key)
    print("[E1] parametri Forza per giorno pronti")

    current = V4GoalsConfig()
    ref_run = _run(history, current, baseline, params, cache_key)
    # controllo di identita' con il termine di paragone
    max_diff = max(
        abs(r.probs[k] - r.baseline_probs[k]) for r in ref_run.rows.values() for k in r.baseline_probs
    )
    print(f"[E1] V4 spenta = V3 Fase 4: differenza massima {max_diff:.2e}")
    ablation: list[dict[str, Any]] = []
    for letter, name, label in ADDITIONS:
        cfg = current.with_(**{name: True})
        run = _run(history, cfg, baseline, params, cache_key)
        report, adopted = _step_report(letter, name, label, cfg, run, ref_run.rows)
        ablation.append(report)
        print(f"[E1] {letter}. {label}: {'adottata' if adopted else 'non adottata'}")
        if adopted:
            current, ref_run = cfg, run

    final_cfg = current.with_(live_hyper_xi=baseline.next_forza.xi, live_hyper_sigma=baseline.next_forza.sigma)
    final_run = ref_run
    base_m = metrics_table(final_run.rows, baseline=True)
    acc = accuracy_rule(metrics_table(final_run.rows), base_m)
    cal = calibration_rule(calibration_table(final_run.rows), calibration_table(final_run.rows, baseline=True))
    unc = uncertainty_rule(excess_brier_by_level(final_run.rows))
    criteria = {"E1.1": acc["e1_1"], "E1.2": acc["e1_2"], "E1.3": cal["e1_3"], "E1.4": unc["e1_4"]}
    passed = all(criteria.values())

    result: dict[str, Any] = {
        "code": "E1",
        "title": "Motore gol V4 contro V3 Fase 4",
        "preregistration": PREREGISTRATION,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_seconds": round(time.monotonic() - t0, 1),
        "matches": len(matches),
        "eligible": int(sum(m.eval_eligible for m in matches)),
        "baseline_identity_max_diff": max_diff,
        "chosen_hyper_forza": {s: h.key for s, h in baseline.chosen_forza.items()},
        "chosen_hyper_game": {stat: {s: h.key for s, h in ch.items()} for stat, ch in baseline.chosen_game.items()},
        "next_season": {
            "season": baseline.next_season,
            "hyper_forza": baseline.next_forza.key,
            "hyper_game": {k: v.key for k, v in baseline.next_game.items()},
            "final_weights": baseline.next_final_weights,
            "dispersion": {k: list(v) for k, v in final_run.artifacts.dispersion.items()},
            "uncertainty_cuts": list(final_run.artifacts.uncertainty_cuts),
            "calibration_applied": final_run.artifacts.calibration_applied,
        },
        "orchestrator_weights": baseline.final_weights,
        "ablation": ablation,
        "final": {"accuracy": acc, "calibration": cal, "uncertainty": unc, "season_info": final_run.season_info},
        "criteria": criteria,
        "passed": passed,
        "adopted_config": final_cfg.as_dict(),
        "deviations": [
            "Le squadre con evidenza zero (mai viste nella piramide) ricevono livello di incertezza 'alta' "
            "indipendentemente dai tagli, come previsto per il live (sezione 7): nessuna di queste partite e' "
            "idonea, quindi E1.4 non ne risente.",
            "Il verdetto usa la configurazione adottata dall'ablazione; poiche' nessuna novita' che cambia le "
            "probabilita' e' stata adottata, E1.2 non puo' passare (sezione 6).",
        ],
        "timings": {"baseline": baseline.timings, "final_run": final_run.timings},
    }
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "E1.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    (DOCS_DIR / "E1.md").write_text(_markdown(result), encoding="utf-8")
    _write_adopted_config(final_cfg)
    print(f"[E1] criteri: {criteria}")
    print(f"[E1] configurazione adottata: {final_cfg.as_dict()}")
    print(f"[E1] VERDETTO: {'SUPERATO' if passed else 'NON SUPERATO'} in {result['runtime_seconds']} s")
    return 0 if passed else 1


def _json_default(o: Any) -> Any:
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return str(o)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
