"""Acquistabilità v3 — candidate fixed_discount_v3.

Parallela a v1.1 e v2. Scale fisse, nessun profilo storico.
Formula: score = ROUND_HALF_UP(value_score × quality_score / 100).
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.schemas.cecchino_purchasability_v3 import (
    PURCHASABILITY_V3_AUDIT_VERSION,
    PURCHASABILITY_V3_CANDIDATE_NAME,
    PURCHASABILITY_V3_CANDIDATE_VERSION,
    PURCHASABILITY_V3_CONTRACT_VERSION,
    PURCHASABILITY_V3_FEATURE_VERSION,
    PURCHASABILITY_V3_FORMULA_VERSION,
    PURCHASABILITY_V3_REGISTRY_STATUS,
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
from app.services.cecchino.cecchino_purchasability_v3_opposition import (
    SUPPORTED_V3_MARKETS,
    competitors_for_market,
    is_v3_supported_market,
    linked_market_key_for,
    market_family_for,
    market_label_for,
    period_and_line_for,
    resolve_opposite_selection,
)

# --- Scale fisse versionate ---
VALUE_EDGE_FULL_SCORE_PCT = 50.0

PROBABILITY_NO_PENALTY_PCT = 35.0
PROBABILITY_MAX_PENALTY_PCT = 10.0
PROBABILITY_MAX_PENALTY_POINTS = 20.0

OPPOSITE_PRESSURE_START_PCT = 50.0
OPPOSITE_PRESSURE_FULL_PCT = 75.0
OPPOSITE_PRESSURE_MAX_POINTS = 35.0

DIVERGENCE_EDGE_START_PCT = 30.0
DIVERGENCE_EDGE_FULL_PCT = 100.0
DIVERGENCE_PROBABILITY_START_PCT = 30.0
DIVERGENCE_PROBABILITY_FULL_PCT = 10.0
DIVERGENCE_MAX_PENALTY_POINTS = 15.0

FAMILY_CLEAR_GAP_PCT = 25.0
FAMILY_TIE_MAX_PENALTY_POINTS = 15.0
FAMILY_NOT_LEADER_BASE_PENALTY_POINTS = 15.0
FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS = 10.0

DERIVED_QUOTE_PENALTY_POINTS = 15.0

READING_GATE_NOT_ACTIVATED = (
    "Indice non attivato: nessun valore positivo. "
    "L'Acquistabilità V3 richiede Edge e vantaggio probabilistico entrambi positivi."
)

DEPENDENCY_META = {
    "rating_used_in_score": False,
    "probability_advantage_used_as_weight": False,
    "score_acquisto_used": False,
    "historical_profile_used": False,
    "linked_markets_used_in_score": False,
    "fixed_scales_used": True,
    "edge_used_in_value_score": True,
    "edge_used_in_family_ambiguity_only_as_comparison": True,
    "book_opposite_used_only_in_opposite_penalty": True,
    "probability_cecchino_used_in_risk_and_divergence_only": True,
}


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
    return float(
        Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _round4(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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
    """Probabilità Cecchino contestuale in percentuale 0–100."""
    p = model_probs.get(market_key)
    if p is None:
        p = _safe_float(row.get("prob_cecchino"))
    if p is None:
        return None
    # Accetta frazione (0–1) o già percentuale (>1 e ≤100).
    if 0.0 <= p <= 1.0:
        return p * 100.0
    if 1.0 < p <= 100.0:
        return p
    return None


def _fair_prob_map(
    panel_rows: list[dict[str, Any]],
    *,
    today_fixture_id: Any = None,
    snapshot_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    return resolve_fair_book_for_panel_rows(
        panel_rows,
        today_fixture_id=today_fixture_id,
        snapshot_at=snapshot_at,
    )


def _fair_prob_value(fair_info: dict[str, Any] | None) -> float | None:
    if not isinstance(fair_info, dict):
        return None
    if fair_info.get("fair_book_probability_verified") is False:
        return None
    return _safe_float(fair_info.get("fair_book_probability"))


def _raw_prob_value(fair_info: dict[str, Any] | None, row: dict[str, Any]) -> float | None:
    if isinstance(fair_info, dict):
        raw = _safe_float(fair_info.get("raw_implied_probability"))
        if raw is not None:
            return raw
    pb = _safe_float(row.get("prob_book"))
    if pb is not None:
        return pb if pb <= 1.0 else pb / 100.0
    qb = _safe_float(row.get("quota_book"))
    if qb is not None and qb > 1.0:
        return 1.0 / qb
    return None


def evaluate_v3_gate(row: dict[str, Any]) -> dict[str, Any]:
    """Gate: Edge e vantaggio probabilistico entrambi disponibili e > 0."""
    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    edge_available = edge is not None
    vant_available = vant is not None
    edge_positive = edge > 0 if edge is not None else None
    vant_positive = vant > 0 if vant is not None else None

    if not edge_available or not vant_available:
        return {
            "gate_status": "unavailable_inputs",
            "gate_reason_codes": ["gate_inputs_unavailable"],
            "edge_available": edge_available,
            "edge_positive": edge_positive,
            "probability_advantage_available": vant_available,
            "probability_advantage_positive": vant_positive,
            "gate_reading": READING_GATE_NOT_ACTIVATED,
        }

    edge_fail = edge is not None and edge <= 0
    vant_fail = vant is not None and vant <= 0
    if edge_fail and vant_fail:
        status = "failed_multiple_non_positive_components"
        codes = [
            "failed_non_positive_edge",
            "failed_non_positive_probability_advantage",
            "failed_multiple_non_positive_components",
        ]
    elif edge_fail:
        status = "failed_non_positive_edge"
        codes = ["failed_non_positive_edge"]
    elif vant_fail:
        status = "failed_non_positive_probability_advantage"
        codes = ["failed_non_positive_probability_advantage"]
    else:
        return {
            "gate_status": "passed",
            "gate_reason_codes": [],
            "edge_available": True,
            "edge_positive": True,
            "probability_advantage_available": True,
            "probability_advantage_positive": True,
            "gate_reading": None,
        }

    return {
        "gate_status": status,
        "gate_reason_codes": codes,
        "edge_available": edge_available,
        "edge_positive": edge_positive,
        "probability_advantage_available": vant_available,
        "probability_advantage_positive": vant_positive,
        "gate_reading": READING_GATE_NOT_ACTIVATED,
    }


def compute_value_score(edge_pct: float) -> float:
    return clamp(float(edge_pct) / VALUE_EDGE_FULL_SCORE_PCT * 100.0, 0.0, 100.0)


def compute_probability_risk_penalty(probability_cecchino_pct: float) -> dict[str, Any]:
    severity = _clamp01(
        (PROBABILITY_NO_PENALTY_PCT - float(probability_cecchino_pct))
        / (PROBABILITY_NO_PENALTY_PCT - PROBABILITY_MAX_PENALTY_PCT)
    )
    points = PROBABILITY_MAX_PENALTY_POINTS * severity
    return {
        "key": "probability_risk",
        "label": "Rischio di probabilità",
        "raw_inputs": {"probability_cecchino_pct": _round4(probability_cecchino_pct)},
        "threshold_start": PROBABILITY_NO_PENALTY_PCT,
        "threshold_full": PROBABILITY_MAX_PENALTY_PCT,
        "severity": _round4(severity),
        "max_points": PROBABILITY_MAX_PENALTY_POINTS,
        "penalty_points": _round4(points),
        "applied": points > 0,
        "explanation": (
            "Una probabilità assoluta Cecchino bassa rende la quota più fragile, "
            "anche in presenza di valore teorico."
            if points > 0
            else "Probabilità Cecchino sufficientemente elevata: nessuna penalità."
        ),
    }


def compute_opposite_pressure_penalty(
    opposite_fair_probability_pct: float,
) -> dict[str, Any]:
    severity = _clamp01(
        (float(opposite_fair_probability_pct) - OPPOSITE_PRESSURE_START_PCT)
        / (OPPOSITE_PRESSURE_FULL_PCT - OPPOSITE_PRESSURE_START_PCT)
    )
    points = OPPOSITE_PRESSURE_MAX_POINTS * severity
    return {
        "key": "opposite_market_pressure",
        "label": "Pressione del mercato opposto",
        "raw_inputs": {
            "opposite_fair_probability_pct": _round4(opposite_fair_probability_pct)
        },
        "threshold_start": OPPOSITE_PRESSURE_START_PCT,
        "threshold_full": OPPOSITE_PRESSURE_FULL_PCT,
        "severity": _round4(severity),
        "max_points": OPPOSITE_PRESSURE_MAX_POINTS,
        "penalty_points": _round4(points),
        "applied": points > 0,
        "explanation": (
            "Il Book considera fortemente favorito il mercato opposto, "
            "riducendo la qualità della decisione."
            if points > 0
            else "Il mercato opposto non esercita pressione rilevante."
        ),
    }


def compute_extreme_divergence_penalty(
    *,
    edge_pct: float,
    probability_cecchino_pct: float,
) -> dict[str, Any]:
    edge_severity = _clamp01(
        (float(edge_pct) - DIVERGENCE_EDGE_START_PCT)
        / (DIVERGENCE_EDGE_FULL_PCT - DIVERGENCE_EDGE_START_PCT)
    )
    probability_fragility = _clamp01(
        (DIVERGENCE_PROBABILITY_START_PCT - float(probability_cecchino_pct))
        / (DIVERGENCE_PROBABILITY_START_PCT - DIVERGENCE_PROBABILITY_FULL_PCT)
    )
    points = DIVERGENCE_MAX_PENALTY_POINTS * edge_severity * probability_fragility
    return {
        "key": "extreme_divergence",
        "label": "Divergenza estrema e fragile",
        "raw_inputs": {
            "edge_pct": _round4(edge_pct),
            "probability_cecchino_pct": _round4(probability_cecchino_pct),
            "edge_severity": _round4(edge_severity),
            "probability_fragility": _round4(probability_fragility),
        },
        "threshold_start": DIVERGENCE_EDGE_START_PCT,
        "threshold_full": DIVERGENCE_EDGE_FULL_PCT,
        "severity": _round4(edge_severity * probability_fragility),
        "max_points": DIVERGENCE_MAX_PENALTY_POINTS,
        "penalty_points": _round4(points),
        "applied": points > 0,
        "explanation": (
            "Il valore è molto elevato, ma deriva da una divergenza estrema su un evento "
            "che il Cecchino considera ancora poco probabile."
            if points > 0
            else "Nessuna combinazione Edge elevato / probabilità bassa: nessuna penalità."
        ),
    }


def compute_family_ambiguity_penalty(
    *,
    selected_edge: float,
    gate_passed_family_edges: dict[str, float],
    market_key: str,
) -> dict[str, Any]:
    others = {
        mk: edge
        for mk, edge in gate_passed_family_edges.items()
        if mk != market_key and edge is not None
    }
    if not others:
        return {
            "key": "family_ambiguity",
            "label": "Ambiguità nella famiglia",
            "raw_inputs": {
                "selected_edge": _round4(selected_edge),
                "best_other_edge": None,
                "edge_gap_or_deficit": None,
            },
            "threshold_start": FAMILY_CLEAR_GAP_PCT,
            "threshold_full": FAMILY_CLEAR_GAP_PCT,
            "severity": 0.0,
            "max_points": FAMILY_NOT_LEADER_BASE_PENALTY_POINTS
            + FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS,
            "penalty_points": 0.0,
            "applied": False,
            "ambiguity_status": "insufficient_family_comparison",
            "selected_is_family_edge_leader": True,
            "best_other_edge": None,
            "best_family_market_by_edge": market_key,
            "second_best_family_market_by_edge": None,
            "edge_gap_or_deficit": None,
            "explanation": (
                "Nessun altro concorrente valutabile nella famiglia: "
                "penalità 0 con warning insufficient_family_comparison."
            ),
            "warning": "insufficient_family_comparison",
        }

    best_other_mk = max(others, key=lambda k: others[k])
    best_other_edge = float(others[best_other_mk])
    all_edges = {**others, market_key: float(selected_edge)}
    ranked = sorted(all_edges.items(), key=lambda kv: kv[1], reverse=True)
    best_mk = ranked[0][0]
    second_mk = ranked[1][0] if len(ranked) > 1 else None
    second_edge = all_edges[second_mk] if second_mk else None

    is_leader = float(selected_edge) >= best_other_edge
    if is_leader:
        edge_gap = float(selected_edge) - best_other_edge
        severity = 1.0 - _clamp01(edge_gap / FAMILY_CLEAR_GAP_PCT)
        points = FAMILY_TIE_MAX_PENALTY_POINTS * severity
        status = "leader_clear" if edge_gap >= FAMILY_CLEAR_GAP_PCT else "leader_close"
        gap_or_deficit = edge_gap
        explanation = (
            "Il mercato ha l'Edge più alto della famiglia; "
            + (
                "il distacco è netto."
                if status == "leader_clear"
                else "il distacco rispetto al secondo è limitato."
            )
        )
    else:
        edge_deficit = best_other_edge - float(selected_edge)
        extra = FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS * _clamp01(
            edge_deficit / FAMILY_CLEAR_GAP_PCT
        )
        points = FAMILY_NOT_LEADER_BASE_PENALTY_POINTS + extra
        status = "not_leader"
        gap_or_deficit = -edge_deficit
        explanation = (
            "Un altro mercato della stessa famiglia ha Edge superiore: "
            "la scelta risulta ambigua o subordinata."
        )

    return {
        "key": "family_ambiguity",
        "label": "Ambiguità nella famiglia",
        "raw_inputs": {
            "selected_edge": _round4(selected_edge),
            "best_other_edge": _round4(best_other_edge),
            "edge_gap_or_deficit": _round4(gap_or_deficit),
        },
        "threshold_start": FAMILY_CLEAR_GAP_PCT,
        "threshold_full": FAMILY_CLEAR_GAP_PCT,
        "severity": _round4(
            points
            / (
                FAMILY_NOT_LEADER_BASE_PENALTY_POINTS
                + FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS
            )
        ),
        "max_points": FAMILY_NOT_LEADER_BASE_PENALTY_POINTS
        + FAMILY_NOT_LEADER_EXTRA_PENALTY_POINTS,
        "penalty_points": _round4(points),
        "applied": points > 0,
        "ambiguity_status": status,
        "selected_is_family_edge_leader": is_leader,
        "best_other_edge": _round4(best_other_edge),
        "best_family_market_by_edge": best_mk,
        "second_best_family_market_by_edge": second_mk,
        "edge_gap_or_deficit": _round4(gap_or_deficit),
        "explanation": explanation,
        "warning": None,
    }


def resolve_quote_quality(
    fair_info: dict[str, Any] | None,
    row: dict[str, Any],
    market_key: str,
) -> dict[str, Any]:
    quota_book = _safe_float(row.get("quota_book"))
    source = None
    if isinstance(fair_info, dict):
        source = fair_info.get("fair_book_probability_source")
    row_source = row.get("quote_source") or row.get("odds_source")

    if quota_book is None or quota_book <= 1.0:
        return {
            "performance_type": "unavailable",
            "quote_quality": "unavailable",
            "quote_source": source or row_source,
            "diagnostic_only": True,
            "not_real_book_quote": True,
            "penalty_points": None,
            "score_available": False,
            "reason_code": "quote_unavailable",
        }

    is_derived = source == SOURCE_DC_DERIVED or bool(
        row.get("derived_quote") or row.get("not_real_book_quote")
    )
    # Doppia chance tipicamente derivata se source indica DC derived
    family = market_family_for(market_key)
    if family == "DOUBLE_CHANCE" and source == SOURCE_DC_DERIVED:
        is_derived = True
    if family == "DOUBLE_CHANCE" and row.get("force_derived_quote") is True:
        is_derived = True

    if is_derived:
        return {
            "performance_type": "derived",
            "quote_quality": "derived",
            "quote_source": source or row_source or SOURCE_DC_DERIVED,
            "diagnostic_only": True,
            "not_real_book_quote": True,
            "penalty_points": DERIVED_QUOTE_PENALTY_POINTS,
            "score_available": True,
            "reason_code": None,
        }

    return {
        "performance_type": "real",
        "quote_quality": "real",
        "quote_source": source or row_source or "betfair_panel",
        "diagnostic_only": False,
        "not_real_book_quote": False,
        "penalty_points": 0.0,
        "score_available": True,
        "reason_code": None,
    }


def _build_reading(
    *,
    gate_status: str,
    market_label: str,
    value_score: float | None,
    penalties: dict[str, dict[str, Any]],
    score: int | None,
    klass: str | None,
) -> tuple[str, str, list[str], list[str]]:
    if gate_status != "passed" or score is None:
        short = "Indice non attivato: nessun valore positivo"
        return short, READING_GATE_NOT_ACTIVATED, [], ["gate_not_passed"]

    strengths: list[str] = []
    risks: list[str] = []
    parts: list[str] = []

    if value_score is not None and value_score >= 80:
        strengths.append("valore_teorico_molto_alto")
        parts.append(
            f"Il segno {market_label} presenta un valore teorico molto alto perché "
            "la quota Book è molto superiore alla quota stimata dal Cecchino."
        )
    elif value_score is not None and value_score >= 40:
        strengths.append("valore_teorico_presente")
        parts.append(
            f"Il segno {market_label} presenta valore teorico positivo rispetto al Book."
        )
    elif value_score is not None:
        parts.append(
            f"Il segno {market_label} presenta un valore teorico contenuto."
        )

    prob_pen = penalties.get("probability_risk") or {}
    if float(prob_pen.get("penalty_points") or 0) > 0:
        risks.append("probabilita_assoluta_bassa")
        parts.append("La probabilità assoluta rimane però bassa.")

    opp_pen = penalties.get("opposite_market_pressure") or {}
    if float(opp_pen.get("penalty_points") or 0) >= 20:
        risks.append("forte_mercato_opposto")
        parts.append("Il Book considera il mercato opposto fortemente favorito.")
    elif float(opp_pen.get("penalty_points") or 0) > 0:
        risks.append("pressione_mercato_opposto")
        parts.append("Esiste una pressione significativa dal mercato opposto.")

    div_pen = penalties.get("extreme_divergence") or {}
    if float(div_pen.get("penalty_points") or 0) > 0:
        risks.append("divergenza_estrema_fragile")
        parts.append(
            "La divergenza è quindi fragile e riduce sensibilmente l'Acquistabilità."
        )

    fam_pen = penalties.get("family_ambiguity") or {}
    amb = fam_pen.get("ambiguity_status")
    if amb == "not_leader":
        risks.append("scelta_non_leader_nella_famiglia")
        parts.append(
            "Un altro mercato della stessa famiglia presenta Edge superiore."
        )
    elif amb == "leader_close":
        risks.append("scelta_ambigua_nella_famiglia")
        parts.append("Il vantaggio di Edge rispetto ai concorrenti della famiglia è limitato.")

    quote_pen = penalties.get("quote_quality") or {}
    if float(quote_pen.get("penalty_points") or 0) > 0:
        risks.append("quota_derivata")
        parts.append(
            "La quota è derivata e non costituisce prova di giocabilità reale."
        )

    detailed = " ".join(parts) if parts else (
        f"Acquistabilità V3 classificata {klass or 'n/d'} (score {score})."
    )
    short = f"{score} ({klass})" if klass else str(score)
    return short, detailed, strengths, risks


def calculate_purchasability_v3_item(
    market_key: str,
    row: dict[str, Any],
    by_mk: dict[str, dict[str, Any]],
    *,
    fair_by: dict[str, dict[str, Any]],
    model_probs: dict[str, float | None],
    gate_by_market: dict[str, dict[str, Any]] | None = None,
    edge_by_market: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    period, line = period_and_line_for(market_key)
    family = market_family_for(market_key)
    base_meta = {
        "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_V3_CANDIDATE_NAME,
        "contract_version": PURCHASABILITY_V3_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V3_FEATURE_VERSION,
        "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
        "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
        "market_key": market_key,
        "market_label": market_label_for(market_key),
        "market_family": family,
        "period": period,
        "line": line,
        "historical_profile_used": False,
        "fixed_scales_used": True,
        "pre_match_only": True,
        "parallel_candidate": True,
        "current_operational_version": False,
        "dependency_meta": dict(DEPENDENCY_META),
        "rating_used_in_score": False,
        "probability_advantage_used_as_weight": False,
        "linked_markets_used_in_score": False,
    }

    if not is_v3_supported_market(market_key):
        return make_json_safe(
            {
                **base_meta,
                "status": "not_applicable",
                "calculation_quality": "not_applicable",
                "score": None,
                "raw_score": None,
                "class": None,
                "gate_status": "unsupported_market",
                "gate": {
                    "gate_status": "unsupported_market",
                    "gate_reason_codes": ["unsupported_market"],
                    "edge_available": None,
                    "edge_positive": None,
                    "probability_advantage_available": None,
                    "probability_advantage_positive": None,
                    "gate_reading": READING_GATE_NOT_ACTIVATED,
                },
                "value_score": None,
                "quality_score": None,
                "reading_short": "Indice non attivato: mercato non supportato",
                "reading_detailed": READING_GATE_NOT_ACTIVATED,
                "reason_codes": ["unsupported_market"],
                "warnings": [],
            }
        )

    gate = evaluate_v3_gate(row) if gate_by_market is None else dict(
        gate_by_market.get(market_key) or evaluate_v3_gate(row)
    )
    gate_status = str(gate.get("gate_status") or "unavailable_inputs")

    edge = _safe_float(row.get("edge_pct"))
    vant = _safe_float(row.get("vantaggio_prob"))
    vant_pp = None if vant is None else (vant * 100.0 if abs(vant) <= 1.0 else vant)
    rating = _safe_float(row.get("rating"))
    score_acquisto = _safe_float(row.get("score_acquisto"))
    quota_book = _safe_float(row.get("quota_book"))
    quota_cecchino = _safe_float(row.get("quota_cecchino"))
    prob_cec_pct = _prob_cecchino_pct(row, model_probs, market_key)

    fair_info = fair_by.get(market_key)
    fair_prob = _fair_prob_value(fair_info)
    raw_prob = _raw_prob_value(fair_info, row)

    fair_simple = {
        mk: _fair_prob_value(info) for mk, info in fair_by.items()
    }
    opp = resolve_opposite_selection(market_key, fair_book_by_market=fair_simple)
    opposite_key = opp.get("opposite_market_key")
    opposite_fair = opp.get("opposite_fair_probability")
    if opposite_fair is None and opposite_key and opposite_key in fair_by:
        opposite_fair = _fair_prob_value(fair_by.get(opposite_key))
    opposite_raw = None
    if opposite_key and opposite_key in by_mk:
        opposite_raw = _raw_prob_value(fair_by.get(opposite_key), by_mk[opposite_key])

    quote_q = resolve_quote_quality(fair_info, row, market_key)

    # Linked market context (diagnostic only)
    linked_mk, linked_rel = linked_market_key_for(market_key)
    linked_ctx: dict[str, Any] | None = None
    if linked_mk:
        linked_row = by_mk.get(linked_mk) or {}
        linked_gate = (
            (gate_by_market or {}).get(linked_mk)
            or evaluate_v3_gate(linked_row)
            if linked_row
            else {"gate_status": "unavailable_inputs"}
        )
        linked_ctx = {
            "linked_market_key": linked_mk,
            "relationship": linked_rel,
            "edge_pct": _safe_float(linked_row.get("edge_pct")),
            "vantaggio_prob": _safe_float(linked_row.get("vantaggio_prob")),
            "rating": _safe_float(linked_row.get("rating")),
            "gate_status": linked_gate.get("gate_status"),
            "used_in_score": False,
            "diagnostic_only": True,
        }

    input_block = {
        "quota_book": quota_book,
        "quote_source": quote_q.get("quote_source"),
        "quote_quality": quote_q.get("quote_quality"),
        "fair_book_probability": fair_prob,
        "raw_book_probability": raw_prob,
        "quota_cecchino": quota_cecchino,
        "probability_cecchino": None if prob_cec_pct is None else prob_cec_pct / 100.0,
        "probability_cecchino_pct": prob_cec_pct,
        "edge_pct": edge,
        "probability_advantage_pp": vant_pp,
        "rating_diagnostic": rating,
        "score_acquisto_diagnostic": score_acquisto,
        "performance_type": quote_q.get("performance_type"),
        "diagnostic_only": quote_q.get("diagnostic_only"),
        "not_real_book_quote": quote_q.get("not_real_book_quote"),
    }

    if gate_status != "passed":
        return make_json_safe(
            {
                **base_meta,
                "status": "not_applicable",
                "calculation_quality": "not_applicable",
                "score": None,
                "raw_score": None,
                "score_display": None,
                "class": None,
                "gate_status": gate_status,
                "gate": gate,
                "gate_reason_codes": list(gate.get("gate_reason_codes") or []),
                "edge_available": gate.get("edge_available"),
                "edge_positive": gate.get("edge_positive"),
                "probability_advantage_available": gate.get(
                    "probability_advantage_available"
                ),
                "probability_advantage_positive": gate.get(
                    "probability_advantage_positive"
                ),
                "gate_reading": gate.get("gate_reading"),
                "input": input_block,
                "value_score": None,
                "quality_score": None,
                "penalties": {},
                "linked_market_context": linked_ctx,
                "reading_short": "Indice non attivato: nessun valore positivo",
                "reading_detailed": READING_GATE_NOT_ACTIVATED,
                "strengths": [],
                "risks": [],
                "reason_codes": list(gate.get("gate_reason_codes") or []),
                "warnings": [],
                "formula_steps": [],
                "rounding": {"policy": "ROUND_HALF_UP", "precision": 0},
                "source_paths": {
                    "edge_pct": "kpi_panel.rows[].edge_pct",
                    "vantaggio_prob": "kpi_panel.rows[].vantaggio_prob",
                },
            }
        )

    assert edge is not None
    reason_codes: list[str] = []
    warnings: list[str] = []

    # Quote assenti → score non calcolabile
    if not quote_q.get("score_available"):
        return make_json_safe(
            {
                **base_meta,
                "status": "unavailable",
                "calculation_quality": None,
                "score": None,
                "raw_score": None,
                "class": None,
                "gate_status": gate_status,
                "gate": gate,
                "input": input_block,
                "value_score": None,
                "quality_score": None,
                "linked_market_context": linked_ctx,
                "reading_short": "Score non disponibile: quota assente",
                "reading_detailed": "La quota Book non è disponibile; lo score V3 non è calcolabile.",
                "reason_codes": ["quote_unavailable"],
                "warnings": ["quote_unavailable"],
            }
        )

    if prob_cec_pct is None:
        return make_json_safe(
            {
                **base_meta,
                "status": "unavailable",
                "calculation_quality": None,
                "score": None,
                "raw_score": None,
                "class": None,
                "gate_status": gate_status,
                "gate": gate,
                "input": input_block,
                "value_score": None,
                "quality_score": None,
                "linked_market_context": linked_ctx,
                "reading_short": "Score non disponibile: probabilità Cecchino assente",
                "reading_detailed": (
                    "Manca la probabilità contestuale Cecchino obbligatoria."
                ),
                "reason_codes": ["probability_cecchino_unavailable"],
                "warnings": ["probability_cecchino_unavailable"],
            }
        )

    if opposite_fair is None:
        return make_json_safe(
            {
                **base_meta,
                "status": "unavailable",
                "calculation_quality": None,
                "score": None,
                "raw_score": None,
                "class": None,
                "gate_status": gate_status,
                "gate": gate,
                "input": input_block,
                "value_score": None,
                "quality_score": None,
                "linked_market_context": linked_ctx,
                "opposite_market_key": opposite_key,
                "opposite_fair_probability": None,
                "reading_short": "Score non disponibile: probabilità fair opposta assente",
                "reading_detailed": (
                    "Manca la probabilità fair del mercato opposto obbligatoria."
                ),
                "reason_codes": ["opposite_fair_probability_unavailable"],
                "warnings": ["opposite_fair_probability_unavailable"],
            }
        )

    value_score = compute_value_score(edge)
    value_block = {
        "value_score": _round4(value_score),
        "value_formula": f"clamp(edge_pct / {VALUE_EDGE_FULL_SCORE_PCT} × 100, 0, 100)",
        "value_full_score_edge_pct": VALUE_EDGE_FULL_SCORE_PCT,
        "value_explanation": (
            f"Edge { _round2(edge) }% mappato su scala fissa "
            f"(pieno punteggio a {VALUE_EDGE_FULL_SCORE_PCT}%)."
        ),
    }

    # Family edges: solo gate-passed
    comps = competitors_for_market(market_key)
    family_all = [market_key] + comps
    edges_map = edge_by_market or {
        mk: _safe_float((by_mk.get(mk) or {}).get("edge_pct")) for mk in family_all
    }
    gates_map = gate_by_market or {}
    gate_passed_edges: dict[str, float] = {}
    for mk in family_all:
        g = gates_map.get(mk) or evaluate_v3_gate(by_mk.get(mk) or {})
        e = edges_map.get(mk)
        if g.get("gate_status") == "passed" and e is not None:
            gate_passed_edges[mk] = float(e)

    evaluated_comps = [mk for mk in comps if mk in by_mk]
    gate_passed_comps = [mk for mk in comps if mk in gate_passed_edges]

    pen_prob = compute_probability_risk_penalty(prob_cec_pct)
    opposite_fair_pct = float(opposite_fair) * 100.0 if opposite_fair <= 1.0 else float(opposite_fair)
    pen_opp = compute_opposite_pressure_penalty(opposite_fair_pct)
    pen_div = compute_extreme_divergence_penalty(
        edge_pct=edge, probability_cecchino_pct=prob_cec_pct
    )
    pen_fam = compute_family_ambiguity_penalty(
        selected_edge=edge,
        gate_passed_family_edges=gate_passed_edges,
        market_key=market_key,
    )
    if pen_fam.get("warning"):
        warnings.append(str(pen_fam["warning"]))

    quote_points = float(quote_q.get("penalty_points") or 0.0)
    pen_quote = {
        "key": "quote_quality",
        "label": "Qualità della quota",
        "raw_inputs": {
            "performance_type": quote_q.get("performance_type"),
            "quote_source": quote_q.get("quote_source"),
        },
        "threshold_start": None,
        "threshold_full": None,
        "severity": 1.0 if quote_points > 0 else 0.0,
        "max_points": DERIVED_QUOTE_PENALTY_POINTS,
        "penalty_points": _round4(quote_points),
        "applied": quote_points > 0,
        "explanation": (
            "Quota derivata (tipicamente doppia chance): penalità fissa."
            if quote_points > 0
            else "Quota reale verificata: nessuna penalità."
        ),
    }

    penalties = {
        "probability_risk": pen_prob,
        "opposite_market_pressure": pen_opp,
        "extreme_divergence": pen_div,
        "family_ambiguity": pen_fam,
        "quote_quality": pen_quote,
    }
    total_penalty = (
        float(pen_prob["penalty_points"])
        + float(pen_opp["penalty_points"])
        + float(pen_div["penalty_points"])
        + float(pen_fam["penalty_points"])
        + float(pen_quote["penalty_points"])
    )
    quality_score = clamp(100.0 - total_penalty, 0.0, 100.0)
    raw_score = value_score * quality_score / 100.0
    score = round_purchasability_score_half_up(raw_score)
    klass = map_score_to_class(score)

    reading_short, reading_detailed, strengths, risks = _build_reading(
        gate_status=gate_status,
        market_label=market_label_for(market_key),
        value_score=value_score,
        penalties=penalties,
        score=score,
        klass=klass,
    )

    formula_steps = [
        f"value_score = clamp({_round2(edge)} / {VALUE_EDGE_FULL_SCORE_PCT} × 100) = {_round4(value_score)}",
        f"probability_risk_penalty = {_round4(float(pen_prob['penalty_points']))}",
        f"opposite_market_pressure_penalty = {_round4(float(pen_opp['penalty_points']))}",
        f"extreme_divergence_penalty = {_round4(float(pen_div['penalty_points']))}",
        f"family_ambiguity_penalty = {_round4(float(pen_fam['penalty_points']))}",
        f"quote_quality_penalty = {_round4(float(pen_quote['penalty_points']))}",
        f"quality_score = clamp(100 - {_round4(total_penalty)}) = {_round4(quality_score)}",
        f"raw_score = {_round4(value_score)} × {_round4(quality_score)} / 100 = {_round4(raw_score)}",
        f"score = ROUND_HALF_UP({_round4(raw_score)}) = {score}",
    ]

    family_block = {
        "family_competitors": comps,
        "evaluated_family_competitors": evaluated_comps,
        "gate_passed_family_competitors": gate_passed_comps,
        "best_family_market_by_edge": pen_fam.get("best_family_market_by_edge"),
        "second_best_family_market_by_edge": pen_fam.get(
            "second_best_family_market_by_edge"
        ),
        "selected_is_family_edge_leader": pen_fam.get("selected_is_family_edge_leader"),
        "selected_edge": _round4(edge),
        "best_other_edge": pen_fam.get("best_other_edge"),
        "edge_gap_or_deficit": pen_fam.get("edge_gap_or_deficit"),
        "ambiguity_status": pen_fam.get("ambiguity_status"),
    }

    return make_json_safe(
        {
            **base_meta,
            "status": "available",
            "calculation_quality": "full",
            "score": score,
            "raw_score": _round4(raw_score),
            "score_display": f"{score} ({klass})",
            "class": klass,
            "gate_status": gate_status,
            "gate": gate,
            "gate_reason_codes": [],
            "edge_available": True,
            "edge_positive": True,
            "probability_advantage_available": True,
            "probability_advantage_positive": True,
            "gate_reading": None,
            "input": input_block,
            "value_score": _round4(value_score),
            "value_formula": value_block["value_formula"],
            "value_full_score_edge_pct": VALUE_EDGE_FULL_SCORE_PCT,
            "value_explanation": value_block["value_explanation"],
            "quality_start": 100.0,
            "quality_score": _round4(quality_score),
            "total_penalty": _round4(total_penalty),
            "penalties": penalties,
            "family": family_block,
            "family_competitors": comps,
            "evaluated_family_competitors": evaluated_comps,
            "gate_passed_family_competitors": gate_passed_comps,
            "best_family_market_by_edge": family_block["best_family_market_by_edge"],
            "second_best_family_market_by_edge": family_block[
                "second_best_family_market_by_edge"
            ],
            "selected_is_family_edge_leader": family_block[
                "selected_is_family_edge_leader"
            ],
            "selected_edge": family_block["selected_edge"],
            "best_other_edge": family_block["best_other_edge"],
            "edge_gap_or_deficit": family_block["edge_gap_or_deficit"],
            "ambiguity_status": family_block["ambiguity_status"],
            "opposite_market_key": opposite_key,
            "opposite_fair_probability": opposite_fair,
            "opposite_raw_probability": opposite_raw,
            "opposite_pressure_status": (
                "full"
                if float(pen_opp["penalty_points"]) >= OPPOSITE_PRESSURE_MAX_POINTS
                else ("partial" if float(pen_opp["penalty_points"]) > 0 else "none")
            ),
            "opposite_pressure_penalty": float(pen_opp["penalty_points"]),
            "linked_market_context": linked_ctx,
            "reading_short": reading_short,
            "reading_detailed": reading_detailed,
            "strengths": strengths,
            "risks": risks,
            "reason_codes": reason_codes,
            "warnings": warnings,
            "formula_steps": formula_steps,
            "rounding": {"policy": "ROUND_HALF_UP", "precision": 0},
            "class_thresholds": list(CLASS_THRESHOLDS),
            "source_paths": {
                "edge_pct": "kpi_panel.rows[].edge_pct",
                "vantaggio_prob": "kpi_panel.rows[].vantaggio_prob",
                "probability_cecchino": "model_context_probability|kpi_panel.rows[].prob_cecchino",
                "fair_book": "resolve_fair_book_for_panel_rows",
                "opposite_fair": "resolve_opposite_selection",
            },
            "audit_result": {
                "value_score": _round4(value_score),
                "quality_score": _round4(quality_score),
                "raw_score": _round4(raw_score),
                "score": score,
                "class": klass,
            },
            "persisted_result": None,
            "consistency": {"status": "computed", "delta": None},
        }
    )


def calculate_purchasability_v3_batch(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = fixture_meta or {}
    rows = _panel_rows(kpi_panel)
    by_mk = _index_rows(rows)
    fair_by = _fair_prob_map(
        rows,
        today_fixture_id=meta.get("today_fixture_id"),
        snapshot_at=(
            str(meta.get("snapshot_at")) if meta.get("snapshot_at") else None
        ),
    )
    model_probs = _model_prob_map(rows)

    panel_markets = [mk for mk in by_mk.keys() if is_v3_supported_market(mk)]
    extra_unsupported = [
        mk for mk in by_mk.keys() if not is_v3_supported_market(mk)
    ]
    ordered = list(dict.fromkeys(panel_markets + extra_unsupported))

    gate_by_market: dict[str, dict[str, Any]] = {}
    edge_by_market: dict[str, float | None] = {}
    for mk in ordered:
        row = by_mk.get(mk) or {}
        if is_v3_supported_market(mk):
            gate_by_market[mk] = evaluate_v3_gate(row)
        else:
            gate_by_market[mk] = {
                "gate_status": "unsupported_market",
                "gate_reason_codes": ["unsupported_market"],
                "edge_available": None,
                "edge_positive": None,
                "probability_advantage_available": None,
                "probability_advantage_positive": None,
                "gate_reading": READING_GATE_NOT_ACTIVATED,
            }
        edge_by_market[mk] = _safe_float(row.get("edge_pct"))

    items: list[dict[str, Any]] = []
    for mk in ordered:
        row = by_mk.get(mk) or {}
        items.append(
            calculate_purchasability_v3_item(
                mk,
                row,
                by_mk,
                fair_by=fair_by,
                model_probs=model_probs,
                gate_by_market=gate_by_market,
                edge_by_market=edge_by_market,
            )
        )

    available_n = sum(1 for it in items if it.get("status") == "available")
    na_n = sum(1 for it in items if it.get("status") == "not_applicable")
    unavailable_n = sum(1 for it in items if it.get("status") == "unavailable")
    if available_n == 0 and unavailable_n == 0:
        batch_status = "unavailable" if not items else "partial"
    elif available_n == 0:
        batch_status = "unavailable"
    elif unavailable_n > 0 or na_n > 0:
        batch_status = "partial"
    else:
        batch_status = "ok"

    payload = {
        "candidate_version": PURCHASABILITY_V3_CANDIDATE_VERSION,
        "candidate_name": PURCHASABILITY_V3_CANDIDATE_NAME,
        "contract_version": PURCHASABILITY_V3_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_V3_FEATURE_VERSION,
        "formula_version": PURCHASABILITY_V3_FORMULA_VERSION,
        "audit_version": PURCHASABILITY_V3_AUDIT_VERSION,
        "registry_status": PURCHASABILITY_V3_REGISTRY_STATUS,
        "status": batch_status,
        "items": items,
        "summary": {
            "markets_total": len(items),
            "available": available_n,
            "unavailable": unavailable_n,
            "not_applicable": na_n,
            "supported_markets": sorted(SUPPORTED_V3_MARKETS),
        },
        "historical_profile_used": False,
        "fixed_scales_used": True,
        "pre_match_only": True,
        "parallel_candidate": True,
        "current_operational_version": False,
        "dependency_meta": dict(DEPENDENCY_META),
    }
    return make_json_safe(payload)


def canonical_v3_candidate_sha256(batch: dict[str, Any]) -> str:
    raw = json.dumps(batch, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
