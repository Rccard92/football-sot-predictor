"""Discovery diagnostica alias squadra CSV → Lab (schedule-based, zero DB write).

Non modifica TEAM_ALIASES. Non assegna match. Fuzzy solo informativo.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    MATCH_STATUS_NOT_FOUND,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    CandidateIndex,
    LabMatchCandidate,
    MatchResult,
    find_schedule_candidates,
)
from app.services.cecchino_data_lab.bet365_enrichment.normalize import normalize_name

logger = logging.getLogger(__name__)

SCHEDULE_SINGLE = "SINGLE_SCHEDULE_CANDIDATE"
SCHEDULE_NONE = "NO_SCHEDULE_CANDIDATE"
SCHEDULE_MULTI = "MULTIPLE_SCHEDULE_CANDIDATES"

CONF_HIGH = "HIGH_CONFIDENCE"
CONF_LOW = "LOW_EVIDENCE"
CONF_CONFLICT = "CONFLICT"
CONF_IDENTITY = "IDENTITY_CONFIRMED"

SUGGESTION_COLUMNS = [
    "csv_team_name",
    "csv_team_name_display",
    "suggested_db_team_name",
    "evidence_count",
    "competitions",
    "seasons",
    "first_evidence",
    "last_evidence",
    "confidence_status",
    "conflict_count",
    "fuzzy_name_score",
]

UNRESOLVED_COLUMNS = [
    "source_match_id",
    "schedule_status",
    "competition_name",
    "season",
    "csv_home_team",
    "csv_away_team",
    "csv_kickoff_utc",
    "candidate_count",
    "candidate_ids",
]


@dataclass
class AliasEvidence:
    csv_team_raw: str
    db_team_raw: str
    competition: str
    season: str
    source_match_id: str
    lab_match_id: int
    kickoff_delta_minutes: int | None
    kickoff_sort: datetime | None


@dataclass
class ScheduleUnresolvedRow:
    source_match_id: str
    schedule_status: str
    competition_name: str
    season: str
    csv_home_team: str
    csv_away_team: str
    csv_kickoff_utc: str
    candidate_count: int
    candidate_ids: list[int]


@dataclass
class AliasDiscoveryResult:
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    schedule_unresolved: list[ScheduleUnresolvedRow] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    # Per recoverable: csv_norm -> set of confirmed db_norm (identity or HIGH)
    resolved_csv_to_db: dict[str, set[str]] = field(default_factory=dict)
    high_confidence_map: dict[str, str] = field(default_factory=dict)  # csv_norm -> db_display
    identity_norms: set[str] = field(default_factory=set)
    single_evidence_rows: list[tuple[MatchResult, LabMatchCandidate, int | None]] = field(
        default_factory=list
    )


def _display_name(raw: str | None) -> str:
    return str(raw or "").strip()


def _fuzzy_score(csv_name: str, db_name: str) -> float:
    a = normalize_name(csv_name)
    b = normalize_name(db_name)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def _evidence_sort_key(ev: AliasEvidence) -> tuple:
    ko = ev.kickoff_sort or datetime.min
    return (ko, ev.source_match_id, ev.lab_match_id)


def collect_schedule_evidence(
    results: list[MatchResult],
    *,
    index: CandidateIndex,
) -> tuple[list[AliasEvidence], list[ScheduleUnresolvedRow], list[tuple[MatchResult, LabMatchCandidate, int | None]]]:
    """Analizza NOT_FOUND: evidence su fixture unica, unresolved altrimenti."""
    evidences: list[AliasEvidence] = []
    unresolved: list[ScheduleUnresolvedRow] = []
    singles: list[tuple[MatchResult, LabMatchCandidate, int | None]] = []

    not_found = [r for r in results if r.match_status == MATCH_STATUS_NOT_FOUND]
    total = len(not_found)

    for i, result in enumerate(not_found, start=1):
        row = result.csv_row
        pool = index.lookup(row)
        schedule = find_schedule_candidates(row, pool)

        if len(schedule) == 1:
            cand, delta = schedule[0]
            singles.append((result, cand, delta))
            competition = cand.competition_name or _display_name(row.competition_name)
            season = cand.season_label or _display_name(row.season)
            for csv_team, db_team in (
                (_display_name(row.home_team), _display_name(cand.home_team)),
                (_display_name(row.away_team), _display_name(cand.away_team)),
            ):
                if not csv_team:
                    continue
                evidences.append(
                    AliasEvidence(
                        csv_team_raw=csv_team,
                        db_team_raw=db_team,
                        competition=competition,
                        season=season,
                        source_match_id=row.source_match_id,
                        lab_match_id=cand.id,
                        kickoff_delta_minutes=delta,
                        kickoff_sort=row.kickoff_utc,
                    )
                )
        else:
            status = SCHEDULE_NONE if len(schedule) == 0 else SCHEDULE_MULTI
            unresolved.append(
                ScheduleUnresolvedRow(
                    source_match_id=row.source_match_id,
                    schedule_status=status,
                    competition_name=_display_name(row.competition_name),
                    season=_display_name(row.season),
                    csv_home_team=_display_name(row.home_team),
                    csv_away_team=_display_name(row.away_team),
                    csv_kickoff_utc=(
                        row.kickoff_utc.isoformat() if row.kickoff_utc else ""
                    ),
                    candidate_count=len(schedule),
                    candidate_ids=[c.id for c, _ in schedule[:20]],
                )
            )

        if i % 1000 == 0 or i == total:
            logger.info(
                "alias-discovery: processed_not_found=%d/%d, evidence=%d, unresolved=%d",
                i,
                total,
                len(evidences),
                len(unresolved),
            )

    return evidences, unresolved, singles


def aggregate_alias_suggestions(
    evidences: list[AliasEvidence],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], dict[str, str]]:
    """Aggrega per normalize(csv); IDENTITY esclusi da suggestions.

    Returns:
        suggestions, conflicts, identity_norms, high_confidence_map (csv_norm -> db_display)
    """
    # csv_norm -> list of evidence (non-empty csv)
    by_csv: dict[str, list[AliasEvidence]] = defaultdict(list)
    csv_display: dict[str, str] = {}
    identity_norms: set[str] = set()

    for ev in evidences:
        csv_norm = normalize_name(ev.csv_team_raw)
        if not csv_norm:
            continue
        # Preferisci display più frequente / prima vista
        if csv_norm not in csv_display:
            csv_display[csv_norm] = ev.csv_team_raw
        db_norm = normalize_name(ev.db_team_raw)
        if db_norm and csv_norm == db_norm:
            identity_norms.add(csv_norm)
            continue
        by_csv[csv_norm].append(ev)

    suggestions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    high_map: dict[str, str] = {}

    for csv_norm, evs in sorted(by_csv.items(), key=lambda x: x[0]):
        # Raggruppa per db_norm
        by_db: dict[str, list[AliasEvidence]] = defaultdict(list)
        db_display: dict[str, str] = {}
        for ev in evs:
            db_norm = normalize_name(ev.db_team_raw)
            if not db_norm:
                continue
            by_db[db_norm].append(ev)
            if db_norm not in db_display:
                db_display[db_norm] = ev.db_team_raw

        distinct_targets = len(by_db)
        conflict_count = distinct_targets if distinct_targets > 1 else 0

        for db_norm, db_evs in sorted(by_db.items(), key=lambda x: (-len(x[1]), x[0])):
            sorted_evs = sorted(db_evs, key=_evidence_sort_key)
            competitions = sorted({e.competition for e in sorted_evs if e.competition})
            seasons = sorted({e.season for e in sorted_evs if e.season})
            display_csv = csv_display.get(csv_norm, sorted_evs[0].csv_team_raw)
            display_db = db_display.get(db_norm, sorted_evs[0].db_team_raw)
            evidence_count = len(sorted_evs)

            if conflict_count > 0:
                status = CONF_CONFLICT
            elif evidence_count >= 3:
                status = CONF_HIGH
            else:
                status = CONF_LOW

            row = {
                "csv_team_name": csv_norm,
                "csv_team_name_display": display_csv,
                "suggested_db_team_name": display_db,
                "evidence_count": evidence_count,
                "competitions": "|".join(competitions),
                "seasons": "|".join(seasons),
                "first_evidence": sorted_evs[0].source_match_id,
                "last_evidence": sorted_evs[-1].source_match_id,
                "confidence_status": status,
                "conflict_count": conflict_count,
                "fuzzy_name_score": _fuzzy_score(display_csv, display_db),
            }
            suggestions.append(row)
            if status == CONF_CONFLICT:
                conflicts.append(row)
            elif status == CONF_HIGH:
                high_map[csv_norm] = display_db

    # Ordina suggestions: HIGH, LOW, CONFLICT poi nome
    status_order = {CONF_HIGH: 0, CONF_LOW: 1, CONF_CONFLICT: 2}
    suggestions.sort(
        key=lambda r: (
            status_order.get(r["confidence_status"], 9),
            -int(r["evidence_count"]),
            r["csv_team_name"],
            r["suggested_db_team_name"],
        )
    )
    return suggestions, conflicts, identity_norms, high_map


def _side_resolved(
    csv_team: str | None,
    db_team: str | None,
    *,
    identity_norms: set[str],
    high_map: dict[str, str],
) -> bool:
    csv_norm = normalize_name(csv_team)
    db_norm = normalize_name(db_team)
    if not csv_norm or not db_norm:
        return False
    if csv_norm == db_norm:
        return True
    if csv_norm in identity_norms and csv_norm == db_norm:
        return True
    suggested = high_map.get(csv_norm)
    if suggested is None:
        return False
    return normalize_name(suggested) == db_norm


def build_alias_audit_summary(
    *,
    results: list[MatchResult],
    suggestions: list[dict[str, Any]],
    identity_norms: set[str],
    high_map: dict[str, str],
    singles: list[tuple[MatchResult, LabMatchCandidate, int | None]],
) -> dict[str, Any]:
    analyzed: set[str] = set()
    for r in results:
        if r.match_status != MATCH_STATUS_NOT_FOUND:
            continue
        for name in (r.csv_row.home_team, r.csv_row.away_team):
            n = normalize_name(name)
            if n:
                analyzed.add(n)

    # Unique csv_norm per confidence (non-identity suggestions)
    status_by_csv: dict[str, str] = {}
    for row in suggestions:
        csv_norm = row["csv_team_name"]
        st = row["confidence_status"]
        prev = status_by_csv.get(csv_norm)
        if prev is None or st == CONF_CONFLICT:
            status_by_csv[csv_norm] = st
        elif prev == CONF_CONFLICT:
            continue
        elif st == CONF_HIGH and prev == CONF_LOW:
            status_by_csv[csv_norm] = CONF_HIGH

    high_n = sum(1 for s in status_by_csv.values() if s == CONF_HIGH)
    low_n = sum(1 for s in status_by_csv.values() if s == CONF_LOW)
    conflict_n = sum(1 for s in status_by_csv.values() if s == CONF_CONFLICT)

    # IDENTITY: norms with identity evidence that are NOT also alias suggestions
    # (identity_norms may overlap if some evidence identity and some not — rare)
    # Count unique analyzed teams that have identity and no non-identity suggestion need
    # Actually: IDENTITY_CONFIRMED = teams with at least one identity evidence
    identity_count = len(identity_norms & analyzed)

    suggested_norms = set(status_by_csv.keys())
    not_resolved = analyzed - identity_norms - suggested_norms

    recoverable = 0
    for result, cand, _delta in singles:
        row = result.csv_row
        home_ok = _side_resolved(
            row.home_team,
            cand.home_team,
            identity_norms=identity_norms,
            high_map=high_map,
        )
        away_ok = _side_resolved(
            row.away_team,
            cand.away_team,
            identity_norms=identity_norms,
            high_map=high_map,
        )
        if home_ok and away_ok:
            recoverable += 1

    return {
        "unique_csv_team_names_analyzed": len(analyzed),
        "IDENTITY_CONFIRMED": identity_count,
        "HIGH_CONFIDENCE": high_n,
        "LOW_EVIDENCE": low_n,
        "CONFLICT": conflict_n,
        "NOT_RESOLVED": len(not_resolved),
        "not_found_total": sum(
            1 for r in results if r.match_status == MATCH_STATUS_NOT_FOUND
        ),
        "not_found_potentially_recoverable_high_confidence": recoverable,
        "schedule_single_candidate_rows": len(singles),
        "db_writes": False,
        "team_aliases_modified": False,
        "discover_aliases": True,
    }


def run_alias_discovery(
    results: list[MatchResult],
    candidates: list[LabMatchCandidate],
    *,
    index: CandidateIndex | None = None,
) -> AliasDiscoveryResult:
    idx = index if index is not None else CandidateIndex.build(candidates)
    evidences, unresolved, singles = collect_schedule_evidence(results, index=idx)
    suggestions, conflicts, identity_norms, high_map = aggregate_alias_suggestions(
        evidences
    )
    summary = build_alias_audit_summary(
        results=results,
        suggestions=suggestions,
        identity_norms=identity_norms,
        high_map=high_map,
        singles=singles,
    )
    return AliasDiscoveryResult(
        suggestions=suggestions,
        conflicts=conflicts,
        schedule_unresolved=unresolved,
        summary=summary,
        high_confidence_map=high_map,
        identity_norms=identity_norms,
        single_evidence_rows=singles,
    )


def write_alias_discovery_reports(
    output_dir: str | Path,
    discovery: AliasDiscoveryResult,
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    suggestions_path = out / "alias_suggestions.csv"
    conflicts_path = out / "alias_conflicts.csv"
    unresolved_path = out / "schedule_unresolved.csv"
    summary_path = out / "alias_audit_summary.json"

    with suggestions_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUGGESTION_COLUMNS)
        writer.writeheader()
        for row in discovery.suggestions:
            writer.writerow({k: row.get(k, "") for k in SUGGESTION_COLUMNS})

    with conflicts_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUGGESTION_COLUMNS)
        writer.writeheader()
        for row in discovery.conflicts:
            writer.writerow({k: row.get(k, "") for k in SUGGESTION_COLUMNS})

    with unresolved_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=UNRESOLVED_COLUMNS)
        writer.writeheader()
        for row in discovery.schedule_unresolved:
            writer.writerow(
                {
                    "source_match_id": row.source_match_id,
                    "schedule_status": row.schedule_status,
                    "competition_name": row.competition_name,
                    "season": row.season,
                    "csv_home_team": row.csv_home_team,
                    "csv_away_team": row.csv_away_team,
                    "csv_kickoff_utc": row.csv_kickoff_utc,
                    "candidate_count": row.candidate_count,
                    "candidate_ids": "|".join(str(i) for i in row.candidate_ids),
                }
            )

    summary_path.write_text(
        json.dumps(discovery.summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "alias_suggestions_csv": str(suggestions_path),
        "alias_conflicts_csv": str(conflicts_path),
        "schedule_unresolved_csv": str(unresolved_path),
        "alias_audit_summary_json": str(summary_path),
    }
