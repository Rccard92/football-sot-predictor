"""Helper read-only audit Intensità Goal v5 — Fase 1A.2."""

from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.team import Team
from app.services.cecchino.cecchino_current_season_xg import (
    PROFILE_VERSION,
    build_current_season_team_xg_profile,
)
from app.services.cecchino.cecchino_fixture_history import load_finished_fixtures_for_team, take_last_n
from app.services.cecchino.cecchino_goal_intensity_analysis import METHOD as V4_METHOD
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.datetime_utils import ensure_datetime_utc

PILLAR_OFFENSIVE = "offensive_production"
PILLAR_DEFENSIVE = "defensive_solidity"
PILLAR_TEMPO = "match_tempo"
PILLAR_STABILITY = "offensive_stability"

PILLARS = (PILLAR_OFFENSIVE, PILLAR_DEFENSIVE, PILLAR_TEMPO, PILLAR_STABILITY)

_MAX_DEBUG_SAMPLES = 20


def pct(n: int | float, d: int | float) -> float:
    if d <= 0:
        return 0.0
    return round(100.0 * float(n) / float(d), 2)


def num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def descriptive_stats(values: list[float]) -> dict[str, Any]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "p10": None,
            "p25": None,
            "p75": None,
            "p90": None,
            "zero_rate": None,
            "outlier_rate": None,
            "valid_numeric_rows": 0,
        }
    sorted_vals = sorted(clean)
    mean = statistics.fmean(clean)
    std = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    q1 = percentile(sorted_vals, 25) or 0.0
    q3 = percentile(sorted_vals, 75) or 0.0
    iqr = q3 - q1
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    outliers = sum(1 for v in clean if v < lo or v > hi)
    zeros = sum(1 for v in clean if v == 0.0)
    return {
        "min": round(sorted_vals[0], 6),
        "max": round(sorted_vals[-1], 6),
        "mean": round(mean, 6),
        "median": round(statistics.median(clean), 6),
        "standard_deviation": round(std, 6),
        "p10": round(percentile(sorted_vals, 10) or 0.0, 6),
        "p25": round(q1, 6),
        "p75": round(q3, 6),
        "p90": round(percentile(sorted_vals, 90) or 0.0, 6),
        "zero_rate": pct(zeros, len(clean)),
        "outlier_rate": pct(outliers, len(clean)),
        "valid_numeric_rows": len(clean),
    }


def mad(values: list[float]) -> float | None:
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median([abs(v - med) for v in values])


def cv(values: list[float]) -> float | None:
    if not values:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values) / abs(mean)


def month_key_from_dt(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    u = ensure_datetime_utc(dt, field_name="month") or dt
    return f"{u.year:04d}-{u.month:02d}"


def months_in_range(date_from: date, date_to: date) -> list[str]:
    out: list[str] = []
    y, m = date_from.year, date_from.month
    end = (date_to.year, date_to.month)
    while (y, m) <= end:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def sanitize_exception_message(exc: BaseException, *, limit: int = 200) -> str:
    msg = str(exc).replace("\n", " ").strip()
    if len(msg) > limit:
        return msg[: limit - 3] + "..."
    return msg


def finished_local_fixtures_in_kickoff_range(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> list[Fixture]:
    start = datetime(date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc)
    end_exclusive = datetime(date_to.year, date_to.month, date_to.day, tzinfo=timezone.utc) + timedelta(days=1)
    clauses = [
        Fixture.kickoff_at >= start,
        Fixture.kickoff_at < end_exclusive,
        Fixture.status.in_(tuple(FINISHED_STATUSES)),
        Fixture.goals_home.is_not(None),
        Fixture.goals_away.is_not(None),
        Fixture.home_team_id.is_not(None),
        Fixture.away_team_id.is_not(None),
    ]
    if competition_id is not None:
        clauses.append(Fixture.competition_id == competition_id)
    return list(db.scalars(select(Fixture).where(*clauses).order_by(Fixture.kickoff_at.asc())).all())


def dedupe_local_fixtures(fixtures: list[Fixture]) -> tuple[list[Fixture], int]:
    """Dedup api_fixture_id, fallback Fixture.id. Returns (deduped, duplicates_removed)."""
    seen_api: set[int] = set()
    seen_id: set[int] = set()
    out: list[Fixture] = []
    removed = 0
    for fx in fixtures:
        api = getattr(fx, "api_fixture_id", None)
        fid = int(fx.id)
        if api is not None:
            api_i = int(api)
            if api_i in seen_api:
                removed += 1
                continue
            seen_api.add(api_i)
            seen_id.add(fid)
            out.append(fx)
            continue
        if fid in seen_id:
            removed += 1
            continue
        seen_id.add(fid)
        out.append(fx)
    return out, removed


def load_today_snapshots_for_fixtures(
    db: Session,
    fixtures: list[Fixture],
) -> list[CecchinoTodayFixture]:
    if not fixtures:
        return []
    local_ids = [int(fx.id) for fx in fixtures]
    api_ids = [int(fx.api_fixture_id) for fx in fixtures if fx.api_fixture_id is not None]
    clauses = [CecchinoTodayFixture.local_fixture_id.in_(local_ids)]
    if api_ids:
        clauses.append(CecchinoTodayFixture.provider_fixture_id.in_(api_ids))
    return list(db.scalars(select(CecchinoTodayFixture).where(or_(*clauses))).all())


def _snapshot_pre_kickoff_score(row: CecchinoTodayFixture, target_ko: datetime) -> datetime | None:
    """Timestamp usato per scegliere lo snapshot più recente ma ≤ kickoff."""
    candidates: list[datetime] = []
    for attr in ("kickoff", "created_at", "updated_at"):
        raw = getattr(row, attr, None)
        dt = ensure_datetime_utc(raw, field_name=attr) if isinstance(raw, datetime) else None
        if dt is None and attr == "kickoff" and raw is not None:
            dt = parse_iso(raw)
        if dt is not None and dt <= target_ko:
            candidates.append(dt)
    scan = getattr(row, "scan_date", None)
    if isinstance(scan, date):
        scan_dt = datetime(scan.year, scan.month, scan.day, tzinfo=timezone.utc)
        if scan_dt <= target_ko:
            candidates.append(scan_dt)
    if not candidates:
        return None
    return max(candidates)


def match_today_snapshot(
    target: Fixture,
    candidates: list[CecchinoTodayFixture],
) -> CecchinoTodayFixture | None:
    target_ko = ensure_datetime_utc(target.kickoff_at, field_name="target.kickoff_at")
    if target_ko is None:
        return None
    tid = int(target.id)
    tapi = int(target.api_fixture_id) if target.api_fixture_id is not None else None

    by_local = [r for r in candidates if getattr(r, "local_fixture_id", None) is not None and int(r.local_fixture_id) == tid]
    by_provider = [
        r
        for r in candidates
        if tapi is not None and getattr(r, "provider_fixture_id", None) is not None and int(r.provider_fixture_id) == tapi
    ]
    pool = by_local or by_provider
    if not pool:
        return None

    scored: list[tuple[datetime, CecchinoTodayFixture]] = []
    for row in pool:
        score = _snapshot_pre_kickoff_score(row, target_ko)
        if score is not None:
            scored.append((score, row))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def goals_scored_conceded(fx: Fixture, team_id: int) -> tuple[int | None, int | None]:
    if fx.goals_home is None or fx.goals_away is None:
        return None, None
    tid = int(team_id)
    if int(fx.home_team_id) == tid:
        return int(fx.goals_home), int(fx.goals_away)
    if int(fx.away_team_id) == tid:
        return int(fx.goals_away), int(fx.goals_home)
    return None, None


def _avg(vals: list[float]) -> float | None:
    if not vals:
        return None
    return round(statistics.fmean(vals), 6)


def _freq(hits: int, sample: int) -> float | None:
    if sample <= 0:
        return None
    return round(hits / sample, 6)


def team_goal_series(priors: list[Fixture], team_id: int) -> list[float]:
    out: list[float] = []
    for fx in priors:
        scored, _ = goals_scored_conceded(fx, team_id)
        if scored is not None:
            out.append(float(scored))
    return out


def team_conceded_series(priors: list[Fixture], team_id: int) -> list[float]:
    out: list[float] = []
    for fx in priors:
        _, conc = goals_scored_conceded(fx, team_id)
        if conc is not None:
            out.append(float(conc))
    return out


def combined_total_goals(fixtures: list[Fixture]) -> list[float]:
    out: list[float] = []
    for fx in fixtures:
        if fx.goals_home is None or fx.goals_away is None:
            continue
        out.append(float(int(fx.goals_home) + int(fx.goals_away)))
    return out


def parse_xg_profiles(row: CecchinoTodayFixture | None) -> dict[str, Any]:
    if row is None:
        return {}
    raw = getattr(row, "xg_profiles_json", None)
    return raw if isinstance(raw, dict) else {}


def profile_team_avg(profiles: dict[str, Any], side: str, field: str) -> float | None:
    for key in (side, f"{side}_profile", f"{side}_team"):
        block = profiles.get(key)
        if isinstance(block, dict):
            val = num(block.get(field))
            if val is not None:
                return val
    return None


def xg_cutoff_iso(profiles: dict[str, Any]) -> str | None:
    anti = profiles.get("anti_leakage")
    if isinstance(anti, dict) and anti.get("fixture_date_cutoff"):
        return str(anti["fixture_date_cutoff"])
    for side in ("home", "away", "home_profile", "away_profile", "home_team", "away_team"):
        block = profiles.get(side)
        if isinstance(block, dict):
            a = block.get("anti_leakage")
            if isinstance(a, dict) and a.get("fixture_date_cutoff"):
                return str(a["fixture_date_cutoff"])
    return None


def kickoffs_within_one_minute(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return False
    a_u = ensure_datetime_utc(a, field_name="a")
    b_u = ensure_datetime_utc(b, field_name="b")
    if a_u is None or b_u is None:
        return False
    return abs((a_u - b_u).total_seconds()) <= 60


def parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_datetime_utc(value, field_name="iso")
    try:
        s = str(value).replace("Z", "+00:00")
        return ensure_datetime_utc(datetime.fromisoformat(s), field_name="iso")
    except ValueError:
        return None


FEATURE_SPECS: list[dict[str, Any]] = [
    {"feature_key": "home_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For casa (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For trasferta (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "pair_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For casa+ospite", "source_table_or_payload": "derived", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_scored_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa (stagione prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_scored_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati trasferta (stagione prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "home_goals_scored_rolling_5", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_goals_scored_rolling_5", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati ospite last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_scored_rolling_10", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_scored_rolling_10", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati ospite last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "home_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against casa (pre-match)", "source_table_or_payload": "xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against trasferta (pre-match)", "source_table_or_payload": "xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "pair_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against casa+ospite", "source_table_or_payload": "derived", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_conceded_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media goal subiti casa", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_conceded", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_conceded_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media goal subiti trasferta", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_conceded", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "home_clean_sheet_freq", "pillar": PILLAR_DEFENSIVE, "description": "Frequenza clean sheet casa (prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "clean_sheet", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_clean_sheet_freq", "pillar": PILLAR_DEFENSIVE, "description": "Frequenza clean sheet trasferta (prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "clean_sheet", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "over_2_5_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza Over 2.5 last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "over_frequency", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "gg_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza GG/BTTS last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "gg_frequency", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "total_goals_avg", "pillar": PILLAR_TEMPO, "description": "Media goal totali prior combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "total_goals_rolling_5", "pillar": PILLAR_TEMPO, "description": "Media goal totali last 5 combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "total_goals_rolling_10", "pillar": PILLAR_TEMPO, "description": "Media goal totali last 10 combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_ge_2_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza partite ≥2 goal last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals_threshold", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_ge_3_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza partite ≥3 goal last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals_threshold", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "pair_goals_scored_rolling_5", "pillar": PILLAR_STABILITY, "description": "Media goal segnati pair last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_level", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "pair_goals_scored_rolling_10", "pillar": PILLAR_STABILITY, "description": "Media goal segnati pair last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_level", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_scored_std_last_10", "pillar": PILLAR_STABILITY, "description": "Deviazione standard goal segnati last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_scored_mad_last_10", "pillar": PILLAR_STABILITY, "description": "MAD goal segnati last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_scored_cv_last_10", "pillar": PILLAR_STABILITY, "description": "CV goal segnati last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_rolling_5_vs_10_delta", "pillar": PILLAR_STABILITY, "description": "Differenza media rolling 5 vs 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_shift", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
]

EXCLUDED_ADVANCED: list[dict[str, Any]] = [
    {"feature_key": "first_half_xg", "description": "First Half xG", "source": "EGE advanced", "coverage_note": "copertura irregolare", "exclusion_reason": "non nel cuore v5", "recommended_status": "optional_corrector", "future_use": "correttore opzionale"},
    {"feature_key": "ppda", "description": "PPDA", "source": "EGE advanced", "coverage_note": "spesso non popolato", "exclusion_reason": "copertura irregolare", "recommended_status": "unavailable", "future_use": "correttore se stabile"},
    {"feature_key": "field_tilt", "description": "Field Tilt", "source": "EGE advanced", "coverage_note": "spesso non popolato", "exclusion_reason": "copertura irregolare", "recommended_status": "unavailable", "future_use": "correttore se stabile"},
    {"feature_key": "xthreat", "description": "xThreat", "source": "EGE advanced", "coverage_note": "spesso non popolato", "exclusion_reason": "copertura irregolare", "recommended_status": "unavailable", "future_use": "correttore se stabile"},
    {"feature_key": "big_chances_created", "description": "Big Chances Created", "source": "EGE advanced", "coverage_note": "spesso non popolato", "exclusion_reason": "copertura irregolare", "recommended_status": "unavailable", "future_use": "correttore se stabile"},
    {"feature_key": "big_chances_conceded", "description": "Big Chances Conceded", "source": "EGE advanced", "coverage_note": "spesso non popolato", "exclusion_reason": "copertura irregolare", "recommended_status": "unavailable", "future_use": "correttore se stabile"},
]


def current_v4_inventory() -> dict[str, Any]:
    return {
        "role": "legacy_reference",
        "version": V4_VERSION,
        "method": V4_METHOD,
        "primary_quantity": "expected_goals_total",
        "classification_thresholds": [0.5, 1.5, 2.5, 3.5],
        "labels": ["Molto Difensiva", "Difensiva", "Equilibrata", "Offensiva", "Molto Offensiva"],
        "over_threshold_keys": ["over_0_5", "over_1_5", "over_2_5", "over_3_5"],
        "depends_on": [
            "internal_cecchino_goal_engine",
            "goal_markets.summary.lambda",
            "cecchino_goal_poisson_v2.weighted_lambda",
            "cecchino_fixture_history.build_goal_market_contexts",
        ],
        "baselines_q44": {"module": "cecchino_goal_intensity_baselines", "status": "orphan_legacy_not_wired_to_v4"},
        "frontend": "CecchinoGoalIntensityAnalysisPanel",
        "persistence": "payload_only_on_today_detail",
        "conflicts_with_v5": [
            "singola grandezza invece di quattro pilastri",
            "traduzione diretta in soglie Over",
            "soglie fisse non calibrate storicamente",
            "non separa produzione/difesa/ritmo/stabilità",
        ],
        "production_unchanged": True,
    }


def empty_pillar_coverage() -> dict[str, Any]:
    return {
        "fixtures_total": 0,
        "fixtures_with_any_feature": 0,
        "fixtures_with_all_primary": 0,
        "coverage_complete_pct": 0.0,
        "coverage_partial_pct": 0.0,
        "coverage_none_pct": 0.0,
        "competitions": 0,
        "countries": 0,
        "temporal_distribution": {},
        "sample_size_mean": None,
        "sample_size_min": None,
        "warnings": [],
    }


def primary_keys_for_pillar(pillar: str) -> list[str]:
    return [
        s["feature_key"]
        for s in FEATURE_SPECS
        if s["pillar"] == pillar and s["recommended_status"] == "primary_candidate"
    ]


def resolve_team_names(db: Session, local: Fixture) -> tuple[str | None, str | None]:
    home_name = None
    away_name = None
    if local.home_team_id is not None:
        ht = db.get(Team, int(local.home_team_id))
        home_name = ht.name if ht else None
    if local.away_team_id is not None:
        at = db.get(Team, int(local.away_team_id))
        away_name = at.name if at else None
    return home_name, away_name


def resolve_country(db: Session, competition_id: int | None) -> str | None:
    if competition_id is None:
        return None
    comp = db.get(Competition, int(competition_id))
    if comp is None:
        return None
    return str(comp.country) if comp.country else None


def extract_features_for_local_fixture(
    db: Session,
    target: Fixture,
    today_row: CecchinoTodayFixture | None,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    """Feature pre-match da Fixture prior (+ xG snapshot/team_stats). Non richiede Today per i goal."""
    features: dict[str, float | None] = {spec["feature_key"]: None for spec in FEATURE_SPECS}
    meta: dict[str, Any] = {
        "current_fixture_included": False,
        "future_fixture_included": False,
        "cutoff_mismatch": False,
        "max_source_kickoff": None,
        "source_fixture_ids": [],
        "xg_source": "missing",
        "sample_size": 0,
    }

    target_ko = ensure_datetime_utc(target.kickoff_at, field_name="target.kickoff_at")
    hid = int(target.home_team_id)
    aid = int(target.away_team_id)
    target_id = int(target.id)
    target_api = int(target.api_fixture_id) if target.api_fixture_id is not None else None

    # --- xG: snapshot Today first ---
    profiles = parse_xg_profiles(today_row)
    home_xg_for = profile_team_avg(profiles, "home", "xg_for_avg")
    away_xg_for = profile_team_avg(profiles, "away", "xg_for_avg")
    home_xg_against = profile_team_avg(profiles, "home", "xg_against_avg")
    away_xg_against = profile_team_avg(profiles, "away", "xg_against_avg")
    cutoff = parse_iso(xg_cutoff_iso(profiles))
    if profiles and cutoff is not None and target_ko is not None and not kickoffs_within_one_minute(cutoff, target_ko):
        meta["cutoff_mismatch"] = True
        meta["xg_source"] = "snapshot_cutoff_mismatch"
        home_xg_for = away_xg_for = home_xg_against = away_xg_against = None
    elif any(v is not None for v in (home_xg_for, away_xg_for, home_xg_against, away_xg_against)):
        meta["xg_source"] = "today_snapshot"

    if meta["xg_source"] in ("missing", "snapshot_cutoff_mismatch") and not meta["cutoff_mismatch"]:
        # Fallback FixtureTeamStat via profile builder (DB-only, no API)
        try:
            home_prof = build_current_season_team_xg_profile(
                db, target, hid, exclude_provider_fixture_id=target_api
            )
            away_prof = build_current_season_team_xg_profile(
                db, target, aid, exclude_provider_fixture_id=target_api
            )
            home_xg_for = num(home_prof.get("xg_for_avg"))
            home_xg_against = num(home_prof.get("xg_against_avg"))
            away_xg_for = num(away_prof.get("xg_for_avg"))
            away_xg_against = num(away_prof.get("xg_against_avg"))
            if any(v is not None for v in (home_xg_for, away_xg_for, home_xg_against, away_xg_against)):
                meta["xg_source"] = "fixture_team_stats"
        except Exception:
            pass

    features["home_xg_for_avg"] = home_xg_for
    features["away_xg_for_avg"] = away_xg_for
    features["home_xg_against_avg"] = home_xg_against
    features["away_xg_against_avg"] = away_xg_against
    if home_xg_for is not None and away_xg_for is not None:
        features["pair_xg_for_avg"] = round((home_xg_for + away_xg_for) / 2.0, 6)
    if home_xg_against is not None and away_xg_against is not None:
        features["pair_xg_against_avg"] = round((home_xg_against + away_xg_against) / 2.0, 6)

    home_prior_raw = list(load_finished_fixtures_for_team(db, target, hid))
    away_prior_raw = list(load_finished_fixtures_for_team(db, target, aid))

    def _sanitize(priors: list[Fixture]) -> list[Fixture]:
        clean: list[Fixture] = []
        for fx in priors:
            fid = int(fx.id)
            if fid == target_id:
                meta["current_fixture_included"] = True
                continue
            if target_api is not None and int(getattr(fx, "api_fixture_id", -1) or -1) == target_api:
                meta["current_fixture_included"] = True
                continue
            fx_ko = ensure_datetime_utc(fx.kickoff_at, field_name=f"prior_{fid}")
            if target_ko is not None and fx_ko is not None and fx_ko >= target_ko:
                meta["future_fixture_included"] = True
                continue
            clean.append(fx)
            if fx_ko is not None:
                prev = meta["max_source_kickoff"]
                if prev is None or fx_ko.isoformat() > str(prev):
                    meta["max_source_kickoff"] = fx_ko.isoformat()
            meta["source_fixture_ids"].append(fid)
        return clean

    home_prior = _sanitize(home_prior_raw)
    away_prior = _sanitize(away_prior_raw)
    meta["sample_size"] = len(set(meta["source_fixture_ids"]))

    home_scored = team_goal_series(home_prior, hid)
    away_scored = team_goal_series(away_prior, aid)
    home_conc = team_conceded_series(home_prior, hid)
    away_conc = team_conceded_series(away_prior, aid)

    features["home_goals_scored_avg"] = _avg(home_scored)
    features["away_goals_scored_avg"] = _avg(away_scored)
    features["home_goals_conceded_avg"] = _avg(home_conc)
    features["away_goals_conceded_avg"] = _avg(away_conc)
    features["home_goals_scored_rolling_5"] = _avg(home_scored[-5:]) if home_scored else None
    features["away_goals_scored_rolling_5"] = _avg(away_scored[-5:]) if away_scored else None
    features["home_goals_scored_rolling_10"] = _avg(home_scored[-10:]) if home_scored else None
    features["away_goals_scored_rolling_10"] = _avg(away_scored[-10:]) if away_scored else None
    features["home_clean_sheet_freq"] = _freq(sum(1 for v in home_conc if v == 0.0), len(home_conc))
    features["away_clean_sheet_freq"] = _freq(sum(1 for v in away_conc if v == 0.0), len(away_conc))

    combined_ids: dict[int, Fixture] = {}
    for fx in home_prior + away_prior:
        combined_ids[int(fx.id)] = fx
    combined = sorted(
        combined_ids.values(),
        key=lambda f: (
            ensure_datetime_utc(f.kickoff_at, field_name="sort") or datetime.min.replace(tzinfo=timezone.utc),
            int(f.id),
        ),
    )
    last10 = take_last_n(combined, 10)
    last5 = take_last_n(combined, 5)
    totals10 = combined_total_goals(last10)
    totals5 = combined_total_goals(last5)
    totals_all = combined_total_goals(combined)

    features["total_goals_avg"] = _avg(totals_all)
    features["total_goals_rolling_5"] = _avg(totals5)
    features["total_goals_rolling_10"] = _avg(totals10)
    features["over_2_5_frequency_last_10"] = _freq(sum(1 for t in totals10 if t > 2.5), len(totals10))
    features["goals_ge_2_frequency_last_10"] = _freq(sum(1 for t in totals10 if t >= 2), len(totals10))
    features["goals_ge_3_frequency_last_10"] = _freq(sum(1 for t in totals10 if t >= 3), len(totals10))

    gg_hits = 0
    gg_sample = 0
    for fx in last10:
        if fx.goals_home is None or fx.goals_away is None:
            continue
        gg_sample += 1
        if int(fx.goals_home) > 0 and int(fx.goals_away) > 0:
            gg_hits += 1
    features["gg_frequency_last_10"] = _freq(gg_hits, gg_sample)

    pair_scored_10 = (home_scored[-10:] if home_scored else []) + (away_scored[-10:] if away_scored else [])
    pair_scored_5 = (home_scored[-5:] if home_scored else []) + (away_scored[-5:] if away_scored else [])
    features["pair_goals_scored_rolling_5"] = _avg(pair_scored_5)
    features["pair_goals_scored_rolling_10"] = _avg(pair_scored_10)
    if len(pair_scored_10) >= 2:
        features["goals_scored_std_last_10"] = round(statistics.pstdev(pair_scored_10), 6)
        m = mad(pair_scored_10)
        features["goals_scored_mad_last_10"] = round(m, 6) if m is not None else None
        c = cv(pair_scored_10)
        features["goals_scored_cv_last_10"] = round(c, 6) if c is not None else None
    r5 = features["pair_goals_scored_rolling_5"]
    r10 = features["pair_goals_scored_rolling_10"]
    if r5 is not None and r10 is not None:
        features["goals_rolling_5_vs_10_delta"] = round(r5 - r10, 6)

    return features, meta


def append_debug_sample(
    buckets: dict[str, list[dict[str, Any]]],
    reason: str,
    *,
    today_fixture_id: int | None,
    local_fixture_id: int | None,
    provider_fixture_id: int | None,
    kickoff: str | None,
    exception_type: str | None = None,
    exception_message: str | None = None,
) -> None:
    samples = buckets.setdefault(reason, [])
    if len(samples) >= _MAX_DEBUG_SAMPLES:
        return
    samples.append(
        {
            "today_fixture_id": today_fixture_id,
            "local_fixture_id": local_fixture_id,
            "provider_fixture_id": provider_fixture_id,
            "kickoff": kickoff,
            "reason": reason,
            "exception_type": exception_type,
            "exception_message": exception_message,
        }
    )
