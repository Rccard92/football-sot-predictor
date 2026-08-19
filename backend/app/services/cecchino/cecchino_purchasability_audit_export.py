"""Export audit Acquistabilità fixture — read-only, contract v1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.schemas.cecchino_purchasability_v3 import PURCHASABILITY_V3_FORMULA_VERSION
from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION,
)
from app.services.cecchino.cecchino_constants import CECCHINO_BOOK_POLICY_VERSION
from app.services.cecchino.cecchino_historical_reliability import HISTORICAL_RELIABILITY_VERSION
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_VERSION
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    complement_definition_for,
    complement_selection_keys,
    complete_set_for,
    competitors_for_market,
    diagnostic_direct_comparators,
    market_family_for,
    market_label_for,
    period_and_line_for,
)
from app.services.cecchino.cecchino_purchasability_v31_snapshot import (
    index_purchasability_v31_snapshot_by_market,
)
from app.services.cecchino.cecchino_purchasability_v3_snapshot import (
    index_purchasability_v3_snapshot_by_market,
)

PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION = "cecchino_purchasability_audit_export_v1"

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
        "won",
        "lost",
        "hit",
    }
)


def _index_kpi_rows(panel: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(panel, dict):
        return out
    for row in panel.get("rows") or []:
        if not isinstance(row, dict):
            continue
        mk = row.get("market_key") or row.get("segno")
        if isinstance(mk, str) and mk:
            out[mk] = row
    return out


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if n != n else n  # NaN guard


def _book_context_entry(
    market_key: str,
    kpi_row: dict[str, Any] | None,
    v31_item: dict[str, Any] | None,
) -> dict[str, Any]:
    fair_audit = (
        (v31_item or {}).get("fair_book_audit")
        if isinstance((v31_item or {}).get("fair_book_audit"), dict)
        else {}
    )
    inp = (v31_item or {}).get("input") if isinstance((v31_item or {}).get("input"), dict) else {}
    kpi = kpi_row or {}

    fair_prob = _safe_float(
        fair_audit.get("selected_fair_probability")
        or fair_audit.get("fair_book_probability")
        or inp.get("fair_book_probability")
        or kpi.get("prob_book")
    )
    raw_prob = _safe_float(
        fair_audit.get("raw_probability")
        or fair_audit.get("implied_probability")
        or kpi.get("prob_book")
    )

    return {
        "quota": _safe_float(kpi.get("quota_book")),
        "fair_probability": fair_prob,
        "raw_probability": raw_prob,
        "source": kpi.get("book_source"),
        "bookmaker_name": kpi.get("bookmaker_name"),
        "provider_bookmaker_id": kpi.get("provider_bookmaker_id"),
        "book_source": kpi.get("book_source"),
        "book_fallback_used": kpi.get("book_fallback_used"),
    }


def _cecchino_context_entry(kpi_row: dict[str, Any] | None) -> dict[str, Any]:
    kpi = kpi_row or {}
    return {
        "quota": _safe_float(kpi.get("quota_cecchino")),
        "probability": _safe_float(kpi.get("prob_cecchino")),
        "edge": _safe_float(kpi.get("edge_pct")),
        "rating": kpi.get("rating"),
    }


def _kpi_raw_block(kpi_row: dict[str, Any] | None) -> dict[str, Any]:
    kpi = kpi_row or {}
    return {
        "quota_book": _safe_float(kpi.get("quota_book")),
        "book_source": kpi.get("book_source"),
        "bookmaker_name": kpi.get("bookmaker_name"),
        "provider_bookmaker_id": kpi.get("provider_bookmaker_id"),
        "book_fallback_used": kpi.get("book_fallback_used"),
        "quota_cecchino": _safe_float(kpi.get("quota_cecchino")),
        "prob_book": _safe_float(kpi.get("prob_book")),
        "prob_cecchino": _safe_float(kpi.get("prob_cecchino")),
        "vantaggio_prob": _safe_float(kpi.get("vantaggio_prob")),
        "edge_pct": _safe_float(kpi.get("edge_pct")),
        "rating": kpi.get("rating"),
        "score_acquisto": _safe_float(kpi.get("score_acquisto")),
    }


def _market_meta(
    market_key: str,
    kpi_row: dict[str, Any] | None,
    v31_item: dict[str, Any] | None,
) -> dict[str, Any]:
    v31 = v31_item or {}
    kpi = kpi_row or {}
    period, line = period_and_line_for(market_key)
    return {
        "market_key": market_key,
        "label": v31.get("label") or v31.get("market_label") or kpi.get("label") or market_label_for(market_key),
        "family": v31.get("market_family") or market_family_for(market_key),
        "period": v31.get("period") or period,
        "line": v31.get("line") if v31.get("line") is not None else line,
    }


def _relationships_block(market_key: str) -> dict[str, Any]:
    complete = complete_set_for(market_key)
    return {
        "complement_selection_keys": complement_selection_keys(market_key),
        "complement_definition": complement_definition_for(market_key),
        "family_competitors": competitors_for_market(market_key),
        "diagnostic_direct_comparators": diagnostic_direct_comparators(market_key),
        "complete_set": sorted(complete) if complete else None,
        "market_family": market_family_for(market_key),
    }


def _v31_export_block(v31_item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(v31_item, dict):
        return None
    theoretical = v31_item.get("theoretical") if isinstance(v31_item.get("theoretical"), dict) else {}
    return {
        "status": v31_item.get("status"),
        "score_v31": v31_item.get("score_v31"),
        "raw_score_v31": v31_item.get("raw_score_v31"),
        "class_v31": v31_item.get("class_v31") or v31_item.get("class"),
        "calculation_quality": v31_item.get("calculation_quality"),
        "gate": v31_item.get("gate"),
        "gate_reason_codes": list(v31_item.get("gate_reason_codes") or []),
        "reason_codes": list(v31_item.get("reason_codes") or []),
        "warnings": list(v31_item.get("warnings") or []),
        "input": v31_item.get("input"),
        "fair_book_audit": v31_item.get("fair_book_audit"),
        "theoretical": theoretical or None,
        "historical": v31_item.get("historical"),
        "formula_steps": list(v31_item.get("formula_steps") or []),
        "reading_short": v31_item.get("reading_short"),
        "reading_detailed": v31_item.get("reading_detailed"),
        "dependency_meta": v31_item.get("dependency_meta"),
        "value_score": v31_item.get("value_score") or theoretical.get("value_score"),
        "quality_score": v31_item.get("quality_score") or theoretical.get("theoretical_quality_score"),
        "formula_version": v31_item.get("formula_version"),
    }


def _v3_baseline_block(v3_item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(v3_item, dict):
        return None
    return {
        "status": v3_item.get("status"),
        "score_v3": v3_item.get("score") or v3_item.get("score_v3"),
        "raw_score_v3": v3_item.get("raw_score") or v3_item.get("raw_score_v3"),
        "class_v3": v3_item.get("class") or v3_item.get("class_v3"),
        "gate_status": v3_item.get("gate_status"),
        "gate_reason_codes": list(v3_item.get("gate_reason_codes") or []),
        "reason_codes": list(v3_item.get("reason_codes") or []),
        "reading_short": v3_item.get("reading_short"),
        "reading_detailed": v3_item.get("reading_detailed"),
        "formula_version": v3_item.get("formula_version"),
        "linked_market_context": v3_item.get("linked_market_context"),
    }


def _linked_relationships(v3_item: dict[str, Any] | None) -> list[Any] | None:
    if not isinstance(v3_item, dict):
        return None
    ctx = v3_item.get("linked_market_context")
    if ctx is None:
        return None
    if isinstance(ctx, list):
        return ctx
    if isinstance(ctx, dict):
        return [ctx]
    return None


def _fixture_block(row: CecchinoTodayFixture, v31_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snap = v31_snapshot if isinstance(v31_snapshot, dict) else {}
    snapshot_ts = snap.get("source_snapshot_at") or snap.get("generated_at")
    snapshot_verified = snap.get("source_snapshot_verified")
    if snapshot_verified is None:
        snapshot_verified = snap.get("source_snapshot_before_kickoff")

    kickoff = row.kickoff.isoformat() if row.kickoff else None
    scan_date = row.scan_date.isoformat() if row.scan_date else None

    return {
        "today_fixture_id": row.id,
        "provider_fixture_id": row.provider_fixture_id,
        "date": scan_date,
        "kickoff": kickoff,
        "league": row.league_name,
        "country": row.country_name,
        "season": row.provider_season,
        "home_team": row.home_team_name,
        "away_team": row.away_team_name,
        "snapshot_timestamp": snapshot_ts,
        "snapshot_timestamp_verified": snapshot_verified,
    }


def _source_versions_block(
    kpi_panel: dict[str, Any] | None,
    v31_snapshot: dict[str, Any] | None,
    v3_snapshot: dict[str, Any] | None,
    cecchino_output: dict[str, Any] | None,
) -> dict[str, Any]:
    kpi = kpi_panel if isinstance(kpi_panel, dict) else {}
    v31 = v31_snapshot if isinstance(v31_snapshot, dict) else {}
    v3 = v3_snapshot if isinstance(v3_snapshot, dict) else {}
    out = cecchino_output if isinstance(cecchino_output, dict) else {}

    signals_version: str | None = None
    signals = out.get("signals_matrix")
    if isinstance(signals, dict):
        signals_version = signals.get("version") or signals.get("contract_version")

    return {
        "kpi_contract_version": kpi.get("version") or KPI_V2_VERSION,
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
        "purchasability_v3_formula_version": v3.get("formula_version") or PURCHASABILITY_V3_FORMULA_VERSION,
        "purchasability_v31_formula_version": v31.get("formula_version") or PURCHASABILITY_V31_FORMULA_VERSION,
        "purchasability_v31_candidate_version": v31.get("candidate_version") or PURCHASABILITY_V31_CANDIDATE_VERSION,
        "historical_reliability_version": HISTORICAL_RELIABILITY_VERSION,
        "signals_version": signals_version,
    }


def _assert_no_post_match_leakage(payload: dict[str, Any]) -> None:
    """Sanity check interno — nessun campo risultato post-match nel payload."""

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in _POST_MATCH_EXCLUDE_KEYS:
                    raise ValueError(f"post_match_leakage at {path}.{k}")
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(payload)


def build_purchasability_audit_export(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    """Assembla export audit read-only da snapshot persistiti."""
    row = db.get(CecchinoTodayFixture, today_fixture_id)
    if row is None:
        return None

    kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
    cecchino_output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
    v31_snapshot = cecchino_output.get("purchasability_preview_v31")
    v3_snapshot = cecchino_output.get("purchasability_preview_v3")

    kpi_by_market = _index_kpi_rows(kpi_panel)
    v31_by_market = index_purchasability_v31_snapshot_by_market(v31_snapshot)
    v3_by_market = index_purchasability_v3_snapshot_by_market(v3_snapshot)

    book_context: dict[str, Any] = {}
    cecchino_context: dict[str, Any] = {}
    markets: dict[str, Any] = {}

    for mk in PANEL_MARKET_KEYS:
        kpi_row = kpi_by_market.get(mk)
        v31_item = v31_by_market.get(mk)
        v3_item = v3_by_market.get(mk)

        book_context[mk] = _book_context_entry(mk, kpi_row, v31_item)
        cecchino_context[mk] = _cecchino_context_entry(kpi_row)

        rel = _relationships_block(mk)
        linked = _linked_relationships(v3_item)

        market_entry: dict[str, Any] = {
            **_market_meta(mk, kpi_row, v31_item),
            "kpi_raw": _kpi_raw_block(kpi_row),
            "purchasability_v31": _v31_export_block(v31_item),
            "purchasability_v3_baseline": _v3_baseline_block(v3_item),
            **rel,
        }
        if linked is not None:
            market_entry["linked_relationships"] = linked
        markets[mk] = market_entry

    payload = make_json_safe(
        {
            "contract_version": PURCHASABILITY_AUDIT_EXPORT_CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fixture": _fixture_block(row, v31_snapshot if isinstance(v31_snapshot, dict) else None),
            "source_versions": _source_versions_block(kpi_panel, v31_snapshot, v3_snapshot, cecchino_output),
            "market_order": list(PANEL_MARKET_KEYS),
            "market_context": {
                "BOOK": book_context,
                "CECCHINO": cecchino_context,
            },
            "markets": markets,
        }
    )
    _assert_no_post_match_leakage(payload)
    return payload


def get_purchasability_audit_export(db: Session, today_fixture_id: int) -> dict[str, Any] | None:
    """Entry point API — alias esplicito."""
    return build_purchasability_audit_export(db, today_fixture_id)
