"""Test aggregazione unavailable_macro_summary mini-run (Step K.5)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.backtest_sot_v21_preview import (
    ActualsForScoring,
    SotV21PreviewErrors,
    SotV21PreviewFixtureBrief,
    SotV21PreviewMacroTrace,
    SotV21PreviewPrediction,
    SotV21PreviewResponse,
    SotV21PreviewSideTrace,
)
from app.services.backtest.sot_v21_mini_run_preview_service import _aggregate_unavailable_macro_summary

_CUTOFF = datetime(2026, 3, 15, 19, 0, tzinfo=timezone.utc)


def _preview_with_unavail(
    fixture_id: int,
    *,
    home_records: int = 0,
    away_records: int = 0,
    home_important: int = 0,
    away_important: int = 0,
    home_mapped: int = 0,
    away_mapped: int = 0,
) -> SotV21PreviewResponse:
    def _side(records: int, important: int, mapped: int) -> SotV21PreviewSideTrace:
        return SotV21PreviewSideTrace(
            base_anchor_sot={"value": 5.0},
            weighted_macro_multiplier=1.0,
            expected_sot_v21_pit=5.0,
            macros=[
                SotV21PreviewMacroTrace(
                    key="injuries_unavailable",
                    label="Injuries",
                    macro_weight=1.0,
                    macro_index=1.0,
                    status="available",
                    details={
                        "unavailable_macro_detail": {
                            "source_fixture_id": fixture_id,
                            "records_count": records,
                            "important_absences_count": important,
                            "mapped_count": mapped,
                            "unmapped_count": max(0, records - mapped),
                            "players": [],
                        },
                    },
                ),
            ],
        )

    return SotV21PreviewResponse(
        competition_id=1,
        fixture_id=fixture_id,
        fixture=SotV21PreviewFixtureBrief(
            home_team="Home",
            away_team="Away",
            kickoff_at=_CUTOFF,
        ),
        cutoff_time=_CUTOFF,
        prediction=SotV21PreviewPrediction(
            home_predicted_sot=5.0,
            away_predicted_sot=4.0,
            total_predicted_sot=9.0,
        ),
        actuals_for_scoring=ActualsForScoring(
            actual_home_sot=5,
            actual_away_sot=4,
            actual_total_sot=9,
            fixture_status="FT",
        ),
        errors=SotV21PreviewErrors(
            home_error=0.0,
            away_error=0.0,
            total_error=0.0,
            home_abs_error=0.0,
            away_abs_error=0.0,
            total_abs_error=0.0,
        ),
        home_trace=_side(home_records, home_important, home_mapped),
        away_trace=_side(away_records, away_important, away_mapped),
    )


def test_summary_counts_only_normalized_records():
    previews = [
        _preview_with_unavail(359, home_records=3, away_records=1, home_mapped=2, away_mapped=1),
        _preview_with_unavail(360),
        _preview_with_unavail(361),
    ]
    summary = _aggregate_unavailable_macro_summary(previews)
    assert summary.fixtures_with_unavailable == 1
    assert summary.total_unavailable_players == 4
    assert summary.mapped_unavailable_players == 3
    assert summary.unmapped_unavailable_players == 1


def test_summary_important_absences():
    previews = [
        _preview_with_unavail(359, home_records=2, home_important=1),
    ]
    summary = _aggregate_unavailable_macro_summary(previews)
    assert summary.fixtures_with_important_absences == 1
    assert summary.important_absences_count == 1
