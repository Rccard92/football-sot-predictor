"""Baseline storiche OVER Q44 per Intensità Goal — Cecchino Fase 47/48."""

from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture
from app.services.cecchino.cecchino_constants import STATUS_INSUFFICIENT_DATA
from app.services.cecchino.cecchino_fixture_history import (
    build_goal_fixture_slices,
    load_league_finished_fixtures_before,
)
from app.services.cecchino.cecchino_goal_formulas import (
    calculate_over_fulltime_excel_parity,
    calculate_under_fulltime_excel_parity,
)
from app.services.sot_feature_math import fixture_key_before

MAX_FIXTURES_PER_SCOPE = 200
MIN_SAMPLE_LEAGUE = 30
MIN_SAMPLE_COUNTRY = 40
MIN_SAMPLE_GLOBAL = 50

_BASELINE_CACHE: dict[str, dict[str, Any]] = {}
_OVER_BASELINE_CACHE: dict[str, dict[str, Any]] = {}


def clear_goal_intensity_baseline_cache() -> None:
    """Svuota cache in-process (utile per test)."""
    _BASELINE_CACHE.clear()
    _OVER_BASELINE_CACHE.clear()


def _q44_from_blocks(blocks: dict[str, Any] | None) -> float | None:
    if not blocks:
        return None
    ha = blocks.get("home_away") or {}
    tot = blocks.get("totals") or {}
    if ha.get("block_value") is None or tot.get("block_value") is None:
        return None
    return round(float(ha["block_value"]) + float(tot["block_value"]), 2)


def compute_raw_over_q44_for_fixture(db: Session, fixture: Fixture) -> float | None:
    """OVER Q44 grezzo per una fixture, se calcolabile."""
    slices = build_goal_fixture_slices(db, fixture)
    over_ft = calculate_over_fulltime_excel_parity(slices)
    if over_ft.get("status") == STATUS_INSUFFICIENT_DATA:
        return None
    raw_over = _q44_from_blocks(over_ft.get("blocks"))
    if raw_over is None or raw_over <= 0:
        return None
    return raw_over


def compute_raw_q44_pair_for_fixture(
    db: Session,
    fixture: Fixture,
) -> tuple[float, float] | None:
    """Coppia (OVER Q44, UNDER Q44) grezza per una fixture, se calcolabile."""
    slices = build_goal_fixture_slices(db, fixture)
    over_ft = calculate_over_fulltime_excel_parity(slices)
    under_ft = calculate_under_fulltime_excel_parity(slices)
    if over_ft.get("status") == STATUS_INSUFFICIENT_DATA or under_ft.get("status") == STATUS_INSUFFICIENT_DATA:
        return None
    raw_off = _q44_from_blocks(over_ft.get("blocks"))
    raw_def = _q44_from_blocks(under_ft.get("blocks"))
    if raw_off is None or raw_def is None or raw_off <= 0 or raw_def <= 0:
        return None
    return raw_off, raw_def


def _collect_over_values(db: Session, fixtures: list[Fixture]) -> list[float]:
    capped = fixtures[-MAX_FIXTURES_PER_SCOPE:] if len(fixtures) > MAX_FIXTURES_PER_SCOPE else fixtures
    values: list[float] = []
    for fx in capped:
        raw_over = compute_raw_over_q44_for_fixture(db, fx)
        if raw_over is not None:
            values.append(raw_over)
    return values


def _collect_pairs(
    db: Session,
    fixtures: list[Fixture],
) -> list[tuple[float, float]]:
    capped = fixtures[-MAX_FIXTURES_PER_SCOPE:] if len(fixtures) > MAX_FIXTURES_PER_SCOPE else fixtures
    pairs: list[tuple[float, float]] = []
    for fx in capped:
        pair = compute_raw_q44_pair_for_fixture(db, fx)
        if pair is not None:
            pairs.append(pair)
    return pairs


def _percentile_at(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return round(sorted_vals[f], 2)
    return round(sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f]), 2)


def percentile_rank_percent(values: list[float], current: float) -> float:
    """
    Percentile rank (proportion_leq): % valori storici <= current.
    Es. [1,2,3,4,5], current=4 → 80.0
    """
    if not values:
        return 50.0
    return round(100.0 * sum(1 for v in values if v <= current) / len(values), 1)


def _over_distribution(over_values: list[float]) -> dict[str, float | None]:
    sorted_vals = sorted(over_values)
    return {
        "median_over_q44": _percentile_at(sorted_vals, 0.50),
        "p20_over_q44": _percentile_at(sorted_vals, 0.20),
        "p40_over_q44": _percentile_at(sorted_vals, 0.40),
        "p60_over_q44": _percentile_at(sorted_vals, 0.60),
        "p80_over_q44": _percentile_at(sorted_vals, 0.80),
    }


def _empty_over_baseline() -> dict[str, Any]:
    return {
        "source": None,
        "sample_size": 0,
        "median_over_q44": None,
        "p20_over_q44": None,
        "p40_over_q44": None,
        "p60_over_q44": None,
        "p80_over_q44": None,
        "method": "percentile_distribution",
        "over_values": [],
    }


def _over_baseline_result(*, source: str, over_values: list[float]) -> dict[str, Any]:
    dist = _over_distribution(over_values)
    return {
        "source": source,
        "sample_size": len(over_values),
        "method": "percentile_distribution",
        "over_values": over_values,
        **dist,
    }


def _median_baselines(pairs: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    if not pairs:
        return None, None
    overs = [p[0] for p in pairs]
    unders = [p[1] for p in pairs]
    return round(statistics.median(overs), 2), round(statistics.median(unders), 2)


def _empty_baseline() -> dict[str, Any]:
    return {
        "source": None,
        "sample_size": 0,
        "baseline_over_q44": None,
        "baseline_under_q44": None,
        "method": "median",
    }


def _baseline_result(
    *,
    source: str,
    pairs: list[tuple[float, float]],
) -> dict[str, Any]:
    med_over, med_under = _median_baselines(pairs)
    return {
        "source": source,
        "sample_size": len(pairs),
        "baseline_over_q44": med_over,
        "baseline_under_q44": med_under,
        "method": "median",
    }


def _load_country_finished_fixtures_before(
    db: Session,
    target_fixture: Fixture,
    country_name: str | None,
) -> list[Fixture]:
    if not country_name or not country_name.strip():
        return []
    cutoff_ko = target_fixture.kickoff_at
    cutoff_id = int(target_fixture.id)
    if cutoff_ko is None:
        return []

    rows = db.scalars(
        select(Fixture)
        .join(Competition, Fixture.competition_id == Competition.id)
        .where(
            Competition.country == country_name.strip(),
            Fixture.status.in_(FINISHED_STATUSES),
        )
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
    ).all()
    return [
        f
        for f in rows
        if f.kickoff_at is not None
        and fixture_key_before(f.kickoff_at, int(f.id), cutoff_ko, cutoff_id)
        and f.goals_home is not None
        and f.goals_away is not None
    ]


def _load_global_finished_fixtures_before(
    db: Session,
    target_fixture: Fixture,
) -> list[Fixture]:
    cutoff_ko = target_fixture.kickoff_at
    cutoff_id = int(target_fixture.id)
    if cutoff_ko is None:
        return []

    rows = db.scalars(
        select(Fixture)
        .where(Fixture.status.in_(FINISHED_STATUSES))
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc()),
    ).all()
    return [
        f
        for f in rows
        if f.kickoff_at is not None
        and fixture_key_before(f.kickoff_at, int(f.id), cutoff_ko, cutoff_id)
        and f.goals_home is not None
        and f.goals_away is not None
    ]


def _try_scope_over_baseline(
    db: Session,
    fixtures: list[Fixture],
    *,
    source: str,
    min_sample: int,
) -> dict[str, Any] | None:
    over_values = _collect_over_values(db, fixtures)
    if len(over_values) < min_sample:
        return None
    median = _over_distribution(over_values).get("median_over_q44")
    if median is None or median <= 0:
        return None
    return _over_baseline_result(source=source, over_values=over_values)


def _try_scope_baseline(
    db: Session,
    fixtures: list[Fixture],
    *,
    source: str,
    min_sample: int,
) -> dict[str, Any] | None:
    pairs = _collect_pairs(db, fixtures)
    if len(pairs) < min_sample:
        return None
    med_over, med_under = _median_baselines(pairs)
    if med_over is None or med_under is None or med_over <= 0 or med_under <= 0:
        return None
    return _baseline_result(source=source, pairs=pairs)


def get_goal_intensity_over_baseline(
    db: Session,
    target_fixture: Fixture,
    *,
    competition_id: int | None = None,
    country_name: str | None = None,
) -> dict[str, Any]:
    """
    Distribuzione storica OVER Q44 con fallback league → country → global.
    Cache in-process per (competition_id, country_name, target_fixture.id).
    """
    comp_id = competition_id if competition_id is not None else target_fixture.competition_id
    cache_key = f"gi_over_baseline:{comp_id}:{country_name}:{target_fixture.id}"
    if cache_key in _OVER_BASELINE_CACHE:
        return _OVER_BASELINE_CACHE[cache_key]

    league_fixtures = load_league_finished_fixtures_before(db, target_fixture)
    result = _try_scope_over_baseline(
        db,
        league_fixtures,
        source="league",
        min_sample=MIN_SAMPLE_LEAGUE,
    )
    if result is not None:
        _OVER_BASELINE_CACHE[cache_key] = result
        return result

    country_fixtures = _load_country_finished_fixtures_before(
        db,
        target_fixture,
        country_name,
    )
    result = _try_scope_over_baseline(
        db,
        country_fixtures,
        source="country",
        min_sample=MIN_SAMPLE_COUNTRY,
    )
    if result is not None:
        _OVER_BASELINE_CACHE[cache_key] = result
        return result

    global_fixtures = _load_global_finished_fixtures_before(db, target_fixture)
    result = _try_scope_over_baseline(
        db,
        global_fixtures,
        source="global",
        min_sample=MIN_SAMPLE_GLOBAL,
    )
    if result is not None:
        _OVER_BASELINE_CACHE[cache_key] = result
        return result

    empty = _empty_over_baseline()
    _OVER_BASELINE_CACHE[cache_key] = empty
    return empty


def get_goal_intensity_baselines(
    db: Session,
    target_fixture: Fixture,
    *,
    competition_id: int | None = None,
    country_name: str | None = None,
) -> dict[str, Any]:
    """Baseline mediana v2 (legacy) — fallback league → country → global."""
    comp_id = competition_id if competition_id is not None else target_fixture.competition_id
    cache_key = f"gi_baseline:{comp_id}:{country_name}:{target_fixture.id}"
    if cache_key in _BASELINE_CACHE:
        return _BASELINE_CACHE[cache_key]

    league_fixtures = load_league_finished_fixtures_before(db, target_fixture)
    result = _try_scope_baseline(
        db,
        league_fixtures,
        source="league",
        min_sample=MIN_SAMPLE_LEAGUE,
    )
    if result is not None:
        _BASELINE_CACHE[cache_key] = result
        return result

    country_fixtures = _load_country_finished_fixtures_before(
        db,
        target_fixture,
        country_name,
    )
    result = _try_scope_baseline(
        db,
        country_fixtures,
        source="country",
        min_sample=MIN_SAMPLE_COUNTRY,
    )
    if result is not None:
        _BASELINE_CACHE[cache_key] = result
        return result

    global_fixtures = _load_global_finished_fixtures_before(db, target_fixture)
    result = _try_scope_baseline(
        db,
        global_fixtures,
        source="global",
        min_sample=MIN_SAMPLE_GLOBAL,
    )
    if result is not None:
        _BASELINE_CACHE[cache_key] = result
        return result

    empty = _empty_baseline()
    _BASELINE_CACHE[cache_key] = empty
    return empty
