"""Prepare-apply plan Bet365: solo SELECT + report filesystem, zero scritture DB."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cecchino_lab_match import CecchinoLabMatch
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    APPLY_PLAN_CSV_FILENAME,
    APPLY_PLAN_IDENTITY_COLUMNS,
    APPLY_PLAN_SUMMARY_FILENAME,
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_INVALID_SOURCE_VALUE,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    ENRICHMENT_MODEL_FIELDS,
    ENRICHMENT_ODDS_SELECT_CHUNK_SIZE,
    LAST_SEEN_ODDS_MAP,
    MATCH_STATUS_AMBIGUOUS,
    MATCHED_STATUSES,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import MatchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedOddsField:
    """Esito parse di una colonna *_last_seen."""

    raw: str
    value: Decimal | None = None
    invalid: bool = False


@dataclass
class ApplyPlanRow:
    source_match_id: str
    lab_match_id: int | None
    competition: str
    season: str
    csv_home_team: str
    csv_away_team: str
    db_home_team: str
    db_away_team: str
    matching_status: str
    matching_rule: str
    field_values: dict[str, str] = field(default_factory=dict)
    field_actions: dict[str, str] = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_odds_decimal(raw: str | None) -> ParsedOddsField:
    """Parse una singola quota last_seen.

    - vuoto/whitespace -> empty (NO_SOURCE_VALUE)
    - numerico -> Decimal
    - non vuoto non Decimal -> invalid (INVALID_SOURCE_VALUE)
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return ParsedOddsField(raw="", value=None, invalid=False)
    try:
        return ParsedOddsField(raw=text, value=Decimal(text), invalid=False)
    except (InvalidOperation, ValueError):
        return ParsedOddsField(raw=text, value=None, invalid=True)


def parse_last_seen_odds(raw_row: dict[str, str]) -> dict[str, ParsedOddsField]:
    """Parse tutte le 12 quote *_last_seen; ignora *_opening."""
    out: dict[str, ParsedOddsField] = {}
    for csv_col, model_field in LAST_SEEN_ODDS_MAP.items():
        out[model_field] = parse_odds_decimal(raw_row.get(csv_col))
    return out


def _normalize_decimal(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    # Confronti stabili: 1.50 == 1.5
    return value.normalize() if isinstance(value, Decimal) else Decimal(str(value)).normalize()


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def classify_cell(
    db_val: Decimal | None,
    parsed: ParsedOddsField,
) -> str:
    """Classifica una cella plan. INVALID distinto da CONFLICT."""
    if parsed.invalid:
        return CELL_ACTION_INVALID_SOURCE_VALUE
    if parsed.value is None:
        return CELL_ACTION_NO_SOURCE_VALUE
    db_norm = _normalize_decimal(_as_decimal(db_val))
    csv_norm = _normalize_decimal(parsed.value)
    if db_norm is None:
        return CELL_ACTION_WOULD_WRITE
    if db_norm == csv_norm:
        return CELL_ACTION_ALREADY_SAME
    return CELL_ACTION_CONFLICT


def _chunked(ids: Sequence[int], size: int) -> Iterable[list[int]]:
    for i in range(0, len(ids), size):
        yield list(ids[i : i + size])


def load_enrichment_odds(
    session: Session,
    lab_match_ids: Sequence[int],
    *,
    chunk_size: int = ENRICHMENT_ODDS_SELECT_CHUNK_SIZE,
) -> dict[int, dict[str, Decimal | None]]:
    """SELECT read-only delle 12 colonne enrichment, a chunk.

    Mai un singolo IN con tutti gli ID. Solo SELECT.
    """
    unique_ids = sorted({int(i) for i in lab_match_ids if i is not None})
    if not unique_ids:
        return {}

    columns = [getattr(CecchinoLabMatch, name) for name in ENRICHMENT_MODEL_FIELDS]
    result: dict[int, dict[str, Decimal | None]] = {}
    size = max(1, int(chunk_size))

    for batch in _chunked(unique_ids, size):
        stmt = select(CecchinoLabMatch.id, *columns).where(
            CecchinoLabMatch.id.in_(batch)
        )
        rows = session.execute(stmt).all()
        for row in rows:
            odds: dict[str, Decimal | None] = {}
            for idx, field_name in enumerate(ENRICHMENT_MODEL_FIELDS):
                # row[0] = id; row[1..] = enrichment fields
                odds[field_name] = _as_decimal(row[idx + 1])
            result[int(row[0])] = odds

    return result


def _competition_display(result: MatchResult) -> str:
    row = result.csv_row
    return str(row.competition_name or row.competition_api_name or "").strip()


def _season_display(result: MatchResult) -> str:
    row = result.csv_row
    if row.season:
        return str(row.season).strip()
    if row.season_start_year is not None:
        return str(row.season_start_year)
    matched = result.matched
    if matched is not None and matched.season_label:
        return str(matched.season_label).strip()
    return ""


def _format_plan_value(parsed: ParsedOddsField) -> str:
    if parsed.invalid:
        return parsed.raw
    if parsed.value is None:
        return ""
    # Mantieni rappresentazione CSV grezza quando disponibile
    return parsed.raw


def build_apply_plan_rows(
    simulated_results: list[MatchResult],
    db_odds: dict[int, dict[str, Decimal | None]],
) -> list[ApplyPlanRow]:
    """Solo righe MATCHED (EXACT/SAFE_ALIAS). NOT_FOUND/AMBIGUOUS esclusi."""
    plan_rows: list[ApplyPlanRow] = []
    for result in simulated_results:
        if result.match_status not in MATCHED_STATUSES:
            continue
        matched = result.matched
        lab_id = int(matched.id) if matched is not None else None
        csv_row = result.csv_row
        parsed_odds = parse_last_seen_odds(csv_row.raw)
        current = db_odds.get(lab_id, {}) if lab_id is not None else {}

        field_values: dict[str, str] = {}
        field_actions: dict[str, str] = {}
        for model_field in ENRICHMENT_MODEL_FIELDS:
            parsed = parsed_odds[model_field]
            action = classify_cell(current.get(model_field), parsed)
            field_values[model_field] = _format_plan_value(parsed)
            field_actions[model_field] = action

        plan_rows.append(
            ApplyPlanRow(
                source_match_id=str(csv_row.source_match_id or "").strip(),
                lab_match_id=lab_id,
                competition=_competition_display(result),
                season=_season_display(result),
                csv_home_team=str(csv_row.home_team or ""),
                csv_away_team=str(csv_row.away_team or ""),
                db_home_team=str(matched.home_team or "") if matched else "",
                db_away_team=str(matched.away_team or "") if matched else "",
                matching_status=result.match_status,
                matching_rule=result.matching_rule,
                field_values=field_values,
                field_actions=field_actions,
            )
        )
    return plan_rows


def _count_duplicates(values: list[Any]) -> int:
    counts = Counter(values)
    return sum(1 for v, n in counts.items() if v is not None and n > 1)


def evaluate_plan_invariants(
    *,
    plan_rows: list[ApplyPlanRow],
    simulated_results: list[MatchResult],
    db_odds: dict[int, dict[str, Decimal | None]],
) -> dict[str, Any]:
    """Valuta invarianti; PLAN_VALID=false se uno fallisce."""
    matched_rows = sum(
        1 for r in simulated_results if r.match_status in MATCHED_STATUSES
    )
    ambiguous_rows = sum(
        1 for r in simulated_results if r.match_status == MATCH_STATUS_AMBIGUOUS
    )
    not_found_exact = sum(
        1
        for r in simulated_results
        if r.match_status not in MATCHED_STATUSES
        and r.match_status != MATCH_STATUS_AMBIGUOUS
    )

    source_ids = [r.source_match_id for r in plan_rows]
    lab_ids = [r.lab_match_id for r in plan_rows]

    duplicate_source = _count_duplicates(source_ids)
    duplicate_lab = _count_duplicates([i for i in lab_ids if i is not None])

    empty_source = sum(1 for s in source_ids if not s)
    missing_lab = sum(1 for i in lab_ids if i is None)

    conflict_cells = 0
    invalid_cells = 0
    already_same = 0
    no_source = 0
    would_write = 0
    per_field: dict[str, dict[str, int]] = {
        f: {
            "source_non_null": 0,
            "would_write": 0,
            "already_same": 0,
            "conflicts": 0,
            "no_source_value": 0,
            "invalid_source_value": 0,
        }
        for f in ENRICHMENT_MODEL_FIELDS
    }
    invalid_rows = 0
    would_update_rows = 0
    matched_with_new = 0
    matched_without_new = 0

    lab_ids_missing_in_db = 0
    parseable_actions = frozenset(
        {
            CELL_ACTION_WOULD_WRITE,
            CELL_ACTION_ALREADY_SAME,
            CELL_ACTION_CONFLICT,
        }
    )
    for row in plan_rows:
        row_invalid = False
        row_would_write = False
        if row.lab_match_id is not None and row.lab_match_id not in db_odds:
            lab_ids_missing_in_db += 1
        for f in ENRICHMENT_MODEL_FIELDS:
            action = row.field_actions[f]
            stats = per_field[f]
            if action in parseable_actions:
                stats["source_non_null"] += 1
            if action == CELL_ACTION_WOULD_WRITE:
                would_write += 1
                stats["would_write"] += 1
                row_would_write = True
            elif action == CELL_ACTION_ALREADY_SAME:
                already_same += 1
                stats["already_same"] += 1
            elif action == CELL_ACTION_CONFLICT:
                conflict_cells += 1
                stats["conflicts"] += 1
            elif action == CELL_ACTION_NO_SOURCE_VALUE:
                no_source += 1
                stats["no_source_value"] += 1
            elif action == CELL_ACTION_INVALID_SOURCE_VALUE:
                invalid_cells += 1
                stats["invalid_source_value"] += 1
                row_invalid = True

        if row_invalid:
            invalid_rows += 1
        if row_would_write:
            would_update_rows += 1
            matched_with_new += 1
        else:
            matched_without_new += 1

    unique_sources = len({s for s in source_ids if s})
    unique_labs = len({i for i in lab_ids if i is not None})

    plan_rows_count = len(plan_rows)
    plan_rows_eq_matched = plan_rows_count == matched_rows

    failures: list[str] = []
    if duplicate_source > 0:
        failures.append("duplicate_source_match_ids")
    if duplicate_lab > 0:
        failures.append("duplicate_lab_match_ids")
    if ambiguous_rows > 0:
        failures.append("ambiguous_rows")
    if conflict_cells > 0:
        failures.append("conflict_cells")
    if invalid_cells > 0:
        failures.append("invalid_source_value_cells")
    if empty_source > 0:
        failures.append("empty_source_match_id")
    if missing_lab > 0:
        failures.append("missing_lab_match_id")
    if not plan_rows_eq_matched:
        failures.append("plan_rows_ne_matched_rows")
    if lab_ids_missing_in_db > 0:
        failures.append("lab_match_id_missing_from_db_select")

    # Biunivocità: unique counts must equal plan size when no empties/duplicates
    if plan_rows_count > 0:
        if unique_sources != plan_rows_count - empty_source and empty_source == 0:
            # if any source maps to >1 (duplicates already caught) or collision
            if unique_sources < plan_rows_count:
                if "duplicate_source_match_ids" not in failures:
                    failures.append("source_to_lab_not_injective")
        if unique_labs != plan_rows_count - missing_lab and missing_lab == 0:
            if unique_labs < plan_rows_count:
                if "duplicate_lab_match_ids" not in failures:
                    failures.append("lab_to_source_not_injective")

    plan_valid = len(failures) == 0

    return {
        "matched_rows": matched_rows,
        "not_found_rows": not_found_exact,  # NOT_FOUND (+ altri non-matched non ambigui)
        "ambiguous_rows": ambiguous_rows,
        "plan_rows": plan_rows_count,
        "unique_source_match_ids": unique_sources,
        "unique_lab_match_ids": unique_labs,
        "duplicate_source_match_ids": duplicate_source,
        "duplicate_lab_match_ids": duplicate_lab,
        "empty_source_match_id_rows": empty_source,
        "missing_lab_match_id_rows": missing_lab,
        "lab_match_ids_missing_from_db_select": lab_ids_missing_in_db,
        "matched_rows_with_any_new_odds": matched_with_new,
        "matched_rows_without_new_odds": matched_without_new,
        "would_update_rows": would_update_rows,
        "would_update_cells": would_write,
        "already_same_cells": already_same,
        "no_source_value_cells": no_source,
        "conflict_cells": conflict_cells,
        "invalid_source_value_cells": invalid_cells,
        "invalid_source_value_rows": invalid_rows,
        "per_field": per_field,
        "PLAN_VALID": plan_valid,
        "plan_validity_failures": failures,
        "plan_rows_eq_matched_rows": plan_rows_eq_matched,
    }


def plan_row_to_csv_dict(row: ApplyPlanRow) -> dict[str, str]:
    out: dict[str, str] = {
        "source_match_id": row.source_match_id,
        "lab_match_id": "" if row.lab_match_id is None else str(row.lab_match_id),
        "competition": row.competition,
        "season": row.season,
        "csv_home_team": row.csv_home_team,
        "csv_away_team": row.csv_away_team,
        "db_home_team": row.db_home_team,
        "db_away_team": row.db_away_team,
        "matching_status": row.matching_status,
        "matching_rule": row.matching_rule,
    }
    for f in ENRICHMENT_MODEL_FIELDS:
        out[f] = row.field_values.get(f, "")
        out[f"{f}__action"] = row.field_actions.get(f, "")
    return out


def apply_plan_csv_columns() -> list[str]:
    cols = list(APPLY_PLAN_IDENTITY_COLUMNS)
    for f in ENRICHMENT_MODEL_FIELDS:
        cols.append(f)
        cols.append(f"{f}__action")
    return cols


def write_apply_plan_csv(path: Path, plan_rows: list[ApplyPlanRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = apply_plan_csv_columns()
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in plan_rows:
            writer.writerow(plan_row_to_csv_dict(row))


def build_apply_summary(
    *,
    csv_rows_total: int,
    simulated_results: list[MatchResult],
    plan_rows: list[ApplyPlanRow],
    invariants: dict[str, Any],
    source_csv_sha256: str,
    apply_plan_sha256: str,
    read_only_transaction: bool,
) -> dict[str, Any]:
    return {
        "csv_rows_total": csv_rows_total,
        "matched_rows": invariants["matched_rows"],
        "not_found_rows": invariants["not_found_rows"],
        "ambiguous_rows": invariants["ambiguous_rows"],
        "unique_source_match_ids": invariants["unique_source_match_ids"],
        "unique_lab_match_ids": invariants["unique_lab_match_ids"],
        "duplicate_source_match_ids": invariants["duplicate_source_match_ids"],
        "duplicate_lab_match_ids": invariants["duplicate_lab_match_ids"],
        "empty_source_match_id_rows": invariants["empty_source_match_id_rows"],
        "missing_lab_match_id_rows": invariants["missing_lab_match_id_rows"],
        "lab_match_ids_missing_from_db_select": invariants[
            "lab_match_ids_missing_from_db_select"
        ],
        "plan_rows": invariants["plan_rows"],
        "plan_rows_eq_matched_rows": invariants["plan_rows_eq_matched_rows"],
        "matched_rows_with_any_new_odds": invariants["matched_rows_with_any_new_odds"],
        "matched_rows_without_new_odds": invariants["matched_rows_without_new_odds"],
        "would_update_rows": invariants["would_update_rows"],
        "would_update_cells": invariants["would_update_cells"],
        "already_same_cells": invariants["already_same_cells"],
        "no_source_value_cells": invariants["no_source_value_cells"],
        "conflict_cells": invariants["conflict_cells"],
        "invalid_source_value_cells": invariants["invalid_source_value_cells"],
        "invalid_source_value_rows": invariants["invalid_source_value_rows"],
        "per_field": invariants["per_field"],
        "PLAN_VALID": invariants["PLAN_VALID"],
        "plan_validity_failures": invariants["plan_validity_failures"],
        "source_csv_sha256": source_csv_sha256,
        "apply_plan_sha256": apply_plan_sha256,
        "db_writes": False,
        "read_only_transaction": read_only_transaction,
        "prepare_apply": True,
        "apply_forbidden_until_plan_valid": not bool(invariants["PLAN_VALID"]),
        "simulated_bet365_rows": len(simulated_results),
    }


def run_prepare_apply(
    *,
    session: Session,
    csv_path: Path,
    output_dir: Path,
    simulated_results: list[MatchResult],
    csv_rows_total: int,
    read_only_transaction: bool,
    chunk_size: int = ENRICHMENT_ODDS_SELECT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Costruisce plan CSV + summary JSON. Solo SELECT; nessun DML."""
    matched_ids = [
        int(r.matched.id)
        for r in simulated_results
        if r.match_status in MATCHED_STATUSES and r.matched is not None
    ]
    db_odds = load_enrichment_odds(session, matched_ids, chunk_size=chunk_size)
    plan_rows = build_apply_plan_rows(simulated_results, db_odds)
    invariants = evaluate_plan_invariants(
        plan_rows=plan_rows,
        simulated_results=simulated_results,
        db_odds=db_odds,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / APPLY_PLAN_CSV_FILENAME
    summary_path = out / APPLY_PLAN_SUMMARY_FILENAME

    write_apply_plan_csv(plan_path, plan_rows)
    apply_plan_sha256 = sha256_file(plan_path)
    source_csv_sha256 = sha256_file(Path(csv_path))

    summary = build_apply_summary(
        csv_rows_total=csv_rows_total,
        simulated_results=simulated_results,
        plan_rows=plan_rows,
        invariants=invariants,
        source_csv_sha256=source_csv_sha256,
        apply_plan_sha256=apply_plan_sha256,
        read_only_transaction=read_only_transaction,
    )

    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)

    summary["output_files"] = {
        "apply_plan_csv": str(plan_path),
        "apply_summary_json": str(summary_path),
    }
    logger.info(
        "prepare-apply: plan_rows=%d PLAN_VALID=%s would_update_cells=%d",
        len(plan_rows),
        summary["PLAN_VALID"],
        summary["would_update_cells"],
    )
    return summary
