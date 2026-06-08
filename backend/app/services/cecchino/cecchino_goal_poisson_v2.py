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
    SEL_OVER_1_5,
    SEL_OVER_2_5,
    SEL_OVER_PT_0_5,
    SEL_OVER_PT_1_5,
    SEL_UNDER_2_5,
    SEL_UNDER_3_5,
    SEL_UNDER_PT_1_5,
)

FORMULA_V2 = "goal_market_poisson_empirical_v2"
BLEND_POISSON = 0.65
BLEND_EMPIRICAL = 0.35
MIN_PROB = 0.03
MAX_PROB = 0.97

_CONTEXT_WEIGHT_MAP: dict[str, float] = {
    CONTEXT_KEY_TOTALS: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_TOTALS],
    CONTEXT_KEY_HOME_AWAY: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_HOME_AWAY],
    CONTEXT_KEY_LAST6_TOTALS: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST6_TOTALS],
    CONTEXT_KEY_LAST5_HOME_AWAY: CECCHINO_GOAL_MARKET_WEIGHTS[PICCHETTO_KEY_LAST5_HOME_AWAY],
}

_FT_MARKETS = (SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5)
_PT_MARKETS = (SEL_OVER_PT_0_5, SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5)


def poisson_pmf(k: int, lambda_value: float) -> float:
    if lambda_value <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lambda_value) * (lambda_value**k) / factorial(k)


def poisson_cumulative(lam: float, max_k: int) -> float:
    return sum(poisson_pmf(k, lam) for k in range(max_k + 1))


def poisson_market_probability_ft(market_key: str, lambda_ft: float) -> float:
    if market_key == SEL_OVER_1_5:
        return 1.0 - poisson_cumulative(lambda_ft, 1)
    if market_key == SEL_OVER_2_5:
        return 1.0 - poisson_cumulative(lambda_ft, 2)
    if market_key == SEL_UNDER_2_5:
        return poisson_cumulative(lambda_ft, 2)
    if market_key == SEL_UNDER_3_5:
        return poisson_cumulative(lambda_ft, 3)
    return 0.0


def poisson_market_probability_ht(market_key: str, lambda_ht: float) -> float:
    if market_key == SEL_OVER_PT_0_5:
        return 1.0 - poisson_pmf(0, lambda_ht)
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
    if market_key == SEL_OVER_2_5:
        return total >= 3
    if market_key == SEL_UNDER_2_5:
        return total <= 2
    if market_key == SEL_UNDER_3_5:
        return total <= 3
    return False


def _pt_event_hit(ht_total: int, market_key: str) -> bool:
    if market_key == SEL_OVER_PT_0_5:
        return ht_total >= 1
    if market_key == SEL_OVER_PT_1_5:
        return ht_total >= 2
    if market_key == SEL_UNDER_PT_1_5:
        return ht_total <= 1
    return False


def _hit_rates_for_context(
    ctx: GoalContextSlice,
    market_key: str,
    *,
    home_team_id: int,
    away_team_id: int,
    is_ht: bool,
) -> tuple[float | None, float | None]:
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
            if _pt_event_hit(total, market_key):
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
            if _pt_event_hit(total, market_key):
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
    if not league_fixtures:
        return {m: None for m in _FT_MARKETS + _PT_MARKETS}

    ft_totals: dict[str, int] = {m: 0 for m in _FT_MARKETS}
    pt_totals: dict[str, int] = {m: 0 for m in _PT_MARKETS}
    ft_n = pt_n = 0

    for f in league_fixtures:
        if f.goals_home is None or f.goals_away is None:
            continue
        gh, ga = int(f.goals_home), int(f.goals_away)
        ft_n += 1
        for m in _FT_MARKETS:
            if _ft_event_hit(gh, ga, m):
                ft_totals[m] += 1

        ht = halftime_total_goals(f)
        if ht is not None:
            pt_n += 1
            if ht >= 1:
                pt_totals[SEL_OVER_PT_0_5] += 1
            if ht >= 2:
                pt_totals[SEL_OVER_PT_1_5] += 1
            if ht <= 1:
                pt_totals[SEL_UNDER_PT_1_5] += 1

    out: dict[str, float | None] = {}
    for m in _FT_MARKETS:
        out[m] = round(ft_totals[m] / ft_n, 4) if ft_n > 0 else None
    for m in _PT_MARKETS:
        out[m] = round(pt_totals[m] / pt_n, 4) if pt_n > 0 else None
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
    if market_key in (SEL_OVER_1_5, SEL_OVER_2_5):
        return calculate_over_fulltime_excel_parity(slices).get("final_odd")
    if market_key in (SEL_UNDER_2_5, SEL_UNDER_3_5):
        return calculate_under_fulltime_excel_parity(slices).get("final_odd")
    if market_key in _PT_MARKETS:
        return calculate_first_half_rate_to_odd(market_key, slices).get("final_odd")
    return None


def _usable_context_count(contexts: list[GoalContextSlice]) -> int:
    return sum(1 for c in contexts if _context_usable(c))


def calculate_goal_market_v2(
    market_key: str,
    contexts: GoalMarketContexts,
    league_probs: dict[str, float | None],
    *,
    legacy_slices,
) -> dict[str, Any]:
    is_ht = market_key in _PT_MARKETS
    ctx_list = contexts.ht_slices() if is_ht else contexts.ft_slices()
    warnings: list[str] = []

    if _usable_context_count(ctx_list) == 0:
        return {
            "market_key": market_key,
            "formula_version": FORMULA_V2,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "summary": None,
            "contexts": [],
            "legacy_excel_parity": {
                "final_odd": _legacy_excel_odd(market_key, legacy_slices),
                "enabled_for_kpi": False,
            },
            "warnings": ["insufficient_goal_sample:all_contexts"],
        }

    lam, lam_rows, overall_rel, lam_warnings = weighted_lambda(ctx_list)
    warnings.extend(lam_warnings)

    if lam is None or lam <= 0:
        return {
            "market_key": market_key,
            "formula_version": FORMULA_V2,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "summary": None,
            "contexts": lam_rows,
            "legacy_excel_parity": {
                "final_odd": _legacy_excel_odd(market_key, legacy_slices),
                "enabled_for_kpi": False,
            },
            "warnings": warnings + ["lambda_not_computable"],
        }

    poisson_fn = poisson_market_probability_ht if is_ht else poisson_market_probability_ft
    poisson_p = poisson_fn(market_key, lam)

    emp_p, emp_rows, emp_warnings = weighted_empirical_probability(
        ctx_list,
        market_key,
        home_team_id=contexts.home_team_id,
        away_team_id=contexts.away_team_id,
        is_ht=is_ht,
    )
    warnings.extend(emp_warnings)

    if emp_p is None:
        return {
            "market_key": market_key,
            "formula_version": FORMULA_V2,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "summary": None,
            "contexts": _merge_context_rows(lam_rows, emp_rows),
            "legacy_excel_parity": {
                "final_odd": _legacy_excel_odd(market_key, legacy_slices),
                "enabled_for_kpi": False,
            },
            "warnings": warnings,
        }

    league_p = league_probs.get(market_key)
    if league_p is None:
        warnings.append("missing_league_event_probability")

    final_raw = blend_and_shrink(poisson_p, emp_p, overall_rel, league_p)
    final_odd, prob_raw, prob_capped, prob_warnings = probability_to_odd(final_raw)
    warnings.extend(prob_warnings)

    status = STATUS_AVAILABLE
    if overall_rel < 1.0 or any("low_sample" in w for w in warnings):
        status = STATUS_PARTIAL_LOW_SAMPLE
    if final_odd is None:
        status = STATUS_INSUFFICIENT_DATA

    if contexts.skipped_missing_halftime_score > 0 and is_ht:
        warnings.append(
            f"skipped_missing_halftime_score:{contexts.skipped_missing_halftime_score}",
        )

    merged_ctx = _merge_context_rows(lam_rows, emp_rows)
    summary = {
        "lambda": round(lam, 4),
        "poisson_probability": round(poisson_p, 4),
        "empirical_probability": round(emp_p, 4),
        "league_event_probability": league_p,
        "final_probability_raw": round(prob_raw, 4),
        "final_probability_capped": round(prob_capped, 4),
        "final_probability": round(prob_capped, 4),
        "final_odd": final_odd,
        "overall_reliability": round(overall_rel, 4),
        "reliability_badge": _reliability_badge(overall_rel),
    }

    return {
        "market_key": market_key,
        "formula_version": FORMULA_V2,
        "final_odd": final_odd,
        "status": status,
        "weights": dict(CECCHINO_GOAL_MARKET_WEIGHTS),
        "summary": summary,
        "contexts": merged_ctx,
        "technical": {
            "lambda_home_contexts": lam_rows,
            "blend_poisson": BLEND_POISSON,
            "blend_empirical": BLEND_EMPIRICAL,
            "min_probability": MIN_PROB,
            "max_probability": MAX_PROB,
        },
        "legacy_excel_parity": {
            "final_odd": _legacy_excel_odd(market_key, legacy_slices),
            "enabled_for_kpi": False,
        },
        "warnings": warnings,
    }


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


def build_goal_markets_v2(
    db: Session,
    target_fixture: Fixture,
    contexts: GoalMarketContexts,
) -> dict[str, Any]:
    """Entry point v2: Poisson+empirico per KPI + legacy Excel annex."""
    legacy_slices = build_goal_fixture_slices(db, target_fixture)
    league_fx = load_league_finished_fixtures_before(db, target_fixture)
    league_probs = league_event_probabilities(league_fx)

    markets: dict[str, Any] = {}
    for mk in _FT_MARKETS + _PT_MARKETS:
        markets[mk] = calculate_goal_market_v2(
            mk,
            contexts,
            league_probs,
            legacy_slices=legacy_slices,
        )
    return markets
