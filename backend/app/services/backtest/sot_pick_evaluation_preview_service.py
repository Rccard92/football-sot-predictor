"""Pick evaluation read-only Over/Under SOT su prediction PIT (Step H)."""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI, BACKTEST_MODE_PRE_LINEUP
from app.backtest.errors import raise_backtest_http
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Competition
from app.schemas.backtest_sot_pick_evaluation import (
    SotPickBreakdownActualTotalBucketStats,
    SotPickBreakdownConfidenceStats,
    SotPickBreakdownLineStats,
    SotPickBreakdownSampleBucketStats,
    SotPickBreakdownSideStats,
    SotPickEvaluationFailedFixture,
    SotPickEvaluationFixtureResult,
    SotPickEvaluationResponse,
    SotPickEvaluationSelection,
    SotPickEvaluationSummary,
    SotPickLineEvaluation,
    SotPickRecommendedPick,
)
from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.sot_pick_evaluation_logic import (
    ConfidenceSignals,
    apply_confidence_caps,
    collect_candidates,
    compute_base_confidence,
    compute_pick_outcome,
    player_layer_is_neutral,
    round4,
    sample_bucket_key,
    select_recommended_pick,
)
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


def _hit_rate(wins: int, losses: int) -> float | None:
    total = wins + losses
    if total <= 0:
        return None
    return _round4(100.0 * wins / total)


def _extract_http_error(exc: HTTPException) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("code") or "preview_failed"), str(detail.get("message") or "Preview failed")
    return "preview_failed", str(detail)


def _player_layer_status(preview: SotV21PreviewResponse, side: str) -> str | None:
    trace = preview.home_trace if side == "home" else preview.away_trace
    for macro in trace.macros:
        if macro.key == "player_layer":
            return macro.status
    return None


def _evaluate_fixture(
    preview: SotV21PreviewResponse,
    *,
    lines: list[float],
    min_edge: float,
    mode: str,
) -> SotPickEvaluationFixtureResult:
    predicted = preview.prediction.total_predicted_sot
    actual = preview.actuals_for_scoring.actual_total_sot
    total_abs_error = preview.errors.total_abs_error

    line_evals, candidates = collect_candidates(
        float(predicted) if predicted is not None else 0.0,
        lines,
        min_edge,
    ) if predicted is not None else ([], [])

    all_line_evaluations = [
        SotPickLineEvaluation(
            line=ev.line,
            edge_over=ev.edge_over,
            edge_under=ev.edge_under,
            over_meets_min_edge=ev.over_meets_min_edge,
            under_meets_min_edge=ev.under_meets_min_edge,
            over_candidate=ev.over_meets_min_edge,
            under_candidate=ev.under_meets_min_edge,
        )
        for ev in line_evals
    ]

    recommended: SotPickRecommendedPick | None = None
    selected = select_recommended_pick(candidates)
    if selected is not None and actual is not None:
        outcome = compute_pick_outcome(selected.side, selected.line, int(actual))
        edge_abs = abs(selected.edge)
        base_conf = compute_base_confidence(edge_abs)
        home_pl = _player_layer_status(preview, "home")
        away_pl = _player_layer_status(preview, "away")
        confidence = apply_confidence_caps(
            base_conf,
            ConfidenceSignals(
                mode=mode,
                min_prior_matches=min(
                    int(preview.home_prior_matches_count),
                    int(preview.away_prior_matches_count),
                ),
                warnings_count=len(preview.warnings),
                player_layer_neutral=player_layer_is_neutral(home_pl, away_pl),
            ),
        )
        recommended = SotPickRecommendedPick(
            side=selected.side,
            line=selected.line,
            edge=round4(selected.edge),
            outcome=outcome,
            confidence=confidence,
        )

    return SotPickEvaluationFixtureResult(
        fixture_id=int(preview.fixture_id),
        match=f"{preview.fixture.home_team} vs {preview.fixture.away_team}",
        round=preview.fixture.round,
        kickoff_at=preview.fixture.kickoff_at,
        predicted_total_sot=_round4(predicted),
        actual_total_sot=actual,
        total_abs_error=total_abs_error,
        recommended_pick=recommended,
        no_pick=recommended is None,
        all_line_evaluations=all_line_evaluations,
        sample_bucket=sample_bucket_key(
            int(preview.home_prior_matches_count),
            int(preview.away_prior_matches_count),
        ),
        actual_total_bucket=(
            "low_total"
            if actual is not None and actual <= 6
            else "medium_total"
            if actual is not None and actual <= 10
            else "high_total"
            if actual is not None
            else None
        ),
        warnings_count=len(preview.warnings),
        leakage_guard=preview.leakage_guard,
        home_prior_matches_count=int(preview.home_prior_matches_count),
        away_prior_matches_count=int(preview.away_prior_matches_count),
    )


def _compute_summary(results: list[SotPickEvaluationFixtureResult], *, failed: int) -> SotPickEvaluationSummary:
    with_pick = [r for r in results if r.recommended_pick is not None]
    no_pick = [r for r in results if r.no_pick]
    wins = [r for r in with_pick if r.recommended_pick and r.recommended_pick.outcome == "win"]
    losses = [r for r in with_pick if r.recommended_pick and r.recommended_pick.outcome == "loss"]
    over_picks = [r for r in with_pick if r.recommended_pick and r.recommended_pick.side == "over"]
    under_picks = [r for r in with_pick if r.recommended_pick and r.recommended_pick.side == "under"]

    return SotPickEvaluationSummary(
        fixtures_processed=len(results),
        fixtures_failed=failed,
        pick_opportunities=len(with_pick),
        no_pick_count=len(no_pick),
        wins=len(wins),
        losses=len(losses),
        hit_rate=_hit_rate(len(wins), len(losses)),
        avg_edge=_mean(
            abs(r.recommended_pick.edge)
            for r in with_pick
            if r.recommended_pick is not None
        ),
        avg_predicted_total_sot=_mean(
            r.predicted_total_sot for r in results if r.predicted_total_sot is not None
        ),
        avg_actual_total_sot=_mean(
            float(r.actual_total_sot) for r in results if r.actual_total_sot is not None
        ),
        avg_total_abs_error=_mean(
            r.total_abs_error for r in results if r.total_abs_error is not None
        ),
        over_picks_count=len(over_picks),
        under_picks_count=len(under_picks),
        over_wins=sum(
            1 for r in over_picks if r.recommended_pick and r.recommended_pick.outcome == "win"
        ),
        over_losses=sum(
            1 for r in over_picks if r.recommended_pick and r.recommended_pick.outcome == "loss"
        ),
        under_wins=sum(
            1 for r in under_picks if r.recommended_pick and r.recommended_pick.outcome == "win"
        ),
        under_losses=sum(
            1 for r in under_picks if r.recommended_pick and r.recommended_pick.outcome == "loss"
        ),
    )


def _breakdown_by_line(results: list[SotPickEvaluationFixtureResult], lines: list[float]) -> list[SotPickBreakdownLineStats]:
    out: list[SotPickBreakdownLineStats] = []
    for line in lines:
        picks = [
            r for r in results
            if r.recommended_pick is not None and r.recommended_pick.line == float(line)
        ]
        wins = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "win")
        losses = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "loss")
        out.append(
            SotPickBreakdownLineStats(
                line=float(line),
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(
                    abs(r.recommended_pick.edge)
                    for r in picks
                    if r.recommended_pick is not None
                ),
            ),
        )
    return out


def _breakdown_by_side(results: list[SotPickEvaluationFixtureResult]) -> list[SotPickBreakdownSideStats]:
    out: list[SotPickBreakdownSideStats] = []
    for side in ("over", "under"):
        picks = [
            r for r in results
            if r.recommended_pick is not None and r.recommended_pick.side == side
        ]
        wins = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "win")
        losses = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "loss")
        out.append(
            SotPickBreakdownSideStats(
                side=side,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(
                    abs(r.recommended_pick.edge)
                    for r in picks
                    if r.recommended_pick is not None
                ),
            ),
        )
    return out


def _breakdown_by_confidence(results: list[SotPickEvaluationFixtureResult]) -> list[SotPickBreakdownConfidenceStats]:
    out: list[SotPickBreakdownConfidenceStats] = []
    for confidence in ("low", "medium", "high"):
        picks = [
            r for r in results
            if r.recommended_pick is not None and r.recommended_pick.confidence == confidence
        ]
        wins = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "win")
        losses = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "loss")
        out.append(
            SotPickBreakdownConfidenceStats(
                confidence=confidence,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(
                    abs(r.recommended_pick.edge)
                    for r in picks
                    if r.recommended_pick is not None
                ),
            ),
        )
    return out


def _breakdown_by_sample_bucket(results: list[SotPickEvaluationFixtureResult]) -> list[SotPickBreakdownSampleBucketStats]:
    buckets = ("early_low_sample", "medium_sample", "stable_sample")
    out: list[SotPickBreakdownSampleBucketStats] = []
    for bucket in buckets:
        picks = [
            r for r in results
            if r.recommended_pick is not None and r.sample_bucket == bucket
        ]
        wins = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "win")
        losses = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "loss")
        out.append(
            SotPickBreakdownSampleBucketStats(
                bucket=bucket,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(
                    abs(r.recommended_pick.edge)
                    for r in picks
                    if r.recommended_pick is not None
                ),
            ),
        )
    return out


def _breakdown_by_actual_total_bucket(
    results: list[SotPickEvaluationFixtureResult],
) -> list[SotPickBreakdownActualTotalBucketStats]:
    buckets = ("low_total", "medium_total", "high_total")
    out: list[SotPickBreakdownActualTotalBucketStats] = []
    for bucket in buckets:
        picks = [
            r for r in results
            if r.recommended_pick is not None and r.actual_total_bucket == bucket
        ]
        wins = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "win")
        losses = sum(1 for r in picks if r.recommended_pick and r.recommended_pick.outcome == "loss")
        out.append(
            SotPickBreakdownActualTotalBucketStats(
                bucket=bucket,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(
                    abs(r.recommended_pick.edge)
                    for r in picks
                    if r.recommended_pick is not None
                ),
            ),
        )
    return out


class SotPickEvaluationPreviewService:
    def run_pick_evaluation(
        self,
        db: Session,
        *,
        competition_id: int,
        mode: str = BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
        limit: int = 20,
        offset: int = 0,
        round_number: int | None = None,
        round_contains: str | None = None,
        fixture_ids: list[int] | None = None,
        lines: list[float] | None = None,
        min_edge: float = 0.75,
        include_no_pick: bool = True,
    ) -> SotPickEvaluationResponse:
        if mode not in (BACKTEST_MODE_PRE_LINEUP, BACKTEST_MODE_HISTORICAL_OFFICIAL_XI):
            raise_backtest_http(
                422,
                "mode_not_supported_yet",
                "Pick evaluation supporta pre_lineup e historical_official_xi.",
                mode=mode,
            )

        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        eval_lines = list(lines) if lines else [5.5, 6.5, 7.5, 8.5, 9.5]

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
        results: list[SotPickEvaluationFixtureResult] = []
        failed_fixtures: list[SotPickEvaluationFailedFixture] = []

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
                    SotPickEvaluationFailedFixture(
                        fixture_id=int(candidate.fixture_id),
                        error_code=code,
                        message=message,
                    ),
                )
                continue

            if not preview.leakage_guard:
                failed_fixtures.append(
                    SotPickEvaluationFailedFixture(
                        fixture_id=int(candidate.fixture_id),
                        error_code="leakage_guard_failed",
                        message="Fixture invalidata: leakage_guard=false",
                    ),
                )
                continue

            if preview.actuals_for_scoring.actual_total_sot is None:
                failed_fixtures.append(
                    SotPickEvaluationFailedFixture(
                        fixture_id=int(candidate.fixture_id),
                        error_code="actual_total_sot_missing",
                        message="Fixture invalidata: actual_total_sot mancante",
                    ),
                )
                continue

            if preview.prediction.total_predicted_sot is None:
                failed_fixtures.append(
                    SotPickEvaluationFailedFixture(
                        fixture_id=int(candidate.fixture_id),
                        error_code="predicted_total_sot_missing",
                        message="Fixture invalidata: predicted_total_sot mancante",
                    ),
                )
                continue

            row = _evaluate_fixture(
                preview,
                lines=eval_lines,
                min_edge=float(min_edge),
                mode=mode,
            )
            results.append(row)

        if not include_no_pick:
            results = [r for r in results if r.recommended_pick is not None]

        failed_count = len(failed_fixtures)
        if len(results) == 0 and failed_count > 0:
            status = "error"
        elif failed_count > 0:
            status = "partial_ok"
        else:
            status = "ok"

        if round_number is not None:
            round_filter_mode = "exact_round_number"
            selection_round_contains = None
        elif round_contains and round_contains.strip():
            round_filter_mode = "text_contains"
            selection_round_contains = round_contains
        else:
            round_filter_mode = "none"
            selection_round_contains = None

        return SotPickEvaluationResponse(
            status=status,
            preview_only=True,
            db_writes=False,
            market_key="shots_on_target",
            algorithm_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            mode=mode,
            competition_id=int(competition_id),
            competition_name=str(comp.name),
            selection=SotPickEvaluationSelection(
                limit=int(limit),
                offset=int(offset),
                round_number=int(round_number) if round_number is not None else None,
                round_contains=selection_round_contains,
                round_filter_mode=round_filter_mode,
                fixture_ids=fixture_ids,
                lines=eval_lines,
                min_edge=float(min_edge),
                include_no_pick=include_no_pick,
                order_by=selection.order_by,
            ),
            summary=_compute_summary(results, failed=failed_count),
            breakdown_by_line=_breakdown_by_line(results, eval_lines),
            breakdown_by_side=_breakdown_by_side(results),
            breakdown_by_confidence=_breakdown_by_confidence(results),
            breakdown_by_sample_bucket=_breakdown_by_sample_bucket(results),
            breakdown_by_actual_total_bucket=_breakdown_by_actual_total_bucket(results),
            results=results,
            failed_fixtures=failed_fixtures,
            feature_snapshot_json={
                "preview_only": True,
                "pick_evaluation": True,
                "include_no_pick": include_no_pick,
            },
        )
