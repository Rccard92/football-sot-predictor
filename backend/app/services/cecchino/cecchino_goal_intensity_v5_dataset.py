"""Dataset storico Intensità Goal v5 — Fase 1B.1 (summary compatto + export stream)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import statistics
import time
from collections import Counter
from datetime import date
from typing import Any, Iterator, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture import Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_historical_fixture_identity_consistency,
)
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    FEATURE_SPECS,
    append_debug_sample,
    dedupe_fixtures_provider_then_composite,
    extract_features_from_indexes,
    finished_local_fixtures_in_kickoff_range,
    load_today_snapshots_for_fixtures,
    match_today_snapshot_indexed,
    month_key_from_dt,
    pct,
    sanitize_exception_message,
    snapshot_time_status,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import (
    build_today_indexes,
    preload_audit_indexes,
)
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

logger = logging.getLogger(__name__)

VERSION = "cecchino_goal_intensity_v5_dataset_v1_1"
_PROGRESS_EVERY = 500
_PAIRED_XG_MIN_SAMPLE = 50
_PREVIEW_MAX_ROWS = 100
_SUMMARY_PAYLOAD_SOFT_LIMIT_BYTES = 2 * 1024 * 1024

ExportKind = Literal["all", "core_min5", "core_min10", "xg_paired"]

XG_FEATURE_KEYS = (
    "home_xg_for_avg",
    "away_xg_for_avg",
    "pair_xg_for_avg",
    "home_xg_against_avg",
    "away_xg_against_avg",
    "pair_xg_against_avg",
)

CORE_FEATURE_KEYS = tuple(
    s["feature_key"] for s in FEATURE_SPECS if s["feature_key"] not in XG_FEATURE_KEYS
)

CORE_PRIMARY_KEYS = tuple(
    s["feature_key"]
    for s in FEATURE_SPECS
    if s["feature_key"] not in XG_FEATURE_KEYS and s.get("recommended_status") == "primary_candidate"
)

DATASET_FEATURE_KEYS = (
    "home_goals_scored_avg",
    "away_goals_scored_avg",
    "home_goals_scored_rolling_5",
    "away_goals_scored_rolling_5",
    "home_goals_scored_rolling_10",
    "away_goals_scored_rolling_10",
    "home_xg_for_avg",
    "away_xg_for_avg",
    "pair_xg_for_avg",
    "home_goals_conceded_avg",
    "away_goals_conceded_avg",
    "home_clean_sheet_freq",
    "away_clean_sheet_freq",
    "home_xg_against_avg",
    "away_xg_against_avg",
    "pair_xg_against_avg",
    "over_2_5_frequency_last_10",
    "gg_frequency_last_10",
    "total_goals_avg",
    "total_goals_rolling_5",
    "total_goals_rolling_10",
    "goals_ge_2_frequency_last_10",
    "goals_ge_3_frequency_last_10",
    "pair_goals_scored_rolling_5",
    "pair_goals_scored_rolling_10",
    "goals_scored_std_last_10",
    "goals_scored_mad_last_10",
    "goals_scored_cv_last_10",
    "goals_rolling_5_vs_10_delta",
)

CSV_COLUMNS: tuple[str, ...] = (
    "local_fixture_id",
    "provider_fixture_id",
    "competition_id",
    "country",
    "league_name",
    "kickoff",
    "home_team_id",
    "home_team",
    "away_team_id",
    "away_team",
    "row_feature_safe",
    "static_identity_status",
    "snapshot_time_status",
    "sample_size",
    "history_quality_tier",
    "core_feature_status",
    "xg_status",
    "xg_source",
    "xg_available_fields",
    "xg_missing_fields",
    "xg_exclusion_reasons",
    *DATASET_FEATURE_KEYS,
    "goals_home_ft",
    "goals_away_ft",
    "total_goals_ft",
    "goals_ge_2",
    "goals_ge_3",
    "btts_ft",
    "kickoff_month",
    "chronological_index",
    "temporal_fold_candidate",
    "train_candidate",
    "validation_candidate",
    "test_candidate",
)


def history_quality_tier(sample_size: int) -> str:
    if sample_size <= 0:
        return "none"
    if sample_size <= 4:
        return "very_low"
    if sample_size <= 9:
        return "low"
    if sample_size <= 19:
        return "standard"
    return "robust"


def core_feature_status(features: dict[str, Any], sample_size: int) -> str:
    if sample_size <= 0:
        return "missing"
    present = sum(1 for k in CORE_PRIMARY_KEYS if features.get(k) is not None)
    if present == 0:
        return "missing"
    if present >= len(CORE_PRIMARY_KEYS):
        return "available"
    return "partial"


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return round(float(statistics.median(vals)), 6)


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return round(float(statistics.fmean(vals)), 6)


def _cohort_target_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    goals = [float(r["total_goals_ft"]) for r in rows if r.get("total_goals_ft") is not None]
    n = len(rows)
    ge2 = sum(1 for r in rows if r.get("goals_ge_2"))
    ge3 = sum(1 for r in rows if r.get("goals_ge_3"))
    btts = sum(1 for r in rows if r.get("btts_ft"))
    by_month: Counter[str] = Counter()
    by_country: Counter[str] = Counter()
    by_comp: Counter[str] = Counter()
    for r in rows:
        mk = r.get("kickoff_month") or (str(r.get("kickoff") or "")[:7] if r.get("kickoff") else "unknown")
        by_month[str(mk)] += 1
        by_country[str(r.get("country") or "unknown")] += 1
        by_comp[str(r.get("competition_id") if r.get("competition_id") is not None else "unknown")] += 1
    return {
        "rows": n,
        "mean_total_goals_ft": _mean(goals),
        "median_total_goals_ft": _median(goals),
        "goals_ge_2_count": ge2,
        "goals_ge_2_rate_pct": pct(ge2, n),
        "goals_ge_3_count": ge3,
        "goals_ge_3_rate_pct": pct(ge3, n),
        "btts_count": btts,
        "btts_rate_pct": pct(btts, n),
        "monthly_distribution": dict(sorted(by_month.items())),
        "country_distribution": dict(sorted(by_country.items(), key=lambda x: (-x[1], x[0]))[:40]),
        "competition_distribution": dict(sorted(by_comp.items(), key=lambda x: (-x[1], x[0]))[:60]),
    }


def _names_close(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().casefold() == b.strip().casefold()


def _fixture_ids_with_team_stats(db: Session, fixture_ids: list[int]) -> set[int]:
    if not fixture_ids:
        return set()
    rows = db.scalars(
        select(FixtureTeamStat.fixture_id).where(FixtureTeamStat.fixture_id.in_(fixture_ids)).distinct()
    ).all()
    return {int(x) for x in rows}


def _filter_today_for_retained(
    today_rows: list[CecchinoTodayFixture],
    fixtures: list[Fixture],
) -> list[CecchinoTodayFixture]:
    retained_local = {int(f.id) for f in fixtures}
    retained_api = {
        int(f.api_fixture_id) for f in fixtures if getattr(f, "api_fixture_id", None) is not None
    }
    out: list[CecchinoTodayFixture] = []
    for row in today_rows:
        lid = getattr(row, "local_fixture_id", None)
        pid = getattr(row, "provider_fixture_id", None)
        if lid is not None and int(lid) in retained_local:
            out.append(row)
            continue
        if pid is not None and int(pid) in retained_api:
            out.append(row)
    return out


def _sha256_canonical(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _core_ready(r: dict[str, Any], min_sample: int) -> bool:
    return r.get("core_feature_status") == "available" and int(r.get("sample_size") or 0) >= min_sample


def filter_dataset_rows_by_kind(rows: list[dict[str, Any]], kind: ExportKind) -> list[dict[str, Any]]:
    if kind == "all":
        return rows
    if kind == "core_min5":
        return [r for r in rows if _core_ready(r, 5)]
    if kind == "core_min10":
        return [r for r in rows if _core_ready(r, 10)]
    return [
        r
        for r in rows
        if _core_ready(r, 1)
        and r.get("xg_status") == "available"
        and all(r.get(k) is not None for k in XG_FEATURE_KEYS)
    ]


def _row_to_csv_dict(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in CSV_COLUMNS:
        val = row.get(col)
        if isinstance(val, list):
            out[col] = "|".join(str(x) for x in val)
        elif isinstance(val, bool):
            out[col] = "true" if val else "false"
        else:
            out[col] = "" if val is None else val
    return out


def build_goal_intensity_v5_dataset_internal(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Dataset completo in memoria — riusabile da summary ed export."""
    t0 = time.perf_counter()
    warnings: list[str] = []
    phases: dict[str, float] = {}

    t_cohort = time.perf_counter()
    raw_fixtures = finished_local_fixtures_in_kickoff_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    phases["cohort_ms"] = round((time.perf_counter() - t_cohort) * 1000.0, 2)
    rows_initial = len(raw_fixtures)

    t_today = time.perf_counter()
    today_all = load_today_snapshots_for_fixtures(db, raw_fixtures)
    by_local, by_provider = build_today_indexes(today_all)
    has_today: dict[int, bool] = {}
    for fx in raw_fixtures:
        has_today[int(fx.id)] = match_today_snapshot_indexed(fx, by_local, by_provider) is not None
    phases["today_load_ms"] = round((time.perf_counter() - t_today) * 1000.0, 2)

    t_fts = time.perf_counter()
    fts_ids = _fixture_ids_with_team_stats(db, [int(f.id) for f in raw_fixtures])
    has_fts = {fid: True for fid in fts_ids}
    phases["fts_lookup_ms"] = round((time.perf_counter() - t_fts) * 1000.0, 2)

    t_dedupe = time.perf_counter()
    fixtures, dedupe_report = dedupe_fixtures_provider_then_composite(
        raw_fixtures,
        has_today_by_id=has_today,
        has_fts_by_id=has_fts,
    )
    phases["dedupe_ms"] = round((time.perf_counter() - t_dedupe) * 1000.0, 2)
    dedupe_timings = dedupe_report.get("timings_ms") or {}
    phases["provider_dedupe_ms"] = float(dedupe_timings.get("provider_dedupe_ms") or 0)
    phases["composite_bucket_build_ms"] = float(dedupe_timings.get("composite_bucket_build_ms") or 0)
    phases["composite_cluster_ms"] = float(dedupe_timings.get("composite_cluster_ms") or 0)

    # Riuso snapshot Today già caricati (niente seconda query)
    today_candidates = _filter_today_for_retained(today_all, fixtures)

    t_preload = time.perf_counter()
    indexes = preload_audit_indexes(db, fixtures, today_candidates)
    phases["preload_ms"] = round((time.perf_counter() - t_preload) * 1000.0, 2)
    phases.update({f"index_{k}": v for k, v in (indexes.timings_ms or {}).items()})

    dataset_rows: list[dict[str, Any]] = []
    identity_excluded: list[dict[str, Any]] = []
    all_finished_diag: list[dict[str, Any]] = []
    debug_samples: dict[str, list[dict[str, Any]]] = {}

    identity_fail_by_reason: Counter[str] = Counter()
    identity_fail_by_month: Counter[str] = Counter()
    identity_fail_by_comp: Counter[str] = Counter()
    identity_fail_by_country: Counter[str] = Counter()
    identity_fail_goals: list[float] = []

    t_feat = time.perf_counter()
    total = len(fixtures)

    for i, local in enumerate(fixtures, start=1):
        lid = int(local.id)
        api_id = int(local.api_fixture_id) if local.api_fixture_id is not None else None
        ko = ensure_datetime_utc(local.kickoff_at, field_name="local.kickoff_at")
        ko_iso = safe_isoformat(ko, field_name="local.kickoff_at") if ko else None
        mk = month_key_from_dt(ko)

        if local.home_team_id is None or local.away_team_id is None:
            continue
        if ko is None:
            continue
        if local.goals_home is None or local.goals_away is None:
            continue

        gh, ga = int(local.goals_home), int(local.goals_away)
        total_goals = gh + ga
        goals_ge_2 = total_goals >= 2
        goals_ge_3 = total_goals >= 3
        btts_ft = gh > 0 and ga > 0

        comp_id = int(local.competition_id) if local.competition_id is not None else None
        country = indexes.country_by_competition_id.get(comp_id) if comp_id is not None else None
        league_name = indexes.competition_name_by_id.get(comp_id) if comp_id is not None else None
        home_name = indexes.team_name_by_id.get(int(local.home_team_id))
        away_name = indexes.team_name_by_id.get(int(local.away_team_id))

        today_row = match_today_snapshot_indexed(
            local,
            indexes.today_by_local_fixture_id,
            indexes.today_by_provider_fixture_id,
        )
        snap_status = snapshot_time_status(today_row, ko)

        identity_status = "static_identity_unavailable"
        identity_mismatch = False
        identity_check_error = False
        local_fixture_id_match = False
        provider_fixture_id_match = False
        competition_id_match = False
        home_team_match = False
        away_team_match = False
        kickoff_match = False
        failure_reasons: list[str] = []

        if today_row is not None:
            try:
                identity_payload = build_historical_fixture_identity_consistency(
                    today_row=today_row,
                    local_fixture=local,
                    local_home_team_name=home_name,
                    local_away_team_name=away_name,
                )
                identity_status = str(identity_payload.get("status") or "static_identity_unavailable")
                local_fixture_id_match = bool(identity_payload.get("local_fixture_id_match"))
                provider_fixture_id_match = bool(identity_payload.get("provider_match"))
                competition_id_match = bool(identity_payload.get("competition_match"))
                kickoff_match = bool(identity_payload.get("kickoff_match"))
                home_team_match = _names_close(getattr(today_row, "home_team_name", None), home_name)
                away_team_match = _names_close(getattr(today_row, "away_team_name", None), away_name)
                if not getattr(today_row, "home_team_name", None) and not getattr(today_row, "away_team_name", None):
                    home_team_match = True
                    away_team_match = True
                if identity_status == "static_identity_failed":
                    identity_mismatch = True
                    failure_reasons = [
                        w
                        for w in (identity_payload.get("warnings") or [])
                        if w
                        not in (
                            "today_upcoming_vs_local_ft",
                            "today_no_score_vs_local_score",
                            "today_local_status_mismatch",
                            "today_local_score_mismatch",
                        )
                    ]
            except Exception as exc:
                identity_check_error = True
                identity_status = "static_identity_failed"
                failure_reasons = ["identity_check_error"]
                append_debug_sample(
                    debug_samples,
                    "identity_check_error",
                    today_fixture_id=int(today_row.id),
                    local_fixture_id=lid,
                    provider_fixture_id=api_id,
                    kickoff=ko_iso,
                    exception_type=type(exc).__name__,
                    exception_message=sanitize_exception_message(exc),
                )

        features, leak_meta = extract_features_from_indexes(local, today_row, indexes)

        failed = identity_mismatch or identity_check_error
        if leak_meta.get("current_fixture_included") or leak_meta.get("future_fixture_included"):
            failed = True

        sample_size = int(leak_meta.get("sample_size") or 0)
        xg_status = str(leak_meta.get("xg_status") or "missing")
        xg_source = str(leak_meta.get("xg_source") or "missing")
        tier = history_quality_tier(sample_size)
        c_status = core_feature_status(features, sample_size)

        base_diag = {
            "local_fixture_id": lid,
            "provider_fixture_id": api_id,
            "competition_id": comp_id,
            "country": country,
            "kickoff": ko_iso,
            "kickoff_month": mk,
            "total_goals_ft": total_goals,
            "goals_ge_2": goals_ge_2,
            "goals_ge_3": goals_ge_3,
            "btts_ft": btts_ft,
            "sample_size": sample_size,
            "row_feature_safe": False,
        }
        all_finished_diag.append(base_diag)

        if failed:
            reason = failure_reasons[0] if failure_reasons else (
                "future_source_fixture"
                if leak_meta.get("future_fixture_included")
                else "current_fixture_included"
                if leak_meta.get("current_fixture_included")
                else "identity_mismatch"
            )
            identity_fail_by_reason[reason] += 1
            identity_fail_by_month[mk] += 1
            identity_fail_by_comp[str(comp_id if comp_id is not None else "unknown")] += 1
            identity_fail_by_country[str(country or "unknown")] += 1
            identity_fail_goals.append(float(total_goals))
            identity_excluded.append(
                {
                    **base_diag,
                    "static_identity_status": identity_status,
                    "static_identity_failure_reasons": failure_reasons or [reason],
                    "target_total_goals_ft": total_goals,
                }
            )
            if i % _PROGRESS_EVERY == 0 or i == total:
                _log_progress(i, total, t_feat)
            continue

        row: dict[str, Any] = {
            "local_fixture_id": lid,
            "provider_fixture_id": api_id,
            "competition_id": comp_id,
            "country": country,
            "league_name": league_name,
            "kickoff": ko_iso,
            "home_team_id": int(local.home_team_id),
            "home_team": home_name,
            "away_team_id": int(local.away_team_id),
            "away_team": away_name,
            "row_feature_safe": True,
            "static_identity_status": identity_status,
            "snapshot_time_status": snap_status,
            "local_fixture_id_match": local_fixture_id_match if today_row else None,
            "provider_fixture_id_match": provider_fixture_id_match if today_row else None,
            "competition_id_match": competition_id_match if today_row else None,
            "home_team_match": home_team_match if today_row else None,
            "away_team_match": away_team_match if today_row else None,
            "kickoff_match": kickoff_match if today_row else None,
            "static_identity_failure_reasons": [],
            "sample_size": sample_size,
            "history_quality_tier": tier,
            "core_feature_status": c_status,
            "xg_status": xg_status,
            "xg_source": xg_source,
            "xg_available_fields": list(leak_meta.get("xg_available_fields") or []),
            "xg_missing_fields": list(leak_meta.get("xg_missing_fields") or []),
            "xg_exclusion_reasons": list(leak_meta.get("xg_exclusion_reasons") or []),
        }
        for key in DATASET_FEATURE_KEYS:
            row[key] = features.get(key)
        row["goals_home_ft"] = gh
        row["goals_away_ft"] = ga
        row["total_goals_ft"] = total_goals
        row["goals_ge_2"] = goals_ge_2
        row["goals_ge_3"] = goals_ge_3
        row["btts_ft"] = btts_ft
        row["kickoff_month"] = mk
        dataset_rows.append(row)

        if i % _PROGRESS_EVERY == 0 or i == total:
            _log_progress(i, total, t_feat)

    phases["feature_calculation_ms"] = round((time.perf_counter() - t_feat) * 1000.0, 2)

    t_cohort_calc = time.perf_counter()
    dataset_rows.sort(key=lambda r: (str(r.get("kickoff") or ""), int(r["local_fixture_id"])))
    n_safe = len(dataset_rows)
    train_end = int(n_safe * 0.70)
    val_end = int(n_safe * 0.85)
    for idx_i, row in enumerate(dataset_rows):
        row["chronological_index"] = idx_i
        row["train_candidate"] = idx_i < train_end
        row["validation_candidate"] = train_end <= idx_i < val_end
        row["test_candidate"] = idx_i >= val_end
        if row["train_candidate"]:
            row["temporal_fold_candidate"] = "train"
        elif row["validation_candidate"]:
            row["temporal_fold_candidate"] = "validation"
        else:
            row["temporal_fold_candidate"] = "test"

    cohort_ids = {
        "all_feature_safe": [r["local_fixture_id"] for r in dataset_rows],
        "core_history_any": [r["local_fixture_id"] for r in dataset_rows if _core_ready(r, 1)],
        "core_history_min_5": [r["local_fixture_id"] for r in dataset_rows if _core_ready(r, 5)],
        "core_history_min_10": [r["local_fixture_id"] for r in dataset_rows if _core_ready(r, 10)],
        "core_history_min_20": [r["local_fixture_id"] for r in dataset_rows if _core_ready(r, 20)],
        "xg_complete_paired": [
            r["local_fixture_id"]
            for r in dataset_rows
            if _core_ready(r, 1)
            and r.get("xg_status") == "available"
            and all(r.get(k) is not None for k in XG_FEATURE_KEYS)
        ],
        "xg_partial_diagnostic": [
            r["local_fixture_id"] for r in dataset_rows if r.get("xg_status") == "partial"
        ],
    }

    history_counts = {
        "none": sum(1 for r in dataset_rows if r["history_quality_tier"] == "none"),
        "very_low": sum(1 for r in dataset_rows if r["history_quality_tier"] == "very_low"),
        "low": sum(1 for r in dataset_rows if r["history_quality_tier"] == "low"),
        "standard": sum(1 for r in dataset_rows if r["history_quality_tier"] == "standard"),
        "robust": sum(1 for r in dataset_rows if r["history_quality_tier"] == "robust"),
        "history_any": sum(1 for r in dataset_rows if int(r["sample_size"]) >= 1),
        "history_min_5": sum(1 for r in dataset_rows if int(r["sample_size"]) >= 5),
        "history_min_10": sum(1 for r in dataset_rows if int(r["sample_size"]) >= 10),
        "history_min_20": sum(1 for r in dataset_rows if int(r["sample_size"]) >= 20),
    }

    xg_cohorts = {
        "all_feature_safe": n_safe,
        "xg_available": sum(1 for r in dataset_rows if r["xg_status"] == "available"),
        "xg_partial": sum(1 for r in dataset_rows if r["xg_status"] == "partial"),
        "xg_missing": sum(1 for r in dataset_rows if r["xg_status"] == "missing"),
        "xg_excluded_unsafe": sum(1 for r in dataset_rows if r["xg_status"] == "excluded_unsafe"),
    }
    xg_cohorts.update(
        {
            "xg_available_pct": pct(xg_cohorts["xg_available"], n_safe),
            "xg_partial_pct": pct(xg_cohorts["xg_partial"], n_safe),
            "xg_missing_pct": pct(xg_cohorts["xg_missing"], n_safe),
            "xg_excluded_unsafe_pct": pct(xg_cohorts["xg_excluded_unsafe"], n_safe),
        }
    )

    paired_ids = cohort_ids["xg_complete_paired"]
    paired_id_set = set(paired_ids)
    paired_rows = [r for r in dataset_rows if r["local_fixture_id"] in paired_id_set]
    paired_targets = [
        {
            "local_fixture_id": r["local_fixture_id"],
            "total_goals_ft": r["total_goals_ft"],
            "goals_ge_2": r["goals_ge_2"],
            "goals_ge_3": r["goals_ge_3"],
            "btts_ft": r["btts_ft"],
        }
        for r in paired_rows
    ]
    fixture_ids_hash = _sha256_canonical(paired_ids)
    targets_hash = _sha256_canonical(paired_targets)
    first_kickoff = paired_rows[0]["kickoff"] if paired_rows else None
    last_kickoff = paired_rows[-1]["kickoff"] if paired_rows else None
    phases["cohort_calculation_ms"] = round((time.perf_counter() - t_cohort_calc) * 1000.0, 2)

    t_bias = time.perf_counter()
    no_history_rows = [
        {
            **{k: r.get(k) for k in ("local_fixture_id", "competition_id", "country", "kickoff", "kickoff_month")},
            "total_goals_ft": r["total_goals_ft"],
            "goals_ge_2": r["goals_ge_2"],
            "goals_ge_3": r["goals_ge_3"],
            "btts_ft": r["btts_ft"],
        }
        for r in dataset_rows
        if int(r["sample_size"]) == 0
    ]
    core_ready_rows = [
        {
            **{k: r.get(k) for k in ("local_fixture_id", "competition_id", "country", "kickoff", "kickoff_month")},
            "total_goals_ft": r["total_goals_ft"],
            "goals_ge_2": r["goals_ge_2"],
            "goals_ge_3": r["goals_ge_3"],
            "btts_ft": r["btts_ft"],
        }
        for r in dataset_rows
        if _core_ready(r, 5)
    ]
    identity_excl_for_bias = [
        {
            "local_fixture_id": r["local_fixture_id"],
            "competition_id": r.get("competition_id"),
            "country": r.get("country"),
            "kickoff": r.get("kickoff"),
            "kickoff_month": r.get("kickoff_month"),
            "total_goals_ft": r.get("total_goals_ft"),
            "goals_ge_2": r.get("goals_ge_2"),
            "goals_ge_3": r.get("goals_ge_3"),
            "btts_ft": r.get("btts_ft"),
        }
        for r in identity_excluded
    ]
    safe_for_bias = [
        {
            "local_fixture_id": r["local_fixture_id"],
            "competition_id": r.get("competition_id"),
            "country": r.get("country"),
            "kickoff": r.get("kickoff"),
            "kickoff_month": r.get("kickoff_month"),
            "total_goals_ft": r["total_goals_ft"],
            "goals_ge_2": r["goals_ge_2"],
            "goals_ge_3": r["goals_ge_3"],
            "btts_ft": r["btts_ft"],
        }
        for r in dataset_rows
    ]
    exclusion_bias_report = {
        "all_finished": _cohort_target_stats(all_finished_diag),
        "feature_safe": _cohort_target_stats(safe_for_bias),
        "identity_excluded": _cohort_target_stats(identity_excl_for_bias),
        "no_history": _cohort_target_stats(no_history_rows),
        "core_model_ready_min_5": _cohort_target_stats(core_ready_rows),
        "note": "Solo diagnostica selection bias; nessuna correzione automatica del dataset.",
    }
    phases["bias_report_ms"] = round((time.perf_counter() - t_bias) * 1000.0, 2)

    feature_definitions = []
    for spec in FEATURE_SPECS:
        key = spec["feature_key"]
        status = spec["recommended_status"]
        if key in XG_FEATURE_KEYS and status not in ("optional_enrichment", "conditional_enrichment"):
            status = "optional_enrichment"
        feature_definitions.append(
            {
                "feature_key": key,
                "pillar": spec["pillar"],
                "description": spec["description"],
                "recommended_status": status,
                "pre_match_safe": bool(spec.get("pre_match_safe")),
                "is_xg": key in XG_FEATURE_KEYS,
                "is_core": key in CORE_FEATURE_KEYS,
            }
        )
    if any(f["is_xg"] and f["recommended_status"] == "exclude_low_coverage" for f in feature_definitions):
        warnings.append("xg_exclude_low_coverage_unexpected")

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    rows_processed = len(fixtures)
    fixtures_per_second = round(rows_processed / (elapsed_ms / 1000.0), 2) if elapsed_ms > 0 else None

    return {
        "version": VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
        },
        "rows_initial": rows_initial,
        "deduplication": {
            "duplicates_provider_removed": dedupe_report["duplicates_provider_removed"],
            "duplicates_composite_removed": dedupe_report["duplicates_composite_removed"],
            "rows_after_provider": dedupe_report["rows_after_provider"],
            "rows_after_composite": dedupe_report["rows_after_composite"],
            "duplicate_groups_count": len(dedupe_report.get("duplicate_groups") or []),
            # gruppi completi solo in internal (export summary li omette)
            "duplicate_groups": dedupe_report.get("duplicate_groups") or [],
        },
        "dataset_rows": dataset_rows,
        "identity_excluded": identity_excluded,
        "identity_fail_by_reason": dict(identity_fail_by_reason),
        "identity_fail_by_month": dict(sorted(identity_fail_by_month.items())),
        "identity_fail_by_comp": dict(
            sorted(identity_fail_by_comp.items(), key=lambda x: (-x[1], x[0]))[:60]
        ),
        "identity_fail_by_country": dict(
            sorted(identity_fail_by_country.items(), key=lambda x: (-x[1], x[0]))[:40]
        ),
        "identity_fail_goals_mean": _mean(identity_fail_goals),
        "cohort_ids": cohort_ids,
        "cohort_counts": {k: len(v) for k, v in cohort_ids.items()},
        "history_quality": history_counts,
        "xg_cohorts": xg_cohorts,
        "paired_ids": paired_ids,
        "paired_targets": paired_targets,
        "fixture_ids_hash": fixture_ids_hash,
        "targets_hash": targets_hash,
        "paired_first_kickoff": first_kickoff,
        "paired_last_kickoff": last_kickoff,
        "exclusion_bias_report": exclusion_bias_report,
        "feature_definitions": feature_definitions,
        "warnings": warnings,
        "debug_samples": debug_samples,
        "phases": phases,
        "elapsed_ms": elapsed_ms,
        "rows_processed": rows_processed,
        "fixtures_per_second": fixtures_per_second,
        "index_sizes": {
            "history_index_teams": indexes.history_index_teams,
            "today_index_local_keys": indexes.today_index_local_keys,
            "xg_index_teams": indexes.xg_index_teams,
            "team_names": len(indexes.team_name_by_id),
            "competition_names": len(indexes.competition_name_by_id),
        },
        "v4_version": V4_VERSION,
    }


def build_goal_intensity_v5_dataset_summary_from_internal(internal: dict[str, Any]) -> dict[str, Any]:
    t_sum = time.perf_counter()
    rows = internal["dataset_rows"]
    preview = rows[:_PREVIEW_MAX_ROWS]
    dedupe = internal["deduplication"]
    paired_count = len(internal["paired_ids"])

    payload = {
        "status": "ok",
        "version": VERSION,
        "filters": internal["filters"],
        "dataset_summary": {
            "rows_initial": internal["rows_initial"],
            "rows_after_provider_dedupe": dedupe["rows_after_provider"],
            "rows_after_composite_dedupe": dedupe["rows_after_composite"],
            "rows_feature_safe": len(rows),
            "rows_identity_excluded": len(internal["identity_excluded"]),
            "cohort_counts": internal["cohort_counts"],
            "v4_unchanged": True,
            "v4_version": internal["v4_version"],
            "no_v5_formula": True,
            "preview_rows": len(preview),
            "preview_note": "Anteprima limitata a 100 righe. Gli export completi vengono generati dal backend.",
        },
        "deduplication": {
            "duplicates_provider_removed": dedupe["duplicates_provider_removed"],
            "duplicates_composite_removed": dedupe["duplicates_composite_removed"],
            "rows_after_provider": dedupe["rows_after_provider"],
            "rows_after_composite": dedupe["rows_after_composite"],
            "duplicate_groups_count": dedupe["duplicate_groups_count"],
        },
        "identity_diagnostics": {
            "identity_excluded_count": len(internal["identity_excluded"]),
            "by_reason": internal["identity_fail_by_reason"],
            "by_month": internal["identity_fail_by_month"],
            "by_competition_id": internal["identity_fail_by_comp"],
            "by_country": internal["identity_fail_by_country"],
            "mean_target_total_goals_ft": internal["identity_fail_goals_mean"],
        },
        "exclusion_bias_report": internal["exclusion_bias_report"],
        "history_quality": internal["history_quality"],
        "xg_cohorts": internal["xg_cohorts"],
        "paired_xg_readiness": {
            "paired_fixture_count": paired_count,
            "paired_comparison_possible": paired_count > 0,
            "minimum_recommended_sample_reached": paired_count >= _PAIRED_XG_MIN_SAMPLE,
            "same_fixture_ids": True,
            "same_targets": True,
            "first_kickoff": internal["paired_first_kickoff"],
            "last_kickoff": internal["paired_last_kickoff"],
            "fixture_ids_hash": internal["fixture_ids_hash"],
            "targets_hash": internal["targets_hash"],
            "note": "Stessa coorte per confronto futuro con/senza xG; hash SHA-256 senza array duplicati.",
        },
        "feature_definitions": internal["feature_definitions"],
        "dataset_preview_rows": preview,
        "warnings": list(internal["warnings"]),
    }

    summary_build_ms = round((time.perf_counter() - t_sum) * 1000.0, 2)
    phases = dict(internal["phases"])
    phases["summary_build_ms"] = summary_build_ms

    payload["performance"] = {
        "elapsed_ms": internal["elapsed_ms"],
        "rows_processed": internal["rows_processed"],
        "fixtures_per_second": internal["fixtures_per_second"],
        "response_preview_rows": len(preview),
        "estimated_full_dataset_rows": len(rows),
        "response_payload_bytes": 0,
        "db_query_phases": {
            "cohort_ms": phases.get("cohort_ms"),
            "today_load_ms": phases.get("today_load_ms"),
            "fts_lookup_ms": phases.get("fts_lookup_ms"),
            "preload_ms": phases.get("preload_ms"),
        },
        "calculation_phases": {
            "provider_dedupe_ms": phases.get("provider_dedupe_ms"),
            "composite_bucket_build_ms": phases.get("composite_bucket_build_ms"),
            "composite_cluster_ms": phases.get("composite_cluster_ms"),
            "feature_calculation_ms": phases.get("feature_calculation_ms"),
            "cohort_calculation_ms": phases.get("cohort_calculation_ms"),
            "bias_report_ms": phases.get("bias_report_ms"),
            "summary_build_ms": summary_build_ms,
        },
        "index_sizes": internal["index_sizes"],
    }

    encoded = json.dumps(payload, default=str, separators=(",", ":"))
    payload_bytes = len(encoded.encode("utf-8"))
    payload["performance"]["response_payload_bytes"] = payload_bytes
    if payload_bytes > _SUMMARY_PAYLOAD_SOFT_LIMIT_BYTES:
        payload["warnings"].append("summary_payload_exceeds_2mb_soft_limit")

    logger.info(
        "goal_intensity_v5_dataset completed rows_initial=%s rows_safe=%s elapsed_ms=%s payload_bytes=%s fixtures_per_second=%s",
        internal["rows_initial"],
        len(rows),
        internal["elapsed_ms"],
        payload_bytes,
        internal["fixtures_per_second"],
    )
    return payload


def build_goal_intensity_v5_dataset(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Payload HTTP compatto v1_1 (preview ≤100)."""
    internal = build_goal_intensity_v5_dataset_internal(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return build_goal_intensity_v5_dataset_summary_from_internal(internal)


def stream_goal_intensity_v5_dataset_csv(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    kind: ExportKind = "all",
) -> Iterator[str]:
    internal = build_goal_intensity_v5_dataset_internal(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    selected = filter_dataset_rows_by_kind(internal["dataset_rows"], kind)
    yield "\ufeff"
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    for row in selected:
        writer.writerow(_row_to_csv_dict(row))
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def stream_goal_intensity_v5_dataset_summary_json(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> Iterator[str]:
    payload = build_goal_intensity_v5_dataset(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    yield json.dumps(payload, default=str, ensure_ascii=False)


def dataset_export_filename(
    *,
    kind: ExportKind | Literal["summary"],
    date_from: date,
    date_to: date,
) -> str:
    from_s = date_from.isoformat()
    to_s = date_to.isoformat()
    if kind == "summary":
        return f"cecchino_goal_intensity_v5_dataset_summary_{from_s}_{to_s}.json"
    map_kind = {
        "all": "all",
        "core_min5": "core_min5",
        "core_min10": "core_min10",
        "xg_paired": "xg_paired",
    }
    return f"cecchino_goal_intensity_v5_dataset_{map_kind[kind]}_{from_s}_{to_s}.csv"


def _log_progress(done: int, total: int, t_calc_start: float) -> None:
    elapsed = max(time.perf_counter() - t_calc_start, 1e-9)
    rate = done / elapsed
    logger.info(
        "goal_intensity_v5_dataset progress %s/%s (%.1f fx/s)",
        done,
        total,
        rate,
    )
