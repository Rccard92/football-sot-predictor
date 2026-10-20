"""CLV dalla prima quota pubblicata e esiti a quarti di handicap (difetti dell'audit del 20/10/2026).

1. Il piano "prematch" legge la chiusura e ricalcola la lista provvisoria: la voce prende la quota di chiusura.
   La prima quota pubblicata deve restare ferma e il CLV si misura da lei, non dalla quota riscritta.
2. `result` deve contenere `mezza_vinta` / `mezza_persa` (11 caratteri).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.cecchino_v4 import CecchinoV4OddsSnapshot, CecchinoV4ShortlistItem
from app.services.cecchino_v4 import serving
from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKERS,
    SHORTLIST_SETTLED,
    VERDICT_LABELS,
    VERDICT_PLAYABLE,
)
from app.services.cecchino_v4.pipeline import day as day_mod
from app.services.cecchino_v4.selection.labels import market_family
from app.services.cecchino_v4.selection.rules import MarketRow
from app.services.cecchino_v4.selection.settlement import HALF_LOST, HALF_WON, settle
from app.services.cecchino_v4.selection.shortlist import (
    build_shortlist,
    get_shortlist,
    list_items,
    save_provisional,
    settle_item,
)
from tests.v4.test_pipeline_serving import DAY, NOW, _FakeHistory, _fake_goals, _fake_stats, seeded  # noqa: F401

STAT_KEY = "STAT:sot:away:over:6.5"


def _naive(dt: datetime | None) -> datetime | None:
    """SQLite perde il fuso: si confrontano gli orari senza fuso."""
    return None if dt is None else dt.replace(tzinfo=None)


def _items_by_fixture(db) -> dict[int, CecchinoV4ShortlistItem]:
    record = get_shortlist(db, DAY)
    assert record is not None
    return {i.fixture_id: i for i in list_items(db, record.id)}


def _build(db, now, recompute=True):
    return day_mod.build_days(
        db, days=[DAY], now=now, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory(), recompute_predictions=recompute
    )


def test_first_published_quota_survives_closing_rebuild_and_drives_clv(v4_db, seeded):
    f1, _ = seeded
    # mattina: lista provvisoria con la quota del mattino (2,20 su Bet365)
    _build(v4_db, NOW)
    morning = _items_by_fixture(v4_db)[f1.id]
    assert morning.market_key == STAT_KEY and morning.quota == pytest.approx(2.2)
    assert morning.published_quota == pytest.approx(2.2) and morning.published_bookmaker_id == BOOKMAKER_BET365_ID
    published_at = morning.published_at

    # piano prematch: chiusura letta 10 minuti prima del via, poi ricalcolo della lista (senza ricalcolare i motori)
    closing_at = datetime(2026, 9, 19, 18, 35, tzinfo=timezone.utc)
    v4_db.add(
        CecchinoV4OddsSnapshot(
            fixture_id=f1.id,
            bookmaker_id=BOOKMAKER_BET365_ID,
            kind="chiusura",
            taken_at=closing_at,
            markets_json={"HOME": 3.0, "DRAW": 3.4, "AWAY": 2.5, STAT_KEY: 2.1},
            created_at=closing_at,
        )
    )
    v4_db.commit()
    _build(v4_db, closing_at, recompute=False)
    rebuilt = _items_by_fixture(v4_db)[f1.id]
    assert rebuilt.market_key == STAT_KEY
    assert rebuilt.quota == pytest.approx(2.1), "la lista mostra la quota piu' fresca (chiusura)"
    assert rebuilt.published_quota == pytest.approx(2.2), "la prima quota pubblicata non si riscrive"
    assert rebuilt.published_at == published_at

    # partita iniziata: la voce si congela e la prima quota pubblicata resta
    _build(v4_db, datetime(2026, 9, 19, 19, 0, tzinfo=timezone.utc), recompute=False)
    frozen = _items_by_fixture(v4_db)[f1.id]
    assert frozen.quota == pytest.approx(2.1) and frozen.published_quota == pytest.approx(2.2)

    # regolamento: CLV = 2,20 / 2,10 - 1, non 0
    f1.status, f1.ft_home, f1.ft_away, f1.ht_home, f1.ht_away = "FT", 0, 2, 0, 1
    f1.stats_json = {"home": {"sot": 3, "shots": 9}, "away": {"sot": 8, "shots": 15}}
    v4_db.commit()
    assert day_mod.settle_finished(v4_db, now=datetime(2026, 9, 19, 21, 0, tzinfo=timezone.utc)) >= 1
    settled = _items_by_fixture(v4_db)[f1.id]
    assert settled.closing_quota == pytest.approx(2.1)
    assert settled.clv == pytest.approx(2.2 / 2.1 - 1, abs=1e-4)
    assert settled.clv > 0
    payload = serving.shortlist(v4_db, DAY)
    item = next(i for i in payload["items"] if i["fixture_id"] == f1.id)
    assert item["published_quota"] == pytest.approx(2.2) and item["clv"] == pytest.approx(2.2 / 2.1 - 1, abs=1e-4)
    m = serving.measure_summary(v4_db)
    assert m["totals"]["plays"] >= 1


def _row(market_key: str, quota: float, p: float = 0.55) -> MarketRow:
    return MarketRow(
        market_key=market_key,
        family=market_family(market_key),
        label=market_key,
        p=p,
        lo=p - 0.03,
        hi=p + 0.03,
        p_prudent=p,
        quota_bet365=quota,
        quota_betfair=None,
        quota_used=quota,
        bookmaker_used=BOOKMAKERS[BOOKMAKER_BET365_ID],
        bookmaker_id=BOOKMAKER_BET365_ID,
        expected_profit=p * quota - 1.0,
        verdict=VERDICT_PLAYABLE,
        verdict_label=VERDICT_LABELS[VERDICT_PLAYABLE],
        advised=True,
    )


def _meta(fixture_id: int) -> dict:
    return {"fixture_id": fixture_id, "home_team": "Casa", "away_team": "Ospite", "kickoff_at": "2026-10-21T18:45:00+00:00", "league_code": "I1"}


def test_settle_item_clv_against_published_quota_not_rewritten_quota(v4_db):
    day = date(2026, 10, 21)
    t0 = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
    save_provisional(v4_db, build_shortlist(day, [(_meta(1), _row("AWAY", 2.30))]), now=t0)
    # ricalcolo con la chiusura: stessa giocata, quota scesa a 2,00
    save_provisional(v4_db, build_shortlist(day, [(_meta(1), _row("AWAY", 2.00))]), now=t0 + timedelta(hours=10))
    record = get_shortlist(v4_db, day)
    (item,) = list_items(v4_db, record.id)
    assert item.quota == pytest.approx(2.00)
    assert item.published_quota == pytest.approx(2.30) and _naive(item.published_at) == _naive(t0)

    settled = settle_item(v4_db, item.id, "vinta", closing_quota=2.00, now=t0 + timedelta(hours=14))
    assert settled.clv == pytest.approx(2.30 / 2.00 - 1, abs=1e-4)  # +15%, non 0
    assert settled.profit_units == pytest.approx(1.00)  # il profitto resta sulla quota della voce


def test_new_play_after_rebuild_is_published_at_its_own_quota(v4_db):
    """Una giocata comparsa solo al ricalcolo (es. alla chiusura) e' pubblicata a quella quota: CLV ~0 e' corretto."""
    day = date(2026, 10, 22)
    t0 = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)
    save_provisional(v4_db, build_shortlist(day, [(_meta(1), _row("AWAY", 2.30))]), now=t0)
    save_provisional(v4_db, build_shortlist(day, [(_meta(1), _row("HOME", 2.40))]), now=t0 + timedelta(hours=10))
    (item,) = list_items(v4_db, get_shortlist(v4_db, day).id)
    assert item.market_key == "HOME" and item.published_quota == pytest.approx(2.40)
    assert _naive(item.published_at) == _naive(t0 + timedelta(hours=10))


def test_legacy_item_without_published_quota_falls_back_to_quota(v4_db):
    """Voci create prima della correzione (published_quota NULL): il CLV usa la quota della voce, come prima."""
    day = date(2026, 10, 23)
    save_provisional(v4_db, build_shortlist(day, [(_meta(1), _row("AWAY", 2.20))]))
    (item,) = list_items(v4_db, get_shortlist(v4_db, day).id)
    item.published_quota = None
    item.published_bookmaker_id = None
    v4_db.commit()
    settled = settle_item(v4_db, item.id, "persa", closing_quota=2.0)
    assert settled.clv == pytest.approx(2.2 / 2.0 - 1, abs=1e-4)


@pytest.mark.parametrize(
    ("market_key", "result", "outcome", "profit"),
    [
        ("AH_HOME:+0.25", {"ft_home": 2, "ft_away": 2}, HALF_WON, (1.90 - 1.0) / 2.0),
        ("AH_HOME:-0.25", {"ft_home": 2, "ft_away": 2}, HALF_LOST, -0.5),
    ],
)
def test_settle_quarter_line_half_outcome_is_stored(v4_db, market_key, result, outcome, profit):
    day = date(2026, 10, 24)
    save_provisional(v4_db, build_shortlist(day, [(_meta(7), _row(market_key, 1.90))]))
    (item,) = list_items(v4_db, get_shortlist(v4_db, day).id)
    got = settle(market_key, {**result, "ht_home": None, "ht_away": None})
    assert got == outcome
    settled = settle_item(v4_db, item.id, got, closing_quota=1.85)
    v4_db.expire_all()
    stored = v4_db.get(CecchinoV4ShortlistItem, settled.id)
    assert stored.result == outcome and stored.status == SHORTLIST_SETTLED
    assert stored.profit_units == pytest.approx(profit)


def test_result_column_fits_half_outcomes():
    length = CecchinoV4ShortlistItem.__table__.c.result.type.length
    assert length >= max(len(HALF_WON), len(HALF_LOST))


def test_migration_is_the_single_head_and_widens_result():
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["20261020090000_v4_clv_published"]
    rev = script.get_revision("20261020090000_v4_clv_published")
    assert rev.down_revision == "20261013090000_xg_league_tags"
    assert len(rev.revision) <= 32
