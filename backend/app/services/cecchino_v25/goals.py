"""Mercati gol V2.5: stesso modello della V2 (Poisson 65% + frequenze 35%, stesse
finestre e pesi), con le correzioni:

- gol fatti/subiti e frequenze delle squadre partono da poche partite "virtuali" con
  la media del campionato (in V2 con 1-2 partite il valore della squadra era preso
  cosi' com'era);
- nelle finestre casa/trasferta il riferimento e' la media gol in casa o in trasferta
  del campionato, non la media generica;
- l'affidabilita' del contesto e' n / (n + K): cresce con le partite ma non arriva mai
  a 1. In V2 era min(campione) / obiettivo, che valeva 1 gia' con 5-10 partite e
  cancellava la correzione verso il campionato;
- la frequenza di campionato di tutti i mercati e' corretta (in V2 Under 0.5 primo
  tempo valeva sempre 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, floor
from typing import Any

from app.services.cecchino.cecchino_constants import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
)
from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    GoalContextSlice,
    team_goals_in_fixture,
    team_halftime_goals_in_fixture,
)
from app.services.cecchino.cecchino_goal_poisson_v2 import _CONTEXT_WEIGHT_MAP
from app.services.cecchino_v25.constants import (
    BLEND_EMPIRICAL,
    BLEND_POISSON,
    GOAL_HIT_PRIOR_MATCHES,
    GOAL_RATE_PRIOR_MATCHES,
    GOAL_RELIABILITY_PRIOR,
    MAX_PROB,
    MIN_PROB,
)
from app.services.cecchino_v25.league import LeagueReference

FORMULA_VERSION = "cecchino_v25_goals_v1"

_VENUE_WINDOWS = frozenset({CONTEXT_KEY_HOME_AWAY, CONTEXT_KEY_LAST5_HOME_AWAY})

FT_PAIRS: tuple[tuple[float, str, str], ...] = (
    (0.5, "UNDER_0_5", "OVER_0_5"),
    (1.5, "UNDER_1_5", "OVER_1_5"),
    (2.5, "UNDER_2_5", "OVER_2_5"),
    (3.5, "UNDER_3_5", "OVER_3_5"),
)
HT_PAIRS: tuple[tuple[float, str, str], ...] = (
    (0.5, "UNDER_PT_0_5", "OVER_PT_0_5"),
    (1.5, "UNDER_PT_1_5", "OVER_PT_1_5"),
)
HT_1X2_KEYS = ("HOME_PT", "DRAW_PT", "AWAY_PT")


@dataclass(frozen=True)
class GoalParams:
    rate_prior: float = GOAL_RATE_PRIOR_MATCHES
    hit_prior: float = GOAL_HIT_PRIOR_MATCHES
    reliability_prior: float = GOAL_RELIABILITY_PRIOR


def _poisson_cdf(k: int, lam: float) -> float:
    term = exp(-lam)
    total = term
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(1.0, total)


def _clip(p: float) -> float:
    return max(MIN_PROB, min(MAX_PROB, p))


def _usable(ctx: GoalContextSlice) -> bool:
    return ctx.sample_home >= ctx.min_sample and ctx.sample_away >= ctx.min_sample


def _weights(slices: list[GoalContextSlice]) -> dict[str, float]:
    usable = {c.name: _CONTEXT_WEIGHT_MAP.get(c.name, 0.0) for c in slices if _usable(c)}
    total = sum(usable.values())
    return {k: v / total for k, v in usable.items()} if total > 0 else {}


def _scores(fixtures: list, team_id: int, *, ht: bool) -> list[tuple[int, int]]:
    getter = team_halftime_goals_in_fixture if ht else team_goals_in_fixture
    out: list[tuple[int, int]] = []
    for f in fixtures:
        gf, ga = getter(f, team_id)
        if gf is not None and ga is not None:
            out.append((int(gf), int(ga)))
    return out


@dataclass
class WindowGoals:
    name: str
    weight: float
    home: list[tuple[int, int]]  # (fatti, subiti) della squadra di casa del match
    away: list[tuple[int, int]]  # (fatti, subiti) della squadra ospite del match
    lambda_home: float
    lambda_away: float

    @property
    def sample(self) -> float:
        return (len(self.home) + len(self.away)) / 2.0


def _window(
    ctx: GoalContextSlice,
    weight: float,
    *,
    home_id: int,
    away_id: int,
    league: LeagueReference,
    ht: bool,
    params: GoalParams,
) -> WindowGoals:
    home = _scores(ctx.home_fixtures, home_id, ht=ht)
    away = _scores(ctx.away_fixtures, away_id, ht=ht)
    lg_home = league.ht_home_goals if ht else league.home_goals
    lg_away = league.ht_away_goals if ht else league.away_goals
    if ctx.name in _VENUE_WINDOWS:
        # casa gioca in casa (fa gol "da casa", subisce gol "da trasferta"); ospite il contrario
        mu_h_for, mu_h_against, mu_a_for, mu_a_against = lg_home, lg_away, lg_away, lg_home
    else:
        mu = (lg_home + lg_away) / 2.0
        mu_h_for = mu_h_against = mu_a_for = mu_a_against = mu
    k = params.rate_prior

    def rate(values: list[int], mu: float) -> float:
        return (sum(values) + k * mu) / (len(values) + k)

    att_h = rate([s[0] for s in home], mu_h_for)
    def_h = rate([s[1] for s in home], mu_h_against)
    att_a = rate([s[0] for s in away], mu_a_for)
    def_a = rate([s[1] for s in away], mu_a_against)
    return WindowGoals(
        name=ctx.name,
        weight=weight,
        home=home,
        away=away,
        lambda_home=(att_h + def_a) / 2.0,
        lambda_away=(att_a + def_h) / 2.0,
    )


def _windows(goal_contexts: Any, league: LeagueReference, *, ht: bool, params: GoalParams) -> list[WindowGoals]:
    slices = goal_contexts.ht_slices() if ht else goal_contexts.ft_slices()
    weights = _weights(slices)
    return [
        _window(
            c,
            weights[c.name],
            home_id=goal_contexts.home_team_id,
            away_id=goal_contexts.away_team_id,
            league=league,
            ht=ht,
            params=params,
        )
        for c in slices
        if c.name in weights
    ]


def _weighted(values: list[tuple[float, float]]) -> float:
    return sum(v * w for v, w in values)


def _reliability(windows: list[WindowGoals], params: GoalParams) -> float:
    n = _weighted([(w.sample, w.weight) for w in windows])
    return n / (n + params.reliability_prior)


def _hit_rate(pairs: list[tuple[int, int]], hit, league_p: float, k: float) -> float:
    hits = sum(1 for gf, ga in pairs if hit(gf, ga))
    return (hits + k * league_p) / (len(pairs) + k)


def _side_block(
    key: str,
    p: float | None,
    *,
    complementary: str,
    reliability: float,
    summary_extra: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    if p is None:
        return {
            "market_key": key,
            "formula_version": FORMULA_VERSION,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "summary": None,
            "complementary_market": complementary,
            "warnings": ["insufficient_goal_sample:all_contexts"],
        }
    capped = _clip(p)
    return {
        "market_key": key,
        "formula_version": FORMULA_VERSION,
        "final_odd": round(1.0 / capped, 4),
        "status": status,
        "summary": {
            **summary_extra,
            "final_probability_raw": round(p, 6),
            "final_probability": round(capped, 6),
            "final_odd": round(1.0 / capped, 4),
            "overall_reliability": round(reliability, 6),
        },
        "complementary_market": complementary,
        "warnings": [],
    }


def _ou_pairs(
    windows: list[WindowGoals],
    league: LeagueReference,
    *,
    ht: bool,
    params: GoalParams,
) -> dict[str, dict[str, Any]]:
    pairs = HT_PAIRS if ht else FT_PAIRS
    out: dict[str, dict[str, Any]] = {}
    if not windows:
        for _, under, over in pairs:
            out[under] = _side_block(under, None, complementary=over, reliability=0.0, summary_extra={}, status="")
            out[over] = _side_block(over, None, complementary=under, reliability=0.0, summary_extra={}, status="")
        return out
    lam_home = _weighted([(w.lambda_home, w.weight) for w in windows])
    lam_away = _weighted([(w.lambda_away, w.weight) for w in windows])
    lam = lam_home + lam_away
    rel = _reliability(windows, params)
    status = STATUS_AVAILABLE if all(len(w.home) >= 5 and len(w.away) >= 5 for w in windows) else STATUS_PARTIAL_LOW_SAMPLE
    for line, under, over in pairs:
        league_under = 1.0 - league.over(line, ht=ht)
        poisson_under = _poisson_cdf(int(floor(line)), lam)
        cut = int(floor(line))
        emp_under = _weighted(
            [
                (
                    (
                        _hit_rate(w.home, lambda gf, ga: gf + ga <= cut, league_under, params.hit_prior)
                        + _hit_rate(w.away, lambda gf, ga: gf + ga <= cut, league_under, params.hit_prior)
                    )
                    / 2.0,
                    w.weight,
                )
                for w in windows
            ]
        )
        blended = BLEND_POISSON * poisson_under + BLEND_EMPIRICAL * emp_under
        p_under = rel * blended + (1.0 - rel) * league_under
        common = {
            "lambda_home": round(lam_home, 6),
            "lambda_away": round(lam_away, 6),
            "lambda_total": round(lam, 6),
            "blend_poisson": BLEND_POISSON,
            "blend_empirical": BLEND_EMPIRICAL,
        }
        out[under] = _side_block(
            under,
            p_under,
            complementary=over,
            reliability=rel,
            status=status,
            summary_extra={
                **common,
                "poisson_probability": round(poisson_under, 6),
                "empirical_probability": round(emp_under, 6),
                "league_event_probability": round(league_under, 6),
            },
        )
        out[over] = _side_block(
            over,
            1.0 - p_under,
            complementary=under,
            reliability=rel,
            status=status,
            summary_extra={
                **common,
                "poisson_probability": round(1.0 - poisson_under, 6),
                "empirical_probability": round(1.0 - emp_under, 6),
                "league_event_probability": round(1.0 - league_under, 6),
            },
        )
    return out


def _ht_1x2_family(windows: list[WindowGoals], league: LeagueReference, params: GoalParams) -> dict[str, dict[str, Any]]:
    if not windows:
        return {k: _side_block(k, None, complementary="HT_1X2", reliability=0.0, summary_extra={}, status="") for k in HT_1X2_KEYS}
    league_vec = (league.ht_p_home, league.ht_p_draw, league.ht_p_away)
    k = params.hit_prior
    acc = [0.0, 0.0, 0.0]
    for w in windows:
        # dal punto di vista della partita: casa avanti / pari / ospite avanti
        home_counts = [sum(1 for gf, ga in w.home if gf > ga), sum(1 for gf, ga in w.home if gf == ga), sum(1 for gf, ga in w.home if gf < ga)]
        away_counts = [sum(1 for gf, ga in w.away if gf < ga), sum(1 for gf, ga in w.away if gf == ga), sum(1 for gf, ga in w.away if gf > ga)]
        for i in range(3):
            rate_h = (home_counts[i] + k * league_vec[i]) / (len(w.home) + k)
            rate_a = (away_counts[i] + k * league_vec[i]) / (len(w.away) + k)
            acc[i] += w.weight * (rate_h + rate_a) / 2.0
    rel = _reliability(windows, params)
    final = [rel * acc[i] + (1.0 - rel) * league_vec[i] for i in range(3)]
    total = sum(final)
    final = [v / total for v in final]
    status = STATUS_AVAILABLE if all(len(w.home) >= 5 and len(w.away) >= 5 for w in windows) else STATUS_PARTIAL_LOW_SAMPLE
    return {
        key: _side_block(
            key,
            final[i],
            complementary="HT_1X2",
            reliability=rel,
            status=status,
            summary_extra={
                "empirical_probability": round(acc[i], 6),
                "league_event_probability": round(league_vec[i], 6),
                "family_sum": 1.0,
            },
        )
        for i, key in enumerate(HT_1X2_KEYS)
    }


@dataclass
class GoalOutput:
    goal_markets: dict[str, dict[str, Any]]  # O/U 1.5-3.5 FT, O/U PT, X PT
    ou_05_markets: dict[str, dict[str, Any]]
    ht_1x2_markets: dict[str, dict[str, Any]]
    lambda_home: float | None
    lambda_away: float | None
    ht_lambda_home: float | None
    ht_lambda_away: float | None
    reliability: float

    def probability(self, key: str) -> float | None:
        for group in (self.goal_markets, self.ou_05_markets, self.ht_1x2_markets):
            block = group.get(key)
            if block and block.get("summary"):
                return float(block["summary"]["final_probability"])
        return None


def compute_goal_markets_v25(contexts: Any, league: LeagueReference, *, params: GoalParams | None = None) -> GoalOutput:
    params = params or GoalParams()
    gc = getattr(contexts, "goal_contexts", None)
    if gc is None:
        return GoalOutput({}, {}, {}, None, None, None, None, 0.0)
    ft = _windows(gc, league, ht=False, params=params)
    ht = _windows(gc, league, ht=True, params=params)
    ft_markets = _ou_pairs(ft, league, ht=False, params=params)
    ht_markets = _ou_pairs(ht, league, ht=True, params=params)
    family = _ht_1x2_family(ht, league, params)
    goal_markets = {k: v for k, v in ft_markets.items() if k not in ("UNDER_0_5", "OVER_0_5")}
    goal_markets.update(ht_markets)
    goal_markets["DRAW_PT"] = family["DRAW_PT"]
    return GoalOutput(
        goal_markets=goal_markets,
        ou_05_markets={k: ft_markets[k] for k in ("OVER_0_5", "UNDER_0_5")},
        ht_1x2_markets=family,
        lambda_home=_weighted([(w.lambda_home, w.weight) for w in ft]) if ft else None,
        lambda_away=_weighted([(w.lambda_away, w.weight) for w in ft]) if ft else None,
        ht_lambda_home=_weighted([(w.lambda_home, w.weight) for w in ht]) if ht else None,
        ht_lambda_away=_weighted([(w.lambda_away, w.weight) for w in ht]) if ht else None,
        reliability=_reliability(ft, params) if ft else 0.0,
    )
