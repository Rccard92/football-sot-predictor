"""Test replay storico Cecchino Lab — isolato da Today/Betfair."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_constants import CECCHINO_BOOKMAKER
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import KPI_V2_VERSION
from app.services.cecchino_data_lab.constants import HISTORICAL_SCAN_CONFIRM_TOKEN
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    SOURCE_CLOSING,
    SOURCE_NOT_AVAILABLE,
    SOURCE_PRE_FALLBACK,
    build_match_quote_bundle,
    select_1x2_family,
    select_ou25_family,
)
from app.services.cecchino_data_lab.historical_context_builder import (
    build_input_snapshot,
    build_lab_prematch_contexts,
    compute_cecchino_from_contexts,
    lab_match_to_proxy,
    prior_proxies_strict,
    sha256_prematch_payload,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_eligibility import (
    ELIGIBLE_CORE,
    EXCLUDED_INSUFFICIENT_HISTORY,
    evaluate_historical_eligibility,
)
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_scan_preflight import (
    STATUS_BLOCKED,
    run_historical_scan_preflight,
)
from app.services.cecchino_data_lab.historical_settlement import (
    PROFIT_ACTUAL,
    PROFIT_SYNTHETIC,
    settle_historical_markets,
)


def _match(**kwargs):
    defaults = dict(
        bet365_home=None,
        bet365_draw=None,
        bet365_away=None,
        bet365_closing_home=None,
        bet365_closing_draw=None,
        bet365_closing_away=None,
        bet365_over_25=None,
        bet365_under_25=None,
        bet365_closing_over_25=None,
        bet365_closing_under_25=None,
        ft_home_goals=2,
        ft_away_goals=1,
        ht_home_goals=1,
        ht_away_goals=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_bet365_closing_priority_complete():
    m = _match(
        bet365_home=2.0,
        bet365_draw=3.2,
        bet365_away=3.5,
        bet365_closing_home=1.9,
        bet365_closing_draw=3.4,
        bet365_closing_away=4.0,
    )
    fam = select_1x2_family(m)
    assert fam["available"] is True
    assert fam["family_snapshot_type"] == "closing"
    assert fam["quotes"]["HOME"].source_type == SOURCE_CLOSING
    assert fam["quotes"]["HOME"].value == 1.9


def test_bet365_pre_fallback_complete():
    m = _match(bet365_home=2.1, bet365_draw=3.3, bet365_away=3.4)
    fam = select_1x2_family(m)
    assert fam["family_snapshot_type"] == "pre"
    assert fam["quotes"]["HOME"].source_type == SOURCE_PRE_FALLBACK


def test_bet365_no_mix_closing_pre():
    # closing incompleto → deve usare pre completo, non mix
    m = _match(
        bet365_home=2.0,
        bet365_draw=3.0,
        bet365_away=4.0,
        bet365_closing_home=1.8,
        bet365_closing_draw=None,
        bet365_closing_away=3.5,
    )
    fam = select_1x2_family(m)
    assert fam["family_snapshot_type"] == "pre"
    assert fam["quotes"]["HOME"].value == 2.0


def test_fair_normalization_and_dc_derivation():
    m = _match(
        bet365_closing_home=2.0,
        bet365_closing_draw=3.5,
        bet365_closing_away=3.5,
    )
    fam = select_1x2_family(m)
    fair = fam["fair_probs"]
    assert fair is not None
    assert abs(sum(fair.values()) - 1.0) < 1e-9
    for sk in ("ONE_X", "X_TWO", "ONE_TWO"):
        q = fam["quotes"][sk]
        assert q.is_derived is True
        assert q.is_real_book_quote is False
        assert q.derivation_method == "normalized_fair_probability_from_bet365_1x2"
        assert q.value is not None and q.value > 1


def test_no_derivation_o15_u35_ht():
    m = _match(
        bet365_closing_home=2.0,
        bet365_closing_draw=3.2,
        bet365_closing_away=3.5,
        bet365_closing_over_25=1.9,
        bet365_closing_under_25=1.9,
    )
    bundle = build_match_quote_bundle(m)
    for mk in ("OVER_1_5", "UNDER_3_5", "DRAW_PT", "OVER_PT_0_5", "OVER_PT_1_5", "UNDER_PT_1_5"):
        assert bundle["quotes"][mk]["source_type"] == SOURCE_NOT_AVAILABLE
        assert bundle["quotes"][mk]["value"] is None


def test_ou25_no_mix():
    m = _match(
        bet365_over_25=1.85,
        bet365_under_25=2.0,
        bet365_closing_over_25=1.9,
        bet365_closing_under_25=None,
    )
    fam = select_ou25_family(m)
    assert fam["family_snapshot_type"] == "pre"


def test_same_kickoff_excluded_from_history():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    proxies = sort_proxies(
        [
            SimpleNamespace(
                id=1,
                kickoff_at=ko,
                match_date=date(2021, 8, 14),
                match_time=time(15, 0),
                source_row_number=1,
                home_team_id=10,
                away_team_id=20,
                goals_home=1,
                goals_away=0,
                status="FT",
                competition_id=1,
                raw_json={"score": {"halftime": {"home": 0, "away": 0}}},
            ),
            SimpleNamespace(
                id=2,
                kickoff_at=ko,
                match_date=date(2021, 8, 14),
                match_time=time(15, 0),
                source_row_number=2,
                home_team_id=30,
                away_team_id=40,
                goals_home=0,
                goals_away=0,
                status="FT",
                competition_id=1,
                raw_json={"score": {"halftime": {"home": 0, "away": 0}}},
            ),
        ]
    )
    priors = prior_proxies_strict(proxies, proxies[0])
    assert all(int(p.id) != 2 for p in priors)
    assert all(p.kickoff_at < ko for p in priors)


def test_eight_contexts_and_insufficient_early_rounds():
    comps = []
    base = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    # few matches → insufficient history for target
    for i in range(3):
        comps.append(
            SimpleNamespace(
                id=i + 1,
                kickoff_at=base.replace(day=1 + i),
                match_date=date(2021, 8, 1 + i),
                match_time=time(15, 0),
                source_row_number=i + 1,
                home_team_id=100,
                away_team_id=200 + i,
                home_team_name="Home",
                away_team_name=f"Away{i}",
                goals_home=1,
                goals_away=0,
                status="FT",
                competition_id=7,
                raw_json={"score": {"halftime": {"home": 0, "away": 0}}},
            )
        )
    target = comps[-1]
    ctx = build_lab_prematch_contexts(competition_ordered=comps, target=target)
    snap = build_input_snapshot(ctx)
    assert "home_context" in snap and "away_recent_total_6" in snap
    out = compute_cecchino_from_contexts(ctx)
    elig = evaluate_historical_eligibility(
        home_team="Home",
        away_team="Away2",
        kickoff_at=target.kickoff_at,
        contexts=ctx,
        cecchino_output=out,
    )
    assert elig["status"] == EXCLUDED_INSUFFICIENT_HISTORY


def test_prematch_hash_invariant_to_target_result():
    base = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    proxies = []
    for i in range(20):
        proxies.append(
            SimpleNamespace(
                id=i + 1,
                kickoff_at=base.replace(day=min(1 + i, 28)),
                match_date=date(2021, 9, min(1 + i, 28)),
                match_time=time(15, 0),
                source_row_number=i + 1,
                home_team_id=100 if i % 2 == 0 else 200,
                away_team_id=200 if i % 2 == 0 else 100,
                home_team_name="A",
                away_team_name="B",
                goals_home=1,
                goals_away=0 if i % 3 else 1,
                status="FT",
                competition_id=1,
                raw_json={"score": {"halftime": {"home": 0, "away": 0}}},
            )
        )
    proxies = sort_proxies(proxies)
    target = proxies[15]
    ctx = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    payload = {"input": build_input_snapshot(ctx), "cecchino": compute_cecchino_from_contexts(ctx)}
    h1 = sha256_prematch_payload(payload)
    target.goals_home = 99
    target.goals_away = 99
    ctx2 = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    payload2 = {"input": build_input_snapshot(ctx2), "cecchino": compute_cecchino_from_contexts(ctx2)}
    h2 = sha256_prematch_payload(payload2)
    assert h1 == h2


def test_future_result_change_does_not_affect_prior_hash():
    base = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    proxies = []
    for i in range(18):
        proxies.append(
            SimpleNamespace(
                id=i + 1,
                kickoff_at=base.replace(day=min(1 + i, 28)),
                match_date=date(2021, 9, min(1 + i, 28)),
                match_time=time(15, 0),
                source_row_number=i + 1,
                home_team_id=100 if i % 2 == 0 else 200,
                away_team_id=200 if i % 2 == 0 else 100,
                home_team_name="A",
                away_team_name="B",
                goals_home=2,
                goals_away=1,
                status="FT",
                competition_id=1,
                raw_json={"score": {"halftime": {"home": 1, "away": 0}}},
            )
        )
    proxies = sort_proxies(proxies)
    earlier = proxies[10]
    ctx = build_lab_prematch_contexts(competition_ordered=proxies, target=earlier)
    h1 = sha256_prematch_payload(build_input_snapshot(ctx))
    proxies[-1].goals_home = 0
    proxies[-1].goals_away = 7
    ctx2 = build_lab_prematch_contexts(competition_ordered=proxies, target=earlier)
    h2 = sha256_prematch_payload(build_input_snapshot(ctx2))
    assert h1 == h2


def test_hash_reproducibility():
    payload = {"a": 1, "b": {"c": [1, 2, 3]}, "z": "x"}
    assert sha256_prematch_payload(payload) == sha256_prematch_payload(dict(payload))


def test_kpi_panel_no_betfair_provenance():
    m = _match(
        bet365_closing_home=2.0,
        bet365_closing_draw=3.4,
        bet365_closing_away=3.6,
        bet365_closing_over_25=1.9,
        bet365_closing_under_25=1.95,
    )
    final = {
        "status": "available",
        "quota_1": 2.1,
        "quota_x": 3.3,
        "quota_2": 3.5,
        "prob_1": 0.4,
        "prob_x": 0.3,
        "prob_2": 0.3,
    }
    panel = build_historical_kpi_panel_bet365(final_odds=final, match=m, goal_markets={})
    assert panel["bookmaker"]["name"] == "Bet365"
    assert panel["historical_only"] is True
    assert panel["source_builder_version"] == KPI_V2_VERSION
    assert "Betfair" not in str(panel["bookmaker"])
    assert CECCHINO_BOOKMAKER["name"] == "Betfair"  # operativo invariato


def test_settlement_real_vs_synthetic_profit_separated():
    m = _match(
        bet365_closing_home=2.0,
        bet365_closing_draw=3.5,
        bet365_closing_away=3.5,
        ft_home_goals=1,
        ft_away_goals=0,
        ht_home_goals=1,
        ht_away_goals=0,
    )
    bundle = build_match_quote_bundle(m)
    final = {
        "status": "available",
        "quota_1": 2.05,
        "quota_x": 3.4,
        "quota_2": 3.6,
        "prob_1": 0.42,
        "prob_x": 0.29,
        "prob_2": 0.29,
    }
    panel = build_historical_kpi_panel_bet365(final_odds=final, match=m, goal_markets={}, quote_bundle=bundle)
    rows = settle_historical_markets(match=m, kpi_panel=panel, quote_bundle=bundle)
    home = next(r for r in rows if r["market_key"] == "HOME")
    one_x = next(r for r in rows if r["market_key"] == "ONE_X")
    assert home["won"] is True
    assert home["profit_category"] == PROFIT_ACTUAL
    assert home["profit_1u_real"] == pytest.approx(1.0)
    assert home["profit_1u_synthetic"] is None
    assert one_x["is_derived_quote"] is True
    assert one_x["profit_category"] == PROFIT_SYNTHETIC
    assert one_x["profit_1u_real"] is None
    assert one_x["profit_1u_synthetic"] is not None
    o15 = next(r for r in rows if r["market_key"] == "OVER_1_5")
    assert o15["quota_book"] is None


def test_preflight_missing_season_blocked():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    result = run_historical_scan_preflight(db, season_label="2099/2100")
    assert result["status"] == STATUS_BLOCKED


def test_confirm_token_constant():
    assert HISTORICAL_SCAN_CONFIRM_TOKEN == "RUN_CECCHINO_LAB_HISTORICAL_SCAN"


def test_today_still_betfair_constant():
    assert CECCHINO_BOOKMAKER["name"] == "Betfair"


def test_bet365_adapter_not_imported_by_today_modules():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino"
    forbidden = []
    for path in root.glob("cecchino_today*.py"):
        text = path.read_text(encoding="utf-8")
        if "historical_bet365_adapter" in text:
            forbidden.append(path.name)
    auto = root.parent / ".." / "jobs"
    # also check jobs folder if present
    jobs = Path(__file__).resolve().parents[1] / "app" / "jobs"
    if jobs.exists():
        for path in jobs.glob("*cecchino*"):
            text = path.read_text(encoding="utf-8")
            if "historical_bet365_adapter" in text:
                forbidden.append(str(path))
    assert forbidden == []
