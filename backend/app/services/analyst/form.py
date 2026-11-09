"""Forma alla data della gara per il Diario analisi (documento "Modifiche" di Giovanni, 09/11/2026).

- Solo gare della stagione in corso, dello stesso campionato, in ordine di data: mai la stagione passata
  (prima le ultime gare arrivavano dalla fotografia del calcolo Cecchino, che a inizio stagione completa
  apposta con la stagione precedente: 19 gare su 427 nel Diario).
- Numero +/- sotto ogni risultato: punti dell'avversaria meno quelli della squadra, alla data di quella gara
  e a parita' di partite: Diff = ARROTONDA(Pa - Ps x Ga / Gs; 0). Partite uguali: Pa - Ps. Gs = 0: Pa - Ps.
  Da +3 avversaria piu' forte (cornice e grassetto), da -3 piu' debole, in mezzo alla pari.
- La classifica alla data si rifa' con le sole gare del campionato giocate prima (3 punti vittoria, 1 pari).
  Due eccezioni, per non mescolare tornei diversi: Apertura e Clausura (stessa "stagione" del fornitore in
  Messico, Colombia, Paraguay...) hanno classifiche separate; le gare a eliminazione diretta (quarti,
  semifinali, finali, play-off) non danno punti in classifica ma restano nella forma.
- Forza media = media dei +/- delle gare mostrate, una cifra decimale.
- Segni: quante volte e' uscito X PT, Under 1,5 PT, X, Under 2,5, Under 3,5 nelle gare mostrate.
- "Forma da gol": gol del finale nelle gare in casa della squadra di casa e fuori dell'ospite (fino a 5 per
  parte); sopra 2,7 a partita compare un avviso arancione su Under 2,5 e Under 1,5 PT. Solo un avviso.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

STRONG_DIFF = 3  # da +3 avversaria piu' forte di almeno una vittoria; da -3 piu' debole
GOAL_FORM_THRESHOLD = 2.7  # "sopra 2,7" gol a partita
GOAL_FORM_MARKETS = ("UNDER_2_5", "UNDER_PT_1_5")
_TOURNAMENTS = ("apertura", "clausura")
_KNOCKOUT_WORDS = ("final", "round of", "play-off", "playoff", "play off", "knockout", "1/8", "1/4", "1/2")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def excel_round(value: Fraction | float, digits: int = 0) -> Decimal:
    """ARROTONDA di Excel: la meta' si arrotonda lontano dallo zero (round() di Python va al pari)."""
    if isinstance(value, Fraction):
        exact = Decimal(value.numerator) / Decimal(value.denominator)
    else:
        exact = Decimal(str(value))
    return exact.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def points_diff(pa: int, ga: int, ps: int, gs: int) -> int:
    """Differenza punti avversaria - squadra a parita' di partite (formula di Giovanni)."""
    if gs == 0 or ga == gs:
        return int(pa - ps)
    return int(excel_round(Fraction(pa) - Fraction(ps * ga, gs)))


def diff_level(diff: int | None) -> str | None:
    if diff is None:
        return None
    return "strong" if diff >= STRONG_DIFF else "weak" if diff <= -STRONG_DIFF else "even"


def tournament_of(round_name: str | None) -> str:
    r = (round_name or "").strip().lower()
    return next((t for t in _TOURNAMENTS if r.startswith(t)), "")


def is_knockout(round_name: str | None) -> bool:
    r = (round_name or "").strip().lower()
    return any(w in r for w in _KNOCKOUT_WORDS)


def _key(g: dict[str, Any]) -> tuple[datetime, int]:
    return (g["kickoff"] or _EPOCH, int(g["id"]))


@dataclass
class _Timeline:
    keys: list[tuple[datetime, int]] = field(default_factory=list)
    points: list[int] = field(default_factory=list)  # cumulati DOPO ogni gara


class LeagueSeason:
    """Le gare di un campionato in una stagione, per la classifica a una data qualsiasi.

    games: dizionari con id, kickoff, home, away, gh, ga (gol finali, None se non finita) e round."""

    def __init__(self, games: list[dict[str, Any]]):
        self.games = sorted(games, key=_key)
        self.finished = [g for g in self.games if g["gh"] is not None and g["ga"] is not None]
        # gare di ogni squadra (in ordine di data): il sabato le partite del giorno sono centinaia
        self._by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for g in self.games:
            self._by_team[int(g["home"])].append(g)
            self._by_team[int(g["away"])].append(g)
        # torneo della classifica di ogni gara: le gare a eliminazione prendono quello in corso
        self.table_of: dict[int, str] = {}
        self._lines: dict[tuple[str, int], _Timeline] = defaultdict(_Timeline)
        current = ""
        for g in self.finished:
            if is_knockout(g.get("round")):
                self.table_of[int(g["id"])] = current
                continue
            current = tournament_of(g.get("round"))
            self.table_of[int(g["id"])] = current
            for team, gf, gs in ((g["home"], g["gh"], g["ga"]), (g["away"], g["ga"], g["gh"])):
                line = self._lines[(current, int(team))]
                line.keys.append(_key(g))
                line.points.append((line.points[-1] if line.points else 0) + (3 if gf > gs else 1 if gf == gs else 0))

    def record_before(self, team: int, game: dict[str, Any]) -> tuple[int, int]:
        """Punti e partite della squadra prima di quella gara, nel torneo di quella gara."""
        line = self._lines.get((self.table_of.get(int(game["id"]), ""), int(team)))
        if line is None:
            return 0, 0
        n = bisect_left(line.keys, _key(game))
        return (line.points[n - 1] if n else 0), n

    def diff(self, team: int, game: dict[str, Any]) -> int:
        opponent = game["away"] if game["home"] == team else game["home"]
        ps, gs = self.record_before(team, game)
        pa, ga = self.record_before(opponent, game)
        return points_diff(pa, ga, ps, gs)

    def recent(self, team: int, before: dict[str, Any], *, side: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Ultime gare finite della squadra prima di "before" (side: "home", "away" o None = tutte), dalla piu' vecchia."""
        cutoff = _key(before)
        out = [
            g
            for g in self._by_team.get(int(team), [])
            if g["gh"] is not None
            and g["ga"] is not None
            and _key(g) < cutoff
            and int(g["id"]) != int(before["id"])
            and (side is None or (side == "home" and g["home"] == team) or (side == "away" and g["away"] == team))
        ]
        return out[-limit:]

    def missing_before(self, team: int, before: dict[str, Any], *, now: datetime, side: str | None = None) -> list[dict[str, Any]]:
        """Gare gia' passate (da piu' di 3 ore) ma senza risultato nel nostro archivio: le "ultime" potrebbero non essere davvero le ultime."""
        cutoff = _key(before)
        out = []
        for g in self._by_team.get(int(team), []):
            if g["gh"] is not None or g.get("void") or g["kickoff"] is None:
                continue
            if _key(g) >= cutoff or (now - g["kickoff"]).total_seconds() < 3 * 3600:
                continue
            if side is None or (side == "home" and g["home"] == team) or (side == "away" and g["away"] == team):
                out.append(g)
        return out


def strength(diffs: list[int]) -> float | None:
    if not diffs:
        return None
    return float(excel_round(Fraction(sum(diffs), len(diffs)), 1))


def signs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Quante volte e' uscito il segno nelle gare mostrate (risultati dal punto di vista della squadra)."""
    ht = [tuple(int(x) for x in r["ht"].split("-")) for r in rows if r.get("ht")]
    ft = [tuple(int(x) for x in r["ft"].split("-")) for r in rows if r.get("ft")]
    return {
        "ht_games": len(ht),
        "x_pt": sum(1 for a, b in ht if a == b),
        "u15_pt": sum(1 for a, b in ht if a + b < 1.5),
        "ft_games": len(ft),
        "x": sum(1 for a, b in ft if a == b),
        "u25": sum(1 for a, b in ft if a + b < 2.5),
        "u35": sum(1 for a, b in ft if a + b < 3.5),
    }


def goal_form(home_block: dict[str, Any], away_block: dict[str, Any]) -> dict[str, Any] | None:
    """Media gol del finale nelle gare in casa della squadra di casa piu' quelle fuori dell'ospite."""
    if not home_block.get("enough") or not away_block.get("enough"):
        return None
    goals = games = 0
    for block in (home_block, away_block):
        for r in block["results"]:
            if r.get("ft"):
                a, b = (int(x) for x in r["ft"].split("-"))
                goals += a + b
                games += 1
    if not games:
        return None
    avg = goals / games
    return {
        "goals": goals,
        "games": games,
        "avg": float(excel_round(Fraction(goals, games), 1)),
        "alert": avg > GOAL_FORM_THRESHOLD,
        "threshold": GOAL_FORM_THRESHOLD,
        "markets": list(GOAL_FORM_MARKETS),
    }
