"""Service API confronto componenti predetto vs actual."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PredictiveFixtureComponentComparison, PredictiveSimulationRun
from app.services.backtest.v31_component_aggregators import (
    round_component_error_summary,
    season_component_error_summary,
)
from app.services.backtest.v31_component_trace_builder import flatten_component_rows

COMPONENT_COMPARISON_AUDIT: dict[str, bool] = {
    "predicted_value_pre_match_only": True,
    "actual_value_post_match_diagnostic_only": True,
    "actual_contribution_proxy_diagnostic_only": True,
    "no_weight_mutation": True,
}


class PredictiveComponentComparisonService:
    def _get_run(self, db: Session, run_id: int) -> PredictiveSimulationRun | None:
        return db.get(PredictiveSimulationRun, int(run_id))

    def _load_payloads(
        self,
        db: Session,
        run_id: int,
        *,
        strategy_key: str | None = None,
        round_number: int | None = None,
        fixture_id: int | None = None,
    ) -> list[dict[str, Any]]:
        q = select(PredictiveFixtureComponentComparison).where(
            PredictiveFixtureComponentComparison.run_id == int(run_id),
        )
        if strategy_key:
            q = q.where(PredictiveFixtureComponentComparison.strategy_key == strategy_key)
        if round_number is not None:
            q = q.where(PredictiveFixtureComponentComparison.round_number == int(round_number))
        if fixture_id is not None:
            q = q.where(PredictiveFixtureComponentComparison.fixture_id == int(fixture_id))

        rows = db.scalars(q).all()
        out: list[dict[str, Any]] = []
        for r in rows:
            payload = {
                "match_summary": r.match_summary_json or {},
                "home": (r.component_payload_json or {}).get("home") or {},
                "away": (r.component_payload_json or {}).get("away") or {},
                "match_level": (r.component_payload_json or {}).get("match_level") or {},
            }
            ms = payload["match_summary"]
            ms.setdefault("fixture_id", r.fixture_id)
            ms.setdefault("round_number", r.round_number)
            ms.setdefault("strategy_key", r.strategy_key)
            out.append(payload)
        return out

    def list_fixture_rows(
        self,
        db: Session,
        run_id: int,
        *,
        strategy_key: str | None = None,
        round_number: int | None = None,
        fixture_id: int | None = None,
        team_side: str | None = None,
        macro_area: str | None = None,
        error_direction: str | None = None,
        suspicious_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        if self._get_run(db, run_id) is None:
            return {"error_code": "RUN_NOT_FOUND"}

        payloads = self._load_payloads(
            db,
            run_id,
            strategy_key=strategy_key,
            round_number=round_number,
            fixture_id=fixture_id,
        )
        flat: list[dict[str, Any]] = []
        for p in payloads:
            flat.extend(flatten_component_rows(p))

        if team_side:
            flat = [r for r in flat if r.get("team_side") == team_side]
        if macro_area:
            flat = [r for r in flat if r.get("macro_area") == macro_area]
        if error_direction:
            flat = [r for r in flat if r.get("error_direction") == error_direction]
        if suspicious_only:
            flat = [r for r in flat if r.get("suspicion_level") == "high"]

        total = len(flat)
        items = flat[offset : offset + min(limit, 500)]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
            "audit": COMPONENT_COMPARISON_AUDIT,
        }

    def get_fixture_detail(
        self,
        db: Session,
        run_id: int,
        *,
        fixture_id: int,
        strategy_key: str,
    ) -> dict[str, Any] | None:
        row = db.scalar(
            select(PredictiveFixtureComponentComparison).where(
                PredictiveFixtureComponentComparison.run_id == int(run_id),
                PredictiveFixtureComponentComparison.fixture_id == int(fixture_id),
                PredictiveFixtureComponentComparison.strategy_key == strategy_key,
            ),
        )
        if row is None:
            return None
        return {
            "fixture_id": row.fixture_id,
            "strategy_key": row.strategy_key,
            "round_number": row.round_number,
            "home_team_id": row.home_team_id,
            "away_team_id": row.away_team_id,
            "match_summary": row.match_summary_json,
            "component_payload": row.component_payload_json,
            "audit": COMPONENT_COMPARISON_AUDIT,
        }

    def get_report(
        self,
        db: Session,
        run_id: int,
        *,
        detail: str = "summary",
        strategy_key: str | None = None,
        round_number: int | None = None,
    ) -> dict[str, Any]:
        run = self._get_run(db, run_id)
        if run is None:
            return {"error_code": "RUN_NOT_FOUND"}

        payloads = self._load_payloads(
            db,
            run_id,
            strategy_key=strategy_key,
            round_number=round_number,
        )

        round_summary = round_component_error_summary(
            payloads,
            round_number=round_number,
            strategy_key=strategy_key,
        )

        season_summary = run.season_component_error_summary_json or {}
        if not season_summary and payloads:
            season_summary = season_component_error_summary(payloads)

        result: dict[str, Any] = {
            "run_id": run_id,
            "detail": detail,
            "round_summary": round_summary,
            "season_summary": season_summary if detail == "full" else _trim_season_summary(season_summary),
            "fixtures_in_scope": len(payloads),
            "audit": COMPONENT_COMPARISON_AUDIT,
        }

        if detail == "full":
            result["fixtures"] = payloads

        return result

    def get_round_summary(
        self,
        db: Session,
        run_id: int,
        round_number: int,
        *,
        strategy_key: str | None = None,
    ) -> dict[str, Any]:
        run = self._get_run(db, run_id)
        if run is None:
            return {"error_code": "RUN_NOT_FOUND"}

        payloads = self._load_payloads(
            db,
            run_id,
            strategy_key=strategy_key,
            round_number=round_number,
        )
        summary = round_component_error_summary(
            payloads,
            round_number=round_number,
            strategy_key=strategy_key,
        )
        return {
            "run_id": run_id,
            "round_number": round_number,
            "strategy_key": strategy_key,
            **summary,
            "audit": COMPONENT_COMPARISON_AUDIT,
        }

    def count_comparisons(self, db: Session, run_id: int) -> int:
        return int(
            db.scalar(
                select(func.count()).where(
                    PredictiveFixtureComponentComparison.run_id == int(run_id),
                ),
            )
            or 0,
        )


def _trim_season_summary(season: dict[str, Any]) -> dict[str, Any]:
    strategies = season.get("strategies") or {}
    trimmed: dict[str, Any] = {}
    for sk, data in strategies.items():
        if not isinstance(data, dict):
            continue
        trimmed[sk] = {
            "aggregates_count": data.get("aggregates_count"),
            "top_overestimated_macros": (data.get("top_overestimated_macros") or [])[:3],
            "top_underestimated_macros": (data.get("top_underestimated_macros") or [])[:3],
            "top_suspicious_variables": (data.get("top_suspicious_variables") or [])[:5],
        }
    return {
        "fixtures_compared": season.get("fixtures_compared"),
        "strategies": trimmed,
    }
