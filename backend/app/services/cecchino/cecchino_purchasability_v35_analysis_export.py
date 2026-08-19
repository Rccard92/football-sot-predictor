"""Export analysis Acquistabilità V3.5 fixture — frozen + post-match + evaluation read-only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v35 import (
    PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION,
)
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v35_analysis_evaluation import (
    build_market_evaluation_block,
    compute_candidate_top_picks,
    normalize_match_status,
)
from app.services.cecchino.cecchino_purchasability_v35_snapshot import (
    index_purchasability_v35_snapshot_by_market,
)
from app.services.cecchino.cecchino_signal_evaluation import match_result_from_fixture

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


def _assert_no_post_match_in_pre_match(payload: dict[str, Any]) -> None:
    """Verifica che pre_match non contenga campi post-match."""

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
    kickoff = row.kickoff.isoformat() if row.kickoff else None
    scan_date = row.scan_date.isoformat() if row.scan_date else None
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": int(row.provider_fixture_id),
        "scan_date": scan_date,
        "kickoff": kickoff,
        "country": row.country_name,
        "league": row.league_name,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
    }


def _pre_match_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    by_market = index_purchasability_v35_snapshot_by_market(snapshot)
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
        "candidate_registry_version": snapshot.get("candidate_registry_version"),
        "relation_registry_version": snapshot.get("relation_registry_version"),
        "experiment_version": snapshot.get("experiment_version"),
        "source_snapshot_at": snapshot.get("source_snapshot_at"),
        "kickoff": snapshot.get("kickoff"),
        "input_fingerprint_sha256": snapshot.get("input_fingerprint_sha256"),
        "engine_payload_sha256": snapshot.get("engine_payload_sha256"),
        "frozen_config": snapshot.get("frozen_config"),
        "candidate_registry": snapshot.get("candidate_registry"),
        "relation_registry": snapshot.get("relation_registry"),
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


def _build_analysis_summary(markets: dict[str, Any]) -> dict[str, Any]:
    scored = 0
    evaluated_scored = 0
    won = lost = pending = result_missing = not_evaluable = 0
    priced_settled = 0
    profit_sum = 0.0
    stake_count = 0

    for item in markets.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "") == "score":
            scored += 1
        ev = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
        outcome = ev.get("outcome")
        if str(item.get("status") or "") != "score":
            continue
        if outcome in {EVAL_WON, EVAL_LOST, EVAL_PENDING, EVAL_RESULT_MISSING, EVAL_NOT_EVALUABLE}:
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
            priced_settled += 1
            profit_sum += float(profit)
            stake_count += 1

    roi_pct = round((profit_sum / stake_count) * 100, 4) if stake_count else None

    return {
        "scored_market_count": scored,
        "evaluated_scored_count": evaluated_scored,
        "won_scored_count": won,
        "lost_scored_count": lost,
        "pending_scored_count": pending,
        "result_missing_scored_count": result_missing,
        "not_evaluable_scored_count": not_evaluable,
        "priced_settled_count": priced_settled,
        "profit_units_all_scored": round(profit_sum, 4) if stake_count else 0.0,
        "roi_pct_all_scored": roi_pct,
    }


def build_purchasability_v35_analysis_export(
    row: CecchinoTodayFixture,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Costruisce export analysis: frozen snapshot + post-match + evaluation."""
    pre_match = _pre_match_block(snapshot)
    _assert_no_post_match_in_pre_match(pre_match)

    frozen_markets = pre_match.get("markets") if isinstance(pre_match.get("markets"), dict) else {}
    markets: dict[str, Any] = {}
    for mk in PANEL_MARKET_KEYS:
        item = frozen_markets.get(mk)
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        enriched["evaluation"] = build_market_evaluation_block(item, row, market_key=mk)
        markets[mk] = enriched

    candidate_top_picks = compute_candidate_top_picks(markets)

    payload = make_json_safe(
        {
            "contract_version": PURCHASABILITY_V35_ANALYSIS_EXPORT_CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fixture": _fixture_block(row),
            "snapshot_integrity": {
                "valid": True,
                "engine_payload_sha256": snapshot.get("engine_payload_sha256"),
                "input_fingerprint_sha256": snapshot.get("input_fingerprint_sha256"),
            },
            "pre_match": pre_match,
            "post_match": _post_match_block(row),
            "markets": markets,
            "candidate_top_picks": candidate_top_picks,
            "analysis_summary": _build_analysis_summary(markets),
        }
    )
    return payload


__all__ = [
    "build_purchasability_v35_analysis_export",
]
