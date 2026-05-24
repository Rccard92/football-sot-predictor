"""Test contesto match arbitro su righe cache."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.referee_severity_service import aggregate_card_rows


def test_aggregate_card_rows_team_side():
    rows = [
        SimpleNamespace(
            total_yellow=5,
            total_red=1,
            home_yellow=3,
            home_red=1,
            away_yellow=2,
            away_red=0,
            home_team_api_id=10,
            away_team_api_id=20,
            card_source="events",
        ),
        SimpleNamespace(
            total_yellow=4,
            total_red=0,
            home_yellow=1,
            home_red=0,
            away_yellow=3,
            away_red=0,
            home_team_api_id=20,
            away_team_api_id=10,
            card_source="events",
        ),
    ]
    agg = aggregate_card_rows(rows, team_api_id=10)
    assert agg["matches_count"] == 2
    assert agg["avg_yellow_cards"] == 4.5
    assert agg["data_source"] == "api_sports_fetched"
