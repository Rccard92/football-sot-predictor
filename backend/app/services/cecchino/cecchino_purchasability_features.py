"""Acquistabilità feature layer pre-match — FASE 2/5.

Versione: cecchino_purchasability_features_v1

Layer operativo feature (phase_1_value + phase_2_quality) su snapshot KPI salvati.
Nessuna formula 0–100; score/class/reading restano null (status=not_calculated).
Non importa Affidabilità storica. Read-only, deterministico, JSON-safe.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
    RATING_DEPENDENCY_METADATA,
)
from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    FAMILY_MATCH_WINNER,
    FAMILY_OVER_UNDER,
    OPPOSITION_SUPPORTED,
    get_opposition,
    required_selections_for_normalization,
)
from app.services.cecchino.cecchino_purchasability_audit import (
    FIDELITY_FALLBACK,
    make_json_safe,
    resolve_purchasability_snapshot_timestamp,
)
from app.services.cecchino.cecchino_purchasability_fair_book import (
    DC_SELS,
    MATCH_WINNER_SELS,
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)

PURCHASABILITY_FEATURE_VERSION_CONST = PURCHASABILITY_FEATURE_VERSION

PRIMARY_ROW_FIELDS = (
    "quota_book",
    "quota_cecchino",
    "prob_book",
    "prob_cecchino",
)
DERIVED_ROW_FIELDS = (
    "vantaggio_prob",
    "edge_pct",
    "score_acquisto",
    "rating",
)


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _market_key(row: dict[str, Any]) -> str:
    return str(row.get("market_key") or row.get("selection") or "").strip()


def _rows_by_market(panel_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in panel_rows:
        mk = _market_key(row)
        if mk:
            out[mk] = row
    return out


def _build_phase_1(panel_row: dict[str, Any]) -> dict[str, Any]:
    inputs = {
        "quota_book": _num(panel_row.get("quota_book")),
        "quota_cecchino": _num(panel_row.get("quota_cecchino")),
        "prob_book": _num(panel_row.get("prob_book")),
        "prob_cecchino": _num(panel_row.get("prob_cecchino")),
        "vantaggio_prob": _num(panel_row.get("vantaggio_prob")),
        "edge_pct": _num(panel_row.get("edge_pct")),
        "score_acquisto": _num(panel_row.get("score_acquisto")),
        "rating": _num(panel_row.get("rating")),
        "rating_label": panel_row.get("rating_label"),
        "row_status": panel_row.get("status"),
        "book_source": panel_row.get("book_source"),
        "cecchino_source": panel_row.get("cecchino_source"),
    }
    primary_ok = all(inputs[k] is not None for k in PRIMARY_ROW_FIELDS)
    derived_ok = all(inputs[k] is not None for k in DERIVED_ROW_FIELDS)
    if primary_ok and derived_ok:
        status = "available"
    elif any(inputs[k] is not None for k in PRIMARY_ROW_FIELDS):
        status = "partial"
    else:
        status = "unavailable"
    return {
        "status": status,
        "score": None,
        "inputs": inputs,
        "dependency_metadata": dict(RATING_DEPENDENCY_METADATA),
    }


def build_model_context_probability_map(
    panel_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Normalizzazione descrittiva Probabilità Cecchino (non modifica le righe KPI)."""
    by_m = _rows_by_market(panel_rows)
    out: dict[str, dict[str, Any]] = {}

    # 1X2 FT
    mw_probs = {
        sel: _num(by_m[sel].get("prob_cecchino"))
        for sel in MATCH_WINNER_SELS
        if sel in by_m
    }
    mw_complete = {
        k: v for k, v in mw_probs.items() if v is not None and v >= 0
    }
    mw_norm: dict[str, float] | None = None
    mw_status = "incomplete_market"
    if set(MATCH_WINNER_SELS).issubset(set(mw_complete.keys())):
        total = sum(mw_complete[s] for s in MATCH_WINNER_SELS)
        if total > 0:
            mw_norm = {s: mw_complete[s] / total for s in MATCH_WINNER_SELS}
            mw_status = "ok"

    for sel in MATCH_WINNER_SELS:
        raw = mw_probs.get(sel)
        out[sel] = {
            "model_probability_raw": raw,
            "model_context_probability": mw_norm.get(sel) if mw_norm else None,
            "normalization_status": mw_status if sel in by_m else "unavailable",
            "source": "normalized_1x2_model" if mw_norm else "raw_or_unavailable",
        }

    # Double Chance derived from normalized 1X2
    if mw_norm:
        derived = {
            SEL_ONE_X: mw_norm[SEL_HOME] + mw_norm[SEL_DRAW],
            SEL_X_TWO: mw_norm[SEL_DRAW] + mw_norm[SEL_AWAY],
            SEL_ONE_TWO: mw_norm[SEL_HOME] + mw_norm[SEL_AWAY],
        }
        for sel, prob in derived.items():
            raw = _num(by_m[sel].get("prob_cecchino")) if sel in by_m else None
            out[sel] = {
                "model_probability_raw": raw,
                "model_context_probability": prob,
                "normalization_status": "ok",
                "source": "derived_double_chance_from_normalized_1x2_model",
            }
    else:
        for sel in DC_SELS:
            raw = _num(by_m[sel].get("prob_cecchino")) if sel in by_m else None
            out[sel] = {
                "model_probability_raw": raw,
                "model_context_probability": None,
                "normalization_status": "partial" if raw is not None else "unavailable",
                "source": "raw_or_unavailable",
            }

    # OU pairs
    for pair, family, period, line in (
        (
            (SEL_OVER_2_5, SEL_UNDER_2_5),
            FAMILY_OVER_UNDER,
            "FT",
            2.5,
        ),
        (
            (SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5),
            FAMILY_OVER_UNDER,
            "HT",
            1.5,
        ),
    ):
        required = required_selections_for_normalization(family, period, line)
        probs = {
            sel: _num(by_m[sel].get("prob_cecchino"))
            for sel in pair
            if sel in by_m
        }
        complete = {k: v for k, v in probs.items() if v is not None and v >= 0}
        if required and required.issubset(set(complete.keys())):
            total = sum(complete[s] for s in required)
            if total > 0:
                norm = {s: complete[s] / total for s in required}
                for sel in pair:
                    out[sel] = {
                        "model_probability_raw": probs.get(sel),
                        "model_context_probability": norm.get(sel),
                        "normalization_status": "ok",
                        "source": "normalized_two_way_model",
                    }
                continue
        for sel in pair:
            raw = probs.get(sel)
            out[sel] = {
                "model_probability_raw": raw,
                "model_context_probability": None,
                "normalization_status": "partial" if raw is not None else "unavailable",
                "source": "raw_or_unavailable",
            }

    # Remaining panel markets: raw only, never invent complement
    for mk, row in by_m.items():
        if mk in out:
            continue
        raw = _num(row.get("prob_cecchino"))
        out[mk] = {
            "model_probability_raw": raw,
            "model_context_probability": None,
            "normalization_status": "partial" if raw is not None else "unavailable",
            "source": "raw_or_unavailable",
        }

    return out


def _favourite_from_probs(
    probs: dict[str, float],
) -> tuple[str | None, float | None, float | None]:
    """Ritorna (selection, intensity, first_prob). Intensità = 1° − 2°."""
    if len(probs) < 2:
        return None, None, None
    ranked = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    first_sel, first_p = ranked[0]
    second_p = ranked[1][1]
    intensity = max(0.0, min(1.0, first_p - second_p))
    return first_sel, intensity, first_p


def _build_favourite_context(
    *,
    market_key: str,
    opp: dict[str, Any],
    fair_by_m: dict[str, dict[str, Any]],
    model_by_m: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    family = opp.get("canonical_market_family")
    period = opp.get("period")
    line = opp.get("line")

    basis: str | None = None
    book_probs: dict[str, float] = {}
    model_probs: dict[str, float] = {}

    if family == FAMILY_MATCH_WINNER or family == FAMILY_DOUBLE_CHANCE:
        basis = "normalized_1x2"
        for sel in MATCH_WINNER_SELS:
            fb = fair_by_m.get(sel) or {}
            if fb.get("fair_book_probability_verified") and fb.get("fair_book_probability") is not None:
                book_probs[sel] = float(fb["fair_book_probability"])
            mc = model_by_m.get(sel) or {}
            if mc.get("model_context_probability") is not None:
                model_probs[sel] = float(mc["model_context_probability"])
        if len(book_probs) < 3:
            book_probs = {}
        if len(model_probs) < 3:
            model_probs = {}
    elif family == FAMILY_OVER_UNDER and market_key in (
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    ):
        required = required_selections_for_normalization(FAMILY_OVER_UNDER, period, line)
        basis = f"normalized_ou_{period}_{line}"
        if required:
            for sel in required:
                fb = fair_by_m.get(sel) or {}
                if fb.get("fair_book_probability_verified") and fb.get("fair_book_probability") is not None:
                    book_probs[sel] = float(fb["fair_book_probability"])
                mc = model_by_m.get(sel) or {}
                if mc.get("model_context_probability") is not None:
                    model_probs[sel] = float(mc["model_context_probability"])
            if set(book_probs.keys()) != set(required):
                book_probs = {}
            if set(model_probs.keys()) != set(required):
                model_probs = {}
    else:
        return {
            "favourite_context_basis": None,
            "book_favourite": None,
            "model_favourite": None,
            "favourite_alignment": "unavailable",
            "favourite_intensity_book": None,
            "favourite_intensity_model": None,
        }

    book_sel, book_int, book_p = _favourite_from_probs(book_probs)
    model_sel, model_int, model_p = _favourite_from_probs(model_probs)

    if book_sel and model_sel:
        alignment = "aligned" if book_sel == model_sel else "disagree"
    elif book_sel or model_sel:
        alignment = "partial"
    else:
        alignment = "unavailable"

    return {
        "favourite_context_basis": basis,
        "book_favourite": (
            {"selection": book_sel, "implied_prob": book_p} if book_sel else None
        ),
        "model_favourite": (
            {"selection": model_sel, "model_prob": model_p} if model_sel else None
        ),
        "favourite_alignment": alignment,
        "favourite_intensity_book": book_int,
        "favourite_intensity_model": model_int,
    }


def _build_phase_2(
    *,
    market_key: str,
    panel_row: dict[str, Any],
    rows_by_m: dict[str, dict[str, Any]],
    fair_by_m: dict[str, dict[str, Any]],
    model_by_m: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    opp = get_opposition(market_key)
    opposition_status = opp.get("opposition_status")
    comparators = list(opp.get("comparator_selections") or [])
    complement = opp.get("complement_selection")

    selected_fair = fair_by_m.get(market_key) or {}
    selected_model = model_by_m.get(market_key) or {}
    sel_fair_p = _num(selected_fair.get("fair_book_probability"))
    sel_model_ctx = _num(selected_model.get("model_context_probability"))
    sel_quota = _num(panel_row.get("quota_book"))

    evidence: list[dict[str, Any]] = []
    book_pressures: list[tuple[str, float]] = []
    model_pressures: list[tuple[str, float]] = []

    if opposition_status != OPPOSITION_SUPPORTED:
        return {
            "status": "unavailable",
            "score": None,
            "opposition_status": opposition_status,
            "unsupported_reason": opp.get("unsupported_reason"),
            "canonical_market_family": opp.get("canonical_market_family"),
            "period": opp.get("period"),
            "line": opp.get("line"),
            "comparator_selections": [],
            "complement_selection": complement,
            "comparator_evidence": [],
            "strongest_comparator_selection": None,
            "strongest_comparator_book_probability": None,
            "strongest_comparator_model_probability": None,
            "opposition_pressure_book": None,
            "opposition_pressure_model": None,
            **_build_favourite_context(
                market_key=market_key,
                opp=opp,
                fair_by_m=fair_by_m,
                model_by_m=model_by_m,
            ),
            "fair_book_probability": sel_fair_p,
            "model_context_probability": sel_model_ctx,
            "model_book_gap": None,
            "absolute_model_book_gap": None,
            "gap_direction": "unavailable",
        }

    for cmp_key in comparators:
        cmp_row = rows_by_m.get(cmp_key)
        cmp_fair = fair_by_m.get(cmp_key) or {}
        cmp_model = model_by_m.get(cmp_key) or {}
        reasons: list[str] = []
        if cmp_row is None:
            reasons.append("comparator_row_missing")
            availability = "unavailable"
        else:
            availability = "available"

        cmp_quota = _num(cmp_row.get("quota_book")) if cmp_row else None
        cmp_quota_cec = _num(cmp_row.get("quota_cecchino")) if cmp_row else None
        raw_book = None
        if cmp_quota and cmp_quota > 0:
            raw_book = 1.0 / cmp_quota
        fair_p = _num(cmp_fair.get("fair_book_probability"))
        fair_verified = bool(cmp_fair.get("fair_book_probability_verified"))
        model_raw = _num(cmp_model.get("model_probability_raw"))
        model_ctx = _num(cmp_model.get("model_context_probability"))

        book_gap = (
            (sel_fair_p - fair_p) if sel_fair_p is not None and fair_p is not None else None
        )
        model_gap = (
            (sel_model_ctx - model_ctx)
            if sel_model_ctx is not None and model_ctx is not None
            else None
        )
        odds_gap = (
            (sel_quota - cmp_quota)
            if sel_quota is not None and cmp_quota is not None
            else None
        )

        if fair_p is not None and fair_verified:
            book_pressures.append((cmp_key, fair_p))
        if model_ctx is not None:
            model_pressures.append((cmp_key, model_ctx))

        evidence.append(
            {
                "market_key": cmp_key,
                "quota_book": cmp_quota,
                "quota_cecchino": cmp_quota_cec,
                "raw_book_probability": raw_book,
                "fair_book_probability": fair_p,
                "fair_book_probability_verified": fair_verified if cmp_row else None,
                "model_probability_raw": model_raw,
                "model_probability_context": model_ctx,
                "book_probability_gap_vs_selected": book_gap,
                "model_probability_gap_vs_selected": model_gap,
                "book_odds_gap_vs_selected": odds_gap,
                "availability_status": availability,
                "reason_codes": reasons,
            }
        )

    strongest_book = max(book_pressures, key=lambda x: x[1]) if book_pressures else None
    strongest_model = (
        max(model_pressures, key=lambda x: x[1]) if model_pressures else None
    )
    # Strongest comparator: prefer book pressure selection, else model
    strongest_sel = None
    if strongest_book:
        strongest_sel = strongest_book[0]
    elif strongest_model:
        strongest_sel = strongest_model[0]

    fav = _build_favourite_context(
        market_key=market_key,
        opp=opp,
        fair_by_m=fair_by_m,
        model_by_m=model_by_m,
    )

    # Gaps selected vs book/model
    model_book_gap = None
    abs_gap = None
    gap_direction = "unavailable"
    if sel_model_ctx is not None and sel_fair_p is not None:
        model_book_gap = sel_model_ctx - sel_fair_p
        abs_gap = abs(model_book_gap)
        if abs(model_book_gap) < 1e-12:
            gap_direction = "neutral"
        elif model_book_gap > 0:
            gap_direction = "positive"
        else:
            gap_direction = "negative"

    fair_ok = bool(selected_fair.get("fair_book_probability_verified"))
    model_ok = sel_model_ctx is not None
    comps_present = all(c in rows_by_m for c in comparators) if comparators else False

    if (
        opposition_status == OPPOSITION_SUPPORTED
        and comps_present
        and fair_ok
        and model_ok
    ):
        p2_status = "available"
    elif opposition_status == OPPOSITION_SUPPORTED and (
        comps_present or fair_ok or model_ok or evidence
    ):
        p2_status = "partial"
    else:
        p2_status = "unavailable"

    return {
        "status": p2_status,
        "score": None,
        "opposition_status": opposition_status,
        "unsupported_reason": opp.get("unsupported_reason"),
        "canonical_market_family": opp.get("canonical_market_family"),
        "period": opp.get("period"),
        "line": opp.get("line"),
        "comparator_selections": comparators,
        "complement_selection": complement,
        "comparator_evidence": evidence,
        "strongest_comparator_selection": strongest_sel,
        "strongest_comparator_book_probability": (
            strongest_book[1] if strongest_book else None
        ),
        "strongest_comparator_model_probability": (
            strongest_model[1] if strongest_model else None
        ),
        "opposition_pressure_book": strongest_book[1] if strongest_book else None,
        "opposition_pressure_model": strongest_model[1] if strongest_model else None,
        **fav,
        "fair_book_probability": sel_fair_p,
        "model_context_probability": sel_model_ctx,
        "model_book_gap": model_book_gap,
        "absolute_model_book_gap": abs_gap,
        "gap_direction": gap_direction,
    }


def _gap_reason_codes(phase_2: dict[str, Any]) -> list[str]:
    direction = phase_2.get("gap_direction")
    if direction == "positive":
        return ["model_above_book"]
    if direction == "negative":
        return ["model_below_book"]
    if direction == "neutral":
        return ["model_book_aligned"]
    return ["model_book_gap_unavailable"]


def _build_context_hooks(context_meta: dict[str, Any] | None) -> dict[str, Any]:
    meta = context_meta or {}

    def _hook(key: str) -> dict[str, Any]:
        block = meta.get(key)
        if not isinstance(block, dict):
            return {
                "status": "not_connected",
                "source_version": None,
                "available": None,
                "reason_codes": ["hook_not_provided"],
                "payload": None,
            }
        available = bool(block.get("available"))
        status = block.get("status")
        if status not in ("not_connected", "available_not_used", "unavailable"):
            status = "available_not_used" if available else "unavailable"
        return {
            "status": status,
            "source_version": block.get("source_version"),
            "available": available,
            "reason_codes": list(block.get("reason_codes") or []),
            "payload": None,
        }

    return {
        "balance_v5": _hook("balance_v5"),
        "goal_intensity_v5": _hook("goal_intensity_v5"),
    }


def _build_data_quality(
    *,
    fixture_meta: dict[str, Any],
    snapshot_info: dict[str, Any],
    phase_1: dict[str, Any],
    phase_2: dict[str, Any],
) -> dict[str, Any]:
    kickoff = _parse_dt(fixture_meta.get("kickoff"))
    snap_at = snapshot_info.get("snapshot_at")
    snap_dt = _parse_dt(snap_at) if not isinstance(snap_at, datetime) else snap_at
    if isinstance(snap_at, datetime):
        snap_dt = snap_at if snap_at.tzinfo else snap_at.replace(tzinfo=timezone.utc)

    before = None
    if snap_dt is not None and kickoff is not None:
        before = snap_dt < kickoff

    missing: list[str] = []
    inputs = phase_1.get("inputs") or {}
    for k in PRIMARY_ROW_FIELDS + DERIVED_ROW_FIELDS:
        if inputs.get(k) is None:
            missing.append(k)

    warnings: list[str] = []
    fidelity = snapshot_info.get("snapshot_fidelity")
    verified = bool(snapshot_info.get("snapshot_timestamp_verified"))
    if fidelity == FIDELITY_FALLBACK or not verified:
        warnings.append("snapshot_timestamp_unverified")
    if before is False:
        warnings.append("snapshot_not_before_kickoff")
    if phase_2.get("opposition_status") != OPPOSITION_SUPPORTED:
        warnings.append("opposition_unsupported")

    return {
        "source": "stored_kpi_panel_snapshot",
        "today_fixture_id": fixture_meta.get("today_fixture_id"),
        "local_fixture_id": fixture_meta.get("local_fixture_id")
        or fixture_meta.get("today_fixture_id"),
        "provider_fixture_id": fixture_meta.get("provider_fixture_id"),
        "competition_id": fixture_meta.get("competition_id"),
        "scan_date": _iso(fixture_meta.get("scan_date")),
        "kickoff": _iso(fixture_meta.get("kickoff")),
        "snapshot_at": _iso(snap_dt) if snap_dt else _iso(snap_at),
        "snapshot_source": snapshot_info.get("snapshot_source"),
        "snapshot_fidelity": fidelity,
        "snapshot_timestamp_verified": verified,
        "snapshot_before_kickoff": before,
        "pre_match_only": True,
        "no_post_match_features": True,
        "contains_settlement_fields": False,
        "contains_result_fields": False,
        "missing_fields": missing,
        "warning_codes": warnings,
    }


def _resolve_feature_status(
    *,
    phase_1: dict[str, Any],
    phase_2: dict[str, Any],
    data_quality: dict[str, Any],
) -> str:
    if data_quality.get("snapshot_before_kickoff") is False:
        return "unavailable"
    if not data_quality.get("snapshot_timestamp_verified"):
        # cannot be ready
        if phase_1.get("status") == "unavailable" and phase_2.get("status") == "unavailable":
            return "unavailable"
        return "partial"
    if phase_1.get("status") == "available" and phase_2.get("status") == "available":
        return "ready"
    if phase_1.get("status") == "unavailable" and phase_2.get("status") == "unavailable":
        return "unavailable"
    return "partial"


def build_purchasability_feature_item(
    *,
    panel_row: dict[str, Any],
    sibling_rows: list[dict[str, Any]],
    fixture_meta: dict[str, Any],
    context_meta: dict[str, Any] | None = None,
    fair_by_market: dict[str, dict[str, Any]] | None = None,
    model_by_market: dict[str, dict[str, Any]] | None = None,
    snapshot_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market_key = _market_key(panel_row)
    rows_by_m = _rows_by_market(sibling_rows)
    rows_by_m[market_key] = panel_row

    snap = snapshot_info or {
        "snapshot_at": fixture_meta.get("snapshot_at"),
        "snapshot_source": fixture_meta.get("snapshot_source"),
        "snapshot_fidelity": fixture_meta.get("snapshot_fidelity"),
        "snapshot_timestamp_verified": fixture_meta.get(
            "snapshot_timestamp_verified", False
        ),
    }

    fair_by_m = fair_by_market or resolve_fair_book_for_panel_rows(
        list(rows_by_m.values()),
        today_fixture_id=fixture_meta.get("today_fixture_id"),
        snapshot_at=_iso(snap.get("snapshot_at")),
        bookmaker_name=str(fixture_meta.get("bookmaker_name") or "panel"),
    )
    model_by_m = model_by_market or build_model_context_probability_map(
        list(rows_by_m.values())
    )

    phase_1 = _build_phase_1(panel_row)
    phase_2 = _build_phase_2(
        market_key=market_key,
        panel_row=panel_row,
        rows_by_m=rows_by_m,
        fair_by_m=fair_by_m,
        model_by_m=model_by_m,
    )
    data_quality = _build_data_quality(
        fixture_meta=fixture_meta,
        snapshot_info=snap,
        phase_1=phase_1,
        phase_2=phase_2,
    )
    feature_status = _resolve_feature_status(
        phase_1=phase_1, phase_2=phase_2, data_quality=data_quality
    )

    reason_codes = ["formula_not_implemented_phase_1"]
    reason_codes.extend(_gap_reason_codes(phase_2))
    if feature_status == "unavailable" and data_quality.get("snapshot_before_kickoff") is False:
        reason_codes.append("snapshot_not_before_kickoff")

    item = {
        "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
        "feature_version": PURCHASABILITY_FEATURE_VERSION,
        "feature_status": feature_status,
        "status": "not_calculated",
        "score": None,
        "class": None,
        "reading": None,
        "market_key": market_key,
        "selection": market_key,
        "phase_1_value": phase_1,
        "phase_2_quality": phase_2,
        "context_hooks": _build_context_hooks(context_meta),
        "reason_codes": reason_codes,
        "data_quality": data_quality,
    }
    return make_json_safe(item)


def build_purchasability_features_for_panel(
    *,
    kpi_panel: dict[str, Any] | None,
    fixture_meta: dict[str, Any],
    context_meta: dict[str, Any] | None = None,
    snapshot_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    panel = kpi_panel if isinstance(kpi_panel, dict) else {}
    rows = panel.get("rows") if isinstance(panel.get("rows"), list) else []
    bookmaker = panel.get("bookmaker") if isinstance(panel.get("bookmaker"), dict) else {}

    snap = snapshot_info or {
        "snapshot_at": fixture_meta.get("snapshot_at"),
        "snapshot_source": fixture_meta.get("snapshot_source"),
        "snapshot_fidelity": fixture_meta.get("snapshot_fidelity"),
        "snapshot_timestamp_verified": fixture_meta.get(
            "snapshot_timestamp_verified", False
        ),
    }

    meta = {
        **fixture_meta,
        "bookmaker_name": bookmaker.get("name") or fixture_meta.get("bookmaker_name"),
    }

    fair_by_m = resolve_fair_book_for_panel_rows(
        rows,
        today_fixture_id=meta.get("today_fixture_id"),
        snapshot_at=_iso(snap.get("snapshot_at")),
        bookmaker_name=str(meta.get("bookmaker_name") or "panel"),
    )
    model_by_m = build_model_context_probability_map(rows)

    items: list[dict[str, Any]] = []
    ready = partial = unavailable = 0
    supported: list[str] = []
    unsupported: list[str] = []

    for row in rows:
        mk = _market_key(row)
        if not mk:
            continue
        item = build_purchasability_feature_item(
            panel_row=row,
            sibling_rows=rows,
            fixture_meta=meta,
            context_meta=context_meta,
            fair_by_market=fair_by_m,
            model_by_market=model_by_m,
            snapshot_info=snap,
        )
        items.append(item)
        fs = item.get("feature_status")
        if fs == "ready":
            ready += 1
        elif fs == "partial":
            partial += 1
        else:
            unavailable += 1
        opp = get_opposition(mk)
        if opp.get("opposition_status") == OPPOSITION_SUPPORTED:
            supported.append(mk)
        else:
            unsupported.append(mk)

    if not rows:
        payload = {
            "status": "unavailable",
            "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_FEATURE_VERSION,
            "today_fixture_id": meta.get("today_fixture_id"),
            "items": [],
            "summary": {
                "total": 0,
                "ready": 0,
                "partial": 0,
                "unavailable": 0,
                "supported_markets": [],
                "unsupported_markets": [],
                "reason": "kpi_panel_json_missing_or_empty",
            },
            "no_score_formula": True,
            "no_db_writes": True,
            "no_signal_integration": True,
        }
    else:
        payload = {
            "status": "ok",
            "version": PURCHASABILITY_PREVIEW_CONTRACT_VERSION,
            "feature_version": PURCHASABILITY_FEATURE_VERSION,
            "today_fixture_id": meta.get("today_fixture_id"),
            "items": items,
            "summary": {
                "total": len(items),
                "ready": ready,
                "partial": partial,
                "unavailable": unavailable,
                "supported_markets": sorted(set(supported)),
                "unsupported_markets": sorted(set(unsupported)),
            },
            "no_score_formula": True,
            "no_db_writes": True,
            "no_signal_integration": True,
        }

    safe = make_json_safe(payload)
    json.dumps(safe, allow_nan=False)
    return safe


def build_purchasability_features_for_fixture(fixture: Any) -> dict[str, Any]:
    """Feature batch da CecchinoTodayFixture salvata (solo snapshot)."""
    panel = getattr(fixture, "kpi_panel_json", None)
    snap_info = resolve_purchasability_snapshot_timestamp(fixture)
    # Convert datetime snapshot_at to iso for downstream
    snap_at = snap_info.get("snapshot_at")
    if isinstance(snap_at, datetime):
        snap_info = {**snap_info, "snapshot_at": snap_at.isoformat()}

    fixture_meta = {
        "today_fixture_id": getattr(fixture, "id", None),
        "local_fixture_id": getattr(fixture, "id", None),
        "provider_fixture_id": getattr(fixture, "provider_fixture_id", None),
        "competition_id": getattr(fixture, "competition_id", None),
        "scan_date": getattr(fixture, "scan_date", None),
        "kickoff": getattr(fixture, "kickoff", None),
    }

    context_meta: dict[str, Any] = {}
    output = getattr(fixture, "cecchino_output", None)
    if isinstance(output, dict):
        if output.get("balance_v5") is not None or fixture_meta:
            bal = getattr(fixture, "balance_v5", None)
            # Prefer explicit attrs if present on detail payloads; from ORM often in cecchino_output
            bal = bal if bal is not None else output.get("balance_v5")
            if bal is not None:
                context_meta["balance_v5"] = {
                    "status": "available_not_used",
                    "available": True,
                    "source_version": (
                        bal.get("version") if isinstance(bal, dict) else None
                    ),
                    "reason_codes": ["detected_not_used_in_phase_2"],
                }
            gi = output.get("goal_intensity_v5_preview") or output.get(
                "goal_intensity_v5"
            )
            if gi is not None:
                context_meta["goal_intensity_v5"] = {
                    "status": "available_not_used",
                    "available": True,
                    "source_version": (
                        gi.get("version") if isinstance(gi, dict) else None
                    ),
                    "reason_codes": ["detected_not_used_in_phase_2"],
                }

    return build_purchasability_features_for_panel(
        kpi_panel=panel if isinstance(panel, dict) else None,
        fixture_meta=fixture_meta,
        context_meta=context_meta or None,
        snapshot_info=snap_info,
    )
