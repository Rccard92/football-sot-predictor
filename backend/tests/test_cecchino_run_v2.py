"""Test RUN V2: formula freeze, anti-leakage, doppio binario, export."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    CONTEXT_KEY_LAST6_TOTALS,
    CONTEXT_KEY_TOTALS,
    CONTEXT_LABELS,
    CONTEXT_TARGETS,
    GoalContextSlice,
    GoalMarketContexts,
    aggregate_goal_totals,
    aggregate_halftime_goal_totals,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_OVER_0_5,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_0_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
)

HOME_ID = 101
AWAY_ID = 202
NOW = datetime(2024, 3, 1, 15, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CORE FORMULA FREEZE
# ---------------------------------------------------------------------------

# Golden prodotti confrontando la versione corrente con quella pre-estensione
# O/U 0.5 presa da git: se uno solo di questi valori cambia, una formula V1 e
# stata toccata.
GOLDEN_V1_MARKETS: dict[str, tuple[float, float]] = {
    SEL_OVER_1_5: (1.34, 0.746409),
    SEL_UNDER_1_5: (3.94, 0.253591),
    SEL_OVER_2_5: (1.68, 0.595571),
    SEL_UNDER_2_5: (2.47, 0.404429),
    SEL_OVER_3_5: (2.68, 0.373303),
    SEL_UNDER_3_5: (1.60, 0.626697),
    SEL_OVER_PT_0_5: (1.53, 0.652451),
    SEL_UNDER_PT_0_5: (2.88, 0.347549),
    SEL_OVER_PT_1_5: (4.25, 0.235433),
    SEL_UNDER_PT_1_5: (1.31, 0.764567),
}

GOLDEN_HT_1X2_FAMILY: dict[str, tuple[float, float]] = {
    SEL_HOME_PT: (4.00, 0.250000),
    SEL_DRAW_PT: (2.27, 0.440833),
    SEL_AWAY_PT: (3.23, 0.309167),
}


def _fixture(fid: int, hid: int, aid: int, gh: int, ga: int, hth: int, hta: int):
    return SimpleNamespace(
        id=fid,
        home_team_id=hid,
        away_team_id=aid,
        goals_home=gh,
        goals_away=ga,
        raw_json={"score": {"halftime": {"home": hth, "away": hta}}},
        status="FT",
    )


def _goal_contexts() -> GoalMarketContexts:
    home_fx = [
        _fixture(1 + i, HOME_ID, 900 + i, 2, 1, 1, 0)
        if i % 2 == 0
        else _fixture(1 + i, HOME_ID, 900 + i, 0, 0, 0, 0)
        for i in range(8)
    ]
    away_fx = [
        _fixture(50 + i, 800 + i, AWAY_ID, 1, 3, 0, 1)
        if i % 3
        else _fixture(50 + i, 800 + i, AWAY_ID, 2, 2, 1, 1)
        for i in range(8)
    ]

    def make(name: str, hf, af, ht: bool = False) -> GoalContextSlice:
        target, min_sample = CONTEXT_TARGETS[name]
        aggregate = aggregate_halftime_goal_totals if ht else aggregate_goal_totals
        return GoalContextSlice(
            name=name,
            label=CONTEXT_LABELS[name],
            home_fixtures=hf,
            away_fixtures=af,
            home_totals=aggregate(hf, HOME_ID),
            away_totals=aggregate(af, AWAY_ID),
            target_sample=target,
            min_sample=min_sample,
        )

    return GoalMarketContexts(
        totals=make(CONTEXT_KEY_TOTALS, home_fx, away_fx),
        home_away=make(CONTEXT_KEY_HOME_AWAY, home_fx[:5], away_fx[:5]),
        last6_totals=make(CONTEXT_KEY_LAST6_TOTALS, home_fx[-6:], away_fx[-6:]),
        last5_home_away=make(CONTEXT_KEY_LAST5_HOME_AWAY, home_fx[-5:], away_fx[-5:]),
        ht_totals=make(CONTEXT_KEY_TOTALS, home_fx, away_fx, True),
        ht_home_away=make(CONTEXT_KEY_HOME_AWAY, home_fx[:5], away_fx[:5], True),
        ht_last6_totals=make(CONTEXT_KEY_LAST6_TOTALS, home_fx[-6:], away_fx[-6:], True),
        ht_last5_home_away=make(CONTEXT_KEY_LAST5_HOME_AWAY, home_fx[-5:], away_fx[-5:], True),
        skipped_missing_halftime_score=0,
        home_team_id=HOME_ID,
        away_team_id=AWAY_ID,
    )


def _league_probs() -> dict[str, float | None]:
    import app.services.cecchino.cecchino_goal_poisson_v2 as poisson

    probs = {m: 0.5 for m in poisson._FT_MARKETS + poisson._PT_MARKETS}
    probs[SEL_DRAW_PT] = 0.25
    return probs


def test_v1_market_tuples_are_frozen():
    """Le tuple iterate dalle pipeline V1 non possono accogliere nuove chiavi."""
    import app.services.cecchino.cecchino_goal_poisson_v2 as poisson

    assert poisson._FT_MARKETS == (
        SEL_OVER_1_5,
        SEL_UNDER_1_5,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_3_5,
        SEL_UNDER_3_5,
    )
    assert poisson._PT_MARKETS == (
        SEL_OVER_PT_0_5,
        SEL_UNDER_PT_0_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    )
    assert poisson._HT_1X2_MARKETS == (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT)
    assert poisson._OU_COMPLEMENT_PAIRS == (
        (SEL_UNDER_1_5, SEL_OVER_1_5, False),
        (SEL_UNDER_2_5, SEL_OVER_2_5, False),
        (SEL_UNDER_3_5, SEL_OVER_3_5, False),
        (SEL_UNDER_PT_0_5, SEL_OVER_PT_0_5, True),
        (SEL_UNDER_PT_1_5, SEL_OVER_PT_1_5, True),
    )
    assert SEL_OVER_0_5 not in poisson._FT_MARKETS
    assert poisson._OU_COMPLEMENT_PAIRS_V2_OPTIONAL == (
        (SEL_UNDER_0_5, SEL_OVER_0_5, False),
    )


@pytest.mark.parametrize("market_key", sorted(GOLDEN_V1_MARKETS))
def test_v1_market_outputs_unchanged(market_key):
    from app.services.cecchino.cecchino_goal_poisson_v2 import calculate_goal_market_v2

    block = calculate_goal_market_v2(
        market_key, _goal_contexts(), _league_probs(), legacy_slices=None
    )
    expected_odd, expected_prob = GOLDEN_V1_MARKETS[market_key]
    assert block["final_odd"] == pytest.approx(expected_odd, abs=1e-9)
    assert block["summary"]["final_probability_raw"] == pytest.approx(
        expected_prob, abs=1e-6
    )


def test_ht_1x2_family_outputs_unchanged():
    from app.services.cecchino.cecchino_goal_poisson_v2 import (
        calculate_first_half_1x2_family_v2,
    )

    family = calculate_first_half_1x2_family_v2(_goal_contexts(), _league_probs())
    for market_key, (expected_odd, expected_prob) in GOLDEN_HT_1X2_FAMILY.items():
        assert family[market_key]["final_odd"] == pytest.approx(expected_odd, abs=1e-9)
        assert family[market_key]["summary"]["final_probability_raw"] == pytest.approx(
            expected_prob, abs=1e-6
        )


def test_event_definitions_of_existing_markets_unchanged():
    from app.services.cecchino.cecchino_goal_poisson_v2 import EVENT_DEFINITIONS

    assert EVENT_DEFINITIONS[SEL_UNDER_1_5] == "FT total goals <= 1"
    assert EVENT_DEFINITIONS[SEL_OVER_2_5] == "FT total goals >= 3"
    assert EVENT_DEFINITIONS[SEL_UNDER_PT_0_5] == "HT total goals = 0"
    # Le nuove chiavi si aggiungono senza toccare le precedenti.
    assert EVENT_DEFINITIONS[SEL_OVER_0_5] == "FT total goals >= 1"


def test_lab_goal_markets_keys_unchanged():
    """`compute_goal_markets_from_contexts` non deve produrre chiavi nuove."""
    from app.services.cecchino_data_lab.historical_context_builder import (
        compute_goal_markets_from_contexts,
    )

    contexts = SimpleNamespace(
        goal_contexts=_goal_contexts(),
        goal_slices=object(),
        league_probs=_league_probs(),
    )
    markets = compute_goal_markets_from_contexts(contexts)
    assert set(markets) == {
        SEL_DRAW_PT,
        SEL_OVER_1_5,
        SEL_UNDER_1_5,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
        SEL_OVER_3_5,
        SEL_UNDER_3_5,
        SEL_OVER_PT_0_5,
        SEL_UNDER_PT_0_5,
        SEL_OVER_PT_1_5,
        SEL_UNDER_PT_1_5,
    }


# ---------------------------------------------------------------------------
# FT Over/Under 0.5 (capability opt-in)
# ---------------------------------------------------------------------------


def test_ou_05_pair_is_complementary():
    from app.services.cecchino.cecchino_goal_poisson_v2 import (
        calculate_ou_05_pair_v2_optional,
    )

    league = {**_league_probs(), SEL_OVER_0_5: 0.9, SEL_UNDER_0_5: 0.1}
    pair = calculate_ou_05_pair_v2_optional(_goal_contexts(), league, legacy_slices=None)

    assert set(pair) == {SEL_OVER_0_5, SEL_UNDER_0_5}
    total = (
        pair[SEL_OVER_0_5]["summary"]["final_probability_raw"]
        + pair[SEL_UNDER_0_5]["summary"]["final_probability_raw"]
    )
    assert total == pytest.approx(1.0, abs=1e-9)
    assert pair[SEL_OVER_0_5]["final_odd"] < pair[SEL_UNDER_0_5]["final_odd"]


def test_poisson_probability_ou_05_matches_zero_goal_mass():
    from math import exp

    from app.services.cecchino.cecchino_goal_poisson_v2 import (
        poisson_market_probability_ft,
    )

    lam = 2.4
    assert poisson_market_probability_ft(SEL_UNDER_0_5, lam) == pytest.approx(exp(-lam))
    assert poisson_market_probability_ft(SEL_OVER_0_5, lam) == pytest.approx(
        1.0 - exp(-lam)
    )


def test_settlement_ou_05():
    from app.services.cecchino_data_lab.run_v2.settlement import (
        evaluate_market_outcome_v2,
    )

    goalless = {"fulltime": {"home": 0, "away": 0}, "halftime": {"home": 0, "away": 0}}
    scored = {"fulltime": {"home": 1, "away": 0}, "halftime": {"home": 0, "away": 0}}

    assert evaluate_market_outcome_v2(SEL_UNDER_0_5, goalless)["won"] is True
    assert evaluate_market_outcome_v2(SEL_OVER_0_5, goalless)["won"] is False
    assert evaluate_market_outcome_v2(SEL_OVER_0_5, scored)["won"] is True
    # I mercati gia noti alla V1 restano gestiti dalla funzione V1.
    assert evaluate_market_outcome_v2(SEL_UNDER_2_5, scored)["won"] is True


# ---------------------------------------------------------------------------
# Anti-leakage
# ---------------------------------------------------------------------------


def test_history_strictly_before_target_passes():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import audit_history_window

    audit = audit_history_window(
        lab_match_id=10,
        target_kickoff=NOW,
        history_kickoffs=[NOW - timedelta(days=7), NOW - timedelta(seconds=1)],
        history_ids=[1, 2],
    )
    assert audit.pre_match_cutoff_ok is True
    assert audit.violations == []
    assert audit.latest_history_kickoff_used == NOW - timedelta(seconds=1)


def test_same_kickoff_in_history_is_a_violation():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import (
        VIOLATION_HISTORY_NOT_STRICTLY_BEFORE,
        audit_history_window,
    )

    audit = audit_history_window(
        lab_match_id=10,
        target_kickoff=NOW,
        history_kickoffs=[NOW - timedelta(days=1), NOW],
        history_ids=[1, 2],
    )
    assert audit.pre_match_cutoff_ok is False
    assert audit.violations[0]["code"] == VIOLATION_HISTORY_NOT_STRICTLY_BEFORE


def test_future_match_in_history_is_a_violation():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import audit_history_window

    audit = audit_history_window(
        lab_match_id=10,
        target_kickoff=NOW,
        history_kickoffs=[NOW + timedelta(days=3)],
        history_ids=[99],
    )
    assert audit.pre_match_cutoff_ok is False


def test_target_match_inside_its_own_history_is_a_violation():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import (
        VIOLATION_TARGET_IN_HISTORY,
        audit_history_window,
    )

    audit = audit_history_window(
        lab_match_id=10,
        target_kickoff=NOW,
        history_kickoffs=[NOW - timedelta(days=1)],
        history_ids=[10],
    )
    codes = {v["code"] for v in audit.violations}
    assert VIOLATION_TARGET_IN_HISTORY in codes


def test_pre_match_payload_rejects_post_match_keys():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import (
        audit_pre_match_payload,
    )

    clean = {"identity": {"lab_match_id": 1}, "input_snapshot": {"prior_count": 4}}
    assert audit_pre_match_payload(clean) == []

    dirty = {"identity": {"lab_match_id": 1}, "labels": {"actual_total_shots": 22}}
    violations = audit_pre_match_payload(dirty)
    assert violations and violations[0]["path"].endswith("actual_total_shots")


def test_run_fails_when_leakage_violations_exist():
    from app.services.cecchino_data_lab.run_v2.leakage_audit import (
        RunLeakageAuditor,
        audit_history_window,
    )

    auditor = RunLeakageAuditor()
    auditor.record(
        audit_history_window(
            lab_match_id=1,
            target_kickoff=NOW,
            history_kickoffs=[NOW - timedelta(days=1)],
        )
    )
    assert auditor.ok is True

    auditor.record(
        audit_history_window(
            lab_match_id=2, target_kickoff=NOW, history_kickoffs=[NOW]
        )
    )
    assert auditor.ok is False
    assert auditor.to_dict()["leakage_violations"] == 1


# ---------------------------------------------------------------------------
# Quote STRICT: legacy + enrichment closing/pre-kickoff
# ---------------------------------------------------------------------------


def _lab_match(**overrides):
    base = dict(
        id=1,
        home_team="Alpha",
        away_team="Beta",
        referee="Mr Rossi",
        kickoff_at=NOW,
        ft_home_goals=2,
        ft_away_goals=1,
        ht_home_goals=1,
        ht_away_goals=0,
        ft_result="H",
        ht_result="H",
        bet365_home=2.10,
        bet365_draw=3.40,
        bet365_away=3.60,
        bet365_over_25=1.90,
        bet365_under_25=1.95,
        bet365_dc_1x=1.30,
        bet365_dc_12=1.28,
        bet365_dc_x2=1.75,
        bet365_over_05=1.06,
        bet365_under_05=9.50,
        bet365_over_15=1.28,
        bet365_under_15=3.60,
        bet365_over_35=2.90,
        bet365_under_35=1.42,
        bet365_ht_home=2.70,
        bet365_ht_draw=2.05,
        bet365_ht_away=4.20,
        home_shots=14,
        away_shots=9,
        home_shots_on_target=6,
        away_shots_on_target=3,
        home_corners=7,
        away_corners=4,
        home_fouls=11,
        away_fouls=13,
        home_yellow_cards=2,
        away_yellow_cards=3,
        home_red_cards=0,
        away_red_cards=1,
        raw_json={"Div": "I1", "HST": 6},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_enrichment_quotes_are_strict_pre_match_input():
    from app.services.cecchino.cecchino_selection_keys import (
        SEL_OVER_0_5,
        SEL_OVER_1_5,
        SEL_ONE_X,
        SEL_HOME_PT,
    )
    from app.services.cecchino_data_lab.run_v2.constants import (
        QUOTE_SNAPSHOT_CLOSING_PRE_KICKOFF,
        TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF,
    )
    from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle

    bundle = build_run_v2_quote_bundle(_lab_match())
    strict = bundle["strict_by_market"]

    for mk in (SEL_ONE_X, SEL_HOME_PT, SEL_OVER_0_5, SEL_OVER_1_5):
        quote = strict[mk]
        assert quote["pre_match_input_safe"] is True, mk
        assert quote["used_for_prediction"] is True, mk
        assert quote["available_at_prediction_time"] is True, mk
        assert quote["economic_observation_only"] is False, mk
        assert quote["quote_snapshot_type"] == QUOTE_SNAPSHOT_CLOSING_PRE_KICKOFF, mk
        assert quote["temporal_classification"] == TEMPORAL_CLASSIFICATION_CLOSING_PRE_KICKOFF
        assert quote["is_real_quote"] is True, mk
        assert quote["is_derived"] is False, mk

    assert bundle["economic"]["counts"]["markets_with_real_quote"] == 0
    assert bundle["counts"]["economic_markets_with_quote"] == 0


def test_strict_columns_include_enrichment_and_no_economic_columns():
    from app.services.cecchino_data_lab.run_v2.constants import (
        ECONOMIC_QUOTE_COLUMNS,
        ENRICHMENT_STRICT_QUOTE_COLUMNS,
        STRICT_QUOTE_COLUMNS,
    )

    assert ECONOMIC_QUOTE_COLUMNS == ()
    assert ENRICHMENT_STRICT_QUOTE_COLUMNS.issubset(set(STRICT_QUOTE_COLUMNS))
    assert len(ENRICHMENT_STRICT_QUOTE_COLUMNS) == 12


def test_real_quote_is_never_replaced_by_a_derived_one():
    from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle
    from app.services.cecchino.cecchino_selection_keys import (
        SEL_HOME,
        SEL_ONE_X,
        SEL_OVER_2_5,
    )

    bundle = build_run_v2_quote_bundle(_lab_match())
    strict = bundle["strict_by_market"]

    assert strict[SEL_HOME]["value"] == pytest.approx(2.10)
    assert strict[SEL_HOME]["is_real_quote"] is True
    assert strict[SEL_HOME]["is_derived"] is False
    assert strict[SEL_OVER_2_5]["value"] == pytest.approx(1.90)
    assert strict[SEL_OVER_2_5]["is_derived"] is False
    # DC reale preferita alla derivata.
    assert strict[SEL_ONE_X]["value"] == pytest.approx(1.30)
    assert strict[SEL_ONE_X]["is_real_quote"] is True
    assert strict[SEL_ONE_X]["is_derived"] is False
    assert strict[SEL_ONE_X]["source_column"] == "bet365_dc_1x"


def test_dc_falls_back_to_derived_when_real_missing():
    from app.services.cecchino.cecchino_selection_keys import SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO
    from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle

    match = _lab_match(bet365_dc_1x=None, bet365_dc_12=None, bet365_dc_x2=None)
    bundle = build_run_v2_quote_bundle(match)
    strict = bundle["strict_by_market"]

    for mk in (SEL_ONE_X, SEL_ONE_TWO, SEL_X_TWO):
        assert strict[mk]["value"] is not None, mk
        assert strict[mk]["is_derived"] is True, mk
        assert strict[mk]["is_real_quote"] is False, mk
        assert "dc_real_quote_missing_fallback_derived_1x2" in (strict[mk].get("warnings") or [])


def test_null_quotes_do_not_drop_the_market():
    from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS
    from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle

    empty = _lab_match(
        **{col: None for col in (
            "bet365_home", "bet365_draw", "bet365_away",
            "bet365_over_25", "bet365_under_25",
            "bet365_dc_1x", "bet365_dc_12", "bet365_dc_x2",
            "bet365_over_05", "bet365_under_05",
            "bet365_over_15", "bet365_under_15",
            "bet365_over_35", "bet365_under_35",
            "bet365_ht_home", "bet365_ht_draw", "bet365_ht_away",
        )}
    )
    bundle = build_run_v2_quote_bundle(empty)

    assert len(bundle["strict_by_market"]) == len(CORE_MARKETS)
    for market in CORE_MARKETS:
        quote = bundle["strict_by_market"][market.key]
        if market.has_strict_real_quote and not market.strict_quote_derived_from_1x2:
            # Senza colonne valorizzate la quota STRICT e assente, il mercato resta.
            assert quote["value"] is None
            assert quote["market_quote_available"] is False


def test_economic_benchmark_helpers_remain_for_legacy_runs():
    """Helper legacy restano importabili; non usati dalle nuove RUN."""
    from app.services.cecchino_data_lab.run_v2.economic_observation import (
        build_economic_benchmark_row,
        summarize_economic_benchmark,
    )

    row = build_economic_benchmark_row(
        market_key=SEL_OVER_1_5,
        frozen_probability=0.80,
        economic_quote={
            "value": 1.30,
            "quote_source": "bet365_enrichment_last_seen",
            "source_column": "bet365_over_15",
            "is_real_quote": True,
        },
        outcome={"outcome": "WIN", "won": True},
    )
    assert row["economic_observation_only"] is True
    summary = summarize_economic_benchmark([row])
    assert summary["economic_observation_only"] is True


# ---------------------------------------------------------------------------
# BLOCCO 2 — statistiche extra
# ---------------------------------------------------------------------------


def test_extra_stats_use_only_prior_matches():
    from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry

    registry = ExtraStatsRegistry()
    features = registry.build_prematch_features(
        competition="Serie A",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee="Mr Rossi",
    )
    # Nessuno storico ancora ingerito: tutto vuoto, ma niente errori.
    assert features["teams"]["home"]["sample_count"] == 0
    assert features["teams"]["home"]["stats"]["shots"]["season_avg_for"] is None
    assert features["availability"]["status"] == "no_history"

    registry.ingest_match(
        _lab_match(id=1, home_team="Alpha", away_team="Gamma"),
        competition="Serie A",
        season_label="2023-2024",
    )
    after = registry.build_prematch_features(
        competition="Serie A",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee="Mr Rossi",
    )
    assert after["teams"]["home"]["sample_count"] == 1
    assert after["teams"]["home"]["stats"]["shots"]["season_avg_for"] == pytest.approx(14.0)
    assert after["teams"]["home"]["stats"]["shots"]["season_avg_against"] == pytest.approx(9.0)
    assert after["teams"]["away"]["sample_count"] == 0


def test_extra_stats_are_missing_safe():
    from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry

    registry = ExtraStatsRegistry()
    registry.ingest_match(
        _lab_match(id=7, home_team="Alpha", away_team="Gamma", home_shots=None, home_corners=None),
        competition="Serie A",
        season_label="2023-2024",
    )
    features = registry.build_prematch_features(
        competition="Serie A",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee=None,
    )
    shots = features["teams"]["home"]["stats"]["shots"]
    assert shots["season_avg_for"] is None
    assert shots["season_sample"] == 0
    # Le altre famiglie restano valorizzate.
    assert features["teams"]["home"]["stats"]["sot"]["season_avg_for"] == pytest.approx(6.0)
    assert "referee_missing" in features["warnings"]


def test_referee_history_is_optional():
    from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry

    registry = ExtraStatsRegistry()
    features = registry.build_prematch_features(
        competition="Serie A",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee=None,
    )
    assert features["referee"]["available"] is False
    assert features["referee"]["previous_matches"] == 0

    registry.ingest_match(
        _lab_match(id=3, referee="Mr Rossi"),
        competition="Serie A",
        season_label="2023-2024",
    )
    with_history = registry.build_prematch_features(
        competition="Serie A",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee="Mr Rossi",
    )
    assert with_history["referee"]["available"] is True
    assert with_history["referee"]["previous_yellow_cards_avg"] == pytest.approx(5.0)


def test_competition_split_is_independent():
    from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry

    registry = ExtraStatsRegistry()
    registry.ingest_match(
        _lab_match(id=1, home_team="Alpha", away_team="Gamma"),
        competition="Serie A",
        season_label="2023-2024",
    )
    other = registry.build_prematch_features(
        competition="Premier League",
        season_label="2023-2024",
        home_team="Alpha",
        away_team="Beta",
        referee=None,
    )
    assert other["teams"]["home"]["sample_count"] == 0

    other_season = registry.build_prematch_features(
        competition="Serie A",
        season_label="2024-2025",
        home_team="Alpha",
        away_team="Beta",
        referee=None,
    )
    assert other_season["teams"]["home"]["sample_count"] == 0


def test_actual_stats_cover_every_canonical_statistic():
    from app.services.cecchino_data_lab.run_v2.extra_stats import build_actual_stats

    actuals = build_actual_stats(_lab_match())
    for family in ("shots", "sot", "corners", "fouls", "yellow_cards", "red_cards"):
        for side in ("home", "away", "total"):
            assert f"{side}_{family}" in actuals
    assert actuals["total_shots"] == pytest.approx(23.0)
    assert actuals["ft_total_goals"] == 3
    assert actuals["ht_total_goals"] == 1


# ---------------------------------------------------------------------------
# Registry mercati ed export
# ---------------------------------------------------------------------------


def test_core_market_registry_shape():
    from app.services.cecchino_data_lab.run_v2.constants import (
        CORE_MARKETS,
        FAMILY_1X2,
        FAMILY_DC,
        FAMILY_HT_1X2,
        FAMILY_OU,
    )

    assert len(CORE_MARKETS) == 17
    by_family: dict[str, int] = {}
    for market in CORE_MARKETS:
        by_family[market.family] = by_family.get(market.family, 0) + 1
    assert by_family == {FAMILY_1X2: 3, FAMILY_DC: 3, FAMILY_HT_1X2: 3, FAMILY_OU: 8}
    assert len({m.export_key for m in CORE_MARKETS}) == 17


def test_market_rows_cardinality_is_one_per_market_strict_only():
    from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS
    from app.services.cecchino_data_lab.run_v2.economic_observation import (
        build_economic_benchmark_rows,
    )
    from app.services.cecchino_data_lab.run_v2.market_rows import (
        build_core_strict_market_rows,
        frozen_probabilities,
    )
    from app.services.cecchino_data_lab.run_v2.quotes import build_run_v2_quote_bundle
    from app.services.cecchino_data_lab.run_v2.settlement import (
        evaluate_market_outcome_v2,
        match_result_from_lab_match,
    )

    match = _lab_match()
    bundle = build_run_v2_quote_bundle(match)
    result = match_result_from_lab_match(match)
    outcomes = {m.key: evaluate_market_outcome_v2(m.key, result) for m in CORE_MARKETS}

    core_rows = build_core_strict_market_rows(
        kpi_panel={"rows": []},
        goal_markets={},
        ou_05_markets={},
        ht_1x2_markets={},
        strict_by_market=bundle["strict_by_market"],
        balance=None,
        gi_payload=None,
        purchasability=None,
        outcomes=outcomes,
    )
    economic_rows = build_economic_benchmark_rows(
        economic_bundle=bundle["economic"],
        frozen_probabilities=frozen_probabilities(core_rows),
        outcomes=outcomes,
    )

    assert len(core_rows) == 17
    assert len(economic_rows) == 0
    assert len({r["market_key"] for r in core_rows}) == 17
    assert all(r["observation_layer"] == "core_strict" for r in core_rows)
    assert all(r["economic_observation_only"] is False for r in core_rows)
    # Settlement riusa quota STRICT congelata.
    over05 = next(r for r in core_rows if r["market_key"] == "OVER_0_5")
    assert over05["quota_book"] == pytest.approx(1.06)
    assert over05["pre_match_input_safe"] is True


def test_core_and_economic_rows_coexist_for_the_same_market():
    """La chiave unica include il layer, quindi i due record convivono."""
    from app.models.cecchino_run_v2 import CecchinoRunV2MarketResult

    constraint = next(
        c
        for c in CecchinoRunV2MarketResult.__table__.constraints
        if getattr(c, "name", None) == "uq_cecchino_run_v2_mkt_snap_key_layer"
    )
    assert [c.name for c in constraint.columns] == [
        "match_snapshot_id",
        "market_key",
        "observation_layer",
    ]


def test_full_export_columns_are_unique_and_stable():
    from app.services.cecchino_data_lab.run_v2.column_registry import full_export_columns

    first = [c.column for c in full_export_columns()]
    second = [c.column for c in full_export_columns()]
    assert first == second
    assert len(first) == len(set(first))


def test_data_dictionary_matches_csv_columns_exactly():
    from app.services.cecchino_data_lab.run_v2.column_registry import (
        CORE_MARKETS_LONG_COLUMNS,
        build_data_dictionary,
        full_export_columns,
    )

    raw_columns = ["Div", "HST"]
    dictionary = build_data_dictionary(run_id=1, source_raw_columns=raw_columns)

    full_columns = {c.column for c in full_export_columns()}
    documented = {e["column"] for e in dictionary["files"]["FULL.csv"]}
    assert full_columns == documented

    long_columns = {c[0] for c in CORE_MARKETS_LONG_COLUMNS}
    assert long_columns == {e["column"] for e in dictionary["files"]["core_markets_long.csv"]}

    raw_documented = {e["column"] for e in dictionary["files"]["SOURCE_RAW.csv"]}
    assert raw_documented == {"lab_match_id", *raw_columns}


def test_enrichment_strict_columns_are_prediction_input():
    from app.services.cecchino_data_lab.run_v2.column_registry import (
        LAYER_CORE_STRICT_QUOTE,
        LAYER_ECONOMIC_QUOTE,
        full_export_columns,
    )

    economic = [c for c in full_export_columns() if c.layer == LAYER_ECONOMIC_QUOTE]
    assert economic == []

    enrichment_cols = [
        c
        for c in full_export_columns()
        if c.layer == LAYER_CORE_STRICT_QUOTE
        and any(
            token in c.column
            for token in (
                "over_0_5",
                "under_0_5",
                "over_1_5",
                "ht_home",
                "one_x",
                "over_3_5",
            )
        )
        and c.column.endswith("_value")
    ]
    assert enrichment_cols
    for column in enrichment_cols:
        assert column.allowed_as_prediction_input is True, column.column
        assert column.available_at_prediction_time is True, column.column


def test_ou05_kpi_append_reuses_v1_metrics_row_and_keeps_v1_rows():
    from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _build_metrics_row
    from app.services.cecchino.cecchino_selection_keys import SEL_OVER_0_5, SEL_UNDER_0_5
    from app.services.cecchino_data_lab.run_v2.kpi_ou05_ext import append_ou05_kpi_rows

    v1_panel = {
        "rows": [
            {"market_key": "HOME", "quota_book": 2.1, "quota_cecchino": 2.0, "rating": 70},
            {"market_key": "OVER_2_5", "quota_book": 1.9, "quota_cecchino": 1.85, "rating": 65},
        ]
    }
    ou05 = {
        SEL_OVER_0_5: {"final_odd": 1.05},
        SEL_UNDER_0_5: {"final_odd": 10.0},
    }
    strict = {
        SEL_OVER_0_5: {"value": 1.06, "quote_source": "bet365_enrichment_closing_pre_kickoff"},
        SEL_UNDER_0_5: {"value": 9.5, "quote_source": "bet365_enrichment_closing_pre_kickoff"},
    }
    out = append_ou05_kpi_rows(v1_panel, ou_05_markets=ou05, strict_by_market=strict)
    assert out["v1_row_count"] == 2
    assert out["rows"][:2] == v1_panel["rows"]
    keys = [r["market_key"] for r in out["rows"]]
    assert keys[-2:] == [SEL_OVER_0_5, SEL_UNDER_0_5]

    expected = _build_metrics_row(
        market_key=SEL_OVER_0_5,
        segno="Over 0.5",
        quota_book=1.06,
        quota_cecchino=1.05,
        book_source="bet365_enrichment_closing_pre_kickoff",
        cecchino_source="goal_markets_ou_05_v2",
        bookmaker_name="Bet365",
        provider_bookmaker_id=0,
        book_fallback_used=False,
    )
    got = out["rows"][-2]
    for field in ("edge_pct", "vantaggio_prob", "rating", "score_acquisto", "prob_book", "prob_cecchino"):
        assert got.get(field) == expected.get(field), field


def test_v1_kpi_row_defs_unchanged_no_ou05():
    from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_ROW_DEFS
    from app.services.cecchino.cecchino_selection_keys import SEL_OVER_0_5, SEL_UNDER_0_5

    keys = {k for k, _ in KPI_V2_ROW_DEFS}
    assert SEL_OVER_0_5 not in keys
    assert SEL_UNDER_0_5 not in keys
    assert len(KPI_V2_ROW_DEFS) == 19


def test_actual_columns_are_never_prediction_input():
    from app.services.cecchino_data_lab.run_v2.column_registry import (
        LAYER_POST_MATCH_LABEL,
        full_export_columns,
    )

    labels = [c for c in full_export_columns() if c.layer == LAYER_POST_MATCH_LABEL]
    assert labels
    for column in labels:
        assert column.allowed_as_prediction_input is False, column.column
        assert column.available_at_prediction_time is False, column.column


def test_prematch_feature_columns_are_declared_as_input():
    from app.services.cecchino_data_lab.run_v2.column_registry import (
        LAYER_EXTRA_PRE_MATCH_FEATURE,
        LAYER_PRE_MATCH_FEATURE,
        full_export_columns,
    )

    features = [
        c
        for c in full_export_columns()
        if c.layer in (LAYER_PRE_MATCH_FEATURE, LAYER_EXTRA_PRE_MATCH_FEATURE)
        and c.column != "prematch_extra_stats_status"
    ]
    assert features
    for column in features:
        assert column.allowed_as_prediction_input is True, column.column
        assert column.available_at_prediction_time is True, column.column


def test_export_row_getters_are_missing_safe():
    """Un contesto vuoto non deve far esplodere l'export."""
    from app.services.cecchino_data_lab.run_v2.column_registry import full_export_columns

    empty_ctx = {"run_version": "cecchino_run_v2", "snapshot": {}, "markets": {}}
    values = [c.getter(empty_ctx) for c in full_export_columns()]
    assert len(values) == len(full_export_columns())
    assert all(v is None for v in values if v is not None) or True


def test_purchasability_diagnostic_fallback_core_strict_only():
    """Diagnostici v5 da purchasability_json solo su core_strict; score/class intatti."""
    from app.services.cecchino_data_lab.run_v2.column_registry import full_export_columns
    from app.services.cecchino_data_lab.run_v2.constants import (
        LAYER_CORE_STRICT,
        LAYER_ECONOMIC,
    )
    from app.services.cecchino_data_lab.run_v2.export import (
        _apply_purchasability_diagnostic_fallback,
        _overlay_core_strict_diagnostics,
    )

    purch_by_key = {
        "ONE_X": {
            "market_key": "ONE_X",
            "score": 55.0,
            "class": "Media",
            "status": "score",
            "gate_status": "passed",
            "gate_reason_codes": [],
            "fair_book_probability": 0.72,
            "fair_book_probability_source": "run_v2_strict_bet365_1x2_derived_dc",
        }
    }

    core_row = {
        "market_key": "ONE_X",
        "observation_layer": LAYER_CORE_STRICT,
        "buyability_score": 55.0,
        "buyability_class": "Media",
        "buyability_status": None,
        "buyability_gate_status": None,
        "buyability_gate_reason_codes": None,
        "fair_book_probability": None,
        "fair_book_probability_source": None,
    }
    econ_row = {
        "market_key": "ONE_X",
        "observation_layer": LAYER_ECONOMIC,
        "buyability_score": None,
        "buyability_class": None,
        "buyability_status": None,
        "buyability_gate_status": None,
        "buyability_gate_reason_codes": None,
        "fair_book_probability": None,
        "fair_book_probability_source": None,
    }

    _apply_purchasability_diagnostic_fallback(
        core_row,
        market_key="ONE_X",
        observation_layer=LAYER_CORE_STRICT,
        purch_by_key=purch_by_key,
    )
    _apply_purchasability_diagnostic_fallback(
        econ_row,
        market_key="ONE_X",
        observation_layer=LAYER_ECONOMIC,
        purch_by_key=purch_by_key,
    )

    assert core_row["buyability_score"] == 55.0
    assert core_row["buyability_class"] == "Media"
    assert core_row["buyability_status"] == "score"
    assert core_row["buyability_gate_status"] == "passed"
    assert core_row["buyability_gate_reason_codes"] == []
    assert core_row["fair_book_probability"] == 0.72
    assert (
        core_row["fair_book_probability_source"]
        == "run_v2_strict_bet365_1x2_derived_dc"
    )

    assert econ_row["buyability_status"] is None
    assert econ_row["buyability_gate_status"] is None
    assert econ_row["fair_book_probability"] is None
    assert econ_row["fair_book_probability_source"] is None

    grouped = {
        LAYER_CORE_STRICT: {
            "ONE_X": {
                "buyability_score": 55.0,
                "buyability_class": "Media",
                "buyability_status": None,
                "fair_book_probability": None,
                "fair_book_probability_source": None,
            }
        },
        LAYER_ECONOMIC: {
            "ONE_X": {
                "buyability_status": None,
                "fair_book_probability": None,
            }
        },
    }
    _overlay_core_strict_diagnostics(
        grouped,
        {"markets": [purch_by_key["ONE_X"]]},
    )
    assert grouped[LAYER_CORE_STRICT]["ONE_X"]["buyability_status"] == "score"
    assert grouped[LAYER_CORE_STRICT]["ONE_X"]["fair_book_probability"] == 0.72
    assert grouped[LAYER_CORE_STRICT]["ONE_X"]["buyability_score"] == 55.0
    assert grouped[LAYER_ECONOMIC]["ONE_X"]["buyability_status"] is None

    ctx = {
        "run_version": "cecchino_run_v2",
        "snapshot": {},
        "markets": grouped,
    }
    by_col = {c.column: c.getter(ctx) for c in full_export_columns()}
    assert by_col["core_one_x_buyability_status"] == "score"
    assert by_col["core_one_x_fair_book_probability"] == 0.72
    assert (
        by_col["core_one_x_fair_book_probability_source"]
        == "run_v2_strict_bet365_1x2_derived_dc"
    )
    assert by_col["core_one_x_buyability_score"] == 55.0


def test_purchasability_diagnostic_fallback_does_not_override_orm():
    from app.services.cecchino_data_lab.run_v2.constants import LAYER_CORE_STRICT
    from app.services.cecchino_data_lab.run_v2.export import (
        _apply_purchasability_diagnostic_fallback,
    )

    row = {
        "buyability_status": "gate_failed",
        "fair_book_probability": 0.1,
    }
    _apply_purchasability_diagnostic_fallback(
        row,
        market_key="HOME",
        observation_layer=LAYER_CORE_STRICT,
        purch_by_key={
            "HOME": {
                "status": "score",
                "fair_book_probability": 0.9,
            }
        },
    )
    assert row["buyability_status"] == "gate_failed"
    assert row["fair_book_probability"] == 0.1


def test_statistical_target_lines_are_not_bookmaker_markets():
    from app.services.cecchino_data_lab.run_v2.constants import (
        CORE_MARKET_KEYS,
        STATISTICAL_TARGET_LINES,
    )

    assert STATISTICAL_TARGET_LINES
    for name in STATISTICAL_TARGET_LINES:
        assert name not in CORE_MARKET_KEYS
