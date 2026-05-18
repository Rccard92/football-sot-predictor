"""Debug availability — top shooter e high impact."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.models import PlayerSeasonProfile
from app.services.availability.availability_debug import _pack_player_row
from app.services.availability.availability_helpers import HIGH_IMPACT_THRESHOLD


def test_pack_player_row_top_shooter_and_high_impact():
    av = MagicMock()
    av.api_player_id = 10
    av.player_name = "Striker"
    av.availability_status = "out"
    av.availability_type = "injury"
    av.reason = "Muscle"
    av.source = "api_football_injuries"

    prof = MagicMock(spec=PlayerSeasonProfile)
    prof.shots_on_per90 = Decimal("0.5")
    prof.team_sot_share = Decimal("0.2")
    prof.shooting_impact_score = Decimal(str(HIGH_IMPACT_THRESHOLD))
    prof.reliability_score = 80
    prof.minutes_total = 2000
    prof.shots_total_per90 = Decimal("2.0")

    row = _pack_player_row(av, prof, is_top_shooter=True)
    assert row["is_top_shooter"] is True
    assert row["high_impact"] is True
    assert row["profile_found"] is True


def test_debug_module_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.services.availability.availability_debug")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
