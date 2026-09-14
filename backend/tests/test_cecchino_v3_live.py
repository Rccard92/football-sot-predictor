"""V3 estesa: parametri congelati, contesto di stagione dal calendario, calcolo su dati sintetici, payload registro."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.cecchino_live.registry import v3_payload
from app.services.cecchino_v3.constants import PHASE_EARLY, PHASE_FINAL, PHASE_MID
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3_live.engine import _annotate_context, predict_records
from app.services.cecchino_v3_live.params import _from_summary, fallback_params

_EPOCH = date(2000, 1, 1)


def test_params_from_final_run_summary_use_last_season():
    summary = {
        "orchestrator_weights": {
            "2024/2025": {"intercept": 0.0, "forza": 1.0, "sot": 0.0, "shots": 0.0},
            "2025/2026": {"intercept": -0.03, "forza": 0.49, "sot": 0.26, "shots": 0.34, "form_shots": 0.2},
        },
        "base_orchestrator_weights": {"2025/2026": {"intercept": -0.04, "forza": 0.46, "sot": 0.28, "shots": 0.38}},
        "chosen_hyper": {"2025/2026": {"xi": 0.002, "sigma": 0.4}},
        "game_chosen_hyper": {"sot": {"2025/2026": {"xi": 0.004, "sigma": 0.4}}, "shots": {"2025/2026": {"xi": 0.004, "sigma": 0.4}}},
    }
    p = _from_summary(11, summary)
    assert p.season == "2025/2026" and p.source_run_id == 11
    assert p.weights["form_shots"] == 0.2 and p.base_weights["forza"] == 0.46
    assert (p.hyper_forza.xi, p.hyper_sot.xi) == (0.002, 0.004)
    assert fallback_params().weights["forza"] == 0.488955


def _record(mid: int, day: date, home: str, away: str, season: str = "2026", **kw) -> MatchRecord:
    return MatchRecord(
        lab_match_id=mid, competition="api:1", group="api:1", season_label=season, match_date=day,
        kickoff_at=datetime(day.year, day.month, day.day, 18, tzinfo=timezone.utc), day=(day - _EPOCH).days,
        home_team=home, away_team=away, ft_home=kw.get("fh", 1), ft_away=kw.get("fa", 1), ht_home=0, ht_away=0,
        home_shots=kw.get("hs"), away_shots=kw.get("as_"), home_sot=kw.get("ht"), away_sot=kw.get("at"),
    )


def test_annotate_context_uses_full_season_calendar():
    start = date(2026, 3, 1)
    fixtures, records = [], []
    for k in range(12):
        day = start + timedelta(days=7 * k)
        status = "FT" if k < 8 else "NS"
        fixtures.append(SimpleNamespace(id=k + 1, competition_id=1, home_team_id=1 if k % 2 == 0 else 2,
                                        away_team_id=2 if k % 2 == 0 else 1, status=status,
                                        kickoff_at=datetime(day.year, day.month, day.day, 18, tzinfo=timezone.utc)))
        if k <= 8:
            records.append(_record(k + 1, day, "1" if k % 2 == 0 else "2", "2" if k % 2 == 0 else "1"))
    _annotate_context(records, fixtures, {1: "2026"})
    target = records[-1]  # 9a partita: 8 giocate, 4 rimanenti (questa inclusa)
    assert (target.home_played, target.home_remaining) == (8, 4)
    assert target.phase == PHASE_FINAL
    assert records[2].phase == PHASE_EARLY
    fixtures += [SimpleNamespace(id=100 + k, competition_id=1, home_team_id=1, away_team_id=2, status="NS",
                                 kickoff_at=datetime(2026, 12, 1, tzinfo=timezone.utc) + timedelta(days=k)) for k in range(10)]
    _annotate_context(records, fixtures, {1: "2026"})
    assert target.phase == PHASE_MID


def test_annotate_context_with_incomplete_calendar_uses_previous_season_length():
    def fx(i, comp, day, status):
        return SimpleNamespace(id=i, competition_id=comp, home_team_id=1 if i % 2 else 2, away_team_id=2 if i % 2 else 1,
                               status=status, kickoff_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=day))
    fixtures = [fx(k, 1, k * 7, "FT") for k in range(1, 31)]  # stagione precedente: 30 partite a squadra
    fixtures += [fx(100 + k, 2, 400 + k * 7, "FT") for k in range(23)]  # in corso: 23 giocate, calendario futuro assente
    fixtures.append(fx(200, 2, 400 + 23 * 7, "NS"))
    day = date(2025, 1, 1) + timedelta(days=400 + 23 * 7)
    target = _record(200, day, "2", "1", "2026")
    _annotate_context([target], fixtures, {1: "2025", 2: "2026"})
    assert (target.home_played, target.home_remaining) == (23, 7)
    assert target.phase == PHASE_MID


def test_predict_records_on_synthetic_league_gives_coherent_probabilities():
    rng = random.Random(7)
    teams = [str(t) for t in range(1, 9)]
    strength = {t: 0.8 + 0.1 * int(t) for t in teams}
    records: list[MatchRecord] = []
    mid = 0
    day = date(2025, 3, 1)
    for season in ("2025", "2026"):
        for rnd in range(14):
            order = teams[:]
            rng.shuffle(order)
            for i in range(0, len(order), 2):
                h, a = order[i], order[i + 1]
                mid += 1
                gh = min(6, int(rng.expovariate(1 / strength[h])))
                ga = min(6, int(rng.expovariate(1 / strength[a])))
                records.append(_record(mid, day, h, a, season, fh=gh, fa=ga, hs=10 + gh * 2, as_=9 + ga * 2, ht=3 + gh, at=3 + ga))
            day += timedelta(days=7)
    target = _record(mid + 1, day, "8", "1", "2026")
    records.append(target)
    for m in records:
        m.home_played = m.away_played = 10
        m.home_remaining = m.away_remaining = 10
        m.eval_eligible = True
        m.phase = PHASE_MID
    finals = predict_records(records, fallback_params())
    fin = finals[target.lab_match_id]
    probs = fin["probabilities"]
    assert abs(probs["HOME"] + probs["DRAW"] + probs["AWAY"] - 1.0) < 1e-9
    assert abs(probs["OVER_2_5"] + probs["UNDER_2_5"] - 1.0) < 1e-9
    assert fin["lambda_home"] > 0 and fin["lambda_away"] > 0
    assert set(fin["specialists"]) >= {"forza", "sot", "shots", "weights", "form", "calendar"}
    assert "equilibrio" in fin["indices"]


def test_v3_payload_uses_real_bet365_quotes_and_no_purchasability():
    probs = {k: 0.0 for k in ("HOME", "DRAW", "AWAY", "ONE_X", "X_TWO", "ONE_TWO", "HOME_PT", "DRAW_PT", "AWAY_PT",
                              "OVER_0_5", "UNDER_0_5", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5")}
    probs.update({"HOME": 0.5, "DRAW": 0.3, "AWAY": 0.2, "OVER_2_5": 0.55, "UNDER_2_5": 0.45})
    kpi = {"rows": [
        {"market_key": "HOME", "quota_book": 2.1}, {"market_key": "DRAW", "quota_book": 3.4}, {"market_key": "AWAY", "quota_book": 4.0},
        {"market_key": "OVER_2_5", "quota_book": 1.9, "book_fallback_used": True},
    ]}
    result = {"probabilities": probs, "lambda_home": 1.5, "lambda_away": 1.0, "eligible": True, "indices": {}, "specialists": {}}
    markets, modules = v3_payload(result, kpi)
    assert markets["HOME"]["quota_book"] == 2.1
    assert round(markets["HOME"]["edge_pct"], 1) == 5.0
    assert markets["HOME"]["prob_book_fair"] is not None
    assert markets["HOME"]["buyability_score"] is None
    assert modules["expected_goals"] == {"home": 1.5, "away": 1.0}
    assert modules["eligibility"] == "ok"
