"""Intensita' Goal V2.5: stessi 4 pilastri e stessa classe finale della V2, riscritti.

Difetti della V2 corretti:
- "produzione offensiva" guardava solo i gol fatti della squadra di casa: in V2.5 sono
  gli attacchi di entrambe le squadre;
- tutti i valori erano assoluti e i percentili mescolavano campionati (un campionato
  da tanti gol finiva sempre "alto"): in V2.5 attacco, difesa e ritmo sono rapportati
  alla media del proprio campionato;
- la "stabilita' offensiva" era la deviazione standard dei gol fatti, che cresce con
  la media gol (in pratica un altro indicatore di gol): in V2.5 e' la costanza nel
  segnare (quota di partite con almeno un gol, rispetto a quanto ci si aspetta);
- i percentili erano ricalcolati durante la stagione (classi mancanti a inizio anno e
  con significato diverso nel tempo): in V2.5 le scale sono congelate (vedi scales.py);
- la classe finale era la media dei 4 pilastri, con la stabilita' contata al contrario:
  in V2.5 e' la probabilita' Over 2.5 del modello gol V2.5, cioe' quanta intensita' di
  gol ci si aspetta davvero dalla partita.
"""

from __future__ import annotations

from math import exp
from typing import Any

from app.services.cecchino.cecchino_fixture_history import team_goals_in_fixture
from app.services.cecchino_v25 import scales
from app.services.cecchino_v25.constants import GOAL_HIT_PRIOR_MATCHES, GOAL_RATE_PRIOR_MATCHES
from app.services.cecchino_v25.goals import GoalOutput
from app.services.cecchino_v25.league import LeagueReference

MODULE_VERSION = "cecchino_v25_goal_intensity_v1"
RECENT_MATCHES = 10
MIN_TEAM_MATCHES = 3

SCALE_ATTACK = "gi_attack_ratio"
SCALE_DEFENCE = "gi_defence_ratio"
SCALE_TEMPO = "gi_tempo_ratio"
SCALE_CONSISTENCY = "gi_scoring_consistency"
SCALE_FINAL = "gi_over_2_5_probability"

PILLARS = (
    ("offensive_production", "Produzione offensiva"),
    ("defensive_solidity", "Solidita' difensiva"),
    ("match_tempo", "Ritmo partita"),
    ("offensive_stability", "Stabilita' offensiva"),
)


def _team_scores(fixtures: list, team_id: int) -> list[tuple[int, int]]:
    out = []
    for f in fixtures:
        gf, ga = team_goals_in_fixture(f, team_id)
        if gf is not None and ga is not None:
            out.append((int(gf), int(ga)))
    return out


def raw_features(contexts: Any, league: LeagueReference, goals: GoalOutput) -> dict[str, float] | None:
    gc = getattr(contexts, "goal_contexts", None)
    if gc is None or goals.lambda_home is None:
        return None
    totals = gc.totals
    home = _team_scores(totals.home_fixtures, gc.home_team_id)
    away = _team_scores(totals.away_fixtures, gc.away_team_id)
    if len(home) < MIN_TEAM_MATCHES or len(away) < MIN_TEAM_MATCHES:
        return None
    mu = league.team_goals
    k = GOAL_RATE_PRIOR_MATCHES

    def shrunk(values: list[int]) -> float:
        return (sum(values) + k * mu) / (len(values) + k)

    attack = (shrunk([s[0] for s in home]) + shrunk([s[0] for s in away])) / 2.0
    defence = (shrunk([s[1] for s in home]) + shrunk([s[1] for s in away])) / 2.0
    expected_score_rate = 1.0 - exp(-mu)
    kh = GOAL_HIT_PRIOR_MATCHES

    def consistency(scores: list[tuple[int, int]]) -> float:
        recent = scores[-RECENT_MATCHES:]
        hits = sum(1 for gf, _ in recent if gf >= 1)
        return (hits + kh * expected_score_rate) / (len(recent) + kh)

    over_25 = goals.probability("OVER_2_5")
    return {
        "attack_ratio": attack / mu,
        "defence_ratio": defence / mu,
        "tempo_ratio": (goals.lambda_home + goals.lambda_away) / league.total_goals,  # type: ignore[operator]
        "scoring_consistency": ((consistency(home) + consistency(away)) / 2.0) / expected_score_rate,
        "over_2_5_probability": over_25 if over_25 is not None else float("nan"),
    }


def _pillar(key: str, label: str, raw: float, score_value: float | None) -> dict[str, Any]:
    class_key, class_label = scales.five_class(score_value)
    return {
        "key": key,
        "title": label,
        "raw_value": round(raw, 6),
        "score": round(score_value, 3) if score_value is not None else None,
        "class_key": class_key,
        "label": class_label,
        "status": "ok" if class_key else "unavailable",
        "formula_version": MODULE_VERSION,
    }


def build_goal_intensity_v25(contexts: Any, league: LeagueReference, goals: GoalOutput) -> dict[str, Any]:
    feats = raw_features(contexts, league, goals)
    if feats is None or feats["over_2_5_probability"] != feats["over_2_5_probability"]:
        return {
            "module_version": MODULE_VERSION,
            "status": "insufficient_sample",
            "execution_status": "insufficient_sample",
            "pillars": {},
            "final_class": None,
            "composite_gi_a_strict_core": None,
            "raw_features": feats,
        }
    attack_score = scales.score(SCALE_ATTACK, feats["attack_ratio"])
    defence_score = scales.score(SCALE_DEFENCE, feats["defence_ratio"])
    tempo_score = scales.score(SCALE_TEMPO, feats["tempo_ratio"])
    consistency_score = scales.score(SCALE_CONSISTENCY, feats["scoring_consistency"])
    final_score = scales.score(SCALE_FINAL, feats["over_2_5_probability"])
    pillars = {
        "offensive_production": _pillar("offensive_production", PILLARS[0][1], feats["attack_ratio"], attack_score),
        # solidita' alta = difese che subiscono poco
        "defensive_solidity": _pillar(
            "defensive_solidity",
            PILLARS[1][1],
            feats["defence_ratio"],
            100.0 - defence_score if defence_score is not None else None,
        ),
        "match_tempo": _pillar("match_tempo", PILLARS[2][1], feats["tempo_ratio"], tempo_score),
        "offensive_stability": _pillar("offensive_stability", PILLARS[3][1], feats["scoring_consistency"], consistency_score),
    }
    final_key, final_label = scales.five_class(final_score)
    return {
        "module_version": MODULE_VERSION,
        "scales_version": scales.scales_version(),
        "status": "ok" if final_key else "scales_missing",
        "execution_status": "computed" if final_key else "scales_missing",
        "pillars": pillars,
        "final_class": (
            {"key": final_key, "label": final_label, "score": round(final_score, 3), "source": "over_2_5_probability_v25"}
            if final_key
            else None
        ),
        "composite_gi_a_strict_core": round(final_score, 3) if final_score is not None else None,
        "raw_features": {k: round(v, 6) for k, v in feats.items()},
    }
