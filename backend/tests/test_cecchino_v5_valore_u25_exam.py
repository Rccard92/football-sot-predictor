"""Prova storica V5 Valore Under 2,5 (Giovanni, 17-18/11/2026): riepilogo, fasce e stagione in corso."""

from datetime import date

import numpy as np

from app.services.cecchino_v3.constants import PHASE_FINAL, PHASE_MID
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v5.valore_u25_exam import _band, _fix_partial_season, _play_row, summarize


def _odds(goals: int, day: str = "2026-09-01", qu: float = 2.0) -> dict:
    return {
        "season": "2026/2027", "league": "Serie A", "home": "A", "away": "B", "kickoff": None, "day": date.fromisoformat(day),
        "qu": qu, "qo": 1.8, "cu": 1.9, "co": 1.9, "pu": None, "po": None, "goals": goals, "score": f"{goals}-0",
    }


def test_play_row_profit_and_novig_clv():
    won = _play_row(1, _odds(2), 0.6, 0.58, 0.57)
    assert won["esito"] == "vinta" and won["profitto"] == 1.0 and won["valore"] == 0.14
    # chiusura 1,90 / 1,90: probabilita' senza margine 50%, CLV = 2,00 x 0,5 - 1 = 0
    assert won["clv_b365"] == 0.0 and won["clv_pinnacle"] is None and won["profitto_chiusura"] == 0.9
    lost = _play_row(2, _odds(3), 0.6, 0.58, 0.57)
    assert lost["esito"] == "persa" and lost["profitto"] == -1.0


def test_summary_and_bootstrap_by_day():
    rows = [_play_row(i, _odds(2 if i % 2 else 3, f"2026-09-{1 + i // 2:02d}"), 0.6, 0.58, 0.57) for i in range(1, 11)]
    s = summarize(rows, np.random.default_rng(1))
    assert s["giocate"] == 10 and s["vinte_pct"] == 50.0 and s["roi_pre_pct"] == 0.0
    low, high = s["roi_ic95_pct"]
    assert low <= 0.0 <= high
    assert summarize([]) == {"giocate": 0}
    assert [_band(v) for v in (0.10, 0.149, 0.15, 0.2, 0.3)] == ["10-15", "10-15", "15-20", "20-25", "25-30"]


def _rec(mid: int, season: str, home: str, away: str, day: int) -> MatchRecord:
    return MatchRecord(
        lab_match_id=mid, competition="Serie A", group="IT", season_label=season, match_date=date(2026, 1, 1),
        kickoff_at=None, day=day, home_team=home, away_team=away, ft_home=1, ft_away=0, ht_home=0, ht_away=0,
    )


def test_partial_season_uses_last_season_length():
    # stagione passata: 38 gare a squadra; stagione in corso con 6 gare giocate: non e' la fase finale
    prev = [_rec(i, "2025/2026", "A", "B", i) for i in range(38)]
    cur = _rec(100, "2026/2027", "A", "B", 200)
    cur.home_played = cur.away_played = 6
    cur.home_remaining = cur.away_remaining = 1  # quello che direbbe il conteggio sulle sole gare scaricate
    cur.eval_eligible, cur.phase = True, PHASE_FINAL
    _fix_partial_season(prev + [cur], "2026/2027", "2025/2026")
    assert cur.home_remaining == 32 and cur.phase == PHASE_MID
