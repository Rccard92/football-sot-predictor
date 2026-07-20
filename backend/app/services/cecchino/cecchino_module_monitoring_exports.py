"""Export di monitoraggio Cecchino — forensic v5.

Il modulo assembla esclusivamente dati e formule già prodotti dai servizi
canonici. Gli export sono riproducibili, autocontenuti e verificabili tramite
hash SHA-256 nel manifest.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_today_fixture import (
    ELIGIBILITY_ELIGIBLE,
    CecchinoTodayFixture,
)
from app.schemas.cecchino_purchasability_preview import (
    PURCHASABILITY_CANDIDATE_VERSION,
)
from app.services.cecchino.cecchino_balance_v5_monitoring import (
    BALANCE_ROW_FIELDS,
    build_balance_export_files,
    build_balance_module_overview_v2,
    build_balance_monitoring_rows,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    build_prospective_monitoring,
    get_active_bundle,
    stream_preview_export,
)
from app.services.cecchino.cecchino_monitoring_cohorts import (
    COHORT_FILTER_ALL,
    COHORT_PROSPECTIVE,
    analysis_query_flags,
    normalize_cohort,
    parse_export_cohort_filter,
)
from app.services.cecchino.cecchino_purchasability_audit import make_json_safe
from app.services.cecchino.cecchino_purchasability_validation import (
    PURCHASABILITY_VALIDATION_VERSION,
    build_purchasability_validation_health,
    build_purchasability_validation_rows,
    export_purchasability_validation_csv,
)
from app.services.cecchino.cecchino_purchasability_validation_aggregation import (
    PURCHASABILITY_PROMOTION_POLICY_VERSION,
    build_purchasability_promotion_readiness,
    build_purchasability_validation_summary,
)
from app.services.cecchino.cecchino_constants import CECCHINO_DEFAULT_WEIGHT_MODEL_KEY
from app.services.cecchino.cecchino_signal_aggregation import (
    build_signals_summary,
    export_signals_csv,
    list_signal_activations,
)

logger = logging.getLogger(__name__)

ModuleKey = Literal[
    "purchasability",
    "balance-v5",
    "goal-intensity-v5",
    "signals",
]

VALID_MODULE_KEYS: frozenset[str] = frozenset(
    {"purchasability", "balance-v5", "goal-intensity-v5", "signals"}
)
MONITORING_EXPORT_VERSION = "cecchino_module_monitoring_exports_v5"

_COMMON_REQUIRED_FILES: tuple[str, ...] = (
    "README_ANALISI.md",
    "CHATGPT_HANDOFF.md",
    "manifest.json",
    "versions.json",
    "filters.json",
    "data_dictionary.md",
    "schema_contract.json",
    "export_audit.json",
    "health.json",
    "summary.json",
    "warnings.json",
    "source_cohorts.json",
)

# Full forensic fields for purchasability validation rows
_PURCHASABILITY_ROW_FIELDS = [
    # Identity fields
    "id",
    "today_fixture_id",
    "local_fixture_id",
    "provider_fixture_id",
    "competition_id",
    "scan_date",
    "kickoff",
    "country_name",
    "league_name",
    "home_team_name",
    "away_team_name",
    # Snapshot fields
    "source_cohort",
    "source_mode",
    "snapshot_version",
    "snapshot_hash",
    "source_snapshot_at",
    "snapshot_timestamp_verified",
    "snapshot_before_kickoff",
    # Candidate/version fields
    "candidate_version",
    "candidate_name",
    "feature_version",
    "validation_version",
    # Market fields
    "market_key",
    "market_family",
    "selection",
    "calculation_status",
    "calculation_quality",
    # Score fields
    "purchasability_score",
    "raw_score",
    "score_band",
    "purchasability_class",
    "phase_1_score",
    "phase_2_score",
    "reading",
    # Odds/probability fields
    "quota_book",
    "analysis_eligible",
    "data_quality_status",
    "analysis_exclusion_reason",
    "quota_cecchino",
    "fair_book_probability",
    "prob_cecchino",
    "edge_pct",
    "rating_score",
    "score_acquisto",
    # Evaluation fields
    "evaluation_status",
    "evaluation_reason",
    "result_home_ft",
    "result_away_ft",
    "result_home_ht",
    "result_away_ht",
    "stake_units",
    "profit_units",
    "evaluated_at",
    # Promotion fields
    "promotion_eligible",
    "is_current",
    "created_at",
    "updated_at",
]

# Full forensic fields for signal activations
_SIGNALS_ROW_FIELDS = [
    "id",
    "today_fixture_id",
    "local_fixture_id",
    "provider_fixture_id",
    "competition_id",
    "country_name",
    "league_name",
    "home_team_name",
    "away_team_name",
    "scan_date",
    "kickoff",
    "activation_timestamp",
    "source_cohort",
    "is_current",
    "model_key",
    "model_label",
    "weights_version",
    "weights_display",
    "signal_group",
    "signal_label",
    "selection",
    "selection_source",
    "source_column",
    "target_market_key",
    "target_market_label",
    "rating",
    "score",
    "quota_book",
    "quota_cecchino",
    "prob_book",
    "prob_cecchino",
    "edge_pct",
    "activation_status",
    "evaluation_status",
    "evaluation_reason",
    "result_home_ft",
    "result_away_ft",
    "result_home_ht",
    "result_away_ht",
    "ft_home_goals",
    "ft_away_goals",
    "ht_home_goals",
    "ht_away_goals",
    "ft_score",
    "ht_score",
    "stake_units",
    "profit_units",
    "evaluated_at",
    "warning_codes",
    "match",
    "counts_in_avg_won_odds",
]

_COMPLETENESS_VALUES = frozenset({"complete", "partial", "empty", "blocked"})
_GOAL_EXPORTS: tuple[tuple[str, str, str], ...] = (
    ("preview_summary", "preview_summary.json", "json"),
    ("preview_snapshots", "preview_snapshots.csv", "csv"),
    ("preview_completed_results", "preview_completed_results.csv", "csv"),
    ("preview_candidate_monitoring", "preview_candidate_monitoring.csv", "csv"),
    ("preview_calibration", "preview_calibration.json", "json"),
    ("preview_bundle_definition", "preview_bundle_definition.json", "json"),
)
_GOAL_EMPTY_HEADERS: dict[str, list[str]] = {
    "preview_snapshots.csv": [
        "id",
        "today_fixture_id",
        "scan_date",
        "kickoff",
        "competition_id",
        "competition_name",
        "home_team_name",
        "away_team_name",
        "snapshot_status",
        "preview_status",
        "source_snapshot_at",
        "history_sample_size",
        "xg_status",
        "GI_A",
        "GI_B",
        "MT1",
        "GI_A_without_volatility",
        "expected_goals_GI_A",
        "p_ge2_GI_A",
        "p_ge3_GI_A",
        "p_btts_GI_A",
        "total_goals_ft",
        "result_attached",
        "source_snapshot_after_freeze",
        "source_snapshot_before_kickoff",
    ],
    "preview_completed_results.csv": [
        "id",
        "today_fixture_id",
        "scan_date",
        "kickoff",
        "competition_id",
        "snapshot_status",
        "GI_A",
        "GI_B",
        "MT1",
        "total_goals_ft",
        "result_attached",
    ],
    "preview_candidate_monitoring.csv": [
        "section",
        "candidate",
        "name",
        "n",
        "status",
        "spearman",
        "pearson",
        "mae",
        "rmse",
        "delta_mae",
        "evidence_level",
    ],
}

# Contratti minimi forensic dei quattro moduli (piano §§15-18).
SCHEMA_CONTRACTS: dict[str, dict[str, Any]] = {
    "purchasability": {
        "primary_rows_file": "rows.csv",
        "required_columns": _PURCHASABILITY_ROW_FIELDS,
        "optional_aliases": {
            "distributions.csv": "distributions_by_score_band.csv",
        },
        "required_files": [
            "gates.json",
            "readiness.json",
            "summary_all_selected_cohorts.json",
            "summary_prospective_only.json",
            "distributions_by_score_band.csv",
            "distributions_by_market.csv",
            "distributions_by_cohort.csv",
            "rows.csv",
        ],
    },
    "balance-v5": {
        "primary_rows_file": "balance_rows.csv",
        "required_columns": BALANCE_ROW_FIELDS,
        "required_files": [
            "balance_rows.csv",
            "f36_distribution.csv",
            "dominance_distribution.csv",
            "draw_credibility_distribution.csv",
            "gap_distribution.csv",
            "monthly_timeseries.csv",
            "snapshot_health.json",
            "source_cohort_distribution.json",
            "version_definition.json",
            "draw_credibility_research.json",
        ],
    },
    "goal-intensity-v5": {
        "primary_rows_file": "preview_snapshots.csv",
        "required_columns": _GOAL_EMPTY_HEADERS["preview_snapshots.csv"],
        "required_files": [
            filename for _, filename, _ in _GOAL_EXPORTS
        ] + ["prospective_progress.json", "data_health.json", "historical_availability.json"],
    },
    "signals": {
        "primary_rows_file": "activations_all_models.csv",
        "required_columns": _SIGNALS_ROW_FIELDS,
        "optional_aliases": {
            "activations_all_rows.csv": "activations_all_models.csv",
            "activations_current_rows.csv": "activations_current_model.csv",
        },
        "required_files": [
            "activations_all_models.csv",
            "activations_current_model.csv",
            "activations_verified_pre_match.csv",
            "activations_unusable.csv",
            "aggregations_by_model.csv",
            "aggregations_by_weights_version.csv",
            "field_availability.json",
            "by_signal.csv",
            "by_column.csv",
            "by_signal_and_column.csv",
            "monthly_timeseries.csv",
            "overall.json",
            "version_definition.json",
            "model_summary.csv",
        ],
    },
}


def _utcnow() -> str:
    """Timestamp UTC ISO-8601 usato da overview e manifest."""
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(payload: Any) -> bytes:
    """Serializza JSON strict dopo la normalizzazione canonica."""
    return json.dumps(
        make_json_safe(payload),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")


def _csv_bom(rows: list[dict[str, Any]], fieldnames: list[str]) -> bytes:
    """Crea un CSV UTF-8 con BOM e header sempre presente."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(make_json_safe(row.get(key)), ensure_ascii=False)
                    if isinstance(row.get(key), (dict, list))
                    else row.get(key)
                )
                for key in fieldnames
            }
        )
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _sha256(content: bytes) -> str:
    """Hash esadecimale del contenuto esatto inserito nello ZIP."""
    return hashlib.sha256(content).hexdigest()


def _count_csv_rows(content: bytes) -> int:
    """Conta le righe dati dopo l'header, gestendo il BOM UTF-8."""
    if not content:
        return 0
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) <= 1:
        return 0
    header = rows[0]
    count = 0
    for row in rows[1:]:
        if not row or all(cell == "" for cell in row):
            continue
        if len(row) == 1 and row[0] in {"", "note"}:
            continue
        if header and len(row) == len(header):
            mapped = dict(zip(header, row))
            if mapped.get("note") == "empty":
                continue
        count += 1
    return count


def _goal_effective_date_range(content: bytes) -> dict[str, str | None]:
    if not content:
        return {"from": None, "to": None}
    text = content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    dates = [
        str(r.get("scan_date") or "")[:10]
        for r in rows
        if r.get("scan_date") and r.get("note") != "empty"
    ]
    if not dates:
        return {"from": None, "to": None}
    return {"from": min(dates), "to": max(dates)}


def _chunk_csv_bytes(
    content: bytes,
    prefix: str = "rows",
    max_rows: int = 50_000,
) -> dict[str, bytes]:
    """Suddivide un CSV preservando BOM e header in ogni parte."""
    if max_rows <= 0:
        raise ValueError("max_rows_must_be_positive")
    text = content.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(text)))
    if not parsed:
        return {f"{prefix}_0001.csv": _with_bom(content)}
    header, data_rows = parsed[0], parsed[1:]
    chunks: dict[str, bytes] = {}
    for index, start in enumerate(range(0, len(data_rows), max_rows), start=1):
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(data_rows[start : start + max_rows])
        chunks[f"{prefix}_{index:04d}.csv"] = _with_bom(buf.getvalue())
    if not chunks:
        chunks[f"{prefix}_0001.csv"] = _with_bom(text)
    return chunks


def _csv_header(content: bytes) -> list[str]:
    try:
        return next(csv.reader(io.StringIO(content.decode("utf-8-sig"))), [])
    except (UnicodeDecodeError, csv.Error):
        return []


def _primary_csv_names(
    files: dict[str, bytes],
    schema_contract: dict[str, Any],
) -> list[str]:
    primary = str(schema_contract.get("primary_rows_file") or "rows.csv")
    if primary in files:
        return [primary]
    chunks = [
        str(item)
        for item in (schema_contract.get("primary_rows_chunks") or [])
        if str(item) in files
    ]
    return sorted(chunks)


def _build_export_audit(
    files: dict[str, bytes],
    meta: dict[str, Any],
    module_key: str,
    required_files: list[str],
    schema_contract: dict[str, Any],
) -> dict[str, Any]:
    """Verifica completezza, schema e cardinalità dell'inventario forensic."""
    optional_aliases = dict(schema_contract.get("optional_aliases") or {})
    alias_names = set(optional_aliases.keys())
    virtual_actual = set(files) | {"manifest.json", "export_audit.json"}
    actual_files = sorted(virtual_actual)
    missing_files = sorted(set(required_files) - virtual_actual)
    unexpected_files = sorted(
        virtual_actual - set(required_files) - alias_names - {"manifest.json", "export_audit.json"}
    )
    primary_names = _primary_csv_names(files, schema_contract)
    required_columns = list(schema_contract.get("required_columns") or [])
    actual_columns = _csv_header(files[primary_names[0]]) if primary_names else []
    missing_columns = sorted(set(required_columns) - set(actual_columns))

    exported_row_count = sum(_count_csv_rows(files[name]) for name in primary_names)
    source_row_count = int(meta.get("source_total_rows", meta.get("primary_rows", 0)) or 0)
    row_count_match = source_row_count == exported_row_count
    truncated = bool(meta.get("truncated", False))

    null_counts: Counter[str] = Counter()
    observed_rows = 0
    date_values: list[str] = []
    cohort_counts: Counter[str] = Counter()
    for name in primary_names:
        try:
            reader = csv.DictReader(io.StringIO(files[name].decode("utf-8-sig")))
            for row in reader:
                observed_rows += 1
                for column in actual_columns:
                    if row.get(column) in (None, ""):
                        null_counts[column] += 1
                raw_date = row.get("scan_date") or row.get("Data") or row.get("kickoff")
                if raw_date:
                    date_values.append(str(raw_date)[:10])
                cohort = row.get("source_cohort")
                if cohort:
                    cohort_counts[str(cohort)] += 1
        except (UnicodeDecodeError, csv.Error):
            continue
    null_ratios = {
        column: (null_counts[column] / observed_rows if observed_rows else 0.0)
        for column in actual_columns
    }
    source_cohort_counts: Any = dict(cohort_counts)
    if not source_cohort_counts:
        source_cohort_counts = meta.get("source_cohort_counts")
        if source_cohort_counts is None:
            source_cohorts = meta.get("source_cohorts") or {}
            if isinstance(source_cohorts, dict):
                source_cohort_counts = source_cohorts
            elif isinstance(source_cohorts, list) and len(source_cohorts) == 1:
                source_cohort_counts = {
                    str(source_cohorts[0]): source_row_count,
                }
            else:
                source_cohort_counts = {
                    str(cohort): 0 for cohort in source_cohorts
                }

    validation_errors: list[str] = []
    if missing_files:
        validation_errors.append("required_files_missing")
    if missing_columns:
        validation_errors.append("required_columns_missing")
    if not row_count_match:
        validation_errors.append("row_count_mismatch")
    if truncated:
        validation_errors.append("export_truncated")
    warnings = list(meta.get("warnings") or [])
    if unexpected_files:
        warnings.append("File non previsti dal contratto presenti nell'inventario")

    # Technical status: file/schema integrity
    hard_failure = bool(
        missing_files or missing_columns or not row_count_match or truncated
    )
    technical_status = "fail" if hard_failure else "pass"

    # Scientific status: schema/cohorts/results — allowed: pass|partial|fail|partial_collecting
    completed_count = int(meta.get("completed_count", 0) or 0)
    settled_count = int(meta.get("settled_count", 0) or 0)
    completeness = str(meta.get("completeness") or "")
    blocking_reasons = list(meta.get("blocking_reasons") or [])

    if hard_failure:
        scientific_status = "fail"
    elif exported_row_count == 0 and completeness == "blocked":
        scientific_status = "fail"
    elif exported_row_count == 0:
        scientific_status = "fail"
    elif module_key == "goal-intensity-v5" and completed_count == 0:
        scientific_status = "partial_collecting"
    elif module_key == "purchasability":
        if settled_count == 0 and exported_row_count > 0:
            scientific_status = "partial_collecting"
        elif blocking_reasons and exported_row_count > 0:
            scientific_status = "partial"
        elif completeness in {"partial", "empty"}:
            scientific_status = "partial"
        else:
            scientific_status = "pass"
    elif module_key == "balance-v5":
        ts_verified = int(meta.get("timestamp_verified_count", 0) or 0)
        if exported_row_count > 0 and ts_verified == 0:
            scientific_status = "partial"
        elif completeness in {"partial", "empty"}:
            scientific_status = "partial"
        else:
            scientific_status = "pass"
    elif module_key == "signals":
        if not meta.get("all_models_exported"):
            scientific_status = "partial"
        elif not meta.get("source_cohort_counts"):
            scientific_status = "partial"
        elif settled_count == 0 and exported_row_count > 0:
            scientific_status = "monitoring"
        elif completeness in {"partial", "empty"}:
            scientific_status = "partial"
        else:
            scientific_status = "pass"
    elif settled_count == 0 and module_key in {"purchasability", "signals"}:
        scientific_status = "partial_collecting"
    elif completeness in {"partial", "empty"}:
        scientific_status = "partial"
    else:
        scientific_status = "pass"

    # Combined status for backward compatibility (prefer technical fail)
    if technical_status == "fail" or scientific_status == "fail":
        status = "fail"
    elif scientific_status in {"partial_collecting", "monitoring", "partial"}:
        status = "partial"
    else:
        status = "pass"

    reconciliation = {
        "source_total_rows": source_row_count,
        "selected_cohort_rows": int(meta.get("selected_cohort_rows", source_row_count) or source_row_count),
        "exported_rows": exported_row_count,
        "excluded_rows": int(meta.get("excluded_rows", 0) or 0),
        "excluded_by_reason": meta.get("excluded_by_reason") or {},
        "duplicate_rows": int(meta.get("duplicate_rows", 0) or 0),
        "not_evaluable_rows": int(meta.get("not_evaluable_rows", 0) or 0),
        "unusable_rows": int(meta.get("unusable_rows", 0) or 0),
        "truncated": truncated,
    }

    return make_json_safe(
        {
            "export_version": MONITORING_EXPORT_VERSION,
            "module_key": module_key,
            "status": status,
            "technical_status": technical_status,
            "scientific_status": scientific_status,
            "source_row_count": source_row_count,
            "exported_row_count": exported_row_count,
            "row_count_match": row_count_match,
            "truncated": truncated,
            "reconciliation": reconciliation,
            "required_files": required_files,
            "optional_aliases": optional_aliases,
            "actual_files": actual_files,
            "missing_files": missing_files,
            "unexpected_files": unexpected_files,
            "required_columns": required_columns,
            "actual_columns": actual_columns,
            "missing_columns": missing_columns,
            "null_ratio_by_column": null_ratios,
            "source_cohort_counts": source_cohort_counts,
            "date_min": min(date_values) if date_values else None,
            "date_max": max(date_values) if date_values else None,
            "validation_errors": validation_errors,
            "warnings": list(dict.fromkeys(str(item) for item in warnings)),
        }
    )


def _file_entry(
    name: str,
    content: bytes,
    kind: str,
    schema_version: str,
    row_count: int | None = None,
) -> dict[str, Any]:
    """Descrittore verificabile di un file del pacchetto."""
    effective_rows = _count_csv_rows(content) if kind == "csv" and row_count is None else row_count
    return {
        "name": name,
        "kind": kind,
        "row_count": effective_rows,
        "size_bytes": len(content),
        "sha256": _sha256(content),
        "empty": (
            effective_rows == 0
            if effective_rows is not None
            else len(content.strip()) == 0
        ),
        "schema_version": schema_version,
    }


def _pack_zip(files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    """Inserisce manifest e file nello ZIP in ordine stabile."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for name in sorted(files):
            archive.writestr(name, files[name])
    return buf.getvalue()


def _with_bom(csv_text: str | bytes) -> bytes:
    content = csv_text.encode("utf-8") if isinstance(csv_text, str) else csv_text
    return content if content.startswith(b"\xef\xbb\xbf") else b"\xef\xbb\xbf" + content


def _fixture_is_settled(row: CecchinoTodayFixture) -> bool:
    return row.score_fulltime_home is not None and row.score_fulltime_away is not None


def _eligible_fixture_counts(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
) -> tuple[int, int]:
    query = select(CecchinoTodayFixture).where(
        CecchinoTodayFixture.scan_date >= date_from,
        CecchinoTodayFixture.scan_date <= date_to,
        CecchinoTodayFixture.eligibility_status == ELIGIBILITY_ELIGIBLE,
    )
    if competition_id is not None:
        query = query.where(CecchinoTodayFixture.competition_id == int(competition_id))
    fixtures = list(db.scalars(query).all())
    return len(fixtures), sum(1 for row in fixtures if _fixture_is_settled(row))


def _active_goal_bundle(db: Session) -> Any | None:
    """Accetta solo un bundle materializzato con versione testuale."""
    bundle = get_active_bundle(db)
    version = getattr(bundle, "version", None) if bundle is not None else None
    return bundle if isinstance(version, str) and version else None


def build_purchasability_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Overview Acquistabilità basata su health e readiness canonici."""
    health = build_purchasability_validation_health(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    summary_historical = build_purchasability_validation_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        bootstrap_iterations=50,
        promotion_eligible_only=False,
    )
    hist_metrics = summary_historical.get("metrics") or {}
    readiness = build_purchasability_promotion_readiness(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        bootstrap_iterations=50,
    )
    warnings = list(readiness.get("warnings") or [])
    coverage = health.get("snapshot_persistence_coverage")
    if coverage is None and int(health.get("fixtures_with_kpi_panel") or 0) == 0:
        warnings.append("Nessuna fixture eleggibile con KPI panel nel periodo")
    elif int(health.get("result_settled_count") or 0) == 0:
        warnings.append("Coorte con esito won/lost ancora vuota")
    blocking_reason = health.get("persistence_blocking_reason")
    if blocking_reason:
        warnings.append(f"Persistenza bloccata: {blocking_reason}")
    return make_json_safe(
        {
            "module_key": "purchasability",
            "status": readiness.get("status") or "collecting_data",
            "scientific_maturity": readiness.get("status") or "collecting_data",
            "readiness_status": readiness.get("status") or "collecting_data",
            "version": PURCHASABILITY_CANDIDATE_VERSION,
            "coverage": coverage,
            "fixtures": health.get("fixtures_with_verified_pre_match_preview"),
            "prospective_fixtures": health.get("fixtures_with_persisted_preview"),
            "historical_fixtures": health.get("historical_fixtures"),
            "settled": health.get("result_settled_count"),
            "evaluated_rows": health.get("evaluated_rows"),
            "prospective_rows": health.get("prospective_rows_available"),
            "historical_rows": health.get("historical_rows_available"),
            "historical_settled_rows": hist_metrics.get("settled"),
            "pending_rows": health.get("result_pending_count"),
            "result_missing_rows": health.get("result_missing_count"),
            "data_quality_excluded_rows": health.get("data_quality_excluded_rows"),
            "invalid_book_odds_count": health.get("invalid_book_odds_count"),
            "reconciliation": summary_historical.get("reconciliation"),
            "validation_rows_total": health.get("validation_rows_total"),
            "validation_rows_by_source_cohort": health.get(
                "validation_rows_by_source_cohort"
            ),
            "settled_historical": hist_metrics.get("settled"),
            "last_snapshot_at": health.get("last_persisted_snapshot_at"),
            "next_review_at": readiness.get("prima_data_teorica_promozione"),
            "warnings": list(dict.fromkeys(str(item) for item in warnings)),
            "persistence_blocking_reason": blocking_reason,
            "persistence_blocking_note": health.get("persistence_blocking_note"),
        }
    )


def extract_balance_v5_from_today_output(
    output: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Compatibilità legacy: estrae il payload Balance già persistito."""
    if not isinstance(output, dict):
        return None
    balance = output.get("balance_v5")
    if isinstance(balance, dict) and balance:
        if str(balance.get("status") or "").strip().lower() != "unavailable":
            return balance
    legacy = output.get("balance_analysis")
    if not isinstance(legacy, dict) or not legacy:
        return None
    status = str(legacy.get("status") or "").strip().lower()
    if status == "unavailable":
        return None
    meaningful = any(key not in {"status", "message", "error"} for key in legacy)
    return legacy if meaningful or (status and status != "unavailable") else None


def build_balance_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Delega integralmente all'adapter Balance v5 hardened."""
    return build_balance_module_overview_v2(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )


def build_goal_intensity_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Overview soft della preview Goal Intensity v5."""
    eligible, settled = _eligible_fixture_counts(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    bundle = _active_goal_bundle(db)
    warnings = [
        "Preview research: metriche candidate e calibrazione disponibili nel pacchetto",
    ]
    snapshots_count = 0
    global_snapshots_count = 0
    pending_count = 0
    completed_count = 0
    monitoring_status = None
    min_sample = None
    first_effective_date = None
    last_effective_date = None
    snapshot_collection_progress = None
    completed_results_progress = None
    if bundle is None:
        warnings.insert(0, "Bundle Goal Intensity v5 attivo assente")
    else:
        from app.models.cecchino_goal_intensity_v5_preview import (
            CecchinoGoalIntensityV5PreviewSnapshot,
        )
        from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
            MINIMUM_PROSPECTIVE_MATCHES,
            build_prospective_monitoring,
        )

        all_snaps = list(
            db.scalars(
                select(CecchinoGoalIntensityV5PreviewSnapshot).where(
                    CecchinoGoalIntensityV5PreviewSnapshot.bundle_id == bundle.id,
                )
            ).all()
        )
        global_snapshots_count = len(all_snaps)
        snaps = [
            s
            for s in all_snaps
            if s.scan_date is not None
            and s.scan_date >= date_from
            and s.scan_date <= date_to
        ]
        snapshots_count = len(snaps)
        completed_count = sum(1 for s in snaps if s.result_attached_at is not None)
        pending_count = max(0, snapshots_count - completed_count)
        scan_dates = [s.scan_date for s in snaps if s.scan_date is not None]
        if scan_dates:
            first_effective_date = min(scan_dates).isoformat()
            last_effective_date = max(scan_dates).isoformat()
        monitoring = build_prospective_monitoring(db, bundle)
        monitoring_status = monitoring.get("status")
        min_sample = MINIMUM_PROSPECTIVE_MATCHES
        if min_sample:
            snapshot_collection_progress = min(
                1.0, global_snapshots_count / min_sample
            )
            completed_results_progress = min(1.0, completed_count / min_sample)
    if eligible == 0:
        warnings.insert(0, "Nessuna fixture eleggibile nel periodo")
    scientific_maturity = (
        "raccolta_dati"
        if completed_count == 0
        else "validazione_in_corso"
    )
    return make_json_safe(
        {
            "module_key": "goal-intensity-v5",
            "status": "preview_research" if bundle is not None else "blocked",
            "scientific_maturity": scientific_maturity,
            "version": bundle.version if bundle is not None else None,
            "coverage": None,
            "fixtures": eligible if eligible else None,
            "settled": settled if eligible else None,
            "eligible_fixtures": eligible,
            "global_snapshots": global_snapshots_count if bundle is not None else None,
            "snapshots_in_period": snapshots_count if bundle is not None else None,
            "prospective_snapshots": snapshots_count if bundle is not None else None,
            "pending_snapshots": pending_count if bundle is not None else None,
            "completed_snapshots": completed_count if bundle is not None else None,
            "minimum_sample": min_sample,
            "snapshot_collection_progress": snapshot_collection_progress,
            "completed_results_progress": completed_results_progress,
            "monitoring_status": monitoring_status,
            "first_effective_date": first_effective_date,
            "last_effective_date": last_effective_date,
            "last_snapshot_at": last_effective_date,
            "next_review_at": None,
            "warnings": warnings,
        }
    )


def build_signals_module_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Overview Signals con conteggi fixture e attivazioni non ambigui."""
    try:
        summary = build_signals_summary(db, date_from=date_from, date_to=date_to)
        overall = summary.get("overall") or {}
        eligible = int(overall.get("eligible_fixtures_count") or 0)
        distinct_fixtures = int(overall.get("fixtures_with_signals_count") or 0)
        activations = int(overall.get("activations") or 0)
        settled_activations = int(overall.get("won") or 0) + int(
            overall.get("lost") or 0
        )
        all_payload = list_signal_activations(
            db,
            date_from=date_from,
            date_to=date_to,
            limit=500_000,
            offset=0,
            only_current=False,
            all_models=True,
        )
        all_items = [
            row for row in (all_payload.get("items") or []) if isinstance(row, dict)
        ]
        current_items = [
            item
            for item in all_items
            if item.get("is_current")
            and str(item.get("model_key") or "").upper()
            == str(CECCHINO_DEFAULT_WEIGHT_MODEL_KEY).upper()
        ]
        current_count = len(current_items)
        fixtures_with_current_signals = len(
            {
                int(item["today_fixture_id"])
                for item in current_items
                if item.get("today_fixture_id") is not None
            }
        )
        current_activations_evaluated = sum(
            1
            for item in current_items
            if str(item.get("evaluation_status") or "") in {"won", "lost"}
        )
        historical_activations_total = len(all_items)
        verified_count = sum(
            1 for item in all_items if item.get("source_cohort") == "historical_persisted_verified"
        )
        unusable_count = sum(
            1 for item in all_items if item.get("source_cohort") == "unusable"
        )
        warnings = list(summary.get("warnings") or [])
        if competition_id is not None:
            warnings.append(
                "Filtro competition_id non applicabile al servizio Signals; export su tutte le competizioni"
            )
        if activations and distinct_fixtures == 0:
            warnings.append(
                "Fixture distinte con segnali assenti; gli esiti won/lost sono conteggi di attivazioni"
            )
        return make_json_safe(
            {
                "module_key": "signals",
                "status": "operational",
                "scientific_maturity": "monitoraggio",
                "version": "signals_aggregation_current",
                "coverage": None,
                "fixtures": fixtures_with_current_signals,
                "fixtures_with_current_signals": fixtures_with_current_signals,
                "distinct_fixtures": distinct_fixtures,
                "eligible_fixtures": eligible,
                "activations": activations,
                "current_activations": current_count,
                "current_activations_evaluated": current_activations_evaluated,
                "historical_activations_total": historical_activations_total,
                "historical_activations": historical_activations_total,
                "verified_pre_match_count": verified_count,
                "post_kickoff_excluded_count": unusable_count,
                "unusable_count": unusable_count,
                "settled": settled_activations,
                "settled_activations": settled_activations,
                "last_snapshot_at": None,
                "next_review_at": None,
                "warnings": warnings,
            }
        )
    except Exception as exc:
        return make_json_safe(
            {
                "module_key": "signals",
                "status": "blocked",
                "version": "signals_aggregation_current",
                "coverage": None,
                "fixtures": None,
                "distinct_fixtures": None,
                "eligible_fixtures": None,
                "activations": None,
                "settled": None,
                "settled_activations": None,
                "last_snapshot_at": None,
                "next_review_at": None,
                "warnings": [f"Summary Signals non disponibile: {type(exc).__name__}"],
            }
        )


def build_module_monitoring_overview(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
) -> dict[str, Any]:
    """Overview con adapter indipendenti per i quattro moduli."""
    modules = [
        build_purchasability_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_balance_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_goal_intensity_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
        build_signals_module_overview(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        ),
    ]
    return make_json_safe(
        {
            "generated_at": _utcnow(),
            "version": MONITORING_EXPORT_VERSION,
            "modules": modules,
        }
    )


def analysis_pack_filename(module_key: str, date_from: date, date_to: date) -> str:
    return f"SOT_MONITOR_{module_key}_{date_from.isoformat()}_{date_to.isoformat()}.zip"


def rows_csv_filename(module_key: str, date_from: date, date_to: date) -> str:
    return (
        f"SOT_MONITOR_{module_key}_{date_from.isoformat()}_"
        f"{date_to.isoformat()}_rows.csv"
    )


def _rows_to_csv(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return _csv_bom([], ["note"])
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return _csv_bom(rows, fields)


def _summary_csv(summary: dict[str, Any], key: str, fallback: list[str]) -> bytes:
    rows = list(summary.get(key) or [])
    if not rows:
        return _csv_bom([], fallback)
    fields: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for field in row:
                if field not in fields:
                    fields.append(field)
    return _csv_bom([row for row in rows if isinstance(row, dict)], fields or fallback)


def _materialize_preview_export(
    db: Session,
    kind: str,
    filename: str,
    file_kind: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> bytes:
    raw = "".join(
        stream_preview_export(db, kind=kind, date_from=date_from, date_to=date_to)
    ).encode("utf-8")
    if file_kind == "csv":
        return _with_bom(raw)
    try:
        return _json_bytes(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_bytes({"status": "error", "error": "invalid_preview_export"})


def _goal_data_health(
    preview_summary: dict[str, Any] | None,
    monitoring: dict[str, Any],
    *,
    bundle_available: bool,
) -> dict[str, Any]:
    bundle_summary = (preview_summary or {}).get("bundle") or {}
    return {
        "bundle_available": bundle_available,
        "prospective_matches_collected": bundle_summary.get(
            "prospective_matches_collected"
        ),
        "completed_prospective_matches": monitoring.get(
            "completed_prospective_matches"
        ),
        "monitoring_status": monitoring.get("status"),
        "blocking_reasons": (
            [] if bundle_available else ["bundle_missing"]
        ),
    }


def _signals_monthly_timeseries(items: list[dict[str, Any]]) -> bytes:
    """Aggrega soli conteggi; le quote persistite non vengono ricalcolate."""
    monthly: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        month = str(item.get("scan_date") or item.get("kickoff") or "")[:7] or "unknown"
        status = str(item.get("evaluation_status") or "unknown")
        monthly[month]["activations"] += 1
        monthly[month][status] += 1
        if status in {"won", "lost"}:
            monthly[month]["settled_activations"] += 1
    rows = [
        {
            "month": month,
            "activations": counts["activations"],
            "won": counts["won"],
            "lost": counts["lost"],
            "settled_activations": counts["settled_activations"],
            "pending": counts["pending"] + counts["result_missing"],
            "not_evaluable": counts["not_evaluable"],
        }
        for month, counts in sorted(monthly.items())
    ]
    return _csv_bom(
        rows,
        [
            "month",
            "activations",
            "won",
            "lost",
            "settled_activations",
            "pending",
            "not_evaluable",
        ],
    )


def _dictionary_md(module_key: str) -> str:
    dictionaries = {
        "purchasability": """# Dizionario dati — Acquistabilità

- `health.json`: copertura della persistenza pre-match, distribuzioni versione e anomalie di sync.
- `summary.json`: metriche soltanto sulla coorte di validazione ammessa dalla policy.
- `gates.json`: esito puntuale dei gate temporali, di numerosità e copertura.
- `readiness.json`: stato della revisione manuale; non autorizza promozioni automatiche.
- `warnings.json`: avvisi consolidati, incluso l'eventuale blocco di persistenza.
- `distributions_by_score_band.csv`: righe aggregate per fascia dello score Acquistabilità (canonico).
- `distributions.csv`: alias legacy opzionale di `distributions_by_score_band.csv` (non incluso nel pacchetto v5).
- `rows.csv`: validazioni per mercato; `source_cohort` distingue origine prospettica/legacy.

`settled` indica esclusivamente righe con esito `won` o `lost`. Quote e profitto sono valori
già prodotti dal servizio di validazione.
""",
        "balance-v5": """# Dizionario dati — Balance v5

- `balance_rows.csv`: una riga per fixture coperta, con quattro pilastri, probabilità e FT.
- `source_cohort`: `prospective_persisted` oppure `legacy_derived_diagnostic`.
- `source_mode`: modalità scelta dal resolver read-only.
- `*_distribution.csv`: distribuzione delle classi già assegnate dal modulo Balance.
- `monthly_timeseries.csv`: copertura mensile e distinzione fra coorti.
- `snapshot_health.json`: eleggibili, coperti e coperti con risultato.
- `version_definition.json`: versioni Balance, snapshot e chiave di persistenza.

Le righe legacy sono diagnostiche e non equivalgono a snapshot prospettici verificati.
""",
        "goal-intensity-v5": """# Dizionario dati — Goal Intensity v5 Preview

- `preview_snapshots.csv`: snapshot prospettici e score congelati prima del kickoff.
- `preview_completed_results.csv`: sottoinsieme con target FT allegato senza ricalcolo score.
- `preview_candidate_monitoring.csv`: metriche e confronti dei candidati congelati.
- `preview_calibration.json`: parametri di calibrazione train-only del bundle.
- `preview_bundle_definition.json`: definizioni, hash, freeze e protocollo prospettico.
- `prospective_progress.json`: avanzamento verso il campione minimo e gate Phase 2B.
- `data_health.json`: disponibilità bundle, numerosità e ragioni bloccanti.

Gli score non sono probabilità. Le probabilità presenti sono esclusivamente stime calibrate
dal bundle attivo; il modulo resta research e non genera segnali betting.
""",
        "signals": """# Dizionario dati — Signals

- `activations_rows.csv`: una riga per attivazione corrente, con quota già memorizzata.
- `overall.json`: conteggi globali; `settled_activations = won + lost`.
- `by_signal.csv`, `by_column.csv`, `by_signal_and_column.csv`: aggregazioni canoniche.
- `monthly_timeseries.csv`: soli conteggi mensili, senza ricalcolo delle quote.
- `model_summary.csv`: riepilogo del modello selezionato dalle metriche `overall`.
- `version_definition.json`: modello, filtri e semantica esplicita dei conteggi.

`eligible_fixtures_count` è il denominatore; `fixtures_with_signals_count` conta fixture
distinte; `activations` può essere maggiore perché una fixture può avere più segnali.
""",
    }
    return dictionaries[module_key]


def _readme_md(module_key: str) -> str:
    return (
        f"# SOT Monitor — {module_key}\n\n"
        f"Pacchetto generato da `{MONITORING_EXPORT_VERSION}`.\n"
        "Ogni file è descritto nel manifest con dimensione e SHA-256.\n"
        "I JSON sono strict; i CSV sono UTF-8 con BOM e mantengono l'header anche se vuoti.\n"
    )


def _handoff_md(
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    source_cohorts: list[str],
    entries: list[dict[str, Any]],
    warnings: list[str],
    completeness: str,
) -> str:
    possible = {
        "purchasability": [
            "copertura della persistenza e cause di blocco",
            "distribuzione score e risultati della coorte validabile",
            "verifica dei gate per revisione manuale",
        ],
        "balance-v5": [
            "copertura per coorte e mese",
            "distribuzione delle classi dei quattro pilastri",
            "confronto descrittivo con risultati FT disponibili",
        ],
        "goal-intensity-v5": [
            "avanzamento prospettico e integrità temporale",
            "confronti fra candidati già calcolati dal servizio",
            "audit di bundle, calibrazione e definizioni congelate",
        ],
        "signals": [
            "volumi per segnale, colonna e mese",
            "esiti won/lost sulle attivazioni valutate",
            "copertura fixture distinte rispetto alle eleggibili",
        ],
    }[module_key]
    impossible = {
        "purchasability": [
            "promuovere automaticamente il candidate",
            "inferire causalità o performance fuori dalla coorte esportata",
        ],
        "balance-v5": [
            "trattare la coorte legacy come prospettica",
            "ricostruire input non presenti negli snapshot",
        ],
        "goal-intensity-v5": [
            "validare il modello se il campione minimo non è raggiunto",
            "interpretare lo score grezzo come probabilità",
        ],
        "signals": [
            "ricostruire quote storiche mancanti",
            "confondere fixture distinte con numero di attivazioni",
        ],
    }[module_key]
    file_lines = []
    for entry in entries:
        rows = entry.get("row_count")
        suffix = f", {rows} righe dati" if rows is not None else ""
        file_lines.append(f"- `{entry['name']}` ({entry['kind']}{suffix})")
    return (
        f"# Handoff ChatGPT — {module_key}\n\n"
        f"## Periodo e filtri\n- Periodo: {date_from.isoformat()} → {date_to.isoformat()}\n"
        f"- Competizione: {competition_id if competition_id is not None else 'tutte'}\n"
        f"- Completezza: `{completeness}`\n"
        f"- Coorti sorgente: {', '.join(source_cohorts) if source_cohorts else 'nessuna'}\n\n"
        "## File reali inclusi\n"
        + "\n".join(file_lines)
        + "\n\n## Analisi possibili\n"
        + "\n".join(f"- {item}" for item in possible)
        + "\n\n## Analisi non possibili\n"
        + "\n".join(f"- {item}" for item in impossible)
        + "\n\n## Warning\n"
        + ("\n".join(f"- {item}" for item in warnings) if warnings else "- Nessuno")
        + "\n\n## Domande consigliate\n"
        "- Verifica prima coorti, numerosità e completezza.\n"
        "- Separa sempre evidenza descrittiva da conclusioni validative.\n"
    )


def _module_schema_version(module_key: str) -> str:
    return f"{MONITORING_EXPORT_VERSION}:{module_key}"


def _build_purchasability_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    market_key: str | None,
    include_rows: bool,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    # Parse filter and get query flags
    parsed_filter = parse_export_cohort_filter(source_cohort_filter)
    flags = analysis_query_flags(parsed_filter)
    
    # Health is always unfiltered
    health = build_purchasability_validation_health(
        db, date_from=date_from, date_to=date_to, competition_id=competition_id
    )
    
    # Summary for selected cohorts (based on filter)
    summary_selected = build_purchasability_validation_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        bootstrap_iterations=50,
        promotion_eligible_only=flags["promotion_eligible_only"],
        source_cohorts=flags["source_cohorts"],
    )
    
    # Summary always prospective only (for gates/readiness)
    summary_prospective = build_purchasability_validation_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        bootstrap_iterations=50,
        promotion_eligible_only=True,
    )
    
    # Gates and readiness ALWAYS use prospective only
    readiness = build_purchasability_promotion_readiness(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        bootstrap_iterations=50,
    )
    
    warnings = list(readiness.get("warnings") or [])
    blocking = health.get("persistence_blocking_reason")
    if blocking:
        warnings.append(f"Persistenza bloccata: {blocking}")
    
    # Build distribution CSVs
    distributions_by_score_band = _summary_csv(
        {"rows": summary_selected.get("by_score_band") or []},
        "rows",
        [
            "score_band",
            "rows",
            "fixtures",
            "win_rate",
            "roi_pct",
            "realized_margin",
            "average_phase_1",
            "average_phase_2",
        ],
    )
    
    distributions_by_market = _summary_csv(
        {"rows": summary_selected.get("by_market_key") or []},
        "rows",
        ["market_key", "rows", "fixtures", "win_rate", "roi_pct"],
    )
    
    distributions_by_cohort = _summary_csv(
        {"rows": summary_selected.get("by_source_cohort") or []},
        "rows",
        ["source_cohort", "rows", "fixtures", "won", "lost", "pending"],
    )
    
    files = {
        "health.json": _json_bytes(health),
        "summary.json": _json_bytes(summary_selected),  # summary = selected filter
        "summary_all_selected_cohorts.json": _json_bytes(summary_selected),
        "summary_prospective_only.json": _json_bytes(summary_prospective),
        "gates.json": _json_bytes(readiness.get("data_gates") or {}),
        "readiness.json": _json_bytes(readiness),
        "warnings.json": _json_bytes({"warnings": warnings}),
        "distributions_by_score_band.csv": distributions_by_score_band,
        "distributions_by_market.csv": distributions_by_market,
        "distributions_by_cohort.csv": distributions_by_cohort,
    }
    
    source_total_rows = int(
        (summary_selected.get("metrics") or {}).get("rows_total_filtered") or 0
    )
    exported_row_count = 0
    truncated = False
    settled_count = 0
    
    if include_rows:
        page_size = 100_000
        safety_cap = 2_000_000
        offset = 0
        exported_rows: list[dict[str, Any]] = []
        while offset < safety_cap:
            payload = build_purchasability_validation_rows(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                market_key=market_key,
                limit=min(page_size, safety_cap - offset),
                offset=offset,
                # Use filter flags for rows (NOT always promotion_eligible_only)
                promotion_eligible_only=flags["promotion_eligible_only"],
                source_cohorts=flags["source_cohorts"],
            )
            page = list(payload.get("items") or [])
            source_total_rows = int(payload.get("total") or source_total_rows)
            exported_rows.extend(row for row in page if isinstance(row, dict))
            offset += len(page)
            if not page or offset >= source_total_rows:
                break
        truncated = source_total_rows > len(exported_rows)
        if truncated:
            warnings.append(
                "Export Acquistabilità fermato al limite di sicurezza di 2.000.000 righe"
            )
        files["rows.csv"] = _csv_bom(exported_rows, _PURCHASABILITY_ROW_FIELDS)
        exported_row_count = len(exported_rows)
        # Count settled for scientific status
        settled_count = sum(
            1 for r in exported_rows
            if r.get("evaluation_status") in ("won", "lost")
        )
    
    row_count = exported_row_count if include_rows else source_total_rows
    
    # Completeness: blocking + exported > 0 → partial NOT blocked
    if blocking and exported_row_count == 0:
        completeness = "blocked"
    elif row_count == 0:
        completeness = "empty"
    elif blocking or warnings:
        completeness = "partial"
    else:
        completeness = "complete"
    
    cohorts = [
        str(row.get("source_cohort"))
        for row in (summary_selected.get("by_source_cohort") or [])
        if isinstance(row, dict) and row.get("source_cohort")
    ]
    reconciliation = summary_selected.get("reconciliation") or {}
    invalid_book_odds_count = int(reconciliation.get("invalid_book_odds", 0) or 0)

    return files, {
        "module_version": PURCHASABILITY_CANDIDATE_VERSION,
        "versions": {
            "candidate": PURCHASABILITY_CANDIDATE_VERSION,
            "validation": PURCHASABILITY_VALIDATION_VERSION,
            "policy": PURCHASABILITY_PROMOTION_POLICY_VERSION,
        },
        "source_cohorts": cohorts,
        "source_cohort_filter": parsed_filter,
        "warnings": warnings,
        "completeness": completeness,
        "blocking_reasons": [str(blocking)] if blocking else [],
        "include_rows_effective": include_rows and "rows.csv" in files,
        "primary_rows": row_count,
        "source_total_rows": source_total_rows,
        "exported_total_rows": exported_row_count,
        "settled_count": settled_count,
        "truncated": truncated,
        "invalid_book_odds_count": invalid_book_odds_count,
        "excluded_from_performance_count": invalid_book_odds_count,
        "reconciliation": reconciliation,
    }


def _build_balance_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    include_rows: bool,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    files = build_balance_export_files(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    overview = build_balance_module_overview(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    warnings = list(overview.get("warnings") or [])
    rows = _count_csv_rows(files["balance_rows.csv"])
    timestamp_verified = sum(
        1
        for r in build_balance_monitoring_rows(
            db, date_from=date_from, date_to=date_to, competition_id=competition_id
        )
        if r.get("snapshot_timestamp") and r.get("pre_match_verified") is True
    )
    eligible = int(overview.get("eligible_fixtures") or 0)
    if eligible == 0:
        completeness = "empty"
    elif rows == 0:
        completeness = "partial"
    elif int(overview.get("prospective_persisted") or 0) == 0:
        completeness = "partial"
    else:
        completeness = "complete"
    cohorts_map = overview.get("source_cohorts") or {
        "prospective_persisted": overview.get("prospective_persisted") or 0,
        "legacy_derived_diagnostic": overview.get("legacy_derived_diagnostic") or 0,
    }
    return files, {
        "module_version": overview.get("version"),
        "versions": {"balance": overview.get("version")},
        "source_cohorts": cohorts_map,
        "warnings": warnings,
        "completeness": completeness,
        "blocking_reasons": [],
        "include_rows_effective": include_rows and "balance_rows.csv" in files,
        "primary_rows": rows,
        "source_total_rows": rows,
        "exported_total_rows": rows,
        "timestamp_verified_count": timestamp_verified,
        "truncated": False,
    }


def _build_goal_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    include_rows: bool,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    bundle = _active_goal_bundle(db)
    warnings: list[str] = []
    files: dict[str, bytes] = {}
    completed_count = 0
    
    if bundle is None:
        warnings.append("Bundle Goal Intensity v5 attivo assente")
        for _, filename, kind in _GOAL_EXPORTS:
            files[filename] = (
                _csv_bom([], _GOAL_EMPTY_HEADERS[filename])
                if kind == "csv"
                else _json_bytes({})
            )
        monitoring = {"status": "error", "error": "bundle_missing"}
        preview_summary: dict[str, Any] = {}
        completeness = "blocked"
        blocking_reasons = ["bundle_missing"]
        module_version = None
        historical_availability = {
            "status": "unavailable",
            "eligible_fixtures": 0,
            "coverage_fixtures": 0,
            "exclusion_reasons": ["bundle_missing"],
            "effective_date_range": None,
        }
    else:
        for export_kind, filename, kind in _GOAL_EXPORTS:
            files[filename] = _materialize_preview_export(
                db,
                export_kind,
                filename,
                kind,
                date_from=date_from,
                date_to=date_to,
            )
        try:
            preview_summary = json.loads(files["preview_summary.json"].decode("utf-8"))
        except json.JSONDecodeError:
            preview_summary = {}
        monitoring = build_prospective_monitoring(db, bundle)
        snapshots = _count_csv_rows(files["preview_snapshots.csv"])
        
        # Count completed results (with FT attached) - DO NOT invent from Today FT
        completed_count = _count_csv_rows(files["preview_completed_results.csv"])
        
        # Completeness depends on completed results for scientific validity
        if snapshots == 0:
            completeness = "empty"
        elif completed_count == 0:
            completeness = "partial"  # collecting data, no completed results yet
        else:
            completeness = "complete"
        blocking_reasons = []
        module_version = bundle.version
        
        # Historical availability: document eligible/coverage/exclusion
        bundle_summary = (preview_summary or {}).get("bundle") or {}
        eligible_fixtures, _ = _eligible_fixture_counts(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
        )
        effective_range = _goal_effective_date_range(files["preview_snapshots.csv"])
        historical_availability = {
            "status": "available" if bundle is not None else "unavailable",
            "eligible_fixtures": eligible_fixtures,
            "coverage_fixtures": snapshots,
            "completed_count": completed_count,
            "prospective_matches_collected": bundle_summary.get(
                "prospective_matches_collected"
            ),
            "exclusion_reasons": [],
            "effective_date_range": effective_range,
            "requested_date_range": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
            },
            "bundle_version": module_version,
        }
    
    files["prospective_progress.json"] = _json_bytes(monitoring)
    files["data_health.json"] = _json_bytes(
        _goal_data_health(
            preview_summary,
            monitoring,
            bundle_available=bundle is not None,
        )
    )
    files["historical_availability.json"] = _json_bytes(historical_availability)
    
    rows = _count_csv_rows(files["preview_snapshots.csv"])
    return files, {
        "module_version": module_version,
        "versions": {"goal_intensity_bundle": module_version},
        "source_cohorts": ["prospective_frozen_bundle"] if bundle is not None else [],
        "warnings": warnings,
        "completeness": completeness,
        "blocking_reasons": blocking_reasons,
        "include_rows_effective": include_rows and "preview_snapshots.csv" in files,
        "primary_rows": rows,
        "source_total_rows": rows,
        "exported_total_rows": rows,
        "completed_count": completed_count,
        "truncated": False,
    }


def _is_verified_pre_match(item: dict[str, Any]) -> bool:
    """Check if activation was created before kickoff."""
    activation_ts = item.get("activation_timestamp")
    kickoff = item.get("kickoff")
    if not activation_ts or not kickoff:
        return False
    try:
        # Parse timestamps
        act_str = str(activation_ts).replace("Z", "+00:00")
        kick_str = str(kickoff).replace("Z", "+00:00")
        act_dt = datetime.fromisoformat(act_str)
        kick_dt = datetime.fromisoformat(kick_str)
        return act_dt < kick_dt
    except (ValueError, TypeError):
        return False


def _signals_aggregation_table(
    items: list[dict[str, Any]],
    key_name: str,
) -> bytes:
    groups: dict[str, dict[str, int]] = defaultdict(
        lambda: {"activations": 0, "won": 0, "lost": 0, "pending": 0}
    )
    for item in items:
        key = str(item.get(key_name) or "unknown")
        groups[key]["activations"] += 1
        status = str(item.get("evaluation_status") or "")
        if status == "won":
            groups[key]["won"] += 1
        elif status == "lost":
            groups[key]["lost"] += 1
        elif status == "pending":
            groups[key]["pending"] += 1
    rows = [{key_name: k, **v} for k, v in sorted(groups.items())]
    fields = [key_name, "activations", "won", "lost", "pending"]
    return _csv_bom(rows, fields)


def _signals_field_availability(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {
            "persisted": [],
            "derived": ["selection", "source_cohort"],
            "unavailable": [
                "rating",
                "score",
                "stake_units",
                "profit_units",
                "activation_status",
                "warning_codes",
            ],
        }
    sample = items[0]
    persisted = [
        field
        for field in (
            "model_key",
            "weights_version",
            "quota_book",
            "quota_cecchino",
            "prob_book",
            "prob_cecchino",
            "edge_pct",
            "evaluation_status",
            "target_market_key",
        )
        if sample.get(field) is not None
    ]
    derived = []
    if sample.get("selection") is not None:
        derived.append("selection")
    if sample.get("source_cohort") is not None:
        derived.append("source_cohort")
    if sample.get("selection_source"):
        derived.append("selection_source")
    unavailable = [
        field
        for field in ("rating", "score", "stake_units", "profit_units", "activation_status", "warning_codes")
        if sample.get(field) is None
    ]
    return {
        "persisted": persisted,
        "derived": derived,
        "unavailable": unavailable,
        "note": "Nessun Rating/Score/stake/profit inventato — solo campi persistiti o derivati documentati.",
    }


def _build_signals_files(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    include_rows: bool,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    default_model = str(CECCHINO_DEFAULT_WEIGHT_MODEL_KEY).upper()
    summary = build_signals_summary(
        db, date_from=date_from, date_to=date_to, only_current=True
    )
    overall = summary.get("overall") or {}

    page_size = 100_000
    safety_cap = 2_000_000
    offset = 0
    source_total_rows = 0
    all_items: list[dict[str, Any]] = []

    while offset < safety_cap:
        activation_payload = list_signal_activations(
            db,
            date_from=date_from,
            date_to=date_to,
            limit=min(page_size, safety_cap - offset),
            offset=offset,
            only_current=False,
            all_models=True,
        )
        source_total_rows = int(activation_payload.get("total") or source_total_rows)
        page = [
            row
            for row in (activation_payload.get("items") or [])
            if isinstance(row, dict)
        ]
        all_items.extend(page)
        offset += len(page)
        if not page or offset >= source_total_rows:
            break

    truncated = source_total_rows > len(all_items)

    current_model_items: list[dict[str, Any]] = []
    verified_pre_match: list[dict[str, Any]] = []
    verified_current_model: list[dict[str, Any]] = []
    unusable: list[dict[str, Any]] = []
    historical_items: list[dict[str, Any]] = []

    for item in all_items:
        is_current = bool(item.get("is_current", False))
        model_key = str(item.get("model_key") or "").upper()
        cohort = item.get("source_cohort")
        is_pre_match = _is_verified_pre_match(item)

        if is_current and model_key == default_model:
            current_model_items.append(item)

        if is_pre_match:
            verified_pre_match.append(item)
            if is_current and model_key == default_model:
                verified_current_model.append(item)
            if cohort == "historical_persisted_verified":
                historical_items.append(item)
        elif item.get("kickoff") and item.get("activation_timestamp"):
            unusable.append(item)

    all_models_csv = _csv_bom(all_items, _SIGNALS_ROW_FIELDS)
    files: dict[str, bytes] = {
        "activations_all_models.csv": all_models_csv,
        "activations_all_rows.csv": all_models_csv,
        "activations_current_model.csv": _csv_bom(
            current_model_items, _SIGNALS_ROW_FIELDS
        ),
        "activations_current_rows.csv": _csv_bom(
            current_model_items, _SIGNALS_ROW_FIELDS
        ),
        "activations_verified_pre_match.csv": _csv_bom(
            verified_pre_match, _SIGNALS_ROW_FIELDS
        ),
        "activations_unusable.csv": _csv_bom(unusable, _SIGNALS_ROW_FIELDS),
        "aggregations_by_model.csv": _signals_aggregation_table(all_items, "model_key"),
        "aggregations_by_weights_version.csv": _signals_aggregation_table(
            all_items, "weights_version"
        ),
        "field_availability.json": _json_bytes(_signals_field_availability(all_items)),
    }

    model_key = (summary.get("filters") or {}).get("model_key") or default_model
    model_row = {"model_key": model_key, **overall}
    version_definition = {
        "version": "signals_aggregation_current",
        "model_key": model_key,
        "filters": summary.get("filters") or {},
        "semantics": {
            "eligible_fixtures": "overall.eligible_fixtures_count",
            "distinct_fixtures": "overall.fixtures_with_signals_count",
            "settled_activations": "overall.won + overall.lost",
            "odds": "persisted_only_no_recalculation",
            "primary_rows_file": "activations_all_models.csv",
            "performance_source": "activations_verified_pre_match.csv (model F current)",
            "all_models": True,
        },
    }

    summary_verified = build_signals_summary(
        db, date_from=date_from, date_to=date_to, only_current=True
    )

    files.update({
        "by_signal.csv": _summary_csv(
            summary_verified, "by_signal", ["signal_group", "signal_label", "activations"]
        ),
        "by_column.csv": _summary_csv(
            summary_verified, "by_column", ["source_column", "activations"]
        ),
        "by_signal_and_column.csv": _summary_csv(
            summary_verified,
            "by_signal_and_column",
            ["signal_group", "signal_label", "source_column", "activations"],
        ),
        "overall.json": _json_bytes(overall),
        "monthly_timeseries.csv": _signals_monthly_timeseries(verified_current_model),
        "version_definition.json": _json_bytes(version_definition),
        "model_summary.csv": _rows_to_csv([model_row]),
    })

    warnings = list(summary.get("warnings") or [])
    if truncated:
        warnings.append(
            "Export Signals fermato al limite di sicurezza di 2.000.000 righe"
        )
    if competition_id is not None:
        warnings.append(
            "Filtro competition_id non applicabile al servizio Signals; export su tutte le competizioni"
        )
    if len(unusable) > 0:
        warnings.append(
            f"{len(unusable)} attivazioni create post-kickoff escluse da performance aggregations"
        )
    model_keys = {str(item.get("model_key") or "") for item in all_items}
    if len(model_keys) < 2 and len(all_items) > 0:
        warnings.append("Export all_models con un solo model_key presente nel periodo")

    rows = len(all_items)
    settled_count = int(overall.get("won", 0) or 0) + int(overall.get("lost", 0) or 0)
    completeness = "empty" if rows == 0 else ("partial" if warnings else "complete")

    return files, {
        "module_version": "signals_aggregation_current",
        "versions": {"signals": "signals_aggregation_current", "model_key": model_key},
        "source_cohorts": sorted({str(i.get("source_cohort") or "unknown") for i in all_items}),
        "source_cohort_counts": dict(
            Counter(str(i.get("source_cohort") or "unknown") for i in all_items)
        ),
        "warnings": warnings,
        "completeness": completeness,
        "blocking_reasons": [],
        "include_rows_effective": include_rows and "activations_all_models.csv" in files,
        "primary_rows": rows,
        "source_total_rows": source_total_rows,
        "exported_total_rows": rows,
        "settled_count": settled_count,
        "verified_pre_match_count": len(verified_pre_match),
        "unusable_count": len(unusable),
        "historical_activations_count": len(historical_items),
        "current_model_activations_count": len(current_model_items),
        "all_models_exported": True,
        "model_keys_present": sorted(k for k in model_keys if k),
        "truncated": truncated,
    }


def _build_module_inventory(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None,
    market_key: str | None,
    include_rows: bool,
    include_debug: bool,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    if module_key not in VALID_MODULE_KEYS:
        raise ValueError("invalid_module_key")
    if module_key == "purchasability":
        files, meta = _build_purchasability_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            source_cohort_filter=source_cohort_filter,
        )
    elif module_key == "balance-v5":
        files, meta = _build_balance_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            include_rows=include_rows,
        )
    elif module_key == "goal-intensity-v5":
        files, meta = _build_goal_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            include_rows=include_rows,
        )
    else:
        files, meta = _build_signals_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            include_rows=include_rows,
        )

    # Parse and normalize cohort filter for filters.json
    parsed_cohort_filter = parse_export_cohort_filter(source_cohort_filter)
    
    filters = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "competition_id": competition_id,
        "market_key": market_key,
        "include_rows_requested": include_rows,
        "include_debug": include_debug,
        "source_cohort_filter": parsed_cohort_filter,
    }
    meta.setdefault("versions", {})
    meta.setdefault("source_cohorts", [])
    meta.setdefault("warnings", [])
    meta.setdefault("completeness", "partial")
    meta.setdefault("blocking_reasons", [])
    meta.setdefault("primary_rows", 0)
    meta.setdefault("source_total_rows", meta.get("primary_rows", 0))
    meta.setdefault("exported_total_rows", meta.get("primary_rows", 0))
    meta.setdefault("truncated", False)
    files["versions.json"] = _json_bytes(meta.get("versions") or {})
    files["filters.json"] = _json_bytes(filters)
    files["README_ANALISI.md"] = _readme_md(module_key).encode("utf-8")
    files["data_dictionary.md"] = _dictionary_md(module_key).encode("utf-8")
    files["source_cohorts.json"] = _json_bytes(meta.get("source_cohorts") or [])
    files.setdefault("warnings.json", _json_bytes({"warnings": meta.get("warnings") or []}))
    if "health.json" not in files:
        health_source = (
            files.get("snapshot_health.json")
            or files.get("data_health.json")
            or _json_bytes(
                {
                    "source_total_rows": meta.get("source_total_rows", 0),
                    "exported_total_rows": meta.get("exported_total_rows", 0),
                    "truncated": bool(meta.get("truncated", False)),
                }
            )
        )
        files["health.json"] = health_source
    if "summary.json" not in files:
        summary_source = (
            files.get("preview_summary.json")
            or files.get("overall.json")
            or _json_bytes({"primary_rows": meta.get("primary_rows", 0)})
        )
        files["summary.json"] = summary_source

    schema_contract = {
        **SCHEMA_CONTRACTS[module_key],
        "export_version": MONITORING_EXPORT_VERSION,
        "module_key": module_key,
        "required_columns": list(SCHEMA_CONTRACTS[module_key]["required_columns"]),
        "required_files": list(SCHEMA_CONTRACTS[module_key]["required_files"]),
    }
    csv_chunks: dict[str, list[str]] = {}
    primary_name = str(schema_contract["primary_rows_file"])
    for csv_name in [
        name
        for name, content in files.items()
        if name.endswith(".csv") and _count_csv_rows(content) > 50_000
    ]:
        prefix = "rows" if csv_name == primary_name else csv_name.removesuffix(".csv")
        chunks = _chunk_csv_bytes(files.pop(csv_name), prefix=prefix)
        files.update(chunks)
        chunk_names = sorted(chunks)
        csv_chunks[csv_name] = chunk_names
        if csv_name == primary_name:
            schema_contract["primary_rows_chunks"] = chunk_names
        schema_contract["required_files"] = [
            name for name in schema_contract["required_files"] if name != csv_name
        ] + chunk_names
    files["schema_contract.json"] = _json_bytes(schema_contract)

    schema_version = _module_schema_version(module_key)
    pre_handoff_entries = [
        _file_entry(
            name,
            content,
            "csv" if name.endswith(".csv") else (
                "json" if name.endswith(".json") else "markdown"
            ),
            schema_version,
        )
        for name, content in sorted(files.items())
    ]
    files["CHATGPT_HANDOFF.md"] = _handoff_md(
        module_key=module_key,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        source_cohorts=meta.get("source_cohorts") or [],
        entries=pre_handoff_entries,
        warnings=meta.get("warnings") or [],
        completeness=str(meta.get("completeness") or "partial"),
    ).encode("utf-8")
    required_files = list(
        dict.fromkeys(
            [*_COMMON_REQUIRED_FILES, *schema_contract.get("required_files", [])]
        )
    )
    export_audit = _build_export_audit(
        files,
        meta,
        module_key,
        required_files,
        schema_contract,
    )
    files["export_audit.json"] = _json_bytes(export_audit)
    meta["export_audit"] = export_audit
    if (
        export_audit.get("status") != "pass"
        and meta.get("completeness") != "blocked"
    ):
        meta["completeness"] = "partial"
    entries = [
        _file_entry(
            name,
            content,
            "csv" if name.endswith(".csv") else (
                "json" if name.endswith(".json") else "markdown"
            ),
            schema_version,
        )
        for name, content in sorted(files.items())
    ]
    manifest = {
        "schema_version": MONITORING_EXPORT_VERSION,
        "export_version": MONITORING_EXPORT_VERSION,
        "module_key": module_key,
        "module_version": meta.get("module_version"),
        "generated_at": _utcnow(),
        "source_cohorts": meta.get("source_cohorts") or [],
        "source_total_rows": int(meta.get("source_total_rows", 0) or 0),
        "exported_total_rows": int(meta.get("exported_total_rows", 0) or 0),
        "truncated": bool(meta.get("truncated", False)),
        "csv_chunks": csv_chunks,
        "date_range": {
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
        },
        "competition": competition_id,
        "market_key": market_key,
        "include_rows": bool(meta.get("include_rows_effective", include_rows)),
        "include_rows_requested": include_rows,
        "include_debug": include_debug,
        "warnings_count": len(meta.get("warnings") or []),
        "export_audit_status": export_audit.get("status"),
        "export_completeness_status": meta.get("completeness") or "partial",
        "files": entries,
        "manifest_self_hash_excluded": True,
    }
    if manifest["export_completeness_status"] not in _COMPLETENESS_VALUES:
        raise ValueError("invalid_export_completeness_status")
    return files, manifest, meta


def build_module_analysis_pack_zip(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    include_rows: bool = True,
    include_debug: bool = False,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> tuple[bytes, str]:
    """Costruisce il pacchetto forensic v4 con audit incorporato."""
    files, manifest, _ = _build_module_inventory(
        db,
        module_key=module_key,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        include_rows=include_rows,
        include_debug=include_debug,
        source_cohort_filter=source_cohort_filter,
    )
    return (
        _pack_zip(files, manifest),
        analysis_pack_filename(module_key, date_from, date_to),
    )


def build_module_analysis_pack_audit(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    include_rows: bool = True,
    include_debug: bool = False,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> dict[str, Any]:
    """Costruisce l'audit completo senza materializzare i byte ZIP."""
    _, manifest, meta = _build_module_inventory(
        db,
        module_key=module_key,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        include_rows=include_rows,
        include_debug=include_debug,
        source_cohort_filter=source_cohort_filter,
    )
    file_names = ["manifest.json"] + [
        str(entry.get("name"))
        for entry in (manifest.get("files") or [])
        if entry.get("name")
    ]
    export_audit = meta.get("export_audit") or {}
    required = list(export_audit.get("required_files") or [])
    actual = list(export_audit.get("actual_files") or sorted(file_names))
    return make_json_safe(
        {
            "module_key": module_key,
            "export_version": MONITORING_EXPORT_VERSION,
            "export_audit": export_audit,
            "files": sorted(file_names),
            "files_available": actual,
            "files_expected": required or sorted(file_names),
            "rows": export_audit.get("exported_row_count"),
            "completeness": manifest.get("export_completeness_status"),
            "source_cohort_filter": parse_export_cohort_filter(source_cohort_filter),
        }
    )


def _failed_module_audit_payload(module_key: str, exc: Exception) -> dict[str, Any]:
    """Payload sanitizzato quando l'audit di un singolo modulo fallisce."""
    error_type = type(exc).__name__
    export_audit = {
        "technical_status": "fail",
        "scientific_status": "fail",
        "status": "fail",
        "error_code": "module_audit_failed",
        "error_type": error_type,
    }
    return make_json_safe(
        {
            "module_key": module_key,
            "status": "failed",
            "technical_status": "fail",
            "scientific_status": "fail",
            "error_code": "module_audit_failed",
            "error_type": error_type,
            "files_available": 0,
            "files_expected": None,
            "export_audit": export_audit,
            "completeness": "blocked",
        }
    )


def build_modules_analysis_packs_audit(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    include_rows: bool = True,
    include_debug: bool = False,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> dict[str, Any]:
    """Costruisce in un'unica risposta gli audit dei quattro moduli."""
    module_keys = (
        "purchasability",
        "balance-v5",
        "goal-intensity-v5",
        "signals",
    )
    modules: list[dict[str, Any]] = []
    for module_key in module_keys:
        try:
            modules.append(
                build_module_analysis_pack_audit(
                    db,
                    module_key=module_key,
                    date_from=date_from,
                    date_to=date_to,
                    competition_id=competition_id,
                    market_key=market_key,
                    include_rows=include_rows,
                    include_debug=include_debug,
                    source_cohort_filter=source_cohort_filter,
                )
            )
        except Exception as exc:
            logger.exception("module_audit_failed module_key=%s", module_key)
            modules.append(_failed_module_audit_payload(module_key, exc))
    return make_json_safe(
        {
            "generated_at": _utcnow(),
            "export_version": MONITORING_EXPORT_VERSION,
            "source_cohort_filter": parse_export_cohort_filter(source_cohort_filter),
            "modules": modules,
        }
    )


def build_module_summary_payload(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> dict[str, Any]:
    """Payload summary API, mantenuto compatibile con la versione precedente."""
    if module_key not in VALID_MODULE_KEYS:
        raise ValueError("invalid_module_key")
    if module_key == "purchasability":
        # Apply cohort filter to summary
        flags = analysis_query_flags(parse_export_cohort_filter(source_cohort_filter))
        return build_purchasability_validation_summary(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            bootstrap_iterations=50,
            promotion_eligible_only=flags["promotion_eligible_only"],
            source_cohorts=flags["source_cohorts"],
        )
    if module_key == "balance-v5":
        return {
            "overview": build_balance_module_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
        }
    if module_key == "goal-intensity-v5":
        return {
            "overview": build_goal_intensity_module_overview(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
            )
        }
    return {
        "overview": build_signals_module_overview(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
        )
    }


def build_module_rows_csv(
    db: Session,
    *,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> tuple[bytes, str]:
    """CSV righe canonico: validazioni, Balance, snapshot Goal o attivazioni."""
    if module_key not in VALID_MODULE_KEYS:
        raise ValueError("invalid_module_key")
    filename = rows_csv_filename(module_key, date_from, date_to)
    if module_key == "purchasability":
        # Apply cohort filter to rows
        flags = analysis_query_flags(parse_export_cohort_filter(source_cohort_filter))
        content = _with_bom(
            export_purchasability_validation_csv(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                market_key=market_key,
                promotion_eligible_only=flags["promotion_eligible_only"],
            )
        )
    elif module_key == "balance-v5":
        content = build_balance_export_files(
            db,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
        ).get("balance_rows.csv", _csv_bom([], BALANCE_ROW_FIELDS))
    elif module_key == "goal-intensity-v5":
        if _active_goal_bundle(db) is None:
            content = _csv_bom([], _GOAL_EMPTY_HEADERS["preview_snapshots.csv"])
        else:
            content = _materialize_preview_export(
                db,
                "preview_snapshots",
                "preview_snapshots.csv",
                "csv",
                date_from=date_from,
                date_to=date_to,
            )
    else:
        content = _with_bom(
            export_signals_csv(db, date_from=date_from, date_to=date_to)
        )
    return content, filename


def build_module_export_status(
    db: Session,
    module_key: str,
    date_from: date,
    date_to: date,
    competition_id: int | None = None,
    market_key: str | None = None,
    include_rows: bool = True,
    source_cohort_filter: str = COHORT_FILTER_ALL,
) -> dict[str, Any]:
    """Dry-run dell'inventario senza comprimere lo ZIP."""
    files, manifest, meta = _build_module_inventory(
        db,
        module_key=module_key,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        include_rows=include_rows,
        include_debug=False,
        source_cohort_filter=source_cohort_filter,
    )
    expected = [entry["name"] for entry in manifest["files"]]
    return make_json_safe(
        {
            "module_key": module_key,
            "files_expected": expected,
            "files_available": sorted(files),
            "rows": meta["primary_rows"],
            "source_cohorts": meta["source_cohorts"],
            "source_cohort_filter": parse_export_cohort_filter(source_cohort_filter),
            "completeness": meta["completeness"],
            "blocking_reasons": meta["blocking_reasons"],
            "estimated_size_bytes": sum(len(content) for content in files.values())
            + len(_json_bytes(manifest)),
            "export_completeness_status": meta["completeness"],
            "warnings": meta.get("warnings") or [],
        }
    )
