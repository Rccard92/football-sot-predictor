"""Quota finale Cecchino 1-X-2 v2 (documento "Modifiche" di Giovanni, punto 4, 09/11/2026)."""

import pytest

from app.services.cecchino.cecchino_constants import (
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
)
from app.services.cecchino.cecchino_engine import OutcomeOdds, PicchettoBlock, compute_final_odds


def block(key, p1, px, p2):
    def o(p):
        return OutcomeOdds(prob=p, quota=round(1 / p, 2))

    return PicchettoBlock(
        key=key, label=key, home_context=None, away_context=None, total_matches=10,
        outcome_1=o(p1), outcome_x=o(px), outcome_2=o(p2), status=STATUS_AVAILABLE,
    )


PICS = {
    PICCHETTO_KEY_TOTALS: block(PICCHETTO_KEY_TOTALS, 0.50, 0.25, 0.25),
    PICCHETTO_KEY_HOME_AWAY: block(PICCHETTO_KEY_HOME_AWAY, 0.40, 0.40, 0.20),
    PICCHETTO_KEY_LAST6_TOTALS: block(PICCHETTO_KEY_LAST6_TOTALS, 0.20, 0.20, 0.60),
    PICCHETTO_KEY_LAST5_HOME_AWAY: block(PICCHETTO_KEY_LAST5_HOME_AWAY, 0.60, 0.20, 0.20),
}


def test_point_1_is_giovannis_formula_and_sums_to_100():
    f = compute_final_odds(PICS, home_factor=(1.0, 1.0))
    # 1 / (0,3/q tot + 0,3/q casa-fuori + 0,2/q ultime 6 + 0,2/q ultime 5)
    q = {k: round(1 / p, 2) for k, p in (("t", 0.5), ("h", 0.4), ("l6", 0.2), ("l5", 0.6))}
    expected = 1 / (0.3 / q["t"] + 0.3 / q["h"] + 0.2 / q["l6"] + 0.2 / q["l5"])
    assert f.quota_1 == pytest.approx(expected, rel=2e-3)
    assert f.prob_1 + f.prob_x + f.prob_2 == pytest.approx(1.0)
    # la quota di prima (media delle quote) e' piu' alta e somma meno di 100%
    v1 = f.v1
    assert 1 / v1["quota_1"] + 1 / v1["quota_x"] + 1 / v1["quota_2"] < 0.99
    assert v1["version"] == "1x2_v1_media_quote"


def test_home_factor_moves_probability_to_the_home_win():
    base = compute_final_odds(PICS, home_factor=(1.0, 1.0))
    f = compute_final_odds(PICS, home_factor=(1.25, 1.05))
    assert f.prob_1 > base.prob_1 and f.prob_2 < base.prob_2
    assert f.prob_1 + f.prob_x + f.prob_2 == pytest.approx(1.0)
    assert f.home_factor == {"1": 1.25, "x": 1.05, "2": 1.0}
    d = f.to_dict()
    assert d["version"] == "1x2_v2_20261109" and d["sum_prob"] == pytest.approx(1.0) and d["v1"]["quota_1"]


def test_default_home_factor_from_settings():
    f = compute_final_odds(PICS)
    assert f.home_factor["1"] == 1.25 and f.home_factor["x"] == 1.05


def test_missing_picchetto_keeps_insufficient_data():
    pics = dict(PICS)
    pics.pop(PICCHETTO_KEY_TOTALS)
    f = compute_final_odds(pics)
    assert f.status != STATUS_AVAILABLE and f.quota_1 is None
