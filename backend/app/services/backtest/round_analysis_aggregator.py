"""Aggregazione summary analisi giornata (Step I)."""

from __future__ import annotations

from typing import Any, Iterable

from app.schemas.backtest_round_analysis import (
    MODEL_LABELS,
    RoundAnalysisDataQualitySummary,
    RoundAnalysisModelSummary,
)
from app.services.backtest.round_analysis_data_prep_service import FixturePreflight, RoundAnalysisPrepResult


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
    ) -> dict[str, Any]:
        preflights = list(prep.fixture_preflights.values())
        total = len(preflights) or len(fixture_results)
        with_lineup = sum(1 for p in preflights if p.has_lineup)
        with_unavail = sum(1 for p in preflights if p.unavailable_count > 0)
        missing_map = sum(1 for p in preflights if not p.has_mapping)

        warnings = list(prep.prep_warnings)
        badge = "OK"
        if missing_map > 0 or with_lineup < total:
            badge = "Avvisi"
        if total > 0 and (missing_map >= total * 0.5 or with_lineup == 0):
            badge = "Critico"

        summary = RoundAnalysisDataQualitySummary(
            badge=badge,  # type: ignore[arg-type]
            total_fixtures=total,
            fixtures_with_lineup=with_lineup,
            fixtures_with_unavailable=with_unavail,
            fixtures_missing_mapping=missing_map,
            fixtures_player_layer_ok=0,
            fixtures_split_ok=0,
            warnings=warnings,
            details={
                "mapping_backfill": prep.mapping_backfill_summary,
                "unavailable_backfill": prep.unavailable_backfill_summary,
            },
        )
        return summary.model_dump()

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
        agg_w = agg_l = caut_w = caut_l = advised = 0
        pred_totals: list[float] = []
        actual_totals: list[float] = []
        abs_errors: list[float] = []
        errors_signed: list[float] = []

        for row in fixture_results:
            if row.get("status") != "ok":
                continue
            block = (row.get("models_json") or {}).get(model_key)
            if not isinstance(block, dict):
                continue
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

            if block.get("aggressive_outcome") == "WIN":
                agg_w += 1
            elif block.get("aggressive_outcome") == "LOSS":
                agg_l += 1
            if block.get("cautious_outcome") == "WIN":
                caut_w += 1
            elif block.get("cautious_outcome") == "LOSS":
                caut_l += 1
            for field in ("aggressive_advice", "cautious_advice"):
                if str(block.get(field) or "").strip().upper() == "GIOCA":
                    advised += 1

        avg_pred = _mean(pred_totals)
        avg_actual = _mean(actual_totals)
        mae = _mean(abs_errors)
        bias = _mean(errors_signed)

        return RoundAnalysisModelSummary(
            model_key=model_key,
            label=MODEL_LABELS.get(model_key, model_key),
            fixtures=len([r for r in fixture_results if r.get("status") == "ok"]),
            aggressive_wins=agg_w,
            aggressive_losses=agg_l,
            aggressive_hit_rate=_hit_rate(agg_w, agg_l),
            cautious_wins=caut_w,
            cautious_losses=caut_l,
            cautious_hit_rate=_hit_rate(caut_w, caut_l),
            advised_plays=advised,
            avg_predicted_total=avg_pred,
            avg_actual_total=avg_actual,
            mae=mae,
            bias=bias,
        )
