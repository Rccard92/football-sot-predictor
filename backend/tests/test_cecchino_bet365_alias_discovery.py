"""Test discovery alias Bet365 (schedule-based, no DB writes, no TEAM_ALIASES edit)."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
    CONF_CONFLICT,
    CONF_HIGH,
    CONF_LOW,
    SCHEDULE_MULTI,
    SCHEDULE_NONE,
    aggregate_alias_suggestions,
    collect_schedule_evidence,
    run_alias_discovery,
    write_alias_discovery_reports,
)
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    MATCH_STATUS_NOT_FOUND,
)
from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    run_bet365_enrichment_dry_run,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    CandidateIndex,
    LabMatchCandidate,
    MatchResult,
    find_schedule_candidates,
    match_csv_row,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.normalize import normalize_name
from app.services.cecchino_data_lab.bet365_enrichment.team_aliases import TEAM_ALIASES


def _ko(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _candidate(**kwargs: Any) -> LabMatchCandidate:
    defaults = dict(
        id=1,
        dataset_id=10,
        competition_name="Jupiler Pro League",
        season_label="2021/2022",
        start_year=2021,
        home_team="Standard",
        away_team="Genk",
        kickoff_at=_ko(2021, 7, 23, 17, 45),
    )
    defaults.update(kwargs)
    return LabMatchCandidate(**defaults)


def _csv_row(**kwargs: Any) -> dict[str, str]:
    base = {
        "source_match_id": "m1",
        "competition_name": "Jupiler Pro League",
        "competition_api_name": "Jupiler Pro League",
        "season": "2021/2022",
        "season_start_year": "2021",
        "kickoff_utc": "2021-07-23 18:45:00",
        "home_team": "Standard Liège FC",
        "away_team": "KRC Genk",
        "bookmaker": "Bet365",
        "dc_1x_last_seen": "1.50",
        "dc_12_last_seen": "",
        "dc_x2_last_seen": "2.10",
        "ou_0_5_over_last_seen": "1.05",
        "ou_0_5_under_last_seen": "",
        "ou_1_5_over_last_seen": "1.30",
        "ou_1_5_under_last_seen": "3.40",
        "ou_3_5_over_last_seen": "",
        "ou_3_5_under_last_seen": "1.40",
        "ht_1_last_seen": "2.20",
        "ht_x_last_seen": "2.10",
        "ht_2_last_seen": "3.00",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _not_found_result(raw: dict[str, str], candidates: list[LabMatchCandidate]) -> MatchResult:
    row = parse_csv_row(raw)
    result = match_csv_row(row, candidates)
    assert result.match_status == MATCH_STATUS_NOT_FOUND
    return result


class _RecordingSession:
    def __init__(self, candidates: list[LabMatchCandidate]) -> None:
        self._candidates = candidates
        self.autoflush = False
        self.commit_calls = 0
        self.flush_calls = 0
        self.rollback_calls = 0
        self.executed_sql: list[str] = []
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def get_bind(self) -> Any:
        return self._bind

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement).upper()
        self.executed_sql.append(sql)
        for verb in ("INSERT", "UPDATE", "DELETE"):
            if verb in sql and "SELECT" not in sql.split(verb)[0][-20:]:
                # allow SELECT ... ; reject DML
                pass
        if any(sql.strip().startswith(v) for v in ("INSERT", "UPDATE", "DELETE")):
            raise AssertionError(f"DML vietato in dry-run: {sql}")
        if "SET TRANSACTION" in sql:
            return SimpleNamespace(all=lambda: [])

        # Fake SELECT returning candidates as row-like namespaces
        rows = []
        for c in self._candidates:
            rows.append(
                SimpleNamespace(
                    id=c.id,
                    dataset_id=c.dataset_id,
                    home_team=c.home_team,
                    away_team=c.away_team,
                    kickoff_at=c.kickoff_at,
                    competition_name=c.competition_name,
                    season_label=c.season_label,
                    start_year=c.start_year,
                )
            )
        return SimpleNamespace(all=lambda: rows)

    def commit(self) -> None:
        self.commit_calls += 1
        raise AssertionError("commit vietato in dry-run")

    def flush(self) -> None:
        self.flush_calls += 1
        raise AssertionError("flush vietato in dry-run")

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_single_schedule_candidate_produces_evidence():
    cand = _candidate(home_team="Standard", away_team="Genk")
    result = _not_found_result(_csv_row(), [cand])
    index = CandidateIndex.build([cand])
    evidences, unresolved, singles = collect_schedule_evidence([result], index=index)
    assert len(singles) == 1
    assert unresolved == []
    assert len(evidences) == 2
    pairs = {(e.csv_team_raw, e.db_team_raw) for e in evidences}
    assert ("Standard Liège FC", "Standard") in pairs
    assert ("KRC Genk", "Genk") in pairs


def test_multiple_schedule_candidates_no_evidence():
    c1 = _candidate(id=1, kickoff_at=_ko(2021, 7, 23, 17, 45))
    c2 = _candidate(id=2, kickoff_at=_ko(2021, 7, 23, 18, 0))
    result = _not_found_result(_csv_row(kickoff_utc="2021-07-23 18:30:00"), [c1, c2])
    index = CandidateIndex.build([c1, c2])
    schedule = find_schedule_candidates(result.csv_row, index.lookup(result.csv_row))
    assert len(schedule) > 1
    evidences, unresolved, singles = collect_schedule_evidence([result], index=index)
    assert evidences == []
    assert singles == []
    assert len(unresolved) == 1
    assert unresolved[0].schedule_status == SCHEDULE_MULTI


def test_no_schedule_candidate_unresolved():
    cand = _candidate(kickoff_at=_ko(2021, 7, 23, 12, 0))  # >2h from 18:45
    result = _not_found_result(_csv_row(), [cand])
    index = CandidateIndex.build([cand])
    evidences, unresolved, singles = collect_schedule_evidence([result], index=index)
    assert evidences == []
    assert singles == []
    assert len(unresolved) == 1
    assert unresolved[0].schedule_status == SCHEDULE_NONE


def test_high_confidence_same_target_three_evidence():
    candidates = []
    results = []
    for i in range(3):
        cand = _candidate(
            id=i + 1,
            home_team="Standard",
            away_team=f"Away{i}",
            kickoff_at=_ko(2021, 7, 23 + i, 17, 45),
        )
        candidates.append(cand)
        raw = _csv_row(
            source_match_id=f"m{i}",
            home_team="Standard Liège FC",
            away_team=f"Away{i} FC",
            kickoff_utc=f"2021-07-{23 + i} 18:45:00",
        )
        results.append(_not_found_result(raw, [cand]))

    discovery = run_alias_discovery(results, candidates)
    high = [
        s
        for s in discovery.suggestions
        if s["confidence_status"] == CONF_HIGH
        and "standard liege" in s["csv_team_name"]
    ]
    assert len(high) == 1
    assert high[0]["evidence_count"] == 3
    assert high[0]["suggested_db_team_name"] == "Standard"
    assert high[0]["csv_team_name"] == normalize_name("Standard Liège FC")
    assert discovery.summary["HIGH_CONFIDENCE"] >= 1


def test_conflict_same_csv_different_db_targets():
    from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
        AliasEvidence,
    )

    evidences = [
        AliasEvidence(
            csv_team_raw="St. Liège",
            db_team_raw="Standard",
            competition="JPL",
            season="2021/2022",
            source_match_id="a",
            lab_match_id=1,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 23, 18, 0),
        ),
        AliasEvidence(
            csv_team_raw="St Liege",
            db_team_raw="Standard Liege",
            competition="JPL",
            season="2021/2022",
            source_match_id="b",
            lab_match_id=2,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 24, 18, 0),
        ),
        AliasEvidence(
            csv_team_raw="St. Liège",
            db_team_raw="RFC Seraing",
            competition="JPL",
            season="2021/2022",
            source_match_id="c",
            lab_match_id=3,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 25, 18, 0),
        ),
    ]
    # St. Liège / St Liege normalize together; Standard vs Standard Liege may differ;
    # ensure at least two distinct db norms: Standard vs RFC Seraing
    suggestions, conflicts, identity_norms, _high = aggregate_alias_suggestions(evidences)
    assert identity_norms == set()
    conflict_rows = [s for s in suggestions if s["confidence_status"] == CONF_CONFLICT]
    assert conflict_rows
    assert conflicts
    assert all(r["conflict_count"] >= 2 for r in conflict_rows)


def test_identity_confirmed_excluded_from_suggestions():
    from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
        AliasEvidence,
        build_alias_audit_summary,
    )

    evidences = [
        AliasEvidence(
            csv_team_raw="Genk",
            db_team_raw="Genk",
            competition="JPL",
            season="2021/2022",
            source_match_id="id1",
            lab_match_id=1,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 23, 18, 0),
        ),
        AliasEvidence(
            csv_team_raw="Standard Liège FC",
            db_team_raw="Standard",
            competition="JPL",
            season="2021/2022",
            source_match_id="a1",
            lab_match_id=1,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 23, 18, 0),
        ),
    ]
    suggestions, _conflicts, identity_norms, high_map = aggregate_alias_suggestions(
        evidences
    )
    assert normalize_name("Genk") in identity_norms
    assert all(s["csv_team_name"] != normalize_name("Genk") for s in suggestions)
    assert any(
        s["csv_team_name"] == normalize_name("Standard Liège FC") for s in suggestions
    )

    # Build fake NOT_FOUND results covering both teams
    cand = _candidate()
    r1 = _not_found_result(
        _csv_row(home_team="Genk", away_team="Standard Liège FC"), [cand]
    )
    summary = build_alias_audit_summary(
        results=[r1],
        suggestions=suggestions,
        identity_norms=identity_norms,
        high_map=high_map,
        singles=[],
    )
    assert summary["IDENTITY_CONFIRMED"] >= 1
    # Genk is identity → not NOT_RESOLVED
    assert normalize_name("Genk") not in (
        # reconstruct not_resolved check via counts
        set()
    )
    analyzed = {normalize_name("Genk"), normalize_name("Standard Liège FC")}
    suggested = {s["csv_team_name"] for s in suggestions}
    not_resolved = analyzed - identity_norms - suggested
    assert normalize_name("Genk") not in not_resolved
    assert summary["NOT_RESOLVED"] == len(not_resolved)


def test_low_evidence_one_or_two():
    from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
        AliasEvidence,
    )

    evidences = [
        AliasEvidence(
            csv_team_raw="Club Brugge KV",
            db_team_raw="Club Brugge",
            competition="JPL",
            season="2021/2022",
            source_match_id="x1",
            lab_match_id=1,
            kickoff_delta_minutes=5,
            kickoff_sort=_ko(2021, 8, 1, 16, 0),
        ),
        AliasEvidence(
            csv_team_raw="Club Brugge KV",
            db_team_raw="Club Brugge",
            competition="JPL",
            season="2021/2022",
            source_match_id="x2",
            lab_match_id=2,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 8, 8, 16, 0),
        ),
    ]
    suggestions, _, _, _ = aggregate_alias_suggestions(evidences)
    assert len(suggestions) == 1
    assert suggestions[0]["confidence_status"] == CONF_LOW
    assert suggestions[0]["evidence_count"] == 2


def test_dry_run_discover_aliases_no_db_write(tmp_path: Path):
    aliases_before = deepcopy(TEAM_ALIASES)
    cand = _candidate(home_team="Standard", away_team="Genk")
    csv_path = tmp_path / "in.csv"
    # Row that won't EXACT-match (different team names) but schedule-matches
    rows = [
        _csv_row(
            source_match_id="nf1",
            home_team="Standard Liège FC",
            away_team="Racing Genk",
        ),
        _csv_row(bookmaker="Pinnacle", source_match_id="skip"),
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    out_dir = tmp_path / "out"
    session = _RecordingSession([cand])
    summary = run_bet365_enrichment_dry_run(
        csv_path=csv_path,
        output_dir=out_dir,
        session=session,
        discover_aliases=True,
    )
    assert summary["discover_aliases"] is True
    assert summary["db_writes"] is False
    assert session.commit_calls == 0
    assert session.flush_calls == 0
    assert session.rollback_calls >= 1
    assert (out_dir / "kickoff_delta_profiles.csv").is_file()
    assert (out_dir / "alias_suggestions_v2.csv").is_file()
    assert (out_dir / "alias_conflicts_v2.csv").is_file()
    assert (out_dir / "schedule_unresolved_v2.csv").is_file()
    assert (out_dir / "alias_audit_summary_v2.json").is_file()
    assert (out_dir / "alias_v2_simulation_summary.json").is_file()
    audit = json.loads(
        (out_dir / "alias_audit_summary_v2.json").read_text(encoding="utf-8")
    )
    assert audit["db_writes"] is False
    assert audit["team_aliases_modified"] is False
    assert audit["alias_discovery_version"] == 2
    assert "IDENTITY_CONFIRMED" in audit
    assert "ANCHORED_HIGH_CONFIDENCE" in audit
    assert "SCHEDULE_ONLY" in audit
    assert "LOW_EVIDENCE" in audit
    assert "CONFLICT" in audit
    assert "NOT_RESOLVED" in audit
    assert TEAM_ALIASES == aliases_before
    assert "alias_v2_simulation" in summary


def test_normalized_aggregation_merges_display_variants():
    from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery import (
        AliasEvidence,
    )

    evidences = [
        AliasEvidence(
            csv_team_raw="Standard Liège FC",
            db_team_raw="Standard",
            competition="JPL",
            season="2021/2022",
            source_match_id="a",
            lab_match_id=1,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 23, 18, 0),
        ),
        AliasEvidence(
            csv_team_raw="standard liege fc",
            db_team_raw="Standard",
            competition="JPL",
            season="2021/2022",
            source_match_id="b",
            lab_match_id=2,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2021, 7, 24, 18, 0),
        ),
        AliasEvidence(
            csv_team_raw="Standard Liège FC!",
            db_team_raw="Standard",
            competition="JPL",
            season="2022/2023",
            source_match_id="c",
            lab_match_id=3,
            kickoff_delta_minutes=0,
            kickoff_sort=_ko(2022, 7, 23, 18, 0),
        ),
    ]
    suggestions, _, _, _ = aggregate_alias_suggestions(evidences)
    assert len(suggestions) == 1
    assert suggestions[0]["confidence_status"] == CONF_HIGH
    assert suggestions[0]["evidence_count"] == 3
    assert suggestions[0]["csv_team_name"] == normalize_name("Standard Liège FC")
    assert suggestions[0]["csv_team_name_display"]


def test_schedule_single_rows_consistent_with_alias_evidence():
    """Invariant: evidence alias solo da NOT_FOUND con esattamente 1 schedule candidate."""
    candidates = []
    results = []
    for i in range(3):
        cand = _candidate(
            id=i + 1,
            home_team="Standard",
            away_team=f"Away{i}",
            kickoff_at=_ko(2021, 7, 23 + i, 17, 45),
        )
        candidates.append(cand)
        raw = _csv_row(
            source_match_id=f"m{i}",
            home_team="Standard Liège FC",
            away_team=f"Away{i} FC",
            kickoff_utc=f"2021-07-{23 + i} 18:45:00",
        )
        results.append(_not_found_result(raw, [cand]))

    # Anche una riga senza schedule candidate (competizione diversa → 0 candidati)
    far = _candidate(
        id=99,
        competition_name="Serie A",
        kickoff_at=_ko(2021, 7, 23, 17, 45),
    )
    candidates.append(far)
    results.append(
        _not_found_result(
            _csv_row(
                source_match_id="far",
                competition_name="Unknown League XYZ",
                competition_api_name="Unknown League XYZ",
                home_team="Ghost FC",
                away_team="Nobody FC",
                kickoff_utc="2021-07-23 18:45:00",
            ),
            candidates,
        )
    )

    index = CandidateIndex.build(candidates)
    evidences, unresolved, singles = collect_schedule_evidence(results, index=index)
    discovery = run_alias_discovery(results, candidates, index=index)

    assert discovery.summary["schedule_single_candidate_rows"] == len(singles)
    assert len(singles) == 3
    assert discovery.summary["schedule_single_candidate_rows"] == 3
    assert len(evidences) > 0
    assert discovery.suggestions  # alias non-identity presenti
    assert discovery.summary["schedule_single_candidate_rows"] > 0

    single_ids = {r.csv_row.source_match_id for r, _c, _d in singles}
    for ev in evidences:
        assert ev.source_match_id in single_ids

    for result, cand, _delta in singles:
        sched = find_schedule_candidates(result.csv_row, index.lookup(result.csv_row))
        assert len(sched) == 1
        assert sched[0][0].id == cand.id

    assert any(u.schedule_status == SCHEDULE_NONE for u in unresolved)
    assert discovery.summary["HIGH_CONFIDENCE"] >= 1
    assert discovery.summary["LOW_EVIDENCE"] >= 1  # Away{i} FC -> Away{i}
    assert set(discovery.summary) >= {
        "unique_csv_team_names_analyzed",
        "IDENTITY_CONFIRMED",
        "HIGH_CONFIDENCE",
        "LOW_EVIDENCE",
        "CONFLICT",
        "NOT_RESOLVED",
        "schedule_single_candidate_rows",
    }