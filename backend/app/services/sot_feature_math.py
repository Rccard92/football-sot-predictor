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


def pick_fallback_value(
    league_fallback: float | None,
    baseline: float | None,
) -> tuple[float | None, bool]:
    """Valore prudenziale quando mancano campioni; True = percorso fallback."""
    if league_fallback is not None:
        return float(league_fallback), True
    if baseline is not None:
        return float(baseline), True
    return None, True


def coerce_or_fallback(
    raw: float | None,
    league_fallback: float | None,
    baseline: float | None,
) -> tuple[float | None, bool]:
    if raw is not None:
        return float(raw), False
    return pick_fallback_value(league_fallback, baseline)


def avg_with_fallback_flag(
    values: list[int | None],
    n_prior_matches: int,
    league_fallback: float | None,
    baseline: float | None,
    min_samples: int = MIN_PRIOR_MATCHES_FOR_TEAM_AVG,
) -> tuple[float | None, bool]:
    if n_prior_matches < min_samples:
        return pick_fallback_value(league_fallback, baseline)
    m = mean_numeric(values)
    return coerce_or_fallback(m, league_fallback, baseline)


def last_n_matches(priors: list[PriorMatch], n: int) -> list[PriorMatch]:
    if n <= 0 or not priors:
        return []
    return priors[-n:]


def rolling_avg_pair(
    priors: list[PriorMatch],
    n: int,
    n_team_prior_matches: int,
    league_fallback: float | None,
    baseline: float | None,
) -> tuple[float | None, float | None, bool]:
    window = last_n_matches(priors, n)
    if n_team_prior_matches < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        v, fb = pick_fallback_value(league_fallback, baseline)
        return v, v, fb
    for_avg = mean_numeric([m.sot_for for m in window])
    against_avg = mean_numeric([m.sot_against for m in window])
    out_f, fb_f = coerce_or_fallback(for_avg, league_fallback, baseline)
    out_a, fb_a = coerce_or_fallback(against_avg, league_fallback, baseline)
    return out_f, out_a, fb_f or fb_a


def league_avg_sot_from_prior_fixtures(
    prior_fixture_rows: list[tuple[int | None, int | None]],
) -> float | None:
    """
    Media SOT su tutte le partite già concluse prima della corrente (solo `processed`).
    Nessun dato => None (niente media lega).
    """
    flat: list[float] = []
    for h, a in prior_fixture_rows:
        if h is not None:
            flat.append(float(h))
        if a is not None:
            flat.append(float(a))
    if not flat:
        return None
    return sum(flat) / len(flat)


def rest_days_between(current_kickoff: datetime, team_priors: list[PriorMatch]) -> int | None:
    if not team_priors:
        return None
    last = team_priors[-1].kickoff
    delta = current_kickoff.date() - last.date()
    return max(0, delta.days)


def _r4(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 4)


def compute_row_features(
    *,
    current_kickoff: datetime,
    team_priors: list[PriorMatch],
    is_home_current: bool,
    opponent_priors: list[PriorMatch],
    opponent_is_home_current: bool,
    league_fallback: float | None,
    baseline: float | None,
    actual_sot: int | None,
) -> dict[str, Any]:
    """
    Calcola le feature per una squadra in una fixture. Nessun uso della partita corrente
    nelle medie (solo `team_priors` / `opponent_priors` già costruiti senza leakage).
    """
    n_team = len(team_priors)
    n_opp = len(opponent_priors)

    for_vals = [m.sot_for for m in team_priors]
    against_vals = [m.sot_against for m in team_priors]

    season_avg_sot_for, fb_season_for = avg_with_fallback_flag(
        for_vals, n_team, league_fallback, baseline,
    )
    season_avg_sot_against, fb_season_against = avg_with_fallback_flag(
        against_vals, n_team, league_fallback, baseline,
    )

    ha = [m for m in team_priors if m.is_home == is_home_current]
    ha_for = [m.sot_for for m in ha]
    ha_against = [m.sot_against for m in ha]
    home_away_avg_sot_for, fb_ha_for = avg_with_fallback_flag(
        ha_for, len(ha), league_fallback, baseline,
    )
    home_away_avg_sot_against, fb_ha_against = avg_with_fallback_flag(
        ha_against, len(ha), league_fallback, baseline,
    )

    if n_team < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        last5_for, fb_last5_for = pick_fallback_value(league_fallback, baseline)
        last5_against, fb_last5_against = pick_fallback_value(league_fallback, baseline)
    else:
        w5 = last_n_matches(team_priors, 5)
        m5f = mean_numeric([m.sot_for for m in w5])
        m5a = mean_numeric([m.sot_against for m in w5])
        last5_for, fb_last5_for = coerce_or_fallback(m5f, league_fallback, baseline)
        last5_against, fb_last5_against = coerce_or_fallback(m5a, league_fallback, baseline)

    last10_for, last10_against, fb_last10 = rolling_avg_pair(
        team_priors, 10, n_team, league_fallback, baseline,
    )

    opp_conceded_vals = [m.sot_against for m in opponent_priors]
    opponent_season_avg_sot_conceded, fb_opp_season = avg_with_fallback_flag(
        opp_conceded_vals, n_opp, league_fallback, baseline,
    )

    opp_ha = [m for m in opponent_priors if m.is_home == opponent_is_home_current]
    opp_ha_conceded = [m.sot_against for m in opp_ha]
    opponent_home_away_avg_sot_conceded, fb_opp_ha = avg_with_fallback_flag(
        opp_ha_conceded,
        len(opp_ha),
        league_fallback,
        baseline,
    )

    if n_opp < MIN_PRIOR_MATCHES_FOR_TEAM_AVG:
        opponent_last5_avg_sot_conceded, fb_opp_l5 = pick_fallback_value(league_fallback, baseline)
    else:
        w = last_n_matches(opponent_priors, 5)
        m = mean_numeric([x.sot_against for x in w])
        opponent_last5_avg_sot_conceded, fb_opp_l5 = coerce_or_fallback(
            m, league_fallback, baseline,
        )

    formula_fallbacks = {
        "season_avg_sot_for": fb_season_for,
        "season_avg_sot_against": fb_season_against,
        "home_away_avg_sot_for": fb_ha_for,
        "home_away_avg_sot_against": fb_ha_against,
        "last5_avg_sot_for": fb_last5_for,
        "last5_avg_sot_against": fb_last5_against,
        "last10_avg_sot_for": fb_last10,
        "last10_avg_sot_against": fb_last10,
        "opponent_season_avg_sot_conceded": fb_opp_season,
        "opponent_home_away_avg_sot_conceded": fb_opp_ha,
        "opponent_last5_avg_sot_conceded": fb_opp_l5,
    }
    fb_count = sum(1 for v in formula_fallbacks.values() if v)

    rest_days = rest_days_between(current_kickoff, team_priors)

    return {
        "season_avg_sot_for": _r4(season_avg_sot_for),
        "season_avg_sot_against": _r4(season_avg_sot_against),
        "home_away_avg_sot_for": _r4(home_away_avg_sot_for),
        "home_away_avg_sot_against": _r4(home_away_avg_sot_against),
        "last5_avg_sot_for": _r4(last5_for),
        "last5_avg_sot_against": _r4(last5_against),
        "last10_avg_sot_for": _r4(last10_for),
        "last10_avg_sot_against": _r4(last10_against),
        "opponent_season_avg_sot_conceded": _r4(opponent_season_avg_sot_conceded),
        "opponent_home_away_avg_sot_conceded": _r4(opponent_home_away_avg_sot_conceded),
        "opponent_last5_avg_sot_conceded": _r4(opponent_last5_avg_sot_conceded),
        "rest_days": rest_days,
        "actual_sot": actual_sot,
        "fallback_used": fb_count > 0,
        "previous_matches_count": n_team,
        "opponent_previous_matches_count": n_opp,
        "meta": {
            "n_team_priors": n_team,
            "n_opp_priors": n_opp,
            "formula_fallbacks": formula_fallbacks,
            "formula_fallback_count": fb_count,
        },
    }
