"""Preflight read-only replay Acquistabilità V3 su run storico Cecchino Lab.

STEP 3A: nessuna scrittura DB, nessun replay completo, nessuna nuova scansione.
Verifica copertura input congelati pre-match + probe diagnostico max 30 snapshot.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_historical_market_result import CecchinoLabHistoricalMarketResult
from app.models.cecchino_lab_historical_match_snapshot import CecchinoLabHistoricalMatchSnapshot
from app.models.cecchino_lab_historical_scan_run import (
    ACTIVE_STATUSES,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_WARNINGS,
    STATUS_FAILED,
    CecchinoLabHistoricalScanRun,
)
from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_AUDIT_VERSION,
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    calculate_purchasability_v3_batch,
)
from app.services.cecchino.cecchino_purchasability_v3_opposition import (
    DOUBLE_CHANCE_MARKETS,
    FAMILY_DOUBLE_CHANCE,
    FAMILY_GOALS_FT_2_5,
    FAMILY_MATCH_WINNER_FT,
    GOALS_FT_2_5_MARKETS,
    MATCH_WINNER_FT_MARKETS,
    SUPPORTED_V3_MARKETS,
    is_v3_supported_market,
    linked_market_key_for,
    market_family_for,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.historical_eligibility import ELIGIBLE_CORE
from app.services.cecchino_data_lab.historical_scan_service import _run_scope_meta
from app.services.cecchino_data_lab.revision_resolve import resolve_code_revision

PREFLIGHT_SCHEMA_VERSION = "cecchino_lab_purchasability_v3_replay_preflight_v1"
FAIR_SUM_TOLERANCE = 1e-4
PROBE_SNAPSHOT_LIMIT = 30
PROBE_BUCKET_SIZE = 10
MAX_EXAMPLES_PER_REASON = 20
MAX_PROBLEMATIC_SNAPSHOTS = 20
CACHE_TTL_COMPLETED_S = 300.0
CACHE_TTL_BLOCKED_S = 60.0
CACHE_MAX_ENTRIES = 64

STATUS_READY = "ready"
STATUS_READY_WITH_WARNINGS = "ready_with_warnings"
STATUS_BLOCKED = "blocked"

ALLOWED_RUN_STATUSES = frozenset({STATUS_COMPLETED, STATUS_COMPLETED_WITH_WARNINGS})

V3_MARKET_ORDER: tuple[str, ...] = (
    SEL_HOME,
    SEL_DRAW,
    SEL_AWAY,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_ONE_X,
    SEL_X_TWO,
    SEL_ONE_TWO,
)

FAMILY_ORDER: tuple[str, ...] = (
    FAMILY_MATCH_WINNER_FT,
    FAMILY_GOALS_FT_2_5,
    FAMILY_DOUBLE_CHANCE,
)

FAMILY_MEMBERS: dict[str, frozenset[str]] = {
    FAMILY_MATCH_WINNER_FT: MATCH_WINNER_FT_MARKETS,
    FAMILY_GOALS_FT_2_5: GOALS_FT_2_5_MARKETS,
    FAMILY_DOUBLE_CHANCE: DOUBLE_CHANCE_MARKETS,
}

# Opposti richiesti per score (DRAW richiede entrambi i laterali).
OPPOSITE_REQUIREMENTS: dict[str, frozenset[str]] = {
    SEL_HOME: frozenset({SEL_AWAY}),
    SEL_AWAY: frozenset({SEL_HOME}),
    SEL_DRAW: frozenset({SEL_HOME, SEL_AWAY}),
    SEL_OVER_2_5: frozenset({SEL_UNDER_2_5}),
    SEL_UNDER_2_5: frozenset({SEL_OVER_2_5}),
    SEL_ONE_X: frozenset({SEL_AWAY}),
    SEL_X_TWO: frozenset({SEL_HOME}),
    SEL_ONE_TWO: frozenset({SEL_DRAW}),
}

PRE_MATCH_INPUT_FIELDS = (
    "run_id",
    "snapshot_id",
    "lab_match_id",
    "market_key",
    "family",
    "kickoff_at",
    "pre_match_locked_at",
    "pre_match_payload_sha256",
    "quota_book",
    "quota_cecchino",
    "prob_book_raw",
    "prob_book_fair",
    "prob_cecchino",
    "edge_pct",
    "vantaggio_prob",
    "quote_source_type",
    "is_real_book_quote",
    "is_derived_quote",
    "derivation_method",
    "evaluation_status",
)

POST_MATCH_PERFORMANCE_FIELDS = (
    "won",
    "profit_1u_real",
    "profit_1u_synthetic",
    "result_reason",
    "evaluation_status",
    "result_json",
    "settlement_status",
    "settlement_summary_json",
)

FORBIDDEN_FORMULA_FIELDS = (
    "result_json",
    "won",
    "profit_1u_real",
    "profit_1u_synthetic",
    "settlement_status",
    "settlement_summary_json",
    "ft_result",
    "ht_result",
    "home_score_ft",
    "away_score_ft",
    "home_score_ht",
    "away_score_ht",
)

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def clear_purchasability_v3_replay_preflight_cache() -> None:
    """Solo per test."""
    with _cache_lock:
        _cache.clear()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cache_get(key: str) -> Any | None:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        expires, value = item
        if expires < now:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: float) -> None:
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) >= CACHE_MAX_ENTRIES:
            expired = [k for k, (exp, _) in _cache.items() if exp < now]
            for k in expired:
                _cache.pop(k, None)
            while len(_cache) >= CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                _cache.pop(oldest, None)
        _cache[key] = (now + ttl, value)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    out.update(extra)
    return out


def _empty_market_bucket() -> dict[str, Any]:
    return {
        "eligible_rows": 0,
        "exact_replay_ready": 0,
        "ready_with_warning": 0,
        "gate_only_ready": 0,
        "not_replayable": 0,
        "invalid_pre_match_integrity": 0,
        "ambiguous_market_join": 0,
        "unsupported_market": 0,
        "quote_real": 0,
        "quote_derived": 0,
        "quote_unavailable": 0,
        "quote_inconsistent": 0,
        "performance_real_ready": 0,
        "performance_synthetic_ready": 0,
        "performance_result_without_profit": 0,
        "performance_not_applicable": 0,
    }


def _empty_family_bucket() -> dict[str, Any]:
    return {
        "snapshots_with_full_family": 0,
        "snapshots_with_partial_family": 0,
        "snapshots_with_missing_family": 0,
        "exact_replay_ready": 0,
        "ready_with_warning": 0,
        "not_replayable": 0,
        "family_decisions_theoretical": 0,
    }


def _empty_competition_bucket() -> dict[str, Any]:
    return {
        "snapshots_eligible": 0,
        "exact_replay_ready": 0,
        "missing_inputs": 0,
        "quote_real": 0,
        "quote_derived": 0,
        "performance_ready": 0,
        "blockers": 0,
    }


def _example_store() -> dict[str, list[dict[str, Any]]]:
    return defaultdict(list)


def _push_example(
    store: dict[str, list[dict[str, Any]]],
    reason: str,
    example: dict[str, Any],
) -> None:
    bucket = store[reason]
    if len(bucket) < MAX_EXAMPLES_PER_REASON:
        bucket.append(example)


def _quota_valid(quota: float | None) -> bool:
    return quota is not None and quota > 1.0


def classify_quote_quality(m: Any) -> tuple[str, list[str]]:
    """Ritorna (real|derived|unavailable|inconsistent, reason_codes)."""
    real = bool(getattr(m, "is_real_book_quote", False))
    derived = bool(getattr(m, "is_derived_quote", False))
    quota = _safe_float(getattr(m, "quota_book", None))
    derivation = getattr(m, "derivation_method", None)
    profit_real = _safe_float(getattr(m, "profit_1u_real", None))
    profit_synth = _safe_float(getattr(m, "profit_1u_synthetic", None))
    reasons: list[str] = []

    if real and derived:
        reasons.append("real_and_derived_both_true")
    if real and not _quota_valid(quota):
        reasons.append("real_flag_without_valid_quota")
    if derived and not derivation:
        reasons.append("derived_without_derivation_method")
    if derived and profit_real is not None:
        reasons.append("profit_real_on_derived_quote")
    if real and profit_synth is not None and profit_real is None:
        reasons.append("profit_synthetic_on_real_without_real_profit")

    if reasons:
        return "inconsistent", reasons

    if real and not derived and _quota_valid(quota):
        return "real", []
    if derived:
        return "derived", []
    if not _quota_valid(quota):
        return "unavailable", ["quota_unavailable"]
    return "unavailable", ["quote_flags_unavailable"]


def classify_performance(m: Any, quote_class: str) -> str:
    won = getattr(m, "won", None)
    profit_real = _safe_float(getattr(m, "profit_1u_real", None))
    profit_synth = _safe_float(getattr(m, "profit_1u_synthetic", None))
    eval_status = getattr(m, "evaluation_status", None)

    if quote_class == "real" and profit_real is not None and won is not None:
        return "real_profit_ready"
    if quote_class == "derived" and profit_synth is not None and won is not None:
        return "synthetic_profit_ready"
    if won is not None or eval_status in ("won", "lost", "settled"):
        if profit_real is None and profit_synth is None:
            return "result_available_but_profit_missing"
    if won is None and profit_real is None and profit_synth is None:
        return "not_applicable"
    if profit_real is not None:
        return "real_profit_ready"
    if profit_synth is not None:
        return "synthetic_profit_ready"
    return "not_applicable"


def _opposite_keys_present(market_key: str, by_mk: dict[str, Any]) -> tuple[bool, list[str]]:
    required = OPPOSITE_REQUIREMENTS.get(market_key, frozenset())
    missing = [k for k in sorted(required) if k not in by_mk]
    return len(missing) == 0, missing


def _family_completeness(family: str | None, by_mk: dict[str, Any]) -> str:
    if family is None:
        return "missing"
    members = FAMILY_MEMBERS.get(family, frozenset())
    present = sum(1 for m in members if m in by_mk)
    if present == len(members):
        return "full"
    if present == 0:
        return "missing"
    return "partial"


def _pre_match_integrity(snap: Any) -> tuple[str, list[str]]:
    """Ritorna (ok|invalid|missing, reason_codes)."""
    reasons: list[str] = []
    sha = getattr(snap, "pre_match_payload_sha256", None)
    locked = getattr(snap, "pre_match_locked_at", None)
    kickoff = getattr(snap, "kickoff_at", None)

    if not sha:
        reasons.append("missing_pre_match_hash")
    if locked is None:
        reasons.append("missing_pre_match_lock")
    if kickoff is None:
        reasons.append("missing_kickoff")

    if locked is not None and kickoff is not None:
        try:
            # Confronta timezone-aware se possibile
            lk = locked
            ko = kickoff
            if getattr(lk, "tzinfo", None) is None and getattr(ko, "tzinfo", None) is not None:
                lk = lk.replace(tzinfo=timezone.utc)
            if getattr(ko, "tzinfo", None) is None and getattr(lk, "tzinfo", None) is not None:
                ko = ko.replace(tzinfo=timezone.utc)
            if lk >= ko:
                reasons.append("lock_not_before_kickoff")
        except Exception:
            reasons.append("lock_kickoff_not_comparable")

    if "lock_not_before_kickoff" in reasons:
        return "invalid", reasons
    if reasons:
        # Hash/lock assenti: warning strutturale gestito a livello aggregato;
        # per singola valutazione non blocca se altri input score ci sono.
        return "missing", reasons
    return "ok", []


def build_adapter_panel_row(m: Any) -> dict[str, Any]:
    """Costruisce una panel row compatibile V3 (solo campi pre-match)."""
    quote_class, _ = classify_quote_quality(m)
    source_type = getattr(m, "quote_source_type", None) or "historical_bet365"
    if str(source_type).startswith("bet365") or source_type in (
        "bet365_closing",
        "bet365_pre_fallback",
        "derived_from_bet365_1x2_closing",
        "derived_from_bet365_1x2_pre",
    ):
        quote_source = f"historical_{source_type}" if not str(source_type).startswith("historical_") else source_type
    else:
        quote_source = "historical_bet365"

    derived = quote_class == "derived" or bool(getattr(m, "is_derived_quote", False))
    return {
        "market_key": getattr(m, "market_key", None),
        "edge_pct": _safe_float(getattr(m, "edge_pct", None)),
        "vantaggio_prob": _safe_float(getattr(m, "vantaggio_prob", None)),
        "prob_cecchino": _safe_float(getattr(m, "prob_cecchino", None)),
        "quota_book": _safe_float(getattr(m, "quota_book", None)),
        "quota_cecchino": _safe_float(getattr(m, "quota_cecchino", None)),
        "quote_source": quote_source,
        "odds_source": quote_source,
        "book_source": quote_source,
        "derived_quote": derived,
        "not_real_book_quote": derived or quote_class != "real",
        "force_derived_quote": derived and market_family_for(str(getattr(m, "market_key", "") or "")) == FAMILY_DOUBLE_CHANCE,
    }


def adapter_contract_payload() -> dict[str, Any]:
    return {
        "source_fields": [
            "MarketResult.market_key",
            "MarketResult.edge_pct",
            "MarketResult.vantaggio_prob",
            "MarketResult.prob_cecchino",
            "MarketResult.quota_book",
            "MarketResult.quota_cecchino",
            "MarketResult.prob_book_fair",
            "MarketResult.quote_source_type",
            "MarketResult.is_real_book_quote",
            "MarketResult.is_derived_quote",
            "MarketResult.derivation_method",
            "snapshot.pre_match_payload_sha256",
            "snapshot.pre_match_locked_at",
            "snapshot.kickoff_at",
            "snapshot.historical_kpi_json.rows (diagnostic fallback)",
        ],
        "target_fields": [
            "kpi_panel.rows[].market_key",
            "kpi_panel.rows[].edge_pct",
            "kpi_panel.rows[].vantaggio_prob",
            "kpi_panel.rows[].prob_cecchino",
            "kpi_panel.rows[].quota_book",
            "kpi_panel.rows[].quota_cecchino",
            "kpi_panel.rows[].quote_source",
            "kpi_panel.rows[].odds_source",
            "kpi_panel.rows[].derived_quote",
            "kpi_panel.rows[].not_real_book_quote",
        ],
        "required_transformations": [
            "map quote_source_type Bet365 → quote_source/odds_source historical_* (mai betfair_panel)",
            "set derived_quote/not_real_book_quote from MarketResult flags",
            "build family panel from same-snapshot MarketResult rows only",
            "pass panel to calculate_purchasability_v3_batch without result/settlement fields",
        ],
        "unit_conversions": {
            "edge_pct": {
                "stored": "percentage_points",
                "example": 20.0,
                "v3_expects": "percentage (same)",
                "conversion_in_adapter": "none",
            },
            "vantaggio_prob": {
                "stored": "fraction_typical_lab",
                "example": 0.05,
                "v3_expects": "fraction (|v|<=1 → pp=v*100) or already pp",
                "conversion_in_adapter": "none_passthrough",
            },
            "prob_cecchino": {
                "stored": "fraction_0_1",
                "v3_expects": "fraction_0_1_or_percent_1_100",
                "conversion_in_adapter": "none",
            },
            "prob_book_fair": {
                "stored": "fraction_0_1",
                "v3_usage": "preflight_coherence_only; V3 recomputes fair from quota_book",
                "conversion_in_adapter": "none",
            },
        },
        "preserved_values": [
            "edge_pct",
            "vantaggio_prob",
            "prob_cecchino",
            "quota_book",
            "quota_cecchino",
            "frozen_prob_book_fair_for_diagnostics",
        ],
        "forbidden_recalculations": [
            "kpi_recalculation",
            "cecchino_model_recalculation",
            "signal_recalculation",
            "balance_recalculation",
            "goal_intensity_recalculation",
            "external_api_odds_fetch",
            "settlement_rewrite",
            "snapshot_mutation",
            "market_result_mutation",
        ],
        "historical_quote_source_label": "historical_bet365",
        "today_default_to_avoid": "betfair_panel",
        "formula_invocation": "calculate_purchasability_v3_batch(kpi_panel=..., fixture_meta=...)",
    }


def classify_score_replay(
    *,
    market_key: str,
    m: Any | None,
    by_mk: dict[str, Any],
    integrity: str,
    integrity_reasons: list[str],
    duplicate: bool,
) -> tuple[str, list[str]]:
    if not is_v3_supported_market(market_key):
        return "unsupported_market", ["unsupported_market"]

    if duplicate:
        return "ambiguous_market_join", ["duplicate_market_key"]

    if integrity == "invalid":
        return "invalid_pre_match_integrity", list(integrity_reasons)

    if m is None:
        return "not_replayable_missing_inputs", ["market_row_missing"]

    reasons: list[str] = []
    edge = _safe_float(getattr(m, "edge_pct", None))
    vant = _safe_float(getattr(m, "vantaggio_prob", None))
    prob_c = _safe_float(getattr(m, "prob_cecchino", None))
    quota_c = _safe_float(getattr(m, "quota_cecchino", None))
    quota_b = _safe_float(getattr(m, "quota_book", None))
    fair = _safe_float(getattr(m, "prob_book_fair", None))
    quote_class, quote_reasons = classify_quote_quality(m)
    reasons.extend(quote_reasons)

    opp_ok, opp_missing = _opposite_keys_present(market_key, by_mk)
    family = market_family_for(market_key)
    fam_status = _family_completeness(family, by_mk)
    linked_mk, _ = linked_market_key_for(market_key)
    linked_present = linked_mk is None or linked_mk in by_mk

    gate_ok = edge is not None and vant is not None
    score_core = (
        gate_ok
        and prob_c is not None
        and (_quota_valid(quota_b) or quote_class == "derived")
        and (fair is not None or _quota_valid(quota_b))
        and opp_ok
        and quote_class in ("real", "derived")
    )

    if integrity == "missing":
        # hash/lock assenti: ancora scoreabile con warning se core ok
        if score_core:
            return "score_replay_ready_with_warning", reasons + integrity_reasons + ["pre_match_integrity_incomplete"]
        if gate_ok:
            return "gate_only_replay_ready", reasons + ["missing_score_inputs"] + integrity_reasons
        return "not_replayable_missing_inputs", reasons + ["missing_gate_inputs"] + integrity_reasons

    if not gate_ok:
        missing = []
        if edge is None:
            missing.append("missing_edge_pct")
        if vant is None:
            missing.append("missing_vantaggio_prob")
        return "not_replayable_missing_inputs", reasons + missing

    if not score_core:
        if prob_c is None:
            reasons.append("missing_prob_cecchino")
        if not _quota_valid(quota_b) and quote_class != "derived":
            reasons.append("missing_quota_book")
        if fair is None and not _quota_valid(quota_b):
            reasons.append("missing_prob_book_fair")
        if not opp_ok:
            reasons.append(f"missing_opposite:{','.join(opp_missing)}")
        if quote_class == "unavailable":
            reasons.append("quote_unavailable")
        if quote_class == "inconsistent":
            return "not_replayable_missing_inputs", reasons
        return "gate_only_replay_ready", reasons

    warnings: list[str] = []
    if fam_status != "full":
        warnings.append(f"family_{fam_status}")
    if not linked_present:
        warnings.append("linked_context_absent")
    if quote_class == "derived":
        warnings.append("derived_quote_diagnostic_only")
    if quota_c is None:
        warnings.append("missing_quota_cecchino_diagnostic")

    if warnings:
        return "score_replay_ready_with_warning", warnings
    return "exact_replay_ready", []


def _fair_group_status(values: list[float | None]) -> str:
    if any(v is None for v in values):
        return "fair_group_missing"
    assert all(v is not None for v in values)
    nums = [float(v) for v in values]  # type: ignore[arg-type]
    if any(not math.isfinite(v) for v in nums):
        return "fair_group_non_finite"
    if any(v < 0.0 or v > 1.0 for v in nums):
        return "fair_group_out_of_range"
    total = sum(nums)
    if abs(total - 1.0) <= FAIR_SUM_TOLERANCE:
        return "fair_group_valid"
    return "fair_group_out_of_tolerance"


def _select_probe_snapshot_ids(eligible_snaps: list[Any]) -> list[int]:
    if not eligible_snaps:
        return []
    ordered = sorted(
        eligible_snaps,
        key=lambda s: (
            getattr(s, "kickoff_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            int(getattr(s, "chronological_order", 0) or 0),
            int(s.id),
        ),
    )
    n = len(ordered)
    if n <= PROBE_SNAPSHOT_LIMIT:
        return [int(s.id) for s in ordered]

    first = ordered[:PROBE_BUCKET_SIZE]
    last = ordered[-PROBE_BUCKET_SIZE:]
    mid_start = max(0, (n // 2) - (PROBE_BUCKET_SIZE // 2))
    mid = ordered[mid_start : mid_start + PROBE_BUCKET_SIZE]
    seen: set[int] = set()
    out: list[int] = []
    for s in first + mid + last:
        sid = int(s.id)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out[:PROBE_SNAPSHOT_LIMIT]


def _run_probe(
    *,
    eligible_snaps: list[Any],
    markets_by_snap: dict[int, list[Any]],
) -> dict[str, Any]:
    ids = _select_probe_snapshot_ids(eligible_snaps)
    snap_by_id = {int(s.id): s for s in eligible_snaps}
    counts = {
        "snapshots_probed": 0,
        "markets_scored": 0,
        "markets_gate_failed": 0,
        "markets_unavailable": 0,
        "markets_error": 0,
        "markets_not_applicable": 0,
    }
    errors: list[dict[str, Any]] = []

    for sid in ids:
        snap = snap_by_id.get(sid)
        if snap is None:
            continue
        rows_src = markets_by_snap.get(sid, [])
        panel_rows = [
            build_adapter_panel_row(m)
            for m in rows_src
            if is_v3_supported_market(str(getattr(m, "market_key", "") or ""))
        ]
        # Anti-leakage: nessuna chiave risultato nel panel
        for row in panel_rows:
            for forbidden in FORBIDDEN_FORMULA_FIELDS:
                assert forbidden not in row

        try:
            result = calculate_purchasability_v3_batch(
                kpi_panel={"rows": panel_rows},
                fixture_meta={
                    "snapshot_at": (
                        snap.pre_match_locked_at.isoformat()
                        if getattr(snap, "pre_match_locked_at", None)
                        else None
                    ),
                    "lab_snapshot_id": sid,
                    "quote_source_profile": "historical_bet365",
                },
            )
            make_json_safe(result)
            counts["snapshots_probed"] += 1
            items = result.get("items") if isinstance(result, dict) else None
            if not isinstance(items, list):
                items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "")
                gate = _as_dict(item.get("gate"))
                gate_status = str(gate.get("gate_status") or "")
                if status == "available" and item.get("score") is not None:
                    counts["markets_scored"] += 1
                elif gate_status.startswith("failed"):
                    counts["markets_gate_failed"] += 1
                elif status == "unavailable":
                    counts["markets_unavailable"] += 1
                elif status == "not_applicable" or gate_status == "unsupported_market":
                    counts["markets_not_applicable"] += 1
                else:
                    counts["markets_unavailable"] += 1
        except Exception as exc:  # noqa: BLE001 — probe diagnostico
            counts["markets_error"] += 1
            if len(errors) < MAX_EXAMPLES_PER_REASON:
                errors.append({"snapshot_id": sid, "error": str(exc)[:300]})

    return {
        "probe_is_diagnostic_only": True,
        "probe_not_a_backtest": True,
        "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
        "probe_selected_snapshot_ids": ids,
        "probe_selection_rule": "first_10_chrono + mid_10 + last_10",
        "invoked_v3_formula": True,
        "persisted_results": False,
        **counts,
        "errors": errors,
    }


def _blocked_payload(
    *,
    run: CecchinoLabHistoricalScanRun,
    runtime_rev: dict[str, Any],
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scope = _run_scope_meta(run)
    base = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "status": STATUS_BLOCKED,
        "generated_at": _utcnow().isoformat(),
        "run": {
            "run_id": int(run.id),
            "season_label": run.season_label,
            "status": run.status,
            "run_scope": scope.get("run_scope"),
            "is_partial_run": bool(scope.get("is_partial_run")),
            "not_full_season_report": bool(scope.get("not_full_season_report")),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "source_git_commit": run.source_git_commit,
            "source_revision_status": getattr(run, "source_revision_status", None),
            "scan_version": run.scan_version,
        },
        "formula": {
            "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
            "runtime_git_commit": runtime_rev.get("git_commit"),
            "runtime_git_commit_source": runtime_rev.get("git_commit_source"),
            "historical_profile_used": False,
            "fixed_scales_used": True,
        },
        "bookmakers": {
            "historical": "Bet365",
            "today_operational": "Betfair",
            "providers_are_different": True,
            "bookmaker_parity_status": "different_provider_expected",
            "formula_provider_dependency": "book_agnostic_with_fair_probability_inputs",
        },
        "source_integrity": {},
        "workload": {
            "supported_markets_per_snapshot": 8,
            "theoretical_evaluations": 0,
            "market_rows_found": 0,
            "exact_replay_ready": 0,
            "ready_with_warning": 0,
            "gate_only_ready": 0,
            "not_replayable": 0,
            "family_decisions_theoretical": 0,
        },
        "input_coverage": {},
        "by_market": {mk: _empty_market_bucket() for mk in V3_MARKET_ORDER},
        "by_family": {fam: _empty_family_bucket() for fam in FAMILY_ORDER},
        "by_competition": {},
        "quote_quality": {
            "real": 0,
            "derived": 0,
            "unavailable": 0,
            "inconsistent_flags": 0,
        },
        "fair_probability_checks": {
            "fair_sum_tolerance": FAIR_SUM_TOLERANCE,
            "fair_group_valid": 0,
            "fair_group_missing": 0,
            "fair_group_out_of_tolerance": 0,
            "fair_group_non_finite": 0,
            "fair_group_out_of_range": 0,
            "double_chance_derivation_ok": 0,
            "double_chance_derivation_missing": 0,
        },
        "performance_coverage": {
            "real_profit_ready": 0,
            "synthetic_profit_ready": 0,
            "result_available_but_profit_missing": 0,
            "not_applicable": 0,
        },
        "adapter_contract": adapter_contract_payload(),
        "anti_leakage": {
            "pre_match_input_fields": list(PRE_MATCH_INPUT_FIELDS),
            "post_match_performance_fields": list(POST_MATCH_PERFORMANCE_FIELDS),
            "forbidden_formula_fields": list(FORBIDDEN_FORMULA_FIELDS),
            "anti_leakage_status": "enforced_in_preflight_contract",
            "result_fields_passed_to_formula": False,
            "settlement_fields_passed_to_formula": False,
        },
        "probe": {
            "probe_is_diagnostic_only": True,
            "probe_not_a_backtest": True,
            "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
            "skipped": True,
            "reason": "run_blocked",
        },
        "blockers": blockers,
        "warnings": warnings or [],
        "status_rules": {
            "blocked_if": [
                "run_not_in_completed_or_completed_with_warnings",
                "zero_eligible_core",
                "structural_duplicate_market_keys",
                "structural_pre_match_integrity_absent",
                "mandatory_inputs_missing_almost_all",
                "fair_probabilities_structurally_incoherent",
                "real_derived_indistinguishable",
                "adapter_non_deterministic",
            ],
            "ready_with_warnings_if": [
                "replay_possible_with_incomplete_coverage",
                "partial_run",
                "derived_quotes_diagnostic_only",
                "linked_context_absent",
            ],
            "ready_if": [
                "no_blockers",
                "deterministic_replay",
                "mandatory_inputs_available",
                "coverage_losses_only_expected_unavailable_markets",
            ],
        },
        "issue_examples": {},
        "problematic_snapshots": [],
        "replay_recommendation": {
            "can_replay_without_full_scan": False,
            "requires_new_external_data": False,
            "requires_model_recalculation": False,
            "requires_database_migration": False,
            "recommended_next_action": "resolve_blockers",
        },
    }
    if extra:
        base.update(extra)
    return make_json_safe(base)


def _compute_preflight(db: Session, run_id: int) -> dict[str, Any]:
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    runtime_rev = resolve_code_revision()
    scope = _run_scope_meta(run)
    is_partial = bool(scope.get("is_partial_run"))

    if run.status in ACTIVE_STATUSES:
        return _blocked_payload(
            run=run,
            runtime_rev=runtime_rev,
            blockers=[
                _issue(
                    "run_active",
                    "Il run è ancora attivo: preflight consentito solo come blocked, replay non pronto.",
                    run_status=run.status,
                )
            ],
        )

    if run.status in (STATUS_FAILED, STATUS_CANCELLED):
        return _blocked_payload(
            run=run,
            runtime_rev=runtime_rev,
            blockers=[
                _issue(
                    "run_terminal_incompatible",
                    f"Run in stato {run.status}: replay non affidabile.",
                    run_status=run.status,
                )
            ],
        )

    if run.status not in ALLOWED_RUN_STATUSES:
        return _blocked_payload(
            run=run,
            runtime_rev=runtime_rev,
            blockers=[
                _issue(
                    "run_status_unsupported",
                    f"Stato run non ammesso al preflight: {run.status}",
                    run_status=run.status,
                )
            ],
        )

    snaps = list(
        db.scalars(
            select(CecchinoLabHistoricalMatchSnapshot).where(
                CecchinoLabHistoricalMatchSnapshot.run_id == int(run.id)
            )
        ).all()
    )
    markets = list(
        db.scalars(
            select(CecchinoLabHistoricalMarketResult).where(
                CecchinoLabHistoricalMarketResult.run_id == int(run.id)
            )
        ).all()
    )

    eligible = [s for s in snaps if s.historical_eligibility_status == ELIGIBLE_CORE]
    excluded = [s for s in snaps if s.historical_eligibility_status != ELIGIBLE_CORE]
    exclusions_by_reason: dict[str, int] = defaultdict(int)
    for s in excluded:
        key = s.historical_eligibility_reason or s.historical_eligibility_status or "unknown"
        exclusions_by_reason[str(key)] += 1

    if not eligible:
        return _blocked_payload(
            run=run,
            runtime_rev=runtime_rev,
            blockers=[
                _issue(
                    "zero_eligible_core",
                    "Nessuno snapshot eligible_core: replay non possibile senza nuova scansione.",
                )
            ],
            extra={
                "source_integrity": {
                    "snapshots_total": len(snaps),
                    "snapshots_eligible_core": 0,
                    "snapshots_excluded": len(excluded),
                    "exclusions_by_reason": dict(exclusions_by_reason),
                }
            },
        )

    markets_by_snap: dict[int, list[Any]] = defaultdict(list)
    for m in markets:
        markets_by_snap[int(m.match_snapshot_id)].append(m)

    example_store = _example_store()
    problematic_snaps: list[dict[str, Any]] = []
    by_market = {mk: _empty_market_bucket() for mk in V3_MARKET_ORDER}
    by_family = {fam: _empty_family_bucket() for fam in FAMILY_ORDER}
    by_competition: dict[str, dict[str, Any]] = defaultdict(_empty_competition_bucket)

    workload = {
        "supported_markets_per_snapshot": 8,
        "theoretical_evaluations": len(eligible) * 8,
        "market_rows_found": 0,
        "exact_replay_ready": 0,
        "ready_with_warning": 0,
        "gate_only_ready": 0,
        "not_replayable": 0,
        "invalid_pre_match_integrity": 0,
        "ambiguous_market_join": 0,
        "unsupported_market_rows": 0,
        "family_decisions_theoretical": len(eligible) * 3,
    }

    quote_quality = {
        "real": 0,
        "derived": 0,
        "unavailable": 0,
        "inconsistent_flags": 0,
    }
    fair_checks = {
        "fair_sum_tolerance": FAIR_SUM_TOLERANCE,
        "fair_group_valid": 0,
        "fair_group_missing": 0,
        "fair_group_out_of_tolerance": 0,
        "fair_group_non_finite": 0,
        "fair_group_out_of_range": 0,
        "double_chance_derivation_ok": 0,
        "double_chance_derivation_missing": 0,
    }
    performance_coverage = {
        "real_profit_ready": 0,
        "synthetic_profit_ready": 0,
        "result_available_but_profit_missing": 0,
        "not_applicable": 0,
    }
    input_coverage = {
        "with_edge_pct": 0,
        "with_vantaggio_prob": 0,
        "with_prob_cecchino": 0,
        "with_quota_book": 0,
        "with_quota_cecchino": 0,
        "with_prob_book_fair": 0,
        "with_opposite": 0,
        "with_family_full": 0,
    }

    integrity_counts = {
        "snapshots_total": len(snaps),
        "snapshots_eligible_core": len(eligible),
        "snapshots_excluded": len(excluded),
        "exclusions_by_reason": dict(exclusions_by_reason),
        "with_pre_match_hash": 0,
        "with_pre_match_lock": 0,
        "lock_before_kickoff": 0,
        "invalid_lock_timestamp": 0,
        "duplicate_market_keys": 0,
        "snapshots_with_duplicates": 0,
    }

    structural_duplicates = False
    structural_integrity_absent = False
    hash_present = 0
    lock_present = 0

    for snap in eligible:
        sid = int(snap.id)
        comp = str(snap.competition_name or "unknown")
        by_competition[comp]["snapshots_eligible"] += 1

        integrity, integrity_reasons = _pre_match_integrity(snap)
        if getattr(snap, "pre_match_payload_sha256", None):
            integrity_counts["with_pre_match_hash"] += 1
            hash_present += 1
        if getattr(snap, "pre_match_locked_at", None):
            integrity_counts["with_pre_match_lock"] += 1
            lock_present += 1
        if integrity == "ok":
            integrity_counts["lock_before_kickoff"] += 1
        if "lock_not_before_kickoff" in integrity_reasons:
            integrity_counts["invalid_lock_timestamp"] += 1

        rows = markets_by_snap.get(sid, [])
        # Index by market_key; detect duplicates
        keyed: dict[str, list[Any]] = defaultdict(list)
        for m in rows:
            keyed[str(m.market_key)].append(m)

        duplicate_keys = {k for k, v in keyed.items() if len(v) > 1}
        if duplicate_keys:
            structural_duplicates = True
            integrity_counts["duplicate_market_keys"] += len(duplicate_keys)
            integrity_counts["snapshots_with_duplicates"] += 1
            if len(problematic_snaps) < MAX_PROBLEMATIC_SNAPSHOTS:
                problematic_snaps.append(
                    {
                        "snapshot_id": sid,
                        "competition_name": comp,
                        "reason": "duplicate_market_keys",
                        "keys": sorted(duplicate_keys)[:8],
                    }
                )

        by_mk_single: dict[str, Any] = {
            k: v[0] for k, v in keyed.items() if len(v) == 1
        }
        # For supported markets still present once among duplicates, keep first only for opposite checks
        by_mk_for_opp = {k: v[0] for k, v in keyed.items()}

        # Fair family checks
        for fam, members in (
            (FAMILY_MATCH_WINNER_FT, (SEL_HOME, SEL_DRAW, SEL_AWAY)),
            (FAMILY_GOALS_FT_2_5, (SEL_OVER_2_5, SEL_UNDER_2_5)),
        ):
            vals = [
                _safe_float(getattr(by_mk_for_opp[m], "prob_book_fair", None))
                if m in by_mk_for_opp
                else None
                for m in members
            ]
            status = _fair_group_status(vals)
            fair_checks[status] = fair_checks.get(status, 0) + 1

        for mk in DOUBLE_CHANCE_MARKETS:
            if mk not in by_mk_for_opp:
                continue
            m = by_mk_for_opp[mk]
            if getattr(m, "derivation_method", None) and bool(getattr(m, "is_derived_quote", False)):
                fair_checks["double_chance_derivation_ok"] += 1
            else:
                fair_checks["double_chance_derivation_missing"] += 1

        # Family completeness per family
        for fam in FAMILY_ORDER:
            fam_status = _family_completeness(fam, by_mk_for_opp)
            if fam_status == "full":
                by_family[fam]["snapshots_with_full_family"] += 1
                input_coverage["with_family_full"] += 1
            elif fam_status == "partial":
                by_family[fam]["snapshots_with_partial_family"] += 1
            else:
                by_family[fam]["snapshots_with_missing_family"] += 1
            by_family[fam]["family_decisions_theoretical"] += 1

        snap_has_blocker = False

        for mk in V3_MARKET_ORDER:
            bucket = by_market[mk]
            bucket["eligible_rows"] += 1
            duplicate = mk in duplicate_keys
            m = by_mk_single.get(mk) if not duplicate else (keyed[mk][0] if keyed.get(mk) else None)
            if m is not None and not duplicate:
                workload["market_rows_found"] += 1

            score_status, reason_codes = classify_score_replay(
                market_key=mk,
                m=m if not duplicate else None,
                by_mk=by_mk_for_opp,
                integrity=integrity,
                integrity_reasons=integrity_reasons,
                duplicate=duplicate,
            )
            # If duplicate, classify as ambiguous even if m exists
            if duplicate:
                score_status, reason_codes = "ambiguous_market_join", ["duplicate_market_key"]

            fam = market_family_for(mk) or "unknown"
            quote_class = "unavailable"
            perf_status = "not_applicable"
            if m is not None and not duplicate:
                quote_class, _ = classify_quote_quality(m)
                perf_status = classify_performance(m, quote_class)
                edge = _safe_float(getattr(m, "edge_pct", None))
                vant = _safe_float(getattr(m, "vantaggio_prob", None))
                if edge is not None:
                    input_coverage["with_edge_pct"] += 1
                if vant is not None:
                    input_coverage["with_vantaggio_prob"] += 1
                if _safe_float(getattr(m, "prob_cecchino", None)) is not None:
                    input_coverage["with_prob_cecchino"] += 1
                if _quota_valid(_safe_float(getattr(m, "quota_book", None))):
                    input_coverage["with_quota_book"] += 1
                if _safe_float(getattr(m, "quota_cecchino", None)) is not None:
                    input_coverage["with_quota_cecchino"] += 1
                if _safe_float(getattr(m, "prob_book_fair", None)) is not None:
                    input_coverage["with_prob_book_fair"] += 1
                opp_ok, _ = _opposite_keys_present(mk, by_mk_for_opp)
                if opp_ok:
                    input_coverage["with_opposite"] += 1

            # Quote counts
            if quote_class == "real":
                quote_quality["real"] += 1
                bucket["quote_real"] += 1
                by_competition[comp]["quote_real"] += 1
            elif quote_class == "derived":
                quote_quality["derived"] += 1
                bucket["quote_derived"] += 1
                by_competition[comp]["quote_derived"] += 1
            elif quote_class == "inconsistent":
                quote_quality["inconsistent_flags"] += 1
                bucket["quote_inconsistent"] += 1
            else:
                quote_quality["unavailable"] += 1
                bucket["quote_unavailable"] += 1

            # Performance
            if perf_status == "real_profit_ready":
                performance_coverage["real_profit_ready"] += 1
                bucket["performance_real_ready"] += 1
                by_competition[comp]["performance_ready"] += 1
            elif perf_status == "synthetic_profit_ready":
                performance_coverage["synthetic_profit_ready"] += 1
                bucket["performance_synthetic_ready"] += 1
                by_competition[comp]["performance_ready"] += 1
            elif perf_status == "result_available_but_profit_missing":
                performance_coverage["result_available_but_profit_missing"] += 1
                bucket["performance_result_without_profit"] += 1
            else:
                performance_coverage["not_applicable"] += 1
                bucket["performance_not_applicable"] += 1

            # Workload / market buckets
            if score_status == "exact_replay_ready":
                workload["exact_replay_ready"] += 1
                bucket["exact_replay_ready"] += 1
                by_family[fam]["exact_replay_ready"] += 1
                by_competition[comp]["exact_replay_ready"] += 1
            elif score_status == "score_replay_ready_with_warning":
                workload["ready_with_warning"] += 1
                bucket["ready_with_warning"] += 1
                by_family[fam]["ready_with_warning"] += 1
            elif score_status == "gate_only_replay_ready":
                workload["gate_only_ready"] += 1
                bucket["gate_only_ready"] += 1
            elif score_status == "invalid_pre_match_integrity":
                workload["invalid_pre_match_integrity"] += 1
                bucket["invalid_pre_match_integrity"] += 1
                snap_has_blocker = True
            elif score_status == "ambiguous_market_join":
                workload["ambiguous_market_join"] += 1
                bucket["ambiguous_market_join"] += 1
                snap_has_blocker = True
            else:
                workload["not_replayable"] += 1
                bucket["not_replayable"] += 1
                by_family[fam]["not_replayable"] += 1
                by_competition[comp]["missing_inputs"] += 1

            if score_status not in ("exact_replay_ready", "score_replay_ready_with_warning"):
                for rc in reason_codes or [score_status]:
                    _push_example(
                        example_store,
                        rc,
                        {
                            "snapshot_id": sid,
                            "market_key": mk,
                            "competition_name": comp,
                            "score_replay_status": score_status,
                            "performance_evaluation_status": perf_status,
                        },
                    )

        if snap_has_blocker:
            by_competition[comp]["blockers"] += 1
            if len(problematic_snaps) < MAX_PROBLEMATIC_SNAPSHOTS:
                if not any(p.get("snapshot_id") == sid for p in problematic_snaps):
                    problematic_snaps.append(
                        {
                            "snapshot_id": sid,
                            "competition_name": comp,
                            "reason": "snapshot_has_blockers",
                        }
                    )

        # Unsupported market rows (count only, no V3 evaluations)
        for mk, lst in keyed.items():
            if not is_v3_supported_market(mk):
                workload["unsupported_market_rows"] += len(lst)

    # Structural integrity: if almost no hash/lock on eligible → blocker
    eligible_n = len(eligible)
    if eligible_n > 0 and hash_present == 0 and lock_present == 0:
        structural_integrity_absent = True

    theoretical = max(1, workload["theoretical_evaluations"])
    replayable = workload["exact_replay_ready"] + workload["ready_with_warning"]
    missing_ratio = workload["not_replayable"] / theoretical
    fair_bad = (
        fair_checks["fair_group_out_of_tolerance"]
        + fair_checks["fair_group_non_finite"]
        + fair_checks["fair_group_out_of_range"]
    )
    fair_total = (
        fair_checks["fair_group_valid"]
        + fair_checks["fair_group_missing"]
        + fair_bad
    )
    fair_structurally_bad = fair_total > 0 and fair_checks["fair_group_valid"] == 0 and fair_bad > 0

    quote_total = (
        quote_quality["real"]
        + quote_quality["derived"]
        + quote_quality["unavailable"]
        + quote_quality["inconsistent_flags"]
    )
    real_derived_indistinguishable = (
        quote_total > 0
        and quote_quality["real"] == 0
        and quote_quality["derived"] == 0
        and quote_quality["inconsistent_flags"] > quote_total * 0.5
    )

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if structural_duplicates:
        blockers.append(
            _issue(
                "duplicate_market_keys",
                "Join MarketResult non deterministico: chiavi mercato duplicate sullo stesso snapshot.",
                count=integrity_counts["duplicate_market_keys"],
            )
        )
    if structural_integrity_absent:
        blockers.append(
            _issue(
                "pre_match_integrity_structurally_absent",
                "Hash e lock pre-match assenti su tutti gli snapshot eleggibili.",
            )
        )
    if missing_ratio >= 0.95 and replayable == 0:
        blockers.append(
            _issue(
                "mandatory_inputs_missing_almost_all",
                "Input obbligatori mancanti sulla quasi totalità delle valutazioni V3.",
                not_replayable=workload["not_replayable"],
                theoretical=workload["theoretical_evaluations"],
            )
        )
    if fair_structurally_bad:
        blockers.append(
            _issue(
                "fair_probabilities_structurally_incoherent",
                "Probabilità fair congelate strutturalmente incoerenti (nessun gruppo valido).",
            )
        )
    if real_derived_indistinguishable:
        blockers.append(
            _issue(
                "real_derived_indistinguishable",
                "Impossibile distinguere quote reali e derivate in modo affidabile.",
            )
        )

    if is_partial:
        warnings.append(
            _issue(
                "partial_run",
                "Run parziale: analizzabile ma non rappresentativo della stagione completa.",
            )
        )
    if quote_quality["derived"] > 0:
        warnings.append(
            _issue(
                "derived_quotes_diagnostic_only",
                "Quote derivate replayabili solo in diagnostica; escluse dal ROI reale.",
                count=quote_quality["derived"],
            )
        )
    if workload["ready_with_warning"] > 0 or workload["not_replayable"] > 0:
        if not blockers:
            warnings.append(
                _issue(
                    "incomplete_coverage",
                    "Copertura replay incompleta su alcuni mercati/snapshot.",
                    ready_with_warning=workload["ready_with_warning"],
                    not_replayable=workload["not_replayable"],
                )
            )
    if integrity_counts["with_pre_match_hash"] < eligible_n:
        warnings.append(
            _issue(
                "partial_pre_match_hash",
                "Alcuni snapshot eleggibili sono senza hash pre-match.",
                with_hash=integrity_counts["with_pre_match_hash"],
                eligible=eligible_n,
            )
        )
    if run.status == STATUS_COMPLETED_WITH_WARNINGS:
        warnings.append(
            _issue(
                "run_completed_with_warnings",
                "Il run è completed_with_warnings: verificare matches_error prima del replay completo.",
            )
        )

    # Probe only if not structurally blocked by duplicates/zero eligible (already handled)
    probe: dict[str, Any]
    if blockers and any(
        b["code"]
        in (
            "duplicate_market_keys",
            "mandatory_inputs_missing_almost_all",
            "real_derived_indistinguishable",
        )
        for b in blockers
    ):
        probe = {
            "probe_is_diagnostic_only": True,
            "probe_not_a_backtest": True,
            "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
            "skipped": True,
            "reason": "structural_blockers",
        }
    else:
        probe = _run_probe(eligible_snaps=eligible, markets_by_snap=markets_by_snap)

    if blockers:
        status = STATUS_BLOCKED
        can_replay = False
        next_action = "resolve_blockers"
    elif warnings:
        status = STATUS_READY_WITH_WARNINGS
        can_replay = True
        next_action = "implement_isolated_v3_replay"
    else:
        status = STATUS_READY
        can_replay = True
        next_action = "implement_isolated_v3_replay"

    # Cap issue examples
    issue_examples = {
        k: v[:MAX_EXAMPLES_PER_REASON] for k, v in list(example_store.items())[:40]
    }

    payload = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "generated_at": _utcnow().isoformat(),
        "run": {
            "run_id": int(run.id),
            "season_label": run.season_label,
            "status": run.status,
            "run_scope": scope.get("run_scope"),
            "is_partial_run": is_partial,
            "not_full_season_report": bool(scope.get("not_full_season_report")),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "source_git_commit": run.source_git_commit,
            "source_revision_status": getattr(run, "source_revision_status", None),
            "scan_version": run.scan_version,
        },
        "formula": {
            "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
            "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
            "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
            "runtime_git_commit": runtime_rev.get("git_commit"),
            "runtime_git_commit_source": runtime_rev.get("git_commit_source"),
            "historical_profile_used": False,
            "fixed_scales_used": True,
        },
        "bookmakers": {
            "historical": "Bet365",
            "today_operational": "Betfair",
            "providers_are_different": True,
            "bookmaker_parity_status": "different_provider_expected",
            "formula_provider_dependency": "book_agnostic_with_fair_probability_inputs",
        },
        "source_integrity": integrity_counts,
        "workload": workload,
        "input_coverage": input_coverage,
        "by_market": by_market,
        "by_family": by_family,
        "by_competition": dict(by_competition),
        "quote_quality": quote_quality,
        "fair_probability_checks": fair_checks,
        "performance_coverage": performance_coverage,
        "adapter_contract": adapter_contract_payload(),
        "anti_leakage": {
            "pre_match_input_fields": list(PRE_MATCH_INPUT_FIELDS),
            "post_match_performance_fields": list(POST_MATCH_PERFORMANCE_FIELDS),
            "forbidden_formula_fields": list(FORBIDDEN_FORMULA_FIELDS),
            "anti_leakage_status": "enforced_in_preflight_contract",
            "result_fields_passed_to_formula": False,
            "settlement_fields_passed_to_formula": False,
        },
        "probe": probe,
        "blockers": blockers,
        "warnings": warnings,
        "status_rules": {
            "applied_status": status,
            "blocked_if": [
                "run_not_in_completed_or_completed_with_warnings",
                "zero_eligible_core",
                "structural_duplicate_market_keys",
                "structural_pre_match_integrity_absent",
                "mandatory_inputs_missing_almost_all",
                "fair_probabilities_structurally_incoherent",
                "real_derived_indistinguishable",
            ],
            "ready_with_warnings_if": [
                "replay_possible_with_incomplete_coverage",
                "partial_run",
                "derived_quotes_diagnostic_only",
                "linked_context_absent",
            ],
            "ready_if": [
                "no_blockers",
                "deterministic_replay",
                "mandatory_inputs_available",
            ],
        },
        "issue_examples": issue_examples,
        "problematic_snapshots": problematic_snaps[:MAX_PROBLEMATIC_SNAPSHOTS],
        "replay_recommendation": {
            "can_replay_without_full_scan": can_replay,
            "requires_new_external_data": False,
            "requires_model_recalculation": False,
            "requires_database_migration": False,
            "recommended_next_action": next_action,
        },
    }
    return make_json_safe(payload)


def run_purchasability_v3_replay_preflight(db: Session, run_id: int) -> dict[str, Any]:
    """Entry point read-only. Cache in-memory per run completato."""
    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    runtime_rev = resolve_code_revision()
    cache_key = "|".join(
        [
            str(int(run_id)),
            PREFLIGHT_SCHEMA_VERSION,
            PURCHASABILITY_V3_FORMULA_VERSION,
            str(runtime_rev.get("git_commit") or "unknown"),
        ]
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        out = dict(cached)
        out["cache_hit"] = True
        return out

    result = _compute_preflight(db, run_id)
    ttl = (
        CACHE_TTL_COMPLETED_S
        if run.status in ALLOWED_RUN_STATUSES
        else CACHE_TTL_BLOCKED_S
    )
    result["cache_hit"] = False
    _cache_set(cache_key, result, ttl)
    return result
