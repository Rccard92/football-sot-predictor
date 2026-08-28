"""Test Historical Scan V4 — gate anti-leakage, determinismo, rolling state."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino_data_lab.constants import (
    HISTORICAL_FEATURE_CONTRACT_V4,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
    HISTORICAL_SCAN_VERSION_V4,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import (
    REFERENCE_STATUS_UNAVAILABLE,
    SOURCE_NOT_AVAILABLE,
    build_match_quote_bundle,
)
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_modules_compat import (
    build_historical_balance_v5,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    build_historical_purchasability_v36,
)
from app.services.cecchino_data_lab.historical_context_builder import (
    build_lab_prematch_contexts,
    lab_match_to_proxy,
    prior_proxies_strict,
    sha256_prematch_payload,
    sort_proxies,
)
from app.services.cecchino_data_lab.historical_quote_observations import (
    AVAILABILITY_HORIZON,
    build_quote_observations,
)
from app.services.cecchino_data_lab.historical_rolling_state import (
    CompetitionRollingState,
    GiEcdfAccumulator,
    RunPriorModuleCache,
)
from app.services.cecchino_data_lab.historical_scan_v4_executor import (
    _group_by_kickoff,
    _signals_prematch_for_hash,
)
from app.services.cecchino_data_lab.historical_signal_models import (
    attach_historical_signal_settlements,
    build_historical_signal_models,
)


def _lab_match(mid: int, home: str, away: str, ko: datetime, **kwargs):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=mid,
        home_team=home,
        away_team=away,
        kickoff_at=ko,
        match_date=ko.date(),
        match_time=ko.time(),
        source_row_number=mid,
        ft_home_goals=kwargs.get("ft_home_goals", 1),
        ft_away_goals=kwargs.get("ft_away_goals", 0),
        ht_home_goals=kwargs.get("ht_home_goals", 0),
        ht_away_goals=kwargs.get("ht_away_goals", 0),
        bet365_home=kwargs.get("bet365_home", 2.0),
        bet365_draw=kwargs.get("bet365_draw", 3.2),
        bet365_away=kwargs.get("bet365_away", 3.5),
        bet365_closing_home=kwargs.get("bet365_closing_home", 1.9),
        bet365_closing_draw=kwargs.get("bet365_closing_draw", 3.4),
        bet365_closing_away=kwargs.get("bet365_closing_away", 4.0),
        bet365_over_25=kwargs.get("bet365_over_25", 1.85),
        bet365_under_25=kwargs.get("bet365_under_25", 1.95),
        bet365_closing_over_25=kwargs.get("bet365_closing_over_25", 1.80),
        bet365_closing_under_25=kwargs.get("bet365_closing_under_25", 2.0),
        home_shots=10,
        away_shots=8,
        home_shots_on_target=4,
        away_shots_on_target=3,
        home_corners=5,
        away_corners=4,
        home_fouls=12,
        away_fouls=11,
        home_yellow_cards=2,
        away_yellow_cards=1,
        home_red_cards=0,
        away_red_cards=0,
    )


def _proxies_from_matches(matches, comp_id=1):
    return sort_proxies([lab_match_to_proxy(m, competition_id=comp_id) for m in matches])


def test_rolling_state_parity_with_build_lab_prematch_contexts():
    base = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    matches = [
        _lab_match(1, "A", "B", base.replace(day=1)),
        _lab_match(2, "C", "D", base.replace(day=8)),
        _lab_match(3, "A", "C", base.replace(day=15)),
        _lab_match(4, "B", "D", base.replace(day=22)),
    ]
    proxies = _proxies_from_matches(matches)
    state = CompetitionRollingState(competition_name="Test", all_proxies=proxies)
    for p in proxies[:-1]:
        state.commit_group([p])
    target = proxies[-1]
    ctx_state = state.contexts_for(target)
    ctx_ref = build_lab_prematch_contexts(competition_ordered=proxies, target=target)
    assert ctx_state.prior_count == ctx_ref.prior_count
    assert ctx_state.home_total.total == ctx_ref.home_total.total
    assert ctx_state.leakage_ok is True


def test_same_kickoff_not_in_rolling_committed_priors():
    ko = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    matches = [
        _lab_match(1, "A", "B", ko),
        _lab_match(2, "C", "D", ko),
        _lab_match(3, "E", "F", ko.replace(day=8)),
    ]
    proxies = _proxies_from_matches(matches)
    state = CompetitionRollingState(competition_name="Test", all_proxies=proxies)
    state.commit_group([proxies[0], proxies[1]])
    target = proxies[2]
    priors = state.priors_for(target)
    assert all(p.kickoff_at < target.kickoff_at for p in priors if p.kickoff_at and target.kickoff_at)
    priors_same = prior_proxies_strict(proxies, proxies[0])
    assert len(priors_same) == 0


def test_prior_cache_incremental_before_kickoff():
    ko1 = datetime(2021, 8, 1, tzinfo=timezone.utc)
    ko2 = datetime(2021, 9, 1, tzinfo=timezone.utc)
    cache = RunPriorModuleCache()
    cache.append_eligible(
        kickoff_at=ko1,
        lab_match_id=1,
        gi_feature_row={"features": {"home_goals_scored_avg": 1.5}},
        kpi_panel={"rows": []},
    )
    cache.append_eligible(
        kickoff_at=ko2,
        lab_match_id=2,
        gi_feature_row={"features": {"home_goals_scored_avg": 1.8}},
        kpi_panel={"rows": []},
    )
    rows = cache.gi_rows_before(ko2)
    assert len(rows) == 1
    assert rows[0]["features"]["home_goals_scored_avg"] == 1.5


def test_quote_observations_excluded_from_prematch_hash():
    m = _lab_match(1, "Home", "Away", datetime(2021, 8, 1, tzinfo=timezone.utc))
    obs = build_quote_observations(m)
    assert obs["availability_horizon"] == AVAILABILITY_HORIZON
    assert obs["anti_leakage"]["excluded_from_pre_match_hash"] is True
    payload = {
        "scan_version": HISTORICAL_SCAN_VERSION_V4,
        "feature_contract_version": HISTORICAL_FEATURE_CONTRACT_V4,
        "identity": {"lab_match_id": 1},
    }
    h_base = sha256_prematch_payload(payload)
    polluted = dict(payload)
    polluted["movement_features"] = obs.get("movement_features")
    h_polluted = sha256_prematch_payload(polluted)
    assert h_base != h_polluted
    assert "quote_observations" not in payload
    assert "movement_features" not in payload


def test_event_stats_not_in_prematch_payload_pattern():
    from app.services.cecchino_data_lab.historical_scan_v4_executor import _event_stats_from_match

    m = _lab_match(1, "H", "A", datetime(2021, 8, 1, tzinfo=timezone.utc))
    stats = _event_stats_from_match(m)
    assert stats["home_shots"] == 10
    pre = {"identity": {"lab_match_id": 1}, "scan_version": HISTORICAL_SCAN_VERSION_V4}
    assert "event_stats" not in pre
    assert "home_shots" not in pre


def test_gi_ecdf_accumulator_incremental():
    acc = GiEcdfAccumulator()
    acc.ingest_feature_row({"features": {"home_goals_scored_avg": 1.2, "away_goals_conceded_avg": 1.0,
        "home_goals_scored_rolling_5": 1.1, "home_goals_conceded_avg": 0.9, "total_goals_avg": 2.5,
        "total_goals_rolling_5": 2.4, "goals_scored_std_last_10": 0.5}})
    acc.ingest_feature_row({"features": {"home_goals_scored_avg": 1.5, "away_goals_conceded_avg": 1.1,
        "home_goals_scored_rolling_5": 1.3, "home_goals_conceded_avg": 1.0, "total_goals_avg": 2.7,
        "total_goals_rolling_5": 2.6, "goals_scored_std_last_10": 0.6}})
    assert acc.train_n() >= 2
    ecdfs = acc.ecdfs()
    assert "home_goals_scored_avg" in ecdfs


def test_group_by_kickoff():
    ko = datetime(2021, 8, 1, tzinfo=timezone.utc)
    ko2 = datetime(2021, 8, 2, tzinfo=timezone.utc)
    m1 = _lab_match(1, "A", "B", ko)
    m2 = _lab_match(2, "C", "D", ko)
    m3 = _lab_match(3, "E", "F", ko2)
    items = [(m1, "c", MagicMock(), MagicMock()), (m2, "c", MagicMock(), MagicMock()), (m3, "c", MagicMock(), MagicMock())]
    groups = _group_by_kickoff(items)
    assert len(groups) == 2
    assert len(groups[0]) == 2


def test_signals_settle_attach_without_rebuild():
    """attach_historical_signal_settlements non altera matrix pre-match."""
    cecchino = {
        "picchetti": {
            "home_away": {"home_sample_count": 5, "away_sample_count": 5},
            "totals": {},
            "last5_home_away": {},
            "last6_totals": {},
        },
        "final": {
            "status": "available",
            "quota_1": 2.0,
            "quota_x": 3.2,
            "quota_2": 3.5,
            "prob_1": 0.45,
            "prob_x": 0.28,
            "prob_2": 0.27,
        },
    }
    quote_bundle = {"quotes": {"HOME": {"value": 2.1, "is_real_book_quote": True}}}
    signals = build_historical_signal_models(
        cecchino_output=cecchino,
        quote_bundle=quote_bundle,
        under_2_5_cecchino_odd=1.9,
        contexts=None,
        match=None,
        settle=False,
    )
    matrix_before = json.dumps(
        _signals_prematch_for_hash(signals), sort_keys=True, default=str
    )
    match = SimpleNamespace(ft_home_goals=2, ft_away_goals=1, ht_home_goals=1, ht_away_goals=0)
    attach_historical_signal_settlements(signals, match=match, quote_bundle=quote_bundle)
    matrix_after = json.dumps(_signals_prematch_for_hash(signals), sort_keys=True, default=str)
    assert matrix_before == matrix_after


def test_scan_version_constants_v4():
    assert HISTORICAL_SCAN_VERSION_V4 == "cecchino_lab_historical_scan_v4"
    assert HISTORICAL_FEATURE_CONTRACT_V4 == "cecchino_lab_historical_feature_contract_v4"


def test_scan_run_router_version_dispatch(monkeypatch):
    os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")
    from app.services.cecchino_data_lab.constants import (
        HISTORICAL_SCAN_VERSION,
        HISTORICAL_SCAN_VERSION_V4,
    )
    from app.services.cecchino_data_lab import historical_scan_service as svc

    calls: list[str] = []
    monkeypatch.setattr(svc, "execute_historical_scan_run_v3", lambda rid: calls.append("v3"))
    monkeypatch.setattr(svc, "execute_historical_scan_run_v4", lambda rid: calls.append("v4"))

    class FakeRun:
        scan_version = HISTORICAL_SCAN_VERSION_V4

    class FakeSession:
        def get(self, model, rid):
            return FakeRun()

        def close(self):
            pass

    monkeypatch.setattr(svc, "SessionLocal", lambda: FakeSession())
    svc.execute_historical_scan_run(1)
    assert calls == ["v4"]

    calls.clear()
    FakeRun.scan_version = HISTORICAL_SCAN_VERSION
    svc.execute_historical_scan_run(2)
    assert calls == ["v3"]


def test_prior_cache_rebuild_deterministic_order():
    base = datetime(2021, 8, 1, tzinfo=timezone.utc)
    cache = RunPriorModuleCache()
    for i in [3, 1, 2]:
        cache.append_eligible(
            kickoff_at=base + timedelta(days=i),
            lab_match_id=i,
            gi_feature_row={"features": {"home_goals_scored_avg": float(i)}},
            kpi_panel={},
        )
    rows = cache.gi_rows_before(base + timedelta(days=10))
    assert len(rows) == 3
    avgs = sorted(r["features"]["home_goals_scored_avg"] for r in rows)
    assert avgs == [1.0, 2.0, 3.0]


def _cecchino_final_fixture():
    return {
        "status": "available",
        "quota_1": 2.1,
        "quota_x": 3.3,
        "quota_2": 3.5,
        "prob_1": 0.42,
        "prob_x": 0.29,
        "prob_2": 0.29,
    }


def _build_v4_quote_sensitive_payload(match):
    """Slice pre-match dipendente dalle quote reference PRE (policy V4)."""
    final = _cecchino_final_fixture()
    quote_bundle = build_match_quote_bundle(match, policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4)
    quote_observations = build_quote_observations(match)
    kpi = build_historical_kpi_panel_bet365(
        final_odds=final,
        match=match,
        goal_markets={},
        quote_bundle=quote_bundle,
    )
    balance = build_historical_balance_v5(
        cecchino_final=final,
        goal_markets={},
        kpi_panel=kpi,
        identity={
            "home_team": match.home_team,
            "away_team": match.away_team,
            "competition": "Test",
            "season_label": "2021/2022",
        },
    )
    purch = build_historical_purchasability_v36(
        kpi_panel=kpi,
        match=match,
        season_label="2021/2022",
        competition_name="Test",
    )
    cecchino_output = {
        "picchetti": {
            "home_away": {"home_sample_count": 5, "away_sample_count": 5},
            "totals": {},
            "last5_home_away": {},
            "last6_totals": {},
        },
        "final": final,
        "status": "available",
        "warnings": [],
    }
    signals = build_historical_signal_models(
        cecchino_output=cecchino_output,
        quote_bundle=quote_bundle,
        under_2_5_cecchino_odd=None,
        contexts=None,
        match=None,
        settle=False,
    )
    payload = {
        "scan_version": HISTORICAL_SCAN_VERSION_V4,
        "feature_contract_version": HISTORICAL_FEATURE_CONTRACT_V4,
        "identity": {"lab_match_id": int(match.id)},
        "historical_kpi": kpi,
        "balance_v5": balance,
        "purchasability": purch,
        "signals_matrix": _signals_prematch_for_hash(signals),
        "quote_sources": {
            "counts": quote_bundle.get("counts"),
            "family_1x2": quote_bundle.get("family_1x2"),
            "family_ou25": quote_bundle.get("family_ou25"),
            "quotes": {
                mk: {
                    "value": (qv or {}).get("value"),
                    "source_type": (qv or {}).get("source_type"),
                    "is_real_book_quote": (qv or {}).get("is_real_book_quote"),
                    "is_derived": (qv or {}).get("is_derived"),
                    "derivation_method": (qv or {}).get("derivation_method"),
                }
                for mk, qv in (quote_bundle.get("quotes") or {}).items()
            },
        },
        "module_versions": {
            "scan_version": HISTORICAL_SCAN_VERSION_V4,
            "quote_policy_version": HISTORICAL_QUOTE_POLICY_VERSION_V4,
        },
    }
    return payload, quote_observations, quote_bundle


def test_v4_closing_only_change_invariant_prematch_hash():
    ko = datetime(2021, 8, 1, tzinfo=timezone.utc)
    base_kwargs = dict(
        bet365_home=2.0,
        bet365_draw=3.2,
        bet365_away=3.5,
        bet365_over_25=1.85,
        bet365_under_25=1.95,
    )
    m1 = _lab_match(1, "Home", "Away", ko, bet365_closing_home=1.9, **base_kwargs)
    m2 = _lab_match(
        1,
        "Home",
        "Away",
        ko,
        bet365_closing_home=9.9,
        bet365_closing_draw=9.9,
        bet365_closing_away=9.9,
        bet365_closing_over_25=9.9,
        bet365_closing_under_25=9.9,
        **base_kwargs,
    )

    payload1, obs1, bundle1 = _build_v4_quote_sensitive_payload(m1)
    payload2, obs2, bundle2 = _build_v4_quote_sensitive_payload(m2)

    h1 = sha256_prematch_payload(payload1)
    h2 = sha256_prematch_payload(payload2)
    assert h1 == h2

    home1 = next(r for r in payload1["historical_kpi"]["rows"] if r["market_key"] == "HOME")
    home2 = next(r for r in payload2["historical_kpi"]["rows"] if r["market_key"] == "HOME")
    assert home1.get("edge_pct") == home2.get("edge_pct")
    assert home1.get("quota_book") == home2.get("quota_book") == 2.0

    assert obs1["movement_features"]["HOME"]["quota_closing"] == 1.9
    assert obs2["movement_features"]["HOME"]["quota_closing"] == 9.9
    assert obs1["movement_features"]["HOME"]["delta_abs"] != obs2["movement_features"]["HOME"]["delta_abs"]
    assert all(
        qv.get("source_type") not in ("bet365_closing", "derived_from_bet365_1x2_closing")
        for qv in bundle1["quotes"].values()
    )
    assert "movement_features" not in payload1


def test_v4_pre_change_affects_kpi_edge_and_hash():
    ko = datetime(2021, 8, 1, tzinfo=timezone.utc)
    closing = dict(
        bet365_closing_home=1.9,
        bet365_closing_draw=3.4,
        bet365_closing_away=4.0,
        bet365_closing_over_25=1.8,
        bet365_closing_under_25=2.0,
    )
    m1 = _lab_match(
        1,
        "Home",
        "Away",
        ko,
        bet365_home=2.0,
        bet365_draw=3.2,
        bet365_away=3.5,
        **closing,
    )
    m2 = _lab_match(
        1,
        "Home",
        "Away",
        ko,
        bet365_home=2.5,
        bet365_draw=3.2,
        bet365_away=3.5,
        **closing,
    )

    payload1, _, _ = _build_v4_quote_sensitive_payload(m1)
    payload2, _, _ = _build_v4_quote_sensitive_payload(m2)

    assert sha256_prematch_payload(payload1) != sha256_prematch_payload(payload2)

    home1 = next(r for r in payload1["historical_kpi"]["rows"] if r["market_key"] == "HOME")
    home2 = next(r for r in payload2["historical_kpi"]["rows"] if r["market_key"] == "HOME")
    assert home1.get("quota_book") == 2.0
    assert home2.get("quota_book") == 2.5
    assert home1.get("edge_pct") != home2.get("edge_pct")


def test_v4_no_pre_with_closing_no_fallback():
    ko = datetime(2021, 8, 1, tzinfo=timezone.utc)
    m = _lab_match(
        1,
        "Home",
        "Away",
        ko,
        bet365_home=None,
        bet365_draw=None,
        bet365_away=None,
        bet365_over_25=None,
        bet365_under_25=None,
        bet365_closing_home=1.9,
        bet365_closing_draw=3.4,
        bet365_closing_away=4.0,
        bet365_closing_over_25=1.8,
        bet365_closing_under_25=2.0,
    )

    payload, obs, bundle = _build_v4_quote_sensitive_payload(m)

    assert bundle["family_1x2"]["reference_quote_status"] == REFERENCE_STATUS_UNAVAILABLE
    assert bundle["family_ou25"]["reference_quote_status"] == REFERENCE_STATUS_UNAVAILABLE
    assert bundle["quotes"]["HOME"]["source_type"] == SOURCE_NOT_AVAILABLE
    assert bundle["quotes"]["HOME"]["value"] is None

    assert all(
        qv.get("source_type") not in ("bet365_closing", "derived_from_bet365_1x2_closing")
        for qv in bundle["quotes"].values()
    )

    home = next(r for r in payload["historical_kpi"]["rows"] if r["market_key"] == "HOME")
    assert home.get("quota_book") is None
    assert home.get("book_quote_class") == "unavailable"

    assert obs["quote_families_raw"]["closing"]["1x2"]["HOME"] == 1.9
    assert obs["quote_families_raw"]["pre_closing"]["1x2"]["HOME"] is None
    assert "HOME" not in obs["movement_features"]
    assert "movement_features" not in payload
    assert "quote_observations" not in payload


def test_v4_closing_only_in_observations_not_reference_bundle():
    ko = datetime(2021, 8, 1, tzinfo=timezone.utc)
    m = _lab_match(1, "Home", "Away", ko)
    _, obs, bundle = _build_v4_quote_sensitive_payload(m)

    assert bundle["quotes"]["HOME"]["value"] == 2.0
    assert all(
        v.get("source_type") not in ("bet365_closing", "derived_from_bet365_1x2_closing")
        for v in bundle["quotes"].values()
    )
    assert obs["quote_families_raw"]["closing"]["1x2"]["HOME"] == 1.9
    assert obs["quote_families_raw"]["pre_closing"]["1x2"]["HOME"] == 2.0
    assert "HOME" in obs["movement_features"]


def test_quote_observations_dual_families():
    m = _lab_match(1, "H", "A", datetime(2021, 8, 1, tzinfo=timezone.utc))
    obs = build_quote_observations(m)
    raw = obs["quote_families_raw"]
    assert raw["pre_closing"]["1x2"]["HOME"] == 2.0
    assert raw["closing"]["1x2"]["HOME"] == 1.9
    assert "HOME" in obs["movement_features"]


def test_stable_competition_id_v4_process_invariant():
    from app.services.cecchino_data_lab.historical_scan_v4_ordering import stable_competition_id_v4

    assert stable_competition_id_v4("Premier League") == stable_competition_id_v4("Premier League")
    assert stable_competition_id_v4("Premier League") != stable_competition_id_v4("Serie A")
    # Non dipende da PYTHONHASHSEED
    a = stable_competition_id_v4("La Liga")
    b = stable_competition_id_v4("La Liga")
    assert a == b
    assert 1 <= a < 10**9 + 1


def test_match_sort_key_v4_cross_competition_same_kickoff():
    from app.services.cecchino_data_lab.historical_scan_v4_ordering import match_sort_key_v4

    ko = datetime(2021, 8, 15, 15, 0, tzinfo=timezone.utc)
    m_a = _lab_match(10, "A", "B", ko, source_row_number=5)
    m_b = _lab_match(11, "C", "D", ko, source_row_number=5)
    key_a = match_sort_key_v4(m_a, competition_name="Bundesliga", dataset_id=2)
    key_b = match_sort_key_v4(m_b, competition_name="Premier League", dataset_id=1)
    assert key_a != key_b
    assert key_a < key_b or key_b < key_a


def test_classify_kickoff_groups_partial_vs_complete():
    from app.services.cecchino_data_lab.historical_kickoff_group import (
        classify_kickoff_groups,
        kickoff_group_token,
    )

    ko = datetime(2021, 8, 1, 15, 0, tzinfo=timezone.utc)
    all_work = [
        (_lab_match(1, "A", "B", ko), "CompA", None, None),
        (_lab_match(2, "C", "D", ko), "CompA", None, None),
    ]
    token = kickoff_group_token(ko, 1)
    complete, partial = classify_kickoff_groups(all_work, {token: {1, 2}})
    assert complete == {1, 2}
    assert partial == set()

    complete2, partial2 = classify_kickoff_groups(all_work, {token: {1}})
    assert complete2 == set()
    assert partial2 == {1}


def test_from_resume_commits_all_same_kickoff_siblings():
    from app.services.cecchino_data_lab.historical_rolling_state import GlobalRollingStateRegistry

    ko = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    matches = [
        _lab_match(1, "A", "B", ko),
        _lab_match(2, "C", "D", ko),
        _lab_match(3, "E", "F", ko.replace(day=8)),
    ]
    proxies = _proxies_from_matches(matches)
    comp_proxies = {"Test": proxies}

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeDb:
        def execute(self, query):
            sql = str(query)
            if "historical_eligibility_status" in sql:
                return FakeResult([])
            return FakeResult(
                [
                    ("Test", 1, ko),
                    ("Test", 2, ko),
                ]
            )

    reg = GlobalRollingStateRegistry.from_resume(
        FakeDb(),
        run_id=1,
        comp_proxies=comp_proxies,
        complete_lab_match_ids={1, 2},
    )
    state = reg.get_competition("Test")
    assert state is not None
    target = proxies[2]
    priors = state.priors_for(target)
    assert len(priors) == 2


def test_deep_diff_payload_first_divergence():
    from app.services.cecchino_data_lab.historical_payload_diff import deep_diff_payload

    a = {"identity": {"chronological_order": 5, "x": 1}, "input_snapshot": {"prior_count": 3}}
    b = {"identity": {"chronological_order": 6, "x": 1}, "input_snapshot": {"prior_count": 3}}
    diff = deep_diff_payload(a, b)
    assert diff is not None
    assert diff["path"] == "identity.chronological_order"
    assert diff["run_a"] == 5
    assert diff["run_b"] == 6


def test_same_kickoff_never_in_priors():
    ko = datetime(2021, 9, 1, 15, 0, tzinfo=timezone.utc)
    ko_later = datetime(2021, 9, 8, 15, 0, tzinfo=timezone.utc)
    matches = [
        _lab_match(1, "A", "B", ko),
        _lab_match(2, "C", "D", ko),
        _lab_match(3, "E", "F", ko_later),
    ]
    proxies = _proxies_from_matches(matches)
    state = CompetitionRollingState(competition_name="Test", all_proxies=proxies)
    target_same_ko = proxies[0]
    assert state.priors_for(target_same_ko) == []
    state.commit_group([proxies[0], proxies[1]])
    assert state.priors_for(proxies[1]) == []
    priors_future = state.priors_for(proxies[2])
    assert len(priors_future) == 2
    assert all(p.kickoff_at < ko_later for p in priors_future)

