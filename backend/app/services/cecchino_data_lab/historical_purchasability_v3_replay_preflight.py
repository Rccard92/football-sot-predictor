"""Preflight read-only replay Acquistabilità V3 su run storico Cecchino Lab.

STEP 3A.2: semantica integrità storica (freeze vs cattura prospettica),
classificazione completa, probe leggibile. Resource-safe (aggregati SQL +
streaming), nessuna scrittura DB, nessun replay completo, nessuna nuova scansione.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterator

from sqlalchemy import func, select
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

logger = logging.getLogger(__name__)

PREFLIGHT_SCHEMA_VERSION = "cecchino_lab_purchasability_v3_replay_preflight_v2"
INTEGRITY_POLICY_VERSION = "cecchino_lab_historical_reconstruction_integrity_v1"
FAIR_SUM_TOLERANCE = 1e-4
PROBE_SNAPSHOT_LIMIT = 30
PROBE_BUCKET_SIZE = 10
MAX_EXAMPLES_PER_REASON = 20
MAX_PROBLEMATIC_SNAPSHOTS = 20
CACHE_TTL_COMPLETED_S = 300.0
CACHE_TTL_BLOCKED_S = 60.0
CACHE_MAX_ENTRIES = 64

INTEGRITY_MODE_PROSPECTIVE = "prospective_pre_match"
INTEGRITY_MODE_FROZEN = "historical_reconstruction_frozen"
INTEGRITY_MODE_INCOMPLETE = "historical_reconstruction_incomplete"
INTEGRITY_MODE_INVALID = "invalid_or_ambiguous"

CHRONOLOGY_PASSED = "passed"
CHRONOLOGY_FAILED = "failed"
CHRONOLOGY_NOT_APPLICABLE = "not_applicable"
CHRONOLOGY_REASON_HISTORICAL_FREEZE = (
    "lock_timestamp_is_historical_freeze_time_not_original_capture_time"
)

WORKLOAD_CLASSIFICATION_KEYS = (
    "exact_replay_ready",
    "ready_with_warning",
    "gate_only_ready",
    "not_replayable",
    "invalid_integrity",
    "ambiguous_market_join",
)

PREFLIGHT_STREAM_YIELD_PER = 500
PREFLIGHT_MAX_SUPPORTED_ROWS = 100_000
PREFLIGHT_MAX_RUNTIME_SECONDS = 30

SNAPSHOT_LEAN_COLS = (
    CecchinoLabHistoricalMatchSnapshot.id,
    CecchinoLabHistoricalMatchSnapshot.run_id,
    CecchinoLabHistoricalMatchSnapshot.lab_match_id,
    CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status,
    CecchinoLabHistoricalMatchSnapshot.historical_eligibility_reason,
    CecchinoLabHistoricalMatchSnapshot.competition_name,
    CecchinoLabHistoricalMatchSnapshot.kickoff_at,
    CecchinoLabHistoricalMatchSnapshot.pre_match_locked_at,
    CecchinoLabHistoricalMatchSnapshot.pre_match_payload_sha256,
    CecchinoLabHistoricalMatchSnapshot.chronological_order,
)

MARKET_STREAM_COLS = (
    CecchinoLabHistoricalMarketResult.id,
    CecchinoLabHistoricalMarketResult.match_snapshot_id,
    CecchinoLabHistoricalMarketResult.market_key,
    CecchinoLabHistoricalMarketResult.quota_book,
    CecchinoLabHistoricalMarketResult.quota_cecchino,
    CecchinoLabHistoricalMarketResult.prob_book_raw,
    CecchinoLabHistoricalMarketResult.prob_book_fair,
    CecchinoLabHistoricalMarketResult.prob_cecchino,
    CecchinoLabHistoricalMarketResult.edge_pct,
    CecchinoLabHistoricalMarketResult.vantaggio_prob,
    CecchinoLabHistoricalMarketResult.quote_source_type,
    CecchinoLabHistoricalMarketResult.is_real_book_quote,
    CecchinoLabHistoricalMarketResult.is_derived_quote,
    CecchinoLabHistoricalMarketResult.derivation_method,
    CecchinoLabHistoricalMarketResult.evaluation_status,
    CecchinoLabHistoricalMarketResult.won,
    CecchinoLabHistoricalMarketResult.profit_1u_real,
    CecchinoLabHistoricalMarketResult.profit_1u_synthetic,
    CecchinoLabHistoricalMarketResult.result_reason,
)

HEAVY_JSON_FIELD_NAMES = frozenset(
    {
        "input_snapshot_json",
        "cecchino_output_json",
        "historical_kpi_json",
        "result_json",
        "settlement_summary_json",
        "signals_json",
        "balance_v5_json",
        "goal_intensity_compatibility_json",
        "purchasability_compatibility_json",
        "quote_sources_json",
        "module_availability_json",
        "blocking_reasons_json",
        "warnings_json",
        "error_json",
        "signal_sources_json",
    }
)


class PreflightResourceBudgetExceeded(Exception):
    """Budget risorse superato: risposta blocked controllata, non crash worker."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

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

FORMULA_PAYLOAD_ALLOWED_FIELDS = (
    "market_key",
    "edge_pct",
    "vantaggio_prob",
    "prob_cecchino",
    "quota_book",
    "quota_cecchino",
    "quote_source",
    "odds_source",
    "book_source",
    "derived_quote",
    "not_real_book_quote",
    "force_derived_quote",
    "rating",  # gate V3.1 (pre-match); ignorato da V3
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
        "invalid_integrity": 0,
        "ambiguous_market_join": 0,
        "classified_total": 0,
        "unclassified": 0,
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


def _empty_integrity_counts(
    *,
    snapshots_total: int = 0,
    snapshots_eligible_core: int = 0,
    snapshots_excluded: int = 0,
    exclusions_by_reason: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "snapshots_total": snapshots_total,
        "snapshots_eligible_core": snapshots_eligible_core,
        "snapshots_excluded": snapshots_excluded,
        "exclusions_by_reason": dict(exclusions_by_reason or {}),
        "with_payload_hash": 0,
        "with_historical_freeze_lock": 0,
        # Legacy aliases (compat); non sono requisito del replay storico.
        "with_pre_match_hash": 0,
        "with_pre_match_lock": 0,
        "lock_before_kickoff": 0,
        "invalid_lock_timestamp": 0,
        "historical_reconstruction_verified": 0,
        "historical_reconstruction_with_warning": 0,
        "historical_reconstruction_invalid": 0,
        "prospective_pre_match_verified": 0,
        "chronological_lock_check_applicable": 0,
        "chronological_lock_check_passed": 0,
        "chronological_lock_check_failed": 0,
        "chronological_lock_check_not_applicable": 0,
        "duplicate_market_keys": 0,
        "snapshots_with_duplicates": 0,
        "formula_input_whitelist_verified": True,
        "post_match_fields_excluded": True,
        "score_performance_phase_separation_verified": True,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
        "integrity_mode_dominant": None,
    }


def _empty_probe_by_market() -> dict[str, dict[str, int]]:
    return {
        mk: {
            "submitted": 0,
            "returned": 0,
            "scored": 0,
            "gate_failed": 0,
            "unavailable": 0,
            "not_applicable": 0,
            "unsupported": 0,
            "errors": 0,
            "unclassified": 0,
        }
        for mk in V3_MARKET_ORDER
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


def _normalize_comparable_datetimes(
    locked: Any, kickoff: Any
) -> tuple[Any, Any] | None:
    try:
        lk = locked
        ko = kickoff
        if getattr(lk, "tzinfo", None) is None and getattr(ko, "tzinfo", None) is not None:
            lk = lk.replace(tzinfo=timezone.utc)
        if getattr(ko, "tzinfo", None) is None and getattr(lk, "tzinfo", None) is not None:
            ko = ko.replace(tzinfo=timezone.utc)
        return lk, ko
    except Exception:
        return None


def _payload_hash_present(sha: Any) -> bool:
    if sha is None:
        return False
    text = str(sha).strip()
    return bool(text)


def _payload_hash_malformed(sha: Any) -> bool:
    """True solo se presente ma chiaramente non utilizzabile."""
    if sha is None:
        return False
    text = str(sha).strip()
    if not text:
        return True
    if any(ch.isspace() for ch in text):
        return True
    return False


def evaluate_historical_integrity_policy(
    snap: Any,
    *,
    eligibility_verified: bool = True,
    formula_whitelist_verified: bool = True,
    post_match_excluded: bool = True,
    phase_separation_verified: bool = True,
    structural_invalid: bool = False,
) -> dict[str, Any]:
    """Policy esplicita STEP 3A.2: prospective vs historical reconstruction.

    `pre_match_locked_at` nella scansione Lab è il wall-clock del freeze di
    ricostruzione (``_utcnow()``), non una cattura prospettica pre-kickoff.
    """
    reasons: list[str] = []
    sha = getattr(snap, "pre_match_payload_sha256", None)
    locked = getattr(snap, "pre_match_locked_at", None)
    kickoff = getattr(snap, "kickoff_at", None)
    elig = getattr(snap, "historical_eligibility_status", None)

    hash_present = _payload_hash_present(sha)
    lock_present = locked is not None
    kickoff_present = kickoff is not None
    eligible_ok = eligibility_verified and (elig is None or elig == ELIGIBLE_CORE)

    if structural_invalid:
        reasons.append("structural_invalid")
    if _payload_hash_malformed(sha):
        reasons.append("malformed_pre_match_hash")
        hash_present = False
    if not hash_present:
        reasons.append("missing_pre_match_hash")
    if not lock_present:
        reasons.append("missing_pre_match_lock")
    if not kickoff_present:
        reasons.append("missing_kickoff")
    if not eligible_ok:
        reasons.append("eligibility_not_verified")
    if not formula_whitelist_verified:
        reasons.append("formula_input_whitelist_unverified")
    if not post_match_excluded:
        reasons.append("post_match_fields_not_excluded")
    if not phase_separation_verified:
        reasons.append("score_performance_phase_separation_unverified")

    lock_before_kickoff: bool | None = None
    chrono_comparable = False
    if lock_present and kickoff_present:
        pair = _normalize_comparable_datetimes(locked, kickoff)
        if pair is None:
            reasons.append("lock_kickoff_not_comparable")
        else:
            lk, ko = pair
            chrono_comparable = True
            lock_before_kickoff = bool(lk < ko)

    freeze_complete = (
        hash_present
        and lock_present
        and eligible_ok
        and formula_whitelist_verified
        and post_match_excluded
        and phase_separation_verified
        and not structural_invalid
        and "malformed_pre_match_hash" not in reasons
    )

    # Prospective: solo quando lock < kickoff è dimostrabile.
    if (
        freeze_complete
        and kickoff_present
        and chrono_comparable
        and lock_before_kickoff is True
    ):
        return {
            "integrity_mode": INTEGRITY_MODE_PROSPECTIVE,
            "integrity_gate": "ok",
            "reasons": [],
            "chronological_lock_check": CHRONOLOGY_PASSED,
            "chronological_lock_check_reason": None,
            "historical_freeze_lock_present": lock_present,
            "historical_payload_hash_present": hash_present,
            "formula_input_whitelist_verified": formula_whitelist_verified,
            "post_match_fields_excluded": post_match_excluded,
            "score_performance_phase_separation_verified": phase_separation_verified,
            "captured_before_kickoff": True,
            "eligibility_verified": eligible_ok,
        }

    # Historical reconstruction frozen: lock dopo kickoff NON è errore.
    if freeze_complete:
        return {
            "integrity_mode": INTEGRITY_MODE_FROZEN,
            "integrity_gate": "ok",
            "reasons": [],
            "chronological_lock_check": CHRONOLOGY_NOT_APPLICABLE,
            "chronological_lock_check_reason": CHRONOLOGY_REASON_HISTORICAL_FREEZE,
            "historical_freeze_lock_present": lock_present,
            "historical_payload_hash_present": hash_present,
            "formula_input_whitelist_verified": formula_whitelist_verified,
            "post_match_fields_excluded": post_match_excluded,
            "score_performance_phase_separation_verified": phase_separation_verified,
            "captured_before_kickoff": False,
            "eligibility_verified": eligible_ok,
        }

    # Incomplete freeze ma separazione pre/post dimostrabile → warning path.
    separation_ok = (
        formula_whitelist_verified
        and post_match_excluded
        and phase_separation_verified
        and not structural_invalid
        and "malformed_pre_match_hash" not in reasons
    )
    if separation_ok and eligible_ok:
        return {
            "integrity_mode": INTEGRITY_MODE_INCOMPLETE,
            "integrity_gate": "incomplete",
            "reasons": [r for r in reasons if r],
            "chronological_lock_check": CHRONOLOGY_NOT_APPLICABLE,
            "chronological_lock_check_reason": CHRONOLOGY_REASON_HISTORICAL_FREEZE,
            "historical_freeze_lock_present": lock_present,
            "historical_payload_hash_present": hash_present,
            "formula_input_whitelist_verified": formula_whitelist_verified,
            "post_match_fields_excluded": post_match_excluded,
            "score_performance_phase_separation_verified": phase_separation_verified,
            "captured_before_kickoff": False,
            "eligibility_verified": eligible_ok,
        }

    # Prospective chronology failed alone is NOT used as historical invalid —
    # only structural / unverifiable separation is blocking.
    chrono_check = CHRONOLOGY_NOT_APPLICABLE
    chrono_reason: str | None = CHRONOLOGY_REASON_HISTORICAL_FREEZE
    if (
        chrono_comparable
        and lock_before_kickoff is False
        and hash_present
        and lock_present
        and kickoff_present
        and not freeze_complete
    ):
        # Tentativo prospective fallito per altri motivi: chronology failed
        # solo se qualcuno chiedesse prospective; per Lab resta N/A.
        chrono_check = CHRONOLOGY_NOT_APPLICABLE
        chrono_reason = CHRONOLOGY_REASON_HISTORICAL_FREEZE

    return {
        "integrity_mode": INTEGRITY_MODE_INVALID,
        "integrity_gate": "invalid",
        "reasons": [r for r in reasons if r] or ["invalid_or_ambiguous_integrity"],
        "chronological_lock_check": chrono_check,
        "chronological_lock_check_reason": chrono_reason,
        "historical_freeze_lock_present": lock_present,
        "historical_payload_hash_present": hash_present,
        "formula_input_whitelist_verified": formula_whitelist_verified,
        "post_match_fields_excluded": post_match_excluded,
        "score_performance_phase_separation_verified": phase_separation_verified,
        "captured_before_kickoff": False,
        "eligibility_verified": eligible_ok,
    }


def _pre_match_integrity(snap: Any) -> tuple[str, list[str]]:
    """Compat legacy: mappa la policy 3A.2 su (ok|invalid|missing, reasons)."""
    policy = evaluate_historical_integrity_policy(snap)
    gate = str(policy.get("integrity_gate") or "invalid")
    reasons = list(policy.get("reasons") or [])
    if gate == "ok":
        return "ok", reasons
    if gate == "incomplete":
        return "missing", reasons
    return "invalid", reasons


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
        return "invalid_integrity", list(integrity_reasons)

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

    if integrity in ("missing", "incomplete"):
        # Hash/lock assenti o freeze incompleto: scoreabile con warning se core ok.
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


def map_score_status_to_workload_key(score_status: str) -> str | None:
    """Mappa status raw → chiave workload; None = unsupported (non conta come teorica)."""
    if score_status == "exact_replay_ready":
        return "exact_replay_ready"
    if score_status == "score_replay_ready_with_warning":
        return "ready_with_warning"
    if score_status == "gate_only_replay_ready":
        return "gate_only_ready"
    if score_status in ("invalid_integrity", "invalid_pre_match_integrity"):
        return "invalid_integrity"
    if score_status == "ambiguous_market_join":
        return "ambiguous_market_join"
    if score_status == "unsupported_market":
        return None
    if score_status == "source_market_unavailable":
        return "not_replayable"
    return "not_replayable"

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


def _as_row_id(row: Any) -> int:
    if isinstance(row, int):
        return int(row)
    if isinstance(row, (tuple, list)):
        return int(row[0])
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        if "id" in mapping:
            return int(mapping["id"])
        return int(next(iter(mapping.values())))
    if hasattr(row, "id"):
        return int(row.id)
    try:
        return int(row[0])
    except Exception as exc:  # noqa: BLE001
        raise TypeError(f"Cannot extract id from row: {type(row)}") from exc


def _row_to_ns(row: Any) -> SimpleNamespace:
    if isinstance(row, SimpleNamespace):
        return row
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return SimpleNamespace(**dict(mapping))
    if isinstance(row, dict):
        return SimpleNamespace(**row)
    keys = getattr(row, "_fields", None) or getattr(row, "keys", lambda: ())()
    data = {k: getattr(row, k) for k in keys}
    return SimpleNamespace(**data)


def _empty_resource_profile(*, probe_requested: bool = False) -> dict[str, Any]:
    return {
        "strategy": "sql_aggregates_and_streaming",
        "full_orm_entities_loaded": False,
        "snapshot_json_fields_loaded": False,
        "market_json_fields_loaded": False,
        "market_rows_streamed": 0,
        "max_market_rows_held_in_memory": 0,
        "stream_yield_per": PREFLIGHT_STREAM_YIELD_PER,
        "probe_requested": probe_requested,
        "probe_snapshot_count": 0,
        "duration_ms": 0,
        "resource_budget_exceeded": False,
    }


def _empty_query_profile() -> dict[str, Any]:
    return {
        "snapshot_aggregate_queries": 0,
        "snapshot_lean_queries": 0,
        "market_count_queries": 0,
        "market_stream_queries": 0,
        "unsupported_count_queries": 0,
        "probe_selection_queries": 0,
        "probe_market_queries": 0,
    }


def _budget_check_runtime(started: float, phase: str) -> None:
    elapsed = time.monotonic() - started
    if elapsed > PREFLIGHT_MAX_RUNTIME_SECONDS:
        raise PreflightResourceBudgetExceeded(
            "preflight_resource_budget_exceeded",
            f"Runtime preflight oltre il budget di {PREFLIGHT_MAX_RUNTIME_SECONDS}s.",
            phase=phase,
            elapsed_s=round(elapsed, 3),
            limit_s=PREFLIGHT_MAX_RUNTIME_SECONDS,
        )


def _scalar_count(db: Session, stmt: Any) -> int:
    result = db.execute(stmt)
    value = result.scalar()
    return int(value or 0)


def _load_snapshot_aggregates(
    db: Session,
    run_id: int,
    query_profile: dict[str, Any],
) -> dict[str, Any]:
    Snap = CecchinoLabHistoricalMatchSnapshot
    total = _scalar_count(
        db,
        select(func.count()).select_from(Snap).where(Snap.run_id == run_id),
    )
    query_profile["snapshot_aggregate_queries"] += 1

    eligible = _scalar_count(
        db,
        select(func.count())
        .select_from(Snap)
        .where(Snap.run_id == run_id, Snap.historical_eligibility_status == ELIGIBLE_CORE),
    )
    query_profile["snapshot_aggregate_queries"] += 1

    excluded = total - eligible

    reason_rows = db.execute(
        select(Snap.historical_eligibility_reason, func.count())
        .where(
            Snap.run_id == run_id,
            Snap.historical_eligibility_status != ELIGIBLE_CORE,
        )
        .group_by(Snap.historical_eligibility_reason)
    ).all()
    query_profile["snapshot_aggregate_queries"] += 1
    exclusions_by_reason: dict[str, int] = {}
    for reason, cnt in reason_rows:
        key = str(reason or "unknown")
        exclusions_by_reason[key] = int(cnt)

    comp_rows = db.execute(
        select(Snap.competition_name, func.count())
        .where(Snap.run_id == run_id, Snap.historical_eligibility_status == ELIGIBLE_CORE)
        .group_by(Snap.competition_name)
    ).all()
    query_profile["snapshot_aggregate_queries"] += 1
    by_competition_eligible = {str(name or "unknown"): int(cnt) for name, cnt in comp_rows}

    return {
        "snapshots_total": total,
        "snapshots_eligible_core": eligible,
        "snapshots_excluded": excluded,
        "exclusions_by_reason": exclusions_by_reason,
        "by_competition_eligible": by_competition_eligible,
    }


def _load_eligible_snap_meta(
    db: Session,
    run_id: int,
    query_profile: dict[str, Any],
) -> dict[int, SimpleNamespace]:
    """Carica solo colonne lean degli eligible_core (nessun JSON)."""
    stmt = (
        select(*SNAPSHOT_LEAN_COLS)
        .where(
            CecchinoLabHistoricalMatchSnapshot.run_id == run_id,
            CecchinoLabHistoricalMatchSnapshot.historical_eligibility_status == ELIGIBLE_CORE,
        )
        .order_by(
            CecchinoLabHistoricalMatchSnapshot.kickoff_at.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.chronological_order.asc().nulls_last(),
            CecchinoLabHistoricalMatchSnapshot.id.asc(),
        )
    )
    rows = db.execute(stmt).all()
    query_profile["snapshot_lean_queries"] += 1
    out: dict[int, SimpleNamespace] = {}
    for row in rows:
        ns = _row_to_ns(row)
        out[int(ns.id)] = ns
    return out


def _count_supported_market_rows(db: Session, run_id: int, query_profile: dict[str, Any]) -> int:
    stmt = (
        select(func.count())
        .select_from(CecchinoLabHistoricalMarketResult)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V3_MARKET_ORDER)),
        )
    )
    n = _scalar_count(db, stmt)
    query_profile["market_count_queries"] += 1
    return n


def _count_unsupported_market_rows(db: Session, run_id: int, query_profile: dict[str, Any]) -> int:
    stmt = (
        select(func.count())
        .select_from(CecchinoLabHistoricalMarketResult)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.notin_(list(V3_MARKET_ORDER)),
        )
    )
    n = _scalar_count(db, stmt)
    query_profile["unsupported_count_queries"] += 1
    return n


def _iter_supported_market_rows(db: Session, run_id: int, query_profile: dict[str, Any]) -> Iterator[Any]:
    stmt = (
        select(*MARKET_STREAM_COLS)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V3_MARKET_ORDER)),
        )
        .order_by(
            CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
            CecchinoLabHistoricalMarketResult.market_key.asc(),
            CecchinoLabHistoricalMarketResult.id.asc(),
        )
        .execution_options(
            stream_results=True,
            yield_per=PREFLIGHT_STREAM_YIELD_PER,
        )
    )
    result = db.execute(stmt)
    query_profile["market_stream_queries"] += 1
    yield_per = getattr(result, "yield_per", None)
    if callable(yield_per):
        iterator = yield_per(PREFLIGHT_STREAM_YIELD_PER)
    else:
        iterator = iter(result)
    for row in iterator:
        yield row


def _select_probe_snapshot_ids_from_meta(eligible_meta: dict[int, SimpleNamespace]) -> list[int]:
    if not eligible_meta:
        return []
    ordered = sorted(
        eligible_meta.values(),
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


def _select_probe_snapshot_ids_sql(
    db: Session,
    run_id: int,
    eligible_count: int,
    query_profile: dict[str, Any],
) -> list[int]:
    """Selezione deterministica first/mid/last senza materializzare tutti gli ORM."""
    Snap = CecchinoLabHistoricalMatchSnapshot
    order = (
        Snap.kickoff_at.asc().nulls_last(),
        Snap.chronological_order.asc().nulls_last(),
        Snap.id.asc(),
    )
    base = select(Snap.id).where(
        Snap.run_id == run_id,
        Snap.historical_eligibility_status == ELIGIBLE_CORE,
    )
    if eligible_count <= PROBE_SNAPSHOT_LIMIT:
        rows = db.execute(base.order_by(*order)).all()
        query_profile["probe_selection_queries"] += 1
        return [_as_row_id(r) for r in rows]

    first_rows = db.execute(base.order_by(*order).limit(PROBE_BUCKET_SIZE)).all()
    query_profile["probe_selection_queries"] += 1
    last_rows = db.execute(
        base.order_by(
            Snap.kickoff_at.desc().nulls_first(),
            Snap.chronological_order.desc().nulls_first(),
            Snap.id.desc(),
        ).limit(PROBE_BUCKET_SIZE)
    ).all()
    query_profile["probe_selection_queries"] += 1
    mid_start = max(0, (eligible_count // 2) - (PROBE_BUCKET_SIZE // 2))
    mid_rows = db.execute(
        base.order_by(*order).offset(mid_start).limit(PROBE_BUCKET_SIZE)
    ).all()
    query_profile["probe_selection_queries"] += 1

    seen: set[int] = set()
    out: list[int] = []
    for r in first_rows + mid_rows + list(reversed(last_rows)):
        sid = _as_row_id(r)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out[:PROBE_SNAPSHOT_LIMIT]


def _load_markets_for_snapshots(
    db: Session,
    run_id: int,
    snap_ids: list[int],
    query_profile: dict[str, Any],
) -> dict[int, list[SimpleNamespace]]:
    if not snap_ids:
        return {}
    stmt = (
        select(*MARKET_STREAM_COLS)
        .where(
            CecchinoLabHistoricalMarketResult.run_id == run_id,
            CecchinoLabHistoricalMarketResult.match_snapshot_id.in_(snap_ids),
            CecchinoLabHistoricalMarketResult.market_key.in_(list(V3_MARKET_ORDER)),
        )
        .order_by(
            CecchinoLabHistoricalMarketResult.match_snapshot_id.asc(),
            CecchinoLabHistoricalMarketResult.market_key.asc(),
            CecchinoLabHistoricalMarketResult.id.asc(),
        )
    )
    rows = db.execute(stmt).all()
    query_profile["probe_market_queries"] += 1
    by_snap: dict[int, list[SimpleNamespace]] = defaultdict(list)
    for row in rows:
        ns = _row_to_ns(row)
        by_snap[int(ns.match_snapshot_id)].append(ns)
    return by_snap


def _classify_probe_item(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "")
    gate = _as_dict(item.get("gate"))
    gate_status = str(gate.get("gate_status") or "")
    if status == "available" and item.get("score") is not None:
        return "scored"
    if gate_status.startswith("failed"):
        return "gate_failed"
    if gate_status == "unsupported_market" or status == "unsupported":
        return "unsupported"
    if status == "not_applicable" or gate_status == "not_applicable":
        return "not_applicable"
    if status == "unavailable":
        return "unavailable"
    if status in ("error", "failed") or gate_status == "error":
        return "error"
    return "unclassified"


def _run_probe(
    *,
    db: Session,
    run_id: int,
    eligible_meta: dict[int, SimpleNamespace],
    query_profile: dict[str, Any],
) -> dict[str, Any]:
    ids = _select_probe_snapshot_ids_sql(
        db, run_id, len(eligible_meta), query_profile
    )
    # Fallback deterministico se SQL mock non distingue limit/offset
    if not ids and eligible_meta:
        ids = _select_probe_snapshot_ids_from_meta(eligible_meta)
    markets_by_snap = _load_markets_for_snapshots(db, run_id, ids, query_profile)

    by_market = _empty_probe_by_market()
    counts = {
        "snapshots_selected": len(ids),
        "snapshots_probed": 0,
        "markets_expected": len(ids) * 8,
        "panel_rows_submitted": 0,
        "formula_items_returned": 0,
        "markets_scored": 0,
        "markets_gate_failed": 0,
        "markets_unavailable": 0,
        "markets_not_applicable": 0,
        "markets_unsupported": 0,
        "markets_error": 0,
        "markets_unclassified": 0,
        "snapshots_with_error": 0,
        "probe_classified_total": 0,
    }
    errors: list[dict[str, Any]] = []
    formula_forbidden_found: list[str] = []

    for sid in ids:
        snap = eligible_meta.get(sid)
        if snap is None:
            continue
        rows_src = markets_by_snap.get(sid, [])
        panel_rows = [
            build_adapter_panel_row(m)
            for m in rows_src
            if is_v3_supported_market(str(getattr(m, "market_key", "") or ""))
        ]
        submitted_keys = [str(r.get("market_key") or "") for r in panel_rows]
        for mk in submitted_keys:
            if mk in by_market:
                by_market[mk]["submitted"] += 1
        counts["panel_rows_submitted"] += len(panel_rows)

        for row in panel_rows:
            for forbidden in FORBIDDEN_FORMULA_FIELDS:
                if forbidden in row:
                    if forbidden not in formula_forbidden_found:
                        formula_forbidden_found.append(forbidden)

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
            counts["formula_items_returned"] += len(items)
            for item in items:
                if not isinstance(item, dict):
                    counts["markets_unclassified"] += 1
                    continue
                mk = str(item.get("market_key") or "")
                bucket = by_market.get(mk)
                if bucket is not None:
                    bucket["returned"] += 1
                kind = _classify_probe_item(item)
                if kind == "scored":
                    counts["markets_scored"] += 1
                    if bucket is not None:
                        bucket["scored"] += 1
                elif kind == "gate_failed":
                    counts["markets_gate_failed"] += 1
                    if bucket is not None:
                        bucket["gate_failed"] += 1
                elif kind == "unavailable":
                    counts["markets_unavailable"] += 1
                    if bucket is not None:
                        bucket["unavailable"] += 1
                elif kind == "not_applicable":
                    counts["markets_not_applicable"] += 1
                    if bucket is not None:
                        bucket["not_applicable"] += 1
                elif kind == "unsupported":
                    counts["markets_unsupported"] += 1
                    if bucket is not None:
                        bucket["unsupported"] += 1
                elif kind == "error":
                    counts["markets_error"] += 1
                    if bucket is not None:
                        bucket["errors"] += 1
                else:
                    counts["markets_unclassified"] += 1
                    if bucket is not None:
                        bucket["unclassified"] += 1
        except Exception as exc:  # noqa: BLE001 — probe diagnostico
            counts["snapshots_with_error"] += 1
            n_err = len(panel_rows) if panel_rows else 8
            counts["markets_error"] += n_err
            for mk in submitted_keys:
                if mk in by_market:
                    by_market[mk]["errors"] += 1
            if not submitted_keys:
                # Nessuna row inviata: distribuisci sugli 8 mercati attesi
                for mk in V3_MARKET_ORDER:
                    by_market[mk]["errors"] += 1
            if len(errors) < MAX_EXAMPLES_PER_REASON:
                errors.append(
                    {
                        "snapshot_id": sid,
                        "phase": "formula",
                        "error_type": type(exc).__name__,
                    }
                )

    classified = (
        counts["markets_scored"]
        + counts["markets_gate_failed"]
        + counts["markets_unavailable"]
        + counts["markets_not_applicable"]
        + counts["markets_unsupported"]
        + counts["markets_error"]
        + counts["markets_unclassified"]
    )
    counts["probe_classified_total"] = classified
    returned = counts["formula_items_returned"]
    # Gli errori a livello snapshot incrementano markets_error senza items returned.
    expected_vs = "match" if returned == counts["panel_rows_submitted"] else "mismatch"

    return {
        "probe_is_diagnostic_only": True,
        "probe_not_a_backtest": True,
        "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
        "probe_selected_snapshot_ids": ids,
        "probe_selection_rule": "first_10_chrono + mid_10 + last_10",
        "invoked_v3_formula": True,
        "persisted_results": False,
        "skipped": False,
        **counts,
        "expected_vs_returned_status": expected_vs,
        "by_market": by_market,
        "formula_payload_forbidden_fields_found": formula_forbidden_found,
        "errors": errors,
    }


def _process_eligible_snapshot(
    *,
    snap: SimpleNamespace,
    market_rows: list[Any],
    by_market: dict[str, dict[str, Any]],
    by_family: dict[str, dict[str, Any]],
    by_competition: dict[str, dict[str, Any]],
    workload: dict[str, Any],
    quote_quality: dict[str, Any],
    fair_checks: dict[str, Any],
    performance_coverage: dict[str, Any],
    input_coverage: dict[str, Any],
    integrity_counts: dict[str, Any],
    example_store: dict[str, list[dict[str, Any]]],
    problematic_snaps: list[dict[str, Any]],
) -> bool:
    """Elabora un singolo snapshot eligible. Ritorna True se ci sono duplicati."""
    sid = int(snap.id)
    comp = str(snap.competition_name or "unknown")
    by_competition[comp]["snapshots_eligible"] += 1

    policy = evaluate_historical_integrity_policy(
        snap,
        eligibility_verified=True,
        formula_whitelist_verified=True,
        post_match_excluded=True,
        phase_separation_verified=True,
    )
    integrity = str(policy.get("integrity_gate") or "invalid")
    integrity_reasons = list(policy.get("reasons") or [])
    integrity_mode = str(policy.get("integrity_mode") or INTEGRITY_MODE_INVALID)

    if policy.get("historical_payload_hash_present"):
        integrity_counts["with_payload_hash"] += 1
        integrity_counts["with_pre_match_hash"] += 1
    if policy.get("historical_freeze_lock_present"):
        integrity_counts["with_historical_freeze_lock"] += 1
        integrity_counts["with_pre_match_lock"] += 1

    chrono = str(policy.get("chronological_lock_check") or CHRONOLOGY_NOT_APPLICABLE)
    if chrono == CHRONOLOGY_PASSED:
        integrity_counts["chronological_lock_check_applicable"] += 1
        integrity_counts["chronological_lock_check_passed"] += 1
        integrity_counts["lock_before_kickoff"] += 1
        integrity_counts["prospective_pre_match_verified"] += 1
    elif chrono == CHRONOLOGY_FAILED:
        integrity_counts["chronological_lock_check_applicable"] += 1
        integrity_counts["chronological_lock_check_failed"] += 1
        integrity_counts["invalid_lock_timestamp"] += 1
    else:
        integrity_counts["chronological_lock_check_not_applicable"] += 1

    if integrity_mode == INTEGRITY_MODE_FROZEN:
        integrity_counts["historical_reconstruction_verified"] += 1
    elif integrity_mode == INTEGRITY_MODE_INCOMPLETE:
        integrity_counts["historical_reconstruction_with_warning"] += 1
    elif integrity_mode == INTEGRITY_MODE_INVALID:
        integrity_counts["historical_reconstruction_invalid"] += 1
    elif integrity_mode == INTEGRITY_MODE_PROSPECTIVE:
        # Prospective già contato sopra; non è invalid storico.
        pass

    keyed: dict[str, list[Any]] = defaultdict(list)
    for m in market_rows:
        keyed[str(getattr(m, "market_key", "") or "")].append(m)

    duplicate_keys = {k for k, v in keyed.items() if len(v) > 1 and is_v3_supported_market(k)}
    has_duplicates = bool(duplicate_keys)
    if has_duplicates:
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

    by_mk_single: dict[str, Any] = {k: v[0] for k, v in keyed.items() if len(v) == 1}
    by_mk_for_opp = {k: v[0] for k, v in keyed.items()}

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

        wl_key = map_score_status_to_workload_key(score_status)
        if wl_key is None:
            bucket["unsupported_market"] += 1
            workload["unsupported_market_rows"] = int(workload.get("unsupported_market_rows") or 0) + 1
            # Non dovrebbe accadere su V3_MARKET_ORDER; conta come unclassified.
            workload["unclassified_evaluations"] = int(workload.get("unclassified_evaluations") or 0) + 1
            bucket["unclassified"] += 1
        else:
            workload[wl_key] = int(workload.get(wl_key) or 0) + 1
            bucket[wl_key] = int(bucket.get(wl_key) or 0) + 1
            bucket["classified_total"] = int(bucket.get("classified_total") or 0) + 1
            workload["classified_evaluations_total"] = (
                int(workload.get("classified_evaluations_total") or 0) + 1
            )
            if wl_key == "exact_replay_ready":
                by_family[fam]["exact_replay_ready"] += 1
                by_competition[comp]["exact_replay_ready"] += 1
            elif wl_key == "ready_with_warning":
                by_family[fam]["ready_with_warning"] += 1
            elif wl_key == "not_replayable":
                by_family[fam]["not_replayable"] += 1
                by_competition[comp]["missing_inputs"] += 1
            elif wl_key in ("invalid_integrity", "ambiguous_market_join"):
                snap_has_blocker = True

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
                        "integrity_mode": integrity_mode,
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

    return has_duplicates


def _blocked_payload(
    *,
    run: CecchinoLabHistoricalScanRun,
    runtime_rev: dict[str, Any],
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    include_probe: bool = False,
) -> dict[str, Any]:
    scope = _run_scope_meta(run)
    base = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "integrity_policy_version": INTEGRITY_POLICY_VERSION,
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
            "invalid_integrity": 0,
            "ambiguous_market_join": 0,
            "classified_evaluations_total": 0,
            "unclassified_evaluations": 0,
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
            "formula_payload_allowed_fields": list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
            "formula_payload_forbidden_fields_found": [],
            "performance_fields_loaded_but_not_forwarded": True,
            "anti_leakage_status": "enforced_in_preflight_contract",
            "result_fields_passed_to_formula": False,
            "settlement_fields_passed_to_formula": False,
        },
        "probe": {
            "probe_is_diagnostic_only": True,
            "probe_not_a_backtest": True,
            "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
            "skipped": True,
            "reason": "run_blocked" if not include_probe else "run_blocked",
        },
        "resource_profile": _empty_resource_profile(probe_requested=include_probe),
        "query_profile": _empty_query_profile(),
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
                "preflight_resource_budget_exceeded",
                "unclassified_replay_evaluations",
                "probe_formula_error",
                "forbidden_fields_forwarded_to_formula",
            ],
            "ready_with_warnings_if": [
                "replay_possible_with_incomplete_coverage",
                "partial_run",
                "derived_quotes_diagnostic_only",
                "linked_context_absent",
                "historical_lock_chronology_not_applicable",
            ],
            "ready_if": [
                "no_blockers",
                "deterministic_replay",
                "mandatory_inputs_available",
                "coverage_losses_only_expected_unavailable_markets",
                "all_evaluations_classified",
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


def _compute_preflight(
    db: Session,
    run_id: int,
    *,
    include_probe: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    phase = "init"
    resource_profile = _empty_resource_profile(probe_requested=include_probe)
    query_profile = _empty_query_profile()

    run = db.get(CecchinoLabHistoricalScanRun, run_id)
    if not run:
        raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

    runtime_rev = resolve_code_revision()
    scope = _run_scope_meta(run)
    is_partial = bool(scope.get("is_partial_run"))

    def _attach_profiles(payload: dict[str, Any]) -> dict[str, Any]:
        resource_profile["duration_ms"] = int((time.monotonic() - started) * 1000)
        payload["resource_profile"] = resource_profile
        payload["query_profile"] = query_profile
        return make_json_safe(payload)

    if run.status in ACTIVE_STATUSES:
        return _attach_profiles(
            _blocked_payload(
                run=run,
                runtime_rev=runtime_rev,
                include_probe=include_probe,
                blockers=[
                    _issue(
                        "run_active",
                        "Il run è ancora attivo: preflight consentito solo come blocked, replay non pronto.",
                        run_status=run.status,
                    )
                ],
            )
        )

    if run.status in (STATUS_FAILED, STATUS_CANCELLED):
        return _attach_profiles(
            _blocked_payload(
                run=run,
                runtime_rev=runtime_rev,
                include_probe=include_probe,
                blockers=[
                    _issue(
                        "run_terminal_incompatible",
                        f"Run in stato {run.status}: replay non affidabile.",
                        run_status=run.status,
                    )
                ],
            )
        )

    if run.status not in ALLOWED_RUN_STATUSES:
        return _attach_profiles(
            _blocked_payload(
                run=run,
                runtime_rev=runtime_rev,
                include_probe=include_probe,
                blockers=[
                    _issue(
                        "run_status_unsupported",
                        f"Stato run non ammesso al preflight: {run.status}",
                        run_status=run.status,
                    )
                ],
            )
        )

    try:
        phase = "snapshot_aggregates"
        _budget_check_runtime(started, phase)
        aggregates = _load_snapshot_aggregates(db, int(run.id), query_profile)

        if aggregates["snapshots_eligible_core"] <= 0:
            return _attach_profiles(
                _blocked_payload(
                    run=run,
                    runtime_rev=runtime_rev,
                    include_probe=include_probe,
                    blockers=[
                        _issue(
                            "zero_eligible_core",
                            "Nessuno snapshot eligible_core: replay non possibile senza nuova scansione.",
                        )
                    ],
                    extra={
                        "source_integrity": {
                            "snapshots_total": aggregates["snapshots_total"],
                            "snapshots_eligible_core": 0,
                            "snapshots_excluded": aggregates["snapshots_excluded"],
                            "exclusions_by_reason": aggregates["exclusions_by_reason"],
                        }
                    },
                )
            )

        phase = "market_counts"
        _budget_check_runtime(started, phase)
        supported_rows = _count_supported_market_rows(db, int(run.id), query_profile)
        unsupported_rows = _count_unsupported_market_rows(db, int(run.id), query_profile)

        if supported_rows > PREFLIGHT_MAX_SUPPORTED_ROWS:
            resource_profile["resource_budget_exceeded"] = True
            logger.warning(
                "purchasability_v3_preflight_budget_exceeded run_id=%s supported_rows=%s",
                run_id,
                supported_rows,
            )
            raise PreflightResourceBudgetExceeded(
                "preflight_resource_budget_exceeded",
                f"Righe mercato supportate ({supported_rows}) oltre il budget "
                f"({PREFLIGHT_MAX_SUPPORTED_ROWS}).",
                phase="market_counts",
                supported_rows=supported_rows,
                limit=PREFLIGHT_MAX_SUPPORTED_ROWS,
            )

        phase = "eligible_snap_meta"
        _budget_check_runtime(started, phase)
        eligible_meta = _load_eligible_snap_meta(db, int(run.id), query_profile)
        eligible_n = len(eligible_meta)

        example_store = _example_store()
        problematic_snaps: list[dict[str, Any]] = []
        by_market = {mk: _empty_market_bucket() for mk in V3_MARKET_ORDER}
        by_family = {fam: _empty_family_bucket() for fam in FAMILY_ORDER}
        by_competition: dict[str, dict[str, Any]] = defaultdict(_empty_competition_bucket)

        workload = {
            "supported_markets_per_snapshot": 8,
            "theoretical_evaluations": eligible_n * 8,
            "market_rows_found": 0,
            "exact_replay_ready": 0,
            "ready_with_warning": 0,
            "gate_only_ready": 0,
            "not_replayable": 0,
            "invalid_integrity": 0,
            "ambiguous_market_join": 0,
            "classified_evaluations_total": 0,
            "unclassified_evaluations": 0,
            "unsupported_market_rows": unsupported_rows,
            "family_decisions_theoretical": eligible_n * 3,
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
        integrity_counts = _empty_integrity_counts(
            snapshots_total=aggregates["snapshots_total"],
            snapshots_eligible_core=eligible_n,
            snapshots_excluded=aggregates["snapshots_excluded"],
            exclusions_by_reason=aggregates["exclusions_by_reason"],
        )

        structural_duplicates = False
        processed_eligible: set[int] = set()
        current_sid: int | None = None
        current_rows: list[Any] = []
        max_held = 0
        rows_streamed = 0

        phase = "market_stream"
        for raw_row in _iter_supported_market_rows(db, int(run.id), query_profile):
            _budget_check_runtime(started, phase)
            row = _row_to_ns(raw_row)
            sid = int(row.match_snapshot_id)
            rows_streamed += 1

            if current_sid is None:
                current_sid = sid
            if sid != current_sid:
                if current_sid in eligible_meta:
                    dup = _process_eligible_snapshot(
                        snap=eligible_meta[current_sid],
                        market_rows=current_rows,
                        by_market=by_market,
                        by_family=by_family,
                        by_competition=by_competition,
                        workload=workload,
                        quote_quality=quote_quality,
                        fair_checks=fair_checks,
                        performance_coverage=performance_coverage,
                        input_coverage=input_coverage,
                        integrity_counts=integrity_counts,
                        example_store=example_store,
                        problematic_snaps=problematic_snaps,
                    )
                    structural_duplicates = structural_duplicates or dup
                    processed_eligible.add(current_sid)
                current_rows = []
                current_sid = sid

            current_rows.append(row)
            if len(current_rows) > max_held:
                max_held = len(current_rows)
            # Cap difesa: non accumulare oltre i mercati V3 attesi + margine duplicati
            if len(current_rows) > 20:
                # Mantieni comunque il gruppo corrente fino al cambio sid,
                # ma registra il massimo reale tenuto.
                pass

        if current_sid is not None and current_sid in eligible_meta and current_sid not in processed_eligible:
            dup = _process_eligible_snapshot(
                snap=eligible_meta[current_sid],
                market_rows=current_rows,
                by_market=by_market,
                by_family=by_family,
                by_competition=by_competition,
                workload=workload,
                quote_quality=quote_quality,
                fair_checks=fair_checks,
                performance_coverage=performance_coverage,
                input_coverage=input_coverage,
                integrity_counts=integrity_counts,
                example_store=example_store,
                problematic_snaps=problematic_snaps,
            )
            structural_duplicates = structural_duplicates or dup
            processed_eligible.add(current_sid)
        current_rows = []

        # Eligible senza market rows nello stream
        for sid, snap in eligible_meta.items():
            if sid in processed_eligible:
                continue
            _budget_check_runtime(started, "eligible_without_markets")
            dup = _process_eligible_snapshot(
                snap=snap,
                market_rows=[],
                by_market=by_market,
                by_family=by_family,
                by_competition=by_competition,
                workload=workload,
                quote_quality=quote_quality,
                fair_checks=fair_checks,
                performance_coverage=performance_coverage,
                input_coverage=input_coverage,
                integrity_counts=integrity_counts,
                example_store=example_store,
                problematic_snaps=problematic_snaps,
            )
            structural_duplicates = structural_duplicates or dup

        resource_profile["market_rows_streamed"] = rows_streamed
        resource_profile["max_market_rows_held_in_memory"] = max_held

        # Allinea classified totals e unclassified rispetto a theoretical.
        classified_sum = sum(int(workload.get(k) or 0) for k in WORKLOAD_CLASSIFICATION_KEYS)
        theoretical = int(workload["theoretical_evaluations"])
        workload["classified_evaluations_total"] = classified_sum
        if classified_sum < theoretical:
            workload["unclassified_evaluations"] = theoretical - classified_sum
        else:
            # Se classified > theoretical (non dovrebbe), non creare negativo.
            workload["unclassified_evaluations"] = max(
                0, int(workload.get("unclassified_evaluations") or 0)
            )
            if classified_sum > theoretical:
                workload["unclassified_evaluations"] = 0

        for mk, bucket in by_market.items():
            m_classified = sum(int(bucket.get(k) or 0) for k in WORKLOAD_CLASSIFICATION_KEYS)
            bucket["classified_total"] = m_classified
            eligible_rows = int(bucket.get("eligible_rows") or 0)
            bucket["unclassified"] = max(0, eligible_rows - m_classified)

        # Dominant integrity mode for UI.
        if integrity_counts["historical_reconstruction_verified"] > 0:
            integrity_counts["integrity_mode_dominant"] = INTEGRITY_MODE_FROZEN
        elif integrity_counts["prospective_pre_match_verified"] > 0:
            integrity_counts["integrity_mode_dominant"] = INTEGRITY_MODE_PROSPECTIVE
        elif integrity_counts["historical_reconstruction_with_warning"] > 0:
            integrity_counts["integrity_mode_dominant"] = INTEGRITY_MODE_INCOMPLETE
        elif integrity_counts["historical_reconstruction_invalid"] > 0:
            integrity_counts["integrity_mode_dominant"] = INTEGRITY_MODE_INVALID

        hash_present = integrity_counts["with_payload_hash"]
        lock_present = integrity_counts["with_historical_freeze_lock"]
        structural_integrity_absent = eligible_n > 0 and hash_present == 0 and lock_present == 0

        theoretical_safe = max(1, theoretical)
        replayable = workload["exact_replay_ready"] + workload["ready_with_warning"]
        missing_ratio = workload["not_replayable"] / theoretical_safe
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
                    "Hash e lock di congelamento assenti su tutti gli snapshot eleggibili.",
                )
            )
        if int(workload.get("unclassified_evaluations") or 0) > 0:
            blockers.append(
                _issue(
                    "unclassified_replay_evaluations",
                    "Esistono valutazioni teoriche non classificate: Go STEP 3B non consentito.",
                    unclassified=workload["unclassified_evaluations"],
                    theoretical=theoretical,
                    classified=workload["classified_evaluations_total"],
                )
            )
        by_market_mismatch = [
            mk
            for mk, b in by_market.items()
            if int(b.get("classified_total") or 0) != int(b.get("eligible_rows") or 0)
        ]
        if by_market_mismatch:
            warnings.append(
                _issue(
                    "by_market_classification_mismatch",
                    "classified_total != eligible_rows su uno o più mercati.",
                    markets=by_market_mismatch[:8],
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
        if integrity_counts["with_payload_hash"] < eligible_n:
            warnings.append(
                _issue(
                    "partial_pre_match_hash",
                    "Alcuni snapshot eleggibili sono senza hash di congelamento.",
                    with_hash=integrity_counts["with_payload_hash"],
                    eligible=eligible_n,
                )
            )
        if integrity_counts["chronological_lock_check_not_applicable"] > 0:
            warnings.append(
                _issue(
                    "historical_lock_chronology_not_applicable",
                    "Il controllo lock < kickoff non è applicabile alla ricostruzione storica: "
                    "il lock certifica il freeze, non la cattura pre-partita.",
                    count=integrity_counts["chronological_lock_check_not_applicable"],
                )
            )
        if run.status == STATUS_COMPLETED_WITH_WARNINGS:
            warnings.append(
                _issue(
                    "run_completed_with_warnings",
                    "Il run è completed_with_warnings: verificare matches_error prima del replay completo.",
                )
            )

        phase = "probe"
        if not include_probe:
            probe = {
                "probe_is_diagnostic_only": True,
                "probe_not_a_backtest": True,
                "probe_snapshot_limit": PROBE_SNAPSHOT_LIMIT,
                "skipped": True,
                "reason": "not_requested",
            }
        elif blockers and any(
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
            _budget_check_runtime(started, phase)
            probe = _run_probe(
                db=db,
                run_id=int(run.id),
                eligible_meta=eligible_meta,
                query_profile=query_profile,
            )
            resource_profile["probe_snapshot_count"] = int(probe.get("snapshots_probed") or 0)
            if int(probe.get("snapshots_with_error") or 0) > 0 or int(probe.get("markets_error") or 0) > 0:
                blockers.append(
                    _issue(
                        "probe_formula_error",
                        "Il probe formula ha prodotto errori: Go STEP 3B non consentito.",
                        snapshots_with_error=probe.get("snapshots_with_error"),
                        markets_error=probe.get("markets_error"),
                    )
                )
            forbidden_found = list(probe.get("formula_payload_forbidden_fields_found") or [])
            if forbidden_found:
                blockers.append(
                    _issue(
                        "forbidden_fields_forwarded_to_formula",
                        "Campi post-match/forbidden trovati nel panel passato alla formula V3.",
                        fields=forbidden_found,
                    )
                )
            if (
                probe.get("expected_vs_returned_status") == "mismatch"
                and int(probe.get("formula_items_returned") or 0)
                != int(probe.get("panel_rows_submitted") or 0)
            ):
                # Documentato solo se mismatch non spiegato; warning non bloccante
                # se il motore restituisce meno item per gate (comportamento possibile).
                warnings.append(
                    _issue(
                        "probe_expected_vs_returned_mismatch",
                        "formula_items_returned diverso da panel_rows_submitted.",
                        panel_rows_submitted=probe.get("panel_rows_submitted"),
                        formula_items_returned=probe.get("formula_items_returned"),
                    )
                )

        anti_leakage = {
            "pre_match_input_fields": list(PRE_MATCH_INPUT_FIELDS),
            "post_match_performance_fields": list(POST_MATCH_PERFORMANCE_FIELDS),
            "forbidden_formula_fields": list(FORBIDDEN_FORMULA_FIELDS),
            "formula_payload_allowed_fields": list(FORMULA_PAYLOAD_ALLOWED_FIELDS),
            "formula_payload_forbidden_fields_found": list(
                (probe or {}).get("formula_payload_forbidden_fields_found") or []
            ),
            "performance_fields_loaded_but_not_forwarded": True,
            "anti_leakage_status": "enforced_in_preflight_contract",
            "result_fields_passed_to_formula": False,
            "settlement_fields_passed_to_formula": False,
        }

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

        issue_examples = {
            k: v[:MAX_EXAMPLES_PER_REASON] for k, v in list(example_store.items())[:40]
        }

        payload = {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "integrity_policy_version": INTEGRITY_POLICY_VERSION,
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
            "anti_leakage": anti_leakage,
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
                    "preflight_resource_budget_exceeded",
                    "unclassified_replay_evaluations",
                    "probe_formula_error",
                    "forbidden_fields_forwarded_to_formula",
                ],
                "ready_with_warnings_if": [
                    "replay_possible_with_incomplete_coverage",
                    "partial_run",
                    "derived_quotes_diagnostic_only",
                    "linked_context_absent",
                    "historical_lock_chronology_not_applicable",
                ],
                "ready_if": [
                    "no_blockers",
                    "deterministic_replay",
                    "mandatory_inputs_available",
                    "all_evaluations_classified",
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
        return _attach_profiles(payload)

    except PreflightResourceBudgetExceeded as exc:
        resource_profile["resource_budget_exceeded"] = True
        logger.warning(
            "purchasability_v3_preflight_budget_exceeded run_id=%s phase=%s",
            run_id,
            getattr(exc, "details", {}).get("phase", phase),
        )
        return _attach_profiles(
            _blocked_payload(
                run=run,
                runtime_rev=runtime_rev,
                include_probe=include_probe,
                blockers=[
                    _issue(
                        "preflight_resource_budget_exceeded",
                        exc.message,
                        **(exc.details or {}),
                    )
                ],
            )
        )


def run_purchasability_v3_replay_preflight(
    db: Session,
    run_id: int,
    *,
    include_probe: bool = False,
) -> dict[str, Any]:
    """Entry point read-only. Cache in-memory distinta per include_probe."""
    logger.info(
        "purchasability_v3_preflight_started run_id=%s include_probe=%s",
        run_id,
        include_probe,
    )
    started = time.monotonic()
    try:
        run = db.get(CecchinoLabHistoricalScanRun, run_id)
        if not run:
            raise CecchinoLabImportError("run_not_found", "Run non trovato", status_code=404)

        runtime_rev = resolve_code_revision()
        cache_key = "|".join(
            [
                str(int(run_id)),
                PREFLIGHT_SCHEMA_VERSION,
                INTEGRITY_POLICY_VERSION,
                PURCHASABILITY_V3_FORMULA_VERSION,
                str(runtime_rev.get("git_commit") or "unknown"),
                "probe" if include_probe else "summary",
            ]
        )
        cached = _cache_get(cache_key)
        if cached is not None:
            out = dict(cached)
            out["cache_hit"] = True
            return out

        result = _compute_preflight(db, run_id, include_probe=include_probe)
        ttl = (
            CACHE_TTL_COMPLETED_S
            if run.status in ALLOWED_RUN_STATUSES
            else CACHE_TTL_BLOCKED_S
        )
        result["cache_hit"] = False
        _cache_set(cache_key, result, ttl)

        rp = result.get("resource_profile") or {}
        logger.info(
            "purchasability_v3_preflight_completed run_id=%s status=%s duration_ms=%s "
            "market_rows_streamed=%s max_rows_held=%s",
            run_id,
            result.get("status"),
            rp.get("duration_ms"),
            rp.get("market_rows_streamed"),
            rp.get("max_market_rows_held_in_memory"),
        )
        return result
    except CecchinoLabImportError:
        raise
    except Exception as exc:
        logger.exception(
            "purchasability_v3_preflight_failed run_id=%s phase=entry error_type=%s",
            run_id,
            type(exc).__name__,
        )
        raise
    finally:
        _ = started  # duration logged above when successful
