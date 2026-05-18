"""Debug availability — top shooter, team-level, date range."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.models import PlayerSeasonProfile
from app.services.availability.availability_debug import _date_in_range, _pack_player_row


def test_date_in_range_active_unbounded():
    ok, window = _date_in_range(date(2025, 5, 20), date(2025, 5, 1), None)
    assert ok is True
    assert window == "active_unbounded"


def test_date_in_range_out_of_range():
    ok, window = _date_in_range(date(2025, 5, 20), date(2025, 5, 1), date(2025, 5, 10))
    assert ok is False
    assert window == "out_of_range"


def test_pack_player_row_top_shooter_and_high_impact():
    av = MagicMock()
    av.api_player_id = 10
    av.player_name = "Striker"
    av.availability_status = "suspended"
    av.availability_type = "suspension"
    av.reason = "Yellow Cards"
    av.source = "api_football_injuries"
    av.api_fixture_id = None
    av.fixture_id = None
    av.start_date = None
    av.end_date = None

    prof = MagicMock(spec=PlayerSeasonProfile)
    prof.shots_on_per90 = Decimal("0.5")
    prof.team_sot_share = Decimal("0.2")
    prof.shooting_impact_score = Decimal("70")
    prof.reliability_score = 80
    prof.minutes_total = 2000
    prof.shots_total_per90 = Decimal("2.0")

    row = _pack_player_row(av, prof, is_top_shooter=True, kickoff=date(2025, 5, 20))
    assert row["is_top_shooter"] is True
    assert row["high_impact"] is True
    assert row["is_team_level"] is True
    assert row["date_window"] == "unknown"


def test_debug_module_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.services.availability.availability_debug")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
