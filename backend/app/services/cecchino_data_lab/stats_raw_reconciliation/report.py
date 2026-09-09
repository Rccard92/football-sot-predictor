"""Aggregazione metriche e scrittura summary JSON + audit CSV."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.services.cecchino_data_lab.stats_raw_reconciliation.constants import (
    AUDIT_COLUMNS,
    AUDIT_CSV_FILENAME,
    CELL_ACTION_ALREADY_SAME,
    CELL_ACTION_CONFLICT,
    CELL_ACTION_INVALID_SOURCE_VALUE,
    CELL_ACTION_NO_SOURCE_VALUE,
    CELL_ACTION_WOULD_WRITE,
    COVERAGE_GROUPS,
    SOURCE_AVAILABLE_ACTIONS,
    STATS_MODEL_FIELDS,
    SUMMARY_FILENAME,
)


@dataclass
class FieldCounters:
    source_non_null: int = 0
    db_non_null: int = 0
    would_write: int = 0
    already_same: int = 0
    conflicts: int = 0
    no_source: int = 0
    invalid_source: int = 0

    def observe(self, *, action: str, db_non_null: bool) -> None:
        if db_non_null:
            self.db_non_null += 1
        if action in SOURCE_AVAILABLE_ACTIONS:
            self.source_non_null += 1
        if action == CELL_ACTION_WOULD_WRITE:
            self.would_write += 1
        elif action == CELL_ACTION_ALREADY_SAME:
            self.already_same += 1
        elif action == CELL_ACTION_CONFLICT:
            self.conflicts += 1
        elif action == CELL_ACTION_NO_SOURCE_VALUE:
            self.no_source += 1
        else:
            self.invalid_source += 1

    def to_metrics(self, matches_total: int) -> dict[str, Any]:
        return {
            "matches_total": matches_total,
            "source_non_null": self.source_non_null,
            "db_non_null": self.db_non_null,
            "would_write": self.would_write,
            "already_same": self.already_same,
            "conflicts": self.conflicts,
            "no_source": self.no_source,
            "invalid_source": self.invalid_source,
            "source_coverage_pct": _pct(self.source_non_null, matches_total),
            "db_coverage_pct": _pct(self.db_non_null, matches_total),
            "aligned_coverage_pct": _pct_or_none(
                self.already_same, self.source_non_null
            ),
        }


@dataclass
class BucketAccumulator:
    """Accumulatori per un bucket (GLOBAL / competition / competition+season)."""

    match_ids: set[int] = field(default_factory=set)
    has_raw_ids: set[int] = field(default_factory=set)
    field_counters: dict[str, FieldCounters] = field(
        default_factory=lambda: defaultdict(FieldCounters)
    )
    group_field_actions: dict[int, dict[str, str]] = field(default_factory=dict)
    group_field_db_nn: dict[int, dict[str, bool]] = field(default_factory=dict)

    def add_match(self, lab_match_id: int, *, has_raw: bool) -> None:
        self.match_ids.add(lab_match_id)
        if has_raw:
            self.has_raw_ids.add(lab_match_id)

    def observe_field(
        self,
        lab_match_id: int,
        field_name: str,
        *,
        action: str,
        db_non_null: bool,
    ) -> None:
        self.field_counters[field_name].observe(action=action, db_non_null=db_non_null)
        self.group_field_actions.setdefault(lab_match_id, {})[field_name] = action
        self.group_field_db_nn.setdefault(lab_match_id, {})[field_name] = db_non_null

    def finalize(self) -> dict[str, Any]:
        matches_total = len(self.match_ids)
        fields_out: dict[str, Any] = {
            fname: self.field_counters[fname].to_metrics(matches_total)
            for fname in STATS_MODEL_FIELDS
        }
        groups_out: dict[str, Any] = {
            gname: _group_metrics(
                match_ids=self.match_ids,
                group_fields=gfields,
                field_actions=self.group_field_actions,
                field_db_nn=self.group_field_db_nn,
                matches_total=matches_total,
            )
            for gname, gfields in COVERAGE_GROUPS.items()
        }
        return {
            "matches_total": matches_total,
            "matches_with_raw_json": len(self.has_raw_ids),
            "matches_without_raw_json": matches_total - len(self.has_raw_ids),
            "fields": fields_out,
            "groups": groups_out,
        }


def _pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(100.0 * num / den, 4)


def _pct_or_none(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(100.0 * num / den, 4)


def _group_metrics(
    *,
    match_ids: set[int],
    group_fields: tuple[str, ...],
    field_actions: dict[int, dict[str, str]],
    field_db_nn: dict[int, dict[str, bool]],
    matches_total: int,
) -> dict[str, Any]:
    """Gruppo: tutti i campi devono soddisfare la condizione (AND)."""
    source_non_null = 0
    db_non_null = 0
    would_write = 0
    already_same = 0
    conflicts = 0
    no_source = 0
    invalid_source = 0

    for mid in match_ids:
        actions_map = field_actions.get(mid, {})
        db_nn_map = field_db_nn.get(mid, {})
        resolved = [
            actions_map.get(f, CELL_ACTION_NO_SOURCE_VALUE) for f in group_fields
        ]

        if all(bool(db_nn_map.get(f)) for f in group_fields):
            db_non_null += 1

        if any(a == CELL_ACTION_INVALID_SOURCE_VALUE for a in resolved):
            invalid_source += 1
            continue

        if not all(a in SOURCE_AVAILABLE_ACTIONS for a in resolved):
            no_source += 1
            continue

        source_non_null += 1
        if all(a == CELL_ACTION_ALREADY_SAME for a in resolved):
            already_same += 1
        elif any(a == CELL_ACTION_CONFLICT for a in resolved):
            conflicts += 1
        else:
            # source completo, nessun conflict: almeno un WOULD_WRITE (o mix SAME+WRITE)
            would_write += 1

    return {
        "matches_total": matches_total,
        "source_non_null": source_non_null,
        "db_non_null": db_non_null,
        "would_write": would_write,
        "already_same": already_same,
        "conflicts": conflicts,
        "no_source": no_source,
        "invalid_source": invalid_source,
        "source_coverage_pct": _pct(source_non_null, matches_total),
        "db_coverage_pct": _pct(db_non_null, matches_total),
        "aligned_coverage_pct": _pct_or_none(already_same, source_non_null),
    }


def write_reports(
    *,
    output_dir: Path,
    summary: dict[str, Any],
    audit_rows: Iterable[dict[str, Any]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_FILENAME
    audit_path = output_dir / AUDIT_CSV_FILENAME

    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)

    with audit_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(AUDIT_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in audit_rows:
            writer.writerow({k: row.get(k, "") for k in AUDIT_COLUMNS})

    return {
        "summary_path": str(summary_path),
        "audit_path": str(audit_path),
    }
