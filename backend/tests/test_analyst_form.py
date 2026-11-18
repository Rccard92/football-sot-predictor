"""Forma alla data della gara nel Diario analisi (documento "Modifiche" di Giovanni, 09/11/2026)."""

from datetime import datetime, timedelta, timezone
from fractions import Fraction

from app.services.analyst.form import (
    LeagueSeason,
    diff_level,
    excel_round,
    goal_form,
    is_knockout,
    points_diff,
    season_lengths,
    signs,
    strength,
    tournament_of,
)
from app.services.analyst.table import _block

T0 = datetime(2026, 8, 1, 18, 0, tzinfo=timezone.utc)
A, B, C, D = 1, 2, 3, 4


def game(gid, day, home, away, gh=None, ga=None, rnd="Regular Season - 1", ht=(0, 0)):
    return {
        "id": gid,
        "kickoff": T0 + timedelta(days=day),
        "home": home,
        "away": away,
        "gh": gh,
        "ga": ga,
        "hth": ht[0] if gh is not None else None,
        "hta": ht[1] if gh is not None else None,
        "round": rnd,
        "void": False,
    }


def test_formula_example_from_the_document():
    # avversaria 22 punti in 10 gare, squadra 15 in 9: 22 - 15 x 10 / 9 = +5
    assert points_diff(22, 10, 15, 9) == 5
    # partite uguali: semplice differenza
    assert points_diff(12, 6, 15, 6) == -3
    # squadra senza partite: Pa - Ps
    assert points_diff(3, 1, 0, 0) == 3
    # prima giornata: 0
    assert points_diff(0, 0, 0, 0) == 0


def test_rounding_is_excel_not_bankers():
    assert excel_round(Fraction(5, 2)) == 3
    assert excel_round(Fraction(-5, 2)) == -3
    assert points_diff(7, 4, 5, 2) == -3  # 7 - 5 x 4 / 2 = -3
    assert points_diff(9, 4, 5, 8) == 7  # 9 - 2,5 = 6,5 -> 7


def test_levels_and_average_strength():
    assert [diff_level(x) for x in (3, 2, -2, -3, None)] == ["strong", "even", "even", "weak", None]
    assert strength([7, 1, 4, -2, 5]) == 3.0  # Inter Playa in casa
    assert strength([-6, -1, -3, 2, -2]) == -2.0  # Lobos totale
    assert strength([1, 0, 0, 0]) == 0.3  # 0,25 -> 0,3
    assert strength([]) is None


def test_table_at_the_date_of_each_game():
    season = LeagueSeason(
        [
            game(1, 0, A, B, 2, 0),  # A 3, B 0
            game(2, 0, C, D, 1, 1),  # C 1, D 1
            game(3, 7, A, C, 3, 0),  # A 6, C 1
            game(4, 7, B, D, 0, 1),  # B 0, D 4
            game(5, 14, B, A, 1, 1),
        ]
    )
    g5 = season.games[-1]
    # prima della gara 5: A 6 punti in 2, B 0 in 2 -> per B l'avversaria e' piu' forte di 6
    assert season.record_before(A, g5) == (6, 2)
    assert season.diff(B, g5) == 6 and season.diff(A, g5) == -6
    # alla prima giornata tutti a 0
    assert season.diff(A, season.games[0]) == 0
    # gara 3 (A-C): A 3 in 1, C 1 in 1 -> per C +2 (alla pari)
    g3 = next(g for g in season.games if g["id"] == 3)
    assert season.diff(C, g3) == 2


def test_apertura_and_clausura_are_separate_tables_and_knockouts_give_no_points():
    season = LeagueSeason(
        [
            game(1, 0, A, B, 3, 0, "Apertura - 1"),
            game(2, 7, A, B, 2, 0, "Apertura - 2"),
            game(3, 14, A, B, 1, 0, "Quarter-finals"),
            game(4, 60, B, A, 0, 0, "Clausura - 1"),
            game(5, 67, B, A, 0, 0, "Clausura - 2"),
        ]
    )
    g3 = next(g for g in season.games if g["id"] == 3)
    assert season.record_before(A, g3) == (6, 2)  # quarto di finale: classifica dell'Apertura
    g5 = next(g for g in season.games if g["id"] == 5)
    assert season.record_before(A, g5) == (1, 1)  # nel Clausura si riparte da zero, il quarto non conta
    assert tournament_of("Clausura - 3") == "clausura" and tournament_of("Regular Season - 3") == ""
    assert is_knockout("Semi-finals") and is_knockout("Play-offs") and not is_knockout("Regular Season - 9")


def test_recent_games_are_only_the_last_played_before_the_match_and_missing_results_are_flagged():
    games = [game(i, i * 7, A, B if i % 2 else C, 1, 0) for i in range(1, 8)]
    games.append(game(20, 60, D, A))  # passata ma senza risultato
    target = game(30, 70, A, D)
    season = LeagueSeason(games + [target])
    recent = season.recent(A, target, limit=5)
    assert [g["id"] for g in recent] == [3, 4, 5, 6, 7]
    assert [g["id"] for g in season.recent(A, target, side="away")] == []
    now = T0 + timedelta(days=70)
    assert [g["id"] for g in season.missing_before(A, target, now=now)] == [20]
    assert season.missing_before(A, target, now=now, side="home") == []


def test_block_has_numbers_border_strength_and_signs():
    games = [
        game(1, 0, A, B, 2, 0, ht=(1, 0)),
        game(2, 0, C, D, 0, 0),
        game(3, 7, A, C, 0, 0, ht=(0, 0)),
        game(4, 7, B, D, 0, 3),
        game(5, 14, D, A, 4, 1, ht=(2, 1)),
    ]
    season = LeagueSeason(games)
    block = _block(season.recent(A, game(9, 30, A, B), limit=5), A, {}, {B: "B", C: "C", D: "D"}, season)
    assert block["enough"] and block["games"] == 3
    # dal 18/11/2026 il numero e' in punti a partita; quello in punti resta in diff_points
    # gara 1: 0; gara 3: C 1 in 1, A 3 in 1 -> -2; gara 5: D 4 in 2, A 4 in 2 -> 0
    assert [r["diff_points"] for r in block["results"]] == [0, -2, 0]
    assert [r["diff"] for r in block["results"]] == [0.0, -2.0, 0.0]
    assert not any(r["bold_ft"] for r in block["results"])
    assert block["strength"] == -0.67 and block["strength_level"] == "weak"
    assert block["strength_points"] == -0.7
    assert block["signs"] == {"ht_games": 3, "x_pt": 1, "u15_pt": 2, "ft_games": 3, "x": 1, "u25": 2, "u35": 2}


def test_border_follows_the_number_not_todays_table():
    # B vince le prime due, poi pareggia con A: per A, alla data, B era piu' forte di 6 punti
    season = LeagueSeason([game(1, 0, B, C, 3, 0), game(2, 7, B, D, 3, 0), game(3, 14, A, B, 1, 1), game(4, 21, A, C, 2, 0), game(5, 28, D, A, 0, 0)])
    block = _block(season.recent(A, game(9, 40, A, C), limit=5), A, {A: 1, B: 9}, {}, season)
    first = block["results"][0]
    # B 6 punti in 2 gare (3 a partita), A nessuna gara: +3 punti a partita
    assert first["diff_points"] == 6 and first["diff"] == 3.0 and first["level"] == "strong"
    # oggi B e' 9ª e A 1ª: con la classifica di oggi non ci sarebbe la cornice, alla data si'
    assert first["bold_ft"] and first["bold_ht"] and first["opponent_rank"] == 9


def test_goal_form_alert_above_2_7():
    def block(scores):
        return {"enough": True, "results": [{"ft": s} for s in scores]}

    # Hammarby-Elfsborg: 28 gol in 10 gare = 2,8
    form = goal_form(block(["3-1", "2-2", "4-0", "1-1", "2-1"]), block(["2-1", "1-0", "1-2", "0-3", "1-0"]))
    assert form["goals"] == 28 and form["games"] == 10 and form["avg"] == 2.8 and form["alert"]
    assert not goal_form(block(["2-1"] * 5), block(["1-1", "2-1", "1-0", "2-0", "1-1"]))["alert"]  # 27 / 10 = 2,7
    assert goal_form({"enough": False}, block(["9-9"])) is None


def test_signs_count_each_line():
    s = signs([{"ht": "0-0", "ft": "1-1"}, {"ht": "1-1", "ft": "2-2"}, {"ht": None, "ft": "3-1"}])
    assert s == {"ht_games": 2, "x_pt": 2, "u15_pt": 1, "ft_games": 3, "x": 2, "u25": 1, "u35": 1}


# --- 18/11/2026: documento "Errori, modifiche, migliorie" di Giovanni ---

from app.services.analyst.table import match_cutoff, moved_to, standings  # noqa: E402


def test_postponed_match_keeps_the_form_at_the_original_date():
    # FC Tulsa: in lista il 5 luglio, giocata il 6 agosto; nel frattempo altre due gare
    games = [
        game(1, 0, A, B, 2, 0),
        game(2, 10, A, C, 1, 0),  # dopo la data originale
        game(3, 20, A, D, 0, 0),  # dopo la data originale
        game(9, 30, A, B),  # la gara rinviata, ora il 31° giorno
    ]
    season = LeagueSeason(games)
    original = T0 + timedelta(days=5)
    cutoff = match_cutoff(original, games[3]["kickoff"])
    assert cutoff == original
    recent = season.recent(A, {"id": 9, "kickoff": cutoff})
    assert [g["id"] for g in recent] == [1]
    # rinviata: segnalata, con la data nuova
    moved = moved_to(original, games[3]["kickoff"], "NS")
    assert moved == {"status": "moved", "kickoff": games[3]["kickoff"].isoformat()}
    assert moved_to(original, original + timedelta(hours=2), "NS") is None
    assert moved_to(original, original, "PST")["status"] == "PST"


def test_table_at_the_date_does_not_contain_the_match_itself():
    games = [game(1, 0, A, B, 1, 0), game(2, 0, C, D, 0, 0), game(3, 7, B, A, 3, 0)]
    season = LeagueSeason(games)
    before = season.table_games_before({"id": 3, "kickoff": games[2]["kickoff"]})
    ranks, _ = standings([(g["home"], g["away"], g["gh"], g["ga"]) for g in before])
    assert ranks[A] == 1 and ranks[B] == 4  # prima della gara del 7° giorno
    after = season.table_games_before({"id": 99, "kickoff": T0 + timedelta(days=30)})
    ranks_after, _ = standings([(g["home"], g["away"], g["gh"], g["ga"]) for g in after])
    assert ranks_after[B] == 1


def test_two_games_a_few_hours_apart_are_a_data_error():
    # Rosario: lo stesso codice per due squadre, due gare il 1° novembre alle 19:00
    games = [game(1, 0, A, B, 3, 2), {**game(2, 0, C, A, 1, 5), "kickoff": T0 + timedelta(minutes=30)}, game(3, 7, A, D)]
    season = LeagueSeason(games)
    problems = season.data_problems(A, {"id": 3, "kickoff": games[2]["kickoff"]})
    assert len(problems) == 1 and "due gare" in problems[0]
    assert season.data_problems(B, {"id": 3, "kickoff": games[2]["kickoff"]}) == []
    # un recupero il giorno dopo (19 ore) non e' un errore
    ok = LeagueSeason([game(1, 0, A, B, 1, 0), {**game(2, 0, A, C, 1, 0), "kickoff": T0 + timedelta(hours=19)}])
    assert ok.data_problems(A, {"id": 9, "kickoff": T0 + timedelta(days=5)}) == []


def test_more_games_than_the_median_plus_four_is_a_data_error():
    teams = [10, 11, 12, 13, 14, 15]
    games, gid = [], 0
    for day in range(6):  # 6 giornate da 3 gare: tutte le squadre a 6 gare
        for i in range(3):
            gid += 1
            games.append(game(gid, day * 7, teams[(i + day) % 6], teams[(i + day + 3) % 6], 1, 1))
    for k in range(5):  # la squadra 10 ne ha 5 in piu' (fusa con un'altra), a giorni diversi
        gid += 1
        games.append(game(gid, 50 + k * 3, 10, 99, 2, 0))
    season = LeagueSeason(games)
    target = {"id": 1000, "kickoff": T0 + timedelta(days=80)}
    assert any("mediana" in p for p in season.data_problems(10, target))
    assert season.data_problems(11, target) == []


def test_remaining_games_exact_with_calendar_or_estimated():
    # calendario noto: gare da giocare oltre 3 giorni nel nostro archivio
    now = T0 + timedelta(days=8)
    games = [game(1, 0, A, B, 1, 0), game(2, 0, C, D, 0, 0), game(3, 7, A, C), game(4, 14, D, A), game(5, 21, A, B)]
    season = LeagueSeason(games)
    target = {"id": 3, "kickoff": games[2]["kickoff"]}
    assert season.remaining(A, target, now=now) == {"games": 3, "exact": True}
    # senza calendario: lunghezza della stagione precedente (30 gare), A ne ha giocata 1
    season = LeagueSeason(games[:3], {"": 30})
    est = season.remaining(A, target, now=now)
    assert est == {"games": 29, "exact": False, "season_games": 30}
    # senza stagione precedente: nessuna stima (non si inventa "andata e ritorno")
    assert LeagueSeason(games[:3]).remaining(A, target, now=now) is None
    # Apertura: la lunghezza dell'Apertura dell'anno prima
    ap = LeagueSeason(
        [game(1, 0, A, B, 1, 0, rnd="Apertura - 1"), game(2, 0, C, D, 0, 0, rnd="Apertura - 1"), game(3, 7, A, C, rnd="Apertura - 2")],
        {"apertura": 15, "clausura": 17},
    )
    assert ap.remaining(A, {"id": 3, "kickoff": T0 + timedelta(days=7)}, now=now)["games"] == 14
    # turni con nomi diversi dall'anno prima ma tornei della stessa lunghezza (Costa Rica)
    cr = LeagueSeason(games[:3], {"apertura": 14, "clausura": 14})
    assert cr.remaining(A, target, now=now)["games"] == 13
    # gara a eliminazione diretta: fase finale
    ko = LeagueSeason(games[:2] + [game(3, 7, A, C, rnd="Quarter-finals")], {"": 30})
    assert ko.remaining(A, target, now=now) == {"games": 0, "exact": True, "phase": "knockout"}
    # stagione regolare finita
    done = LeagueSeason(games[:3], {"": 1})
    assert done.remaining(A, target, now=now)["phase"] == "end"


def test_season_lengths_from_the_previous_season():
    prev = [(A, B, "Regular Season - 1"), (C, D, "Regular Season - 1"), (A, C, "Regular Season - 2"), (B, D, "Regular Season - 2"), (A, B, "Final")]
    assert season_lengths(prev) == {"": 2}
    split = [(A, B, "Apertura - 1"), (C, D, "Apertura - 1"), (A, B, "Clausura - 1"), (C, D, "Clausura - 1"), (A, C, "Clausura - 2"), (B, D, "Clausura - 2")]
    assert season_lengths(split) == {"apertura": 1, "clausura": 2}


# --- 18/11/2026, fase 2-3: punti a partita, primo tempo, campionati ammessi, affidabilita' ---

from app.services.analyst.form import alert_markets, ppg_diff, ppg_level, pt_form, strength_ppg  # noqa: E402
from app.services.analyst.leagues import league_admitted, parse_leagues  # noqa: E402
from app.services.analyst.table import _reliability  # noqa: E402


def test_points_per_game_difference_and_threshold():
    # avversaria 22 punti in 10, squadra 15 in 9: 2,2 - 1,67 = +0,53
    assert ppg_diff(22, 10, 15, 9) == 0.53
    assert ppg_diff(0, 0, 0, 0) == 0.0
    assert ppg_diff(6, 2, 0, 0) == 3.0  # chi non ha giocato conta 0
    assert [ppg_level(x) for x in (0.3, 0.29, -0.29, -0.3, None)] == ["strong", "even", "even", "weak", None]
    assert strength_ppg([0.5, 0.25, -0.1]) == 0.22


def test_pt_form_average_of_the_two_teams_and_alert():
    def block(halves):
        return {"enough": True, "results": [{"ht": h} for h in halves]}

    # esempio di Giovanni: casa 5-3 in 5 gare, ospite 4-7 in 5 -> 19 gol PT in 10 = 1,9
    home = block(["1-0", "2-1", "0-0", "1-2", "1-0"])
    away = block(["0-2", "1-1", "2-2", "1-1", "0-1"])
    f = pt_form(home, away)
    assert f["goals"] == 19 and f["games"] == 10 and f["avg"] == 1.9 and f["alert"]
    assert f["x_pt"] == 4 and f["x_pct"] == 40 and f["u15_pt"] == 4 and f["u15_pct"] == 40
    calm = pt_form(block(["0-0", "1-0", "0-0"]), block(["0-1", "0-0", "1-0"]))
    assert calm["avg"] == 0.5 and not calm["alert"]
    assert pt_form({"enough": False}, away) is None
    row = {"goal_form": {"alert": True, "markets": ["UNDER_2_5", "UNDER_PT_1_5"]}, "pt_form": f}
    assert alert_markets(row) == {"UNDER_2_5", "UNDER_PT_1_5", "DRAW_PT"}
    assert alert_markets({"goal_form": None, "pt_form": calm}) == set()


def test_admitted_leagues_file():
    parsed = parse_leagues("# commento con | barra\nItaly|Serie A\nCosta-Rica|Primera División\n\n")
    assert parsed == {("italy", "serie a"), ("costa-rica", "primera división")}
    # il file vero: ammessi e non ammessi del 17-18 novembre
    assert league_admitted("Italy", "Serie C - Girone A")
    assert league_admitted("Costa-Rica", "Primera División")
    assert league_admitted("nigeria", " NPFL ")
    assert not league_admitted("Costa-Rica", "Liga de Ascenso")
    assert not league_admitted("England", "National League")
    assert not league_admitted("England", "League Two")
    assert not league_admitted("Argentina", "Torneo Federal A")
    assert not league_admitted("Scotland", "Football League - Lowland League")


def test_reliability_green_yellow_red():
    ko = T0 + timedelta(days=10)
    ok_cards = {"home": {"available": True}, "away": {"available": True}}
    green = _reliability(problems=[], future_games=[], standings_complete=True, odds_at=ko - timedelta(hours=3), kickoff=ko, cards=ok_cards)
    assert green["level"] == "green" and not green["yellow"] and not green["red"]
    yellow = _reliability(
        problems=[], future_games=[], standings_complete=False, odds_at=ko - timedelta(hours=20), kickoff=ko,
        cards={"home": {"available": False}, "away": {"available": True}},
    )
    assert yellow["level"] == "yellow" and len(yellow["yellow"]) == 3
    red = _reliability(problems=["Rosario: due gare"], future_games=[{"id": 1}], standings_complete=True, odds_at=None, kickoff=ko, cards=ok_cards)
    assert red["level"] == "red" and len(red["red"]) == 2
