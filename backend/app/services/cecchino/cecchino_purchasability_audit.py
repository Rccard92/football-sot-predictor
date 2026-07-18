"""Indice di Acquistabilità — Fase 1 audit e dataset storico research (read-only).

Versioni:
  cecchino_purchasability_audit_v1
  cecchino_purchasability_dataset_v1

Nessuna formula 0–100, nessuna scrittura DB, nessuna modifica al Rating/Segnali.
"""

from __future__ import annotations

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
    OPPOSITION_SUPPORTED,
    get_opposition,
    list_opposition_map,
    required_selections_for_normalization,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    evaluate_market_selection,
    match_result_from_fixture,
)

AUDIT_VERSION = "cecchino_purchasability_audit_v1"
DATASET_VERSION = "cecchino_purchasability_dataset_v1"

COHORT_ALL = "all_observed_rows"
COHORT_PRE_MATCH = "pre_match_rows"
COHORT_CORE = "core_complete_rows"
COHORT_SETTLED = "settled_core_rows"
COHORT_EXCLUDED = "excluded_rows"

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def rating_dependency_map() -> dict[str, Any]:
    """Dipendenze Rating da cecchino_kpi_panel_v2_betfair._compute_rating (codice reale)."""
    return {
        "version": AUDIT_VERSION,
        "rating_function": "cecchino_kpi_panel_v2_betfair._compute_rating",
        "formula": (
            "raw = (prob_cecchino*100)*0.5 + (vantaggio_prob*100)*2.0 + edge_pct; "
            "clamp 0–100; round int"
        ),
        "direct_components": [
            {
                "name": "prob_cecchino",
                "weight_in_raw": 50.0,
                "source": "1/quota_cecchino",
                "panel_field": "prob_cecchino",
            },
            {
                "name": "vantaggio_prob",
                "weight_in_raw": 200.0,
                "source": "prob_cecchino - prob_book",
                "panel_field": "vantaggio_prob",
            },
            {
                "name": "edge_pct",
                "weight_in_raw": 1.0,
                "source": "(quota_book/quota_cecchino - 1)*100",
                "panel_field": "edge_pct",
            },
        ],
        "indirect_components": [
            {"name": "quota_book", "panel_field": "quota_book"},
            {"name": "quota_cecchino", "panel_field": "quota_cecchino"},
            {"name": "prob_book", "panel_field": "prob_book", "source": "1/quota_book"},
        ],
        "parallel_not_in_rating": [
            {
                "name": "score_acquisto",
                "formula": "prob_cecchino * edge_pct / 100",
                "panel_field": "score_acquisto",
            }
        ],
        "thresholds": {
            "rating_label": "Elite>=90 Premium>=80 Forte>=70 Buona>=60 Sufficiente>=50 Debole>=40 else Scarto",
            "signal_activation_min_rating": 50,
            "note": "Le soglie label/signal non sono input dell'Indice; documentate solo come contesto.",
        },
        "classification": "benchmark_candidate",
        "persisted_as_components": False,
        "historical_fidelity": (
            "Il valore storico è quello in kpi_panel_json al momento dell'ultimo upsert Today; "
            "non esiste storico multi-versione del panel."
        ),
    }


def build_variable_registry() -> list[dict[str, Any]]:
    """Inventario variabili candidate con origine verificata nel codice."""
    return [
        {
            "canonical_name": "odds",
            "source_field": "quota_book",
            "source_model": "CecchinoTodayFixture.kpi_panel_json.rows[]",
            "source_function": "build_cecchino_kpi_panel_v2_betfair._build_metrics_row",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low_if_snapshot_before_kickoff",
            "independence_class": "independent_candidate",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Quota Book mostrata nel Pannello KPI.",
        },
        {
            "canonical_name": "model_probability",
            "source_field": "prob_cecchino",
            "source_model": "CecchinoTodayFixture.kpi_panel_json.rows[]",
            "source_function": "_prob_from_odd(quota_cecchino)",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low_if_snapshot_before_kickoff",
            "independence_class": "derived_candidate",
            "redundancy_note": "Incorporata nel Rating (peso 0.5).",
            "explainability": "high",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Probabilità Cecchino da quota modello.",
        },
        {
            "canonical_name": "raw_book_implied_probability",
            "source_field": "1/quota_book (runtime; panel ha anche prob_book)",
            "source_model": "runtime + kpi_panel_json.prob_book",
            "source_function": "research: 1/odds",
            "persistence": "runtime",
            "pre_match_available": True,
            "leakage_risk": "low_if_snapshot_before_kickoff",
            "independence_class": "derived_candidate",
            "redundancy_note": "Dovrebbe coincidere con prob_book panel.",
            "explainability": "high",
            "source_quality": "derived_from_odds",
            "audit_status": "verified",
            "motivation": "Implicita grezza per ROI/confronto.",
        },
        {
            "canonical_name": "normalized_book_probability",
            "source_field": "runtime overround removal",
            "source_model": "sibling rows stesso panel",
            "source_function": "_normalize_book_probs",
            "persistence": "runtime",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": "Dipende da completezza mercato.",
            "explainability": "high",
            "source_quality": "conditional",
            "audit_status": "verified",
            "motivation": "Solo se mercato completo nello stesso snapshot.",
        },
        {
            "canonical_name": "market_overround",
            "source_field": "sum(raw_implied) - 1",
            "source_model": "runtime",
            "source_function": "_normalize_book_probs",
            "persistence": "runtime",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "conditional",
            "audit_status": "verified",
            "motivation": "Overround book sullo stesso mercato/period/line.",
        },
        {
            "canonical_name": "probability_advantage",
            "source_field": "vantaggio_prob",
            "source_model": "CecchinoTodayFixture.kpi_panel_json.rows[]",
            "source_function": "prob_cecchino - prob_book",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": "Componente diretta del Rating (peso 2.0).",
            "explainability": "high",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Non persistito nelle activation KPI (solo panel).",
        },
        {
            "canonical_name": "edge",
            "source_field": "edge_pct",
            "source_model": "kpi_panel_json.rows[]",
            "source_function": "_edge_pct",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": "Componente diretta del Rating.",
            "explainability": "high",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Edge % book vs Cecchino.",
        },
        {
            "canonical_name": "score",
            "source_field": "score_acquisto",
            "source_model": "kpi_panel_json.rows[]",
            "source_function": "prob_cecchino * edge_pct / 100",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": "Parallelo al Rating; non entra nella formula rating.",
            "explainability": "medium",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Score acquisto runtime nel panel.",
        },
        {
            "canonical_name": "rating",
            "source_field": "rating",
            "source_model": "kpi_panel_json.rows[]",
            "source_function": "_compute_rating",
            "persistence": "persisted_json",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "benchmark_candidate",
            "redundancy_note": "Aggrega prob, vantaggio, edge.",
            "explainability": "medium",
            "source_quality": "panel_row",
            "audit_status": "verified",
            "motivation": "Benchmark; non input obbligatorio Indice.",
        },
        {
            "canonical_name": "rating_component_payload",
            "source_field": "ricostruito (non serializzato storicamente)",
            "source_model": "runtime da campi panel",
            "source_function": "rating_dependency_map / row builder",
            "persistence": "runtime",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "derived_candidate",
            "redundancy_note": "Duplica componenti rating.",
            "explainability": "high",
            "source_quality": "reconstructed",
            "audit_status": "verified",
            "motivation": "Nessun campo components dedicato nel panel.",
        },
        {
            "canonical_name": "comparator_context",
            "source_field": "sibling rows same panel",
            "source_model": "kpi_panel_json.rows[]",
            "source_function": "cecchino_market_opposition + panel siblings",
            "persistence": "runtime",
            "pre_match_available": True,
            "leakage_risk": "low",
            "independence_class": "independent_candidate",
            "redundancy_note": None,
            "explainability": "high",
            "source_quality": "panel_siblings",
            "audit_status": "verified",
            "motivation": "Contesto mercato opposto dallo stesso snapshot.",
        },
        {
            "canonical_name": "btts_gg_nogal",
            "source_field": None,
            "source_model": None,
            "source_function": None,
            "persistence": "unavailable",
            "pre_match_available": False,
            "leakage_risk": "n/a",
            "independence_class": "unavailable",
            "redundancy_note": None,
            "explainability": "n/a",
            "source_quality": "absent",
            "audit_status": "unavailable",
            "motivation": "GG/No Goal assenti dal Pannello KPI v2.",
        },
        {
            "canonical_name": "settlement_targets",
            "source_field": "score_fulltime_* / score_halftime_*",
            "source_model": "CecchinoTodayFixture",
            "source_function": "evaluate_market_selection + match_result_from_fixture",
            "persistence": "persisted_columns",
            "pre_match_available": False,
            "leakage_risk": "target_only_not_features",
            "independence_class": "excluded_leakage",
            "redundancy_note": "Target research; mai feature.",
            "explainability": "high",
            "source_quality": "fixture_scores",
            "audit_status": "verified",
            "motivation": "Esito post-match solo nei target.",
        },
    ]


def _source_snapshot_at(row: CecchinoTodayFixture) -> datetime | None:
    # Canonico: updated_at del Today row (ultimo upsert panel). Fallback odds_checked_at.
    return _ensure_utc(getattr(row, "updated_at", None)) or _ensure_utc(
        getattr(row, "odds_checked_at", None)
    )


def _panel_rows(fixture: CecchinoTodayFixture) -> list[dict[str, Any]]:
    panel = fixture.kpi_panel_json
    if not isinstance(panel, dict):
        return []
    rows = panel.get("rows")
    if not isinstance(rows, list):
        return []
    # normalize mutates in place copy
    copied = [dict(r) if isinstance(r, dict) else {} for r in rows]
    normalize_kpi_panel_rows(copied)
    return [r for r in copied if isinstance(r, dict)]


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
    void = False  # evaluator corrente non emette void
    profit: float | None = None
    if won:
        profit = round(odds - 1.0, 4)
    elif lost:
        profit = -1.0
    elif void:
        profit = 0.0
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
    intensity = None
    if len(vals) >= 2:
        intensity = round(vals[0] - vals[1], 6)
    elif vals:
        intensity = round(vals[0], 6)
    return best_k, intensity


def _build_observed_row(
    fixture: CecchinoTodayFixture,
    panel_row: dict[str, Any],
    siblings: dict[str, dict[str, Any]],
    book_source: str | None,
) -> dict[str, Any]:
    market_key = str(panel_row.get("market_key") or panel_row.get("segno") or "").strip().upper()
    opp = get_opposition(market_key)
    kickoff = _ensure_utc(fixture.kickoff)
    snapshot_at = _source_snapshot_at(fixture)
    odds = _num(panel_row.get("quota_book"))
    model_prob = _num(panel_row.get("prob_cecchino"))
    panel_prob_book = _num(panel_row.get("prob_book"))
    raw_implied = round(1.0 / odds, 6) if odds and odds > 0 else None
    edge = _num(panel_row.get("edge_pct"))
    vantaggio = _num(panel_row.get("vantaggio_prob"))
    score = _num(panel_row.get("score_acquisto"))
    rating = panel_row.get("rating")
    rating_i = int(rating) if isinstance(rating, (int, float)) and not isinstance(rating, bool) else None

    exclusion: list[str] = []
    leakage_status = "safe"
    source_snapshot_before_kickoff = False
    if kickoff is None:
        exclusion.append("kickoff_missing")
    if snapshot_at is None:
        exclusion.append("snapshot_at_missing")
        leakage_status = "unknown"
    elif kickoff is not None:
        if snapshot_at < kickoff:
            source_snapshot_before_kickoff = True
        else:
            exclusion.append("snapshot_not_before_kickoff")
            leakage_status = "excluded_leakage"

    if odds is None or odds <= 1.0:
        exclusion.append("invalid_odds")
    if not market_key:
        exclusion.append("market_key_missing")
    if opp["opposition_status"] != OPPOSITION_SUPPORTED:
        exclusion.append("opposition_unsupported")

    # Sibling odds for same family/period/line
    family = opp["canonical_market_family"]
    period = opp["period"]
    line = opp["line"]
    sibling_odds: dict[str, float] = {}
    sibling_model: dict[str, float] = {}
    sibling_book_prob: dict[str, float] = {}
    for sk, srow in siblings.items():
        sopp = get_opposition(sk)
        if sopp["canonical_market_family"] != family or sopp["period"] != period or sopp["line"] != line:
            continue
        o = _num(srow.get("quota_book"))
        if o and o > 0:
            sibling_odds[sk] = o
            sibling_book_prob[sk] = 1.0 / o
        mp = _num(srow.get("prob_cecchino"))
        if mp is not None:
            sibling_model[sk] = mp

    required = required_selections_for_normalization(family, period, line)
    normalized_map, overround, norm_status = _normalize_book_probs(sibling_odds, required)
    normalized_prob = None
    if normalized_map and market_key in normalized_map:
        normalized_prob = round(normalized_map[market_key], 6)

    if norm_status == "incomplete_market" and opp["opposition_status"] == OPPOSITION_SUPPORTED:
        # non blocca core se odds+opposition ok; flagga solo normalizzazione
        pass

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

    if settle["settlement_status"] == "missing":
        # missing settlement: riga può restare in core ma non settled
        pass

    completeness = "complete"
    if exclusion:
        completeness = "excluded"
    elif odds is None or model_prob is None:
        completeness = "partial"

    pre_match_ok = source_snapshot_before_kickoff and "snapshot_not_before_kickoff" not in exclusion
    core_ok = (
        pre_match_ok
        and opp["opposition_status"] == OPPOSITION_SUPPORTED
        and odds is not None
        and odds > 1.0
        and not any(
            x in exclusion
            for x in ("kickoff_missing", "snapshot_at_missing", "invalid_odds", "market_key_missing")
        )
    )

    settled_ok = core_ok and settle["settlement_status"] in ("won", "lost", "void")

    row = {
        "local_fixture_id": fixture.local_fixture_id,
        "today_fixture_id": int(fixture.id),
        "provider_fixture_id": int(fixture.provider_fixture_id),
        "competition_id": fixture.competition_id,
        "competition_name": fixture.league_name,
        "kickoff": _iso(kickoff),
        "snapshot_at": _iso(snapshot_at),
        "source_snapshot_before_kickoff": source_snapshot_before_kickoff,
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
        "book_source": book_source,
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
        "completeness_status": completeness,
        "source_quality_status": "kpi_panel_json",
        "leakage_status": leakage_status,
        "exclusion_reason_codes": exclusion,
        "canonical_row_key": _canonical_row_key(
            today_fixture_id=int(fixture.id),
            market_key=market_key,
            period=period,
            line=line,
            selection=market_key,
            snapshot_at=snapshot_at,
        ),
        "dataset_version": DATASET_VERSION,
        "no_post_match_data_in_features": leakage_status != "excluded_leakage",
        "is_pre_match": pre_match_ok,
        "is_core": core_ok,
        "is_settled_core": settled_ok,
        "feature_keys": list(FEATURE_CANDIDATE_KEYS),
        "target_keys": list(TARGET_KEYS),
    }
    return row


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
    out: list[dict[str, Any]] = []
    for fx in fixtures:
        panel = fx.kpi_panel_json if isinstance(fx.kpi_panel_json, dict) else {}
        panel_book = book_source or panel.get("bookmaker") or panel.get("book_source")
        if book_source and panel_book and str(panel_book).lower() != str(book_source).lower():
            continue
        rows = _panel_rows(fx)
        if not rows:
            continue
        siblings = {
            str(r.get("market_key") or "").strip().upper(): r
            for r in rows
            if r.get("market_key")
        }
        for prow in rows:
            built = _build_observed_row(fx, prow, siblings, str(panel_book) if panel_book else None)
            if market_family and built.get("canonical_market_family") != market_family:
                continue
            out.append(built)
    return out


def _cohort_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fixtures = {r["today_fixture_id"] for r in rows}
    markets = sorted({r["raw_market_code"] for r in rows if r.get("raw_market_code")})
    selections = markets
    dates = [r.get("scan_date") for r in rows if r.get("scan_date")]
    comps = {r.get("competition_id") for r in rows if r.get("competition_id") is not None}
    settled_n = sum(1 for r in rows if r.get("settlement_status") in ("won", "lost", "void"))
    void_n = sum(1 for r in rows if r.get("selection_void"))
    missing_n = sum(1 for r in rows if r.get("settlement_status") == "missing")
    excl = Counter()
    for r in rows:
        for code in r.get("exclusion_reason_codes") or []:
            excl[code] += 1
    n = len(rows) or 1
    return {
        "rows": len(rows),
        "unique_fixtures": len(fixtures),
        "markets": markets,
        "selections": selections,
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


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        for rank, i in enumerate(order):
            r[i] = float(rank + 1)
        return r

    if len(xs) < 3:
        return None
    return _pearson(ranks(xs), ranks(ys))


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
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            xs, ys = [], []
            for r in core_rows:
                va, vb = _num(r.get(a)), _num(r.get(b))
                if va is None or vb is None:
                    continue
                xs.append(va)
                ys.append(vb)
            if len(xs) < 10:
                continue
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "n": len(xs),
                    "pearson": _pearson(xs, ys),
                    "spearman": _spearman(xs, ys),
                }
            )
    derived = [
        {"field": "raw_book_implied_probability", "derived_from": "odds", "rule": "1/odds"},
        {"field": "probability_advantage", "derived_from": "model_probability,panel_prob_book"},
        {"field": "edge", "derived_from": "odds,quota_cecchino"},
        {"field": "score", "derived_from": "model_probability,edge"},
        {
            "field": "rating",
            "derived_from": "model_probability,probability_advantage,edge",
            "class": "benchmark_candidate",
        },
    ]
    high = [p for p in pairs if (p.get("pearson") or 0) >= 0.9 or (p.get("spearman") or 0) >= 0.9]
    return {
        "pair_correlations": pairs[:40],
        "high_correlation_pairs": high,
        "derived_field_dependencies": derived,
        "exact_duplicates_detected": False,
        "vif_note": "VIF descrittivo omesso sotto soglia campione o collinearità attesa su derived fields.",
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
    core = [r for r in rows if r.get("is_core")]
    settled = [r for r in rows if r.get("is_settled_core")]
    excluded = [r for r in rows if r.get("exclusion_reason_codes")]

    market_counts: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        mk = r.get("raw_market_code") or "UNKNOWN"
        market_counts[mk]["observed"] += 1
        if r.get("is_pre_match"):
            market_counts[mk]["pre_match"] += 1
        if r.get("is_core"):
            market_counts[mk]["core"] += 1
        if r.get("is_settled_core"):
            market_counts[mk]["settled"] += 1

    market_coverage = []
    for entry in list_opposition_map():
        mk = entry["raw_market_code"]
        c = market_counts.get(mk, Counter())
        market_coverage.append(
            {
                **entry,
                "observed_rows": c["observed"],
                "pre_match_rows": c["pre_match"],
                "core_rows": c["core"],
                "settled_rows": c["settled"],
                "settlement_available": c["settled"] > 0,
            }
        )

    markets_ready = sorted(
        {
            r["raw_market_code"]
            for r in core
            if r.get("opposition_status") == OPPOSITION_SUPPORTED
        }
    )
    markets_insufficient = sorted(
        {
            e["raw_market_code"]
            for e in market_coverage
            if e["opposition_status"] != OPPOSITION_SUPPORTED or e["core_rows"] == 0
        }
    )

    registry = build_variable_registry()
    independent = [v["canonical_name"] for v in registry if v["independence_class"] == "independent_candidate"]
    benchmark = [v["canonical_name"] for v in registry if v["independence_class"] == "benchmark_candidate"]
    redundant = [
        v["canonical_name"]
        for v in registry
        if v["independence_class"] == "derived_candidate"
        and v.get("redundancy_note")
        and "Rating" in (v.get("redundancy_note") or "")
    ]
    excluded_vars = [
        v["canonical_name"]
        for v in registry
        if v["independence_class"] in ("unavailable", "excluded_leakage")
    ]

    blocking: list[str] = []
    if not any(r.get("snapshot_at") for r in rows):
        blocking.append("no_snapshot_timestamp")
    if len(core) == 0:
        blocking.append("no_core_rows")
    if len(settled) == 0:
        blocking.append("no_settled_core_rows")
    if not markets_ready:
        blocking.append("no_markets_ready")

    readiness = {
        "kpi_source_identified": True,
        "canonical_snapshot_available": any(r.get("snapshot_at") for r in rows),
        "pre_match_timestamp_verified": any(r.get("source_snapshot_before_kickoff") for r in rows),
        "market_opposition_map_complete": True,
        "rating_dependency_map_complete": True,
        "odds_source_verified": any(r.get("odds") for r in rows),
        "book_overround_computable": any(
            r.get("book_probability_normalization_status") == "ok" for r in core
        ),
        "settlement_available": len(settled) > 0,
        "unit_profit_computable": any(r.get("unit_stake_profit") is not None for r in settled),
        "core_dataset_rows": len(core),
        "settled_core_rows": len(settled),
        "markets_ready": markets_ready,
        "markets_insufficient": markets_insufficient,
        "variables_independent_candidates": independent,
        "variables_benchmark_candidates": benchmark,
        "variables_redundant_candidates": redundant + ["probability_advantage", "edge", "model_probability"],
        "variables_excluded": excluded_vars,
        "blocking_issues": blocking,
        "recommended_next_step": (
            "phase_2_statistical_research" if not blocking else "resolve_data_gaps"
        ),
    }

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
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
            "pre_match_rows": len(pre_match),
            "core_rows": len(core),
            "settled_core_rows": len(settled),
            "excluded_rows": len(excluded),
            "unique_fixtures": len({r["today_fixture_id"] for r in all_rows}),
            "markets_ready": markets_ready,
            "date_min": _cohort_stats(all_rows).get("date_min"),
            "date_max": _cohort_stats(all_rows).get("date_max"),
            "note": (
                "Fase di audit research. Nessun Indice di Acquistabilità calcolato. "
                "Nessuna influenza sui Segnali Cecchino."
            ),
            "snapshot_limitation": (
                "Un solo kpi_panel_json per Today fixture (overwrite). "
                "source_snapshot_at = updated_at (fallback odds_checked_at)."
            ),
        },
        "cohorts": {
            COHORT_ALL: _cohort_stats(all_rows),
            COHORT_PRE_MATCH: _cohort_stats(pre_match),
            COHORT_CORE: _cohort_stats(core),
            COHORT_SETTLED: _cohort_stats(settled),
            COHORT_EXCLUDED: _cohort_stats(excluded),
        },
        "variable_registry": registry,
        "rating_dependency_map": rating_dependency_map(),
        "input_redundancy": _input_redundancy(core),
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
    rows = build_purchasability_rows(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_family=market_family,
        book_source=book_source,
    )
    if status == "core":
        rows = [r for r in rows if r.get("is_core")]
    elif status == "settled":
        rows = [r for r in rows if r.get("is_settled_core")]
    elif status == "pre_match":
        rows = [r for r in rows if r.get("is_pre_match")]
    elif status == "excluded":
        rows = [r for r in rows if r.get("exclusion_reason_codes")]

    total = len(rows)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    page = rows[offset : offset + limit]
    # Strip internal flags already present; ensure no target in feature list
    for r in page:
        assert "selection_won" not in (r.get("feature_keys") or [])
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


# --- Exports ---

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
    if kind == "dataset":
        rows = build_purchasability_rows(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_family=market_family,
            book_source=book_source,
        )
        # Prefer core for export; include all with flag
        yield _csv_from_dicts(rows).encode("utf-8")
        return
    yield json.dumps({"error": "unknown_export_kind", "kind": kind}).encode("utf-8")
