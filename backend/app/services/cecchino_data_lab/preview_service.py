"""Preview CSV senza scrittura DB."""

from __future__ import annotations

from typing import Any

from app.services.cecchino_data_lab.csv_parser import ParseResult, parse_football_data_csv


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
    competition_name: str,
    country: str,
    season_label: str,
    timezone_name: str = "Europe/Rome",
    division_code: str | None = None,
    source_filename: str | None = None,
) -> dict[str, Any]:
    result: ParseResult = parse_football_data_csv(raw, timezone_name=timezone_name)
    issues = [_issue_to_dict(i) for i in result.issues]
    # Cap issues in response for large files
    issues_preview = issues[:200]
    return {
        "source_filename": source_filename,
        "competition_name": competition_name,
        "country": country,
        "season_label": season_label,
        "division_code": division_code,
        "timezone": timezone_name,
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
        "issues": issues_preview,
        "issues_truncated": len(issues) > len(issues_preview),
        "summary": result.summary,
    }
