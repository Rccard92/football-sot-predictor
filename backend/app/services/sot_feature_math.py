from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.constants import MIN_PRIOR_MATCHES_FOR_TEAM_AVG


@dataclass(frozen=True)
class PriorMatch:
    """Partita precedente di una squadra (stessa stagione), ordinata temporalmente."""

    kickoff: datetime
    fixture_id: int
    is_home: bool
    sot_for: int | None
    sot_against: int | None


def fixture_key_before(
    kickoff_a: datetime,
    id_a: int,
    kickoff_b: datetime,
    id_b: int,
) -> bool:
    """True se la partita A è strettamente precedente a B (anti-leakage)."""
    if kickoff_a < kickoff_b:
        return True
    if kickoff_a > kickoff_b:
        return False
    return id_a < id_b


def mean_numeric(values: list[int | float | None]) -> float | None:
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def avg_with_fallback(
    values: list[int | None],
    n_prior_matches: int,
    league_fallback: float,
    min_samples: int = MIN_PRIOR_MATCHES_FOR_TEAM_AVG,
) -> float:
    if n_prior_matches < min_samples:
        return league_fallback
    m = mean_numeric(values)
    return league_fallback if m is None else float(m)


def avg_with_fallback_flag(
    values: list[int | None],
    n_prior_matches: int,
    league_fallback: float,
    min_samples: int = MIN_PRIOR_MATCHES_FOR_TEAM_AVG,
) -> tuple[float, bool]:
    if n_prior_matches < min_samples:
        return league_fallback, True
    m = mean_numeric(values)
    if m is None:
        return league_fallback, True
    return float(m), False


def last_n_matches(priors: list[PriorMatch], n: int) -> list[PriorMatch]:
    if n <= 0 or not priors:
        return []
    return priors[-n:]


def rolling_avg_pair(
    priors: list[PriorMatch],
    n: int,
    n_team_prior_matches: int,
    league_fallback: float,
) -> tuple[float, float]:
    window = last_n_matches(priors, n)
    if n_team_prior_matches < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        return league_fallback, league_fallback
    for_vals = [m.sot_for for m in window]
    against_vals = [m.sot_against for m in window]
    for_avg = mean_numeric(for_vals)
    against_avg = mean_numeric(against_vals)
    return (
        league_fallback if for_avg is None else float(for_avg),
        league_fallback if against_avg is None else float(against_avg),
    )


def league_avg_sot_from_prior_fixtures(
    prior_fixture_rows: list[tuple[int | None, int | None]],
) -> float:
    """
    prior_fixture_rows: per ogni partita precedente, (sot_home, sot_away).
    Fallback di lega = media di tutti i SOT segnati (due valori per partita).
    """
    flat: list[float] = []
    for h, a in prior_fixture_rows:
        if h is not None:
            flat.append(float(h))
        if a is not None:
            flat.append(float(a))
    if not flat:
        return 0.0
    return sum(flat) / len(flat)


def rest_days_between(current_kickoff: datetime, team_priors: list[PriorMatch]) -> int | None:
    if not team_priors:
        return None
    last = team_priors[-1].kickoff
    delta = current_kickoff.date() - last.date()
    return max(0, delta.days)


def compute_row_features(
    *,
    current_kickoff: datetime,
    team_priors: list[PriorMatch],
    is_home_current: bool,
    opponent_priors: list[PriorMatch],
    opponent_is_home_current: bool,
    league_fallback: float,
    actual_sot: int | None,
) -> dict[str, Any]:
    """
    Calcola il dizionario features per una squadra in una singola fixture.
    Include `meta` per confidenza del modello di previsione (fallback su media lega).
    """
    n_team = len(team_priors)
    n_opp = len(opponent_priors)

    for_vals = [m.sot_for for m in team_priors]
    against_vals = [m.sot_against for m in team_priors]

    season_avg_sot_for, fb_season_for = avg_with_fallback_flag(
        for_vals, n_team, league_fallback,
    )
    season_avg_sot_against, _fb_season_against = avg_with_fallback_flag(
        against_vals, n_team, league_fallback,
    )

    ha = [m for m in team_priors if m.is_home == is_home_current]
    ha_for = [m.sot_for for m in ha]
    ha_against = [m.sot_against for m in ha]
    home_away_avg_sot_for, fb_ha_for = avg_with_fallback_flag(
        ha_for, len(ha), league_fallback,
    )
    home_away_avg_sot_against, _fb_ha_against = avg_with_fallback_flag(
        ha_against, len(ha), league_fallback,
    )

    if n_team < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        last5_for = league_fallback
        last5_against = league_fallback
        fb_last5_for = True
    else:
        w5 = last_n_matches(team_priors, 5)
        m5f = mean_numeric([m.sot_for for m in w5])
        m5a = mean_numeric([m.sot_against for m in w5])
        fb_last5_for = m5f is None
        last5_for = league_fallback if m5f is None else float(m5f)
        last5_against = league_fallback if m5a is None else float(m5a)

    last10_for, last10_against = rolling_avg_pair(team_priors, 10, n_team, league_fallback)

    opp_conceded_vals = [m.sot_against for m in opponent_priors]
    opponent_season_avg_sot_conceded, fb_opp_season = avg_with_fallback_flag(
        opp_conceded_vals, n_opp, league_fallback,
    )

    opp_ha = [m for m in opponent_priors if m.is_home == opponent_is_home_current]
    opp_ha_conceded = [m.sot_against for m in opp_ha]
    opponent_home_away_avg_sot_conceded, fb_opp_ha = avg_with_fallback_flag(
        opp_ha_conceded,
        len(opp_ha),
        league_fallback,
    )

    if n_opp < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        opponent_last5_avg_sot_conceded = league_fallback
        fb_opp_l5 = True
    else:
        w = last_n_matches(opponent_priors, 5)
        m = mean_numeric([x.sot_against for x in w])
        fb_opp_l5 = m is None
        opponent_last5_avg_sot_conceded = league_fallback if m is None else float(m)

    formula_fallbacks = {
        "season_avg_sot_for": fb_season_for,
        "opponent_season_avg_sot_conceded": fb_opp_season,
        "home_away_avg_sot_for": fb_ha_for,
        "opponent_home_away_avg_sot_conceded": fb_opp_ha,
        "last5_avg_sot_for": fb_last5_for,
        "opponent_last5_avg_sot_conceded": fb_opp_l5,
    }
    fb_count = sum(1 for v in formula_fallbacks.values() if v)

    rest_days = rest_days_between(current_kickoff, team_priors)

    return {
        "season_avg_sot_for": round(float(season_avg_sot_for), 4),
        "season_avg_sot_against": round(float(season_avg_sot_against), 4),
        "home_away_avg_sot_for": round(float(home_away_avg_sot_for), 4),
        "home_away_avg_sot_against": round(float(home_away_avg_sot_against), 4),
        "last5_avg_sot_for": round(float(last5_for), 4),
        "last5_avg_sot_against": round(float(last5_against), 4),
        "last10_avg_sot_for": round(float(last10_for), 4),
        "last10_avg_sot_against": round(float(last10_against), 4),
        "opponent_season_avg_sot_conceded": round(float(opponent_season_avg_sot_conceded), 4),
        "opponent_home_away_avg_sot_conceded": round(float(opponent_home_away_avg_sot_conceded), 4),
        "opponent_last5_avg_sot_conceded": round(float(opponent_last5_avg_sot_conceded), 4),
        "rest_days": rest_days,
        "actual_sot": actual_sot,
        "meta": {
            "n_team_priors": n_team,
            "n_opp_priors": n_opp,
            "formula_fallbacks": formula_fallbacks,
            "formula_fallback_count": fb_count,
        },
    }
