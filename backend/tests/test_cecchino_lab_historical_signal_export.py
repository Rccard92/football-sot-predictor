"""Test export canonico opportunità segnali A–F (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.cecchino_data_lab.historical_analytics_agg import ANALYTICS_AGGREGATION_VERSION
from app.services.cecchino_data_lab.historical_signal_export import (
    CURRENT_MODEL_KEY,
    SIGNAL_EXPORT_SCHEMA_VERSION,
    build_cell_rows_from_opportunity,
    build_model_overlap_matrix,
    build_opportunity_id,
    build_signal_cell_id,
    build_signal_export_reconciliation,
    build_signal_models_summary,
    collect_all_opportunities,
    normalize_signal_market_key,
    public_opportunity_row,
)


def _market(
    *,
    snapshot_id: int,
    market_key: str,
    prob=0.4,
    quota=2.5,
    rating=80,
    won=True,
    real=True,
    profit=1.5,
    signal_active=False,
):
    return SimpleNamespace(
        id=1,
        run_id=1,
        match_snapshot_id=snapshot_id,
        lab_match_id=10,
        market_key=market_key,
        market_label=market_key,
        period="FT",
        line=None,
        prob_cecchino=prob,
        quota_cecchino=quota,
        rating=rating,
        edge_pct=5.0,
        vantaggio_prob=0.02,
        is_real_book_quote=real,
        is_derived_quote=not real,
        quota_book=2.5 if real or not real else None,
        won=won,
        evaluation_status="won" if won else "lost",
        result_reason="ft",
        profit_1u_real=profit if real else None,
        profit_1u_synthetic=None if real else profit,
        signal_active=signal_active,
        profit_category="real" if real else "synthetic",
    )


def _snap(
    *,
    sid: int = 100,
    models: dict | None = None,
    purch_markets: list | None = None,
):
    return SimpleNamespace(
        id=sid,
        run_id=1,
        dataset_id=7,
        lab_match_id=10,
        competition_name="Serie A",
        kickoff_at=datetime(2021, 9, 1, 18, 0, tzinfo=timezone.utc),
        chronological_order=1,
        home_team="Home FC",
        away_team="Away FC",
        settlement_status="settled",
        result_json={
            "fulltime": {"home": 2, "away": 1},
            "halftime": {"home": 1, "away": 0},
        },
        purchasability_compatibility_json={
            "execution_status": "computed",
            "historical_purchasability_status": "computed",
            "markets": purch_markets
            or [
                {"market_key": "HOME", "score": 72, "status": "ok"},
                {"market_key": "OVER_2_5", "score": 55, "status": "ok"},
                {"market_key": "ONE_X", "score": 60, "status": "ok"},
            ],
        },
        signals_json={
            "default_model_key": "F",
            "models": models
            or {
                "A": {
                    "active_signals": [
                        {
                            "row_key": "one",
                            "signal_group": "HOME",
                            "signal_family": "HOME",
                            "signal_label": "1",
                            "source_column": "EXCEL_D",
                            "column_key": "excel_d",
                            "raw_signal_value": "SI",
                        },
                        {
                            "row_key": "one",
                            "signal_group": "HOME",
                            "signal_family": "HOME",
                            "signal_label": "1",
                            "source_column": "EXCEL_E",
                            "column_key": "excel_e",
                            "raw_signal_value": "SI",
                        },
                        {
                            "row_key": "one",
                            "signal_group": "HOME",
                            "signal_family": "HOME",
                            "signal_label": "1",
                            "source_column": "EXCEL_F",
                            "column_key": "excel_f",
                            "raw_signal_value": "SI",
                        },
                    ],
                    "settlements": [
                        {"target_market": "HOME", "signal_family": "HOME", "source_column": "EXCEL_D"},
                        {"target_market": "HOME", "signal_family": "HOME", "source_column": "EXCEL_E"},
                        {"target_market": "HOME", "signal_family": "HOME", "source_column": "EXCEL_F"},
                    ],
                },
                "B": {"active_signals": [], "settlements": []},
                "C": {"active_signals": [], "settlements": []},
                "D": {"active_signals": [], "settlements": []},
                "E": {"active_signals": [], "settlements": []},
                "F": {
                    "active_signals": [
                        {
                            "row_key": "one",
                            "signal_group": "HOME",
                            "signal_family": "HOME",
                            "signal_label": "1",
                            "source_column": "EXCEL_D",
                            "column_key": "excel_d",
                            "raw_signal_value": "SI",
                        },
                        {
                            "row_key": "over_over_pt",
                            "signal_group": "OVER_OVER_PT",
                            "signal_family": "OVER_OVER_PT",
                            "signal_label": "Over",
                            "source_column": "EXCEL_D",
                            "column_key": "excel_d",
                            "raw_signal_value": "SI",
                        },
                    ],
                    "settlements": [
                        {"target_market": "HOME", "signal_family": "HOME", "source_column": "EXCEL_D"},
                        {
                            "target_market": "OVER_2_5",
                            "signal_family": "OVER_OVER_PT",
                            "source_column": "EXCEL_D",
                            "quota_cecchino": None,
                            "probabilita_cecchino": None,
                        },
                    ],
                },
            },
        },
    )


def test_versions():
    assert ANALYTICS_AGGREGATION_VERSION == "cecchino_lab_analytics_agg_v2_2"
    assert SIGNAL_EXPORT_SCHEMA_VERSION == "cecchino_lab_signal_export_v1"
    assert CURRENT_MODEL_KEY == "F"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HOME", "HOME"),
        ("DRAW", "DRAW"),
        ("AWAY", "AWAY"),
        ("OVER", "OVER_2_5"),
        ("OVER_2_5", "OVER_2_5"),
        ("UNDER", "UNDER_2_5"),
        ("UNDER_2_5", "UNDER_2_5"),
        ("ONE_X", "ONE_X"),
        ("X_TWO", "X_TWO"),
        ("ONE_TWO", "ONE_TWO"),
        ("1X", "ONE_X"),
        (None, None),
        ("TOTALLY_UNKNOWN", None),
    ],
)
def test_normalize_signal_market_key(raw, expected):
    assert normalize_signal_market_key(raw) == expected


def test_opportunity_and_cell_ids_deterministic():
    oid = build_opportunity_id(run_id=3, snapshot_id=100, model_key="A", market_key="HOME")
    assert oid == "run:3:snapshot:100:model:A:market:HOME"
    cid = build_signal_cell_id(oid, signal_group="HOME", source_column="EXCEL_D", cell_key="one")
    assert cid == "run:3:snapshot:100:model:A:market:HOME:group:HOME:col:EXCEL_D:cell:one"
    assert build_opportunity_id(run_id=3, snapshot_id=100, model_key="A", market_key="HOME") == oid


def test_three_cells_one_opportunity_three_cell_rows():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME", signal_active=True),
        _market(snapshot_id=100, market_key="OVER_2_5", prob=0.55, quota=1.9, rating=70),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    a_home = [o for o in opps if o["model_key"] == "A" and o["market_key"] == "HOME"]
    assert len(a_home) == 1
    opp = a_home[0]
    assert opp["row_granularity"] == "signal_opportunity"
    assert opp["active_cell_count"] == 3
    assert len(opp["active_cells"]) == 3
    cells = build_cell_rows_from_opportunity(opp)
    assert len(cells) == 3
    assert all(c["row_granularity"] == "signal_cell" for c in cells)
    assert all(c["do_not_sum_as_independent_opportunities"] is True for c in cells)
    assert all(c["do_not_sum_cell_profit"] is True for c in cells)
    assert all(c["profit_attribution"] == "shared_opportunity_result" for c in cells)
    assert all(c["opportunity_id"] == opp["opportunity_id"] for c in cells)
    assert len({c["signal_cell_id"] for c in cells}) == 3


def test_reconciliation_and_unique_ids():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME"),
        _market(snapshot_id=100, market_key="OVER_2_5"),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    cell_rows = []
    for o in opps:
        cell_rows.extend(build_cell_rows_from_opportunity(o))
    recon = build_signal_export_reconciliation(opps, cell_rows)
    assert recon["cell_rows"] == recon["sum_active_cell_count"]
    assert recon["cell_rows_equal_sum_active_cell_count"] is True
    assert recon["opportunity_rows"] == recon["unique_opportunity_ids"]
    assert recon["opportunity_id_unique"] is True
    assert recon["performance_uses_opportunities_only"] is True
    assert recon["current_model_key"] == "F"


def test_with_signal_active_is_opportunity_count_not_f_overlap():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME", signal_active=True),
        _market(snapshot_id=100, market_key="OVER_2_5"),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    summary = build_signal_models_summary(opps)
    by_key = {m["model_key"]: m for m in summary["models"]}
    # A ha 1 opportunità HOME (3 celle) — with_signal_active = 1, non overlap F
    assert by_key["A"]["with_signal_active"] == by_key["A"]["model_active_opportunity_count"] == 1
    assert by_key["A"]["active_cell_row_count"] == 3
    assert by_key["A"]["overlap_with_current_model_F_count"] == 1  # HOME condivisa con F
    assert by_key["F"]["model_active_opportunity_count"] == 2  # HOME + OVER


def test_overlap_matrix_and_jaccard():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME"),
        _market(snapshot_id=100, market_key="OVER_2_5"),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    matrix = build_model_overlap_matrix(opps)
    af = next(r for r in matrix if r["model_a"] == "A" and r["model_b"] == "F")
    assert af["intersection_count"] == 1
    assert af["union_count"] == 2
    assert af["jaccard_pct"] == 50.0


def test_market_join_home_over_under_derived():
    snap = _snap(
        models={
            "A": {
                "active_signals": [
                    {
                        "row_key": "one",
                        "signal_group": "HOME",
                        "signal_family": "HOME",
                        "signal_label": "1",
                        "source_column": "EXCEL_D",
                        "raw_signal_value": "SI",
                    },
                    {
                        "row_key": "over_over_pt",
                        "signal_group": "OVER_OVER_PT",
                        "signal_family": "OVER_OVER_PT",
                        "signal_label": "O",
                        "source_column": "EXCEL_D",
                        "raw_signal_value": "SI",
                    },
                    {
                        "row_key": "under_under_pt",
                        "signal_group": "UNDER_UNDER_PT",
                        "signal_family": "UNDER_UNDER_PT",
                        "signal_label": "U",
                        "source_column": "EXCEL_D",
                        "raw_signal_value": "SI",
                    },
                    {
                        "row_key": "one_x",
                        "signal_group": "ONE_X",
                        "signal_family": "ONE_X",
                        "signal_label": "1X",
                        "source_column": "EXCEL_D",
                        "raw_signal_value": "SI",
                    },
                ],
                "settlements": [],
            },
            "B": {"active_signals": [], "settlements": []},
            "C": {"active_signals": [], "settlements": []},
            "D": {"active_signals": [], "settlements": []},
            "E": {"active_signals": [], "settlements": []},
            "F": {"active_signals": [], "settlements": []},
        }
    )
    markets = [
        _market(snapshot_id=100, market_key="HOME", prob=0.45, quota=2.2),
        _market(snapshot_id=100, market_key="OVER_2_5", prob=0.52, quota=1.85),
        _market(snapshot_id=100, market_key="UNDER_2_5", prob=0.48, quota=2.05),
        _market(
            snapshot_id=100,
            market_key="ONE_X",
            prob=0.7,
            quota=1.4,
            real=False,
            profit=0.4,
        ),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    a_opps = {o["market_key"]: o for o in opps if o["model_key"] == "A"}
    assert a_opps["HOME"]["market_join_status"] == "matched"
    assert a_opps["HOME"]["prob_cecchino"] == 0.45
    assert a_opps["HOME"]["quota_cecchino"] == 2.2
    assert a_opps["HOME"]["rating"] == 80
    assert a_opps["HOME"]["purchasability_score"] == 72
    assert a_opps["OVER_2_5"]["prob_cecchino"] == 0.52
    assert a_opps["OVER_2_5"]["quota_cecchino"] == 1.85
    assert a_opps["UNDER_2_5"]["prob_cecchino"] == 0.48
    assert a_opps["ONE_X"]["is_derived_quote"] is True
    assert a_opps["ONE_X"]["prob_cecchino"] == 0.7
    # Nessuna probabilità inventata da Bet365
    assert a_opps["HOME"]["prob_cecchino"] != a_opps["HOME"]["real_book_odds"]


def test_missing_market_join_null_metrics():
    snap = _snap(
        models={
            "A": {
                "active_signals": [
                    {
                        "row_key": "one",
                        "signal_group": "HOME",
                        "signal_family": "HOME",
                        "signal_label": "1",
                        "source_column": "EXCEL_D",
                        "raw_signal_value": "SI",
                    }
                ],
                "settlements": [],
            },
            "B": {"active_signals": [], "settlements": []},
            "C": {"active_signals": [], "settlements": []},
            "D": {"active_signals": [], "settlements": []},
            "E": {"active_signals": [], "settlements": []},
            "F": {"active_signals": [], "settlements": []},
        }
    )
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=[])
    assert len(opps) == 1
    o = opps[0]
    assert o["market_join_status"] == "missing_market_result"
    assert o["prob_cecchino"] is None
    assert o["quota_cecchino"] is None
    assert o["profit_1u_real"] is None
    assert o["performance_eligible"] is False
    diag = build_signal_models_summary(opps)["market_join_diagnostics"]
    assert diag["missing_count"] == 1
    assert diag["matched_count"] == 0


def test_identity_fields_and_scores():
    snap = _snap()
    markets = [_market(snapshot_id=100, market_key="HOME")]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    o = next(x for x in opps if x["model_key"] == "A")
    assert o["home_team"] == "Home FC"
    assert o["away_team"] == "Away FC"
    assert o["kickoff_at"] is not None
    assert o["competition_name"] == "Serie A"
    assert o["home_score_ft"] == 2
    assert o["away_score_ft"] == 1
    assert o["home_score_ht"] == 1
    assert o["dataset_id"] == 7
    pub = public_opportunity_row(o)
    assert "_market_obj" not in pub


def test_performance_not_multiplied_by_cells():
    snap = _snap()
    markets = [_market(snapshot_id=100, market_key="HOME", profit=1.5)]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    summary = build_signal_models_summary(opps)
    a = next(m for m in summary["models"] if m["model_key"] == "A")
    # 3 celle ma 1 opportunità → profit 1.5 non 4.5
    assert a["real_quote_count"] == 1
    assert a["real_profit_1u"] == 1.5
    assert a["active_cell_row_count"] == 3


def test_cell_attribution_overlapping():
    snap = _snap()
    markets = [_market(snapshot_id=100, market_key="HOME")]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    attrs = build_signal_models_summary(opps)["cell_attribution"]
    a_cells = [c for c in attrs if c["model_key"] == "A" and c["market_key"] == "HOME"]
    assert len(a_cells) == 3
    assert all(c["attribution_mode"] == "overlapping" for c in a_cells)
    assert all(c["do_not_sum_across_cells"] is True for c in a_cells)
    assert all(c["shared_with_other_cells_count"] == 1 for c in a_cells)


def test_f_diagnostics():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME"),
        _market(snapshot_id=100, market_key="OVER_2_5"),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    diag = build_signal_models_summary(opps)["current_model_F_diagnostics"]
    assert diag["current_model_key"] == "F"
    assert diag["opportunities_total"] == 2
    assert diag["opportunities_unique_to_F"] == 1  # OVER only in F
    assert "non automaticamente" in (diag.get("note") or "").lower() or "corrente" in (
        diag.get("note") or ""
    ).lower()
    assert isinstance(diag["f_selected_vs_excluded_same_market"], list)


def test_consensus_market_specific():
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME"),
        _market(snapshot_id=100, market_key="OVER_2_5"),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    consensus = build_signal_models_summary(opps)["consensus_distribution"]
    # HOME ha A+F → consensus 2; OVER solo F → consensus 1 — separati
    home = [c for c in consensus if c["market_key"] == "HOME"]
    over = [c for c in consensus if c["market_key"] == "OVER_2_5"]
    assert any(c["consensus_model_count"] == 2 for c in home)
    assert any(c["consensus_model_count"] == 1 for c in over)


def test_no_invented_cecchino_from_settlement_null():
    """Settlement OVER senza prob: join MarketResult recupera; non inventa da Bet365."""
    snap = _snap()
    markets = [
        _market(snapshot_id=100, market_key="HOME"),
        _market(snapshot_id=100, market_key="OVER_2_5", prob=0.61, quota=1.77),
    ]
    opps = collect_all_opportunities(run_id=1, snapshots=[snap], markets=markets)
    f_over = next(o for o in opps if o["model_key"] == "F" and o["market_key"] == "OVER_2_5")
    assert f_over["prob_cecchino"] == 0.61
    assert f_over["quota_cecchino"] == 1.77
