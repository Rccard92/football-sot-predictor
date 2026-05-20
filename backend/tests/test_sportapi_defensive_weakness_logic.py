"""Test logica impatto difensivo Lineup Impact."""

from app.services.sportapi.sportapi_defensive_weakness_logic import (
    clamp_defensive_weakness_factor,
    compute_defensive_weakness_side,
    compute_raw_defensive_importance,
    defensive_penalty_weight,
    find_defensive_replacement,
    is_defensive_relevant_position,
)


def test_is_defensive_relevant_gk_and_def():
    assert is_defensive_relevant_position("G")
    assert is_defensive_relevant_position("CB")
    assert not is_defensive_relevant_position("LW")


def test_defensive_penalty_missing_full():
    assert defensive_penalty_weight("MISSING", False) == 1.0
    assert defensive_penalty_weight("BENCH", True) == 0.35


def test_defensive_replacement_capped():
    starter = [
        {
            "player_id": 1,
            "defensive_role": "D",
            "defensive_importance": 0.8,
            "player_name": "Sub",
        },
    ]
    rep, credit = find_defensive_replacement(
        target_role="D",
        starter_pool=starter,
        bench_pool=[],
        used_ids=set(),
        max_credit=0.3,
    )
    assert rep is not None
    assert credit <= 0.3


def test_clamp_defensive_weakness_max_probable():
    assert clamp_defensive_weakness_factor(2.0, False) == 1.15
    assert clamp_defensive_weakness_factor(0.5, True) == 1.0


def test_compute_defensive_weakness_side_increases_factor():
    key = [
        {
            "player_id": 1,
            "player_name": "Parisi",
            "defensive_role": "D",
            "defensive_importance": 0.9,
            "status": "MISSING",
            "status_note": "Infortunato",
        },
    ]
    out = compute_defensive_weakness_side(
        team_name="Fiorentina",
        confirmed=False,
        key_players=key,
        starter_pool=[],
        bench_pool=[],
    )
    assert out["defensive_weakness_factor"] > 1.0
    assert out["gross_defensive_loss"] > 0


def test_raw_importance_goalkeeper_high():
    raw = compute_raw_defensive_importance(
        position="G",
        total_minutes=2000,
        starts=22,
        appearances=25,
        avg_rating=7.0,
        tackles_total=0,
        interceptions=0,
        tackles_blocks=0,
        duels_won=0,
    )
    assert raw > 0.5
