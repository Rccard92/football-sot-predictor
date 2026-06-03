"""Service v3.0 SOT Value Selector — wrapper pre-match per Round Analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR,
)
from app.models import Fixture
from app.services.backtest.round_analysis_v21_trace_helpers import (
    extract_v21_macro_averages,
)
from app.services.backtest.sot_v30_human_explanation import build_human_explanation
from app.services.backtest.sot_v30_value_selector_logic import (
    FORBIDDEN_INPUT_FIELDS,
    select_value_pick,
)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return None


class SotV30ValueSelectorService:
    """
    Costruisce un output v3.0 che usa v1.1 + v2.1 come input, senza leakage.

    Nota: questo service NON è un predittore numerico indipendente; usa `predicted_total_sot`
    del reference v2.1 come `predicted_total_sot` nel blocco, e aggiunge selection/audit
    in `trace_summary`.
    """

    model_key = BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR
    model_label = "v3.0 SOT Value Selector"
    reference_model = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

    def build_selection(
        self,
        db: Session,
        *,
        fixture: Fixture,
        competition_id: int,
        mode: str,
        cutoff_time: datetime | None,
        v11_block: dict[str, Any] | None,
        v21_block: dict[str, Any] | None,
        explanation_v21: dict[str, Any] | None,
        data_quality: dict[str, str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        v11_block = dict(v11_block or {})
        v21_block = dict(v21_block or {})

        macros = extract_v21_macro_averages(explanation_v21)
        fallback_count = int((explanation_v21 or {}).get("fallback_count") or 0) if isinstance(explanation_v21, dict) else 0

        pre_match_context: dict[str, Any] = {
            "fixture_id": int(fixture.id),
            "competition_id": int(competition_id),
            "mode": mode,
            "cutoff_time": cutoff_time.isoformat() if cutoff_time else None,
            "v1_1": {
                "predicted_total_sot": _safe_float(v11_block.get("predicted_total_sot")),
                "cautious_advice": v11_block.get("cautious_advice"),
                "cautious_line": _safe_float(v11_block.get("cautious_line")),
            },
            "v2_1": {
                "predicted_total_sot": _safe_float(v21_block.get("predicted_total_sot")),
                "cautious_advice": v21_block.get("cautious_advice"),
                "cautious_line": _safe_float(v21_block.get("cautious_line")),
                "warnings": list(v21_block.get("warnings") or []),
                "confidence": v21_block.get("confidence"),
                "sample_bucket": v21_block.get("sample_bucket"),
            },
            "macros": macros,
            "fallback_count": fallback_count,
            "data_quality": dict(data_quality or {}),
        }

        selection_obj, trace = select_value_pick(pre_match_context)
        selection = selection_obj.as_json()

        v11_pt = _safe_float(v11_block.get("predicted_total_sot"))
        v21_pt = _safe_float(v21_block.get("predicted_total_sot"))
        gap = None
        if v11_pt is not None and v21_pt is not None:
            gap = round(float(v21_pt) - float(v11_pt), 4)

        human_explanation = build_human_explanation(
            pre_match_context,
            selection_obj,
            trace,
            explanation_v21=explanation_v21,
        )

        # Audit anti-leakage: dimostrare cosa NON è stato usato
        audit = {
            "actuals_used_as_input": False,
            "leakage_guard": True,
            "selection_inputs_used": sorted(
                [
                    "v1_1.predicted_total_sot",
                    "v1_1.cautious_advice",
                    "v2_1.predicted_total_sot",
                    "v2_1.cautious_advice",
                    "v2_1.cautious_line",
                    "v2_1.warnings",
                    "v2_1.confidence",
                    "v2_1.sample_bucket",
                    "macros.*",
                    "fallback_count",
                    "data_quality",
                ],
            ),
            "forbidden_fields_not_used": sorted(list(FORBIDDEN_INPUT_FIELDS)),
            "forbidden_fields_present_in_selection_input": any(
                k in pre_match_context for k in FORBIDDEN_INPUT_FIELDS
            ),
        }

        payload = {
            "status": "ok" if selection["decision"] in ("GIOCA", "BORDERLINE") else "no_bet",
            "model_key": self.model_key,
            "model_label": self.model_label,
            "reference_model": self.reference_model,
            "predicted_total_sot_reference": _safe_float(v21_block.get("predicted_total_sot")),
            "v1_1_predicted_total": v11_pt,
            "v2_1_predicted_total": v21_pt,
            "prediction_gap": gap,
            "selected_market": "shots_on_target",
            "selection": selection,
            "audit": audit,
            "trace": trace,
            "human_explanation": human_explanation,
        }

        macro_snapshot = trace.get("macro_snapshot") or macros

        trace_summary = {
            "selection": selection,
            "audit": audit,
            "selection_trace": trace,
            "model_key": self.model_key,
            "reference_model": self.reference_model,
            "v1_1_predicted_total": v11_pt,
            "v2_1_predicted_total": v21_pt,
            "prediction_gap": gap,
            "macro_snapshot": macro_snapshot,
            "human_explanation": human_explanation,
        }
        return payload, trace_summary

