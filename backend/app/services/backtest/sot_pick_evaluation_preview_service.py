"""Pick evaluation read-only Over SOT su prediction PIT (Step H / H.1)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI, BACKTEST_MODE_PRE_LINEUP
from app.backtest.errors import raise_backtest_http
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Competition
from app.schemas.backtest_sot_pick_evaluation import (
    SotPickAdvisedSummary,
    SotPickBreakdownActualTotalBucketStats,
    SotPickBreakdownConfidenceStats,
    SotPickBreakdownLineStats,
    SotPickBreakdownSampleBucketStats,
    SotPickCalculatedSummary,
    SotPickEvaluationFailedFixture,
    SotPickEvaluationFixtureResult,
    SotPickEvaluationResponse,
    SotPickEvaluationSelection,
    SotPickOverPick,
    SotPickPlayAdvice,
)
from app.schemas.backtest_sot_v21_preview import SotV21PreviewResponse
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.backtest.sot_pick_evaluation_logic import (
    DEFAULT_PICK_LINES,
    ConfidenceSignals,
    OverPickResult,
    actual_total_bucket_key,
    evaluate_over_picks,
    player_layer_is_neutral,
    sample_bucket_key,
)
from app.services.backtest.sot_pick_play_advice_logic import (
    PlayAdviceConfig,
    PlayAdviceResult,
    PlayAdviceSignals,
    compute_play_advice,
    detect_player_layer_fallback,
    detect_split_fallback,
    is_playable_advice,
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


def _to_play_advice_schema(advice: PlayAdviceResult) -> SotPickPlayAdvice:
    return SotPickPlayAdvice(
        play_advice=advice.play_advice,
        play_advice_label=advice.play_advice_label,
        playability_score=advice.playability_score,
        advice_reasons=list(advice.advice_reasons),
        advice_summary=advice.advice_summary,
    )


def _to_over_pick(
    pick: OverPickResult | None,
    advice: PlayAdviceResult | None,
) -> SotPickOverPick | None:
    if pick is None:
        return None
    return SotPickOverPick(
        side=pick.side,
        line=pick.line,
        edge=pick.edge,
        outcome=pick.outcome,
        confidence=pick.confidence,
        play_advice=_to_play_advice_schema(advice) if advice else None,
    )


def _build_advice_signals(
    preview: SotV21PreviewResponse,
    *,
    pick_kind: str,
    no_line_available: bool,
    no_lower_line: bool,
    bucket: str,
) -> PlayAdviceSignals:
    home_pl = _player_layer_status(preview, "home")
    away_pl = _player_layer_status(preview, "away")
    return PlayAdviceSignals(
        min_prior_matches=min(
            int(preview.home_prior_matches_count),
            int(preview.away_prior_matches_count),
        ),
        warnings_count=len(preview.warnings),
        sample_bucket=bucket,
        player_layer_fallback=detect_player_layer_fallback(
            home_pl,
            away_pl,
            list(preview.fallback_variables),
        ),
        split_fallback=detect_split_fallback(
            preview.home_trace.macros,
            preview.away_trace.macros,
            list(preview.fallback_variables),
        ),
        pick_kind=pick_kind,  # type: ignore[arg-type]
        no_line_available=no_line_available,
        no_lower_line=no_lower_line,
    )


def _evaluate_fixture(
    preview: SotV21PreviewResponse,
    *,
    lines: list[float],
    cautious_drop_threshold: float,
    play_advice_config: PlayAdviceConfig,
) -> SotPickEvaluationFixtureResult:
    predicted = float(preview.prediction.total_predicted_sot)  # type: ignore[arg-type]
    actual = preview.actuals_for_scoring.actual_total_sot
    home_pl = _player_layer_status(preview, "home")
    away_pl = _player_layer_status(preview, "away")
    bucket = sample_bucket_key(
        int(preview.home_prior_matches_count),
        int(preview.away_prior_matches_count),
    )
    signals = ConfidenceSignals(
        min_prior_matches=min(
            int(preview.home_prior_matches_count),
            int(preview.away_prior_matches_count),
        ),
        warnings_count=len(preview.warnings),
        player_layer_neutral=player_layer_is_neutral(home_pl, away_pl),
    )

    aggressive, cautious, fixture_warnings = evaluate_over_picks(
        predicted,
        lines,
        actual,
        cautious_drop_threshold=cautious_drop_threshold,
        signals=signals,
    )

    no_lower_line = "no_lower_cautious_line_available" in fixture_warnings
    agg_advice = compute_play_advice(
        aggressive,
        _build_advice_signals(
            preview,
            pick_kind="aggressive",
            no_line_available=aggressive is None,
            no_lower_line=False,
            bucket=bucket,
        ),
        play_advice_config,
    )
    caut_advice = compute_play_advice(
        cautious,
        _build_advice_signals(
            preview,
            pick_kind="cautious",
            no_line_available=cautious is None,
            no_lower_line=no_lower_line,
            bucket=bucket,
        ),
        play_advice_config,
    )

    return SotPickEvaluationFixtureResult(
        fixture_id=int(preview.fixture_id),
        match=f"{preview.fixture.home_team} vs {preview.fixture.away_team}",
        round=preview.fixture.round,
        kickoff_at=preview.fixture.kickoff_at,
        predicted_total_sot=_round4(predicted),
        actual_total_sot=actual,
        total_abs_error=preview.errors.total_abs_error,
        aggressive_pick=_to_over_pick(aggressive, agg_advice),
        cautious_pick=_to_over_pick(cautious, caut_advice),
        no_aggressive_pick=aggressive is None,
        no_cautious_pick=cautious is None,
        warnings=fixture_warnings,
        sample_bucket=bucket,
        actual_total_bucket=actual_total_bucket_key(actual),
        warnings_count=len(preview.warnings),
        leakage_guard=preview.leakage_guard,
        home_prior_matches_count=int(preview.home_prior_matches_count),
        away_prior_matches_count=int(preview.away_prior_matches_count),
    )


def _strategy_stats(
    results: list[SotPickEvaluationFixtureResult],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
    no_pick_getter: Callable[[SotPickEvaluationFixtureResult], bool],
) -> tuple[int, int, int, int, float | None]:
    with_pick = [r for r in results if pick_getter(r) is not None]
    wins = sum(1 for r in with_pick if pick_getter(r) and pick_getter(r).outcome == "win")
    losses = sum(1 for r in with_pick if pick_getter(r) and pick_getter(r).outcome == "loss")
    return (
        len(with_pick),
        sum(1 for r in results if no_pick_getter(r)),
        wins,
        losses,
        _hit_rate(wins, losses),
    )


def _compute_calculated_summary(
    results: list[SotPickEvaluationFixtureResult],
    *,
    failed: int,
) -> SotPickCalculatedSummary:
    agg_picks, agg_no, agg_w, agg_l, agg_hr = _strategy_stats(
        results,
        lambda r: r.aggressive_pick,
        lambda r: r.no_aggressive_pick,
    )
    caut_picks, caut_no, caut_w, caut_l, caut_hr = _strategy_stats(
        results,
        lambda r: r.cautious_pick,
        lambda r: r.no_cautious_pick,
    )
    return SotPickCalculatedSummary(
        fixtures_processed=len(results),
        fixtures_failed=failed,
        aggressive_calculated_count=agg_picks,
        aggressive_no_pick_count=agg_no,
        aggressive_wins=agg_w,
        aggressive_losses=agg_l,
        aggressive_hit_rate=agg_hr,
        cautious_calculated_count=caut_picks,
        cautious_no_pick_count=caut_no,
        cautious_wins=caut_w,
        cautious_losses=caut_l,
        cautious_hit_rate=caut_hr,
        avg_predicted_total_sot=_mean(
            r.predicted_total_sot for r in results if r.predicted_total_sot is not None
        ),
        avg_actual_total_sot=_mean(
            float(r.actual_total_sot) for r in results if r.actual_total_sot is not None
        ),
        avg_total_abs_error=_mean(
            r.total_abs_error for r in results if r.total_abs_error is not None
        ),
    )


def _advice_kind_counts(
    results: list[SotPickEvaluationFixtureResult],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
    config: PlayAdviceConfig,
) -> tuple[int, int, int, int, int, float | None]:
    play = borderline = no_play = 0
    wins = losses = 0
    for row in results:
        pick = pick_getter(row)
        if pick is None or pick.play_advice is None:
            no_play += 1
            continue
        advice = pick.play_advice
        if advice.play_advice == "play":
            play += 1
        elif advice.play_advice == "borderline":
            borderline += 1
        else:
            no_play += 1

        if is_playable_advice(advice, config):
            if pick.outcome == "win":
                wins += 1
            elif pick.outcome == "loss":
                losses += 1

    return play, no_play, borderline, wins, losses, _hit_rate(wins, losses)


def _compute_advised_summary(
    results: list[SotPickEvaluationFixtureResult],
    config: PlayAdviceConfig,
) -> SotPickAdvisedSummary:
    agg_play, agg_no, agg_border, agg_w, agg_l, agg_hr = _advice_kind_counts(
        results,
        lambda r: r.aggressive_pick,
        config,
    )
    caut_play, caut_no, caut_border, caut_w, caut_l, caut_hr = _advice_kind_counts(
        results,
        lambda r: r.cautious_pick,
        config,
    )
    return SotPickAdvisedSummary(
        aggressive_play_count=agg_play,
        aggressive_no_play_count=agg_no,
        aggressive_borderline_count=agg_border,
        aggressive_play_wins=agg_w,
        aggressive_play_losses=agg_l,
        aggressive_play_hit_rate=agg_hr,
        cautious_play_count=caut_play,
        cautious_no_play_count=caut_no,
        cautious_borderline_count=caut_border,
        cautious_play_wins=caut_w,
        cautious_play_losses=caut_l,
        cautious_play_hit_rate=caut_hr,
    )


def _is_advised_playable_pick(
    pick: SotPickOverPick | None,
    config: PlayAdviceConfig,
) -> bool:
    if pick is None or pick.play_advice is None:
        return False
    return is_playable_advice(pick.play_advice, config)


def _breakdown_by_line(
    results: list[SotPickEvaluationFixtureResult],
    lines: list[float],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
    *,
    advised_only: bool = False,
    play_advice_config: PlayAdviceConfig | None = None,
) -> list[SotPickBreakdownLineStats]:
    out: list[SotPickBreakdownLineStats] = []
    for line in lines:
        picks = [
            r for r in results
            if pick_getter(r) is not None
            and pick_getter(r).line == float(line)
            and (
                not advised_only
                or _is_advised_playable_pick(pick_getter(r), play_advice_config)  # type: ignore[arg-type]
            )
        ]
        wins = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "win")
        losses = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "loss")
        out.append(
            SotPickBreakdownLineStats(
                line=float(line),
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(pick_getter(r).edge for r in picks if pick_getter(r) is not None),
            ),
        )
    return out


def _breakdown_by_confidence(
    results: list[SotPickEvaluationFixtureResult],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
    *,
    advised_only: bool = False,
    play_advice_config: PlayAdviceConfig | None = None,
) -> list[SotPickBreakdownConfidenceStats]:
    out: list[SotPickBreakdownConfidenceStats] = []
    for confidence in ("low", "medium", "high"):
        picks = [
            r for r in results
            if pick_getter(r) is not None
            and pick_getter(r).confidence == confidence
            and (
                not advised_only
                or _is_advised_playable_pick(pick_getter(r), play_advice_config)  # type: ignore[arg-type]
            )
        ]
        wins = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "win")
        losses = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "loss")
        out.append(
            SotPickBreakdownConfidenceStats(
                confidence=confidence,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(pick_getter(r).edge for r in picks if pick_getter(r) is not None),
            ),
        )
    return out


def _breakdown_by_sample_bucket(
    results: list[SotPickEvaluationFixtureResult],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
    *,
    advised_only: bool = False,
    play_advice_config: PlayAdviceConfig | None = None,
) -> list[SotPickBreakdownSampleBucketStats]:
    buckets = ("early_low_sample", "medium_sample", "stable_sample")
    out: list[SotPickBreakdownSampleBucketStats] = []
    for bucket in buckets:
        picks = [
            r for r in results
            if pick_getter(r) is not None
            and r.sample_bucket == bucket
            and (
                not advised_only
                or _is_advised_playable_pick(pick_getter(r), play_advice_config)  # type: ignore[arg-type]
            )
        ]
        wins = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "win")
        losses = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "loss")
        out.append(
            SotPickBreakdownSampleBucketStats(
                bucket=bucket,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(pick_getter(r).edge for r in picks if pick_getter(r) is not None),
            ),
        )
    return out


def _breakdown_by_actual_total_bucket(
    results: list[SotPickEvaluationFixtureResult],
    pick_getter: Callable[[SotPickEvaluationFixtureResult], SotPickOverPick | None],
) -> list[SotPickBreakdownActualTotalBucketStats]:
    buckets = ("low_total", "medium_total", "high_total")
    out: list[SotPickBreakdownActualTotalBucketStats] = []
    for bucket in buckets:
        picks = [r for r in results if pick_getter(r) is not None and r.actual_total_bucket == bucket]
        wins = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "win")
        losses = sum(1 for r in picks if pick_getter(r) and pick_getter(r).outcome == "loss")
        out.append(
            SotPickBreakdownActualTotalBucketStats(
                bucket=bucket,
                picks_count=len(picks),
                wins=wins,
                losses=losses,
                hit_rate=_hit_rate(wins, losses),
                avg_edge=_mean(pick_getter(r).edge for r in picks if pick_getter(r) is not None),
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
        cautious_drop_threshold: float = 0.75,
        include_no_pick: bool = True,
        play_advice_config: PlayAdviceConfig | None = None,
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

        advice_config = play_advice_config or PlayAdviceConfig()
        eval_lines = list(lines) if lines else list(DEFAULT_PICK_LINES)

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

            results.append(
                _evaluate_fixture(
                    preview,
                    lines=eval_lines,
                    cautious_drop_threshold=float(cautious_drop_threshold),
                    play_advice_config=advice_config,
                ),
            )

        if not include_no_pick:
            results = [
                r for r in results
                if not (r.no_aggressive_pick and r.no_cautious_pick)
            ]

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

        agg_getter = lambda r: r.aggressive_pick
        caut_getter = lambda r: r.cautious_pick

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
                cautious_drop_threshold=float(cautious_drop_threshold),
                include_no_pick=include_no_pick,
                order_by=selection.order_by,
                min_prior_matches_for_play=advice_config.min_prior_matches_for_play,
                min_aggressive_edge_for_play=advice_config.min_aggressive_edge_for_play,
                min_cautious_edge_for_play=advice_config.min_cautious_edge_for_play,
                max_warnings_for_play=advice_config.max_warnings_for_play,
                allow_early_low_sample=advice_config.allow_early_low_sample,
                allow_low_confidence=advice_config.allow_low_confidence,
                include_borderline_as_playable=advice_config.include_borderline_as_playable,
            ),
            calculated_summary=_compute_calculated_summary(results, failed=failed_count),
            advised_summary=_compute_advised_summary(results, advice_config),
            aggressive_by_line=_breakdown_by_line(results, eval_lines, agg_getter),
            cautious_by_line=_breakdown_by_line(results, eval_lines, caut_getter),
            aggressive_by_confidence=_breakdown_by_confidence(results, agg_getter),
            cautious_by_confidence=_breakdown_by_confidence(results, caut_getter),
            aggressive_by_sample_bucket=_breakdown_by_sample_bucket(results, agg_getter),
            cautious_by_sample_bucket=_breakdown_by_sample_bucket(results, caut_getter),
            aggressive_by_actual_total_bucket=_breakdown_by_actual_total_bucket(results, agg_getter),
            cautious_by_actual_total_bucket=_breakdown_by_actual_total_bucket(results, caut_getter),
            advised_aggressive_by_line=_breakdown_by_line(
                results, eval_lines, agg_getter, advised_only=True, play_advice_config=advice_config,
            ),
            advised_cautious_by_line=_breakdown_by_line(
                results, eval_lines, caut_getter, advised_only=True, play_advice_config=advice_config,
            ),
            advised_aggressive_by_confidence=_breakdown_by_confidence(
                results, agg_getter, advised_only=True, play_advice_config=advice_config,
            ),
            advised_cautious_by_confidence=_breakdown_by_confidence(
                results, caut_getter, advised_only=True, play_advice_config=advice_config,
            ),
            advised_aggressive_by_sample_bucket=_breakdown_by_sample_bucket(
                results, agg_getter, advised_only=True, play_advice_config=advice_config,
            ),
            advised_cautious_by_sample_bucket=_breakdown_by_sample_bucket(
                results, caut_getter, advised_only=True, play_advice_config=advice_config,
            ),
            results=results,
            failed_fixtures=failed_fixtures,
            feature_snapshot_json={
                "preview_only": True,
                "pick_evaluation": True,
                "pick_advice_layer": True,
                "include_no_pick": include_no_pick,
                "over_only": True,
            },
        )
