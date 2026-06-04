from app.services.cecchino.cecchino_statistical_kpi import build_statistical_kpi_odds
from tests.test_cecchino_engine_excel_parity import _san_lorenzo_riestra_input


def _v02_snapshot() -> dict:
    inp = _san_lorenzo_riestra_input()
    ha_h, ha_a = inp.home_away
    tot_h, tot_a = inp.totals
    l5_h, l5_a = inp.last5_home_away
    l6_h, l6_a = inp.last6_totals

    def blk(w, d, l):
        s = w + d + l
        return {"wdl": {"wins": w, "draws": d, "losses": l}, "sample_count": s}

    return {
        "home_context": blk(ha_h.wins, ha_h.draws, ha_h.losses),
        "away_context": blk(ha_a.wins, ha_a.draws, ha_a.losses),
        "home_total": blk(tot_h.wins, tot_h.draws, tot_h.losses),
        "away_total": blk(tot_a.wins, tot_a.draws, tot_a.losses),
        "home_recent_context_5": blk(l5_h.wins, l5_h.draws, l5_h.losses),
        "away_recent_context_5": blk(l5_a.wins, l5_a.draws, l5_a.losses),
        "home_recent_total_6": blk(l6_h.wins, l6_h.draws, l6_h.losses),
        "away_recent_total_6": blk(l6_a.wins, l6_a.draws, l6_a.losses),
    }


def test_statistical_kpi_san_lorenzo_approx():
    out = build_statistical_kpi_odds(_v02_snapshot())
    assert out["status"] == "available"
    assert abs(out["odd_1"] - 2.29) < 0.15
    assert abs(out["odd_x"] - 2.67) < 0.15
    assert abs(out["odd_2"] - 5.52) < 0.25
    assert abs(out["odd_1x"] - 1.23) < 0.15
    assert abs(out["odd_x2"] - 1.80) < 0.15
    assert abs(out["odd_12"] - 1.62) < 0.15
