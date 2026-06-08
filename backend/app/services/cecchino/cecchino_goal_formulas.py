"""Formule Quota Cecchino Over/Under — parità Excel OVER/UNDER + rate-to-odd PT."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_constants import (
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PARTIAL_LOW_SAMPLE,
    WARNING_ZERO_PROBABILITY,
)
from app.services.cecchino.cecchino_fixture_history import (
    MIN_GOAL_HOME_AWAY,
    MIN_GOAL_HT,
    MIN_GOAL_TOTAL,
    TARGET_GOAL_HOME_AWAY,
    TARGET_GOAL_HT,
    TARGET_GOAL_TOTAL,
    GoalFixtureSlices,
    GoalTotals,
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

FORMULA_FT_OVER = "over_under_fulltime_excel_parity_v1"
FORMULA_FT_UNDER = "over_under_fulltime_excel_parity_v1"
FORMULA_PT = "first_half_rate_to_odd_v1"

_OVER_NOTE = (
    "Excel parity: Over 1.5 e Over 2.5 usano stesso coefficiente nel foglio OVER."
)
_UNDER_NOTE = (
    "Excel parity: Under 2.5 e Under 3.5 usano stesso coefficiente nel foglio UNDER."
)

_FT_MARKETS = (SEL_OVER_1_5, SEL_OVER_2_5, SEL_UNDER_2_5, SEL_UNDER_3_5)
_PT_MARKETS = (SEL_OVER_PT_0_5, SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5)


def _round_odd(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v, 2)


def _ft_samples_ok(slices: GoalFixtureSlices) -> tuple[bool, bool, list[str]]:
    """Restituisce (min_ok, ideal_ok, warnings)."""
    warnings: list[str] = []
    checks = (
        (slices.home_home_5.sample, slices.away_away_5.sample, MIN_GOAL_HOME_AWAY, TARGET_GOAL_HOME_AWAY, "cf"),
        (slices.home_total_10.sample, slices.away_total_10.sample, MIN_GOAL_TOTAL, TARGET_GOAL_TOTAL, "totals"),
    )
    min_ok = True
    ideal_ok = True
    for h_s, a_s, min_n, ideal_n, label in checks:
        if h_s < min_n or a_s < min_n:
            min_ok = False
            warnings.append(f"insufficient_goal_sample:{label}")
        elif h_s < ideal_n or a_s < ideal_n:
            ideal_ok = False
            warnings.append(f"partial_goal_sample:{label}")
    if not min_ok:
        return False, False, warnings
    if not ideal_ok:
        warnings.append("sample_status:partial_sample")
    return True, ideal_ok, warnings


def _pt_samples_ok(slices: GoalFixtureSlices) -> tuple[bool, bool, list[str]]:
    warnings: list[str] = []
    h_s = slices.home_home_ht_5.sample
    a_s = slices.away_away_ht_5.sample
    if h_s < MIN_GOAL_HT or a_s < MIN_GOAL_HT:
        warnings.append("insufficient_goal_sample:pt")
        return False, False, warnings
    ideal_ok = h_s >= TARGET_GOAL_HT and a_s >= TARGET_GOAL_HT
    if not ideal_ok:
        warnings.append("partial_goal_sample:pt")
        warnings.append("sample_status:partial_sample")
    if slices.skipped_missing_halftime_score > 0:
        warnings.append(f"skipped_missing_halftime_score:{slices.skipped_missing_halftime_score}")
    return True, ideal_ok, warnings


def _block_home_away(
    *,
    home: GoalTotals,
    away: GoalTotals,
    divisor: int,
) -> dict[str, Any]:
    home_component = (home.goals_for + away.goals_against) / divisor
    away_component = (away.goals_for + home.goals_against) / divisor
    block_value = (home_component + away_component) / 2
    return {
        "home_goals_for": home.goals_for,
        "away_goals_against": away.goals_against,
        "divisor_home": divisor,
        "home_component": round(home_component, 4),
        "away_goals_for": away.goals_for,
        "home_goals_against": home.goals_against,
        "divisor_away": divisor,
        "away_component": round(away_component, 4),
        "block_value": round(block_value, 4),
    }


def _block_totals(
    *,
    home_total: GoalTotals,
    away_total: GoalTotals,
    divisor: int,
) -> dict[str, Any]:
    home_component = (home_total.goals_for + away_total.goals_against) / divisor
    away_component = (away_total.goals_for + home_total.goals_against) / divisor
    block_value = (home_component + away_component) / 2
    return {
        "home_goals_for": home_total.goals_for,
        "away_goals_against": away_total.goals_against,
        "divisor": divisor,
        "home_component": round(home_component, 4),
        "away_goals_for": away_total.goals_for,
        "home_goals_against": home_total.goals_against,
        "away_component": round(away_component, 4),
        "block_value": round(block_value, 4),
    }


def _block_mixed(
    *,
    home_ctx: GoalTotals,
    away_ctx: GoalTotals,
    home_total: GoalTotals,
    away_total: GoalTotals,
    divisor: int,
) -> dict[str, Any]:
    home_for = (home_ctx.goals_for + home_total.goals_for) / divisor
    home_against = (home_ctx.goals_against + home_total.goals_against) / divisor
    home_coeff = (home_for + home_against) / 2
    away_for = (away_ctx.goals_for + away_total.goals_for) / divisor
    away_against = (away_ctx.goals_against + away_total.goals_against) / divisor
    away_coeff = (away_for + away_against) / 2
    block_value = (home_coeff + away_coeff) / 2
    return {
        "home_goals_for_ctx": home_ctx.goals_for,
        "home_goals_for_total": home_total.goals_for,
        "home_goals_against_ctx": home_ctx.goals_against,
        "home_goals_against_total": home_total.goals_against,
        "divisor": divisor,
        "home_coeff": round(home_coeff, 4),
        "away_goals_for_ctx": away_ctx.goals_for,
        "away_goals_for_total": away_total.goals_for,
        "away_goals_against_ctx": away_ctx.goals_against,
        "away_goals_against_total": away_total.goals_against,
        "away_coeff": round(away_coeff, 4),
        "block_value": round(block_value, 4),
    }


def _build_ft_result(
    *,
    market_key: str,
    slices: GoalFixtureSlices,
    divisors: tuple[int, int, int],
    formula_note: str,
    formula_version: str,
) -> dict[str, Any]:
    min_ok, ideal_ok, warnings = _ft_samples_ok(slices)
    if not min_ok:
        return {
            "market_key": market_key,
            "formula_version": formula_version,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "blocks": None,
            "formula_note": formula_note,
            "warnings": warnings,
            "sample_status": STATUS_INSUFFICIENT_DATA,
        }

    d_cf, d_tot, d_mix = divisors
    blocks = {
        "home_away": _block_home_away(
            home=slices.home_home_5,
            away=slices.away_away_5,
            divisor=d_cf,
        ),
        "totals": _block_totals(
            home_total=slices.home_total_10,
            away_total=slices.away_total_10,
            divisor=d_tot,
        ),
        "mixed": _block_mixed(
            home_ctx=slices.home_home_5,
            away_ctx=slices.away_away_5,
            home_total=slices.home_total_10,
            away_total=slices.away_total_10,
            divisor=d_mix,
        ),
    }
    coeffs = [blocks[k]["block_value"] for k in ("home_away", "totals", "mixed")]
    final_odd = _round_odd(sum(coeffs) / 3)

    status = STATUS_AVAILABLE if ideal_ok else STATUS_PARTIAL_LOW_SAMPLE
    return {
        "market_key": market_key,
        "formula_version": formula_version,
        "final_odd": final_odd,
        "status": status,
        "blocks": blocks,
        "formula_note": formula_note,
        "warnings": warnings,
        "sample_status": STATUS_AVAILABLE if ideal_ok else "partial_sample",
    }


def calculate_over_fulltime_excel_parity(slices: GoalFixtureSlices) -> dict[str, Any]:
    """Coefficiente Over FT — divisori 6/11/16, media 3 blocchi."""
    return _build_ft_result(
        market_key="OVER_FT",
        slices=slices,
        divisors=(6, 11, 16),
        formula_note=_OVER_NOTE,
        formula_version=FORMULA_FT_OVER,
    )


def calculate_under_fulltime_excel_parity(slices: GoalFixtureSlices) -> dict[str, Any]:
    """Coefficiente Under FT — divisori 4/9/14, media 3 blocchi."""
    return _build_ft_result(
        market_key="UNDER_FT",
        slices=slices,
        divisors=(4, 9, 14),
        formula_note=_UNDER_NOTE,
        formula_version=FORMULA_FT_UNDER,
    )


def _pt_hits(totals: GoalTotals, market_key: str) -> int:
    if market_key == SEL_OVER_PT_0_5:
        return totals.over_pt_0_5_hits
    if market_key == SEL_OVER_PT_1_5:
        return totals.over_pt_1_5_hits
    if market_key == SEL_UNDER_PT_1_5:
        return totals.under_pt_1_5_hits
    return 0


def _pt_event_label(market_key: str) -> str:
    if market_key == SEL_OVER_PT_0_5:
        return "halftime_total_goals >= 1"
    if market_key == SEL_OVER_PT_1_5:
        return "halftime_total_goals >= 2"
    return "halftime_total_goals <= 1"


def calculate_first_half_rate_to_odd(
    market_key: str,
    slices: GoalFixtureSlices,
) -> dict[str, Any]:
    """Rate hit HT → prob media → quota = 1/prob."""
    min_ok, ideal_ok, warnings = _pt_samples_ok(slices)
    event = _pt_event_label(market_key)
    home = slices.home_home_ht_5
    away = slices.away_away_ht_5

    if not min_ok:
        return {
            "market_key": market_key,
            "formula_version": FORMULA_PT,
            "event": event,
            "home": {"sample": home.sample, "hits": 0, "rate": None},
            "away": {"sample": away.sample, "hits": 0, "rate": None},
            "probability": None,
            "final_odd": None,
            "status": STATUS_INSUFFICIENT_DATA,
            "warnings": warnings,
            "skipped_missing_halftime_score": slices.skipped_missing_halftime_score,
        }

    home_hits = _pt_hits(home, market_key)
    away_hits = _pt_hits(away, market_key)
    rate_home = home_hits / home.sample if home.sample > 0 else 0.0
    rate_away = away_hits / away.sample if away.sample > 0 else 0.0
    prob = (rate_home + rate_away) / 2

    final_odd: float | None = None
    status = STATUS_AVAILABLE if ideal_ok else STATUS_PARTIAL_LOW_SAMPLE
    if prob <= 0:
        warnings.append(f"{WARNING_ZERO_PROBABILITY}:{market_key}")
        status = STATUS_INSUFFICIENT_DATA
    else:
        final_odd = _round_odd(1.0 / prob)

    return {
        "market_key": market_key,
        "formula_version": FORMULA_PT,
        "event": event,
        "home": {
            "sample": home.sample,
            "hits": home_hits,
            "rate": round(rate_home, 4),
        },
        "away": {
            "sample": away.sample,
            "hits": away_hits,
            "rate": round(rate_away, 4),
        },
        "probability": round(prob, 4) if prob > 0 else None,
        "final_odd": final_odd,
        "status": status,
        "warnings": warnings,
        "skipped_missing_halftime_score": slices.skipped_missing_halftime_score,
    }


def calculate_first_half_goal_market_odds(
    market_key: str,
    slices: GoalFixtureSlices,
) -> dict[str, Any]:
    """Alias per calculate_first_half_rate_to_odd."""
    return calculate_first_half_rate_to_odd(market_key, slices)


def build_goal_market_cecchino_odds_legacy(slices: GoalFixtureSlices) -> dict[str, Any]:
    """Calcola quote Excel parity legacy (solo debug)."""
    over_ft = calculate_over_fulltime_excel_parity(slices)
    under_ft = calculate_under_fulltime_excel_parity(slices)

    def _clone_ft(base: dict[str, Any], market_key: str) -> dict[str, Any]:
        out = dict(base)
        out["market_key"] = market_key
        return out

    markets: dict[str, Any] = {
        SEL_OVER_1_5: _clone_ft(over_ft, SEL_OVER_1_5),
        SEL_OVER_2_5: _clone_ft(over_ft, SEL_OVER_2_5),
        SEL_UNDER_2_5: _clone_ft(under_ft, SEL_UNDER_2_5),
        SEL_UNDER_3_5: _clone_ft(under_ft, SEL_UNDER_3_5),
    }
    for mk in (SEL_OVER_PT_0_5, SEL_OVER_PT_1_5, SEL_UNDER_PT_1_5):
        markets[mk] = calculate_first_half_rate_to_odd(mk, slices)
    return markets


def build_goal_market_cecchino_odds(
    db,
    target_fixture,
    contexts=None,
) -> dict[str, Any]:
    """Calcola quote Cecchino v2 Poisson+empirico per i 7 mercati OU."""
    from app.services.cecchino.cecchino_fixture_history import (
        GoalMarketContexts,
        build_goal_market_contexts,
    )
    from app.services.cecchino.cecchino_goal_poisson_v2 import build_goal_markets_v2

    if contexts is None:
        contexts = build_goal_market_contexts(db, target_fixture)
    return build_goal_markets_v2(db, target_fixture, contexts)


def build_goal_market_debug(market_result: dict[str, Any]) -> dict[str, Any]:
    """Payload debug compatto per un singolo mercato goal."""
    if not market_result:
        return {}
    out: dict[str, Any] = {
        "market_key": market_result.get("market_key"),
        "formula_version": market_result.get("formula_version"),
        "final_odd": market_result.get("final_odd"),
        "status": market_result.get("status"),
        "warnings": list(market_result.get("warnings") or []),
    }
    if market_result.get("weights"):
        out["weights"] = market_result["weights"]
    if market_result.get("summary"):
        out["summary"] = market_result["summary"]
    if market_result.get("contexts"):
        out["contexts"] = market_result["contexts"]
    if market_result.get("technical"):
        out["technical"] = market_result["technical"]
    if market_result.get("legacy_excel_parity"):
        out["legacy_excel_parity"] = market_result["legacy_excel_parity"]
    if market_result.get("formula_note"):
        out["formula_note"] = market_result["formula_note"]
    if market_result.get("blocks"):
        out["blocks"] = market_result["blocks"]
    if market_result.get("event"):
        out["event"] = market_result["event"]
        out["home"] = market_result.get("home")
        out["away"] = market_result.get("away")
        out["probability"] = market_result.get("probability")
        out["skipped_missing_halftime_score"] = market_result.get(
            "skipped_missing_halftime_score",
        )
    return out


def goal_market_kpi_entry(markets: dict[str, Any], market_key: str) -> tuple[float | None, str | None, str | None]:
    """Restituisce (quota, formula_version, status) per KPI."""
    block = markets.get(market_key) if isinstance(markets, dict) else None
    if not block or not isinstance(block, dict):
        return None, None, None
    odd = block.get("final_odd")
    try:
        q = round(float(odd), 2) if odd is not None else None
    except (TypeError, ValueError):
        q = None
    return q, block.get("formula_version"), block.get("status")
