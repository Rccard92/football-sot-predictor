"""Calcolo del giorno, letture e rotte V4 con motori finti (nessun calcolo pesante, nessuna rete)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.models.cecchino_v4 import CecchinoV4Fixture, CecchinoV4OddsSnapshot, CecchinoV4Prediction, CecchinoV4Explanation
from app.routes import cecchino_v4 as v4_routes
from app.services.cecchino_v4 import serving
from app.services.cecchino_v4.pipeline import day as day_mod

DAY = date(2026, 9, 19)
NOW = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)


def _goals_payload(p_away: float = 0.50, level: str = "bassa") -> dict:
    p_home = 0.30 if p_away >= 0.45 else 0.45
    p_draw = round(1.0 - p_home - p_away, 4)
    lines = {"HOME": p_home, "DRAW": p_draw, "AWAY": p_away, "OVER_2_5": 0.55, "UNDER_2_5": 0.45, "ONE_X": p_home + p_draw, "X_TWO": p_draw + p_away, "ONE_TWO": p_home + p_away}
    return {
        "engine_version": "test",
        "lambda_home": 1.2,
        "lambda_away": 1.6,
        "rho": -0.05,
        "ht_share": 0.44,
        "dispersion": {"home": None, "away": None},
        "uncertainty": {"score": 0.2, "level": level, "home_evidence": 30, "away_evidence": 28, "disagreement": 0.05, "new_team_home": False, "new_team_away": False},
        "markets": {k: {"p": v, "lo": max(0.01, v - 0.04), "hi": min(0.99, v + 0.04)} for k, v in lines.items()},
        "ratings": {
            "home": {"attack": 0.1, "defence": 0.0, "attack_rank": 5, "defence_rank": 8, "teams_in_division": 20, "home_advantage": 0.2},
            "away": {"attack": 0.3, "defence": -0.1, "attack_rank": 1, "defence_rank": 3, "teams_in_division": 20, "home_advantage": 0.15},
        },
        "specialists": {"forza": {"home": 1.2, "away": 1.6}, "sot": {"home": 1.1, "away": 1.7}, "shots": {"home": 1.2, "away": 1.5}, "weights": {"forza": 0.5, "sot": 0.2, "shots": 0.3},
                        "form": {"goals_home": 0.0, "goals_away": 0.05, "shots_home": 0.02, "shots_away": 0.1, "matches_home": 5, "matches_away": 5},
                        "calendar": {"rest_days_home": 7, "rest_days_away": 4, "final_phase": False}},
        "calibration": {"applied": True, "season": "2025/2026"},
    }


def _stats_payload() -> dict:
    def side(mean):
        return {"mean": mean, "dispersion": None, "division_mean": 4.6, "rank_for": 3, "rank_against": 9, "teams_in_division": 20, "evidence": 30,
                "lines": {f"{x + 0.5}": {"over": max(0.02, min(0.98, 1 - (x + 0.5) / (2 * mean))), "lo": 0.5, "hi": 0.7} for x in range(2, 10)}}
    return {"engine_version": "test", "stats": {"sot": {"exam": "superato", "home": side(4.9), "away": side(6.8), "total": side(11.7)}}}


def _fixture(db, home="Milan", away="Inter", kickoff_hour=18, odds=None, status="NS"):
    f = CecchinoV4Fixture(
        api_fixture_id=-abs(hash((home, away))) % 10**9,
        league_code="I1",
        api_league_id=135,
        competition="Serie A",
        season_label="2026/2027",
        match_date=DAY,
        kickoff_at=datetime(2026, 9, 19, kickoff_hour, 45, tzinfo=timezone.utc),
        status=status,
        home_team_api_id=1,
        away_team_api_id=2,
        home_team=home,
        away_team=away,
        home_team_history=home,
        away_team_history=away,
    )
    db.add(f)
    db.flush()
    if odds:
        for bk, markets in odds.items():
            db.add(CecchinoV4OddsSnapshot(fixture_id=f.id, bookmaker_id=bk, kind="mattina", taken_at=NOW, markets_json=markets, created_at=NOW))
    db.flush()
    return f


@pytest.fixture()
def seeded(v4_db):
    f1 = _fixture(v4_db, odds={8: {"HOME": 3.1, "DRAW": 3.4, "AWAY": 2.6, "OVER_2_5": 1.9, "UNDER_2_5": 1.95, "STAT:sot:away:over:6.5": 1.85}, 3: {"AWAY": 2.65}})
    f2 = _fixture(v4_db, "Bologna", "Torino", 15, odds={8: {"HOME": 2.0, "DRAW": 3.3, "AWAY": 3.9}})
    v4_db.commit()
    return f1, f2


def _fake_goals(history_matches, targets, _cfg):
    return {t["key"]: _goals_payload() for t in targets}


def _fake_stats(history, targets, _cfg):
    return {t["key"]: _stats_payload() for t in targets}


class _FakeHistory:
    matches: list = []
    extras: dict = {}


def test_build_days_writes_predictions_explanations_and_shortlist(v4_db, seeded):
    f1, f2 = seeded
    report = day_mod.build_days(v4_db, days=[DAY], now=NOW, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory())
    assert report.fixtures == 2 and report.predicted == 2
    preds = v4_db.query(CecchinoV4Prediction).all()
    assert {(p.fixture_id, p.kind) for p in preds} == {(f1.id, "goals"), (f1.id, "stats"), (f2.id, "goals"), (f2.id, "stats")}
    expl = {e.fixture_id: e.payload_json for e in v4_db.query(CecchinoV4Explanation).all()}
    assert set(expl) == {f1.id, f2.id}
    blocks = expl[f1.id]["blocks"]
    assert set(blocks) >= {"who", "how", "context", "predicts", "why"}
    assert blocks["predicts"]["markets"], "la tabella mercati deve avere righe"
    card = expl[f1.id]["card"]
    assert card["home_team"] == "Milan" and card["most_likely"]["market_key"] == "AWAY"
    # segno 2 a 2,60 con probabilita' prudente ~43%: profitto atteso sopra il 3% -> giocata
    assert card["best_play"] is not None
    sl = serving.shortlist(v4_db, DAY)
    assert sl["status"] == "provvisoria" and len(sl["items"]) >= 1
    assert sl["items"][0]["rank"] == 1 and sl["items"][0]["top"] is True
    # ricalcolo idempotente: sostituisce, non duplica
    day_mod.build_days(v4_db, days=[DAY], now=NOW, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory())
    assert v4_db.query(CecchinoV4Prediction).count() == 4
    assert v4_db.query(CecchinoV4Explanation).count() == 2


def test_serving_days_and_fixtures_after_build(v4_db, seeded):
    day_mod.build_days(v4_db, days=[DAY], now=NOW, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory())
    d = serving.days(v4_db, DAY, 2)
    assert d["days"][0]["fixtures"] == 2 and d["days"][0]["plays"] >= 1 and d["days"][1]["fixtures"] == 0
    fx = serving.fixtures(v4_db, DAY, sort="profit")
    assert len(fx["items"]) == 2
    only = serving.fixtures(v4_db, DAY, only_plays=True)
    assert all(c["best_play"] for c in only["items"])
    detail = serving.fixture_detail(v4_db, seeded[0].id)
    assert detail["fixture"]["home_team"] == "Milan" and detail["blocks"]["who"]["sentence"]
    with pytest.raises(serving.NotFound):
        serving.fixture_detail(v4_db, 99999)


def test_serving_before_build_gives_fallback_cards(v4_db, seeded):
    fx = serving.fixtures(v4_db, DAY)
    assert len(fx["items"]) == 2
    assert fx["items"][0]["best_play"] is None and fx["items"][0]["no_play_reason"] == "in_attesa_calcolo"


def test_settle_finished_updates_items(v4_db, seeded):
    f1, _ = seeded
    day_mod.build_days(v4_db, days=[DAY], now=NOW, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory())
    f1.status = "FT"
    f1.ft_home, f1.ft_away, f1.ht_home, f1.ht_away = 0, 2, 0, 1
    f1.stats_json = {"home": {"sot": 3, "shots": 9, "corners": 4, "yellow": 2, "red": 0, "fouls": 11}, "away": {"sot": 8, "shots": 15, "corners": 6, "yellow": 1, "red": 0, "fouls": 9}}
    v4_db.add(CecchinoV4OddsSnapshot(fixture_id=f1.id, bookmaker_id=8, kind="chiusura", taken_at=NOW + timedelta(hours=10), markets_json={"AWAY": 2.1, "STAT:sot:away:over:6.5": 1.7}, created_at=NOW))
    v4_db.commit()
    n = day_mod.settle_finished(v4_db, now=NOW + timedelta(hours=12))
    assert n >= 1
    sl = serving.shortlist(v4_db, DAY)
    settled = [i for i in sl["items"] if i["fixture_id"] == f1.id]
    assert settled and settled[0]["result"] in {"vinta", "persa", "void", "mezza_vinta", "mezza_persa"}
    m = serving.measure_summary(v4_db)
    assert m["totals"]["plays"] >= 1


def test_routes_read_endpoints(v4_db, seeded, monkeypatch):
    day_mod.build_days(v4_db, days=[DAY], now=NOW, goals_predictor=_fake_goals, stats_predictor=_fake_stats, history=_FakeHistory())
    app = FastAPI()
    app.include_router(v4_routes.router, prefix="/api")
    app.include_router(v4_routes.admin_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: v4_db
    client = TestClient(app)
    assert client.get("/api/cecchino/v4/status").status_code == 200
    r = client.get(f"/api/cecchino/v4/fixtures?date={DAY.isoformat()}&league=I1")
    assert r.status_code == 200 and len(r.json()["items"]) == 2
    r = client.get(f"/api/cecchino/v4/fixtures/{seeded[0].id}")
    assert r.status_code == 200 and r.json()["blocks"]["predicts"]["markets"]
    assert client.get("/api/cecchino/v4/fixtures/424242").status_code == 404
    assert client.get("/api/cecchino/v4/fixtures?date=non-una-data").status_code == 422
    r = client.get(f"/api/cecchino/v4/shortlist?date={DAY.isoformat()}")
    assert r.status_code == 200 and r.json()["items"]
    assert client.get("/api/cecchino/v4/engine/exams").status_code == 200
    assert client.get("/api/cecchino/v4/engine/data").status_code == 200
    assert client.get("/api/cecchino/v4/measure/summary").status_code == 200
    # senza sessione admin le azioni sono chiuse (503 non configurata o 401)
    assert client.post("/api/admin/cecchino/v4/jobs/predict/run").status_code in (401, 503)
