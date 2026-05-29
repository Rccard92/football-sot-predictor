from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.models import (
    Fixture,
    FixtureLineup,
    FixtureProviderLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    IngestionRun,
    PlayerSeasonProfile,
    TeamSotPrediction,
    TrackedBettingPick,
)
from app.services.competition_service import CompetitionService
from app.services.next_round_selection import select_next_round_fixtures
from app.services.predictions_v21.v21_variable_coverage import aggregate_v21_coverage_from_predictions
from app.services.predictions_v21.v21_xg_coverage import xg_coverage_summary
from app.services.sot_model_registry import label_for_model, user_visible_model_versions


def build_competition_data_health(
    db: Session,
    competition_id: int,
    *,
    selected_model_version: str | None = None,
) -> dict[str, Any]:
    comp = CompetitionService().get_by_id_or_raise(db, competition_id)

    fixture_count = int(
        db.scalar(select(func.count()).select_from(Fixture).where(Fixture.competition_id == comp.id)) or 0
    )
    finished_count = int(
        db.scalar(
            select(func.count())
            .select_from(Fixture)
            .where(Fixture.competition_id == comp.id, Fixture.status.in_(tuple(FINISHED_STATUSES)))
        )
        or 0
    )
    team_stats_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureTeamStat)
            .where(FixtureTeamStat.competition_id == comp.id)
        )
        or 0
    )
    profiles_count = int(
        db.scalar(
            select(func.count())
            .select_from(PlayerSeasonProfile)
            .where(PlayerSeasonProfile.competition_id == comp.id)
        )
        or 0
    )
    predictions_count = int(
        db.scalar(
            select(func.count())
            .select_from(TeamSotPrediction)
            .where(TeamSotPrediction.competition_id == comp.id)
        )
        or 0
    )

    all_upcoming = list(
        db.scalars(
            select(Fixture).where(
                Fixture.competition_id == comp.id,
                ~Fixture.status.in_(FINISHED_STATUSES),
            )
        ).all()
    )
    next_round_sel = select_next_round_fixtures(all_upcoming, limit=100, only_next_round=True)
    next_round_ids = [int(fx.id) for fx in next_round_sel.fixtures]
    next_round_fixture_count = len(next_round_ids)

    pred_by_model_rows = db.execute(
        select(TeamSotPrediction.model_version, func.count())
        .where(TeamSotPrediction.competition_id == comp.id)
        .group_by(TeamSotPrediction.model_version)
    ).all()
    predictions_by_model = {str(mv): int(cnt) for mv, cnt in pred_by_model_rows}

    next_round_pred_by_model: dict[str, int] = {}
    last_gen_by_model: dict[str, str | None] = {}
    predictions_by_model_detail: list[dict[str, Any]] = []
    if next_round_ids:
        nr_rows = db.execute(
            select(
                TeamSotPrediction.model_version,
                func.count(),
                func.max(TeamSotPrediction.updated_at),
            )
            .where(
                TeamSotPrediction.competition_id == comp.id,
                TeamSotPrediction.fixture_id.in_(next_round_ids),
                TeamSotPrediction.predicted_sot.isnot(None),
            )
            .group_by(TeamSotPrediction.model_version)
        ).all()
        for mv, cnt, gen_at in nr_rows:
            next_round_pred_by_model[str(mv)] = int(cnt or 0)
            last_gen_by_model[str(mv)] = gen_at.isoformat() if gen_at else None

    for mv in user_visible_model_versions():
        total = int(predictions_by_model.get(mv, 0))
        nr_cnt = int(next_round_pred_by_model.get(mv, 0))
        if next_round_fixture_count > 0:
            expected = 2 * next_round_fixture_count
            readiness = "ready" if nr_cnt >= expected else ("partial" if nr_cnt > 0 else "missing")
        else:
            readiness = "ready" if total > 0 else "missing"
        predictions_by_model_detail.append(
            {
                "model_version": mv,
                "label": label_for_model(mv),
                "predictions_count": total,
                "next_round_predictions_count": nr_cnt,
                "last_generated_at": last_gen_by_model.get(mv),
                "readiness": readiness,
            }
        )

    selected_next_round_count = (
        int(next_round_pred_by_model.get(str(selected_model_version), 0))
        if selected_model_version
        else None
    )
    lineups_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureLineup)
            .where(FixtureLineup.competition_id == comp.id)
        )
        or 0
    )
    sportapi_lineups_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureProviderLineup)
            .where(FixtureProviderLineup.competition_id == comp.id)
        )
        or 0
    )
    picks_count = int(
        db.scalar(
            select(func.count())
            .select_from(TrackedBettingPick)
            .where(TrackedBettingPick.competition_id == comp.id)
        )
        or 0
    )
    teams_count = int(
        db.scalar(
            select(func.count(func.distinct(Fixture.home_team_id)))
            .select_from(Fixture)
            .where(Fixture.competition_id == comp.id)
        )
        or 0
    )
    last_ingestion = db.scalar(
        select(IngestionRun)
        .where(IngestionRun.competition_id == comp.id)
        .order_by(IngestionRun.started_at.desc().nulls_last(), IngestionRun.id.desc())
    )

    mappings_count = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureProviderMapping)
            .where(FixtureProviderMapping.competition_id == comp.id)
        )
        or 0
    )

    next_round_mappings_count = 0
    next_round_lineups_count = 0
    if next_round_ids:
        next_round_mappings_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderMapping)
                .where(
                    FixtureProviderMapping.competition_id == comp.id,
                    FixtureProviderMapping.fixture_id.in_(next_round_ids),
                )
            )
            or 0
        )
        next_round_lineups_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureProviderLineup)
                .where(
                    FixtureProviderLineup.competition_id == comp.id,
                    FixtureProviderLineup.fixture_id.in_(next_round_ids),
                )
            )
            or 0
        )

    next_round_lineup_coverage_pct = round(
        100.0 * next_round_lineups_count / max(next_round_fixture_count, 1),
        1,
    )
    missing_mappings_next_round = max(next_round_fixture_count - next_round_mappings_count, 0)

    expected_per_model = 2 * next_round_fixture_count if next_round_fixture_count > 0 else 0
    base_nr = int(next_round_pred_by_model.get(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT, 0))
    compare_nr = int(next_round_pred_by_model.get(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS, 0))
    model_comparison_available = (
        next_round_fixture_count > 0
        and expected_per_model > 0
        and base_nr >= expected_per_model
        and compare_nr >= expected_per_model
    )

    sportapi_rows = list(
        db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.competition_id == comp.id,
            )
        ).all()
    )
    confirmed_lineups_count = sum(1 for r in sportapi_rows if bool(r.confirmed))
    probable_lineups_count = len(sportapi_rows) - confirmed_lineups_count

    lineup_coverage_pct = round(100.0 * lineups_count / max(finished_count * 2, 1), 1)

    xg_feed = xg_coverage_summary(db, int(comp.id))
    v21_variable_coverage = None
    if next_round_ids:
        v21_rows = db.scalars(
            select(TeamSotPrediction).where(
                TeamSotPrediction.competition_id == comp.id,
                TeamSotPrediction.fixture_id.in_(next_round_ids),
                TeamSotPrediction.model_version == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
                TeamSotPrediction.predicted_sot.isnot(None),
            ),
        ).all()
        raw_payloads = [r.raw_json for r in v21_rows if isinstance(r.raw_json, dict)]
        if raw_payloads:
            v21_variable_coverage = aggregate_v21_coverage_from_predictions(raw_payloads)

    return {
        "competition_id": comp.id,
        "competition_key": comp.key,
        "competition_name": comp.name,
        "season": comp.season,
        "fixture_count": fixture_count,
        "finished_fixture_count": finished_count,
        "teams_count": teams_count,
        "player_profiles_count": profiles_count,
        "team_stats_count": team_stats_count,
        "predictions_count": predictions_count,
        "predictions_by_model": predictions_by_model,
        "predictions_by_model_detail": predictions_by_model_detail,
        "model_comparison_available": model_comparison_available,
        "model_comparison_next_round": {
            "base_model": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
            "compare_model": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
            "base_next_round_count": base_nr,
            "compare_next_round_count": compare_nr,
            "expected_per_model": expected_per_model,
            "next_round_fixture_count": next_round_fixture_count,
        },
        "selected_model_version": selected_model_version,
        "selected_model_next_round_predictions_count": selected_next_round_count,
        "lineup_rows_count": lineups_count,
        "lineups_api_football_count": lineups_count,
        "sportapi_lineup_rows_count": sportapi_lineups_count,
        "lineups_sportapi_count": sportapi_lineups_count,
        "confirmed_lineups_count": confirmed_lineups_count,
        "probable_lineups_count": probable_lineups_count,
        "lineup_coverage_pct": lineup_coverage_pct,
        "sportapi_mappings_count": mappings_count,
        "missing_mappings": max(finished_count - mappings_count, 0),
        "next_round_fixture_count": next_round_fixture_count,
        "next_round_lineups_count": next_round_lineups_count,
        "next_round_sportapi_lineups_count": next_round_lineups_count,
        "next_round_lineup_coverage_pct": next_round_lineup_coverage_pct,
        "missing_mappings_next_round": missing_mappings_next_round,
        "tracked_picks_count": picks_count,
        "xg_feed": xg_feed,
        "v21_variable_coverage": v21_variable_coverage,
        "last_ingestion": {
            "source": last_ingestion.source if last_ingestion else None,
            "status": last_ingestion.status if last_ingestion else None,
            "started_at": last_ingestion.started_at.isoformat() if last_ingestion and last_ingestion.started_at else None,
            "records_processed": last_ingestion.records_processed if last_ingestion else None,
        },
    }
