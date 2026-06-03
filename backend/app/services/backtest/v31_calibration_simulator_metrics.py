"""Metriche regressione e betting per simulatore v3.1."""

from __future__ import annotations

import math
from typing import Any

STRATEGY_VERDICT_LABELS = {
    "weak": "Debole",
    "promising": "Promettente",
    "solid": "Solida",
    "v31_candidate": "Candidata v3.1",
}


def _round1(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 1)


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 4)


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return _round4(sum(vals) / len(vals))


def _hit_rate(wins: int, losses: int) -> float | None:
    t = wins + losses
    if t <= 0:
        return None
    return _round1(100.0 * wins / t)


def regression_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errs: list[float] = []
    signed: list[float] = []
    for r in rows:
        pred = r.get("predicted_total_sot")
        actual = r.get("actual_total_sot")
        if pred is None or actual is None:
            continue
        e = float(pred) - float(actual)
        signed.append(e)
        errs.append(abs(e))
    if not errs:
        return {"mae": None, "bias": None, "rmse": None, "n": 0}
    mse = sum(e * e for e in signed) / len(signed)
    return {
        "mae": _round4(sum(errs) / len(errs)),
        "bias": _round4(sum(signed) / len(signed)),
        "rmse": _round4(math.sqrt(mse)),
        "n": len(errs),
    }


def _picks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("decision") == "GIOCA" and r.get("selected_line") is not None]


def _betting_summary(picks: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for p in picks if p.get("outcome") == "WIN")
    losses = sum(1 for p in picks if p.get("outcome") == "LOSS")
    return {
        "pick_count": len(picks),
        "win_count": wins,
        "loss_count": losses,
        "hit_rate": _hit_rate(wins, losses),
    }


def _hit_for_line(picks: list[dict[str, Any]], line: float) -> float | None:
    sub = [p for p in picks if p.get("selected_line") is not None and float(p["selected_line"]) == line]
    w = sum(1 for p in sub if p.get("outcome") == "WIN")
    l = sum(1 for p in sub if p.get("outcome") == "LOSS")
    return _hit_rate(w, l)


def betting_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    picks = _picks(rows)
    no_bet = sum(1 for r in rows if r.get("decision") in ("NO_BET", "BORDERLINE"))
    borderline = sum(1 for r in rows if r.get("decision") == "BORDERLINE")
    summary = _betting_summary(picks)
    by_tier: dict[str, Any] = {}
    for tier in ("high", "medium", "low"):
        sub = [p for p in picks if p.get("confidence_tier") == tier]
        by_tier[tier] = _betting_summary(sub)

    by_block: dict[str, Any] = {}
    for name, lo, hi in (
        ("rounds_5_15", 5, 15),
        ("rounds_16_26", 16, 26),
        ("rounds_27_37", 27, 37),
    ):
        sub = [r for r in rows if lo <= int(r.get("round_number") or 0) <= hi]
        by_block[name] = {
            "regression": regression_metrics(sub),
            "betting": {**_betting_summary(_picks(sub)), "fixture_count": len(sub)},
        }

    return {
        **summary,
        "no_bet_count": no_bet,
        "borderline_count": borderline,
        "hit_rate_over_6_5": _hit_for_line(picks, 6.5),
        "hit_rate_over_7_5": _hit_for_line(picks, 7.5),
        "hit_rate_over_8_5": _hit_for_line(picks, 8.5),
        "by_confidence_tier": by_tier,
        "by_round_block": by_block,
    }


def line_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    picks = _picks(rows)
    acc: dict[str, dict[str, int]] = {}
    for p in picks:
        ln = str(float(p["selected_line"]))
        cell = acc.setdefault(ln, {"wins": 0, "losses": 0, "picks": 0})
        cell["picks"] += 1
        if p.get("outcome") == "WIN":
            cell["wins"] += 1
        elif p.get("outcome") == "LOSS":
            cell["losses"] += 1
    out: dict[str, Any] = {}
    for ln, cell in sorted(acc.items(), key=lambda x: float(x[0])):
        out[ln] = {**cell, "hit_rate": _hit_rate(cell["wins"], cell["losses"])}
    return out


def confidence_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return betting_metrics(rows).get("by_confidence_tier") or {}


def walk_forward_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def _wf(train_lo: int, train_hi: int, test_lo: int, test_hi: int, name: str) -> dict[str, Any]:
        test_rows = [r for r in rows if test_lo <= int(r.get("round_number") or 0) <= test_hi]
        train_rows = [r for r in rows if train_lo <= int(r.get("round_number") or 0) <= train_hi]
        return {
            "name": name,
            "train_rounds": f"{train_lo}-{train_hi}",
            "test_rounds": f"{test_lo}-{test_hi}",
            "train_fixture_count": len(train_rows),
            "test_fixture_count": len(test_rows),
            "test_regression": regression_metrics(test_rows),
            "test_betting": _betting_summary(_picks(test_rows)),
        }

    return {
        "wf_5_15_to_16_26": _wf(5, 15, 16, 26, "wf_5_15_to_16_26"),
        "wf_5_26_to_27_37": _wf(5, 26, 27, 37, "wf_5_26_to_27_37"),
    }


def reason_code_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        for code in r.get("reason_codes") or []:
            counts[str(code)] = counts.get(str(code), 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def compute_strategy_verdict(
    *,
    mae: float | None,
    hit_rate: float | None,
    pick_count: int,
    best_mae: float | None,
) -> str:
    if pick_count < 5:
        return "weak"
    if mae is not None and best_mae is not None and mae <= best_mae * 1.02 and hit_rate is not None and hit_rate >= 55.0:
        return "v31_candidate"
    if hit_rate is not None and hit_rate >= 58.0 and pick_count >= 15:
        return "solid"
    if hit_rate is not None and hit_rate >= 52.0:
        return "promising"
    return "weak"


def balanced_score(hit_rate: float | None, mae: float | None, lam: float = 2.0) -> float | None:
    if hit_rate is None or mae is None:
        return None
    return _round4(float(hit_rate) - lam * float(mae))


def summarize_strategy(
    strategy_key: str,
    rows: list[dict[str, Any]],
    *,
    best_mae: float | None,
) -> dict[str, Any]:
    reg = regression_metrics(rows)
    bet = betting_metrics(rows)
    picks = _picks(rows)
    verdict = compute_strategy_verdict(
        mae=reg.get("mae"),
        hit_rate=bet.get("hit_rate"),
        pick_count=bet.get("pick_count", 0),
        best_mae=best_mae,
    )
    return {
        "key": strategy_key,
        "regression_metrics": reg,
        "betting_metrics": bet,
        "walk_forward_metrics": walk_forward_metrics(rows),
        "line_metrics": line_metrics(rows),
        "confidence_metrics": confidence_metrics(rows),
        "reason_code_counts": reason_code_counts(rows),
        "verdict": verdict,
        "verdict_label": STRATEGY_VERDICT_LABELS.get(verdict, verdict),
        "metrics": {
            "mae": reg.get("mae"),
            "bias": reg.get("bias"),
            "rmse": reg.get("rmse"),
            "pick_count": bet.get("pick_count"),
            "no_bet_count": bet.get("no_bet_count"),
            "win_count": bet.get("win_count"),
            "loss_count": bet.get("loss_count"),
            "hit_rate": bet.get("hit_rate"),
            "hit_rate_over_6_5": bet.get("hit_rate_over_6_5"),
            "hit_rate_over_7_5": bet.get("hit_rate_over_7_5"),
        },
    }


def compute_best_by(strategy_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    best_mae_key = None
    best_mae_val = None
    best_hr_key = None
    best_hr_val = None
    best_bal_key = None
    best_bal_val = None
    cons_proxy = None

    for block in strategy_blocks:
        key = block["key"]
        m = block.get("metrics") or {}
        mae = m.get("mae")
        hr = m.get("hit_rate")
        if mae is not None and (best_mae_val is None or mae < best_mae_val):
            best_mae_val = mae
            best_mae_key = key
        if hr is not None and (best_hr_val is None or hr > best_hr_val):
            best_hr_val = hr
            best_hr_key = key
        bs = balanced_score(hr, mae)
        if bs is not None and (best_bal_val is None or bs > best_bal_val):
            best_bal_val = bs
            best_bal_key = key
        if key == "v31_conservative_selector":
            w = m.get("win_count") or 0
            l = m.get("loss_count") or 0
            cons_proxy = {"strategy": key, "wins_minus_losses": w - l}

    recommended = best_bal_key or best_hr_key or best_mae_key
    return {
        "mae": {"strategy": best_mae_key, "value": best_mae_val},
        "hit_rate": {"strategy": best_hr_key, "value": best_hr_val},
        "balanced_score": {"strategy": best_bal_key, "value": best_bal_val},
        "conservative_profit_proxy": cons_proxy,
        "recommended_strategy": recommended,
    }
