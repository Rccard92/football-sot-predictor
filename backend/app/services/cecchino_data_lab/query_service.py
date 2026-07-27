"""Query read-only Cecchino Lab (overview, datasets, matches, issues)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.cecchino_lab_data_issue import CecchinoLabDataIssue
from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_import import CecchinoLabImport
from app.models.cecchino_lab_match import CecchinoLabMatch


def _dec(v: Decimal | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _dataset_dict(ds: CecchinoLabDataset, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = ds.metadata_json or {}
    coverage = meta.get("bet365_coverage") or {}
    out = {
        "id": ds.id,
        "dataset_key": ds.dataset_key,
        "competition_name": ds.competition_name,
        "country": ds.country,
        "division_code": ds.division_code,
        "season_label": ds.season_label,
        "start_year": ds.start_year,
        "end_year": ds.end_year,
        "timezone": ds.timezone,
        "source_provider": ds.source_provider,
        "status": ds.status,
        "matches_count": ds.matches_count,
        "data_quality_status": ds.data_quality_status,
        "bet365_1x2_coverage_pct": coverage.get("1x2_pre_pct"),
        "bet365_ou25_coverage_pct": coverage.get("ou25_pre_pct"),
        "last_import_id": meta.get("last_import_id"),
        "last_import_at": meta.get("last_import_at"),
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
    }
    if extra:
        out.update(extra)
    return out


def _match_summary(m: CecchinoLabMatch, ds: CecchinoLabDataset | None = None) -> dict[str, Any]:
    return {
        "id": m.id,
        "dataset_id": m.dataset_id,
        "import_id": m.import_id,
        "match_date": m.match_date.isoformat() if m.match_date else None,
        "match_time": m.match_time.isoformat() if m.match_time else None,
        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "ft_home_goals": m.ft_home_goals,
        "ft_away_goals": m.ft_away_goals,
        "ft_result": m.ft_result,
        "ht_home_goals": m.ht_home_goals,
        "ht_away_goals": m.ht_away_goals,
        "ht_result": m.ht_result,
        "bet365_home": _dec(m.bet365_home),
        "bet365_draw": _dec(m.bet365_draw),
        "bet365_away": _dec(m.bet365_away),
        "bet365_over_25": _dec(m.bet365_over_25),
        "bet365_under_25": _dec(m.bet365_under_25),
        "row_quality_status": m.row_quality_status,
        "result_ft_ready": m.result_ft_ready,
        "statistics_ready": m.statistics_ready,
        "bet365_1x2_pre_ready": m.bet365_1x2_pre_ready,
        "bet365_ou25_pre_ready": m.bet365_ou25_pre_ready,
        "competition_name": ds.competition_name if ds else None,
        "season_label": ds.season_label if ds else None,
        "country": ds.country if ds else None,
    }


def _match_detail(m: CecchinoLabMatch, ds: CecchinoLabDataset | None, issues: list[dict]) -> dict[str, Any]:
    base = _match_summary(m, ds)
    base.update(
        {
            "division_code": m.division_code,
            "referee": m.referee,
            "home_shots": m.home_shots,
            "away_shots": m.away_shots,
            "home_shots_on_target": m.home_shots_on_target,
            "away_shots_on_target": m.away_shots_on_target,
            "home_fouls": m.home_fouls,
            "away_fouls": m.away_fouls,
            "home_corners": m.home_corners,
            "away_corners": m.away_corners,
            "home_yellow_cards": m.home_yellow_cards,
            "away_yellow_cards": m.away_yellow_cards,
            "home_red_cards": m.home_red_cards,
            "away_red_cards": m.away_red_cards,
            "bet365_closing_home": _dec(m.bet365_closing_home),
            "bet365_closing_draw": _dec(m.bet365_closing_draw),
            "bet365_closing_away": _dec(m.bet365_closing_away),
            "bet365_closing_over_25": _dec(m.bet365_closing_over_25),
            "bet365_closing_under_25": _dec(m.bet365_closing_under_25),
            "asian_handicap_home_line": _dec(m.asian_handicap_home_line),
            "bet365_ah_home": _dec(m.bet365_ah_home),
            "bet365_ah_away": _dec(m.bet365_ah_away),
            "asian_handicap_closing_home_line": _dec(m.asian_handicap_closing_home_line),
            "bet365_closing_ah_home": _dec(m.bet365_closing_ah_home),
            "bet365_closing_ah_away": _dec(m.bet365_closing_ah_away),
            "result_ht_ready": m.result_ht_ready,
            "bet365_1x2_closing_ready": m.bet365_1x2_closing_ready,
            "bet365_ou25_closing_ready": m.bet365_ou25_closing_ready,
            "odds_movement": {
                "home": {
                    "pre": _dec(m.bet365_home),
                    "closing": _dec(m.bet365_closing_home),
                },
                "draw": {
                    "pre": _dec(m.bet365_draw),
                    "closing": _dec(m.bet365_closing_draw),
                },
                "away": {
                    "pre": _dec(m.bet365_away),
                    "closing": _dec(m.bet365_closing_away),
                },
                "over_25": {
                    "pre": _dec(m.bet365_over_25),
                    "closing": _dec(m.bet365_closing_over_25),
                },
                "under_25": {
                    "pre": _dec(m.bet365_under_25),
                    "closing": _dec(m.bet365_closing_under_25),
                },
            },
            "raw_json": m.raw_json,
            "issues": issues,
        }
    )
    return base


def get_overview(db: Session) -> dict[str, Any]:
    datasets = db.query(CecchinoLabDataset).all()
    total_matches = db.query(func.count(CecchinoLabMatch.id)).scalar() or 0
    complete = (
        db.query(func.count(CecchinoLabMatch.id))
        .filter(CecchinoLabMatch.row_quality_status == "complete")
        .scalar()
        or 0
    )
    incomplete = total_matches - complete
    errors = (
        db.query(func.count(CecchinoLabDataIssue.id))
        .filter(CecchinoLabDataIssue.severity == "error")
        .scalar()
        or 0
    )
    warnings = (
        db.query(func.count(CecchinoLabDataIssue.id))
        .filter(CecchinoLabDataIssue.severity == "warning")
        .scalar()
        or 0
    )
    # Solo errori + warning; le info restano in Qualità dati ma non contano come anomalie
    anomalies = errors + warnings

    with_1x2 = (
        db.query(func.count(CecchinoLabMatch.id))
        .filter(CecchinoLabMatch.bet365_1x2_pre_ready.is_(True))
        .scalar()
        or 0
    )
    with_ou = (
        db.query(func.count(CecchinoLabMatch.id))
        .filter(CecchinoLabMatch.bet365_ou25_pre_ready.is_(True))
        .scalar()
        or 0
    )

    competitions = sorted({d.competition_name for d in datasets})
    seasons = sorted({d.season_label for d in datasets}, reverse=True)
    countries = sorted({d.country for d in datasets})

    recent_imports = (
        db.query(CecchinoLabImport)
        .order_by(CecchinoLabImport.created_at.desc())
        .limit(8)
        .all()
    )
    ds_by_id = {d.id: d for d in datasets}
    recent = []
    for imp in recent_imports:
        ds = ds_by_id.get(imp.dataset_id)
        recent.append(
            {
                "id": imp.id,
                "dataset_id": imp.dataset_id,
                "source_filename": imp.source_filename,
                "status": imp.status,
                "rows_imported": imp.rows_imported,
                "rows_skipped": imp.rows_skipped,
                "warnings_count": imp.warnings_count,
                "errors_count": imp.errors_count,
                "competition_name": ds.competition_name if ds else None,
                "season_label": ds.season_label if ds else None,
                "created_at": imp.created_at.isoformat() if imp.created_at else None,
            }
        )

    best = [_dataset_dict(d) for d in sorted(datasets, key=lambda d: d.matches_count, reverse=True)[:3]]
    worst = [
        _dataset_dict(d)
        for d in sorted(
            datasets,
            key=lambda d: (
                0 if d.data_quality_status in ("error", "poor") else 1 if d.data_quality_status == "partial" else 2,
                -d.matches_count,
            ),
        )[:3]
    ]

    # Per-dataset issue counts (via imports of that dataset)
    def _season_sort_key(label: str) -> tuple[int, str]:
        try:
            start = int(str(label).split("/")[0].split("-")[0])
            return (-start, label)
        except (ValueError, IndexError):
            return (0, label)

    sorted_datasets = sorted(
        datasets,
        key=lambda d: (_season_sort_key(d.season_label or ""), (d.competition_name or "").lower()),
    )

    datasets_status: list[dict[str, Any]] = []
    for ds in sorted_datasets:
        meta = ds.metadata_json or {}
        coverage = meta.get("bet365_coverage") or {}
        import_ids = [
            r[0]
            for r in db.query(CecchinoLabImport.id)
            .filter(CecchinoLabImport.dataset_id == ds.id)
            .all()
        ]
        err_c = warn_c = info_c = 0
        if import_ids:
            err_c = (
                db.query(func.count(CecchinoLabDataIssue.id))
                .filter(
                    CecchinoLabDataIssue.import_id.in_(import_ids),
                    CecchinoLabDataIssue.severity == "error",
                )
                .scalar()
                or 0
            )
            warn_c = (
                db.query(func.count(CecchinoLabDataIssue.id))
                .filter(
                    CecchinoLabDataIssue.import_id.in_(import_ids),
                    CecchinoLabDataIssue.severity == "warning",
                )
                .scalar()
                or 0
            )
            info_c = (
                db.query(func.count(CecchinoLabDataIssue.id))
                .filter(
                    CecchinoLabDataIssue.import_id.in_(import_ids),
                    CecchinoLabDataIssue.severity == "info",
                )
                .scalar()
                or 0
            )
        datasets_status.append(
            {
                "id": ds.id,
                "competition_name": ds.competition_name,
                "season_label": ds.season_label,
                "matches_count": ds.matches_count,
                "bet365_1x2_coverage_pct": coverage.get("1x2_pre_pct"),
                "bet365_ou25_coverage_pct": coverage.get("ou25_pre_pct"),
                "errors_count": err_c,
                "warnings_count": warn_c,
                "info_count": info_c,
                "data_quality_status": ds.data_quality_status,
            }
        )

    return {
        "competitions_count": len(competitions),
        "seasons_count": len(seasons),
        "datasets_count": len(datasets),
        "matches_total": total_matches,
        "matches_complete": complete,
        "matches_incomplete": incomplete,
        "anomalies_total": anomalies,
        "anomalies_errors": errors,
        "anomalies_warnings": warnings,
        "bet365_1x2_coverage_pct": round(100.0 * with_1x2 / total_matches, 1) if total_matches else 0.0,
        "bet365_ou25_coverage_pct": round(100.0 * with_ou / total_matches, 1) if total_matches else 0.0,
        "competitions": competitions,
        "seasons": seasons,
        "countries": countries,
        "recent_imports": recent,
        "best_quality_datasets": best,
        "worst_quality_datasets": worst,
        "datasets_status": datasets_status,
        "completeness": {
            "complete": complete,
            "incomplete": incomplete,
            "complete_pct": round(100.0 * complete / total_matches, 1) if total_matches else 0.0,
        },
        "is_empty": total_matches == 0 and len(datasets) == 0,
    }


def list_datasets(
    db: Session,
    *,
    country: str | None = None,
    competition: str | None = None,
    season: str | None = None,
    quality_status: str | None = None,
) -> dict[str, Any]:
    q = db.query(CecchinoLabDataset)
    if country:
        q = q.filter(CecchinoLabDataset.country.ilike(f"%{country}%"))
    if competition:
        q = q.filter(CecchinoLabDataset.competition_name.ilike(f"%{competition}%"))
    if season:
        q = q.filter(CecchinoLabDataset.season_label == season)
    if quality_status:
        q = q.filter(CecchinoLabDataset.data_quality_status == quality_status)

    rows = q.order_by(CecchinoLabDataset.country, CecchinoLabDataset.competition_name, CecchinoLabDataset.season_label).all()

    items = []
    for ds in rows:
        anomaly_count = (
            db.query(func.count(CecchinoLabDataIssue.id))
            .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
            .filter(CecchinoLabImport.dataset_id == ds.id)
            .scalar()
            or 0
        )
        items.append(_dataset_dict(ds, extra={"anomalies_count": anomaly_count}))

    return {"items": items, "total": len(items)}


def get_dataset(db: Session, dataset_id: int) -> dict[str, Any] | None:
    ds = db.query(CecchinoLabDataset).filter(CecchinoLabDataset.id == dataset_id).one_or_none()
    if not ds:
        return None
    imports = (
        db.query(CecchinoLabImport)
        .filter(CecchinoLabImport.dataset_id == dataset_id)
        .order_by(CecchinoLabImport.created_at.desc())
        .all()
    )
    anomaly_count = (
        db.query(func.count(CecchinoLabDataIssue.id))
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .filter(CecchinoLabImport.dataset_id == dataset_id)
        .scalar()
        or 0
    )
    out = _dataset_dict(ds, extra={"anomalies_count": anomaly_count})
    out["imports"] = [
        {
            "id": i.id,
            "source_filename": i.source_filename,
            "status": i.status,
            "rows_imported": i.rows_imported,
            "rows_skipped": i.rows_skipped,
            "warnings_count": i.warnings_count,
            "errors_count": i.errors_count,
            "file_sha256": i.file_sha256,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in imports
    ]
    return out


_SORTABLE = {
    "match_date": CecchinoLabMatch.match_date,
    "home_team": CecchinoLabMatch.home_team,
    "away_team": CecchinoLabMatch.away_team,
    "ft_result": CecchinoLabMatch.ft_result,
    "row_quality_status": CecchinoLabMatch.row_quality_status,
    "bet365_home": CecchinoLabMatch.bet365_home,
    "id": CecchinoLabMatch.id,
}


def list_matches(
    db: Session,
    *,
    dataset_id: int | None = None,
    competition: str | None = None,
    season: str | None = None,
    team: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    result: str | None = None,
    quality_status: str | None = None,
    has_bet365_1x2: bool | None = None,
    has_bet365_ou25: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "match_date",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    q = db.query(CecchinoLabMatch, CecchinoLabDataset).join(
        CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabMatch.dataset_id
    )
    if dataset_id is not None:
        q = q.filter(CecchinoLabMatch.dataset_id == dataset_id)
    if competition:
        q = q.filter(CecchinoLabDataset.competition_name.ilike(f"%{competition}%"))
    if season:
        q = q.filter(CecchinoLabDataset.season_label == season)
    if team:
        like = f"%{team}%"
        q = q.filter(or_(CecchinoLabMatch.home_team.ilike(like), CecchinoLabMatch.away_team.ilike(like)))
    if date_from:
        q = q.filter(CecchinoLabMatch.match_date >= date_from)
    if date_to:
        q = q.filter(CecchinoLabMatch.match_date <= date_to)
    if result:
        q = q.filter(CecchinoLabMatch.ft_result == result.upper())
    if quality_status:
        q = q.filter(CecchinoLabMatch.row_quality_status == quality_status)
    if has_bet365_1x2 is True:
        q = q.filter(CecchinoLabMatch.bet365_1x2_pre_ready.is_(True))
    elif has_bet365_1x2 is False:
        q = q.filter(CecchinoLabMatch.bet365_1x2_pre_ready.is_(False))
    if has_bet365_ou25 is True:
        q = q.filter(CecchinoLabMatch.bet365_ou25_pre_ready.is_(True))
    elif has_bet365_ou25 is False:
        q = q.filter(CecchinoLabMatch.bet365_ou25_pre_ready.is_(False))
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                CecchinoLabMatch.home_team.ilike(like),
                CecchinoLabMatch.away_team.ilike(like),
                CecchinoLabMatch.referee.ilike(like),
                CecchinoLabDataset.competition_name.ilike(like),
            )
        )

    total = q.count()
    col = _SORTABLE.get(sort_by, CecchinoLabMatch.match_date)
    order = col.asc() if sort_dir.lower() == "asc" else col.desc()
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    rows = q.order_by(order, CecchinoLabMatch.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_match_summary(m, ds) for m, ds in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


def get_match(db: Session, match_id: int) -> dict[str, Any] | None:
    row = (
        db.query(CecchinoLabMatch, CecchinoLabDataset)
        .join(CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabMatch.dataset_id)
        .filter(CecchinoLabMatch.id == match_id)
        .one_or_none()
    )
    if not row:
        return None
    m, ds = row
    issues_orm = (
        db.query(CecchinoLabDataIssue)
        .filter(CecchinoLabDataIssue.match_id == match_id)
        .order_by(CecchinoLabDataIssue.id)
        .all()
    )
    issues = [
        {
            "id": i.id,
            "severity": i.severity,
            "issue_code": i.issue_code,
            "field_name": i.field_name,
            "message": i.message,
            "raw_value": i.raw_value,
        }
        for i in issues_orm
    ]
    return _match_detail(m, ds, issues)


def _issues_base_query(
    db: Session,
    *,
    dataset_id: int | None = None,
    import_id: int | None = None,
    severity: str | None = None,
    issue_code: str | None = None,
    match_id: int | None = None,
    competition: str | None = None,
    season_label: str | None = None,
):
    """Query issues con join import + dataset (per filtri campionato/stagione)."""
    q = (
        db.query(CecchinoLabDataIssue, CecchinoLabImport, CecchinoLabDataset)
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .join(CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabImport.dataset_id)
    )
    if dataset_id is not None:
        q = q.filter(CecchinoLabImport.dataset_id == dataset_id)
    if import_id is not None:
        q = q.filter(CecchinoLabDataIssue.import_id == import_id)
    if severity:
        q = q.filter(CecchinoLabDataIssue.severity == severity)
    if issue_code:
        q = q.filter(CecchinoLabDataIssue.issue_code == issue_code)
    if match_id is not None:
        q = q.filter(CecchinoLabDataIssue.match_id == match_id)
    if competition:
        q = q.filter(CecchinoLabDataset.competition_name == competition)
    if season_label:
        q = q.filter(CecchinoLabDataset.season_label == season_label)
    return q


def list_data_quality_issues(
    db: Session,
    *,
    dataset_id: int | None = None,
    import_id: int | None = None,
    severity: str | None = None,
    issue_code: str | None = None,
    match_id: int | None = None,
    competition: str | None = None,
    season_label: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    q = _issues_base_query(
        db,
        dataset_id=dataset_id,
        import_id=import_id,
        severity=severity,
        issue_code=issue_code,
        match_id=match_id,
        competition=competition,
        season_label=season_label,
    )

    total = q.count()
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    rows = q.order_by(CecchinoLabDataIssue.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    code_q = (
        db.query(CecchinoLabDataIssue.issue_code, func.count(CecchinoLabDataIssue.id))
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .join(CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabImport.dataset_id)
    )
    if dataset_id is not None:
        code_q = code_q.filter(CecchinoLabImport.dataset_id == dataset_id)
    if severity:
        code_q = code_q.filter(CecchinoLabDataIssue.severity == severity)
    if issue_code:
        code_q = code_q.filter(CecchinoLabDataIssue.issue_code == issue_code)
    if competition:
        code_q = code_q.filter(CecchinoLabDataset.competition_name == competition)
    if season_label:
        code_q = code_q.filter(CecchinoLabDataset.season_label == season_label)
    code_counts = (
        code_q.group_by(CecchinoLabDataIssue.issue_code)
        .order_by(func.count(CecchinoLabDataIssue.id).desc())
        .limit(15)
        .all()
    )

    items = []
    for issue, imp, ds in rows:
        items.append(
            {
                "id": issue.id,
                "import_id": issue.import_id,
                "dataset_id": imp.dataset_id,
                "match_id": issue.match_id,
                "source_row_number": issue.source_row_number,
                "severity": issue.severity,
                "issue_code": issue.issue_code,
                "field_name": issue.field_name,
                "raw_value": issue.raw_value,
                "message": issue.message,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "competition_name": ds.competition_name,
                "season_label": ds.season_label,
                "country": ds.country,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "top_issue_codes": [{"issue_code": c, "count": n} for c, n in code_counts],
        "severity_counts": {
            "error": db.query(func.count(CecchinoLabDataIssue.id))
            .filter(CecchinoLabDataIssue.severity == "error")
            .scalar()
            or 0,
            "warning": db.query(func.count(CecchinoLabDataIssue.id))
            .filter(CecchinoLabDataIssue.severity == "warning")
            .scalar()
            or 0,
            "info": db.query(func.count(CecchinoLabDataIssue.id))
            .filter(CecchinoLabDataIssue.severity == "info")
            .scalar()
            or 0,
        },
    }


EXPORT_ISSUE_COLUMNS = [
    "issue_id",
    "severity",
    "issue_code",
    "message",
    "field_name",
    "raw_value",
    "source_row_number",
    "match_id",
    "match_date",
    "home_team",
    "away_team",
    "dataset_id",
    "competition_name",
    "country",
    "season_label",
    "division_code",
    "import_id",
    "source_filename",
    "details_json",
    "created_at",
]


def _issue_export_row(
    issue: CecchinoLabDataIssue,
    imp: CecchinoLabImport,
    ds: CecchinoLabDataset,
    match: CecchinoLabMatch | None,
) -> dict[str, Any]:
    import json

    details = issue.details_json
    details_str = json.dumps(details, ensure_ascii=False) if details is not None else None
    return {
        "issue_id": issue.id,
        "severity": issue.severity,
        "issue_code": issue.issue_code,
        "message": issue.message,
        "field_name": issue.field_name,
        "raw_value": issue.raw_value,
        "source_row_number": issue.source_row_number,
        "match_id": issue.match_id,
        "match_date": match.match_date.isoformat() if match and match.match_date else None,
        "home_team": match.home_team if match else None,
        "away_team": match.away_team if match else None,
        "dataset_id": imp.dataset_id,
        "competition_name": ds.competition_name,
        "country": ds.country,
        "season_label": ds.season_label,
        "division_code": ds.division_code,
        "import_id": issue.import_id,
        "source_filename": imp.source_filename,
        "details_json": details_str,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
    }


def export_data_quality_issues(
    db: Session,
    *,
    format: str = "json",
    scope: str = "filtered",
    severity: str | None = None,
    issue_code: str | None = None,
    dataset_id: int | None = None,
    competition: str | None = None,
    season_label: str | None = None,
) -> tuple[str, str, str]:
    """Esporta tutte le segnalazioni (senza paginazione).

    Restituisce (content, media_type, filename).
    Non include raw_json delle partite.
    """
    import csv
    import io
    import json
    from datetime import datetime, timezone

    fmt = (format or "json").lower().strip()
    if fmt not in ("csv", "json"):
        fmt = "json"
    use_filters = (scope or "filtered").lower().strip() != "all"

    filt_severity = severity if use_filters else None
    filt_code = issue_code if use_filters else None
    filt_dataset = dataset_id if use_filters else None
    filt_comp = competition if use_filters else None
    filt_season = season_label if use_filters else None

    q = (
        db.query(CecchinoLabDataIssue, CecchinoLabImport, CecchinoLabDataset, CecchinoLabMatch)
        .join(CecchinoLabImport, CecchinoLabImport.id == CecchinoLabDataIssue.import_id)
        .join(CecchinoLabDataset, CecchinoLabDataset.id == CecchinoLabImport.dataset_id)
        .outerjoin(CecchinoLabMatch, CecchinoLabMatch.id == CecchinoLabDataIssue.match_id)
    )
    if filt_dataset is not None:
        q = q.filter(CecchinoLabImport.dataset_id == filt_dataset)
    if filt_severity:
        q = q.filter(CecchinoLabDataIssue.severity == filt_severity)
    if filt_code:
        q = q.filter(CecchinoLabDataIssue.issue_code == filt_code)
    if filt_comp:
        q = q.filter(CecchinoLabDataset.competition_name == filt_comp)
    if filt_season:
        q = q.filter(CecchinoLabDataset.season_label == filt_season)

    rows = q.order_by(CecchinoLabDataIssue.id.asc()).all()
    items = [_issue_export_row(issue, imp, ds, match) for issue, imp, ds, match in rows]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filters_meta = {
        "scope": "filtered" if use_filters else "all",
        "severity": filt_severity,
        "issue_code": filt_code,
        "dataset_id": filt_dataset,
        "competition": filt_comp,
        "season_label": filt_season,
    }

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=EXPORT_ISSUE_COLUMNS,
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        for item in items:
            writer.writerow(item)
        # UTF-8 con BOM
        content = "\ufeff" + buf.getvalue()
        filename = f"cecchino_lab_quality_{stamp}.csv"
        return content, "text/csv; charset=utf-8", filename

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters_meta,
        "count": len(items),
        "items": items,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"cecchino_lab_quality_{stamp}.json"
    return content, "application/json; charset=utf-8", filename
