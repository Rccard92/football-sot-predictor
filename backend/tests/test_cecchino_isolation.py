"""Cecchino non deve importare SOT predictions."""


def test_cecchino_services_no_team_sot_predictions():
    import app.services.cecchino.cecchino_service as svc

    src = open(svc.__file__, encoding="utf-8").read()
    assert "team_sot_predictions" not in src
    assert "predictions_v20" not in src
    assert "predictions_v21" not in src


def test_cecchino_constants_bookmakers():
    from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKERS

    ids = {int(b["provider_bookmaker_id"]) for b in CECCHINO_BOOKMAKERS}
    assert ids == {8, 3, 4}
    names = {b["name"] for b in CECCHINO_BOOKMAKERS}
    assert names == {"Bet365", "Betfair", "Pinnacle"}
