"""Unit test logica pura Lineup Impact v2."""

from app.services.sportapi.sportapi_lineup_impact_logic import (
    classify_lineup_status,
    clamp_factor,
    compute_impact_confidence,
    find_replacement,
    penalty_weight_for_status,
    resolve_display_name,
)


def test_resolve_display_name_api_first():
    assert resolve_display_name(player_name_api="Kean") == "Kean"


def test_resolve_display_name_fallback_api_id():
    name = resolve_display_name(api_player_id=12345)
    assert "API-Sports ID: 12345" in name


def test_resolve_display_name_fallback_sportapi_id():
    name = resolve_display_name(sportapi_player_id=99)
    assert "SportAPI ID: 99" in name


def test_classify_starter():
    assert (
        classify_lineup_status(
            player_id=1,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=95.0,
            sportapi_provider_id=10,
            sportapi_starter_pids={10},
            sportapi_bench_pids=set(),
            sportapi_missing_pids=set(),
        )
        == "STARTER"
    )


def test_classify_bench():
    assert (
        classify_lineup_status(
            player_id=2,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=90.0,
            sportapi_provider_id=20,
            sportapi_starter_pids=set(),
            sportapi_bench_pids={20},
            sportapi_missing_pids=set(),
        )
        == "BENCH"
    )


def test_classify_missing():
    assert (
        classify_lineup_status(
            player_id=3,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=88.0,
            sportapi_provider_id=30,
            sportapi_starter_pids=set(),
            sportapi_bench_pids=set(),
            sportapi_missing_pids={30},
        )
        == "MISSING"
    )


def test_classify_out_of_lineup():
    assert (
        classify_lineup_status(
            player_id=4,
            mapping_recommendation="AUTO_SAFE",
            mapping_confidence=92.0,
            sportapi_provider_id=40,
            sportapi_starter_pids=set(),
            sportapi_bench_pids=set(),
            sportapi_missing_pids=set(),
        )
        == "OUT_OF_LINEUP"
    )


def test_classify_unmapped_low_score():
    assert (
        classify_lineup_status(
            player_id=5,
            mapping_recommendation="REVIEW",
            mapping_confidence=70.0,
            sportapi_provider_id=50,
            sportapi_starter_pids={50},
            sportapi_bench_pids=set(),
            sportapi_missing_pids=set(),
        )
        == "UNMAPPED"
    )


def test_penalty_share_bench_vs_missing_probable():
    share = 0.20
    bench_pen = share * penalty_weight_for_status("BENCH", False)
    missing_pen = share * penalty_weight_for_status("MISSING", False)
    assert bench_pen == 0.07
    assert missing_pen == 0.20


def test_replacement_credit_non_negative_net():
    starter_pool = [
        {
            "player_id": 100,
            "display_role": "A",
            "team_sot_share": 0.12,
            "sot_per_90": 1.5,
            "player_name": "Sostituto",
        },
    ]
    rep, credit, _ = find_replacement(
        target_role="A",
        target_share=0.18,
        starter_pool=starter_pool,
        bench_pool=[],
        used_replacement_player_ids=set(),
    )
    assert rep is not None
    assert credit > 0
    penalty = 0.18
    net = max(0.0, penalty - credit)
    assert net >= 0


def test_clamp_factor_probable_max_115():
    assert clamp_factor(0.5, False) == 0.75
    assert clamp_factor(1.5, False) == 1.15


def test_clamp_factor_official_max_120():
    assert clamp_factor(0.5, True) == 0.65
    assert clamp_factor(1.5, True) == 1.20


def test_confidence_unmapped_lowers_label():
    top = [
        {"status": "UNMAPPED", "mapping_recommendation": "NO_MATCH", "player_name": "X"},
        {"status": "UNMAPPED", "mapping_recommendation": "NO_MATCH", "player_name": "Y"},
    ]
    label, reasons = compute_impact_confidence(
        confirmed=False,
        top_players=top,
        profiles_missing=False,
    )
    assert label in ("media", "bassa")
    assert any("non mappati" in r for r in reasons)


def test_confidence_roster_missing():
    label, reasons = compute_impact_confidence(
        confirmed=False,
        top_players=[],
        profiles_missing=False,
        roster_sync_hints=["missing", "ok"],
    )
    assert label in ("media", "bassa")
    assert any("filtro giocatori trasferiti" in r for r in reasons)
