"""Aggregazione diagnostica pura su righe fixture×modello (Step V3.0-A)."""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.schemas.backtest_round_analysis import MODEL_LABELS
from app.services.backtest.round_analysis_calibration_export import extract_v21_calibration_fields
from app.services.backtest.round_analysis_mode_stats import advice_bucket, count_play_mode, is_advised_label
from app.services.backtest.sot_pick_evaluation_logic import DEFAULT_PICK_LINES, compute_pick_outcome

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V20 = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

SOT_BUCKETS = ("low_total", "medium_total", "high_total")
EDGE_BUCKETS = ("edge_low", "edge_medium", "edge_high")
MACRO_BUCKET_KEYS = ("low", "neutral", "high")
RISK_BUCKETS = ("low", "medium", "high")

from app.services.backtest.round_analysis_v21_trace_helpers import (
    V21_MACRO_AVG_KEYS,
    extract_v21_macro_averages,
    extract_v21_split_status,
    split_status_summary,
)


def _round1(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 1)


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _hit_rate(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return _round1(100.0 * wins / total)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return _round4(sum(values) / len(values))


def diagnostics_actual_total_bucket(actual: int | None) -> str | None:
    if actual is None:
        return None
    if actual <= 6:
        return "low_total"
    if actual <= 9:
        return "medium_total"
    return "high_total"


def diagnostics_predicted_total_bucket(predicted: float | None) -> str | None:
    if predicted is None:
        return None
    p = float(predicted)
    if p <= 6:
        return "low_total"
    if p <= 9:
        return "medium_total"
    return "high_total"


def macro_value_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    v = float(value)
    if v < 0.90:
        return "low"
    if v <= 1.10:
        return "neutral"
    return "high"


def edge_value_bucket(edge: float | None) -> str | None:
    if edge is None:
        return None
    e = float(edge)
    if e < 0.50:
        return "edge_low"
    if e < 1.00:
        return "edge_medium"
    return "edge_high"


def _macro_index(side_data: dict[str, Any] | None, macro_key: str) -> float | None:
    from app.services.backtest.round_analysis_v21_trace_helpers import macro_index as _mi

    return _mi(side_data, macro_key)


def _split_partial_low_sample(explanation_slice: dict[str, Any] | None) -> bool:
    return extract_v21_split_status(explanation_slice) == "partial_low_sample"


def compute_low_total_risk_score(row: dict[str, Any]) -> float:
    block = row.get("block") or {}
    score = 0.0
    pt = block.get("predicted_total_sot")
    if pt is not None and 7.0 <= float(pt) <= 9.0:
        score += 1.5
    macros = extract_v21_macro_averages(row.get("explanation_v21"))
    for key in ("pace_control_avg", "chance_quality_avg", "offensive_production_avg"):
        v = macros.get(key)
        if v is not None and v < 0.95:
            score += 1.0
    if _split_partial_low_sample(row.get("explanation_v21")):
        score += 1.0
    if block.get("confidence") == "low":
        score += 1.0
    if block.get("sample_bucket") == "early_low_sample":
        score += 1.0
    warnings = block.get("warnings") or []
    if len(warnings) >= 4:
        score += 0.5
    pl = macros.get("player_layer_avg")
    if pl is not None and pl < 1.0:
        score += 0.5
    lu = macros.get("lineups_avg")
    if lu is not None and lu < 1.0:
        score += 0.5
    return score


def low_total_risk_bucket(score: float) -> str:
    if score < 2.0:
        return "low"
    if score < 4.0:
        return "medium"
    return "high"


def _mode_outcome_stats(
    rows: list[dict[str, Any]],
    mode: str,
    *,
    advised_only: bool = False,
) -> dict[str, Any]:
    wins = losses = 0
    for row in rows:
        block = row.get("block") or {}
        outcome = block.get(f"{mode}_outcome")
        if outcome not in ("WIN", "LOSS"):
            continue
        if advised_only:
            advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
            if advice != "GIOCA":
                continue
        if outcome == "WIN":
            wins += 1
        else:
            losses += 1
    hr = _hit_rate(wins, losses)
    return {"wins": wins, "losses": losses, "hit_rate": hr, "plays": wins + losses}


def _empty_sot_bucket() -> dict[str, Any]:
    return {
        "fixtures": 0,
        "avg_predicted_total": None,
        "avg_actual_total": None,
        "mae": None,
        "bias": None,
        "aggressive": {"wins": 0, "losses": 0, "hit_rate": None},
        "cautious": {"wins": 0, "losses": 0, "hit_rate": None},
        "advised_aggressive": {"wins": 0, "losses": 0, "hit_rate": None},
        "advised_cautious": {"wins": 0, "losses": 0, "hit_rate": None},
    }


def build_sot_bucket_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    acc: dict[str, dict[str, Any]] = {b: _empty_sot_bucket() for b in SOT_BUCKETS}
    for row in rows:
        bucket = diagnostics_actual_total_bucket(row.get("actual_total_sot"))
        if bucket is None or bucket not in acc:
            continue
        block = row.get("block") or {}
        pt = block.get("predicted_total_sot")
        at = row.get("actual_total_sot")
        cell = acc[bucket]
        cell["fixtures"] += 1
        if pt is not None and at is not None:
            cell.setdefault("_preds", []).append(float(pt))
            cell.setdefault("_acts", []).append(float(at))
            cell.setdefault("_abs_errs", []).append(abs(float(pt) - float(at)))
            cell.setdefault("_signed_errs", []).append(float(pt) - float(at))
        for mode, adv_key in (("aggressive", "advised_aggressive"), ("cautious", "advised_cautious")):
            outcome = block.get(f"{mode}_outcome")
            if outcome not in ("WIN", "LOSS"):
                continue
            target = cell[mode]
            if outcome == "WIN":
                target["wins"] += 1
            else:
                target["losses"] += 1
            advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
            if advice == "GIOCA":
                adv = cell[adv_key]
                if outcome == "WIN":
                    adv["wins"] += 1
                else:
                    adv["losses"] += 1

    out: dict[str, Any] = {}
    for bucket, cell in acc.items():
        cell["avg_predicted_total"] = _mean(cell.pop("_preds", []))
        cell["avg_actual_total"] = _mean(cell.pop("_acts", []))
        cell["mae"] = _mean(cell.pop("_abs_errs", []))
        cell["bias"] = _mean(cell.pop("_signed_errs", []))
        for key in ("aggressive", "cautious", "advised_aggressive", "advised_cautious"):
            w, l = cell[key]["wins"], cell[key]["losses"]
            cell[key]["hit_rate"] = _hit_rate(w, l)
            cell[key]["plays"] = w + l
        out[bucket] = cell
    return out


def build_line_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lines_out: dict[str, Any] = {"aggressive": {}, "cautious": {}}
    for line in DEFAULT_PICK_LINES:
        line_key = str(line)
        for mode in ("aggressive", "cautious"):
            calc_w = calc_l = adv_w = adv_l = 0
            edges: list[float] = []
            preds: list[float] = []
            acts: list[float] = []
            for row in rows:
                block = row.get("block") or {}
                pt = block.get("predicted_total_sot")
                at = row.get("actual_total_sot")
                if pt is None or at is None:
                    continue
                outcome = compute_pick_outcome(line, int(at))
                edge = float(pt) - line
                calc_w += 1 if outcome == "win" else 0
                calc_l += 0 if outcome == "win" else 1
                edges.append(edge)
                preds.append(float(pt))
                acts.append(float(at))
                stored_line = block.get(f"{mode}_line")
                advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
                if stored_line is not None and float(stored_line) == float(line) and advice == "GIOCA":
                    if outcome == "win":
                        adv_w += 1
                    else:
                        adv_l += 1
            lines_out[mode][line_key] = {
                "line": line,
                "calculated_all": {
                    "plays": calc_w + calc_l,
                    "wins": calc_w,
                    "losses": calc_l,
                    "hit_rate": _hit_rate(calc_w, calc_l),
                    "avg_edge": _mean(edges),
                    "avg_predicted_total": _mean(preds),
                    "avg_actual_total": _mean(acts),
                },
                "advised_only": {
                    "plays": adv_w + adv_l,
                    "wins": adv_w,
                    "losses": adv_l,
                    "hit_rate": _hit_rate(adv_w, adv_l),
                },
            }
    return lines_out


def build_edge_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"aggressive": {}, "cautious": {}}
    for mode in ("aggressive", "cautious"):
        acc = {b: {"plays": 0, "wins": 0, "losses": 0, "hit_rate": None} for b in EDGE_BUCKETS}
        for row in rows:
            block = row.get("block") or {}
            edge = block.get(f"{mode}_edge")
            outcome = block.get(f"{mode}_outcome")
            if outcome not in ("WIN", "LOSS"):
                continue
            bucket = edge_value_bucket(edge)
            if bucket is None:
                continue
            cell = acc[bucket]
            cell["plays"] += 1
            if outcome == "WIN":
                cell["wins"] += 1
            else:
                cell["losses"] += 1
        for bucket, cell in acc.items():
            cell["hit_rate"] = _hit_rate(cell["wins"], cell["losses"])
        out[mode] = acc
    return out


def build_advice_diagnostic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in ("aggressive", "cautious"):
        advised_w = advised_l = 0
        no_play_w = no_play_l = 0
        for row in rows:
            block = row.get("block") or {}
            advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
            outcome = block.get(f"{mode}_outcome")
            if outcome not in ("WIN", "LOSS"):
                continue
            if advice == "GIOCA":
                if outcome == "WIN":
                    advised_w += 1
                else:
                    advised_l += 1
            elif advice in ("NON GIOCARE", "BORDERLINE"):
                if outcome == "WIN":
                    no_play_w += 1
                else:
                    no_play_l += 1
        out[mode] = {
            "advised_play_wins": advised_w,
            "advised_play_losses": advised_l,
            "advised_play_hit_rate": _hit_rate(advised_w, advised_l),
            "no_play_would_have_won": no_play_w,
            "no_play_would_have_lost": no_play_l,
            "avoided_losses": no_play_l,
            "missed_wins": no_play_w,
        }
    return out


def build_model_overview(rows: list[dict[str, Any]], model_key: str) -> dict[str, Any]:
    abs_errs: list[float] = []
    signed_errs: list[float] = []
    for row in rows:
        block = row.get("block") or {}
        pt = block.get("predicted_total_sot")
        at = row.get("actual_total_sot")
        if pt is not None and at is not None:
            err = float(pt) - float(at)
            abs_errs.append(abs(err))
            signed_errs.append(err)
    agg_acc = {"w": 0, "l": 0}
    caut_acc = {"w": 0, "l": 0}
    for row in rows:
        block = row.get("block") or {}
        a = count_play_mode(block, "aggressive")
        c = count_play_mode(block, "cautious")
        agg_acc["w"] += int((a.get("advised") or {}).get("wins") or 0)
        agg_acc["l"] += int((a.get("advised") or {}).get("losses") or 0)
        caut_acc["w"] += int((c.get("advised") or {}).get("wins") or 0)
        caut_acc["l"] += int((c.get("advised") or {}).get("losses") or 0)
    sot = build_sot_bucket_breakdown(rows)
    return {
        "model_key": model_key,
        "label": MODEL_LABELS.get(model_key, model_key),
        "fixtures": len(rows),
        "mae": _mean(abs_errs),
        "bias": _mean(signed_errs),
        "cautious_advised": {
            "wins": caut_acc["w"],
            "losses": caut_acc["l"],
            "hit_rate": _hit_rate(caut_acc["w"], caut_acc["l"]),
            "display": f"{caut_acc['w']}/{caut_acc['w'] + caut_acc['l']}",
        },
        "aggressive_advised": {
            "wins": agg_acc["w"],
            "losses": agg_acc["l"],
            "hit_rate": _hit_rate(agg_acc["w"], agg_acc["l"]),
            "display": f"{agg_acc['w']}/{agg_acc['w'] + agg_acc['l']}",
        },
        "sot_buckets_summary": {
            b: {"hit_rate_cautious_advised": sot[b]["advised_cautious"]["hit_rate"], "mae": sot[b]["mae"]}
            for b in SOT_BUCKETS
        },
    }


def build_model_diagnostics(rows: list[dict[str, Any]], model_key: str) -> dict[str, Any]:
    return {
        "overview": build_model_overview(rows, model_key),
        "sot_buckets": build_sot_bucket_breakdown(rows),
        "lines": build_line_breakdown(rows),
        "edge_buckets": build_edge_breakdown(rows),
        "advice_diagnostic": build_advice_diagnostic(rows),
    }


def _empty_macro_bucket_cell() -> dict[str, Any]:
    return {
        "fixtures": 0,
        "avg_predicted_total": None,
        "avg_actual_total": None,
        "mae": None,
        "bias": None,
        "aggressive_hit_rate": None,
        "cautious_hit_rate": None,
    }


def build_v21_macro_diagnostics(v21_rows: list[dict[str, Any]]) -> dict[str, Any]:
    macro_buckets: dict[str, dict[str, dict[str, Any]]] = {
        mk: {b: _empty_macro_bucket_cell() for b in MACRO_BUCKET_KEYS} for mk in V21_MACRO_AVG_KEYS
    }
    for row in v21_rows:
        block = row.get("block") or {}
        pt = block.get("predicted_total_sot")
        at = row.get("actual_total_sot")
        macros = extract_v21_macro_averages(row.get("explanation_v21"))
        for mk, avg_val in macros.items():
            bucket = macro_value_bucket(avg_val)
            if bucket is None:
                continue
            cell = macro_buckets[mk][bucket]
            cell["fixtures"] += 1
            if pt is not None and at is not None:
                cell.setdefault("_preds", []).append(float(pt))
                cell.setdefault("_acts", []).append(float(at))
                cell.setdefault("_abs_errs", []).append(abs(float(pt) - float(at)))
                cell.setdefault("_signed_errs", []).append(float(pt) - float(at))
            for mode, hr_key in (("aggressive", "aggressive_hit_rate"), ("cautious", "cautious_hit_rate")):
                outcome = block.get(f"{mode}_outcome")
                advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
                if outcome in ("WIN", "LOSS") and advice == "GIOCA":
                    cell.setdefault(f"_{mode}_w", 0)
                    cell.setdefault(f"_{mode}_l", 0)
                    if outcome == "WIN":
                        cell[f"_{mode}_w"] += 1
                    else:
                        cell[f"_{mode}_l"] += 1

    for mk, buckets in macro_buckets.items():
        for bucket, cell in buckets.items():
            cell["avg_predicted_total"] = _mean(cell.pop("_preds", []))
            cell["avg_actual_total"] = _mean(cell.pop("_acts", []))
            cell["mae"] = _mean(cell.pop("_abs_errs", []))
            cell["bias"] = _mean(cell.pop("_signed_errs", []))
            for mode in ("aggressive", "cautious"):
                w = cell.pop(f"_{mode}_w", 0)
                l = cell.pop(f"_{mode}_l", 0)
                cell[f"{mode}_hit_rate"] = _hit_rate(w, l)
    return macro_buckets


def build_low_total_risk_diagnostic(v21_rows: list[dict[str, Any]]) -> dict[str, Any]:
    acc: dict[str, dict[str, Any]] = {
        b: {"fixtures": 0, "actual_low_total_rate": None, "aggressive_hit_rate": None, "cautious_hit_rate": None, "avg_error": None}
        for b in RISK_BUCKETS
    }
    for row in v21_rows:
        score = compute_low_total_risk_score(row)
        bucket = low_total_risk_bucket(score)
        cell = acc[bucket]
        cell["fixtures"] += 1
        at = row.get("actual_total_sot")
        if at is not None and at <= 6:
            cell.setdefault("_low_count", 0)
            cell["_low_count"] += 1
        block = row.get("block") or {}
        pt = block.get("predicted_total_sot")
        if pt is not None and at is not None:
            cell.setdefault("_errs", []).append(abs(float(pt) - float(at)))
        for mode in ("aggressive", "cautious"):
            outcome = block.get(f"{mode}_outcome")
            advice = advice_bucket(str(block.get(f"{mode}_advice") or ""))
            if outcome in ("WIN", "LOSS") and advice == "GIOCA":
                cell.setdefault(f"_{mode}_w", 0)
                cell.setdefault(f"_{mode}_l", 0)
                if outcome == "WIN":
                    cell[f"_{mode}_w"] += 1
                else:
                    cell[f"_{mode}_l"] += 1

    for bucket, cell in acc.items():
        fx = cell["fixtures"]
        low_c = cell.pop("_low_count", 0)
        cell["actual_low_total_rate"] = _round1(100.0 * low_c / fx) if fx > 0 else None
        cell["avg_error"] = _mean(cell.pop("_errs", []))
        for mode in ("aggressive", "cautious"):
            w = cell.pop(f"_{mode}_w", 0)
            l = cell.pop(f"_{mode}_l", 0)
            cell[f"{mode}_hit_rate"] = _hit_rate(w, l)
    return acc


def _block_pick_summary(block: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    return {
        "predicted_total_sot": block.get("predicted_total_sot"),
        "aggressive_line": block.get("aggressive_line"),
        "aggressive_outcome": block.get("aggressive_outcome"),
        "aggressive_advice": block.get("aggressive_advice"),
        "cautious_line": block.get("cautious_line"),
        "cautious_outcome": block.get("cautious_outcome"),
        "cautious_advice": block.get("cautious_advice"),
    }


def _fixture_models_index(flat_rows: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, dict[str, Any]]]:
    idx: dict[tuple[int, int], dict[str, Any]] = {}
    for row in flat_rows:
        key = (int(row["analysis_id"]), int(row["fixture_id"]))
        if key not in idx:
            idx[key] = {
                "analysis_id": row["analysis_id"],
                "round_number": row["round_number"],
                "fixture_id": row["fixture_id"],
                "match": row["match"],
                "actual_total_sot": row["actual_total_sot"],
                "models": {},
                "explanation_v21": None,
            }
        idx[key]["models"][row["model_key"]] = row.get("block") or {}
        if row["model_key"] == V21:
            idx[key]["explanation_v21"] = row.get("explanation_v21")
    return idx


def _critical_match_base(entry: dict[str, Any]) -> dict[str, Any]:
    models = entry.get("models") or {}
    v21_expl = entry.get("explanation_v21")
    v21_macros = extract_v21_macro_averages(v21_expl) if v21_expl else {}
    v21_block = models.get(V21) or {}
    return {
        "category": "",
        "round_number": entry["round_number"],
        "analysis_id": entry["analysis_id"],
        "fixture_id": entry["fixture_id"],
        "match": entry["match"],
        "actual_total_sot": entry["actual_total_sot"],
        "v1_1": _block_pick_summary(models.get(V11)),
        "v2_0": _block_pick_summary(models.get(V20)),
        "v2_1": _block_pick_summary(models.get(V21)),
        "v21_macros": v21_macros,
        "warnings": list(v21_block.get("warnings") or []),
        "fixture_report_url": f"/api/backtest/round-analysis/{entry['analysis_id']}/fixture/{entry['fixture_id']}/report-json",
    }


def build_critical_matches(flat_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixture_idx = _fixture_models_index(flat_rows)
    critical: list[dict[str, Any]] = []

    v21_rows = [r for r in flat_rows if r["model_key"] == V21]
    overest = sorted(
        v21_rows,
        key=lambda r: float((r["block"].get("predicted_total_sot") or 0)) - float(r["actual_total_sot"]),
        reverse=True,
    )[:20]
    for row in overest:
        pt = row["block"].get("predicted_total_sot")
        if pt is None:
            continue
        entry = fixture_idx[(int(row["analysis_id"]), int(row["fixture_id"]))]
        item = _critical_match_base(entry)
        item["category"] = "overestimate_v21"
        item["error_delta"] = _round4(float(pt) - float(row["actual_total_sot"]))
        critical.append(item)

    underest = sorted(
        v21_rows,
        key=lambda r: float(r["actual_total_sot"]) - float((r["block"].get("predicted_total_sot") or 0)),
        reverse=True,
    )[:20]
    for row in underest:
        pt = row["block"].get("predicted_total_sot")
        if pt is None:
            continue
        entry = fixture_idx[(int(row["analysis_id"]), int(row["fixture_id"]))]
        item = _critical_match_base(entry)
        item["category"] = "underestimate_v21"
        item["error_delta"] = _round4(float(row["actual_total_sot"]) - float(pt))
        critical.append(item)

    for entry in fixture_idx.values():
        models = entry["models"]
        all_caut_loss = True
        has_any = False
        for mk in (V11, V20, V21):
            block = models.get(mk)
            if not isinstance(block, dict):
                all_caut_loss = False
                continue
            outcome = block.get("cautious_outcome")
            if outcome not in ("WIN", "LOSS"):
                all_caut_loss = False
                continue
            has_any = True
            if outcome != "LOSS":
                all_caut_loss = False
        if has_any and all_caut_loss:
            item = _critical_match_base(entry)
            item["category"] = "all_models_cautious_loss"
            critical.append(item)

    for entry in fixture_idx.values():
        v11 = entry["models"].get(V11) or {}
        v21 = entry["models"].get(V21) or {}
        if v11.get("cautious_outcome") == "WIN" and v21.get("cautious_outcome") == "LOSS":
            item = _critical_match_base(entry)
            item["category"] = "v11_cautious_win_v21_cautious_loss"
            critical.append(item)

    for row in v21_rows:
        block = row["block"]
        if is_advised_label(str(block.get("cautious_advice") or "")) and block.get("cautious_outcome") == "LOSS":
            entry = fixture_idx[(int(row["analysis_id"]), int(row["fixture_id"]))]
            item = _critical_match_base(entry)
            item["category"] = "v21_cautious_gioca_loss"
            critical.append(item)

    return critical


def build_diagnostics_payload(
    flat_rows: list[dict[str, Any]],
    model_keys: list[str],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    models_out: dict[str, Any] = {}
    for mk in model_keys:
        model_rows = [r for r in flat_rows if r["model_key"] == mk]
        models_out[mk] = build_model_diagnostics(model_rows, mk)

    v21_rows = [r for r in flat_rows if r["model_key"] == V21]
    low_risk = build_low_total_risk_diagnostic(v21_rows)
    return {
        "report_type": "round_analysis_diagnostics_v30",
        "metadata": metadata,
        "models": models_out,
        "v21_diagnostics": {
            "macro_buckets": build_v21_macro_diagnostics(v21_rows),
            "split_status_summary": split_status_summary(v21_rows),
            "low_total_risk": {
                **low_risk,
                "reliability": "experimental_unreliable",
                "note": (
                    "Indice low_total_risk attuale non discrimina in modo affidabile tra partite basse "
                    "e altre; usare solo come esplorazione. Calibrazione prevista in v3.0."
                ),
            },
        },
        "critical_matches": build_critical_matches(flat_rows),
    }
