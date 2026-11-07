"""Regole di acquisto del Diario analisi (PDF "Gare sbagliate" di Giovanni, 06/11/2026)."""

from types import SimpleNamespace

from app.services.analyst.rules import (
    DEFAULT_RULES,
    checklist_warning,
    clean_rules,
    entry_codes,
    fixture_context,
    match_type,
    quota_status,
    quota_warnings,
)

R = DEFAULT_RULES


def codes(*args, **kw):
    return [w["code"] for w in quota_warnings(R, *args, **kw)]


def test_match_type_examples_from_the_pdf():
    assert match_type(2.55, 3.30, 2.38) == "Equilibrio"
    assert match_type(1.67, 4.00, 5.00) == "Squilibrio"
    assert match_type(1.75, 3.80, 4.50) == "Scala 1X"
    assert match_type(3.75, 2.80, 2.10) == "Scala X2"
    # le gare sbagliate del 5-6/11
    assert match_type(1.25, 6.50, 12.00) == "Squilibrio"  # Palmeiras-Remo
    assert match_type(8.00, 4.33, 1.44) == "Squilibrio"  # Aldosivi-River
    assert match_type(None, 3.2, 2.1) is None


def test_under_needs_cecchino_quota_times_1_15():
    # Botafogo SP-Londrina: Under PT 1,5 a 1,40 con quota Cecchino 1,77 -> minimo 2,04
    w = quota_warnings(R, "UNDER_PT_1_5", 1.40, 1.77, "Scala 1X")
    assert [x["code"] for x in w] == ["sotto_minimo"]
    assert "2,04" in w[0]["text"] and "1,77" in w[0]["text"]
    assert codes("UNDER_PT_1_5", 2.10, 1.77, "Scala 1X") == []


def test_under_3_5_floor_is_the_higher_of_the_two():
    assert codes("UNDER_3_5", 1.45, 1.20, "Equilibrio") == ["sotto_minimo"]  # 1,50 fisso
    assert codes("UNDER_3_5", 1.55, 1.40, "Equilibrio") == ["sotto_minimo"]  # 1,40 x 1,15 = 1,61
    assert codes("UNDER_3_5", 1.65, 1.40, "Equilibrio") == []


def test_never_under_in_squilibrio():
    assert "under_squilibrio" in codes("UNDER_3_5", 1.62, 1.30, "Squilibrio")  # Palmeiras-Remo
    assert "under_squilibrio" not in codes("OVER_2_5", 1.80, None, "Squilibrio")


def test_ranges_have_a_minimum_and_a_maximum():
    assert codes("HOME", 1.25) == ["sotto_minimo"]
    assert codes("HOME", 1.40) == []
    assert codes("HOME", 1.70) == ["sopra_massimo"]
    assert codes("DRAW", 3.40) == []
    assert codes("DRAW", 4.20) == ["sopra_massimo"]
    assert codes("DRAW_PT", 2.38) == []
    assert codes("OVER_2_5", 2.10) == ["sopra_massimo"]


def test_avoided_markets_and_markets_without_rules():
    assert codes("OVER_3_5", 2.20) == ["segno_da_evitare"]
    assert quota_status(R, "HOME_PT", 2.5) == "avoid"
    assert quota_status(R, "UNDER_0_5", 9.0) == "none"
    assert quota_status(R, "HOME", 1.40) == "ok"
    assert quota_status(R, "HOME", 1.20) == "out"


def test_checklist_needs_five_points():
    five = {f"k{i}": {"value": "favorevole"} for i in range(5)}
    assert checklist_warning(R, five) is None
    w = checklist_warning(R, {"a": {"value": "neutro"}, "b": {"value": None, "note": "x"}})
    assert w and w["code"] == "checklist_incompleta" and "1 punti" in w["text"]


def test_fixture_context_reads_the_kpi_panel():
    fx = SimpleNamespace(
        kpi_panel_json={
            "rows": [
                {"market_key": "HOME", "quota_book": 1.25, "quota_cecchino": 1.78},
                {"market_key": "DRAW", "quota_book": 6.5},
                {"market_key": "AWAY", "quota_book": 12.0},
                {"market_key": "UNDER_3_5", "quota_book": 1.62, "quota_cecchino": 1.30},
            ]
        }
    )
    assert fixture_context(fx, "UNDER_3_5") == {"match_type": "Squilibrio", "quota_cecchino": 1.30, "quota_book": 1.62}


def test_entry_codes_join_saved_warnings_checklist_and_review_tags():
    e = SimpleNamespace(rule_check_json={"warnings": [{"code": "sotto_minimo", "text": "x"}]}, checklist_json={})
    assert entry_codes(e, R, {"motivo_generico"}) == {"sotto_minimo", "checklist_incompleta", "motivo_generico"}


def test_clean_rules_from_admin():
    out = clean_rules({"checklist_min": 6, "markets": {"HOME": {"min": "1,3", "max": 1.6}, "BOH": {"min": 2}}}, {"HOME"})
    assert out["checklist_min"] == 6 and out["markets"] == {"HOME": {"max": 1.6}}  # "1,3" non e' un numero valido
    try:
        clean_rules({"markets": {"HOME": {"min": 2, "max": 1.5}}}, {"HOME"})
        raise AssertionError("doveva rifiutare")
    except ValueError:
        pass
