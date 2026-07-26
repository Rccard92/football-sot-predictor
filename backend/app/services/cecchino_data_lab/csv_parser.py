"""Parser CSV Football-Data per Cecchino Lab."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.services.cecchino_data_lab.constants import (
    ALL_KNOWN_HEADERS,
    BET365_COLUMN_MAP,
    BET365_HEADERS,
    ISSUE_IRREGULAR_COLUMN_COUNT,
    ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS,
    KNOWN_RESULT_HEADERS,
    PARSER_VERSION,
    RAW_EXTRA_COLUMNS_KEY,
    REQUIRED_HEADERS,
)
from app.services.cecchino_data_lab.csv_encoding import DecodedCsv, decode_csv_bytes


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def parse_football_date(raw: str | None) -> date | None:
    """Date Football-Data: gg/mm/aaaa oppure gg/mm/aa."""
    s = _blank_to_none(raw)
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_football_time(raw: str | None) -> time | None:
    s = _blank_to_none(raw)
    if not s:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def parse_int(raw: str | None) -> int | None:
    s = _blank_to_none(raw)
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(Decimal(s.replace(",", ".")))
        except (InvalidOperation, ValueError):
            return None


def parse_decimal(raw: str | None) -> Decimal | None:
    s = _blank_to_none(raw)
    if s is None:
        return None
    try:
        return Decimal(s.replace(",", "."))
    except InvalidOperation:
        return None


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass
class ParsedIssue:
    severity: str
    issue_code: str
    message: str
    source_row_number: int | None = None
    field_name: str | None = None
    raw_value: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class ParsedMatchRow:
    source_row_number: int
    raw: dict[str, Any]
    division_code: str | None = None
    match_date: date | None = None
    match_time: time | None = None
    kickoff_at: datetime | None = None
    home_team: str | None = None
    away_team: str | None = None
    referee: str | None = None
    ft_home_goals: int | None = None
    ft_away_goals: int | None = None
    ft_result: str | None = None
    ht_home_goals: int | None = None
    ht_away_goals: int | None = None
    ht_result: str | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_yellow_cards: int | None = None
    away_yellow_cards: int | None = None
    home_red_cards: int | None = None
    away_red_cards: int | None = None
    bet365_home: Decimal | None = None
    bet365_draw: Decimal | None = None
    bet365_away: Decimal | None = None
    bet365_over_25: Decimal | None = None
    bet365_under_25: Decimal | None = None
    asian_handicap_home_line: Decimal | None = None
    bet365_ah_home: Decimal | None = None
    bet365_ah_away: Decimal | None = None
    bet365_closing_home: Decimal | None = None
    bet365_closing_draw: Decimal | None = None
    bet365_closing_away: Decimal | None = None
    bet365_closing_over_25: Decimal | None = None
    bet365_closing_under_25: Decimal | None = None
    asian_handicap_closing_home_line: Decimal | None = None
    bet365_closing_ah_home: Decimal | None = None
    bet365_closing_ah_away: Decimal | None = None
    result_ft_ready: bool = False
    result_ht_ready: bool = False
    statistics_ready: bool = False
    bet365_1x2_pre_ready: bool = False
    bet365_1x2_closing_ready: bool = False
    bet365_ou25_pre_ready: bool = False
    bet365_ou25_closing_ready: bool = False
    row_quality_status: str = "partial"
    issues: list[ParsedIssue] = field(default_factory=list)
    importable: bool = True


@dataclass
class ParseResult:
    parser_version: str
    file_sha256: str
    file_size_bytes: int
    encoding: str
    encoding_fallback: bool
    headers: list[str]
    recognized_columns: list[str]
    missing_required_columns: list[str]
    missing_optional_known: list[str]
    unexpected_columns: list[str]
    rows_total: int
    preview_rows: list[dict[str, Any]]
    matches: list[ParsedMatchRow]
    issues: list[ParsedIssue]
    rows_importable: int
    rows_skipped: int
    warnings_count: int
    errors_count: int
    info_count: int = 0
    bet365_coverage: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


_SEASON_RE = re.compile(r"^(\d{4})[/\-](\d{2}|\d{4})$")


def parse_season_years(season_label: str) -> tuple[int | None, int | None]:
    s = season_label.strip()
    m = _SEASON_RE.match(s)
    if not m:
        try:
            y = int(s)
            return y, y + 1
        except ValueError:
            return None, None
    start = int(m.group(1))
    end_raw = m.group(2)
    if len(end_raw) == 2:
        end = 2000 + int(end_raw) if int(end_raw) < 100 else int(end_raw)
        if end < start:
            end = start // 100 * 100 + int(end_raw)
            if end < start:
                end += 100
    else:
        end = int(end_raw)
    return start, end


def build_dataset_key(competition_name: str, country: str, season_label: str) -> str:
    def slug(v: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", v.strip().lower()).strip("-")

    return f"{slug(country)}-{slug(competition_name)}-{slug(season_label)}"


def _extra_columns_from_values(
    extra_values: list[Any],
    *,
    header_columns: int,
) -> list[dict[str, Any]]:
    """Build explicit __extra_columns__ entries (1-based CSV positions)."""
    extras: list[dict[str, Any]] = []
    for i, val in enumerate(extra_values):
        extras.append(
            {
                "position": header_columns + i + 1,
                "value": None if val is None else str(val),
            }
        )
    return extras


def _row_to_match(
    row: dict[str, str | None],
    row_number: int,
    timezone_name: str,
    expected_col_count: int,
    *,
    extra_columns: list[dict[str, Any]] | None = None,
) -> ParsedMatchRow:
    from app.services.cecchino_data_lab.quality import compute_row_quality_flags
    from app.services.cecchino_data_lab.validators import validate_match_row

    raw_dict: dict[str, Any] = {k: (_blank_to_none(v) if isinstance(v, str) else v) for k, v in row.items()}
    # Preserve full original row including empty strings as None already applied
    for k, v in row.items():
        if k not in raw_dict:
            raw_dict[k] = v
    if extra_columns:
        raw_dict[RAW_EXTRA_COLUMNS_KEY] = extra_columns

    match = ParsedMatchRow(source_row_number=row_number, raw=raw_dict)
    match.division_code = _blank_to_none(row.get("Div"))
    match.match_date = parse_football_date(row.get("Date"))
    match.match_time = parse_football_time(row.get("Time"))
    match.home_team = _blank_to_none(row.get("HomeTeam"))
    match.away_team = _blank_to_none(row.get("AwayTeam"))
    match.referee = _blank_to_none(row.get("Referee"))
    match.ft_home_goals = parse_int(row.get("FTHG"))
    match.ft_away_goals = parse_int(row.get("FTAG"))
    match.ft_result = _blank_to_none(row.get("FTR"))
    match.ht_home_goals = parse_int(row.get("HTHG"))
    match.ht_away_goals = parse_int(row.get("HTAG"))
    match.ht_result = _blank_to_none(row.get("HTR"))
    match.home_shots = parse_int(row.get("HS"))
    match.away_shots = parse_int(row.get("AS"))
    match.home_shots_on_target = parse_int(row.get("HST"))
    match.away_shots_on_target = parse_int(row.get("AST"))
    match.home_fouls = parse_int(row.get("HF"))
    match.away_fouls = parse_int(row.get("AF"))
    match.home_corners = parse_int(row.get("HC"))
    match.away_corners = parse_int(row.get("AC"))
    match.home_yellow_cards = parse_int(row.get("HY"))
    match.away_yellow_cards = parse_int(row.get("AY"))
    match.home_red_cards = parse_int(row.get("HR"))
    match.away_red_cards = parse_int(row.get("AR"))

    for csv_col, field_name in BET365_COLUMN_MAP.items():
        setattr(match, field_name, parse_decimal(row.get(csv_col)))

    if match.match_date is not None:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Europe/Rome")
        t = match.match_time or time(0, 0)
        match.kickoff_at = datetime.combine(match.match_date, t, tzinfo=tz)

    # Column count: DictReader pads/truncates; detect via raw field size if available
    issues = validate_match_row(match, expected_col_count=expected_col_count, raw_row=row)
    match.issues = issues
    # Blocking errors prevent import of the row
    has_blocking = any(
        i.severity == "error"
        and i.issue_code
        in {
            "missing_home_team",
            "missing_away_team",
            "missing_division",
            "invalid_date",
            "same_team_home_away",
            "row_error",
        }
        for i in issues
    )
    if has_blocking:
        match.importable = False
    compute_row_quality_flags(match)
    if has_blocking:
        match.row_quality_status = "error"
    return match


def parse_football_data_csv(
    raw: bytes,
    *,
    timezone_name: str = "Europe/Rome",
    preview_limit: int = 8,
) -> ParseResult:
    decoded: DecodedCsv = decode_csv_bytes(raw)
    sha = file_sha256(raw)
    size = len(raw)
    issues: list[ParsedIssue] = []

    if not decoded.text.strip():
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code="empty_file",
                message="Il file CSV è vuoto.",
            )
        )
        return ParseResult(
            parser_version=PARSER_VERSION,
            file_sha256=sha,
            file_size_bytes=size,
            encoding=decoded.encoding,
            encoding_fallback=decoded.used_fallback,
            headers=[],
            recognized_columns=[],
            missing_required_columns=sorted(REQUIRED_HEADERS),
            missing_optional_known=[],
            unexpected_columns=[],
            rows_total=0,
            preview_rows=[],
            matches=[],
            issues=issues,
            rows_importable=0,
            rows_skipped=0,
            warnings_count=0,
            errors_count=1,
            info_count=0,
            bet365_coverage={},
            summary={"importable": False, "reason": "empty_file"},
        )

    if decoded.used_fallback:
        issues.append(
            ParsedIssue(
                severity="info",
                issue_code="encoding_fallback_cp1252",
                message="File decodificato con fallback CP1252 (non UTF-8).",
                details={"encoding": "cp1252"},
            )
        )

    reader = csv.DictReader(io.StringIO(decoded.text))
    if reader.fieldnames is None:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code="invalid_header",
                message="Intestazione CSV assente o non valida.",
            )
        )
        return ParseResult(
            parser_version=PARSER_VERSION,
            file_sha256=sha,
            file_size_bytes=size,
            encoding=decoded.encoding,
            encoding_fallback=decoded.used_fallback,
            headers=[],
            recognized_columns=[],
            missing_required_columns=sorted(REQUIRED_HEADERS),
            missing_optional_known=[],
            unexpected_columns=[],
            rows_total=0,
            preview_rows=[],
            matches=[],
            issues=issues,
            rows_importable=0,
            rows_skipped=0,
            warnings_count=0,
            errors_count=1,
            info_count=0,
            bet365_coverage={},
            summary={"importable": False, "reason": "invalid_header"},
        )

    headers = [h for h in reader.fieldnames if h is not None and h.strip() != ""]
    # Normalize: strip BOM leftovers on first header
    if headers and headers[0].startswith("\ufeff"):
        headers[0] = headers[0].lstrip("\ufeff")

    header_set = set(headers)
    missing_required = sorted(REQUIRED_HEADERS - header_set)
    recognized = sorted(header_set & ALL_KNOWN_HEADERS)
    unexpected = sorted(header_set - ALL_KNOWN_HEADERS)
    optional_known = (KNOWN_RESULT_HEADERS | BET365_HEADERS) - REQUIRED_HEADERS
    missing_optional = sorted(optional_known - header_set)

    if missing_required:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code="invalid_header",
                message=f"Intestazione non valida: mancano {', '.join(missing_required)}.",
                details={"missing": missing_required},
            )
        )

    if unexpected:
        issues.append(
            ParsedIssue(
                severity="info",
                issue_code="unexpected_columns",
                message=f"Colonne inattese preservate in raw_json: {', '.join(unexpected[:20])}"
                + ("…" if len(unexpected) > 20 else ""),
                details={"columns": unexpected},
            )
        )

    matches: list[ParsedMatchRow] = []
    preview_rows: list[dict[str, Any]] = []
    expected_col_count = len(headers)

    # Also detect ragged rows via csv.reader
    raw_lines = list(csv.reader(io.StringIO(decoded.text)))
    data_lines = raw_lines[1:] if raw_lines else []
    row_col_counts: list[tuple[int, int]] = []  # (source_row_number, col_count)

    for idx, row in enumerate(reader, start=2):  # 1-based with header = line 1
        # Fix fieldnames BOM on keys; capture DictReader restkey (None) extras
        cleaned: dict[str, str | None] = {}
        dict_extra_values: list[Any] = []
        for k, v in row.items():
            if k is None:
                if isinstance(v, (list, tuple)):
                    dict_extra_values.extend(v)
                elif v is not None:
                    dict_extra_values.append(v)
                continue
            key = k.lstrip("\ufeff") if isinstance(k, str) else k
            cleaned[key] = v

        line_idx = idx - 2
        actual_cols = expected_col_count
        line_extras: list[Any] = []
        if line_idx < len(data_lines):
            actual_cols = len(data_lines[line_idx])
            if actual_cols > expected_col_count:
                line_extras = list(data_lines[line_idx][expected_col_count:])
        row_col_counts.append((idx, actual_cols))

        # Prefer csv.reader trailing values; fall back to DictReader restkey
        extra_source = line_extras if line_extras else dict_extra_values
        extra_columns = (
            _extra_columns_from_values(extra_source, header_columns=expected_col_count)
            if extra_source
            else None
        )

        if missing_required:
            continue

        match = _row_to_match(
            cleaned,
            idx,
            timezone_name,
            expected_col_count,
            extra_columns=extra_columns,
        )
        matches.append(match)
        if len(preview_rows) < preview_limit:
            preview_row = dict(cleaned)
            if extra_columns:
                preview_row[RAW_EXTRA_COLUMNS_KEY] = extra_columns  # type: ignore[assignment]
            preview_rows.append(preview_row)

    # Aggregate column-count issues (uniform extras vs irregular)
    if data_lines and expected_col_count > 0 and row_col_counts:
        counts = [c for _, c in row_col_counts]
        unique_counts = set(counts)
        if len(unique_counts) == 1:
            only = next(iter(unique_counts))
            extra_n = only - expected_col_count
            if extra_n > 0:
                affected = len(row_col_counts)
                if extra_n == 1:
                    col_word = "1 colonna extra finale"
                else:
                    col_word = f"{extra_n} colonne extra finali"
                issues.append(
                    ParsedIssue(
                        severity="info",
                        issue_code=ISSUE_UNIFORM_EXTRA_TRAILING_COLUMNS,
                        message=(
                            f"Il file contiene {col_word} senza intestazione "
                            f"in tutte le {affected} righe. I valori sono stati "
                            f"preservati nel raw_json e non sono stati normalizzati."
                        ),
                        details={
                            "header_columns": expected_col_count,
                            "row_columns": only,
                            "extra_columns_count": extra_n,
                            "affected_rows": affected,
                            "raw_storage_key": RAW_EXTRA_COLUMNS_KEY,
                        },
                    )
                )
            elif only < expected_col_count:
                # Uniform shortfall — treat as irregular aggregate warning
                mismatched = [rn for rn, c in row_col_counts if c != expected_col_count]
                distribution: dict[str, int] = {}
                for c in counts:
                    key = str(c)
                    distribution[key] = distribution.get(key, 0) + 1
                issues.append(
                    ParsedIssue(
                        severity="warning",
                        issue_code=ISSUE_IRREGULAR_COLUMN_COUNT,
                        message=(
                            f"Numero colonne irregolare rispetto all'intestazione "
                            f"({expected_col_count}): distribuzione {distribution}."
                        ),
                        details={
                            "header_columns": expected_col_count,
                            "distribution": distribution,
                            "affected_rows_count": len(mismatched),
                            "sample_rows": mismatched[:20],
                        },
                    )
                )
        else:
            mismatched = [rn for rn, c in row_col_counts if c != expected_col_count]
            distribution = {}
            for c in counts:
                key = str(c)
                distribution[key] = distribution.get(key, 0) + 1
            issues.append(
                ParsedIssue(
                    severity="warning",
                    issue_code=ISSUE_IRREGULAR_COLUMN_COUNT,
                    message=(
                        f"Numero colonne irregolare rispetto all'intestazione "
                        f"({expected_col_count}): distribuzione {distribution}."
                    ),
                    details={
                        "header_columns": expected_col_count,
                        "distribution": distribution,
                        "affected_rows_count": len(mismatched),
                        "sample_rows": mismatched[:20],
                    },
                )
            )

    # Duplicate match detection within file
    from app.services.cecchino_data_lab.validators import flag_duplicate_matches

    flag_duplicate_matches(matches)

    rows_importable = sum(1 for m in matches if m.importable)
    rows_skipped = len(matches) - rows_importable

    all_issues = list(issues)
    for m in matches:
        all_issues.extend(m.issues)

    warnings_count = sum(1 for i in all_issues if i.severity == "warning")
    errors_count = sum(1 for i in all_issues if i.severity == "error")
    info_count = sum(1 for i in all_issues if i.severity == "info")

    from app.services.cecchino_data_lab.quality import compute_bet365_coverage

    coverage = compute_bet365_coverage(matches)

    importable = len(missing_required) == 0 and rows_importable > 0
    summary = {
        "importable": importable,
        "rows_total": len(matches),
        "rows_importable": rows_importable,
        "rows_skipped": rows_skipped,
        "warnings_count": warnings_count,
        "errors_count": errors_count,
        "info_count": info_count,
        "bet365_coverage": coverage,
    }

    return ParseResult(
        parser_version=PARSER_VERSION,
        file_sha256=sha,
        file_size_bytes=size,
        encoding=decoded.encoding,
        encoding_fallback=decoded.used_fallback,
        headers=headers,
        recognized_columns=recognized,
        missing_required_columns=missing_required,
        missing_optional_known=missing_optional,
        unexpected_columns=unexpected,
        rows_total=len(matches),
        preview_rows=preview_rows,
        matches=matches,
        issues=all_issues,
        rows_importable=rows_importable,
        rows_skipped=rows_skipped,
        warnings_count=warnings_count,
        errors_count=errors_count,
        info_count=info_count,
        bet365_coverage=coverage,
        summary=summary,
    )
