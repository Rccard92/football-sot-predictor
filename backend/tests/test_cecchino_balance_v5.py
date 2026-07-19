"""Test Equilibrio vs Squilibrio v5 — modulo canonico cecchino_balance_v5_v2."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.encoders import jsonable_encoder

from app.services.cecchino.cecchino_balance_analysis import (
    VERSION as LEGACY_VERSION,
    build_cecchino_balance_analysis,
    compute_dominance_pp,
)
from app.services.cecchino.cecchino_balance_v5 import (
    PILLAR_ORDER,
    VERSION,
    build_cecchino_balance_v5,
    classify_conviction,
    classify_gap_coherence,
    conviction_index,
    dominant_side_to_market_label,
    gap_coherence_index,
    probability_balance_index,
)
from app.services.cecchino.cecchino_icm_analysis import build_cecchino_icm_analysis
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY,
    SEL_DRAW,
    SEL_HOME,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
)

ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "balance_v5_parity" / "live_consumer_slices.json"

BETTING_PHRASES = (
    "x / under",
    "da giocare",
    "interessante",
    "tipica partita",
    "procedere con cautela",
    "orientata verso",
    "value bet",
    "stake",
)


def _final(**kwargs):
    defaults = dict(
        status="available",
        quota_1=2.10,
        quota_x=3.40,
        quota_2=3.60,
        prob_1=0.42,
        prob_x=0.28,
        prob_2=0.30,
    )
    defaults.update(kwargs)
    return defaults


def _kpi_with_book():
    return {
        "version": "cecchino_kpi_v2_betfair",
        "rows": [
            {
                "market_key": SEL_HOME,
                "quota_cecchino": 2.1,
                "quota_book": 2.2,
                "prob_book": 0.40,
                "prob_cecchino": 0.42,
            },
            {
                "market_key": SEL_DRAW,
                "quota_cecchino": 3.4,
                "quota_book": 3.5,
                "prob_book": 0.28,
                "prob_cecchino": 0.28,
            },
            {
                "market_key": SEL_AWAY,
                "quota_cecchino": 3.6,
                "quota_book": 3.7,
                "prob_book": 0.27,
                "prob_cecchino": 0.30,
            },
            {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9},
            {"market_key": SEL_OVER_2_5, "quota_cecchino": 2.05, "quota_book": 2.1},
        ],
    }


def test_f36_01_formula_invariata():
    v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=2.82, quota_2=7.77))
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.82,
        quota_cecchino_x=3.4,
        quota_cecchino_2=7.77,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    assert v5["pillars"]["f36"]["index"] == bal["f36"]["score"]
    assert abs(bal["f36"]["signed"] - (7.77 - 2.82)) < 0.001


def test_f36_02_soglie():
    cases = [
        (2.50, 2.90, 100, "Equilibrio forte"),
        (2.00, 2.80, 80, "Equilibrio"),
        (2.00, 3.20, 60, "Transizione"),
        (1.80, 4.00, 40, "Squilibrio"),
    ]
    for q1, q2, score, label in cases:
        v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=q1, quota_2=q2))
        assert v5["pillars"]["f36"]["index"] == score
        assert v5["pillars"]["f36"]["class_label"] == label


def test_f36_03_05_direction():
    d1 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=2.0, quota_2=3.0))
    assert d1["pillars"]["f36"]["direction"] == "1"
    d2 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=3.0, quota_2=2.0))
    assert d2["pillars"]["f36"]["direction"] == "2"
    neut = build_cecchino_balance_v5(cecchino_final=_final(quota_1=2.5, quota_2=2.5))
    assert neut["pillars"]["f36"]["direction"] is None


def test_dominance_06_10():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(prob_1=0.50, prob_x=0.25, prob_2=0.25)
    )
    dom = v5["pillars"]["dominance"]
    assert dom["status"] == "official"
    expected = conviction_index(50.0, 25.0, 25.0)
    assert abs(dom["index"] - expected) < 0.01
    assert dom["direction"] == "1"
    assert classify_conviction(10) == "Molto Debole"
    assert classify_conviction(30) == "Debole"
    assert classify_conviction(50) == "Moderata"
    assert classify_conviction(70) == "Forte"
    assert classify_conviction(90) == "Molto Forte"
    blob = json.dumps(dom).lower()
    assert "research" not in blob
    assert "candidate" not in blob


def test_draw_cred_11_18():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(prob_1=0.30, prob_x=0.40, prob_2=0.30, quota_x=3.10),
        kpi_panel=_kpi_with_book(),
    )
    dc = v5["pillars"]["draw_credibility"]
    assert dc["status"] == "descriptive_official"
    assert dc["index"] == pytest.approx(40.0)
    assert dc["class_label"] == "Pareggio forte"
    assert "book" not in json.dumps(dc).lower()
    reading = (dc.get("reading") or "").lower()
    for phrase in BETTING_PHRASES:
        assert phrase not in reading


def test_gap_19_23():
    v5 = build_cecchino_balance_v5(cecchino_final=_final())
    gap = v5["pillars"]["gap_coherence"]
    assert gap["status"] == "official"
    pb = probability_balance_index(42.0, 30.0)
    bal = build_cecchino_balance_analysis(
        quota_cecchino_1=2.1,
        quota_cecchino_x=3.4,
        quota_cecchino_2=3.6,
        prob_cecchino_1=0.42,
        prob_cecchino_x=0.28,
        prob_cecchino_2=0.30,
    )
    expected = gap_coherence_index(bal["f36"]["score"], pb)
    assert abs(gap["index"] - expected) < 0.01
    assert classify_gap_coherence(10) == "Non Confermato"
    assert classify_gap_coherence(90) == "Fortemente Confermato"
    blob = json.dumps(gap).lower()
    assert "research" not in blob


def test_market_24_28():
    v5 = build_cecchino_balance_v5(cecchino_final=_final(), kpi_panel=_kpi_with_book())
    md = v5["market_deviation"]
    reading = (md.get("reading") or "").lower()
    assert "distanza" in reading or "scostamento" in reading or "non stabilisce" in reading
    pairs = {p["key"]: p for p in md["pairs"]}
    assert "1" in pairs and "x" in pairs and "2" in pairs
    for key in PILLAR_ORDER:
        assert "book" not in json.dumps(v5["pillars"][key]).lower()


def test_api_29_33():
    v5 = build_cecchino_balance_v5(cecchino_final=_final())
    assert VERSION == "cecchino_balance_v5_v2"
    assert v5["version"] == VERSION
    assert set(v5["pillars"].keys()) == set(PILLAR_ORDER)
    assert v5["pillar_order"] == PILLAR_ORDER
    assert isinstance(v5.get("structural_summary"), str) and v5["structural_summary"]
    blocked = build_cecchino_balance_v5(
        cecchino_final=_final(),
        identity_consistency={"status": "inconsistent", "warnings": ["x"]},
    )
    assert blocked["status"] == "unavailable"
    json.dumps(jsonable_encoder(v5), allow_nan=False)


def test_label_mapping():
    assert dominant_side_to_market_label("HOME") == "1"
    assert dominant_side_to_market_label("DRAW") == "X"
    assert dominant_side_to_market_label("AWAY") == "2"


def test_parity_live_consumer_slices():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scenarios = {
        "equilibrio_forte_x_dominante": dict(
            quota_cecchino_1=2.50,
            quota_cecchino_x=3.20,
            quota_cecchino_2=2.90,
            prob_cecchino_1=31.0,
            prob_cecchino_x=42.0,
            prob_cecchino_2=27.0,
        ),
        "equilibrio_forte_1_dominante": dict(
            quota_cecchino_1=2.50,
            quota_cecchino_x=3.40,
            quota_cecchino_2=2.90,
            prob_cecchino_1=45.0,
            prob_cecchino_x=25.0,
            prob_cecchino_2=30.0,
        ),
        "transizione": dict(
            quota_cecchino_1=2.20,
            quota_cecchino_x=3.50,
            quota_cecchino_2=3.40,
            prob_cecchino_1=40.0,
            prob_cecchino_x=28.0,
            prob_cecchino_2=32.0,
        ),
        "squilibrio_verso_1": dict(
            quota_cecchino_1=1.80,
            quota_cecchino_x=3.80,
            quota_cecchino_2=4.50,
            prob_cecchino_1=55.0,
            prob_cecchino_x=22.0,
            prob_cecchino_2=23.0,
        ),
        "squilibrio_verso_2": dict(
            quota_cecchino_1=4.20,
            quota_cecchino_x=3.60,
            quota_cecchino_2=1.90,
            prob_cecchino_1=22.0,
            prob_cecchino_x=23.0,
            prob_cecchino_2=55.0,
        ),
        "x_prima": dict(
            quota_cecchino_1=2.60,
            quota_cecchino_x=3.10,
            quota_cecchino_2=2.70,
            prob_cecchino_1=30.0,
            prob_cecchino_x=40.0,
            prob_cecchino_2=30.0,
        ),
        "x_seconda": dict(
            quota_cecchino_1=2.40,
            quota_cecchino_x=3.30,
            quota_cecchino_2=2.80,
            prob_cecchino_1=42.0,
            prob_cecchino_x=30.0,
            prob_cecchino_2=28.0,
        ),
        "x_terza": dict(
            quota_cecchino_1=2.10,
            quota_cecchino_x=4.50,
            quota_cecchino_2=3.20,
            prob_cecchino_1=48.0,
            prob_cecchino_x=18.0,
            prob_cecchino_2=34.0,
        ),
        "dati_mancanti": dict(
            quota_cecchino_1=None,
            quota_cecchino_x=3.40,
            quota_cecchino_2=3.60,
            prob_cecchino_1=0.42,
            prob_cecchino_x=0.28,
            prob_cecchino_2=0.30,
        ),
    }
    for name, kw in scenarios.items():
        expected = data[name]
        bal = build_cecchino_balance_analysis(**kw)
        assert bal.get("status") == expected["balance_status"]
        assert bal.get("version") == expected["balance_version"] == LEGACY_VERSION
        if bal.get("status") == "available":
            assert bal["f36"] == expected["f36"]
            assert bal["dominance"] == expected["dominance"]
            assert bal["draw"] == expected["draw"]
            assert bal["inputs"] == expected["inputs"]
            assert (bal.get("operational") or {}).get("class_key") == expected[
                "operational_class_key"
            ]
        assert (
            compute_dominance_pp(
                kw.get("prob_cecchino_1"),
                kw.get("prob_cecchino_x"),
                kw.get("prob_cecchino_2"),
            )
            == expected["dominance_pp_fn"]
        )
        icm = build_cecchino_icm_analysis(balance_analysis=bal, kpi_panel=None)
        assert icm.get("status") == expected["icm"]["status"]
        assert icm.get("score") == expected["icm"]["score"]
        assert icm.get("version") == expected["icm"]["version"]


def test_arch_no_preview_imports():
    app_dir = BACKEND / "app"
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "cecchino_balance_v5_preview" not in text, path
        assert "balance_v5_preview" not in text, path
    fe = ROOT / "frontend" / "src"
    if fe.exists():
        for path in fe.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert "balance_v5_preview" not in text, path
            assert "BalanceV5Preview" not in text, path


def test_arch_single_formula_defs():
    names = {
        "conviction_index": 0,
        "probability_balance_index": 0,
        "gap_coherence_index": 0,
        "classify_conviction": 0,
        "classify_gap_coherence": 0,
    }
    for path in (BACKEND / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in names:
                names[node.name] += 1
    for name, count in names.items():
        assert count == 1, f"{name} defined {count} times"


def test_arch_no_research_candidates_file():
    assert not (BACKEND / "app/services/cecchino/cecchino_balance_research_candidates.py").exists()
    assert not (BACKEND / "app/services/cecchino/cecchino_balance_v5_preview.py").exists()


def test_arch_no_betting_in_v5_payload():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(prob_1=0.31, prob_x=0.42, prob_2=0.27, quota_x=3.2)
    )
    blob = json.dumps(v5, ensure_ascii=False).lower()
    for phrase in ("x / under molto", "da giocare", "value bet", "stake consigliato"):
        assert phrase not in blob


def test_f36_reading_transition_uses_class_key():
    v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=2.20, quota_2=3.40))
    f36 = v5["pillars"]["f36"]
    assert f36["class_label"] == "Transizione"
    reading = (f36["reading"] or "").lower()
    assert "distanza intermedia" in reading
    assert "relativamente vicine" not in reading


def test_f36_reading_imbalance_uses_class_key():
    v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=1.80, quota_2=4.50))
    f36 = v5["pillars"]["f36"]
    assert f36["class_label"] == "Squilibrio"
    reading = (f36["reading"] or "").lower()
    assert "sbilanciata" in reading
    assert "relativamente vicine" not in reading


def test_norm_1x2_shared_across_pillars_and_market():
    v5 = build_cecchino_balance_v5(
        cecchino_final={
            "status": "available",
            "quota_1": 2.10,
            "quota_x": 3.40,
            "quota_2": 3.60,
            "prob_1_pct": 22.90,
            "prob_x_pct": 58.75,
            "prob_2_pct": 15.28,
        }
    )
    assert v5["inputs"]["prob_x"] == pytest.approx(58.75)
    assert v5["inputs"]["prob_x_norm"] == pytest.approx(60.61, abs=0.02)
    dc = v5["pillars"]["draw_credibility"]
    assert dc["index"] == pytest.approx(v5["inputs"]["prob_x_norm"], abs=0.02)
    pairs = {p["key"]: p for p in v5["market_deviation"]["pairs"]}
    assert pairs["x"]["prob_cecchino_norm"] == pytest.approx(dc["index"], abs=0.02)
    gap_pp = abs(v5["inputs"]["prob_1_norm"] - v5["inputs"]["prob_2_norm"])
    gap_comp = next(
        c for c in v5["pillars"]["gap_coherence"]["components"] if c["key"] == "probability_gap_1_2_pp"
    )
    assert gap_comp["value"] == pytest.approx(gap_pp, abs=0.02)
    assert pairs["x"]["direction_label"] in (
        "Probabilità allineate",
        "Probabilità Cecchino maggiore",
        "Probabilità Book maggiore",
        None,
    )


def test_goal_markets_separate_from_final():
    gm = {
        SEL_UNDER_2_5: {"status": "available", "final_odd": 1.85},
        SEL_OVER_2_5: {"status": "available", "final_odd": 2.05},
    }
    v5 = build_cecchino_balance_v5(cecchino_final=_final(), goal_markets=gm)
    assert v5["inputs"]["under_odd"] == pytest.approx(1.85)
    assert v5["inputs"]["over_odd"] == pytest.approx(2.05)
    dc_keys = [c["key"] for c in v5["pillars"]["draw_credibility"]["components"]]
    assert "quota_under_2_5" in dc_keys
    assert "quota_over_2_5" in dc_keys
    pairs = {p["key"]: p for p in v5["market_deviation"]["pairs"]}
    assert pairs["under_2_5"]["quota_cecchino"] == pytest.approx(1.85)
    assert pairs["over_2_5"]["quota_cecchino"] == pytest.approx(2.05)
    assert pairs["under_2_5"]["prob_cecchino_norm"] is not None
