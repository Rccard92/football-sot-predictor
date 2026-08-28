"""Export Pattern Discovery — ZIP chunked/streaming, anti-leakage, READ-ONLY.

Non carica tutte le righe RUN+MATCH+MARKET in RAM: ParquetWriter a chunk.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.pattern_lab_constants import (
    CSV_ROW_THRESHOLD,
    EXPORT_MODE_FILTERED,
    EXPORT_MODE_FULL,
    PATTERN_LAB_EXPORT_KIND,
    PATTERN_LAB_SORT_POLICY_BB,
    PATTERN_LAB_VERSION,
    SNAPSHOT_CHUNK_SIZE,
)
from app.services.cecchino_data_lab.pattern_lab_filters import parse_pattern_lab_filters
from app.services.cecchino_data_lab.pattern_lab_service import (
    _resolve_runs,
    iter_pattern_lab_rows,
)

logger = logging.getLogger(__name__)

# Schema canonico colonne (ordine stabile)
EXPORT_COLUMNS: list[str] = [
    # identity
    "run_id",
    "season",
    "competition",
    "lab_match_id",
    "snapshot_id",
    "kickoff_at",
    "home_team",
    "away_team",
    "market_key",
    "market_label",
    "eligibility_status",
    # quote PRE
    "pre_quota_bet365",
    "pre_quote_type",
    "pre_implied_probability",
    "pre_is_real_book_quote",
    "pre_is_derived_quote",
    "pre_derivation_method",
    "pre_quote_source_type",
    "pre_quota_cecchino",
    "pre_prob_cecchino",
    "pre_prob_book",
    "pre_prob_book_fair",
    # KPI
    "pre_rating",
    "pre_rating_label",
    "pre_edge_pct",
    "pre_value",
    "pre_score_acquisto",
    "pre_value_positive",
    "pre_vantaggio_prob",
    "pre_kpi_status",
    "pre_book_source",
    "pre_cecchino_source",
    # signals
    "pre_signal_active",
    "pre_signal_count",
    "pre_signal_family",
    "pre_signal_excel_d",
    "pre_signal_excel_e",
    "pre_signal_excel_f",
    "pre_signal_excel_g",
    "pre_consensus_yes_count",
    "pre_consensus_status",
    # balance
    "pre_balance_structural_class",
    "pre_balance_observation_status",
    "pre_balance_f36_score",
    "pre_balance_f36_class",
    "pre_balance_dominance_score",
    "pre_balance_dominance_class",
    "pre_balance_draw_credibility_score",
    "pre_balance_draw_credibility_class",
    "pre_balance_gap_coherence_score",
    "pre_balance_gap_coherence_class",
    "pre_balance_geometry",
    # goal v4-compat
    "pre_goal_v4_compat_execution_status",
    "pre_goal_v4_compat_composite",
    "pre_goal_v4_compat_final_class",
    "pre_goal_v4_compat_direction",
    "pre_goal_v4_compat_final_score",
    "pre_goal_v4_compat_offensive_production_score",
    "pre_goal_v4_compat_offensive_production_class",
    "pre_goal_v4_compat_defensive_solidity_score",
    "pre_goal_v4_compat_defensive_solidity_class",
    "pre_goal_v4_compat_match_tempo_score",
    "pre_goal_v4_compat_match_tempo_class",
    "pre_goal_v4_compat_offensive_stability_score",
    "pre_goal_v4_compat_offensive_stability_class",
    # purchasability v3.6
    "pre_purch_v36_score",
    "pre_purch_v36_class",
    "pre_purch_v36_status",
    "pre_purch_v36_gate_status",
    "pre_purch_v36_value_core",
    "pre_purch_v36_structural_factor",
    "pre_purch_v36_quality_factor",
    "pre_purch_v36_acquisition_core",
    # bet builder historical
    "pre_pattern_lab_bet_builder_active",
    "pre_pattern_lab_bet_builder_rank",
    "pre_pattern_lab_bet_builder_selection_reason",
    "pre_pattern_lab_bet_builder_origin",
    # targets POST
    "target_evaluation_status",
    "target_won",
    "target_lost",
    "target_void",
    "target_profit_1u",
    "target_profit_1u_real",
    "target_profit_1u_synthetic",
    "target_profit_category",
    "target_result_reason",
    "target_ft_home",
    "target_ft_away",
    "target_ht_home",
    "target_ht_away",
    "target_ft_result",
    # observational only
    "observational_only_quota_closing",
    "observational_only_implied_prob_closing",
    "observational_only_movement_delta_pct",
    "observational_only_movement_direction",
    "observational_only_movement_intensity",
    "observational_only_availability_horizon",
]

IDENTITY_COLS = {
    "run_id",
    "season",
    "competition",
    "lab_match_id",
    "snapshot_id",
    "kickoff_at",
    "home_team",
    "away_team",
    "market_key",
    "market_label",
    "eligibility_status",
}

# Tipi Arrow canonici (stringhe: risolti in pa.* da build_export_arrow_schema).
# Tutti i campi sono nullable: anche un batch tutto-NULL mantiene il tipo finale.
EXPORT_ARROW_TYPE_NAMES: dict[str, str] = {
    # identity — id → int64; resto → string
    "run_id": "int64",
    "season": "string",
    "competition": "string",
    "lab_match_id": "int64",
    "snapshot_id": "int64",
    "kickoff_at": "string",
    "home_team": "string",
    "away_team": "string",
    "market_key": "string",
    "market_label": "string",
    "eligibility_status": "string",
    # quote PRE
    "pre_quota_bet365": "float64",
    "pre_quote_type": "string",
    "pre_implied_probability": "float64",
    "pre_is_real_book_quote": "bool",
    "pre_is_derived_quote": "bool",
    "pre_derivation_method": "string",
    "pre_quote_source_type": "string",
    "pre_quota_cecchino": "float64",
    "pre_prob_cecchino": "float64",
    "pre_prob_book": "float64",
    "pre_prob_book_fair": "float64",
    # KPI
    "pre_rating": "int64",
    "pre_rating_label": "string",
    "pre_edge_pct": "float64",
    "pre_value": "float64",
    "pre_score_acquisto": "float64",
    "pre_value_positive": "bool",
    "pre_vantaggio_prob": "float64",
    "pre_kpi_status": "string",
    "pre_book_source": "string",
    "pre_cecchino_source": "string",
    # signals
    "pre_signal_active": "bool",
    "pre_signal_count": "int64",
    "pre_signal_family": "string",
    "pre_signal_excel_d": "bool",
    "pre_signal_excel_e": "bool",
    "pre_signal_excel_f": "bool",
    "pre_signal_excel_g": "bool",
    "pre_consensus_yes_count": "int64",
    "pre_consensus_status": "string",
    # balance
    "pre_balance_structural_class": "string",
    "pre_balance_observation_status": "string",
    "pre_balance_f36_score": "float64",
    "pre_balance_f36_class": "string",
    "pre_balance_dominance_score": "float64",
    "pre_balance_dominance_class": "string",
    "pre_balance_draw_credibility_score": "float64",
    "pre_balance_draw_credibility_class": "string",
    "pre_balance_gap_coherence_score": "float64",
    "pre_balance_gap_coherence_class": "string",
    "pre_balance_geometry": "float64",
    # goal v4-compat
    "pre_goal_v4_compat_execution_status": "string",
    "pre_goal_v4_compat_composite": "float64",
    "pre_goal_v4_compat_final_class": "string",
    "pre_goal_v4_compat_direction": "string",
    "pre_goal_v4_compat_final_score": "float64",
    "pre_goal_v4_compat_offensive_production_score": "float64",
    "pre_goal_v4_compat_offensive_production_class": "string",
    "pre_goal_v4_compat_defensive_solidity_score": "float64",
    "pre_goal_v4_compat_defensive_solidity_class": "string",
    "pre_goal_v4_compat_match_tempo_score": "float64",
    "pre_goal_v4_compat_match_tempo_class": "string",
    "pre_goal_v4_compat_offensive_stability_score": "float64",
    "pre_goal_v4_compat_offensive_stability_class": "string",
    # purchasability v3.6
    "pre_purch_v36_score": "float64",
    "pre_purch_v36_class": "string",
    "pre_purch_v36_status": "string",
    "pre_purch_v36_gate_status": "string",
    "pre_purch_v36_value_core": "float64",
    "pre_purch_v36_structural_factor": "float64",
    "pre_purch_v36_quality_factor": "float64",
    "pre_purch_v36_acquisition_core": "float64",
    # bet builder historical
    "pre_pattern_lab_bet_builder_active": "bool",
    "pre_pattern_lab_bet_builder_rank": "int64",
    "pre_pattern_lab_bet_builder_selection_reason": "string",
    "pre_pattern_lab_bet_builder_origin": "string",
    # targets POST
    "target_evaluation_status": "string",
    "target_won": "bool",
    "target_lost": "bool",
    "target_void": "bool",
    "target_profit_1u": "float64",
    "target_profit_1u_real": "float64",
    "target_profit_1u_synthetic": "float64",
    "target_profit_category": "string",
    "target_result_reason": "string",
    "target_ft_home": "int64",
    "target_ft_away": "int64",
    "target_ht_home": "int64",
    "target_ht_away": "int64",
    "target_ft_result": "string",
    # observational only
    "observational_only_quota_closing": "float64",
    "observational_only_implied_prob_closing": "float64",
    "observational_only_movement_delta_pct": "float64",
    "observational_only_movement_direction": "string",
    "observational_only_movement_intensity": "string",
    "observational_only_availability_horizon": "string",
}

_missing_arrow = [c for c in EXPORT_COLUMNS if c not in EXPORT_ARROW_TYPE_NAMES]
_extra_arrow = [c for c in EXPORT_ARROW_TYPE_NAMES if c not in EXPORT_COLUMNS]
if _missing_arrow or _extra_arrow:
    raise RuntimeError(
        f"EXPORT_ARROW_TYPE_NAMES mismatch: missing={_missing_arrow} extra={_extra_arrow}"
    )

FORBIDDEN_PRE_SUBSTRINGS = (
    "closing",
    "movement",
    "post_match",
    "event_stat",
    "ft_home",
    "ft_away",
    "ht_home",
    "ht_away",
    "profit",
    "won",
    "lost",
    "void",
)


def column_role(name: str) -> str:
    if name in IDENTITY_COLS:
        return "identity"
    if name.startswith("pre_"):
        return "pre_feature"
    if name.startswith("target_"):
        return "post_target"
    if name.startswith("observational_only_"):
        return "observational_only"
    return "other"


def allowed_as_predictor(name: str) -> bool:
    return column_role(name) == "pre_feature"


def build_data_dictionary_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for col in EXPORT_COLUMNS:
        role = column_role(col)
        rows.append(
            {
                "column": col,
                "role": role,
                "allowed_as_predictor": allowed_as_predictor(col),
                "group": (
                    "identity"
                    if role == "identity"
                    else (
                        "pre"
                        if role == "pre_feature"
                        else ("target" if role == "post_target" else "observational")
                    )
                ),
                "notes": (
                    "Join key — not an ML predictor"
                    if role == "identity"
                    else (
                        "Pre-match feature from V4 snapshot / market_results"
                        if role == "pre_feature"
                        else (
                            "Post-match target — never use as predictor"
                            if role == "post_target"
                            else "Post-horizon observational — allowed_as_predictor=false"
                        )
                    )
                ),
            }
        )
    return rows


def assert_anti_leakage_schema() -> None:
    """Fail-fast se una colonna pre_* viola anti-leakage."""
    for col in EXPORT_COLUMNS:
        if not col.startswith("pre_"):
            continue
        low = col.lower()
        for bad in FORBIDDEN_PRE_SUBSTRINGS:
            if bad in low:
                raise RuntimeError(f"anti_leakage_violation: {col} contains '{bad}'")


def _row_for_export(row: dict[str, Any]) -> dict[str, Any]:
    return {c: row.get(c) for c in EXPORT_COLUMNS}


def _pa_type_from_name(pa: Any, name: str) -> Any:
    mapping = {
        "int64": pa.int64(),
        "float64": pa.float64(),
        "bool": pa.bool_(),
        "string": pa.string(),
    }
    try:
        return mapping[name]
    except KeyError as exc:
        raise RuntimeError(f"unsupported_arrow_type_name: {name}") from exc


def build_export_arrow_schema(export_cols: list[str] | None = None) -> Any:
    """Schema Arrow esplicito e canonico per ParquetWriter (niente inferenza)."""
    import pyarrow as pa

    cols = list(export_cols) if export_cols is not None else list(EXPORT_COLUMNS)
    fields = []
    for c in cols:
        type_name = EXPORT_ARROW_TYPE_NAMES.get(c)
        if type_name is None:
            raise RuntimeError(f"missing_arrow_type_for_column: {c}")
        fields.append(pa.field(c, _pa_type_from_name(pa, type_name), nullable=True))
    return pa.schema(fields)


def _coerce_cell(val: Any, type_name: str) -> Any:
    """Normalizza valori Python prima di pa.array tipizzato."""
    if val is None:
        return None
    if type_name == "string":
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False, default=str)
        return str(val)
    if type_name == "bool":
        return bool(val)
    if type_name == "int64":
        if isinstance(val, bool):
            return int(val)
        return int(val)
    if type_name == "float64":
        return float(val)
    return val


def table_from_export_batch(
    batch: list[dict[str, Any]],
    *,
    schema: Any | None = None,
    export_cols: list[str] | None = None,
) -> Any:
    """Costruisce un Table tipizzato con lo schema canonico (stabile tra chunk)."""
    import pyarrow as pa

    cols = list(export_cols) if export_cols is not None else list(EXPORT_COLUMNS)
    arrow_schema = schema if schema is not None else build_export_arrow_schema(cols)
    arrays = []
    for c in cols:
        type_name = EXPORT_ARROW_TYPE_NAMES[c]
        field_type = arrow_schema.field(c).type
        values = [_coerce_cell(r.get(c), type_name) for r in batch]
        arrays.append(pa.array(values, type=field_type))
    return pa.Table.from_arrays(arrays, schema=arrow_schema)


def write_discovery_dataset_files(
    db: Session,
    *,
    run_ids: list[int],
    mode: str,
    filters: dict[str, Any] | None,
    include_observational_only: bool = True,
    dest_dir: Path,
    chunk_size: int = SNAPSHOT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Scrive parquet (+ csv opzionale) + metadata + dictionary in dest_dir. Chunked."""
    assert_anti_leakage_schema()
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CecchinoLabImportError(
            "pyarrow_missing",
            "pyarrow richiesto per export Pattern Discovery",
            status_code=500,
        ) from exc

    if mode not in (EXPORT_MODE_FULL, EXPORT_MODE_FILTERED):
        raise CecchinoLabImportError(
            "invalid_export_mode",
            f"mode deve essere {EXPORT_MODE_FULL} o {EXPORT_MODE_FILTERED}",
            status_code=400,
        )

    runs = _resolve_runs(db, run_ids)
    apply_filters = mode == EXPORT_MODE_FILTERED
    parsed = parse_pattern_lab_filters(filters) if apply_filters else parse_pattern_lab_filters({})

    parquet_path = dest_dir / "pattern_lab_dataset.parquet"
    csv_path = dest_dir / "pattern_lab_dataset.csv"
    dict_path = dest_dir / "data_dictionary.csv"
    meta_path = dest_dir / "metadata.json"

    export_cols = list(EXPORT_COLUMNS)
    if not include_observational_only:
        export_cols = [c for c in export_cols if not c.startswith("observational_only_")]

    arrow_schema = build_export_arrow_schema(export_cols)
    writer = pq.ParquetWriter(str(parquet_path), arrow_schema, compression="zstd")
    csv_file = csv_path.open("w", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=export_cols, extrasaction="ignore")
    csv_writer.writeheader()

    row_count = 0
    match_ids: set[tuple[int, int]] = set()
    batch: list[dict[str, Any]] = []
    batch_flush = max(200, min(chunk_size * 4, 2000))

    def flush_batch() -> None:
        nonlocal batch
        if not batch:
            return
        slim = [{c: r.get(c) for c in export_cols} for r in batch]
        table = table_from_export_batch(slim, schema=arrow_schema, export_cols=export_cols)
        writer.write_table(table)
        for r in slim:
            csv_writer.writerow(r)
        batch = []

    try:
        for row in iter_pattern_lab_rows(
            db,
            run_ids,
            filters=parsed if apply_filters else {"eligibility": parsed.get("eligibility")},
            apply_filters=apply_filters,
            chunk_size=chunk_size,
        ):
            # full mode still respects eligibility from filters eligibility key
            if not apply_filters:
                # re-apply only eligibility already in iterator
                pass
            exported = _row_for_export(row)
            if not include_observational_only:
                exported = {k: v for k, v in exported.items() if not k.startswith("observational_only_")}
            batch.append(exported)
            row_count += 1
            run_id = row.get("run_id")
            lab_match_id = row.get("lab_match_id")
            if run_id is not None and lab_match_id is not None:
                match_ids.add((int(run_id), int(lab_match_id)))
            if len(batch) >= batch_flush:
                flush_batch()
        flush_batch()
    finally:
        writer.close()
        csv_file.close()

    include_csv = row_count <= CSV_ROW_THRESHOLD
    if not include_csv and csv_path.exists():
        csv_path.unlink(missing_ok=True)

    # data dictionary
    dict_rows = build_data_dictionary_rows()
    if not include_observational_only:
        dict_rows = [r for r in dict_rows if not str(r["column"]).startswith("observational_only_")]
    with dict_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["column", "role", "allowed_as_predictor", "group", "notes"],
        )
        w.writeheader()
        for r in dict_rows:
            w.writerow(r)

    quote_policies = []
    module_versions = []
    for run in runs:
        if isinstance(run.quote_policy_json, dict):
            quote_policies.append(run.quote_policy_json)
        if isinstance(run.module_policy_json, dict):
            module_versions.append(
                {
                    "run_id": int(run.id),
                    "scan_version": run.scan_version,
                    "source_git_commit": run.source_git_commit,
                    "module_policy": {
                        k: run.module_policy_json.get(k)
                        for k in (
                            "run_scope",
                            "quote_policy_version",
                            "feature_contract_version",
                        )
                        if k in run.module_policy_json
                    },
                }
            )

    metadata = {
        "export_kind": PATTERN_LAB_EXPORT_KIND,
        "pattern_lab_version": PATTERN_LAB_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "run_ids": [int(r) for r in run_ids],
        "seasons": sorted({str(r.season_label) for r in runs}),
        "scan_versions": sorted({str(r.scan_version) for r in runs if r.scan_version}),
        "source_git_commits": sorted(
            {str(r.source_git_commit) for r in runs if r.source_git_commit}
        ),
        "quote_policy": quote_policies[0] if len(quote_policies) == 1 else quote_policies,
        "module_versions": module_versions,
        "match_count": len(match_ids),
        "market_row_count": row_count,
        "csv_included": include_csv,
        "csv_row_threshold": CSV_ROW_THRESHOLD,
        "include_observational_only": include_observational_only,
        "filters_applied": parsed if apply_filters else None,
        "bet_builder_sort_policy": PATTERN_LAB_SORT_POLICY_BB,
        "feature_roles": {
            "pre_features": [c for c in export_cols if c.startswith("pre_")],
            "post_targets": [c for c in export_cols if c.startswith("target_")],
            "observational_only": [
                c for c in export_cols if c.startswith("observational_only_")
            ],
            "identity": [c for c in export_cols if c in IDENTITY_COLS],
        },
        "anti_leakage": {
            "prediction_horizon": "pre_match_kickoff",
            "observational_only_allowed_as_predictor": False,
            "excluded_from_pre_features": [
                "closing_odds",
                "quote_movement",
                "post_match_event_stats",
            ],
            "goal_intensity_naming": "pre_goal_v4_compat_* (not live V5)",
        },
    }
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "metadata": metadata,
        "parquet_path": parquet_path,
        "csv_path": csv_path if include_csv else None,
        "dictionary_path": dict_path,
        "metadata_path": meta_path,
        "row_count": row_count,
    }


def build_discovery_export_zip_response(
    db: Session,
    *,
    run_ids: list[int],
    mode: str = EXPORT_MODE_FULL,
    filters: dict[str, Any] | None = None,
    include_observational_only: bool = True,
) -> StreamingResponse:
    """Genera ZIP su tempfile e streamma — Pattern Lab non tiene il dataset in RAM."""
    tmp = tempfile.TemporaryDirectory(prefix="pattern_lab_export_")
    dest = Path(tmp.name)
    try:
        info = write_discovery_dataset_files(
            db,
            run_ids=run_ids,
            mode=mode,
            filters=filters,
            include_observational_only=include_observational_only,
            dest_dir=dest,
        )
        zip_path = dest / "pattern_lab_discovery.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(info["parquet_path"], arcname="pattern_lab_dataset.parquet")
            if info["csv_path"] and Path(info["csv_path"]).exists():
                zf.write(info["csv_path"], arcname="pattern_lab_dataset.csv")
            zf.write(info["metadata_path"], arcname="metadata.json")
            zf.write(info["dictionary_path"], arcname="data_dictionary.csv")

        # Read zip in chunks for StreamingResponse; cleanup after iterate
        zip_bytes_path = zip_path

        def _iter() -> Iterator[bytes]:
            try:
                with open(zip_bytes_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 256)
                        if not chunk:
                            break
                        yield chunk
            finally:
                tmp.cleanup()

        run_tag = "-".join(str(r) for r in run_ids[:5])
        filename = f"pattern_lab_discovery_runs_{run_tag}.zip"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pattern-Lab-Rows": str(info["row_count"]),
            "X-Pattern-Lab-Mode": mode,
        }
        return StreamingResponse(_iter(), media_type="application/zip", headers=headers)
    except Exception:
        tmp.cleanup()
        raise


def validate_export_gate_artifacts(dest_dir: Path, *, expected_min_rows: int = 1) -> list[str]:
    """Controlli gate post-export (usati da script Run #15). Ritorna lista errori."""
    errors: list[str] = []
    parquet_path = dest_dir / "pattern_lab_dataset.parquet"
    meta_path = dest_dir / "metadata.json"
    dict_path = dest_dir / "data_dictionary.csv"
    if not parquet_path.exists():
        errors.append("missing parquet")
        return errors
    try:
        import pyarrow.parquet as pq

        table = pq.read_table(str(parquet_path))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"parquet_unreadable: {exc}")
        return errors

    n = table.num_rows
    if n < expected_min_rows:
        errors.append(f"row_count_too_low: {n}")

    names = set(table.column_names)
    for col in names:
        if col.startswith("pre_"):
            low = col.lower()
            for bad in FORBIDDEN_PRE_SUBSTRINGS:
                if bad in low:
                    errors.append(f"pre_leakage_column: {col}")

    required_groups = [
        "pre_purch_v36_score",
        "pre_signal_active",
        "pre_rating",
        "pre_balance_geometry",
        "pre_goal_v4_compat_composite",
        "target_profit_1u",
        "target_won",
    ]
    for col in required_groups:
        if col not in names:
            errors.append(f"missing_column: {col}")

    if not meta_path.exists():
        errors.append("missing metadata.json")
    else:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("market_row_count") != n:
            errors.append(
                f"metadata_row_mismatch: meta={meta.get('market_row_count')} parquet={n}"
            )
        if not meta.get("anti_leakage"):
            errors.append("metadata_missing_anti_leakage")

    if not dict_path.exists():
        errors.append("missing data_dictionary.csv")
    else:
        with dict_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        obs = [r for r in rows if str(r.get("column", "")).startswith("observational_only_")]
        for r in obs:
            if str(r.get("allowed_as_predictor")).lower() not in ("false", "0"):
                errors.append(f"observational_predictor_true: {r.get('column')}")
        targets = [r for r in rows if str(r.get("column", "")).startswith("target_")]
        if not targets:
            errors.append("dictionary_missing_targets")

    return errors
