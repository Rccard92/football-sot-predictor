"""Metodi di puntata del Diario analisi (30/10/2026): stessi numeri del file Excel."""

from __future__ import annotations

from app.services.analyst.staking import SettledBet as B
from app.services.analyst.staking import cycle_state, recovery_weight, suggest_stake

CECCHINO = {"bankroll": 1000, "target_pct": 0.2, "bets": 10, "strike": 0.6}


def test_cecchino_first_and_next_stake():
    s = cycle_state("cecchino", CECCHINO, [])
    assert s.info["ref_quota"] == 1.33  # 1 + round(200/6)/round(1000/10)
    assert suggest_stake(s, 1.5)["stake"] == 100.0
    assert suggest_stake(s, 1.2)["stake"] == 165.0  # ceil(33 / 0.2)
    s = cycle_state("cecchino", CECCHINO, [B(100, 1.5, "won")])
    assert (s.info["wins_needed"], s.info["losses_allowed"]) == (5, 4)
    assert suggest_stake(s, 1.5)["stake"] == 60.0  # round((200-50)/5 / 0.5)


def test_cecchino_target_reached_stops():
    s = cycle_state("cecchino", CECCHINO, [B(100, 3.0, "won")])
    assert s.status == "obiettivo_raggiunto" and suggest_stake(s, 2)["stake"] is None


def test_ceccxino_up_after_loss_down_after_win():
    assert suggest_stake(cycle_state("ceccxino", {"bankroll": 1000}, []), 2)["stake"] == 60.0
    s = cycle_state("ceccxino", {"bankroll": 1000}, [B(60, 2, "lost")])
    assert suggest_stake(s, 2)["stake"] == 90.0
    s = cycle_state("ceccxino", {"bankroll": 1000}, [B(60, 2, "lost"), B(90, 2, "won")])
    assert suggest_stake(s, 2)["stake"] == 89.0
    s = cycle_state("ceccxino", {"bankroll": 1000}, [B(60, 2, "won")])
    assert suggest_stake(s, 2)["stake"] == 60.0  # mai sotto la base


def test_ceccxino_stop_loss():
    s = cycle_state("ceccxino", {"bankroll": 1000, "stop_loss_pct": 0.1}, [B(60, 2, "lost"), B(90, 2, "lost")])
    assert s.status == "stop_loss"


def test_meraviglia_percentage_plus_recovery():
    assert suggest_stake(cycle_state("meraviglia", {"bankroll": 1000, "stake_pct": 0.05}, []), 2)["stake"] == 50.0
    s = cycle_state("meraviglia", {"bankroll": 1000, "stake_pct": 0.05}, [B(50, 2, "lost")])
    assert s.bankroll == 950.0 and suggest_stake(s, 2)["stake"] == 52.5  # 5% di 950 + 10% di 50
    assert [recovery_weight(d) for d in (1, 3, 4, 6, 7, 12, 13, 17, 18, 20)] == [0.1, 0.1, 0.15, 0.15, 0.2, 0.2, 0.25, 0.25, 0.3, 0.3]


def test_void_does_not_count():
    s = cycle_state("ceccxino", {"bankroll": 1000}, [B(60, 2, "void")])
    assert s.bets_played == 0 and suggest_stake(s, 2)["stake"] == 60.0
