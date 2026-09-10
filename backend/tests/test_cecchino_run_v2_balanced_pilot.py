"""Test mirati RUN V2: pilot bilanciato, is_predicted_selection, economic legacy."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_is_predicted_selection_marks_only_family_argmax():
    from app.services.cecchino_data_lab.run_v2.constants import CORE_MARKETS
    from app.services.cecchino_data_lab.run_v2.market_rows import (
        build_core_strict_market_rows,
    )

    # Probabilita artificiali: HOME vince 1X2, ONE_X vince DC, OVER_2_5 vince OU 2.5.
    kpi_rows = [
        {"market_key": "HOME", "prob_cecchino": 0.55, "quota_cecchino": 1.8, "rating": 3},
        {"market_key": "DRAW", "prob_cecchino": 0.25, "quota_cecchino": 3.5, "rating": 2},
        {"market_key": "AWAY", "prob_cecchino": 0.20, "quota_cecchino": 4.0, "rating": 1},
        {"market_key": "ONE_X", "prob_cecchino": 0.70, "quota_cecchino": 1.3, "rating": 3},
        {"market_key": "ONE_TWO", "prob_cecchino": 0.60, "quota_cecchino": 1.4, "rating": 2},
        {"market_key": "X_TWO", "prob_cecchino": 0.40, "quota_cecchino": 1.8, "rating": 1},
        {"market_key": "OVER_2_5", "prob_cecchino": 0.62, "quota_cecchino": 1.7, "rating": 3},
        {"market_key": "UNDER_2_5", "prob_cecchino": 0.38, "quota_cecchino": 2.2, "rating": 2},
    ]
    strict = {
        m.key: {
            "value": 2.0,
            "pre_match_input_safe": True,
            "used_for_prediction": True,
            "is_real_quote": True,
            "is_derived": False,
        }
        for m in CORE_MARKETS
    }
    outcomes = {
        m.key: {"outcome": "UNKNOWN", "won": None, "result_reason": None}
        for m in CORE_MARKETS
    }

    rows = build_core_strict_market_rows(
        kpi_panel={"rows": kpi_rows},
        goal_markets={},
        ou_05_markets={},
        ht_1x2_markets={},
        strict_by_market=strict,
        balance=None,
        gi_payload=None,
        purchasability=None,
        outcomes=outcomes,
    )

    by_key = {r["market_key"]: r for r in rows}
    assert by_key["HOME"]["is_predicted_selection"] is True
    assert by_key["DRAW"]["is_predicted_selection"] is False
    assert by_key["AWAY"]["is_predicted_selection"] is False
    assert by_key["HOME"]["prediction"] == "HOME"
    assert by_key["DRAW"]["prediction"] == "HOME"

    assert by_key["ONE_X"]["is_predicted_selection"] is True
    assert by_key["ONE_TWO"]["is_predicted_selection"] is False
    assert by_key["OVER_2_5"]["is_predicted_selection"] is True
    assert by_key["UNDER_2_5"]["is_predicted_selection"] is False

    # Condizione esatta del codice: predicted_key == market.key
    for r in rows:
        assert r["is_predicted_selection"] is (r["prediction"] == r["market_key"])


def test_core_result_orm_persists_is_predicted_selection():
    from app.services.cecchino_data_lab.run_v2.executor import _core_result_orm

    row = {
        "market_key": "HOME",
        "market_label": "1",
        "market_family": "FT_1X2",
        "period": "FT",
        "line": None,
        "prediction": "HOME",
        "is_predicted_selection": True,
        "probability": 0.55,
        "market_available": True,
        "market_quote_available": True,
        "pre_match_input_safe": True,
        "used_for_prediction": True,
        "is_real_quote": True,
        "is_derived_quote": False,
    }
    orm = _core_result_orm(1, 2, 3, row)
    assert orm.is_predicted_selection is True
    assert orm.prediction == "HOME"


def test_economic_benchmark_neutralized_when_no_economic_rows():
    from app.services.cecchino_data_lab.run_v2.summary import _economic_benchmark_totals

    db = MagicMock()
    db.execute.return_value.one.return_value = (0, 0, 0.0)
    payload = _economic_benchmark_totals(db, run_id=99)
    assert payload["active"] is False
    assert payload["deprecated_for_new_runs"] is True
    assert payload["rows"] == 0
    assert "pre_match_input_safe" not in payload
    assert "economic_observation_only" not in payload


def test_economic_benchmark_keeps_legacy_flags_when_rows_present():
    from app.services.cecchino_data_lab.run_v2.summary import _economic_benchmark_totals

    db = MagicMock()
    db.execute.return_value.one.return_value = (4, 2, 1.5)
    payload = _economic_benchmark_totals(db, run_id=99)
    assert payload["active"] is True
    assert payload["rows"] == 4
    assert payload["pre_match_input_safe"] is False
    assert payload["economic_observation_only"] is True


def test_create_run_balanced_pilot_policy_no_max_matches_slice():
    from app.services.cecchino_data_lab.run_v2.constants import (
        RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION,
        RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
        RUN_V2_SCOPE_BALANCED_PILOT,
    )
    from app.services.cecchino_data_lab.run_v2.executor import (
        create_run_v2,
        is_balanced_pilot_run,
        select_work_for_run,
    )

    db = MagicMock()
    captured = {}

    def _add(obj):
        captured["run"] = obj

    db.add.side_effect = _add
    db.commit.side_effect = lambda: None
    db.refresh.side_effect = lambda obj: setattr(obj, "id", 7)

    run = create_run_v2(
        db,
        season_label="2021/2022",
        run_scope=RUN_V2_SCOPE_BALANCED_PILOT,
        pilot_strategy=RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP,
        eligible_per_competition=3,
        max_matches=50,  # deve essere ignorato
    )
    assert run.run_scope == RUN_V2_SCOPE_BALANCED_PILOT
    assert run.max_matches is None
    assert is_balanced_pilot_run(run) is True
    policy = run.module_policy_json
    assert policy["pilot_strategy"] == RUN_V2_PILOT_STRATEGY_ELIGIBLE_PER_COMP
    assert policy["eligible_per_competition"] == 3
    assert (
        policy["target_eligible_per_competition"]
        == RUN_V2_BALANCED_PILOT_ELIGIBLE_PER_COMPETITION
    )

    # select_work: tutta la stagione, niente slice ai primi 50.
    work = [
        SimpleNamespace(
            season_label="2021/2022",
            competition=f"C{i % 2}",
            rolling_key=f"C{i % 2}::2021/2022",
            dataset=SimpleNamespace(id=1),
            match=SimpleNamespace(
                id=i,
                kickoff_at=None,
                home_team="H",
                away_team="A",
            ),
        )
        for i in range(80)
    ]
    # match_sort_key_v4 needs real kickoff — stub via patch would be heavy;
    # instead only assert balanced path skips slicing when max_matches is None.
    run.max_matches = None
    # Without sorting dependencies: call with empty and with same season items
    # that have comparable keys — use a tiny fake by patching sort key.
    from app.services.cecchino_data_lab.run_v2 import executor as ex

    original = ex.match_sort_key_v4
    ex.match_sort_key_v4 = lambda *a, **k: (0, 0, 0)
    try:
        selected = select_work_for_run(run, work)
    finally:
        ex.match_sort_key_v4 = original
    assert len(selected) == 80


def test_select_work_smoke_pilot_still_slices_first_n():
    from app.services.cecchino_data_lab.run_v2.executor import select_work_for_run
    from app.services.cecchino_data_lab.run_v2 import executor as ex

    run = SimpleNamespace(
        id=1,
        run_scope="pilot",
        max_matches=50,
        module_policy_json={
            "season_label": "2021/2022",
            "run_scope": "pilot",
            "pilot_strategy": "max_matches",
        },
    )
    work = [
        SimpleNamespace(
            season_label="2021/2022",
            competition="E0",
            rolling_key="E0::2021/2022",
            dataset=SimpleNamespace(id=1),
            match=SimpleNamespace(id=i, kickoff_at=None),
        )
        for i in range(80)
    ]
    original = ex.match_sort_key_v4
    ex.match_sort_key_v4 = lambda *a, **k: (a[0].id,)
    try:
        selected = select_work_for_run(run, work)
    finally:
        ex.match_sort_key_v4 = original
    assert len(selected) == 50


def test_is_predicted_selection_in_long_and_full_registry():
    from app.services.cecchino_data_lab.run_v2.column_registry import (
        CORE_MARKETS_LONG_COLUMNS,
        full_export_columns,
    )

    long_names = [c[0] for c in CORE_MARKETS_LONG_COLUMNS]
    assert "is_predicted_selection" in long_names
    full_names = [c.column for c in full_export_columns()]
    assert any(name.endswith("_is_predicted_selection") for name in full_names)


def test_orm_model_has_is_predicted_selection_column():
    from app.models.cecchino_run_v2 import CecchinoRunV2MarketResult

    assert "is_predicted_selection" in CecchinoRunV2MarketResult.__table__.c
