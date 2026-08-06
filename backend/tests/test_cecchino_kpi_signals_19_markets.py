"""Test estensione Segnali KPI: 19 mercati, settlement, Acquistabilità snapshot/filtri."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://user:pass@localhost:5432/test",
)

from app.models.cecchino_kpi_signal_activation import (
    KPI_EVAL_LOST,
    KPI_EVAL_WON,
    CecchinoKpiSignalActivation,
)
from app.services.cecchino.cecchino_kpi_signals import (
    HEATMAP_SELECTION_ROWS,
    KPI_MARKET_FOR_KEY,
    KPI_SELECTION_LABELS,
    KPI_SIGNAL_MARKET_DEFS,
    compute_profit_units,
    normalize_kpi_row,
)
from app.services.cecchino.cecchino_kpi_signals_aggregation import (
    validate_purchasability_filters,
)
from app.services.cecchino.cecchino_kpi_signals_purchasability import (
    PURCHASABILITY_STATUS_GATE_FAILED,
    PURCHASABILITY_STATUS_NON_CALCULABLE,
    PURCHASABILITY_STATUS_SCORE,
    PURCHASABILITY_STATUS_SCORE_PROVISIONAL,
    PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE,
    PURCHASABILITY_STATUS_UNSUPPORTED,
    activation_purchasability_fingerprint,
    apply_purchasability_to_activation,
    extract_purchasability_snapshots_for_selection,
    extract_v3_snapshot,
    extract_v31_snapshot,
    purchasability_fingerprint,
    serialize_purchasability_from_activation,
)
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_1X2_FH,
    MARKET_DC,
    MARKET_OU,
    MARKET_OU_FH,
    SEL_AWAY_PT,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_HOME_PT,
    SEL_OVER_3_5,
    SEL_UNDER_1_5,
    SEL_UNDER_PT_0_5,
)
from app.services.cecchino.cecchino_signal_evaluation import (
    PT_SELECTION_KEYS,
    evaluate_market_selection,
)


def _kpi_row(**kwargs):
    base = {
        "market_key": "HOME",
        "segno": "1",
        "label": "1",
        "quota_book": 2.0,
        "quota_cecchino": 1.8,
        "rating": 75,
        "rating_label": "Premium",
    }
    base.update(kwargs)
    return base


def _ft(home: int, away: int, ht_home: int | None = 0, ht_away: int | None = 0):
    return {
        "fulltime": {"home": home, "away": away},
        "halftime": {"home": ht_home, "away": ht_away},
    }


def _ht(home: int | None, away: int | None):
    return {
        "fulltime": {"home": None, "away": None},
        "halftime": {"home": home, "away": away},
    }


# --- Mercati canonici ---


def test_exactly_19_market_definitions():
    assert len(KPI_SIGNAL_MARKET_DEFS) == 19
    assert len(KPI_MARKET_FOR_KEY) == 19
    assert len(KPI_SELECTION_LABELS) == 19
    assert len(HEATMAP_SELECTION_ROWS) == 19


def test_canonical_order_and_labels():
    expected = [
        (SEL_HOME, "1", MARKET_1X2),
        ("DRAW", "X", MARKET_1X2),
        ("AWAY", "2", MARKET_1X2),
        (SEL_HOME_PT, "1 PT", MARKET_1X2_FH),
        (SEL_DRAW_PT, "X PT", MARKET_1X2_FH),
        (SEL_AWAY_PT, "2 PT", MARKET_1X2_FH),
        ("ONE_X", "1X", MARKET_DC),
        ("X_TWO", "X2", MARKET_DC),
        ("ONE_TWO", "12", MARKET_DC),
        ("OVER_1_5", "Over 1.5", MARKET_OU),
        (SEL_UNDER_1_5, "Under 1.5", MARKET_OU),
        ("OVER_2_5", "Over 2.5", MARKET_OU),
        ("UNDER_2_5", "Under 2.5", MARKET_OU),
        (SEL_OVER_3_5, "Over 3.5", MARKET_OU),
        ("UNDER_3_5", "Under 3.5", MARKET_OU),
        ("OVER_PT_0_5", "Over PT 0.5", MARKET_OU_FH),
        (SEL_UNDER_PT_0_5, "Under PT 0.5", MARKET_OU_FH),
        ("OVER_PT_1_5", "Over PT 1.5", MARKET_OU_FH),
        ("UNDER_PT_1_5", "Under PT 1.5", MARKET_OU_FH),
    ]
    for idx, (key, label, market) in enumerate(expected):
        d = KPI_SIGNAL_MARKET_DEFS[idx]
        assert d["selection_key"] == key
        assert d["selection_label"] == label
        assert d["normalized_market"] == market
        assert d["display_order"] == idx + 1


def test_new_markets_normalized():
    for key, label in [
        (SEL_HOME_PT, "1 PT"),
        (SEL_DRAW_PT, "X PT"),
        (SEL_AWAY_PT, "2 PT"),
        (SEL_UNDER_1_5, "Under 1.5"),
        (SEL_OVER_3_5, "Over 3.5"),
        (SEL_UNDER_PT_0_5, "Under PT 0.5"),
    ]:
        row = normalize_kpi_row(_kpi_row(market_key=key, segno=label, label=label, rating=60))
        assert row is not None
        assert row["selection_key"] == key
        assert row["selection_label"] == label


def test_previous_13_markets_unchanged_families():
    assert KPI_MARKET_FOR_KEY[SEL_HOME] == MARKET_1X2
    assert KPI_MARKET_FOR_KEY["ONE_X"] == MARKET_DC
    assert KPI_MARKET_FOR_KEY["OVER_1_5"] == MARKET_OU
    assert KPI_MARKET_FOR_KEY["OVER_PT_0_5"] == MARKET_OU_FH


def test_rating_below_50_still_excluded():
    assert normalize_kpi_row(_kpi_row(market_key=SEL_HOME_PT, segno="1 PT", rating=49)) is None


def test_missing_book_still_excluded():
    assert normalize_kpi_row(_kpi_row(market_key=SEL_UNDER_1_5, segno="Under 1.5", quota_book=None)) is None


def test_missing_purchasability_does_not_block_candidate():
    row = normalize_kpi_row(_kpi_row(rating=70, score_acquisto=None))
    assert row is not None


# --- Settlement ---


@pytest.mark.parametrize(
    "ht,expected",
    [((1, 0), KPI_EVAL_WON), ((0, 1), KPI_EVAL_LOST), ((0, 0), KPI_EVAL_LOST)],
)
def test_settlement_home_pt(ht, expected):
    assert evaluate_market_selection(SEL_HOME_PT, _ht(*ht))["evaluation_status"] == expected


@pytest.mark.parametrize(
    "ht,expected",
    [((0, 0), KPI_EVAL_WON), ((1, 1), KPI_EVAL_WON), ((1, 0), KPI_EVAL_LOST)],
)
def test_settlement_draw_pt(ht, expected):
    assert evaluate_market_selection(SEL_DRAW_PT, _ht(*ht))["evaluation_status"] == expected


@pytest.mark.parametrize(
    "ht,expected",
    [((0, 1), KPI_EVAL_WON), ((1, 0), KPI_EVAL_LOST), ((0, 0), KPI_EVAL_LOST)],
)
def test_settlement_away_pt(ht, expected):
    assert evaluate_market_selection(SEL_AWAY_PT, _ht(*ht))["evaluation_status"] == expected


@pytest.mark.parametrize(
    "ft,expected",
    [((0, 0), KPI_EVAL_WON), ((1, 0), KPI_EVAL_WON), ((0, 1), KPI_EVAL_WON), ((1, 1), KPI_EVAL_LOST), ((2, 0), KPI_EVAL_LOST)],
)
def test_settlement_under_1_5(ft, expected):
    assert evaluate_market_selection(SEL_UNDER_1_5, _ft(*ft))["evaluation_status"] == expected


@pytest.mark.parametrize(
    "ft,expected",
    [((2, 2), KPI_EVAL_WON), ((4, 0), KPI_EVAL_WON), ((2, 1), KPI_EVAL_LOST), ((0, 0), KPI_EVAL_LOST)],
)
def test_settlement_over_3_5(ft, expected):
    assert evaluate_market_selection(SEL_OVER_3_5, _ft(*ft))["evaluation_status"] == expected


@pytest.mark.parametrize(
    "ht,expected",
    [((0, 0), KPI_EVAL_WON), ((1, 0), KPI_EVAL_LOST), ((0, 1), KPI_EVAL_LOST)],
)
def test_settlement_under_pt_0_5(ht, expected):
    assert evaluate_market_selection(SEL_UNDER_PT_0_5, _ht(*ht))["evaluation_status"] == expected


@pytest.mark.parametrize("key", sorted(PT_SELECTION_KEYS))
def test_pt_markets_result_missing_without_ht(key):
    result = evaluate_market_selection(key, _ht(None, None))
    assert result["evaluation_status"] == "result_missing"


def test_profit_unit_rules_unchanged():
    assert compute_profit_units(KPI_EVAL_WON, Decimal("2.4")) == Decimal("1.4")
    assert compute_profit_units(KPI_EVAL_LOST, Decimal("2.4")) == Decimal("-1")


# --- Acquistabilità adapter ---


def _v3_snapshot(items: list[dict], **meta):
    return {
        "purchasability_preview_v3": {
            "formula_version": "cecchino_purchasability_v3_fixed_discount_v1",
            "candidate_version": "cecchino_purchasability_v3_candidate_1",
            "source_snapshot_at": "2026-08-01T10:00:00+00:00",
            "generated_at": "2026-08-01T10:00:00+00:00",
            "items": items,
            **meta,
        }
    }


def _v31_snapshot(items: list[dict], **meta):
    return {
        "purchasability_preview_v31": {
            "formula_version": "cecchino_purchasability_v31_fixed_discount_empirical_v2",
            "candidate_version": "cecchino_purchasability_v31_candidate_2",
            "formula_config_version": "fixed_discount_v31_empirical_v2",
            "audit_version": "cecchino_purchasability_v31_audit_v2",
            "source_snapshot_at": "2026-08-01T10:00:00+00:00",
            "generated_at": "2026-08-01T10:05:00+00:00",
            "items": items,
            **meta,
        }
    }


def test_extract_v3_score_available():
    out = _v3_snapshot(
        [{"market_key": "HOME", "status": "available", "score": 72, "class": "Alta", "calculation_quality": "full"}]
    )
    snap = extract_v3_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["status"] == PURCHASABILITY_STATUS_SCORE
    assert snap["score"] == 72
    assert snap["class_key"] == "high"
    assert snap["formula_version"]


def test_extract_v3_gate_failed():
    out = _v3_snapshot(
        [
            {
                "market_key": "HOME",
                "status": "not_applicable",
                "score": None,
                "gate_status": "failed_non_positive_edge",
                "reason_codes": ["gate_failed"],
            }
        ]
    )
    snap = extract_v3_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["status"] == PURCHASABILITY_STATUS_GATE_FAILED
    assert snap["score"] is None


def test_extract_v3_unsupported_market():
    snap = extract_v3_snapshot(cecchino_output_json=_v3_snapshot([]), selection_key=SEL_HOME_PT)
    assert snap["status"] == PURCHASABILITY_STATUS_UNSUPPORTED
    assert snap["score"] is None


def test_extract_v31_score_and_provisional():
    out = _v31_snapshot(
        [
            {
                "market_key": "HOME",
                "status": "score",
                "score": 80,
                "class": "Alta",
                "calculation_quality": "full",
                "historical": {"historical_evidence_quality": "definitive"},
                "execution_quote_real": True,
            },
            {
                "market_key": "DRAW",
                "status": "score_provisional",
                "score": 55,
                "class": "Media",
                "calculation_quality": "provisional",
                "historical": {"historical_evidence_quality": "provisional"},
            },
        ]
    )
    home = extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")
    draw = extract_v31_snapshot(cecchino_output_json=out, selection_key="DRAW")
    assert home["status"] == PURCHASABILITY_STATUS_SCORE
    assert home["historical_evidence_quality"] == "definitive"
    assert draw["status"] == PURCHASABILITY_STATUS_SCORE_PROVISIONAL


def test_extract_v31_gate_and_non_calculable():
    out = _v31_snapshot(
        [
            {"market_key": "HOME", "status": "gate_failed", "score": None},
            {"market_key": "DRAW", "status": "non_calculable", "score": None},
        ]
    )
    assert extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")["status"] == PURCHASABILITY_STATUS_GATE_FAILED
    assert extract_v31_snapshot(cecchino_output_json=out, selection_key="DRAW")["status"] == PURCHASABILITY_STATUS_NON_CALCULABLE


def test_snapshot_absent_and_score_zero_and_100():
    assert extract_v3_snapshot(cecchino_output_json=None, selection_key="HOME")["status"] == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE
    out0 = _v3_snapshot([{"market_key": "HOME", "status": "available", "score": 0, "class": "Molto Bassa"}])
    out100 = _v3_snapshot([{"market_key": "HOME", "status": "available", "score": 100, "class": "Molto Alta"}])
    assert extract_v3_snapshot(cecchino_output_json=out0, selection_key="HOME")["score"] == 0
    assert extract_v3_snapshot(cecchino_output_json=out100, selection_key="HOME")["score"] == 100
    assert extract_v3_snapshot(cecchino_output_json=out0, selection_key="HOME")["class_key"] == "very_low"
    assert extract_v3_snapshot(cecchino_output_json=out100, selection_key="HOME")["class_key"] == "very_high"


def test_x_pt_not_matched_to_x_ft():
    out = {
        **_v3_snapshot([{"market_key": "DRAW", "status": "available", "score": 40, "class": "Bassa"}]),
        **_v31_snapshot([{"market_key": "DRAW", "status": "score", "score": 40, "class": "Bassa"}]),
    }
    both = extract_purchasability_snapshots_for_selection(
        cecchino_output_json=out,
        selection_key=SEL_DRAW_PT,
        kpi_row={"segno": "X PT", "label": "X PT"},
    )
    assert both["v3"]["status"] == PURCHASABILITY_STATUS_UNSUPPORTED
    assert both["v31"]["status"] == PURCHASABILITY_STATUS_SNAPSHOT_UNAVAILABLE


def test_apply_purchasability_preserves_versions_and_timestamp():
    activation = CecchinoKpiSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 8, 1),
        kpi_row_key="HOME",
        selection_label="1",
        normalized_market=MARKET_1X2,
        selection_key=SEL_HOME,
        rating_score=70,
        rating_bucket="70-79",
        quota_book=Decimal("2.0"),
    )
    out = {
        **_v3_snapshot(
            [{"market_key": "HOME", "status": "available", "score": 61, "class": "Alta", "calculation_quality": "full"}]
        ),
        **_v31_snapshot(
            [
                {
                    "market_key": "HOME",
                    "status": "score_provisional",
                    "score": 58,
                    "class": "Media",
                    "calculation_quality": "provisional",
                    "historical": {"historical_evidence_quality": "provisional"},
                    "registry_status": "shadow_candidate",
                }
            ]
        ),
    }
    snaps = extract_purchasability_snapshots_for_selection(cecchino_output_json=out, selection_key="HOME")
    apply_purchasability_to_activation(activation, snaps)
    assert activation.purchasability_v3_formula_version
    assert activation.purchasability_v3_score == 61
    assert activation.purchasability_v31_status == PURCHASABILITY_STATUS_SCORE_PROVISIONAL
    assert activation.purchasability_v31_registry_status == "shadow_candidate"
    assert isinstance(activation.purchasability_v3_source_snapshot_at, datetime)


# --- registry_status V3.1 ---


def test_registry_status_from_item_level():
    out = _v31_snapshot(
        [
            {
                "market_key": "HOME",
                "status": "score",
                "score": 70,
                "class": "Alta",
                "registry_status": "shadow_candidate",
            }
        ]
    )
    snap = extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["registry_status"] == "shadow_candidate"


def test_registry_status_from_snapshot_top_level():
    out = _v31_snapshot(
        [{"market_key": "HOME", "status": "score", "score": 70, "class": "Alta"}],
        registry_status="validated_operational",
    )
    snap = extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["registry_status"] == "validated_operational"


def test_registry_status_item_precedes_snapshot():
    out = _v31_snapshot(
        [
            {
                "market_key": "HOME",
                "status": "score",
                "score": 70,
                "class": "Alta",
                "registry_status": "shadow_candidate",
            }
        ],
        registry_status="validated_operational",
    )
    snap = extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["registry_status"] == "shadow_candidate"


def test_registry_status_absent_is_none():
    out = _v31_snapshot([{"market_key": "HOME", "status": "score", "score": 70, "class": "Alta"}])
    snap = extract_v31_snapshot(cecchino_output_json=out, selection_key="HOME")
    assert snap["registry_status"] is None


def test_serialize_registry_status_and_legacy_null():
    activation = CecchinoKpiSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 8, 1),
        kpi_row_key="HOME",
        selection_label="1",
        normalized_market=MARKET_1X2,
        selection_key=SEL_HOME,
        rating_score=70,
        rating_bucket="70-79",
        quota_book=Decimal("2.0"),
        purchasability_v31_status=PURCHASABILITY_STATUS_SCORE,
        purchasability_v31_score=80.0,
        purchasability_v31_formula_version="cecchino_purchasability_v31_fixed_discount_empirical_v2",
        purchasability_v31_candidate_version="cecchino_purchasability_v31_candidate_2",
        purchasability_v31_registry_status="shadow_candidate",
    )
    payload = serialize_purchasability_from_activation(activation, version="v31")
    assert payload["registry_status"] == "shadow_candidate"
    assert payload["snapshot_available"] is True

    activation.purchasability_v31_registry_status = None
    payload_null = serialize_purchasability_from_activation(activation, version="v31")
    assert payload_null["registry_status"] is None
    assert payload_null["snapshot_available"] is True
    assert payload_null["status"] == PURCHASABILITY_STATUS_SCORE


def test_fingerprint_changes_only_when_registry_status_changes():
    base_v3 = {
        "status": PURCHASABILITY_STATUS_SCORE,
        "score": 70.0,
        "class_key": "high",
        "formula_version": "v3",
        "calculation_quality": "full",
        "source_snapshot_at": None,
        "reason_codes": [],
    }
    v31_a = {
        "status": PURCHASABILITY_STATUS_SCORE,
        "score": 80.0,
        "class_key": "high",
        "candidate_version": "c2",
        "formula_version": "v31",
        "registry_status": "shadow_candidate",
        "calculation_quality": "full",
        "historical_evidence_quality": "definitive",
        "source_snapshot_at": None,
        "execution_quote_real": True,
        "reason_codes": [],
    }
    v31_b = {**v31_a, "registry_status": "validated_operational"}
    fp_a = purchasability_fingerprint(base_v3, v31_a)
    fp_b = purchasability_fingerprint(base_v3, v31_b)
    assert fp_a != fp_b

    activation = CecchinoKpiSignalActivation(
        today_fixture_id=1,
        provider_fixture_id=1,
        scan_date=date(2026, 8, 1),
        kpi_row_key="HOME",
        selection_label="1",
        normalized_market=MARKET_1X2,
        selection_key=SEL_HOME,
        rating_score=70,
        rating_bucket="70-79",
        quota_book=Decimal("2.0"),
        purchasability_v31_status=PURCHASABILITY_STATUS_SCORE,
        purchasability_v31_score=80.0,
        purchasability_v31_class_key="high",
        purchasability_v31_candidate_version="c2",
        purchasability_v31_formula_version="v31",
        purchasability_v31_registry_status="shadow_candidate",
        purchasability_v31_calculation_quality="full",
        purchasability_v31_historical_evidence_quality="definitive",
        purchasability_v31_execution_quote_real=True,
        purchasability_v31_reason_codes_json=[],
        purchasability_v3_status=PURCHASABILITY_STATUS_SCORE,
        purchasability_v3_score=70.0,
        purchasability_v3_class_key="high",
        purchasability_v3_formula_version="v3",
        purchasability_v3_calculation_quality="full",
        purchasability_v3_reason_codes_json=[],
    )
    act_fp = activation_purchasability_fingerprint(activation)
    assert "shadow_candidate" in act_fp
    assert act_fp == fp_a


def test_sync_updates_when_only_registry_status_changes():
    from app.services.cecchino.cecchino_kpi_signals import sync_kpi_signals_for_fixture
    from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE

    db = MagicMock()
    existing = CecchinoKpiSignalActivation(
        today_fixture_id=10,
        provider_fixture_id=999,
        scan_date=date(2026, 8, 1),
        kpi_row_key="HOME",
        selection_label="1",
        normalized_market=MARKET_1X2,
        selection_key=SEL_HOME,
        rating_score=70,
        rating_bucket="70-79",
        rating_label="Premium",
        quota_book=Decimal("2.0"),
        stake_units=Decimal("1"),
        is_current=True,
        purchasability_v3_status=PURCHASABILITY_STATUS_SCORE,
        purchasability_v3_score=61.0,
        purchasability_v3_class_key="high",
        purchasability_v3_formula_version="cecchino_purchasability_v3_fixed_discount_v1",
        purchasability_v3_calculation_quality="full",
        purchasability_v3_reason_codes_json=[],
        purchasability_v31_status=PURCHASABILITY_STATUS_SCORE_PROVISIONAL,
        purchasability_v31_score=58.0,
        purchasability_v31_class_key="medium",
        purchasability_v31_candidate_version="cecchino_purchasability_v31_candidate_2",
        purchasability_v31_formula_version="cecchino_purchasability_v31_fixed_discount_empirical_v2",
        purchasability_v31_formula_config_version="fixed_discount_v31_empirical_v2",
        purchasability_v31_audit_version="cecchino_purchasability_v31_audit_v2",
        purchasability_v31_registry_status="shadow_candidate",
        purchasability_v31_calculation_quality="provisional",
        purchasability_v31_historical_evidence_quality="provisional",
        purchasability_v31_reason_codes_json=[],
    )
    row = MagicMock()
    row.id = 10
    row.provider_fixture_id = 999
    row.scan_date = date(2026, 8, 1)
    row.kickoff = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
    row.country_name = "Italy"
    row.league_name = "Serie A"
    row.home_team_name = "A"
    row.away_team_name = "B"
    row.eligibility_status = ELIGIBILITY_ELIGIBLE
    row.kpi_panel_json = {
        "version": "cecchino_kpi_v2_betfair",
        "rows": [
            {
                "market_key": "HOME",
                "segno": "1",
                "label": "1",
                "quota_book": 2.0,
                "rating": 70,
                "rating_label": "Premium",
            }
        ],
    }
    row.cecchino_output_json = {
        **_v3_snapshot(
            [
                {
                    "market_key": "HOME",
                    "status": "available",
                    "score": 61,
                    "class": "Alta",
                    "calculation_quality": "full",
                }
            ]
        ),
        **_v31_snapshot(
            [
                {
                    "market_key": "HOME",
                    "status": "score_provisional",
                    "score": 58,
                    "class": "Media",
                    "calculation_quality": "provisional",
                    "historical": {"historical_evidence_quality": "provisional"},
                    "registry_status": "validated_operational",
                }
            ]
        ),
    }
    row.score_fulltime_home = None
    row.score_fulltime_away = None
    row.score_halftime_home = None
    row.score_halftime_away = None
    row.match_display_status = "scheduled"
    row.fixture_status = "NS"
    db.get.return_value = row
    db.scalar.return_value = existing
    db.scalars.return_value.all.return_value = [existing]
    db.flush = MagicMock()

    result = sync_kpi_signals_for_fixture(db, 10)
    assert result["updated"] == 1
    assert existing.purchasability_v31_registry_status == "validated_operational"

    # Idempotente: stesso registry → fingerprint invariato, apply non deve cambiare di nuovo
    fp_before = activation_purchasability_fingerprint(existing)
    snaps = extract_purchasability_snapshots_for_selection(
        cecchino_output_json=row.cecchino_output_json,
        selection_key="HOME",
    )
    assert purchasability_fingerprint(snaps["v3"], snaps["v31"]) == fp_before


def test_backfill_reads_registry_from_persisted_snapshot_no_recompute():
    """Backfill = sync range: legge solo cecchino_output_json già persistito."""
    from app.services.cecchino.cecchino_kpi_signals import backfill_kpi_signals
    from unittest.mock import patch

    db = MagicMock()
    fixture_output = _v31_snapshot(
        [{"market_key": "HOME", "status": "score", "score": 70, "registry_status": "shadow_candidate"}]
    )
    assert "score_fulltime" not in str(fixture_output)

    with patch(
        "app.services.cecchino.cecchino_kpi_signals.sync_kpi_signals_for_range",
        return_value={
            "fixtures_seen": 1,
            "created": 0,
            "updated": 1,
            "deactivated": 0,
            "evaluated": 0,
            "errors": 0,
        },
    ) as sync_mock:
        result = backfill_kpi_signals(db, date_from=date(2026, 8, 1), date_to=date(2026, 8, 1))
    sync_mock.assert_called_once()
    assert result["updated"] == 1
    snap = extract_v31_snapshot(cecchino_output_json=fixture_output, selection_key="HOME")
    assert snap["registry_status"] == "shadow_candidate"


# --- Filtri ---


def test_filters_without_version_raise_422():
    with pytest.raises(HTTPException) as exc:
        validate_purchasability_filters(purchasability_status="score")
    assert exc.value.status_code == 422


def test_filters_min_max_validation():
    with pytest.raises(HTTPException) as exc:
        validate_purchasability_filters(
            purchasability_version="v3",
            purchasability_score_min=80,
            purchasability_score_max=60,
        )
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_purchasability_filters(purchasability_version="v3", purchasability_score_min=-1)
    with pytest.raises(HTTPException):
        validate_purchasability_filters(purchasability_version="v3", purchasability_score_max=101)


def test_filters_no_version_ok():
    validate_purchasability_filters()
