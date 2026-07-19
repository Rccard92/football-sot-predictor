"""Test Fase 5 — validazione prospettica Acquistabilità."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.cecchino_purchasability_evaluation import (
    EVAL_LOST,
    EVAL_PENDING,
    EVAL_WON,
    SOURCE_LEGACY_DERIVED,
    SOURCE_PROSPECTIVE,
    CecchinoPurchasabilityEvaluation,
)
from app.schemas.cecchino_purchasability_preview import (
    ACTIVE_PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_CANDIDATE_VERSION,
    PURCHASABILITY_FEATURE_V1_1_VERSION,
    PURCHASABILITY_FEATURE_VERSION,
    PURCHASABILITY_SNAPSHOT_VERSION,
)
from app.services.cecchino.cecchino_purchasability_features import (
    build_purchasability_features_for_panel,
)
from app.services.cecchino.cecchino_purchasability_validation import (
    PURCHASABILITY_VALIDATION_VERSION,
    compute_profit_units,
    evaluate_purchasability_validation_for_fixture,
    score_band_for,
    sync_purchasability_validation_for_fixture,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    PURCHASABILITY_PROMOTION_POLICY_VERSION,
    _metrics_block,
    _settled_rows,
    _signed_residual,
    build_purchasability_promotion_readiness,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
)


def _full_row(market_key: str, *, qb=2.0, qc=1.9, pb=0.5, pc=0.52, **kw) -> dict:
    base = {
        "market_key": market_key,
        "quota_book": qb,
        "quota_cecchino": qc,
        "prob_book": pb,
        "prob_cecchino": pc,
        "vantaggio_prob": pc - pb,
        "edge_pct": (qb / qc - 1) * 100 if qc else None,
        "score_acquisto": pc * ((qb / qc - 1) * 100) / 100 if qc else None,
        "rating": 72,
        "rating_label": "Buona",
        "status": "ok",
        "book_source": "betfair",
        "cecchino_source": "model",
    }
    base.update(kw)
    return base


def test_feature_version_active_is_v1_1():
    assert PURCHASABILITY_FEATURE_VERSION == PURCHASABILITY_FEATURE_V1_1_VERSION
    assert ACTIVE_PURCHASABILITY_FEATURE_VERSION.endswith("v1_1")


@pytest.mark.parametrize(
    "market_key",
    [SEL_DRAW_PT, SEL_OVER_1_5, SEL_UNDER_3_5, SEL_OVER_PT_0_5],
)
def test_unsupported_markets_no_favourite_ft_context(market_key):
    rows = [_full_row(market_key, qb=1.8, qc=1.7, pb=0.55, pc=0.58)]
    # add 1x2 so favourite would historically leak
    rows.extend(
        [
            _full_row(SEL_HOME, qb=2.1, qc=2.0, pb=0.47, pc=0.48),
            _full_row(SEL_DRAW, qb=3.4, qc=3.2, pb=0.29, pc=0.30),
            _full_row("AWAY", qb=3.5, qc=3.4, pb=0.28, pc=0.22),
        ]
    )
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2026-07-20T18:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-07-20T12:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
    )
    item = next(i for i in batch["items"] if i["market_key"] == market_key)
    p2 = item["phase_2_quality"]
    assert p2["favourite_alignment"] == "unavailable"
    assert p2["favourite_context_basis"] is None
    assert p2["book_favourite"] is None
    assert p2["model_favourite"] is None
    assert batch["feature_version"] == PURCHASABILITY_FEATURE_V1_1_VERSION


def test_supported_market_still_has_favourite_when_applicable():
    rows = [
        _full_row(SEL_HOME, qb=2.1, qc=2.0, pb=0.47, pc=0.48),
        _full_row(SEL_DRAW, qb=3.4, qc=3.2, pb=0.29, pc=0.30),
        _full_row("AWAY", qb=3.5, qc=3.4, pb=0.28, pc=0.22),
    ]
    batch = build_purchasability_features_for_panel(
        kpi_panel={"rows": rows},
        fixture_meta={"today_fixture_id": 1, "kickoff": "2026-07-20T18:00:00+00:00"},
        snapshot_info={
            "snapshot_at": "2026-07-20T12:00:00+00:00",
            "snapshot_timestamp_verified": True,
        },
    )
    home = next(i for i in batch["items"] if i["market_key"] == SEL_HOME)
    assert home["phase_2_quality"]["favourite_alignment"] in (
        "aligned",
        "disagree",
        "partial",
        "unavailable",
    )
    # supported path may populate favourite (not forced null stub)
    assert "favourite_alignment" in home["phase_2_quality"]


def test_score_bands_separate_zero():
    assert score_band_for(0) == "ZERO"
    assert score_band_for(15) == "1-19"
    assert score_band_for(100) == "80-100"


def test_profit_units_stake_one():
    assert compute_profit_units(EVAL_WON, Decimal("2.5")) == Decimal("1.5")
    assert compute_profit_units(EVAL_LOST, Decimal("2.5")) == Decimal("-1")
    assert compute_profit_units(EVAL_PENDING, Decimal("2.5")) is None


def _preview_snapshot(*, score=40, market=SEL_HOME):
    return {
        "snapshot_version": PURCHASABILITY_SNAPSHOT_VERSION,
        "candidate_version": PURCHASABILITY_CANDIDATE_VERSION,
        "candidate_name": "balanced_geometric_v1_1",
        "feature_version": PURCHASABILITY_FEATURE_V1_1_VERSION,
        "source_snapshot_at": "2026-07-19T10:00:00+00:00",
        "source_snapshot_verified": True,
        "source_snapshot_before_kickoff": True,
        "full_candidate_payload_sha256": "abc123",
        "contains_settlement_fields": False,
        "contains_result_fields": False,
        "signals_integration": False,
        "items": [
            {
                "market_key": market,
                "selection": market,
                "status": "available",
                "calculation_quality": "full",
                "score": score,
                "raw_score": float(score),
                "class": "Media",
                "phase_1_score": 50.0,
                "phase_2_score": 30.0,
                "reading": "test",
            }
        ],
    }


def test_sync_creates_promotion_eligible_row():
    kick = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id=42,
        local_fixture_id=1,
        provider_fixture_id=100,
        competition_id=7,
        scan_date=date(2026, 7, 19),
        kickoff=kick,
        country_name="IT",
        league_name="Serie A",
        home_team_name="A",
        away_team_name="B",
        cecchino_output_json={"purchasability_preview": _preview_snapshot()},
        kpi_panel_json={
            "odds_meta": {"odds_fetched_at": "2026-07-19T10:00:00+00:00"},
            "rows": [
                _full_row(SEL_HOME),
                _full_row(SEL_DRAW, qb=3.4, qc=3.2),
                _full_row("AWAY", qb=3.5, qc=3.4),
            ],
        },
    )
    added: list[CecchinoPurchasabilityEvaluation] = []
    db = MagicMock()
    db.get.return_value = row
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.add.side_effect = lambda obj: added.append(obj)

    result = sync_purchasability_validation_for_fixture(db, 42)
    assert result["synced"] == 1
    assert len(added) == 1
    ev = added[0]
    assert ev.promotion_eligible is True
    assert ev.source_cohort == SOURCE_PROSPECTIVE
    assert ev.purchasability_score == 40
    assert ev.market_key == SEL_HOME
    assert ev.evaluation_status == EVAL_PENDING


def test_sync_score_zero_included():
    kick = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id=43,
        local_fixture_id=1,
        provider_fixture_id=100,
        competition_id=7,
        scan_date=date(2026, 7, 19),
        kickoff=kick,
        country_name="IT",
        league_name="Serie A",
        home_team_name="A",
        away_team_name="B",
        cecchino_output_json={"purchasability_preview": _preview_snapshot(score=0)},
        kpi_panel_json={
            "odds_meta": {"odds_fetched_at": "2026-07-19T10:00:00+00:00"},
            "rows": [_full_row(SEL_HOME)],
        },
    )
    added: list = []
    db = MagicMock()
    db.get.return_value = row
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.add.side_effect = lambda obj: added.append(obj)
    result = sync_purchasability_validation_for_fixture(db, 43)
    assert result["synced"] == 1
    assert added[0].purchasability_score == 0


def test_sync_timestamp_mismatch_not_promotion_eligible():
    kick = datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id=44,
        local_fixture_id=1,
        provider_fixture_id=100,
        competition_id=7,
        scan_date=date(2026, 7, 19),
        kickoff=kick,
        country_name="IT",
        league_name="Serie A",
        home_team_name="A",
        away_team_name="B",
        cecchino_output_json={"purchasability_preview": _preview_snapshot()},
        kpi_panel_json={
            "odds_meta": {"odds_fetched_at": "2026-07-19T12:00:00+00:00"},
            "rows": [_full_row(SEL_HOME)],
        },
    )
    added: list = []
    db = MagicMock()
    db.get.return_value = row
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    db.add.side_effect = lambda obj: added.append(obj)
    sync_purchasability_validation_for_fixture(db, 44)
    assert added[0].promotion_eligible is False
    assert added[0].source_cohort == SOURCE_LEGACY_DERIVED


def test_evaluate_settlement_won_lost():
    row = SimpleNamespace(
        id=50,
        score_halftime_home=0,
        score_halftime_away=0,
        score_fulltime_home=2,
        score_fulltime_away=1,
        match_display_status="FT",
        fixture_status="FT",
    )
    ev_home = CecchinoPurchasabilityEvaluation(
        today_fixture_id=50,
        source_cohort=SOURCE_PROSPECTIVE,
        candidate_version=PURCHASABILITY_CANDIDATE_VERSION,
        market_key=SEL_HOME,
        quota_book=Decimal("2.00"),
        evaluation_status=EVAL_PENDING,
        promotion_eligible=True,
        is_current=True,
        stake_units=Decimal("1"),
    )
    ev_under = CecchinoPurchasabilityEvaluation(
        today_fixture_id=50,
        source_cohort=SOURCE_PROSPECTIVE,
        candidate_version=PURCHASABILITY_CANDIDATE_VERSION,
        market_key=SEL_UNDER_2_5,
        quota_book=Decimal("1.90"),
        evaluation_status=EVAL_PENDING,
        promotion_eligible=True,
        is_current=True,
        stake_units=Decimal("1"),
    )
    db = MagicMock()
    db.get.return_value = row
    db.scalars.return_value.all.return_value = [ev_home, ev_under]
    counts = evaluate_purchasability_validation_for_fixture(db, 50)
    assert counts["evaluated"] == 2
    assert ev_home.evaluation_status == EVAL_WON
    assert ev_home.profit_units == Decimal("1.0000")
    assert ev_under.evaluation_status == EVAL_LOST
    assert ev_under.profit_units == Decimal("-1")


def test_signed_residual_and_metrics():
    won = CecchinoPurchasabilityEvaluation(
        today_fixture_id=1,
        source_cohort=SOURCE_PROSPECTIVE,
        candidate_version=PURCHASABILITY_CANDIDATE_VERSION,
        market_key=SEL_HOME,
        purchasability_score=80,
        quota_book=Decimal("2.0"),
        fair_book_probability=Decimal("0.45"),
        evaluation_status=EVAL_WON,
        profit_units=Decimal("1"),
        promotion_eligible=True,
        snapshot_timestamp_verified=True,
        snapshot_before_kickoff=True,
        is_current=True,
        stake_units=Decimal("1"),
    )
    lost = CecchinoPurchasabilityEvaluation(
        today_fixture_id=2,
        source_cohort=SOURCE_PROSPECTIVE,
        candidate_version=PURCHASABILITY_CANDIDATE_VERSION,
        market_key=SEL_HOME,
        purchasability_score=10,
        quota_book=Decimal("2.0"),
        fair_book_probability=Decimal("0.45"),
        evaluation_status=EVAL_LOST,
        profit_units=Decimal("-1"),
        promotion_eligible=True,
        snapshot_timestamp_verified=True,
        snapshot_before_kickoff=True,
        is_current=True,
        stake_units=Decimal("1"),
    )
    assert abs(_signed_residual(won) - 0.55) < 1e-9
    assert abs(_signed_residual(lost) - (-0.45)) < 1e-9
    settled = _settled_rows([won, lost])
    assert len(settled) == 2
    m = _metrics_block(settled)
    assert m["won"] == 1
    assert m["lost"] == 1
    assert m["win_rate"] == 0.5


def test_readiness_collecting_when_sample_small(monkeypatch):
    from app.services.cecchino import cecchino_purchasability_validation_aggregation as agg

    def fake_summary(db, **kwargs):
        return {
            "metrics": {
                "fixtures": 10,
                "settled": 20,
                "zero_score_share": 0.1,
            },
            "temporal_span": {
                "span_days": 10,
                "prima_data_teorica_promozione": "2026-10-01",
            },
            "temporal_folds": [],
            "residual": {"spearman_score_vs_signed_book_residual": {}, "top_bottom": {}},
            "phase1_comparison": {},
            "by_market_family": [],
            "by_score_band": [],
            "by_month": [],
        }

    def fake_health(db, **kwargs):
        return {
            "snapshot_persistence_coverage": 0.5,
            "duplicate_validation_rows": 0,
        }

    monkeypatch.setattr(agg, "build_purchasability_validation_summary", fake_summary)
    monkeypatch.setattr(agg, "build_purchasability_validation_health", fake_health)
    out = build_purchasability_promotion_readiness(
        MagicMock(),
        date_from=date(2026, 1, 1),
        date_to=date(2026, 3, 1),
    )
    assert out["promotion_is_automatic"] is False
    assert out["eligible_for_manual_promotion"] is False
    assert out["status"] in (
        "data_quality_blocked",
        "insufficient_temporal_span",
        "insufficient_sample",
        "collecting_data",
        "performance_not_confirmed",
    )
    assert out["policy_version"] == PURCHASABILITY_PROMOTION_POLICY_VERSION
    assert PURCHASABILITY_VALIDATION_VERSION


def test_pipeline_helpers_exist():
    from app.services.cecchino import cecchino_today_service as today
    from app.services.cecchino import cecchino_recompute_service as recompute

    assert hasattr(today, "_maybe_sync_purchasability_validation_for_fixture")
    src = open(recompute.__file__, encoding="utf-8").read()
    assert "sync_purchasability_validation_for_fixture" in src
    today_src = open(today.__file__, encoding="utf-8").read()
    assert "evaluate_purchasability_validation_for_fixture" in today_src
