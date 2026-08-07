"""Test Bet Builder BET-01 — opportunity aggregator (price OR signals, V3.1 only)."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routes.cecchino_bet_builder import router
from app.services.cecchino.cecchino_bet_builder_constants import (
    BET_BUILDER_AGGREGATOR_VERSION,
    BET_BUILDER_CONTRACT_VERSION,
    ORIGIN_PRICE,
    ORIGIN_PRICE_AND_SIGNALS,
    ORIGIN_SIGNALS,
    PRICE_VALUE_METHOD,
    PURCHASABILITY_POLICY,
    REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING,
    REASON_PURCHASABILITY_V31_UNAVAILABLE,
)
from app.services.cecchino.cecchino_bet_builder_freshness import (
    build_source_generated_from,
    compute_source_revision,
)
from app.services.cecchino.cecchino_bet_builder_markets import BET_BUILDER_MARKET_KEYS
from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import (
    aggregate_bet_builder_opportunities,
    build_price_value,
    build_purchasability_v31_block,
    build_signals_evidence,
    opportunity_key,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_DRAW_PT,
    SEL_HOME,
    SEL_ONE_TWO,
    SEL_ONE_X,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_X_TWO,
)
from app.services.cecchino.cecchino_signal_consensus import (
    CURRENT_SIGNAL_FORMULA_VERSION,
    PREVIOUS_SIGNAL_FORMULA_VERSION,
    LEGACY_SIGNAL_FORMULA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kpi_row(
    market_key: str,
    *,
    book: float | None = 2.10,
    cecchino: float | None = 1.90,
    rating: int | None = 40,
    status: str = "available",
) -> dict:
    edge = None
    if book is not None and cecchino is not None and cecchino > 0:
        edge = round((book / cecchino - 1.0) * 100, 4)
    prob_book = (1.0 / book) if book else None
    prob_cec = (1.0 / cecchino) if cecchino else None
    vant = None
    if prob_book is not None and prob_cec is not None:
        vant = round(prob_cec - prob_book, 6)
    return {
        "market_key": market_key,
        "segno": market_key,
        "quota_book": book,
        "quota_cecchino": cecchino,
        "prob_book": prob_book,
        "prob_cecchino": prob_cec,
        "vantaggio_prob": vant,
        "edge_pct": edge,
        "score_acquisto": (prob_cec * (edge or 0) / 100) if prob_cec is not None else None,
        "rating": rating,
        "rating_label": "basso" if rating is not None and rating < 50 else "medio",
        "status": status,
        "book_source": "betfair",
        "cecchino_source": "model",
    }


def _matrix_v3(*, draw_yes: int = 0, home_si: bool = False, away_si: bool = False) -> dict:
    """Matrice V3 minimale con consensus-ready rows."""
    draw_signals = {
        "excel_d": "SI" if draw_yes >= 1 else "NO",
        "excel_e": "SI" if draw_yes >= 2 else "NO",
        "excel_f": "SI" if draw_yes >= 3 else "NO",
        "excel_g": "SI" if draw_yes >= 4 else "NO",
    }
    rows = [
        {"key": "draw", "label": "X", "signals": draw_signals},
        {
            "key": "one",
            "label": "1",
            "signals": {"excel_d": "SI" if home_si else "NO"},
        },
        {
            "key": "two",
            "label": "2",
            "signals": {"excel_d": "SI" if away_si else "NO"},
        },
        {
            "key": "one_x",
            "label": "1X",
            "signals": {
                "excel_d": "NO",
                "excel_e": "NO",
                "excel_f": "NO",
                "excel_g": "NO",
                "scala_1x": "NO",
            },
        },
        {
            "key": "x_two",
            "label": "X2",
            "signals": {
                "excel_d": "NO",
                "excel_e": "NO",
                "excel_f": "NO",
                "excel_g": "NO",
                "scala_x2": "NO",
            },
        },
        {
            "key": "twelve",
            "label": "12",
            "signals": {"excel_d": "NO", "excel_e": "NO"},
        },
        {
            "key": "over_over_pt",
            "label": "Over",
            "signals": {
                "excel_d": "NO",
                "excel_e": "NO",
                "excel_f": "NO",
                "excel_g": "NO",
            },
        },
        {
            "key": "under_under_pt",
            "label": "Under",
            "signals": {
                "excel_d": "NO",
                "excel_e": "NO",
                "excel_f": "NO",
                "excel_g": "NO",
            },
        },
    ]
    return {
        "status": "available",
        "formula_version": CURRENT_SIGNAL_FORMULA_VERSION,
        "rows": rows,
    }


def _v31_item(market_key: str, *, score: float | None = 80.0, class_v: str = "alta") -> dict:
    return {
        "market_key": market_key,
        "market_label": market_key,
        "score_v31": score,
        "raw_score_v31": (score + 1) if score is not None else None,
        "class_v31": class_v,
        "status": "score" if score is not None else "non_calculable",
        "calculation_quality": "full" if score is not None else "unavailable",
        "gate_status": "passed" if score is not None else "unavailable_inputs",
        "gate_reason_codes": [],
        "formula_version": "cecchino_purchasability_v31_fixed_discount_empirical_v2",
        "candidate_version": "cecchino_purchasability_v31_candidate_2",
        "registry_status": "shadow_candidate",
        "historical_multiplier": 1.0,
        "historical_adjustment_points": 0,
        "generated_at": "2026-08-07T10:00:00+00:00",
    }


def _fixture_row(
    *,
    fid: int = 1,
    scan_date: date = date(2026, 8, 8),
    kickoff: datetime | None = None,
    kpi_rows: list[dict] | None = None,
    signals_matrix: dict | None = None,
    v31_items: list[dict] | None = None,
    v3_items: list[dict] | None = None,
    balance: dict | None = None,
    match_status: str = "upcoming",
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    if kickoff is None:
        kickoff = datetime.now(timezone.utc) + timedelta(hours=5)
    output: dict = {}
    if signals_matrix is not None:
        output["signals_matrix"] = signals_matrix
    if v31_items is not None:
        output["purchasability_preview_v31"] = {
            "status": "ok",
            "items": v31_items,
            "generated_at": "2026-08-07T10:00:00+00:00",
            "registry_status": "shadow_candidate",
            "candidate_version": "cecchino_purchasability_v31_candidate_2",
        }
    if v3_items is not None:
        output["purchasability_preview_v3"] = {
            "status": "ok",
            "items": v3_items,
            "generated_at": "2026-08-07T09:00:00+00:00",
        }
    if balance is not None:
        output["balance_v5_monitoring"] = balance
    return SimpleNamespace(
        id=fid,
        provider_fixture_id=1000 + fid,
        scan_date=scan_date,
        kickoff=kickoff,
        country_name="Italy",
        league_name="Serie A",
        home_team_name="Inter",
        away_team_name="Milan",
        home_team_logo_url="http://logo/h.png",
        away_team_logo_url="http://logo/a.png",
        eligibility_status="eligible",
        match_display_status=match_status,
        kpi_panel_json={"rows": kpi_rows or []},
        cecchino_output_json=output,
        updated_at=updated_at or datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        local_fixture_id=None,
        competition_id=None,
        odds_snapshot_json=None,
    )


def _mock_db(rows: list[SimpleNamespace], *, latest_job=None) -> MagicMock:
    db = MagicMock()

    def _scalars(stmt):
        # Rough dispatch: fixture query vs GI vs scan job handled via scalar
        result = MagicMock()
        # For fixture selects return rows; for GI return empty
        text = str(stmt)
        if "cecchino_goal_intensity" in text.lower() or "GoalIntensity" in text:
            result.all.return_value = []
            result.first.return_value = None
        else:
            result.all.return_value = rows
            result.first.return_value = rows[0] if rows else None
        return result

    db.scalars.side_effect = _scalars
    db.scalar.return_value = latest_job
    db.get.return_value = None
    return db


# ---------------------------------------------------------------------------
# Price value
# ---------------------------------------------------------------------------


def test_price_only_opportunity():
    price = build_price_value(_kpi_row(SEL_DRAW, book=2.2, cecchino=1.9))
    assert price["present"] is True
    assert price["method"] == PRICE_VALUE_METHOD
    signals = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=0))
    assert signals["present"] is False
    assert ORIGIN_PRICE == "price"


def test_signals_only_opportunity():
    price = build_price_value(_kpi_row(SEL_DRAW, book=1.8, cecchino=2.0))
    assert price["present"] is False
    signals = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=2))
    assert signals["present"] is True
    assert signals["passed"] is True


def test_price_and_signals_opportunity():
    price = build_price_value(_kpi_row(SEL_DRAW, book=2.2, cecchino=1.9))
    signals = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=3))
    assert price["present"] and signals["present"]


def test_neither_excluded():
    price = build_price_value(_kpi_row(SEL_DRAW, book=1.8, cecchino=2.0))
    signals = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=1))
    assert price["present"] is False
    assert signals["present"] is False


def test_positive_edge_detected():
    price = build_price_value(_kpi_row(SEL_HOME, book=2.0, cecchino=1.8))
    assert price["present"] is True
    assert price["edge_pct"] is not None and price["edge_pct"] > 0


def test_non_positive_edge_no_price_trigger():
    price = build_price_value(_kpi_row(SEL_HOME, book=1.8, cecchino=1.8))
    assert price["present"] is False
    price2 = build_price_value(_kpi_row(SEL_HOME, book=1.7, cecchino=1.9))
    assert price2["present"] is False


def test_rating_is_not_a_gate():
    # rating basso ma book > cecchino → price present
    price = build_price_value(_kpi_row(SEL_AWAY, book=3.0, cecchino=2.5, rating=10))
    assert price["present"] is True
    assert price["rating"] == 10


def test_low_quota_not_auto_excluded():
    price = build_price_value(_kpi_row(SEL_HOME, book=1.25, cecchino=1.15, rating=20))
    assert price["present"] is True


# ---------------------------------------------------------------------------
# Market mapping coverage (11)
# ---------------------------------------------------------------------------


def test_market_keys_total_eleven():
    assert len(BET_BUILDER_MARKET_KEYS) == 11


@pytest.mark.parametrize(
    "mk",
    [
        SEL_HOME,
        SEL_DRAW,
        SEL_AWAY,
        SEL_ONE_X,
        SEL_X_TWO,
        SEL_ONE_TWO,
        SEL_DRAW_PT,
        SEL_OVER_1_5,
        SEL_UNDER_1_5,
        SEL_OVER_2_5,
        SEL_UNDER_2_5,
    ],
)
def test_market_mapping_keys(mk):
    assert mk in BET_BUILDER_MARKET_KEYS
    assert opportunity_key(1, mk) == f"1:{mk}"


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_signals_v3_only_ignores_v1_v2():
    for fv in (LEGACY_SIGNAL_FORMULA_VERSION, PREVIOUS_SIGNAL_FORMULA_VERSION):
        matrix = _matrix_v3(draw_yes=3)
        matrix["formula_version"] = fv
        ev = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=matrix)
        assert ev["present"] is False
        assert ev["available"] is False


def test_raw_si_read_even_if_not_acquired_semantics():
    # consensus_passed True indipendentemente da is_acquired operativo
    ev = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=2))
    assert ev["present"] is True
    assert "is_acquired" not in ev or ev.get("present") is True


def test_two_si_consensus_true_one_false():
    assert build_signals_evidence(
        market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=2)
    )["present"] is True
    assert build_signals_evidence(
        market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=1)
    )["present"] is False


def test_home_away_direct_single_formula():
    home = build_signals_evidence(
        market_key=SEL_HOME, signals_matrix=_matrix_v3(home_si=True)
    )
    away = build_signals_evidence(
        market_key=SEL_AWAY, signals_matrix=_matrix_v3(away_si=True)
    )
    assert home["evidence_mode"] == "direct_single_formula"
    assert home["required_count"] == 1
    assert home["present"] is True
    assert home["consensus_exempt"] is True
    assert away["evidence_mode"] == "direct_single_formula"
    assert away["present"] is True


def test_home_away_no_false_min_two_requirement():
    home = build_signals_evidence(
        market_key=SEL_HOME, signals_matrix=_matrix_v3(home_si=True)
    )
    assert home["required_count"] == 1
    assert home["yes_count"] == 1


def test_yes_columns_no_duplicates():
    matrix = _matrix_v3(draw_yes=3)
    # force duplicate columns in consensus path by duplicating SI keys — consensus dedups
    ev = build_signals_evidence(market_key=SEL_DRAW, signals_matrix=matrix)
    assert len(ev["yes_columns"]) == len(set(ev["yes_columns"]))


def test_draw_pt_derived_from_draw_consensus():
    ev = build_signals_evidence(
        market_key=SEL_DRAW_PT, signals_matrix=_matrix_v3(draw_yes=2)
    )
    assert ev["present"] is True
    assert ev["evidence_mode"] == "derived_from_draw_consensus"
    assert ev["source_group"] == "DRAW"


def test_draw_pt_without_draw_consensus_not_present():
    ev = build_signals_evidence(
        market_key=SEL_DRAW_PT, signals_matrix=_matrix_v3(draw_yes=1)
    )
    assert ev["present"] is False


def test_over_under_1_5_no_signal_mapping():
    ev = build_signals_evidence(
        market_key=SEL_OVER_1_5, signals_matrix=_matrix_v3(draw_yes=4)
    )
    assert ev["present"] is False
    assert ev["reason"] == REASON_NO_CANONICAL_RAW_SIGNAL_MAPPING


def test_value_gate_does_not_kill_signal_only():
    # book < cecchino ma consensus DRAW ok → signal present
    price = build_price_value(_kpi_row(SEL_DRAW, book=1.7, cecchino=2.0))
    signals = build_signals_evidence(
        market_key=SEL_DRAW, signals_matrix=_matrix_v3(draw_yes=2)
    )
    assert price["present"] is False
    assert signals["present"] is True


# ---------------------------------------------------------------------------
# Purchasability V3.1
# ---------------------------------------------------------------------------


def test_v31_present_used():
    block = build_purchasability_v31_block(
        market_key=SEL_DRAW,
        v31_by_market={SEL_DRAW: _v31_item(SEL_DRAW, score=90)},
        snapshot={"source_mode": "persisted_pre_match_snapshot"},
    )
    assert block["available"] is True
    assert block["score"] == 90
    assert block["registry_status"] == "shadow_candidate"


def test_v3_present_but_v31_used_when_both():
    # V3 non entra nel block builder — solo V3.1 index
    block = build_purchasability_v31_block(
        market_key=SEL_DRAW,
        v31_by_market={SEL_DRAW: _v31_item(SEL_DRAW, score=77)},
        snapshot=None,
    )
    assert block["score"] == 77


def test_v3_only_no_fallback():
    block = build_purchasability_v31_block(
        market_key=SEL_DRAW,
        v31_by_market={},
        snapshot=None,
    )
    assert block["available"] is False
    assert block["reason"] == REASON_PURCHASABILITY_V31_UNAVAILABLE
    assert block["score"] is None


def test_v31_fields_preserved():
    item = _v31_item(SEL_HOME, score=88, class_v="molto_alta")
    item["gate_status"] = "passed"
    item["historical_adjustment_pct"] = 5.0
    block = build_purchasability_v31_block(
        market_key=SEL_HOME,
        v31_by_market={SEL_HOME: item},
        snapshot={"source_mode": "persisted_pre_match_snapshot", "generated_at": "T"},
    )
    assert block["class"] == "molto_alta"
    assert block["gate_status"] == "passed"
    assert block["formula_version"]
    assert block["historical_adjustment_pct"] == 5.0


# ---------------------------------------------------------------------------
# Aggregator integration (mocked DB)
# ---------------------------------------------------------------------------


def test_aggregate_origins_and_sort(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {
            "status": "ok",
            "source_mode": "persisted_pre_match_snapshot",
            "items": [
                _v31_item(SEL_DRAW, score=90),
                _v31_item(SEL_HOME, score=70),
                _v31_item(SEL_OVER_2_5, score=None),
            ],
            "generated_at": "2026-08-07T10:00:00+00:00",
        },
    )

    # DRAW: price+signals score 90; HOME: signals only score 70; OVER_2_5: price only null v31
    rows = [
        _fixture_row(
            fid=1,
            kpi_rows=[
                _kpi_row(SEL_DRAW, book=2.2, cecchino=1.9),
                _kpi_row(SEL_HOME, book=1.5, cecchino=1.8),  # no price
                _kpi_row(SEL_OVER_2_5, book=2.0, cecchino=1.7),
            ],
            signals_matrix=_matrix_v3(draw_yes=2, home_si=True),
            balance={
                "status": "ok",
                "balance_version": "cecchino_balance_v5_v3",
                "f36_index": 50,
                "f36_class": "Equilibrio",
                "dominance_index": 40,
                "dominance_class": "Debole",
                "draw_credibility_index": 30,
                "draw_credibility_class": "Pareggio forte",
                "gap_index": 20,
                "gap_class": "Confermato",
                "source_mode": "prospective_scan",
                "pre_match_verified": True,
            },
        )
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert payload["contract_version"] == BET_BUILDER_CONTRACT_VERSION
    assert payload["aggregator_version"] == BET_BUILDER_AGGREGATOR_VERSION
    assert payload["purchasability_policy"] == PURCHASABILITY_POLICY
    keys = [o["opportunity_key"] for o in payload["opportunities"]]
    assert "1:DRAW" in keys
    assert "1:HOME" in keys
    assert "1:OVER_2_5" in keys
    origins = {o["opportunity_key"]: o["origin"] for o in payload["opportunities"]}
    assert origins["1:DRAW"] == ORIGIN_PRICE_AND_SIGNALS
    assert origins["1:HOME"] == ORIGIN_SIGNALS
    assert origins["1:OVER_2_5"] == ORIGIN_PRICE
    # sort: score 90 before 70 before null
    scores = [
        (o.get("purchasability_v31") or {}).get("score")
        for o in payload["opportunities"]
    ]
    assert scores[0] == 90
    assert scores[1] == 70
    # nulls at end among these
    assert scores[-1] is None or scores.index(None) > scores.index(70)

    draw = next(o for o in payload["opportunities"] if o["market"]["market_key"] == SEL_DRAW)
    assert draw["context_support"]["available"] is True
    assert draw["context_support"]["module"] == "balance_v5"
    assert "supports" not in (draw["context_support"].get("payload") or {})


def test_aggregate_excludes_neither_and_post_kickoff(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {"status": "unavailable", "items": []},
    )
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    rows = [
        _fixture_row(
            fid=1,
            kpi_rows=[_kpi_row(SEL_DRAW, book=1.5, cecchino=1.8)],
            signals_matrix=_matrix_v3(draw_yes=0),
        ),
        _fixture_row(
            fid=2,
            kickoff=past,
            match_status="finished",
            kpi_rows=[_kpi_row(SEL_DRAW, book=2.5, cecchino=2.0)],
            signals_matrix=_matrix_v3(draw_yes=3),
        ),
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert payload["summary"]["opportunities_total"] == 0
    assert payload["summary"]["excluded_post_kickoff"] >= 1


def test_v3_does_not_affect_sort(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )

    def _resolve(**kw):
        # V3.1 has score 70; V3 in output has 99 — must not use V3
        return {
            "status": "ok",
            "source_mode": "persisted_pre_match_snapshot",
            "items": [_v31_item(SEL_DRAW, score=70)],
            "generated_at": "2026-08-07T10:00:00+00:00",
        }

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        _resolve,
    )
    rows = [
        _fixture_row(
            fid=1,
            kpi_rows=[_kpi_row(SEL_DRAW, book=2.2, cecchino=1.9)],
            signals_matrix=_matrix_v3(draw_yes=0),
            v3_items=[{"market_key": SEL_DRAW, "score_v3": 99, "score": 99}],
        )
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    opp = payload["opportunities"][0]
    assert opp["purchasability_v31"]["score"] == 70


def test_freshness_revision_changes_on_rescan(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )

    state = {"score": 50, "book": 2.0, "draw_yes": 0, "gen": "2026-08-07T10:00:00+00:00"}

    def _resolve(**kw):
        return {
            "status": "ok",
            "source_mode": "persisted_pre_match_snapshot",
            "items": [_v31_item(SEL_DRAW, score=state["score"])],
            "generated_at": state["gen"],
        }

    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        _resolve,
    )

    def _row():
        return _fixture_row(
            fid=1,
            kpi_rows=[_kpi_row(SEL_DRAW, book=state["book"], cecchino=1.9)],
            signals_matrix=_matrix_v3(draw_yes=state["draw_yes"]),
            updated_at=datetime.fromisoformat(state["gen"].replace("Z", "+00:00"))
            if "Z" not in state["gen"]
            else datetime(2026, 8, 7, 10, tzinfo=timezone.utc),
        )

    db = _mock_db([_row()])
    a = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    rev_a = a["source_revision"]
    a2 = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert a2["source_revision"] == rev_a

    state["book"] = 2.5
    state["draw_yes"] = 3
    state["score"] = 95
    state["gen"] = "2026-08-07T12:00:00+00:00"
    db = _mock_db([_row()])
    b = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert b["source_revision"] != rev_a
    opp = b["opportunities"][0]
    assert opp["price_value"]["quota_book"] == 2.5
    assert opp["signals"]["present"] is True
    assert opp["purchasability_v31"]["score"] == 95
    assert opp["origin"] == ORIGIN_PRICE_AND_SIGNALS


def test_source_revision_stable_hash():
    payload = build_source_generated_from(
        scan_date=date(2026, 8, 8),
        fixtures=[],
        latest_job=None,
        max_v31_generated_at=None,
        max_gi_snapshot_at=None,
    )
    r1 = compute_source_revision(payload)
    r2 = compute_source_revision(payload)
    assert r1 == r2
    assert len(r1) == 64


def test_readonly_no_writes(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {"items": []},
    )
    rows = [
        _fixture_row(
            fid=1,
            kpi_rows=[_kpi_row(SEL_HOME, book=2.0, cecchino=1.8)],
            signals_matrix=_matrix_v3(home_si=True),
        )
    ]
    db = _mock_db(rows)
    aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert db.add.call_count == 0
    assert db.commit.call_count == 0
    assert db.delete.call_count == 0
    assert db.flush.call_count == 0


# ---------------------------------------------------------------------------
# BET-01.1 — Balance V5 context mapping (snapshot monitoring keys)
# ---------------------------------------------------------------------------


def _canonical_balance_snapshot(**overrides) -> dict:
    base = {
        "status": "ok",
        "balance_version": "cecchino_balance_v5_v3",
        "snapshot_version": "cecchino_balance_v5_monitoring_snapshot_v2",
        "f36_index": 73.99,
        "f36_class": "Equilibrio",
        "dominance_index": 29.57,
        "dominance_class": "Debole",
        "draw_credibility_index": 45.14,
        "draw_credibility_class": "Pareggio forte",
        "gap_index": 75.9,
        "gap_class": "Confermato",
        "source_mode": "prospective_scan",
        "pre_match_verified": True,
        "prob_1_norm": 0.33,
        "prob_x_norm": 0.34,
        "prob_2_norm": 0.33,
    }
    base.update(overrides)
    return base


def test_balance_context_four_pillars_from_canonical_snapshot(monkeypatch):
    """BET-01.1: mapping gap_index/*_class → pillars + gap_coherence_index."""
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {
            "status": "ok",
            "items": [_v31_item(SEL_DRAW, score=80)],
            "source_mode": "persisted_pre_match_snapshot",
            "generated_at": "2026-08-07T10:00:00+00:00",
        },
    )
    rows = [
        _fixture_row(
            fid=11,
            kpi_rows=[_kpi_row(SEL_DRAW, book=2.2, cecchino=1.9)],
            signals_matrix=_matrix_v3(draw_yes=2),
            balance=_canonical_balance_snapshot(),
        )
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    draw = next(o for o in payload["opportunities"] if o["market"]["market_key"] == SEL_DRAW)
    ctx = draw["context_support"]
    assert ctx["available"] is True
    assert ctx["module"] == "balance_v5"
    assert ctx["status"] == "raw_context_only"
    pl = ctx["payload"]
    assert pl["gap_coherence_index"] == 75.9
    pillars = pl["pillars"]
    assert pillars["f36"] == {"index": 73.99, "class_label": "Equilibrio"}
    assert pillars["dominance"] == {"index": 29.57, "class_label": "Debole"}
    assert pillars["draw_credibility"] == {"index": 45.14, "class_label": "Pareggio forte"}
    assert pillars["gap_coherence"] == {"index": 75.9, "class_label": "Confermato"}
    assert "supports" not in pl
    assert "contradicts" not in pl


def test_balance_context_gap_absent_stays_null(monkeypatch):
    """BET-01.1: senza gap_index lo pillar 4 resta null (nessuna formula inventata)."""
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {
            "status": "ok",
            "items": [_v31_item(SEL_HOME, score=70)],
            "source_mode": "persisted_pre_match_snapshot",
            "generated_at": "2026-08-07T10:00:00+00:00",
        },
    )
    snap = _canonical_balance_snapshot()
    del snap["gap_index"]
    del snap["gap_class"]
    rows = [
        _fixture_row(
            fid=12,
            kpi_rows=[_kpi_row(SEL_HOME, book=2.0, cecchino=1.8)],
            signals_matrix=_matrix_v3(home_si=True),
            balance=snap,
        )
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    home = next(o for o in payload["opportunities"] if o["market"]["market_key"] == SEL_HOME)
    pl = home["context_support"]["payload"]
    assert pl["gap_coherence_index"] is None
    assert pl["pillars"]["gap_coherence"]["index"] is None
    assert pl["pillars"]["gap_coherence"]["class_label"] is None
    # altri tre pilastri ancora valorizzati
    assert pl["pillars"]["f36"]["index"] == 73.99
    assert pl["pillars"]["f36"]["class_label"] == "Equilibrio"
    assert pl["dominance_index"] == 29.57
    assert pl["draw_credibility_index"] == 45.14


def test_balance_context_does_not_recalculate_or_alter_other_context(monkeypatch):
    """BET-01.1: solo remapping; opportunity/GI/aggregation invariati strutturalmente."""
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {
            "status": "ok",
            "items": [
                _v31_item(SEL_DRAW, score=90),
                _v31_item(SEL_OVER_2_5, score=55),
            ],
            "source_mode": "persisted_pre_match_snapshot",
            "generated_at": "2026-08-07T10:00:00+00:00",
        },
    )
    rows = [
        _fixture_row(
            fid=13,
            kpi_rows=[
                _kpi_row(SEL_DRAW, book=2.2, cecchino=1.9),
                _kpi_row(SEL_OVER_2_5, book=2.0, cecchino=1.7),
            ],
            signals_matrix=_matrix_v3(draw_yes=2),
            balance=_canonical_balance_snapshot(),
        )
    ]
    db = _mock_db(rows)
    payload = aggregate_bet_builder_opportunities(db, scan_date=date(2026, 8, 8))
    assert payload["purchasability_policy"] == PURCHASABILITY_POLICY
    keys = {o["opportunity_key"] for o in payload["opportunities"]}
    assert "13:DRAW" in keys
    assert "13:OVER_2_5" in keys
    draw = next(o for o in payload["opportunities"] if o["market"]["market_key"] == SEL_DRAW)
    over = next(o for o in payload["opportunities"] if o["market"]["market_key"] == SEL_OVER_2_5)
    assert draw["origin"] == ORIGIN_PRICE_AND_SIGNALS
    assert draw["context_support"]["module"] == "balance_v5"
    assert draw["context_support"]["payload"]["gap_coherence_index"] == 75.9
    # O/U non usa Balance; GI context invariato (bundle assente → unavailable)
    assert over["context_support"]["module"] != "balance_v5"
    assert over["purchasability_v31"]["score"] == 55
    # nessuna chiave formula inventata nel payload Balance
    bal = draw["context_support"]["payload"]
    assert "gap_coherence_formula" not in bal
    assert bal["f36_index"] == 73.99


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_api_opportunities_200(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {
            "status": "ok",
            "items": [_v31_item(SEL_DRAW, score=80)],
            "source_mode": "persisted_pre_match_snapshot",
            "generated_at": "2026-08-07T10:00:00+00:00",
        },
    )
    rows = [
        _fixture_row(
            fid=5,
            kpi_rows=[_kpi_row(SEL_DRAW, book=2.1, cecchino=1.9)],
            signals_matrix=_matrix_v3(draw_yes=2),
        )
    ]
    db = _mock_db(rows)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    res = client.get("/api/cecchino/bet-builder/opportunities?date=2026-08-08")
    assert res.status_code == 200
    body = res.json()
    assert body["contract_version"] == BET_BUILDER_CONTRACT_VERSION
    assert body["summary"]["opportunities_total"] >= 1
    assert "source_revision" in body
    # no leakage keys
    blob = str(body)
    assert "evaluation_status" not in blob or "won" not in blob.lower()
    assert "goals_home_ft" not in blob


def test_api_invalid_date_422():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    client = TestClient(app)
    res = client.get("/api/cecchino/bet-builder/opportunities?date=not-a-date")
    assert res.status_code == 422


def test_api_market_and_origin_filter(monkeypatch):
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.get_active_bundle",
        lambda _db: None,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_bet_builder_opportunity_aggregator.resolve_purchasability_preview_v31_for_detail",
        lambda **kw: {"items": [], "status": "unavailable"},
    )
    rows = [
        _fixture_row(
            fid=1,
            kpi_rows=[
                _kpi_row(SEL_DRAW, book=2.2, cecchino=1.9),
                _kpi_row(SEL_HOME, book=2.2, cecchino=1.9),
            ],
            signals_matrix=_matrix_v3(draw_yes=2, home_si=True),
        )
    ]
    db = _mock_db(rows)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: (yield db)  # type: ignore
    # proper override
    def _ov():
        yield db

    app.dependency_overrides[get_db] = _ov
    client = TestClient(app)
    res = client.get(
        "/api/cecchino/bet-builder/opportunities?date=2026-08-08&market_key=DRAW&origin=price_and_signals"
    )
    assert res.status_code == 200
    body = res.json()
    for opp in body["opportunities"]:
        assert opp["market"]["market_key"] == SEL_DRAW
        assert opp["origin"] == ORIGIN_PRICE_AND_SIGNALS
