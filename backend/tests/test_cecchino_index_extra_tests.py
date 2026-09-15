"""Test 1-2-3 sull'indice: apertura, accordo V2.5/V3, una giocata per partita."""

from __future__ import annotations

import numpy as np

from app.services.cecchino_v25 import index_extra_tests as ext
from app.services.cecchino_v25.index_pattern_accord import SeasonRows


def _rows(scores, markets=("UNDER_2_5", "UNDER_1_5", "HOME", "DRAW"), ids=(1, 1, 1, 2), won=(1, 0, 1, 0), quota=(1.6, 2.5, 1.9, 3.3)):
    return SeasonRows(
        market=np.array(markets, dtype=object), match_id=np.array(ids), score=np.array(scores, dtype=float),
        won=np.array(won, dtype=float), base=np.full(len(ids), 0.4), quota=np.array(quota, dtype=float),
    )


def test_one_per_match_keeps_strongest():
    out = ext.test_one_per_match({"2022/2023": _rows([92, 80, 75, 71])})["stagioni"]["2022/2023"]
    assert out["tutte_le_predizioni_70+"]["rows"] == 4
    assert out["solo_la_piu_forte_per_partita"]["rows"] == 2
    # per famiglia: nella partita 1 restano Under 2.5 (gol) e 1 (esito)
    assert out["la_piu_forte_per_famiglia"]["rows"] == 3


def test_opening_compares_same_rows():
    rows = {"2022/2023": _rows([95, 40, 91, 72])}
    opening = {1: {"HOME": 2.1, "UNDER_2_5": 1.7}, 2: {"DRAW": 3.5}}
    closing = {1: {"HOME": 1.9, "UNDER_2_5": 1.6}, 2: {"DRAW": 3.3}}
    out = ext.test_opening(rows, opening, closing)["complessivo"]["90-100"]
    assert out["chiusura"]["rows"] == out["apertura"]["rows"] == 2
    assert out["apertura"]["roi_pct"] == 90.0 and out["chiusura"]["roi_pct"] == 75.0


def test_agreement_joins_on_match_and_market():
    a = _rows([95, 30, 60, 91])
    b = _rows([93, 20, 92, 40])
    out = ext.test_agreement({"2022/2023": a}, {"2022/2023": b})
    assert out["righe_in_comune"] == 4 and out["entrambi_90+"]["rows"] == 1
    assert out["V2.5_90+_e_V3_sotto_50"]["rows"] == 1
