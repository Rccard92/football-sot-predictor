"""Builder condiviso estensioni historical_official_xi per PIT context/preview (Step JK.1)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.backtest_historical_fixture_snapshot import HistoricalFixtureOfficialSnapshot
from app.schemas.backtest_point_in_time import PointInTimeContextResponse
from app.schemas.backtest_point_in_time_historical_summary import (
    FixtureSnapshotSummaryBrief,
    PointInTimeHistoricalSummary,
)
from app.services.backtest.historical_fixture_snapshot_service import HistoricalFixtureSnapshotService
from app.services.backtest.historical_lineup_macro_service import HistoricalLineupMacroService
from app.services.backtest.historical_unavailable_macro_service import HistoricalUnavailableMacroService
from app.services.backtest.rolling_player_layer_service import RollingPlayerLayerService


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def build_historical_summary(
    *,
    fixture_id: int,
    snapshot: HistoricalFixtureOfficialSnapshot,
    ctx: PointInTimeContextResponse,
) -> PointInTimeHistoricalSummary:
    home_lm = ctx.home_lineup_macro
    away_lm = ctx.away_lineup_macro
    home_um = ctx.home_unavailable_macro
    away_um = ctx.away_unavailable_macro
    home_pl = ctx.home_player_layer
    away_pl = ctx.away_player_layer
    fid = int(fixture_id)

    return PointInTimeHistoricalSummary(
        source_fixture_id=fid,
        fixture_snapshot_summary=FixtureSnapshotSummaryBrief(
            fixture_id=fid,
            home_status=snapshot.home.status,
            away_status=snapshot.away.status,
            home_starters_count=len(snapshot.home.starters),
            away_starters_count=len(snapshot.away.starters),
            home_unavailable_count=len(snapshot.home.unavailable),
            away_unavailable_count=len(snapshot.away.unavailable),
            home_unavailable_source=snapshot.home.unavailable_source,
            away_unavailable_source=snapshot.away.unavailable_source,
        ),
        home_lineup_macro_status=home_lm.status if home_lm else None,
        home_lineup_macro_index=_round4(home_lm.lineup_macro_index if home_lm else None),
        away_lineup_macro_status=away_lm.status if away_lm else None,
        away_lineup_macro_index=_round4(away_lm.lineup_macro_index if away_lm else None),
        home_unavailable_macro_status=home_um.status if home_um else None,
        home_unavailable_macro_index=_round4(home_um.unavailable_macro_index if home_um else None),
        away_unavailable_macro_status=away_um.status if away_um else None,
        away_unavailable_macro_index=_round4(away_um.unavailable_macro_index if away_um else None),
        home_player_layer_status=home_pl.status if home_pl else None,
        home_player_layer_index=_round4(home_pl.player_layer_index if home_pl else None),
        away_player_layer_status=away_pl.status if away_pl else None,
        away_player_layer_index=_round4(away_pl.player_layer_index if away_pl else None),
        source_fixture_id_lineup_home=home_lm.source_fixture_id if home_lm else fid,
        source_fixture_id_lineup_away=away_lm.source_fixture_id if away_lm else fid,
        source_fixture_id_unavailable_home=home_um.source_fixture_id if home_um else fid,
        source_fixture_id_unavailable_away=away_um.source_fixture_id if away_um else fid,
    )


class HistoricalPitExtensionsBuilder:
    def build_historical_extensions(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
        ctx: PointInTimeContextResponse,
    ) -> PointInTimeContextResponse:
        snapshot_svc = HistoricalFixtureSnapshotService()
        layer_svc = RollingPlayerLayerService()
        lineup_svc = HistoricalLineupMacroService()
        unavail_svc = HistoricalUnavailableMacroService()

        snapshot = snapshot_svc.get_fixture_official_snapshot(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
        )

        home_layer = layer_svc.build_team_player_layer(
            db,
            competition_id=int(competition_id),
            team_id=int(ctx.home_team_id),
            cutoff_time=ctx.cutoff_time,
            side_snapshot=snapshot.home,
            league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
        )
        away_layer = layer_svc.build_team_player_layer(
            db,
            competition_id=int(competition_id),
            team_id=int(ctx.away_team_id),
            cutoff_time=ctx.cutoff_time,
            side_snapshot=snapshot.away,
            league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
        )
        home_lineup_macro = lineup_svc.build_team_lineup_macro(
            db,
            snapshot=snapshot,
            competition_id=int(competition_id),
            team_id=int(ctx.home_team_id),
            cutoff_time=ctx.cutoff_time,
            side="home",
        )
        away_lineup_macro = lineup_svc.build_team_lineup_macro(
            db,
            snapshot=snapshot,
            competition_id=int(competition_id),
            team_id=int(ctx.away_team_id),
            cutoff_time=ctx.cutoff_time,
            side="away",
        )
        home_unavailable_macro = unavail_svc.build_team_unavailable_macro(
            db,
            snapshot=snapshot,
            competition_id=int(competition_id),
            team_id=int(ctx.home_team_id),
            cutoff_time=ctx.cutoff_time,
            side="home",
            opponent_side=snapshot.away,
            league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
        )
        away_unavailable_macro = unavail_svc.build_team_unavailable_macro(
            db,
            snapshot=snapshot,
            competition_id=int(competition_id),
            team_id=int(ctx.away_team_id),
            cutoff_time=ctx.cutoff_time,
            side="away",
            opponent_side=snapshot.home,
            league_avg_sot_for=ctx.league_baselines.league_avg_sot_for,
        )

        extended = ctx.model_copy(
            update={
                "fixture_snapshot": snapshot,
                "home_player_layer": home_layer,
                "away_player_layer": away_layer,
                "home_lineup_macro": home_lineup_macro,
                "away_lineup_macro": away_lineup_macro,
                "home_unavailable_macro": home_unavailable_macro,
                "away_unavailable_macro": away_unavailable_macro,
            },
        )
        summary = build_historical_summary(
            fixture_id=int(fixture_id),
            snapshot=snapshot,
            ctx=extended,
        )
        return extended.model_copy(update={"historical_summary": summary})
