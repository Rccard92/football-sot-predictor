"""Orchestratore run laboratorio predittivo persistente."""

from __future__ import annotations

import copy
import logging
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    PredictiveFixtureComponentComparison,
    PredictiveFixtureNote,
    PredictiveFixturePrediction,
    PredictivePatternInsight,
    PredictiveSimulationRun,
)
from app.services.backtest.v31_component_aggregators import season_component_error_summary
from app.services.backtest.v31_component_trace_builder import build_component_comparison
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.v31_calibration_dataset_builder import build_v31_dataset_rows_standard
from app.services.backtest.v31_calibration_simulator_error_reasons import safe_probable_reason
from app.services.backtest.v31_calibration_simulator_service import (
    ROUND_MAX,
    ROUND_MIN,
    V31CalibrationSimulatorService,
)
from app.services.backtest.v31_pattern_analysis_distribution import (
    compute_actual_sot_distribution,
    extract_actuals_from_rows,
)
from app.services.backtest.v31_pattern_analysis_service import V31PatternAnalysisService
from app.services.backtest.v31_pattern_analysis_buckets import dynamic_bucket_thresholds
from app.services.backtest.v31_pattern_analysis_win_quality import enrich_row_with_pattern_fields
from app.services.backtest.v31_predictive_pattern_insights import (
    best_mae_strategy_from_simulator,
    generate_pattern_insights,
    main_warning_from_insights,
)
from app.services.backtest.v31_predictive_reason_codes import (
    build_feature_snapshot,
    build_reason_codes,
    derive_outcome_type,
)

logger = logging.getLogger(__name__)

LAB_AUDIT = {
    "actual_post_match_only": True,
    "win_quality_diagnostic_only": True,
    "pattern_no_weight_mutation": True,
    "openai_no_prediction_no_weight_mutation": True,
    "betting_phase_enabled": False,
}


def _filter_rounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        rn = int((row.get("metadata") or {}).get("round_number") or 0)
        if ROUND_MIN <= rn <= ROUND_MAX:
            out.append(row)
    return out


def _parse_teams(row: dict[str, Any]) -> tuple[str, str]:
    match = str(row.get("match") or "")
    if " vs " in match:
        parts = match.split(" vs ", 1)
        return parts[0].strip(), parts[1].strip()
    return "", ""


def _clean_simulator_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    for block in out.get("strategies") or []:
        if isinstance(block, dict):
            block.pop("_all_rows", None)
    return out


def _enrich_rows(
    rows: list[dict[str, Any]],
    *,
    p25: float | None,
    p75: float | None,
    p90: float | None,
    p95: float | None,
) -> list[dict[str, Any]]:
    return [
        enrich_row_with_pattern_fields(r, p25=p25, p75=p75, p90=p90, p95=p95)
        for r in rows
    ]


def _merge_audit(simulator: dict[str, Any], pattern: dict[str, Any]) -> dict[str, Any]:
    audit: dict[str, Any] = {}
    audit.update(simulator.get("audit") or {})
    audit.update(pattern.get("audit") or {})
    audit.update(LAB_AUDIT)
    return audit


class PredictiveSimulationRunService:
    def create_and_run(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        strategy: str = "all",
        strategy_status: str = "active",
        persist: bool = True,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
    ) -> dict[str, Any]:
        logger.info(
            "PREDICTIVE_RUN_START competition_id=%s season_year=%s",
            competition_id,
            season_year,
        )
        raw_rows, excluded, _max_round = build_v31_dataset_rows_standard(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        rows = _filter_rounds(raw_rows)
        dataset_by_fixture: dict[int, dict[str, Any]] = {}
        for row in rows:
            fid = int((row.get("metadata") or {}).get("fixture_id") or 0)
            if fid:
                dataset_by_fixture[fid] = row

        sim_svc = V31CalibrationSimulatorService()
        pat_svc = V31PatternAnalysisService()

        simulator_payload = sim_svc.run_simulator(
            db,
            competition_id=competition_id,
            season_year=season_year,
            strategy=strategy,
            strategy_status_filter=strategy_status,
            include_rows=True,
            rows=rows,
            excluded_analyses=excluded,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        pattern_payload = pat_svc.run_pattern_analysis(
            db,
            competition_id=competition_id,
            season_year=season_year,
            include_fixtures=True,
            rows=rows,
            excluded_analyses=excluded,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )

        distribution = (pattern_payload.get("summary") or {}).get("actual_sot_distribution") or {}
        thresholds = (pattern_payload.get("summary") or {}).get("dynamic_bucket_thresholds") or {}
        if not thresholds:
            bias_rows = []
            for block in simulator_payload.get("strategies") or []:
                if block.get("key") == "v31_bias_corrected":
                    bias_rows = block.get("_all_rows") or []
                    break
            if not bias_rows:
                for block in simulator_payload.get("strategies") or []:
                    bias_rows = block.get("_all_rows") or []
                    if bias_rows:
                        break
            actuals = extract_actuals_from_rows(bias_rows)
            distribution = compute_actual_sot_distribution(actuals)
            thresholds = dynamic_bucket_thresholds(distribution)

        p25 = thresholds.get("p25")
        p75 = thresholds.get("p75")
        p90 = thresholds.get("p90")
        p95 = thresholds.get("p95")

        enriched_by_strategy: dict[str, list[dict[str, Any]]] = {}
        fixture_rows: list[PredictiveFixturePrediction] = []
        component_comparison_payloads: list[dict[str, Any]] = []

        for block in simulator_payload.get("strategies") or []:
            key = block.get("key")
            all_rows = block.get("_all_rows") or []
            if not key or not all_rows:
                continue
            enriched = _enrich_rows(all_rows, p25=p25, p75=p75, p90=p90, p95=p95)
            enriched_by_strategy[str(key)] = enriched

            for row in enriched:
                reason_codes = build_reason_codes(row)
                row_with_codes = {**row, "reason_codes": reason_codes}
                probable = safe_probable_reason(row_with_codes)
                home, away = _parse_teams(row)
                trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
                fid = int(row.get("fixture_id") or 0)
                ds_row = dataset_by_fixture.get(fid)
                if ds_row is not None:
                    cmp_payload = build_component_comparison(
                        db,
                        dataset_row=ds_row,
                        simulated_row=row,
                        strategy_key=str(key),
                    )
                    if cmp_payload is not None:
                        component_comparison_payloads.append(cmp_payload)

                fixture_rows.append(
                    PredictiveFixturePrediction(
                        fixture_id=fid,
                        round_number=int(row.get("round_number") or 0),
                        home_team_name=home,
                        away_team_name=away,
                        strategy_key=str(key),
                        predicted_total_sot=row.get("predicted_total_sot"),
                        actual_total_sot=row.get("actual_total_sot"),
                        error=row.get("error"),
                        abs_error=row.get("abs_error"),
                        predicted_bucket=row.get("predicted_bucket"),
                        actual_bucket=row.get("actual_bucket"),
                        actual_bucket_dynamic=row.get("actual_bucket_dynamic"),
                        win_quality=row.get("win_quality"),
                        outcome_type=derive_outcome_type(row, reason_codes),
                        reason_codes_json=reason_codes,
                        probable_reason=probable,
                        boost_applied=float(trace.get("boost_applied")) if trace.get("boost_applied") is not None else None,
                        high_total_signal=float(trace.get("high_total_signal")) if trace.get("high_total_signal") is not None else None,
                        feature_snapshot_json=build_feature_snapshot(row),
                    ),
                )

        pattern_verdict = (pattern_payload.get("summary") or {}).get("pattern_verdict") or {}
        insight_dicts = generate_pattern_insights(
            enriched_by_strategy=enriched_by_strategy,
            top3_cluster_summary=(pattern_payload.get("summary") or {}).get("top3_cluster_summary") or {},
            distribution=distribution,
            pattern_verdict=pattern_verdict,
        )

        sim_summary = simulator_payload.get("summary") or {}
        clean_sim = _clean_simulator_payload(simulator_payload)
        audit = _merge_audit(simulator_payload, pattern_payload)

        season_cmp_summary = season_component_error_summary(component_comparison_payloads)

        summary_json = {
            "competition_id": competition_id,
            "season_year": season_year,
            "season_label": season_label_from_year(season_year),
            "fixtures_count": sim_summary.get("fixtures_count"),
            "strategies_count": sim_summary.get("strategies_run"),
            "recommended_strategy": sim_summary.get("recommended_strategy"),
            "recommendation_note": sim_summary.get("recommendation_note"),
            "recommendation_tradeoff": sim_summary.get("recommendation_tradeoff"),
            "best_mae_strategy": best_mae_strategy_from_simulator(simulator_payload),
            "main_warning": main_warning_from_insights(insight_dicts),
            "pattern_verdict": pattern_verdict,
            "insights_count": len(insight_dicts),
        }

        run = PredictiveSimulationRun(
            competition_id=int(competition_id),
            season_year=int(season_year),
            season_label=season_label_from_year(season_year),
            run_type="full_lab",
            model_version="v3.1",
            strategy_status_filter=strategy_status,
            strategies_count=int(sim_summary.get("strategies_run") or 0),
            fixtures_count=int(sim_summary.get("fixtures_count") or 0),
            round_range=f"{ROUND_MIN}-{ROUND_MAX}",
            recommended_strategy=sim_summary.get("recommended_strategy"),
            recommendation_note=sim_summary.get("recommendation_note"),
            recommendation_tradeoff=sim_summary.get("recommendation_tradeoff"),
            phase=str(sim_summary.get("phase") or "predictive_numeric"),
            betting_phase_enabled=False,
            summary_json=summary_json,
            simulator_payload_json=clean_sim,
            pattern_payload_json=pattern_payload,
            audit_json=audit,
            season_component_error_summary_json=season_cmp_summary,
        )

        if persist:
            db.add(run)
            db.flush()
            for fr in fixture_rows:
                fr.run_id = run.id
                db.add(fr)
            for ins in insight_dicts:
                db.add(
                    PredictivePatternInsight(
                        run_id=run.id,
                        insight_type=ins["insight_type"],
                        severity=ins["severity"],
                        title=ins["title"],
                        description=ins["description"],
                        evidence_json=ins.get("evidence_json") or {},
                        recommended_action=ins.get("recommended_action"),
                        strategy_key=ins.get("strategy_key"),
                    ),
                )
            for cmp_payload in component_comparison_payloads:
                ms = cmp_payload.get("match_summary") or {}
                home = cmp_payload.get("home") or {}
                away = cmp_payload.get("away") or {}
                db.add(
                    PredictiveFixtureComponentComparison(
                        run_id=run.id,
                        fixture_id=int(ms.get("fixture_id") or 0),
                        strategy_key=str(ms.get("strategy_key") or ""),
                        round_number=int(ms.get("round_number") or 0),
                        home_team_id=int(home.get("team_id") or 0),
                        away_team_id=int(away.get("team_id") or 0),
                        match_summary_json=ms,
                        component_payload_json={
                            "home": home,
                            "away": away,
                            "match_level": cmp_payload.get("match_level") or {},
                        },
                    ),
                )
            db.commit()
            db.refresh(run)

        return {
            "run_id": run.id if persist else None,
            "summary": summary_json,
            "simulator": clean_sim,
            "pattern": pattern_payload,
            "insights": insight_dicts,
            "audit": audit,
            "message": "Analisi salvata nello storico" if persist else "Analisi completata (non persistita)",
        }

    def list_runs(
        self,
        db: Session,
        *,
        competition_id: int | None = None,
        season_year: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = select(PredictiveSimulationRun).order_by(desc(PredictiveSimulationRun.created_at))
        if competition_id is not None:
            q = q.where(PredictiveSimulationRun.competition_id == int(competition_id))
        if season_year is not None:
            q = q.where(PredictiveSimulationRun.season_year == int(season_year))
        q = q.limit(min(limit, 100))
        runs = db.scalars(q).all()
        out: list[dict[str, Any]] = []
        for r in runs:
            s = r.summary_json or {}
            out.append(
                {
                    "run_id": r.id,
                    "competition_id": r.competition_id,
                    "season_year": r.season_year,
                    "season_label": r.season_label,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "fixtures_count": r.fixtures_count,
                    "strategies_count": r.strategies_count,
                    "recommended_strategy": r.recommended_strategy,
                    "best_mae_strategy": s.get("best_mae_strategy"),
                    "main_warning": s.get("main_warning"),
                    "run_type": r.run_type,
                    "model_version": r.model_version,
                },
            )
        return out

    def get_run(self, db: Session, run_id: int) -> dict[str, Any] | None:
        run = db.get(PredictiveSimulationRun, int(run_id))
        if run is None:
            return None
        insights = db.scalars(
            select(PredictivePatternInsight)
            .where(PredictivePatternInsight.run_id == run.id)
            .order_by(PredictivePatternInsight.id),
        ).all()
        return {
            "run_id": run.id,
            "competition_id": run.competition_id,
            "season_year": run.season_year,
            "season_label": run.season_label,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "summary": run.summary_json,
            "simulator": run.simulator_payload_json,
            "pattern": run.pattern_payload_json,
            "insights": [
                {
                    "id": i.id,
                    "insight_type": i.insight_type,
                    "severity": i.severity,
                    "title": i.title,
                    "description": i.description,
                    "evidence_json": i.evidence_json,
                    "recommended_action": i.recommended_action,
                    "strategy_key": i.strategy_key,
                }
                for i in insights
            ],
            "audit": run.audit_json,
            "betting_phase_enabled": run.betting_phase_enabled,
            "season_component_error_summary": run.season_component_error_summary_json,
        }

    def get_fixtures(
        self,
        db: Session,
        run_id: int,
        *,
        strategy_key: str | None = None,
        round_number: int | None = None,
        outcome_type: str | None = None,
        predicted_bucket: str | None = None,
        actual_bucket: str | None = None,
        min_abs_error: float | None = None,
        max_abs_error: float | None = None,
        sort_by: str = "abs_error",
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        q = select(PredictiveFixturePrediction).where(PredictiveFixturePrediction.run_id == int(run_id))
        if strategy_key:
            q = q.where(PredictiveFixturePrediction.strategy_key == strategy_key)
        if round_number is not None:
            q = q.where(PredictiveFixturePrediction.round_number == int(round_number))
        if outcome_type:
            q = q.where(PredictiveFixturePrediction.outcome_type == outcome_type)
        if predicted_bucket:
            q = q.where(PredictiveFixturePrediction.predicted_bucket == predicted_bucket)
        if actual_bucket:
            q = q.where(PredictiveFixturePrediction.actual_bucket == actual_bucket)
        if min_abs_error is not None:
            q = q.where(PredictiveFixturePrediction.abs_error >= float(min_abs_error))
        if max_abs_error is not None:
            q = q.where(PredictiveFixturePrediction.abs_error <= float(max_abs_error))

        count_q = select(func.count()).select_from(q.subquery())
        total = db.scalar(count_q) or 0

        sort_col = getattr(PredictiveFixturePrediction, sort_by, PredictiveFixturePrediction.abs_error)
        if sort_dir == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        rows = db.scalars(q.offset(offset).limit(min(limit, 500))).all()
        notes_map: dict[tuple[int, str], PredictiveFixtureNote] = {}
        if rows:
            note_rows = db.scalars(
                select(PredictiveFixtureNote).where(PredictiveFixtureNote.run_id == int(run_id)),
            ).all()
            for n in note_rows:
                notes_map[(int(n.fixture_id), n.strategy_key)] = n

        items = []
        for r in rows:
            note = notes_map.get((int(r.fixture_id), r.strategy_key))
            items.append(
                {
                    "fixture_id": r.fixture_id,
                    "round_number": r.round_number,
                    "home_team_name": r.home_team_name,
                    "away_team_name": r.away_team_name,
                    "match": f"{r.home_team_name} vs {r.away_team_name}".strip(" vs "),
                    "strategy_key": r.strategy_key,
                    "predicted_total_sot": r.predicted_total_sot,
                    "actual_total_sot": r.actual_total_sot,
                    "error": r.error,
                    "abs_error": r.abs_error,
                    "predicted_bucket": r.predicted_bucket,
                    "actual_bucket": r.actual_bucket,
                    "actual_bucket_dynamic": r.actual_bucket_dynamic,
                    "win_quality": r.win_quality,
                    "outcome_type": r.outcome_type,
                    "reason_codes": r.reason_codes_json,
                    "probable_reason": r.probable_reason,
                    "boost_applied": r.boost_applied,
                    "high_total_signal": r.high_total_signal,
                    "feature_snapshot": r.feature_snapshot_json,
                    "user_note": note.note if note else None,
                    "user_note_tag": note.tag if note else None,
                },
            )

        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def upsert_note(
        self,
        db: Session,
        run_id: int,
        fixture_id: int,
        strategy_key: str,
        note: str,
        tag: str | None = None,
    ) -> dict[str, Any]:
        existing = db.scalar(
            select(PredictiveFixtureNote).where(
                PredictiveFixtureNote.run_id == int(run_id),
                PredictiveFixtureNote.fixture_id == int(fixture_id),
                PredictiveFixtureNote.strategy_key == strategy_key,
            ),
        )
        if existing:
            existing.note = note
            existing.tag = tag
            db.commit()
            db.refresh(existing)
            row = existing
        else:
            row = PredictiveFixtureNote(
                run_id=int(run_id),
                fixture_id=int(fixture_id),
                strategy_key=strategy_key,
                note=note,
                tag=tag,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return {
            "id": row.id,
            "run_id": row.run_id,
            "fixture_id": row.fixture_id,
            "strategy_key": row.strategy_key,
            "note": row.note,
            "tag": row.tag,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
