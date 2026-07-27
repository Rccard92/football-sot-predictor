"""Acquistabilità storica Bet365 — profilo progressivo Lab (no Betfair/Today).

Invoca calculate_purchasability_v2_item con profilo costruito solo da
eligible_core precedenti dello stesso run. Osservazionale: non blocca
eleggibilità né settlement.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_purchasability_fair_book import (
    resolve_fair_book_for_panel_rows,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_model_context_probability_map,
)
from app.services.cecchino.cecchino_purchasability_v2_candidate import (
    calculate_purchasability_v2_item,
)
from app.services.cecchino.cecchino_purchasability_v2_normalization import (
    MIN_SIDE_SAMPLES,
    _ingest_observations,
    _new_accumulator,
    _safe_float,
    collect_fixture_component_observations,
    finalize_profile_from_accumulator,
)
from app.services.cecchino.cecchino_purchasability_v2_opposition import (
    is_v2_supported_market,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_purchasability_compatibility,
)

HIST_NORM_PROFILE_VERSION = "cecchino_lab_purchasability_hist_norm_v1"
FORMULA_VERSION = "cecchino_lab_purchasability_historical_v1"
PARITY_STATUS = "historical_bet365_v2"
STATUS_INSUFFICIENT = "insufficient_historical_normalization_sample"


def _quote_quality(row: dict[str, Any], quote_meta: dict[str, Any] | None) -> str:
    q = quote_meta or {}
    if q.get("is_real_book_quote") or row.get("book_quote_class") == "real_bet365":
        return "real"
    if q.get("is_derived") or row.get("book_quote_class") == "derived":
        return "derived"
    if q.get("value") is not None or row.get("quota_book") is not None:
        if row.get("is_derived_quote"):
            return "derived"
        if row.get("is_real_book_quote"):
            return "real"
    return "unavailable"


def _model_probs_from_panel(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    model_by = build_model_context_probability_map(rows)
    out: dict[str, float | None] = {}
    for mk, meta in (model_by or {}).items():
        if isinstance(meta, dict):
            out[str(mk)] = _safe_float(meta.get("model_context_probability"))
        else:
            out[str(mk)] = _safe_float(meta)
    return out


def build_progressive_normalization_profile(
    prior_kpi_panels: list[dict[str, Any]],
    *,
    cutoff: str | None = None,
) -> dict[str, Any]:
    """Profilo da sole partite eligible precedenti (no target, no future, no Betfair)."""
    acc = _new_accumulator()
    fixtures_seen = 0
    for panel in prior_kpi_panels:
        if not isinstance(panel, dict):
            continue
        rows = panel.get("rows") if isinstance(panel.get("rows"), list) else []
        if not rows:
            continue
        try:
            fair_by = resolve_fair_book_for_panel_rows(rows)
        except Exception:
            fair_by = {}
        model_probs = _model_probs_from_panel(rows)
        obs = collect_fixture_component_observations(
            panel,
            fair_book_by_market=fair_by if isinstance(fair_by, dict) else {},
            model_context_by_market=model_probs,
        )
        if obs:
            _ingest_observations(acc, obs)
            fixtures_seen += 1

    profile = finalize_profile_from_accumulator(
        acc,
        version=HIST_NORM_PROFILE_VERSION,
        cutoff=str(cutoff or "progressive"),
        fixtures_seen=fixtures_seen,
    )
    # Sovrascrivi metadati Lab (finalize marca Today/excludes_lab)
    profile["source"] = "cecchino_lab_eligible_core_progressive"
    profile["excludes_cecchino_lab"] = False
    profile["excludes_betfair_operational_profile"] = True
    profile["excludes_post_match"] = True
    profile["betfair_operational_profile_applied"] = False
    # Ricalcola hash con source Lab
    from app.services.cecchino.cecchino_purchasability_v2_normalization import (
        compute_profile_hash,
    )

    profile["hash"] = compute_profile_hash(profile)
    summary = dict(profile.get("summary") or {})
    summary["hash"] = profile["hash"]
    summary["source"] = profile["source"]
    profile["summary"] = summary
    return profile


def build_historical_purchasability(
    *,
    kpi_panel: dict[str, Any],
    quote_bundle: dict[str, Any],
    prior_kpi_panels: list[dict[str, Any]] | None = None,
    cutoff: str | None = None,
) -> dict[str, Any]:
    """Calcola indice storico per mercato supportato con profilo progressivo."""
    compat = build_purchasability_compatibility(
        kpi_panel=kpi_panel, quote_bundle=quote_bundle
    )
    prior_panels = list(prior_kpi_panels or [])
    profile = build_progressive_normalization_profile(prior_panels, cutoff=cutoff)
    fixtures_seen = int(profile.get("fixtures_seen") or 0)
    sample_ok = fixtures_seen >= MIN_SIDE_SAMPLES

    rows = [r for r in (kpi_panel.get("rows") or []) if isinstance(r, dict)]
    by_mk = {str(r.get("market_key")): r for r in rows if r.get("market_key")}
    quotes = quote_bundle.get("quotes") or {}

    try:
        fair_by = resolve_fair_book_for_panel_rows(rows)
    except Exception:
        fair_by = {}
    model_probs = _model_probs_from_panel(rows)

    markets: list[dict[str, Any]] = []
    for mk, row in by_mk.items():
        qmeta = quotes.get(mk) if isinstance(quotes.get(mk), dict) else {}
        qq = _quote_quality(row, qmeta)

        if not sample_ok:
            markets.append(
                {
                    "market_key": mk,
                    "status": STATUS_INSUFFICIENT,
                    "score": None,
                    "raw_score": None,
                    "class": None,
                    "phase_1": None,
                    "phase_2": None,
                    "positive_value_gate": None,
                    "quote_quality": qq,
                    "normalization_profile_version": HIST_NORM_PROFILE_VERSION,
                    "normalization_profile_hash": profile.get("hash"),
                    "normalization_sample_size": fixtures_seen,
                    "reason_codes": [STATUS_INSUFFICIENT],
                    "formula_version": FORMULA_VERSION,
                    "parity_status": PARITY_STATUS,
                    "rating": row.get("rating"),
                    "edge_pct": row.get("edge_pct"),
                    "vantaggio_prob": row.get("vantaggio_prob"),
                }
            )
            continue

        if not is_v2_supported_market(mk):
            markets.append(
                {
                    "market_key": mk,
                    "status": "unsupported_market",
                    "score": None,
                    "raw_score": None,
                    "class": None,
                    "phase_1": None,
                    "phase_2": None,
                    "positive_value_gate": None,
                    "quote_quality": qq,
                    "normalization_profile_version": HIST_NORM_PROFILE_VERSION,
                    "normalization_profile_hash": profile.get("hash"),
                    "normalization_sample_size": fixtures_seen,
                    "reason_codes": ["purchasability_v2_market_unsupported"],
                    "formula_version": FORMULA_VERSION,
                    "parity_status": PARITY_STATUS,
                    "rating": row.get("rating"),
                    "edge_pct": row.get("edge_pct"),
                    "vantaggio_prob": row.get("vantaggio_prob"),
                }
            )
            continue

        item = calculate_purchasability_v2_item(
            mk,
            row,
            by_mk,
            profile=profile,
            fair_by=fair_by if isinstance(fair_by, dict) else {},
            model_probs=model_probs,
        )
        markets.append(
            {
                "market_key": mk,
                "status": item.get("status") or "ok",
                "score": item.get("score"),
                "raw_score": item.get("raw_score"),
                "class": item.get("class"),
                "phase_1": item.get("phase_1_value"),
                "phase_2": item.get("phase_2_quality"),
                "positive_value_gate": item.get("positive_value_gate"),
                "quote_quality": qq,
                "normalization_profile_version": HIST_NORM_PROFILE_VERSION,
                "normalization_profile_hash": profile.get("hash"),
                "normalization_sample_size": fixtures_seen,
                "reason_codes": item.get("reason_codes") or [],
                "formula_version": FORMULA_VERSION,
                "parity_status": PARITY_STATUS,
                "rating": row.get("rating"),
                "edge_pct": row.get("edge_pct"),
                "vantaggio_prob": row.get("vantaggio_prob"),
                "components": {
                    "phase_1": item.get("phase_1_value"),
                    "phase_2": item.get("phase_2_quality"),
                },
            }
        )

    execution_status = (
        "computed" if sample_ok else STATUS_INSUFFICIENT
    )
    return {
        **compat,
        "execution_status": execution_status,
        "historical_purchasability_status": execution_status,
        "parity_status": PARITY_STATUS,
        "formula_version": FORMULA_VERSION,
        "final_score_not_executed": False,
        "final_score": None,  # per-mercato in markets[]
        "betfair_operational_profile_applied": False,
        "markets": markets,
        "normalization_profile": {
            "version": HIST_NORM_PROFILE_VERSION,
            "hash": profile.get("hash"),
            "sample_size": fixtures_seen,
            "cutoff": profile.get("cutoff"),
            "min_side_samples": MIN_SIDE_SAMPLES,
            "source": profile.get("source"),
        },
        "anti_leakage": {
            "prior_eligible_core_only": True,
            "target_excluded": True,
            "future_excluded": True,
            "no_real_results_in_profile": True,
            "betfair_live_profile_forbidden": True,
        },
        "observational_only": True,
        "does_not_affect_eligibility": True,
        "does_not_affect_settlement": True,
        "blockers_for_full_calculation": [
            b
            for b in (compat.get("blockers_for_full_calculation") or [])
            if b
            not in (
                "final_score_not_executed_on_historical_lab",
                "operational_betfair_normalization_profile_not_applicable",
            )
        ]
        + (["operational_betfair_not_used_by_design"] if sample_ok else [STATUS_INSUFFICIENT]),
    }
