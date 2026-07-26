"""Sostituzione controllata di un singolo dataset Cecchino Lab."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_lab_data_issue import CecchinoLabDataIssue
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_import import CecchinoLabImport
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.competition_catalog import get_competition_by_division
from app.services.cecchino_data_lab.constants import PARSER_VERSION, REPLACE_CONFIRM_TOKEN
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.import_helpers import parse_with_catalog
from app.services.cecchino_data_lab.import_service import write_import_rows


def replace_dataset_csv(
    db: Session,
    dataset_id: int,
    raw: bytes,
    *,
    source_filename: str = "upload.csv",
    confirm: str | None = None,
) -> dict[str, Any]:
    if confirm != REPLACE_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "invalid_confirm_token",
            f"Conferma richiesta: inviare confirm={REPLACE_CONFIRM_TOKEN}",
            status_code=400,
        )

    dataset = (
        db.query(CecchinoLabDataset)
        .filter(CecchinoLabDataset.id == dataset_id)
        .one_or_none()
    )
    if dataset is None:
        raise CecchinoLabImportError(
            "dataset_not_found",
            f"Dataset {dataset_id} non trovato.",
            status_code=404,
        )

    entry = get_competition_by_division(dataset.division_code)
    if entry is None:
        raise CecchinoLabImportError(
            "unknown_division_code",
            f"Impossibile risolvere il campionato dal division_code '{dataset.division_code}'.",
            status_code=400,
            details={"division_code": dataset.division_code, "dataset_id": dataset_id},
        )

    # Full analysis BEFORE any deletion
    _, parsed = parse_with_catalog(
        raw,
        competition_key=entry.key,
        season_label=dataset.season_label,
    )

    if parsed.missing_required_columns:
        raise CecchinoLabImportError(
            "invalid_header",
            "Intestazione CSV non valida.",
            status_code=400,
            details={"missing": parsed.missing_required_columns},
        )

    if parsed.summary.get("division_mismatch"):
        raise CecchinoLabImportError(
            "division_mismatch",
            (
                f"La colonna Div del CSV non coincide con {entry.division_code} "
                f"({entry.display_name})."
            ),
            status_code=400,
            details={
                "expected": entry.division_code,
                "competition_key": entry.key,
                "errors_count": parsed.errors_count,
            },
        )

    if not parsed.summary.get("importable") or parsed.rows_importable == 0:
        raise CecchinoLabImportError(
            "no_importable_rows",
            "Il nuovo CSV non è importabile.",
            status_code=400,
            details={
                "errors_count": parsed.errors_count,
                "warnings_count": parsed.warnings_count,
            },
        )

    previous_matches = dataset.matches_count
    try:
        import_ids = [
            r[0]
            for r in db.query(CecchinoLabImport.id)
            .filter(CecchinoLabImport.dataset_id == dataset.id)
            .all()
        ]

        if import_ids:
            db.query(CecchinoLabDataIssue).filter(
                CecchinoLabDataIssue.import_id.in_(import_ids)
            ).delete(synchronize_session=False)

        db.query(CecchinoLabMatch).filter(
            CecchinoLabMatch.dataset_id == dataset.id
        ).delete(synchronize_session=False)

        db.query(CecchinoLabImport).filter(
            CecchinoLabImport.dataset_id == dataset.id
        ).delete(synchronize_session=False)

        # Flush so unique (file_sha256, parser_version) is freed before reinsert
        db.flush()

        imp, imported = write_import_rows(
            db,
            dataset=dataset,
            parsed=parsed,
            source_filename=source_filename,
        )

        db.commit()
        db.refresh(imp)
        db.refresh(dataset)

        return {
            "status": "replaced",
            "dataset_id": dataset.id,
            "dataset_key": dataset.dataset_key,
            "competition_name": dataset.competition_name,
            "season_label": dataset.season_label,
            "previous_matches_count": previous_matches,
            "import_id": imp.id,
            "rows_total": parsed.rows_total,
            "rows_imported": imported,
            "rows_skipped": parsed.rows_total - imported,
            "warnings_count": parsed.warnings_count,
            "errors_count": parsed.errors_count,
            "info_count": parsed.info_count,
            "bet365_coverage": parsed.bet365_coverage,
            "file_sha256": parsed.file_sha256,
            "parser_version": PARSER_VERSION,
            "data_quality_status": dataset.data_quality_status,
        }
    except CecchinoLabImportError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
