"""Test storico indice + pattern: fasce da 10 e accordo con i pattern."""

from __future__ import annotations

import numpy as np

from app.services.cecchino_v25 import index_pattern_accord as acc


def _rows():
    return acc.SeasonRows(
        market=np.array(["HOME", "AWAY", "DRAW", "OVER_2_5", "HOME"], dtype=object),
        match_id=np.array([1, 1, 2, 3, 4]),
        score=np.array([95.0, 30.0, 75.0, 55.0, 72.0]),
        won=np.array([1.0, 0.0, 0.0, 1.0, 1.0]),
        base=np.array([0.44, 0.30, 0.26, 0.5, 0.44]),
        quota=np.array([1.8, 4.0, 3.2, 1.9, np.nan]),
    )


def test_bands_cover_100_and_split_rows():
    bands = acc.index_bands(_rows())
    assert list(bands)[-1] == "90-100" and bands["90-100"]["rows"] == 1
    assert sum(b.get("rows", 0) for b in bands.values()) == 5


def test_accord_confirmed_conflict_and_none():
    fired = {("HOME", 1): 2, ("UNDER_2_5", 3): 1}
    out = acc.season_accord(_rows(), fired)
    preds = out["predizioni_indice_70+"]
    assert preds["tutte"]["rows"] == 3
    assert preds["confermate_dal_pattern"]["rows"] == 1 and preds["confermate_dal_pattern"]["roi_pct"] == 80.0
    assert preds["senza_pattern"]["rows"] == 2
    pat = out["pattern_acceso"]
    assert pat["tutti"]["rows"] == 1 and pat["indice_d_accordo_e_2+_pattern"]["rows"] == 1
    # l'Over 2.5 della partita 3 e' in contrasto con l'Under 2.5 acceso, ma ha punteggio 55: non e' una predizione
    assert out["confermate_per_fascia"]["90-100"]["rows"] == 1


def test_book_conditions_excluded():
    assert acc._clean([{"column": "quota", "value": "Q2"}], acc.V3_EXCLUDED_COLUMNS) is None
    assert acc._clean([{"column": "livello", "value": "top"}], acc.V3_EXCLUDED_COLUMNS) is None
    assert acc._clean([{"column": "equilibrio", "value": "alto"}], acc.V3_EXCLUDED_COLUMNS) == [("equilibrio", "alto")]
