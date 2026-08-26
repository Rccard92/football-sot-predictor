"""Replay Structural V2 da analysis CSV/ZIP V1 — solo input pre-match + diagnostic post-freeze."""

from __future__ import annotations

import csv
import io
import math
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_v35_v2_config import (
    compute_v2_formula_freeze_sha256,
    frozen_math_config_v35_v2,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_engine import (
    calculate_purchasability_v35_v2_item_from_prematch,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_features import (
    evaluate_v35_v2_gate_from_inputs,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
)

POST_MATCH_FIELDS = frozenset(
    {
        "match_status",
        "ht_home",
        "ht_away",
        "ft_home",
        "ft_away",
        "outcome",
        "evaluation_reason",
        "profit_1u",
        "break_even_probability",
        "score_A",
        "raw_A",
        "class_A",
        "score_B",
        "raw_B",
        "class_B",
        "score_C",
        "raw_C",
        "class_C",
        "score_D",
        "raw_D",
        "class_D",
        "V",
        "D",
        "S",
        "S_raw",
        "S_confidence",
        "S_coverage",
        "Q",
    }
)

PREMATCH_KEEP = frozenset(
    {
        "scan_date",
        "today_fixture_id",
        "provider_fixture_id",
        "country",
        "league",
        "home_team",
        "away_team",
        "kickoff",
        "source_snapshot_at",
        "hours_to_kickoff",
        "market_key",
        "market_label",
        "market_status",
        "gate_status",
        "gate_reason_codes",
        "execution_quote",
        "execution_quote_real",
        "execution_quote_source",
        "probability_cecchino",
        "fair_book_probability",
        "rating",
        "overround",
        "book_fallback_used",
        "fair_probability_may_be_derived",
        "input_fingerprint_sha256",
        "engine_payload_sha256",
    }
)

FT_1X2 = (SEL_HOME, SEL_DRAW, SEL_AWAY)
PT_1X2 = (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT)

SCORE_BANDS = (
    ("<40", lambda s: s < 40),
    ("40-49", lambda s: 40 <= s <= 49),
    ("50-59", lambda s: 50 <= s <= 59),
    ("60-69", lambda s: 60 <= s <= 69),
    ("70-79", lambda s: 70 <= s <= 79),
    ("80+", lambda s: s >= 80),
)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y"}


def strip_post_match_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Elimina fisicamente i campi post-match / V1 score dal payload replay."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in POST_MATCH_FIELDS:
            continue
        if k in PREMATCH_KEEP or k.startswith("prematch_"):
            out[k] = v
    # Keep only known pre-match keys to be strict
    strict = {k: out[k] for k in out if k in PREMATCH_KEEP}
    return strict


def load_analysis_rows_from_zip(zip_path: str | Path) -> list[dict[str, Any]]:
    path = Path(zip_path)
    with zipfile.ZipFile(path, "r") as zf:
        raw = zf.read("analysis_rows.csv").decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw))
    return [dict(r) for r in reader]


def group_rows_by_fixture(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        fid = str(
            row.get("today_fixture_id")
            or row.get("provider_fixture_id")
            or ""
        ).strip()
        if not fid:
            continue
        grouped[fid].append(row)
    return dict(grouped)


def reconstruct_19_prematch_markets(
    fixture_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_mk: dict[str, dict[str, Any]] = {}
    for row in fixture_rows:
        mk = str(row.get("market_key") or "").strip()
        if not mk:
            continue
        by_mk[mk] = strip_post_match_fields(row)
    # Ensure all 19 keys exist (possibly empty shells)
    for mk in PANEL_MARKET_KEYS:
        by_mk.setdefault(
            mk,
            {
                "market_key": mk,
                "execution_quote": None,
                "execution_quote_real": False,
                "probability_cecchino": None,
                "fair_book_probability": None,
                "rating": None,
                "overround": None,
                "book_fallback_used": False,
                "fair_probability_may_be_derived": False,
            },
        )
    return by_mk


def _probs_map_from_prematch(
    by_mk: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for mk in PANEL_MARKET_KEYS:
        row = by_mk.get(mk) or {}
        out[mk] = {
            "probability_cecchino": _safe_float(row.get("probability_cecchino")),
            "fair_book_probability": _safe_float(row.get("fair_book_probability")),
        }
    return out


def score_fixture_v2(
    by_mk: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    probs = _probs_map_from_prematch(by_mk)
    items: list[dict[str, Any]] = []
    for mk in PANEL_MARKET_KEYS:
        row = by_mk.get(mk) or {}
        gate = evaluate_v35_v2_gate_from_inputs(
            execution_quote=_safe_float(row.get("execution_quote")),
            execution_quote_real=_safe_bool(row.get("execution_quote_real")),
            probability_cecchino=_safe_float(row.get("probability_cecchino")),
            fair_book_probability=_safe_float(row.get("fair_book_probability")),
            rating=_safe_float(row.get("rating")),
            pre_match_verified=True,
        )
        input_payload = {
            "execution_quote": _safe_float(row.get("execution_quote")),
            "execution_quote_real": _safe_bool(row.get("execution_quote_real")),
            "execution_quote_source": row.get("execution_quote_source"),
            "probability_cecchino": _safe_float(row.get("probability_cecchino")),
            "fair_book_probability": _safe_float(row.get("fair_book_probability")),
            "rating": _safe_float(row.get("rating")),
            "overround": _safe_float(row.get("overround")),
            "book_fallback_used": _safe_bool(row.get("book_fallback_used")),
            "fair_probability_may_be_derived": _safe_bool(
                row.get("fair_probability_may_be_derived")
            ),
        }
        item = calculate_purchasability_v35_v2_item_from_prematch(
            mk,
            gate=gate,
            input_payload=input_payload,
            probs_by_market=probs,
        )
        # Carry fixture identity for reports (still pre-match)
        item["fixture_identity"] = {
            "today_fixture_id": row.get("today_fixture_id"),
            "provider_fixture_id": row.get("provider_fixture_id"),
            "scan_date": row.get("scan_date"),
            "kickoff": row.get("kickoff"),
            "source_snapshot_at": row.get("source_snapshot_at"),
            "home_team": row.get("home_team"),
            "away_team": row.get("away_team"),
            "league": row.get("league"),
            "country": row.get("country"),
        }
        items.append(item)
    return items


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def distribution_stats(scores: list[int]) -> dict[str, Any]:
    if not scores:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p75": None,
            "max": None,
            "share_ge_60": None,
            "share_ge_70": None,
            "share_ge_80": None,
        }
    vals = sorted(float(s) for s in scores)
    n = len(vals)
    return {
        "n": n,
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "p75": _percentile(vals, 0.75),
        "max": max(vals),
        "share_ge_60": sum(1 for s in vals if s >= 60) / n,
        "share_ge_70": sum(1 for s in vals if s >= 70) / n,
        "share_ge_80": sum(1 for s in vals if s >= 80) / n,
    }


def anti_inflation_acceptance(dist: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "mean_le_60": dist["mean"] is not None and dist["mean"] <= 60.0,
        "median_le_60": dist["median"] is not None and dist["median"] <= 60.0,
        "share_ge_70_le_15pct": dist["share_ge_70"] is not None
        and dist["share_ge_70"] <= 0.15,
        "share_ge_80_le_3pct": dist["share_ge_80"] is not None
        and dist["share_ge_80"] <= 0.03,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "distribution": dist,
    }


def family_complete(probs: dict[str, dict[str, float | None]], keys: tuple[str, ...]) -> bool:
    for mk in keys:
        entry = probs.get(mk) or {}
        p_cec = entry.get("probability_cecchino")
        p_fair = entry.get("fair_book_probability")
        if p_cec is None or p_fair is None:
            return False
        if not (0.0 < float(p_cec) < 1.0 and 0.0 < float(p_fair) < 1.0):
            return False
    return True


def s_availability_for_family(
    items: list[dict[str, Any]],
    family: tuple[str, ...],
    probs: dict[str, dict[str, float | None]],
) -> dict[str, Any]:
    """S availability for scored family markets when opponent probs are complete.

    Opponents may be gate_failed; selected markets that pass the gate must still
    get S available from pre-match probabilities alone.
    """
    by_mk = {it["market_key"]: it for it in items}
    if not family_complete(probs, family):
        return {
            "family_complete": False,
            "markets_checked": 0,
            "s_available": 0,
            "availability_rate": None,
        }
    checked = 0
    avail = 0
    for mk in family:
        it = by_mk.get(mk) or {}
        if it.get("status") != "score":
            continue
        checked += 1
        s_block = (it.get("components") or {}).get("structural_coherence") or {}
        if s_block.get("status") == "available":
            avail += 1
    if checked == 0:
        return {
            "family_complete": True,
            "markets_checked": 0,
            "s_available": 0,
            "availability_rate": None,
        }
    return {
        "family_complete": True,
        "markets_checked": checked,
        "s_available": avail,
        "availability_rate": avail / checked,
    }


def replay_structural_v2_from_v1_analysis_csv(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replay pre-match only. Outcome fields are stripped before scoring."""
    grouped = group_rows_by_fixture(rows)
    scored_items: list[dict[str, Any]] = []
    all_items: list[dict[str, Any]] = []
    s_missing_scores: list[int] = []
    s_available_scores: list[int] = []
    ft_s_rates: list[float] = []
    pt_s_rates: list[float] = []
    post_match_leaks = 0

    for _fid, fixture_rows in grouped.items():
        # Leak check on raw rows before strip
        for raw in fixture_rows:
            for k in POST_MATCH_FIELDS:
                if k in raw and raw.get(k) not in (None, ""):
                    # expected in source CSV; must be absent after strip
                    pass
        by_mk = reconstruct_19_prematch_markets(fixture_rows)
        for mk, payload in by_mk.items():
            for k in POST_MATCH_FIELDS:
                if k in payload:
                    post_match_leaks += 1
        probs = _probs_map_from_prematch(by_mk)
        items = score_fixture_v2(by_mk)
        all_items.extend(items)

        ft_av = s_availability_for_family(items, FT_1X2, probs)
        pt_av = s_availability_for_family(items, PT_1X2, probs)
        if ft_av["availability_rate"] is not None:
            ft_s_rates.append(float(ft_av["availability_rate"]))
        if pt_av["availability_rate"] is not None:
            pt_s_rates.append(float(pt_av["availability_rate"]))

        for it in items:
            if it.get("status") != "score":
                continue
            score = it.get("score")
            if score is None:
                continue
            scored_items.append(it)
            s_block = (it.get("components") or {}).get("structural_coherence") or {}
            if s_block.get("status") == "available":
                s_available_scores.append(int(score))
            else:
                s_missing_scores.append(int(score))

    scores = [int(it["score"]) for it in scored_items if it.get("score") is not None]
    dist = distribution_stats(scores)
    acceptance = anti_inflation_acceptance(dist)

    def _mean_or_none(vals: list[float]) -> float | None:
        return statistics.fmean(vals) if vals else None

    return {
        "fixtures": len(grouped),
        "items_total": len(all_items),
        "scored_rows": len(scored_items),
        "distribution": dist,
        "anti_inflation": acceptance,
        "s_missing_vs_available_diagnostic": {
            "mean_score_s_missing": _mean_or_none([float(x) for x in s_missing_scores]),
            "mean_score_s_available": _mean_or_none(
                [float(x) for x in s_available_scores]
            ),
            "n_s_missing": len(s_missing_scores),
            "n_s_available": len(s_available_scores),
            "note": "diagnostic_only_not_blocker_different_market_populations",
        },
        "pt_s_availability_when_family_complete": {
            "fixture_families": len(pt_s_rates),
            "mean_availability_rate": _mean_or_none(pt_s_rates),
            "all_complete_100pct": bool(pt_s_rates)
            and all(abs(r - 1.0) < 1e-9 for r in pt_s_rates),
        },
        "ft_s_availability_when_family_complete": {
            "fixture_families": len(ft_s_rates),
            "mean_availability_rate": _mean_or_none(ft_s_rates),
            "all_complete_100pct": bool(ft_s_rates)
            and all(abs(r - 1.0) < 1e-9 for r in ft_s_rates),
        },
        "post_match_fields_in_replay_payload": post_match_leaks,
        "scored_items": scored_items,
        "all_items": all_items,
    }


def join_outcome_diagnostic(
    *,
    source_rows: list[dict[str, Any]],
    scored_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read-only join con outcome CSV — NON usato per retune."""
    key_to_outcome: dict[tuple[str, str], dict[str, Any]] = {}
    for row in source_rows:
        fid = str(row.get("today_fixture_id") or "").strip()
        mk = str(row.get("market_key") or "").strip()
        if not fid or not mk:
            continue
        key_to_outcome[(fid, mk)] = {
            "outcome": row.get("outcome"),
            "profit_1u": _safe_float(row.get("profit_1u")),
            "match_status": row.get("match_status"),
            "score_A": _safe_float(row.get("score_A")),
        }

    bands: dict[str, dict[str, Any]] = {
        name: {"count": 0, "wins": 0, "losses": 0, "profit_sum": 0.0}
        for name, _ in SCORE_BANDS
    }
    settled: list[dict[str, Any]] = []
    top_by_fixture: dict[str, dict[str, Any]] = {}

    for it in scored_items:
        if it.get("status") != "score" or it.get("score") is None:
            continue
        fid = str((it.get("fixture_identity") or {}).get("today_fixture_id") or "")
        mk = str(it.get("market_key") or "")
        score = int(it["score"])
        oc = key_to_outcome.get((fid, mk), {})
        outcome = str(oc.get("outcome") or "").upper()
        profit = oc.get("profit_1u")
        row_out = {
            "today_fixture_id": fid,
            "market_key": mk,
            "score": score,
            "outcome": outcome,
            "profit_1u": profit,
        }
        if outcome in {"WON", "LOST"} and profit is not None:
            settled.append(row_out)
            for name, pred in SCORE_BANDS:
                if pred(score):
                    bands[name]["count"] += 1
                    if outcome == "WON":
                        bands[name]["wins"] += 1
                    else:
                        bands[name]["losses"] += 1
                    bands[name]["profit_sum"] += float(profit)
                    break
            prev = top_by_fixture.get(fid)
            if prev is None or score > int(prev["score"]):
                top_by_fixture[fid] = row_out

    band_report = []
    for name, _ in SCORE_BANDS:
        b = bands[name]
        n = b["count"]
        hit = (b["wins"] / n) if n else None
        roi = (b["profit_sum"] / n) if n else None
        band_report.append(
            {
                "band": name,
                "count": n,
                "wins": b["wins"],
                "losses": b["losses"],
                "hit_rate": hit,
                "roi": roi,
            }
        )

    top_rows = list(top_by_fixture.values())
    top_settled = [r for r in top_rows if r["outcome"] in {"WON", "LOST"}]
    top_wins = sum(1 for r in top_settled if r["outcome"] == "WON")
    top_losses = sum(1 for r in top_settled if r["outcome"] == "LOST")
    top_n = len(top_settled)
    top_profit = sum(float(r["profit_1u"] or 0.0) for r in top_settled)

    # Monotonicity diagnostic: hit_rate should not collapse as score rises
    settled_bands = [b for b in band_report if b["count"] >= 20 and b["hit_rate"] is not None]
    collapse = False
    collapse_detail = None
    if len(settled_bands) >= 2:
        # Compare lowest band with highest band that has enough samples
        low = settled_bands[0]
        high = settled_bands[-1]
        if high["hit_rate"] + 0.10 < low["hit_rate"] and high["band"] in {
            "70-79",
            "80+",
        }:
            collapse = True
            collapse_detail = {
                "low_band": low,
                "high_band": high,
                "rule": "high_band_hit_rate_below_low_band_minus_10pp",
            }

    # V1 A 80+ reference from source (diagnostic)
    v1_80 = {"count": 0, "wins": 0, "losses": 0, "profit_sum": 0.0}
    for row in source_rows:
        sa = _safe_float(row.get("score_A"))
        outcome = str(row.get("outcome") or "").upper()
        profit = _safe_float(row.get("profit_1u"))
        if sa is None or sa < 80:
            continue
        if outcome not in {"WON", "LOST"} or profit is None:
            continue
        v1_80["count"] += 1
        if outcome == "WON":
            v1_80["wins"] += 1
        else:
            v1_80["losses"] += 1
        v1_80["profit_sum"] += profit

    return {
        "bands": band_report,
        "top_market_per_fixture": {
            "fixtures": len(top_rows),
            "settled": top_n,
            "wins": top_wins,
            "losses": top_losses,
            "hit_rate": (top_wins / top_n) if top_n else None,
            "roi": (top_profit / top_n) if top_n else None,
        },
        "monotonicity_collapse_flag": collapse,
        "monotonicity_detail": collapse_detail,
        "v1_a_80_plus_reference": {
            "count": v1_80["count"],
            "wins": v1_80["wins"],
            "losses": v1_80["losses"],
            "hit_rate": (v1_80["wins"] / v1_80["count"]) if v1_80["count"] else None,
            "roi": (v1_80["profit_sum"] / v1_80["count"]) if v1_80["count"] else None,
        },
        "settled_rows": len(settled),
    }


def run_full_replay_with_freeze(
    zip_path: str | Path,
) -> dict[str, Any]:
    """Sequenza: freeze → replay pre-match → outcome join → re-freeze proof."""
    freeze_cfg = frozen_math_config_v35_v2()
    freeze_sha_before = compute_v2_formula_freeze_sha256(freeze_cfg)

    source_rows = load_analysis_rows_from_zip(zip_path)
    replay = replay_structural_v2_from_v1_analysis_csv(source_rows)

    freeze_sha_after_replay = compute_v2_formula_freeze_sha256(freeze_cfg)

    outcome = join_outcome_diagnostic(
        source_rows=source_rows,
        scored_items=replay["scored_items"],
    )

    freeze_sha_after_outcome = compute_v2_formula_freeze_sha256(
        frozen_math_config_v35_v2()
    )
    freeze_ok = (
        freeze_sha_before
        == freeze_sha_after_replay
        == freeze_sha_after_outcome
    )

    go_phase_b = (
        bool(replay["anti_inflation"]["passed"])
        and replay["post_match_fields_in_replay_payload"] == 0
        and bool(replay["pt_s_availability_when_family_complete"]["all_complete_100pct"])
        and bool(replay["ft_s_availability_when_family_complete"]["all_complete_100pct"])
        and freeze_ok
        and not bool(outcome["monotonicity_collapse_flag"])
    )

    return {
        "V2_FORMULA_FREEZE_SHA256": freeze_sha_before,
        "freeze_sha_after_replay": freeze_sha_after_replay,
        "freeze_sha_after_outcome": freeze_sha_after_outcome,
        "freeze_unchanged": freeze_ok,
        "replay": {
            k: v
            for k, v in replay.items()
            if k not in {"scored_items", "all_items"}
        },
        "outcome_diagnostic": outcome,
        "GO_TO_PHASE_B": go_phase_b,
        "NO_GO_TO_PHASE_B": not go_phase_b,
    }
