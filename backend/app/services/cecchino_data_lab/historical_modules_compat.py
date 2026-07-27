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


def _wdl_rates(wdl: dict[str, int] | None, sample: int) -> dict[str, float | None]:
    if not sample or not isinstance(wdl, dict):
        return {"win_rate": None, "draw_rate": None, "loss_rate": None}
    return {
        "win_rate": round(int(wdl.get("wins") or 0) / sample, 4),
        "draw_rate": round(int(wdl.get("draws") or 0) / sample, 4),
        "loss_rate": round(int(wdl.get("losses") or 0) / sample, 4),
    }


def _goal_totals_dict(totals: Any) -> dict[str, Any] | None:
    if totals is None:
        return None
    if hasattr(totals, "to_dict"):
        return totals.to_dict()
    if isinstance(totals, dict):
        return totals
    return None


def _slice_raw(slice_obj: Any) -> dict[str, Any] | None:
    if slice_obj is None:
        return None
    home = _goal_totals_dict(getattr(slice_obj, "home_totals", None))
    away = _goal_totals_dict(getattr(slice_obj, "away_totals", None))
    if home is None and away is None:
        return None
    return {
        "name": getattr(slice_obj, "name", None),
        "label": getattr(slice_obj, "label", None),
        "home_totals": home,
        "away_totals": away,
        "sample_home": getattr(slice_obj, "sample_home", None),
        "sample_away": getattr(slice_obj, "sample_away", None),
        "target_sample": getattr(slice_obj, "target_sample", None),
        "min_sample": getattr(slice_obj, "min_sample", None),
    }


def _compute_goal_pace(totals: dict[str, Any] | None) -> dict[str, float | None]:
    if not totals:
        return {"gf_per_match": None, "ga_per_match": None, "tg_per_match": None}
    sample = int(totals.get("sample") or 0)
    if sample <= 0:
        return {"gf_per_match": None, "ga_per_match": None, "tg_per_match": None}
    return {
        "gf_per_match": round(int(totals.get("goals_for") or 0) / sample, 4),
        "ga_per_match": round(int(totals.get("goals_against") or 0) / sample, 4),
        "tg_per_match": round(int(totals.get("total_goals") or 0) / sample, 4),
    }


def build_goal_intensity_compatibility(
    *,
    input_snapshot: dict[str, Any],
    contexts: Any | None = None,
    has_xg: bool = False,
) -> dict[str, Any]:
    """Feature raw pre-match ricostruibili — punteggio v5 NON eseguito."""
    context_keys = [
        "home_context",
        "away_context",
        "home_total",
        "away_total",
        "home_recent_context_5",
        "away_recent_context_5",
        "home_recent_total_6",
        "away_recent_total_6",
    ]
    wdl_features: dict[str, Any] = {}
    samples: dict[str, int] = {}
    missing: list[str] = []
    for key in context_keys:
        block = input_snapshot.get(key) if isinstance(input_snapshot, dict) else None
        if not isinstance(block, dict):
            missing.append(key)
            continue
        sample = int(block.get("sample") or 0)
        samples[key] = sample
        if not sample:
            missing.append(key)
        wdl = block.get("wdl") if isinstance(block.get("wdl"), dict) else {}
        wdl_features[key] = {
            "wdl": wdl,
            "sample": sample,
            "min_required": block.get("min_required"),
            **_wdl_rates(wdl, sample),
        }

    goal_slices_raw: dict[str, Any] = {}
    goal_contexts_raw: dict[str, Any] = {}
    pace: dict[str, Any] = {}
    volatility: dict[str, Any] = {}

    if contexts is not None:
        gs = getattr(contexts, "goal_slices", None)
        if gs is not None and hasattr(gs, "to_dict"):
            goal_slices_raw = gs.to_dict()
            for name, totals in goal_slices_raw.items():
                if isinstance(totals, dict) and "sample" in totals:
                    pace[name] = _compute_goal_pace(totals)
                    sample = int(totals.get("sample") or 0)
                    if sample > 0:
                        # Volatilità grezza: share over/under come proxy ritmo
                        volatility[name] = {
                            "over_2_5_rate": round(
                                int(totals.get("over_2_5_hits") or 0) / sample, 4
                            ),
                            "under_2_5_rate": round(
                                int(totals.get("under_2_5_hits") or 0) / sample, 4
                            ),
                            "over_1_5_rate": round(
                                int(totals.get("over_1_5_hits") or 0) / sample, 4
                            ),
                        }
        gc = getattr(contexts, "goal_contexts", None)
        if gc is not None:
            for attr in (
                "totals",
                "home_away",
                "last6_totals",
                "last5_home_away",
                "ht_totals",
                "ht_home_away",
                "ht_last6_totals",
                "ht_last5_home_away",
            ):
                raw = _slice_raw(getattr(gc, attr, None))
                if raw:
                    goal_contexts_raw[attr] = raw
                    if raw.get("home_totals"):
                        pace[f"{attr}_home"] = _compute_goal_pace(raw["home_totals"])
                    if raw.get("away_totals"):
                        pace[f"{attr}_away"] = _compute_goal_pace(raw["away_totals"])

    has_any_sample = any(s > 0 for s in samples.values())
    has_goal_totals = bool(goal_slices_raw) or bool(goal_contexts_raw)
    raw_features_available = has_any_sample or has_goal_totals

    if missing and len(missing) == len(context_keys):
        status = "input_unavailable"
    elif missing:
        status = "input_partial"
    else:
        status = "input_compatible"

    return {
        "status": status,
        "execution_status": "not_executed_production_bundle",
        "raw_features_available": raw_features_available,
        "v5_score_not_executed": True,
        "v5_score": None,
        "raw_features": {
            "wdl_contexts": wdl_features,
            "goal_slices": goal_slices_raw,
            "goal_contexts": goal_contexts_raw,
            "pace": pace,
            "volatility_proxy": volatility,
            "prior_count": (
                input_snapshot.get("prior_count") if isinstance(input_snapshot, dict) else None
            ),
            "leakage_ok": (
                input_snapshot.get("leakage_ok") if isinstance(input_snapshot, dict) else None
            ),
            "sample_meta": (
                input_snapshot.get("sample_meta") if isinstance(input_snapshot, dict) else None
            ),
            "note": (
                "Feature ricostruite solo da prior pre-match. "
                "Nessun xG inventato, nessun risultato target, nessun bundle prospettico produttivo."
            ),
        },
        "feature_availability": {
            "pre_match_reconstructible": status != "input_unavailable",
            "sample_size": samples,
            "missing_fields": missing,
            "xg_status": "available" if has_xg else "missing",
            "xg_imputed_to_zero": False,
            "leakage_absent": True,
            "contract_compatible": status == "input_compatible",
            "raw_features_available": raw_features_available,
            "v5_score_not_executed": True,
        },
        "blockers_for_future_scientific_replay": (
            ["missing_xg"] if not has_xg else []
        )
        + (["partial_samples"] if missing else [])
        + ["v5_score_not_executed_on_historical_lab"],
    }


def build_purchasability_compatibility(
    *,
    kpi_panel: dict[str, Any],
    quote_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Input per-mercato disponibili — punteggio finale operativo NON eseguito."""
    rows = kpi_panel.get("rows") or []
    quotes = quote_bundle.get("quotes") or {}
    market_inputs: list[dict[str, Any]] = []
    real_n = 0
    derived_n = 0
    has_rating = False
    has_edge = False
    has_vantaggio = False

    for r in rows:
        if not isinstance(r, dict):
            continue
        mk = r.get("market_key")
        qmeta = quotes.get(mk) or {} if mk else {}
        is_real = bool(qmeta.get("is_real_book_quote") or r.get("book_quote_class") == "real_bet365")
        is_derived = bool(qmeta.get("is_derived") or r.get("book_quote_class") == "derived")
        if is_real:
            real_n += 1
        elif is_derived:
            derived_n += 1
        rating = r.get("rating")
        edge = r.get("edge_pct")
        vantaggio = r.get("vantaggio_prob")
        if rating is not None:
            has_rating = True
        if edge is not None:
            has_edge = True
        if vantaggio is not None:
            has_vantaggio = True
        market_inputs.append(
            {
                "market_key": mk,
                "market_label": r.get("market_label") or r.get("label"),
                "rating": rating,
                "edge_pct": edge,
                "vantaggio_prob": vantaggio,
                "quota_cecchino": r.get("quota_cecchino"),
                "quota_book": qmeta.get("value") if qmeta.get("value") is not None else r.get("quota_book"),
                "is_real_book_quote": is_real,
                "is_derived_quote": is_derived,
                "quote_source_type": qmeta.get("source_type") or r.get("quote_source_type"),
                "competitor_comparison": {
                    "available": False,
                    "note": "Confronto concorrenti non applicato nel replay storico Lab",
                },
            }
        )

    inputs_available = bool(market_inputs) and (has_rating or has_edge or real_n > 0 or derived_n > 0)

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
        "inputs_available": inputs_available,
        "final_score_not_executed": True,
        "final_score": None,
        "betfair_operational_profile_applied": False,
        "market_inputs": market_inputs,
        "inputs": {
            "rating_available": has_rating,
            "edge_available": has_edge,
            "vantaggio_prob_available": has_vantaggio,
            "real_quote_rows": real_n,
            "derived_quote_rows": derived_n,
            "market_opposition_availability": False,
            "inputs_available": inputs_available,
            "final_score_not_executed": True,
            "note": "Normalizzazione operativa Betfair non applicata ai dati Bet365 storici",
        },
        "blockers_for_full_calculation": [
            "operational_betfair_normalization_profile_not_applicable",
            "final_score_not_executed_on_historical_lab",
        ],
        "quote_counts": quote_bundle.get("counts"),
    }
