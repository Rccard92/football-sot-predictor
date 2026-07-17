"""Audit storico Intensità Goal v5 — Fase 1A.3 (preload indici, loop DB-free)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_fixture_identity_consistency import (
    build_historical_fixture_identity_consistency,
)
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_audit_common import (
    EXCLUDED_ADVANCED,
    FEATURE_SPECS,
    PILLAR_DEFENSIVE,
    PILLAR_OFFENSIVE,
    PILLAR_STABILITY,
    PILLAR_TEMPO,
    PILLARS,
    append_debug_sample,
    current_v4_inventory,
    dedupe_local_fixtures,
    descriptive_stats,
    empty_pillar_coverage,
    extract_features_from_indexes,
    finished_local_fixtures_in_kickoff_range,
    load_today_snapshots_for_fixtures,
    match_today_snapshot_indexed,
    month_key_from_dt,
    months_in_range,
    pct,
    primary_keys_for_pillar,
    sanitize_exception_message,
    snapshot_time_status,
)
from app.services.cecchino.cecchino_goal_intensity_v5_audit_indexes import preload_audit_indexes
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

logger = logging.getLogger(__name__)

VERSION = "cecchino_goal_intensity_v5_audit_v1_3"
_PROGRESS_EVERY = 500

AUDIT_QUALITY_RULE = (
    "feature_safe_rate_pct = pct(row_feature_safe, rows_checked); "
    "unusable: rate<20% OR identity_check_errors>0 OR (fixtures>0 e competitions==0) "
    "OR (safe>0 e coverage tutte 0); "
    "usable: rate>=70% AND sample_size_mean>0 AND competitions>0 AND no identity_check_errors "
    "AND non coverage tutte 0; "
    "degraded: resto; audit_usable=(audit_quality==usable)"
)


def build_goal_intensity_v5_audit(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    warnings: list[str] = []

    t_cohort = time.perf_counter()
    raw_fixtures = finished_local_fixtures_in_kickoff_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    fixtures, duplicates_removed = dedupe_local_fixtures(raw_fixtures)
    cohort_ms = round((time.perf_counter() - t_cohort) * 1000.0, 2)

    t_today = time.perf_counter()
    today_candidates = load_today_snapshots_for_fixtures(db, fixtures)
    today_load_ms = round((time.perf_counter() - t_today) * 1000.0, 2)

    t_preload = time.perf_counter()
    indexes = preload_audit_indexes(db, fixtures, today_candidates)
    preload_ms = round((time.perf_counter() - t_preload) * 1000.0, 2)

    anti: dict[str, Any] = {
        "rows_checked": 0,
        "rows_passed": 0,
        "rows_failed": 0,
        "row_feature_safe": 0,
        "static_identity_verified": 0,
        "static_identity_failed": 0,
        "static_identity_unavailable": 0,
        "snapshot_time_verified": 0,
        "snapshot_time_unknown": 0,
        "xg_anti_leakage_verified": 0,
        # alias retrocompatibilità
        "identity_verified": 0,
        "identity_not_available": 0,
        "identity_failed": 0,
        "fixture_identity_mismatch": 0,
        "identity_check_errors": 0,
        "missing_local_fixture_id": 0,
        "local_fixture_not_found": 0,
        "local_fixture_missing_teams": 0,
        "local_fixture_missing_kickoff": 0,
        "cutoff_mismatch": 0,
        "current_fixture_included": 0,
        "future_fixture_included": 0,
        "xg_from_today_snapshot": 0,
        "xg_from_fixture_team_stats": 0,
        "xg_missing": 0,
        "xg_snapshot_cutoff_mismatch": 0,
        "xg_source_all_checked": {
            "today_snapshot": 0,
            "fixture_team_stats": 0,
            "missing": 0,
            "snapshot_cutoff_mismatch": 0,
        },
        "xg_source_feature_safe": {
            "today_snapshot": 0,
            "fixture_team_stats": 0,
            "missing": 0,
            "snapshot_cutoff_mismatch": 0,
        },
        "targets_all_finished": 0,
        "targets_feature_safe": 0,
        "warnings": [],
    }

    exclusion_reasons: dict[str, int] = defaultdict(int)
    debug_samples: dict[str, list[dict[str, Any]]] = {}

    feature_values: dict[str, list[float]] = {s["feature_key"]: [] for s in FEATURE_SPECS}
    feature_available: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}
    feature_missing: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}
    feature_invalid: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}

    safe_rows_meta: list[dict[str, Any]] = []
    today_snapshots_matched = 0
    today_snapshots_missing = 0

    target_total_goals_available = 0
    target_ge2 = 0
    target_ge3 = 0
    target_btts = 0
    competitions: set[int] = set()
    countries: set[str] = set()
    by_month: dict[str, int] = defaultdict(int)

    t_calc = time.perf_counter()
    total_targets = len(fixtures)

    for i, local in enumerate(fixtures, start=1):
        anti["rows_checked"] += 1
        lid = int(local.id)
        api_id = int(local.api_fixture_id) if local.api_fixture_id is not None else None
        ko = ensure_datetime_utc(local.kickoff_at, field_name="local.kickoff_at")
        ko_iso = safe_isoformat(ko, field_name="local.kickoff_at") if ko else None

        if local.home_team_id is None or local.away_team_id is None:
            anti["local_fixture_missing_teams"] += 1
            anti["rows_failed"] += 1
            exclusion_reasons["missing_teams"] += 1
            append_debug_sample(
                debug_samples,
                "missing_teams",
                today_fixture_id=None,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=ko_iso,
            )
            continue

        if ko is None:
            anti["local_fixture_missing_kickoff"] += 1
            anti["rows_failed"] += 1
            exclusion_reasons["missing_kickoff"] += 1
            append_debug_sample(
                debug_samples,
                "missing_kickoff",
                today_fixture_id=None,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=None,
            )
            continue

        if local.goals_home is None or local.goals_away is None:
            anti["rows_failed"] += 1
            exclusion_reasons["missing_result"] += 1
            append_debug_sample(
                debug_samples,
                "missing_result",
                today_fixture_id=None,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=ko_iso,
            )
            continue

        gh, ga = int(local.goals_home), int(local.goals_away)
        target_total_goals_available += 1
        anti["targets_all_finished"] += 1
        if gh + ga >= 2:
            target_ge2 += 1
        if gh + ga >= 3:
            target_ge3 += 1
        if gh > 0 and ga > 0:
            target_btts += 1

        today_row = match_today_snapshot_indexed(
            local,
            indexes.today_by_local_fixture_id,
            indexes.today_by_provider_fixture_id,
        )
        today_id = int(today_row.id) if today_row is not None else None
        snap_status = snapshot_time_status(today_row, ko)
        if snap_status == "snapshot_time_verified":
            anti["snapshot_time_verified"] += 1
        else:
            anti["snapshot_time_unknown"] += 1

        if today_row is None:
            today_snapshots_missing += 1
            today_snapshot_status = "missing"
        else:
            today_snapshots_matched += 1
            today_snapshot_status = "matched"

        identity_status = "static_identity_unavailable"
        identity_mismatch = False
        identity_check_error = False
        if today_row is not None:
            try:
                home_name = indexes.team_name_by_id.get(int(local.home_team_id))
                away_name = indexes.team_name_by_id.get(int(local.away_team_id))
                identity = build_historical_fixture_identity_consistency(
                    today_row=today_row,
                    local_fixture=local,
                    local_home_team_name=home_name,
                    local_away_team_name=away_name,
                )
                st = identity.get("status")
                if st == "static_identity_failed":
                    identity_mismatch = True
                    identity_status = "static_identity_failed"
                elif st == "static_identity_verified":
                    identity_status = "static_identity_verified"
                else:
                    identity_status = "static_identity_unavailable"
                # Status/score diagnostici: non bloccanti
                for w in identity.get("warnings") or []:
                    if w in ("today_upcoming_vs_local_ft", "today_no_score_vs_local_score", "today_local_status_mismatch", "today_local_score_mismatch"):
                        append_debug_sample(
                            debug_samples,
                            w,
                            today_fixture_id=today_id,
                            local_fixture_id=lid,
                            provider_fixture_id=api_id,
                            kickoff=ko_iso,
                        )
            except Exception as exc:
                identity_check_error = True
                identity_status = "static_identity_failed"
                exclusion_reasons["identity_check_error"] += 1
                append_debug_sample(
                    debug_samples,
                    "identity_check_error",
                    today_fixture_id=today_id,
                    local_fixture_id=lid,
                    provider_fixture_id=api_id,
                    kickoff=ko_iso,
                    exception_type=type(exc).__name__,
                    exception_message=sanitize_exception_message(exc),
                )

        features, leak_meta = extract_features_from_indexes(local, today_row, indexes)

        failed = False
        if identity_mismatch:
            anti["static_identity_failed"] += 1
            anti["fixture_identity_mismatch"] += 1
            anti["identity_failed"] += 1
            exclusion_reasons["identity_mismatch"] += 1
            append_debug_sample(
                debug_samples,
                "identity_mismatch",
                today_fixture_id=today_id,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=ko_iso,
            )
            failed = True
        elif identity_check_error:
            anti["static_identity_failed"] += 1
            anti["identity_check_errors"] += 1
            anti["identity_failed"] += 1
            if "fixture_identity_check_failed" not in anti["warnings"]:
                anti["warnings"].append("fixture_identity_check_failed")
            failed = True
        elif identity_status == "static_identity_verified":
            anti["static_identity_verified"] += 1
            anti["identity_verified"] += 1
        else:
            anti["static_identity_unavailable"] += 1
            anti["identity_not_available"] += 1

        if leak_meta.get("cutoff_mismatch"):
            anti["cutoff_mismatch"] += 1
            anti["xg_snapshot_cutoff_mismatch"] += 1
            exclusion_reasons["cutoff_mismatch"] += 1
            append_debug_sample(
                debug_samples,
                "cutoff_mismatch",
                today_fixture_id=today_id,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=ko_iso,
            )
            failed = True
        if leak_meta.get("current_fixture_included"):
            anti["current_fixture_included"] += 1
            exclusion_reasons["current_fixture_included"] += 1
            failed = True
        if leak_meta.get("future_fixture_included"):
            anti["future_fixture_included"] += 1
            exclusion_reasons["future_source_fixture"] += 1
            append_debug_sample(
                debug_samples,
                "future_source_fixture",
                today_fixture_id=today_id,
                local_fixture_id=lid,
                provider_fixture_id=api_id,
                kickoff=ko_iso,
            )
            failed = True

        xg_src = str(leak_meta.get("xg_source") or "missing")
        if xg_src == "today_snapshot":
            anti["xg_from_today_snapshot"] += 1
            anti["xg_source_all_checked"]["today_snapshot"] += 1
        elif xg_src == "fixture_team_stats":
            anti["xg_from_fixture_team_stats"] += 1
            anti["xg_source_all_checked"]["fixture_team_stats"] += 1
        elif xg_src == "snapshot_cutoff_mismatch":
            anti["xg_source_all_checked"]["snapshot_cutoff_mismatch"] += 1
        else:
            anti["xg_missing"] += 1
            anti["xg_source_all_checked"]["missing"] += 1

        if leak_meta.get("xg_anti_leakage_verified"):
            anti["xg_anti_leakage_verified"] += 1

        if failed:
            anti["rows_failed"] += 1
            if i % _PROGRESS_EVERY == 0 or i == total_targets:
                _log_progress(i, total_targets, t_calc)
            continue

        anti["rows_passed"] += 1
        anti["row_feature_safe"] += 1
        anti["targets_feature_safe"] += 1
        if xg_src in anti["xg_source_feature_safe"]:
            anti["xg_source_feature_safe"][xg_src] += 1
        else:
            anti["xg_source_feature_safe"]["missing"] += 1

        comp_id = int(local.competition_id) if local.competition_id is not None else None
        if comp_id is not None:
            competitions.add(comp_id)
        cname = indexes.country_by_competition_id.get(comp_id) if comp_id is not None else None
        if not cname and today_row is not None and getattr(today_row, "country_name", None):
            cname = str(today_row.country_name)
        if cname:
            countries.add(cname)
        by_month[month_key_from_dt(ko)] += 1

        safe_rows_meta.append(
            {
                "features": features,
                "sample_size": int(leak_meta.get("sample_size") or 0),
                "competition_id": comp_id,
                "country_name": cname,
                "month": month_key_from_dt(ko),
                "today_snapshot_status": today_snapshot_status,
                "identity_status": identity_status,
            }
        )

        for spec in FEATURE_SPECS:
            key = spec["feature_key"]
            val = features.get(key)
            if val is None:
                feature_missing[key] += 1
            else:
                feature_available[key] += 1
                feature_values[key].append(float(val))

        if i % _PROGRESS_EVERY == 0 or i == total_targets:
            _log_progress(i, total_targets, t_calc)

    calculation_ms = round((time.perf_counter() - t_calc) * 1000.0, 2)

    rows_safe = len(safe_rows_meta)
    if anti["rows_checked"] == 0:
        warnings.append("nessuna Fixture conclusa con risultato nel periodo kickoff")
    if anti["identity_check_errors"] > 0:
        warnings.append("fixture_identity_check_failed")

    feature_inventory: list[dict[str, Any]] = []
    for spec in FEATURE_SPECS:
        key = spec["feature_key"]
        stats = descriptive_stats(feature_values[key])
        avail = feature_available[key]
        missing = feature_missing[key]
        total = rows_safe
        status = spec["recommended_status"]
        if total > 0 and pct(avail, total) < 20.0 and status in ("primary_candidate", "secondary_candidate"):
            status = "exclude_low_coverage"
        feature_inventory.append(
            {
                "feature_key": key,
                "pillar": spec["pillar"],
                "description": spec["description"],
                "source_table_or_payload": spec["source_table_or_payload"],
                "source_version": spec["source_version"],
                "value_type": spec["value_type"],
                "rows_total": total,
                "rows_available": avail,
                "rows_missing": missing,
                "coverage_pct": pct(avail, total),
                "valid_numeric_rows": stats["valid_numeric_rows"],
                "invalid_rows": feature_invalid[key],
                "min": stats["min"],
                "max": stats["max"],
                "mean": stats["mean"],
                "median": stats["median"],
                "standard_deviation": stats["standard_deviation"],
                "p10": stats["p10"],
                "p25": stats["p25"],
                "p75": stats["p75"],
                "p90": stats["p90"],
                "zero_rate": stats["zero_rate"],
                "outlier_rate": stats["outlier_rate"],
                "pre_match_safe": bool(spec.get("pre_match_safe")),
                "leakage_risk": "low" if spec.get("pre_match_safe") else "high",
                "redundancy_family": spec["redundancy_family"],
                "recommended_status": status,
            }
        )

    temporal_distribution: dict[str, Any] = {}
    for mk in months_in_range(date_from, date_to):
        count = by_month.get(mk, 0)
        if count == 0:
            temporal_distribution[mk] = {"count": 0, "note": "no_local_fixtures_in_month"}
        else:
            temporal_distribution[mk] = {"count": count}

    pillar_coverage: dict[str, Any] = {}
    for pillar in PILLARS:
        primaries = primary_keys_for_pillar(pillar)
        fixtures_total = rows_safe
        any_feat = 0
        all_primary = 0
        sample_sizes: list[int] = []
        comps: set[int] = set()
        ctrs: set[str] = set()
        temporal: dict[str, int] = defaultdict(int)
        pillar_warnings: list[str] = []

        for meta in safe_rows_meta:
            feats = meta["features"]
            present = [k for k in primaries if feats.get(k) is not None]
            if any(feats.get(s["feature_key"]) is not None for s in FEATURE_SPECS if s["pillar"] == pillar):
                any_feat += 1
            if primaries and len(present) == len(primaries):
                all_primary += 1
            sample_sizes.append(int(meta.get("sample_size") or 0))
            if meta.get("competition_id") is not None:
                comps.add(int(meta["competition_id"]))
            if meta.get("country_name"):
                ctrs.add(str(meta["country_name"]))
            temporal[str(meta.get("month") or "unknown")] += 1

        none_count = fixtures_total - any_feat
        partial = any_feat - all_primary
        cov = empty_pillar_coverage()
        cov.update(
            {
                "fixtures_total": fixtures_total,
                "fixtures_with_any_feature": any_feat,
                "fixtures_with_all_primary": all_primary,
                "coverage_complete_pct": pct(all_primary, fixtures_total),
                "coverage_partial_pct": pct(partial, fixtures_total),
                "coverage_none_pct": pct(none_count, fixtures_total),
                "competitions": len(comps),
                "countries": len(ctrs),
                "temporal_distribution": dict(sorted(temporal.items())),
                "sample_size_mean": round(sum(sample_sizes) / len(sample_sizes), 2) if sample_sizes else None,
                "sample_size_min": min(sample_sizes) if sample_sizes else None,
                "warnings": pillar_warnings,
                "primary_feature_keys": primaries,
            }
        )
        if fixtures_total > 0 and cov["coverage_complete_pct"] < 30:
            pillar_warnings.append("copertura primaria completa sotto il 30%")
            cov["warnings"] = pillar_warnings
        pillar_coverage[pillar] = cov

    inv_by_key = {f["feature_key"]: f for f in feature_inventory}

    def _rec_for_pillar(pillar: str) -> dict[str, Any]:
        primary = [
            f["feature_key"]
            for f in feature_inventory
            if f["pillar"] == pillar and f["recommended_status"] == "primary_candidate"
        ]
        secondary = [
            f["feature_key"]
            for f in feature_inventory
            if f["pillar"] == pillar and f["recommended_status"] == "secondary_candidate"
        ]
        excluded = [
            f["feature_key"]
            for f in feature_inventory
            if f["pillar"] == pillar
            and f["recommended_status"]
            in ("exclude_low_coverage", "exclude_leakage", "exclude_redundant", "unavailable")
        ]
        coverages = [inv_by_key[k]["coverage_pct"] for k in primary if k in inv_by_key]
        return {
            "primary_features": primary,
            "secondary_features": secondary,
            "excluded_features": excluded,
            "motivations": {
                "primary": "copertura e semantica allineate al fenomeno del pilastro",
                "secondary": "supporto o ridondanza controllata",
                "excluded": "copertura bassa, leakage o ridondanza",
            },
            "expected_coverage_pct": round(sum(coverages) / len(coverages), 2) if coverages else 0.0,
            "dependencies": ["fixtures (storico FT)", "xg_profiles_json / FixtureTeamStat"],
            "risks": ["copertura xG non uniforme", "sample size rolling basso a inizio stagione"],
            "phase_1b_1c_needed": [
                "associazione feature→target total_goals_ft",
                "scelta misura stabilità (std vs MAD vs CV)",
                "ridondanza famiglie",
            ],
        }

    sample_means = [
        pillar_coverage[p]["sample_size_mean"]
        for p in PILLARS
        if pillar_coverage[p].get("sample_size_mean") is not None
    ]
    overall_sample_mean = round(sum(sample_means) / len(sample_means), 2) if sample_means else 0.0

    history_cov = [
        f["coverage_pct"]
        for f in feature_inventory
        if f["source_version"] == "fixture_history"
    ]
    feature_safe_rate_pct = pct(anti["row_feature_safe"], anti["rows_checked"])
    all_coverage_zero = rows_safe > 0 and all(f["coverage_pct"] == 0 for f in feature_inventory)
    no_competitions = len(fixtures) > 0 and len(competitions) == 0
    identity_errors = anti["identity_check_errors"] > 0

    if (
        feature_safe_rate_pct < 20.0
        or identity_errors
        or no_competitions
        or all_coverage_zero
    ):
        audit_quality = "unusable"
    elif (
        feature_safe_rate_pct >= 70.0
        and overall_sample_mean > 0
        and len(competitions) > 0
        and not identity_errors
        and not all_coverage_zero
    ):
        audit_quality = "usable"
    else:
        audit_quality = "degraded"

    audit_usable = audit_quality == "usable"

    dataset_summary = {
        "local_fixtures_raw": len(raw_fixtures),
        "local_fixtures_deduped": len(fixtures),
        "duplicates_removed": duplicates_removed,
        "today_snapshots_matched": today_snapshots_matched,
        "today_snapshots_missing": today_snapshots_missing,
        "leakage_safe_rows": rows_safe,
        "row_feature_safe": anti["row_feature_safe"],
        "feature_safe_rate_pct": feature_safe_rate_pct,
        "targets_all_finished": anti["targets_all_finished"],
        "targets_feature_safe": anti["targets_feature_safe"],
        "competitions": len(competitions),
        "countries": len(countries),
        "temporal_distribution": temporal_distribution,
        "sample_size_mean": overall_sample_mean,
        "audit_quality": audit_quality,
        "audit_quality_rule": AUDIT_QUALITY_RULE,
        "audit_usable": audit_usable,
        "cohort_basis": "fixture_kickoff_at",
        "cohort_notes": {
            "targets": "Fixture FT con risultato nel range kickoff",
            "features": "Solo righe row_feature_safe (identity statica + anti-leakage)",
        },
        "targets": {
            "total_goals_ft_available": target_total_goals_available,
            "goals_ge_2_rate_pct": pct(target_ge2, target_total_goals_available),
            "goals_ge_3_rate_pct": pct(target_ge3, target_total_goals_available),
            "btts_ft_rate_pct": pct(target_btts, target_total_goals_available),
            "note": "I target diagnostici non sono output del modulo Intensità.",
        },
        "rows_raw": len(raw_fixtures),
        "rows_deduped": len(fixtures),
        "finished_fixtures": len(fixtures),
        "finished_with_result": target_total_goals_available,
    }

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    rows_processed = anti["rows_checked"]
    fixtures_per_second = round(rows_processed / (elapsed_ms / 1000.0), 2) if elapsed_ms > 0 else None

    return {
        "status": "ok",
        "version": VERSION,
        "filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "competition_id": competition_id,
        },
        "current_v4_inventory": current_v4_inventory(),
        "dataset_summary": dataset_summary,
        "pillar_coverage": pillar_coverage,
        "feature_inventory": feature_inventory,
        "excluded_advanced_features": EXCLUDED_ADVANCED,
        "anti_leakage": anti,
        "exclusion_reasons": dict(exclusion_reasons),
        "debug_samples": debug_samples,
        "api_availability": {
            "stable_database": {
                "category": 1,
                "items": ["fixtures", "fixture_team_stats", "competitions"],
            },
            "payload_or_cache": {
                "category": 2,
                "items": ["cecchino_today_fixtures.xg_profiles_json"],
            },
            "requires_new_api_calls": {"category": 4, "items": [], "used_in_audit": False},
            "unavailable": {"category": 5, "items": [e["feature_key"] for e in EXCLUDED_ADVANCED]},
            "model_core_preference": "categorie 1 e 2",
        },
        "legacy_dependencies": {
            "v4_module": "cecchino_goal_intensity_analysis",
            "v4_version": V4_VERSION,
            "goal_engine": "cecchino_goal_poisson_v2 + fixture_history contexts",
            "non_consumers": ["ICM", "Balance v5", "Segnali", "KPI"],
        },
        "potential_conflicts": [
            {
                "id": "v4_single_quantity_vs_four_pillars",
                "detail": "v4 riduce tutto a expected_goals_total; v5 richiede quattro letture indipendenti",
            },
        ],
        "interpretative_questions": [
            "Quale misura di stabilità (std, MAD, CV) è più robusta a sample size bassi?",
            "Come mantenere Over 2.5/GG come feature senza farle diventare output di mercato?",
        ],
        "implementation_recommendation": {
            "note": "Nessuna formula numerica né pesi in Fase 1A.",
            "pillars": {
                PILLAR_OFFENSIVE: _rec_for_pillar(PILLAR_OFFENSIVE),
                PILLAR_DEFENSIVE: _rec_for_pillar(PILLAR_DEFENSIVE),
                PILLAR_TEMPO: _rec_for_pillar(PILLAR_TEMPO),
                PILLAR_STABILITY: _rec_for_pillar(PILLAR_STABILITY),
            },
            "no_single_index": True,
            "no_manual_weights": True,
            "keep_v4_as_legacy_reference": True,
            "history_feature_max_coverage_pct": max(history_cov) if history_cov else 0.0,
        },
        "warnings": warnings,
        "performance": {
            "elapsed_ms": elapsed_ms,
            "rows_processed": rows_processed,
            "calculation_ms": calculation_ms,
            "fixtures_per_second": fixtures_per_second,
            "db_query_phases": {
                "cohort_ms": cohort_ms,
                "today_load_ms": today_load_ms,
                "preload_ms": preload_ms,
                **indexes.timings_ms,
            },
            "index_sizes": {
                "history_index_teams": indexes.history_index_teams,
                "today_index_local_keys": indexes.today_index_local_keys,
                "today_index_provider_keys": indexes.today_index_provider_keys,
                "xg_index_teams": indexes.xg_index_teams,
                "team_names": len(indexes.team_name_by_id),
                "countries": len(indexes.country_by_competition_id),
            },
        },
    }


def _log_progress(done: int, total: int, t_calc_start: float) -> None:
    elapsed = max(time.perf_counter() - t_calc_start, 1e-9)
    rate = done / elapsed
    logger.info(
        "goal_intensity_v5_audit progress elaborated=%s total=%s elapsed_s=%.1f rate=%.1f/s",
        done,
        total,
        elapsed,
        rate,
    )
