"""Expected Goal Engine — diagnostica variabili v1 (Fase 50, audit only)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture, FixtureTeamStat
from app.services.cecchino.cecchino_current_season_xg import (
    ANTI_LEAKAGE_NOTE,
    MIN_XG_SAMPLE_AVAILABLE,
    SOURCE_FIELD_AGAINST,
    SOURCE_FIELD_FOR,
    SOURCE_NAME,
    build_current_season_team_xg_profile,
)
from app.services.cecchino.cecchino_fixture_history import (
    _take_last_n_with_halftime,
    aggregate_halftime_goal_totals,
    build_goal_fixture_slices,
    load_finished_fixtures_for_team,
    split_home_away,
    take_last_n,
)
from app.services.fixture_team_stats_mapping import statistics_list_to_fields

VERSION = "expected_goal_engine_diagnostics_v1"
STATUS_AVAILABLE = "available"

_BLOCK_PRODUCTION = "production_goal"
_BLOCK_TEMPORAL = "temporal_distribution"
_BLOCK_ADVANCED = "advanced_correctors"

_VARIABLE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": "home_xg_for",
        "label": "xG For Casa",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.17,
        "required": True,
        "role": "driver",
        "scope": "home_team",
        "period": "current_season_before_fixture",
        "description": "xG prodotti dalla squadra casa (media campionato corrente, pre-match).",
        "ideal_sample": 10,
    },
    {
        "key": "home_xg_against",
        "label": "xG Against Casa",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.15,
        "required": True,
        "role": "driver",
        "scope": "home_team",
        "period": "current_season_before_fixture",
        "description": "xG concessi dalla squadra casa (media campionato corrente, pre-match).",
        "ideal_sample": 10,
    },
    {
        "key": "away_xg_for",
        "label": "xG For Ospite",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.17,
        "required": True,
        "role": "driver",
        "scope": "away_team",
        "period": "current_season_before_fixture",
        "description": "xG prodotti dalla squadra ospite (media campionato corrente, pre-match).",
        "ideal_sample": 10,
    },
    {
        "key": "away_xg_against",
        "label": "xG Against Ospite",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "away_team",
        "period": "current_season_before_fixture",
        "description": "xG concessi dalla squadra ospite (media campionato corrente, pre-match).",
        "ideal_sample": 10,
    },
    {
        "key": "over_2_5_frequency_last_10",
        "label": "Frequenza Over 2.5 ultime 10",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "last_10",
        "description": "Frequenza Over 2.5 sulle ultime gare rilevanti.",
        "ideal_sample": 10,
    },
    {
        "key": "gg_frequency_last_10",
        "label": "Frequenza GG ultime 10",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "last_10",
        "description": "Frequenza entrambe a segno sulle ultime gare.",
        "ideal_sample": 10,
    },
    {
        "key": "rolling_avg_goals_last_5",
        "label": "Rolling Average Goal ultime 5",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.11,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "last_5",
        "description": "Media goal totali ultime 5 gare casa/fuori.",
        "ideal_sample": 5,
    },
    {
        "key": "rolling_avg_goals_last_10",
        "label": "Rolling Average Goal ultime 10",
        "block": _BLOCK_PRODUCTION,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "last_10",
        "description": "Media goal totali ultime 10 gare.",
        "ideal_sample": 10,
    },
    {
        "key": "home_fhgr",
        "label": "FHGR Casa",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.15,
        "required": True,
        "role": "driver",
        "scope": "home_team",
        "period": "first_half",
        "description": "First half goal rate squadra casa.",
        "ideal_sample": 5,
    },
    {
        "key": "away_fhgr",
        "label": "FHGR Ospite",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.15,
        "required": True,
        "role": "driver",
        "scope": "away_team",
        "period": "first_half",
        "description": "First half goal rate squadra ospite.",
        "ideal_sample": 5,
    },
    {
        "key": "home_first_half_xg",
        "label": "First Half xG Casa",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "home_team",
        "period": "first_half",
        "description": "xG primo tempo squadra casa.",
        "ideal_sample": 5,
        "not_supported": True,
    },
    {
        "key": "away_first_half_xg",
        "label": "First Half xG Ospite",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.10,
        "required": True,
        "role": "driver",
        "scope": "away_team",
        "period": "first_half",
        "description": "xG primo tempo squadra ospite.",
        "ideal_sample": 5,
        "not_supported": True,
    },
    {
        "key": "over_0_5_ht_frequency",
        "label": "Frequenza Over 0.5 Primo Tempo",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.20,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "first_half",
        "description": "Frequenza Over 0.5 HT.",
        "ideal_sample": 5,
    },
    {
        "key": "goals_scored_0_30",
        "label": "Goal segnati 0-30",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.15,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "minute_0_30",
        "description": "Goal segnati nel minuto 0-30.",
        "ideal_sample": 10,
        "not_supported": True,
    },
    {
        "key": "goals_scored_31_45",
        "label": "Goal segnati 31-45+",
        "block": _BLOCK_TEMPORAL,
        "weight": 0.15,
        "required": True,
        "role": "driver",
        "scope": "match_context",
        "period": "minute_31_45_plus",
        "description": "Goal segnati nel minuto 31-45+.",
        "ideal_sample": 10,
        "not_supported": True,
    },
    {
        "key": "xthreat",
        "label": "xThreat",
        "block": _BLOCK_ADVANCED,
        "weight": None,
        "required": False,
        "role": "corrector",
        "scope": "match_context",
        "period": "full_time",
        "description": "Metrica xThreat avanzata.",
        "raw_patterns": [r"xthreat", r"threat"],
    },
    {
        "key": "big_chances_created",
        "label": "Big Chances Created",
        "block": _BLOCK_ADVANCED,
        "weight": None,
        "required": False,
        "role": "corrector",
        "scope": "match_context",
        "period": "full_time",
        "description": "Occasioni da gol create.",
        "raw_patterns": [r"big chances created", r"big chance created"],
    },
    {
        "key": "big_chances_conceded",
        "label": "Big Chances Conceded",
        "block": _BLOCK_ADVANCED,
        "weight": None,
        "required": False,
        "role": "corrector",
        "scope": "match_context",
        "period": "full_time",
        "description": "Occasioni da gol concesse.",
        "raw_patterns": [r"big chances conceded", r"big chance conceded"],
    },
    {
        "key": "ppda",
        "label": "PPDA",
        "block": _BLOCK_ADVANCED,
        "weight": None,
        "required": False,
        "role": "corrector",
        "scope": "match_context",
        "period": "full_time",
        "description": "Passes per defensive action.",
        "raw_patterns": [r"ppda", r"passes per defensive"],
    },
    {
        "key": "field_tilt",
        "label": "Field Tilt",
        "block": _BLOCK_ADVANCED,
        "weight": None,
        "required": False,
        "role": "corrector",
        "scope": "match_context",
        "period": "full_time",
        "description": "Field tilt / territorial dominance.",
        "raw_patterns": [r"field tilt", r"territorial"],
    },
)

_ADVANCED_RAW_SCAN_KEYS = (
    "xthreat",
    "big_chances_created",
    "big_chances_conceded",
    "ppda",
    "field_tilt",
)


def _base_entry(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": spec["key"],
        "label": spec["label"],
        "block": spec["block"],
        "weight": spec.get("weight"),
        "required": spec["required"],
        "role": spec["role"],
        "available": False,
        "availability_status": "missing",
        "value": None,
        "normalized_value": None,
        "source": None,
        "source_field": None,
        "sample_size": None,
        "scope": spec["scope"],
        "period": spec["period"],
        "description": spec["description"],
        "warnings": [],
    }


def _finalize_entry(
    entry: dict[str, Any],
    *,
    value: float | None,
    source: str | None,
    source_field: str | None,
    sample_size: int | None,
    ideal_sample: int | None,
    not_supported: bool = False,
) -> dict[str, Any]:
    if not_supported:
        entry["availability_status"] = "not_supported"
        entry["available"] = False
        entry["warnings"] = ["metric_not_supported_in_pipeline"]
        return entry

    if value is None:
        entry["availability_status"] = "missing"
        entry["available"] = False
        if "field_not_found" not in entry["warnings"]:
            entry["warnings"].append("field_not_found")
        return entry

    entry["value"] = round(float(value), 4) if value is not None else None
    entry["normalized_value"] = entry["value"]
    entry["source"] = source
    entry["source_field"] = source_field
    entry["sample_size"] = sample_size

    if sample_size is not None and ideal_sample is not None and sample_size < ideal_sample:
        entry["availability_status"] = "insufficient_sample"
        entry["available"] = True
        entry["warnings"].append(f"sample_below_{ideal_sample}")
    else:
        entry["availability_status"] = "available"
        entry["available"] = True
    return entry


def _finalize_xg_entry(
    entry: dict[str, Any],
    profile: dict[str, Any],
    *,
    value_key: str,
    source_field: str,
    ideal_sample: int | None,
) -> dict[str, Any]:
    """Finalizza variabile xG con soglie sample dedicate (0 missing, 1-2 insufficient, >=3 available)."""
    sample_size = int(profile.get("sample_size") or 0)
    value = profile.get(value_key)
    entry["source"] = SOURCE_NAME
    entry["source_field"] = source_field
    entry["sample_size"] = sample_size if sample_size > 0 else None
    entry["period"] = "current_season_before_fixture"
    entry["note"] = ANTI_LEAKAGE_NOTE
    entry["anti_leakage"] = profile.get("anti_leakage")

    for w in profile.get("warnings") or []:
        if w not in entry["warnings"]:
            entry["warnings"].append(w)

    if value is None or sample_size <= 0:
        entry["availability_status"] = "missing"
        entry["available"] = False
        if "field_not_found" not in entry["warnings"]:
            entry["warnings"].append("field_not_found")
        if profile.get("matches_missing_xg"):
            entry["warnings"].append("missing_xg_in_cache")
        return entry

    entry["value"] = round(float(value), 4)
    entry["normalized_value"] = entry["value"]

    if sample_size < MIN_XG_SAMPLE_AVAILABLE:
        entry["availability_status"] = "insufficient_sample"
        entry["available"] = True
    else:
        entry["availability_status"] = "available"
        entry["available"] = True

    if ideal_sample is not None and sample_size < ideal_sample:
        entry["warnings"].append(f"sample_below_{ideal_sample}")

    return entry


def _team_stat_row(db: Session, fixture_id: int, team_id: int) -> FixtureTeamStat | None:
    return db.scalars(
        select(FixtureTeamStat).where(
            FixtureTeamStat.fixture_id == int(fixture_id),
            FixtureTeamStat.team_id == int(team_id),
        ),
    ).first()


def _combined_frequency(
    hits_a: int,
    sample_a: int,
    hits_b: int,
    sample_b: int,
) -> tuple[float | None, int]:
    hits = hits_a + hits_b
    sample = sample_a + sample_b
    if sample <= 0:
        return None, 0
    return round(hits / sample, 4), sample


def _combined_avg_goals(total_a: int, sample_a: int, total_b: int, sample_b: int) -> tuple[float | None, int]:
    sample = sample_a + sample_b
    if sample <= 0:
        return None, 0
    return round((total_a + total_b) / sample, 4), sample


def _dedupe_fixtures(fixtures: list[Fixture]) -> list[Fixture]:
    seen: set[int] = set()
    out: list[Fixture] = []
    for fx in fixtures:
        fid = int(fx.id)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(fx)
    return out


def _gg_frequency(fixtures: list[Fixture]) -> tuple[float | None, int]:
    hits = 0
    sample = 0
    for fx in fixtures:
        if fx.goals_home is None or fx.goals_away is None:
            continue
        sample += 1
        if int(fx.goals_home) > 0 and int(fx.goals_away) > 0:
            hits += 1
    if sample <= 0:
        return None, 0
    return round(hits / sample, 4), sample


def _scan_raw_statistics(raw_json: dict[str, Any] | None, patterns: list[str]) -> tuple[float | None, str | None]:
    if not raw_json or not isinstance(raw_json, dict):
        return None, None
    stats = raw_json.get("statistics")
    if not isinstance(stats, list):
        return None, None
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    for block in stats:
        if not isinstance(block, dict):
            continue
        label = str(block.get("type") or "")
        if not any(rx.search(label) for rx in compiled):
            continue
        raw_val = block.get("value")
        try:
            if raw_val is not None:
                val = float(str(raw_val).replace(",", ".").rstrip("%"))
                if val == val:
                    return val, f"fixture_team_stats.raw_json.statistics[{label!r}]"
        except (TypeError, ValueError):
            continue
    parsed = statistics_list_to_fields(stats)
    for key, val in parsed.items():
        if any(rx.search(key) for rx in compiled):
            try:
                return float(val), f"fixture_team_stats.raw_json.parsed.{key}"
            except (TypeError, ValueError):
                continue
    return None, None


def _latest_team_raw_stat(db: Session, fixture: Fixture, team_id: int) -> FixtureTeamStat | None:
    prior = load_finished_fixtures_for_team(db, fixture, team_id)
    for fx in reversed(prior):
        st = _team_stat_row(db, int(fx.id), team_id)
        if st is not None and st.raw_json:
            return st
        if st is not None and st.expected_goals is not None:
            return st
    return None


def _resolve_context(db: Session, target: Fixture) -> dict[str, Any]:
    hid = int(target.home_team_id)
    aid = int(target.away_team_id)
    slices = build_goal_fixture_slices(db, target)

    home_prior = load_finished_fixtures_for_team(db, target, hid)
    away_prior = load_finished_fixtures_for_team(db, target, aid)
    home_split = split_home_away(home_prior, hid, is_home=True)
    away_split = split_home_away(away_prior, aid, is_home=False)

    home_home_10 = take_last_n(home_split, 10)
    away_away_10 = take_last_n(away_split, 10)
    home_ht_fx, _ = _take_last_n_with_halftime(home_split, 5)
    away_ht_fx, _ = _take_last_n_with_halftime(away_split, 5)
    ht_home = aggregate_halftime_goal_totals(home_ht_fx, hid)
    ht_away = aggregate_halftime_goal_totals(away_ht_fx, aid)

    combined_last_10 = _dedupe_fixtures(take_last_n(home_prior, 10) + take_last_n(away_prior, 10))

    return {
        "slices": slices,
        "home_home_10": home_home_10,
        "away_away_10": away_away_10,
        "ht_home": ht_home,
        "ht_away": ht_away,
        "combined_last_10": combined_last_10,
    }


def _resolve_variables(
    db: Session,
    fixture: Fixture,
    *,
    exclude_provider_fixture_id: int | None = None,
) -> dict[str, dict[str, Any]]:
    ctx = _resolve_context(db, fixture)
    slices = ctx["slices"]
    hid = int(fixture.home_team_id)
    aid = int(fixture.away_team_id)

    home_xg_profile = build_current_season_team_xg_profile(
        db,
        fixture,
        hid,
        exclude_provider_fixture_id=exclude_provider_fixture_id,
    )
    away_xg_profile = build_current_season_team_xg_profile(
        db,
        fixture,
        aid,
        exclude_provider_fixture_id=exclude_provider_fixture_id,
    )

    o25_val, o25_n = _combined_frequency(
        slices.home_total_10.over_2_5_hits,
        slices.home_total_10.sample,
        slices.away_total_10.over_2_5_hits,
        slices.away_total_10.sample,
    )
    gg_val, gg_n = _gg_frequency(ctx["combined_last_10"])
    avg5_val, avg5_n = _combined_avg_goals(
        slices.home_home_5.total_goals,
        slices.home_home_5.sample,
        slices.away_away_5.total_goals,
        slices.away_away_5.sample,
    )
    avg10_val, avg10_n = _combined_avg_goals(
        slices.home_total_10.total_goals,
        slices.home_total_10.sample,
        slices.away_total_10.total_goals,
        slices.away_total_10.sample,
    )

    ht_home = ctx["ht_home"]
    ht_away = ctx["ht_away"]
    home_fhgr = ht_home.goals_for / ht_home.sample if ht_home.sample > 0 else None
    away_fhgr = ht_away.goals_for / ht_away.sample if ht_away.sample > 0 else None
    o05_ht_val, o05_ht_n = _combined_frequency(
        ht_home.over_pt_0_5_hits,
        ht_home.sample,
        ht_away.over_pt_0_5_hits,
        ht_away.sample,
    )

    resolved: dict[str, dict[str, Any]] = {}

    for spec in _VARIABLE_SPECS:
        key = spec["key"]
        entry = _base_entry(spec)
        ideal = spec.get("ideal_sample")

        if spec.get("not_supported"):
            resolved[key] = _finalize_entry(entry, value=None, source=None, source_field=None, sample_size=None, ideal_sample=ideal, not_supported=True)
            continue

        if key == "home_xg_for":
            resolved[key] = _finalize_xg_entry(
                entry,
                home_xg_profile,
                value_key="xg_for_avg",
                source_field=SOURCE_FIELD_FOR,
                ideal_sample=ideal,
            )
        elif key == "home_xg_against":
            resolved[key] = _finalize_xg_entry(
                entry,
                home_xg_profile,
                value_key="xg_against_avg",
                source_field=SOURCE_FIELD_AGAINST,
                ideal_sample=ideal,
            )
        elif key == "away_xg_for":
            resolved[key] = _finalize_xg_entry(
                entry,
                away_xg_profile,
                value_key="xg_for_avg",
                source_field=SOURCE_FIELD_FOR,
                ideal_sample=ideal,
            )
        elif key == "away_xg_against":
            resolved[key] = _finalize_xg_entry(
                entry,
                away_xg_profile,
                value_key="xg_against_avg",
                source_field=SOURCE_FIELD_AGAINST,
                ideal_sample=ideal,
            )
        elif key == "over_2_5_frequency_last_10":
            resolved[key] = _finalize_entry(entry, value=o25_val, source="cecchino_fixture_history", source_field="GoalTotals.over_2_5_hits/sample", sample_size=o25_n or None, ideal_sample=ideal)
        elif key == "gg_frequency_last_10":
            resolved[key] = _finalize_entry(entry, value=gg_val, source="fixtures", source_field="goals_home+goals_away>0", sample_size=gg_n or None, ideal_sample=ideal)
        elif key == "rolling_avg_goals_last_5":
            resolved[key] = _finalize_entry(entry, value=avg5_val, source="cecchino_fixture_history", source_field="GoalTotals.total_goals/sample", sample_size=avg5_n or None, ideal_sample=ideal)
        elif key == "rolling_avg_goals_last_10":
            resolved[key] = _finalize_entry(entry, value=avg10_val, source="cecchino_fixture_history", source_field="GoalTotals.total_goals/sample", sample_size=avg10_n or None, ideal_sample=ideal)
        elif key == "home_fhgr":
            resolved[key] = _finalize_entry(entry, value=home_fhgr, source="cecchino_fixture_history", source_field="aggregate_halftime_goal_totals.goals_for/sample", sample_size=ht_home.sample or None, ideal_sample=ideal)
        elif key == "away_fhgr":
            resolved[key] = _finalize_entry(entry, value=away_fhgr, source="cecchino_fixture_history", source_field="aggregate_halftime_goal_totals.goals_for/sample", sample_size=ht_away.sample or None, ideal_sample=ideal)
        elif key == "over_0_5_ht_frequency":
            resolved[key] = _finalize_entry(entry, value=o05_ht_val, source="cecchino_fixture_history", source_field="GoalTotals.over_pt_0_5_hits/sample", sample_size=o05_ht_n or None, ideal_sample=ideal)
        elif key in _ADVANCED_RAW_SCAN_KEYS:
            patterns = list(spec.get("raw_patterns") or [])
            st_home = _latest_team_raw_stat(db, fixture, hid)
            st_away = _latest_team_raw_stat(db, fixture, aid)
            val = None
            field = None
            for st in (st_home, st_away):
                if st is None:
                    continue
                raw = st.raw_json if isinstance(st.raw_json, dict) else None
                val, field = _scan_raw_statistics(raw, patterns)
                if val is not None:
                    break
            if val is None:
                resolved[key] = _finalize_entry(entry, value=None, source=None, source_field=None, sample_size=None, ideal_sample=ideal, not_supported=True)
            else:
                resolved[key] = _finalize_entry(entry, value=val, source="fixture_team_stats", source_field=field, sample_size=1, ideal_sample=ideal)
        else:
            resolved[key] = _finalize_entry(entry, value=None, source=None, source_field=None, sample_size=None, ideal_sample=ideal)

    return resolved


def _count_available(variables: dict[str, dict[str, Any]], *, block: str | None = None, required: bool | None = None) -> int:
    count = 0
    for spec in _VARIABLE_SPECS:
        if block is not None and spec["block"] != block:
            continue
        if required is not None and spec["required"] != required:
            continue
        var = variables.get(spec["key"], {})
        if var.get("availability_status") == "available":
            count += 1
    return count


def _confidence(required_available: int, required_total: int) -> str:
    pct = required_available / required_total if required_total else 0.0
    if pct >= 0.80:
        return "high"
    if pct >= 0.60:
        return "medium"
    if pct >= 0.40:
        return "partial"
    return "insufficient"


def _advanced_correctors_ready(advanced_available: int) -> str:
    if advanced_available >= 3:
        return "available"
    if advanced_available >= 1:
        return "partial"
    return "missing"


def _missing_critical_fields(variables: dict[str, dict[str, Any]]) -> list[str]:
    critical_keys = (
        "home_xg_for",
        "away_xg_for",
        "rolling_avg_goals_last_10",
        "over_2_5_frequency_last_10",
        "home_fhgr",
        "away_fhgr",
    )
    missing: list[str] = []
    for key in critical_keys:
        var = variables.get(key, {})
        if var.get("availability_status") != "available":
            missing.append(key)
    return missing


def _has_home_away_split_data(variables: dict[str, dict[str, Any]]) -> bool:
    home_ok = variables.get("home_xg_for", {}).get("availability_status") == "available"
    away_ok = variables.get("away_xg_for", {}).get("availability_status") == "available"
    rolling_home = variables.get("rolling_avg_goals_last_5", {}).get("availability_status") == "available"
    return (home_ok or rolling_home) and (away_ok or rolling_home)


def _build_engine_readiness(
    variables: dict[str, dict[str, Any]],
    *,
    production_goal_ready: bool,
    temporal_distribution_ready: bool,
    advanced_available: int,
) -> dict[str, Any]:
    advanced_status = _advanced_correctors_ready(advanced_available)
    can_ft = production_goal_ready
    can_ht = temporal_distribution_ready
    can_home_away = _has_home_away_split_data(variables)
    return {
        "production_goal_ready": production_goal_ready,
        "temporal_distribution_ready": temporal_distribution_ready,
        "advanced_correctors_ready": advanced_status,
        "can_compute_expected_goals_ft": can_ft,
        "can_compute_expected_goals_ht": can_ht,
        "can_compute_home_away_expected_goals": can_home_away,
        "can_compute_over_probabilities": can_ft,
        "can_compute_gg_ng": can_home_away,
        "can_compute_scorelines": can_home_away,
        "missing_critical_fields": _missing_critical_fields(variables),
    }


def build_expected_goal_engine_diagnostics(
    db: Session,
    fixture: Fixture,
    *,
    exclude_provider_fixture_id: int | None = None,
) -> dict[str, Any]:
    """Audit read-only variabili Expected Goal Engine — nessun calcolo goal attesi."""
    variables = _resolve_variables(
        db,
        fixture,
        exclude_provider_fixture_id=exclude_provider_fixture_id,
    )

    required_total = sum(1 for s in _VARIABLE_SPECS if s["required"])
    advanced_total = sum(1 for s in _VARIABLE_SPECS if not s["required"])
    required_available = _count_available(variables, required=True)
    advanced_available = _count_available(variables, required=False)

    production_available = _count_available(variables, block=_BLOCK_PRODUCTION)
    temporal_available = _count_available(variables, block=_BLOCK_TEMPORAL)
    production_goal_ready = production_available >= 5
    temporal_distribution_ready = temporal_available >= 4

    has_xg_or_rolling = any(
        variables.get(k, {}).get("availability_status") == "available"
        for k in ("home_xg_for", "away_xg_for", "rolling_avg_goals_last_10")
    )
    engine_ready = production_goal_ready and required_available >= 8 and has_xg_or_rolling

    confidence = _confidence(required_available, required_total)
    engine_readiness = _build_engine_readiness(
        variables,
        production_goal_ready=production_goal_ready,
        temporal_distribution_ready=temporal_distribution_ready,
        advanced_available=advanced_available,
    )

    blocks = {
        _BLOCK_PRODUCTION: [variables[s["key"]] for s in _VARIABLE_SPECS if s["block"] == _BLOCK_PRODUCTION],
        _BLOCK_TEMPORAL: [variables[s["key"]] for s in _VARIABLE_SPECS if s["block"] == _BLOCK_TEMPORAL],
        _BLOCK_ADVANCED: [variables[s["key"]] for s in _VARIABLE_SPECS if s["block"] == _BLOCK_ADVANCED],
    }

    return {
        "version": VERSION,
        "status": STATUS_AVAILABLE,
        "fixture_id": int(fixture.id),
        "coverage": {
            "required_available": required_available,
            "required_total": required_total,
            "advanced_available": advanced_available,
            "advanced_total": advanced_total,
            "coverage_pct": round(required_available / required_total, 4) if required_total else 0.0,
            "engine_ready": engine_ready,
            "confidence": confidence,
        },
        "engine_readiness": engine_readiness,
        "blocks": blocks,
        "warnings": [],
    }


def build_expected_goal_engine_diagnostics_for_today_row(
    db: Session,
    row: CecchinoTodayFixture,
) -> dict[str, Any]:
    """Wrapper Cecchino Today detail."""
    if not row.local_fixture_id:
        return {
            "version": VERSION,
            "status": "insufficient_data",
            "fixture_id": None,
            "coverage": None,
            "engine_readiness": None,
            "blocks": None,
            "warnings": ["missing_local_fixture_id"],
        }
    fixture = db.get(Fixture, int(row.local_fixture_id))
    if fixture is None:
        return {
            "version": VERSION,
            "status": "insufficient_data",
            "fixture_id": int(row.local_fixture_id),
            "coverage": None,
            "engine_readiness": None,
            "blocks": None,
            "warnings": ["missing_local_fixture"],
        }
    return build_expected_goal_engine_diagnostics(
        db,
        fixture,
        exclude_provider_fixture_id=int(row.provider_fixture_id) if row.provider_fixture_id else None,
    )
