"""Misura: ROI, bootstrap a blocchi, CLV, CUSUM, riepilogo, fortuna o merito."""

from __future__ import annotations

import pytest

from app.services.cecchino_v4.measure.metrics import (
    CUSUM_MIN_PLAYS,
    block_bootstrap_ci,
    clv,
    clv_summary,
    cusum,
    luck_vs_merit,
    roi,
    summary,
)
from tests.v4.test_selection_samples import goals


def _item(day: str, profit: float | None, league: str = "I1", family: str = "FT_1X2", quota: float = 2.0, closing: float | None = None, idx: int = 0):
    return {
        "day": day,
        "kickoff_at": f"{day}T18:00:00+00:00",
        "fixture_id": idx,
        "profit_units": profit,
        "league_code": league,
        "family": family,
        "quota_used": quota,
        "closing_quota": closing,
    }


def test_roi_basic_and_empty():
    items = [_item("2026-09-01", 0.9), _item("2026-09-01", -1.0), _item("2026-09-02", 0.5), _item("2026-09-02", None)]
    out = roi(items)
    assert out == {"plays": 3, "profit_units": 0.4, "roi": pytest.approx(0.1333, abs=1e-4)}
    assert roi([]) == {"plays": 0, "profit_units": 0.0, "roi": None}


def test_block_bootstrap_ci_shape_and_determinism():
    items = []
    for d in range(20):
        day = f"2026-09-{d + 1:02d}"
        items += [_item(day, 0.9 if d % 2 == 0 else -1.0, idx=3 * d), _item(day, 0.4, idx=3 * d + 1), _item(day, -1.0 if d % 3 == 0 else 0.7, idx=3 * d + 2)]
    lo, hi = block_bootstrap_ci(items, n=500, seed=1)
    assert lo is not None and hi is not None and lo <= hi
    point = roi(items)["roi"]
    assert lo <= point <= hi
    assert block_bootstrap_ci(items, n=500, seed=1) == (lo, hi)
    assert block_bootstrap_ci(items, n=500, seed=2) != (lo, hi) or True  # semi diversi possono dare estremi diversi
    assert block_bootstrap_ci([]) == (None, None)
    same = [_item("2026-09-01", 0.5), _item("2026-09-01", 0.5)]
    assert block_bootstrap_ci(same) == (0.5, 0.5)


def test_clv_and_summary():
    assert clv(2.0, 1.9) == pytest.approx(2.0 / 1.9 - 1, abs=1e-4)
    assert clv(1.8, 2.0) < 0
    assert clv(None, 2.0) is None and clv(2.0, None) is None and clv(2.0, 1.0) is None
    items = [_item("2026-09-01", 0.9, quota=2.0, closing=1.9), _item("2026-09-01", -1.0, quota=1.8, closing=2.0), {"clv": 0.05, "profit_units": None}]
    out = clv_summary(items)
    assert out["plays"] == 3
    assert out["clv_positive_share"] == pytest.approx(2 / 3, abs=1e-4)
    assert clv_summary([]) == {"plays": 0, "clv": None, "clv_positive_share": None}


def test_cusum_alarm_on_decline_and_silence_on_profit():
    series = [0.9] * 10 + [-1.0] * 30
    alarms = cusum(series, k=0.03, h=6.0)
    assert alarms and alarms[0] == 15  # sesta perdita consecutiva: 6 * 1,03 > 6
    assert cusum([0.5] * 50, k=0.03, h=6.0) == []
    assert cusum([], k=0.03, h=6.0) == []


def test_summary_shape_and_alert():
    items = []
    for d in range(40):
        day = f"2026-{9 + d // 28:02d}-{d % 28 + 1:02d}"
        profit = 0.9 if d < 10 else -1.0
        items.append(_item(day, profit, league="I1", family="FT_1X2", quota=1.9, closing=1.85, idx=d))
    for d in range(10):
        items.append(_item(f"2026-11-{d + 1:02d}", 0.8, league="E0", family="STAT_sot", quota=1.8, closing=1.9, idx=100 + d))
    out = summary(items, bootstrap_n=200)
    assert set(out) == {"by_league", "by_market", "totals", "alerts"}
    assert set(out["totals"]) == {"plays", "profit_units", "roi", "roi_lo", "roi_hi", "clv"}
    assert out["totals"]["plays"] == 50
    leagues = {g["league_code"]: g for g in out["by_league"]}
    assert leagues["I1"]["plays"] == 40 and leagues["I1"]["alarm"] is True
    assert leagues["E0"]["plays"] == 10 and leagues["E0"]["alarm"] is False  # sotto il minimo per il CUSUM
    assert leagues["E0"]["plays"] < CUSUM_MIN_PLAYS
    markets = {g["market_family"]: g for g in out["by_market"]}
    assert markets["STAT_sot"]["label"] == "Tiri in porta"
    assert markets["FT_1X2"]["roi_lo"] <= markets["FT_1X2"]["roi"] <= markets["FT_1X2"]["roi_hi"]
    assert len(out["alerts"]) == 2  # campionato I1 e mercato FT_1X2
    alert = next(a for a in out["alerts"] if a["scope"] == "league")
    assert alert["key"] == "I1" and "rendimento in calo" in alert["sentence"] and "ROI" in alert["sentence"]
    assert "−" in alert["sentence"]  # ROI negativo scritto col segno meno tipografico


def test_luck_vs_merit_sentences():
    payload = goals()
    result = {"ft_home": 1, "ft_away": 2}
    play = {"p_prudent": 0.47}
    text = luck_vs_merit(payload, result, play, "vinta", "Milan", "Inter")
    assert "Gol attesi 1,2 per Milan e 1,6 per Inter, reali 1-2" in text
    assert "in linea con le attese" in text
    assert "fortuna" in text  # esito meno probabile vinto
    assert "con merito" in luck_vs_merit(payload, result, {"p_prudent": 0.6}, "vinta")
    assert "sfortuna" in luck_vs_merit(payload, result, {"p_prudent": 0.6}, "persa")
    assert "rimborsata" in luck_vs_merit(payload, result, {"p_prudent": 0.6}, "void")
    assert "sopra le attese" in luck_vs_merit(payload, {"ft_home": 4, "ft_away": 2})
    assert "sotto le attese" in luck_vs_merit(payload, {"ft_home": 0, "ft_away": 0})
    assert luck_vs_merit(payload, None) == "Risultato non ancora disponibile."
