"""Sintesi compatta historical_official_xi per PIT context (Step JK.1)."""

from __future__ import annotations

from pydantic import BaseModel


class FixtureSnapshotSummaryBrief(BaseModel):
    fixture_id: int
    home_status: str
    away_status: str
    home_starters_count: int = 0
    away_starters_count: int = 0
    home_unavailable_count: int = 0
    away_unavailable_count: int = 0
    home_unavailable_source: str = "none"
    away_unavailable_source: str = "none"


class PointInTimeHistoricalSummary(BaseModel):
    source_fixture_id: int
    fixture_snapshot_summary: FixtureSnapshotSummaryBrief
    home_lineup_macro_status: str | None = None
    home_lineup_macro_index: float | None = None
    away_lineup_macro_status: str | None = None
    away_lineup_macro_index: float | None = None
    home_unavailable_macro_status: str | None = None
    home_unavailable_macro_index: float | None = None
    away_unavailable_macro_status: str | None = None
    away_unavailable_macro_index: float | None = None
    home_player_layer_status: str | None = None
    home_player_layer_index: float | None = None
    away_player_layer_status: str | None = None
    away_player_layer_index: float | None = None
    source_fixture_id_lineup_home: int | None = None
    source_fixture_id_lineup_away: int | None = None
    source_fixture_id_unavailable_home: int | None = None
    source_fixture_id_unavailable_away: int | None = None
