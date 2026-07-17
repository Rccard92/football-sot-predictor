"""Helper read-only audit Intensità Goal v5 — Fase 1A."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import MATCH_FINISHED, CecchinoTodayFixture
from app.models.fixture import Fixture
from app.services.cecchino.cecchino_current_season_xg import PROFILE_VERSION
from app.services.cecchino.cecchino_fixture_history import load_finished_fixtures_for_team, take_last_n
from app.services.cecchino.cecchino_goal_intensity_analysis import METHOD as V4_METHOD
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.datetime_utils import ensure_datetime_utc

PILLAR_OFFENSIVE = "offensive_production"
PILLAR_DEFENSIVE = "defensive_solidity"
PILLAR_TEMPO = "match_tempo"
PILLAR_STABILITY = "offensive_stability"

PILLARS = (PILLAR_OFFENSIVE, PILLAR_DEFENSIVE, PILLAR_TEMPO, PILLAR_STABILITY)

FINISHED_LOCAL = frozenset({"FT", "AET", "PEN", "AWD", "WO"})


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


def dedupe_today_rows(rows: list[CecchinoTodayFixture]) -> list[CecchinoTodayFixture]:
    """Dedup provider_source+provider_fixture_id, fallback local_fixture_id."""
    seen_provider: set[tuple[str, int]] = set()
    seen_local: set[int] = set()
    out: list[CecchinoTodayFixture] = []
    for row in rows:
        ps = str(getattr(row, "provider_source", "") or "")
        pfid = getattr(row, "provider_fixture_id", None)
        lid = getattr(row, "local_fixture_id", None)
        if pfid is not None:
            key = (ps, int(pfid))
            if key in seen_provider:
                continue
            seen_provider.add(key)
            out.append(row)
            if lid is not None:
                seen_local.add(int(lid))
            continue
        if lid is not None:
            lid_i = int(lid)
            if lid_i in seen_local:
                continue
            seen_local.add(lid_i)
            out.append(row)
            continue
        out.append(row)
    return out


def is_finished_today(row: CecchinoTodayFixture) -> bool:
    status = str(getattr(row, "match_display_status", "") or "").strip().upper()
    return status == str(MATCH_FINISHED).strip().upper() or status in FINISHED_LOCAL


def resolve_ft_score(row: CecchinoTodayFixture, local: Fixture | None) -> tuple[int | None, int | None]:
    h = getattr(row, "score_fulltime_home", None)
    a = getattr(row, "score_fulltime_away", None)
    if h is None:
        h = getattr(row, "goals_home", None)
    if a is None:
        a = getattr(row, "goals_away", None)
    if h is None and local is not None:
        h = getattr(local, "goals_home", None)
    if a is None and local is not None:
        a = getattr(local, "goals_away", None)
    try:
        return (int(h) if h is not None else None, int(a) if a is not None else None)
    except (TypeError, ValueError):
        return None, None


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


def parse_xg_profiles(row: CecchinoTodayFixture) -> dict[str, Any]:
    raw = getattr(row, "xg_profiles_json", None)
    return raw if isinstance(raw, dict) else {}


def profile_team_avg(profiles: dict[str, Any], side: str, field: str) -> float | None:
    # Shapes: home / away, home_profile / away_profile, home_team / away_team
    candidates = (
        side,
        f"{side}_profile",
        f"{side}_team",
    )
    for key in candidates:
        block = profiles.get(key)
        if isinstance(block, dict):
            val = num(block.get(field))
            if val is not None:
                return val
    return None


def xg_cutoff_iso(profiles: dict[str, Any]) -> str | None:
    anti = profiles.get("anti_leakage")
    if isinstance(anti, dict):
        c = anti.get("fixture_date_cutoff")
        if c:
            return str(c)
    for side in ("home", "away", "home_profile", "away_profile"):
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
    # Offensive production
    {"feature_key": "home_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For casa (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For trasferta (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "pair_xg_for_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media xG For casa+ospite", "source_table_or_payload": "derived from xg_profiles_json", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_for", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_scored_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa (stagione prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_scored_avg", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati trasferta (stagione prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "home_goals_scored_rolling_5", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_goals_scored_rolling_5", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati ospite last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_scored_rolling_10", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati casa last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_scored_rolling_10", "pillar": PILLAR_OFFENSIVE, "description": "Media goal segnati ospite last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_scored_rolling", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    # Defensive
    {"feature_key": "home_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against casa (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "away_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against trasferta (pre-match)", "source_table_or_payload": "cecchino_today_fixtures.xg_profiles_json / FixtureTeamStat", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "pair_xg_against_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media xG Against casa+ospite", "source_table_or_payload": "derived from xg_profiles_json", "source_version": PROFILE_VERSION, "value_type": "float", "redundancy_family": "xg_against", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "home_goals_conceded_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media goal subiti casa", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_conceded", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_goals_conceded_avg", "pillar": PILLAR_DEFENSIVE, "description": "Media goal subiti trasferta", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "goals_conceded", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "home_clean_sheet_freq", "pillar": PILLAR_DEFENSIVE, "description": "Frequenza clean sheet casa (prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "clean_sheet", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "away_clean_sheet_freq", "pillar": PILLAR_DEFENSIVE, "description": "Frequenza clean sheet trasferta (prior)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "clean_sheet", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    # Tempo
    {"feature_key": "over_2_5_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza Over 2.5 last 10 (feature descrittiva)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "over_frequency", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "gg_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza GG/BTTS last 10 (feature descrittiva)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "gg_frequency", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "total_goals_avg", "pillar": PILLAR_TEMPO, "description": "Media goal totali prior combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "total_goals_rolling_5", "pillar": PILLAR_TEMPO, "description": "Media goal totali last 5 combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "total_goals_rolling_10", "pillar": PILLAR_TEMPO, "description": "Media goal totali last 10 combined", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_ge_2_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza partite ≥2 goal last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals_threshold", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_ge_3_frequency_last_10", "pillar": PILLAR_TEMPO, "description": "Frequenza partite ≥3 goal last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "total_goals_threshold", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    # Stability
    {"feature_key": "pair_goals_scored_rolling_5", "pillar": PILLAR_STABILITY, "description": "Media goal segnati pair last 5", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_level", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "pair_goals_scored_rolling_10", "pillar": PILLAR_STABILITY, "description": "Media goal segnati pair last 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_level", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
    {"feature_key": "goals_scored_std_last_10", "pillar": PILLAR_STABILITY, "description": "Deviazione standard goal segnati last 10 (candidato)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_scored_mad_last_10", "pillar": PILLAR_STABILITY, "description": "MAD goal segnati last 10 (candidato)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_scored_cv_last_10", "pillar": PILLAR_STABILITY, "description": "CV goal segnati last 10 (candidato)", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_dispersion", "pre_match_safe": True, "recommended_status": "primary_candidate"},
    {"feature_key": "goals_rolling_5_vs_10_delta", "pillar": PILLAR_STABILITY, "description": "Differenza media rolling 5 vs 10", "source_table_or_payload": "fixtures", "source_version": "fixture_history", "value_type": "float", "redundancy_family": "stability_shift", "pre_match_safe": True, "recommended_status": "secondary_candidate"},
]

EXCLUDED_ADVANCED: list[dict[str, Any]] = [
    {"feature_key": "first_half_xg", "description": "First Half xG", "source": "EGE advanced / raw statistics", "coverage_note": "copertura irregolare", "exclusion_reason": "copertura irregolare e non nel cuore v5", "recommended_status": "optional_corrector", "future_use": "correttore opzionale post-calibrazione"},
    {"feature_key": "ppda", "description": "PPDA", "source": "EGE advanced raw_patterns", "coverage_note": "spesso non popolato", "exclusion_reason": "metriche avanzate a copertura irregolare", "recommended_status": "unavailable", "future_use": "eventuale correttore se copertura stabile"},
    {"feature_key": "field_tilt", "description": "Field Tilt", "source": "EGE advanced raw_patterns", "coverage_note": "spesso non popolato", "exclusion_reason": "metriche avanzate a copertura irregolare", "recommended_status": "unavailable", "future_use": "eventuale correttore se copertura stabile"},
    {"feature_key": "xthreat", "description": "xThreat", "source": "EGE advanced raw_patterns", "coverage_note": "spesso non popolato", "exclusion_reason": "metriche avanzate a copertura irregolare", "recommended_status": "unavailable", "future_use": "eventuale correttore se copertura stabile"},
    {"feature_key": "big_chances_created", "description": "Big Chances Created", "source": "EGE advanced raw_patterns", "coverage_note": "spesso non popolato", "exclusion_reason": "metriche avanzate a copertura irregolare", "recommended_status": "unavailable", "future_use": "eventuale correttore se copertura stabile"},
    {"feature_key": "big_chances_conceded", "description": "Big Chances Conceded", "source": "EGE advanced raw_patterns", "coverage_note": "spesso non popolato", "exclusion_reason": "metriche avanzate a copertura irregolare", "recommended_status": "unavailable", "future_use": "eventuale correttore se copertura stabile"},
]


def current_v4_inventory() -> dict[str, Any]:
    return {
        "role": "legacy_reference",
        "version": V4_VERSION,
        "method": V4_METHOD,
        "primary_quantity": "expected_goals_total",
        "classification_thresholds": [0.5, 1.5, 2.5, 3.5],
        "labels": [
            "Molto Difensiva",
            "Difensiva",
            "Equilibrata",
            "Offensiva",
            "Molto Offensiva",
        ],
        "over_threshold_keys": ["over_0_5", "over_1_5", "over_2_5", "over_3_5"],
        "depends_on": [
            "internal_cecchino_goal_engine",
            "goal_markets.summary.lambda",
            "cecchino_goal_poisson_v2.weighted_lambda",
            "cecchino_fixture_history.build_goal_market_contexts",
        ],
        "baselines_q44": {
            "module": "cecchino_goal_intensity_baselines",
            "status": "orphan_legacy_not_wired_to_v4",
        },
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


def extract_row_features(
    db: Session,
    row: CecchinoTodayFixture,
    local: Fixture | None,
) -> tuple[dict[str, float | None], dict[str, Any], list[Fixture]]:
    """Estrae feature pre-match; restituisce features, meta anti-leakage, prior usati."""
    features: dict[str, float | None] = {spec["feature_key"]: None for spec in FEATURE_SPECS}
    meta: dict[str, Any] = {
        "current_fixture_included": False,
        "future_fixture_included": False,
        "cutoff_mismatch": False,
        "max_source_kickoff": None,
        "source_fixture_ids": [],
    }
    priors_used: list[Fixture] = []

    profiles = parse_xg_profiles(row)
    home_xg_for = profile_team_avg(profiles, "home", "xg_for_avg")
    away_xg_for = profile_team_avg(profiles, "away", "xg_for_avg")
    home_xg_against = profile_team_avg(profiles, "home", "xg_against_avg")
    away_xg_against = profile_team_avg(profiles, "away", "xg_against_avg")
    features["home_xg_for_avg"] = home_xg_for
    features["away_xg_for_avg"] = away_xg_for
    features["home_xg_against_avg"] = home_xg_against
    features["away_xg_against_avg"] = away_xg_against
    if home_xg_for is not None and away_xg_for is not None:
        features["pair_xg_for_avg"] = round((home_xg_for + away_xg_for) / 2.0, 6)
    if home_xg_against is not None and away_xg_against is not None:
        features["pair_xg_against_avg"] = round((home_xg_against + away_xg_against) / 2.0, 6)

    # cutoff xG vs kickoff
    cutoff = parse_iso(xg_cutoff_iso(profiles))
    target_ko = None
    if local is not None:
        target_ko = ensure_datetime_utc(local.kickoff_at, field_name="local.kickoff_at")
    if target_ko is None and getattr(row, "kickoff", None):
        target_ko = parse_iso(row.kickoff)
    if cutoff is not None and target_ko is not None and not kickoffs_within_one_minute(cutoff, target_ko):
        meta["cutoff_mismatch"] = True

    if local is None or local.home_team_id is None or local.away_team_id is None:
        return features, meta, priors_used

    hid = int(local.home_team_id)
    aid = int(local.away_team_id)
    target_id = int(local.id)
    target_api = int(local.api_fixture_id) if local.api_fixture_id is not None else None

    home_prior = list(load_finished_fixtures_for_team(db, local, hid))
    away_prior = list(load_finished_fixtures_for_team(db, local, aid))

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
            priors_used.append(fx)
            if fx_ko is not None:
                prev = meta["max_source_kickoff"]
                if prev is None or fx_ko.isoformat() > str(prev):
                    meta["max_source_kickoff"] = fx_ko.isoformat()
            meta["source_fixture_ids"].append(fid)
        return clean

    home_prior = _sanitize(home_prior)
    away_prior = _sanitize(away_prior)

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

    home_cs = sum(1 for v in home_conc if v == 0.0)
    away_cs = sum(1 for v in away_conc if v == 0.0)
    features["home_clean_sheet_freq"] = _freq(home_cs, len(home_conc))
    features["away_clean_sheet_freq"] = _freq(away_cs, len(away_conc))

    # Combined last 10 for tempo (union of last matches chronologically)
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

    o25_hits = sum(1 for t in totals10 if t > 2.5)
    ge2 = sum(1 for t in totals10 if t >= 2)
    ge3 = sum(1 for t in totals10 if t >= 3)
    features["over_2_5_frequency_last_10"] = _freq(o25_hits, len(totals10))
    features["goals_ge_2_frequency_last_10"] = _freq(ge2, len(totals10))
    features["goals_ge_3_frequency_last_10"] = _freq(ge3, len(totals10))

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

    return features, meta, priors_used


def month_key(d: date | None) -> str:
    if d is None:
        return "unknown"
    return f"{d.year:04d}-{d.month:02d}"


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
