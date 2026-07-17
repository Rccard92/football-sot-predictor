"""Audit storico Intensità Goal v5 — Fase 1A.2 (Fixture kickoff, read-only)."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.cecchino.cecchino_fixture_identity_consistency import build_fixture_identity_consistency
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
    extract_features_for_local_fixture,
    finished_local_fixtures_in_kickoff_range,
    load_today_snapshots_for_fixtures,
    match_today_snapshot,
    month_key_from_dt,
    months_in_range,
    pct,
    primary_keys_for_pillar,
    resolve_country,
    resolve_team_names,
    sanitize_exception_message,
)
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat

VERSION = "cecchino_goal_intensity_v5_audit_v1_1"


def build_goal_intensity_v5_audit(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    warnings: list[str] = []

    raw_fixtures = finished_local_fixtures_in_kickoff_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    fixtures, duplicates_removed = dedupe_local_fixtures(raw_fixtures)

    today_candidates = load_today_snapshots_for_fixtures(db, fixtures)

    anti: dict[str, Any] = {
        "rows_checked": 0,
        "rows_passed": 0,
        "rows_failed": 0,
        "row_feature_safe": 0,
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

    for local in fixtures:
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
        if gh + ga >= 2:
            target_ge2 += 1
        if gh + ga >= 3:
            target_ge3 += 1
        if gh > 0 and ga > 0:
            target_btts += 1

        today_row = match_today_snapshot(local, today_candidates)
        today_id = int(today_row.id) if today_row is not None else None
        if today_row is None:
            today_snapshots_missing += 1
            today_snapshot_status = "missing"
        else:
            today_snapshots_matched += 1
            today_snapshot_status = "matched"

        # Identity: only when Today present; keyword-only
        identity_status = "identity_not_available"
        identity_mismatch = False
        identity_check_error = False
        if today_row is not None:
            try:
                home_name, away_name = resolve_team_names(db, local)
                output = today_row.cecchino_output_json if isinstance(today_row.cecchino_output_json, dict) else None
                ege = None
                if isinstance(output, dict):
                    maybe = output.get("expected_goal_engine_diagnostics")
                    if isinstance(maybe, dict):
                        ege = maybe
                identity = build_fixture_identity_consistency(
                    today_row=today_row,
                    local_fixture=local,
                    cecchino_output=output,
                    expected_goal_diagnostics=ege,
                    local_home_team_name=home_name,
                    local_away_team_name=away_name,
                )
                if identity.get("status") == "inconsistent":
                    identity_mismatch = True
                    identity_status = "identity_failed"
                else:
                    identity_status = "identity_verified"
            except Exception as exc:
                identity_check_error = True
                identity_status = "identity_failed"
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

        features, leak_meta = extract_features_for_local_fixture(db, local, today_row)

        failed = False
        if identity_mismatch:
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
            anti["identity_check_errors"] += 1
            anti["identity_failed"] += 1
            if "fixture_identity_check_failed" not in anti["warnings"]:
                anti["warnings"].append("fixture_identity_check_failed")
            failed = True
        elif identity_status == "identity_verified":
            anti["identity_verified"] += 1
        else:
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

        xg_src = leak_meta.get("xg_source")
        if xg_src == "today_snapshot":
            anti["xg_from_today_snapshot"] += 1
        elif xg_src == "fixture_team_stats":
            anti["xg_from_fixture_team_stats"] += 1
        elif xg_src == "snapshot_cutoff_mismatch":
            pass  # already counted
        else:
            anti["xg_missing"] += 1

        if failed:
            anti["rows_failed"] += 1
            continue

        # Feature-safe even without Today identity
        anti["rows_passed"] += 1
        anti["row_feature_safe"] += 1

        comp_id = int(local.competition_id) if local.competition_id is not None else None
        if comp_id is not None:
            competitions.add(comp_id)
        cname = resolve_country(db, comp_id)
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

    # Temporal: include empty months in requested range
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
    audit_usable = True
    if rows_safe > 0 and all(f["coverage_pct"] == 0 for f in feature_inventory):
        audit_usable = False
    if len(fixtures) > 0 and len(competitions) == 0:
        audit_usable = False
    if rows_safe > 0 and overall_sample_mean == 0:
        audit_usable = False
    if anti["identity_check_errors"] > 0:
        audit_usable = False

    dataset_summary = {
        "local_fixtures_raw": len(raw_fixtures),
        "local_fixtures_deduped": len(fixtures),
        "duplicates_removed": duplicates_removed,
        "today_snapshots_matched": today_snapshots_matched,
        "today_snapshots_missing": today_snapshots_missing,
        "leakage_safe_rows": rows_safe,
        "row_feature_safe": anti["row_feature_safe"],
        "competitions": len(competitions),
        "countries": len(countries),
        "temporal_distribution": temporal_distribution,
        "sample_size_mean": overall_sample_mean,
        "audit_usable": audit_usable,
        "cohort_basis": "fixture_kickoff_at",
        "targets": {
            "total_goals_ft_available": target_total_goals_available,
            "goals_ge_2_rate_pct": pct(target_ge2, target_total_goals_available),
            "goals_ge_3_rate_pct": pct(target_ge3, target_total_goals_available),
            "btts_ft_rate_pct": pct(target_btts, target_total_goals_available),
            "note": "I target diagnostici non sono output del modulo Intensità.",
        },
        # retrocompatibilità chiavi 1A
        "rows_raw": len(raw_fixtures),
        "rows_deduped": len(fixtures),
        "finished_fixtures": len(fixtures),
        "finished_with_result": target_total_goals_available,
    }

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

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
        "performance": {"elapsed_ms": elapsed_ms, "rows_processed": anti["rows_checked"]},
    }
