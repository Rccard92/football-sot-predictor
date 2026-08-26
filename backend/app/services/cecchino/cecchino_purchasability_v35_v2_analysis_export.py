"""Export analysis Structural V2 — frozen snapshot + post-match evaluation read-only."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v35_v2 import (
    PURCHASABILITY_V35_V2_ANALYSIS_EXPORT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    DOUBLE_CHANCE_FT_MARKETS,
    GOALS_FT_1_5_MARKETS,
    GOALS_FT_2_5_MARKETS,
    GOALS_FT_3_5_MARKETS,
    GOALS_HT_0_5_MARKETS,
    GOALS_HT_1_5_MARKETS,
    MATCH_WINNER_FT_MARKETS,
    MATCH_WINNER_HT_MARKETS,
    market_family_for,
)
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    build_market_evaluation_block,
    normalize_match_status,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    _iso_at,
    _parse_dt,
    index_purchasability_v35_snapshot_by_market,
    validate_purchasability_preview_v35_snapshot,
)
from app.services.cecchino.cecchino_purchasability_v35_v2_snapshot import (
    EXPECTED_FORMULA_FREEZE_SHA256,
    index_purchasability_v35_v2_snapshot_by_market,
)
from app.services.cecchino.cecchino_signal_evaluation import match_result_from_fixture

HOLDOUT_FAMILY_FT_1X2 = "FT_1X2"
HOLDOUT_FAMILY_PT_1X2 = "PT_1X2"
HOLDOUT_FAMILY_DOUBLE_CHANCE = "Double_Chance"
HOLDOUT_FAMILY_FT_GOALS = "FT_Goals"
HOLDOUT_FAMILY_PT_GOALS = "PT_Goals"

HOLDOUT_MARKET_FAMILIES = (
    HOLDOUT_FAMILY_FT_1X2,
    HOLDOUT_FAMILY_PT_1X2,
    HOLDOUT_FAMILY_DOUBLE_CHANCE,
    HOLDOUT_FAMILY_FT_GOALS,
    HOLDOUT_FAMILY_PT_GOALS,
)

TECHNICAL_SMOKE_SCAN_DATE = date(2026, 8, 26)
PROSPECTIVE_HOLDOUT_START = date(2026, 8, 27)
COHORT_TECHNICAL_SMOKE = "technical_smoke_cohort"
COHORT_PROSPECTIVE = "prospective_holdout"
COHORT_OTHER = "other_cohort"
PRIMARY_DIAGNOSTIC_COHORT = COHORT_PROSPECTIVE

FLOAT_ALIGNMENT_TOLERANCE = 1e-9

COMMON_INPUT_ALIGNMENT_FIELDS: tuple[str, ...] = (
    "execution_quote",
    "execution_quote_real",
    "probability_cecchino",
    "fair_book_probability",
    "rating",
    "overround",
    "book_fallback_used",
    "fair_probability_may_be_derived",
)

_FLOAT_INPUT_ALIGNMENT_FIELDS = frozenset(
    {
        "execution_quote",
        "probability_cecchino",
        "fair_book_probability",
        "rating",
        "overround",
    }
)

_POST_MATCH_EXCLUDE_KEYS = frozenset(
    {
        "final_score",
        "result",
        "outcome",
        "goals_home",
        "goals_away",
        "score_fulltime_home",
        "score_fulltime_away",
        "score_halftime_home",
        "score_halftime_away",
        "settlement",
        "settlement_status",
        "won",
        "lost",
        "hit",
        "profit",
        "profit_1u",
        "unit_stake_profit",
        "ft_result",
        "ht_result",
        "evaluation",
    }
)


def holdout_market_family(market_key: str) -> str | None:
    if market_key in MATCH_WINNER_FT_MARKETS:
        return HOLDOUT_FAMILY_FT_1X2
    if market_key in MATCH_WINNER_HT_MARKETS:
        return HOLDOUT_FAMILY_PT_1X2
    if market_key in DOUBLE_CHANCE_FT_MARKETS:
        return HOLDOUT_FAMILY_DOUBLE_CHANCE
    if market_key in (GOALS_FT_1_5_MARKETS | GOALS_FT_2_5_MARKETS | GOALS_FT_3_5_MARKETS):
        return HOLDOUT_FAMILY_FT_GOALS
    if market_key in (GOALS_HT_0_5_MARKETS | GOALS_HT_1_5_MARKETS):
        return HOLDOUT_FAMILY_PT_GOALS
    return None


def holdout_cohort_for_scan_date(scan_date: date | None) -> str:
    if scan_date is None:
        return COHORT_OTHER
    if scan_date == TECHNICAL_SMOKE_SCAN_DATE:
        return COHORT_TECHNICAL_SMOKE
    if scan_date >= PROSPECTIVE_HOLDOUT_START:
        return COHORT_PROSPECTIVE
    return COHORT_OTHER


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _normalize_source_snapshot_at(raw: Any) -> str | None:
    """Normalize snapshot timestamp for strict equality (ISO UTC when parseable)."""
    if raw is None:
        return None
    parsed = _parse_dt(raw)
    if parsed is not None:
        return parsed.astimezone(timezone.utc).isoformat()
    text = _iso_at(raw)
    return str(text) if text is not None else None


def _floats_aligned(a: Any, b: Any, *, tol: float = FLOAT_ALIGNMENT_TOLERANCE) -> bool:
    fa = _safe_float(a)
    fb = _safe_float(b)
    if fa is None and fb is None:
        return True
    if fa is None or fb is None:
        return False
    return abs(fa - fb) <= tol


def _bools_aligned(a: Any, b: Any) -> bool:
    return a == b


def _extract_common_input(item: dict[str, Any] | None) -> dict[str, Any]:
    inp = item.get("input") if isinstance(item, dict) and isinstance(item.get("input"), dict) else {}
    return {field: inp.get(field) for field in COMMON_INPUT_ALIGNMENT_FIELDS}


def _build_pair_input_alignment(
    v1_input: dict[str, Any],
    v2_input: dict[str, Any],
) -> tuple[dict[str, bool], list[str]]:
    alignment: dict[str, bool] = {}
    mismatches: list[str] = []
    for field in COMMON_INPUT_ALIGNMENT_FIELDS:
        if field in _FLOAT_INPUT_ALIGNMENT_FIELDS:
            ok = _floats_aligned(v1_input.get(field), v2_input.get(field))
        elif field in {"execution_quote_real", "book_fallback_used", "fair_probability_may_be_derived"}:
            ok = _bools_aligned(v1_input.get(field), v2_input.get(field))
        else:
            ok = v1_input.get(field) == v2_input.get(field)
        alignment[field] = ok
        if not ok:
            mismatches.append(field)
    return alignment, mismatches


def resolve_analysis_ev(item: dict[str, Any]) -> dict[str, Any]:
    """EV from frozen gate; fallback derived analysis only — never mutates V2."""
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    frozen_ev = _safe_float(gate.get("expected_value"))
    if frozen_ev is not None:
        return {"EV": frozen_ev, "ev_source": "frozen_gate"}
    p_cec = _safe_float(inp.get("probability_cecchino"))
    quote = _safe_float(inp.get("execution_quote"))
    if p_cec is not None and quote is not None:
        return {
            "EV": round(p_cec * quote - 1.0, 6),
            "ev_source": "derived_analysis_fallback",
        }
    return {"EV": None, "ev_source": None}


def _assert_no_post_match_in_pre_match(payload: dict[str, Any]) -> None:
    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in _POST_MATCH_EXCLUDE_KEYS:
                    raise ValueError(f"post_match_leakage at pre_match.{path}.{k}")
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(payload)


def _fixture_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "kickoff": row.kickoff.isoformat() if row.kickoff else None,
        "country": row.country_name,
        "league": row.league_name,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "holdout_cohort": holdout_cohort_for_scan_date(row.scan_date),
    }


def _pre_match_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    by_market = index_purchasability_v35_v2_snapshot_by_market(snapshot)
    markets: dict[str, Any] = {}
    for mk in PANEL_MARKET_KEYS:
        item = by_market.get(mk)
        if isinstance(item, dict):
            markets[mk] = item
    return {
        "snapshot_version": snapshot.get("snapshot_version"),
        "contract_version": snapshot.get("contract_version"),
        "feature_version": snapshot.get("feature_version"),
        "formula_version": snapshot.get("formula_version"),
        "relation_registry_version": snapshot.get("relation_registry_version"),
        "experiment_version": snapshot.get("experiment_version"),
        "source_snapshot_at": snapshot.get("source_snapshot_at"),
        "generated_at": snapshot.get("generated_at"),
        "kickoff": snapshot.get("kickoff"),
        "input_fingerprint_sha256": snapshot.get("input_fingerprint_sha256"),
        "engine_payload_sha256": snapshot.get("engine_payload_sha256"),
        "formula_freeze_sha256": snapshot.get("formula_freeze_sha256"),
        "frozen_config": snapshot.get("frozen_config"),
        "runtime_meta": snapshot.get("runtime_meta"),
        "reference": snapshot.get("reference"),
        "summary": snapshot.get("summary"),
        "markets": markets,
    }


def _post_match_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    match_result = match_result_from_fixture(row)
    ht = match_result.get("halftime") or {}
    ft = match_result.get("fulltime") or {}
    return {
        "match_status": normalize_match_status(row),
        "fixture_status": row.fixture_status,
        "halftime": {
            "home": ht.get("home"),
            "away": ht.get("away"),
            "available": bool(ht.get("available")),
        },
        "fulltime": {
            "home": ft.get("home"),
            "away": ft.get("away"),
            "available": bool(ft.get("available")),
        },
    }


def _component_score(components: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(components, dict):
        return None
    block = components.get(key)
    if not isinstance(block, dict):
        return None
    return block.get("score")


def extract_v2_analysis_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten V2 item fields for CSV/diagnostics — read-only."""
    gate = item.get("gate") if isinstance(item.get("gate"), dict) else {}
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    components = item.get("components") if isinstance(item.get("components"), dict) else {}
    s_block = (
        components.get("structural_coherence")
        if isinstance(components.get("structural_coherence"), dict)
        else {}
    )
    r_block = (
        components.get("base_rate_reliability")
        if isinstance(components.get("base_rate_reliability"), dict)
        else {}
    )
    ev_info = resolve_analysis_ev(item)
    return {
        "market_key": item.get("market_key"),
        "market_label": item.get("label"),
        "market_family": market_family_for(str(item.get("market_key") or "")),
        "holdout_market_family": holdout_market_family(str(item.get("market_key") or "")),
        "status": item.get("status"),
        "gate_status": item.get("gate_status") or gate.get("gate_status"),
        "execution_quote": inp.get("execution_quote"),
        "execution_quote_real": inp.get("execution_quote_real"),
        "execution_quote_source": inp.get("execution_quote_source"),
        "probability_cecchino": inp.get("probability_cecchino"),
        "fair_book_probability": inp.get("fair_book_probability"),
        "p_cec": inp.get("probability_cecchino"),
        "p_fair": inp.get("fair_book_probability"),
        "EV": ev_info["EV"],
        "ev_source": ev_info["ev_source"],
        "V": _component_score(components, "executable_value"),
        "D": _component_score(components, "market_disagreement"),
        "R": _component_score(components, "base_rate_reliability"),
        "base_rate_reliability": _component_score(components, "base_rate_reliability"),
        "base_rate_reliability_label": "Base-rate Reliability",
        "R_block": r_block or None,
        "VALUE_CORE": item.get("value_core"),
        "ACQUISITION_CORE": item.get("acquisition_core"),
        "S": _component_score(components, "structural_coherence"),
        "S_raw": s_block.get("S_raw"),
        "structural_confidence": s_block.get("structural_confidence"),
        "structural_factor": item.get("structural_factor"),
        "Q": _component_score(components, "information_quality"),
        "quality_factor": item.get("quality_factor"),
        "adjusted_confidence": item.get("adjusted_confidence"),
        "v2_score": item.get("score"),
        "v2_raw_score": item.get("raw_score"),
        "v2_class": item.get("class"),
    }


def resolve_paired_v1_a(
    *,
    row: CecchinoTodayFixture,
    market_key: str,
    v2_snapshot: dict[str, Any],
    v2_item: dict[str, Any],
) -> dict[str, Any] | None:
    """Soft/strict V1↔V2 pair for the same fixture market (historical + fair holdout)."""
    output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    v1 = output.get("purchasability_preview_v35")
    if not isinstance(v1, dict):
        return None
    check = validate_purchasability_preview_v35_snapshot(v1)
    if not check.get("ok"):
        return None
    by_mk = index_purchasability_v35_snapshot_by_market(v1)
    v1_item = by_mk.get(market_key)
    if not isinstance(v1_item, dict):
        return None

    candidates = v1_item.get("candidates") if isinstance(v1_item.get("candidates"), dict) else {}
    cand_a = candidates.get("A") if isinstance(candidates.get("A"), dict) else None

    v1_status = str(v1_item.get("status") or "") or None
    v2_status = str(v2_item.get("status") or "") or None
    v1_score_a = cand_a.get("score") if cand_a else None
    v1_raw_score_a = cand_a.get("raw_score") if cand_a else None
    v1_class_a = cand_a.get("class") if cand_a else None
    v2_score = v2_item.get("score")
    v2_raw_score = v2_item.get("raw_score")

    v1_snap_at = _normalize_source_snapshot_at(v1.get("source_snapshot_at"))
    v2_snap_at = _normalize_source_snapshot_at(v2_snapshot.get("source_snapshot_at"))

    v1_input = _extract_common_input(v1_item)
    v2_input = _extract_common_input(v2_item)
    pair_input_alignment, input_mismatch_fields = _build_pair_input_alignment(
        v1_input, v2_input
    )

    pair: dict[str, Any] = {
        "paired": True,
        "pair_key": f"{int(row.id)}::{market_key}",
        "v1_score_A": v1_score_a,
        "v1_raw_score_A": v1_raw_score_a,
        "v1_class_A": v1_class_a,
        "v1_source_snapshot_at": v1_snap_at,
        "v2_source_snapshot_at": v2_snap_at,
        "v1_execution_quote": v1_input.get("execution_quote"),
        "v2_execution_quote": v2_input.get("execution_quote"),
        "v1_execution_quote_real": v1_input.get("execution_quote_real"),
        "v2_execution_quote_real": v2_input.get("execution_quote_real"),
        "v1_status": v1_status,
        "v2_status": v2_status,
        "strict_paired": False,
        "pair_alignment_reason": None,
        "pair_input_alignment": pair_input_alignment,
        "input_mismatch_fields": input_mismatch_fields,
    }

    reason: str | None = None
    if v1_status != "score":
        reason = "v1_not_scored"
    elif v2_status != "score":
        reason = "v2_not_scored"
    elif cand_a is None:
        reason = "v1_score_missing"
    elif _safe_float(v1_raw_score_a) is None and _safe_float(v1_score_a) is None:
        reason = "v1_score_missing"
    elif _safe_float(v2_raw_score) is None and _safe_float(v2_score) is None:
        reason = "v2_score_missing"
    elif v1_snap_at is None or v2_snap_at is None or v1_snap_at != v2_snap_at:
        reason = "snapshot_timestamp_mismatch"
    elif input_mismatch_fields:
        reason = "input_context_mismatch"
    else:
        pair["strict_paired"] = True
        pair["pair_alignment_reason"] = None
        return pair

    pair["strict_paired"] = False
    pair["pair_alignment_reason"] = reason
    return pair


def select_top_v2_market_pre_match(markets: dict[str, Any]) -> dict[str, Any] | None:
    """Top market by raw_score among status==score only — before outcome join."""
    best: dict[str, Any] | None = None
    best_raw: float | None = None
    best_panel_idx = 10**9
    best_fixture_tie = 0  # unused here; panel order is enough within fixture

    for idx, mk in enumerate(PANEL_MARKET_KEYS):
        item = markets.get(mk)
        if not isinstance(item, dict) or str(item.get("status") or "") != "score":
            continue
        raw = _safe_float(item.get("raw_score"))
        if raw is None:
            continue
        if (
            best_raw is None
            or raw > best_raw
            or (raw == best_raw and idx < best_panel_idx)
        ):
            best = {"market_key": mk, "item": item}
            best_raw = raw
            best_panel_idx = idx
            _ = best_fixture_tie
    return best


def _build_analysis_summary(markets: dict[str, Any]) -> dict[str, Any]:
    scored = 0
    evaluated_scored = 0
    won = lost = pending = result_missing = not_evaluable = 0
    profit_sum = 0.0
    stake_count = 0
    for item in markets.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") == "score":
            scored += 1
        else:
            continue
        ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
        outcome = ev.get("outcome")
        if outcome in {
            EVAL_WON,
            EVAL_LOST,
            EVAL_PENDING,
            EVAL_RESULT_MISSING,
            EVAL_NOT_EVALUABLE,
        }:
            evaluated_scored += 1
        if outcome == EVAL_WON:
            won += 1
        elif outcome == EVAL_LOST:
            lost += 1
        elif outcome == EVAL_PENDING:
            pending += 1
        elif outcome == EVAL_RESULT_MISSING:
            result_missing += 1
        elif outcome == EVAL_NOT_EVALUABLE:
            not_evaluable += 1
        profit = ev.get("profit_1u")
        if profit is not None:
            profit_sum += float(profit)
            stake_count += 1
    return {
        "scored_market_count": scored,
        "evaluated_scored_count": evaluated_scored,
        "won_scored_count": won,
        "lost_scored_count": lost,
        "pending_scored_count": pending,
        "result_missing_scored_count": result_missing,
        "not_evaluable_scored_count": not_evaluable,
        "priced_settled_count": stake_count,
        "profit_units_all_scored": round(profit_sum, 4) if stake_count else 0.0,
        "roi_pct_all_scored": round((profit_sum / stake_count) * 100, 4)
        if stake_count
        else None,
    }


def build_purchasability_v35_v2_analysis_export(
    row: CecchinoTodayFixture,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Analysis export V2: frozen + post-match evaluation; no V2 recompute."""
    pre_match = _pre_match_block(snapshot)
    _assert_no_post_match_in_pre_match(pre_match)

    frozen_markets = (
        pre_match.get("markets") if isinstance(pre_match.get("markets"), dict) else {}
    )
    # Top pick BEFORE attaching outcomes
    top_pre = select_top_v2_market_pre_match(frozen_markets)

    markets: dict[str, Any] = {}
    for mk in PANEL_MARKET_KEYS:
        item = frozen_markets.get(mk)
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        analysis_fields = extract_v2_analysis_fields(item)
        enriched["analysis"] = analysis_fields
        paired = resolve_paired_v1_a(
            row=row,
            market_key=mk,
            v2_snapshot=snapshot,
            v2_item=item,
        )
        if paired is not None:
            enriched["paired_v1"] = paired
        enriched["evaluation"] = build_market_evaluation_block(
            item, row, market_key=mk
        )
        markets[mk] = enriched

    top_pick: dict[str, Any] | None = None
    if top_pre is not None:
        mk = top_pre["market_key"]
        chosen = markets.get(mk)
        if isinstance(chosen, dict):
            ev = chosen.get("evaluation") if isinstance(chosen.get("evaluation"), dict) else {}
            top_pick = {
                "market_key": mk,
                "v2_score": chosen.get("score"),
                "v2_raw_score": chosen.get("raw_score"),
                "v2_class": chosen.get("class"),
                "outcome": ev.get("outcome"),
                "profit_1u": ev.get("profit_1u"),
                "execution_quote": (chosen.get("input") or {}).get("execution_quote")
                if isinstance(chosen.get("input"), dict)
                else None,
                "selection_basis": "pre_match_status_score_raw_score",
            }

    freeze_sha = snapshot.get("formula_freeze_sha256")
    payload = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_V2_ANALYSIS_EXPORT_CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fixture": _fixture_block(row),
            "snapshot_integrity": {
                "valid": True,
                "engine_payload_sha256": snapshot.get("engine_payload_sha256"),
                "input_fingerprint_sha256": snapshot.get("input_fingerprint_sha256"),
                "formula_freeze_sha256": freeze_sha,
                "formula_freeze_ok": freeze_sha == EXPECTED_FORMULA_FREEZE_SHA256,
            },
            "pre_match": pre_match,
            "post_match": _post_match_block(row),
            "markets": markets,
            "top_v2_market": top_pick,
            "analysis_summary": _build_analysis_summary(markets),
            "terminology": {
                "R": "Base-rate Reliability",
                "base_rate_reliability": "Base-rate Reliability",
                "not": [
                    "Reliability Probability",
                    "win probability",
                    "probabilità di vittoria",
                ],
            },
        }
    )
    return payload


__all__ = [
    "COHORT_OTHER",
    "COHORT_PROSPECTIVE",
    "COHORT_TECHNICAL_SMOKE",
    "COMMON_INPUT_ALIGNMENT_FIELDS",
    "FLOAT_ALIGNMENT_TOLERANCE",
    "HOLDOUT_MARKET_FAMILIES",
    "PRIMARY_DIAGNOSTIC_COHORT",
    "PROSPECTIVE_HOLDOUT_START",
    "TECHNICAL_SMOKE_SCAN_DATE",
    "build_purchasability_v35_v2_analysis_export",
    "extract_v2_analysis_fields",
    "holdout_cohort_for_scan_date",
    "holdout_market_family",
    "resolve_analysis_ev",
    "resolve_paired_v1_a",
    "select_top_v2_market_pre_match",
]
