"""Import reale CSV Cecchino Lab — transazionale."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.cecchino_lab_data_issue import CecchinoLabDataIssue
from app.models.cecchino_lab_dataset import (
    DATASET_STATUS_ACTIVE,
    CecchinoLabDataset,
)
from app.models.cecchino_lab_import import (
    IMPORT_STATUS_COMPLETED,
    IMPORT_STATUS_DUPLICATE,
    CecchinoLabImport,
)
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.errors import CecchinoLabImportError
from app.services.cecchino_data_lab.constants import (
    IMPORT_CONFIRM_TOKEN,
    PARSER_VERSION,
    SOURCE_PROVIDER,
)
from app.services.cecchino_data_lab.csv_parser import (
    ParsedIssue,
    ParsedMatchRow,
    ParseResult,
    build_dataset_key,
    parse_season_years,
)
from app.services.cecchino_data_lab.import_helpers import parse_with_catalog
from app.services.cecchino_data_lab.quality import dataset_quality_from_matches


def _match_to_orm(
    match: ParsedMatchRow,
    *,
    dataset_id: int,
    import_id: int,
) -> CecchinoLabMatch:
    return CecchinoLabMatch(
        dataset_id=dataset_id,
        import_id=import_id,
        source_row_number=match.source_row_number,
        division_code=match.division_code,
        match_date=match.match_date,
        match_time=match.match_time,
        kickoff_at=match.kickoff_at,
        home_team=match.home_team,
        away_team=match.away_team,
        referee=match.referee,
        ft_home_goals=match.ft_home_goals,
        ft_away_goals=match.ft_away_goals,
        ft_result=match.ft_result,
        ht_home_goals=match.ht_home_goals,
        ht_away_goals=match.ht_away_goals,
        ht_result=match.ht_result,
        home_shots=match.home_shots,
        away_shots=match.away_shots,
        home_shots_on_target=match.home_shots_on_target,
        away_shots_on_target=match.away_shots_on_target,
        home_fouls=match.home_fouls,
        away_fouls=match.away_fouls,
        home_corners=match.home_corners,
        away_corners=match.away_corners,
        home_yellow_cards=match.home_yellow_cards,
        away_yellow_cards=match.away_yellow_cards,
        home_red_cards=match.home_red_cards,
        away_red_cards=match.away_red_cards,
        bet365_home=match.bet365_home,
        bet365_draw=match.bet365_draw,
        bet365_away=match.bet365_away,
        bet365_over_25=match.bet365_over_25,
        bet365_under_25=match.bet365_under_25,
        asian_handicap_home_line=match.asian_handicap_home_line,
        bet365_ah_home=match.bet365_ah_home,
        bet365_ah_away=match.bet365_ah_away,
        bet365_closing_home=match.bet365_closing_home,
        bet365_closing_draw=match.bet365_closing_draw,
        bet365_closing_away=match.bet365_closing_away,
        bet365_closing_over_25=match.bet365_closing_over_25,
        bet365_closing_under_25=match.bet365_closing_under_25,
        asian_handicap_closing_home_line=match.asian_handicap_closing_home_line,
        bet365_closing_ah_home=match.bet365_closing_ah_home,
        bet365_closing_ah_away=match.bet365_closing_ah_away,
        result_ft_ready=match.result_ft_ready,
        result_ht_ready=match.result_ht_ready,
        statistics_ready=match.statistics_ready,
        bet365_1x2_pre_ready=match.bet365_1x2_pre_ready,
        bet365_1x2_closing_ready=match.bet365_1x2_closing_ready,
        bet365_ou25_pre_ready=match.bet365_ou25_pre_ready,
        bet365_ou25_closing_ready=match.bet365_ou25_closing_ready,
        row_quality_status=match.row_quality_status,
        raw_json=match.raw,
    )


def _issue_dedupe_key(issue: ParsedIssue) -> tuple[Any, ...]:
    return (
        issue.severity,
        issue.issue_code,
        issue.source_row_number,
        issue.field_name,
        issue.message,
    )


def persist_parsed_issues(
    db: Session,
    *,
    import_id: int,
    parsed: ParseResult,
    row_to_match_id: dict[int, int],
) -> None:
    """Persist every ParseResult issue once, linking match_id when possible."""
    seen: set[tuple[Any, ...]] = set()
    for issue in parsed.issues:
        key = _issue_dedupe_key(issue)
        if key in seen:
            continue
        seen.add(key)
        match_id = None
        if issue.source_row_number is not None:
            match_id = row_to_match_id.get(issue.source_row_number)
        db.add(
            CecchinoLabDataIssue(
                import_id=import_id,
                match_id=match_id,
                source_row_number=issue.source_row_number,
                severity=issue.severity,
                issue_code=issue.issue_code,
                field_name=issue.field_name,
                raw_value=issue.raw_value,
                message=issue.message,
                details_json=issue.details,
            )
        )


def refresh_dataset_aggregates(
    db: Session,
    dataset: CecchinoLabDataset,
    *,
    bet365_coverage: dict[str, Any] | None = None,
    last_import_id: int | None = None,
    last_import_at: str | None = None,
) -> None:
    complete = (
        db.query(CecchinoLabMatch)
        .filter(
            CecchinoLabMatch.dataset_id == dataset.id,
            CecchinoLabMatch.row_quality_status == "complete",
        )
        .count()
    )
    partial = (
        db.query(CecchinoLabMatch)
        .filter(
            CecchinoLabMatch.dataset_id == dataset.id,
            CecchinoLabMatch.row_quality_status == "partial",
        )
        .count()
    )
    row_errors = (
        db.query(CecchinoLabMatch)
        .filter(
            CecchinoLabMatch.dataset_id == dataset.id,
            CecchinoLabMatch.row_quality_status == "error",
        )
        .count()
    )
    total = (
        db.query(CecchinoLabMatch)
        .filter(CecchinoLabMatch.dataset_id == dataset.id)
        .count()
    )

    import_ids = [
        r[0]
        for r in db.query(CecchinoLabImport.id)
        .filter(CecchinoLabImport.dataset_id == dataset.id)
        .all()
    ]
    issue_errors = 0
    issue_warnings = 0
    if import_ids:
        issue_errors = (
            db.query(CecchinoLabDataIssue)
            .filter(
                CecchinoLabDataIssue.import_id.in_(import_ids),
                CecchinoLabDataIssue.severity == "error",
            )
            .count()
        )
        issue_warnings = (
            db.query(CecchinoLabDataIssue)
            .filter(
                CecchinoLabDataIssue.import_id.in_(import_ids),
                CecchinoLabDataIssue.severity == "warning",
            )
            .count()
        )

    dataset.matches_count = total
    dataset.status = DATASET_STATUS_ACTIVE if total > 0 else dataset.status
    dataset.data_quality_status = dataset_quality_from_matches(
        complete,
        partial,
        row_errors,
        total,
        issue_errors=issue_errors,
        issue_warnings=issue_warnings,
    )
    meta = dict(dataset.metadata_json or {})
    if last_import_id is not None:
        meta["last_import_id"] = last_import_id
    if last_import_at is not None:
        meta["last_import_at"] = last_import_at
    if bet365_coverage is not None:
        meta["bet365_coverage"] = bet365_coverage
    dataset.metadata_json = meta


def get_or_create_dataset(
    db: Session,
    *,
    competition_name: str,
    country: str,
    season_label: str,
    timezone_name: str,
    division_code: str | None,
) -> CecchinoLabDataset:
    existing = (
        db.query(CecchinoLabDataset)
        .filter(
            CecchinoLabDataset.competition_name == competition_name,
            CecchinoLabDataset.country == country,
            CecchinoLabDataset.season_label == season_label,
            CecchinoLabDataset.source_provider == SOURCE_PROVIDER,
        )
        .one_or_none()
    )
    if existing:
        if division_code and not existing.division_code:
            existing.division_code = division_code
        return existing

    start_year, end_year = parse_season_years(season_label)
    ds = CecchinoLabDataset(
        dataset_key=build_dataset_key(competition_name, country, season_label),
        competition_name=competition_name,
        country=country,
        division_code=division_code,
        season_label=season_label,
        start_year=start_year,
        end_year=end_year,
        timezone=timezone_name,
        source_provider=SOURCE_PROVIDER,
        status=DATASET_STATUS_ACTIVE,
        matches_count=0,
        data_quality_status="unknown",
        metadata_json={},
    )
    db.add(ds)
    db.flush()
    return ds


def write_import_rows(
    db: Session,
    *,
    dataset: CecchinoLabDataset,
    parsed: ParseResult,
    source_filename: str,
) -> tuple[CecchinoLabImport, int]:
    """Create import + matches + issues for an existing dataset (no commit)."""
    now = datetime.now(timezone.utc)
    imp = CecchinoLabImport(
        dataset_id=dataset.id,
        source_filename=source_filename,
        file_sha256=parsed.file_sha256,
        file_size_bytes=parsed.file_size_bytes,
        parser_version=PARSER_VERSION,
        status="pending",
        rows_total=parsed.rows_total,
        rows_imported=0,
        rows_skipped=parsed.rows_skipped,
        warnings_count=parsed.warnings_count,
        errors_count=parsed.errors_count,
        columns_json={
            "headers": parsed.headers,
            "recognized": parsed.recognized_columns,
            "unexpected": parsed.unexpected_columns,
        },
        summary_json=parsed.summary,
        started_at=now,
    )
    db.add(imp)
    db.flush()

    match_orms: list[tuple[ParsedMatchRow, CecchinoLabMatch]] = []
    imported = 0
    for m in parsed.matches:
        if not m.importable:
            continue
        orm = _match_to_orm(m, dataset_id=dataset.id, import_id=imp.id)
        db.add(orm)
        match_orms.append((m, orm))
        imported += 1

    db.flush()

    row_to_match_id = {m.source_row_number: orm.id for m, orm in match_orms}
    persist_parsed_issues(
        db,
        import_id=imp.id,
        parsed=parsed,
        row_to_match_id=row_to_match_id,
    )

    imp.rows_imported = imported
    imp.rows_skipped = parsed.rows_total - imported
    imp.status = IMPORT_STATUS_COMPLETED
    imp.completed_at = datetime.now(timezone.utc)

    refresh_dataset_aggregates(
        db,
        dataset,
        bet365_coverage=parsed.bet365_coverage,
        last_import_id=imp.id,
        last_import_at=now.isoformat(),
    )
    return imp, imported


def import_csv_bytes(
    db: Session,
    raw: bytes,
    *,
    competition_key: str,
    season_label: str,
    source_filename: str = "upload.csv",
    confirm: str | None = None,
) -> dict[str, Any]:
    if confirm != IMPORT_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "invalid_confirm_token",
            f"Conferma richiesta: inviare confirm={IMPORT_CONFIRM_TOKEN}",
            status_code=400,
        )

    entry, parsed = parse_with_catalog(
        raw,
        competition_key=competition_key,
        season_label=season_label,
    )
    competition_name = entry.display_name
    country = entry.country
    timezone_name = entry.timezone
    division_code = entry.division_code

    existing_import = (
        db.query(CecchinoLabImport)
        .filter(
            CecchinoLabImport.file_sha256 == parsed.file_sha256,
            CecchinoLabImport.parser_version == PARSER_VERSION,
        )
        .one_or_none()
    )
    if existing_import is not None:
        raise CecchinoLabImportError(
            "duplicate_file",
            "Questo file è già stato importato (stesso SHA-256 e parser).",
            status_code=409,
            details={
                "import_id": existing_import.id,
                "dataset_id": existing_import.dataset_id,
                "status": IMPORT_STATUS_DUPLICATE,
                "file_sha256": parsed.file_sha256,
            },
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
            f"La colonna Div del CSV non coincide con {division_code} ({competition_name}).",
            status_code=400,
            details={
                "expected": division_code,
                "competition_key": competition_key,
                "errors_count": parsed.errors_count,
            },
        )

    if parsed.rows_importable == 0:
        raise CecchinoLabImportError(
            "no_importable_rows",
            "Nessuna riga importabile nel file.",
            status_code=400,
            details={"errors_count": parsed.errors_count},
        )

    try:
        dataset = get_or_create_dataset(
            db,
            competition_name=competition_name.strip(),
            country=country.strip(),
            season_label=season_label.strip(),
            timezone_name=timezone_name,
            division_code=(division_code.strip() if division_code else None),
        )

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
            "status": "completed",
            "import_id": imp.id,
            "dataset_id": dataset.id,
            "dataset_key": dataset.dataset_key,
            "rows_total": parsed.rows_total,
            "rows_imported": imported,
            "rows_skipped": parsed.rows_total - imported,
            "warnings_count": parsed.warnings_count,
            "errors_count": parsed.errors_count,
            "info_count": parsed.info_count,
            "bet365_coverage": parsed.bet365_coverage,
            "file_sha256": parsed.file_sha256,
            "parser_version": PARSER_VERSION,
        }
    except CecchinoLabImportError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
