"""Dry-run riconciliazione stats: SELECT + report, zero scritture DB."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.cecchino_lab_dataset import CecchinoLabDataset
from app.models.cecchino_lab_import import CecchinoLabImport
from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.stats_raw_reconciliation.classify import (
    classify_cell,
    db_value_for_audit,
    parse_source_for_field,
    source_value_for_audit,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.constants import (
    CELL_ACTION_NO_SOURCE_VALUE,
    MATCH_STATUS_HAS_RAW,
    MATCH_STATUS_NO_RAW,
    STATS_MODEL_FIELDS,
)
from app.services.cecchino_data_lab.stats_raw_reconciliation.report import (
    BucketAccumulator,
    write_reports,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchScanRow:
    lab_match_id: int
    source_file: str
    source_row: int
    competition: str
    season: str
    kickoff: datetime | None
    home_team: str | None
    away_team: str | None
    raw_json: dict[str, Any] | None
    db_values: dict[str, Any]


def enable_read_only_transaction(session: Session) -> bool:
    """Attiva SET TRANSACTION READ ONLY su PostgreSQL."""
    bind = session.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "") or ""
    if dialect_name != "postgresql":
        logger.info(
            "dry-run: dialetto %s — SKIP SET TRANSACTION READ ONLY",
            dialect_name or "unknown",
        )
        return False
    session.execute(text("SET TRANSACTION READ ONLY"))
    logger.info("dry-run: SET TRANSACTION READ ONLY attivo")
    return True


def load_match_scan_rows(session: Session) -> list[MatchScanRow]:
    """SELECT read-only: match JOIN dataset JOIN import, dedupe su lab_match_id."""
    stmt = (
        select(
            CecchinoLabMatch.id,
            CecchinoLabMatch.source_row_number,
            CecchinoLabMatch.kickoff_at,
            CecchinoLabMatch.home_team,
            CecchinoLabMatch.away_team,
            CecchinoLabMatch.raw_json,
            CecchinoLabMatch.referee,
            CecchinoLabMatch.home_shots,
            CecchinoLabMatch.away_shots,
            CecchinoLabMatch.home_shots_on_target,
            CecchinoLabMatch.away_shots_on_target,
            CecchinoLabMatch.home_fouls,
            CecchinoLabMatch.away_fouls,
            CecchinoLabMatch.home_corners,
            CecchinoLabMatch.away_corners,
            CecchinoLabMatch.home_yellow_cards,
            CecchinoLabMatch.away_yellow_cards,
            CecchinoLabMatch.home_red_cards,
            CecchinoLabMatch.away_red_cards,
            CecchinoLabMatch.ht_home_goals,
            CecchinoLabMatch.ht_away_goals,
            CecchinoLabMatch.ht_result,
            CecchinoLabMatch.ft_home_goals,
            CecchinoLabMatch.ft_away_goals,
            CecchinoLabMatch.ft_result,
            CecchinoLabDataset.competition_name,
            CecchinoLabDataset.season_label,
            CecchinoLabImport.source_filename,
        )
        .join(
            CecchinoLabDataset,
            CecchinoLabMatch.dataset_id == CecchinoLabDataset.id,
        )
        .join(
            CecchinoLabImport,
            CecchinoLabMatch.import_id == CecchinoLabImport.id,
        )
        .order_by(CecchinoLabMatch.id)
    )
    rows = session.execute(stmt).all()

    by_id: dict[int, MatchScanRow] = {}
    for r in rows:
        mid = int(r.id)
        if mid in by_id:
            # Anti fan-out: conserva la prima riga, ignora duplicati join
            continue
        raw = r.raw_json if isinstance(r.raw_json, dict) else None
        db_values = {f: getattr(r, f) for f in STATS_MODEL_FIELDS}
        by_id[mid] = MatchScanRow(
            lab_match_id=mid,
            source_file=str(r.source_filename or ""),
            source_row=int(r.source_row_number),
            competition=str(r.competition_name or ""),
            season=str(r.season_label or ""),
            kickoff=r.kickoff_at,
            home_team=r.home_team,
            away_team=r.away_team,
            raw_json=raw,
            db_values=db_values,
        )
    return list(by_id.values())


def classify_match(
    row: MatchScanRow,
) -> tuple[str, list[dict[str, Any]]]:
    """Classifica tutti i campi di un match. Ritorna (match_status, audit_rows)."""
    has_raw = isinstance(row.raw_json, dict)
    match_status = MATCH_STATUS_HAS_RAW if has_raw else MATCH_STATUS_NO_RAW
    audit: list[dict[str, Any]] = []

    kickoff_str = ""
    if row.kickoff is not None:
        kickoff_str = row.kickoff.isoformat()

    for field_name in STATS_MODEL_FIELDS:
        db_val = row.db_values.get(field_name)
        if has_raw:
            source_val, invalid = parse_source_for_field(field_name, row.raw_json)
            action = classify_cell(
                field=field_name,
                db_value=db_val,
                source_value=source_val,
                source_invalid=invalid,
            )
            src_audit = source_value_for_audit(
                source_val, invalid, row.raw_json, field_name
            )
        else:
            action = CELL_ACTION_NO_SOURCE_VALUE
            src_audit = ""

        audit.append(
            {
                "source_file": row.source_file,
                "source_row": row.source_row,
                "lab_match_id": row.lab_match_id,
                "competition": row.competition,
                "season": row.season,
                "kickoff": kickoff_str,
                "home_team": row.home_team or "",
                "away_team": row.away_team or "",
                "match_status": match_status,
                "field": field_name,
                "source_value": src_audit,
                "db_value": db_value_for_audit(db_val),
                "action": action,
            }
        )
    return match_status, audit


def build_summary_from_rows(
    rows: list[MatchScanRow],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Classifica e aggrega: GLOBAL / COMPETITION / COMPETITION+SEASON."""
    global_acc = BucketAccumulator()
    by_competition: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_comp_season: dict[tuple[str, str], BucketAccumulator] = defaultdict(
        BucketAccumulator
    )

    all_audit: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, str]] = set()
    seen_match_ids: set[int] = set()

    for row in rows:
        if row.lab_match_id in seen_match_ids:
            continue
        seen_match_ids.add(row.lab_match_id)

        match_status, audit_rows = classify_match(row)
        has_raw = match_status == MATCH_STATUS_HAS_RAW

        global_acc.add_match(row.lab_match_id, has_raw=has_raw)
        by_competition[row.competition].add_match(row.lab_match_id, has_raw=has_raw)
        by_comp_season[(row.competition, row.season)].add_match(
            row.lab_match_id, has_raw=has_raw
        )

        for arow in audit_rows:
            pair = (int(arow["lab_match_id"]), str(arow["field"]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            all_audit.append(arow)

            field_name = str(arow["field"])
            action = str(arow["action"])
            db_nn = arow["db_value"] not in ("", None)

            # db_non_null reale dalla riga match (più affidabile della stringa audit)
            db_nn = row.db_values.get(field_name) is not None

            for acc in (
                global_acc,
                by_competition[row.competition],
                by_comp_season[(row.competition, row.season)],
            ):
                acc.observe_field(
                    row.lab_match_id,
                    field_name,
                    action=action,
                    db_non_null=db_nn,
                )

    matches_total = len(global_acc.match_ids)
    summary: dict[str, Any] = {
        "ok": True,
        "mode": "dry_run",
        "source": "cecchino_lab_matches.raw_json",
        "matches_total": matches_total,
        "matches_with_raw_json": len(global_acc.has_raw_ids),
        "matches_without_raw_json": matches_total - len(global_acc.has_raw_ids),
        "raw_source_rows_preservable": len(global_acc.has_raw_ids),
        "unmatched_rows": 0,
        "ambiguous_rows": 0,
        "audit_rows": len(all_audit),
        "fields_per_match": len(STATS_MODEL_FIELDS),
        "GLOBAL": global_acc.finalize(),
        "COMPETITION": {
            comp: acc.finalize() for comp, acc in sorted(by_competition.items())
        },
        "COMPETITION_SEASON": {
            f"{comp}||{season}": acc.finalize()
            for (comp, season), acc in sorted(by_comp_season.items())
        },
    }
    return summary, all_audit


def run_stats_raw_reconciliation_dry_run(
    *,
    session: Session,
    output_dir: Path,
) -> dict[str, Any]:
    """Esegue dry-run read-only e scrive summary + audit su output_dir."""
    enable_read_only_transaction(session)
    rows = load_match_scan_rows(session)
    summary, audit_rows = build_summary_from_rows(rows)
    paths = write_reports(
        output_dir=output_dir,
        summary=summary,
        audit_rows=audit_rows,
    )
    summary["output"] = paths
    logger.info(
        "stats raw reconciliation dry-run: matches=%s has_raw=%s audit_rows=%s",
        summary["matches_total"],
        summary["matches_with_raw_json"],
        summary["audit_rows"],
    )
    return summary
