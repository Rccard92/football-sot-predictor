"""Valutazione read-only mercati V3.5 per analysis export — no settlement persistito."""

from __future__ import annotations

from typing import Any

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import (
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_signal_evaluation import (
    PT_SELECTION_KEYS,
    evaluate_market_selection,
    match_result_from_fixture,
)

MATCH_STATUS_CANONICAL = frozenset(
    {
        MATCH_UPCOMING,
        MATCH_LIVE,
        MATCH_FINISHED,
        MATCH_POSTPONED,
        MATCH_CANCELLED,
        "unknown",
    }
)


def normalize_match_status(row: CecchinoTodayFixture) -> str:
    status = str(row.match_display_status or "").strip().lower()
    if status in MATCH_STATUS_CANONICAL:
        return status
    if not status:
        return MATCH_UPCOMING
    return "unknown"


def evaluate_v35_market_outcome(
    market_key: str,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Outcome read-only per mercato V3.5 — semantica match status canonica."""
    match_status = normalize_match_status(row)

    if match_status in {MATCH_CANCELLED, MATCH_POSTPONED}:
        return {
            "outcome": EVAL_NOT_EVALUABLE,
            "evaluation_reason": f"match_{match_status}",
            "match_status": match_status,
            "result_home_ht": row.score_halftime_home,
            "result_away_ht": row.score_halftime_away,
            "result_home_ft": row.score_fulltime_home,
            "result_away_ft": row.score_fulltime_away,
        }

    match_result = match_result_from_fixture(row)
    ht = match_result.get("halftime") or {}
    ft = match_result.get("fulltime") or {}
    ht_ready = ht.get("home") is not None and ht.get("away") is not None
    ft_ready = ft.get("home") is not None and ft.get("away") is not None

    if market_key in PT_SELECTION_KEYS:
        if ht_ready:
            ev = evaluate_market_selection(market_key, match_result)
            return {
                "outcome": ev.get("evaluation_status") or EVAL_NOT_EVALUABLE,
                "evaluation_reason": ev.get("evaluation_reason"),
                "match_status": match_status,
                "result_home_ht": ev.get("result_home_ht"),
                "result_away_ht": ev.get("result_away_ht"),
                "result_home_ft": row.score_fulltime_home,
                "result_away_ft": row.score_fulltime_away,
            }
        if match_status == MATCH_FINISHED:
            return {
                "outcome": EVAL_RESULT_MISSING,
                "evaluation_reason": "halftime_result_missing",
                "match_status": match_status,
                "result_home_ht": row.score_halftime_home,
                "result_away_ht": row.score_halftime_away,
                "result_home_ft": row.score_fulltime_home,
                "result_away_ft": row.score_fulltime_away,
            }
        return {
            "outcome": EVAL_PENDING,
            "evaluation_reason": "awaiting_halftime_result",
            "match_status": match_status,
            "result_home_ht": row.score_halftime_home,
            "result_away_ht": row.score_halftime_away,
            "result_home_ft": row.score_fulltime_home,
            "result_away_ft": row.score_fulltime_away,
        }

    if ft_ready:
        ev = evaluate_market_selection(market_key, match_result)
        return {
            "outcome": ev.get("evaluation_status") or EVAL_NOT_EVALUABLE,
            "evaluation_reason": ev.get("evaluation_reason"),
            "match_status": match_status,
            "result_home_ht": ev.get("result_home_ht"),
            "result_away_ht": ev.get("result_away_ht"),
            "result_home_ft": ev.get("result_home_ft"),
            "result_away_ft": ev.get("result_away_ft"),
        }

    if match_status == MATCH_FINISHED:
        return {
            "outcome": EVAL_RESULT_MISSING,
            "evaluation_reason": "fulltime_result_missing",
            "match_status": match_status,
            "result_home_ht": row.score_halftime_home,
            "result_away_ht": row.score_halftime_away,
            "result_home_ft": row.score_fulltime_home,
            "result_away_ft": row.score_fulltime_away,
        }

    return {
        "outcome": EVAL_PENDING,
        "evaluation_reason": "awaiting_fulltime_result",
        "match_status": match_status,
        "result_home_ht": row.score_halftime_home,
        "result_away_ht": row.score_halftime_away,
        "result_home_ft": row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home,
        "result_away_ft": row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away,
    }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def compute_break_even_probability(execution_quote: float | None) -> float | None:
    if execution_quote is None or execution_quote <= 1:
        return None
    return round(1.0 / execution_quote, 6)


def compute_profit_1u(item: dict[str, Any], outcome: str) -> float | None:
    """Profit flat stake 1u — solo mercati scored con quota reale."""
    if str(item.get("status") or "") != "score":
        return None
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    execution_quote = _safe_float(inp.get("execution_quote"))
    execution_quote_real = inp.get("execution_quote_real") is True
    if not execution_quote_real or execution_quote is None or execution_quote <= 1:
        return None
    if outcome == EVAL_WON:
        return round(execution_quote - 1.0, 4)
    if outcome == EVAL_LOST:
        return -1.0
    return None


def build_market_evaluation_block(
    item: dict[str, Any],
    row: CecchinoTodayFixture,
    *,
    market_key: str,
) -> dict[str, Any]:
    """Blocco evaluation per singolo mercato frozen."""
    eval_core = evaluate_v35_market_outcome(market_key, row)
    inp = item.get("input") if isinstance(item.get("input"), dict) else {}
    execution_quote = _safe_float(inp.get("execution_quote"))
    execution_quote_real = inp.get("execution_quote_real") is True
    outcome = eval_core["outcome"]

    return {
        "market_key": market_key,
        "outcome": outcome,
        "evaluation_reason": eval_core.get("evaluation_reason"),
        "result_home_ht": eval_core.get("result_home_ht"),
        "result_away_ht": eval_core.get("result_away_ht"),
        "result_home_ft": eval_core.get("result_home_ft"),
        "result_away_ft": eval_core.get("result_away_ft"),
        "scored_by_v35": str(item.get("status") or "") == "score",
        "execution_quote": execution_quote,
        "execution_quote_real": execution_quote_real,
        "profit_1u": compute_profit_1u(item, outcome),
        "break_even_probability": compute_break_even_probability(execution_quote),
    }


def compute_candidate_top_picks(
    markets: dict[str, Any],
) -> dict[str, Any]:
    """Top pick per candidate A/B/C/D — max score tra status=score, tie-break panel order."""
    candidates = ("A", "B", "C", "D")
    result: dict[str, Any] = {}

    for ck in candidates:
        best_key: str | None = None
        best_score: float | None = None

        for mk in PANEL_MARKET_KEYS:
            item = markets.get(mk)
            if not isinstance(item, dict) or str(item.get("status") or "") != "score":
                continue
            cands = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
            cand = cands.get(ck)
            if not isinstance(cand, dict):
                continue
            score = _safe_float(cand.get("score"))
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_key = mk
                best_score = score
            elif best_score is not None and score == best_score:
                if best_key is None or PANEL_MARKET_KEYS.index(mk) < PANEL_MARKET_KEYS.index(best_key):
                    best_key = mk
                    best_score = score

        if best_key is None:
            result[ck] = None
            continue

        item = markets[best_key]
        cands = item.get("candidates") if isinstance(item.get("candidates"), dict) else {}
        cand = cands.get(ck) if isinstance(cands.get(ck), dict) else {}
        eval_block = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
        inp = item.get("input") if isinstance(item.get("input"), dict) else {}

        result[ck] = {
            "market_key": best_key,
            "score": cand.get("score"),
            "raw_score": cand.get("raw_score"),
            "class": cand.get("class"),
            "outcome": eval_block.get("outcome"),
            "execution_quote": eval_block.get("execution_quote"),
            "profit_1u": eval_block.get("profit_1u"),
        }

        if result[ck]["execution_quote"] is None:
            result[ck]["execution_quote"] = _safe_float(inp.get("execution_quote"))

    return result


__all__ = [
    "build_market_evaluation_block",
    "compute_break_even_probability",
    "compute_candidate_top_picks",
    "compute_profit_1u",
    "evaluate_v35_market_outcome",
    "normalize_match_status",
]
