"""Indici a 360 gradi per partita, letti dal modello di riferimento.

Non cambiano le probabilita': le raccontano. Tutto e' pre-partita:
- valori della partita = uscite del modello (gia' walk-forward) e calendario;
- confronti con il campionato (media gol, frequenza pareggi, percentili) usano
  solo partite dei giorni PRECEDENTI dello stesso campionato.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.services.cecchino_v3.constants import (
    INDEX_CLASS_EDGES,
    INDEX_CLASSES,
    INDEX_MIN_HISTORY,
    RELIABILITY_EARLY_FACTOR,
    RELIABILITY_FULL_EVIDENCE,
    RELIABILITY_HIGH,
    RELIABILITY_MEDIUM,
    RELIABILITY_NEW_TEAM_FACTOR,
    RELIABILITY_SUPREMACY_SCALE,
    RELIABILITY_TOTAL_SCALE,
)
from app.services.cecchino_v3.data import MatchRecord
from app.services.cecchino_v3.discipline import DisciplineFeatures

SPECIALISTS: tuple[str, ...] = ("forza", "sot", "shots")


@dataclass
class IndexInput:
    """Tutto cio' che serve per gli indici di una partita."""

    match: MatchRecord
    prob_home: float
    prob_draw: float
    prob_away: float
    prob_over_2_5: float
    lambda_home: float
    lambda_away: float
    home_evidence: float
    away_evidence: float
    specialists: dict[str, Any]
    new_team_home: bool = False  # neopromossa o nuova nel dataset, prima stagione
    new_team_away: bool = False
    discipline: DisciplineFeatures | None = None


def percentile_class(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    return INDEX_CLASSES[bisect.bisect_right(list(INDEX_CLASS_EDGES), percentile)]


class RollingPercentile:
    """Percentile di un valore tra quelli gia' inseriti (giorni precedenti)."""

    def __init__(self) -> None:
        self._values: list[float] = []

    def percentile(self, value: float) -> float | None:
        if len(self._values) < INDEX_MIN_HISTORY:
            return None
        rank = bisect.bisect_right(self._values, value)
        return round(100.0 * rank / len(self._values), 2)

    def add(self, value: float) -> None:
        bisect.insort(self._values, value)


@dataclass
class _LeagueHistory:
    matches: int = 0
    goals: float = 0.0
    draws: int = 0
    percentiles: dict[str, RollingPercentile] = field(default_factory=dict)

    def pct(self, name: str) -> RollingPercentile:
        if name not in self.percentiles:
            self.percentiles[name] = RollingPercentile()
        return self.percentiles[name]


def equilibrium_value(prob_home: float, prob_away: float) -> float:
    """100 = 1 e 2 alla pari, 0 = uno dei due non ha probabilita'."""
    total = prob_home + prob_away
    if total <= 0:
        return 100.0
    return 100.0 * (1.0 - abs(prob_home - prob_away) / total)


def specialist_disagreement(specialists: dict[str, Any]) -> tuple[float | None, float | None]:
    """Differenza massima tra specialisti su differenza di forza (log casa/ospite)
    e su gol totali (log casa+ospite)."""
    supremacy: list[float] = []
    totals: list[float] = []
    for name in SPECIALISTS:
        opinion = specialists.get(name) if isinstance(specialists, dict) else None
        if not isinstance(opinion, dict):
            continue
        home, away = opinion.get("home"), opinion.get("away")
        if home is None or away is None or home <= 0 or away <= 0:
            continue
        supremacy.append(math.log(home / away))
        totals.append(math.log(home + away))
    if len(supremacy) < 2:
        return None, None
    return max(supremacy) - min(supremacy), max(totals) - min(totals)


def reliability(
    *,
    home_evidence: float,
    away_evidence: float,
    disagreement_supremacy: float | None,
    disagreement_total: float | None,
    new_team: bool,
    early: bool,
) -> dict[str, Any]:
    knowledge = min(1.0, min(home_evidence, away_evidence) / RELIABILITY_FULL_EVIDENCE)
    if disagreement_supremacy is None or disagreement_total is None:
        agreement = 1.0
    else:
        agreement = 1.0 / (
            1.0
            + disagreement_supremacy / RELIABILITY_SUPREMACY_SCALE
            + disagreement_total / RELIABILITY_TOTAL_SCALE
        )
    value = 100.0 * knowledge * agreement
    if new_team:
        value *= RELIABILITY_NEW_TEAM_FACTOR
    if early:
        value *= RELIABILITY_EARLY_FACTOR
    if value >= RELIABILITY_HIGH:
        klass = "alta"
    elif value >= RELIABILITY_MEDIUM:
        klass = "media"
    else:
        klass = "bassa"
    return {
        "value": round(value, 1),
        "class": klass,
        "knowledge": round(knowledge, 3),
        "agreement": round(agreement, 3),
        "disagreement_supremacy": round(disagreement_supremacy, 4) if disagreement_supremacy is not None else None,
        "disagreement_total": round(disagreement_total, 4) if disagreement_total is not None else None,
        "new_team": new_team,
        "early_season": early,
    }


def _form_block(detail: dict[str, Any] | None, side: str, matches: Any) -> dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None
    attack_shots = detail.get(f"{side}_attack_shots")
    defence_shots = detail.get(f"{side}_defence_shots")
    attack_goals = detail.get(f"{side}_attack_goals")
    defence_goals = detail.get(f"{side}_defence_goals")
    if None in (attack_shots, defence_shots, attack_goals, defence_goals):
        return None
    return {
        # positivo = sopra le attese (attacca piu' del previsto e concede meno)
        "gioco": round(float(attack_shots) - float(defence_shots), 4),
        "risultati": round(float(attack_goals) - float(defence_goals), 4),
        "matches": matches,
    }


def compute_indices(inputs: Iterable[IndexInput]) -> dict[int, dict[str, Any]]:
    """Indici per ogni partita; gli input devono essere in ordine cronologico."""
    ordered = list(inputs)
    leagues: dict[str, _LeagueHistory] = {}
    out: dict[int, dict[str, Any]] = {}

    i = 0
    n = len(ordered)
    while i < n:
        j = i
        while j < n and ordered[j].match.day == ordered[i].match.day:
            j += 1
        day = ordered[i:j]
        pending: list[tuple[_LeagueHistory, dict[str, float], IndexInput]] = []

        for item in day:
            m = item.match
            league = leagues.setdefault(m.competition, _LeagueHistory())
            has_history = league.matches >= INDEX_MIN_HISTORY

            eq = equilibrium_value(item.prob_home, item.prob_away)
            total_goals = item.lambda_home + item.lambda_away
            league_goals = league.goals / league.matches if has_history else None
            league_draws = league.draws / league.matches if has_history else None
            eq_pct = league.pct("equilibrio").percentile(eq)
            draw_pct = league.pct("pareggio").percentile(item.prob_draw)
            goals_pct = league.pct("intensita_goal").percentile(total_goals)

            specialists = item.specialists or {}
            form_detail = specialists.get("form") if isinstance(specialists, dict) else None
            calendar = specialists.get("calendar") if isinstance(specialists, dict) else None
            d_sup, d_tot = specialist_disagreement(specialists)
            rest_home = calendar.get("rest_days_home") if isinstance(calendar, dict) else None
            rest_away = calendar.get("rest_days_away") if isinstance(calendar, dict) else None

            if item.prob_home > item.prob_away:
                favourite = "home"
            elif item.prob_away > item.prob_home:
                favourite = "away"
            else:
                favourite = "none"

            discipline = item.discipline.detail if item.discipline is not None else None
            out[m.lab_match_id] = {
                "equilibrio": {
                    "value": round(eq, 2),
                    "favourite": favourite,
                    "gap_pp": round(abs(item.prob_home - item.prob_away) * 100.0, 2),
                    "percentile": eq_pct,
                    "class": percentile_class(eq_pct),
                },
                "pareggio": {
                    "prob": round(item.prob_draw, 4),
                    "league_draw_rate": round(league_draws, 4) if league_draws is not None else None,
                    "delta_pp": (
                        round((item.prob_draw - league_draws) * 100.0, 2) if league_draws is not None else None
                    ),
                    "percentile": draw_pct,
                    "class": percentile_class(draw_pct),
                },
                "intensita_goal": {
                    "total": round(total_goals, 3),
                    "home": round(item.lambda_home, 3),
                    "away": round(item.lambda_away, 3),
                    "league_goals_avg": round(league_goals, 3) if league_goals is not None else None,
                    "ratio": round(total_goals / league_goals, 3) if league_goals else None,
                    "p_over_2_5": round(item.prob_over_2_5, 4),
                    "percentile": goals_pct,
                    "class": percentile_class(goals_pct),
                },
                "forma": {
                    "home": _form_block(form_detail, "home", (form_detail or {}).get("matches_home")),
                    "away": _form_block(form_detail, "away", (form_detail or {}).get("matches_away")),
                },
                "calendario": {
                    "rest_days_home": rest_home,
                    "rest_days_away": rest_away,
                    "rest_diff": (rest_home - rest_away) if rest_home is not None and rest_away is not None else None,
                    "final_phase": m.phase == "final",
                },
                "disciplina": discipline,
                "affidabilita": reliability(
                    home_evidence=item.home_evidence,
                    away_evidence=item.away_evidence,
                    disagreement_supremacy=d_sup,
                    disagreement_total=d_tot,
                    new_team=item.new_team_home or item.new_team_away,
                    early=not m.eval_eligible,
                ),
            }
            pending.append((league, {"equilibrio": eq, "pareggio": item.prob_draw, "intensita_goal": total_goals}, item))

        # solo dopo aver calcolato il giorno si aggiornano storia e percentili
        for league, values, item in pending:
            for name, value in values.items():
                league.pct(name).add(value)
            league.matches += 1
            league.goals += item.match.ft_home + item.match.ft_away
            league.draws += int(item.match.ft_home == item.match.ft_away)
        i = j
    return out


# --- controlli di coerenza ---------------------------------------------------------


def _strictly_monotonic(values: list[float], *, increasing: bool) -> bool:
    if len(values) < 2:
        return False
    pairs = zip(values, values[1:])
    return all(b > a for a, b in pairs) if increasing else all(b < a for a, b in pairs)


def coherence_checks(
    inputs: list[IndexInput], indices: dict[int, dict[str, Any]], judge_seasons: tuple[str, ...]
) -> list[dict[str, Any]]:
    """C1-C4 sulle stagioni di giudizio, partite idonee."""
    rows = [
        (item, indices[item.match.lab_match_id])
        for item in inputs
        if item.match.season_label in judge_seasons
        and item.match.eval_eligible
        and item.match.lab_match_id in indices
    ]

    def by_class(index_name: str, classes: tuple[str, ...], metric) -> list[dict[str, Any]]:
        buckets: dict[str, list[float]] = {c: [] for c in classes}
        for item, idx in rows:
            klass = idx[index_name]["class"]
            if klass in buckets:
                buckets[klass].append(metric(item))
        return [
            {"class": c, "n": len(v), "value": round(sum(v) / len(v), 5) if v else None}
            for c, v in buckets.items()
        ]

    def goals(item: IndexInput) -> float:
        return float(item.match.ft_home + item.match.ft_away)

    def draw(item: IndexInput) -> float:
        return float(item.match.ft_home == item.match.ft_away)

    def favourite_won(item: IndexInput) -> float:
        m = item.match
        if item.prob_home >= item.prob_away:
            return float(m.ft_home > m.ft_away)
        return float(m.ft_away > m.ft_home)

    def brier_1x2(item: IndexInput) -> float:
        m = item.match
        outcomes = (m.ft_home > m.ft_away, m.ft_home == m.ft_away, m.ft_home < m.ft_away)
        probs = (item.prob_home, item.prob_draw, item.prob_away)
        return sum((float(o) - p) ** 2 for o, p in zip(outcomes, probs)) / 3.0

    checks = [
        ("C1", "Intensita' goal -> gol reali medi sempre crescenti", "intensita_goal", INDEX_CLASSES, goals, True),
        ("C2", "Credibilita' pareggio -> frequenza pareggi sempre crescente", "pareggio", INDEX_CLASSES, draw, True),
        ("C3", "Equilibrio -> vittorie del favorito sempre decrescenti", "equilibrio", INDEX_CLASSES, favourite_won, False),
        ("C4", "Affidabilita' bassa -> alta: errore 1X2 sempre decrescente", "affidabilita", ("bassa", "media", "alta"), brier_1x2, False),
    ]
    out: list[dict[str, Any]] = []
    for code, label, index_name, classes, metric, increasing in checks:
        table = by_class(index_name, classes, metric)
        values = [r["value"] for r in table]
        complete = all(v is not None for v in values)
        out.append(
            {
                "code": code,
                "label": label,
                "index": index_name,
                "increasing": increasing,
                "rows": table,
                "passed": complete and _strictly_monotonic([float(v) for v in values], increasing=increasing),
            }
        )
    return out
