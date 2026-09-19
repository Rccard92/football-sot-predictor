"""Storico CSV e partite in programma: forme, guardie sul lockbox, id stabili."""

from __future__ import annotations

from collections import Counter

import pytest

from app.services.cecchino_v4.constants import CURRENT_SEASON, HISTORY_SEASONS, LEAGUES, LOCKBOX_SEASON
from app.services.cecchino_v4.history.fixtures_csv import load_upcoming
from app.services.cecchino_v4.history.football_data import load_history


def test_history_default_excludes_lockbox_and_current():
    h = load_history(league_codes=["I1"])
    seasons = {m.season_label for m in h.matches}
    assert seasons == set(HISTORY_SEASONS)
    assert LOCKBOX_SEASON not in seasons and CURRENT_SEASON not in seasons


def test_history_guard_raises_without_flags():
    with pytest.raises(ValueError):
        load_history(seasons=[LOCKBOX_SEASON], league_codes=["I1"])
    with pytest.raises(ValueError):
        load_history(seasons=[CURRENT_SEASON], league_codes=["I1"])


def test_history_ids_are_stable_and_unique():
    h1 = load_history(league_codes=["I1", "E0"], seasons=["2024/2025"])
    h2 = load_history(league_codes=["I1", "E0"], seasons=["2024/2025"])
    ids1 = [m.lab_match_id for m in h1.matches]
    assert ids1 == [m.lab_match_id for m in h2.matches]
    assert len(set(ids1)) == len(ids1)
    assert all(m.lab_match_id in h1.extras for m in h1.matches)


def test_history_season_context_annotated():
    h = load_history(league_codes=["I1"], seasons=["2024/2025"])
    assert len(h.matches) == 380
    assert Counter(m.phase for m in h.matches)["early"] > 0
    assert any(m.eval_eligible for m in h.matches)
    ex = h.extras[h.matches[-1].lab_match_id]
    assert ex.home_corners is not None
    assert "HOME" in ex.odds_close and ex.odds_close["HOME"] > 1.0


def test_all_16_leagues_present_in_history():
    h = load_history(seasons=["2024/2025"])
    comps = {m.competition for m in h.matches}
    assert comps == {lg.competition for lg in LEAGUES}


def test_upcoming_fixtures_shape():
    fx = load_upcoming()
    if not fx:  # il file pubblico puo' essere assente
        pytest.skip("fixtures.csv non presente")
    f = fx[0]
    assert f.kickoff_at.tzinfo is not None
    assert f.synthetic_api_fixture_id < 0
    assert f.season_label == CURRENT_SEASON
    keys = {k for odds in f.odds.values() for k in odds}
    assert keys & {"HOME", "DRAW", "AWAY"}
