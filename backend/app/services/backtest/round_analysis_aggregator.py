"""Aggregazione summary analisi giornata (Step I)."""

from __future__ import annotations

from typing import Any, Iterable

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR
from app.schemas.backtest_round_analysis import (
    MODEL_LABELS,
    RoundAnalysisDataQualitySummary,
    RoundAnalysisModelSummary,
)
from app.services.backtest.round_analysis_data_prep_service import RoundAnalysisPrepResult
from app.services.backtest.round_analysis_model_registry import ROUND_ANALYSIS_MODEL_REGISTRY
from app.services.backtest.player_layer_fixture_status import (
    merge_player_layer_into_data_quality_summary,
    summarize_player_layer_from_fixture_rows,
)
from app.services.backtest.round_analysis_mode_stats import advice_bucket
from app.services.backtest.round_analysis_preflight import (
    RoundHistoryPreflight,
    accordion_summary_from_models,
    model_block_is_error,
    model_block_is_no_prediction,
)


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _mean(values: Iterable[float]) -> float | None:
    items = [float(v) for v in values]
    if not items:
        return None
    return _round4(sum(items) / len(items))


def _hit_rate(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return _round4(100.0 * wins / total)


class RoundAnalysisAggregator:
    def build_data_quality_summary(
        self,
        *,
        prep: RoundAnalysisPrepResult,
        fixture_results: list[dict[str, Any]],
        history_preflight: RoundHistoryPreflight | None = None,
        model_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preflights = list(prep.fixture_preflights.values())
        total = len(preflights) or len(fixture_results)
        with_lineup = sum(1 for p in preflights if p.has_lineup)
        with_unavail = sum(1 for p in preflights if p.unavailable_count > 0)
        missing_map = sum(1 for p in preflights if not p.has_mapping)

        warnings = list(prep.prep_warnings)
        insufficient = bool(history_preflight and history_preflight.insufficient_history)
        if insufficient and history_preflight and history_preflight.reason:
            warnings.append(history_preflight.reason.lower())

        badge = "OK"
        if insufficient:
            badge = "Critico"
        elif missing_map > 0 or with_lineup < total:
            badge = "Avvisi"
        if total > 0 and not insufficient and (missing_map >= total * 0.5 or with_lineup == 0):
            badge = "Critico"

        details: dict[str, Any] = {
            "mapping_backfill": prep.mapping_backfill_summary,
            "unavailable_backfill": prep.unavailable_backfill_summary,
        }
        if history_preflight:
            details["preflight"] = history_preflight.to_dict()

        accordion = accordion_summary_from_models(
            model_summary,
            insufficient_history=insufficient,
        )

        pl_counts = summarize_player_layer_from_fixture_rows(fixture_results)
        summary = RoundAnalysisDataQualitySummary(
            badge=badge,  # type: ignore[arg-type]
            total_fixtures=total,
            fixtures_with_lineup=with_lineup,
            fixtures_with_unavailable=with_unavail,
            fixtures_missing_mapping=missing_map,
            fixtures_player_layer_ok=pl_counts["fixtures_player_layer_ok"],
            fixtures_player_layer_partial=pl_counts["fixtures_player_layer_partial"],
            fixtures_player_layer_missing=pl_counts["fixtures_player_layer_missing"],
            player_layer_sides_available=pl_counts["player_layer_sides_available"],
            player_layer_sides_total=pl_counts["player_layer_sides_total"],
            fixtures_split_ok=0,
            warnings=warnings,
            details=details,
        )
        out = summary.model_dump()
        if history_preflight and isinstance(out.get("details"), dict):
            pf = dict((out["details"] or {}).get("preflight") or {})
            pf["player_stats_available"] = pl_counts["fixtures_player_layer_ok"]
            out["details"]["preflight"] = pf
        out["data_quality_status"] = (
            history_preflight.data_quality_status if history_preflight else badge.lower()
        )
        out["accordion_summary"] = accordion
        if history_preflight:
            out["first_recommended_round"] = history_preflight.first_recommended_round
        return out

    def build_model_summary(
        self,
        *,
        models: list[str],
        fixture_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for model_key in models:
            out[model_key] = self._summarize_model(model_key, fixture_results).model_dump()
        return out

    def _summarize_model(
        self,
        model_key: str,
        fixture_results: list[dict[str, Any]],
    ) -> RoundAnalysisModelSummary:
        is_v30 = model_key == BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR
        agg_w = agg_l = caut_w = caut_l = advised = 0
        no_bet_count = borderline_count = 0
        pred_totals: list[float] = []
        actual_totals: list[float] = []
        abs_errors: list[float] = []
        errors_signed: list[float] = []
        predictions_available = 0
        no_prediction_count = 0
        fixtures_ok = fixtures_nd = fixtures_error = 0
        error_codes: list[str] = []
        model_engine_name: str | None = ROUND_ANALYSIS_MODEL_REGISTRY.get(model_key, {}).get("engine")
        total_fixture_rows = len([r for r in fixture_results if r.get("status") == "ok"])

        for row in fixture_results:
            if row.get("status") != "ok":
                continue
            block = (row.get("models_json") or {}).get(model_key)
            if not isinstance(block, dict):
                no_prediction_count += 1
                fixtures_nd += 1
                continue
            if block.get("model_engine_name"):
                model_engine_name = str(block["model_engine_name"])
            if model_block_is_error(block):
                fixtures_error += 1
                code = block.get("error_code")
                if code:
                    error_codes.append(str(code))
                continue
            if model_block_is_no_prediction(block):
                no_prediction_count += 1
                fixtures_nd += 1
                code = block.get("error_code") or block.get("reason")
                if code:
                    error_codes.append(str(code))
                continue

            fixtures_ok += 1
            predictions_available += 1
            pt = block.get("predicted_total_sot")
            at = row.get("actual_total_sot")
            if pt is not None:
                pred_totals.append(float(pt))
            if at is not None:
                actual_totals.append(float(at))
            if pt is not None and at is not None:
                err = float(pt) - float(at)
                errors_signed.append(err)
                abs_errors.append(abs(err))

            if str(block.get("status") or "ok") == "ok":
                caut_advice = advice_bucket(str(block.get("cautious_advice") or ""))
                caut_out = block.get("cautious_outcome")
                if is_v30:
                    if caut_advice == "GIOCA" and caut_out in ("WIN", "LOSS"):
                        if caut_out == "WIN":
                            caut_w += 1
                        else:
                            caut_l += 1
                        advised += 1
                    elif caut_advice == "NO_BET":
                        no_bet_count += 1
                    elif caut_advice == "BORDERLINE":
                        borderline_count += 1
                else:
                    agg_advice = advice_bucket(str(block.get("aggressive_advice") or ""))
                    agg_out = block.get("aggressive_outcome")
                    if agg_advice == "GIOCA" and agg_out in ("WIN", "LOSS"):
                        if agg_out == "WIN":
                            agg_w += 1
                        else:
                            agg_l += 1
                        advised += 1
                    if caut_advice == "GIOCA" and caut_out in ("WIN", "LOSS"):
                        if caut_out == "WIN":
                            caut_w += 1
                        else:
                            caut_l += 1
                        advised += 1

        prevalent_error_code: str | None = None
        if error_codes:
            from collections import Counter

            prevalent_error_code = Counter(error_codes).most_common(1)[0][0]

        if fixtures_error > 0 and predictions_available == 0:
            display = "ERROR"
        elif predictions_available == 0:
            display = "ND"
        elif fixtures_nd > 0 or fixtures_error > 0:
            display = "WARNINGS"
        else:
            display = "OK"

        return RoundAnalysisModelSummary(
            model_key=model_key,
            label=MODEL_LABELS.get(model_key, model_key),
            fixtures=total_fixture_rows,
            fixtures_ok=fixtures_ok,
            fixtures_nd=fixtures_nd,
            fixtures_error=fixtures_error,
            aggressive_wins=0 if is_v30 else agg_w,
            aggressive_losses=0 if is_v30 else agg_l,
            aggressive_hit_rate=None if is_v30 else _hit_rate(agg_w, agg_l),
            cautious_wins=caut_w,
            cautious_losses=caut_l,
            cautious_hit_rate=_hit_rate(caut_w, caut_l),
            advised_plays=advised,
            no_bet_count=no_bet_count if is_v30 else 0,
            borderline_count=borderline_count if is_v30 else 0,
            aggressive_na=is_v30,
            avg_predicted_total=_mean(pred_totals),
            avg_actual_total=_mean(actual_totals),
            mae=_mean(abs_errors),
            bias=_mean(errors_signed),
            predictions_available=predictions_available,
            no_prediction_count=no_prediction_count,
            display=display,
            prevalent_error_code=prevalent_error_code,
            model_engine_name=model_engine_name,
        )
