"""Test dry-run matching enrichment Bet365 (no DB writes)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    LAST_SEEN_ODDS_MAP,
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    is_bet365_bookmaker,
    run_bet365_enrichment_dry_run,
    run_matching,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    CandidateIndex,
    LabMatchCandidate,
    match_csv_row,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.report import build_summary


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
        "home_team": "Standard",
        "away_team": "Genk",
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
        # opening: devono essere ignorate dal parser
        "dc_1x_opening": "9.99",
        "ou_0_5_over_opening": "9.99",
        "ht_1_opening": "9.99",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def test_exact_match():
    row = parse_csv_row(_csv_row(home_team="Standard", away_team="Genk"))
    cand = _candidate(home_team="Standard", away_team="Genk")
    result = match_csv_row(row, [cand])
    assert result.match_status == MATCH_STATUS_EXACT
    assert result.matched is not None
    assert result.matched.id == 1
    assert result.kickoff_delta_minutes == 60


def test_alias_standard_liege_and_krc_genk():
    row = parse_csv_row(
        _csv_row(home_team="Standard Liège", away_team="KRC Genk")
    )
    cand = _candidate(home_team="Standard", away_team="Genk")
    result = match_csv_row(row, [cand])
    assert result.match_status == MATCH_STATUS_SAFE_ALIAS
    assert result.matched is not None
    assert result.matched.id == 1


def test_kickoff_60_minutes_accepted():
    row = parse_csv_row(_csv_row(kickoff_utc="2021-07-23 18:45:00"))
    cand = _candidate(kickoff_at=_ko(2021, 7, 23, 17, 45))
    result = match_csv_row(row, [cand])
    assert result.match_status == MATCH_STATUS_EXACT
    assert result.kickoff_delta_minutes == 60


def test_kickoff_over_2_hours_rejected():
    row = parse_csv_row(_csv_row(kickoff_utc="2021-07-23 21:00:00"))
    cand = _candidate(kickoff_at=_ko(2021, 7, 23, 17, 45))
    result = match_csv_row(row, [cand])
    assert result.match_status == MATCH_STATUS_NOT_FOUND
    assert result.matched is None


def test_ambiguous_not_accepted():
    row = parse_csv_row(_csv_row())
    c1 = _candidate(id=1, kickoff_at=_ko(2021, 7, 23, 17, 45))
    c2 = _candidate(id=2, kickoff_at=_ko(2021, 7, 23, 18, 0))
    result = match_csv_row(row, [c1, c2])
    assert result.match_status == MATCH_STATUS_AMBIGUOUS
    assert result.matched is None
    assert set(result.candidate_ids) == {1, 2}


def test_not_found():
    row = parse_csv_row(_csv_row(home_team="Unknown FC", away_team="Other FC"))
    cand = _candidate()
    result = match_csv_row(row, [cand])
    assert result.match_status == MATCH_STATUS_NOT_FOUND
    assert result.matched is None


def test_opening_columns_never_mapped_or_read():
    raw = _csv_row()
    assert "dc_1x_opening" in raw  # presente nel CSV grezzo
    parsed = parse_csv_row(raw)
    assert "dc_1x_opening" not in parsed.raw
    assert "ou_0_5_over_opening" not in parsed.raw
    assert "ht_1_opening" not in parsed.raw
    for col in LAST_SEEN_ODDS_MAP:
        assert "_opening" not in col
    # Valori opening non influenzano odds_available
    assert parsed.odds_available["bet365_dc_1x"] is True  # last_seen 1.50
    # se rimuoviamo last_seen ma lasciamo opening, deve risultare False
    raw2 = _csv_row(dc_1x_last_seen="")
    parsed2 = parse_csv_row(raw2)
    assert parsed2.odds_available["bet365_dc_1x"] is False
    assert "dc_1x_opening" not in LAST_SEEN_ODDS_MAP
    assert "dc_1x_opening" not in parsed2.raw


def test_matched_pct_on_bet365_rows_only():
    results, _index = run_matching(
        [
            parse_csv_row(_csv_row(source_match_id="1")),
            parse_csv_row(
                _csv_row(source_match_id="2", home_team="Unknown", away_team="X")
            ),
        ],
        [_candidate()],
    )
    summary = build_summary(csv_rows_total=5, bet365_rows=2, results=results)
    assert summary["EXACT"] == 1
    assert summary["NOT_FOUND"] == 1
    assert summary["matched"] == 1
    assert summary["matched_pct"] == 50.0
    assert summary["matched_pct_formula"] == "(EXACT + SAFE_ALIAS) / bet365_rows"


def test_is_bet365_bookmaker():
    assert is_bet365_bookmaker("Bet365")
    assert is_bet365_bookmaker("bet365")
    assert not is_bet365_bookmaker("Pinnacle")


class _RecordingSession:
    """Session fake: consente SELECT, vieta DML/flush/commit."""

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
        sql = str(statement).strip().lower()
        self.executed_sql.append(sql)
        # SET TRANSACTION / DML checks
        forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ")
        for token in forbidden:
            if token in sql:
                raise AssertionError(f"DML vietato in dry-run: {sql}")
        # SELECT lab candidates: restituisci rows style
        if "cecchino_lab_matches" in sql or "cecchinolabmatch" in sql.replace(" ", ""):
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
        # SET TRANSACTION READ ONLY su sqlite non arriva (skip)
        return SimpleNamespace(all=lambda: [])

    def commit(self) -> None:
        self.commit_calls += 1
        raise AssertionError("commit vietato in dry-run")

    def flush(self, *args: Any, **kwargs: Any) -> None:
        self.flush_calls += 1
        raise AssertionError("flush vietato in dry-run")

    def rollback(self) -> None:
        self.rollback_calls += 1


def test_dry_run_allows_select_but_no_dml_flush_commit(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    fieldnames = list(_csv_row().keys())
    # rimuovi opening dal CSV scritto? le lasciamo per verificare ignore
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(_csv_row(home_team="Standard Liège", away_team="KRC Genk"))
        writer.writerow(
            _csv_row(
                source_match_id="m2",
                bookmaker="Pinnacle",
                home_team="Standard",
                away_team="Genk",
            )
        )

    out_dir = tmp_path / "out"
    session = _RecordingSession([_candidate()])

    summary = run_bet365_enrichment_dry_run(
        csv_path=csv_path,
        output_dir=out_dir,
        session=session,  # type: ignore[arg-type]
    )

    assert summary["db_writes"] is False
    assert summary["dry_run"] is True
    assert summary["fuzzy_suggestions"] is False
    assert summary["csv_rows_total"] == 2
    assert summary["bet365_rows"] == 1
    assert summary["SAFE_ALIAS"] == 1
    assert summary["matched_pct"] == 100.0
    assert session.commit_calls == 0
    assert session.flush_calls == 0
    assert session.rollback_calls >= 1

    for sql in session.executed_sql:
        low = sql.lower()
        assert "insert " not in low
        assert "update " not in low
        assert "delete " not in low

    summary_path = out_dir / "summary.json"
    assert summary_path.is_file()
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    assert loaded["SAFE_ALIAS"] == 1
    assert (out_dir / "matches_detail.csv").is_file()
    assert (out_dir / "anomalies.csv").is_file()
    assert (out_dir / "unresolved_teams.json").is_file()


def test_cli_requires_dry_run():
    from app.jobs.cecchino_bet365_enrichment import main

    with pytest.raises(SystemExit) as exc:
        main(["--csv", "x.csv", "--output-dir", "out"])
    assert exc.value.code != 0


def _assert_match_results_equivalent(legacy, indexed) -> None:
    assert legacy.match_status == indexed.match_status
    assert legacy.matching_rule == indexed.matching_rule
    assert legacy.kickoff_delta_minutes == indexed.kickoff_delta_minutes
    assert legacy.candidate_ids == indexed.candidate_ids
    legacy_id = legacy.matched.id if legacy.matched else None
    indexed_id = indexed.matched.id if indexed.matched else None
    assert legacy_id == indexed_id


def test_indexed_matcher_matches_full_scan_semantics():
    """Regression: CandidateIndex by_date deve produrre gli stessi esiti del full-scan."""
    candidates = [
        _candidate(id=1, home_team="Standard", away_team="Genk"),
        _candidate(
            id=2,
            home_team="Standard",
            away_team="Genk",
            kickoff_at=_ko(2021, 7, 23, 18, 0),
        ),
        _candidate(
            id=3,
            home_team="Club Brugge",
            away_team="Anderlecht",
            kickoff_at=_ko(2021, 8, 1, 16, 0),
        ),
        # Boundary mezzanotte: DB giorno precedente, entro 120'
        _candidate(
            id=4,
            home_team="Antwerp",
            away_team="Gent",
            kickoff_at=_ko(2021, 7, 22, 23, 0),
        ),
        # Fuori tolleranza (>2h) stesso giorno rispetto a 21:00
        _candidate(
            id=5,
            home_team="Standard",
            away_team="Genk",
            kickoff_at=_ko(2021, 7, 23, 12, 0),
        ),
        # Decoy altro giorno/stagione
        _candidate(
            id=99,
            home_team="Standard",
            away_team="Genk",
            kickoff_at=_ko(2020, 1, 1, 12, 0),
            start_year=2020,
            season_label="2020/2021",
        ),
    ]
    index = CandidateIndex.build(candidates)

    cases = [
        # EXACT: solo id=1 entro ±120' (15:45 vs 17:45=120'; 18:00=135')
        parse_csv_row(
            _csv_row(source_match_id="exact", kickoff_utc="2021-07-23 15:45:00")
        ),
        # SAFE_ALIAS stesso boundary
        parse_csv_row(
            _csv_row(
                source_match_id="alias",
                home_team="Standard Liège",
                away_team="KRC Genk",
                kickoff_utc="2021-07-23 15:45:00",
            )
        ),
        # AMBIGUOUS (id=1 e id=2 entro tolleranza)
        parse_csv_row(
            _csv_row(
                source_match_id="amb",
                kickoff_utc="2021-07-23 18:30:00",
            )
        ),
        # NOT_FOUND team
        parse_csv_row(
            _csv_row(
                source_match_id="nf",
                home_team="Unknown FC",
                away_team="Other FC",
            )
        ),
        # Kickoff >2h → NOT_FOUND
        parse_csv_row(
            _csv_row(
                source_match_id="ko_far",
                kickoff_utc="2021-07-23 21:00:00",
                home_team="Standard",
                away_team="Genk",
            )
        ),
        # Midnight boundary: CSV 00:30 UTC, DB 23:00 giorno prima (Δ 90')
        parse_csv_row(
            _csv_row(
                source_match_id="midnight",
                home_team="Antwerp",
                away_team="Gent",
                kickoff_utc="2021-07-23 00:30:00",
            )
        ),
    ]

    expected_statuses = {
        "exact": MATCH_STATUS_EXACT,
        "alias": MATCH_STATUS_SAFE_ALIAS,
        "amb": MATCH_STATUS_AMBIGUOUS,
        "nf": MATCH_STATUS_NOT_FOUND,
        "ko_far": MATCH_STATUS_NOT_FOUND,
        "midnight": MATCH_STATUS_EXACT,
    }

    for row in cases:
        legacy = match_csv_row(row, candidates)
        indexed = match_csv_row(row, candidates, index=index)
        _assert_match_results_equivalent(legacy, indexed)
        assert legacy.match_status == expected_statuses[row.source_match_id]


def _classification_tuple(result):
    matched_id = result.matched.id if result.matched else None
    return (
        result.match_status,
        result.matching_rule,
        matched_id,
        list(result.candidate_ids),
        result.kickoff_delta_minutes,
    )


def test_fuzzy_on_off_same_match_status():
    """Fuzzy on/off non deve cambiare classificazione o matched."""
    candidates = [
        _candidate(id=1, home_team="Standard", away_team="Genk"),
        _candidate(
            id=2,
            home_team="Standard",
            away_team="Genk",
            kickoff_at=_ko(2021, 7, 23, 18, 0),
        ),
    ]
    cases = [
        parse_csv_row(_csv_row(source_match_id="exact")),
        parse_csv_row(
            _csv_row(
                source_match_id="alias",
                home_team="Standard Liège",
                away_team="KRC Genk",
            )
        ),
        parse_csv_row(
            _csv_row(
                source_match_id="amb",
                kickoff_utc="2021-07-23 18:30:00",
            )
        ),
        parse_csv_row(
            _csv_row(
                source_match_id="nf",
                home_team="Unknown FC",
                away_team="Other FC",
            )
        ),
    ]
    for row in cases:
        off = match_csv_row(row, candidates, fuzzy_suggestions=False)
        on = match_csv_row(row, candidates, fuzzy_suggestions=True)
        assert _classification_tuple(off) == _classification_tuple(on)
        if off.match_status in (MATCH_STATUS_AMBIGUOUS, MATCH_STATUS_NOT_FOUND):
            assert off.matched is None
            assert on.matched is None


def test_fuzzy_off_skips_sequence_matcher_on_not_found(monkeypatch):
    """Con fuzzy off, NOT_FOUND non deve chiamare SequenceMatcher/_fuzzy_suggestions."""
    import app.services.cecchino_data_lab.bet365_enrichment.matching as matching_mod

    calls = {"fuzzy": 0, "seq": 0}
    real_fuzzy = matching_mod._fuzzy_suggestions
    real_seq = matching_mod.SequenceMatcher

    def spy_fuzzy(*args, **kwargs):
        calls["fuzzy"] += 1
        return real_fuzzy(*args, **kwargs)

    def spy_seq(*args, **kwargs):
        calls["seq"] += 1
        return real_seq(*args, **kwargs)

    monkeypatch.setattr(matching_mod, "_fuzzy_suggestions", spy_fuzzy)
    monkeypatch.setattr(matching_mod, "SequenceMatcher", spy_seq)

    row = parse_csv_row(
        _csv_row(home_team="Unknown FC", away_team="Other FC")
    )
    cand = _candidate()

    off = match_csv_row(row, [cand], fuzzy_suggestions=False)
    assert off.match_status == MATCH_STATUS_NOT_FOUND
    assert off.matched is None
    assert calls["fuzzy"] == 0
    assert calls["seq"] == 0

    on = match_csv_row(row, [cand], fuzzy_suggestions=True)
    assert on.match_status == MATCH_STATUS_NOT_FOUND
    assert on.matched is None
    assert calls["fuzzy"] >= 1
    assert calls["seq"] >= 1


def test_fuzzy_never_auto_assigns_match():
    """Anche con fuzzy on, AMBIGUOUS/NOT_FOUND restano unmatched."""
    row_nf = parse_csv_row(
        _csv_row(home_team="Unknown FC", away_team="Other FC")
    )
    row_amb = parse_csv_row(
        _csv_row(kickoff_utc="2021-07-23 18:30:00")
    )
    candidates = [
        _candidate(id=1, kickoff_at=_ko(2021, 7, 23, 17, 45)),
        _candidate(id=2, kickoff_at=_ko(2021, 7, 23, 18, 0)),
    ]
    nf = match_csv_row(row_nf, candidates, fuzzy_suggestions=True)
    amb = match_csv_row(row_amb, candidates, fuzzy_suggestions=True)
    assert nf.match_status == MATCH_STATUS_NOT_FOUND
    assert nf.matched is None
    assert amb.match_status == MATCH_STATUS_AMBIGUOUS
    assert amb.matched is None

