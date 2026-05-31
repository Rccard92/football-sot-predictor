"""Mini-run read-only SOT v2.1 point-in-time su più fixture (Step F)."""

from __future__ import annotations

import math
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backtest.errors import raise_backtest_http
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Competition
from app.schemas.backtest_sot_v21_mini_run import (
    SotV21MiniRunActualTotalBreakdown,
    SotV21MiniRunBucketStats,
    SotV21MiniRunCaseBrief,
    SotV21MiniRunFailedFixture,
    SotV21MiniRunFixtureResult,
    SotV21MiniRunResponse,
    SotV21MiniRunSampleBreakdown,
    SotV21MiniRunSelection,
    SotV21MiniRunSplitSummary,
    SotV21MiniRunSummary,
)
from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.sot_v21_preview_service import SotV21PointInTimePreviewService


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _mean(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return _round4(sum(items) / len(items))


def _extract_http_error(exc: HTTPException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code") or "preview_failed"), str(detail.get("message") or "Preview failed")
    return "preview_failed", str(detail)


def _sample_bucket_key(home_prior: int, away_prior: int) -> str:
    min_prior = min(home_prior, away_prior)
    if min_prior < 5:
        return "early_low_sample"
    if min_prior <= 14:
        return "medium_sample"
    return "stable_sample"


def _actual_total_bucket_key(actual_total: int | None) -> str | None:
    if actual_total is None:
        return None
    if actual_total <= 6:
        return "low_total"
    if actual_total <= 10:
        return "medium_total"
    return "high_total"


def _compute_bucket_stats(results: list[SotV21MiniRunFixtureResult]) -> SotV21MiniRunBucketStats:
    scored = [r for r in results if r.total_abs_error is not None]
    if not scored:
        return SotV21MiniRunBucketStats(fixtures_count=len(results))
    return SotV21MiniRunBucketStats(
        fixtures_count=len(results),
        total_mae=_mean(r.total_abs_error for r in scored if r.total_abs_error is not None),
        total_bias=_mean(r.total_error for r in scored if r.total_error is not None),
        avg_predicted_total_sot=_mean(
            r.predicted_total_sot for r in scored if r.predicted_total_sot is not None
        ),
        avg_actual_total_sot=_mean(r.actual_total_sot for r in scored if r.actual_total_sot is not None),
    )


def _extract_split_macro(side_trace) -> tuple[float | None, str | None]:
    if side_trace is None:
        return None, None
    for macro in side_trace.macros:
        if macro.key == "home_away_split":
            return macro.macro_index, macro.status
    return None, None


def _fixture_split_bucket(home_status: str | None, away_status: str | None) -> str:
    statuses = [s for s in (home_status, away_status) if s]
    if not statuses:
        return "fallback"
    if "neutral_fallback" in statuses:
        return "fallback"
    if "partial_low_sample" in statuses:
        return "partial"
    if all(s == "available" for s in statuses):
        return "available"
    return "fallback"


def _aggregate_split_summary(previews: list[SotV21PreviewResponse]) -> SotV21MiniRunSplitSummary:
    available = partial = fallback = 0
    home_indexes: list[float] = []
    away_indexes: list[float] = []

    for preview in previews:
        home_idx, home_status = _extract_split_macro(preview.home_trace)
        away_idx, away_status = _extract_split_macro(preview.away_trace)
        bucket = _fixture_split_bucket(home_status, away_status)
        if bucket == "available":
            available += 1
        elif bucket == "partial":
            partial += 1
        else:
            fallback += 1
        if home_idx is not None:
            home_indexes.append(float(home_idx))
        if away_idx is not None:
            away_indexes.append(float(away_idx))

    return SotV21MiniRunSplitSummary(
        available_count=available,
        partial_count=partial,
        fallback_count=fallback,
        avg_home_split_index=_mean(home_indexes),
        avg_away_split_index=_mean(away_indexes),
    )


def _compute_summary(results: list[SotV21MiniRunFixtureResult], *, requested: int, failed: int) -> SotV21MiniRunSummary:
    scored = [r for r in results if r.total_abs_error is not None]
    home_scored = [r for r in results if r.home_error is not None]
    away_scored = [r for r in results if r.away_error is not None]

    total_sq = [float(r.total_error) ** 2 for r in scored if r.total_error is not None]
    total_rmse = None
    if total_sq:
        total_rmse = _round4(math.sqrt(sum(total_sq) / len(total_sq)))

    over = sum(1 for r in scored if r.total_error is not None and r.total_error > 0)
    under = sum(1 for r in scored if r.total_error is not None and r.total_error < 0)
    exact_near = sum(1 for r in scored if r.total_abs_error is not None and r.total_abs_error <= 1.0)
    high_error = sum(1 for r in scored if r.total_abs_error is not None and r.total_abs_error >= 3.0)

    return SotV21MiniRunSummary(
        fixtures_requested=requested,
        fixtures_processed=len(results),
        fixtures_failed=failed,
        total_mae=_mean(r.total_abs_error for r in scored if r.total_abs_error is not None),
        home_mae=_mean(abs(r.home_error) for r in home_scored if r.home_error is not None),
        away_mae=_mean(abs(r.away_error) for r in away_scored if r.away_error is not None),
        total_rmse=total_rmse,
        total_bias=_mean(r.total_error for r in scored if r.total_error is not None),
        home_bias=_mean(r.home_error for r in home_scored if r.home_error is not None),
        away_bias=_mean(r.away_error for r in away_scored if r.away_error is not None),
        avg_predicted_total_sot=_mean(
            r.predicted_total_sot for r in scored if r.predicted_total_sot is not None
        ),
        avg_actual_total_sot=_mean(r.actual_total_sot for r in scored if r.actual_total_sot is not None),
        overestimated_count=over,
        underestimated_count=under,
        exact_or_near_count=exact_near,
        high_error_count=high_error,
    )


def _compute_sample_breakdown(results: list[SotV21MiniRunFixtureResult]) -> SotV21MiniRunSampleBreakdown:
    buckets: dict[str, list[SotV21MiniRunFixtureResult]] = {
        "early_low_sample": [],
        "medium_sample": [],
        "stable_sample": [],
    }
    for row in results:
        buckets[_sample_bucket_key(row.home_prior_matches_count, row.away_prior_matches_count)].append(row)
    return SotV21MiniRunSampleBreakdown(
        early_low_sample=_compute_bucket_stats(buckets["early_low_sample"]),
        medium_sample=_compute_bucket_stats(buckets["medium_sample"]),
        stable_sample=_compute_bucket_stats(buckets["stable_sample"]),
    )


def _compute_actual_total_breakdown(results: list[SotV21MiniRunFixtureResult]) -> SotV21MiniRunActualTotalBreakdown:
    buckets: dict[str, list[SotV21MiniRunFixtureResult]] = {
        "low_total": [],
        "medium_total": [],
        "high_total": [],
    }
    for row in results:
        key = _actual_total_bucket_key(row.actual_total_sot)
        if key:
            buckets[key].append(row)
    return SotV21MiniRunActualTotalBreakdown(
        low_total=_compute_bucket_stats(buckets["low_total"]),
        medium_total=_compute_bucket_stats(buckets["medium_total"]),
        high_total=_compute_bucket_stats(buckets["high_total"]),
    )


def _to_case_brief(row: SotV21MiniRunFixtureResult) -> SotV21MiniRunCaseBrief:
    return SotV21MiniRunCaseBrief(
        fixture_id=row.fixture_id,
        kickoff_at=row.kickoff_at,
        round=row.round,
        home_team=row.home_team,
        away_team=row.away_team,
        predicted_home_sot=row.predicted_home_sot,
        predicted_away_sot=row.predicted_away_sot,
        predicted_total_sot=row.predicted_total_sot,
        actual_home_sot=row.actual_home_sot,
        actual_away_sot=row.actual_away_sot,
        actual_total_sot=row.actual_total_sot,
        total_error=row.total_error,
        total_abs_error=row.total_abs_error,
        home_prior_matches_count=row.home_prior_matches_count,
        away_prior_matches_count=row.away_prior_matches_count,
        warnings_count=len(row.warnings),
    )


def _worst_best_cases(results: list[SotV21MiniRunFixtureResult], n: int = 5) -> tuple[list[SotV21MiniRunCaseBrief], list[SotV21MiniRunCaseBrief]]:
    scored = [r for r in results if r.total_abs_error is not None]
    if not scored:
        return [], []
    worst = sorted(scored, key=lambda r: float(r.total_abs_error or 0), reverse=True)[:n]
    best = sorted(scored, key=lambda r: float(r.total_abs_error or 0))[:n]
    return [_to_case_brief(r) for r in worst], [_to_case_brief(r) for r in best]


def _preview_to_result(
    preview: SotV21PreviewResponse,
    *,
    include_trace: bool,
) -> SotV21MiniRunFixtureResult:
    actuals = preview.actuals_for_scoring
    errors = preview.errors
    pred = preview.prediction
    return SotV21MiniRunFixtureResult(
        fixture_id=int(preview.fixture_id),
        round=preview.fixture.round,
        kickoff_at=preview.fixture.kickoff_at,
        home_team=preview.fixture.home_team,
        away_team=preview.fixture.away_team,
        predicted_home_sot=pred.home_predicted_sot,
        predicted_away_sot=pred.away_predicted_sot,
        predicted_total_sot=pred.total_predicted_sot,
        actual_home_sot=actuals.actual_home_sot,
        actual_away_sot=actuals.actual_away_sot,
        actual_total_sot=actuals.actual_total_sot,
        home_error=errors.home_error,
        away_error=errors.away_error,
        total_error=errors.total_error,
        total_abs_error=errors.total_abs_error,
        leakage_guard=preview.leakage_guard,
        actuals_used_as_input=preview.actuals_used_as_input,
        latest_fixture_used_at=preview.latest_fixture_used_at,
        cutoff_time=preview.cutoff_time,
        home_prior_matches_count=int(preview.home_prior_matches_count),
        away_prior_matches_count=int(preview.away_prior_matches_count),
        warnings=list(preview.warnings),
        home_trace=preview.home_trace if include_trace else None,
        away_trace=preview.away_trace if include_trace else None,
    )


class SotV21MiniRunPreviewService:
    def run_preview(
        self,
        db: Session,
        *,
        competition_id: int,
        mode: str = "pre_lineup",
        limit: int = 20,
        offset: int = 0,
        round_number: int | None = None,
        round_contains: str | None = None,
        fixture_ids: list[int] | None = None,
        include_trace: bool = False,
    ) -> SotV21MiniRunResponse:
        if mode != "pre_lineup":
            raise_backtest_http(
                422,
                "mode_not_supported_yet",
                "La mini-run supporta solo pre_lineup in questa fase.",
                mode=mode,
            )

        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        selection = BacktestFixtureDebugService().select_fixtures_for_mini_run(
            db,
            competition_id=int(competition_id),
            limit=int(limit),
            offset=int(offset),
            round_number=round_number,
            round_contains=round_contains if round_number is None else None,
            fixture_ids=fixture_ids,
            order_by="kickoff_at asc",
        )

        preview_svc = SotV21PointInTimePreviewService()
        results: list[SotV21MiniRunFixtureResult] = []
        failed_fixtures: list[SotV21MiniRunFailedFixture] = []
        trace_included_count = 0
        preview_snapshots: list[SotV21PreviewResponse] = []

        for candidate in selection.items:
            try:
                preview = preview_svc.build_preview(
                    db,
                    competition_id=int(competition_id),
                    fixture_id=int(candidate.fixture_id),
                    mode=mode,
                )
            except HTTPException as exc:
                code, message = _extract_http_error(exc)
                failed_fixtures.append(
                    SotV21MiniRunFailedFixture(
                        fixture_id=int(candidate.fixture_id),
                        error_code=code,
                        message=message,
                    ),
                )
                continue

            preview_snapshots.append(preview)
            with_trace = include_trace and trace_included_count < 10
            result = _preview_to_result(preview, include_trace=with_trace)
            results.append(result)
            if with_trace:
                trace_included_count += 1

        failed_count = len(failed_fixtures)
        if len(results) == 0 and failed_count > 0:
            status = "error"
        elif failed_count > 0:
            status = "partial_ok"
        else:
            status = "ok"

        summary = _compute_summary(
            results,
            requested=selection.fixtures_requested,
            failed=failed_count,
        )
        worst, best = _worst_best_cases(results)

        if round_number is not None:
            round_filter_mode = "exact_round_number"
            selection_round_contains = None
        elif round_contains and round_contains.strip():
            round_filter_mode = "text_contains"
            selection_round_contains = round_contains
        else:
            round_filter_mode = "none"
            selection_round_contains = None

        return SotV21MiniRunResponse(
            status=status,
            preview_only=True,
            market_key="shots_on_target",
            algorithm_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            competition_id=int(competition_id),
            competition_name=str(comp.name),
            mode=mode,
            selection=SotV21MiniRunSelection(
                limit=int(limit),
                offset=int(offset),
                round_number=int(round_number) if round_number is not None else None,
                round_contains=selection_round_contains,
                round_filter_mode=round_filter_mode,
                fixture_ids=fixture_ids,
                order_by=selection.order_by,
            ),
            summary=summary,
            split_summary=_aggregate_split_summary(preview_snapshots),
            sample_breakdown=_compute_sample_breakdown(results),
            actual_total_breakdown=_compute_actual_total_breakdown(results),
            worst_cases=worst,
            best_cases=best,
            results=results,
            failed_fixtures=failed_fixtures,
            db_writes=False,
            feature_snapshot_json={
                "preview_only": True,
                "mini_run": True,
                "include_trace": include_trace,
                "trace_included_count": trace_included_count,
            },
        )
