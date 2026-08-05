"""Modello goal Over/Under v2 — Poisson + hit-rate storico + reliability shrinkage."""

from __future__ import annotations

from math import exp, factorial
from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.services.cecchino.cecchino_constants import (
    CECCHINO_GOAL_MARKET_WEIGHTS,
    PICCHETTO_KEY_HOME_AWAY,
    PICCHETTO_KEY_LAST5_HOME_AWAY,
    PICCHETTO_KEY_LAST6_TOTALS,
    PICCHETTO_KEY_TOTALS,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    WARNING_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_fixture_history import (
    CONTEXT_KEY_HOME_AWAY,
    CONTEXT_KEY_LAST5_HOME_AWAY,
    CONTEXT_KEY_LAST6_TOTALS,
    CONTEXT_KEY_TOTALS,
    GoalContextSlice,
    GoalMarketContexts,
    GoalTotals,
    halftime_total_goals,
    load_league_finished_fixtures_before,
    team_goals_in_fixture,
    team_halftime_goals_in_fixture,
)
from app.services.cecchino.cecchino_fixture_history import build_goal_fixture_slices
from app.services.cecchino.cecchino_goal_formulas import (
    calculate_first_half_rate_to_odd,
    calculate_over_fulltime_excel_parity,
    calculate_under_fulltime_excel_parity,
)
from app.services.cecchino.cecchino_selection_keys import (
    SEL_AWAY_PT,
    SEL_DRAW_PT,
    SEL_HOME_PT,
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_3_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_0_5,
    SEL_UNDER_PT_1_5,
)

FORMULA_V2 = "goal_market_poisson_empirical_v2"
FORMULA_DRAW_PT_V1 = "first_half_draw_empirical_shrinkage_v1"
FORMULA_HT_1X2_V1 = "first_half_1x2_empirical_shrinkage_v1"
FORMULA_HT_1X2_V2 = "first_half_1x2_empirical_shrinkage_v2"
BLEND_POISSON = 0.65
BLEND_EMPIRICAL = 0.35
MIN_PROB = 0.03
MAX_PROB = 0.97
COMPLEMENT_TOLERANCE = 1e-9
FAMILY_SUM_TOLERANCE = 1e-9

# Event definitions for debug / Analisi formule
EVENT_DEFINITIONS: dict[str, str] = {
    SEL_UNDER_1_5: "FT total goals <= 1",
    SEL_OVER_1_5: "FT total goals >= 2",
    SEL_UNDER_2_5: "FT total goals <= 2",
    SEL_OVER_2_5: "FT total goals >= 3",
    SEL_UNDER_3_5: "FT total goals <= 3",
    SEL_OVER_3_5: "FT total goals >= 4",
    SEL_UNDER_PT_0_5: "HT total goals = 0",
    SEL_OVER_PT_0_5: "HT total goals >= 1",
    SEL_UNDER_PT_1_5: "HT total goals <= 1",
    SEL_OVER_PT_1_5: "HT total goals >= 2",
    SEL_HOME_PT: "home goals HT > away goals HT",
    SEL_DRAW_PT: "home goals HT = away goals HT",
    SEL_AWAY_PT: "away goals HT > home goals HT",
}

# Complementary OU pairs: (under_key, over_key, is_ht)
_OU_COMPLEMENT_PAIRS: tuple[tuple[str, str, bool], ...] = (
    (SEL_UNDER_1_5, SEL_OVER_1_5, False),
    (SEL_UNDER_2_5, SEL_OVER_2_5, False),
    (SEL_UNDER_3_5, SEL_OVER_3_5, False),
    (SEL_UNDER_PT_0_5, SEL_OVER_PT_0_5, True),
    (SEL_UNDER_PT_1_5, SEL_OVER_PT_1_5, True),
)

_CONTEXT_WEIGHT_MAP: dict[str, float] = {
    CONTEXT_KEY_TOTALS: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_TOTALS],
    CONTEXT_KEY_HOME_AWAY: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_HOME_AWAY],
    CONTEXT_KEY_LAST6_TOTALS: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST6_TOTALS],
    CONTEXT_KEY_LAST5_HOME_AWAY: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST5_HOME_AWAY],
}

_FT_MARKETS = (
    SEL_OVER_1_5,
    SEL_UNDER_1_5,
    SEL_OVER_2_5,
    SEL_UNDER_2_5,
    SEL_OVER_3_5,
    SEL_UNDER_3_5,
)
_PT_MARKETS = (
    SEL_OVER_PT_0_5,
    SEL_UNDER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_PT_1_5,
)
_HT_1X2_MARKETS = (SEL_HOME_PT, SEL_DRAW_PT, SEL_AWAY_PT)


def poisson_pmf(k: int, lambda_value: float) -> float:
    if lambda_value <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lambda_value) * (lambda_value**k) / factorial(k)


def poisson_cumulative(lam: float, max_k: int) -> float:
    return sum(poisson_pmf(k, lam) for k in range(max_k + 1))


def poisson_market_probability_ft(market_key: str, lambda_ft: float) -> float:
    if market_key == SEL_OVER_1_5:
        return 1.0 - poisson_cumulative(lambda_ft, 1)
    if market_key == SEL_UNDER_1_5:
        return poisson_cumulative(lambda_ft, 1)
    if market_key == SEL_OVER_2_5:
        return 1.0 - poisson_cumulative(lambda_ft, 2)
    if market_key == SEL_UNDER_2_5:
        return poisson_cumulative(lambda_ft, 2)
    if market_key == SEL_OVER_3_5:
        return 1.0 - poisson_cumulative(lambda_ft, 3)
    if market_key == SEL_UNDER_3_5:
        return poisson_cumulative(lambda_ft, 3)
    return 0.0


def poisson_market_probability_ht(market_key: str, lambda_ht: float) -> float:
    if market_key == SEL_OVER_PT_0_5:
        return 1.0 - poisson_pmf(0, lambda_ht)
    if market_key == SEL_UNDER_PT_0_5:
        return poisson_pmf(0, lambda_ht)
    if market_key == SEL_OVER_PT_1_5:
        return 1.0 - poisson_cumulative(lambda_ht, 1)
    if market_key == SEL_UNDER_PT_1_5:
        return poisson_cumulative(lambda_ht, 1)
    return 0.0


def lambda_for_context(home: GoalTotals, away: GoalTotals) -> dict[str, float]:
    sh, sa = home.sample, away.sample
    if sh <= 0 or sa <= 0:
        return {"lambda_home": 0.0, "lambda_away": 0.0, "lambda_total": 0.0}
    home_attack = home.goals_for / sh
    away_defense = away.goals_against / sa
    lambda_home = (home_attack + away_defense) / 2
    away_attack = away.goals_for / sa
    home_defense = home.goals_against / sh
    lambda_away = (away_attack + home_defense) / 2
    return {
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "lambda_total": lambda_home + lambda_away,
    }


def context_reliability(sample_home: int, sample_away: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return min(1.0, min(sample_home, sample_away) / target)


def _context_usable(ctx: GoalContextSlice) -> bool:
    return ctx.sample_home >= ctx.min_sample and ctx.sample_away >= ctx.min_sample


def _reliability_badge(rel: float) -> str:
    if rel >= 0.85:
        return "Alta"
    if rel >= 0.65:
        return "Media"
    return "Bassa"


def _weighted_blend(values: list[tuple[float, float]]) -> float | None:
    usable = [(v, w) for v, w in values if w > 0]
    if not usable:
        return None
    total_w = sum(w for _, w in usable)
    if total_w <= 0:
        return None
    return sum(v * w for v, w in usable) / total_w


def _context_weight_details(
    contexts: list[GoalContextSlice],
) -> tuple[bool, dict[str, dict[str, float | bool]]]:
    """Calcola original/effective weight per contesto goal market."""
    details: dict[str, dict[str, float | bool]] = {}
    usable_sum = 0.0
    for ctx in contexts:
        original = _CONTEXT_WEIGHT_MAP.get(ctx.name, 0.0)
        if _context_usable(ctx):
            usable_sum += original
        details[ctx.name] = {"original_weight": original, "effective_weight": 0.0}

    renormalized = usable_sum < 0.9999
    for ctx in contexts:
        d = details[ctx.name]
        original = float(d["original_weight"])
        if _context_usable(ctx) and usable_sum > 0:
            d["effective_weight"] = original / usable_sum
        d["weight_renormalized"] = renormalized
    return renormalized, details


def _weight_fields(
    ctx: GoalContextSlice,
    weight_details: dict[str, dict[str, float | bool]],
) -> dict[str, Any]:
    d = weight_details.get(ctx.name, {})
    original = float(d.get("original_weight", 0.0))
    effective = float(d.get("effective_weight", 0.0))
    return {
        "weight": original,
        "original_weight": original,
        "effective_weight": effective,
        "weight_renormalized": bool(d.get("weight_renormalized", False)),
    }


def weighted_lambda(
    contexts: list[GoalContextSlice],
) -> tuple[float | None, list[dict[str, Any]], float, list[str]]:
    warnings: list[str] = []
    ctx_rows: list[dict[str, Any]] = []
    weighted_vals: list[tuple[float, float]] = []
    rel_vals: list[tuple[float, float]] = []
    _, weight_details = _context_weight_details(contexts)

    for ctx in contexts:
        wf = _weight_fields(ctx, weight_details)
        lam_d = lambda_for_context(ctx.home_totals, ctx.away_totals)
        rel = context_reliability(ctx.sample_home, ctx.sample_away, ctx.target_sample)
        usable = _context_usable(ctx)
        status = STATUS_AVAILABLE if usable else "low_sample"
        if not usable:
            warnings.append(f"low_sample:{ctx.name}")
        else:
            eff = float(wf["effective_weight"])
            weighted_vals.append((lam_d["lambda_total"], eff))
            rel_vals.append((rel, eff))
        ctx_rows.append(
            {
                "name": ctx.name,
                "label": ctx.label,
                **wf,
                "sample_home": ctx.sample_home,
                "sample_away": ctx.sample_away,
                "lambda_home": round(lam_d["lambda_home"], 4),
                "lambda_away": round(lam_d["lambda_away"], 4),
                "lambda_total": round(lam_d["lambda_total"], 4),
                "reliability": round(rel, 4),
                "status": status,
            },
        )

    lam = _weighted_blend(weighted_vals)
    overall_rel = _weighted_blend(rel_vals) or 0.0
    return lam, ctx_rows, overall_rel, warnings


def _ft_event_hit(goals_for: int, goals_against: int, market_key: str) -> bool:
    total = goals_for + goals_against
    if market_key == SEL_OVER_1_5:
        return total >= 2
    if market_key == SEL_UNDER_1_5:
        return total <= 1
    if market_key == SEL_OVER_2_5:
        return total >= 3
    if market_key == SEL_UNDER_2_5:
        return total <= 2
    if market_key == SEL_OVER_3_5:
        return total >= 4
    if market_key == SEL_UNDER_3_5:
        return total <= 3
    return False


def _pt_event_hit(ht_total: int, market_key: str) -> bool:
    if market_key == SEL_OVER_PT_0_5:
        return ht_total >= 1
    if market_key == SEL_UNDER_PT_0_5:
        return ht_total <= 0
    if market_key == SEL_OVER_PT_1_5:
        return ht_total >= 2
    if market_key == SEL_UNDER_PT_1_5:
        return ht_total <= 1
    return False


def _ht_1x2_hit_from_home_pov(gf: int, ga: int, market_key: str) -> bool:
    """Hit HT 1X2 dal POV della squadra di casa del matchup target."""
    if market_key == SEL_HOME_PT:
        return gf > ga
    if market_key == SEL_DRAW_PT:
        return gf == ga
    if market_key == SEL_AWAY_PT:
        return gf < ga
    return False


def _ht_1x2_hit_from_away_pov(gf: int, ga: int, market_key: str) -> bool:
    """Hit HT 1X2 dal POV della squadra ospite del matchup target."""
    if market_key == SEL_HOME_PT:
        return gf < ga
    if market_key == SEL_DRAW_PT:
        return gf == ga
    if market_key == SEL_AWAY_PT:
        return gf > ga
    return False


def _hit_rates_for_context(
    ctx: GoalContextSlice,
    market_key: str,
    *,
    home_team_id: int,
    away_team_id: int,
    is_ht: bool,
) -> tuple[float | None, float | None]:
    if market_key == SEL_DRAW_PT and is_ht:
        if not ctx.home_fixtures and ctx.home_totals.sample > 0:
            rate_home = ctx.home_totals.halftime_draw_hits / ctx.home_totals.sample
        else:
            rate_home = None
        if not ctx.away_fixtures and ctx.away_totals.sample > 0:
            rate_away = ctx.away_totals.halftime_draw_hits / ctx.away_totals.sample
        else:
            rate_away = None
        if rate_home is not None and rate_away is not None:
            return rate_home, rate_away

    # Totals-only fallback (test / edge) per OU
    if not ctx.home_fixtures and not ctx.away_fixtures and market_key not in _HT_1X2_MARKETS:
        rh = _ou_rates_from_totals(ctx.home_totals, market_key, is_ht=is_ht)
        ra = _ou_rates_from_totals(ctx.away_totals, market_key, is_ht=is_ht)
        return rh, ra

    home_hits = away_hits = 0
    home_sample = away_sample = 0

    for f in ctx.home_fixtures:
        if is_ht:
            gf, ga = team_halftime_goals_in_fixture(f, home_team_id)
        else:
            gf, ga = team_goals_in_fixture(f, home_team_id)
        if gf is None or ga is None:
            continue
        home_sample += 1
        total = gf + ga
        if is_ht:
            if market_key in _HT_1X2_MARKETS:
                if _ht_1x2_hit_from_home_pov(gf, ga, market_key):
                    home_hits += 1
            elif _pt_event_hit(total, market_key):
                home_hits += 1
        elif _ft_event_hit(gf, ga, market_key):
            home_hits += 1

    for f in ctx.away_fixtures:
        if is_ht:
            gf, ga = team_halftime_goals_in_fixture(f, away_team_id)
        else:
            gf, ga = team_goals_in_fixture(f, away_team_id)
        if gf is None or ga is None:
            continue
        away_sample += 1
        total = gf + ga
        if is_ht:
            if market_key in _HT_1X2_MARKETS:
                if _ht_1x2_hit_from_away_pov(gf, ga, market_key):
                    away_hits += 1
            elif _pt_event_hit(total, market_key):
                away_hits += 1
        elif _ft_event_hit(gf, ga, market_key):
            away_hits += 1

    rate_home = home_hits / home_sample if home_sample > 0 else None
    rate_away = away_hits / away_sample if away_sample > 0 else None
    return rate_home, rate_away


def empirical_probability_for_context(
    ctx: GoalContextSlice,
    market_key: str,
    *,
    home_team_id: int,
    away_team_id: int,
    is_ht: bool,
) -> float | None:
    rate_home, rate_away = _hit_rates_for_context(
        ctx,
        market_key,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        is_ht=is_ht,
    )
    if rate_home is None or rate_away is None:
        return None
    return (rate_home + rate_away) / 2


def weighted_empirical_probability(
    contexts: list[GoalContextSlice],
    market_key: str,
    *,
    home_team_id: int,
    away_team_id: int,
    is_ht: bool,
) -> tuple[float | None, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    vals: list[tuple[float, float]] = []
    _, weight_details = _context_weight_details(contexts)

    for ctx in contexts:
        wf = _weight_fields(ctx, weight_details)
        if not _context_usable(ctx):
            rows.append(
                {
                    "name": ctx.name,
                    "label": ctx.label,
                    **wf,
                    "sample_home": ctx.sample_home,
                    "sample_away": ctx.sample_away,
                    "hit_rate_home": None,
                    "hit_rate_away": None,
                    "empirical_probability": None,
                    "status": "low_sample",
                },
            )
            continue
        rate_home, rate_away = _hit_rates_for_context(
            ctx,
            market_key,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            is_ht=is_ht,
        )
        emp = empirical_probability_for_context(
            ctx,
            market_key,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            is_ht=is_ht,
        )
        if emp is not None:
            vals.append((emp, float(wf["effective_weight"])))
        rows.append(
            {
                "name": ctx.name,
                "label": ctx.label,
                **wf,
                "sample_home": ctx.sample_home,
                "sample_away": ctx.sample_away,
                "hit_rate_home": round(rate_home, 4) if rate_home is not None else None,
                "hit_rate_away": round(rate_away, 4) if rate_away is not None else None,
                "empirical_probability": round(emp, 4) if emp is not None else None,
                "status": STATUS_AVAILABLE,
            },
        )

    if not vals:
        warnings.append(f"insufficient_empirical:{market_key}")
        return None, rows, warnings
    return _weighted_blend(vals), rows, warnings


def league_event_probabilities(
    league_fixtures: list[Fixture],
) -> dict[str, float | None]:
    """Rate evento su tutte le fixture lega finite."""
    all_markets = _FT_MARKETS + _PT_MARKETS + _HT_1X2_MARKETS
    if not league_fixtures:
        return {m: None for m in all_markets}

    ft_totals: dict[str, int] = {m: 0 for m in _FT_MARKETS}
    pt_totals: dict[str, int] = {m: 0 for m in _PT_MARKETS}
    ht_1x2_totals: dict[str, int] = {m: 0 for m in _HT_1X2_MARKETS}
    ft_n = pt_n = 0

    for f in league_fixtures:
        if f.goals_home is None or f.goals_away is None:
            continue
        gh, ga = int(f.goals_home), int(f.goals_away)
        ft_n += 1
        for m in _FT_MARKETS:
            if _ft_event_hit(gh, ga, m):
                ft_totals[m] += 1

        raw = f.raw_json if isinstance(f.raw_json, dict) else {}
        score = raw.get("score") if isinstance(raw.get("score"), dict) else {}
        ht = score.get("halftime") if isinstance(score.get("halftime"), dict) else {}
        hh, ha = ht.get("home"), ht.get("away")
        if hh is not None and ha is not None:
            try:
                ht_home, ht_away = int(hh), int(ha)
            except (TypeError, ValueError):
                ht_home = ht_away = None
            if ht_home is not None and ht_away is not None:
                pt_n += 1
                ht_total = ht_home + ht_away
                for m in _PT_MARKETS:
                    if _pt_event_hit(ht_total, m):
                        pt_totals[m] += 1
                if ht_home > ht_away:
                    ht_1x2_totals[SEL_HOME_PT] += 1
                elif ht_home == ht_away:
                    ht_1x2_totals[SEL_DRAW_PT] += 1
                else:
                    ht_1x2_totals[SEL_AWAY_PT] += 1

    out: dict[str, float | None] = {}
    for m in _FT_MARKETS:
        out[m] = round(ft_totals[m] / ft_n, 4) if ft_n > 0 else None
    for m in _PT_MARKETS:
        out[m] = round(pt_totals[m] / pt_n, 4) if pt_n > 0 else None
    for m in _HT_1X2_MARKETS:
        out[m] = round(ht_1x2_totals[m] / pt_n, 4) if pt_n > 0 else None
    return out


def blend_and_shrink(
    poisson_p: float,
    empirical_p: float,
    overall_reliability: float,
    league_p: float | None,
) -> float:
    base = BLEND_POISSON * poisson_p + BLEND_EMPIRICAL * empirical_p
    if league_p is not None:
        return overall_reliability * base + (1.0 - overall_reliability) * league_p
    return base


def probability_to_odd(p_raw: float) -> tuple[float | None, float, float, list[str]]:
    warnings: list[str] = []
    if p_raw <= 0:
        warnings.append(WARNING_ZERO_PROBABILITY)
        return None, p_raw, p_raw, warnings
    capped = max(MIN_PROB, min(MAX_PROB, p_raw))
    if capped != p_raw:
        warnings.append("probability_capped")
    odd = round(1.0 / capped, 2)
    return odd, p_raw, capped, warnings


def _legacy_excel_odd(market_key: str, slices) -> float | None:
    if slices is None:
        return None
    try:
        if market_key in (SEL_OVER_1_5, SEL_OVER_2_5, SEL_OVER_3_5):
            return calculate_over_fulltime_excel_parity(slices).get("final_odd")
        if market_key in (SEL_UNDER_1_5, SEL_UNDER_2_5, SEL_UNDER_3_5):
            return calculate_under_fulltime_excel_parity(slices).get("final_odd")
        if market_key in _PT_MARKETS:
            return calculate_first_half_rate_to_odd(market_key, slices).get("final_odd")
    except Exception:
        return None
    return None


def _ou_rates_from_totals(totals: GoalTotals, market_key: str, *, is_ht: bool) -> float | None:
    """Fallback empirico da contatori GoalTotals quando le liste fixture sono vuote."""
    sample = totals.sample
    if sample <= 0:
        return None
    if not is_ht:
        if market_key == SEL_OVER_1_5:
            return totals.over_1_5_hits / sample
        if market_key == SEL_UNDER_1_5:
            return max(0.0, 1.0 - totals.over_1_5_hits / sample)
        if market_key == SEL_OVER_2_5:
            return totals.over_2_5_hits / sample
        if market_key == SEL_UNDER_2_5:
            return totals.under_2_5_hits / sample
        if market_key == SEL_UNDER_3_5:
            return totals.under_3_5_hits / sample
        if market_key == SEL_OVER_3_5:
            return max(0.0, 1.0 - totals.under_3_5_hits / sample)
        return None
    if market_key == SEL_OVER_PT_0_5:
        return totals.over_pt_0_5_hits / sample
    if market_key == SEL_UNDER_PT_0_5:
        return max(0.0, 1.0 - totals.over_pt_0_5_hits / sample)
    if market_key == SEL_OVER_PT_1_5:
        return totals.over_pt_1_5_hits / sample
    if market_key == SEL_UNDER_PT_1_5:
        return totals.under_pt_1_5_hits / sample
    return None


def _usable_context_count(contexts: list[GoalContextSlice]) -> int:
    return sum(1 for c in contexts if _context_usable(c))


def _insufficient_goal_block(
    market_key: str,
    *,
    warnings: list[str],
    legacy_slices,
    contexts: list[dict[str, Any]] | None = None,
    complementary_market: str | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "market_key": market_key,
        "formula_version": FORMULA_V2,
        "event_definition": EVENT_DEFINITIONS.get(market_key),
        "final_odd": None,
        "status": STATUS_INSUFFICIENT_DATA,
        "summary": None,
        "contexts": contexts or [],
        "legacy_excel_parity": {
            "final_odd": _legacy_excel_odd(market_key, legacy_slices),
            "enabled_for_kpi": False,
        },
        "warnings": list(warnings),
    }
    if complementary_market:
        block["complementary_market"] = complementary_market
        block["complement_sum_check"] = None
    return block


def _build_ou_side_block(
    *,
    market_key: str,
    complementary_market: str,
    lam: float,
    lambda_rows: list[dict[str, Any]],
    poisson_p: float,
    emp_p: float,
    league_p: float | None,
    final_raw: float,
    overall_rel: float,
    merged_ctx: list[dict[str, Any]],
    warnings: list[str],
    legacy_slices,
    is_ht: bool,
    contexts_obj: GoalMarketContexts,
    complement_sum: float,
) -> dict[str, Any]:
    final_odd, prob_raw, prob_capped, prob_warnings = probability_to_odd(final_raw)
    side_warnings = list(warnings) + list(prob_warnings)
    status = STATUS_AVAILABLE
    if overall_rel < 1.0 or any("low_sample" in w for w in side_warnings):
        status = STATUS_PARTIAL_LOW_SAMPLE
    if final_odd is None:
        status = STATUS_INSUFFICIENT_DATA
    if contexts_obj.skipped_missing_halftime_score > 0 and is_ht:
        side_warnings.append(
            f"skipped_missing_halftime_score:{contexts_obj.skipped_missing_halftime_score}",
        )

    lambda_home = None
    lambda_away = None
    if lambda_rows:
        # Media pesata dei lambda home/away dai contesti utilizzabili
        lh_vals: list[tuple[float, float]] = []
        la_vals: list[tuple[float, float]] = []
        for row in lambda_rows:
            ew = float(row.get("effective_weight") or 0.0)
            if ew <= 0:
                continue
            if row.get("lambda_home") is not None:
                lh_vals.append((float(row["lambda_home"]), ew))
            if row.get("lambda_away") is not None:
                la_vals.append((float(row["lambda_away"]), ew))
        lambda_home = _weighted_blend(lh_vals)
        lambda_away = _weighted_blend(la_vals)

    summary = {
        "lambda": round(lam, 6),
        "lambda_home": round(lambda_home, 6) if lambda_home is not None else None,
        "lambda_away": round(lambda_away, 6) if lambda_away is not None else None,
        "lambda_total": round(lam, 6),
        "poisson_probability": round(poisson_p, 6),
        "empirical_probability": round(emp_p, 6),
        "league_event_probability": league_p,
        "blend_poisson": BLEND_POISSON,
        "blend_empirical": BLEND_EMPIRICAL,
        "final_probability_raw": round(prob_raw, 6),
        "final_probability_capped": round(prob_capped, 6),
        "final_probability": round(prob_capped, 6),
        "final_odd": final_odd,
        "overall_reliability": round(overall_rel, 6),
        "reliability_badge": _reliability_badge(overall_rel),
        "complementary_market": complementary_market,
        "complement_sum_raw": round(complement_sum, 6),
        "complement_sum_ok": abs(complement_sum - 1.0) <= COMPLEMENT_TOLERANCE,
    }

    return {
        "market_key": market_key,
        "formula_version": FORMULA_V2,
        "event_definition": EVENT_DEFINITIONS.get(market_key),
        "final_odd": final_odd,
        "status": status,
        "weights": dict(CECCHINO_GOAL_MARKET_WEIGHTS),
        "summary": summary,
        "contexts": merged_ctx,
        "complementary_market": complementary_market,
        "complement_sum_check": {
            "sum_raw": complement_sum,
            "tolerance": COMPLEMENT_TOLERANCE,
            "ok": abs(complement_sum - 1.0) <= COMPLEMENT_TOLERANCE,
        },
        "technical": {
            "lambda_home_contexts": lambda_rows,
            "blend_poisson": BLEND_POISSON,
            "blend_empirical": BLEND_EMPIRICAL,
            "min_probability": MIN_PROB,
            "max_probability": MAX_PROB,
            "shared_pair_pipeline": True,
        },
        "legacy_excel_parity": {
            "final_odd": _legacy_excel_odd(market_key, legacy_slices),
            "enabled_for_kpi": False,
        },
        "warnings": side_warnings,
    }


def calculate_goal_market_pair_v2(
    under_key: str,
    over_key: str,
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
    *,
    legacy_slices,
    is_ht: bool,
) -> dict[str, dict[str, Any]]:
    """Calcola Under/Over dalla stessa λ, stessa empirica e stessa reliability."""
    ctx_list = contexts.ht_slices() if is_ht else contexts.ft_slices()
    warnings: list[str] = []

    if _usable_context_count(ctx_list) == 0:
        w = ["insufficient_goal_sample:all_contexts"]
        return {
            under_key: _insufficient_goal_block(
                under_key, warnings=w, legacy_slices=legacy_slices, complementary_market=over_key,
            ),
            over_key: _insufficient_goal_block(
                over_key, warnings=w, legacy_slices=legacy_slices, complementary_market=under_key,
            ),
        }

    lam, lam_rows, overall_rel, lam_warnings = weighted_lambda(ctx_list)
    warnings.extend(lam_warnings)

    if lam is None or lam <= 0:
        w = warnings + ["lambda_not_computable"]
        return {
            under_key: _insufficient_goal_block(
                under_key,
                warnings=w,
                legacy_slices=legacy_slices,
                contexts=lam_rows,
                complementary_market=over_key,
            ),
            over_key: _insufficient_goal_block(
                over_key,
                warnings=w,
                legacy_slices=legacy_slices,
                contexts=lam_rows,
                complementary_market=under_key,
            ),
        }

    poisson_fn = poisson_market_probability_ht if is_ht else poisson_market_probability_ft
    poisson_under = poisson_fn(under_key, lam)
    poisson_over = 1.0 - poisson_under

    emp_under, emp_rows, emp_warnings = weighted_empirical_probability(
        ctx_list,
        under_key,
        home_team_id=contexts.home_team_id,
        away_team_id=contexts.away_team_id,
        is_ht=is_ht,
    )
    warnings.extend(emp_warnings)

    if emp_under is None:
        return {
            under_key: _insufficient_goal_block(
                under_key,
                warnings=warnings,
                legacy_slices=legacy_slices,
                contexts=_merge_context_rows(lam_rows, emp_rows),
                complementary_market=over_key,
            ),
            over_key: _insufficient_goal_block(
                over_key,
                warnings=warnings,
                legacy_slices=legacy_slices,
                contexts=_merge_context_rows(lam_rows, emp_rows),
                complementary_market=under_key,
            ),
        }

    emp_over = 1.0 - emp_under
    league_under = league_probs.get(under_key)
    if league_under is None:
        warnings.append("missing_league_event_probability")
        league_over = league_probs.get(over_key)
    else:
        league_over = 1.0 - float(league_under)

    under_raw = blend_and_shrink(poisson_under, emp_under, overall_rel, league_under)
    over_raw = 1.0 - under_raw
    complement_sum = under_raw + over_raw
    merged_ctx = _merge_context_rows(lam_rows, emp_rows)

    return {
        under_key: _build_ou_side_block(
            market_key=under_key,
            complementary_market=over_key,
            lam=lam,
            lambda_rows=lam_rows,
            poisson_p=poisson_under,
            emp_p=emp_under,
            league_p=league_under,
            final_raw=under_raw,
            overall_rel=overall_rel,
            merged_ctx=merged_ctx,
            warnings=warnings,
            legacy_slices=legacy_slices,
            is_ht=is_ht,
            contexts_obj=contexts,
            complement_sum=complement_sum,
        ),
        over_key: _build_ou_side_block(
            market_key=over_key,
            complementary_market=under_key,
            lam=lam,
            lambda_rows=lam_rows,
            poisson_p=poisson_over,
            emp_p=emp_over,
            league_p=league_over,
            final_raw=over_raw,
            overall_rel=overall_rel,
            merged_ctx=merged_ctx,
            warnings=warnings,
            legacy_slices=legacy_slices,
            is_ht=is_ht,
            contexts_obj=contexts,
            complement_sum=complement_sum,
        ),
    }


def calculate_goal_market_v2(
    market_key: str,
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
    *,
    legacy_slices,
) -> dict[str, Any]:
    """Wrapper singolo mercato: delega alla pipeline a coppia condivisa."""
    for under_key, over_key, is_ht in _OU_COMPLEMENT_PAIRS:
        if market_key in (under_key, over_key):
            pair = calculate_goal_market_pair_v2(
                under_key,
                over_key,
                contexts,
                league_probs,
                legacy_slices=legacy_slices,
                is_ht=is_ht,
            )
            return pair[market_key]
    return _insufficient_goal_block(
        market_key,
        warnings=["unknown_goal_market"],
        legacy_slices=legacy_slices,
    )


def _merge_context_rows(
    lam_rows: list[dict[str, Any]],
    emp_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    emp_by_name = {r["name"]: r for r in emp_rows}
    merged: list[dict[str, Any]] = []
    for lr in lam_rows:
        er = emp_by_name.get(lr["name"], {})
        merged.append(
            {
                "name": lr["name"],
                "label": lr["label"],
                "weight": lr.get("weight"),
                "original_weight": lr.get("original_weight", lr.get("weight")),
                "effective_weight": lr.get("effective_weight", lr.get("weight")),
                "weight_renormalized": lr.get("weight_renormalized", False),
                "sample_home": lr["sample_home"],
                "sample_away": lr["sample_away"],
                "lambda_total": lr.get("lambda_total"),
                "hit_rate_home": er.get("hit_rate_home"),
                "hit_rate_away": er.get("hit_rate_away"),
                "empirical_probability": er.get("empirical_probability"),
                "reliability": lr.get("reliability"),
                "status": lr.get("status") if lr.get("status") != STATUS_AVAILABLE else er.get("status", lr.get("status")),
            },
        )
    return merged


def _overall_reliability_from_contexts(
    contexts: list[GoalContextSlice],
) -> tuple[float, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    rel_vals: list[tuple[float, float]] = []
    _, weight_details = _context_weight_details(contexts)

    for ctx in contexts:
        wf = _weight_fields(ctx, weight_details)
        rel = context_reliability(ctx.sample_home, ctx.sample_away, ctx.target_sample)
        usable = _context_usable(ctx)
        if not usable:
            warnings.append(f"low_sample:{ctx.name}")
        else:
            rel_vals.append((rel, float(wf["effective_weight"])))
        rows.append(
            {
                "name": ctx.name,
                "label": ctx.label,
                **wf,
                "sample_home": ctx.sample_home,
                "sample_away": ctx.sample_away,
                "reliability": round(rel, 4),
                "status": STATUS_AVAILABLE if usable else "low_sample",
            },
        )
    overall_rel = _weighted_blend(rel_vals) or 0.0
    return overall_rel, rows, warnings


def shrink_empirical_only(
    empirical_p: float,
    overall_reliability: float,
    league_p: float | None,
) -> float:
    if league_p is not None:
        return overall_reliability * empirical_p + (1.0 - overall_reliability) * league_p
    return empirical_p


def _ht_1x2_counts_from_fixtures(
    fixtures: list,
    team_id: int,
    *,
    from_home_pov: bool,
) -> tuple[int, int, int, int]:
    """Ritorna (home_lead, draw, away_lead, sample) dal POV del matchup target."""
    home_lead = draw = away_lead = sample = 0
    for f in fixtures:
        gf, ga = team_halftime_goals_in_fixture(f, team_id)
        if gf is None or ga is None:
            continue
        sample += 1
        if from_home_pov:
            if gf > ga:
                home_lead += 1
            elif gf == ga:
                draw += 1
            else:
                away_lead += 1
        else:
            # POV ospite: se ospite avanti → AWAY_PT; se sotto → HOME_PT
            if gf > ga:
                away_lead += 1
            elif gf == ga:
                draw += 1
            else:
                home_lead += 1
    return home_lead, draw, away_lead, sample


def _ht_1x2_rates_for_context(
    ctx: GoalContextSlice,
    *,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, float | None] | None:
    """Vettore empirico [HOME, DRAW, AWAY] su stesso campione di contesto."""
    # Fast path test/totals-only: draw hits cached; resto ripartito in modo simmetrico
    if not ctx.home_fixtures and not ctx.away_fixtures:
        sh = ctx.home_totals.sample
        sa = ctx.away_totals.sample
        if sh <= 0 or sa <= 0:
            return None
        rate_draw = (
            (ctx.home_totals.halftime_draw_hits / sh)
            + (ctx.away_totals.halftime_draw_hits / sa)
        ) / 2
        rem = max(0.0, 1.0 - rate_draw)
        rate_home = rem / 2.0
        rate_away = rem / 2.0
        return {
            SEL_HOME_PT: rate_home,
            SEL_DRAW_PT: rate_draw,
            SEL_AWAY_PT: rate_away,
            "sample_home": sh,
            "sample_away": sa,
            "totals_only_fallback": True,
        }

    hh, hd, ha, hs = _ht_1x2_counts_from_fixtures(
        ctx.home_fixtures, home_team_id, from_home_pov=True,
    )
    ah, ad, aa, as_ = _ht_1x2_counts_from_fixtures(
        ctx.away_fixtures, away_team_id, from_home_pov=False,
    )
    if hs <= 0 or as_ <= 0:
        return None

    rate_home = ((hh / hs) + (ah / as_)) / 2
    rate_draw = ((hd / hs) + (ad / as_)) / 2
    rate_away = ((ha / hs) + (aa / as_)) / 2
    return {
        SEL_HOME_PT: rate_home,
        SEL_DRAW_PT: rate_draw,
        SEL_AWAY_PT: rate_away,
        "hit_rate_home_1": hh / hs,
        "hit_rate_home_x": hd / hs,
        "hit_rate_home_2": ha / hs,
        "hit_rate_away_1": ah / as_,
        "hit_rate_away_x": ad / as_,
        "hit_rate_away_2": aa / as_,
        "sample_home": hs,
        "sample_away": as_,
    }


def weighted_empirical_ht_1x2_vector(
    contexts: list[GoalContextSlice],
    *,
    home_team_id: int,
    away_team_id: int,
) -> tuple[dict[str, float] | None, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    acc: dict[str, list[tuple[float, float]]] = {
        SEL_HOME_PT: [],
        SEL_DRAW_PT: [],
        SEL_AWAY_PT: [],
    }
    _, weight_details = _context_weight_details(contexts)

    for ctx in contexts:
        wf = _weight_fields(ctx, weight_details)
        if not _context_usable(ctx):
            rows.append(
                {
                    "name": ctx.name,
                    "label": ctx.label,
                    **wf,
                    "sample_home": ctx.sample_home,
                    "sample_away": ctx.sample_away,
                    "rate_1_pt": None,
                    "rate_x_pt": None,
                    "rate_2_pt": None,
                    "status": "low_sample",
                },
            )
            continue

        rates = _ht_1x2_rates_for_context(
            ctx, home_team_id=home_team_id, away_team_id=away_team_id,
        )
        if rates is None:
            # Fallback: rates per mercato singolo (compat fixture-less contexts in test)
            rh = empirical_probability_for_context(
                ctx, SEL_HOME_PT, home_team_id=home_team_id, away_team_id=away_team_id, is_ht=True,
            )
            rx = empirical_probability_for_context(
                ctx, SEL_DRAW_PT, home_team_id=home_team_id, away_team_id=away_team_id, is_ht=True,
            )
            ra = empirical_probability_for_context(
                ctx, SEL_AWAY_PT, home_team_id=home_team_id, away_team_id=away_team_id, is_ht=True,
            )
            if rh is None or rx is None or ra is None:
                rows.append(
                    {
                        "name": ctx.name,
                        "label": ctx.label,
                        **wf,
                        "sample_home": ctx.sample_home,
                        "sample_away": ctx.sample_away,
                        "rate_1_pt": None,
                        "rate_x_pt": None,
                        "rate_2_pt": None,
                        "status": "insufficient_ht_1x2_rates",
                    },
                )
                continue
            rates = {
                SEL_HOME_PT: rh,
                SEL_DRAW_PT: rx,
                SEL_AWAY_PT: ra,
            }
            # Normalizza il vettore di contesto se somma > 0
            s = rh + rx + ra
            if s > 0:
                rates = {
                    SEL_HOME_PT: rh / s,
                    SEL_DRAW_PT: rx / s,
                    SEL_AWAY_PT: ra / s,
                }

        ew = float(wf["effective_weight"])
        for mk in _HT_1X2_MARKETS:
            acc[mk].append((float(rates[mk]), ew))
        rows.append(
            {
                "name": ctx.name,
                "label": ctx.label,
                **wf,
                "sample_home": rates.get("sample_home", ctx.sample_home),
                "sample_away": rates.get("sample_away", ctx.sample_away),
                "rate_1_pt": round(float(rates[SEL_HOME_PT]), 6),
                "rate_x_pt": round(float(rates[SEL_DRAW_PT]), 6),
                "rate_2_pt": round(float(rates[SEL_AWAY_PT]), 6),
                "hit_rate_home_1": rates.get("hit_rate_home_1"),
                "hit_rate_home_x": rates.get("hit_rate_home_x"),
                "hit_rate_home_2": rates.get("hit_rate_home_2"),
                "hit_rate_away_1": rates.get("hit_rate_away_1"),
                "hit_rate_away_x": rates.get("hit_rate_away_x"),
                "hit_rate_away_2": rates.get("hit_rate_away_2"),
                "status": STATUS_AVAILABLE,
            },
        )

    if not acc[SEL_HOME_PT]:
        warnings.append("insufficient_empirical:HT_1X2")
        return None, rows, warnings

    vector = {
        mk: _weighted_blend(acc[mk]) or 0.0
        for mk in _HT_1X2_MARKETS
    }
    return vector, rows, warnings


def _normalize_probability_vector(
    probs: dict[str, float],
    keys: tuple[str, ...],
) -> tuple[dict[str, float], float]:
    floored = {k: max(MIN_PROB, float(probs.get(k, 0.0))) for k in keys}
    total = sum(floored.values())
    if total <= 0:
        n = len(keys)
        return {k: 1.0 / n for k in keys}, 1.0
    normalized = {k: floored[k] / total for k in keys}
    return normalized, sum(normalized.values())


def calculate_first_half_1x2_family_v2(
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
) -> dict[str, dict[str, Any]]:
    """Famiglia 1X2 PT: vettore empirico unico + shrinkage + normalizzazione."""
    ctx_list = contexts.ht_slices()
    warnings: list[str] = []

    def _insufficient_all(extra: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for mk in _HT_1X2_MARKETS:
            out[mk] = {
                "market_key": mk,
                "formula_version": FORMULA_HT_1X2_V2,
                "event_definition": EVENT_DEFINITIONS.get(mk),
                "final_odd": None,
                "status": STATUS_INSUFFICIENT_DATA,
                "summary": None,
                "contexts": [],
                "family": {
                    "keys": list(_HT_1X2_MARKETS),
                    "sum_check": None,
                    "formula_version": FORMULA_HT_1X2_V2,
                },
                "legacy_excel_parity": {"final_odd": None, "enabled_for_kpi": False},
                "warnings": list(extra),
            }
        return out

    if _usable_context_count(ctx_list) == 0:
        return _insufficient_all(["insufficient_goal_sample:all_contexts"])

    overall_rel, rel_rows, rel_warnings = _overall_reliability_from_contexts(ctx_list)
    warnings.extend(rel_warnings)

    emp_vec, emp_rows, emp_warnings = weighted_empirical_ht_1x2_vector(
        ctx_list,
        home_team_id=contexts.home_team_id,
        away_team_id=contexts.away_team_id,
    )
    warnings.extend(emp_warnings)

    if emp_vec is None:
        merged = _merge_context_rows(rel_rows, emp_rows)
        out = _insufficient_all(warnings)
        for mk in _HT_1X2_MARKETS:
            out[mk]["contexts"] = merged
        return out

    league_vec: dict[str, float | None] = {
        mk: league_probs.get(mk) for mk in _HT_1X2_MARKETS
    }
    if any(v is None for v in league_vec.values()):
        warnings.append("missing_league_halftime_1x2_probability")
        # Se manca il prior, usa solo empirico (nessuno shrinkage verso None)
        final_pre = dict(emp_vec)
    else:
        final_pre = {
            mk: shrink_empirical_only(
                float(emp_vec[mk]),
                overall_rel,
                float(league_vec[mk]),  # type: ignore[arg-type]
            )
            for mk in _HT_1X2_MARKETS
        }

    final_vec, sum_after = _normalize_probability_vector(final_pre, _HT_1X2_MARKETS)
    if contexts.skipped_missing_halftime_score > 0:
        warnings.append(
            f"skipped_missing_halftime_score:{contexts.skipped_missing_halftime_score}",
        )

    merged_ctx = _merge_context_rows(rel_rows, emp_rows)
    # Arricchisci context rows con rate famiglia se presenti in emp_rows
    emp_by_name = {r["name"]: r for r in emp_rows}
    for row in merged_ctx:
        er = emp_by_name.get(row["name"], {})
        for fld in (
            "rate_1_pt", "rate_x_pt", "rate_2_pt",
            "hit_rate_home_1", "hit_rate_home_x", "hit_rate_home_2",
            "hit_rate_away_1", "hit_rate_away_x", "hit_rate_away_2",
        ):
            if fld in er:
                row[fld] = er[fld]

    family_meta = {
        "keys": list(_HT_1X2_MARKETS),
        "empirical_vector": {mk: round(emp_vec[mk], 6) for mk in _HT_1X2_MARKETS},
        "league_vector": {
            mk: (round(float(league_vec[mk]), 6) if league_vec[mk] is not None else None)
            for mk in _HT_1X2_MARKETS
        },
        "pre_normalize_vector": {mk: round(final_pre[mk], 6) for mk in _HT_1X2_MARKETS},
        "final_vector": {mk: round(final_vec[mk], 6) for mk in _HT_1X2_MARKETS},
        "sum_raw": round(sum_after, 6),
        "sum_check": {
            "sum": sum_after,
            "tolerance": FAMILY_SUM_TOLERANCE,
            "ok": abs(sum_after - 1.0) <= FAMILY_SUM_TOLERANCE,
        },
        "overall_reliability": round(overall_rel, 6),
        "formula_version": FORMULA_HT_1X2_V2,
        "previous_formula_versions": {
            SEL_HOME_PT: FORMULA_HT_1X2_V1,
            SEL_DRAW_PT: FORMULA_DRAW_PT_V1,
            SEL_AWAY_PT: FORMULA_HT_1X2_V1,
        },
        "change_note": (
            "v2: vettore empirico unico per contesto, stessa reliability, "
            "floor di sicurezza e normalizzazione unica (somma=1)."
        ),
    }

    status_base = STATUS_AVAILABLE
    if overall_rel < 1.0 or any("low_sample" in w for w in warnings):
        status_base = STATUS_PARTIAL_LOW_SAMPLE

    out: dict[str, dict[str, Any]] = {}
    for mk in _HT_1X2_MARKETS:
        p_raw = final_vec[mk]
        final_odd, prob_raw, prob_capped, prob_warnings = probability_to_odd(p_raw)
        side_warnings = list(warnings) + list(prob_warnings)
        status = status_base
        if final_odd is None:
            status = STATUS_INSUFFICIENT_DATA
        summary = {
            "empirical_probability": round(emp_vec[mk], 6),
            "league_halftime_1x2_probability": league_vec[mk],
            "overall_reliability": round(overall_rel, 6),
            "reliability_badge": _reliability_badge(overall_rel),
            "probability_raw": round(prob_raw, 6),
            "probability_capped": round(prob_capped, 6),
            "final_probability_raw": round(prob_raw, 6),
            "final_probability": round(prob_capped, 6),
            "final_odd": final_odd,
            "family_sum": round(sum_after, 6),
            "family_sum_ok": abs(sum_after - 1.0) <= FAMILY_SUM_TOLERANCE,
        }
        if mk == SEL_DRAW_PT:
            summary["league_halftime_draw_probability"] = league_vec[mk]
        out[mk] = {
            "market_key": mk,
            "formula_version": FORMULA_HT_1X2_V2,
            "event_definition": EVENT_DEFINITIONS.get(mk),
            "final_odd": final_odd,
            "status": status,
            "weights": dict(CECCHINO_GOAL_MARKET_WEIGHTS),
            "summary": summary,
            "contexts": merged_ctx,
            "family": family_meta,
            "legacy_excel_parity": {"final_odd": None, "enabled_for_kpi": False},
            "warnings": side_warnings,
        }
    return out


def calculate_first_half_1x2_market_v1(
    market_key: str,
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
) -> dict[str, Any]:
    """Compat: singolo esito dalla famiglia v2 normalizzata."""
    family = calculate_first_half_1x2_family_v2(contexts, league_probs)
    return family.get(market_key) or {
        "market_key": market_key,
        "formula_version": FORMULA_HT_1X2_V2,
        "final_odd": None,
        "status": STATUS_INSUFFICIENT_DATA,
        "summary": None,
        "contexts": [],
        "warnings": ["unknown_ht_1x2_market"],
    }


def calculate_first_half_draw_market_v1(
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
) -> dict[str, Any]:
    """Alias compatibile: Quota Cecchino X PT (famiglia v2)."""
    return calculate_first_half_1x2_market_v1(SEL_DRAW_PT, contexts, league_probs)


def build_goal_markets_v2(
    db: Session,
    target_fixture: Fixture,
    contexts: GoalMarketContexts,
) -> dict[str, Any]:
    """Entry point: coppie OU condivise + famiglia 1X2 PT normalizzata."""
    legacy_slices = build_goal_fixture_slices(db, target_fixture)
    league_fx = load_league_finished_fixtures_before(db, target_fixture)
    league_probs = league_event_probabilities(league_fx)

    markets: dict[str, Any] = {}
    markets.update(calculate_first_half_1x2_family_v2(contexts, league_probs))
    for under_key, over_key, is_ht in _OU_COMPLEMENT_PAIRS:
        markets.update(
            calculate_goal_market_pair_v2(
                under_key,
                over_key,
                contexts,
                league_probs,
                legacy_slices=legacy_slices,
                is_ht=is_ht,
            ),
        )
    return markets
