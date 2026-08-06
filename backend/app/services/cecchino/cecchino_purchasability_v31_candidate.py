"""Acquistabilità V3.1 — shadow candidate fixed_discount empirica.

Parallela a fixed_discount_v3. Non operativa.

empirical_v1 (frozen):
  raw_score_v31 = theoretical_raw × (historical_reliability_score / 100)
  sample < MIN_SAMPLE → non_calculable

empirical_v2 (corrente):
  historical_multiplier = 1 + (HR - 50) / 100
  raw_score_v31 = clamp(theoretical_raw × historical_multiplier, 0, 100)
  sample < MIN_SAMPLE → score_provisional (non bloccante)
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.schemas.cecchino_purchasability_v31 import (
    PURCHASABILITY_V31_AUDIT_VERSION,
    PURCHASABILITY_V31_AUDIT_VERSION_V1,
    PURCHASABILITY_V31_CANDIDATE_NAME,
    PURCHASABILITY_V31_CANDIDATE_VERSION,
    PURCHASABILITY_V31_CANDIDATE_VERSION_V1,
    PURCHASABILITY_V31_CONTRACT_VERSION,
    PURCHASABILITY_V31_CONTRACT_VERSION_V1,
    PURCHASABILITY_V31_FEATURE_VERSION,
    PURCHASABILITY_V31_FEATURE_VERSION_V1,
    PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
    PURCHASABILITY_V31_FORMULA_CONFIG_VERSION_V1,
    PURCHASABILITY_V31_FORMULA_VERSION,
    PURCHASABILITY_V31_FORMULA_VERSION_V1,
    PURCHASABILITY_V31_REGISTRY_STATUS,
)
from app.services.cecchino.cecchino_historical_reliability import (
    HISTORICAL_RELIABILITY_VERSION,
    MIN_SAMPLE,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_candidate import (
    CLASS_THRESHOLDS,
    clamp,
    map_score_to_class,
    round_purchasability_score_half_up,
)
from app.services.cecchino.cecchino_purchasability_fair_book import (
    SOURCE_DC_DERIVED,
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v31_historical_policy import (
    apply_historical_to_theoretical,
    build_historical_block,
    resolve_historical,
)
from app.services.cecchino.cecchino_purchasability_v31_opposition import (
    SUPPORTED_V31_MARKETS,
    competitors_for_market,
    family_ambiguity_applicable,
    family_ambiguity_status_default,
    is_v31_supported_market,
    market_family_for,
    market_label_for,
    period_and_line_for,
    resolve_mathematical_complement,
)
from app.services.cecchino.cecchino_purchasability_v3_candidate import (
    DIVERGENCE_EDGE_FULL_PCT,
    DIVERGENCE_EDGE_START_PCT,
    DIVERGENCE_MAX_PENALTY_POINTS,
    DIVERGENCE_PROBABILITY_FULL_PCT,
    DIVERGENCE_PROBABILITY_START_PCT,
    FAMILY_CLEAR_GAP_PCT,
    FAMILY_NOT_LEADER_BASE_PENALTY_POINTS,
    FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS,
    FAMILY_TIE_MAX_PENALTY_POINTS,
    OPPOSITE_PRESSURE_FULL_PCT,
    OPPOSITE_PRESSURE_MAX_POINTS,
    OPPOSITE_PRESSURE_START_PCT,
    PROBABILITY_MAX_PENALTY_PCT,
    PROBABILITY_MAX_PENALTY_POINTS,
    PROBABILITY_NO_PENALTY_PCT,
    VALUE_EDGE_FULL_SCORE_PCT,
    compute_extreme_divergence_penalty,
    compute_family_ambiguity_penalty,
    compute_opposite_pressure_penalty,
    compute_probability_risk_penalty,
    compute_value_score,
)

FormulaPolicy = Literal["v1", "v2"]

RATING_MIN_PURCHASE_SCOPE = 50.0

READING_GATE_NO_VALUE = "Nessun valore positivo"
READING_GATE_RATING = "Rating teorico inferiore alla soglia minima 50"
READING_NON_CALC = "Non calcolabile"

DEPENDENCY_META = {
    "rating_used_in_score": False,
    "rating_used_as_gate": True,
    "historical_reliability_used_as_factor": True,
    "probability_advantage_used_as_weight": False,
    "score_acquisto_used": False,
    "linked_markets_used_in_score": False,
    "fixed_scales_used": True,
    "edge_used_in_value_score": True,
    "mathematical_complement_used": True,
    "derived_quote_blocks_score": True,
}

_DERIVED_BOOK_SOURCE_MARKERS = (
    "derived",
    "synthetic",
    "reconstructed",
    "model",
    "from_1x2",
    "from_betfair_1x2",
)


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


def _round2(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _round4(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


def _panel_rows(kpi_panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(kpi_panel, dict):
        return []
    rows = kpi_panel.get("rows")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        mk = row.get("market_key") or row.get("segno")
        if isinstance(mk, str) and mk:
            out[mk] = row
    return out


def _model_prob_map(panel_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    raw = build_model_context_probability_map(panel_rows)
    out: dict[str, float | None] = {}
    for mk, meta in raw.items():
        if isinstance(meta, dict):
            out[mk] = _safe_float(meta.get("model_context_probability"))
        else:
            out[mk] = _safe_float(meta)
    return out


def _prob_cecchino_pct(
    row: dict[str, Any],
    model_probs: dict[str, float | None],
    market_key: str,
) -> float | None:
    p = model_probs.get(market_key)
    if p is None:
        p = _safe_float(row.get("prob_cecchino"))
    if p is None:
        return None
    if 0.0 <= p <= 1.0:
        return p * 100.0
    if 1.0 < p <= 100.0:
        return p
    return None


def _fair_prob_value(fair_info: dict[str, Any] | None) -> float | None:
    if not isinstance(fair_info, dict):
        return None
    if fair_info.get("fair_book_probability_verified") is False:
        return None
    return _safe_float(fair_info.get("fair_book_probability"))


def _normalized_map_from_fair(fair_info: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(fair_info, dict):
        return {}
    payload = fair_info.get("normalization_payload") or {}
    if not isinstance(payload, dict):
        return {}
    for key in ("normalized_map", "normalized_1x2"):
        raw = payload.get(key)
        if isinstance(raw, dict) and raw:
            out: dict[str, float] = {}
            for k, v in raw.items():
                fv = _safe_float(v)
                if fv is not None:
                    out[str(k)] = fv
            return out
    return {}


def evaluate_v31_gate(row: dict[str, Any]) -> dict[str, Any]:
    """Gate: edge > 0 AND vantaggio > 0 AND rating >= 50."""
    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    rating = _safe_float(row.get("rating"))

    edge_available = edge is not None
    vant_available = vant is not None
    rating_available = rating is not None
    edge_positive = edge > 0 if edge is not None else None
    vant_positive = vant > 0 if vant is not None else None
    rating_ok = rating >= RATING_MIN_PURCHASE_SCOPE if rating is not None else None

    codes: list[str] = []

    if not edge_available:
        codes.append("edge_unavailable")
    if not vant_available:
        codes.append("probability_advantage_unavailable")
    if not rating_available:
        codes.append("rating_unavailable")

    if codes:
        return {
            "gate_status": "unavailable_inputs",
            "gate_reason_codes": codes,
            "edge_available": edge_available,
            "edge_positive": edge_positive,
            "probability_advantage_available": vant_available,
            "probability_advantage_positive": vant_positive,
            "rating_available": rating_available,
            "rating_ok": rating_ok,
            "rating": rating,
            "rating_threshold": RATING_MIN_PURCHASE_SCOPE,
            "gate_reading": READING_NON_CALC,
            "item_status": "non_calculable",
        }

    if edge is not None and edge <= 0:
        codes.append("failed_non_positive_edge")
    if vant is not None and vant <= 0:
        codes.append("failed_non_positive_probability_advantage")
    if rating is not None and rating < RATING_MIN_PURCHASE_SCOPE:
        codes.append("rating_below_purchase_scope")

    if codes:
        reading = READING_GATE_NO_VALUE
        if "rating_below_purchase_scope" in codes and len(codes) == 1:
            reading = READING_GATE_RATING
        elif "rating_below_purchase_scope" in codes:
            reading = f"{READING_GATE_NO_VALUE}; {READING_GATE_RATING}"
        return {
            "gate_status": "gate_failed",
            "gate_reason_codes": codes,
            "edge_available": True,
            "edge_positive": edge_positive,
            "probability_advantage_available": True,
            "probability_advantage_positive": vant_positive,
            "rating_available": True,
            "rating_ok": rating_ok,
            "rating": rating,
            "rating_threshold": RATING_MIN_PURCHASE_SCOPE,
            "gate_reading": reading,
            "item_status": "gate_failed",
        }

    return {
        "gate_status": "passed",
        "gate_reason_codes": [],
        "edge_available": True,
        "edge_positive": True,
        "probability_advantage_available": True,
        "probability_advantage_positive": True,
        "rating_available": True,
        "rating_ok": True,
        "rating": rating,
        "rating_threshold": RATING_MIN_PURCHASE_SCOPE,
        "gate_reading": None,
        "item_status": "score",
    }


def resolve_execution_quote(
    fair_info: dict[str, Any] | None,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Quota realmente acquistabile vs derivata/assente."""
    quota_book = _safe_float(row.get("quota_book"))
    book_source = str(
        row.get("book_source")
        or row.get("odds_source")
        or row.get("quote_source")
        or ""
    )
    fair_source = None
    if isinstance(fair_info, dict):
        fair_source = fair_info.get("fair_book_probability_source")

    if quota_book is None or quota_book <= 1.0:
        return {
            "execution_quote": None,
            "execution_quote_source": book_source or None,
            "execution_quote_real": False,
            "performance_type": "unavailable",
            "diagnostic_only": True,
            "reason_code": "book_quote_unavailable",
            "fair_probability_may_be_derived": fair_source == SOURCE_DC_DERIVED,
        }

    is_derived = bool(
        row.get("derived_quote")
        or row.get("not_real_book_quote")
        or row.get("force_derived_quote")
    )
    src_l = book_source.lower()
    if any(m in src_l for m in _DERIVED_BOOK_SOURCE_MARKERS):
        is_derived = True
    if fair_source == SOURCE_DC_DERIVED and (
        "derived" in src_l or row.get("force_derived_quote") is True
    ):
        is_derived = True
    # Fair DC derived ≠ execution derived: solo se book_source indica derivazione.
    if fair_source == SOURCE_DC_DERIVED and not book_source:
        # Senza book_source esplicito, DC tipicamente derivata nel panel se flag.
        pass

    if is_derived:
        return {
            "execution_quote": quota_book,
            "execution_quote_source": book_source or str(fair_source or "derived"),
            "execution_quote_real": False,
            "performance_type": "derived",
            "diagnostic_only": True,
            "reason_code": "derived_quote_not_executable",
            "fair_probability_may_be_derived": True,
        }

    return {
        "execution_quote": quota_book,
        "execution_quote_source": book_source or "betfair_panel",
        "execution_quote_real": True,
        "performance_type": "real",
        "diagnostic_only": False,
        "reason_code": None,
        "fair_probability_may_be_derived": fair_source == SOURCE_DC_DERIVED,
    }


def _resolve_historical(
    historical_reliability_item: dict[str, Any] | None,
    *,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    return resolve_historical(historical_reliability_item, policy=policy)


def _version_meta(policy: FormulaPolicy) -> dict[str, str]:
    if policy == "v1":
        return {
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION_V1,
            "formula_config_version": PURCHASABILITY_V31_FORMULA_CONFIG_VERSION_V1,
            "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION_V1,
            "contract_version": PURCHASABILITY_V31_CONTRACT_VERSION_V1,
            "feature_version": PURCHASABILITY_V31_FEATURE_VERSION_V1,
            "audit_version": PURCHASABILITY_V31_AUDIT_VERSION_V1,
        }
    return {
        "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
        "formula_config_version": PURCHASABILITY_V31_FORMULA_CONFIG_VERSION,
        "candidate_version": PURCHASABILITY_V31_CANDIDATE_VERSION,
        "contract_version": PURCHASABILITY_V31_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V31_FEATURE_VERSION,
        "audit_version": PURCHASABILITY_V31_AUDIT_VERSION,
    }


def _base_meta(market_key: str, *, policy: FormulaPolicy = "v2") -> dict[str, Any]:
    period, line = period_and_line_for(market_key)
    return {
        **_version_meta(policy),
        "candidate_name": PURCHASABILITY_V31_CANDIDATE_NAME,
        "registry_status": PURCHASABILITY_V31_REGISTRY_STATUS,
        "market_key": market_key,
        "label": market_label_for(market_key),
        "market_label": market_label_for(market_key),
        "market_family": market_family_for(market_key),
        "period": period,
        "line": line,
        "pre_match_only": True,
        "current_operational_version": False,
        "shadow_candidate": True,
        "dependency_meta": dict(DEPENDENCY_META),
        "rounding": {"policy": "ROUND_HALF_UP", "precision": 0},
        "class_thresholds": list(CLASS_THRESHOLDS),
    }


def _non_calculable(
    *,
    market_key: str,
    reason_codes: list[str],
    reading_short: str,
    reading_detailed: str,
    gate: dict[str, Any] | None = None,
    input_block: dict[str, Any] | None = None,
    fair_audit: dict[str, Any] | None = None,
    historical_block: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    g = gate or {
        "gate_status": "unavailable_inputs",
        "gate_reason_codes": list(reason_codes),
    }
    out = {
        **_base_meta(market_key, policy=policy),
        "status": "non_calculable",
        "calculation_quality": "not_applicable",
        "score": None,
        "raw_score": None,
        "score_v31": None,
        "raw_score_v31": None,
        "class": None,
        "class_v31": None,
        "gate": g,
        "gate_status": g.get("gate_status"),
        "gate_reason_codes": list(g.get("gate_reason_codes") or reason_codes),
        "historical_reason_codes": list(
            (historical_block or {}).get("historical_reason_codes") or []
        ),
        "input": input_block or {},
        "fair_book_audit": fair_audit or {},
        "historical": historical_block or {},
        "theoretical": {},
        "reading_short": reading_short,
        "reading_detailed": reading_detailed,
        "reason_codes": list(reason_codes),
        "warnings": list(warnings or []),
        "formula_steps": [],
    }
    if extra:
        out.update(extra)
    return make_json_safe(out)


def _gate_failed_item(
    *,
    market_key: str,
    gate: dict[str, Any],
    input_block: dict[str, Any],
    fair_audit: dict[str, Any] | None = None,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    codes = list(gate.get("gate_reason_codes") or [])
    reading = str(gate.get("gate_reading") or READING_GATE_NO_VALUE)
    return make_json_safe(
        {
            **_base_meta(market_key, policy=policy),
            "status": "gate_failed",
            "calculation_quality": "not_applicable",
            "score": None,
            "raw_score": None,
            "score_v31": None,
            "raw_score_v31": None,
            "class": None,
            "class_v31": None,
            "gate": gate,
            "gate_status": "gate_failed",
            "gate_reason_codes": codes,
            "historical_reason_codes": [],
            "input": input_block,
            "fair_book_audit": fair_audit or {},
            "historical": {},
            "theoretical": {},
            "reading_short": "Non attivato",
            "reading_detailed": reading,
            "reason_codes": codes,
            "warnings": [],
            "formula_steps": [],
        }
    )


def _historical_block(
    hr_resolved: dict[str, Any],
    *,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    return build_historical_block(hr_resolved, policy=policy)



def calculate_purchasability_v31_item(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None],
    historical_reliability_item: dict[str, Any] | None = None,
    gate_by_market: dict[str, dict[str, Any]] | None = None,
    edge_by_market: dict[str, float | None] | None = None,
    fixture_meta: dict[str, Any] | None = None,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    """Calcolatore puro V3.1. Nessuna sessione DB. Default policy=v2."""
    meta = fixture_meta or {}
    family = market_family_for(market_key)

    if not is_v31_supported_market(market_key):
        # I 19 mercati panel non devono mai arrivare qui; protezione.
        return _non_calculable(
            market_key=market_key,
            reason_codes=["unsupported_market"],
            reading_short=READING_NON_CALC,
            reading_detailed="Mercato non supportato dalla V3.1",
            policy=policy,
        )

    kickoff = meta.get("kickoff") or row.get("kickoff")
    snapshot_verified = meta.get("snapshot_timestamp_verified")
    if kickoff is None and meta.get("require_kickoff", True):
        # Solo se meta esplicitamente richiede; batch passa kickoff.
        pass

    fair_info = fair_by.get(market_key)
    fair_prob = _fair_prob_value(fair_info)
    fair_source = (
        fair_info.get("fair_book_probability_source")
        if isinstance(fair_info, dict)
        else None
    )
    norm_payload = (
        (fair_info or {}).get("normalization_payload")
        if isinstance(fair_info, dict)
        else {}
    ) or {}
    normalized_map = _normalized_map_from_fair(fair_info)
    overround = None
    if isinstance(fair_info, dict):
        overround = fair_info.get("market_overround")
        if overround is None and isinstance(norm_payload, dict):
            overround = norm_payload.get("overround") or norm_payload.get(
                "overround_1x2"
            )

    exec_q = resolve_execution_quote(fair_info, row)
    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    vant_pp = None if vant is None else (vant * 100.0 if abs(vant) <= 1.0 else vant)
    rating = _safe_float(row.get("rating"))
    quota_cecchino = _safe_float(row.get("quota_cecchino"))
    prob_cec_pct = _prob_cecchino_pct(row, model_probs, market_key)

    fair_simple = {mk: _fair_prob_value(info) for mk, info in fair_by.items()}
    # Per DC, merge normalized 1x2 into fair_simple for complement lookup.
    if isinstance(norm_payload, dict):
        for src_key in ("normalized_1x2", "normalized_map"):
            nm = norm_payload.get(src_key)
            if isinstance(nm, dict):
                for k, v in nm.items():
                    fv = _safe_float(v)
                    if fv is not None and fair_simple.get(str(k)) is None:
                        fair_simple[str(k)] = fv

    complement = resolve_mathematical_complement(
        market_key,
        selected_fair_probability=fair_prob,
        normalized_fair_probabilities=normalized_map or fair_simple,  # type: ignore[arg-type]
        fair_book_by_market=fair_simple,
    )

    complete_set_status = "ok"
    if fair_prob is None:
        if isinstance(fair_info, dict) and fair_info.get(
            "fair_book_probability_verified"
        ) is False:
            complete_set_status = "incomplete_or_unverified"
        else:
            complete_set_status = "unavailable"

    fair_audit = {
        "selected_fair_probability": fair_prob,
        "complement_fair_probability": complement.get("complement_fair_probability"),
        "complement_definition": complement.get("complement_definition"),
        "complete_set": complement.get("complete_set"),
        "normalized_fair_probabilities": normalized_map or None,
        "overround": overround,
        "normalization_source": fair_source
        or complement.get("normalization_source"),
        "complement_sum_check": complement.get("complement_sum_check"),
        "complement_sum_ok": complement.get("complement_sum_ok"),
        "complete_set_status": complete_set_status,
        "fair_book_probability_source": fair_source,
        "fair_probability_may_be_derived": exec_q.get("fair_probability_may_be_derived"),
    }

    input_block = {
        "quota_book": exec_q.get("execution_quote"),
        "execution_quote": exec_q.get("execution_quote"),
        "execution_quote_source": exec_q.get("execution_quote_source"),
        "execution_quote_real": exec_q.get("execution_quote_real"),
        "quota_cecchino": quota_cecchino,
        "probability_cecchino": None if prob_cec_pct is None else prob_cec_pct / 100.0,
        "probability_cecchino_pct": prob_cec_pct,
        "edge_pct": edge,
        "probability_advantage_pp": vant_pp,
        "rating": rating,
        "fair_book_probability": fair_prob,
        "fair_book_probability_source": fair_source,
        "complement_fair_probability": complement.get("complement_fair_probability"),
        "complete_set_status": complete_set_status,
        "performance_type": exec_q.get("performance_type"),
        "diagnostic_only": exec_q.get("diagnostic_only"),
        "fair_probability_may_be_derived": exec_q.get("fair_probability_may_be_derived"),
    }

    # --- Input obbligatori / non_calculable (prima del gate value) ---
    if not exec_q.get("execution_quote_real"):
        code = exec_q.get("reason_code") or "book_quote_unavailable"
        detail = (
            "Quota derivata, non realmente acquistabile"
            if code == "derived_quote_not_executable"
            else "Quota Book assente o non eseguibile"
        )
        return _non_calculable(
            market_key=market_key,
            reason_codes=[str(code)],
            reading_short=READING_NON_CALC,
            reading_detailed=detail,
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if quota_cecchino is None or quota_cecchino <= 1.0:
        return _non_calculable(
            market_key=market_key,
            reason_codes=["cecchino_quote_unavailable"],
            reading_short=READING_NON_CALC,
            reading_detailed="Quota Cecchino assente",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if prob_cec_pct is None:
        return _non_calculable(
            market_key=market_key,
            reason_codes=["cecchino_probability_unavailable"],
            reading_short=READING_NON_CALC,
            reading_detailed="Probabilità Cecchino assente",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if fair_prob is None:
        reason = "fair_book_probability_unavailable"
        if complete_set_status != "ok":
            reason = "fair_book_complete_set_incomplete"
        return _non_calculable(
            market_key=market_key,
            reason_codes=[reason],
            reading_short=READING_NON_CALC,
            reading_detailed="Probabilità Fair Book non verificata o set incompleto",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if complement.get("complement_fair_probability") is None:
        return _non_calculable(
            market_key=market_key,
            reason_codes=["complement_probability_unavailable"],
            reading_short=READING_NON_CALC,
            reading_detailed="Complemento matematico non disponibile",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if kickoff is None and meta.get("kickoff_required"):
        return _non_calculable(
            market_key=market_key,
            reason_codes=["kickoff_unavailable"],
            reading_short=READING_NON_CALC,
            reading_detailed="Kickoff non disponibile",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if snapshot_verified is False:
        return _non_calculable(
            market_key=market_key,
            reason_codes=["pre_match_snapshot_unverified"],
            reading_short=READING_NON_CALC,
            reading_detailed="Snapshot pre-match non verificabile",
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    gate = (
        dict(gate_by_market.get(market_key) or evaluate_v31_gate(row))
        if gate_by_market is not None
        else evaluate_v31_gate(row)
    )

    if gate.get("gate_status") == "unavailable_inputs":
        return _non_calculable(
            market_key=market_key,
            reason_codes=list(gate.get("gate_reason_codes") or []),
            reading_short=READING_NON_CALC,
            reading_detailed="Input gate mancanti (Edge, vantaggio o Rating)",
            gate=gate,
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    if gate.get("gate_status") == "gate_failed":
        return _gate_failed_item(
            market_key=market_key,
            gate=gate,
            input_block=input_block,
            fair_audit=fair_audit,
            policy=policy,
        )

    # --- Score teorico (sempre dopo gate passato) poi storico ---
    assert edge is not None and prob_cec_pct is not None
    value_score = compute_value_score(edge)
    pen_prob = compute_probability_risk_penalty(prob_cec_pct)

    opp_fair = float(complement["complement_fair_probability"])
    opp_fair_pct = opp_fair * 100.0 if opp_fair <= 1.0 else opp_fair
    pen_opp = compute_opposite_pressure_penalty(opp_fair_pct)
    pen_div = compute_extreme_divergence_penalty(
        edge_pct=edge, probability_cecchino_pct=prob_cec_pct
    )

    warnings: list[str] = []
    if family_ambiguity_applicable(family):
        comps = competitors_for_market(market_key)
        family_all = [market_key] + comps
        edges_map = edge_by_market or {
            mk: _safe_float((by_mk.get(mk) or {}).get("edge_pct")) for mk in family_all
        }
        gates_map = gate_by_market or {}
        gate_passed_edges: dict[str, float] = {}
        for mk in family_all:
            g = gates_map.get(mk) or evaluate_v31_gate(by_mk.get(mk) or {})
            e = edges_map.get(mk)
            if g.get("gate_status") == "passed" and e is not None:
                gate_passed_edges[mk] = float(e)
        pen_fam = compute_family_ambiguity_penalty(
            selected_edge=edge,
            gate_passed_family_edges=gate_passed_edges,
            market_key=market_key,
        )
        if pen_fam.get("warning"):
            warnings.append(str(pen_fam["warning"]))
        ambiguity_status = pen_fam.get("ambiguity_status")
    else:
        comps = []
        pen_fam = {
            "key": "family_ambiguity",
            "label": "Ambiguità nella famiglia",
            "raw_inputs": {},
            "threshold_start": None,
            "threshold_full": None,
            "severity": 0.0,
            "max_points": 0.0,
            "penalty_points": 0.0,
            "applied": False,
            "ambiguity_status": family_ambiguity_status_default(family),
            "explanation": (
                "Family ambiguity non applicabile a questo ambito di mercato."
            ),
        }
        ambiguity_status = pen_fam["ambiguity_status"]

    theoretical_penalty_total = (
        float(pen_prob["penalty_points"])
        + float(pen_opp["penalty_points"])
        + float(pen_div["penalty_points"])
        + float(pen_fam["penalty_points"])
    )
    theoretical_quality_score = clamp(100.0 - theoretical_penalty_total, 0.0, 100.0)
    theoretical_raw_score = value_score * theoretical_quality_score / 100.0

    theoretical = {
        "value_score": _round4(value_score),
        "probability_risk_penalty": _round4(float(pen_prob["penalty_points"])),
        "opposite_market_pressure_penalty": _round4(float(pen_opp["penalty_points"])),
        "extreme_divergence_penalty": _round4(float(pen_div["penalty_points"])),
        "family_ambiguity_penalty": _round4(float(pen_fam["penalty_points"])),
        "theoretical_penalty_total": _round4(theoretical_penalty_total),
        "theoretical_quality_score": _round4(theoretical_quality_score),
        "theoretical_raw_score": _round4(theoretical_raw_score),
        "penalties": {
            "probability_risk": pen_prob,
            "opposite_market_pressure": pen_opp,
            "extreme_divergence": pen_div,
            "family_ambiguity": pen_fam,
        },
        "family_ambiguity_status": ambiguity_status,
        "family_competitors": comps,
        "value_full_score_edge_pct": VALUE_EDGE_FULL_SCORE_PCT,
        "scales": {
            "probability_risk": {
                "start": PROBABILITY_NO_PENALTY_PCT,
                "full": PROBABILITY_MAX_PENALTY_PCT,
                "max": PROBABILITY_MAX_PENALTY_POINTS,
            },
            "opposite_pressure": {
                "start": OPPOSITE_PRESSURE_START_PCT,
                "full": OPPOSITE_PRESSURE_FULL_PCT,
                "max": OPPOSITE_PRESSURE_MAX_POINTS,
            },
            "extreme_divergence": {
                "edge_start": DIVERGENCE_EDGE_START_PCT,
                "edge_full": DIVERGENCE_EDGE_FULL_PCT,
                "prob_start": DIVERGENCE_PROBABILITY_START_PCT,
                "prob_full": DIVERGENCE_PROBABILITY_FULL_PCT,
                "max": DIVERGENCE_MAX_PENALTY_POINTS,
            },
            "family_ambiguity": {
                "clear_gap": FAMILY_CLEAR_GAP_PCT,
                "tie_max": FAMILY_TIE_MAX_PENALTY_POINTS,
                "not_leader_base": FAMILY_NOT_LEADER_BASE_PENALTY_POINTS,
                "not_leader_extra": FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS,
            },
        },
    }

    formula_steps_theo = [
        f"value_score = clamp({_round2(edge)} / {VALUE_EDGE_FULL_SCORE_PCT} × 100) = {_round4(value_score)}",
        f"probability_risk_penalty = {_round4(float(pen_prob['penalty_points']))}",
        f"opposite_market_pressure_penalty = {_round4(float(pen_opp['penalty_points']))}",
        f"extreme_divergence_penalty = {_round4(float(pen_div['penalty_points']))}",
        f"family_ambiguity_penalty = {_round4(float(pen_fam['penalty_points']))} ({ambiguity_status})",
        f"theoretical_quality_score = clamp(100 - {_round4(theoretical_penalty_total)}) = {_round4(theoretical_quality_score)}",
        f"theoretical_raw_score = {_round4(value_score)} × {_round4(theoretical_quality_score)} / 100 = {_round4(theoretical_raw_score)}",
    ]

    hr_resolved = _resolve_historical(historical_reliability_item, policy=policy)
    hist_block = _historical_block(hr_resolved, policy=policy)

    # v1: storico insufficiente blocca ancora (comportamento frozen)
    if policy == "v1" and hr_resolved.get("blocks_score"):
        return _non_calculable(
            market_key=market_key,
            reason_codes=[str(hr_resolved.get("reason_code"))],
            reading_short=READING_NON_CALC,
            reading_detailed=str(hr_resolved.get("reading") or "Storico non disponibile"),
            gate=gate,
            input_block=input_block,
            fair_audit=fair_audit,
            historical_block=hist_block,
            policy=policy,
            extra={"theoretical": theoretical, "formula_steps": formula_steps_theo},
        )

    applied = apply_historical_to_theoretical(
        theoretical_raw_score, hr_resolved, policy=policy
    )
    raw_score_v31 = float(applied["raw_score_v31"])
    score_v31 = round_purchasability_score_half_up(raw_score_v31)
    klass = map_score_to_class(score_v31)

    if policy == "v1":
        historical_factor = float(applied["historical_factor"])
        hist_block["historical_factor"] = _round4(historical_factor)
        hist_block["historical_factor_legacy"] = _round4(historical_factor)
        formula_steps = formula_steps_theo + [
            f"historical_factor = {_round4(float(hr_resolved['score']))} / 100 = {_round4(historical_factor)}",
            f"raw_score_v31 = {_round4(theoretical_raw_score)} × {_round4(historical_factor)} = {_round4(raw_score_v31)}",
            f"score_v31 = ROUND_HALF_UP({_round4(raw_score_v31)}) = {score_v31}",
        ]
        item_status = "score"
        calc_quality = "full"
        hist_reason_codes: list[str] = []
        reading_detailed = (
            f"Acquistabilità V3.1 shadow: score {score_v31} ({klass}). "
            f"theoretical_raw={_round4(theoretical_raw_score)} × "
            f"historical_factor={_round4(historical_factor)}."
        )
        adj_points = None
        adj_pct = None
        multiplier = None
    else:
        multiplier = float(applied["historical_multiplier"])
        adj_points = applied["historical_adjustment_points"]
        adj_pct = applied["historical_adjustment_pct"]
        hist_block["historical_multiplier"] = _round4(multiplier)
        hist_block["historical_adjustment_points"] = (
            _round4(float(adj_points)) if adj_points is not None else None
        )
        hist_block["historical_adjustment_pct"] = (
            _round4(float(adj_pct)) if adj_pct is not None else None
        )
        formula_steps = formula_steps_theo + [
            f"historical_reliability_score = {_round4(float(hr_resolved['score']))}"
            + (
                " (neutral_fallback)"
                if hr_resolved.get("score_is_neutral_fallback")
                else ""
            ),
            f"historical_multiplier = 1 + ({_round4(float(hr_resolved['score']))} - 50) / 100 = {_round4(multiplier)}",
            f"historical_adjusted_raw_score = {_round4(theoretical_raw_score)} × {_round4(multiplier)} = {_round4(float(applied['historical_adjusted_raw_score']))}",
            f"raw_score_v31 = clamp(...) = {_round4(raw_score_v31)}",
            f"historical_adjustment_points = {_round4(float(adj_points)) if adj_points is not None else None}",
            f"score_v31 = ROUND_HALF_UP({_round4(raw_score_v31)}) = {score_v31}",
        ]
        item_status = str(hr_resolved.get("item_status") or "score_provisional")
        calc_quality = str(hr_resolved.get("calculation_quality") or "provisional")
        hist_reason_codes = list(hr_resolved.get("historical_reason_codes") or [])
        sample_n = int(hr_resolved.get("sample_size") or 0)
        if item_status == "score_provisional":
            if sample_n <= 0:
                reading_short_extra = f"{score_v31} ({klass} provvisoria)"
                reading_detailed = (
                    f"Valutazione teorica provvisoria. Nessuno storico: "
                    f"moltiplicatore neutrale 1,00. Score {score_v31} ({klass})."
                )
            else:
                reading_short_extra = f"{score_v31} ({klass} provvisoria)"
                reading_detailed = (
                    f"Valutazione provvisoria. Storico {sample_n}/{MIN_SAMPLE}. "
                    f"theoretical_raw={_round4(theoretical_raw_score)} × "
                    f"historical_multiplier={_round4(multiplier)} → score {score_v31}."
                )
        else:
            reading_short_extra = f"{score_v31} ({klass})"
            reading_detailed = (
                f"Acquistabilità V3.1 shadow: score {score_v31} ({klass}). "
                f"theoretical_raw={_round4(theoretical_raw_score)} × "
                f"historical_multiplier={_round4(multiplier)}."
            )

    if policy == "v1":
        reading_short_extra = f"{score_v31} ({klass})"

    return make_json_safe(
        {
            **_base_meta(market_key, policy=policy),
            "status": item_status,
            "calculation_quality": calc_quality,
            "score": score_v31,
            "raw_score": _round4(raw_score_v31),
            "score_v31": score_v31,
            "raw_score_v31": _round4(raw_score_v31),
            "class": klass,
            "class_v31": klass,
            "score_display": reading_short_extra,
            "gate": gate,
            "gate_status": "passed",
            "gate_reason_codes": [],
            "historical_reason_codes": hist_reason_codes,
            "input": input_block,
            "fair_book_audit": fair_audit,
            "theoretical": theoretical,
            "historical": hist_block,
            "historical_multiplier": (
                _round4(multiplier) if multiplier is not None else None
            ),
            "historical_adjustment_points": (
                _round4(float(adj_points)) if adj_points is not None else None
            ),
            "historical_adjustment_pct": (
                _round4(float(adj_pct)) if adj_pct is not None else None
            ),
            "value_score": _round4(value_score),
            "quality_score": _round4(theoretical_quality_score),
            "theoretical_raw_score": _round4(theoretical_raw_score),
            "total_penalty": _round4(theoretical_penalty_total),
            "penalties": theoretical["penalties"],
            "family_ambiguity_status": ambiguity_status,
            "opposite_fair_probability": complement.get("complement_fair_probability"),
            "complement_fair_probability": complement.get("complement_fair_probability"),
            "reading_short": reading_short_extra,
            "reading_detailed": reading_detailed,
            "reason_codes": [],
            "warnings": warnings,
            "formula_steps": formula_steps,
            "snapshot_at": meta.get("snapshot_at"),
            "kickoff": kickoff,
            "historical_as_of": hist_block.get("historical_date_to"),
        }
    )




def calculate_purchasability_v31_batch(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
    v3_items_by_market: dict[str, dict[str, Any]] | None = None,
    policy: FormulaPolicy = "v2",
) -> dict[str, Any]:
    """Batch puro: richiede historical_by_market già risolto. Default v2."""
    from app.services.cecchino.cecchino_purchasability_v31_compare import (
        attach_comparisons_and_summary,
    )

    meta = fixture_meta or {}
    rows = _panel_rows(kpi_panel)
    by_mk = _index_rows(rows)
    fair_by = resolve_fair_book_for_panel_rows(
        rows,
        today_fixture_id=meta.get("today_fixture_id"),
        snapshot_at=(
            str(meta.get("snapshot_at")) if meta.get("snapshot_at") else None
        ),
    )
    model_probs = _model_prob_map(rows)
    hr_map = historical_by_market or {}

    # Tutti i 19 mercati supportati; includi anche righe panel presenti.
    ordered = list(SUPPORTED_V31_MARKETS)
    for mk in by_mk:
        if mk not in ordered and is_v31_supported_market(mk):
            ordered.append(mk)
    # Preferisci ordine panel se disponibile.
    panel_order = [
        str(r.get("market_key") or r.get("segno"))
        for r in rows
        if (r.get("market_key") or r.get("segno"))
    ]
    if panel_order:
        seen: set[str] = set()
        ordered = []
        for mk in panel_order:
            if mk in SUPPORTED_V31_MARKETS and mk not in seen:
                ordered.append(mk)
                seen.add(mk)
        for mk in SUPPORTED_V31_MARKETS:
            if mk not in seen:
                ordered.append(mk)

    gate_by_market: dict[str, dict[str, Any]] = {}
    edge_by_market: dict[str, float | None] = {}
    for mk in ordered:
        row = by_mk.get(mk) or {}
        gate_by_market[mk] = evaluate_v31_gate(row)
        edge_by_market[mk] = _safe_float(row.get("edge_pct"))

    items: list[dict[str, Any]] = []
    for mk in ordered:
        row = by_mk.get(mk) or {}
        items.append(
            calculate_purchasability_v31_item(
                mk,
                row,
                by_mk,
                fair_by=fair_by,
                model_probs=model_probs,
                historical_reliability_item=hr_map.get(mk),
                gate_by_market=gate_by_market,
                edge_by_market=edge_by_market,
                fixture_meta=meta,
                policy=policy,
            )
        )

    vmeta = _version_meta(policy)
    batch = {
        "candidate_version": vmeta["candidate_version"],
        "candidate_name": PURCHASABILITY_V31_CANDIDATE_NAME,
        "formula_version": vmeta["formula_version"],
        "formula_config_version": vmeta["formula_config_version"],
        "registry_status": PURCHASABILITY_V31_REGISTRY_STATUS,
        "audit_version": vmeta["audit_version"],
        "status": "ok" if items else "unavailable",
        "items": items,
        "fixture_meta": {
            "today_fixture_id": meta.get("today_fixture_id"),
            "kickoff": meta.get("kickoff"),
            "snapshot_at": meta.get("snapshot_at"),
        },
        "summary": {
            "rows_total": len(items),
            "score_count": sum(
                1
                for it in items
                if it.get("status") in ("score", "score_provisional")
            ),
            "score_definitive_count": sum(
                1 for it in items if it.get("status") == "score"
            ),
            "score_provisional_count": sum(
                1 for it in items if it.get("status") == "score_provisional"
            ),
            "gate_failed_count": sum(
                1 for it in items if it.get("status") == "gate_failed"
            ),
            "non_calculable_count": sum(
                1 for it in items if it.get("status") == "non_calculable"
            ),
            "supported_markets": len(SUPPORTED_V31_MARKETS),
        },
    }
    return attach_comparisons_and_summary(
        batch, v3_items_by_market=v3_items_by_market or {}
    )



def calculate_purchasability_v31_batch_v1(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
    historical_by_market: dict[str, dict[str, Any]] | None = None,
    v3_items_by_market: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Entry frozen empirical_v1 per registry/replay."""
    return calculate_purchasability_v31_batch(
        kpi_panel=kpi_panel,
        fixture_meta=fixture_meta,
        historical_by_market=historical_by_market,
        v3_items_by_market=v3_items_by_market,
        policy="v1",
    )


def calculate_purchasability_v31_item_v1(
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    kwargs["policy"] = "v1"
    return calculate_purchasability_v31_item(*args, **kwargs)



def canonical_v31_candidate_sha256(batch: dict[str, Any]) -> str:
    payload = make_json_safe(
        {
            "candidate_version": batch.get("candidate_version"),
            "formula_version": batch.get("formula_version"),
            "items": batch.get("items"),
            "summary": batch.get("summary"),
        }
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def input_fingerprint_v31(
    *,
    kpi_panel: dict[str, Any] | None,
    historical_by_market: dict[str, dict[str, Any]] | None,
    fixture_meta: dict[str, Any] | None,
) -> str:
    rows = _panel_rows(kpi_panel)
    compact_rows = []
    for r in rows:
        compact_rows.append(
            {
                "market_key": r.get("market_key") or r.get("segno"),
                "quota_book": r.get("quota_book"),
                "book_source": r.get("book_source"),
                "quota_cecchino": r.get("quota_cecchino"),
                "prob_cecchino": r.get("prob_cecchino"),
                "edge_pct": r.get("edge_pct"),
                "vantaggio_prob": r.get("vantaggio_prob"),
                "rating": r.get("rating"),
            }
        )
    hr_compact = {}
    for mk, item in (historical_by_market or {}).items():
        if isinstance(item, dict):
            hr_compact[mk] = {
                "status": item.get("status"),
                "score": item.get("score"),
                "selected_sample_size": item.get("selected_sample_size"),
                "rating_band": item.get("rating_band"),
                "cohort_scope": item.get("cohort_scope"),
            }
    meta = fixture_meta or {}
    payload = make_json_safe(
        {
            "rows": compact_rows,
            "historical": hr_compact,
            "kickoff": str(meta.get("kickoff") or ""),
            "snapshot_at": str(meta.get("snapshot_at") or ""),
            "formula_version": PURCHASABILITY_V31_FORMULA_VERSION,
        }
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
