"""Estensione goal markets RUN V2: FT O/U 0.5 e famiglia HT 1X2.

I mercati V1 restano calcolati da `compute_goal_markets_from_contexts`, che non
viene toccata, e il pannello KPI continua a ricevere esattamente quel dict.

Qui si aggiungono due blocchi che quella funzione non produce:

- la coppia FT O/U 0.5, con la stessa pipeline matematica degli altri O/U;
- la famiglia HT 1X2 completa. `compute_goal_markets_from_contexts` calcola il
  solo X PT, quindi nella V1-lab 1 PT e 2 PT restano senza quota Cecchino. La
  famiglia normalizzata `calculate_first_half_1x2_family_v2` e la stessa che il
  Cecchino Today usa in produzione: viene invocata cosi com'e, e i suoi valori
  alimentano le tre righe HT della RUN V2 senza entrare nel pannello KPI.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.cecchino.cecchino_goal_poisson_v2 import (
    calculate_first_half_1x2_family_v2,
    calculate_ou_05_pair_v2_optional,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_OVER_0_5,
    SEL_UNDER_0_5,
)


def league_probs_ou_05(priors: list[SimpleNamespace]) -> dict[str, float | None]:
    """Hit rate di competizione per O/U 0.5, dai soli match precedenti.

    Replica la semantica di `_league_event_probabilities_from_proxies` senza
    modificarla: quella funzione itera `_FT_MARKETS`, che per freeze non puo
    accogliere le nuove chiavi.
    """
    over_hits = 0
    total = 0
    for f in priors:
        gh = getattr(f, "goals_home", None)
        ga = getattr(f, "goals_away", None)
        if gh is None or ga is None:
            continue
        total += 1
        if int(gh) + int(ga) >= 1:
            over_hits += 1

    if total == 0:
        return {SEL_OVER_0_5: None, SEL_UNDER_0_5: None}

    over_p = round(over_hits / total, 4)
    return {
        SEL_OVER_0_5: over_p,
        SEL_UNDER_0_5: round(1.0 - over_p, 4),
    }


def compute_ou_05_markets(
    contexts: Any,
    priors: list[SimpleNamespace],
) -> dict[str, Any]:
    """Blocchi mercato FT O/U 0.5 per la RUN V2."""
    goal_contexts = getattr(contexts, "goal_contexts", None)
    if goal_contexts is None:
        return {}

    return calculate_ou_05_pair_v2_optional(
        goal_contexts,
        league_probs_ou_05(priors),
        legacy_slices=getattr(contexts, "goal_slices", None),
    )


def league_probs_ht_1x2(priors: list[SimpleNamespace]) -> dict[str, float | None]:
    """Hit rate di competizione per gli esiti HT, dai soli match precedenti."""
    home = draw = away = 0
    total = 0
    for f in priors:
        raw = getattr(f, "raw_json", None) or {}
        ht = ((raw.get("score") or {}).get("halftime")) or {}
        gh, ga = ht.get("home"), ht.get("away")
        if gh is None or ga is None:
            continue
        total += 1
        if int(gh) > int(ga):
            home += 1
        elif int(gh) == int(ga):
            draw += 1
        else:
            away += 1

    if total == 0:
        return {SEL_HOME_PT: None, SEL_DRAW_PT: None, SEL_AWAY_PT: None}

    return {
        SEL_HOME_PT: round(home / total, 4),
        SEL_DRAW_PT: round(draw / total, 4),
        SEL_AWAY_PT: round(away / total, 4),
    }


def compute_ht_1x2_markets(
    contexts: Any,
    priors: list[SimpleNamespace],
) -> dict[str, Any]:
    """Famiglia HT 1X2 normalizzata (somma delle tre probabilita = 1)."""
    goal_contexts = getattr(contexts, "goal_contexts", None)
    if goal_contexts is None:
        return {}

    league_probs = dict(getattr(contexts, "league_probs", None) or {})
    # Il builder lab non produce le league prob di 1 PT e 2 PT: si completano
    # qui, senza modificare quelle gia presenti.
    for key, value in league_probs_ht_1x2(priors).items():
        league_probs.setdefault(key, value)
        if league_probs.get(key) is None:
            league_probs[key] = value

    return calculate_first_half_1x2_family_v2(goal_contexts, league_probs)
