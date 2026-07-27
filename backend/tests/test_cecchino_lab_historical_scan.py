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


def test_signal_extraction_none_one_many_and_multi_market():
    from app.services.cecchino_data_lab.historical_signal_extraction import (
        build_market_signal_index,
        iter_active_signal_cells,
    )

    empty = {"rows": [{"key": "one", "label": "1", "signals": {"excel_d": "NO", "excel_e": "NO"}}]}
    assert iter_active_signal_cells(empty) == []
    assert build_market_signal_index(empty) == {}

    one = {
        "rows": [
            {
                "key": "one",
                "label": "1",
                "signals": {"excel_d": "SI", "excel_e": "NO", "excel_f": "NO"},
            }
        ]
    }
    cells = iter_active_signal_cells(one)
    assert len(cells) == 1
    assert cells[0]["source_column"] == "EXCEL_D"
    idx = build_market_signal_index(one)
    assert "HOME" in idx
    assert idx["HOME"]["signal_active"] is True
    assert idx["HOME"]["active_signal_count"] == 1
    assert idx["HOME"]["signal_family"] == "HOME"
    assert idx["HOME"]["signal_sources_json"]["active_signal_count"] == 1

    multi_models = {
        "rows": [
            {
                "key": "one_x",
                "label": "1X",
                "signals": {"excel_d": "SI", "excel_e": "SI", "scala_1x": "SI"},
            }
        ]
    }
    idx2 = build_market_signal_index(multi_models)
    assert idx2["ONE_X"]["active_signal_count"] == 3
    assert len(idx2["ONE_X"]["signal_sources_json"]["sources"]) == 3

    multi_markets = {
        "rows": [
            {"key": "one", "label": "1", "signals": {"excel_d": "SI"}},
            {"key": "under_under_pt", "label": "Under", "signals": {"excel_d": "SI", "excel_e": "SI"}},
            {"key": "over_over_pt", "label": "Over", "signals": {"excel_f": "SI"}},
        ]
    }
    idx3 = build_market_signal_index(multi_markets)
    assert set(idx3.keys()) >= {"HOME", "UNDER_2_5", "OVER_2_5"}
    assert idx3["UNDER_2_5"]["active_signal_count"] == 2
    assert idx3["UNDER_2_5"]["signal_family"] == "UNDER_UNDER_PT"


def test_settlement_reads_nested_signals_not_flat_columns():
    m = _match(
        bet365_closing_home=2.0,
        bet365_closing_draw=3.5,
        bet365_closing_away=3.5,
        ft_home_goals=1,
        ft_away_goals=0,
    )
    bundle = build_match_quote_bundle(m)
    panel = build_historical_kpi_panel_bet365(
        final_odds={
            "status": "available",
            "quota_1": 2.0,
            "quota_x": 3.4,
            "quota_2": 3.6,
            "prob_1": 0.42,
            "prob_x": 0.29,
            "prob_2": 0.29,
        },
        match=m,
        goal_markets={},
        quote_bundle=bundle,
    )
    signals = {
        "rows": [
            {
                "key": "one",
                "label": "1",
                "signals": {"excel_d": "SI", "excel_e": "NO"},
                # flat SI would be wrong path — must be ignored
                "excel_d": "SI",
            }
        ]
    }
    rows = settle_historical_markets(
        match=m, kpi_panel=panel, quote_bundle=bundle, signals_json=signals
    )
    home = next(r for r in rows if r["market_key"] == "HOME")
    draw = next(r for r in rows if r["market_key"] == "DRAW")
    assert home["signal_active"] is True
    assert home["signal_sources_json"]["active_signal_count"] == 1
    assert home["signal_family"] == "HOME"
    assert draw["signal_active"] is False
    assert draw["signal_sources_json"]["active_signal_count"] == 0


def test_excluded_settlement_summary_zero_markets():
    from app.services.cecchino_data_lab.historical_settlement import empty_settlement_summary

    s = empty_settlement_summary()
    assert s["markets_analyzed"] == 0
    assert s["evaluable"] == 0
    assert s["won"] == 0


def test_hash_changes_when_kpi_signals_or_balance_change():
    base = {
        "identity": {"lab_match_id": 1},
        "input_snapshot": {"prior_count": 10},
        "historical_kpi": {"rows": [{"market_key": "HOME", "rating": 55}]},
        "signals_matrix": {"rows": []},
        "balance_v5": {"structural_summary": {"class": "balance"}},
        "eligibility": {"status": "eligible_core", "core_eligible": True},
    }
    h1 = sha256_prematch_payload(base)
    changed_kpi = dict(base)
    changed_kpi["historical_kpi"] = {"rows": [{"market_key": "HOME", "rating": 80}]}
    assert sha256_prematch_payload(changed_kpi) != h1

    changed_sig = dict(base)
    changed_sig["signals_matrix"] = {
        "rows": [{"key": "one", "signals": {"excel_d": "SI"}}]
    }
    assert sha256_prematch_payload(changed_sig) != h1

    changed_bal = dict(base)
    changed_bal["balance_v5"] = {"structural_summary": {"class": "imbalance"}}
    assert sha256_prematch_payload(changed_bal) != h1


def test_hash_invariant_to_result_and_settlement_fields():
    payload = {
        "identity": {"lab_match_id": 1},
        "historical_kpi": {"x": 1},
        "signals_matrix": {},
        "balance_v5": {},
        "eligibility": {"core_eligible": True},
    }
    h1 = sha256_prematch_payload(payload)
    # risultato/settlement non devono essere nel payload — se aggiunti fuori, hash diverso;
    # qui verifichiamo che lo stesso payload pre-match resta stabile
    assert "result" not in payload
    assert sha256_prematch_payload(dict(payload)) == h1


def test_goal_intensity_and_purchasability_flags():
    from app.services.cecchino_data_lab.historical_modules_compat import (
        build_goal_intensity_compatibility,
        build_purchasability_compatibility,
    )

    snap = {
        "home_context": {"wdl": {"wins": 2, "draws": 1, "losses": 1}, "sample": 4, "min_required": 5},
        "away_context": {"wdl": {"wins": 1, "draws": 1, "losses": 2}, "sample": 4, "min_required": 5},
        "home_total": {"wdl": {"wins": 3, "draws": 2, "losses": 3}, "sample": 8, "min_required": 8},
        "away_total": {"wdl": {"wins": 2, "draws": 3, "losses": 3}, "sample": 8, "min_required": 8},
        "home_recent_context_5": {
            "wdl": {"wins": 2, "draws": 1, "losses": 2},
            "sample": 5,
            "min_required": 5,
        },
        "away_recent_context_5": {
            "wdl": {"wins": 1, "draws": 2, "losses": 2},
            "sample": 5,
            "min_required": 5,
        },
        "home_recent_total_6": {
            "wdl": {"wins": 2, "draws": 2, "losses": 2},
            "sample": 6,
            "min_required": 6,
        },
        "away_recent_total_6": {
            "wdl": {"wins": 3, "draws": 1, "losses": 2},
            "sample": 6,
            "min_required": 6,
        },
        "prior_count": 20,
        "leakage_ok": True,
    }
    gi = build_goal_intensity_compatibility(input_snapshot=snap)
    assert gi["raw_features_available"] is True
    assert gi["v5_score_not_executed"] is True
    assert gi["v5_score"] is None
    assert "wdl_contexts" in gi["raw_features"]

    purch = build_purchasability_compatibility(
        kpi_panel={
            "rows": [
                {
                    "market_key": "HOME",
                    "rating": 60,
                    "edge_pct": 4.0,
                    "vantaggio_prob": 0.05,
                    "quota_cecchino": 2.1,
                    "book_quote_class": "real_bet365",
                }
            ]
        },
        quote_bundle={
            "quotes": {
                "HOME": {
                    "value": 2.0,
                    "is_real_book_quote": True,
                    "is_derived": False,
                    "source_type": "closing",
                }
            },
            "counts": {"real": 1, "derived": 0, "not_available": 0},
        },
    )
    assert purch["inputs_available"] is True
    assert purch["final_score_not_executed"] is True
    assert purch["final_score"] is None
    assert purch["betfair_operational_profile_applied"] is False
    assert purch["market_inputs"][0]["market_key"] == "HOME"


def test_normalize_max_matches_and_invalid():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    from app.services.cecchino_data_lab.errors import CecchinoLabImportError
    from app.services.cecchino_data_lab.historical_scan_service import _normalize_max_matches

    assert _normalize_max_matches(None) is None
    assert _normalize_max_matches(200) == 200
    with pytest.raises(CecchinoLabImportError):
        _normalize_max_matches(0)
    with pytest.raises(CecchinoLabImportError):
        _normalize_max_matches("abc")


def test_bet365_adapter_not_imported_by_today_modules():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "services" / "cecchino"
    forbidden = []
    for path in root.glob("cecchino_today*.py"):
        text = path.read_text(encoding="utf-8")
        if "historical_bet365_adapter" in text:
            forbidden.append(path.name)
    jobs = Path(__file__).resolve().parents[1] / "app" / "jobs"
    if jobs.exists():
        for path in jobs.glob("*cecchino*"):
            text = path.read_text(encoding="utf-8")
            if "historical_bet365_adapter" in text:
                forbidden.append(str(path))
    assert forbidden == []
