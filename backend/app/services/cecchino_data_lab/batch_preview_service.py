"""Preview multipla CSV Cecchino Lab — orchestratore read-only."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_import import CecchinoLabImport
from app.services.cecchino_data_lab.constants import (
    BATCH_ISSUES_CAP,
    BATCH_MAX_FILE_BYTES,
    BATCH_MAX_FILES,
    BATCH_PREVIEW_ROWS,
    PARSER_VERSION,
    SOURCE_PROVIDER,
)
from app.services.cecchino_data_lab.division_detect import (
    MAPPING_INVALID_CSV,
    MAPPING_MAPPED,
    MAPPING_MISSING_DIVISION,
    MAPPING_MIXED_DIVISIONS,
    MAPPING_UNKNOWN_DIVISION,
    detect_division,
)
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.preview_service import preview_csv_bytes

IMPORT_STATUS_READY = "ready"
IMPORT_STATUS_READY_WITH_WARNINGS = "ready_with_warnings"
IMPORT_STATUS_BLOCKED = "blocked"
IMPORT_STATUS_ALREADY_IMPORTED = "already_imported"
IMPORT_STATUS_DUPLICATE_IN_BATCH = "duplicate_in_batch"
IMPORT_STATUS_DUPLICATE_COMPETITION_IN_BATCH = "duplicate_competition_in_batch"
IMPORT_STATUS_DATASET_ALREADY_EXISTS = "dataset_already_exists"

READY_STATUSES = frozenset({IMPORT_STATUS_READY, IMPORT_STATUS_READY_WITH_WARNINGS})


def _empty_item(
    *,
    client_file_id: str,
    filename: str,
    file_sha256: str = "",
    file_size_bytes: int = 0,
    season_label: str,
    mapping_status: str,
    import_status: str,
    blocking_reason: str | None,
    division_code: str | None = None,
    competition_key: str | None = None,
    competition_name: str | None = None,
    country: str | None = None,
    timezone: str | None = None,
    dataset_id: int | None = None,
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "client_file_id": client_file_id,
        "filename": filename,
        "file_sha256": file_sha256,
        "file_size_bytes": file_size_bytes,
        "division_code": division_code,
        "competition_key": competition_key,
        "competition_name": competition_name,
        "country": country,
        "timezone": timezone,
        "season_label": season_label,
        "rows_total": None,
        "rows_importable": None,
        "rows_skipped": None,
        "errors_count": 0,
        "warnings_count": 0,
        "info_count": 0,
        "bet365_coverage": {},
        "mapping_status": mapping_status,
        "import_status": import_status,
        "dataset_id": dataset_id,
        "blocking_reason": blocking_reason,
        "issues": issues or [],
        "preview_rows": [],
        "recognized_columns": [],
        "unexpected_columns": [],
        "missing_required_columns": [],
    }


def _find_existing_import(db: Session, file_sha256: str) -> CecchinoLabImport | None:
    return (
        db.query(CecchinoLabImport)
        .filter(
            CecchinoLabImport.file_sha256 == file_sha256,
            CecchinoLabImport.parser_version == PARSER_VERSION,
        )
        .one_or_none()
    )


def _find_existing_dataset(
    db: Session,
    *,
    competition_name: str,
    country: str,
    season_label: str,
) -> CecchinoLabDataset | None:
    return (
        db.query(CecchinoLabDataset)
        .filter(
            CecchinoLabDataset.competition_name == competition_name,
            CecchinoLabDataset.country == country,
            CecchinoLabDataset.season_label == season_label,
            CecchinoLabDataset.source_provider == SOURCE_PROVIDER,
        )
        .one_or_none()
    )


def batch_preview_csv_files(
    db: Session,
    files: list[tuple[str, bytes]],
    *,
    season_label: str,
) -> dict[str, Any]:
    """Analizza più CSV senza scrivere sul DB.

    files: lista di (filename, raw_bytes) nell'ordine della richiesta.
    """
    if not season_label or not season_label.strip():
        raise CecchinoLabImportError(
            "missing_season_label",
            "Stagione obbligatoria.",
            status_code=400,
        )
    season = season_label.strip()

    if not files:
        raise CecchinoLabImportError(
            "empty_batch",
            "Nessun file fornito. Carica almeno un CSV.",
            status_code=400,
        )

    if len(files) > BATCH_MAX_FILES:
        raise CecchinoLabImportError(
            "batch_too_large",
            f"Massimo {BATCH_MAX_FILES} file per richiesta.",
            status_code=400,
            details={"max_files": BATCH_MAX_FILES, "received": len(files)},
        )

    # Pass 1: per-file validation + mapping + preview
    items: list[dict[str, Any]] = []
    for idx, (filename, raw) in enumerate(files):
        client_file_id = str(idx)
        name = filename or f"file_{idx}.csv"

        if not name.lower().endswith(".csv"):
            items.append(
                _empty_item(
                    client_file_id=client_file_id,
                    filename=name,
                    file_size_bytes=len(raw),
                    season_label=season,
                    mapping_status=MAPPING_INVALID_CSV,
                    import_status=IMPORT_STATUS_BLOCKED,
                    blocking_reason="Solo file .csv sono ammessi.",
                )
            )
            continue

        if len(raw) > BATCH_MAX_FILE_BYTES:
            items.append(
                _empty_item(
                    client_file_id=client_file_id,
                    filename=name,
                    file_size_bytes=len(raw),
                    season_label=season,
                    mapping_status=MAPPING_INVALID_CSV,
                    import_status=IMPORT_STATUS_BLOCKED,
                    blocking_reason=(
                        f"File troppo grande ({len(raw)} byte). "
                        f"Limite: {BATCH_MAX_FILE_BYTES} byte."
                    ),
                )
            )
            continue

        detected = detect_division(raw)
        if detected.mapping_status != MAPPING_MAPPED or detected.competition is None:
            reason_map = {
                MAPPING_MISSING_DIVISION: detected.message or "Divisione mancante.",
                MAPPING_UNKNOWN_DIVISION: detected.message
                or f"Divisione sconosciuta: '{detected.division_code}'.",
                MAPPING_MIXED_DIVISIONS: detected.message
                or f"Più divisioni nel file: {detected.detected_divisions}.",
                MAPPING_INVALID_CSV: detected.message or "CSV non valido.",
            }
            items.append(
                _empty_item(
                    client_file_id=client_file_id,
                    filename=name,
                    file_sha256=detected.file_sha256,
                    file_size_bytes=detected.file_size_bytes,
                    season_label=season,
                    mapping_status=detected.mapping_status,
                    import_status=IMPORT_STATUS_BLOCKED,
                    blocking_reason=reason_map.get(
                        detected.mapping_status, detected.message or "File bloccato."
                    ),
                    division_code=detected.division_code,
                    issues=[],
                )
            )
            continue

        entry = detected.competition
        try:
            preview = preview_csv_bytes(
                raw,
                competition_key=entry.key,
                season_label=season,
                source_filename=name,
                preview_limit=BATCH_PREVIEW_ROWS,
                issues_cap=BATCH_ISSUES_CAP,
            )
        except CecchinoLabImportError as exc:
            items.append(
                _empty_item(
                    client_file_id=client_file_id,
                    filename=name,
                    file_sha256=detected.file_sha256,
                    file_size_bytes=detected.file_size_bytes,
                    season_label=season,
                    mapping_status=MAPPING_MAPPED,
                    import_status=IMPORT_STATUS_BLOCKED,
                    blocking_reason=exc.message,
                    division_code=entry.division_code,
                    competition_key=entry.key,
                    competition_name=entry.display_name,
                    country=entry.country,
                    timezone=entry.timezone,
                )
            )
            continue

        importable = bool(preview.get("summary", {}).get("importable"))
        errors_count = int(preview.get("errors_count") or 0)
        warnings_count = int(preview.get("warnings_count") or 0)
        info_count = int(preview.get("info_count") or 0)
        rows_total = preview.get("rows_total")
        rows_importable = preview.get("summary", {}).get("rows_importable")
        rows_skipped = preview.get("summary", {}).get("rows_skipped")

        if not importable:
            import_status = IMPORT_STATUS_BLOCKED
            blocking_reason = "Il file non è importabile (errori di validazione)."
        elif warnings_count > 0:
            import_status = IMPORT_STATUS_READY_WITH_WARNINGS
            blocking_reason = None
        else:
            import_status = IMPORT_STATUS_READY
            blocking_reason = None

        # DB checks (read-only) — may override ready statuses later in priority pass
        existing_imp = _find_existing_import(db, preview["file_sha256"])
        existing_ds = _find_existing_dataset(
            db,
            competition_name=entry.display_name,
            country=entry.country,
            season_label=season,
        )

        items.append(
            {
                "client_file_id": client_file_id,
                "filename": name,
                "file_sha256": preview["file_sha256"],
                "file_size_bytes": preview["file_size_bytes"],
                "division_code": entry.division_code,
                "competition_key": entry.key,
                "competition_name": entry.display_name,
                "country": entry.country,
                "timezone": entry.timezone,
                "season_label": season,
                "rows_total": rows_total,
                "rows_importable": rows_importable,
                "rows_skipped": rows_skipped,
                "errors_count": errors_count,
                "warnings_count": warnings_count,
                "info_count": info_count,
                "bet365_coverage": preview.get("bet365_coverage") or {},
                "mapping_status": MAPPING_MAPPED,
                "import_status": import_status,
                "dataset_id": existing_ds.id if existing_ds else None,
                "blocking_reason": blocking_reason,
                "issues": preview.get("issues") or [],
                "preview_rows": preview.get("preview_rows") or [],
                "recognized_columns": preview.get("recognized_columns") or [],
                "unexpected_columns": preview.get("unexpected_columns") or [],
                "missing_required_columns": preview.get("missing_required_columns") or [],
                "_existing_import_id": existing_imp.id if existing_imp else None,
                "_dataset_exists": existing_ds is not None,
            }
        )

    # Pass 2: batch duplicates (SHA + competition)
    sha_groups: dict[str, list[int]] = {}
    comp_groups: dict[str, list[int]] = {}
    for i, item in enumerate(items):
        sha = item.get("file_sha256") or ""
        if sha:
            sha_groups.setdefault(sha, []).append(i)
        ck = item.get("competition_key")
        if ck and item.get("mapping_status") == MAPPING_MAPPED:
            comp_groups.setdefault(ck, []).append(i)

    duplicate_sha_indices: set[int] = set()
    for indices in sha_groups.values():
        if len(indices) > 1:
            duplicate_sha_indices.update(indices)

    duplicate_comp_indices: set[int] = set()
    for ck, indices in comp_groups.items():
        # Only flag if different SHAs (same competition twice with different files)
        shas = {items[i].get("file_sha256") for i in indices}
        if len(indices) > 1 and len(shas) > 1:
            duplicate_comp_indices.update(indices)
        elif len(indices) > 1 and len(shas) == 1:
            # Same file twice already covered by duplicate_in_batch
            pass

    # Pass 3: apply priority status
    for i, item in enumerate(items):
        if item["import_status"] == IMPORT_STATUS_BLOCKED:
            item.pop("_existing_import_id", None)
            item.pop("_dataset_exists", None)
            continue

        if i in duplicate_sha_indices:
            item["import_status"] = IMPORT_STATUS_DUPLICATE_IN_BATCH
            item["blocking_reason"] = (
                "Lo stesso file (SHA-256) è presente più volte nel batch. "
                "Rimuovi i duplicati prima dell'import."
            )
        elif i in duplicate_comp_indices:
            name = item.get("competition_name") or item.get("competition_key") or "campionato"
            item["import_status"] = IMPORT_STATUS_DUPLICATE_COMPETITION_IN_BATCH
            item["blocking_reason"] = (
                f"Nel batch sono presenti più file associati a {name} {season}. "
                f"Rimuovi i duplicati prima dell'import."
            )
        elif item.get("_existing_import_id") is not None:
            item["import_status"] = IMPORT_STATUS_ALREADY_IMPORTED
            item["blocking_reason"] = (
                "Questo file è già stato importato (stesso SHA-256 e parser)."
            )
        elif item.get("_dataset_exists"):
            name = item.get("competition_name") or "Dataset"
            item["import_status"] = IMPORT_STATUS_DATASET_ALREADY_EXISTS
            item["blocking_reason"] = (
                f"{name} {season} è già presente. "
                f"Utilizza 'Sostituisci CSV' nella tab Dataset per modificarlo."
            )
        # else keep ready / ready_with_warnings

        item.pop("_existing_import_id", None)
        item.pop("_dataset_exists", None)

    ready_count = sum(1 for it in items if it["import_status"] in READY_STATUSES)
    warning_count = sum(
        1 for it in items if it["import_status"] == IMPORT_STATUS_READY_WITH_WARNINGS
    )
    blocked_count = sum(
        1
        for it in items
        if it["import_status"]
        in {
            IMPORT_STATUS_BLOCKED,
            IMPORT_STATUS_DUPLICATE_IN_BATCH,
            IMPORT_STATUS_DUPLICATE_COMPETITION_IN_BATCH,
        }
    )
    already_imported_count = sum(
        1
        for it in items
        if it["import_status"]
        in {IMPORT_STATUS_ALREADY_IMPORTED, IMPORT_STATUS_DATASET_ALREADY_EXISTS}
    )

    rows_total = sum(int(it["rows_total"] or 0) for it in items)
    rows_importable = sum(
        int(it["rows_importable"] or 0)
        for it in items
        if it["import_status"] in READY_STATUSES
    )

    return {
        "status": "ok",
        "season_label": season,
        "files_total": len(items),
        "ready_count": ready_count,
        "warning_count": warning_count,
        "blocked_count": blocked_count,
        "already_imported_count": already_imported_count,
        "rows_total": rows_total,
        "rows_importable": rows_importable,
        "items": items,
    }
