"""Test policy Book Cecchino: Betfair primary → Bet365 fallback (selection-by-selection)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.services.cecchino.cecchino_bet_builder_opportunity_aggregator import build_price_value
from app.services.cecchino.cecchino_bet_builder_results import _primary_quota_book
from decimal import Decimal
from app.services.cecchino.cecchino_betfair_odds_payload import (
    build_betfair_payload_from_raw,
    build_betfair_payload_from_snapshot,
)
from app.services.cecchino.cecchino_canonical_book_resolver import (
    resolve_selection_book_odd,
)
from app.services.cecchino.cecchino_constants import (
    CECCHINO_BOOK_POLICY_VERSION,
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import build_cecchino_kpi_panel_v2_betfair
from app.services.cecchino.cecchino_selection_keys import (
    MARKET_1X2,
    MARKET_OU,
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)
from app.services.cecchino.cecchino_today_bookmaker_gate import verify_complete_1x2_odds
from app.services.cecchino.cecchino_today_odds_fetch import (
    _BET365_ID,
    _BETFAIR_ID,
    _extract_odds_by_book_from_response,
    fetch_fixture_odds_for_cecchino_bookmakers,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics


def _book_raw(
    *,
    bookmaker_id: int,
    bookmaker_name: str,
    match_winner: dict[str, str] | None = None,
    over_under: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    if match_winner:
        values = [{"value": k, "odd": v} for k, v in match_winner.items()]
        bets.append({"id": 1, "name": "Match Winner", "values": values})
    if over_under:
        values = [{"value": k, "odd": v} for k, v in over_under.items()]
        bets.append({"id": 5, "name": "Goals Over/Under", "values": values})
    return [
        {
            "bookmakers": [
                {
                    "id": bookmaker_id,
                    "name": bookmaker_name,
                    "bets": bets,
                },
            ],
        },
    ]


def _final_odds_ok() -> dict[str, Any]:
    return {
        "status": "available",
        "quota_1": 2.10,
        "quota_x": 3.40,
        "quota_2": 3.50,
        "prob_1": 0.40,
        "prob_x": 0.28,
        "prob_2": 0.32,
    }


def _row_by_key(panel: dict[str, Any], key: str) -> dict[str, Any]:
    for row in panel.get("rows") or []:
        if row.get("market_key") == key:
            return row
    raise AssertionError(f"missing row {key}")


# --- CASO A ---
def test_case_a_betfair_over_beats_bet365():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
            over_under={"Over 2.5": "1.80", "Under 2.5": "2.00"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Home": "1.85", "Draw": "3.30", "Away": "4.20"},
            over_under={"Over 2.5": "1.90", "Under 2.5": "1.95"},
        ),
    }
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_OVER_2_5)
    assert row["quota_book"] == 1.80
    assert row["bookmaker_name"] == "Betfair"
    assert row["book_fallback_used"] is False
    assert row["provider_bookmaker_id"] == 3


# --- CASO B ---
def test_case_b_bet365_fallback_over():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Home": "1.85", "Draw": "3.30", "Away": "4.20"},
            over_under={"Over 2.5": "1.36", "Under 2.5": "3.10"},
        ),
    }
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_OVER_2_5)
    assert row["quota_book"] == 1.36
    assert row["bookmaker_name"] == "Bet365"
    assert row["book_fallback_used"] is True
    assert row["provider_bookmaker_id"] == 8


# --- CASO C ---
def test_case_c_bet365_fallback_under():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Under 2.5": "3.00"},
        ),
    }
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_UNDER_2_5)
    assert row["quota_book"] == 3.00
    assert row["bookmaker_name"] == "Bet365"
    assert row["book_fallback_used"] is True


# --- CASO D ---
def test_case_d_both_missing():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        ),
    }
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_OVER_2_5)
    assert row["quota_book"] is None


# --- CASO E ---
def test_case_e_mixed_1x2_gate_passes():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Away": "4.50"},
        ),
    }
    ok, snap, reason, blocking = verify_complete_1x2_odds(odds)
    assert ok
    assert reason is None
    assert blocking == []
    assert snap["selection_sources"][SEL_HOME] == "Betfair"
    assert snap["selection_sources"][SEL_DRAW] == "Betfair"
    assert snap["selection_sources"][SEL_AWAY] == "Bet365"
    assert snap["bookmakers"]["Canonical"]["AWAY"] == 4.50
    # Provenance: Betfair non deve contenere quote Bet365
    bf_snap = snap["bookmakers"].get("Betfair") or {}
    assert bf_snap.get("HOME") == 1.80
    assert bf_snap.get("DRAW") == 3.20
    assert bf_snap.get("AWAY") in (None,)
    assert snap["bookmakers"]["Bet365"]["AWAY"] == 4.50


# --- CASO F ---
def test_case_f_betfair_error_bet365_complete():
    odds = {
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Home": "2.00", "Draw": "3.10", "Away": "3.80"},
        ),
    }
    ok, snap, reason, _ = verify_complete_1x2_odds(odds)
    assert ok
    assert reason is None
    assert snap["selection_sources"][SEL_HOME] == "Bet365"
    assert all(snap["selection_sources"][k] == "Bet365" for k in (SEL_HOME, SEL_DRAW, SEL_AWAY))
    assert "Betfair" not in snap["bookmakers"]
    assert "Bet365" in snap["bookmakers"]
    assert snap["bookmakers"]["Canonical"]["HOME"] == 2.00
    assert snap["bookmakers"]["Canonical"]["DRAW"] == 3.10
    assert snap["bookmakers"]["Canonical"]["AWAY"] == 3.80


# --- CASO G ---
def test_case_g_betfair_never_replaced():
    primary_markets = {MARKET_OU: {SEL_OVER_2_5: 1.80}}
    fallback_markets = {MARKET_OU: {SEL_OVER_2_5: 1.90}}
    odd, prov = resolve_selection_book_odd(
        selection_key=SEL_OVER_2_5,
        primary_markets=primary_markets,
        primary_provenance={SEL_OVER_2_5: {"source": "betfair_raw_over_under"}},
        fallback_markets=fallback_markets,
        fallback_provenance={SEL_OVER_2_5: {"source": "bet365_raw_over_under"}},
    )
    assert odd == 1.80
    assert prov is not None
    assert prov["book_fallback_used"] is False
    assert prov["bookmaker_name"] == "Betfair"


# --- CASO H ---
def test_case_h_no_bet365_specific_when_betfair_covers(monkeypatch):
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    client = MagicMock()
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": 3,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                        {
                            "id": 5,
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 1.5", "odd": "1.25"},
                                {"value": "Under 1.5", "odd": "3.80"},
                                {"value": "Over 2.5", "odd": "1.80"},
                                {"value": "Under 2.5", "odd": "2.00"},
                                {"value": "Over 3.5", "odd": "2.50"},
                                {"value": "Under 3.5", "odd": "1.50"},
                            ],
                        },
                        {
                            "id": 13,
                            "name": "First Half Winner",
                            "values": [
                                {"value": "Home", "odd": "2.2"},
                                {"value": "Draw", "odd": "2.1"},
                                {"value": "Away", "odd": "4.0"},
                            ],
                        },
                        {
                            "name": "Goals Over/Under First Half",
                            "values": [
                                {"value": "Over 0.5", "odd": "1.40"},
                                {"value": "Under 0.5", "odd": "2.80"},
                                {"value": "Over 1.5", "odd": "2.60"},
                                {"value": "Under 1.5", "odd": "1.45"},
                            ],
                        },
                        {
                            "name": "Double Chance",
                            "values": [
                                {"value": "Home/Draw", "odd": "1.20"},
                                {"value": "Draw/Away", "odd": "1.90"},
                                {"value": "Home/Away", "odd": "1.35"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    client.get_fixture_odds_by_fixture.return_value = fixture_wide
    metrics = ScanRunMetrics()
    odds, warnings, strategy, neg = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        99,
        force_rescan=True,
        metrics=metrics,
    )
    assert neg is False
    assert _BETFAIR_ID in odds
    client.get_fixture_odds.assert_not_called()
    assert strategy == "fixture_single_call"


# --- CASO I ---
def test_case_i_one_bet365_specific_call(monkeypatch):
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    client = MagicMock()
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": 3,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    # Betfair-specific non aggiunge O/U → serve Bet365-specific
    betfair_specific = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
    )
    bet365_specific = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        over_under={"Over 2.5": "1.36", "Under 2.5": "3.00"},
    )
    client.get_fixture_odds_by_fixture.return_value = fixture_wide

    def _get_odds(fid, bookmaker_id):
        if bookmaker_id == _BETFAIR_ID:
            return betfair_specific
        assert bookmaker_id == _BET365_ID
        return bet365_specific

    client.get_fixture_odds.side_effect = _get_odds
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    metrics = ScanRunMetrics()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_bookmakers(
        client,
        42,
        force_rescan=True,
        metrics=metrics,
    )
    # Betfair-specific prima, poi Bet365-specific
    assert client.get_fixture_odds.call_count == 2
    assert client.get_fixture_odds.call_args_list[0].args[1] == _BETFAIR_ID
    assert client.get_fixture_odds.call_args_list[1].args[1] == _BET365_ID
    assert _BET365_ID in odds
    assert "bet365" in strategy


# --- CASO J ---
def test_case_j_negative_cache_only_after_canonical_fail():
    # Mixed 1X2 (Betfair incomplete + Bet365 fills) → gate OK → no negative reason
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Away": "4.50"},
        ),
    }
    ok, _, _, _ = verify_complete_1x2_odds(odds)
    assert ok

    # Solo Betfair incompleto senza Bet365 → fail canonical (neg cache candidate)
    ok2, _, reason, _ = verify_complete_1x2_odds(
        {
            _BETFAIR_ID: _book_raw(
                bookmaker_id=_BETFAIR_ID,
                bookmaker_name="Betfair",
                match_winner={"Home": "1.80"},
            ),
        },
    )
    assert not ok2
    assert reason == "missing_1x2_market"


# --- CASO K ---
def test_case_k_offline_rebuild_with_both_raw():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
            over_under={"Over 2.5": "1.80"},
        ),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Under 2.5": "3.00"},
        ),
    }
    snap = {
        "raw_by_bookmaker_id": {str(k): v for k, v in odds.items()},
        "book_policy_version": CECCHINO_BOOK_POLICY_VERSION,
    }
    payload = build_betfair_payload_from_snapshot(snap)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    assert _row_by_key(panel, SEL_OVER_2_5)["quota_book"] == 1.80
    assert _row_by_key(panel, SEL_UNDER_2_5)["quota_book"] == 3.00
    assert _row_by_key(panel, SEL_UNDER_2_5)["book_fallback_used"] is True


# --- CASO L ---
def test_case_l_offline_betfair_only_no_invent():
    odds = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        ),
    }
    snap = {"raw_by_bookmaker_id": {str(_BETFAIR_ID): odds[_BETFAIR_ID]}}
    payload = build_betfair_payload_from_snapshot(snap)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    assert _row_by_key(panel, SEL_OVER_2_5)["quota_book"] is None
    assert panel["book_policy_version"] == CECCHINO_BOOK_POLICY_VERSION


# --- CASO M ---
def test_case_m_bet_builder_signal_only_bet365_provenance():
    kpi_row = {
        "quota_book": 1.36,
        "quota_cecchino": 1.50,
        "prob_book": 0.735,
        "prob_cecchino": 0.667,
        "vantaggio_prob": -0.068,
        "edge_pct": -9.33,
        "score_acquisto": None,
        "rating": 40,
        "rating_label": "Debole",
        "status": "available",
        "book_source": "bet365_raw_over_under",
        "bookmaker_name": "Bet365",
        "provider_bookmaker_id": 8,
        "book_fallback_used": True,
    }
    price = build_price_value(kpi_row)
    assert price["quota_book"] == 1.36
    assert price["bookmaker_name"] == "Bet365"
    assert price["book_fallback_used"] is True
    # present dipende dal gate V3.1 (edge/vantaggio); qui edge negativo → non present
    assert price["present"] is False


# --- CASO N ---
def test_case_n_results_roi_bet365_and_nd():
    assert _primary_quota_book({"price_value": {"quota_book": 1.80}}) == 1.80
    # Profit flat 1u WON @1.80 = +0.80
    qb = _primary_quota_book({"price_value": {"quota_book": 1.80}})
    assert qb is not None and qb > 1.0
    profit_won = Decimal(str(qb)) - Decimal("1")
    assert profit_won == Decimal("0.80")
    assert _primary_quota_book({"price_value": {"quota_book": None}}) is None
    assert _primary_quota_book({"price_value": {}}) is None
    assert _primary_quota_book({}) is None
    # Storico Book N/D escluso da priced_settled (quota assente)
    assert _primary_quota_book({"price_value": {"quota_book": None}}) is None


def test_extract_both_books_from_fixture_wide():
    raw = [
        {
            "bookmakers": [
                {"id": 3, "name": "Betfair", "bets": []},
                {"id": 8, "name": "Bet365", "bets": []},
                {"id": 4, "name": "Pinnacle", "bets": []},
            ],
        },
    ]
    extracted = _extract_odds_by_book_from_response(raw)
    assert set(extracted.keys()) == {_BETFAIR_ID, _BET365_ID}


# --- BET365-FALLBACK-01.1 ---
def test_01_1_betfair_specific_before_fallback_for_ou(monkeypatch):
    """TEST 1: BF 1X2 completo ma O/U mancante → Betfair-specific prima di Bet365."""
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    client = MagicMock()
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": 3,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                    ],
                },
                {
                    "id": 8,
                    "name": "Bet365",
                    "bets": [
                        {
                            "id": 5,
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": "1.90"},
                                {"value": "Under 2.5", "odd": "1.95"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    betfair_specific = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
        over_under={"Over 2.5": "1.80", "Under 2.5": "2.00"},
    )
    client.get_fixture_odds_by_fixture.return_value = fixture_wide
    call_order: list[int] = []

    def _get_odds(fid, bookmaker_id):
        call_order.append(int(bookmaker_id))
        if bookmaker_id == _BETFAIR_ID:
            return betfair_specific
        return _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Over 2.5": "1.90", "Under 2.5": "1.95"},
        )

    client.get_fixture_odds.side_effect = _get_odds
    odds, _, _, _ = fetch_fixture_odds_for_cecchino_bookmakers(
        client, 77, force_rescan=True, metrics=ScanRunMetrics(),
    )
    assert call_order[0] == _BETFAIR_ID
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_OVER_2_5)
    assert row["quota_book"] == 1.80
    assert row["bookmaker_name"] == "Betfair"
    assert row["book_fallback_used"] is False


def test_01_1_true_fallback_after_betfair_specific_miss(monkeypatch):
    """TEST 2: Betfair-specific senza O/U → fallback Bet365 1.90."""
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    client = MagicMock()
    fixture_wide = [
        {
            "bookmakers": [
                {
                    "id": 3,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]
    client.get_fixture_odds_by_fixture.return_value = fixture_wide

    def _get_odds(fid, bookmaker_id):
        if bookmaker_id == _BETFAIR_ID:
            return _book_raw(
                bookmaker_id=_BETFAIR_ID,
                bookmaker_name="Betfair",
                match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
            )
        return _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Over 2.5": "1.90", "Under 2.5": "1.95"},
        )

    client.get_fixture_odds.side_effect = _get_odds
    odds, _, _, _ = fetch_fixture_odds_for_cecchino_bookmakers(
        client, 78, force_rescan=True, metrics=ScanRunMetrics(),
    )
    assert client.get_fixture_odds.call_args_list[0].args[1] == _BETFAIR_ID
    assert client.get_fixture_odds.call_args_list[1].args[1] == _BET365_ID
    payload = build_betfair_payload_from_raw(odds)
    panel = build_cecchino_kpi_panel_v2_betfair(final_odds=_final_odds_ok(), betfair_payload=payload)
    row = _row_by_key(panel, SEL_OVER_2_5)
    assert row["quota_book"] == 1.90
    assert row["bookmaker_name"] == "Bet365"
    assert row["book_fallback_used"] is True


def test_01_1_no_useless_specific_calls_when_betfair_covers(monkeypatch):
    """TEST 3: coverage Betfair completa → 0 specific BF/B365."""
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    bets_full = [
        {
            "id": 1,
            "name": "Match Winner",
            "values": [
                {"value": "Home", "odd": "1.8"},
                {"value": "Draw", "odd": "3.2"},
                {"value": "Away", "odd": "4.5"},
            ],
        },
        {
            "id": 5,
            "name": "Goals Over/Under",
            "values": [
                {"value": "Over 1.5", "odd": "1.25"},
                {"value": "Under 1.5", "odd": "3.80"},
                {"value": "Over 2.5", "odd": "1.80"},
                {"value": "Under 2.5", "odd": "2.00"},
                {"value": "Over 3.5", "odd": "2.50"},
                {"value": "Under 3.5", "odd": "1.50"},
            ],
        },
        {
            "id": 13,
            "name": "First Half Winner",
            "values": [
                {"value": "Home", "odd": "2.2"},
                {"value": "Draw", "odd": "2.1"},
                {"value": "Away", "odd": "4.0"},
            ],
        },
        {
            "name": "Goals Over/Under First Half",
            "values": [
                {"value": "Over 0.5", "odd": "1.40"},
                {"value": "Under 0.5", "odd": "2.80"},
                {"value": "Over 1.5", "odd": "2.60"},
                {"value": "Under 1.5", "odd": "1.45"},
            ],
        },
        {
            "name": "Double Chance",
            "values": [
                {"value": "Home/Draw", "odd": "1.20"},
                {"value": "Draw/Away", "odd": "1.90"},
                {"value": "Home/Away", "odd": "1.35"},
            ],
        },
    ]
    client = MagicMock()
    client.get_fixture_odds_by_fixture.return_value = [
        {"bookmakers": [{"id": 3, "name": "Betfair", "bets": bets_full}]},
    ]
    metrics = ScanRunMetrics()
    fetch_fixture_odds_for_cecchino_bookmakers(
        client, 99, force_rescan=True, metrics=metrics,
    )
    client.get_fixture_odds.assert_not_called()
    assert metrics.api_calls.get("odds") == 1


def test_01_1_legacy_snapshot_betfair_only_readable():
    """TEST 6: snapshot legacy solo Betfair senza Canonical resta leggibile."""
    from app.services.cecchino.cecchino_today_odds_meta import extract_1x2_from_snapshot

    legacy = {
        "bookmakers": {"Betfair": {"HOME": 1.80, "DRAW": 3.20, "AWAY": 4.50}},
    }
    extracted = extract_1x2_from_snapshot(legacy)
    assert extracted["HOME"] == 1.80
    assert extracted["DRAW"] == 3.20
    assert extracted["AWAY"] == 4.50
    payload = build_betfair_payload_from_snapshot(legacy)
    assert payload["status"] == "available"
    markets = (payload["bookmakers"][0].get("markets") or {}).get(MARKET_1X2) or {}
    assert markets.get(SEL_HOME) == 1.80
    assert markets.get(SEL_DRAW) == 3.20
    assert markets.get(SEL_AWAY) == 4.50


def test_01_1_api_calls_used_counts_three(monkeypatch):
    """TEST 7: fixture-wide + BF-specific + B365-specific → api_calls odds = 3."""
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = True
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    client = MagicMock()
    # Fixture-wide: solo Betfair 1X2 (gap canonici) senza Bet365
    client.get_fixture_odds_by_fixture.return_value = [
        {
            "bookmakers": [
                {
                    "id": 3,
                    "name": "Betfair",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "1.8"},
                                {"value": "Draw", "odd": "3.2"},
                                {"value": "Away", "odd": "4.5"},
                            ],
                        },
                    ],
                },
            ],
        },
    ]

    def _get_odds(fid, bookmaker_id):
        if bookmaker_id == _BETFAIR_ID:
            return _book_raw(
                bookmaker_id=_BETFAIR_ID,
                bookmaker_name="Betfair",
                match_winner={"Home": "1.8", "Draw": "3.2", "Away": "4.5"},
            )
        return _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            over_under={"Over 2.5": "1.90"},
        )

    client.get_fixture_odds.side_effect = _get_odds
    metrics = ScanRunMetrics()
    fetch_fixture_odds_for_cecchino_bookmakers(
        client, 88, force_rescan=True, metrics=metrics,
    )
    assert client.get_fixture_odds_by_fixture.call_count == 1
    assert client.get_fixture_odds.call_count == 2
    assert metrics.api_calls.get("odds") == 3
