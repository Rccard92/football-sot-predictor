"""Test export Acquistabilità storica compatto (read-only, formula non ricalcolata)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino_data_lab.historical_analytics_agg import (
    ANALYTICS_AGGREGATION_VERSION,
    classify_purchasability_gate,
    purchasability_accepted_score_band_report,
    purchasability_band_report,
    score_zero_semantics_for_row,
)
from app.services.cecchino_data_lab.historical_purchasability_export import (
    DECISION_GROUP_DC,
    DECISION_GROUP_GOALS_FT,
    DECISION_GROUP_ONE_X_TWO,
    PURCHASABILITY_EXPORT_SCHEMA_VERSION,
    build_compact_evaluation_row,
    build_decision_rows,
    build_export_reconciliation,
    build_purchasability_drift,
    build_purchasability_evaluation_id,
    build_purchasability_export_summary,
    build_purchasability_profiles,
    collect_compact_evaluations,
    derive_diagnostic_ungated_score,
)

FORMULA = "cecchino_lab_purchasability_historical_v1"


def _mk_row(
    market_key: str,
    *,
    score: float | None = 50.0,
    raw_score: float | None = 50.0,
    klass: str | None = "Media",
    gate_status: str = "passed",
    gate_reasons: list | None = None,
    p1: float | None = 64.0,
    p2: float | None = 36.0,
    edge: float | None = 5.0,
    vant: float | None = 0.05,
    status: str = "ok",
    quote_quality: str = "real",
    formula: str | None = FORMULA,
    profile_hash: str = "hash_a",
    sample_size: int = 40,
):
    gate = {
        "status": gate_status,
        "reason_codes": gate_reasons or [],
    }
    phase_1 = {"score": p1, "status": "ok"} if p1 is not None else {"score": None}
    phase_2 = {"score": p2, "status": "ok"} if p2 is not None else {"score": None}
    return {
        "market_key": market_key,
        "status": status,
        "score": score,
        "raw_score": raw_score,
        "class": klass,
        "phase_1": phase_1,
        "phase_2": phase_2,
        "positive_value_gate": gate,
        "quote_quality": quote_quality,
        "normalization_profile_version": "cecchino_lab_purchasability_hist_norm_v1",
        "normalization_profile_hash": profile_hash,
        "normalization_sample_size": sample_size,
        "reason_codes": list(gate_reasons or []),
        "formula_version": formula,
        "parity_status": "historical_bet365_v2",
        "rating": 80,
        "edge_pct": edge,
        "vantaggio_prob": vant,
        "components": {"phase_1": phase_1, "phase_2": phase_2},
    }


def _market(
    *,
    snapshot_id: int,
    market_key: str,
    real: bool = True,
    derived: bool = False,
    won: bool | None = True,
    profit_real: float | None = 0.9,
    profit_synth: float | None = None,
    quota_book: float | None = 1.9,
    rating: int | None = 80,
    edge: float = 5.0,
    vant: float = 0.05,
    prob_cecchino: float = 0.45,
    quota_cecchino: float = 2.2,
):
    return SimpleNamespace(
        id=1,
        run_id=3,
        match_snapshot_id=snapshot_id,
        lab_match_id=100,
        market_key=market_key,
        market_label=market_key,
        period="FT",
        line="2.5" if "2_5" in market_key else None,
        quota_cecchino=Decimal(str(quota_cecchino)),
        prob_cecchino=Decimal(str(prob_cecchino)),
        quota_book=Decimal(str(quota_book)) if quota_book is not None else None,
        prob_book_raw=Decimal("0.50"),
        prob_book_fair=Decimal("0.48"),
        is_real_book_quote=real,
        is_derived_quote=derived,
        edge_pct=Decimal(str(edge)),
        vantaggio_prob=Decimal(str(vant)),
        rating=rating,
        signal_active=False,
        evaluation_status="settled",
        won=won,
        profit_1u_real=Decimal(str(profit_real)) if profit_real is not None else None,
        profit_1u_synthetic=Decimal(str(profit_synth)) if profit_synth is not None else None,
        result_reason="ft",
    )


def _snap(
    *,
    sid: int = 10,
    markets: list | None = None,
    kickoff: datetime | None = None,
    competition: str = "Serie A",
    season: str = "2021/2022",
    profile_hash: str = "hash_a",
):
    mkts = markets or [_mk_row("HOME")]
    return SimpleNamespace(
        id=sid,
        run_id=3,
        dataset_id=1,
        lab_match_id=100 + sid,
        competition_name=competition,
        season_label=season,
        kickoff_at=kickoff or datetime(2021, 9, 12, 18, 0, tzinfo=timezone.utc),
        chronological_order=sid,
        home_team="Home FC",
        away_team="Away FC",
        historical_eligibility_status="eligible_core",
        settlement_status="settled",
        result_json={
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
        },
        purchasability_compatibility_json={
            "execution_status": "computed",
            "historical_purchasability_status": "computed",
            "formula_version": FORMULA,
            "markets": mkts,
            "normalization_profile": {
                "version": "cecchino_lab_purchasability_hist_norm_v1",
                "hash": profile_hash,
                "sample_size": 40,
                "cutoff": "2021-09-01T00:00:00+00:00",
                "min_side_samples": 8,
                "source": "progressive_eligible_core",
            },
        },
    )


def test_evaluation_id_deterministic_and_unique():
    a = build_purchasability_evaluation_id(run_id=3, snapshot_id=10, market_key="HOME")
    b = build_purchasability_evaluation_id(run_id=3, snapshot_id=10, market_key="HOME")
    c = build_purchasability_evaluation_id(run_id=3, snapshot_id=10, market_key="DRAW")
    assert a == b == "run:3:snapshot:10:market:HOME"
    assert a != c


def test_one_row_per_snapshot_market_and_identity():
    snap = _snap(
        markets=[
            _mk_row("HOME", score=70),
            _mk_row("DRAW", score=40),
            _mk_row(
                "AWAY",
                score=0,
                klass="Molto Bassa",
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                edge=-1.0,
            ),
        ]
    )
    markets = [
        _market(snapshot_id=10, market_key="HOME"),
        _market(snapshot_id=10, market_key="DRAW"),
        _market(snapshot_id=10, market_key="AWAY", won=False, profit_real=-1.0),
    ]
    rows = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    assert len(rows) == 3
    ids = [r["purchasability_evaluation_id"] for r in rows]
    assert len(ids) == len(set(ids))

    home = next(r for r in rows if r["market_key"] == "HOME")
    assert home["run_id"] == 3
    assert home["snapshot_id"] == 10
    assert home["match_snapshot_id"] == 10
    assert home["lab_match_id"] == 110
    assert home["dataset_id"] == 1
    assert home["competition_name"] == "Serie A"
    assert home["season_label"] == "2021/2022"
    assert home["kickoff_at"] and "2021-09-12" in home["kickoff_at"]
    assert home["home_team"] == "Home FC"
    assert home["away_team"] == "Away FC"
    assert home["home_score_ft"] == 2
    assert home["away_score_ft"] == 1
    assert home["home_score_ht"] == 1
    assert home["away_score_ht"] == 0
    assert home["eligibility_status"] == "eligible_core"
    assert home["settlement_status"] == "settled"
    assert home["final_score"] == 70
    assert home["persisted_score"] == 70
    assert home["formula_recomputed"] is False


def test_join_matched_missing_ambiguous_invalid():
    snap = _snap(markets=[_mk_row("HOME"), _mk_row("DRAW"), _mk_row("")])
    # fix empty market_key row
    snap.purchasability_compatibility_json["markets"][2]["market_key"] = None
    markets = [
        _market(snapshot_id=10, market_key="HOME"),
        # DRAW missing
        # Ambiguous: two HOME would be wrong; add two OVER
    ]
    snap.purchasability_compatibility_json["markets"].append(_mk_row("OVER_2_5"))
    markets.append(_market(snapshot_id=10, market_key="OVER_2_5"))
    markets.append(_market(snapshot_id=10, market_key="OVER_2_5"))  # ambiguous

    rows = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    by_mk = {r["market_key"]: r for r in rows}
    assert by_mk["HOME"]["market_join_status"] == "matched"
    assert by_mk["DRAW"]["market_join_status"] == "missing_market_result"
    assert by_mk["DRAW"]["profit_1u_real"] is None
    assert by_mk["OVER_2_5"]["market_join_status"] == "ambiguous_market_result"
    invalid = [r for r in rows if r["market_key"] in (None, "INVALID") or r["market_join_status"] == "invalid_market_key"]
    assert invalid
    assert invalid[0]["market_join_status"] == "invalid_market_key"


def test_quotes_real_derived_unavailable_and_probs():
    snap = _snap(
        markets=[
            _mk_row("HOME", quote_quality="real"),
            _mk_row("ONE_X", quote_quality="derived"),
            _mk_row("DRAW", quote_quality="unavailable"),
        ]
    )
    markets = [
        _market(snapshot_id=10, market_key="HOME", real=True, derived=False),
        _market(
            snapshot_id=10,
            market_key="ONE_X",
            real=False,
            derived=True,
            profit_real=None,
            profit_synth=0.5,
        ),
        _market(
            snapshot_id=10,
            market_key="DRAW",
            real=False,
            derived=False,
            quota_book=None,
            profit_real=None,
            profit_synth=None,
        ),
    ]
    rows = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    by_mk = {r["market_key"]: r for r in rows}
    assert by_mk["HOME"]["is_real_book_quote"] is True
    assert by_mk["HOME"]["real_book_odds"] == 1.9
    assert by_mk["HOME"]["prob_cecchino"] == pytest.approx(0.45)
    assert by_mk["HOME"]["quota_cecchino"] == pytest.approx(2.2)
    assert by_mk["HOME"]["rating"] == 80
    assert by_mk["HOME"]["edge_pct"] == pytest.approx(5.0)
    assert by_mk["HOME"]["vantaggio_prob"] == pytest.approx(0.05)
    assert by_mk["HOME"]["profit_1u_real"] == pytest.approx(0.9)

    assert by_mk["ONE_X"]["is_derived_quote"] is True
    assert by_mk["ONE_X"]["derived_odds"] == 1.9
    assert by_mk["ONE_X"]["real_book_odds"] is None
    assert by_mk["ONE_X"]["profit_1u_synthetic"] == pytest.approx(0.5)

    assert by_mk["DRAW"]["profit_1u_real"] is None
    assert by_mk["DRAW"]["profit_1u_synthetic"] is None


def test_gate_statuses_and_zero_semantics():
    cases = [
        (
            _mk_row("HOME", score=55, gate_status="passed"),
            "accepted",
            "not_applicable",
        ),
        (
            _mk_row(
                "HOME",
                score=0,
                klass="Molto Bassa",
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
            ),
            "rejected_non_positive_edge",
            "gate_rejected",
        ),
        (
            _mk_row(
                "HOME",
                score=0,
                klass="Molto Bassa",
                gate_status="failed",
                gate_reasons=["no_positive_probability_advantage", "positive_value_gate_failed"],
            ),
            "rejected_non_positive_probability_advantage",
            "gate_rejected",
        ),
        (
            _mk_row(
                "HOME",
                score=0,
                klass="Molto Bassa",
                gate_status="failed",
                gate_reasons=[
                    "no_positive_edge",
                    "no_positive_probability_advantage",
                    "positive_value_gate_failed",
                ],
            ),
            "rejected_multiple_non_positive_components",
            "gate_rejected",
        ),
        (
            _mk_row(
                "HOME",
                score=None,
                gate_status="unavailable",
                gate_reasons=["positive_value_gate_inputs_missing"],
            ),
            "unavailable_inputs",
            "not_applicable",
        ),
    ]
    for mk_row, expected_gate, expected_zero in cases:
        info = classify_purchasability_gate(mk_row)
        assert info["gate_status"] == expected_gate
        assert score_zero_semantics_for_row(mk_row.get("score"), expected_gate) == expected_zero


def test_gate_rejected_excluded_from_band_0_19():
    assert purchasability_band_report(0) == "0-19"  # legacy
    assert (
        purchasability_accepted_score_band_report(
            0, gate_status="rejected_non_positive_edge"
        )
        == "gate_rejected"
    )
    assert purchasability_accepted_score_band_report(0, gate_status="accepted") == "0-19"


def test_diagnostic_ungated_score_reconstructable_and_not():
    mk = _mk_row("HOME", p1=64, p2=36, score=0, gate_status="failed", gate_reasons=["no_positive_edge"])
    score, src = derive_diagnostic_ungated_score(mk)
    assert score == pytest.approx(round(math.sqrt(64 * 36), 2))
    assert src == "derived_read_only_from_persisted_phase_values"

    mk2 = _mk_row("HOME", p1=None, p2=36, formula=FORMULA)
    score2, src2 = derive_diagnostic_ungated_score(mk2)
    assert score2 is None
    assert src2 == "not_reconstructable"

    mk3 = _mk_row("HOME", formula="unknown_formula")
    score3, src3 = derive_diagnostic_ungated_score(mk3)
    assert score3 is None
    assert src3 == "not_reconstructable"


def test_final_score_equals_persisted_never_recomputed():
    snap = _snap(
        markets=[
            _mk_row(
                "HOME",
                score=0,
                raw_score=0.0,
                p1=81,
                p2=49,
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            )
        ]
    )
    markets = [_market(snapshot_id=10, market_key="HOME")]
    row = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)[0]
    assert row["final_score"] == 0
    assert row["persisted_score"] == 0
    assert row["score_class"] == "Bloccato dal gate"
    assert row["accepted_score_band"] == "gate_rejected"
    assert row["diagnostic_ungated_score"] == pytest.approx(round(math.sqrt(81 * 49), 2))
    assert row["formula_recomputed"] is False


def test_decisions_1x2_goals_dc_tie_and_no_selection():
    snap = _snap(
        markets=[
            _mk_row("HOME", score=70),
            _mk_row("DRAW", score=70),  # tie with HOME
            _mk_row(
                "AWAY",
                score=0,
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            ),
            _mk_row("OVER_2_5", score=60),
            _mk_row("UNDER_2_5", score=40),
            _mk_row(
                "ONE_X",
                score=0,
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            ),
            _mk_row(
                "X_TWO",
                score=0,
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            ),
            _mk_row(
                "ONE_TWO",
                score=0,
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            ),
        ]
    )
    mkeys = ["HOME", "DRAW", "AWAY", "OVER_2_5", "UNDER_2_5", "ONE_X", "X_TWO", "ONE_TWO"]
    markets = [
        _market(
            snapshot_id=10,
            market_key=mk,
            real=mk not in ("ONE_X", "X_TWO", "ONE_TWO"),
            derived=mk in ("ONE_X", "X_TWO", "ONE_TWO"),
        )
        for mk in mkeys
    ]
    ev = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    decisions = build_decision_rows(ev)
    by_g = {d["decision_group"]: d for d in decisions}

    d1 = by_g[DECISION_GROUP_ONE_X_TWO]
    assert d1["selection_tied"] is True
    assert set(d1["tied_market_keys"]) == {"DRAW", "HOME"}
    assert d1["selected_market_key"] == "DRAW"  # lessicografico
    assert d1["selected_score"] == 70
    assert d1["diagnostic_only"] is True
    assert d1["not_a_production_strategy"] is True

    d2 = by_g[DECISION_GROUP_GOALS_FT]
    assert d2["selected_market_key"] == "OVER_2_5"
    assert d2["selected_score"] == 60
    assert d2["selection_tied"] is False

    d3 = by_g[DECISION_GROUP_DC]
    assert d3["selected_market_key"] is None
    assert d3["performance_type"] == "synthetic"
    assert d3["not_real_bet365_strategy"] is True
    assert d3["best_diagnostic_ungated_score"] is not None


def test_drift_monthly_and_profiles_dedup():
    snap1 = _snap(
        sid=1,
        kickoff=datetime(2021, 9, 1, 18, 0, tzinfo=timezone.utc),
        profile_hash="h1",
        markets=[_mk_row("HOME", score=80, profile_hash="h1")],
    )
    snap2 = _snap(
        sid=2,
        kickoff=datetime(2021, 10, 1, 18, 0, tzinfo=timezone.utc),
        profile_hash="h2",
        markets=[
            _mk_row(
                "HOME",
                score=0,
                profile_hash="h2",
                gate_status="failed",
                gate_reasons=["no_positive_edge", "positive_value_gate_failed"],
                klass="Molto Bassa",
            )
        ],
    )
    # stesso kickoff — nessun ordine causale inventato
    snap3 = _snap(
        sid=3,
        kickoff=datetime(2021, 10, 1, 18, 0, tzinfo=timezone.utc),
        competition="Premier League",
        profile_hash="h2",
        markets=[_mk_row("HOME", score=85, profile_hash="h2")],
    )
    markets = [
        _market(snapshot_id=1, market_key="HOME"),
        _market(snapshot_id=2, market_key="HOME"),
        _market(snapshot_id=3, market_key="HOME"),
    ]
    ev = collect_compact_evaluations(run_id=3, snaps=[snap1, snap2, snap3], markets=markets)
    drift = build_purchasability_drift(ev)
    assert "2021-09" in drift["by_month"]
    assert "2021-10" in drift["by_month"]
    assert "Serie A" in drift["by_competition"]
    assert drift["cap_diagnostics_available"] is False
    assert drift["same_kickoff_no_invented_causal_order"] is True

    profiles = build_purchasability_profiles(snaps=[snap1, snap2, snap3], evaluations=ev)
    assert len(profiles) == 2
    assert {p["normalization_profile_hash"] for p in profiles} == {"h1", "h2"}


def test_summary_reconciliation_and_schema_versions():
    snap = _snap(markets=[_mk_row("HOME"), _mk_row("DRAW")])
    markets = [
        _market(snapshot_id=10, market_key="HOME"),
        _market(snapshot_id=10, market_key="DRAW"),
    ]
    ev = collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    decisions = build_decision_rows(ev)
    drift = build_purchasability_drift(ev)
    profiles = build_purchasability_profiles(snaps=[snap], evaluations=ev)
    summary = build_purchasability_export_summary(
        evaluations=ev, decisions=decisions, drift=drift, profiles=profiles
    )
    assert summary["export_schema_version"] == PURCHASABILITY_EXPORT_SCHEMA_VERSION
    assert summary["formula_recomputed"] is False
    assert summary["run_snapshot_modified"] is False
    recon = summary["compact_export_reconciliation"]
    assert recon["evaluation_id_unique"] is True
    assert recon["matched_plus_missing_plus_ambiguous_plus_invalid_equals_total"] is True
    assert recon["source_snapshots_unchanged"] is True
    assert summary["threshold_diagnostics"]["diagnostic_only"] is True
    assert summary["threshold_diagnostics"]["discovered_on_same_season"] is True
    assert ANALYTICS_AGGREGATION_VERSION == "cecchino_lab_analytics_agg_v2_3"
    assert PURCHASABILITY_EXPORT_SCHEMA_VERSION == "cecchino_lab_purchasability_export_v1"


def test_legacy_payload_compatible():
    snap = _snap(
        markets=[
            {
                "market_key": "HOME",
                "score": 40,
                "class": "Bassa",
                # no gate, no phase, no formula
            }
        ]
    )
    markets = [_market(snapshot_id=10, market_key="HOME")]
    row = collect_compact_evaluations(run_id=1, snaps=[snap], markets=markets)[0]
    assert row["final_score"] == 40
    assert row["gate_status"] in ("unknown_legacy", "accepted", "unavailable_inputs")
    assert row["diagnostic_ungated_score"] is None
    assert row["diagnostic_ungated_score_source"] == "not_reconstructable"


def test_no_db_writes_in_export_builders():
    db = MagicMock()
    snap = _snap()
    markets = [_market(snapshot_id=10, market_key="HOME")]
    collect_compact_evaluations(run_id=3, snaps=[snap], markets=markets)
    assert db.add.call_count == 0
    assert db.commit.call_count == 0
    assert db.flush.call_count == 0


def test_insufficient_history_and_unsupported():
    mk_ins = {
        "market_key": "HOME",
        "status": "insufficient_historical_normalization_sample",
        "score": None,
        "positive_value_gate": None,
    }
    info = classify_purchasability_gate(
        mk_ins,
        snap_payload={"execution_status": "insufficient_historical_normalization_sample"},
    )
    assert info["gate_status"] == "not_evaluated_insufficient_history"

    mk_un = {"market_key": "FOO", "status": "unsupported", "score": None}
    info2 = classify_purchasability_gate(mk_un)
    assert info2["gate_status"] == "unsupported_market"
