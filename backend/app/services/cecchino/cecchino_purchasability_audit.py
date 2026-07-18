"""Indice di Acquistabilità — Fase 1.1 audit e dataset (read-only).

Versioni:
  cecchino_purchasability_audit_v1_1
  cecchino_purchasability_dataset_v1_1

Nessuna formula 0–100, nessuna scrittura DB, nessuna modifica al Rating/Segnali.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_signal_activation import (
    EVAL_LOST,
    EVAL_NOT_EVALUABLE,
    EVAL_PENDING,
    EVAL_RESULT_MISSING,
    EVAL_WON,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import normalize_kpi_panel_rows
from app.services.cecchino.cecchino_market_opposition import (
    FAMILY_DOUBLE_CHANCE,
    NORM_NOT_APPLICABLE_OVERLAPPING,
    OPPOSITION_SUPPORTED,
    get_opposition,
    list_opposition_map,
    normalization_status_for_family,
    required_selections_for_normalization,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    match_result_from_fixture,
)

AUDIT_VERSION = "cecchino_purchasability_audit_v1_1"
DATASET_VERSION = "cecchino_purchasability_dataset_v1_1"

COHORT_ALL = "all_observed_rows"
COHORT_PRE_MATCH = "pre_match_rows"
COHORT_MARKET_VALID = "market_valid_rows"
COHORT_MODEL_COMPLETE = "model_complete_rows"
COHORT_CORE = "core_complete_rows"
COHORT_SETTLED = "settled_core_rows"
COHORT_EXCLUDED = "excluded_rows"

FIDELITY_PANEL = "verified_panel_odds_meta"
FIDELITY_SNAPSHOT = "verified_snapshot_odds_meta"
FIDELITY_CHECKED = "verified_odds_checked_at"
FIDELITY_FALLBACK = "generic_updated_at_fallback"
FIDELITY_MISSING = "missing"

VERIFIED_FIDELITIES = frozenset({FIDELITY_PANEL, FIDELITY_SNAPSHOT, FIDELITY_CHECKED})

CORR_THRESHOLD = 0.9

# Label/segno display → selection key canonica (no uppercase libero).
SELECTION_ALIASES: dict[str, str] = {
    "1": SEL_HOME,
    "HOME": SEL_HOME,
    "X": SEL_DRAW,
    "DRAW": SEL_DRAW,
    "2": SEL_AWAY,
    "AWAY": SEL_AWAY,
    "1X": SEL_ONE_X,
    "ONE_X": SEL_ONE_X,
    "X2": SEL_X_TWO,
    "X_TWO": SEL_X_TWO,
    "12": SEL_ONE_TWO,
    "ONE_TWO": SEL_ONE_TWO,
    "OVER 1.5": SEL_OVER_1_5,
    "OVER 2.5": SEL_OVER_2_5,
    "UNDER 2.5": SEL_UNDER_2_5,
    "UNDER 3.5": SEL_UNDER_3_5,
    "OVER1.5": SEL_OVER_1_5,
    "OVER2.5": SEL_OVER_2_5,
    "UNDER2.5": SEL_UNDER_2_5,
    "UNDER3.5": SEL_UNDER_3_5,
    "OVER_1_5": SEL_OVER_1_5,
    "OVER_2_5": SEL_OVER_2_5,
    "UNDER_2_5": SEL_UNDER_2_5,
    "UNDER_3_5": SEL_UNDER_3_5,
    "X PT": SEL_DRAW_PT,
    "DRAW_PT": SEL_DRAW_PT,
    "UNDER PT 1.5": SEL_UNDER_PT_1_5,
    "OVER PT 0.5": SEL_OVER_PT_0_5,
    "OVER PT 1.5": SEL_OVER_PT_1_5,
    "UNDER_PT_1_5": SEL_UNDER_PT_1_5,
    "OVER_PT_0_5": SEL_OVER_PT_0_5,
    "OVER_PT_1_5": SEL_OVER_PT_1_5,
}

FEATURE_CANDIDATE_KEYS = (
    "odds",
    "model_probability",
    "raw_book_implied_probability",
    "normalized_book_probability",
    "market_overround",
    "probability_advantage",
    "edge",
    "score",
    "rating",
    "favourite_intensity_book",
    "favourite_intensity_model",
)

TARGET_KEYS = (
    "settlement_status",
    "selection_won",
    "selection_lost",
    "selection_void",
    "unit_stake_profit",
    "book_break_even_probability",
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return _ensure_utc(datetime.fromisoformat(s))
        except ValueError:
            return None
    return None


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return _ensure_utc(dt).isoformat().replace("+00:00", "Z")


def _meta_pick(meta: dict[str, Any]) -> tuple[datetime | None, str | None]:
    for key in ("last_betfair_refresh_at", "odds_updated_at", "odds_fetched_at"):
        ts = _parse_ts(meta.get(key))
        if ts is not None:
            return ts, key
    return None, None


def resolve_purchasability_snapshot_timestamp(fixture: Any) -> dict[str, Any]:
    """Timestamp canonico snapshot KPI (non updated_at come primario)."""
    panel = fixture.kpi_panel_json if isinstance(getattr(fixture, "kpi_panel_json", None), dict) else {}
    odds_snap = (
        fixture.odds_snapshot_json
        if isinstance(getattr(fixture, "odds_snapshot_json", None), dict)
        else {}
    )
    panel_meta = panel.get("odds_meta") if isinstance(panel.get("odds_meta"), dict) else {}
    snap_meta = odds_snap.get("odds_meta") if isinstance(odds_snap.get("odds_meta"), dict) else {}

    ts, field = _meta_pick(panel_meta)
    if ts is not None:
        return {
            "snapshot_at": ts,
            "snapshot_source": f"kpi_panel_json.odds_meta.{field}",
            "snapshot_fidelity": FIDELITY_PANEL,
            "snapshot_timestamp_verified": True,
        }

    ts, field = _meta_pick(snap_meta)
    if ts is not None:
        return {
            "snapshot_at": ts,
            "snapshot_source": f"odds_snapshot_json.odds_meta.{field}",
            "snapshot_fidelity": FIDELITY_SNAPSHOT,
            "snapshot_timestamp_verified": True,
        }

    checked = _ensure_utc(getattr(fixture, "odds_checked_at", None))
    if checked is not None:
        return {
            "snapshot_at": checked,
            "snapshot_source": "cecchino_today_fixtures.odds_checked_at",
            "snapshot_fidelity": FIDELITY_CHECKED,
            "snapshot_timestamp_verified": True,
        }

    updated = _ensure_utc(getattr(fixture, "updated_at", None))
    if updated is not None:
        return {
            "snapshot_at": updated,
            "snapshot_source": "cecchino_today_fixtures.updated_at",
            "snapshot_fidelity": FIDELITY_FALLBACK,
            "snapshot_timestamp_verified": False,
        }

    return {
        "snapshot_at": None,
        "snapshot_source": None,
        "snapshot_fidelity": FIDELITY_MISSING,
        "snapshot_timestamp_verified": False,
    }


def resolve_selection_key(panel_row: dict[str, Any]) -> str:
    raw_key = panel_row.get("market_key")
    if isinstance(raw_key, str) and raw_key.strip():
        cand = raw_key.strip().upper().replace(" ", "_")
        if cand in SELECTION_ALIASES:
            return SELECTION_ALIASES[cand]
        # già chiave canonica
        if cand in SELECTION_ALIASES.values() or cand in {
            SEL_HOME, SEL_DRAW, SEL_AWAY, SEL_ONE_X, SEL_X_TWO, SEL_ONE_TWO,
            SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5,
            SEL_DRAW_PT, SEL_UNDER_PT_1_5, SEL_OVER_PT_0_5, SEL_OVER_PT_1_5,
        }:
            return cand
    for field in ("segno", "label"):
        lab = panel_row.get(field)
        if not isinstance(lab, str) or not lab.strip():
            continue
        alias = SELECTION_ALIASES.get(lab.strip().upper())
        if alias:
            return alias
        compact = lab.strip().upper().replace(" ", "")
        alias = SELECTION_ALIASES.get(compact) or SELECTION_ALIASES.get(
            lab.strip().upper().replace(" ", "_")
        )
        if alias:
            return alias
    return ""


def _extract_bookmaker(panel: dict[str, Any]) -> dict[str, Any]:
    bm = panel.get("bookmaker")
    if isinstance(bm, dict):
        return {
            "bookmaker_name": bm.get("name"),
            "bookmaker_provider_id": bm.get("provider_bookmaker_id"),
            "bookmaker_provider_source": bm.get("provider_source"),
        }
    return {
        "bookmaker_name": None,
        "bookmaker_provider_id": None,
        "bookmaker_provider_source": None,
    }


def rating_dependency_map() -> dict[str, Any]:
    return {
        "version": AUDIT_VERSION,
        "rating_function": "cecchino_kpi_panel_v2_betfair._compute_rating",
        "formula": (
            "raw = (prob_cecchino*100)*0.5 + (vantaggio_prob*100)*2.0 + edge_pct; "
            "clamp 0–100; round int"
        ),
        "direct_components": [
            {"name": "prob_cecchino", "weight_in_raw": 50.0, "panel_field": "prob_cecchino"},
            {"name": "vantaggio_prob", "weight_in_raw": 200.0, "panel_field": "vantaggio_prob"},
            {"name": "edge_pct", "weight_in_raw": 1.0, "panel_field": "edge_pct"},
        ],
        "parallel_not_in_rating": [
            {"name": "score_acquisto", "formula": "prob_cecchino * edge_pct / 100"}
        ],
        "classification": "benchmark_candidate",
        "persisted_as_components": False,
    }


def build_variable_registry() -> list[dict[str, Any]]:
    return [
        {
            "canonical_name": "odds",
            "source_field": "quota_book",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "independent_candidate",
            "audit_status": "verified",
            "motivation": "Quota Book riga KPI.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "panel_row",
            "source_function": "_build_metrics_row",
        },
        {
            "canonical_name": "model_probability",
            "source_field": "prob_cecchino",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "derived_candidate",
            "audit_status": "verified",
            "motivation": "1/quota_cecchino; in Rating.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": "benchmark_dependency via Rating",
            "explainability": "high",
            "source_quality": "panel_row",
            "source_function": "_prob_from_odd",
        },
        {
            "canonical_name": "probability_advantage",
            "source_field": "vantaggio_prob",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "derived_candidate",
            "audit_status": "verified",
            "motivation": "Componente Rating.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": "benchmark_dependency via Rating",
            "explainability": "high",
            "source_quality": "panel_row",
            "source_function": "prob_cecchino - prob_book",
        },
        {
            "canonical_name": "edge",
            "source_field": "edge_pct",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "derived_candidate",
            "audit_status": "verified",
            "motivation": "Componente Rating.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": "benchmark_dependency via Rating",
            "explainability": "high",
            "source_quality": "panel_row",
            "source_function": "_edge_pct",
        },
        {
            "canonical_name": "score",
            "source_field": "score_acquisto",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "derived_candidate",
            "audit_status": "verified",
            "motivation": "Parallelo; non in Rating.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": "deterministic_redundancy vs model*edge",
            "explainability": "medium",
            "source_quality": "panel_row",
            "source_function": "prob * edge / 100",
        },
        {
            "canonical_name": "rating",
            "source_field": "rating",
            "source_model": "kpi_panel_json.rows[]",
            "persistence": "persisted_json",
            "independence_class": "benchmark_candidate",
            "audit_status": "verified",
            "motivation": "Benchmark; non input obbligatorio Indice.",
            "pre_match_available": True,
            "leakage_risk": "low_if_verified_timestamp",
            "redundancy_note": "benchmark_dependency",
            "explainability": "medium",
            "source_quality": "panel_row",
            "source_function": "_compute_rating",
        },
        {
            "canonical_name": "normalized_book_probability",
            "source_field": "runtime",
            "source_model": "sibling rows",
            "persistence": "runtime",
            "independence_class": "derived_candidate",
            "audit_status": "verified",
            "motivation": "Solo mercati mutuamente esclusivi completi.",
            "pre_match_available": True,
            "leakage_risk": "low",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "conditional",
            "source_function": "_normalize_book_probs",
        },
        {
            "canonical_name": "btts_gg_nogal",
            "source_field": None,
            "source_model": None,
            "persistence": "unavailable",
            "independence_class": "unavailable",
            "audit_status": "unavailable",
            "motivation": "Assenti dal Pannello KPI.",
            "pre_match_available": False,
            "leakage_risk": "n/a",
            "redundancy_note": None,
            "explainability": "n/a",
            "source_quality": "absent",
            "source_function": None,
        },
        {
            "canonical_name": "settlement_targets",
            "source_field": "score_fulltime_*",
            "source_model": "CecchinoTodayFixture",
            "persistence": "persisted_columns",
            "independence_class": "excluded_leakage",
            "audit_status": "verified",
            "motivation": "Solo target.",
            "pre_match_available": False,
            "leakage_risk": "target_only_not_features",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "fixture_scores",
            "source_function": "evaluate_market_selection",
        },
    ]


def _panel_rows(fixture: CecchinoTodayFixture) -> list[dict[str, Any]]:
    panel = fixture.kpi_panel_json
    if not isinstance(panel, dict):
        return []
    normalized = normalize_kpi_panel_rows(copy.deepcopy(panel))
    if not isinstance(normalized, dict):
        return []
    rows = normalized.get("rows") or []
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        key = resolve_selection_key(row)
        if key:
            row["market_key"] = key
        out.append(row)
    return out


def _canonical_row_key(
    *,
    today_fixture_id: int,
    market_key: str,
    period: str,
    line: float | None,
    selection: str,
    snapshot_at: datetime | None,
) -> str:
    raw = "|".join(
        [
            str(today_fixture_id),
            market_key,
            period,
            "" if line is None else str(line),
            selection,
            _iso(snapshot_at) or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _normalize_book_probs(
    sibling_odds: dict[str, float],
    required: frozenset[str] | None,
) -> tuple[dict[str, float] | None, float | None, str]:
    if not required:
        return None, None, "no_normalization_set"
    if not required.issubset(set(sibling_odds.keys())):
        return None, None, "incomplete_market"
    implied = {k: 1.0 / sibling_odds[k] for k in required if sibling_odds[k] > 0}
    if len(implied) != len(required):
        return None, None, "incomplete_market"
    total = sum(implied.values())
    if total <= 0:
        return None, None, "invalid_implied_sum"
    overround = total - 1.0
    normalized = {k: implied[k] / total for k in implied}
    return normalized, overround, "ok"


def _settle_row(selection_key: str, fixture: CecchinoTodayFixture, odds: float) -> dict[str, Any]:
    match_result = match_result_from_fixture(fixture)
    ev = evaluate_market_selection(selection_key, match_result)
    status = ev.get("evaluation_status") or EVAL_PENDING
    won = status == EVAL_WON
    lost = status == EVAL_LOST
    void = False
    profit: float | None = None
    if won:
        profit = round(odds - 1.0, 4)
    elif lost:
        profit = -1.0
    settlement_status = status
    if status == EVAL_RESULT_MISSING:
        settlement_status = "missing"
    elif status == EVAL_PENDING:
        settlement_status = "pending"
    elif status == EVAL_NOT_EVALUABLE:
        settlement_status = "not_evaluable"
    elif won:
        settlement_status = "won"
    elif lost:
        settlement_status = "lost"
    return {
        "settlement_status": settlement_status,
        "selection_won": won,
        "selection_lost": lost,
        "selection_void": void,
        "unit_stake_profit": profit,
        "book_break_even_probability": round(1.0 / odds, 6) if odds > 0 else None,
        "evaluation_reason": ev.get("evaluation_reason"),
    }


def _favourite_from_probs(probs: dict[str, float]) -> tuple[str | None, float | None]:
    if not probs:
        return None, None
    best_k = max(probs, key=lambda k: probs[k])
    vals = sorted(probs.values(), reverse=True)
    intensity = round(vals[0] - vals[1], 6) if len(vals) >= 2 else round(vals[0], 6)
    return best_k, intensity


def _build_observed_row(
    fixture: CecchinoTodayFixture,
    panel_row: dict[str, Any],
    siblings: dict[str, dict[str, Any]],
    bookmaker_info: dict[str, Any],
) -> dict[str, Any]:
    market_key = resolve_selection_key(panel_row)
    opp = get_opposition(market_key) if market_key else get_opposition("")
    kickoff = _ensure_utc(fixture.kickoff)
    snap = resolve_purchasability_snapshot_timestamp(fixture)
    snapshot_at = snap["snapshot_at"]
    fidelity = snap["snapshot_fidelity"]
    verified = bool(snap["snapshot_timestamp_verified"])

    odds = _num(panel_row.get("quota_book"))
    model_prob = _num(panel_row.get("prob_cecchino"))
    panel_prob_book = _num(panel_row.get("prob_book"))
    raw_implied = round(1.0 / odds, 6) if odds and odds > 0 else None
    edge = _num(panel_row.get("edge_pct"))
    vantaggio = _num(panel_row.get("vantaggio_prob"))
    score = _num(panel_row.get("score_acquisto"))
    rating = panel_row.get("rating")
    rating_i = int(rating) if isinstance(rating, (int, float)) and not isinstance(rating, bool) else None
    odds_source = panel_row.get("book_source")
    if odds_source is not None and not isinstance(odds_source, str):
        odds_source = None

    exclusion: list[str] = []
    leakage_status = "safe"
    snapshot_before_kickoff = False

    if kickoff is None:
        exclusion.append("kickoff_missing")
    if fidelity == FIDELITY_MISSING or snapshot_at is None:
        exclusion.append("snapshot_at_missing")
        leakage_status = "unknown"
    elif fidelity == FIDELITY_FALLBACK:
        exclusion.append("snapshot_timestamp_not_verifiable")
        leakage_status = "unknown"
    elif kickoff is not None:
        if snapshot_at < kickoff:
            snapshot_before_kickoff = True
        else:
            exclusion.append("snapshot_not_before_kickoff")
            leakage_status = "excluded_leakage"

    if odds is None or odds <= 1.0:
        exclusion.append("invalid_odds")
    if not market_key:
        exclusion.append("market_key_missing")
    if opp["opposition_status"] != OPPOSITION_SUPPORTED:
        exclusion.append("opposition_unsupported")

    family = opp["canonical_market_family"]
    period = opp["period"]
    line = opp["line"]
    sibling_odds: dict[str, float] = {}
    sibling_model: dict[str, float] = {}
    sibling_book_prob: dict[str, float] = {}
    for sk, srow in siblings.items():
        sopp = get_opposition(sk)
        if (
            sopp["canonical_market_family"] != family
            or sopp["period"] != period
            or sopp["line"] != line
        ):
            continue
        o = _num(srow.get("quota_book"))
        if o and o > 0:
            sibling_odds[sk] = o
            sibling_book_prob[sk] = 1.0 / o
        mp = _num(srow.get("prob_cecchino"))
        if mp is not None:
            sibling_model[sk] = mp

    fixed_norm = normalization_status_for_family(family)
    if fixed_norm:
        normalized_map, overround, norm_status = None, None, fixed_norm
    else:
        required = required_selections_for_normalization(family, period, line)
        normalized_map, overround, norm_status = _normalize_book_probs(sibling_odds, required)

    normalized_prob = None
    if normalized_map and market_key in normalized_map:
        normalized_prob = round(normalized_map[market_key], 6)

    comp_keys = list(opp.get("comparator_selections") or [])
    complement = opp.get("complement_selection")
    comparator_odds = {k: sibling_odds[k] for k in comp_keys if k in sibling_odds}
    comparator_model = {k: sibling_model[k] for k in comp_keys if k in sibling_model}
    comparator_book = {k: sibling_book_prob[k] for k in comp_keys if k in sibling_book_prob}

    book_fav, book_int = _favourite_from_probs(sibling_book_prob)
    model_fav, model_int = _favourite_from_probs(sibling_model)
    alignment = None
    if book_fav and model_fav:
        alignment = "aligned" if book_fav == model_fav else "disagree"

    settle = {
        "settlement_status": "pending",
        "selection_won": False,
        "selection_lost": False,
        "selection_void": False,
        "unit_stake_profit": None,
        "book_break_even_probability": round(1.0 / odds, 6) if odds and odds > 0 else None,
        "evaluation_reason": None,
    }
    if odds and odds > 0 and market_key:
        settle = _settle_row(market_key, fixture, odds)

    feature_completeness = {
        "odds": odds is not None and odds > 1.0,
        "model_probability": model_prob is not None,
        "raw_book_implied_probability": raw_implied is not None,
        "normalized_book_probability": normalized_prob is not None
        or norm_status == NORM_NOT_APPLICABLE_OVERLAPPING,
        "market_overround": overround is not None
        or norm_status == NORM_NOT_APPLICABLE_OVERLAPPING,
        "probability_advantage": vantaggio is not None,
        "edge": edge is not None,
        "score": score is not None,
        "rating": rating_i is not None,
        "favourite_intensity_book": book_int is not None,
        "favourite_intensity_model": model_int is not None,
    }

    market_valid = (
        opp["opposition_status"] == OPPOSITION_SUPPORTED
        and odds is not None
        and odds > 1.0
        and bool(market_key)
        and "kickoff_missing" not in exclusion
    )
    model_complete = (
        market_valid
        and model_prob is not None
        and vantaggio is not None
        and edge is not None
        and score is not None
        and rating_i is not None
    )
    timestamp_ok = (
        verified
        and snapshot_before_kickoff
        and fidelity in VERIFIED_FIDELITIES
        and "snapshot_not_before_kickoff" not in exclusion
        and "snapshot_timestamp_not_verifiable" not in exclusion
    )
    book_identified = bool(odds_source) or bool(bookmaker_info.get("bookmaker_name"))
    if not book_identified:
        exclusion.append("book_source_unverified")

    core_ok = (
        model_complete
        and timestamp_ok
        and book_identified
        and leakage_status != "excluded_leakage"
    )

    settled_ok = core_ok and settle["settlement_status"] in ("won", "lost", "void")

    no_post = bool(timestamp_ok and leakage_status != "excluded_leakage")

    completeness = "complete" if core_ok else ("partial" if market_valid else "excluded")
    if exclusion and not core_ok:
        completeness = "excluded" if not market_valid else "partial"

    return {
        "local_fixture_id": fixture.local_fixture_id,
        "today_fixture_id": int(fixture.id),
        "provider_fixture_id": int(fixture.provider_fixture_id),
        "competition_id": fixture.competition_id,
        "competition_name": fixture.league_name,
        "kickoff": _iso(kickoff),
        "snapshot_at": _iso(snapshot_at),
        "snapshot_source": snap["snapshot_source"],
        "snapshot_fidelity": fidelity,
        "snapshot_timestamp_verified": verified,
        "generic_row_updated_at": _iso(_ensure_utc(getattr(fixture, "updated_at", None))),
        "odds_checked_at": _iso(_ensure_utc(getattr(fixture, "odds_checked_at", None))),
        "snapshot_before_kickoff": snapshot_before_kickoff,
        "source_snapshot_before_kickoff": snapshot_before_kickoff,
        "home_team": fixture.home_team_name,
        "away_team": fixture.away_team_name,
        "scan_date": str(fixture.scan_date) if fixture.scan_date else None,
        "raw_market_code": market_key,
        "canonical_market_family": family,
        "period": period,
        "line": line,
        "selection": market_key,
        "comparator_selections": comp_keys,
        "complement_selection": complement,
        "opposition_status": opp["opposition_status"],
        "bookmaker_name": bookmaker_info.get("bookmaker_name"),
        "bookmaker_provider_id": bookmaker_info.get("bookmaker_provider_id"),
        "bookmaker_provider_source": bookmaker_info.get("bookmaker_provider_source"),
        "odds_source": odds_source,
        "book_source": odds_source,
        "odds": odds,
        "model_probability": model_prob,
        "panel_prob_book": panel_prob_book,
        "raw_book_implied_probability": raw_implied,
        "normalized_book_probability": normalized_prob,
        "book_probability_normalization_status": norm_status,
        "market_overround": round(overround, 6) if overround is not None else None,
        "probability_advantage": vantaggio,
        "edge": edge,
        "score": score,
        "rating": rating_i,
        "rating_component_payload": {
            "prob_cecchino": model_prob,
            "vantaggio_prob": vantaggio,
            "edge_pct": edge,
            "weights": {"prob_cecchino_x100": 0.5, "vantaggio_prob_x100": 2.0, "edge_pct": 1.0},
        },
        "comparator_odds_payload": comparator_odds,
        "comparator_model_probability_payload": comparator_model,
        "comparator_book_probability_payload": comparator_book,
        "book_favourite": book_fav,
        "model_favourite": model_fav,
        "favourite_alignment": alignment,
        "favourite_intensity_book": book_int,
        "favourite_intensity_model": model_int,
        **settle,
        "feature_completeness_payload": feature_completeness,
        "completeness_status": completeness,
        "source_quality_status": "kpi_panel_json",
        "leakage_status": leakage_status,
        "exclusion_reason_codes": exclusion,
        "canonical_row_key": _canonical_row_key(
            today_fixture_id=int(fixture.id),
            market_key=market_key or "UNKNOWN",
            period=period,
            line=line,
            selection=market_key or "UNKNOWN",
            snapshot_at=snapshot_at,
        ),
        "dataset_version": DATASET_VERSION,
        "no_post_match_data_in_features": no_post,
        "is_pre_match": timestamp_ok,
        "is_market_valid": market_valid,
        "is_model_complete": model_complete,
        "is_core": core_ok,
        "is_settled_core": settled_ok,
        "feature_keys": list(FEATURE_CANDIDATE_KEYS),
        "target_keys": list(TARGET_KEYS),
    }


def _load_fixtures(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    competition_id: int | None,
) -> list[CecchinoTodayFixture]:
    stmt = select(CecchinoTodayFixture).order_by(
        CecchinoTodayFixture.scan_date.asc(), CecchinoTodayFixture.id.asc()
    )
    if date_from is not None:
        stmt = stmt.where(CecchinoTodayFixture.scan_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(CecchinoTodayFixture.scan_date <= date_to)
    if competition_id is not None:
        stmt = stmt.where(CecchinoTodayFixture.competition_id == int(competition_id))
    return list(db.scalars(stmt).all())


def _book_filter_match(
    book_filter: str | None,
    bookmaker_name: str | None,
    odds_source: str | None,
) -> bool:
    if not book_filter:
        return True
    f = book_filter.strip().lower()
    if bookmaker_name and bookmaker_name.strip().lower() == f:
        return True
    if odds_source and odds_source.strip().lower() == f:
        return True
    return False


def iter_purchasability_rows(
    fixtures: list[CecchinoTodayFixture],
    *,
    market_family: str | None = None,
    book_source: str | None = None,
) -> Iterator[dict[str, Any]]:
    for fx in fixtures:
        panel = fx.kpi_panel_json if isinstance(fx.kpi_panel_json, dict) else {}
        bookmaker_info = _extract_bookmaker(panel)
        rows = _panel_rows(fx)
        if not rows:
            continue
        siblings = {}
        for r in rows:
            k = resolve_selection_key(r)
            if k:
                siblings[k] = r
        for prow in rows:
            built = _build_observed_row(fx, prow, siblings, bookmaker_info)
            if market_family and built.get("canonical_market_family") != market_family:
                continue
            if not _book_filter_match(
                book_source, built.get("bookmaker_name"), built.get("odds_source")
            ):
                continue
            yield built


def build_purchasability_rows(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    book_source: str | None = None,
) -> list[dict[str, Any]]:
    fixtures = _load_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    return list(
        iter_purchasability_rows(
            fixtures, market_family=market_family, book_source=book_source
        )
    )


def _cohort_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fixtures = {r["today_fixture_id"] for r in rows}
    markets = sorted({r["raw_market_code"] for r in rows if r.get("raw_market_code")})
    dates = [r.get("scan_date") for r in rows if r.get("scan_date")]
    comps = {r.get("competition_id") for r in rows if r.get("competition_id") is not None}
    settled_n = sum(1 for r in rows if r.get("settlement_status") in ("won", "lost", "void"))
    void_n = sum(1 for r in rows if r.get("selection_void"))
    missing_n = sum(1 for r in rows if r.get("settlement_status") == "missing")
    excl: Counter[str] = Counter()
    for r in rows:
        for code in r.get("exclusion_reason_codes") or []:
            excl[code] += 1
    n = len(rows) or 1
    return {
        "rows": len(rows),
        "unique_fixtures": len(fixtures),
        "markets": markets,
        "selections": markets,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "competitions": len(comps),
        "settled_pct": round(100.0 * settled_n / n, 2),
        "void_pct": round(100.0 * void_n / n, 2),
        "missing_settlement_pct": round(100.0 * missing_n / n, 2),
        "exclusion_reasons": dict(excl),
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 6)


def _midranks(vals: list[float]) -> list[float]:
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return _pearson(_midranks(xs), _midranks(ys))


def _missing_overlap(rows: list[dict[str, Any]], a: str, b: str) -> dict[str, Any]:
    both_missing = sum(1 for r in rows if _num(r.get(a)) is None and _num(r.get(b)) is None)
    a_miss = sum(1 for r in rows if _num(r.get(a)) is None)
    b_miss = sum(1 for r in rows if _num(r.get(b)) is None)
    return {"both_missing": both_missing, "a_missing": a_miss, "b_missing": b_miss, "n": len(rows)}


def _vif_status(core_rows: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    if len(core_rows) < max(20, len(keys) + 5):
        return {
            "status": "insufficient_sample",
            "reason": f"n={len(core_rows)} < required for VIF with {len(keys)} vars",
            "vif": {},
        }
    # Build complete cases matrix
    matrix: list[list[float]] = []
    for r in core_rows:
        row = []
        ok = True
        for k in keys:
            v = _num(r.get(k))
            if v is None:
                ok = False
                break
            row.append(v)
        if ok:
            matrix.append(row)
    if len(matrix) < max(20, len(keys) + 5):
        return {
            "status": "insufficient_complete_cases",
            "reason": f"complete_cases={len(matrix)}",
            "vif": {},
        }
    # Simple diagonal VIF via R^2 of each vs others (OLS normal eq); skip if singular
    try:
        import numpy as np

        x = np.asarray(matrix, dtype=float)
        vif: dict[str, float] = {}
        for i, name in enumerate(keys):
            y = x[:, i]
            z = np.delete(x, i, axis=1)
            z = np.column_stack([np.ones(len(z)), z])
            coef, *_ = np.linalg.lstsq(z, y, rcond=None)
            pred = z @ coef
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            vif[name] = round(1.0 / (1.0 - r2), 4) if r2 < 0.999 else float("inf")
        return {"status": "ok", "reason": None, "vif": vif}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(exc), "vif": {}}


def _input_redundancy(core_rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "odds",
        "model_probability",
        "raw_book_implied_probability",
        "probability_advantage",
        "edge",
        "score",
        "rating",
    ]
    pairs = []
    missing = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            xs, ys = [], []
            for r in core_rows:
                va, vb = _num(r.get(a)), _num(r.get(b))
                if va is None or vb is None:
                    continue
                xs.append(va)
                ys.append(vb)
            missing.append({"a": a, "b": b, **_missing_overlap(core_rows, a, b)})
            if len(xs) < 10:
                continue
            p = _pearson(xs, ys)
            s = _spearman(xs, ys)
            pairs.append({"a": a, "b": b, "n": len(xs), "pearson": p, "spearman": s})

    # exact duplicate detection on feature vectors
    seen: dict[tuple, int] = {}
    dup_count = 0
    for r in core_rows:
        vec = tuple(_num(r.get(k)) for k in keys)
        if vec in seen:
            dup_count += 1
        else:
            seen[vec] = 1

    high = [
        {**p, "class": "empirical_high_correlation"}
        for p in pairs
        if (p.get("pearson") is not None and abs(p["pearson"]) >= CORR_THRESHOLD)
        or (p.get("spearman") is not None and abs(p["spearman"]) >= CORR_THRESHOLD)
    ]
    deterministic = [
        {
            "field": "raw_book_implied_probability",
            "derived_from": "odds",
            "rule": "1/odds",
            "class": "deterministic_redundancy",
        },
        {
            "field": "score",
            "derived_from": "model_probability,edge",
            "rule": "model_probability * edge / 100",
            "class": "deterministic_redundancy",
        },
        {
            "field": "rating",
            "derived_from": "model_probability,probability_advantage,edge",
            "class": "benchmark_dependency",
        },
    ]
    vif = _vif_status(core_rows, keys)
    return {
        "pair_correlations": pairs[:40],
        "high_correlation_pairs": high,
        "missing_overlap": missing[:20],
        "derived_field_dependencies": deterministic,
        "exact_duplicates_detected": dup_count > 0,
        "exact_duplicate_count": dup_count,
        "vif": vif,
        "classification_notes": [
            "deterministic_redundancy",
            "empirical_high_correlation",
            "benchmark_dependency",
            "insufficient_sample",
        ],
    }


def build_purchasability_audit(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    book_source: str | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    rows = build_purchasability_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )
    all_rows = rows
    pre_match = [r for r in rows if r.get("is_pre_match")]
    market_valid = [r for r in rows if r.get("is_market_valid")]
    model_complete = [r for r in rows if r.get("is_model_complete")]
    core = [r for r in rows if r.get("is_core")]
    settled = [r for r in rows if r.get("is_settled_core")]
    excluded = [r for r in rows if r.get("exclusion_reason_codes")]

    verified_n = sum(1 for r in rows if r.get("snapshot_timestamp_verified"))
    fallback_n = sum(1 for r in rows if r.get("snapshot_fidelity") == FIDELITY_FALLBACK)
    post_ko = sum(1 for r in rows if "snapshot_not_before_kickoff" in (r.get("exclusion_reason_codes") or []))

    market_counts: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        mk = r.get("raw_market_code") or "UNKNOWN"
        market_counts[mk]["observed"] += 1
        if r.get("snapshot_timestamp_verified") and r.get("snapshot_before_kickoff"):
            market_counts[mk]["verified_pre_match"] += 1
        if r.get("is_model_complete"):
            market_counts[mk]["model_complete"] += 1
        if r.get("is_core"):
            market_counts[mk]["core"] += 1
        if r.get("is_settled_core"):
            market_counts[mk]["settled"] += 1

    market_coverage = []
    markets_ready: list[str] = []
    markets_insufficient: list[str] = []
    for entry in list_opposition_map():
        mk = entry["raw_market_code"]
        c = market_counts.get(mk, Counter())
        obs = c["observed"] or 0
        settled_n = c["settled"]
        core_n = c["core"]
        verified_pm = c["verified_pre_match"]
        blocking_m: list[str] = []
        warnings_m: list[str] = []
        if entry["opposition_status"] != OPPOSITION_SUPPORTED:
            blocking_m.append("unsupported_mapping")
        if obs == 0:
            blocking_m.append("no_observed_rows")
        if core_n == 0:
            blocking_m.append("no_core_rows")
        if settled_n == 0:
            warnings_m.append("no_settled_rows")
            blocking_m.append("no_settled_rows")
        if obs and verified_pm / obs < 0.5:
            warnings_m.append("low_timestamp_coverage")
        if obs < 30:
            warnings_m.append("low_sample")
        if entry["canonical_market_family"] == FAMILY_DOUBLE_CHANCE:
            norm_app = NORM_NOT_APPLICABLE_OVERLAPPING
        elif entry["opposition_status"] != OPPOSITION_SUPPORTED:
            norm_app = "unsupported"
        else:
            norm_app = "applicable_if_complete"
        ready = (
            entry["opposition_status"] == OPPOSITION_SUPPORTED
            and core_n > 0
            and settled_n > 0
            and verified_pm > 0
        )
        if ready:
            markets_ready.append(mk)
        else:
            markets_insufficient.append(mk)
        market_coverage.append(
            {
                **entry,
                "observed_rows": obs,
                "verified_pre_match_rows": verified_pm,
                "model_complete_rows": c["model_complete"],
                "core_complete_rows": core_n,
                "settled_core_rows": settled_n,
                "settlement_pct": round(100.0 * settled_n / obs, 2) if obs else 0.0,
                "timestamp_verified_pct": round(100.0 * verified_pm / obs, 2) if obs else 0.0,
                "normalization_applicability": norm_app,
                "blocking_reasons": blocking_m,
                "sample_size_warning": warnings_m,
                "settlement_available": settled_n > 0,
            }
        )

    registry = build_variable_registry()
    independent = [
        v["canonical_name"] for v in registry if v["independence_class"] == "independent_candidate"
    ]
    benchmark = [
        v["canonical_name"] for v in registry if v["independence_class"] == "benchmark_candidate"
    ]
    redundant_set: list[str] = []
    for v in registry:
        note = v.get("redundancy_note") or ""
        if "benchmark_dependency" in note or "deterministic_redundancy" in note:
            if v["canonical_name"] not in redundant_set:
                redundant_set.append(v["canonical_name"])
    red = _input_redundancy(core)
    for p in red.get("high_correlation_pairs") or []:
        for name in (p.get("a"), p.get("b")):
            if name and name not in redundant_set and name != "odds":
                redundant_set.append(name)
    excluded_vars = [
        v["canonical_name"]
        for v in registry
        if v["independence_class"] in ("unavailable", "excluded_leakage")
    ]

    blocking: list[str] = []
    if verified_n == 0:
        blocking.append("snapshot_timestamp_not_verifiable")
    if not any(r.get("odds_source") or r.get("bookmaker_name") for r in rows):
        blocking.append("book_source_unverified")
    if len(core) == 0:
        blocking.append("no_core_complete_rows")
    if len(settled) == 0:
        blocking.append("no_settled_core_rows")
    if not markets_ready:
        blocking.append("no_usable_markets")

    readiness = {
        "kpi_source_identified": True,
        "canonical_snapshot_available": verified_n > 0,
        "pre_match_timestamp_verified": any(r.get("is_pre_match") for r in rows),
        "market_opposition_map_complete": True,
        "rating_dependency_map_complete": True,
        "odds_source_verified": any(r.get("odds_source") for r in core),
        "book_overround_computable": any(
            r.get("book_probability_normalization_status") == "ok" for r in core
        ),
        "settlement_available": len(settled) > 0,
        "unit_profit_computable": any(r.get("unit_stake_profit") is not None for r in settled),
        "market_valid_rows": len(market_valid),
        "model_complete_rows": len(model_complete),
        "core_dataset_rows": len(core),
        "settled_core_rows": len(settled),
        "markets_ready": sorted(set(markets_ready)),
        "markets_insufficient": sorted(set(markets_insufficient)),
        "variables_independent_candidates": independent,
        "variables_benchmark_candidates": benchmark,
        "variables_redundant_candidates": redundant_set,
        "variables_excluded": excluded_vars,
        "blocking_issues": blocking,
        "recommended_next_step": (
            "phase_2_statistical_research" if not blocking else "resolve_data_gaps"
        ),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    bookmaker_names = sorted(
        {r.get("bookmaker_name") for r in rows if r.get("bookmaker_name")}
    )
    odds_sources = sorted({r.get("odds_source") for r in rows if r.get("odds_source")})

    return {
        "version": AUDIT_VERSION,
        "dataset_version": DATASET_VERSION,
        "status": "ok",
        "elapsed_ms": elapsed_ms,
        "filters": {
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
            "competition_id": competition_id,
            "market_family": market_family,
            "book_source": book_source,
        },
        "summary": {
            "observed_rows": len(all_rows),
            "timestamp_verified_rows": verified_n,
            "generic_updated_at_fallback_rows": fallback_n,
            "post_kickoff_excluded_rows": post_ko,
            "pre_match_rows": len(pre_match),
            "market_valid_rows": len(market_valid),
            "model_complete_rows": len(model_complete),
            "core_rows": len(core),
            "core_complete_rows": len(core),
            "settled_core_rows": len(settled),
            "excluded_rows": len(excluded),
            "unique_fixtures": len({r["today_fixture_id"] for r in all_rows}),
            "timestamp_verified_pct": round(100.0 * verified_n / (len(all_rows) or 1), 2),
            "bookmaker_names": bookmaker_names,
            "odds_sources": odds_sources,
            "markets_ready": readiness["markets_ready"],
            "date_min": _cohort_stats(all_rows).get("date_min"),
            "date_max": _cohort_stats(all_rows).get("date_max"),
            "note": (
                "Fase di audit research. Nessun Indice di Acquistabilità calcolato. "
                "Nessuna influenza sui Segnali Cecchino. "
                "updated_at generico non costituisce prova di uno snapshot pre-match."
            ),
            "snapshot_limitation": (
                "Timestamp canonico da odds_meta (panel/snapshot) o odds_checked_at; "
                "updated_at solo fallback diagnostico non verificato."
            ),
        },
        "cohorts": {
            COHORT_ALL: _cohort_stats(all_rows),
            COHORT_PRE_MATCH: _cohort_stats(pre_match),
            COHORT_MARKET_VALID: _cohort_stats(market_valid),
            COHORT_MODEL_COMPLETE: _cohort_stats(model_complete),
            COHORT_CORE: _cohort_stats(core),
            COHORT_SETTLED: _cohort_stats(settled),
            COHORT_EXCLUDED: _cohort_stats(excluded),
        },
        "variable_registry": registry,
        "rating_dependency_map": rating_dependency_map(),
        "input_redundancy": red,
        "market_coverage": market_coverage,
        "exclusions": _cohort_stats(excluded).get("exclusion_reasons") or {},
        "phase_2_readiness": readiness,
        "no_db_writes": True,
        "no_purchasability_formula": True,
    }


def build_purchasability_dataset(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    book_source: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    fixtures = _load_fixtures(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    end = offset + limit

    def _match_status(r: dict[str, Any]) -> bool:
        if status == "core":
            return bool(r.get("is_core"))
        if status == "settled":
            return bool(r.get("is_settled_core"))
        if status == "pre_match":
            return bool(r.get("is_pre_match"))
        if status == "excluded":
            return bool(r.get("exclusion_reason_codes"))
        if status == "model_complete":
            return bool(r.get("is_model_complete"))
        if status == "market_valid":
            return bool(r.get("is_market_valid"))
        return True

    total = 0
    page: list[dict[str, Any]] = []
    for r in iter_purchasability_rows(
        fixtures, market_family=market_family, book_source=book_source
    ):
        if not _match_status(r):
            continue
        if total >= offset and total < end:
            page.append(r)
        total += 1
        # continue counting after page filled

    return {
        "version": DATASET_VERSION,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": page,
        "no_purchasability_formula": True,
        "no_db_writes": True,
    }


def build_purchasability_markets_payload(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    audit = build_purchasability_audit(db, date_from=date_from, date_to=date_to)
    return {
        "version": AUDIT_VERSION,
        "markets": audit.get("market_coverage") or [],
        "opposition_map": list_opposition_map(),
    }


EXPORT_KINDS = (
    "audit_summary",
    "variable_registry",
    "market_opposition_map",
    "market_coverage",
    "dataset",
    "exclusions",
    "rating_dependency_map",
)


def purchasability_export_filename(kind: str) -> str:
    mapping = {
        "audit_summary": "purchasability_audit_summary.json",
        "variable_registry": "purchasability_variable_registry.csv",
        "market_opposition_map": "purchasability_market_opposition_map.csv",
        "market_coverage": "purchasability_market_coverage.csv",
        "dataset": "purchasability_dataset.csv",
        "exclusions": "purchasability_exclusions.csv",
        "rating_dependency_map": "purchasability_rating_dependency_map.json",
    }
    return mapping.get(kind, f"purchasability_{kind}.txt")


def _csv_from_dicts(rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> str:
    if not rows:
        return ""
    keys = fieldnames or sorted({k for r in rows for k in r.keys()})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        flat = {}
        for k in keys:
            v = r.get(k)
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, ensure_ascii=False)
            else:
                flat[k] = v
        w.writerow(flat)
    return buf.getvalue()


def stream_purchasability_export(
    db: Session,
    kind: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    competition_id: int | None = None,
    market_family: str | None = None,
    book_source: str | None = None,
) -> Iterator[bytes]:
    if kind == "dataset":
        fixtures = _load_fixtures(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        header_written = False
        fieldnames: list[str] | None = None
        buf = io.StringIO()
        writer: csv.DictWriter | None = None
        for r in iter_purchasability_rows(
            fixtures, market_family=market_family, book_source=book_source
        ):
            if not header_written:
                fieldnames = sorted(r.keys())
                writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                header_written = True
                yield buf.getvalue().encode("utf-8")
                buf.seek(0)
                buf.truncate(0)
            assert writer is not None and fieldnames is not None
            flat = {}
            for k in fieldnames:
                v = r.get(k)
                flat[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
            writer.writerow(flat)
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
        if not header_written:
            yield b""
        return

    audit = build_purchasability_audit(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )
    if kind == "audit_summary":
        payload = {
            "version": audit["version"],
            "summary": audit["summary"],
            "cohorts": audit["cohorts"],
            "phase_2_readiness": audit["phase_2_readiness"],
            "exclusions": audit["exclusions"],
        }
        yield json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return
    if kind == "rating_dependency_map":
        yield json.dumps(audit["rating_dependency_map"], ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        return
    if kind == "variable_registry":
        yield _csv_from_dicts(audit["variable_registry"]).encode("utf-8")
        return
    if kind == "market_opposition_map":
        yield _csv_from_dicts(list_opposition_map()).encode("utf-8")
        return
    if kind == "market_coverage":
        yield _csv_from_dicts(audit["market_coverage"]).encode("utf-8")
        return
    if kind == "exclusions":
        excl_rows = [
            {"reason": k, "count": v} for k, v in sorted((audit.get("exclusions") or {}).items())
        ]
        yield _csv_from_dicts(excl_rows, ["reason", "count"]).encode("utf-8")
        return
    yield json.dumps({"error": "unknown_export_kind", "kind": kind}).encode("utf-8")
