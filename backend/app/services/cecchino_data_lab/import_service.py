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
from app.services.cecchino_data_lab.constants import (
    IMPORT_CONFIRM_TOKEN,
    PARSER_VERSION,
    SOURCE_PROVIDER,
)
from app.services.cecchino_data_lab.csv_parser import (
    ParsedMatchRow,
    build_dataset_key,
    parse_football_data_csv,
    parse_season_years,
)
from app.services.cecchino_data_lab.quality import dataset_quality_from_matches


class CecchinoLabImportError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


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


def import_csv_bytes(
    db: Session,
    raw: bytes,
    *,
    competition_name: str,
    country: str,
    season_label: str,
    timezone_name: str = "Europe/Rome",
    division_code: str | None = None,
    source_filename: str = "upload.csv",
    confirm: str | None = None,
) -> dict[str, Any]:
    if confirm != IMPORT_CONFIRM_TOKEN:
        raise CecchinoLabImportError(
            "invalid_confirm_token",
            f"Conferma richiesta: inviáre confirm={IMPORT_CONFIRM_TOKEN}",
            status_code=400,
        )

    parsed = parse_football_data_csv(raw, timezone_name=timezone_name)

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

    if parsed.rows_importable == 0:
        raise CecchinoLabImportError(
            "no_importable_rows",
            "Nessuna riga importabile nel file.",
            status_code=400,
            details={"errors_count": parsed.errors_count},
        )

    now = datetime.now(timezone.utc)
    try:
        dataset = get_or_create_dataset(
            db,
            competition_name=competition_name.strip(),
            country=country.strip(),
            season_label=season_label.strip(),
            timezone_name=timezone_name,
            division_code=(division_code.strip() if division_code else None),
        )

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

        imported = 0
        row_issues_buffer: list[tuple[ParsedMatchRow | None, Any]] = []

        # File-level issues (no match)
        for issue in parsed.issues:
            if issue.source_row_number is None:
                row_issues_buffer.append((None, issue))

        match_orms: list[tuple[ParsedMatchRow, CecchinoLabMatch]] = []
        for m in parsed.matches:
            if not m.importable:
                for issue in m.issues:
                    row_issues_buffer.append((None, issue))
                continue
            orm = _match_to_orm(m, dataset_id=dataset.id, import_id=imp.id)
            db.add(orm)
            match_orms.append((m, orm))
            imported += 1

        db.flush()

        for m, orm in match_orms:
            for issue in m.issues:
                db.add(
                    CecchinoLabDataIssue(
                        import_id=imp.id,
                        match_id=orm.id,
                        source_row_number=issue.source_row_number,
                        severity=issue.severity,
                        issue_code=issue.issue_code,
                        field_name=issue.field_name,
                        raw_value=issue.raw_value,
                        message=issue.message,
                        details_json=issue.details,
                    )
                )

        for _m, issue in row_issues_buffer:
            db.add(
                CecchinoLabDataIssue(
                    import_id=imp.id,
                    match_id=None,
                    source_row_number=issue.source_row_number,
                    severity=issue.severity,
                    issue_code=issue.issue_code,
                    field_name=issue.field_name,
                    raw_value=issue.raw_value,
                    message=issue.message,
                    details_json=issue.details,
                )
            )

        # Refresh dataset aggregates
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
        errors = (
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

        dataset.matches_count = total
        dataset.status = DATASET_STATUS_ACTIVE if total > 0 else dataset.status
        dataset.data_quality_status = dataset_quality_from_matches(
            complete, partial, errors, total
        )
        meta = dict(dataset.metadata_json or {})
        meta["last_import_id"] = imp.id
        meta["last_import_at"] = now.isoformat()
        meta["bet365_coverage"] = parsed.bet365_coverage
        dataset.metadata_json = meta

        imp.rows_imported = imported
        imp.rows_skipped = parsed.rows_total - imported
        imp.status = IMPORT_STATUS_COMPLETED
        imp.completed_at = datetime.now(timezone.utc)

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
