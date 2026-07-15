"""Test analisi statistica Credibilità X — Fase 1C.1 / 1C.2."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.encoders import jsonable_encoder

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, MATCH_FINISHED, CecchinoTodayFixture
from app.services.cecchino.cecchino_constants import STATUS_AVAILABLE
from app.services.cecchino.cecchino_draw_credibility_research_common import normalize_outcome_side
from app.services.cecchino.cecchino_draw_credibility_statistics import (
    VERSION,
    _enrich_research_features,
    apply_quantile_boundaries,
    auc_mann_whitney,
    bootstrap_auc,
    brier_score,
    build_draw_credibility_statistical_analysis,
    build_quantile_boundaries,
    classify_trend,
    classify_trend_with_diagnostics,
    log_loss_score,
    pearson_r,
    spearman_rho,
    wilson_ci,
)
from app.services.cecchino.cecchino_draw_credibility_statistics_helpers import (
    bin_bounds_meta,
    herfindahl,
    hhi_concentration_status,
    matches_candidate_pattern,
)
from app.services.cecchino.cecchino_selection_keys import SEL_AWAY, SEL_DRAW, SEL_HOME, SEL_OVER_2_5, SEL_UNDER_2_5

EXPECTED_INTERACTION_KEYS = [
    "x_rank_x_under_q",
    "dominant_sign_x_conviction_class",
    "f36_class_x_rank",
    "f36_class_x_under_q",
    "x_direction_bucket_x_under_q",
    "dominant_sign_x_f36_class",
    "hours_class_x_prob_x_q",
]

PERFORMANCE_KEYS = [
    "dataset_build_ms",
    "enrichment_ms",
    "univariate_ms",
    "bootstrap_ms",
    "interactions_ms",
    "temporal_ms",
    "league_ms",
    "market_ms",
    "conclusions_ms",
    "statistics_compute_ms",
    "total_ms",
]

PVS_NUMERIC_KEYS = [
    "x_directional_conviction_candidate",
    "hours_to_kickoff",
    "under_strength_pp",
]


def _final(**kwargs) -> dict:
    base = {
        "status": STATUS_AVAILABLE,
        "quota_1": 2.0,
        "quota_x": 3.2,
        "quota_2": 3.5,
        "prob_1": 0.45,
        "prob_x": 0.28,
        "prob_2": 0.27,
    }
    base.update(kwargs)
    return base


def _goal_markets() -> dict:
    return {
        SEL_UNDER_2_5: {"final_odd": 1.85, "status": STATUS_AVAILABLE, "probability": 0.52},
        SEL_OVER_2_5: {"final_odd": 2.05, "status": STATUS_AVAILABLE, "probability": 0.48},
    }


def _kpi_panel(*, with_book: bool = True) -> dict:
    rows = [
        {"market_key": SEL_HOME, "quota_cecchino": 2.0, "quota_book": 2.1 if with_book else None},
        {"market_key": SEL_DRAW, "quota_cecchino": 3.2, "quota_book": 3.3 if with_book else None},
        {"market_key": SEL_AWAY, "quota_cecchino": 3.5, "quota_book": 3.6 if with_book else None},
        {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9 if with_book else None},
        {"market_key": SEL_OVER_2_5, "quota_cecchino": 2.05, "quota_book": 2.1 if with_book else None},
    ]
    return {"version": "cecchino_kpi_v2_betfair", "rows": rows}


def _row(**kwargs) -> CecchinoTodayFixture:
    row = MagicMock(spec=CecchinoTodayFixture)
    kickoff = datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc)
    created = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
    defaults = {
        "id": 1,
        "provider_fixture_id": 9001,
        "local_fixture_id": 501,
        "scan_date": date(2025, 6, 15),
        "competition_id": 39,
        "country_name": "England",
        "league_name": "Premier League",
        "home_team_name": "Home FC",
        "away_team_name": "Away FC",
        "match_display_status": MATCH_FINISHED,
        "eligibility_status": ELIGIBILITY_ELIGIBLE,
        "score_fulltime_home": 1,
        "score_fulltime_away": 1,
        "goals_home": 1,
        "goals_away": 1,
        "kickoff": kickoff,
        "created_at": created,
        "cecchino_output_json": {"version": "cecchino_v1", "final": _final(), "goal_markets": _goal_markets()},
        "kpi_panel_json": _kpi_panel(),
        "odds_snapshot_json": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _many_rows(n: int = 36) -> list[CecchinoTodayFixture]:
    leagues = [
        ("England", "Premier League", 39),
        ("Spain", "La Liga", 140),
        ("Italy", "Serie A", 135),
        ("Germany", "Bundesliga", 78),
        ("France", "Ligue 1", 61),
        ("Portugal", "Primeira Liga", 94),
    ]
    rows: list[CecchinoTodayFixture] = []
    base_day = date(2025, 3, 1)
    for i in range(n):
        league_i = i % len(leagues)
        country, league, comp_id = leagues[league_i]
        day = base_day + timedelta(days=(i * 3) % 120)
        kickoff = datetime(day.year, day.month, day.day, 15 + (i % 5), 0, tzinfo=timezone.utc)
        created = kickoff - timedelta(hours=6 + (i % 48))
        is_draw = i % 3 == 0
        home_g = 1 if is_draw else (2 if i % 2 == 0 else 0)
        away_g = 1 if is_draw else (0 if i % 2 == 0 else 2)
        prob_x = 0.22 + (i % 7) * 0.02
        prob_1 = 0.40 - (i % 5) * 0.01
        prob_2 = max(0.15, 1.0 - prob_1 - prob_x - 0.01)
        rows.append(
            _row(
                id=i + 1,
                provider_fixture_id=9100 + i,
                local_fixture_id=600 + i,
                scan_date=day,
                competition_id=comp_id,
                country_name=country,
                league_name=league,
                home_team_name=f"Home {i}",
                away_team_name=f"Away {i}",
                score_fulltime_home=home_g,
                score_fulltime_away=away_g,
                goals_home=home_g,
                goals_away=away_g,
                kickoff=kickoff,
                created_at=created,
                cecchino_output_json={
                    "version": "cecchino_v1",
                    "final": _final(
                        prob_1=prob_1,
                        prob_x=prob_x,
                        prob_2=prob_2,
                        quota_1=round(1.0 / max(prob_1, 0.05), 2),
                        quota_x=round(1.0 / max(prob_x, 0.05), 2),
                        quota_2=round(1.0 / max(prob_2, 0.05), 2),
                    ),
                    "goal_markets": _goal_markets(),
                },
                kpi_panel_json=_kpi_panel(with_book=True),
            )
        )
    return rows


def _analysis(rows: list | None = None, **kwargs) -> dict:
    db = MagicMock()
    db.scalars.return_value.all.return_value = rows if rows is not None else _many_rows()
    return build_draw_credibility_statistical_analysis(
        db,
        date_from=kwargs.pop("date_from", date(2025, 1, 1)),
        date_to=kwargs.pop("date_to", date(2025, 12, 31)),
        bootstrap_iterations=kwargs.pop("bootstrap_iterations", 40),
        min_group_size=kwargs.pop("min_group_size", 4),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Normalize side
# ---------------------------------------------------------------------------


class TestNormalizeSide:
    def test_home(self):
        assert normalize_outcome_side("HOME") == "HOME"

    def test_draw(self):
        assert normalize_outcome_side("DRAW") == "DRAW"

    def test_away(self):
        assert normalize_outcome_side("AWAY") == "AWAY"

    def test_one(self):
        assert normalize_outcome_side("1") == "HOME"

    def test_x(self):
        assert normalize_outcome_side("X") == "DRAW"

    def test_two(self):
        assert normalize_outcome_side("2") == "AWAY"

    def test_case_insensitive_home(self):
        assert normalize_outcome_side("home") == "HOME"

    def test_case_insensitive_draw(self):
        assert normalize_outcome_side("DrAw") == "DRAW"

    def test_case_insensitive_away(self):
        assert normalize_outcome_side("aWaY") == "AWAY"

    def test_numeric_one(self):
        assert normalize_outcome_side(1) == "HOME"

    def test_numeric_two(self):
        assert normalize_outcome_side(2) == "AWAY"

    def test_unknown_string(self):
        assert normalize_outcome_side("OTHER") is None

    def test_unknown_none(self):
        assert normalize_outcome_side(None) is None

    def test_unknown_empty(self):
        assert normalize_outcome_side("  ") is None


# ---------------------------------------------------------------------------
# Directional conviction
# ---------------------------------------------------------------------------


class TestDirectional:
    def test_draw_positive(self):
        out = _enrich_research_features({
            "conviction_index_candidate": 12.5,
            "dominant_sign": "DRAW",
            "prob_1_norm": 30.0,
            "prob_x_norm": 40.0,
            "prob_2_norm": 30.0,
        })
        assert out["x_directional_conviction_candidate"] == 12.5
        assert out["x_conviction_direction"] == "toward_draw"

    def test_home_negative(self):
        out = _enrich_research_features({
            "conviction_index_candidate": 10.0,
            "dominant_sign": "HOME",
            "prob_1_norm": 50.0,
            "prob_x_norm": 25.0,
            "prob_2_norm": 25.0,
        })
        assert out["x_directional_conviction_candidate"] == -10.0
        assert out["x_conviction_direction"] == "against_draw"

    def test_away_negative(self):
        out = _enrich_research_features({
            "conviction_index_candidate": 8.0,
            "dominant_sign": "AWAY",
            "prob_1_norm": 20.0,
            "prob_x_norm": 25.0,
            "prob_2_norm": 55.0,
        })
        assert out["x_directional_conviction_candidate"] == -8.0
        assert out["x_conviction_direction"] == "against_draw"

    def test_legacy_x_works(self):
        out = _enrich_research_features({
            "conviction_index_candidate": 15.0,
            "dominant_sign": "X",
            "prob_1_norm": 30.0,
            "prob_x_norm": 40.0,
            "prob_2_norm": 30.0,
        })
        assert out["dominant_sign_normalized"] == "DRAW"
        assert out["x_directional_conviction_candidate"] == 15.0
        assert out["x_conviction_direction"] == "toward_draw"

    def test_enrich_on_analysis_payload(self):
        payload = _analysis(_many_rows(30), bootstrap_iterations=30, min_group_size=3)
        assert payload["status"] == "ok"
        primary = payload["numeric_feature_analysis"]["eligible_primary"]
        features = {x["feature"] for x in primary}
        assert "x_directional_conviction_candidate" in features
        assert "dominance_normalized_pp" in features
        assert "under_strength_pp" in features
        assert "hours_to_kickoff" in features


# ---------------------------------------------------------------------------
# Dominance normalized
# ---------------------------------------------------------------------------


class TestDominanceNormalized:
    def test_non_negative_from_norms(self):
        out = _enrich_research_features({
            "prob_1_norm": 45.0,
            "prob_x_norm": 28.0,
            "prob_2_norm": 27.0,
        })
        assert out["dominance_normalized_pp"] == 17.0
        assert out["dominance_normalized_pp"] >= 0

    def test_tie_top_two_zero(self):
        out = _enrich_research_features({
            "prob_1_norm": 40.0,
            "prob_x_norm": 40.0,
            "prob_2_norm": 20.0,
        })
        assert out["dominance_normalized_pp"] == 0.0

    def test_missing_probs_none(self):
        out = _enrich_research_features({"prob_1_norm": 50.0})
        assert out["dominance_normalized_pp"] is None


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


class TestTrend:
    def test_flat(self):
        assert classify_trend([25.0, 25.5, 25.2]) == "flat"

    def test_increasing(self):
        assert classify_trend([20.0, 25.0, 30.0, 35.0]) == "increasing"

    def test_decreasing(self):
        assert classify_trend([35.0, 30.0, 25.0, 20.0]) == "decreasing"

    def test_real_u(self):
        assert classify_trend([40.0, 30.0, 20.0, 30.0, 40.0]) == "u_shaped"

    def test_fake_u_irregular(self):
        assert classify_trend([50.0, 10.0, 40.0, 10.0, 30.0]) == "irregular"

    def test_inverted_u(self):
        assert classify_trend([20.0, 30.0, 40.0, 30.0, 20.0]) == "inverted_u"

    def test_fake_inverted_irregular(self):
        assert classify_trend([25.0, 45.0, 20.0, 50.0, 22.0]) == "irregular"

    def test_diagnostics_keys(self):
        trend, diag = classify_trend_with_diagnostics([40.0, 30.0, 20.0, 30.0, 40.0])
        assert trend == "u_shaped"
        assert diag["valid_bins"] == 5
        assert "reason" in diag
        assert "edge_mean" in diag
        assert "center_mean" in diag
        assert diag["min_bin_index"] is not None
        assert diag["max_bin_index"] is not None

    def test_diagnostics_increasing_reason(self):
        trend, diag = classify_trend_with_diagnostics([20.0, 25.0, 30.0, 35.0])
        assert trend == "increasing"
        assert diag["reason"] == "monotonic_increase"

    def test_insufficient(self):
        assert classify_trend([25.0, 30.0]) == "insufficient_data"

    def test_insufficient_diagnostics(self):
        trend, diag = classify_trend_with_diagnostics([25.0, 30.0])
        assert trend == "insufficient_data"
        assert diag["reason"] == "fewer_than_3_valid_bins"


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


class TestBootstrap:
    def _balanced(self, *, positive_high: bool):
        y = [1, 1, 1, 0, 0, 0] * 8
        if positive_high:
            s = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1] * 8
        else:
            s = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9] * 8
        return y, s

    def test_bootstrap_mean_directional_auc_naming(self):
        y, s = self._balanced(positive_high=True)
        out = bootstrap_auc(y, s, iterations=40, seed=11)
        assert "bootstrap_mean_directional_auc" in out
        assert out["bootstrap_mean_directional_auc"] is not None
        assert out["original_directional_auc"] is not None

    def test_directional_ci(self):
        y, s = self._balanced(positive_high=True)
        out = bootstrap_auc(y, s, iterations=40, seed=11)
        assert out["directional_auc_ci_lower"] is not None
        assert out["directional_auc_ci_upper"] is not None
        assert out["directional_auc_ci_lower"] <= out["directional_auc_ci_upper"]

    def test_disc_ci_when_auc_gt_0_5_equals_dir_ci(self):
        y, s = self._balanced(positive_high=True)
        out = bootstrap_auc(y, s, iterations=40, seed=11)
        assert out["original_directional_auc"] > 0.5
        assert out["discriminative_auc_ci_lower"] == out["directional_auc_ci_lower"]
        assert out["discriminative_auc_ci_upper"] == out["directional_auc_ci_upper"]

    def test_disc_ci_when_auc_lt_0_5_is_flipped(self):
        y, s = self._balanced(positive_high=False)
        out = bootstrap_auc(y, s, iterations=40, seed=11)
        assert out["original_directional_auc"] < 0.5
        lo = out["directional_auc_ci_lower"]
        hi = out["directional_auc_ci_upper"]
        assert out["discriminative_auc_ci_lower"] == pytest.approx(1.0 - hi)
        assert out["discriminative_auc_ci_upper"] == pytest.approx(1.0 - lo)

    def test_reproducible_seed(self):
        y, s = self._balanced(positive_high=True)
        a = bootstrap_auc(y, s, iterations=40, seed=42)
        b = bootstrap_auc(y, s, iterations=40, seed=42)
        assert a["bootstrap_mean_directional_auc"] == b["bootstrap_mean_directional_auc"]
        assert a["directional_auc_ci_lower"] == b["directional_auc_ci_lower"]


# ---------------------------------------------------------------------------
# Quantile boundaries
# ---------------------------------------------------------------------------


class TestQuantileBoundaries:
    def test_build_boundaries(self):
        vals = [float(v) for v in range(1, 101)]
        edges = build_quantile_boundaries(vals, 5)
        assert len(edges) == 4
        assert edges == sorted(edges)
        assert edges[0] < edges[-1]

    def test_build_empty(self):
        assert build_quantile_boundaries([], 5) == []

    def test_build_single_value(self):
        assert build_quantile_boundaries([5.0], 5) == []

    def test_apply_quantile_boundaries(self):
        boundaries = [30.0, 50.0, 70.0]
        labels = apply_quantile_boundaries([10.0, 30.0, 55.0, 70.0, 90.0], boundaries)
        assert labels[0] == 0
        assert labels[1] == 1
        assert labels[2] == 2
        assert labels[3] == 3
        assert labels[4] == 3

    def test_apply_empty_boundaries(self):
        labels = apply_quantile_boundaries([1.0, 2.0, 3.0], [])
        assert labels == [0, 0, 0]


# ---------------------------------------------------------------------------
# Wilson / AUC / Correlations / Calibration
# ---------------------------------------------------------------------------


class TestWilsonAucCorr:
    def test_wilson_zero(self):
        assert wilson_ci(0, 0)["lower_pct"] is None
        assert wilson_ci(0, 0)["upper_pct"] is None

    def test_wilson_nonzero(self):
        ci = wilson_ci(50, 100)
        assert ci["lower_pct"] is not None
        assert ci["upper_pct"] is not None
        assert 0 <= ci["lower_pct"] <= ci["upper_pct"] <= 100

    def test_auc_perfect(self):
        y = [1, 1, 0, 0]
        s = [0.9, 0.8, 0.2, 0.1]
        assert auc_mann_whitney(y, s) == 1.0

    def test_auc_random(self):
        assert auc_mann_whitney([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == 0.5

    def test_auc_single_class_none(self):
        assert auc_mann_whitney([1, 1], [0.1, 0.2]) is None

    def test_pearson(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        assert pearson_r(xs, xs) == pytest.approx(1.0)
        ys = [4.0, 3.0, 2.0, 1.0]
        assert pearson_r(xs, ys) == pytest.approx(-1.0)

    def test_pearson_constant_none(self):
        assert pearson_r([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) is None

    def test_spearman(self):
        xs = [1.0, 2.0, 3.0, 100.0]
        ys = [1.0, 2.0, 3.0, 4.0]
        assert spearman_rho(xs, ys) == pytest.approx(1.0)

    def test_brier(self):
        assert brier_score([1.0, 0.0, 1.0, 0.0], [1, 0, 1, 0]) == 0.0
        assert brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)

    def test_log_loss(self):
        ll = log_loss_score([0.7, 0.3, 0.6, 0.4], [1, 0, 1, 0])
        assert ll is not None and ll > 0
        perfect = log_loss_score([0.999, 0.001], [1, 0])
        assert perfect is not None and perfect < 0.01


# ---------------------------------------------------------------------------
# HHI
# ---------------------------------------------------------------------------


class TestHHI:
    def test_herfindahl_uniform(self):
        assert herfindahl([10, 10, 10, 10]) == pytest.approx(0.25)

    def test_herfindahl_monopoly(self):
        assert herfindahl([100]) == pytest.approx(1.0)

    def test_herfindahl_empty(self):
        assert herfindahl([]) == 0.0
        assert herfindahl([0, 0]) == 0.0

    def test_concentration_highly_fragmented(self):
        assert hhi_concentration_status(0.02) == "highly_fragmented"

    def test_concentration_fragmented(self):
        assert hhi_concentration_status(0.07) == "fragmented"

    def test_concentration_moderate(self):
        assert hhi_concentration_status(0.12) == "moderate_concentration"

    def test_concentration_concentrated(self):
        assert hhi_concentration_status(0.25) == "concentrated"


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_version_v1_2(self):
        assert VERSION == "cecchino_draw_credibility_statistics_v1_2"
        payload = _analysis(_many_rows(20), bootstrap_iterations=30, min_group_size=3)
        assert payload["version"] == VERSION

    def test_seven_interactions_with_keys(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        interactions = payload["interaction_analysis"]
        assert len(interactions) == 7
        keys = [ix["interaction_key"] for ix in interactions]
        assert keys == EXPECTED_INTERACTION_KEYS

    def test_cell_structure_suppressed_reliable(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=5)
        cells = []
        for ix in payload["interaction_analysis"]:
            cells.extend(ix.get("primary_cells") or [])
        assert cells
        for cell in cells:
            assert "suppressed" in cell
            assert "reliable" in cell
            assert cell["suppressed"] is (not cell["reliable"])
            assert "row_category" in cell
            assert "column_category" in cell
            assert "count" in cell
            assert "draws" in cell

    def test_candidate_patterns_is_list(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        assert isinstance(payload["candidate_patterns"], list)

    def test_pvs_includes_key_numerics(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        pvs = payload["primary_vs_sensitivity"]
        features = {c["feature"] for c in pvs["feature_comparisons"] if c.get("type") == "numeric"}
        for key in PVS_NUMERIC_KEYS:
            assert key in features
        assert "sensitivity_only_fixtures" in pvs

    def test_sensitivity_only_fields(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        so = payload["primary_vs_sensitivity"]["sensitivity_only_fixtures"]
        for key in (
            "count",
            "draws",
            "non_draws",
            "draw_rate_pct",
            "wilson_ci_95",
            "eligibility_status_distribution",
            "means",
            "primary_means_for_comparison",
        ):
            assert key in so

    def test_temporal_iso_weeks_and_blocks(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        temporal = payload["temporal_stability"]
        assert "iso_weeks" in temporal
        assert isinstance(temporal["iso_weeks"], list)
        assert "chronological_blocks" in temporal
        assert isinstance(temporal["chronological_blocks"], list)
        assert len(temporal["chronological_blocks"]) >= 1

    def test_league_hhi_top5_leagues(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        league = payload["league_stability"]
        assert "hhi" in league
        assert "concentration_status" in league
        assert "top_5_share_pct" in league
        assert "leagues" in league
        assert isinstance(league["leagues"], list)
        assert len(league["leagues"]) >= 1

    def test_market_comparison_roi_breakdown(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        market = payload["market_analysis"]
        assert "comparison" in market
        assert "roi" in market
        assert "roi_breakdown" in market
        assert isinstance(market["comparison"], dict)
        assert "rows_compared" in market["comparison"]

    def test_conclusions_structure(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        conc = payload["research_conclusions"]
        assert "modest_candidates" in conc
        assert isinstance(conc["modest_candidates"], list)
        assert "redundant_groups" in conc
        assert isinstance(conc["redundant_groups"], list)
        assert "next_phase_feature_recommendations" in conc
        assert isinstance(conc["next_phase_feature_recommendations"], list)

    def test_next_phase_no_dupes_max_10(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        conc = payload["research_conclusions"]
        next_feats = conc["next_phase_features"]
        recs = conc["next_phase_feature_recommendations"]
        assert len(next_feats) <= 10
        assert len(recs) <= 10
        assert len(next_feats) == len(set(next_feats))
        rec_feats = [r["feature"] for r in recs]
        assert len(rec_feats) == len(set(rec_feats))
        assert next_feats == rec_feats

    def test_performance_timing_all_keys(self):
        payload = _analysis(_many_rows(30), bootstrap_iterations=30, min_group_size=3)
        perf = payload["performance"]
        for key in PERFORMANCE_KEYS:
            assert key in perf
            assert isinstance(perf[key], (int, float))
            assert perf[key] >= 0
        assert perf["total_ms"] >= 0

    def test_json_serializable_via_jsonable_encoder(self):
        payload = _analysis(_many_rows(30), bootstrap_iterations=30, min_group_size=3)
        encoded = jsonable_encoder(payload)
        assert isinstance(encoded, dict)
        assert encoded["version"] == VERSION

    @patch(
        "app.services.cecchino.cecchino_draw_credibility_statistics.build_draw_credibility_all_rows",
    )
    def test_uses_shared_all_rows_mock(self, mock_all_rows):
        mock_all_rows.return_value = ([], {})
        db = MagicMock()
        build_draw_credibility_statistical_analysis(
            db,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            bootstrap_iterations=30,
            min_group_size=3,
        )
        mock_all_rows.assert_called_once()

    def test_empty_db_still_has_7_interactions(self):
        payload = _analysis([], bootstrap_iterations=30, min_group_size=3)
        assert payload["dataset_summary"]["primary"]["rows"] == 0
        interactions = payload["interaction_analysis"]
        assert len(interactions) == 7
        keys = [ix["interaction_key"] for ix in interactions]
        assert keys == EXPECTED_INTERACTION_KEYS
        assert isinstance(payload["candidate_patterns"], list)

    def test_dataset_summary_primary_rows(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=3)
        assert payload["dataset_summary"]["primary"]["rows"] >= 1
        assert payload["status"] == "ok"

    def test_feature_leaderboard_present(self):
        payload = _analysis(_many_rows(30), bootstrap_iterations=30, min_group_size=3)
        lb = payload["feature_leaderboard"]
        assert isinstance(lb, list)
        assert len(lb) > 0
        aucs = [x.get("discriminative_auc") or 0 for x in lb]
        assert aucs == sorted(aucs, reverse=True)


# ---------------------------------------------------------------------------
# Fase 1C.2 — matches_candidate_pattern
# ---------------------------------------------------------------------------


def _quantile_pattern(*, bin_index: int, col_dim: str = "prob_x_norm", **overrides) -> dict:
    boundaries = [30.0, 50.0, 70.0]
    bin_0 = bin_index - 1
    meta = bin_bounds_meta(bin_0, boundaries)
    base = {
        "row_dimension": "x_rank",
        "row_category": "2",
        "column_dimension": col_dim,
        "column_type": "quantile",
        "column_category": f"Q{bin_index}",
        "column_bin_index": bin_index,
        "column_boundaries": boundaries,
        "boundary_source": "primary",
        "description": f"x_rank=2 × {col_dim}=Q{bin_index}",
        **meta,
    }
    base.update(overrides)
    return base


class TestMatchesCandidatePattern:
    """Match strutturato: categorical / quantile via apply_quantile_boundaries (_assign_bins)."""

    def test_categorical_match(self):
        pattern = {
            "row_dimension": "dominant_sign_normalized",
            "row_category": "DRAW",
            "column_dimension": "conviction_class_candidate",
            "column_type": "categorical",
            "column_category": "alta",
            "description": "ignored",
        }
        row = {
            "dominant_sign_normalized": "DRAW",
            "conviction_class_candidate": "alta",
        }
        assert matches_candidate_pattern(row, pattern) is True

    def test_categorical_no_match(self):
        pattern = {
            "row_dimension": "dominant_sign_normalized",
            "row_category": "DRAW",
            "column_dimension": "conviction_class_candidate",
            "column_type": "categorical",
            "column_category": "alta",
        }
        row = {
            "dominant_sign_normalized": "DRAW",
            "conviction_class_candidate": "bassa",
        }
        assert matches_candidate_pattern(row, pattern) is False

    def test_quantile_first_bin(self):
        # boundaries [30,50,70]: bin0 = v < 30 → column_bin_index 1
        pattern = _quantile_pattern(bin_index=1)
        row = {"x_rank": "2", "prob_x_norm": 10.0}
        assert apply_quantile_boundaries([10.0], [30.0, 50.0, 70.0])[0] == 0
        assert matches_candidate_pattern(row, pattern) is True

    def test_quantile_middle_bin(self):
        # bin1 = [30, 50) → column_bin_index 2
        pattern = _quantile_pattern(bin_index=2)
        row = {"x_rank": "2", "prob_x_norm": 40.0}
        assert apply_quantile_boundaries([40.0], [30.0, 50.0, 70.0])[0] == 1
        assert matches_candidate_pattern(row, pattern) is True

    def test_quantile_last_bin(self):
        # bin3 = v >= 70 → column_bin_index 4
        pattern = _quantile_pattern(bin_index=4)
        row = {"x_rank": "2", "prob_x_norm": 80.0}
        assert apply_quantile_boundaries([80.0], [30.0, 50.0, 70.0])[0] == 3
        assert matches_candidate_pattern(row, pattern) is True

    def test_quantile_value_equals_lower_bound_middle(self):
        # _assign_bins: bin0 v<e0; else v<e_i → i; else last.
        # v=50: not <30, not <50, <70 → assigned bin 2 (0-based) = bin_index 3
        pattern = _quantile_pattern(bin_index=3)
        row = {"x_rank": "2", "prob_x_norm": 50.0}
        assert apply_quantile_boundaries([50.0], [30.0, 50.0, 70.0])[0] == 2
        assert matches_candidate_pattern(row, pattern) is True

    def test_quantile_bound_equality_documented(self):
        """Documenta uguaglianza sui bound di _assign_bins: e0 esclusivo a sinistra.

        Con boundaries [30,50,70]:
        - v < 30 → bin 0
        - 30 <= v < 50 → bin 1  (v==30 entra nel bin successivo a bin0)
        - 50 <= v < 70 → bin 2
        - v >= 70 → bin 3
        """
        edges = [30.0, 50.0, 70.0]
        labels = apply_quantile_boundaries([29.9, 30.0, 49.9, 50.0, 69.9, 70.0], edges)
        assert labels == [0, 1, 1, 2, 2, 3]

        # v=30 → bin 1 zero-based = column_bin_index 2
        pattern = _quantile_pattern(bin_index=2)
        assert matches_candidate_pattern({"x_rank": "2", "prob_x_norm": 30.0}, pattern) is True
        assert matches_candidate_pattern({"x_rank": "2", "prob_x_norm": 29.9}, pattern) is False

        meta = bin_bounds_meta(1, edges)
        assert meta["column_lower_bound"] == 30.0
        assert meta["column_lower_inclusive"] is True
        assert meta["column_upper_bound"] == 50.0
        assert meta["column_upper_inclusive"] is False

    def test_missing_value_false(self):
        pattern = _quantile_pattern(bin_index=1)
        row = {"x_rank": "2", "prob_x_norm": None}
        assert matches_candidate_pattern(row, pattern) is False

    def test_incomplete_metadata_false(self):
        pattern = {
            "row_dimension": "x_rank",
            "row_category": "2",
            "column_dimension": "prob_x_norm",
            "column_type": "quantile",
            "column_category": "Q1",
            # manca column_bin_index / column_boundaries
        }
        row = {"x_rank": "2", "prob_x_norm": 10.0}
        assert matches_candidate_pattern(row, pattern) is False

        incomplete_cat = {
            "row_dimension": "x_rank",
            "row_category": "2",
            "column_dimension": "conviction_class_candidate",
            "column_type": "categorical",
            # manca column_category
        }
        assert matches_candidate_pattern(
            {"x_rank": "2", "conviction_class_candidate": "alta"},
            incomplete_cat,
        ) is False

    def test_description_change_does_not_affect_match(self):
        pattern_a = _quantile_pattern(bin_index=1, description="alpha")
        pattern_b = {**pattern_a, "description": "beta completamente diversa"}
        row = {"x_rank": "2", "prob_x_norm": 10.0}
        assert matches_candidate_pattern(row, pattern_a) is True
        assert matches_candidate_pattern(row, pattern_b) is True
        assert matches_candidate_pattern(row, pattern_a) == matches_candidate_pattern(row, pattern_b)


# ---------------------------------------------------------------------------
# Fase 1C.2 — celle soppresse e pattern
# ---------------------------------------------------------------------------


class TestSuppressedCells:
    def test_suppressed_cell_clears_rates_keeps_counts(self):
        # min_group_size alto → molte celle unreliable/suppressed
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=50)
        suppressed = []
        for ix in payload["interaction_analysis"]:
            for cell in ix.get("primary_cells") or []:
                if cell.get("suppressed"):
                    suppressed.append(cell)
        assert suppressed, "attesa almeno una cella soppressa con min_group_size alto"
        cell = suppressed[0]
        assert cell["draw_rate_pct"] is None
        assert cell["lift_vs_baseline_pp"] is None
        assert cell["wilson_ci_95"] is None
        assert isinstance(cell["count"], int)
        assert isinstance(cell["draws"], int)
        assert cell["count"] >= 0
        assert cell["draws"] >= 0

    def test_suppressed_cells_not_in_candidate_patterns(self):
        payload = _analysis(_many_rows(36), bootstrap_iterations=30, min_group_size=5)
        suppressed_keys = set()
        for ix in payload["interaction_analysis"]:
            for cell in ix.get("primary_cells") or []:
                if cell.get("suppressed"):
                    suppressed_keys.add(
                        (
                            ix["interaction_key"],
                            cell["row_category"],
                            cell["column_category"],
                        )
                    )
        assert suppressed_keys, "attese celle soppresse nel campione di test"
        for pat in payload["candidate_patterns"]:
            key = (
                pat["interaction_key"],
                pat["row_category"],
                pat["column_category"],
            )
            assert key not in suppressed_keys


# ---------------------------------------------------------------------------
# Fase 1C.2 — ROI pattern con boundary primary
# ---------------------------------------------------------------------------


class TestRoiPatternPrimaryBoundaries:
    def test_primary_boundaries_and_no_recompute(self):
        assert VERSION == "cecchino_draw_credibility_statistics_v1_2"
        payload = _analysis(_many_rows(48), bootstrap_iterations=30, min_group_size=3)
        assert payload["version"] == VERSION

        for pat in payload["candidate_patterns"]:
            if pat.get("column_type") == "quantile":
                assert pat.get("boundary_source") == "primary"

        checks = payload["pattern_consistency_checks"]
        assert checks["market_patterns_using_recomputed_boundaries"] == 0

        for entry in payload["pattern_market_matching"]:
            assert entry.get("using_recomputed_boundaries") is False

        for group in payload["market_analysis"]["roi_breakdown"]:
            gk = group.get("group_key") or ""
            if gk.startswith("pattern__"):
                assert group.get("boundary_source") == "primary"


# ---------------------------------------------------------------------------
# Fase 1C.2 — semantica leghe paese+campionato
# ---------------------------------------------------------------------------


class TestLeagueSemantics:
    def test_distinct_names_vs_country_league_pairs(self):
        # Stesso league_name in due paesi + due leghe nello stesso paese
        rows = [
            _row(
                id=1,
                provider_fixture_id=1,
                local_fixture_id=1,
                country_name="England",
                league_name="Premier League",
                competition_id=39,
            ),
            _row(
                id=2,
                provider_fixture_id=2,
                local_fixture_id=2,
                country_name="Wales",
                league_name="Premier League",
                competition_id=110,
            ),
            _row(
                id=3,
                provider_fixture_id=3,
                local_fixture_id=3,
                country_name="England",
                league_name="Championship",
                competition_id=40,
            ),
            _row(
                id=4,
                provider_fixture_id=4,
                local_fixture_id=4,
                country_name="England",
                league_name="League One",
                competition_id=41,
            ),
        ]
        # Replica per volume minimo analitico
        expanded = []
        for i in range(12):
            base = rows[i % len(rows)]
            expanded.append(
                _row(
                    id=100 + i,
                    provider_fixture_id=9200 + i,
                    local_fixture_id=700 + i,
                    country_name=base.country_name,
                    league_name=base.league_name,
                    competition_id=base.competition_id,
                    score_fulltime_home=1 if i % 3 == 0 else 2,
                    score_fulltime_away=1 if i % 3 == 0 else 0,
                    goals_home=1 if i % 3 == 0 else 2,
                    goals_away=1 if i % 3 == 0 else 0,
                )
            )
        payload = _analysis(expanded, bootstrap_iterations=20, min_group_size=2)
        primary = payload["dataset_summary"]["primary"]
        # "Premier League" condiviso → meno nomi distinti delle coppie paese+lega
        assert primary["distinct_league_names_count"] < primary["distinct_country_league_pairs_count"]

        league = payload["league_stability"]
        pairs = {
            (lg["country_name"], lg["league_name"])
            for lg in league["leagues"]
            if not lg.get("is_others")
        }
        assert ("England", "Premier League") in pairs
        assert ("Wales", "Premier League") in pairs
        assert league["distinct_country_league_pairs_count"] == primary["distinct_country_league_pairs_count"]
        # Raggruppamento per (country, league): due voci "Premier League" distinte
        premier = [
            lg for lg in league["leagues"]
            if lg.get("league_name") == "Premier League" and not lg.get("is_others")
        ]
        assert len(premier) == 2
        assert {lg["country_name"] for lg in premier} == {"England", "Wales"}
