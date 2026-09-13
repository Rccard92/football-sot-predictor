"""Test del valutatore all'apertura e del test finale V3 (logica pura)."""

from __future__ import annotations

from datetime import date

from app.services.cecchino_v3.constants import (
    FINAL_MIN_LIFT,
    JUDGE_SEASONS,
    LOCKBOX,
    PHASE_BASELINE,
    PHASE_FEATURES,
    PHASES,
)
from app.services.cecchino_v3.evaluator import MarketRow


def _row(mid, key, season=LOCKBOX, p_v3=0.5, p_book=0.5, won=True, odds=2.0):
    return MarketRow(
        lab_match_id=mid,
        season_label=season,
        competition="Serie A",
        tier="top",
        match_date=date(2025, 9, 1),
        phase="mid",
        eligible=True,
        home_team="A",
        away_team="B",
        market_key=key,
        p_v3=p_v3,
        p_book=p_book,
        odds=odds,
        won=won,
    )


def test_final_phase_is_reference_model_plus_lockbox_only():
    assert 9 in PHASES and 9 not in PHASE_BASELINE
    final, reference = PHASE_FEATURES[9], PHASE_FEATURES[4]
    assert final.lockbox and not reference.lockbox
    assert (final.game, final.form, final.calendar, final.discipline, final.promotion, final.calibration) == (
        reference.game,
        reference.form,
        reference.calendar,
        reference.discipline,
        reference.promotion,
        reference.calibration,
    )
    assert not any(PHASE_FEATURES[p].lockbox for p in PHASES if p != 9)


def test_opening_rows_replace_quote_and_keep_only_available_markets():
    from app.services.cecchino_v3.evaluator_service import opening_market_rows

    rows = [_row(1, "HOME", odds=2.0, p_book=0.48), _row(1, "HOME_PT", odds=2.5, p_book=0.38)]
    out = opening_market_rows(rows, {(1, "HOME"): (2.2, 0.44)})
    assert len(out) == 1 and out[0].odds == 2.2 and out[0].p_book == 0.44 and out[0].p_v3 == rows[0].p_v3
    assert rows[0].odds == 2.0  # righe originali intatte


def test_accuracy_compares_v3_v2_book_on_common_rows():
    from app.services.cecchino_v3.final_service import accuracy

    rows = [
        _row(1, "HOME", p_v3=0.7, p_book=0.6, won=True),
        _row(1, "AWAY", p_v3=0.1, p_book=0.2, won=False),
        _row(2, "HOME", p_v3=0.4, p_book=0.4, won=False),  # senza V2: esclusa
    ]
    v2 = {(1, "HOME"): 0.5, (1, "AWAY"): 0.3}
    table = {(r["season"], r["family"]): r for r in accuracy(rows, v2, (LOCKBOX,))}
    one = table[(LOCKBOX, "FT_1X2")]
    assert one["n"] == 2
    assert abs(one["brier_v3"] - (0.3**2 + 0.1**2) / 2) < 1e-9
    assert abs(one["brier_v2"] - (0.5**2 + 0.3**2) / 2) < 1e-9
    assert one["v3_vs_v2_pct"] < 0
    assert table[(LOCKBOX, "HT_1X2")]["n"] == 0


def _accuracy_rows(v3_better=True):
    rows = []
    for family in ("FT_1X2", "DOUBLE_CHANCE", "FT_OVER_UNDER", "HT_1X2"):
        rows.append(
            {
                "season": LOCKBOX,
                "family": family,
                "n": 100,
                "brier_v3": 0.20 if v3_better else 0.22,
                "brier_v2": 0.21,
                "brier_book": 0.198,
                "v3_vs_book_pct": 1.0,
            }
        )
    return rows


def _patterns(lift, roi, pooled):
    return {
        "tally": {"per_season": [{"season": LOCKBOX, "tested": 100, "confirmed": int(25 * lift), "expected": 25.0, "lift": lift}]},
        "always_confirmed": {"bets": 50, "roi_pct": roi, "pooled_roi_pct": pooled},
    }


def test_final_exam_rules():
    from app.services.cecchino_v3.final_service import final_exam

    ok_integrity = {"passed": True}
    v2 = {"tally": {"lift": 1.0}, "always_confirmed": {"pooled_roi_pct": -5.0}}
    exam = final_exam(ok_integrity, _accuracy_rows(), _patterns(FINAL_MIN_LIFT + 0.1, 3.0, 2.0), v2)
    assert exam == {"F0": True, "F1": True, "F1_available": True, "F2": True, "F3": True, "passed": True}

    exam = final_exam(ok_integrity, _accuracy_rows(v3_better=False), _patterns(1.0, -1.0, -6.0), v2)
    assert not exam["F1"] and not exam["F2"] and exam["F3"] is False and not exam["passed"]

    exam = final_exam({"passed": False}, _accuracy_rows(), _patterns(1.3, 3.0, 2.0), None)
    assert exam["F3"] is None and not exam["passed"]
    assert JUDGE_SEASONS[-1] < LOCKBOX
