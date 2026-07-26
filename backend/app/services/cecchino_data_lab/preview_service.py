"""Preview CSV senza scrittura DB."""

from __future__ import annotations

from typing import Any

from app.services.cecchino_data_lab.import_helpers import catalog_meta, parse_with_catalog


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    return {
        "severity": issue.severity,
        "issue_code": issue.issue_code,
        "message": issue.message,
        "source_row_number": issue.source_row_number,
        "field_name": issue.field_name,
        "raw_value": issue.raw_value,
        "details": issue.details,
    }


def preview_csv_bytes(
    raw: bytes,
    *,
    competition_key: str,
    season_label: str,
    source_filename: str | None = None,
    preview_limit: int = 8,
    issues_cap: int = 200,
) -> dict[str, Any]:
    entry, result = parse_with_catalog(
        raw,
        competition_key=competition_key,
        season_label=season_label,
        preview_limit=preview_limit,
    )
    meta = catalog_meta(entry, season_label)
    # result.issues already includes file-level + match issues (no double-append)
    issues = [_issue_to_dict(i) for i in result.issues]
    issues_preview = issues[:issues_cap]
    return {
        "source_filename": source_filename,
        **meta,
        "parser_version": result.parser_version,
        "file_sha256": result.file_sha256,
        "file_size_bytes": result.file_size_bytes,
        "encoding": result.encoding,
        "encoding_fallback": result.encoding_fallback,
        "headers": result.headers,
        "recognized_columns": result.recognized_columns,
        "missing_required_columns": result.missing_required_columns,
        "missing_optional_known": result.missing_optional_known,
        "unexpected_columns": result.unexpected_columns,
        "rows_total": result.rows_total,
        "preview_rows": result.preview_rows,
        "bet365_coverage": result.bet365_coverage,
        "warnings_count": result.warnings_count,
        "errors_count": result.errors_count,
        "info_count": result.info_count,
        "issues": issues_preview,
        "issues_truncated": len(issues) > len(issues_preview),
        "summary": result.summary,
    }
