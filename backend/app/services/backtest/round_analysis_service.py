"""Orchestrazione analisi giornata persistente (Step I)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtest.errors import raise_backtest_http
from app.models import Competition, Fixture, FixtureTeamStat
from app.models.backtest_round_analysis import BacktestRoundAnalysis, BacktestRoundFixtureResult
from app.schemas.backtest_round_analysis import (
    RoundAnalysisAnalyzeRequest,
    RoundAnalysisDeleteResponse,
    RoundAnalysisDetailResponse,
    RoundAnalysisFixtureRow,
    RoundAnalysisListItem,
    RoundAnalysisListResponse,
    normalize_model_keys,
    season_label_from_year,
)
from app.services.backtest.round_analysis_aggregator import RoundAnalysisAggregator
from app.services.backtest.round_analysis_data_prep_service import RoundAnalysisDataPrepService
from app.services.backtest.round_analysis_model_runner import RoundAnalysisModelRunner
from app.services.backtest.round_analysis_preflight import preflight_round_history
from app.services.backtest.sot_pick_play_advice_logic import PlayAdviceConfig

def _list_order_clauses(
    sort_by: str = "round_number",
    sort_dir: str = "desc",
) -> tuple[Any, ...]:
    ascending = str(sort_dir).lower() == "asc"

    def _dir(column: Any) -> Any:
        return column.asc() if ascending else column.desc()

    if sort_by == "created_at":
        return (
            _dir(BacktestRoundAnalysis.created_at),
            BacktestRoundAnalysis.round_number.desc(),
            BacktestRoundAnalysis.analysis_version.desc(),
        )
    return (
        _dir(BacktestRoundAnalysis.round_number),
        BacktestRoundAnalysis.analysis_version.desc(),
        BacktestRoundAnalysis.created_at.desc(),
    )


_STATUS_LABELS = {
    "completed": "Completata",
    "completed_with_warnings": "Completata con avvisi",
    "failed": "Fallita",
    "pending": "In attesa",
    "preparing_data": "Preparazione dati",
    "running": "In corso",
}


class RoundAnalysisService:
    def __init__(self) -> None:
        self._prep = RoundAnalysisDataPrepService()
        self._runner = RoundAnalysisModelRunner()
        self._aggregator = RoundAnalysisAggregator()

    def analyze(self, db: Session, request: RoundAnalysisAnalyzeRequest) -> RoundAnalysisDetailResponse:
        comp = db.get(Competition, int(request.competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", "Campionato non trovato.")

        if not request.force_recalculate:
            existing = self._latest_completed(
                db,
                competition_id=request.competition_id,
                season_year=request.season_year,
                round_number=request.round_number,
            )
            if existing is not None:
                raise_backtest_http(
                    409,
                    "analysis_already_completed",
                    "Analisi già completata per questa giornata. Usa Rianalizza per una nuova versione.",
                    existing_analysis_id=int(existing.id),
                )

        version = self._next_version(
            db,
            competition_id=request.competition_id,
            season_year=request.season_year,
            round_number=request.round_number,
        )

        models = normalize_model_keys(request.models)
        advice = request.advice_filters
        play_config = PlayAdviceConfig(
            min_prior_matches_for_play=advice.min_prior_matches_for_play if advice else 10,
            min_aggressive_edge_for_play=advice.min_aggressive_edge_for_play if advice else 0.25,
            min_cautious_edge_for_play=advice.min_cautious_edge_for_play if advice else 1.0,
            max_warnings_for_play=advice.max_warnings_for_play if advice else 6,
            allow_early_low_sample=advice.allow_early_low_sample if advice else False,
            allow_low_confidence=advice.allow_low_confidence if advice else False,
            include_borderline_as_playable=advice.include_borderline_as_playable if advice else False,
        )
        season_label = season_label_from_year(request.season_year)
        config_json: dict[str, Any] = {
            "models": models,
            "lines": list(request.lines or []),
            "cautious_drop_threshold": request.cautious_drop_threshold,
            "advice_filters": advice.model_dump() if advice else {},
            "mode": request.mode,
            "season_label": season_label,
        }

        analysis = BacktestRoundAnalysis(
            competition_id=int(request.competition_id),
            season_year=int(request.season_year),
            round_number=int(request.round_number),
            analysis_version=version,
            status="pending",
            mode=request.mode,
            config_json=config_json,
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        try:
            analysis.status = "preparing_data"
            db.commit()

            prep = self._prep.prepare(
                db,
                competition_id=request.competition_id,
                season_year=request.season_year,
                round_number=request.round_number,
            )
            if not prep.fixtures:
                raise_backtest_http(
                    422,
                    "no_fixtures_for_round",
                    "Nessuna partita con statistiche SOT per questa giornata.",
                )

            history_pf = preflight_round_history(
                db,
                competition_id=request.competition_id,
                season_year=request.season_year,
                fixtures=prep.fixtures,
                prep=prep,
            )
            config_json["first_recommended_round"] = history_pf.first_recommended_round
            analysis.config_json = dict(config_json)

            analysis.total_fixtures = len(prep.fixtures)
            analysis.status = "running"
            db.commit()

            lines = list(request.lines or [])
            fixture_rows: list[dict[str, Any]] = []
            processed = 0
            failed = 0

            for idx, cand in enumerate(prep.fixtures):
                fx = db.get(Fixture, int(cand.fixture_id))
                if fx is None:
                    failed += 1
                    self._save_failed_fixture(
                        db,
                        analysis=analysis,
                        cand=cand,
                        message="Fixture non trovata",
                    )
                    continue

                preflight = prep.fixture_preflights.get(int(cand.fixture_id))
                dq = self._prep.fixture_data_quality(preflight) if preflight else {"lineup": "unknown", "mapping": "unknown"}

                try:
                    models_json, explanation_json = self._runner.run_for_fixture(
                        db,
                        fixture=fx,
                        competition_id=request.competition_id,
                        mode=request.mode,
                        models=models,
                        lines=lines,
                        cautious_drop_threshold=request.cautious_drop_threshold,
                        play_config=play_config,
                        data_quality=dq,
                        actual_total=cand.actual_total_sot,
                        analysis_id=int(analysis.id),
                    )
                    home_sot, away_sot = self._actual_side_sots(db, fx)
                    row = BacktestRoundFixtureResult(
                        analysis_id=int(analysis.id),
                        fixture_id=int(fx.id),
                        round_number=request.round_number,
                        home_team_name=cand.home_team.name,
                        away_team_name=cand.away_team.name,
                        actual_home_sot=home_sot,
                        actual_away_sot=away_sot,
                        actual_total_sot=cand.actual_total_sot,
                        models_json=models_json,
                        explanation_json=explanation_json or {},
                        status="ok",
                    )
                    db.add(row)
                    processed += 1
                    fixture_rows.append(self._fixture_row_dict(row))
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    self._save_failed_fixture(
                        db,
                        analysis=analysis,
                        cand=cand,
                        message=str(exc)[:500],
                        fx=fx,
                    )

                analysis.processed_fixtures = processed
                analysis.failed_fixtures = failed
                total = max(1, len(prep.fixtures))
                analysis.progress_pct = round(100.0 * (idx + 1) / total, 2)
                db.commit()

            if processed == 0:
                analysis.status = "failed"
                analysis.error_json = {
                    "code": "no_fixtures_processed",
                    "message": "Nessuna partita elaborata con successo.",
                    "reason": "TECHNICAL_ERROR",
                }
            else:
                model_summary = self._aggregator.build_model_summary(
                    models=models,
                    fixture_results=fixture_rows,
                )
                dq_summary = self._aggregator.build_data_quality_summary(
                    prep=prep,
                    fixture_results=fixture_rows,
                    history_preflight=history_pf,
                    model_summary=model_summary,
                )
                analysis.data_quality_summary_json = dq_summary
                analysis.model_summary_json = model_summary
                analysis.status = self._resolve_final_status(
                    history_preflight=history_pf,
                    model_summary=model_summary,
                    dq_summary=dq_summary,
                )
                analysis.error_json = self._build_warning_error_json(
                    history_preflight=history_pf,
                    failed_fixtures=failed,
                    model_summary=model_summary,
                    models=models,
                )
                analysis.completed_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(analysis)
            return self.get_detail(db, int(analysis.id))

        except HTTPException as exc:
            analysis.status = "failed"
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            analysis.error_json = {**detail, "reason": detail.get("code") or "TECHNICAL_ERROR"}
            db.commit()
            raise
        except Exception as exc:
            analysis.status = "failed"
            analysis.error_json = {"message": str(exc)[:500], "reason": "TECHNICAL_ERROR"}
            db.commit()
            raise

    def _resolve_final_status(
        self,
        *,
        history_preflight: Any,
        model_summary: dict[str, Any],
        dq_summary: dict[str, Any],
    ) -> str:
        if history_preflight.insufficient_history:
            return "completed_with_warnings"
        all_nd = True
        for key in model_summary:
            m = model_summary.get(key)
            if isinstance(m, dict) and int(m.get("predictions_available") or 0) > 0:
                all_nd = False
                break
        if all_nd:
            return "completed_with_warnings"
        badge = str(dq_summary.get("badge") or "OK")
        if badge in ("Avvisi", "Critico"):
            return "completed_with_warnings"
        warnings = dq_summary.get("warnings") or []
        if warnings:
            return "completed_with_warnings"
        return "completed"

    def _build_warning_error_json(
        self,
        *,
        history_preflight: Any,
        failed_fixtures: int,
        model_summary: dict[str, Any],
        models: list[str],
    ) -> dict[str, Any] | None:
        failed_models = 0
        for key in models:
            m = model_summary.get(key)
            if isinstance(m, dict) and int(m.get("predictions_available") or 0) == 0:
                failed_models += 1

        if not history_preflight.insufficient_history and failed_fixtures == 0 and failed_models == 0:
            return None

        return {
            "reason": history_preflight.reason or "WARNINGS",
            "message": history_preflight.message,
            "failed_fixtures_count": failed_fixtures,
            "failed_models_count": failed_models,
            "data_quality_status": history_preflight.data_quality_status,
            "preflight": history_preflight.to_dict(),
        }

    def delete_analysis(self, db: Session, analysis_id: int) -> RoundAnalysisDeleteResponse:
        analysis = db.get(BacktestRoundAnalysis, int(analysis_id))
        if analysis is None:
            raise_backtest_http(404, "analysis_not_found", "Analisi non trovata.")

        deleted_fixture_results = int(
            db.scalar(
                select(func.count())
                .select_from(BacktestRoundFixtureResult)
                .where(BacktestRoundFixtureResult.analysis_id == int(analysis_id)),
            )
            or 0,
        )
        db.delete(analysis)
        db.commit()
        return RoundAnalysisDeleteResponse(
            deleted_analysis_id=int(analysis_id),
            deleted_fixture_results=deleted_fixture_results,
        )

    def list_analyses(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "round_number",
        sort_dir: str = "desc",
    ) -> RoundAnalysisListResponse:
        clauses = [
            BacktestRoundAnalysis.competition_id == int(competition_id),
            BacktestRoundAnalysis.season_year == int(season_year),
        ]
        total = int(db.scalar(select(func.count()).select_from(BacktestRoundAnalysis).where(*clauses)) or 0)
        safe_sort_by = sort_by if sort_by in ("round_number", "created_at") else "round_number"
        safe_sort_dir = sort_dir if sort_dir in ("asc", "desc") else "desc"
        rows = db.scalars(
            select(BacktestRoundAnalysis)
            .where(*clauses)
            .order_by(*_list_order_clauses(safe_sort_by, safe_sort_dir))
            .offset(max(0, offset))
            .limit(max(1, min(limit, 100))),
        ).all()

        items: list[RoundAnalysisListItem] = []
        for row in rows:
            meta = self._analysis_meta(row)
            items.append(
                RoundAnalysisListItem(
                    id=int(row.id),
                    competition_id=int(row.competition_id),
                    season_year=int(row.season_year),
                    season_label=meta["season_label"],
                    round_number=int(row.round_number),
                    analysis_version=int(row.analysis_version),
                    status=str(row.status),
                    status_label=meta["status_label"],
                    status_reason=meta["status_reason"],
                    mode=str(row.mode),
                    total_fixtures=int(row.total_fixtures),
                    processed_fixtures=int(row.processed_fixtures),
                    failed_fixtures=int(row.failed_fixtures),
                    progress_pct=float(row.progress_pct),
                    data_quality_badge=meta["data_quality_badge"],
                    data_quality_status=meta["data_quality_status"],
                    accordion_summary=meta["accordion_summary"],
                    created_at=row.created_at,
                    completed_at=row.completed_at,
                ),
            )

        return RoundAnalysisListResponse(items=items, total=total, limit=limit, offset=offset)

    def get_detail(self, db: Session, analysis_id: int) -> RoundAnalysisDetailResponse:
        analysis = db.get(BacktestRoundAnalysis, int(analysis_id))
        if analysis is None:
            raise_backtest_http(404, "analysis_not_found", "Analisi non trovata.")

        fixtures = db.scalars(
            select(BacktestRoundFixtureResult)
            .where(BacktestRoundFixtureResult.analysis_id == int(analysis.id))
            .order_by(BacktestRoundFixtureResult.id.asc()),
        ).all()

        meta = self._analysis_meta(analysis)
        failed_models = self._count_failed_models(analysis)

        return RoundAnalysisDetailResponse(
            id=int(analysis.id),
            competition_id=int(analysis.competition_id),
            season_year=int(analysis.season_year),
            season_label=meta["season_label"],
            round_number=int(analysis.round_number),
            analysis_version=int(analysis.analysis_version),
            status=str(analysis.status),
            status_label=meta["status_label"],
            status_reason=meta["status_reason"],
            data_quality_status=meta["data_quality_status"],
            mode=str(analysis.mode),
            config_json=dict(analysis.config_json or {}),
            total_fixtures=int(analysis.total_fixtures),
            processed_fixtures=int(analysis.processed_fixtures),
            failed_fixtures=int(analysis.failed_fixtures),
            failed_models_count=failed_models,
            progress_pct=float(analysis.progress_pct),
            data_quality_summary_json=analysis.data_quality_summary_json,
            model_summary_json=analysis.model_summary_json,
            error_json=analysis.error_json,
            first_recommended_round=meta["first_recommended_round"],
            created_at=analysis.created_at,
            completed_at=analysis.completed_at,
            fixtures=[
                RoundAnalysisFixtureRow(
                    id=int(f.id),
                    fixture_id=int(f.fixture_id),
                    round_number=f.round_number,
                    home_team_name=f.home_team_name,
                    away_team_name=f.away_team_name,
                    actual_home_sot=f.actual_home_sot,
                    actual_away_sot=f.actual_away_sot,
                    actual_total_sot=f.actual_total_sot,
                    models_json=dict(f.models_json or {}),
                    explanation_json=f.explanation_json,
                    status=str(f.status),
                    error_message=f.error_message,
                )
                for f in fixtures
            ],
        )

    def _analysis_meta(self, analysis: BacktestRoundAnalysis) -> dict[str, Any]:
        cfg = analysis.config_json if isinstance(analysis.config_json, dict) else {}
        dq = analysis.data_quality_summary_json if isinstance(analysis.data_quality_summary_json, dict) else {}
        err = analysis.error_json if isinstance(analysis.error_json, dict) else {}
        season_label = str(cfg.get("season_label") or season_label_from_year(int(analysis.season_year)))
        first_rec = cfg.get("first_recommended_round") or dq.get("first_recommended_round")
        status_reason = err.get("reason") if err else dq.get("details", {}).get("preflight", {}).get("reason")
        if isinstance(status_reason, dict):
            status_reason = None
        message = err.get("message") if err else None
        if message and status_reason:
            status_reason = f"{status_reason}: {message}"
        elif message:
            status_reason = str(message)

        return {
            "season_label": season_label,
            "status_label": _STATUS_LABELS.get(str(analysis.status), str(analysis.status)),
            "status_reason": status_reason,
            "data_quality_badge": dq.get("badge"),
            "data_quality_status": dq.get("data_quality_status") or dq.get("badge"),
            "accordion_summary": dq.get("accordion_summary"),
            "first_recommended_round": int(first_rec) if first_rec is not None else None,
        }

    def _count_failed_models(self, analysis: BacktestRoundAnalysis) -> int:
        ms = analysis.model_summary_json if isinstance(analysis.model_summary_json, dict) else {}
        n = 0
        for _key, m in ms.items():
            if isinstance(m, dict) and int(m.get("predictions_available") or 0) == 0:
                n += 1
        return n

    def _latest_completed(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        round_number: int,
    ) -> BacktestRoundAnalysis | None:
        return db.scalar(
            select(BacktestRoundAnalysis)
            .where(
                BacktestRoundAnalysis.competition_id == int(competition_id),
                BacktestRoundAnalysis.season_year == int(season_year),
                BacktestRoundAnalysis.round_number == int(round_number),
                BacktestRoundAnalysis.status == "completed",
            )
            .order_by(BacktestRoundAnalysis.analysis_version.desc())
            .limit(1),
        )

    def _next_version(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        round_number: int,
    ) -> int:
        current = db.scalar(
            select(func.max(BacktestRoundAnalysis.analysis_version)).where(
                BacktestRoundAnalysis.competition_id == int(competition_id),
                BacktestRoundAnalysis.season_year == int(season_year),
                BacktestRoundAnalysis.round_number == int(round_number),
            ),
        )
        return int(current or 0) + 1

    def _save_failed_fixture(
        self,
        db: Session,
        *,
        analysis: BacktestRoundAnalysis,
        cand: Any,
        message: str,
        fx: Fixture | None = None,
    ) -> None:
        row = BacktestRoundFixtureResult(
            analysis_id=int(analysis.id),
            fixture_id=int(cand.fixture_id),
            round_number=int(analysis.round_number),
            home_team_name=cand.home_team.name,
            away_team_name=cand.away_team.name,
            actual_total_sot=cand.actual_total_sot,
            models_json={},
            explanation_json={},
            status="failed",
            error_message=message,
        )
        if fx is not None:
            stats = db.scalars(
                select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fx.id)),
            ).all()
            for st in stats:
                if int(st.team_id) == int(fx.home_team_id) and st.shots_on_target is not None:
                    row.actual_home_sot = int(st.shots_on_target)
                if int(st.team_id) == int(fx.away_team_id) and st.shots_on_target is not None:
                    row.actual_away_sot = int(st.shots_on_target)
        db.add(row)
        db.commit()

    def _actual_side_sots(self, db: Session, fx: Fixture) -> tuple[int | None, int | None]:
        stats = db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fx.id)),
        ).all()
        home_sot = away_sot = None
        for st in stats:
            if int(st.team_id) == int(fx.home_team_id) and st.shots_on_target is not None:
                home_sot = int(st.shots_on_target)
            if int(st.team_id) == int(fx.away_team_id) and st.shots_on_target is not None:
                away_sot = int(st.shots_on_target)
        return home_sot, away_sot

    def _fixture_row_dict(self, row: BacktestRoundFixtureResult) -> dict[str, Any]:
        return {
            "status": row.status,
            "actual_total_sot": row.actual_total_sot,
            "models_json": dict(row.models_json or {}),
            "explanation_json": dict(row.explanation_json or {}),
        }
