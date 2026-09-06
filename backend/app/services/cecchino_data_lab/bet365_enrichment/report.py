"""Scrittura report dry-run enrichment Bet365 (filesystem only)."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    ENRICHMENT_MODEL_FIELDS,
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
    MATCHED_STATUSES,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import MatchResult

DETAIL_COLUMNS = [
    "source_match_id",
    "competition_name",
    "season",
    "csv_home_team",
    "csv_away_team",
    "csv_kickoff_utc",
    "matched_lab_match_id",
    "db_dataset_id",
    "db_competition_name",
    "db_season_label",
    "db_home_team",
    "db_away_team",
    "db_kickoff_at",
    "match_status",
    "matching_rule",
    "kickoff_delta_minutes",
    "warnings",
    "odds_fields_available",
]


def build_summary(
    *,
    csv_rows_total: int,
    bet365_rows: int,
    results: list[MatchResult],
) -> dict[str, Any]:
    counts = Counter(r.match_status for r in results)
    exact = counts.get(MATCH_STATUS_EXACT, 0)
    safe_alias = counts.get(MATCH_STATUS_SAFE_ALIAS, 0)
    ambiguous = counts.get(MATCH_STATUS_AMBIGUOUS, 0)
    not_found = counts.get(MATCH_STATUS_NOT_FOUND, 0)
    matched = exact + safe_alias
    matched_pct = round((matched / bet365_rows) * 100.0, 4) if bet365_rows else 0.0

    odds_counts: dict[str, int] = {field: 0 for field in ENRICHMENT_MODEL_FIELDS}
    for r in results:
        for field, present in r.csv_row.odds_available.items():
            if present and field in odds_counts:
                odds_counts[field] += 1

    return {
        "csv_rows_total": csv_rows_total,
        "bet365_rows": bet365_rows,
        "EXACT": exact,
        "SAFE_ALIAS": safe_alias,
        "AMBIGUOUS": ambiguous,
        "NOT_FOUND": not_found,
        "matched": matched,
        "matched_pct": matched_pct,
        "matched_pct_formula": "(EXACT + SAFE_ALIAS) / bet365_rows",
        "odds_fields_available_counts": odds_counts,
        "dry_run": True,
        "db_writes": False,
    }


def _result_to_detail_row(result: MatchResult) -> dict[str, Any]:
    csv_row = result.csv_row
    matched = result.matched
    odds_avail = ",".join(
        field for field, ok in csv_row.odds_available.items() if ok
    )
    return {
        "source_match_id": csv_row.source_match_id,
        "competition_name": csv_row.competition_name or "",
        "season": csv_row.season or "",
        "csv_home_team": csv_row.home_team or "",
        "csv_away_team": csv_row.away_team or "",
        "csv_kickoff_utc": (
            csv_row.kickoff_utc.isoformat() if csv_row.kickoff_utc else ""
        ),
        "matched_lab_match_id": matched.id if matched else "",
        "db_dataset_id": matched.dataset_id if matched else "",
        "db_competition_name": matched.competition_name if matched else "",
        "db_season_label": matched.season_label if matched else "",
        "db_home_team": matched.home_team if matched else "",
        "db_away_team": matched.away_team if matched else "",
        "db_kickoff_at": (
            matched.kickoff_at.isoformat() if matched and matched.kickoff_at else ""
        ),
        "match_status": result.match_status,
        "matching_rule": result.matching_rule,
        "kickoff_delta_minutes": (
            result.kickoff_delta_minutes
            if result.kickoff_delta_minutes is not None
            else ""
        ),
        "warnings": "; ".join(result.warnings),
        "odds_fields_available": odds_avail,
    }


def build_unresolved_teams(results: list[MatchResult]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for r in results:
        if r.match_status in MATCHED_STATUSES:
            continue
        if r.csv_row.home_team:
            counter[r.csv_row.home_team.strip()] += 1
        if r.csv_row.away_team:
            counter[r.csv_row.away_team.strip()] += 1
    top = [
        {"team_name": name, "count": count}
        for name, count in counter.most_common(100)
    ]
    return {
        "unresolved_team_frequencies": top,
        "note": "Frequenze su righe AMBIGUOUS/NOT_FOUND; utile per alias espliciti futuri.",
    }


def write_reports(
    output_dir: Path,
    *,
    summary: dict[str, Any],
    results: list[MatchResult],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.json"
    detail_path = output_dir / "matches_detail.csv"
    anomalies_path = output_dir / "anomalies.csv"
    unresolved_path = output_dir / "unresolved_teams.json"

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    detail_rows = [_result_to_detail_row(r) for r in results]
    with detail_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DETAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(detail_rows)

    anomaly_rows = [
        _result_to_detail_row(r)
        for r in results
        if r.match_status in (MATCH_STATUS_AMBIGUOUS, MATCH_STATUS_NOT_FOUND)
    ]
    with anomalies_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DETAIL_COLUMNS)
        writer.writeheader()
        writer.writerows(anomaly_rows)

    unresolved = build_unresolved_teams(results)
    unresolved_path.write_text(
        json.dumps(unresolved, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "summary_json": str(summary_path),
        "matches_detail_csv": str(detail_path),
        "anomalies_csv": str(anomalies_path),
        "unresolved_teams_json": str(unresolved_path),
    }
