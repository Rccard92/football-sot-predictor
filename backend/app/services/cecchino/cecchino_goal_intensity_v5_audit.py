"""Audit storico Intensità Goal v5 — Fase 1A (read-only, nessuna formula produttiva)."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Fixture
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_draw_credibility_research_common import fixtures_in_range
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
    current_v4_inventory,
    dedupe_today_rows,
    descriptive_stats,
    empty_pillar_coverage,
    extract_row_features,
    is_finished_today,
    month_key,
    pct,
    primary_keys_for_pillar,
    resolve_ft_score,
)

VERSION = "cecchino_goal_intensity_v5_audit_v1"


def build_goal_intensity_v5_audit(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    warnings: list[str] = []

    raw_rows = fixtures_in_range(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        only_eligible=None,
    )
    deduped = dedupe_today_rows(raw_rows)

    anti = {
        "rows_checked": 0,
        "rows_passed": 0,
        "rows_failed": 0,
        "fixture_identity_mismatch": 0,
        "identity_check_errors": 0,
        "cutoff_mismatch": 0,
        "current_fixture_included": 0,
        "future_fixture_included": 0,
        "warnings": [],
    }

    # Collectors for inventory (only leakage-safe rows)
    feature_values: dict[str, list[float]] = {s["feature_key"]: [] for s in FEATURE_SPECS}
    feature_available: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}
    feature_missing: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}
    feature_invalid: dict[str, int] = {s["feature_key"]: 0 for s in FEATURE_SPECS}

    pillar_rows: dict[str, list[dict[str, Any]]] = {p: [] for p in PILLARS}
    safe_rows_meta: list[dict[str, Any]] = []

    finished_count = 0
    with_result = 0
    target_total_goals_available = 0
    target_ge2 = 0
    target_ge3 = 0
    target_btts = 0
    competitions: set[int] = set()
    countries: set[str] = set()
    by_month: dict[str, int] = defaultdict(int)

    for row in deduped:
        if not is_finished_today(row):
            continue
        finished_count += 1

        local: Fixture | None = None
        lid = getattr(row, "local_fixture_id", None)
        if lid is not None:
            try:
                local = db.get(Fixture, int(lid))
            except Exception:
                local = None

        gh, ga = resolve_ft_score(row, local)
        if gh is None or ga is None:
            continue
        with_result += 1
        total_goals = gh + ga
        target_total_goals_available += 1
        if total_goals >= 2:
            target_ge2 += 1
        if total_goals >= 3:
            target_ge3 += 1
        if gh > 0 and ga > 0:
            target_btts += 1

        # Identity check (read-only, fail-closed su eccezione)
        identity_mismatch = False
        identity_check_error = False
        if local is not None:
            try:
                identity = build_fixture_identity_consistency(row, local)
                if identity.get("status") == "inconsistent":
                    identity_mismatch = True
            except Exception:
                identity_check_error = True

        features, leak_meta, _priors = extract_row_features(db, row, local)

        anti["rows_checked"] += 1
        failed = False
        if identity_mismatch:
            anti["fixture_identity_mismatch"] += 1
            failed = True
        if identity_check_error:
            anti["identity_check_errors"] += 1
            if "fixture_identity_check_failed" not in anti["warnings"]:
                anti["warnings"].append("fixture_identity_check_failed")
            failed = True
        if leak_meta.get("cutoff_mismatch"):
            anti["cutoff_mismatch"] += 1
            failed = True
        if leak_meta.get("current_fixture_included"):
            anti["current_fixture_included"] += 1
            failed = True
        if leak_meta.get("future_fixture_included"):
            anti["future_fixture_included"] += 1
            failed = True

        if failed:
            anti["rows_failed"] += 1
            continue

        anti["rows_passed"] += 1

        if getattr(row, "competition_id", None) is not None:
            competitions.add(int(row.competition_id))
        cname = getattr(row, "country_name", None)
        if cname:
            countries.add(str(cname))
        by_month[month_key(getattr(row, "scan_date", None))] += 1

        sample_sizes = [
            len(leak_meta.get("source_fixture_ids") or []),
        ]
        row_meta = {
            "features": features,
            "sample_size": sample_sizes[0],
            "competition_id": getattr(row, "competition_id", None),
            "country_name": cname,
            "month": month_key(getattr(row, "scan_date", None)),
        }
        safe_rows_meta.append(row_meta)

        for spec in FEATURE_SPECS:
            key = spec["feature_key"]
            val = features.get(key)
            if val is None:
                feature_missing[key] += 1
            else:
                feature_available[key] += 1
                feature_values[key].append(float(val))

        for pillar in PILLARS:
            pillar_rows[pillar].append(row_meta)

    rows_safe = len(safe_rows_meta)
    if anti["rows_checked"] == 0:
        warnings.append("nessuna fixture conclusa con risultato nel periodo")
    if anti["rows_failed"] > 0:
        anti["warnings"].append("alcune righe escluse per anti-leakage o identity mismatch")

    # Feature inventory
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
        leakage_risk = "low" if spec.get("pre_match_safe") else "high"
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
                "leakage_risk": leakage_risk,
                "redundancy_family": spec["redundancy_family"],
                "recommended_status": status,
            }
        )

    # Pillar coverage
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
            "dependencies": [
                "fixtures (storico FT)",
                "xg_profiles_json / FixtureTeamStat per xG",
            ],
            "risks": [
                "copertura xG non uniforme tra campionati",
                "sample size rolling basso a inizio stagione",
            ],
            "phase_1b_1c_needed": [
                "associazione feature→target total_goals_ft",
                "scelta misura stabilità (std vs MAD vs CV)",
                "ridondanza famiglie e rappresentanti",
            ],
        }

    implementation_recommendation = {
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
    }

    api_availability = {
        "stable_database": {
            "category": 1,
            "items": [
                "fixtures.goals_home/goals_away",
                "fixtures.kickoff_at/status",
                "cecchino_today_fixtures (scan, scores, output)",
                "fixture_team_stats.expected_goals (se presente)",
            ],
        },
        "payload_or_cache": {
            "category": 2,
            "items": [
                "cecchino_today_fixtures.xg_profiles_json",
                "cecchino_output_json.goal_markets.summary.lambda (v4)",
            ],
        },
        "recoverable_irregular": {
            "category": 3,
            "items": [
                "xG season profile se FixtureTeamStat parziale",
                "clean sheet frequency su sample piccoli",
            ],
        },
        "requires_new_api_calls": {
            "category": 4,
            "items": [
                "refresh xG mancanti via API-Football",
                "PPDA / Field Tilt / xThreat / Big Chances non in DB",
            ],
            "used_in_audit": False,
        },
        "unavailable": {
            "category": 5,
            "items": [e["feature_key"] for e in EXCLUDED_ADVANCED],
        },
        "model_core_preference": "categorie 1 e 2",
    }

    legacy_dependencies = {
        "v4_module": "cecchino_goal_intensity_analysis",
        "v4_version": V4_VERSION,
        "goal_engine": "cecchino_goal_poisson_v2 + fixture_history contexts",
        "baselines_q44": "cecchino_goal_intensity_baselines (non collegato a v4)",
        "ege_diagnostics": "variabili rolling/xG usate solo come inventory research, non come output Intensità",
        "consumers_of_v4": ["CecchinoTodayDetailPanel / CecchinoGoalIntensityAnalysisPanel"],
        "non_consumers": ["ICM", "Balance v5", "Segnali", "KPI"],
    }

    potential_conflicts = [
        {
            "id": "v4_single_quantity_vs_four_pillars",
            "detail": "v4 riduce tutto a expected_goals_total; v5 richiede quattro letture indipendenti",
        },
        {
            "id": "over_threshold_as_output",
            "detail": "v4 accende soglie Over; i mercati Over/GG in v5 sono solo feature descrittive del ritmo",
        },
        {
            "id": "fixed_thresholds",
            "detail": "soglie 0.5/1.5/2.5/3.5 fisse non calibrate sullo storico",
        },
        {
            "id": "defensive_semantics",
            "detail": "pilastro solidità: indice alto = difesa solida (non intensità offensiva)",
        },
    ]

    interpretative_questions = [
        "Quale misura di stabilità (std, MAD, CV) è più robusta a sample size bassi?",
        "xG For/Against casa-trasferta vanno pesati o bastano le medie season?",
        "Clean sheet frequency ha copertura sufficiente per entrare come primaria?",
        "Come mantenere Over 2.5/GG come feature senza farle diventare output di mercato?",
        "Come confrontare v5 vs v4 legacy_reference senza promuovere indici prematuri?",
    ]

    dataset_summary = {
        "rows_raw": len(raw_rows),
        "rows_deduped": len(deduped),
        "finished_fixtures": finished_count,
        "finished_with_result": with_result,
        "leakage_safe_rows": rows_safe,
        "competitions": len(competitions),
        "countries": len(countries),
        "temporal_distribution": dict(sorted(by_month.items())),
        "targets": {
            "total_goals_ft_available": target_total_goals_available,
            "goals_ge_2_rate_pct": pct(target_ge2, target_total_goals_available),
            "goals_ge_3_rate_pct": pct(target_ge3, target_total_goals_available),
            "btts_ft_rate_pct": pct(target_btts, target_total_goals_available),
            "note": "I target diagnostici non sono output del modulo Intensità.",
        },
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
        "api_availability": api_availability,
        "legacy_dependencies": legacy_dependencies,
        "potential_conflicts": potential_conflicts,
        "interpretative_questions": interpretative_questions,
        "implementation_recommendation": implementation_recommendation,
        "warnings": warnings,
        "performance": {
            "elapsed_ms": elapsed_ms,
            "rows_processed": anti["rows_checked"],
        },
    }
