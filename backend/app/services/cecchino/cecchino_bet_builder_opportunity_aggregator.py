"""Bet Builder BET-01 — Opportunity Aggregator read-only su dati Cecchino Today.

OPPORTUNITY = PRICE_VALUE OR SIGNAL_VALUE
Nessun Bet Builder Score, nessuna write, nessuna API esterna, nessun fallback V3.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_goal_intensity_v5_preview import (
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    resolve_balance_v5_monitoring_snapshot,
)
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_AGGREGATOR_VERSION,
    BET_BUILDER_CONTRACT_VERSION,
    BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
    BET_BUILDER_SIGNAL_EVIDENCE_VERSION,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
    PRICE_VALUE_METHOD,
    PURCHASABILITY_POLICY,
    REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING,
    REASON_NO_VALIDATED_CONTEXT_MODULE,
    REASON_PURCHASABILITY_V31_UNAVAILABLE,
    REASON_SIGNALS_FORMULA_NOT_CURRENT,
    REASON_SIGNALS_MATRIX_UNAVAILABLE,
)
from app.services.cecchino.cecchino_bet_builder_freshness import (
    build_source_generated_from,
    compute_source_revision,
    resolve_source_scan_status,
)
from app.services.cecchino.cecchino_bet_builder_markets import (
    BALANCE_CONTEXT_MARKETS,
    BET_BUILDER_MARKET_KEYS,
    BET_BUILDER_MARKET_KEY_SET,
    GOAL_INTENSITY_CONTEXT_MARKETS,
    market_meta,
    signal_group_for_market,
)
from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
    OPERATIONAL_CALIBRATION_KEY,
    RAW_INDEX_ID,
    TARGET_CALIBRATION_MAPPING,
    is_official_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_active_bundle
from app.services.cecchino.cecchino_goal_intensity_v5_statistics_helpers import safe_float
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import rating_label
from app.services.cecchino.cecchino_purchasability_v31_candidate import (
    RATING_MIN_PURCHASE_SCOPE,
    evaluate_v31_gate,
)
from app.services.cecchino.cecchino_purchasability_v31_snapshot import (
    index_purchasability_v31_snapshot_by_market,
    resolve_purchasability_preview_v31_for_detail,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
)
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    SIGNAL_CONSENSUS_POLICY_VERSION,
    SINGLE_FORMULA_EXEMPT_GROUPS,
    consensus_by_group_from_matrix,
    get_current_signal_contract,
    inherit_draw_consensus,
    is_current_signal_matrix,
)
from app.services.cecchino.cecchino_signal_odds_refresh import _kpi_row_for_market


def opportunity_key(today_fixture_id: int, market_key: str) -> str:
    return f"{int(today_fixture_id)}:{market_key}"


def _finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def build_price_value(kpi_row: dict[str, Any] | None) -> dict[str, Any]:
    """PRICE_VALUE via gate teorico V3.1 (edge>0 ∧ vantaggio>0 ∧ rating>=scope).

    Riusa ``evaluate_v31_gate`` / ``RATING_MIN_PURCHASE_SCOPE``. Lo score V3.1
    non è gate; purchasability persistita non è richiesta.
    """
    if not isinstance(kpi_row, dict):
        return {
            "present": False,
            "method": PRICE_VALUE_METHOD,
            "quota_book": None,
            "quota_cecchino": None,
            "prob_book": None,
            "prob_cecchino": None,
            "vantaggio_prob": None,
            "edge_pct": None,
            "score_acquisto": None,
            "rating": None,
            "rating_label": None,
            "status": None,
            "book_source": None,
            "cecchino_source": None,
        }

    quota_book = _finite_number(kpi_row.get("quota_book"))
    quota_cecchino = _finite_number(kpi_row.get("quota_cecchino"))
    edge_pct = _finite_number(kpi_row.get("edge_pct"))

    # Gate canonico V3.1: edge > 0 AND vantaggio_prob > 0 AND rating >= RATING_MIN_PURCHASE_SCOPE
    gate = evaluate_v31_gate(kpi_row)
    present = (
        gate.get("gate_status") == "passed"
        and gate.get("rating_threshold") == RATING_MIN_PURCHASE_SCOPE
    )

    rating = kpi_row.get("rating")
    try:
        rating_int = int(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating_int = None

    r_label = kpi_row.get("rating_label")
    if r_label is None and rating_int is not None:
        r_label = rating_label(rating_int)

    return {
        "present": bool(present),
        "method": PRICE_VALUE_METHOD,
        "quota_book": quota_book,
        "quota_cecchino": quota_cecchino,
        "prob_book": _finite_number(kpi_row.get("prob_book")),
        "prob_cecchino": _finite_number(kpi_row.get("prob_cecchino")),
        "vantaggio_prob": _finite_number(kpi_row.get("vantaggio_prob")),
        "edge_pct": edge_pct,
        "score_acquisto": _finite_number(kpi_row.get("score_acquisto")),
        "rating": rating_int,
        "rating_label": r_label,
        "status": kpi_row.get("status"),
        "book_source": kpi_row.get("book_source"),
        "cecchino_source": kpi_row.get("cecchino_source"),
    }


def _yes_columns_display(raw_columns: Any) -> list[str]:
    """Colonne SI distinte; display corto D/E/F/G/SCALA senza duplicati."""
    if not isinstance(raw_columns, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for col in raw_columns:
        text = str(col or "").strip()
        if not text:
            continue
        short = text
        if text.startswith("EXCEL_"):
            short = text.replace("EXCEL_", "", 1)
        if short in seen:
            continue
        seen.add(short)
        out.append(short)
    return out


def _signals_unavailable(*, reason: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or get_current_signal_contract()
    return {
        "available": False,
        "present": False,
        "formula_version": contract.get("formula_version"),
        "consensus_policy_version": contract.get("consensus_policy_version"),
        "evidence_mode": None,
        "yes_count": 0,
        "required_count": 0,
        "available_count": 0,
        "yes_columns": [],
        "passed": False,
        "consensus_exempt": False,
        "reason": reason,
    }


def build_signals_evidence(
    *,
    market_key: str,
    signals_matrix: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evidenza formula pre-value-gate. Non usa is_acquired come gate."""
    contract = get_current_signal_contract()

    if not isinstance(signals_matrix, dict):
        return _signals_unavailable(reason=REASON_SIGNALS_MATRIX_UNAVAILABLE, contract=contract)

    if not is_current_signal_matrix(signals_matrix):
        return _signals_unavailable(reason=REASON_SIGNALS_FORMULA_NOT_CURRENT, contract=contract)

    by_group = consensus_by_group_from_matrix(signals_matrix)
    formula_version = str(
        signals_matrix.get("formula_version") or CURRENT_SIGNAL_FORMULA_VERSION
    )
    policy = SIGNAL_CONSENSUS_POLICY_VERSION

    # X PT: derivazione canonica da DRAW (pre-value-gate)
    if market_key == SEL_DRAW_PT:
        draw = by_group.get("DRAW")
        if not isinstance(draw, dict):
            return {
                "available": False,
                "present": False,
                "formula_version": formula_version,
                "consensus_policy_version": policy,
                "evidence_mode": None,
                "yes_count": 0,
                "required_count": 0,
                "available_count": 0,
                "yes_columns": [],
                "passed": False,
                "consensus_exempt": False,
                "source_group": "DRAW",
                "reason": REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING,
            }
        inherited = inherit_draw_consensus(draw)
        yes_cols = _yes_columns_display(inherited.get("consensus_yes_columns"))
        passed = bool(inherited.get("consensus_passed"))
        return {
            "available": True,
            "present": passed,
            "formula_version": formula_version,
            "consensus_policy_version": policy,
            "evidence_mode": "derived_from_draw_consensus",
            "yes_count": int(inherited.get("consensus_yes_count") or 0),
            "required_count": int(inherited.get("consensus_required_count") or 0),
            "available_count": int(inherited.get("consensus_available_count") or 0),
            "yes_columns": yes_cols,
            "passed": passed,
            "consensus_exempt": False,
            "source_group": "DRAW",
        }

    signal_group = signal_group_for_market(market_key)
    if signal_group is None:
        return {
            "available": False,
            "present": False,
            "formula_version": formula_version,
            "consensus_policy_version": policy,
            "evidence_mode": None,
            "yes_count": 0,
            "required_count": 0,
            "available_count": 0,
            "yes_columns": [],
            "passed": False,
            "consensus_exempt": False,
            "reason": REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING,
        }

    consensus = by_group.get(signal_group)
    if not isinstance(consensus, dict):
        return {
            "available": True,
            "present": False,
            "formula_version": formula_version,
            "consensus_policy_version": policy,
            "evidence_mode": (
                "direct_single_formula"
                if signal_group in SINGLE_FORMULA_EXEMPT_GROUPS
                else "consensus"
            ),
            "yes_count": 0,
            "required_count": 1 if signal_group in SINGLE_FORMULA_EXEMPT_GROUPS else 2,
            "available_count": 0,
            "yes_columns": [],
            "passed": False,
            "consensus_exempt": signal_group in SINGLE_FORMULA_EXEMPT_GROUPS,
        }

    yes_cols = _yes_columns_display(consensus.get("consensus_yes_columns"))
    passed = bool(consensus.get("consensus_passed"))
    exempt = signal_group in SINGLE_FORMULA_EXEMPT_GROUPS
    evidence_mode = "direct_single_formula" if exempt else "consensus"

    return {
        "available": True,
        "present": passed,
        "formula_version": formula_version,
        "consensus_policy_version": str(
            consensus.get("consensus_policy_version") or policy
        ),
        "evidence_mode": evidence_mode,
        "yes_count": int(consensus.get("consensus_yes_count") or 0),
        "required_count": int(consensus.get("consensus_required_count") or 0),
        "available_count": int(consensus.get("consensus_available_count") or 0),
        "yes_columns": yes_cols,
        "passed": passed,
        "consensus_exempt": exempt,
    }


def _origin(price_present: bool, signal_present: bool) -> str | None:
    if price_present and signal_present:
        return ORIGIN_PRICE_AND_SIGNALS
    if price_present:
        return ORIGIN_PRICE
    if signal_present:
        return ORIGIN_SIGNALS
    return None


def build_purchasability_v31_block(
    *,
    market_key: str,
    v31_by_market: dict[str, dict[str, Any]],
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    item = v31_by_market.get(market_key)
    if not isinstance(item, dict):
        return {
            "available": False,
            "version": "v31",
            "score": None,
            "raw_score": None,
            "class": None,
            "status": None,
            "calculation_quality": None,
            "gate_status": None,
            "gate_reason_codes": [],
            "formula_version": None,
            "candidate_version": None,
            "registry_status": None,
            "source_mode": None,
            "generated_at": None,
            "reason": REASON_PURCHASABILITY_V31_UNAVAILABLE,
        }

    hist = item.get("historical") if isinstance(item.get("historical"), dict) else {}
    generated_at = (
        item.get("generated_at")
        or item.get("snapshot_at")
        or (snapshot.get("generated_at") if isinstance(snapshot, dict) else None)
        or (snapshot.get("snapshot_at") if isinstance(snapshot, dict) else None)
    )
    score = item.get("score_v31")
    if score is None:
        score = item.get("score")
    raw_score = item.get("raw_score_v31")
    if raw_score is None:
        raw_score = item.get("raw_score")
    class_v = item.get("class_v31")
    if class_v is None:
        class_v = item.get("class")

    return {
        "available": True,
        "version": "v31",
        "market_key": item.get("market_key") or market_key,
        "market_label": item.get("market_label") or item.get("label"),
        "market_family": item.get("market_family"),
        "period": item.get("period"),
        "line": item.get("line"),
        "status": item.get("status"),
        "calculation_quality": item.get("calculation_quality"),
        "score": score,
        "raw_score": raw_score,
        "class": class_v,
        "gate_status": item.get("gate_status"),
        "gate_reason_codes": list(item.get("gate_reason_codes") or []),
        "reading_short": item.get("reading_short"),
        "reading_detailed": item.get("reading_detailed"),
        "reason_codes": list(item.get("reason_codes") or []),
        "warnings": list(item.get("warnings") or []),
        "formula_version": item.get("formula_version"),
        "formula_config_version": item.get("formula_config_version"),
        "candidate_version": item.get("candidate_version")
        or (snapshot.get("candidate_version") if isinstance(snapshot, dict) else None),
        "candidate_name": item.get("candidate_name"),
        "registry_status": item.get("registry_status")
        or (snapshot.get("registry_status") if isinstance(snapshot, dict) else None),
        "source_mode": (
            (snapshot.get("source_mode") if isinstance(snapshot, dict) else None)
            or item.get("source_mode")
        ),
        "generated_at": generated_at,
        "source_snapshot_at": item.get("source_snapshot_at")
        or (snapshot.get("source_snapshot_at") if isinstance(snapshot, dict) else None),
        "source_snapshot_verified": item.get("source_snapshot_verified")
        or (
            snapshot.get("source_snapshot_verified")
            if isinstance(snapshot, dict)
            else None
        ),
        "source_snapshot_before_kickoff": item.get("source_snapshot_before_kickoff")
        or (
            snapshot.get("source_snapshot_before_kickoff")
            if isinstance(snapshot, dict)
            else None
        ),
        "historical_multiplier": item.get("historical_multiplier")
        or hist.get("historical_multiplier"),
        "historical_adjustment_points": item.get("historical_adjustment_points")
        or hist.get("historical_adjustment_points"),
        "historical_adjustment_pct": item.get("historical_adjustment_pct")
        or hist.get("historical_adjustment_pct"),
        "historical_reason_codes": list(
            item.get("historical_reason_codes")
            or hist.get("historical_reason_codes")
            or []
        ),
    }


def _balance_context(row: CecchinoTodayFixture) -> dict[str, Any]:
    resolved = resolve_balance_v5_monitoring_snapshot(row)
    payload = resolved.get("payload") if isinstance(resolved, dict) else None
    if not isinstance(payload, dict) or not payload:
        return {
            "available": False,
            "module": "balance_v5",
            "status": "unavailable",
            "reason": "balance_v5_unavailable",
            "payload": None,
        }
    # Snapshot monitoring canonico: gap_index / *_class (compact_balance_v5_monitoring_snapshot).
    # Fallback sui nomi legacy/errati solo per retrocompatibilità payload non canonici.
    gap_index = payload.get("gap_index")
    if gap_index is None:
        gap_index = payload.get("gap_coherence_index")
    f36_class = payload.get("f36_class")
    if f36_class is None:
        f36_class = payload.get("f36_class_label")
    dominance_class = payload.get("dominance_class")
    if dominance_class is None:
        dominance_class = payload.get("dominance_class_label")
    draw_credibility_class = payload.get("draw_credibility_class")
    if draw_credibility_class is None:
        draw_credibility_class = payload.get("draw_credibility_class_label")
    gap_class = payload.get("gap_class")
    if gap_class is None:
        gap_class = payload.get("gap_coherence_class_label")
    # Solo contesto raw — nessun supports/contradicts
    return {
        "available": True,
        "module": "balance_v5",
        "status": "raw_context_only",
        "payload": {
            "status": payload.get("status"),
            "version": payload.get("balance_version") or payload.get("version"),
            "snapshot_version": payload.get("snapshot_version"),
            "source_mode": payload.get("source_mode") or resolved.get("mode"),
            "pillar_order": payload.get("pillar_order")
            or ["f36", "dominance", "draw_credibility", "gap_coherence"],
            "pillars": {
                "f36": {
                    "index": payload.get("f36_index"),
                    "class_label": f36_class,
                },
                "dominance": {
                    "index": payload.get("dominance_index"),
                    "class_label": dominance_class,
                },
                "draw_credibility": {
                    "index": payload.get("draw_credibility_index"),
                    "class_label": draw_credibility_class,
                },
                "gap_coherence": {
                    "index": gap_index,
                    "class_label": gap_class,
                },
            },
            "f36_index": payload.get("f36_index"),
            "dominance_index": payload.get("dominance_index"),
            "draw_credibility_index": payload.get("draw_credibility_index"),
            "gap_coherence_index": gap_index,
            "prob_1_norm": payload.get("prob_1_norm"),
            "prob_x_norm": payload.get("prob_x_norm"),
            "prob_2_norm": payload.get("prob_2_norm"),
            "snapshot_timestamp": payload.get("snapshot_timestamp"),
            "pre_match_verified": payload.get("pre_match_verified"),
        },
    }


def _gi_context_for_market(
    *,
    market_key: str,
    gi_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(gi_payload, dict) or gi_payload.get("status") not in {
        "ok",
        "available",
    }:
        return {
            "available": False,
            "module": "goal_intensity_v5",
            "status": "unavailable",
            "reason": "goal_intensity_unavailable",
            "payload": None,
        }

    source = str(gi_payload.get("source") or "")
    presentation = str(gi_payload.get("presentation") or "")
    officialish = source == "v5_official"
    fallback = source == "v4_fallback"
    legacy = source == "v5_legacy_preview" or presentation in {
        "legacy_preview",
        "legacy_archive",
    }

    outputs = gi_payload.get("outputs") if isinstance(gi_payload.get("outputs"), dict) else {}
    index = gi_payload.get("index") if isinstance(gi_payload.get("index"), dict) else {}

    def _prob(key: str) -> float | None:
        block = outputs.get(key)
        if isinstance(block, dict):
            return safe_float(block.get("probability"))
        return None

    expected_block = outputs.get("expected_total_goals")
    expected = None
    expected_cal = None
    if isinstance(expected_block, dict):
        expected = safe_float(expected_block.get("value"))
        expected_cal = expected_block.get("calibration_source")

    selection_prob: float | None = None
    opposite_prob: float | None = None
    calibration_source: str | None = None

    if market_key == SEL_OVER_1_5:
        selection_prob = _prob("over_1_5")
        opposite_prob = _prob("under_1_5")
        calibration_source = TARGET_CALIBRATION_MAPPING.get("goals_ge_2") or RAW_INDEX_ID
    elif market_key == SEL_UNDER_1_5:
        selection_prob = _prob("under_1_5")
        opposite_prob = _prob("over_1_5")
        calibration_source = TARGET_CALIBRATION_MAPPING.get("goals_ge_2") or RAW_INDEX_ID
    elif market_key == SEL_OVER_2_5:
        selection_prob = _prob("over_2_5")
        opposite_prob = _prob("under_2_5")
        calibration_source = TARGET_CALIBRATION_MAPPING.get("goals_ge_3")
    elif market_key == SEL_UNDER_2_5:
        selection_prob = _prob("under_2_5")
        opposite_prob = _prob("over_2_5")
        calibration_source = TARGET_CALIBRATION_MAPPING.get("goals_ge_3")

    # Non spacciare legacy come official
    module_label = "goal_intensity_v5"
    status = "raw_context_only"
    if legacy:
        status = "legacy_preview_raw_context"
    elif fallback:
        status = "v4_fallback_raw_context"

    return {
        "available": True,
        "module": module_label,
        "status": status,
        "payload": {
            "module_version": gi_payload.get("module_version"),
            "bundle_version": gi_payload.get("bundle_version"),
            "source": source or None,
            "presentation": presentation or None,
            "official": officialish and not legacy,
            "data_quality": gi_payload.get("data_quality"),
            "raw_index": index.get("id") or RAW_INDEX_ID,
            "raw_index_score": index.get("score"),
            "expected_total_goals": expected,
            "expected_total_goals_calibration_source": expected_cal,
            "probability_selection": selection_prob,
            "probability_opposite": opposite_prob,
            "calibration_source": calibration_source,
            "market_key": market_key,
        },
    }


def _build_gi_payload_from_snapshot(
    *,
    snap: CecchinoGoalIntensityV5PreviewSnapshot,
    bundle: Any,
) -> dict[str, Any]:
    """Costruisce un payload contestuale read-only senza chiamare detail per fixture.

    Non include goals FT/HT / settlement (anti-leakage).
    """
    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        OFFICIAL_BUNDLE_VERSION,
        OFFICIAL_MODULE_VERSION,
        OPERATIONAL_STATUS,
        ROLE,
        SIGNALS_INTEGRATION_STATUS,
    )

    cal_all = snap.calibrated_predictions_payload or {}
    op = {}
    if isinstance(cal_all, dict):
        op = cal_all.get(OPERATIONAL_CALIBRATION_KEY) or {}
        if not isinstance(op, dict):
            op = {}

    official = is_official_bundle(bundle)
    if not official:
        return {
            "status": "ok",
            "module_version": getattr(bundle, "version", None),
            "bundle_version": getattr(bundle, "version", None),
            "source": "v5_legacy_preview",
            "presentation": "legacy_preview",
            "index": {"id": RAW_INDEX_ID, "score": snap.primary_candidate_score},
            "outputs": {},
            "data_quality": {
                "feature_status": snap.feature_status,
                "history_sample_size": snap.history_sample_size,
            },
            "no_betting_signals": True,
        }

    incomplete = str(snap.feature_status or "") in {
        "incomplete",
        "fallback_v4",
        "unavailable",
    } or str(snap.snapshot_status or "") == "incomplete"

    if incomplete or not op:
        return {
            "status": "unavailable",
            "source": "none",
            "module_version": OFFICIAL_MODULE_VERSION,
            "bundle_version": getattr(bundle, "version", None) or OFFICIAL_BUNDLE_VERSION,
        }

    p_ge2 = safe_float(op.get("probability_goals_ge_2"))
    p_ge3 = safe_float(op.get("probability_goals_ge_3"))
    expected = safe_float(op.get("expected_total_goals"))
    p_u15 = safe_float(op.get("probability_under_1_5"))
    p_u25 = safe_float(op.get("probability_under_2_5"))
    if p_u15 is None and p_ge2 is not None:
        p_u15 = round(max(1e-6, min(1.0 - 1e-6, 1.0 - p_ge2)), 6)
    if p_u25 is None and p_ge3 is not None:
        p_u25 = round(max(1e-6, min(1.0 - 1e-6, 1.0 - p_ge3)), 6)
    raw_score = safe_float(op.get("raw_score"))
    if raw_score is None:
        raw_score = safe_float(snap.primary_candidate_score)

    return {
        "status": "ok",
        "module_version": OFFICIAL_MODULE_VERSION,
        "bundle_version": getattr(bundle, "version", None) or OFFICIAL_BUNDLE_VERSION,
        "operational_status": OPERATIONAL_STATUS,
        "role": ROLE,
        "signals_integration_status": SIGNALS_INTEGRATION_STATUS,
        "source": "v5_official",
        "presentation": "official",
        "index": {"id": RAW_INDEX_ID, "score": raw_score},
        "outputs": {
            "expected_total_goals": {
                "value": expected,
                "calibration_source": TARGET_CALIBRATION_MAPPING.get("total_goals_ft"),
            },
            "over_1_5": {
                "probability": p_ge2,
                "calibration_source": TARGET_CALIBRATION_MAPPING.get("goals_ge_2"),
            },
            "under_1_5": {"probability": p_u15, "derived_as_complement": True},
            "over_2_5": {
                "probability": p_ge3,
                "calibration_source": TARGET_CALIBRATION_MAPPING.get("goals_ge_3"),
            },
            "under_2_5": {"probability": p_u25, "derived_as_complement": True},
        },
        "data_quality": {
            "feature_status": snap.feature_status or "official_v5_complete",
            "history_sample_size": snap.history_sample_size,
            "no_target_used_in_score": snap.no_target_used_in_score,
        },
        "no_betting_signals": True,
    }


def _v4_fallback_gi_payload(row: CecchinoTodayFixture, bundle: Any) -> dict[str, Any] | None:
    from app.services.cecchino.cecchino_goal_intensity_v4_v5_benchmark import (
        extract_v4_from_persisted_today,
    )
    from app.services.cecchino.cecchino_goal_intensity_v5 import _build_v4_fallback_payload
    from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
        FALLBACK_REASON_FEATURES_INCOMPLETE,
    )

    if bundle is None or not is_official_bundle(bundle):
        return None
    v4_payload, _reason = extract_v4_from_persisted_today(row)
    if v4_payload is None:
        return None
    return _build_v4_fallback_payload(
        bundle,
        v4_payload,
        reason=FALLBACK_REASON_FEATURES_INCOMPLETE,
        today_fixture_id=int(row.id),
    )


def _context_support(
    *,
    market_key: str,
    row: CecchinoTodayFixture,
    gi_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if market_key in BALANCE_CONTEXT_MARKETS:
        return _balance_context(row)
    if market_key in GOAL_INTENSITY_CONTEXT_MARKETS:
        return _gi_context_for_market(market_key=market_key, gi_payload=gi_payload)
    return {
        "available": False,
        "module": None,
        "reason": REASON_NO_VALIDATED_CONTEXT_MODULE,
        "payload": None,
    }


def _fixture_block(row: CecchinoTodayFixture) -> dict[str, Any]:
    return {
        "today_fixture_id": int(row.id),
        "provider_fixture_id": row.provider_fixture_id,
        "scan_date": row.scan_date.isoformat() if row.scan_date else None,
        "kickoff": _iso(row.kickoff),
        "country": row.country_name,
        "league": row.league_name,
        "home": {
            "name": row.home_team_name,
            "logo": row.home_team_logo_url,
        },
        "away": {
            "name": row.away_team_name,
            "logo": row.away_team_logo_url,
        },
    }


def _is_pre_match_operational(row: CecchinoTodayFixture, *, now: datetime) -> bool:
    status = str(row.match_display_status or "").strip().lower()
    if status in {MATCH_LIVE, MATCH_FINISHED, MATCH_POSTPONED, MATCH_CANCELLED}:
        return False
    if row.kickoff is not None:
        ko = row.kickoff
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=timezone.utc)
        if ko <= now:
            return False
    # upcoming / unknown / vuoto ammessi se kickoff futuro (o assente)
    return status in {"", MATCH_UPCOMING, "unknown"}


def _extract_v31_generated_at(snapshot: dict[str, Any] | None) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    for key in ("generated_at", "snapshot_at"):
        val = snapshot.get(key)
        if val:
            return str(val)
    return None


def _sort_key(opp: dict[str, Any]) -> tuple:
    purch = opp.get("purchasability_v31") or {}
    score = purch.get("score")
    score_sort = (
        (0, -float(score))
        if score is not None and _finite_number(score) is not None
        else (1, 0.0)
    )
    origin = opp.get("origin")
    origin_rank = {
        ORIGIN_PRICE_AND_SIGNALS: 0,
        ORIGIN_SIGNALS: 1,
        ORIGIN_PRICE: 2,
    }.get(origin, 3)
    yes_count = int((opp.get("signals") or {}).get("yes_count") or 0)
    edge = _finite_number((opp.get("price_value") or {}).get("edge_pct"))
    edge_sort = -edge if edge is not None else 0.0
    kickoff = (opp.get("fixture") or {}).get("kickoff") or ""
    key = opp.get("opportunity_key") or ""
    return (score_sort[0], score_sort[1], origin_rank, -yes_count, edge_sort, kickoff, key)


def _load_gi_payloads_batch(
    db: Session,
    rows: list[CecchinoTodayFixture],
) -> tuple[dict[int, dict[str, Any]], str | None]:
    """O(1) query moduli: active bundle + batch snapshots per fixture ids.

    Ritorna (payload_by_fixture_id, max_snapshot_timestamp_iso).
    """
    out: dict[int, dict[str, Any]] = {}
    max_gi_at: str | None = None
    if not rows:
        return out, None
    bundle = get_active_bundle(db)
    ids = [int(r.id) for r in rows]
    snaps_by_id: dict[int, CecchinoGoalIntensityV5PreviewSnapshot] = {}
    if bundle is not None:
        snaps = list(
            db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                    CecchinoGoalIntensityV5PreviewSnapshot.today_fixture_id.in_(ids),
                )
            ).all()
        )
        for snap in snaps:
            snaps_by_id[int(snap.today_fixture_id)] = snap
            ts = _iso(snap.last_computed_at or snap.source_snapshot_at or snap.updated_at)
            if ts and (max_gi_at is None or ts > max_gi_at):
                max_gi_at = ts

    for row in rows:
        fid = int(row.id)
        snap = snaps_by_id.get(fid)
        if snap is not None and bundle is not None:
            payload = _build_gi_payload_from_snapshot(snap=snap, bundle=bundle)
            if payload.get("status") == "ok":
                out[fid] = payload
                continue
            v4 = _v4_fallback_gi_payload(row, bundle)
            out[fid] = v4 if v4 is not None else payload
        else:
            v4 = _v4_fallback_gi_payload(row, bundle)
            if v4 is not None:
                out[fid] = v4
    return out, max_gi_at


def build_opportunities_for_rows(
    rows: list[CecchinoTodayFixture],
    *,
    gi_by_fixture: dict[int, dict[str, Any]],
    market_filter: str | None = None,
    origin_filter: str | None = None,
    freshness_scan_date: date | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Costruisce opportunity dalle row Today (pre-match o post-kickoff).

    Riusato da Pre-match e Results — nessuna formula duplicata.
    Ritorna (opportunities, max_v31_generated_at).
    """
    opportunities: list[dict[str, Any]] = []
    max_v31_at: str | None = None

    for row in rows:
        output = row.cecchino_output_json if isinstance(row.cecchino_output_json, dict) else {}
        kpi_panel = row.kpi_panel_json if isinstance(row.kpi_panel_json, dict) else None
        signals_matrix = output.get("signals_matrix") if isinstance(output, dict) else None

        v31_snapshot = resolve_purchasability_preview_v31_for_detail(
            row=row,
            kpi_panel=kpi_panel,
        )
        v31_at = _extract_v31_generated_at(v31_snapshot)
        if v31_at and (max_v31_at is None or v31_at > max_v31_at):
            max_v31_at = v31_at
        v31_by_market = index_purchasability_v31_snapshot_by_market(v31_snapshot)
        # Mai usare V3: non leggere purchasability_preview_v3 per score/ordinamento

        gi_payload = gi_by_fixture.get(int(row.id))
        fixture_block = _fixture_block(row)
        scan_date_iso = (
            freshness_scan_date.isoformat()
            if freshness_scan_date is not None
            else (
                row.scan_date.isoformat()
                if getattr(row, "scan_date", None) is not None
                else None
            )
        )
        markets = (
            [market_filter]
            if market_filter
            else list(BET_BUILDER_MARKET_KEYS)
        )

        for mk in markets:
            if mk not in BET_BUILDER_MARKET_KEY_SET:
                continue
            kpi_row = _kpi_row_for_market(kpi_panel, mk)
            price = build_price_value(kpi_row)
            signals = build_signals_evidence(
                market_key=mk,
                signals_matrix=signals_matrix if isinstance(signals_matrix, dict) else None,
            )
            price_present = bool(price.get("present"))
            signal_present = bool(signals.get("present"))
            origin_val = _origin(price_present, signal_present)
            if origin_val is None:
                continue
            if origin_filter and origin_val != origin_filter:
                continue

            purch = build_purchasability_v31_block(
                market_key=mk,
                v31_by_market=v31_by_market,
                snapshot=v31_snapshot if isinstance(v31_snapshot, dict) else None,
            )
            ctx = _context_support(market_key=mk, row=row, gi_payload=gi_payload)

            signals_updated = None
            if isinstance(signals_matrix, dict):
                signals_updated = signals_matrix.get("generated_at") or signals_matrix.get(
                    "computed_at"
                )

            context_snap_at = None
            if isinstance(ctx.get("payload"), dict):
                context_snap_at = ctx["payload"].get("snapshot_timestamp")

            opp = {
                "opportunity_key": opportunity_key(int(row.id), mk),
                "fixture": fixture_block,
                "market": market_meta(mk),
                "origin": origin_val,
                "price_value": price,
                "signals": signals,
                "purchasability_v31": purch,
                "context_support": ctx,
                "freshness": {
                    "source_scan_date": scan_date_iso,
                    "fixture_updated_at": _iso(getattr(row, "updated_at", None)),
                    "signals_updated_at": signals_updated,
                    "purchasability_v31_generated_at": purch.get("generated_at"),
                    "context_snapshot_at": context_snap_at,
                },
            }
            opportunities.append(opp)

    return opportunities, max_v31_at


def aggregate_bet_builder_opportunities(
    db: Session,
    *,
    scan_date: date,
    market_key: str | None = None,
    origin: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read-model: legge stato current Today e aggrega opportunity."""
    now = now or datetime.now(timezone.utc)
    market_filter = str(market_key).strip().upper() if market_key else None
    if market_filter and market_filter not in BET_BUILDER_MARKET_KEY_SET:
        market_filter = None
    origin_filter = str(origin).strip().lower() if origin else None
    if origin_filter not in {
        ORIGIN_PRICE,
        ORIGIN_SIGNALS,
        ORIGIN_PRICE_AND_SIGNALS,
        None,
    }:
        origin_filter = None

    source_scan_status, latest_job, freshness_warning = resolve_source_scan_status(
        db, scan_date
    )

    all_eligible = list(
        db.scalars(
            select(CecchinoTodayFixture).where(
                CecchinoTodayFixture.scan_date == scan_date,
                CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
            )
        ).all()
    )

    excluded_post_kickoff = 0
    operational_rows: list[CecchinoTodayFixture] = []
    for row in all_eligible:
        if _is_pre_match_operational(row, now=now):
            operational_rows.append(row)
        else:
            excluded_post_kickoff += 1

    gi_by_fixture, max_gi_at = _load_gi_payloads_batch(db, operational_rows)

    opportunities, max_v31_at = build_opportunities_for_rows(
        operational_rows,
        gi_by_fixture=gi_by_fixture,
        market_filter=market_filter,
        origin_filter=origin_filter,
        freshness_scan_date=scan_date,
    )
    opportunities.sort(key=_sort_key)

    source_generated_from = build_source_generated_from(
        scan_date=scan_date,
        fixtures=operational_rows,
        latest_job=latest_job,
        max_v31_generated_at=max_v31_at,
        max_gi_snapshot_at=max_gi_at,
    )
    source_revision = compute_source_revision(source_generated_from)

    by_market: dict[str, int] = {mk: 0 for mk in BET_BUILDER_MARKET_KEYS}
    price_only = signals_only = both = 0
    with_v31 = without_v31 = 0
    for opp in opportunities:
        mk = opp["market"]["market_key"]
        by_market[mk] = by_market.get(mk, 0) + 1
        if opp["origin"] == ORIGIN_PRICE:
            price_only += 1
        elif opp["origin"] == ORIGIN_SIGNALS:
            signals_only += 1
        elif opp["origin"] == ORIGIN_PRICE_AND_SIGNALS:
            both += 1
        if (opp.get("purchasability_v31") or {}).get("available"):
            with_v31 += 1
        else:
            without_v31 += 1

    freshness = {
        "source_scan_date": scan_date.isoformat(),
        "source_scan_status": source_scan_status,
        "freshness_warning": freshness_warning,
        "max_fixture_updated_at": source_generated_from.get("max_fixture_updated_at"),
        "max_purchasability_v31_generated_at": max_v31_at,
        "max_goal_intensity_snapshot_at": max_gi_at,
    }

    return {
        "contract_version": BET_BUILDER_CONTRACT_VERSION,
        "aggregator_version": BET_BUILDER_AGGREGATOR_VERSION,
        "signal_evidence_version": BET_BUILDER_SIGNAL_EVIDENCE_VERSION,
        "purchasability_policy_version": BET_BUILDER_PURCHASABILITY_POLICY_VERSION,
        "purchasability_policy": PURCHASABILITY_POLICY,
        "scan_date": scan_date.isoformat(),
        "source_revision": source_revision,
        "source_generated_from": source_generated_from,
        "source_scan_status": source_scan_status,
        "freshness": freshness,
        "summary": {
            "fixtures_considered": len(operational_rows),
            "fixtures_eligible_total": len(all_eligible),
            "excluded_post_kickoff": excluded_post_kickoff,
            "opportunities_total": len(opportunities),
            "price_only": price_only,
            "signals_only": signals_only,
            "price_and_signals": both,
            "with_purchasability_v31": with_v31,
            "without_purchasability_v31": without_v31,
            "by_market": by_market,
        },
        "opportunities": opportunities,
    }
