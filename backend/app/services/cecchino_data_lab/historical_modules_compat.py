"""Compatibilità moduli (segnali, balance, intensità, acquistabilità) per replay Lab."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_balance_v5 import build_cecchino_balance_v5
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix


def enrich_signals_with_quote_classes(
    signals: dict[str, Any],
    quote_bundle: dict[str, Any],
) -> dict[str, Any]:
    quotes = quote_bundle.get("quotes") or {}
    out = dict(signals)
    out["quote_classification"] = {
        "mathematical_signal": True,
        "real_bet365_quote_markets": [
            k for k, v in quotes.items() if v.get("is_real_book_quote")
        ],
        "derived_quote_markets": [k for k, v in quotes.items() if v.get("is_derived")],
        "no_book_quote_markets": [k for k, v in quotes.items() if v.get("value") is None],
    }
    # Non classificare derivate come offerte reali Bet365
    out["derived_not_real_book"] = True
    return out


def rebuild_signals_with_under(
    *,
    final: dict[str, Any],
    sample_home_away_split: int,
    under_2_5_cecchino_odd: float | None,
) -> dict[str, Any]:
    return build_signals_matrix(
        q1=final.get("quota_1"),
        qx=final.get("quota_x"),
        q2=final.get("quota_2"),
        sample_home_away_split=sample_home_away_split,
        prob_1=final.get("prob_1"),
        prob_x=final.get("prob_x"),
        prob_2=final.get("prob_2"),
        under_2_5_cecchino_odd=under_2_5_cecchino_odd,
    )


def build_historical_balance_v5(
    *,
    cecchino_final: dict[str, Any],
    goal_markets: dict[str, Any] | None,
    kpi_panel: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    return build_cecchino_balance_v5(
        cecchino_final=cecchino_final,
        goal_markets=goal_markets,
        kpi_panel=kpi_panel,
        identity_consistency=identity,
    )


def build_goal_intensity_compatibility(
    *,
    input_snapshot: dict[str, Any],
    has_xg: bool = False,
) -> dict[str, Any]:
    samples = {
        k: (v or {}).get("sample", 0)
        for k, v in input_snapshot.items()
        if isinstance(v, dict) and "sample" in v
    }
    missing = [k for k, s in samples.items() if not s]
    if missing and len(missing) == len(samples):
        status = "input_unavailable"
    elif missing:
        status = "input_partial"
    else:
        status = "input_compatible"

    return {
        "status": status,
        "execution_status": "not_executed_production_bundle",
        "feature_availability": {
            "pre_match_reconstructible": status != "input_unavailable",
            "sample_size": samples,
            "missing_fields": missing,
            "xg_status": "available" if has_xg else "missing",
            "xg_imputed_to_zero": False,
            "leakage_absent": True,
            "contract_compatible": status == "input_compatible",
        },
        "blockers_for_future_scientific_replay": (
            ["missing_xg"] if not has_xg else []
        )
        + (["partial_samples"] if missing else []),
    }


def build_purchasability_compatibility(
    *,
    kpi_panel: dict[str, Any],
    quote_bundle: dict[str, Any],
) -> dict[str, Any]:
    rows = kpi_panel.get("rows") or []
    real_n = sum(1 for r in rows if r.get("book_quote_class") == "real_bet365")
    derived_n = sum(1 for r in rows if r.get("book_quote_class") == "derived")
    has_rating = any(r.get("rating") is not None for r in rows)
    has_edge = any(r.get("edge_pct") is not None for r in rows)
    has_vantaggio = any(r.get("vantaggio_prob") is not None for r in rows)

    if real_n > 0 and has_rating and has_edge:
        status = "input_compatible_real_quote"
    elif derived_n > 0 and has_rating:
        status = "input_compatible_derived_quote"
    elif has_rating or has_edge or has_vantaggio:
        status = "partial"
    else:
        status = "unavailable"

    return {
        "historical_purchasability_status": status,
        "execution_status": "not_executed_operational_profile",
        "inputs": {
            "rating_available": has_rating,
            "edge_available": has_edge,
            "vantaggio_prob_available": has_vantaggio,
            "real_quote_rows": real_n,
            "derived_quote_rows": derived_n,
            "market_opposition_availability": False,
            "note": "Normalizzazione operativa Betfair non applicata ai dati Bet365 storici",
        },
        "blockers_for_full_calculation": [
            "operational_betfair_normalization_profile_not_applicable",
        ],
        "quote_counts": quote_bundle.get("counts"),
    }
