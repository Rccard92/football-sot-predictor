"""Helpers condivisi preview/import: catalogo + controllo Div."""

from __future__ import annotations

from typing import Any

from app.services.cecchino_data_lab.competition_catalog import LabCompetition, get_competition
from app.services.cecchino_data_lab.constants import ISSUE_DIVISION_MISMATCH
from app.services.cecchino_data_lab.csv_parser import ParsedIssue, ParseResult, parse_football_data_csv
from app.services.cecchino_data_lab.errors import CecchinoLabImportError


def resolve_competition(competition_key: str) -> LabCompetition:
    entry = get_competition(competition_key)
    if entry is None:
        raise CecchinoLabImportError(
            "unknown_competition_key",
            f"Campionato sconosciuto: '{competition_key}'.",
            status_code=400,
            details={"competition_key": competition_key},
        )
    return entry


def _rebuild_issue_counts(parsed: ParseResult) -> None:
    match_issue_ids = {id(i) for m in parsed.matches for i in m.issues}
    file_scoped = [i for i in parsed.issues if id(i) not in match_issue_ids]
    all_issues = list(file_scoped)
    for m in parsed.matches:
        all_issues.extend(m.issues)
    parsed.issues = all_issues
    parsed.warnings_count = sum(1 for i in all_issues if i.severity == "warning")
    parsed.errors_count = sum(1 for i in all_issues if i.severity == "error")
    parsed.rows_importable = sum(1 for m in parsed.matches if m.importable)
    parsed.rows_skipped = len(parsed.matches) - parsed.rows_importable
    parsed.summary = {
        **(parsed.summary or {}),
        "importable": len(parsed.missing_required_columns) == 0 and parsed.rows_importable > 0,
        "rows_importable": parsed.rows_importable,
        "rows_skipped": parsed.rows_skipped,
        "warnings_count": parsed.warnings_count,
        "errors_count": parsed.errors_count,
    }


def apply_division_mismatch(parsed: ParseResult, expected_div: str) -> None:
    """Marca errori bloccanti se Div CSV ≠ division_code catalogo."""
    mismatch_rows: list[int] = []
    for m in parsed.matches:
        if not m.division_code:
            continue
        if m.division_code != expected_div:
            mismatch_rows.append(m.source_row_number)
            issue = ParsedIssue(
                severity="error",
                issue_code=ISSUE_DIVISION_MISMATCH,
                message=(
                    f"Riga {m.source_row_number}: Div '{m.division_code}' non coincide "
                    f"con il campionato selezionato (atteso '{expected_div}')."
                ),
                source_row_number=m.source_row_number,
                field_name="Div",
                raw_value=m.division_code,
                details={"expected": expected_div, "actual": m.division_code},
            )
            m.issues.append(issue)
            m.importable = False
            m.row_quality_status = "error"

    if not mismatch_rows:
        return

    parsed.issues.append(
        ParsedIssue(
            severity="error",
            issue_code=ISSUE_DIVISION_MISMATCH,
            message=(
                f"Colonna Div non coerente con il campionato selezionato "
                f"(atteso {expected_div}; {len(mismatch_rows)} righe non valide)."
            ),
            details={"expected": expected_div, "mismatch_rows": mismatch_rows[:50]},
        )
    )
    _rebuild_issue_counts(parsed)
    parsed.summary["importable"] = False
    parsed.summary["division_mismatch"] = True
    # Blocca intero file: nessuna riga importabile se c'è mismatch Div
    for m in parsed.matches:
        m.importable = False
    parsed.rows_importable = 0
    parsed.rows_skipped = len(parsed.matches)
    parsed.summary["rows_importable"] = 0
    parsed.summary["rows_skipped"] = len(parsed.matches)


def parse_with_catalog(
    raw: bytes,
    *,
    competition_key: str,
    season_label: str,
) -> tuple[LabCompetition, ParseResult]:
    entry = resolve_competition(competition_key)
    if not season_label or not season_label.strip():
        raise CecchinoLabImportError(
            "missing_season_label",
            "Stagione obbligatoria.",
            status_code=400,
        )
    parsed = parse_football_data_csv(raw, timezone_name=entry.timezone)
    apply_division_mismatch(parsed, entry.division_code)
    return entry, parsed


def catalog_meta(entry: LabCompetition, season_label: str) -> dict[str, Any]:
    return {
        "competition_key": entry.key,
        "competition_name": entry.display_name,
        "country": entry.country,
        "division_code": entry.division_code,
        "timezone": entry.timezone,
        "season_label": season_label.strip(),
    }
