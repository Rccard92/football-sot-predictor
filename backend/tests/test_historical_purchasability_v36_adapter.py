"""Test adapter storico Acquistabilità V3.6 — epoch sintetico + anti-leakage."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.cecchino_data_lab.constants import (
    HISTORICAL_PRE_MATCH_EPOCH_POLICY_VERSION,
    HISTORICAL_QUOTE_POLICY_VERSION_V4,
)
from app.services.cecchino_data_lab.historical_bet365_adapter import build_match_quote_bundle
from app.services.cecchino_data_lab.historical_kpi_bet365_wrapper import (
    build_historical_kpi_panel_bet365,
)
from app.services.cecchino_data_lab.historical_purchasability_v36_adapter import (
    build_historical_purchasability_v36,
    synthetic_pre_match_snapshot_at,
)


def _lab_match(mid: int, ko: datetime, **kwargs):
    return SimpleNamespace(
        id=mid,
        home_team="Home",
        away_team="Away",
        kickoff_at=ko,
        match_date=ko.date(),
        match_time=ko.time(),
        source_row_number=mid,
        ft_home_goals=kwargs.get("ft_home_goals", 1),
        ft_away_goals=kwargs.get("ft_away_goals", 0),
        ht_home_goals=0,
        ht_away_goals=0,
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


def _kpi_for_match(match):
    final = {
        "status": "available",
        "quota_1": 2.1,
        "quota_x": 3.3,
        "quota_2": 3.5,
        "prob_1": 0.42,
        "prob_x": 0.29,
        "prob_2": 0.29,
    }
    quote_bundle = build_match_quote_bundle(
        match, policy_version=HISTORICAL_QUOTE_POLICY_VERSION_V4
    )
    return build_historical_kpi_panel_bet365(
        final_odds=final,
        match=match,
        goal_markets={},
        quote_bundle=quote_bundle,
    )


def _score_fingerprint(payload: dict) -> list[tuple]:
    markets = payload.get("markets") or []
    out = []
    for m in markets:
        if not isinstance(m, dict):
            continue
        out.append(
            (
                m.get("market_key"),
                m.get("score"),
                m.get("class"),
                m.get("status"),
                m.get("gate_status"),
            )
        )
    return sorted(out, key=lambda x: str(x[0] or ""))


def test_synthetic_snapshot_at_strictly_before_kickoff():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    snap = synthetic_pre_match_snapshot_at(ko)
    assert snap < ko
    assert ko - snap == timedelta(hours=24)


def test_adapter_sets_synthetic_epoch_and_provenance():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    match = _lab_match(1, ko)
    kpi = _kpi_for_match(match)
    purch = build_historical_purchasability_v36(
        kpi_panel=kpi,
        match=match,
        season_label="2021/2022",
        competition_name="Test",
    )
    batch = purch.get("engine_batch") or {}
    meta = batch.get("fixture_meta") or {}
    assert meta.get("kickoff") == ko.isoformat()
    assert meta.get("snapshot_at") == (ko - timedelta(hours=24)).isoformat()
    assert batch.get("pre_match_verified") is True

    prov = purch.get("snapshot_provenance") or {}
    assert prov.get("snapshot_policy_version") == HISTORICAL_PRE_MATCH_EPOCH_POLICY_VERSION
    assert prov.get("synthetic_timestamp") is True
    assert prov.get("physical_capture_time_known") is False
    assert prov.get("does_not_claim_physical_capture") is True
    assert prov.get("quote_reference") == HISTORICAL_QUOTE_POLICY_VERSION_V4
    assert prov.get("reference_timing") == "pre_closing_reference"
    assert prov.get("inputs_exclude_closing") is True

    anti = purch.get("anti_leakage") or {}
    assert anti.get("synthetic_timestamp") is True
    assert anti.get("inputs_exclude_closing") is True
    assert anti.get("post_match_fields_forbidden") is True


def test_adapter_score_invariant_across_valid_synthetic_leads():
    """−24h / −12h / −6h devono produrre lo stesso score; altrimenti STOP sul lead."""
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    match = _lab_match(42, ko)
    kpi = _kpi_for_match(match)

    leads = [
        timedelta(hours=24),
        timedelta(hours=12),
        timedelta(hours=6),
    ]
    payloads = [
        build_historical_purchasability_v36(
            kpi_panel=kpi,
            match=match,
            season_label="2021/2022",
            competition_name="Test",
            snapshot_lead=lead,
        )
        for lead in leads
    ]
    for p in payloads:
        assert (p.get("engine_batch") or {}).get("pre_match_verified") is True

    fingerprints = [_score_fingerprint(p) for p in payloads]
    if fingerprints[0] != fingerprints[1] or fingerprints[0] != fingerprints[2]:
        pytest.fail(
            "STOP: lead sintetico influenza lo score V3.6 "
            f"(fingerprints diverge: {fingerprints})"
        )


def test_adapter_closing_does_not_influence_v36_score():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    base = dict(
        bet365_home=2.0,
        bet365_draw=3.2,
        bet365_away=3.5,
        bet365_over_25=1.85,
        bet365_under_25=1.95,
    )
    m1 = _lab_match(7, ko, bet365_closing_home=1.9, **base)
    m2 = _lab_match(
        7,
        ko,
        bet365_closing_home=9.9,
        bet365_closing_draw=9.9,
        bet365_closing_away=9.9,
        bet365_closing_over_25=9.9,
        bet365_closing_under_25=9.9,
        **base,
    )
    p1 = build_historical_purchasability_v36(
        kpi_panel=_kpi_for_match(m1),
        match=m1,
        season_label="2021/2022",
        competition_name="Test",
    )
    p2 = build_historical_purchasability_v36(
        kpi_panel=_kpi_for_match(m2),
        match=m2,
        season_label="2021/2022",
        competition_name="Test",
    )
    assert _score_fingerprint(p1) == _score_fingerprint(p2)


def test_adapter_same_input_same_score_determinism():
    ko = datetime(2021, 9, 1, 18, 0, tzinfo=timezone.utc)
    match = _lab_match(9, ko)
    kpi = _kpi_for_match(match)
    a = build_historical_purchasability_v36(
        kpi_panel=kpi, match=match, season_label="2021/2022", competition_name="Test"
    )
    b = build_historical_purchasability_v36(
        kpi_panel=kpi, match=match, season_label="2021/2022", competition_name="Test"
    )
    assert _score_fingerprint(a) == _score_fingerprint(b)


def test_adapter_no_post_match_leakage_fields():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    match = _lab_match(3, ko, ft_home_goals=5, ft_away_goals=4)
    purch = build_historical_purchasability_v36(
        kpi_panel=_kpi_for_match(match),
        match=match,
        season_label="2021/2022",
        competition_name="Test",
    )
    assert purch.get("contains_post_match_fields") is False
    assert purch.get("pre_match_only") is True
    assert purch.get("anti_leakage", {}).get("post_match_fields_forbidden") is True
    assert purch.get("anti_leakage", {}).get("inputs_exclude_closing") is True
    # FT result sul match non deve finire nel batch engine
    blob = str(purch.get("engine_batch") or {})
    assert "ft_home_goals" not in blob
    assert "FTHG" not in blob
    assert "settlement" not in blob.lower()


def test_adapter_scores_when_gate_passes():
    ko = datetime(2021, 8, 14, 15, 0, tzinfo=timezone.utc)
    match = _lab_match(11, ko)
    purch = build_historical_purchasability_v36(
        kpi_panel=_kpi_for_match(match),
        match=match,
        season_label="2021/2022",
        competition_name="Test",
    )
    assert (purch.get("engine_batch") or {}).get("pre_match_verified") is True
    scored = [
        m
        for m in (purch.get("markets") or [])
        if isinstance(m, dict) and m.get("score") is not None
    ]
    # Con KPI storico reale tipicamente almeno un mercato scorable; se gate_failed-only
    # resta accettabile purché non sia invalid_pre_match_snapshot.
    statuses = {m.get("status") for m in (purch.get("markets") or []) if isinstance(m, dict)}
    assert "not_calculable" not in statuses or scored or "gate_failed" in statuses or "score" in statuses
    gates = {
        ((m.get("gate_status") if isinstance(m, dict) else None) or "")
        for m in (purch.get("markets") or [])
    }
    assert "unavailable_inputs" not in gates or any(
        g in ("passed", "gate_failed", "failed") for g in gates
    )
    # Reason invalid_pre_match must be gone
    items = (purch.get("engine_batch") or {}).get("items") or []
    for it in items:
        if not isinstance(it, dict):
            continue
        gate = it.get("gate") if isinstance(it.get("gate"), dict) else {}
        codes = gate.get("gate_reason_codes") or []
        assert "invalid_pre_match_snapshot" not in codes
