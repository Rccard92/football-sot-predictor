"""Modelli pesi Segnali A–F per replay storico Cecchino Lab.

Usa esclusivamente costanti/funzioni canoniche. F ≡ modello corrente.
Non scrive su cecchino_signal_activations.
"""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import (
    CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
    CECCHINO_WEIGHT_MODEL_KEYS,
    STATUS_AVAILABLE,
    model_meta_for_key,
    model_weights_json,
    model_weights_to_picchetto_map,
)
from app.services.cecchino.cecchino_engine import (
    compute_final_odds,
    picchetti_blocks_from_output_json,
)
from app.services.cecchino.cecchino_signals_matrix import build_signals_matrix
from app.services.cecchino_data_lab.historical_modules_compat import (
    enrich_signals_with_quote_classes,
    rebuild_signals_with_under,
)
from app.services.cecchino_data_lab.historical_signal_extraction import (
    iter_active_signal_cells,
)
from app.services.cecchino.cecchino_signal_target_mapping import (
    map_cecchino_signal_to_target,
)
from app.services.cecchino.cecchino_signal_evaluation import evaluate_market_selection
from app.models.cecchino_signal_activation import EVAL_LOST, EVAL_WON


def _sample_home_away_split(cecchino_output: dict[str, Any], contexts: Any | None) -> int:
    if contexts is not None:
        from app.services.cecchino.cecchino_constants import PICCHETTO_KEY_HOME_AWAY

        meta = (getattr(contexts, "sample_meta", None) or {}).get(PICCHETTO_KEY_HOME_AWAY) or {}
        return int(meta.get("home_sample_count") or 0) + int(meta.get("away_sample_count") or 0)
    snap = (cecchino_output.get("input_snapshot") or {}) if isinstance(cecchino_output, dict) else {}
    # fallback: somma sample dai picchetti
    pic = cecchino_output.get("picchetti") or {}
    ha = pic.get("home_away") or pic.get("HOME_AWAY") or {}
    return int(ha.get("home_sample_count") or 0) + int(ha.get("away_sample_count") or 0)


def _final_to_dict(final: Any) -> dict[str, Any]:
    if isinstance(final, dict):
        return final
    return {
        "status": getattr(final, "status", None),
        "quota_1": getattr(final, "quota_1", None),
        "quota_x": getattr(final, "quota_x", None),
        "quota_2": getattr(final, "quota_2", None),
        "prob_1": getattr(final, "prob_1", None),
        "prob_x": getattr(final, "prob_x", None),
        "prob_2": getattr(final, "prob_2", None),
    }


def _settle_active_signals(
    *,
    matrix: dict[str, Any],
    match: Any,
    quote_bundle: dict[str, Any],
    final: dict[str, Any],
) -> list[dict[str, Any]]:
    result = {
        "fulltime": {
            "home": getattr(match, "ft_home_goals", None),
            "away": getattr(match, "ft_away_goals", None),
        },
        "halftime": {
            "home": getattr(match, "ht_home_goals", None),
            "away": getattr(match, "ht_away_goals", None),
        },
    }
    quotes = quote_bundle.get("quotes") or {}
    settlements: list[dict[str, Any]] = []
    for cell in iter_active_signal_cells(matrix):
        target = map_cecchino_signal_to_target(cell["signal_group"], cell["source_column"])
        market_key = target.get("target_market_key")
        if not market_key:
            continue
        qmeta = quotes.get(str(market_key)) or {}
        eval_res = evaluate_market_selection(str(market_key), result)
        status = eval_res.get("evaluation_status")
        won: bool | None
        if status == EVAL_WON:
            won = True
        elif status == EVAL_LOST:
            won = False
        else:
            won = None

        is_real = bool(qmeta.get("is_real_book_quote"))
        is_derived = bool(qmeta.get("is_derived"))
        quota_book = qmeta.get("value")
        real_profit = None
        synth_profit = None
        if won is not None and quota_book is not None:
            try:
                qb = float(quota_book)
            except (TypeError, ValueError):
                qb = None
            if qb is not None and qb > 1:
                pnl = (qb - 1.0) if won else -1.0
                if is_real:
                    real_profit = round(pnl, 4)
                elif is_derived:
                    synth_profit = round(pnl, 4)

        # quota/prob cecchino dal final 1X2 o goal
        quota_cecchino = None
        prob_cecchino = None
        mk = str(market_key)
        if mk == "HOME":
            quota_cecchino, prob_cecchino = final.get("quota_1"), final.get("prob_1")
        elif mk == "DRAW":
            quota_cecchino, prob_cecchino = final.get("quota_x"), final.get("prob_x")
        elif mk == "AWAY":
            quota_cecchino, prob_cecchino = final.get("quota_2"), final.get("prob_2")

        settlements.append(
            {
                "signal_family": cell.get("signal_family"),
                "source_column": cell.get("source_column"),
                "row_key": cell.get("row_key"),
                "target_market": mk,
                "quota_cecchino": quota_cecchino,
                "probabilita_cecchino": prob_cecchino,
                "quota_bet365": quota_book,
                "quote_quality": (
                    "real" if is_real else ("derived" if is_derived else "unavailable")
                ),
                "won": won,
                "real_profit_1u": real_profit,
                "synthetic_profit_1u": synth_profit,
            }
        )
    return settlements


def build_historical_signal_models(
    *,
    cecchino_output: dict[str, Any],
    quote_bundle: dict[str, Any],
    under_2_5_cecchino_odd: float | None = None,
    contexts: Any | None = None,
    match: Any | None = None,
    settle: bool = False,
) -> dict[str, Any]:
    """Costruisce signals_json con default F + models A–F."""
    picchetti = picchetti_blocks_from_output_json(cecchino_output)
    sample_split = _sample_home_away_split(cecchino_output, contexts)
    models: dict[str, Any] = {}

    for key in CECCHINO_WEIGHT_MODEL_KEYS:
        weights_map = model_weights_to_picchetto_map(key)
        final_obj = compute_final_odds(picchetti, weights=weights_map)
        final = _final_to_dict(final_obj)
        status = final.get("status") or getattr(final_obj, "status", None)
        if status == STATUS_AVAILABLE:
            if under_2_5_cecchino_odd is not None:
                matrix = rebuild_signals_with_under(
                    final=final,
                    sample_home_away_split=sample_split,
                    under_2_5_cecchino_odd=under_2_5_cecchino_odd,
                )
            else:
                matrix = build_signals_matrix(
                    q1=final.get("quota_1"),
                    qx=final.get("quota_x"),
                    q2=final.get("quota_2"),
                    sample_home_away_split=sample_split,
                    prob_1=final.get("prob_1"),
                    prob_x=final.get("prob_x"),
                    prob_2=final.get("prob_2"),
                    under_2_5_cecchino_odd=None,
                )
            matrix = enrich_signals_with_quote_classes(matrix, quote_bundle)
        else:
            matrix = {"status": "unavailable", "rows": []}

        active = iter_active_signal_cells(matrix)
        settlements: list[dict[str, Any]] = []
        if settle and match is not None:
            settlements = _settle_active_signals(
                matrix=matrix,
                match=match,
                quote_bundle=quote_bundle,
                final=final,
            )

        meta = model_meta_for_key(key)
        models[key] = {
            "meta": meta,
            "weights": model_weights_json(key),
            "final": final,
            "matrix": matrix,
            "active_signals": active,
            "settlements": settlements,
        }

    default_key = CECCHINO_DEFAULT_WEIGHT_MODEL_KEY
    default_matrix = (models.get(default_key) or {}).get("matrix") or {}

    missing_models = [k for k in CECCHINO_WEIGHT_MODEL_KEYS if k not in models]
    unavailable = [
        k
        for k, block in models.items()
        if isinstance(block, dict)
        and (
            (_as_status((block.get("final") or {}).get("status")) != STATUS_AVAILABLE)
            or (_as_status((block.get("matrix") or {}).get("status")) == "unavailable")
        )
    ]
    if missing_models:
        observation_status = "unavailable"
    elif unavailable:
        observation_status = "partial"
    else:
        observation_status = "complete"

    return {
        "default_model_key": default_key,
        "default_matrix": default_matrix,
        "models": models,
        "observation_status": observation_status,
        "module_version": "cecchino_lab_signals_af_v1",
        "f_equals_current": default_key == CECCHINO_DEFAULT_WEIGHT_MODEL_KEY,
        "missing_fields": [f"models.{k}" for k in missing_models],
        "warnings": (
            [f"model_unavailable:{k}" for k in unavailable]
            + (["partial_models"] if unavailable else [])
        ),
        "sample_size": {
            k: len((block.get("active_signals") or []))
            for k, block in models.items()
            if isinstance(block, dict)
        },
        "inputs": {
            "picchetti_present": bool(picchetti),
            "quote_bundle_present": bool(quote_bundle),
            "under_2_5_cecchino_odd": under_2_5_cecchino_odd,
        },
        "does_not_affect_eligibility": True,
    }


def _as_status(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def resolve_signals_matrix(signals_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Accetta wrapper A–F o matrice flat legacy (Run #1)."""
    if not isinstance(signals_json, dict):
        return signals_json
    if "default_matrix" in signals_json and isinstance(signals_json.get("default_matrix"), dict):
        return signals_json["default_matrix"]
    if "models" in signals_json and isinstance(signals_json.get("models"), dict):
        f = signals_json["models"].get("F") or {}
        if isinstance(f.get("matrix"), dict):
            return f["matrix"]
    return signals_json
