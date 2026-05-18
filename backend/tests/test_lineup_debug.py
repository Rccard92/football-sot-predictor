"""Debug lineups read-only."""

from app.services.lineups.lineup_debug import build_fixture_lineups_debug


def test_debug_module_no_predictions_import():
    import importlib

    mod = importlib.import_module("app.services.lineups.lineup_debug")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "predictions_v11" not in src
