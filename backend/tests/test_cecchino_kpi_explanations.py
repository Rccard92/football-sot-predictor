"""Test unitari servizio kpi-explanations (snapshot-only)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.cecchino.cecchino_constants import (
    FINAL_QUOTA_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
)
from app.services.cecchino.cecchino_kpi_explanations import (
    ANALYZABLE_METRICS,
    EXCLUDED_METRICS,
    build_kpi_explanations,
    get_kpi_explanations,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import (
    _compute_rating,
    _edge_pct,
    _prob_from_odd,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_2_5,
    SEL_X_TWO,
)


def _pic(odd_1: float, odd_x: float, odd_2: float) -> dict:
    return {
        "status": "available",
        "sample_home": 10,
        "sample_away": 10,
        "home_context": {"wins": 5, "draws": 3, "losses": 2},
        "away_context": {"wins": 2, "draws": 3, "losses": 5},
        "outcome_1": {"prob": 1 / odd_1, "quota": odd_1},
        "outcome_x": {"prob": 1 / odd_x, "quota": odd_x},
        "outcome_2": {"prob": 1 / odd_2, "quota": odd_2},
        "warnings": [],
    }


def _row(
    market_key: str,
    segno: str,
    *,
    qb: float | None,
    qc: float | None,
) -> dict:
    pb = _prob_from_odd(qb) if qb else None
    pc = _prob_from_odd(qc) if qc else None
    vant = round(pc - pb, 4) if pc is not None and pb is not None else None
    edge = _edge_pct(qb, qc) if qb and qc else None
    score = round(pc * edge / 100.0, 3) if pc is not None and edge is not None else None
    rating = _compute_rating(pc, vant, edge) if pc is not None and vant is not None and edge is not None else None
    from app.services.cecchino.cecchino_kpi_panel_v2_betfair import rating_label

    return {
        "market_key": market_key,
        "segno": segno,
        "label": segno,
        "quota_book": qb,
        "quota_cecchino": qc,
        "prob_book": pb,
        "prob_cecchino": pc,
        "vantaggio_prob": vant,
        "edge_pct": edge,
        "score_acquisto": score,
        "rating": rating,
        "rating_label": rating_label(rating),
        "status": "available" if qb and qc else "not_available",
        "book_source": "betfair",
        "cecchino_source": "final_odds",
    }


def _make_fixture(**overrides) -> SimpleNamespace:
    # Quote 1X2 ponderate: 1.95*0.3 + 2.10*0.3 + 2.20*0.2 + 2.00*0.2 = 2.055 → 2.06
    q1 = round(
        1.95 * FINAL_QUOTA_WEIGHTS[PICCHETTO_KEY_TOTALS]
        + 2.10 * FINAL_QUOTA_WEIGHTS[PICCHETTO_KEY_HOME_AWAY]
        + 2.20 * FINAL_QUOTA_WEIGHTS[PICCHETTO_KEY_LAST6_TOTALS]
        + 2.00 * FINAL_QUOTA_WEIGHTS[PICCHETTO_KEY_LAST5_HOME_AWAY],
        2,
    )
    qx = 3.40
    q2 = 4.50
    p1 = round(1 / q1, 4)
    px = round(1 / qx, 4)
    p2 = round(1 / q2, 4)
    dc_1x = round(1 / (p1 + px), 2)

    rows = [
        _row(SEL_HOME, "1", qb=2.40, qc=q1),
        _row(SEL_DRAW, "X", qb=3.50, qc=qx),
        _row(SEL_AWAY, "2", qb=3.10, qc=q2),
        _row(SEL_ONE_X, "1X", qb=1.50, qc=dc_1x),
        _row(SEL_X_TWO, "X2", qb=1.80, qc=round(1 / (px + p2), 2)),
        _row(SEL_ONE_TWO, "12", qb=1.40, qc=round(1 / (p1 + p2), 2)),
        _row(SEL_OVER_2_5, "O2.5", qb=2.10, qc=1.95),
        _row("MISSING_EDGE", "ME", qb=2.0, qc=None),  # diagnostica
    ]

    base = dict(
        id=42,
        local_fixture_id=10,
        provider_fixture_id=999001,
        home_team_name="Inter",
        away_team_name="Milan",
        kickoff=None,
        scan_date=date(2026, 7, 25),
        competition_id=135,
        eligibility_status="eligible",
        odds_snapshot_json={},
        stats_snapshot_json={},
        xg_profiles_json={},
        cecchino_output_json={
            "status": "available",
            "warnings": [],
            "picchetti": {
                PICCHETTO_KEY_TOTALS: _pic(1.95, 3.40, 4.50),
                PICCHETTO_KEY_HOME_AWAY: _pic(2.10, 3.40, 4.20),
                PICCHETTO_KEY_LAST6_TOTALS: _pic(2.20, 3.50, 4.00),
                PICCHETTO_KEY_LAST5_HOME_AWAY: _pic(2.00, 3.30, 4.80),
            },
            "final": {
                "status": "available",
                "quota_1": q1,
                "quota_x": qx,
                "quota_2": q2,
                "prob_1": p1,
                "prob_x": px,
                "prob_2": p2,
                "weights": dict(FINAL_QUOTA_WEIGHTS),
            },
            "goal_markets": {
                SEL_OVER_2_5: {
                    "market_key": SEL_OVER_2_5,
                    "formula_version": "goal_market_poisson_empirical_v2",
                    "final_odd": 1.95,
                    "status": "available",
                    "weights": {"totals": 0.2},
                    "summary": {
                        "lambda": 1.42,
                        "final_probability": round(1 / 1.95, 6),
                        "poisson_probability": 0.48,
                        "empirical_probability": 0.52,
                    },
                    "contexts": [],
                    "technical": {},
                    "warnings": [],
                },
            },
            "purchasability_preview": {
                "snapshot_version": "cecchino_purchasability_snapshot_v1",
                "contract_version": "cecchino_purchasability_v1_preview_contract",
                "candidate_version": "cecchino_purchasability_v1_preview_candidate_2",
                "candidate_name": "balanced_geometric_v1_1",
                "status": "available",
                "items": [
                    {
                        "market_key": SEL_HOME,
                        "selection": SEL_HOME,
                        "status": "available",
                        "calculation_quality": "full",
                        "score": 55,
                        "raw_score": 55.2,
                        "class": "Media",
                        "reading": "ok",
                        "phase_1_score": 60.0,
                        "phase_2_score": 50.7,
                        "reason_codes": [],
                    },
                ],
                "summary": {"total": 1},
                "contains_result_fields": False,
                "contains_settlement_fields": False,
                "signals_integration": False,
            },
        },
        kpi_panel_json={
            "version": "cecchino_kpi_v2_betfair",
            "rows": rows,
            "warnings": [],
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def db_mock(monkeypatch):
    db = MagicMock()
    # Affidabilità: evita query storiche reali
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_explanations._build_hr_index_for_fixture",
        lambda *_a, **_k: {
            SEL_HOME: {
                "status": "ok",
                "score": 62,
                "class": "Buona",
                "market_key": SEL_HOME,
                "version": "historical_reliability_v1.1",
                "roi": 0.04,
                "realized_margin": 0.03,
                "stability_ratio": 0.6,
                "sample_size": 80,
                "selected_sample_size": 80,
                "local_sample_size": 80,
                "global_sample_size": 200,
                "wins": 40,
                "losses": 35,
                "voids": 5,
                "win_rate": 0.5,
                "average_odds": 2.1,
                "positive_periods": 3,
                "total_periods": 5,
                "roi_component": 70.0,
                "margin_component": 65.0,
                "stability_component": 60.0,
                "raw_evidence_score": 65.0,
                "rating_band": {"min": 60, "max": 69, "label": "Buona"},
                "cohort_scope": "same_competition",
                "explanation": "Affidabilità Buona sul campione locale.",
                "reason_codes": [],
                "fallback_used": False,
                "formula_symbolic": "score = clamp(...)",
            },
        },
    )
    # Acquistabilità rebuild: evita dipendenze features
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_kpi_explanations._rebuild_purchasability_candidate",
        lambda row, kpi: (None, (row.cecchino_output_json or {}).get("purchasability_preview") or {}),
    )
    return db


def test_get_not_found():
    db = MagicMock()
    db.get.return_value = None
    assert get_kpi_explanations(db, 1) is None


def test_not_eligible():
    db = MagicMock()
    db.get.return_value = _make_fixture(eligibility_status="excluded_cup")
    out = get_kpi_explanations(db, 42)
    assert out["status"] == "error"
    assert out["code"] == "not_eligible"


def test_kpi_not_available():
    db = MagicMock()
    db.get.return_value = _make_fixture(kpi_panel_json=None)
    out = get_kpi_explanations(db, 42)
    assert out["status"] == "error"
    assert out["code"] == "kpi_not_available"


def test_eligible_payload_structure(db_mock):
    row = _make_fixture()
    db_mock.get.return_value = row
    out = get_kpi_explanations(db_mock, 42)
    assert out["status"] in ("ok", "partial")
    assert out["audit_version"] == "cecchino_kpi_explanations_v1"
    assert out["no_model_recalculation"] is True
    assert out["excluded_metrics"] == list(EXCLUDED_METRICS)
    assert "segno" not in (out["markets"][SEL_HOME] or {})
    assert "quota_book" not in (out["markets"][SEL_HOME] or {})
    for m in ANALYZABLE_METRICS:
        assert m in out["markets"][SEL_HOME]


def test_excluded_metrics(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    home = out["markets"][SEL_HOME]
    assert "segno" not in home
    assert "quota_book" not in home
    assert set(EXCLUDED_METRICS) == {"segno", "quota_book"}


def test_prob_book(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["prob_book"]
    assert expl["status"] == "available"
    assert expl["formula_symbolic"].startswith("P_book")
    assert expl["consistency"]["status"] in ("match", "rounding_match")
    assert abs(expl["audit_result"] - round(1 / 2.40, 4)) < 1e-9


def test_prob_cecchino(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["prob_cecchino"]
    assert expl["status"] == "available"
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_vantaggio_prob(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["vantaggio_prob"]
    assert expl["status"] == "available"
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_edge_pct(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["edge_pct"]
    assert expl["status"] == "available"
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_score_acquisto(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["score_acquisto"]
    assert expl["status"] == "available"
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_rating(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["rating"]
    assert expl["status"] == "available"
    assert "components" in expl
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_quota_cecchino_1x2_contributions(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["quota_cecchino"]
    assert expl["status"] == "available"
    assert expl["calculation_type"] == "weighted_picchetti"
    assert len(expl["inputs"]) == 4
    assert expl["consistency"]["status"] in ("match", "rounding_match")
    assert abs(expl["audit_result"] - 2.06) < 0.02


def test_double_chance(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_ONE_X]["quota_cecchino"]
    assert expl["status"] == "available"
    assert expl["calculation_type"] == "derived_from_1x2"
    assert "Probabilità 1" in expl["formula_symbolic"] or "prob" in expl["formula_symbolic"].lower()
    assert expl["consistency"]["status"] in ("match", "rounding_match")


def test_goal_market_persisted(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_OVER_2_5]["quota_cecchino"]
    assert expl["status"] in ("available", "partial")
    assert expl["calculation_type"] == "goal_market_persisted"
    assert expl["formula_version"] == "goal_market_poisson_empirical_v2"
    assert "goal_market_debug" in expl


def test_missing_value_diagnostic(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"]["MISSING_EDGE"]["edge_pct"]
    assert expl["status"] == "unavailable"
    assert expl["unavailable_reason"]
    assert expl["formula_symbolic"]
    assert expl["stored_result"] is None


def test_consistency_match(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    assert out["markets"][SEL_HOME]["prob_book"]["consistency"]["status"] == "match"


def test_consistency_rounding_match(db_mock):
    row = _make_fixture()
    # Forza stored leggermente diverso (entro tolleranza rounding)
    for r in row.kpi_panel_json["rows"]:
        if r["market_key"] == SEL_HOME:
            r["prob_book"] = round(1 / 2.40, 4) + 0.0003
    out = build_kpi_explanations(row, db_mock)
    st = out["markets"][SEL_HOME]["prob_book"]["consistency"]["status"]
    assert st in ("rounding_match", "match")


def test_no_db_writes(db_mock):
    row = _make_fixture()
    build_kpi_explanations(row, db_mock)
    assert not db_mock.add.called
    assert not db_mock.commit.called
    assert not db_mock.flush.called


def test_forbidden_builders_not_called(db_mock, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("builder proibito chiamato")

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_service.get_today_fixture_detail",
        boom,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_service.build_today_payload",
        boom,
        raising=False,
    )
    # Se importati nel modulo explanations non devono essere usati
    out = build_kpi_explanations(_make_fixture(), db_mock)
    assert out["status"] in ("ok", "partial")
    assert out["no_model_recalculation"] is True


def test_purchasability_present(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["purchasability"]
    assert expl["status"] in ("available", "partial")
    assert "√" in expl["formula_symbolic"] or "Fase" in expl["formula_symbolic"]
    assert expl["stored_result"] == 55


def test_historical_reliability_present(db_mock):
    out = build_kpi_explanations(_make_fixture(), db_mock)
    expl = out["markets"][SEL_HOME]["historical_reliability"]
    assert expl["status"] == "available"
    assert expl["stored_result"] == 62


# ---------------------------------------------------------------------------
# STEP 2.1 — Acquistabilità V3 audit hardening
# ---------------------------------------------------------------------------


def _v3_audit_item(
    mk: str,
    *,
    edge: float,
    gate_status: str,
    score: int | None,
    family: str,
    label: str,
    is_leader: bool = False,
    second: str | None = None,
    leader: str | None = None,
    gap: float | None = None,
    gate_passed_comps: list[str] | None = None,
    performance_type: str = "real",
    derived: bool = False,
) -> dict:
    return {
        "market_key": mk,
        "market_label": label,
        "market_family": family,
        "status": "available" if score is not None else "not_applicable",
        "score": score,
        "raw_score": float(score) if score is not None else None,
        "class": "Media" if score == 47 else ("Bassa" if score else None),
        "gate_status": gate_status,
        "gate": {
            "gate_status": gate_status,
            "gate_reason_codes": [],
            "gate_reading": None,
        },
        "gate_reason_codes": [],
        "value_score": 100 if score else None,
        "quality_score": float(score) if score else None,
        "quality_start": 100,
        "total_penalty": None,
        "penalties": {},
        "candidate_version": "cecchino_purchasability_v3_candidate_1",
        "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
        "input": {
            "edge_pct": edge,
            "probability_advantage_pp": 5.0 if gate_status == "passed" else -1.0,
            "performance_type": "derived" if derived else performance_type,
            "not_real_book_quote": derived,
            "diagnostic_only": derived,
        },
        "family": {
            "family_competitors": [],
            "gate_passed_family_competitors": gate_passed_comps or [],
            "best_family_market_by_edge": leader or mk,
            "second_best_family_market_by_edge": second,
            "selected_is_family_edge_leader": is_leader,
            "selected_edge": edge,
            "best_other_edge": 20.0 if mk == "AWAY" else 83.04,
            "edge_gap_or_deficit": gap,
            "ambiguity_status": "leader_clear" if is_leader else "not_leader",
        },
        "reading_short": "sintesi",
        "reading_detailed": "dettaglio",
        "historical_profile_used": False,
        "fixed_scales_used": True,
        "parallel_candidate": True,
        "current_operational_version": False,
    }


def test_purchasability_v3_audit_step21_family_and_versions():
    from app.services.cecchino.cecchino_kpi_explanations import (
        _explain_purchasability_v3,
        _v3_gate_reading_for_audit,
    )

    home = _v3_audit_item(
        "HOME",
        edge=-30.59,
        gate_status="failed_multiple_non_positive_components",
        score=None,
        family="MATCH_WINNER_FT",
        label="1",
        leader="AWAY",
        second="DRAW",
        gap=None,
        gate_passed_comps=["DRAW", "AWAY"],
    )
    draw = _v3_audit_item(
        "DRAW",
        edge=20.0,
        gate_status="passed",
        score=11,
        family="MATCH_WINNER_FT",
        label="X",
        leader="AWAY",
        second="DRAW",
        gap=-63.04,
        is_leader=False,
        gate_passed_comps=["DRAW", "AWAY"],
    )
    away = _v3_audit_item(
        "AWAY",
        edge=83.04,
        gate_status="passed",
        score=47,
        family="MATCH_WINNER_FT",
        label="2",
        leader="AWAY",
        second="DRAW",
        gap=63.04,
        is_leader=True,
        gate_passed_comps=["DRAW", "AWAY"],
    )
    index = {"HOME": home, "DRAW": draw, "AWAY": away}
    kpi = {
        "HOME": {"market_key": "HOME", "edge_pct": -30.59},
        "DRAW": {"market_key": "DRAW", "edge_pct": 20.0},
        "AWAY": {"market_key": "AWAY", "edge_pct": 83.04},
    }
    meta = {
        "candidate_version": "cecchino_purchasability_v3_candidate_1",
        "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
        "audit_version": "cecchino_purchasability_v3_audit_v1",
        "generated_at": "2026-07-28T12:00:00+00:00",
        "source_snapshot_at": "2026-07-28T10:00:00+00:00",
        "pre_match_only": True,
        "historical_profile_used": False,
        "fixed_scales_used": True,
        "parallel_candidate": True,
        "current_operational_version": False,
    }

    expl = _explain_purchasability_v3(
        kpi["AWAY"],
        "2",
        away,
        away,
        meta,
        preview_v3_index=index,
        candidate_v3_index=index,
        kpi_rows_by_market=kpi,
    )
    assert expl["market_family"] == "MATCH_WINNER_FT"
    assert expl["market_family_label"] == "Esito finale 1/X/2"
    assert expl["candidate_version"] == "cecchino_purchasability_v3_candidate_1"
    assert expl["formula_version"] == "cecchino_purchasability_v3_fixed_discount_v1"
    assert expl["candidate_version"] != expl["formula_version"]
    assert expl["audit_version"] == "cecchino_purchasability_v3_audit_v1"
    assert expl["generated_at"] == meta["generated_at"]
    assert expl["source_snapshot_at"] == meta["source_snapshot_at"]

    rows = expl["family_comparison"]["market_rows"]
    assert [r["market_key"] for r in rows] == ["HOME", "DRAW", "AWAY"]
    by_key = {r["market_key"]: r for r in rows}
    assert by_key["AWAY"]["edge_pct"] == 83.04
    assert by_key["DRAW"]["edge_pct"] == 20.0
    assert by_key["HOME"]["edge_pct"] == -30.59
    assert by_key["AWAY"]["is_leader"] is True
    assert by_key["DRAW"]["is_second"] is True
    assert by_key["AWAY"]["rank_by_edge"] == 1
    assert by_key["DRAW"]["rank_by_edge"] == 2
    assert by_key["HOME"]["rank_by_edge"] == 3
    assert by_key["HOME"]["gate_status"] == "failed_multiple_non_positive_components"
    assert by_key["DRAW"]["gate_status"] == "passed"
    assert by_key["AWAY"]["gate_status"] == "passed"
    assert by_key["AWAY"]["score"] == 47
    assert by_key["DRAW"]["score"] == 11
    assert by_key["HOME"]["score"] is None
    assert abs(by_key["DRAW"]["edge_diff_from_leader"] - (-63.04)) < 0.01
    # Nessuna ricostruzione score
    assert expl["persisted_result"]["score"] == 47
    assert expl["stored_result"] == 47

    expl_draw = _explain_purchasability_v3(
        kpi["DRAW"],
        "X",
        draw,
        draw,
        meta,
        preview_v3_index=index,
        candidate_v3_index=index,
        kpi_rows_by_market=kpi,
    )
    rows_d = {r["market_key"]: r for r in expl_draw["family_comparison"]["market_rows"]}
    assert rows_d["AWAY"]["edge_pct"] == 83.04
    assert rows_d["DRAW"]["edge_pct"] == 20.0
    assert rows_d["HOME"]["edge_pct"] == -30.59
    assert rows_d["AWAY"]["is_leader"] is True

    assert "Non supportato" in _v3_gate_reading_for_audit("unsupported_market") or (
        "non supportato" in _v3_gate_reading_for_audit("unsupported_market").lower()
    )
    assert "non sono disponibili" in _v3_gate_reading_for_audit("unavailable_inputs").lower()
    assert "non sono positivi" in _v3_gate_reading_for_audit(
        "failed_multiple_non_positive_components"
    ).lower()
    assert _v3_gate_reading_for_audit("passed") == "Indice attivato"


def test_purchasability_v3_audit_family_goals_and_dc():
    from app.services.cecchino.cecchino_kpi_explanations import _explain_purchasability_v3

    over = _v3_audit_item(
        "OVER_2_5",
        edge=10.0,
        gate_status="passed",
        score=20,
        family="GOALS_FT_2_5",
        label="Over 2.5",
        leader="UNDER_2_5",
        second="OVER_2_5",
        is_leader=False,
        gate_passed_comps=["OVER_2_5", "UNDER_2_5"],
    )
    under = _v3_audit_item(
        "UNDER_2_5",
        edge=25.0,
        gate_status="passed",
        score=12,
        family="GOALS_FT_2_5",
        label="Under 2.5",
        leader="UNDER_2_5",
        second="OVER_2_5",
        is_leader=True,
        gate_passed_comps=["OVER_2_5", "UNDER_2_5"],
    )
    # Fix under edge higher for leader
    under["input"]["edge_pct"] = 25.0
    over["input"]["edge_pct"] = 10.0
    g_index = {"OVER_2_5": over, "UNDER_2_5": under}
    expl_g = _explain_purchasability_v3(
        {"market_key": "UNDER_2_5", "edge_pct": 25.0},
        "Under 2.5",
        under,
        under,
        {
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
            "audit_version": "cecchino_purchasability_v3_audit_v1",
        },
        preview_v3_index=g_index,
        candidate_v3_index=g_index,
        kpi_rows_by_market={
            "OVER_2_5": {"market_key": "OVER_2_5", "edge_pct": 10.0},
            "UNDER_2_5": {"market_key": "UNDER_2_5", "edge_pct": 25.0},
        },
    )
    assert expl_g["market_family"] == "GOALS_FT_2_5"
    assert expl_g["market_family_label"] == "Goal FT 2.5"
    keys_g = [r["market_key"] for r in expl_g["family_comparison"]["market_rows"]]
    assert keys_g == ["OVER_2_5", "UNDER_2_5"]
    assert set(keys_g) == {"OVER_2_5", "UNDER_2_5"}

    ox = _v3_audit_item(
        "ONE_X",
        edge=5.0,
        gate_status="passed",
        score=10,
        family="DOUBLE_CHANCE",
        label="1X",
        leader="X_TWO",
        second="ONE_X",
        derived=True,
        gate_passed_comps=["ONE_X", "X_TWO", "ONE_TWO"],
    )
    xt = _v3_audit_item(
        "X_TWO",
        edge=40.0,
        gate_status="passed",
        score=50,
        family="DOUBLE_CHANCE",
        label="X2",
        leader="X_TWO",
        second="ONE_X",
        is_leader=True,
        derived=True,
        gate_passed_comps=["ONE_X", "X_TWO", "ONE_TWO"],
    )
    ot = _v3_audit_item(
        "ONE_TWO",
        edge=-5.0,
        gate_status="failed_non_positive_edge",
        score=None,
        family="DOUBLE_CHANCE",
        label="12",
        leader="X_TWO",
        second="ONE_X",
        derived=True,
        gate_passed_comps=["ONE_X", "X_TWO"],
    )
    d_index = {"ONE_X": ox, "X_TWO": xt, "ONE_TWO": ot}
    expl_d = _explain_purchasability_v3(
        {"market_key": "X_TWO", "edge_pct": 40.0},
        "X2",
        xt,
        xt,
        {
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
            "audit_version": "cecchino_purchasability_v3_audit_v1",
        },
        preview_v3_index=d_index,
        candidate_v3_index=d_index,
        kpi_rows_by_market={
            "ONE_X": {"market_key": "ONE_X", "edge_pct": 5.0},
            "X_TWO": {"market_key": "X_TWO", "edge_pct": 40.0},
            "ONE_TWO": {"market_key": "ONE_TWO", "edge_pct": -5.0},
        },
    )
    assert expl_d["market_family"] == "DOUBLE_CHANCE"
    assert expl_d["market_family_label"] == "Doppia chance"
    keys_d = [r["market_key"] for r in expl_d["family_comparison"]["market_rows"]]
    assert keys_d == ["ONE_X", "X_TWO", "ONE_TWO"]
    assert expl_d["derived_quote"] is True
    assert expl_d["stored_result"] == 50


def test_purchasability_v3_audit_null_timestamps_and_v2_intact(db_mock):
    from app.services.cecchino.cecchino_kpi_explanations import _explain_purchasability_v3

    away = _v3_audit_item(
        "AWAY",
        edge=83.04,
        gate_status="passed",
        score=47,
        family="MATCH_WINNER_FT",
        label="2",
        is_leader=True,
        leader="AWAY",
        second="DRAW",
        gate_passed_comps=["DRAW", "AWAY"],
    )
    expl = _explain_purchasability_v3(
        {"market_key": "AWAY", "edge_pct": 83.04},
        "2",
        away,
        away,
        {
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
            "audit_version": "cecchino_purchasability_v3_audit_v1",
        },
    )
    assert expl["generated_at"] is None
    assert expl["source_snapshot_at"] is None

    out = build_kpi_explanations(_make_fixture(), db_mock)
    # V1.1 / V2 ancora presenti e analizzabili
    assert "purchasability_v1_1" in out["markets"][SEL_HOME]
    assert "purchasability_v2" in out["markets"][SEL_HOME]
    assert "purchasability_v3" in out["markets"][SEL_HOME]
    v11 = out["markets"][SEL_HOME]["purchasability_v1_1"]
    assert v11["metric_key"] == "purchasability_v1_1"
    assert v11["stored_result"] == 55
