"""Focus sui mercati statistici: i classici restano in osservazione, corner e cartellini sono giocabili, i falli no."""

from app.services.cecchino_v4.constants import VERDICT_DESCRIPTIVE, VERDICT_OBSERVED, VERDICT_PLAYABLE
from app.services.cecchino_v4.selection.rules import best_play, evaluate_fixture


def _goals():
    m = {"HOME": 0.3, "DRAW": 0.2, "AWAY": 0.5}
    return {"markets": {k: {"p": v, "lo": v, "hi": v} for k, v in m.items()}, "uncertainty": {"score": 0.1, "level": "bassa"}, "lambda_home": 1.2, "lambda_away": 1.6}


def _stats():
    def side():
        return {"mean": 6.0, "dispersion": None, "division_mean": 5.0, "evidence": 30, "lines": {"4.5": {"over": 0.75, "lo": 0.75, "hi": 0.75}}}
    return {"stats": {st: {"exam": ex, "home": side(), "away": side(), "total": side()} for st, ex in (("corners", "non_superato"), ("cards", "non_superato"), ("sot", "superato"), ("fouls", "superato"))}}


def test_classic_market_that_passes_the_rule_is_observed_not_playable():
    rows = evaluate_fixture(_goals(), None, {8: {"AWAY": 2.6}}, "Casa", "Ospite", "ufficiali")
    away = next(r for r in rows if r.market_key == "AWAY")
    assert away.verdict == VERDICT_OBSERVED
    assert best_play(rows) is None


def test_classic_playable_only_when_explicitly_allowed_for_exams():
    rows = evaluate_fixture(_goals(), None, {8: {"AWAY": 2.6}}, "Casa", "Ospite", "ufficiali", allow_classic=True)
    assert next(r for r in rows if r.market_key == "AWAY").verdict == VERDICT_PLAYABLE


def test_corners_cards_playable_fouls_descriptive():
    odds = {8: {"STAT:corners:total:over:4.5": 1.6, "STAT:cards:home:over:4.5": 1.6, "STAT:fouls:total:over:4.5": 1.6, "STAT:sot:away:over:4.5": 1.6}}
    rows = evaluate_fixture(_goals(), _stats(), odds, "Casa", "Ospite", "ufficiali")
    by = {r.market_key: r for r in rows}
    assert by["STAT:corners:total:over:4.5"].verdict == VERDICT_PLAYABLE
    assert by["STAT:cards:home:over:4.5"].verdict == VERDICT_PLAYABLE
    assert by["STAT:sot:away:over:4.5"].verdict == VERDICT_PLAYABLE
    assert by["STAT:fouls:total:over:4.5"].verdict == VERDICT_DESCRIPTIVE
    assert best_play(rows).market_key.startswith("STAT:")
