"""Test team mapping audit V2 (reporting only; no DB / TEAM_ALIASES mutations)."""

from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery_v2 import (
    AliasDiscoveryV2Result,
    write_alias_discovery_v2_reports,
)
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
    RULE_EXACT_NORMALIZED,
    RULE_TEMP_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    run_bet365_enrichment_dry_run,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    LabMatchCandidate,
    MatchResult,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.team_aliases import TEAM_ALIASES
from app.services.cecchino_data_lab.bet365_enrichment.team_mapping_audit_v2 import (
    COVERAGE_PARTIAL,
    STATUS_IDENTITY,
    STATUS_MULTI_TARGET,
    STATUS_STATIC_ALIAS,
    STATUS_UNRESOLVED,
    STATUS_V2_TRUSTED_ALIAS,
    build_team_mapping_audit_rows,
    build_team_mapping_audit_summary,
    classify_side_status,
    write_team_mapping_audit_v2_reports,
)


def _ko(year: int, month: int, day: int, hour: int = 18, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _candidate(**kwargs: Any) -> LabMatchCandidate:
    defaults = dict(
        id=1,
        dataset_id=10,
        competition_name="Serie A",
        season_label="2021/2022",
        start_year=2021,
        home_team="Inter",
        away_team="Milan",
        kickoff_at=_ko(2021, 8, 21),
    )
    defaults.update(kwargs)
    return LabMatchCandidate(**defaults)


def _csv_row(**kwargs: Any) -> dict[str, str]:
    base = {
        "source_match_id": "m1",
        "competition_name": "Serie A",
        "competition_api_name": "Serie A",
        "season": "2021/2022",
        "season_start_year": "2021",
        "kickoff_utc": "2021-08-21 18:00:00",
        "home_team": "Inter",
        "away_team": "Milan",
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


def _matched(
    raw: dict[str, str],
    cand: LabMatchCandidate,
    *,
    status: str = MATCH_STATUS_EXACT,
    rule: str = RULE_EXACT_NORMALIZED,
    used_temp: bool = False,
) -> MatchResult:
    return MatchResult(
        csv_row=parse_csv_row(raw),
        match_status=status,
        matching_rule=rule,
        matched=cand,
        kickoff_delta_minutes=0,
        candidate_ids=[cand.id],
        used_temp_alias=used_temp,
    )


def _not_found(raw: dict[str, str]) -> MatchResult:
    return MatchResult(
        csv_row=parse_csv_row(raw),
        match_status=MATCH_STATUS_NOT_FOUND,
        matching_rule="not_found",
        matched=None,
        candidate_ids=[],
    )


def _discovery(sim_results: list[MatchResult], **kwargs: Any) -> AliasDiscoveryV2Result:
    return AliasDiscoveryV2Result(
        simulated_results=sim_results,
        trusted_aliases=kwargs.pop("trusted_aliases", {}),
        suggestions=kwargs.pop("suggestions", []),
        **kwargs,
    )


def _row_for(
    rows: list[dict[str, Any]], competition: str, csv_team: str
) -> dict[str, Any]:
    from app.services.cecchino_data_lab.bet365_enrichment.normalize import (
        normalize_name,
    )

    target = normalize_name(csv_team)
    for r in rows:
        if r["competition_name"] == competition and normalize_name(
            r["csv_team_name"]
        ) == target:
            return r
    raise AssertionError(f"missing row {competition=} {csv_team=}")


class _RecordingSession:
    def __init__(self, candidates: list[LabMatchCandidate]) -> None:
        self._candidates = candidates
        self.autoflush = False
        self.commit_calls = 0
        self.flush_calls = 0
        self.rollback_calls = 0
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def get_bind(self) -> Any:
        return self._bind

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement).upper()
        if any(sql.strip().startswith(v) for v in ("INSERT", "UPDATE", "DELETE")):
            raise AssertionError(f"DML vietato in dry-run: {sql}")
        if "SET TRANSACTION" in sql:
            return SimpleNamespace()

        class _Result:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def all(self) -> list[Any]:
                return self._rows

        rows = [
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
            for c in self._candidates
        ]
        return _Result(rows)

    def commit(self) -> None:
        self.commit_calls += 1

    def flush(self) -> None:
        self.flush_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_classify_side_identity_static_temp():
    assert classify_side_status("Inter", "Inter") == STATUS_IDENTITY
    assert (
        classify_side_status("Standard Liège", "Standard") == STATUS_STATIC_ALIAS
    )
    assert (
        classify_side_status(
            "Man City",
            "Manchester City",
            trusted_aliases={"Man City": "Manchester City"},
        )
        == STATUS_V2_TRUSTED_ALIAS
    )
    assert classify_side_status("Foo", None) is None


def test_identity_mapping_row():
    raw = _csv_row(home_team="Inter", away_team="Milan")
    cand = _candidate(home_team="Inter", away_team="Milan")
    rows = build_team_mapping_audit_rows(_discovery([_matched(raw, cand)]))
    inter = _row_for(rows, "Serie A", "Inter")
    assert inter["resolution_status"] == STATUS_IDENTITY
    assert inter["db_team_name"] == "Inter"
    assert inter["coverage_status"] == "FULL"


def test_static_alias_mapping_row():
    raw = _csv_row(home_team="Standard Liège", away_team="Genk")
    cand = _candidate(
        competition_name="Serie A",
        home_team="Standard",
        away_team="Genk",
    )
    # Genk identity; Standard Liège via TEAM_ALIASES static
    rows = build_team_mapping_audit_rows(
        _discovery(
            [
                _matched(
                    raw,
                    cand,
                    status=MATCH_STATUS_SAFE_ALIAS,
                    rule="safe_alias",
                )
            ]
        )
    )
    std = _row_for(rows, "Serie A", "Standard Liège")
    assert std["resolution_status"] == STATUS_STATIC_ALIAS
    assert std["db_team_name"] == "Standard"
    genk = _row_for(rows, "Serie A", "Genk")
    assert genk["resolution_status"] == STATUS_IDENTITY


def test_temp_alias_home_identity_away_per_side():
    """Fixture TEMP_ALIAS per home alias + away identity: status per lato, non per fixture."""
    raw = _csv_row(home_team="Man City", away_team="Arsenal")
    cand = _candidate(home_team="Manchester City", away_team="Arsenal")
    trusted = {"Man City": "Manchester City"}
    rows = build_team_mapping_audit_rows(
        _discovery(
            [
                _matched(
                    raw,
                    cand,
                    status=MATCH_STATUS_SAFE_ALIAS,
                    rule=RULE_TEMP_ALIAS,
                    used_temp=True,
                )
            ],
            trusted_aliases=trusted,
        )
    )
    home = _row_for(rows, "Serie A", "Man City")
    away = _row_for(rows, "Serie A", "Arsenal")
    assert home["resolution_status"] == STATUS_V2_TRUSTED_ALIAS
    assert home["db_team_name"] == "Manchester City"
    assert away["resolution_status"] == STATUS_IDENTITY
    assert away["db_team_name"] == "Arsenal"


def test_static_alias_one_side_identity_other():
    raw = _csv_row(home_team="KRC Genk", away_team="Club Brugge")
    cand = _candidate(home_team="Genk", away_team="Club Brugge")
    rows = build_team_mapping_audit_rows(
        _discovery(
            [
                _matched(
                    raw,
                    cand,
                    status=MATCH_STATUS_SAFE_ALIAS,
                    rule="safe_alias",
                )
            ]
        )
    )
    assert _row_for(rows, "Serie A", "KRC Genk")["resolution_status"] == STATUS_STATIC_ALIAS
    assert _row_for(rows, "Serie A", "Club Brugge")["resolution_status"] == STATUS_IDENTITY


def test_unresolved_leaves_db_team_empty():
    raw = _csv_row(home_team="Unknown FC", away_team="Also Unknown")
    rows = build_team_mapping_audit_rows(_discovery([_not_found(raw)]))
    u = _row_for(rows, "Serie A", "Unknown FC")
    assert u["resolution_status"] == STATUS_UNRESOLVED
    assert u["db_team_name"] == ""
    assert u["coverage_status"] == "NONE"


def test_partial_coverage_keeps_db_team_name():
    """3 occurrence, 2 matched same target + 1 NOT_FOUND → PARTIAL con db valorizzato."""
    sim: list[MatchResult] = []
    for i, day in enumerate((1, 2)):
        sim.append(
            _matched(
                _csv_row(
                    source_match_id=f"ok{i}",
                    home_team="Inter",
                    away_team="Milan",
                    kickoff_utc=f"2021-08-{day:02d} 18:00:00",
                ),
                _candidate(
                    id=10 + i,
                    home_team="Inter",
                    away_team="Milan",
                    kickoff_at=_ko(2021, 8, day),
                ),
            )
        )
    sim.append(
        _not_found(
            _csv_row(
                source_match_id="nf",
                home_team="Inter",
                away_team="Ghost",
                kickoff_utc="2021-08-03 18:00:00",
            )
        )
    )
    rows = build_team_mapping_audit_rows(_discovery(sim))
    inter = _row_for(rows, "Serie A", "Inter")
    assert inter["db_team_name"] == "Inter"
    assert inter["csv_occurrences"] == 3
    assert inter["matched_fixture_count"] == 2
    assert inter["unmatched_fixture_count"] == 1
    assert inter["coverage_status"] == COVERAGE_PARTIAL
    assert inter["resolution_status"] == STATUS_IDENTITY


def test_multi_target_leaves_db_empty():
    """Stesso csv_norm + competition → due DB team diversi ⇒ MULTI_TARGET, db vuoto."""
    # "Inter" e "Inter." normalizzano entrambi a "inter"
    sim = [
        _matched(
            _csv_row(source_match_id="a", home_team="Inter", away_team="Milan"),
            _candidate(id=1, home_team="Inter", away_team="Milan"),
        ),
        _matched(
            _csv_row(
                source_match_id="b",
                home_team="Inter.",
                away_team="Roma",
                kickoff_utc="2021-08-22 18:00:00",
            ),
            _candidate(
                id=2,
                home_team="Internazionale",
                away_team="Roma",
                kickoff_at=_ko(2021, 8, 22),
            ),
            status=MATCH_STATUS_SAFE_ALIAS,
            rule=RULE_TEMP_ALIAS,
            used_temp=True,
        ),
    ]
    rows = build_team_mapping_audit_rows(
        _discovery(sim, trusted_aliases={"Inter.": "Internazionale"})
    )
    inter = _row_for(rows, "Serie A", "Inter")
    assert inter["resolution_status"] == STATUS_MULTI_TARGET
    assert inter["db_team_name"] == ""
    assert "targets=" in inter["notes"]


def test_separation_by_competition():
    sim = [
        _matched(
            _csv_row(
                competition_name="Serie A",
                competition_api_name="Serie A",
                home_team="United",
                away_team="Milan",
            ),
            _candidate(
                competition_name="Serie A", home_team="United", away_team="Milan"
            ),
        ),
        _matched(
            _csv_row(
                source_match_id="m2",
                competition_name="Premier League",
                competition_api_name="Premier League",
                home_team="United",
                away_team="Chelsea",
                kickoff_utc="2021-08-22 15:00:00",
            ),
            _candidate(
                id=2,
                competition_name="Premier League",
                home_team="United",
                away_team="Chelsea",
                kickoff_at=_ko(2021, 8, 22, 15),
            ),
        ),
    ]
    rows = build_team_mapping_audit_rows(_discovery(sim))
    sa = _row_for(rows, "Serie A", "United")
    pl = _row_for(rows, "Premier League", "United")
    assert sa["competition_name"] != pl["competition_name"]
    assert sa["csv_occurrences"] == 1
    assert pl["csv_occurrences"] == 1


def test_html_contains_all_csv_teams(tmp_path: Path):
    sim = [
        _matched(
            _csv_row(home_team="Inter", away_team="Milan"),
            _candidate(home_team="Inter", away_team="Milan"),
        ),
        _not_found(
            _csv_row(
                source_match_id="nf",
                home_team="Ghost FC",
                away_team="Phantom",
                kickoff_utc="2021-08-22 18:00:00",
            )
        ),
    ]
    discovery = _discovery(sim)
    paths = write_team_mapping_audit_v2_reports(tmp_path, discovery)
    html = Path(paths["team_mapping_audit_v2_html"]).read_text(encoding="utf-8")
    for name in ("Inter", "Milan", "Ghost FC", "Phantom"):
        assert name in html
    assert "PARTIAL coverage" in html or "coverage_partial" in html.lower() or "PARTIAL" in html
    assert "COVERAGE" in html


def test_no_db_write_and_team_aliases_unchanged(tmp_path: Path):
    csv_path = tmp_path / "in.csv"
    rows = [
        _csv_row(
            source_match_id="e1",
            competition_name="Premier League",
            competition_api_name="Premier League",
            home_team="Chelsea",
            away_team="Liverpool",
            kickoff_utc="2021-08-14 15:00:00",
        )
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    session = _RecordingSession(
        [
            _candidate(
                id=1,
                competition_name="Premier League",
                home_team="Chelsea",
                away_team="Liverpool",
                kickoff_at=_ko(2021, 8, 14, 15),
            )
        ]
    )
    aliases_before = deepcopy(TEAM_ALIASES)
    out_dir = tmp_path / "out"
    summary = run_bet365_enrichment_dry_run(
        csv_path=csv_path,
        output_dir=out_dir,
        session=session,
        discover_aliases=True,
    )
    assert session.commit_calls == 0
    assert session.flush_calls == 0
    assert TEAM_ALIASES == aliases_before
    assert (out_dir / "team_mapping_audit_v2.html").is_file()
    assert (out_dir / "team_mapping_audit_v2.csv").is_file()
    assert "team_mapping_audit_v2_html" in summary["output_files"]


def test_write_reports_includes_audit_files(tmp_path: Path):
    discovery = _discovery(
        [
            _matched(
                _csv_row(),
                _candidate(),
            )
        ]
    )
    aliases_before = deepcopy(TEAM_ALIASES)
    paths = write_alias_discovery_v2_reports(tmp_path, discovery)
    assert TEAM_ALIASES == aliases_before
    assert Path(paths["team_mapping_audit_v2_csv"]).is_file()
    assert Path(paths["team_mapping_audit_v2_html"]).is_file()
    summary = build_team_mapping_audit_summary(
        build_team_mapping_audit_rows(discovery)
    )
    assert summary["db_writes"] is False
    assert summary["team_aliases_modified"] is False
    assert summary["unique_csv_teams"] >= 2
