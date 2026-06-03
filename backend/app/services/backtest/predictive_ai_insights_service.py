"""Servizio analisi AI diagnostica mirata."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PredictiveAiInsight
from app.schemas.predictive_ai_output import AnalysisType, normalize_ai_output
from app.services.backtest.predictive_ai_context_builders import build_context

logger = logging.getLogger(__name__)

OPENAI_NOT_CONFIGURED = "OPENAI_NOT_CONFIGURED"

SYSTEM_PROMPT = """Sei un analista diagnostico di modelli predittivi calcio SOT (post-match ONLY).

REGOLE OBBLIGATORIE:
- Non fare frasi generiche. Ogni conclusione deve citare un numero dal payload.
- Ogni raccomandazione deve essere un esperimento testabile nel simulatore.
- Non suggerire bet/no bet, quote, stake o decisioni di scommessa.
- Non suggerire modifica automatica dei pesi del modello.
- Non predire SOT futuri. I campi actual_* sono solo etichette post-match, mai input predittivi.

OUTPUT JSON obbligatorio (in italiano):
{
  "analysis_type": "...",
  "short_verdict": "1-2 frasi concrete con numeri",
  "key_evidence": [{"metric": "...", "value": "...", "interpretation": "..."}],
  "root_causes": [{"cause": "...", "evidence": "...", "affected_models": ["..."], "severity": "low|medium|high"}],
  "recommended_experiments": [{"experiment_name": "...", "hypothesis": "...", "change_to_test": "...", "expected_benefit": "...", "risk": "...", "success_metric": "..."}],
  "do_not_overreact_to": [{"case": "...", "reason": "..."}],
  "next_action": "azione concreta immediata",
  "fixture_notes": [{"match": "...", "predicted": "...", "actual": "...", "error": "...", "reason_codes": ["..."], "diagnosis": "..."}],
  "audit": {"openai_analysis_no_weight_mutation": true, "no_sot_prediction": true}
}
"""

GUIDANCE: dict[str, str] = {
    "missed_high_non_extreme": (
        "Analizza partite high/very_high non estreme sottostimate. "
        "Spiega quali modelli sbagliano, quali segnali pre-match (boost, high_total_signal, feature) "
        "sembrano sottopesati e quale esperimento testare."
    ),
    "false_high_predictions": (
        "Analizza falsi positivi: pred >= 9 e actual <= 7. "
        "Identifica modelli e cluster responsabili, con evidenze numeriche e guardrail da testare."
    ),
    "top3_model_comparison": (
        "Confronta v31_bias_corrected, v31_bias_dynamic_high_guard, v31_chaos_game. "
        "Rispondi: quando hybrid migliora/peggiora bias; quando chaos intercetta high; "
        "quando chaos fa falso positivo; quali regole prendere da chaos senza copiarlo."
    ),
    "single_fixture": (
        "Diagnosi su singola partita. Spiega errore, outlier vs pattern replicabile, "
        "cosa testare nel modello. Usa top3_predictions e reason_codes."
    ),
}


def openai_configured() -> bool:
    key = (get_settings().openai_api_key or "").strip()
    return bool(key)


class PredictiveAiInsightsService:
    def generate(
        self,
        db: Session,
        run_id: int,
        *,
        analysis_type: AnalysisType,
        fixture_id: int | None = None,
        strategy_key: str | None = None,
    ) -> dict[str, Any]:
        if not openai_configured():
            return {"error_code": OPENAI_NOT_CONFIGURED, "configured": False}

        context = build_context(
            db,
            run_id,
            analysis_type,
            fixture_id=fixture_id,
            strategy_key=strategy_key,
        )
        if context.get("error"):
            return {"error_code": context["error"]}

        settings = get_settings()
        model_name = settings.openai_model or "gpt-4o-mini"

        prompt_payload = {
            "task": GUIDANCE.get(analysis_type, ""),
            "guiding_questions": context.get("guiding_questions") or [],
            "context": context,
            "output_schema_reminder": (
                "Rispetta lo schema JSON. key_evidence minimo 3 voci con numeri. "
                "recommended_experiments minimo 2 voci concretes."
            ),
        }

        raw_output = self._call_openai(prompt_payload, model_name=model_name)
        output = normalize_ai_output(raw_output, analysis_type)

        row = PredictiveAiInsight(
            run_id=int(run_id),
            analysis_type=analysis_type,
            fixture_id=int(fixture_id) if fixture_id is not None else None,
            strategy_key=strategy_key,
            input_summary_json=_input_summary(context),
            model_name=model_name,
            output_json=output,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return self._serialize_row(row)

    def list_history(
        self,
        db: Session,
        run_id: int,
        *,
        analysis_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        q = (
            select(PredictiveAiInsight)
            .where(PredictiveAiInsight.run_id == int(run_id))
            .order_by(desc(PredictiveAiInsight.created_at))
        )
        if analysis_type:
            q = q.where(PredictiveAiInsight.analysis_type == analysis_type)
        q = q.limit(min(limit, 50))
        rows = db.scalars(q).all()
        return [self._serialize_row(r, include_output=False) for r in rows]

    def get_by_id(self, db: Session, run_id: int, insight_id: int) -> dict[str, Any] | None:
        row = db.scalar(
            select(PredictiveAiInsight).where(
                PredictiveAiInsight.id == int(insight_id),
                PredictiveAiInsight.run_id == int(run_id),
            ),
        )
        if row is None:
            return None
        return self._serialize_row(row)

    def _serialize_row(self, row: PredictiveAiInsight, *, include_output: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": row.id,
            "run_id": row.run_id,
            "analysis_type": row.analysis_type,
            "fixture_id": row.fixture_id,
            "strategy_key": row.strategy_key,
            "model_name": row.model_name,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "input_summary": row.input_summary_json,
        }
        if include_output:
            data["output"] = row.output_json
        else:
            output = row.output_json or {}
            data["short_verdict"] = output.get("short_verdict")
        return data

    def _call_openai(self, payload: dict[str, Any], *, model_name: str) -> dict[str, Any]:
        key = (get_settings().openai_api_key or "").strip()
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as exc:
            logger.exception("OpenAI call failed")
            return {
                "analysis_type": payload.get("context", {}).get("analysis_type", "unknown"),
                "short_verdict": "Analisi AI non disponibile per errore tecnico.",
                "key_evidence": [],
                "root_causes": [],
                "recommended_experiments": [],
                "do_not_overreact_to": [],
                "next_action": "Riprovare più tardi o verificare OPENAI_API_KEY.",
                "fixture_notes": [],
                "error": str(exc),
                "audit": {"openai_analysis_no_weight_mutation": True, "no_sot_prediction": True},
            }


def _input_summary(context: dict[str, Any]) -> dict[str, Any]:
    """Subset compatto per storico DB."""
    agg = context.get("aggregates") or {}
    return {
        "analysis_type": context.get("analysis_type"),
        "aggregates": agg,
        "fixture_count": len(context.get("top_fixtures") or context.get("top_examples") or []),
        "fixture_id": context.get("fixture_id"),
    }
