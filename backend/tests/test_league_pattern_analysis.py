"""Test League Pattern Analysis — registry, hash, helper, latest semantics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cecchino_data_lab.historical_analytics_agg import as_dict
from app.services.cecchino_data_lab.league_pattern_analysis import (
    compute_competition_regimes_from_snapshots,
    get_latest_league_pattern_analysis_snapshot,
)
from app.services.cecchino_data_lab.league_pattern_analysis_registry import (
    ANALYSIS_VERSION,
    FUTURE_OOS_SEASON,
    FROZEN_LN_SCIENTIFIC_FILTERS_SHA256,
    INCOMPATIBILITY_HYPOTHESES,
    LEAGUE_NATIVE_PATTERNS,
    LOCKED_SEASONS,
    LOCKED_SOURCE_RUN_IDS,
    SPECIALIZATION_HYPOTHESES,
    humanize_filters,
    ln_scientific_filters,
)
from app.services.cecchino_data_lab.pattern_lab_preset_metrics import (
    bump_pattern_selection,
    bump_real_only_econ,
    empty_econ_bucket,
    finalize_real_only_econ,
)
from app.services.cecchino_data_lab.pattern_lab_presets import (
    PATTERN_LAB_PRESETS,
    scientific_filters_sha256,
)


def test_locked_source_runs_and_seasons():
    assert LOCKED_SOURCE_RUN_IDS == [17, 19, 20, 21]
    assert LOCKED_SEASONS == [
        "2021/2022",
        "2022/2023",
        "2023/2024",
        "2024/2025",
    ]
    assert FUTURE_OOS_SEASON == "2025/2026"
    assert FUTURE_OOS_SEASON not in LOCKED_SEASONS


def test_global_and_native_counts():
    assert len(PATTERN_LAB_PRESETS) == 12
    assert len(LEAGUE_NATIVE_PATTERNS) == 10
    assert [p["id"] for p in LEAGUE_NATIVE_PATTERNS] == [f"LN{i:02d}" for i in range(1, 11)]


def test_ln_frozen_hashes():
    for p in LEAGUE_NATIVE_PATTERNS:
        filters = ln_scientific_filters(p)
        computed = scientific_filters_sha256(filters)
        assert computed == FROZEN_LN_SCIENTIFIC_FILTERS_SHA256[p["id"]], p["id"]


def test_ln_base_ops_eligible_core_market_informative():
    for p in LEAGUE_NATIVE_PATTERNS:
        f = p["filters"]
        assert f.get("eligibility") == "eligible_core", p["id"]
        assert f.get("market_informative") is True, p["id"]


def test_pooled_roi_is_profit_over_n():
    bucket = empty_econ_bucket()
    rows = [
        {
            "pre_quote_type": "real",
            "pre_is_real_book_quote": True,
            "target_won": True,
            "target_lost": False,
            "target_void": False,
            "target_profit_1u_real": 1.5,
            "pre_quota_bet365": 2.5,
        },
        {
            "pre_quote_type": "real",
            "pre_is_real_book_quote": True,
            "target_won": False,
            "target_lost": True,
            "target_void": False,
            "target_profit_1u_real": -1.0,
            "pre_quota_bet365": 2.0,
        },
    ]
    for row in rows:
        bump_pattern_selection(bucket, row)
        bump_real_only_econ(bucket, row)
    fin = finalize_real_only_econ(bucket)
    assert fin["real_quote_count"] == 2
    assert abs(fin["profit_1u"] - 0.5) < 1e-9
    assert abs(fin["roi"] - (0.5 / 2)) < 1e-9


def test_competition_baseline_is_match_level_not_market_rows():
    snaps = [
        SimpleNamespace(
            competition_name="Serie B",
            season_label="2021/2022",
            result_json={"fulltime": {"home": 1, "away": 1}},
        ),
        SimpleNamespace(
            competition_name="Serie B",
            season_label="2021/2022",
            result_json={"fulltime": {"home": 2, "away": 0}},
        ),
    ]
    assert as_dict(snaps[0].result_json)["fulltime"]["home"] == 1
    regimes = compute_competition_regimes_from_snapshots(snaps)
    serie_b = next(L for L in regimes["leagues"] if L["competition"] == "Serie B")
    assert serie_b["by_season"]["2021/2022"]["matches"] == 2
    assert abs(serie_b["by_season"]["2021/2022"]["draw_pct"] - 50.0) < 1e-6
    assert abs(serie_b["by_season"]["2021/2022"]["home_pct"] - 50.0) < 1e-6


def test_specializations_do_not_mutate_presets():
    before = [p["id"] for p in PATTERN_LAB_PRESETS]
    assert len(SPECIALIZATION_HYPOTHESES) == 4
    assert len(INCOMPATIBILITY_HYPOTHESES) == 4
    after = [p["id"] for p in PATTERN_LAB_PRESETS]
    assert before == after
    assert before == [f"P{i:02d}" for i in range(1, 13)]


def test_humanize_filters_produces_title_and_formula():
    p09 = next(p for p in PATTERN_LAB_PRESETS if p["id"] == "P09")
    human = humanize_filters(p09["filters"], pattern_id="P09")
    assert "technical_formula" in human
    assert "DRAW" in human["technical_formula"]
    assert human["structured_conditions"]
    assert "short_explanation" in human


def test_latest_filters_ready_and_analysis_version():
    db = MagicMock()
    ready = SimpleNamespace(id=2, status="ready", analysis_version=ANALYSIS_VERSION)
    db.execute.return_value.scalar_one_or_none.return_value = ready
    got = get_latest_league_pattern_analysis_snapshot(db)
    assert got is ready
    assert db.execute.called
