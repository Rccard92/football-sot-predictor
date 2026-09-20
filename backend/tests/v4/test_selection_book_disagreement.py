"""Prezzi incompatibili tra Bet365 e Betfair sulla stessa chiave: quota anomala, mai giocabile."""

from app.services.cecchino_v4.constants import VERDICT_ANOMALOUS, VERDICT_PLAYABLE
from app.services.cecchino_v4.selection.rules import evaluate_fixture


def _stats(p_under=0.95):
    def side():
        return {"mean": 8.5, "dispersion": None, "division_mean": 10.0, "evidence": 30, "lines": {"14.5": {"over": 1 - p_under, "lo": 1 - p_under, "hi": 1 - p_under}}}
    return {"stats": {"corners": {"exam": "non_superato", "home": side(), "away": side(), "total": side()}}}


def test_disagreeing_books_make_the_line_anomalous():
    odds = {8: {"STAT:corners:total:under:14.5": 1.91}, 3: {"STAT:corners:total:under:14.5": 1.01}}
    rows = evaluate_fixture({"markets": {}, "uncertainty": {"score": 0.1, "level": "bassa"}}, _stats(), odds, "Casa", "Ospite", "ufficiali")
    row = next(r for r in rows if r.market_key == "STAT:corners:total:under:14.5")
    assert row.verdict == VERDICT_ANOMALOUS


def test_model_far_above_price_is_anomalous_even_with_one_book():
    odds = {8: {"STAT:corners:total:under:14.5": 1.91}}
    rows = evaluate_fixture({"markets": {}, "uncertainty": {"score": 0.1, "level": "bassa"}}, _stats(), odds, "Casa", "Ospite", "ufficiali")
    assert next(r for r in rows if r.market_key == "STAT:corners:total:under:14.5").verdict == VERDICT_ANOMALOUS


def test_coherent_books_stay_playable():
    odds = {8: {"STAT:corners:total:under:14.5": 1.45}, 3: {"STAT:corners:total:under:14.5": 1.5}}
    rows = evaluate_fixture({"markets": {}, "uncertainty": {"score": 0.1, "level": "bassa"}}, _stats(p_under=0.8), odds, "Casa", "Ospite", "ufficiali")
    assert next(r for r in rows if r.market_key == "STAT:corners:total:under:14.5").verdict == VERDICT_PLAYABLE
