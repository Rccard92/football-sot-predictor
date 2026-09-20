"""Il Ragionamento: frasi italiane a regole fisse, numeri con la virgola, sei blocchi e scheda partita."""

from __future__ import annotations

import pytest

from app.services.cecchino_v4.constants import BOOKMAKER_BET365_ID, BOOKMAKER_BETFAIR_ID, VERDICT_FAIR_PRICE, VERDICT_NO_ODDS
from app.services.cecchino_v4.explain.blocks import build_explanation, fixture_card
from app.services.cecchino_v4.explain.format import fmt_interval, fmt_num, fmt_pct, fmt_quota, join_it, ordinal
from app.services.cecchino_v4.selection.rules import evaluate_fixture
from tests.v4.test_selection_samples import ACTUAL_STATS, AWAY, FIXTURE_META, HOME, RESULT, SOT_KEY, goals, odds, stats

import pytest as _pytest

from app.services.cecchino_v4.selection import rules as _rules


@_pytest.fixture(autouse=True)
def _classic_markets_playable_for_rule_tests(monkeypatch):
    """Questi test verificano la meccanica della regola sui mercati classici: nel prodotto i classici
    restano "in osservazione" (focus statistiche), qui si abilitano per esercitare la regola."""
    monkeypatch.setattr(_rules, "CLASSIC_PLAYABLE_DEFAULT", True)
    # i campioni di questi test furono scritti quando corner e cartellini erano solo descrittivi
    monkeypatch.setattr(_rules, "PLAYABLE_STATS", ("shots", "sot"))


CONTEXT = {"lineups": {"status": "non_note", "absences": []}, "rest": {"home_days": 7, "away_days": 4}, "motivation": None, "referee": None}


@pytest.fixture()
def rows():
    return evaluate_fixture(goals(), stats(), odds(), HOME, AWAY, "non_note")


@pytest.fixture()
def blocks(rows):
    return build_explanation(FIXTURE_META, goals(), stats(), rows, CONTEXT, None)


# --- formato ------------------------------------------------------------------------
def test_italian_number_formatting():
    assert fmt_num(1.85, 2) == "1,85"
    assert fmt_quota(2.3) == "2,30"
    assert fmt_num(6.8) == "6,8"
    assert fmt_num(-0.5) == "−0,5"
    assert fmt_num(0.13, 2, signed=True) == "+0,13"
    assert fmt_pct(0.613) == "61%"
    assert fmt_pct(0.13, signed=True) == "+13%"
    assert fmt_pct(-0.02) == "−2%"
    assert fmt_interval(0.55, 0.66) == "55-66"
    assert ordinal(3) == "terzo" and ordinal(6, feminine=True) == "sesta" and ordinal(21) == "ventunesimo" and ordinal(30) == "30°"
    assert join_it(["a", "b", "c"]) == "a, b e c"


# --- blocchi --------------------------------------------------------------------------
def test_all_six_blocks_present(blocks):
    assert set(blocks) == {"who", "how", "context", "predicts", "why", "aftermath"}
    for name in ("who", "how", "context", "predicts"):
        assert isinstance(blocks[name]["sentence"], str) and blocks[name]["sentence"]
    assert blocks["aftermath"] is None


def test_who_sentence_and_data(blocks):
    who = blocks["who"]
    assert who["sentence"].startswith("Milan: settimo attacco della Serie A in calo, nona difesa, conosciuta bene (34 partite equivalenti).")
    assert "Inter: terzo attacco della Serie A in crescita, sesta difesa, conosciuta abbastanza (12 partite equivalenti)." in who["sentence"]
    assert who["home"]["known"] == "bene" and who["away"]["known"] == "abbastanza"
    assert who["home"]["attack_rank"] == 7 and who["away"]["defence_rank"] == 6
    assert who["home"]["trend"] == "in calo" and who["away"]["trend"] == "in crescita"
    assert "ereditata" in who["away"]["inherited"]


def test_who_with_little_evidence_and_new_team():
    payload = goals()
    payload["uncertainty"].update({"away_evidence": 2.0, "new_team_away": True})
    who = build_explanation(FIXTURE_META, payload, None, [], CONTEXT)["who"]
    assert who["away"]["known"] == "poco"
    assert "conosciuta poco (2 partite equivalenti)" in who["sentence"]
    assert "piramide nazionale" in who["away"]["inherited"]


def test_how_rows_and_biggest_deviation(blocks):
    how = blocks["how"]
    assert how["sentence"] == "Inter: 6,8 tiri in porta attesi fuori casa contro una media di divisione di 4,6; Milan ne concede 5,1."
    sot = next(r for r in how["rows"] if r["stat"] == "sot")
    assert sot == {
        "stat": "sot",
        "label": "tiri in porta",
        "exam": "superato",
        "home_for": 4.9,
        "home_against": 5.1,
        "away_for": 6.8,
        "away_against": 4.2,
        "division_mean": 4.6,
        "home_rank_for": 8,
        "away_rank_for": 4,
        "total": 11.7,
    }
    assert build_explanation(FIXTURE_META, goals(), None, [], CONTEXT)["how"] == {"sentence": "Statistiche di squadra non ancora calcolate.", "rows": []}


def test_how_marks_descriptive_stat_when_it_leads():
    payload = stats()
    del payload["stats"]["sot"]
    how = build_explanation(FIXTURE_META, goals(), payload, [], CONTEXT)["how"]
    assert "Statistica solo descrittiva" in how["sentence"]


def test_context_sentence(blocks):
    ctx = blocks["context"]
    assert "Milan in calo nelle ultime 5 (meno tiri del previsto); Inter in crescita nelle ultime 5 (più tiri del previsto)." in ctx["sentence"]
    assert "Riposo: Milan 7 giorni, Inter 4 giorni." in ctx["sentence"]
    assert "Formazioni non ancora note." in ctx["sentence"]
    assert ctx["motivation"] is None and ctx["referee"] is None
    assert ctx["rest"] == {"home_days": 7, "away_days": 4, "final_phase": False}
    assert ctx["lineups"] == {"status": "non_note", "absences": []}


def test_context_with_lineups_absences_motivation_referee():
    context = {
        "lineups": {"status": "ufficiali", "absences": [{"team": "away", "name": "Lautaro"}, {"team": "home", "name": "Leao"}, {"team": "home", "name": "Theo"}]},
        "rest": {"home_days": 3, "away_days": 1},
        "motivation": {"sentence": "Inter a due punti dalla vetta"},
        "referee": {"name": "Orsato"},
    }
    ctx = build_explanation(FIXTURE_META, goals(), None, [], context)["context"]
    assert "Formazioni ufficiali." in ctx["sentence"]
    assert "Assenze: Milan senza Leao e Theo; Inter senza Lautaro." in ctx["sentence"]
    assert "Inter a due punti dalla vetta." in ctx["sentence"]
    assert "Arbitro: Orsato." in ctx["sentence"]
    assert "Riposo: Milan 3 giorni, Inter 1 giorno." in ctx["sentence"]


def test_predicts_matrix_and_sentence(blocks):
    pred = blocks["predicts"]
    assert pred["max_goals"] == 5
    assert len(pred["score_matrix"]) == 6 and all(len(r) == 6 for r in pred["score_matrix"])
    assert 0.9 < sum(sum(r) for r in pred["score_matrix"]) <= 1.0
    assert pred["most_likely"] == {"market_key": "AWAY", "label": "2", "p": 0.42}
    assert pred["most_likely_score"]["home"] <= 2 and pred["most_likely_score"]["away"] <= 2
    assert "Segno più probabile: 2 al 42%." in pred["sentence"]
    assert "Gol attesi: Milan 1,2, Inter 1,6; over 2,5 al 51%." in pred["sentence"]
    assert pred["sentence"].startswith("Risultato più probabile ")
    markets = pred["markets"]
    assert markets[0]["market_key"] == SOT_KEY  # profitto atteso più alto in testa tra i mercati con verdetto pieno
    assert markets[-1]["expected_profit"] is None  # non quotati in coda
    descriptive = [i for i, m in enumerate(markets) if m["verdict"] == "solo_descrittivo" and m["expected_profit"] is not None]
    priced_full = [i for i, m in enumerate(markets) if m["verdict"] not in ("solo_descrittivo", "non_quotato")]
    assert max(priced_full) < min(descriptive)  # i solo descrittivi con prezzo vengono dopo
    assert {m["verdict"] for m in markets} >= {"giocabile", "prezzo_giusto", "non_quotato", "solo_descrittivo"}


def test_why_for_best_play(blocks):
    why = blocks["why"]
    assert why["play"]["market_key"] == SOT_KEY and why["reason"] is None
    s = why["sentences"]
    assert 4 <= len(s) <= 6
    assert s[0] == "Inter: 6,8 tiri in porta attesi fuori casa contro una media di divisione di 4,6 (quarta squadra della divisione per tiri in porta); Milan ne concede 5,1."
    # lo = 0,56, tasso base Poisson(4,6) oltre 6,5 = 0,18, incertezza 0,22: prudente 0,56 - 0,38 * 0,22 = 0,48
    assert s[1] == "La quota 2,30 di Bet365 vale il 43%; il modello dice 61% con intervallo 56-66, probabilità prudente 48%."
    assert s[2] == "Il profitto atteso è +10%, sopra il 3% richiesto."
    assert s[3] == "Formazioni non ancora note: la giocata è provvisoria e verrà confermata o ritirata alle formazioni ufficiali."
    assert s[4].startswith("Incertezza bassa")
    wc = why["would_change"]
    assert wc[0] == "Assenza di un titolare chiave nel Inter"
    assert wc[1].startswith("Quota Bet365 sotto 2,16") and "pareggio a 2,10" in wc[1]  # 1,03 / 0,4768 e 1 / 0,4768
    assert wc[2] == "Formazioni con turnover"


def test_why_classic_play_and_not_advised():
    rich = odds()
    rich[BOOKMAKER_BET365_ID]["AWAY"] = 3.2
    del rich[BOOKMAKER_BET365_ID][SOT_KEY]
    del rich[BOOKMAKER_BETFAIR_ID][SOT_KEY]
    rows = evaluate_fixture(goals(), stats(), rich, HOME, AWAY, "ufficiali", advised_families={"FT_1X2": False, "AH": False})
    why = build_explanation({**FIXTURE_META, "lineups_status": "ufficiali"}, goals(), stats(), rows, None)["why"]
    assert why["play"]["market_key"] in ("AWAY", "AH_AWAY:-0.5")
    assert why["sentences"][0].startswith("Gol attesi: Milan 1,2, Inter 1,6; attacco Milan settimo e difesa nona, attacco Inter terzo e difesa sesta.")
    assert "Formazioni ufficiali: la giocata è confermata." in why["sentences"]
    assert any("in osservazione" in s for s in why["sentences"])
    assert why["would_change"][0] == "Assenza di un titolare chiave"


def test_why_no_play_reasons():
    fair = odds()
    fair[BOOKMAKER_BET365_ID][SOT_KEY] = 1.85
    fair[BOOKMAKER_BETFAIR_ID][SOT_KEY] = 1.90
    rows = evaluate_fixture(goals(), stats(), fair, HOME, AWAY)
    why = build_explanation(FIXTURE_META, goals(), stats(), rows, CONTEXT)["why"]
    assert why["play"] is None and why["reason"] == VERDICT_FAIR_PRICE and why["would_change"] == []
    assert why["sentences"][0].startswith("Nessuna giocata: il miglior candidato, ")
    assert "sotto il 3% richiesto." in why["sentences"][0]

    rows = evaluate_fixture(goals(), stats(), None, HOME, AWAY)
    why = build_explanation(FIXTURE_META, goals(), stats(), rows, CONTEXT)["why"]
    assert why["reason"] == VERDICT_NO_ODDS and "nessun mercato quotato" in why["sentences"][0]

    payload = goals()
    payload["uncertainty"]["level"] = "alta"
    rows = evaluate_fixture(payload, stats(), odds(), HOME, AWAY)
    why = build_explanation(FIXTURE_META, payload, stats(), rows, CONTEXT)["why"]
    assert why["sentences"][0] == "Nessuna giocata: incertezza alta, il modello conosce poco Inter."

    why = build_explanation(FIXTURE_META, None, None, [], CONTEXT)["why"]
    assert why["sentences"] == ["Nessuna giocata: nessun mercato calcolato per questa partita."]


def test_aftermath_when_result_present(rows):
    blocks = build_explanation(FIXTURE_META, goals(), stats(), rows, CONTEXT, {"result": RESULT, "stats": ACTUAL_STATS})
    after = blocks["aftermath"]
    assert after["sentence"].startswith("Previsto 1,2-1,6, reale 1-2.")
    assert "Tiri in porta: Milan attesi 4,9, reali 3; Inter attesi 6,8, reali 8." in after["sentence"]
    assert "Giocata Inter over 6,5 tiri in porta: vinta (+1,30 unità)." in after["sentence"]
    assert after["play"] == {"label": "Inter over 6,5 tiri in porta", "market_key": SOT_KEY, "outcome": "vinta", "profit_units": pytest.approx(1.3)}
    assert "fortuna" in after["luck"] or "merito" in after["luck"]
    assert after["goals"] == {"expected_home": 1.2, "expected_away": 1.6, "actual_home": 1, "actual_away": 2}
    sot = next(r for r in after["stats"] if r["stat"] == "sot")
    assert sot["actual_away"] == 8.0


def test_aftermath_without_stats_marks_play_unsettled(rows):
    after = build_explanation(FIXTURE_META, goals(), stats(), rows, CONTEXT, {"result": RESULT, "stats": None})["aftermath"]
    assert after["play"]["outcome"] is None
    assert "manca il dato" in after["sentence"]


# --- scheda partita ---------------------------------------------------------------------
def test_fixture_card_shape(rows):
    card = fixture_card(FIXTURE_META, goals(), rows, "non_note", None)
    assert card["id"] == 12 and card["home_team"] == HOME and card["competition"] == "Serie A"
    assert card["most_likely"] == {"market_key": "AWAY", "label": "2", "p": 0.42}
    assert card["expected_goals"] == {"home": 1.2, "away": 1.6}
    assert card["uncertainty"] == {"score": 0.22, "level": "bassa"}
    assert card["lineups_status"] == "non_note"
    assert card["best_play"]["market_key"] == SOT_KEY and card["best_play"]["label"] == "Inter over 6,5 tiri in porta"
    assert card["no_play_reason"] is None and card["result"] is None


def test_fixture_card_without_play():
    rows = evaluate_fixture(goals(), stats(), None, HOME, AWAY)
    card = fixture_card(FIXTURE_META, goals(), rows, "ufficiali", RESULT)
    assert card["best_play"] is None
    assert card["no_play_reason"] == VERDICT_NO_ODDS
    assert card["result"] == RESULT
    assert card["lineups_status"] == "ufficiali"
