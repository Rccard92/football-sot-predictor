"""CECCHINO-BOOK-PERF-01 — call logic Phase A (1X2 gate) + Phase B (full enrich)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.services.cecchino.cecchino_canonical_book_payload import build_single_bookmaker_payload
from app.services.cecchino.cecchino_canonical_book_resolver import (
    resolve_selection_book_odd,
)
from app.services.cecchino.cecchino_constants import (
    CECCHINO_FALLBACK_BOOKMAKER,
    CECCHINO_PRIMARY_BOOKMAKER,
)
from app.services.cecchino.cecchino_selection_keys import SEL_HOME, SEL_OVER_2_5
from app.services.cecchino.cecchino_today_odds_fetch import (
    _BET365_ID,
    _BETFAIR_ID,
    enrich_fixture_odds_full_canonical,
    fetch_fixture_odds_for_cecchino_1x2_gate,
)
from app.services.cecchino.cecchino_today_scan_metrics import ScanRunMetrics


def _book_raw(
    *,
    bookmaker_id: int,
    bookmaker_name: str,
    match_winner: dict[str, str] | None = None,
    over_under: dict[str, str] | None = None,
    double_chance: dict[str, str] | None = None,
    first_half: dict[str, str] | None = None,
    ou_fh: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    bets: list[dict[str, Any]] = []
    if match_winner:
        bets.append(
            {
                "id": 1,
                "name": "Match Winner",
                "values": [{"value": k, "odd": v} for k, v in match_winner.items()],
            },
        )
    if over_under:
        bets.append(
            {
                "id": 5,
                "name": "Goals Over/Under",
                "values": [{"value": k, "odd": v} for k, v in over_under.items()],
            },
        )
    if double_chance:
        bets.append(
            {
                "id": 12,
                "name": "Double Chance",
                "values": [{"value": k, "odd": v} for k, v in double_chance.items()],
            },
        )
    if first_half:
        bets.append(
            {
                "id": 13,
                "name": "First Half Winner",
                "values": [{"value": k, "odd": v} for k, v in first_half.items()],
            },
        )
    if ou_fh:
        bets.append(
            {
                "name": "Goals Over/Under First Half",
                "values": [{"value": k, "odd": v} for k, v in ou_fh.items()],
            },
        )
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


def _full_canonical_bf(**extra_ou: str) -> list[dict[str, Any]]:
    ou = {
        "Over 1.5": "1.25",
        "Under 1.5": "3.80",
        "Over 2.5": "1.72",
        "Under 2.5": "2.10",
        "Over 3.5": "2.50",
        "Under 3.5": "1.50",
        **extra_ou,
    }
    return _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        over_under=ou,
        double_chance={"Home/Draw": "1.20", "Draw/Away": "1.90", "Home/Away": "1.35"},
        first_half={"Home": "2.2", "Draw": "2.1", "Away": "4.0"},
        ou_fh={
            "Over 0.5": "1.40",
            "Under 0.5": "2.80",
            "Over 1.5": "2.60",
            "Under 1.5": "1.45",
        },
    )


def _settings(monkeypatch, *, fallback: bool = True) -> None:
    settings = MagicMock()
    settings.cecchino_odds_bookmaker_fallback = fallback
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )


def _tracking_client() -> tuple[MagicMock, list[tuple[str, int | None]]]:
    client = MagicMock()
    call_order: list[tuple[str, int | None]] = []

    def _by_fixture(fid: int):
        call_order.append(("fixture_wide", None))
        return []

    def _by_book(fid: int, bookmaker_id: int):
        call_order.append(("bookmaker", int(bookmaker_id)))
        return []

    client.get_fixture_odds_by_fixture.side_effect = _by_fixture
    client.get_fixture_odds.side_effect = _by_book
    return client, call_order


def test_01_bf_1x2_complete_no_stats_no_enrich_no_b365(monkeypatch):
    """TEST 1: BF 1X2 completo, no Phase B → 1 BF, 0 B365, no full enrich metrics."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        # O/U incomplete would previously trigger B365 before stats gate
        over_under={"Over 2.5": "1.72"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        assert bookmaker_id == _BETFAIR_ID
        return bf

    client.get_fixture_odds.side_effect = _by_book
    metrics = ScanRunMetrics()
    odds, _, strategy, neg = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 101, force_rescan=True, metrics=metrics,
    )
    assert neg is False
    assert strategy == "betfair_1x2"
    assert call_order == [("bookmaker", _BETFAIR_ID)]
    client.get_fixture_odds_by_fixture.assert_not_called()
    assert metrics.book_coverage_fixture_count == 0
    assert metrics.betfair_primary_selection_count == 0  # no Phase B record
    assert _BETFAIR_ID in odds
    assert _BET365_ID not in odds


def test_02_bf_1x2_incomplete_b365_fills_no_enrich(monkeypatch):
    """TEST 2: BF 1X2 incompleto + B365 completa gate → 1 BF + 1 B365, no Phase B."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20"},  # AWAY missing
    )
    b365 = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        match_winner={"Home": "1.85", "Draw": "3.30", "Away": "4.60"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        if bookmaker_id == _BETFAIR_ID:
            return bf
        return b365

    client.get_fixture_odds.side_effect = _by_book
    metrics = ScanRunMetrics()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 102, force_rescan=True, metrics=metrics,
    )
    assert strategy == "betfair_1x2_with_bet365_fallback"
    assert call_order == [("bookmaker", _BETFAIR_ID), ("bookmaker", _BET365_ID)]
    assert metrics.book_coverage_fixture_count == 0
    assert _BET365_ID in odds


def test_03_bf_full_canonical_after_stats_zero_b365(monkeypatch):
    """TEST 3: BF 1X2 ok + stats pass + BF copre tutto → 1 BF totale, 0 B365."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _full_canonical_bf()

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        assert bookmaker_id == _BETFAIR_ID
        return bf

    client.get_fixture_odds.side_effect = _by_book
    metrics = ScanRunMetrics()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 103, force_rescan=True, metrics=metrics,
    )
    assert strategy == "betfair_1x2"
    odds2, warnings, did_b365 = enrich_fixture_odds_full_canonical(
        client, 103, odds, metrics=metrics,
    )
    assert did_b365 is False
    assert warnings == []
    assert call_order == [("bookmaker", _BETFAIR_ID)]
    assert metrics.book_coverage_fixture_count == 1
    assert metrics.betfair_primary_selection_count > 0
    assert metrics.bet365_fallback_selection_count == 0
    assert _BET365_ID not in odds2


def test_04_bf_missing_over_needs_one_b365_keeps_bf_primary(monkeypatch):
    """TEST 4: BF 1X2 ok, manca OVER_2_5 → 1 BF + 1 B365; BF restano BF."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
        over_under={
            "Over 1.5": "1.25",
            "Under 1.5": "3.80",
            # OVER_2_5 missing on purpose
            "Under 2.5": "2.10",
            "Over 3.5": "2.50",
            "Under 3.5": "1.50",
        },
        double_chance={"Home/Draw": "1.20", "Draw/Away": "1.90", "Home/Away": "1.35"},
        first_half={"Home": "2.2", "Draw": "2.1", "Away": "4.0"},
        ou_fh={
            "Over 0.5": "1.40",
            "Under 0.5": "2.80",
            "Over 1.5": "2.60",
            "Under 1.5": "1.45",
        },
    )
    b365 = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        match_winner={"Home": "1.85", "Draw": "3.30", "Away": "4.70"},
        over_under={"Over 2.5": "1.80", "Under 2.5": "2.05"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        if bookmaker_id == _BETFAIR_ID:
            return bf
        return b365

    client.get_fixture_odds.side_effect = _by_book
    metrics = ScanRunMetrics()
    odds, _, _, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 104, force_rescan=True, metrics=metrics,
    )
    assert call_order == [("bookmaker", _BETFAIR_ID)]  # Phase A: no B365
    odds2, _, did_b365 = enrich_fixture_odds_full_canonical(
        client, 104, odds, metrics=metrics,
    )
    assert did_b365 is True
    assert call_order == [("bookmaker", _BETFAIR_ID), ("bookmaker", _BET365_ID)]

    primary = build_single_bookmaker_payload(odds2[_BETFAIR_ID], CECCHINO_PRIMARY_BOOKMAKER)
    fallback = build_single_bookmaker_payload(odds2[_BET365_ID], CECCHINO_FALLBACK_BOOKMAKER)
    home_odd, home_prov = resolve_selection_book_odd(
        selection_key=SEL_HOME,
        primary_markets=primary["markets"],
        primary_provenance=primary.get("provenance_by_selection"),
        fallback_markets=fallback["markets"],
        fallback_provenance=fallback.get("provenance_by_selection"),
    )
    over_odd, over_prov = resolve_selection_book_odd(
        selection_key=SEL_OVER_2_5,
        primary_markets=primary["markets"],
        primary_provenance=primary.get("provenance_by_selection"),
        fallback_markets=fallback["markets"],
        fallback_provenance=fallback.get("provenance_by_selection"),
    )
    assert home_odd == 1.80
    assert home_prov["bookmaker_name"] == "Betfair"
    assert over_odd == 1.80
    assert over_prov["bookmaker_name"] == "Bet365"
    assert metrics.book_coverage_fixture_count == 1


def test_05_b365_from_gate_reused_in_phase_b(monkeypatch):
    """TEST 5: B365 già in Phase A → Phase B riusa, nessuna seconda call."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20"},  # AWAY missing → B365 gate
    )
    b365 = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        match_winner={"Away": "4.60"},
        over_under={"Over 2.5": "1.80", "Under 2.5": "2.10"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        if bookmaker_id == _BETFAIR_ID:
            return bf
        return b365

    client.get_fixture_odds.side_effect = _by_book
    metrics = ScanRunMetrics()
    odds, _, _, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 105, force_rescan=True, metrics=metrics,
    )
    assert call_order == [("bookmaker", _BETFAIR_ID), ("bookmaker", _BET365_ID)]
    _, _, did_b365 = enrich_fixture_odds_full_canonical(
        client, 105, odds, metrics=metrics,
    )
    assert did_b365 is False
    assert call_order == [("bookmaker", _BETFAIR_ID), ("bookmaker", _BET365_ID)]
    assert metrics.book_coverage_fixture_count == 1


def test_06_cache_bf_b365_zero_api(monkeypatch):
    """TEST 6: cache con BF+B365 sufficiente → 0 API."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    cached = {
        _BETFAIR_ID: _full_canonical_bf(),
        _BET365_ID: _book_raw(
            bookmaker_id=_BET365_ID,
            bookmaker_name="Bet365",
            match_winner={"Home": "1.85", "Draw": "3.30", "Away": "4.70"},
        ),
    }
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.check_negative_odds_cache",
        lambda *a, **k: (False, None, None),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.load_cached_odds_for_fixture",
        lambda *a, **k: cached,
    )
    metrics = ScanRunMetrics()
    db = MagicMock()
    odds, _, strategy, neg = fetch_fixture_odds_for_cecchino_1x2_gate(
        client,
        106,
        db=db,
        scan_date=__import__("datetime").date(2026, 8, 9),
        force_rescan=False,
        metrics=metrics,
    )
    assert strategy == "cached"
    assert neg is False
    assert call_order == []
    client.get_fixture_odds.assert_not_called()
    client.get_fixture_odds_by_fixture.assert_not_called()
    _, _, did_b365 = enrich_fixture_odds_full_canonical(
        client, 106, odds, metrics=metrics,
    )
    assert did_b365 is False
    assert call_order == []
    assert metrics.book_coverage_fixture_count == 1


def test_07_cache_bf_1x2_complete_missing_full_max_one_b365(monkeypatch):
    """TEST 7: cache BF 1X2 ok, full manca → no refetch BF; max 1 B365."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    cached = {
        _BETFAIR_ID: _book_raw(
            bookmaker_id=_BETFAIR_ID,
            bookmaker_name="Betfair",
            match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
            # incomplete full canonical
        ),
    }
    b365 = _book_raw(
        bookmaker_id=_BET365_ID,
        bookmaker_name="Bet365",
        over_under={"Over 2.5": "1.80", "Under 2.5": "2.10"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        assert bookmaker_id == _BET365_ID
        return b365

    client.get_fixture_odds.side_effect = _by_book
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.check_negative_odds_cache",
        lambda *a, **k: (False, None, None),
    )
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.load_cached_odds_for_fixture",
        lambda *a, **k: cached,
    )
    metrics = ScanRunMetrics()
    db = MagicMock()
    odds, _, strategy, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client,
        107,
        db=db,
        scan_date=__import__("datetime").date(2026, 8, 9),
        force_rescan=False,
        metrics=metrics,
    )
    assert strategy == "cached"
    assert call_order == []
    _, _, did_b365 = enrich_fixture_odds_full_canonical(
        client, 107, dict(odds), metrics=metrics,
    )
    assert did_b365 is True
    assert call_order == [("bookmaker", _BET365_ID)]
    assert metrics.book_coverage_fixture_count == 1


def test_08_call_order_and_count_phase_a_primary(monkeypatch):
    """TEST 8: call_order / call_count — Phase A preferisce bookmaker=3, mai fixture-wide."""
    _settings(monkeypatch)
    client, call_order = _tracking_client()
    bf = _book_raw(
        bookmaker_id=_BETFAIR_ID,
        bookmaker_name="Betfair",
        match_winner={"Home": "1.80", "Draw": "3.20", "Away": "4.50"},
    )

    def _by_book(fid, bookmaker_id):
        call_order.append(("bookmaker", int(bookmaker_id)))
        return bf

    client.get_fixture_odds.side_effect = _by_book
    fetch_fixture_odds_for_cecchino_1x2_gate(client, 108, force_rescan=True)
    assert len(call_order) == 1
    assert call_order[0] == ("bookmaker", _BETFAIR_ID)
    assert "fixture_wide" not in {c[0] for c in call_order}
    client.get_fixture_odds_by_fixture.assert_not_called()


def test_phase_a_does_not_double_count_coverage(monkeypatch):
    """Gate + enrich: coverage fixture_count incrementa solo in Phase B."""
    _settings(monkeypatch)
    client = MagicMock()
    bf = _full_canonical_bf()
    client.get_fixture_odds.return_value = bf
    monkeypatch.setattr(
        "app.services.cecchino.cecchino_today_odds_fetch.time.sleep",
        lambda *_a, **_k: None,
    )
    metrics = ScanRunMetrics()
    odds, _, _, _ = fetch_fixture_odds_for_cecchino_1x2_gate(
        client, 109, force_rescan=True, metrics=metrics,
    )
    assert metrics.book_coverage_fixture_count == 0
    enrich_fixture_odds_full_canonical(client, 109, odds, metrics=metrics)
    assert metrics.book_coverage_fixture_count == 1
    # Seconda enrich non dovrebbe essere chiamata in scan reale; se lo fosse conterebbe di nuovo —
    # il contratto Today è una sola chiamata Phase B per fixture.
