"""Caricamento leggero dello storico HR: stesso risultato del caricamento ORM completo.

Confronta, sulla stessa tabella SQLite, il percorso vecchio (`build_purchasability_rows`,
oggetti ORM con tutte le colonne) con quello nuovo (`build_purchasability_rows_for_history`,
solo colonne/chiavi JSON usate, a blocchi). Righe, indici locale/globale e contesto devono
essere identici.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE, CecchinoTodayFixture
from app.services.cecchino import cecchino_hr_history_cache as hr_cache
from app.services.cecchino.cecchino_historical_reliability import (
    build_historical_reliability_global_index,
    build_historical_reliability_index,
)
from app.services.cecchino.cecchino_kpi_panel_v2_betfair import _compute_rating
from app.services.cecchino.cecchino_market_opposition import PANEL_MARKET_KEYS
from app.services.cecchino.cecchino_purchasability_audit import (
    _iter_history_fixture_views,
    build_purchasability_rows,
    build_purchasability_rows_for_history,
    iter_purchasability_rows,
)
from app.services.cecchino.cecchino_purchasability_v31_hr import build_hr_history_context


# JSONB e' solo PostgreSQL: su SQLite lo trattiamo come JSON (stesso tipo Python in lettura).
@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):  # noqa: ARG001
    return "JSON"


DATE_TO = date(2026, 9, 30)


def _panel_row(rng: random.Random, key: str, *, legacy: bool = False) -> dict:
    book = round(rng.uniform(1.15, 6.0), 2)
    cec = round(book * rng.uniform(0.75, 1.25), 2)
    prob_c = round(1.0 / cec, 4)
    prob_b = round(1.0 / book, 4)
    vant = round(prob_c - prob_b, 4)
    edge = round((book / cec - 1.0) * 100.0, 2)
    row = {
        "segno": key,
        "label": key,
        "quota_book": book,
        "quota_cecchino": cec,
        "prob_book": prob_b,
        "prob_cecchino": prob_c,
        "vantaggio_prob": vant,
        "edge_pct": edge,
        "score_acquisto": round(prob_c * edge / 100.0, 4),
        "rating": _compute_rating(prob_c, vant, edge),
        "status": "available",
        "book_source": rng.choice(["betfair_raw_match_winner", "book", None]),
    }
    if not legacy:
        row["market_key"] = key
    if rng.random() < 0.1:
        row["prob_cecchino"] = None  # riga incompleta (non core)
    return row


def _make_fixture(rng: random.Random, i: int) -> CecchinoTodayFixture:
    scan_d = DATE_TO - timedelta(days=rng.randint(-3, 60))  # alcune dopo date_to (escluse)
    kickoff = datetime(scan_d.year, scan_d.month, scan_d.day, 18, 0, tzinfo=timezone.utc)
    pre = (kickoff - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    post = (kickoff + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    variant = i % 12

    rows = [_panel_row(rng, k, legacy=(variant == 9)) for k in PANEL_MARKET_KEYS]
    if variant == 10:
        rows.insert(3, "non-un-dict")  # righe sporche: vanno ignorate in entrambi i percorsi
        rows.append({"segno": "BTTS_YES", "quota_book": 1.8})
    panel_meta = {"last_betfair_refresh_at": pre if variant != 7 else post}
    panel: object = {
        "version": "cecchino_kpi_v2_betfair",
        "bookmaker": {"name": "Betfair", "provider_bookmaker_id": 11, "provider_source": "api_football"},
        "odds_meta": panel_meta,
        "rows": rows,
        "betfair_payload": {"zavorra": ["x" * 50] * 20},  # chiave pesante non letta dallo storico
    }
    snapshot: object = {"odds_meta": {}, "bookmakers": [{"zavorra": "y" * 200}]}
    odds_checked_at = None
    if variant == 1:  # timestamp da odds_snapshot_json.odds_meta
        panel["odds_meta"] = {}
        snapshot["odds_meta"] = {"odds_updated_at": pre}
    elif variant == 2:  # timestamp da odds_checked_at
        del panel["odds_meta"]
        odds_checked_at = kickoff - timedelta(hours=2)
    elif variant == 3:  # solo updated_at (fallback non verificato)
        panel["odds_meta"] = {}
        snapshot = None
    elif variant == 4:
        panel = None
    elif variant == 5:
        panel = {}
    elif variant == 6:
        del panel["bookmaker"]
    elif variant == 8:
        panel = [{"rows": rows}]  # JSON non-oggetto: nessuna riga
        snapshot = ["odds_meta"]

    finished = variant != 11
    ft_h, ft_a = rng.randint(0, 4), rng.randint(0, 4)
    ht_h, ht_a = min(ft_h, rng.randint(0, 2)), min(ft_a, rng.randint(0, 2))
    return CecchinoTodayFixture(
        id=i + 1,
        scan_date=scan_d,
        provider_source="api_football",
        provider_fixture_id=900_000 + i,
        local_fixture_id=(5000 + i) if i % 3 else None,
        competition_id=rng.choice([39, 135, 140, None]),
        league_name=rng.choice(["Premier", "Serie A", None]),
        home_team_name=f"Casa {i}",
        away_team_name=f"Ospiti {i}",
        kickoff=None if variant == 0 and i % 24 == 0 else kickoff,
        fixture_status="FT" if finished else "NS",
        match_display_status="finished" if finished else "upcoming",
        score_fulltime_home=ft_h if finished else None,
        score_fulltime_away=ft_a if finished else None,
        score_halftime_home=ht_h if finished else None,
        score_halftime_away=ht_a if finished else None,
        eligibility_status=ELIGIBILITY_ELIGIBLE,
        odds_checked_at=odds_checked_at,
        kpi_panel_json=panel,
        odds_snapshot_json=snapshot,
        cecchino_output_json={"zavorra": "z" * 500},
        raw_fixture_json={"zavorra": "r" * 500},
        stats_snapshot_json={"zavorra": "s" * 500},
        created_at=kickoff - timedelta(days=1),
        updated_at=kickoff + timedelta(hours=4),
    )


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    CecchinoTodayFixture.__table__.create(eng)
    rng = random.Random(20261020)
    with Session(eng) as s:
        s.add_all([_make_fixture(rng, i) for i in range(240)])
        s.commit()
    yield eng
    eng.dispose()


def _old_rows(eng, **kw):
    with Session(eng) as s:
        return build_purchasability_rows(s, **kw)


def _new_rows(eng, **kw):
    with Session(eng) as s:
        return build_purchasability_rows_for_history(s, **kw)


def test_light_loader_rows_identical_to_orm_loader(engine):
    old = _old_rows(engine, date_to=DATE_TO)
    new = _new_rows(engine, date_to=DATE_TO)
    assert len(old) > 1000
    assert any(r["is_settled_core"] for r in old)
    assert new == old


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"date_from": DATE_TO - timedelta(days=20), "date_to": DATE_TO},
        {"date_to": DATE_TO, "competition_id": 135},
    ],
)
def test_light_loader_same_filters(engine, kw):
    assert _new_rows(engine, **kw) == _old_rows(engine, **kw)


def test_light_loader_small_batches_same_order(engine):
    old = _old_rows(engine, date_to=DATE_TO)
    with Session(engine) as s:
        new = list(
            iter_purchasability_rows(
                _iter_history_fixture_views(
                    s, date_from=None, date_to=DATE_TO, competition_id=None, batch_size=7
                )
            )
        )
        # nessun oggetto ORM caricato nella sessione
        assert len(s.identity_map) == 0
    assert new == old


def test_hr_history_context_identical(engine):
    old_rows = _old_rows(engine, date_to=DATE_TO)
    old_ctx = {
        "history_rows": old_rows,
        "local_index": build_historical_reliability_index(old_rows),
        "global_index": build_historical_reliability_global_index(old_rows),
        "date_to": DATE_TO,
    }
    with Session(engine) as s:
        new_ctx = build_hr_history_context(s, date_to=DATE_TO)
    assert new_ctx["local_index"], "il dataset di test deve popolare gli indici"
    assert new_ctx["global_index"]
    assert new_ctx == old_ctx


def test_hr_cache_hit_shares_context_without_deepcopy(engine):
    hr_cache.clear_hr_history_cache()
    try:
        with Session(engine) as s:
            ctx1 = hr_cache.get_or_build_hr_history_context(s, date_to=DATE_TO)
            ctx2 = hr_cache.get_or_build_hr_history_context(s, date_to=DATE_TO)
        assert ctx2 == ctx1
        assert ctx2["history_rows"] is ctx1["history_rows"]
        assert ctx2 is not ctx1
    finally:
        hr_cache.clear_hr_history_cache()
