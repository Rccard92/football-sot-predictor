"""Quota anomala: una quota incompatibile con la probabilita' del modello non e' mai giocabile."""

from app.services.cecchino_v4.constants import VERDICT_ANOMALOUS, VERDICT_PLAYABLE
from app.services.cecchino_v4.selection.rules import evaluate_fixture


def _goals(p_away: float):
    p_home, p_draw = round((1 - p_away) * 0.6, 4), round((1 - p_away) * 0.4, 4)
    m = {"HOME": p_home, "DRAW": p_draw, "AWAY": p_away}
    return {"markets": {k: {"p": v, "lo": v, "hi": v} for k, v in m.items()}, "uncertainty": {"score": 0.1, "level": "bassa"}, "lambda_home": 1.5, "lambda_away": 1.5}


def test_price_incompatible_with_model_is_anomalous_not_playable():
    rows = evaluate_fixture(_goals(0.61), None, {8: {"AWAY": 13.0}}, "Casa", "Ospite", "ufficiali")
    away = next(r for r in rows if r.market_key == "AWAY")
    assert away.verdict == VERDICT_ANOMALOUS and away.verdict != VERDICT_PLAYABLE


def test_reasonable_price_stays_playable():
    rows = evaluate_fixture(_goals(0.50), None, {8: {"AWAY": 2.6}}, "Casa", "Ospite", "ufficiali", allow_classic=True)
    away = next(r for r in rows if r.market_key == "AWAY")
    assert away.verdict == VERDICT_PLAYABLE
