"""Test Equilibrio vs Squilibrio v5 — modulo canonico cecchino_balance_v5_v3."""

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
    X_MEAN_FULL_EFFECT_DISTANCE,
    X_MEAN_MAX_ADJUSTMENT,
    X_MEAN_THRESHOLD,
    _classify_adjusted_f36_index,
    _compute_x_mean_adjustment,
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
    SEL_DRAW_PT,
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
                "book_source": "betfair_panel",
                "prob_book": 0.40,
                "prob_cecchino": 0.42,
            },
            {
                "market_key": SEL_DRAW,
                "quota_cecchino": 3.4,
                "quota_book": 3.5,
                "book_source": "betfair_panel",
                "prob_book": 0.28,
                "prob_cecchino": 0.28,
            },
            {
                "market_key": SEL_AWAY,
                "quota_cecchino": 3.6,
                "quota_book": 3.7,
                "book_source": "betfair_panel",
                "prob_book": 0.27,
                "prob_cecchino": 0.30,
            },
            {"market_key": SEL_UNDER_2_5, "quota_cecchino": 1.85, "quota_book": 1.9},
            {"market_key": SEL_OVER_2_5, "quota_cecchino": 2.05, "quota_book": 2.1},
        ],
    }


def _kpi_draw_book(quota_book_x: float | None, **draw_extra):
    """KPI minimale con sola riga DRAW personalizzabile."""
    rows = [
        {
            "market_key": SEL_HOME,
            "quota_book": 2.2,
            "book_source": "betfair_panel",
        },
        {
            "market_key": SEL_AWAY,
            "quota_book": 3.7,
            "book_source": "betfair_panel",
        },
    ]
    if quota_book_x is not None or draw_extra:
        row = {
            "market_key": SEL_DRAW,
            "quota_book": quota_book_x,
            "book_source": "betfair_panel",
        }
        row.update(draw_extra)
        rows.insert(1, row)
    return {"version": "cecchino_kpi_v2_betfair", "rows": rows}


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
        # Senza KPI: indice = base F36 (nessuna correzione X)
        v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=q1, quota_2=q2))
        assert v5["pillars"]["f36"]["base_index"] == score
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
    # Book non entra nella matematica del Pilastro 3
    assert "quota_book" not in json.dumps(dc).lower()
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
    # Book non entra nei pilastri 2–4; il Pilastro 1 V3 può citare Quota X Book
    for key in ("dominance", "draw_credibility", "gap_coherence"):
        assert "quota_book" not in json.dumps(v5["pillars"][key]).lower()
    assert v5["pillars"]["f36"].get("quota_x_book") is not None


def test_api_29_33():
    v5 = build_cecchino_balance_v5(cecchino_final=_final())
    assert VERSION == "cecchino_balance_v5_v3"
    assert v5["version"] == VERSION
    assert set(v5["pillars"].keys()) == set(PILLAR_ORDER)
    assert v5["pillar_order"] == PILLAR_ORDER
    assert isinstance(v5.get("structural_summary"), str) and v5["structural_summary"]
    assert v5["structural_summary"].startswith("Geometria:")
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
    assert v5["inputs"]["prob_x_norm"] == 60.61
    dc = v5["pillars"]["draw_credibility"]
    assert dc["index"] == v5["inputs"]["prob_x_norm"]
    pairs = {p["key"]: p for p in v5["market_deviation"]["pairs"]}
    assert pairs["x"]["prob_cecchino_norm"] == dc["index"]
    gap_pp = round(abs(v5["inputs"]["prob_1_norm"] - v5["inputs"]["prob_2_norm"]), 2)
    gap_comp = next(
        c for c in v5["pillars"]["gap_coherence"]["components"] if c["key"] == "probability_gap_1_2_pp"
    )
    assert gap_comp["value"] == gap_pp
    assert pairs["x"]["direction_label"] in (
        "Probabilità allineate",
        "Probabilità Cecchino maggiore",
        "Probabilità Book maggiore",
        None,
    )


def test_no_double_normalize_cecchino_1x2_when_rounded_sum_not_100():
    """Tripletta il cui primo arrotondamento somma 99.99: market non deve rinormalizzare."""
    v5 = build_cecchino_balance_v5(
        cecchino_final={
            "status": "available",
            "quota_1": 2.10,
            "quota_x": 3.40,
            "quota_2": 3.60,
            "prob_1_pct": 33.33,
            "prob_x_pct": 33.33,
            "prob_2_pct": 33.33,
        }
    )
    n1 = v5["inputs"]["prob_1_norm"]
    nx = v5["inputs"]["prob_x_norm"]
    n2 = v5["inputs"]["prob_2_norm"]
    assert round(n1 + nx + n2, 2) == 99.99
    dc = v5["pillars"]["draw_credibility"]
    pairs = {p["key"]: p for p in v5["market_deviation"]["pairs"]}
    assert pairs["x"]["prob_cecchino_norm"] == dc["index"]
    assert pairs["x"]["prob_cecchino_norm"] == nx
    assert pairs["1"]["prob_cecchino_norm"] == n1
    assert pairs["2"]["prob_cecchino_norm"] == n2


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


# ---------------------------------------------------------------------------
# V3 — Quota Media X
# ---------------------------------------------------------------------------


def test_x_mean_constants():
    assert X_MEAN_THRESHOLD == 3.60
    assert X_MEAN_FULL_EFFECT_DISTANCE == 0.60
    assert X_MEAN_MAX_ADJUSTMENT == 20.0


def test_x_mean_adjustment_math_cases_a_to_g():
    # A — soglia neutrale
    a = _compute_x_mean_adjustment(3.60)
    assert a["x_mean_strength"] == 0.0
    assert a["x_mean_adjustment"] == 0.0
    assert a["x_mean_direction"] == "reinforces_imbalance"

    # B — media 3.30 → +10
    b = _compute_x_mean_adjustment(3.30)
    assert b["x_mean_strength"] == pytest.approx(0.50)
    assert b["x_mean_adjustment"] == pytest.approx(10.0)
    assert b["x_mean_direction"] == "reinforces_balance"

    # C — media <= 3.00 → +20
    c = _compute_x_mean_adjustment(3.00)
    assert c["x_mean_strength"] == pytest.approx(1.0)
    assert c["x_mean_adjustment"] == pytest.approx(20.0)

    # D — media 3.90 → −10
    d = _compute_x_mean_adjustment(3.90)
    assert d["x_mean_strength"] == pytest.approx(0.50)
    assert d["x_mean_adjustment"] == pytest.approx(-10.0)
    assert d["x_mean_direction"] == "reinforces_imbalance"

    # E — media >= 4.20 → −20
    e = _compute_x_mean_adjustment(4.20)
    assert e["x_mean_strength"] == pytest.approx(1.0)
    assert e["x_mean_adjustment"] == pytest.approx(-20.0)


def test_x_mean_classification_continuous_preserves_base():
    assert _classify_adjusted_f36_index(100)["label"] == "Equilibrio forte"
    assert _classify_adjusted_f36_index(80)["label"] == "Equilibrio"
    assert _classify_adjusted_f36_index(60)["label"] == "Transizione"
    assert _classify_adjusted_f36_index(40)["label"] == "Squilibrio"
    assert _classify_adjusted_f36_index(90)["label"] == "Equilibrio forte"
    assert _classify_adjusted_f36_index(89.99)["label"] == "Equilibrio"
    assert _classify_adjusted_f36_index(70)["label"] == "Equilibrio"
    assert _classify_adjusted_f36_index(50)["label"] == "Transizione"
    assert _classify_adjusted_f36_index(49.99)["label"] == "Squilibrio"


def test_x_mean_applied_case_b_index_90():
    # F36 base 80 (diff 0.80), book 3.20 + cecchino 3.40 → media 3.30 → +10 → 90
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(3.20),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["base_index"] == 80
    assert f36["quota_x_media"] == pytest.approx(3.30)
    assert f36["x_mean_strength"] == pytest.approx(0.50)
    assert f36["x_mean_adjustment"] == pytest.approx(10.0)
    assert f36["index"] == pytest.approx(90.0)
    assert f36["class_label"] == "Equilibrio forte"
    assert f36["calculation_quality"] == "f36_with_x_mean"


def test_x_mean_applied_case_d_index_70():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=4.00),
        kpi_panel=_kpi_draw_book(3.80),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["base_index"] == 80
    assert f36["quota_x_media"] == pytest.approx(3.90)
    assert f36["x_mean_adjustment"] == pytest.approx(-10.0)
    assert f36["index"] == pytest.approx(70.0)
    assert f36["class_label"] == "Equilibrio"


def test_x_mean_neutral_threshold_no_jump():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.60),
        kpi_panel=_kpi_draw_book(3.60),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["quota_x_media"] == pytest.approx(3.60)
    assert f36["x_mean_adjustment"] == pytest.approx(0.0)
    assert f36["index"] == f36["base_index"] == 80


def test_x_mean_clamp_upper():
    # base 100 +20 → 100
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.50, quota_2=2.90, quota_x=2.80),
        kpi_panel=_kpi_draw_book(2.80),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["base_index"] == 100
    assert f36["x_mean_adjustment"] == pytest.approx(20.0)
    assert f36["adjusted_index_raw"] == pytest.approx(120.0)
    assert f36["index"] == pytest.approx(100.0)


def test_x_mean_clamp_lower():
    # base 40 −20 → 20
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=1.80, quota_2=4.00, quota_x=4.50),
        kpi_panel=_kpi_draw_book(4.50),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["base_index"] == 40
    assert f36["x_mean_adjustment"] == pytest.approx(-20.0)
    assert f36["index"] == pytest.approx(20.0)
    assert f36["class_label"] == "Squilibrio"


def test_x_mean_missing_book_preserves_base():
    v5 = build_cecchino_balance_v5(cecchino_final=_final(quota_1=2.00, quota_2=2.80))
    f36 = v5["pillars"]["f36"]
    assert f36["base_index"] == 80
    assert f36["index"] == 80
    assert f36["calculation_quality"] == "f36_base_only"
    assert f36["x_mean_source_status"] == "unavailable"
    assert f36["quota_x_media"] is None
    assert "x_mean_adjustment_not_applied_f36_preserved" in f36["warnings"]
    assert "non disponibile" in (f36["reading"] or "").lower()


def test_x_mean_missing_cecchino_preserves_base():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=None),
        kpi_panel=_kpi_draw_book(3.20),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["index"] == f36["base_index"] == 80
    assert f36["calculation_quality"] == "f36_base_only"
    assert "x_mean_cecchino_quote_unavailable" in f36["warnings"]


def test_x_mean_invalid_book_le_1():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(1.0),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["calculation_quality"] == "f36_base_only"
    assert f36["index"] == 80


def test_x_mean_derived_book_rejected():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(3.20, book_source="derived_from_betfair_1x2"),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["calculation_quality"] == "f36_base_only"
    assert f36["x_mean_source_status"] == "not_real"
    assert "x_mean_book_quote_not_real" in f36["warnings"]
    assert f36["index"] == 80


def test_x_mean_diagnostic_only_rejected():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(3.20, diagnostic_only=True),
    )
    f36 = v5["pillars"]["f36"]
    assert f36["calculation_quality"] == "f36_base_only"
    assert f36["index"] == 80


def test_x_mean_ignores_draw_pt():
    kpi = {
        "rows": [
            {
                "market_key": SEL_DRAW_PT,
                "quota_book": 2.50,
                "book_source": "betfair_panel",
            }
        ]
    }
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=kpi,
    )
    f36 = v5["pillars"]["f36"]
    assert f36["calculation_quality"] == "f36_base_only"
    assert f36["index"] == 80


def test_gap_uses_f36_base_not_adjusted():
    """Pilastro 4 riceve f36_base_index anche quando l'indice corretto differisce."""
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(3.20),
    )
    f36 = v5["pillars"]["f36"]
    gap = v5["pillars"]["gap_coherence"]
    assert f36["index"] != f36["base_index"]
    assert v5["inputs"]["gap_coherence_f36_input"] == f36["base_index"]
    pb = probability_balance_index(
        v5["inputs"]["prob_1_norm"], v5["inputs"]["prob_2_norm"]
    )
    expected = gap_coherence_index(f36["base_index"], pb)
    assert gap["index"] == pytest.approx(expected)
    # Se usasse l'indice corretto, il gap sarebbe diverso
    wrong = gap_coherence_index(f36["index"], pb)
    assert gap["index"] != pytest.approx(wrong)


def test_other_pillars_invariant_with_x_mean():
    """A parità di input, P2/P3/P4 e probs restano identici con o senza book X reale."""
    final = _final(quota_1=2.00, quota_2=2.80, quota_x=3.40)
    without = build_cecchino_balance_v5(cecchino_final=final)
    with_x = build_cecchino_balance_v5(
        cecchino_final=final, kpi_panel=_kpi_draw_book(3.20)
    )
    for key in ("dominance", "draw_credibility", "gap_coherence"):
        assert without["pillars"][key]["index"] == with_x["pillars"][key]["index"]
        assert without["pillars"][key]["class_label"] == with_x["pillars"][key]["class_label"]
    for k in ("prob_1_norm", "prob_x_norm", "prob_2_norm"):
        assert without["inputs"][k] == with_x["inputs"][k]
    # Solo F36 index finale cambia
    assert without["pillars"]["f36"]["base_index"] == with_x["pillars"]["f36"]["base_index"]
    assert without["pillars"]["f36"]["index"] != with_x["pillars"]["f36"]["index"]


def test_f36_components_order_v3():
    v5 = build_cecchino_balance_v5(
        cecchino_final=_final(quota_1=2.00, quota_2=2.80, quota_x=3.40),
        kpi_panel=_kpi_draw_book(3.20),
    )
    keys = [c["key"] for c in v5["pillars"]["f36"]["components"]]
    assert keys == [
        "quota_1",
        "quota_2",
        "f36_diff",
        "f36_base_index",
        "f36_base_class",
        "quota_x_book",
        "quota_x_cecchino",
        "quota_x_media",
        "x_mean_threshold",
        "x_mean_direction",
        "x_mean_strength_pct",
        "x_mean_adjustment",
        "adjusted_index",
        "adjusted_class",
    ]