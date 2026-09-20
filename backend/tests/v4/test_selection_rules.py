"""Regola della selezione: probabilità prudente, tassi base, verdetti, righe della partita, giocata migliore."""

from __future__ import annotations

import math

import pytest

from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKER_BETFAIR_ID,
    MIN_QUOTA,
    PROFIT_MARGIN,
    VERDICT_DESCRIPTIVE,
    VERDICT_FAIR_PRICE,
    VERDICT_NO_ODDS,
    VERDICT_PLAYABLE,
    VERDICT_UNCERTAIN,
)
from app.services.cecchino_v4.selection.rules import (
    BASE_RATES,
    RowInputs,
    base_rate,
    best_play,
    evaluate_fixture,
    evaluate_market,
    no_play_reason,
    poisson_tail_over,
    prudent_probability,
)
from tests.v4.test_selection_samples import AWAY, HOME, SOT_KEY, goals, odds, stats


# --- probabilità prudente ------------------------------------------------------------
import pytest as _pytest

from app.services.cecchino_v4.selection import rules as _rules


@_pytest.fixture(autouse=True)
def _classic_markets_playable_for_rule_tests(monkeypatch):
    """Questi test verificano la meccanica della regola sui mercati classici: nel prodotto i classici
    restano "in osservazione" (focus statistiche), qui si abilitano per esercitare la regola."""
    monkeypatch.setattr(_rules, "CLASSIC_PLAYABLE_DEFAULT", True)
    # i campioni di questi test furono scritti quando corner e cartellini erano solo descrittivi
    monkeypatch.setattr(_rules, "PLAYABLE_STATS", ("shots", "sot"))


def test_prudent_shrinks_toward_base_rate_by_uncertainty():
    # lo 0,55 sopra il tasso base 0,18 con incertezza 0,22: 0,55 - (0,55 - 0,18) * 0,22
    assert prudent_probability(0.61, 0.55, 0.22, 0.18) == pytest.approx(0.55 - 0.37 * 0.22)


def test_prudent_never_inflates_when_lo_below_base_rate():
    assert prudent_probability(0.30, 0.26, 0.5, 0.44) == pytest.approx(0.26)


def test_prudent_clips_uncertainty_to_unit_interval():
    assert prudent_probability(0.6, 0.55, 3.0, 0.2) == pytest.approx(0.2)  # u = 1 -> tasso base
    assert prudent_probability(0.6, 0.55, -1.0, 0.2) == pytest.approx(0.55)  # u = 0 -> lo


def test_prudent_falls_back_to_p_without_interval_and_never_exceeds_p():
    assert prudent_probability(0.6, None, 0.0, 0.2) == pytest.approx(0.6)
    assert prudent_probability(0.5, 0.7, 0.0, 0.2) == pytest.approx(0.5)


# --- tassi base -------------------------------------------------------------------------
def test_classic_base_rates_declared_for_all_17_markets():
    assert len(BASE_RATES) == 17
    assert BASE_RATES["HOME"] + BASE_RATES["DRAW"] + BASE_RATES["AWAY"] == pytest.approx(1.0)
    assert base_rate("OVER_2_5") + base_rate("UNDER_2_5") == pytest.approx(1.0)


def test_stat_base_rate_is_poisson_tail_at_division_mean():
    scipy_stats = pytest.importorskip("scipy.stats")
    expected = float(scipy_stats.poisson.sf(6, 4.6))
    assert poisson_tail_over(4.6, 6.5) == pytest.approx(expected, abs=1e-9)
    assert base_rate("STAT:sot:away:over:6.5", 4.6) == pytest.approx(expected, abs=1e-9)
    assert base_rate("STAT:sot:away:under:6.5", 4.6) == pytest.approx(1.0 - expected, abs=1e-9)
    with pytest.raises(ValueError):
        base_rate("STAT:sot:away:over:6.5")


def test_ah_base_rate_from_reference_match():
    home_half = base_rate("AH_HOME:-0.5")
    away_half = base_rate("AH_AWAY:+0.5")
    assert home_half == pytest.approx(1.0 - away_half)  # complementari senza void
    assert 0.35 < home_half < 0.5
    assert 0.5 < base_rate("AH_HOME:+0.25") < 0.75
    assert base_rate("AH_HOME:0.0") > 0.5  # a rimborso sul pari, la casa vince più spesso


# --- verdetti -------------------------------------------------------------------------
def _inputs(**over):
    base = dict(
        market_key="AWAY",
        p=0.42,
        lo=0.38,
        hi=0.46,
        uncertainty_score=0.1,
        uncertainty_level="bassa",
        base_rate=0.30,
        label="2",
        quota_bet365=3.0,
        quota_betfair=3.1,
        lineups_status="ufficiali",
    )
    base.update(over)
    return RowInputs(**base)


def test_verdict_playable_uses_bet365_first():
    row = evaluate_market(_inputs())
    p_prudent = 0.38 - 0.08 * 0.1
    assert row.p_prudent == pytest.approx(p_prudent, abs=1e-4)
    assert row.quota_used == 3.0
    assert row.bookmaker_used == "Bet365"
    assert row.bookmaker_id == BOOKMAKER_BET365_ID
    assert row.expected_profit == pytest.approx(p_prudent * 3.0 - 1.0, abs=1e-4)
    assert row.verdict == VERDICT_PLAYABLE
    assert row.verdict_label == "Giocabile"
    assert row.provisional is False
    assert row.advised is True


def test_verdict_falls_back_to_betfair_when_bet365_missing():
    row = evaluate_market(_inputs(quota_bet365=None))
    assert row.quota_used == 3.1
    assert row.bookmaker_used == "Betfair"
    assert row.bookmaker_id == BOOKMAKER_BETFAIR_ID


def test_verdict_no_odds():
    row = evaluate_market(_inputs(quota_bet365=None, quota_betfair=None))
    assert row.verdict == VERDICT_NO_ODDS
    assert row.quota_used is None
    assert row.expected_profit is None


def test_verdict_fair_price_below_margin():
    row = evaluate_market(_inputs(quota_bet365=2.6, quota_betfair=None))
    assert 0 < (row.expected_profit or 0) < PROFIT_MARGIN or (row.expected_profit or 0) <= 0
    assert row.verdict == VERDICT_FAIR_PRICE


def test_verdict_fair_price_when_quota_below_minimum_even_with_margin():
    row = evaluate_market(_inputs(p=0.97, lo=0.96, base_rate=0.93, quota_bet365=1.10, quota_betfair=None))
    assert row.quota_used < MIN_QUOTA
    assert (row.expected_profit or 0) >= PROFIT_MARGIN
    assert row.verdict == VERDICT_FAIR_PRICE


def test_verdict_high_uncertainty_beats_profit():
    row = evaluate_market(_inputs(uncertainty_level="alta"))
    assert row.verdict == VERDICT_UNCERTAIN
    assert row.expected_profit is not None  # il prezzo resta visibile


def test_verdict_descriptive_for_stat_without_passed_exam():
    row = evaluate_market(_inputs(market_key="STAT:fouls:home:over:4.5", label="Milan over 4,5 falli", stat_exam="non_superato", base_rate=0.5))
    assert row.verdict == VERDICT_DESCRIPTIVE  # i falli non sono tra le statistiche giocabili
    assert row.family == "STAT_fouls"
    assert row.stat_exam == "non_superato"


def test_descriptive_only_applies_to_stat_markets():
    row = evaluate_market(_inputs(stat_exam="non_superato"))
    assert row.verdict == VERDICT_PLAYABLE
    assert row.stat_exam is None


def test_provisional_flag_and_advised_flag():
    row = evaluate_market(_inputs(lineups_status="non_note", advised=False))
    assert row.verdict == VERDICT_PLAYABLE  # le formazioni non bloccano il verdetto
    assert row.provisional is True
    assert row.advised is False
    assert row.to_dict()["advised"] is False


# --- partita intera -----------------------------------------------------------------------
def test_evaluate_fixture_covers_classic_ah_and_all_stat_lines():
    rows = evaluate_fixture(goals(), stats(), odds(), HOME, AWAY, "non_note")
    keys = {r.market_key for r in rows}
    assert len(rows) == len(keys)
    assert {"HOME", "DRAW", "AWAY", "OVER_2_5", "HOME_PT", "AH_HOME:-0.5", "AH_AWAY:-0.5", "AH_HOME:+0.25"} <= keys
    # sot: 2 + 2 + 1 linee, over e under; corners: 1 + 1 linee, over e under
    assert sum(1 for k in keys if k.startswith("STAT:sot:")) == 10
    assert sum(1 for k in keys if k.startswith("STAT:corners:")) == 4
    assert len(rows) == 20 + 14


def test_evaluate_fixture_under_row_mirrors_over():
    rows = {r.market_key: r for r in evaluate_fixture(goals(), stats(), odds(), HOME, AWAY)}
    over, under = rows[SOT_KEY], rows["STAT:sot:away:under:6.5"]
    assert under.p == pytest.approx(1 - over.p)
    assert under.lo == pytest.approx(1 - over.hi)
    assert under.hi == pytest.approx(1 - over.lo)
    assert under.base_rate == pytest.approx(1 - over.base_rate, abs=1e-4)
    assert under.label == "Inter under 6,5 tiri in porta"


def test_evaluate_fixture_verdicts_from_sample():
    rows = {r.market_key: r for r in evaluate_fixture(goals(), stats(), odds(), HOME, AWAY, "non_note")}
    sot = rows[SOT_KEY]
    assert sot.verdict == VERDICT_PLAYABLE
    assert sot.quota_used == 2.30 and sot.quota_betfair == 2.40 and sot.bookmaker_used == "Bet365"
    assert sot.provisional is True
    expected_prudent = 0.56 - (0.56 - poisson_tail_over(4.6, 6.5)) * 0.22  # lo del campione = 0,61 - 0,05
    assert sot.p_prudent == pytest.approx(expected_prudent, abs=1e-4)
    assert sot.expected_profit == pytest.approx(expected_prudent * 2.3 - 1, abs=1e-3)
    assert rows["AWAY"].verdict == VERDICT_FAIR_PRICE
    assert rows["STAT:corners:home:over:4.5"].verdict == VERDICT_DESCRIPTIVE  # quotato ma esame non superato
    assert rows["HOME_PT"].verdict == VERDICT_NO_ODDS
    assert rows["UNDER_1_5"].bookmaker_used == "Betfair"


def test_evaluate_fixture_skips_unknown_keys_and_handles_missing_payloads():
    payload = goals()
    payload["markets"]["FOO_BAR"] = {"p": 0.5}
    rows = evaluate_fixture(payload, None, None, HOME, AWAY)
    assert all(r.market_key != "FOO_BAR" for r in rows)
    assert all(r.verdict == VERDICT_NO_ODDS for r in rows)
    assert evaluate_fixture(None, None, None, HOME, AWAY) == []


def test_advised_families_mark_rows():
    rows = evaluate_fixture(goals(), stats(), odds(), HOME, AWAY, advised_families={"STAT_sot": False})
    by_key = {r.market_key: r for r in rows}
    assert by_key[SOT_KEY].advised is False
    assert by_key["AWAY"].advised is True


# --- giocata migliore e motivo dell'astensione ---------------------------------------------
def test_best_play_and_no_reason_when_play_exists():
    rows = evaluate_fixture(goals(), stats(), odds(), HOME, AWAY)
    play = best_play(rows)
    assert play is not None and play.market_key == SOT_KEY
    assert no_play_reason(rows) is None


def test_best_play_none_and_reason_no_odds():
    rows = evaluate_fixture(goals(), stats(), None, HOME, AWAY)
    assert best_play(rows) is None
    assert no_play_reason(rows) == VERDICT_NO_ODDS


def test_no_play_reason_fair_price():
    fair_odds = odds()
    fair_odds[BOOKMAKER_BET365_ID][SOT_KEY] = 1.85
    fair_odds[BOOKMAKER_BETFAIR_ID][SOT_KEY] = 1.90
    rows = evaluate_fixture(goals(), stats(), fair_odds, HOME, AWAY)
    assert best_play(rows) is None
    assert no_play_reason(rows) == VERDICT_FAIR_PRICE


def test_no_play_reason_high_uncertainty():
    payload = goals()
    payload["uncertainty"]["level"] = "alta"
    rows = evaluate_fixture(payload, stats(), odds(), HOME, AWAY)
    assert no_play_reason(rows) == VERDICT_UNCERTAIN


def test_no_play_reason_descriptive_when_only_descriptive_priced():
    only = {BOOKMAKER_BET365_ID: {"STAT:corners:home:over:4.5": 1.9, "STAT:corners:away:under:4.5": 1.9}}
    rows = evaluate_fixture(goals(), stats(), only, HOME, AWAY)
    assert no_play_reason(rows) == VERDICT_DESCRIPTIVE


def test_no_play_reason_empty():
    assert no_play_reason([]) is None
    assert best_play([]) is None


def test_poisson_tail_edges():
    assert poisson_tail_over(3.0, -0.5) == 1.0
    assert 0.0 < poisson_tail_over(3.0, 0.5) < 1.0
    assert math.isclose(poisson_tail_over(3.0, 0.5), 1 - math.exp(-3.0))
