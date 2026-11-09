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
    diffs = [r["diff"] for r in block["results"]]
    # gara 1: 0; gara 3: C 1 in 1, A 3 in 1 -> -2; gara 5: D 4 in 2, A 4 in 2 -> 0
    assert diffs == [0, -2, 0]
    assert not any(r["bold_ft"] for r in block["results"])
    assert block["strength"] == -0.7 and block["strength_level"] == "even"
    assert block["signs"] == {"ht_games": 3, "x_pt": 1, "u15_pt": 2, "ft_games": 3, "x": 1, "u25": 2, "u35": 2}


def test_border_follows_the_number_not_todays_table():
    # B vince le prime due, poi pareggia con A: per A, alla data, B era piu' forte di 6 punti
    season = LeagueSeason([game(1, 0, B, C, 3, 0), game(2, 7, B, D, 3, 0), game(3, 14, A, B, 1, 1), game(4, 21, A, C, 2, 0), game(5, 28, D, A, 0, 0)])
    block = _block(season.recent(A, game(9, 40, A, C), limit=5), A, {A: 1, B: 9}, {}, season)
    first = block["results"][0]
    assert first["diff"] == 6 and first["level"] == "strong"
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
