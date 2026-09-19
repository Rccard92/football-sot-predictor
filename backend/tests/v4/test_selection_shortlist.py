"""Shortlist: una per partita, taglio a 50, top 15, impronta, astensioni, persistenza su SQLite."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.cecchino_v4.constants import (
    MAX_PLAYS_PER_DAY,
    SHORTLIST_CONFIRMED,
    SHORTLIST_PROVISIONAL,
    SHORTLIST_SETTLED,
    SHORTLIST_WITHDRAWN,
    TOP_PLAYS,
    VERDICT_FAIR_PRICE,
    VERDICT_PLAYABLE,
)
from app.services.cecchino_v4.selection.rules import RowInputs, evaluate_market
from app.services.cecchino_v4.selection.settlement import WON
from app.services.cecchino_v4.selection.shortlist import (
    E4_FAILED_BANNER,
    abstention_summary,
    build_shortlist,
    list_items,
    save_provisional,
    seal_digest,
    seal_shortlist,
    settle_item,
    shortlist_payload,
    withdraw_item,
)

DAY = date(2026, 9, 21)


def _row(market_key: str, p: float, quota: float, lineups: str = "ufficiali"):
    return evaluate_market(
        RowInputs(
            market_key=market_key,
            p=p,
            lo=p,
            hi=p,
            uncertainty_score=0.0,
            uncertainty_level="bassa",
            base_rate=0.3,
            label=market_key,
            quota_bet365=quota,
            lineups_status=lineups,
        )
    )


def _candidates(n_fixtures: int):
    cands = []
    for i in range(1, n_fixtures + 1):
        meta = {"fixture_id": i, "home_team": f"Casa{i}", "away_team": f"Ospite{i}", "kickoff_at": "2026-09-21T18:45:00+00:00", "league_code": "I1"}
        strong = _row("AWAY", 0.5, 2.2 + i / 1000.0)  # profitto ~ +10% e crescente con i
        weak = _row("HOME", 0.5, 2.1)  # +5%
        fair = _row("DRAW", 0.3, 3.0)  # -10%: prezzo giusto
        assert strong.verdict == VERDICT_PLAYABLE and weak.verdict == VERDICT_PLAYABLE and fair.verdict == VERDICT_FAIR_PRICE
        cands += [(meta, weak), (meta, strong), (meta, fair)]
    return cands


def test_build_shortlist_one_per_match_sorted_cut_and_top():
    shortlist = build_shortlist(DAY, _candidates(60))
    assert shortlist.status == SHORTLIST_PROVISIONAL
    assert len(shortlist.items) == MAX_PLAYS_PER_DAY
    fixture_ids = [i.fixture_id for i in shortlist.items]
    assert len(set(fixture_ids)) == MAX_PLAYS_PER_DAY
    assert all(i.row.market_key == "AWAY" for i in shortlist.items)  # la migliore per partita
    profits = [i.row.expected_profit for i in shortlist.items]
    assert profits == sorted(profits, reverse=True)
    assert fixture_ids[0] == 60  # profitto più alto
    assert [i.rank for i in shortlist.items] == list(range(1, MAX_PLAYS_PER_DAY + 1))
    assert sum(1 for i in shortlist.items if i.top) == TOP_PLAYS
    assert all(i.top == (i.rank <= TOP_PLAYS) for i in shortlist.items)
    assert all(i.status == SHORTLIST_PROVISIONAL for i in shortlist.items)
    assert shortlist.advised is True and shortlist.banner is None


def test_build_shortlist_ignores_non_playable_and_handles_empty():
    meta = {"fixture_id": 1, "home_team": "A", "away_team": "B"}
    shortlist = build_shortlist(DAY, [(meta, _row("DRAW", 0.3, 3.0))])
    assert shortlist.items == []
    assert shortlist.to_dict()["items"] == []


def test_build_shortlist_not_advised_marks_items_and_banner():
    shortlist = build_shortlist(DAY, _candidates(3), advised=False)
    assert shortlist.advised is False
    assert shortlist.banner == E4_FAILED_BANNER
    assert all(i.row.advised is False for i in shortlist.items)
    payload = shortlist.to_dict()
    assert payload["banner"] == E4_FAILED_BANNER
    assert all(item["advised"] is False for item in payload["items"])
    assert payload["items"][0]["verdict"] == VERDICT_PLAYABLE  # la giocata resta visibile


def test_seal_digest_deterministic_and_sensitive():
    items = build_shortlist(DAY, _candidates(5)).items
    when = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
    first = seal_digest(items, when)
    assert len(first) == 64
    assert seal_digest(list(reversed(items)), when) == first  # l'ordine non conta
    assert seal_digest(items, datetime(2026, 9, 21, 17, 1, tzinfo=timezone.utc)) != first
    as_dicts = [i.to_dict() for i in items]
    assert seal_digest(as_dicts, when) == first  # stessa impronta dai dict
    as_dicts[0]["quota_used"] = 9.99
    assert seal_digest(as_dicts, when) != first


def test_abstention_summary_groups_by_reason():
    fixtures = [
        {"home_team": "Milan", "away_team": "Inter", "no_play_reason": "prezzo_giusto"},
        {"home_team": "Roma", "away_team": "Lazio", "no_play_reason": "prezzo_giusto"},
        {"home_team": "Bari", "away_team": "Pisa", "no_play_reason": "incertezza_alta"},
        {"home_team": "Como", "away_team": "Lecce", "no_play_reason": None},
    ]
    out = abstention_summary(fixtures)
    assert out[0] == {"reason": "prezzo_giusto", "label": "Prezzo giusto", "count": 2, "examples": ["Milan - Inter", "Roma - Lazio"]}
    assert {o["reason"] for o in out} == {"prezzo_giusto", "incertezza_alta", "nessun_mercato"}


# --- persistenza -----------------------------------------------------------------------
def test_persistence_flow(v4_db):
    shortlist = build_shortlist(DAY, _candidates(4), abstentions=[{"reason": "prezzo_giusto", "count": 1, "examples": ["X - Y"]}])
    record = save_provisional(v4_db, shortlist)
    items = list_items(v4_db, record.id)
    assert record.status == SHORTLIST_PROVISIONAL and record.digest is None
    assert len(items) == 4 and [i.rank for i in items] == [1, 2, 3, 4]
    assert items[0].bookmaker_id == 8 and items[0].quota == pytest.approx(2.204)

    # sostituzione della provvisoria
    record2 = save_provisional(v4_db, build_shortlist(DAY, _candidates(2)))
    assert record2.id == record.id
    assert len(list_items(v4_db, record.id)) == 2

    # sigillo
    sealed_at = datetime(2026, 9, 21, 17, 30, tzinfo=timezone.utc)
    sealed = seal_shortlist(v4_db, DAY, sealed_at)
    assert sealed.status == SHORTLIST_CONFIRMED
    assert sealed.digest == seal_digest(list_items(v4_db, record.id), sealed_at)
    assert all(i.status == SHORTLIST_CONFIRMED for i in list_items(v4_db, record.id))
    with pytest.raises(ValueError):
        save_provisional(v4_db, build_shortlist(DAY, _candidates(1)))
    with pytest.raises(ValueError):
        seal_shortlist(v4_db, DAY, sealed_at)

    # ritiro e regolamento
    first, second = list_items(v4_db, record.id)
    withdrawn = withdraw_item(v4_db, first.id, "Titolare chiave assente")
    assert withdrawn.status == SHORTLIST_WITHDRAWN and withdrawn.withdraw_reason == "Titolare chiave assente"
    settled = settle_item(v4_db, second.id, WON, closing_quota=2.10)
    assert settled.status == SHORTLIST_SETTLED
    assert settled.result == WON
    assert settled.profit_units == pytest.approx(second.quota - 1)
    assert settled.clv == pytest.approx(second.quota / 2.10 - 1, abs=1e-4)
    settle_item(v4_db, first.id, WON, closing_quota=2.0)  # la ritirata prende solo il CLV
    refreshed_first = v4_db.get(type(first), first.id)
    assert refreshed_first.status == SHORTLIST_WITHDRAWN and refreshed_first.result is None and refreshed_first.clv is not None
    assert v4_db.get(type(record), record.id).status == SHORTLIST_SETTLED
    with pytest.raises(ValueError):
        withdraw_item(v4_db, second.id, "troppo tardi")

    payload = shortlist_payload(v4_db, DAY)
    assert payload["status"] == SHORTLIST_SETTLED
    assert payload["digest"] == sealed.digest
    assert payload["sealed_at"] == sealed_at.isoformat()
    assert payload["advised"] is True
    assert {i["status"] for i in payload["items"]} == {SHORTLIST_WITHDRAWN, SHORTLIST_SETTLED}
    assert payload["items"][0]["home_team"] == "Casa2"
    assert payload["items"][0]["top"] is True
    assert shortlist_payload(v4_db, date(2000, 1, 1)) is None


def test_persistence_not_advised_banner(v4_db):
    save_provisional(v4_db, build_shortlist(DAY, _candidates(1), advised=False))
    payload = shortlist_payload(v4_db, DAY)
    assert payload["advised"] is False
    assert payload["banner"] == E4_FAILED_BANNER
    assert payload["items"][0]["advised"] is False
