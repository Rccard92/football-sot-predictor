"""Servizio analisi AI diagnostica (placeholder OpenAI)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PredictiveAiInsight, PredictiveSimulationRun
from app.services.backtest.predictive_simulation_run_service import PredictiveSimulationRunService

logger = logging.getLogger(__name__)

OPENAI_NOT_CONFIGURED = "OPENAI_NOT_CONFIGURED"
MAX_SAMPLE_FIXTURES = 12


def openai_configured() -> bool:
    key = (get_settings().openai_api_key or "").strip()
    return bool(key)


class PredictiveAiInsightsService:
    def generate(
        self,
        db: Session,
        run_id: int,
    ) -> dict[str, Any]:
        if not openai_configured():
            return {"error_code": OPENAI_NOT_CONFIGURED, "configured": False}

        run_data = PredictiveSimulationRunService().get_run(db, run_id)
        if run_data is None:
            return {"error_code": "RUN_NOT_FOUND"}

        fixtures = PredictiveSimulationRunService().get_fixtures(
            db,
            run_id,
            sort_by="abs_error",
            sort_dir="desc",
            limit=MAX_SAMPLE_FIXTURES,
        )
        prompt_payload = {
            "run_summary": run_data.get("summary"),
            "pattern_insights": run_data.get("insights"),
            "sample_worst_fixtures": fixtures.get("items"),
            "instructions": (
                "Analisi diagnostica post-match ONLY. Non predire SOT futuri. "
                "Non suggerire modifiche pesi automatiche. Output JSON con: "
                "headline, structural_issues[], fixture_notes[], recommended_experiments[], "
                "confidence_level, audit.openai_analysis_no_weight_mutation=true"
            ),
        }

        output = self._call_openai(prompt_payload)
        output.setdefault("audit", {})
        output["audit"]["openai_analysis_no_weight_mutation"] = True
        output["audit"]["no_sot_prediction"] = True

        row = PredictiveAiInsight(run_id=int(run_id), output_json=output)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "run_id": row.run_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "output": output,
        }

    def get_latest(self, db: Session, run_id: int) -> dict[str, Any] | None:
        row = db.scalar(
            select(PredictiveAiInsight)
            .where(PredictiveAiInsight.run_id == int(run_id))
            .order_by(desc(PredictiveAiInsight.created_at))
            .limit(1),
        )
        if row is None:
            return None
        return {
            "id": row.id,
            "run_id": row.run_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "output": row.output_json,
        }

    def _call_openai(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        key = (settings.openai_api_key or "").strip()
        model = settings.openai_model or "gpt-4o-mini"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sei un analista diagnostico di modelli predittivi calcio SOT. "
                        "Rispondi SOLO con JSON valido in italiano."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=60.0) as client:
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
                "headline": "Analisi AI non disponibile",
                "structural_issues": [],
                "fixture_notes": [],
                "recommended_experiments": [],
                "confidence_level": "low",
                "error": str(exc),
                "audit": {"openai_analysis_no_weight_mutation": True},
            }
