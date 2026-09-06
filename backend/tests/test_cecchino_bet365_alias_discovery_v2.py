"""Test Alias Discovery V2 (kickoff profile, anchor, bootstrap; no DB / TEAM_ALIASES)."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.alias_discovery_v2 import (
    CONF_ANCHORED_HIGH,
    CONF_CONFLICT,
    CONF_CONFLICT_STATIC,
    CONF_SCHEDULE_ONLY,
    build_kickoff_delta_profiles,
    delta_window_for_profile,
    lookup_kickoff_profile,
    run_alias_discovery_v2,
    write_alias_discovery_v2_reports,
)
from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
    RULE_TEMP_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.dry_run import (
    run_bet365_enrichment_dry_run,
)
from app.services.cecchino_data_lab.bet365_enrichment.matching import (
    LabMatchCandidate,
    MatchResult,
    match_csv_row,
    parse_csv_row,
)
from app.services.cecchino_data_lab.bet365_enrichment.normalize import (
    resolve_team_name,
    team_names_equal,
)
from app.services.cecchino_data_lab.bet365_enrichment.team_aliases import TEAM_ALIASES


def _ko(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
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
        kickoff_at=_ko(2021, 8, 21, 18, 0),
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
        "kickoff_utc": "2021-08-21 19:00:00",
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


def _exact_result(
    raw: dict[str, str], cand: LabMatchCandidate, delta: int
) -> MatchResult:
    row = parse_csv_row(raw)
    return MatchResult(
        csv_row=row,
        match_status=MATCH_STATUS_EXACT,
        matching_rule="exact_normalized",
        matched=cand,
        kickoff_delta_minutes=delta,
        candidate_ids=[cand.id],
    )


def _not_found_result(
    raw: dict[str, str], candidates: list[LabMatchCandidate]
) -> MatchResult:
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


def test_kickoff_modal_profile_correct():
    results = []
    for i, delta in enumerate([60, 60, 60, 60, 60, 0]):
        if delta == 60:
            raw = _csv_row(
                source_match_id=f"e{i}",
                kickoff_utc=f"2021-08-{21 + i} 19:00:00",
            )
            cand = _candidate(
                id=i + 1,
                kickoff_at=_ko(2021, 8, 21 + i, 18, 0),
            )
        else:
            raw = _csv_row(
                source_match_id=f"e{i}",
                kickoff_utc=f"2021-08-{21 + i} 18:00:00",
            )
            cand = _candidate(
                id=i + 1,
                kickoff_at=_ko(2021, 8, 21 + i, 18, 0),
            )
        results.append(_exact_result(raw, cand, delta))

    profiles = build_kickoff_delta_profiles(results)
    assert len(profiles) == 1
    p = profiles[0]
    assert p.modal_delta_minutes == 60
    assert p.sample_count == 6
    assert p.modal_count == 5
    assert p.modal_share == round(5 / 6, 4)
    assert p.trusted is True


def test_trusted_vs_non_trusted_profile():
    results = []
    for i in range(3):
        cand = _candidate(id=i + 1, kickoff_at=_ko(2021, 8, 21 + i, 18, 0))
        raw = _csv_row(
            source_match_id=f"s{i}",
            kickoff_utc=f"2021-08-{21 + i} 19:00:00",
        )
        results.append(_exact_result(raw, cand, 60))
    profiles = build_kickoff_delta_profiles(results)
    assert profiles[0].trusted is False
    window, label = delta_window_for_profile(profiles[0])
    assert window is None
    assert label == "fallback_120"

    results2 = []
    for i in range(5):
        cand = _candidate(id=100 + i, kickoff_at=_ko(2021, 9, 1 + i, 18, 0))
        raw = _csv_row(
            source_match_id=f"t{i}",
            kickoff_utc=f"2021-09-0{1 + i} 19:00:00",
        )
        results2.append(_exact_result(raw, cand, 60))
    profiles2 = build_kickoff_delta_profiles(results2)
    assert profiles2[0].trusted is True
    window2, label2 = delta_window_for_profile(profiles2[0])
    assert window2 == (50, 70)
    assert label2 == "trusted"


def test_anchor_home_infers_away_alias():
    matched = []
    for i in range(5):
        cand = _candidate(
            id=1000 + i,
            competition_name="Premier League",
            kickoff_at=_ko(2021, 8, 14 + i, 15, 0),
        )
        raw = _csv_row(
            source_match_id=f"pl{i}",
            competition_name="Premier League",
            competition_api_name="Premier League",
            kickoff_utc=f"2021-08-{14 + i} 15:00:00",
            home_team="Inter",
            away_team="Milan",
        )
        matched.append(_exact_result(raw, cand, 0))

    results = list(matched)
    candidates: list[LabMatchCandidate] = []
    for i in range(3):
        day = 20 + i
        cand = _candidate(
            id=10 + i,
            competition_name="Premier League",
            home_team="Man City",
            away_team="Arsenal",
            kickoff_at=_ko(2021, 9, day, 15, 0),
        )
        candidates.append(cand)
        raw = _csv_row(
            source_match_id=f"a{i}",
            competition_name="Premier League",
            competition_api_name="Premier League",
            kickoff_utc=f"2021-09-{day} 15:00:00",
            home_team="Manchester City",
            away_team="Arsenal",
        )
        results.append(_not_found_result(raw, [cand]))

    discovery = run_alias_discovery_v2(results, candidates)
    high = [
        s
        for s in discovery.suggestions
        if s["confidence_status"] == CONF_ANCHORED_HIGH
        and s["csv_team_name"] == "manchester city"
    ]
    assert len(high) == 1
    assert high[0]["db_team_name"] == "Man City"
    assert high[0]["distinct_fixture_count"] >= 3
    assert high[0]["distinct_dates"] >= 2
    assert discovery.summary["IDENTITY_CONFIRMED"] >= 1
    assert discovery.summary["IDENTITY_CONFIRMED_means"] == (
        "unique_csv_team_norms_used_as_identity_anchors_on_selected_anchored_fixtures"
    )

def test_anchor_away_infers_home_alias():
    matched = [
        _exact_result(
            _csv_row(source_match_id=f"e{i}", kickoff_utc=f"2021-08-{21 + i} 19:00:00"),
            _candidate(id=200 + i, kickoff_at=_ko(2021, 8, 21 + i, 18, 0)),
            60,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates: list[LabMatchCandidate] = []
    for i in range(3):
        day = 10 + i
        cand = _candidate(
            id=30 + i,
            home_team="Roma",
            away_team="Lazio",
            kickoff_at=_ko(2021, 10, day, 18, 0),
        )
        candidates.append(cand)
        raw = _csv_row(
            source_match_id=f"r{i}",
            kickoff_utc=f"2021-10-{day} 19:00:00",
            home_team="AS Roma",
            away_team="Lazio",
        )
        results.append(_not_found_result(raw, [cand]))

    discovery = run_alias_discovery_v2(results, candidates)
    high = [
        s
        for s in discovery.suggestions
        if s["confidence_status"] == CONF_ANCHORED_HIGH and s["csv_team_name"] == "as roma"
    ]
    assert len(high) == 1
    assert high[0]["db_team_name"] == "Roma"


def test_identity_confirmed_only_on_selected_anchored_fixture():
    """IDENTITY_CONFIRMED conta solo identity su fixture con esattamente 1 anchored."""
    matched = [
        _exact_result(
            _csv_row(
                source_match_id=f"e{i}",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc=f"2021-08-{14 + i} 15:00:00",
                home_team="Chelsea",
                away_team="Liverpool",
            ),
            _candidate(
                id=900 + i,
                competition_name="Premier League",
                home_team="Chelsea",
                away_team="Liverpool",
                kickoff_at=_ko(2021, 8, 14 + i, 15, 0),
            ),
            0,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates: list[LabMatchCandidate] = []

    # Una sola fixture anchored: Arsenal identity → conta
    cand_ok = _candidate(
        id=1,
        competition_name="Premier League",
        home_team="Man City",
        away_team="Arsenal",
        kickoff_at=_ko(2021, 9, 1, 15, 0),
    )
    candidates.append(cand_ok)
    results.append(
        _not_found_result(
            _csv_row(
                source_match_id="ok1",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc="2021-09-01 15:00:00",
                home_team="Manchester City",
                away_team="Arsenal",
            ),
            [cand_ok],
        )
    )

    # Due fixture schedule same day entrambe con Arsenal away → >1 anchored → NON conta
    # (e non produce evidence HIGH da questa riga)
    c_a = _candidate(
        id=2,
        competition_name="Premier League",
        home_team="Brighton",
        away_team="Arsenal",
        kickoff_at=_ko(2021, 9, 5, 14, 0),
    )
    c_b = _candidate(
        id=3,
        competition_name="Premier League",
        home_team="Burnley",
        away_team="Arsenal",
        kickoff_at=_ko(2021, 9, 5, 16, 0),
    )
    candidates.extend([c_a, c_b])
    results.append(
        _not_found_result(
            _csv_row(
                source_match_id="multi",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc="2021-09-05 15:00:00",
                home_team="Mystery Town FC",
                away_team="Arsenal",
            ),
            [c_a, c_b],
        )
    )

    # Schedule-only senza identity/anchor → NON conta
    cand_so = _candidate(
        id=4,
        competition_name="Premier League",
        home_team="Club X",
        away_team="Club Y",
        kickoff_at=_ko(2021, 9, 12, 15, 0),
    )
    candidates.append(cand_so)
    results.append(
        _not_found_result(
            _csv_row(
                source_match_id="so",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc="2021-09-12 15:00:00",
                home_team="KSC Lokeren-Temse",
                away_team="Something Else FC",
            ),
            [cand_so],
        )
    )

    discovery = run_alias_discovery_v2(results, candidates)
    assert discovery.summary["IDENTITY_CONFIRMED"] == 1
    assert discovery.summary["IDENTITY_CONFIRMED_means"] == (
        "unique_csv_team_norms_used_as_identity_anchors_on_selected_anchored_fixtures"
    )


def test_no_anchor_no_anchored_high():
    matched = [
        _exact_result(
            _csv_row(
                source_match_id=f"e{i}",
                competition_name="Jupiler Pro League",
                competition_api_name="Jupiler Pro League",
                kickoff_utc=f"2021-08-{21 + i} 18:45:00",
                home_team="Standard",
                away_team="Genk",
            ),
            _candidate(
                id=300 + i,
                competition_name="Jupiler Pro League",
                home_team="Standard",
                away_team="Genk",
                kickoff_at=_ko(2021, 8, 21 + i, 18, 45),
            ),
            0,
        )
        for i in range(5)
    ]
    cand = _candidate(
        id=1,
        competition_name="Jupiler Pro League",
        home_team="Club Brugge",
        away_team="Anderlecht",
        kickoff_at=_ko(2021, 9, 12, 14, 0),
    )
    raw = _csv_row(
        source_match_id="lok",
        competition_name="Jupiler Pro League",
        competition_api_name="Jupiler Pro League",
        kickoff_utc="2021-09-12 14:00:00",
        home_team="KSC Lokeren-Temse",
        away_team="Something Else FC",
    )
    results = list(matched) + [_not_found_result(raw, [cand])]
    discovery = run_alias_discovery_v2(results, [cand])
    assert not any(
        s["confidence_status"] == CONF_ANCHORED_HIGH for s in discovery.suggestions
    )
    assert any(
        s["confidence_status"] == CONF_SCHEDULE_ONLY
        and "lokeren" in s["csv_team_name"]
        for s in discovery.suggestions
    )


def test_home_away_not_inverted():
    matched = [
        _exact_result(
            _csv_row(source_match_id=f"e{i}", kickoff_utc=f"2021-08-{21 + i} 19:00:00"),
            _candidate(id=400 + i, kickoff_at=_ko(2021, 8, 21 + i, 18, 0)),
            60,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates = []
    for i in range(3):
        day = 5 + i
        cand = _candidate(
            id=50 + i,
            home_team="Napoli",
            away_team="Juventus",
            kickoff_at=_ko(2021, 11, day, 18, 0),
        )
        candidates.append(cand)
        raw = _csv_row(
            source_match_id=f"nj{i}",
            kickoff_utc=f"2021-11-0{day} 19:00:00",
            home_team="SSC Napoli",
            away_team="Juventus",
        )
        results.append(_not_found_result(raw, [cand]))

    discovery = run_alias_discovery_v2(results, candidates)
    high = [s for s in discovery.suggestions if s["confidence_status"] == CONF_ANCHORED_HIGH]
    assert any(
        s["csv_team_name"] == "ssc napoli" and s["db_team_name"] == "Napoli" for s in high
    )
    assert not any(
        s["csv_team_name"] == "ssc napoli" and s["db_team_name"] == "Juventus" for s in high
    )


def test_bootstrap_multipass():
    matched = [
        _exact_result(
            _csv_row(
                source_match_id=f"e{i}",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc=f"2021-08-{14 + i} 15:00:00",
                home_team="Chelsea",
                away_team="Liverpool",
            ),
            _candidate(
                id=500 + i,
                competition_name="Premier League",
                home_team="Chelsea",
                away_team="Liverpool",
                kickoff_at=_ko(2021, 8, 14 + i, 15, 0),
            ),
            0,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates: list[LabMatchCandidate] = []

    for i in range(3):
        day = 1 + i
        cand = _candidate(
            id=60 + i,
            competition_name="Premier League",
            home_team="Man City",
            away_team="Arsenal",
            kickoff_at=_ko(2021, 9, day, 15, 0),
        )
        candidates.append(cand)
        results.append(
            _not_found_result(
                _csv_row(
                    source_match_id=f"p1_{i}",
                    competition_name="Premier League",
                    competition_api_name="Premier League",
                    kickoff_utc=f"2021-09-0{day} 15:00:00",
                    home_team="Manchester City",
                    away_team="Arsenal",
                ),
                [cand],
            )
        )

    for i in range(3):
        day = 10 + i
        cand = _candidate(
            id=70 + i,
            competition_name="Premier League",
            home_team="Tottenham",
            away_team="Man City",
            kickoff_at=_ko(2021, 10, day, 15, 0),
        )
        candidates.append(cand)
        results.append(
            _not_found_result(
                _csv_row(
                    source_match_id=f"p2_{i}",
                    competition_name="Premier League",
                    competition_api_name="Premier League",
                    kickoff_utc=f"2021-10-{day} 15:00:00",
                    home_team="Tottenham Hotspur",
                    away_team="Manchester City",
                ),
                [cand],
            )
        )

    discovery = run_alias_discovery_v2(results, candidates)
    norms = {
        s["csv_team_name"]: s
        for s in discovery.suggestions
        if s["confidence_status"] == CONF_ANCHORED_HIGH
    }
    assert "manchester city" in norms
    assert "tottenham hotspur" in norms
    assert norms["tottenham hotspur"]["db_team_name"] == "Tottenham"
    assert discovery.bootstrap_iterations >= 2


def test_conflict_not_promoted():
    matched = [
        _exact_result(
            _csv_row(source_match_id=f"e{i}", kickoff_utc=f"2021-08-{21 + i} 19:00:00"),
            _candidate(id=600 + i, kickoff_at=_ko(2021, 8, 21 + i, 18, 0)),
            60,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates = []
    # Date distanti (≥7 giorni) così ogni NOT_FOUND ha un solo schedule candidate
    fixtures = [
        (1, "Roma"),
        (15, "Roma"),
        (1, "AS Roma Official"),  # febbraio
        (15, "AS Roma Official"),
    ]
    for idx, (day, db_home) in enumerate(fixtures):
        month = 12 if idx < 2 else 2
        year = 2021 if idx < 2 else 2022
        cand = _candidate(
            id=80 + idx,
            home_team=db_home,
            away_team="Lazio",
            kickoff_at=_ko(year, month, day, 18, 0),
            season_label="2021/2022" if idx < 2 else "2021/2022",
            start_year=2021,
        )
        candidates.append(cand)
        results.append(
            _not_found_result(
                _csv_row(
                    source_match_id=f"c{idx}",
                    season="2021/2022",
                    season_start_year="2021",
                    kickoff_utc=f"{year}-{month:02d}-{day:02d} 19:00:00",
                    home_team="Giallorossi",
                    away_team="Lazio",
                ),
                [cand],
            )
        )

    discovery = run_alias_discovery_v2(results, candidates)
    giallo = [s for s in discovery.suggestions if s["csv_team_name"] == "giallorossi"]
    assert giallo
    assert all(s["confidence_status"] == CONF_CONFLICT for s in giallo)
    assert "giallorossi" not in discovery.trusted_aliases_norm


def test_temp_alias_matching_rule_preserves_safe_alias_status():
    row = parse_csv_row(
        _csv_row(
            home_team="Manchester City",
            away_team="Arsenal",
            kickoff_utc="2021-08-21 18:00:00",
        )
    )
    cand = _candidate(
        home_team="Man City",
        away_team="Arsenal",
        kickoff_at=_ko(2021, 8, 21, 18, 0),
    )
    result = match_csv_row(
        row,
        [cand],
        extra_aliases={"Manchester City": "Man City"},
    )
    assert result.match_status == MATCH_STATUS_SAFE_ALIAS
    assert result.matching_rule == RULE_TEMP_ALIAS
    assert result.used_temp_alias is True


def test_static_alias_precedence_over_extra():
    name, used_static, used_temp = resolve_team_name(
        "Standard Liège",
        extra_aliases={"Standard Liège": "Wrong Target"},
    )
    assert name == "Standard"
    assert used_static is True
    assert used_temp is False

    matched, used_static2, used_temp2 = team_names_equal(
        "Standard Liège",
        "Standard",
        extra_aliases={"Standard Liège": "Wrong Target"},
    )
    assert matched is True
    assert used_static2 is True
    assert used_temp2 is False


def test_conflict_with_static_alias_not_used_in_bootstrap():
    matched = [
        _exact_result(
            _csv_row(
                source_match_id=f"e{i}",
                competition_name="Jupiler Pro League",
                competition_api_name="Jupiler Pro League",
                home_team="Club Brugge",
                away_team="Anderlecht",
                kickoff_utc=f"2021-08-{21 + i} 18:45:00",
            ),
            _candidate(
                id=700 + i,
                competition_name="Jupiler Pro League",
                home_team="Club Brugge",
                away_team="Anderlecht",
                kickoff_at=_ko(2021, 8, 21 + i, 18, 45),
            ),
            0,
        )
        for i in range(5)
    ]
    results = list(matched)
    candidates = []
    for i in range(3):
        day = 1 + i
        cand = _candidate(
            id=90 + i,
            competition_name="Jupiler Pro League",
            home_team="Genk",
            away_team="Anderlecht",
            kickoff_at=_ko(2021, 9, day, 18, 45),
        )
        candidates.append(cand)
        results.append(
            _not_found_result(
                _csv_row(
                    source_match_id=f"st{i}",
                    competition_name="Jupiler Pro League",
                    competition_api_name="Jupiler Pro League",
                    kickoff_utc=f"2021-09-0{day} 18:45:00",
                    home_team="Standard Liège",
                    away_team="Anderlecht",
                ),
                [cand],
            )
        )

    aliases_before = deepcopy(TEAM_ALIASES)
    discovery = run_alias_discovery_v2(results, candidates)
    assert TEAM_ALIASES == aliases_before

    # Static alias Standard Liège -> Standard means home is NOT anchored to Genk.
    # Away Anderlecht anchors → infer Standard Liège -> Genk → CONFLICT_WITH_STATIC
    # Actually wait: resolve_team_name("Standard Liège") -> "Standard", then
    # team_names_equal compares Standard vs Genk → False. Away Anderlecht anchors.
    # So we get evidence Standard Liège -> Genk which conflicts with static.
    has_static_conflict = any(
        s["confidence_status"] == CONF_CONFLICT_STATIC for s in discovery.suggestions
    ) or any(
        c["confidence_status"] == CONF_CONFLICT_STATIC
        for c in discovery.conflict_with_static
    )
    assert has_static_conflict
    assert "standard liege" not in discovery.trusted_aliases_norm
    assert discovery.simulation_summary["team_aliases_modified"] is False


def test_simulated_matcher_does_not_modify_team_aliases():
    matched_cands = []
    matched = []
    for i in range(5):
        cand = _candidate(
            id=800 + i,
            competition_name="Premier League",
            home_team="Chelsea",
            away_team="Liverpool",
            kickoff_at=_ko(2021, 8, 14 + i, 15, 0),
        )
        matched_cands.append(cand)
        matched.append(
            _exact_result(
                _csv_row(
                    source_match_id=f"e{i}",
                    competition_name="Premier League",
                    competition_api_name="Premier League",
                    kickoff_utc=f"2021-08-{14 + i} 15:00:00",
                    home_team="Chelsea",
                    away_team="Liverpool",
                ),
                cand,
                0,
            )
        )
    results = list(matched)
    candidates = list(matched_cands)
    for i in range(3):
        day = 1 + i
        cand = _candidate(
            id=95 + i,
            competition_name="Premier League",
            home_team="Man City",
            away_team="Arsenal",
            kickoff_at=_ko(2021, 9, day, 15, 0),
        )
        candidates.append(cand)
        results.append(
            _not_found_result(
                _csv_row(
                    source_match_id=f"sim{i}",
                    competition_name="Premier League",
                    competition_api_name="Premier League",
                    kickoff_utc=f"2021-09-0{day} 15:00:00",
                    home_team="Manchester City",
                    away_team="Arsenal",
                ),
                [cand],
            )
        )

    aliases_before = deepcopy(TEAM_ALIASES)
    discovery = run_alias_discovery_v2(results, candidates)
    assert TEAM_ALIASES == aliases_before
    assert discovery.simulation_summary["recovered_matches"] >= 1
    assert discovery.simulation_summary["TEMP_ALIAS"] >= 1
    assert discovery.simulation_summary["db_writes"] is False
    assert discovery.simulation_summary["SAFE_ALIAS"] >= discovery.simulation_summary[
        "TEMP_ALIAS"
    ]


def test_zero_db_writes_dry_run_v2(tmp_path: Path):
    matched_cands = [
        _candidate(
            id=10 + i,
            competition_name="Premier League",
            home_team="Chelsea",
            away_team="Liverpool",
            kickoff_at=_ko(2021, 8, 14 + i, 15, 0),
        )
        for i in range(5)
    ]
    nf_cands = [
        _candidate(
            id=20 + i,
            competition_name="Premier League",
            home_team="Man City",
            away_team="Arsenal",
            kickoff_at=_ko(2021, 9, 1 + i, 15, 0),
        )
        for i in range(3)
    ]
    all_cands = matched_cands + nf_cands

    csv_path = tmp_path / "in.csv"
    rows = []
    for i in range(5):
        rows.append(
            _csv_row(
                source_match_id=f"e{i}",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc=f"2021-08-{14 + i} 15:00:00",
                home_team="Chelsea",
                away_team="Liverpool",
            )
        )
    for i in range(3):
        rows.append(
            _csv_row(
                source_match_id=f"nf{i}",
                competition_name="Premier League",
                competition_api_name="Premier League",
                kickoff_utc=f"2021-09-0{1 + i} 15:00:00",
                home_team="Manchester City",
                away_team="Arsenal",
            )
        )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    out_dir = tmp_path / "out"
    session = _RecordingSession(all_cands)
    aliases_before = deepcopy(TEAM_ALIASES)
    summary = run_bet365_enrichment_dry_run(
        csv_path=csv_path,
        output_dir=out_dir,
        session=session,
        discover_aliases=True,
    )
    assert session.commit_calls == 0
    assert session.flush_calls == 0
    assert TEAM_ALIASES == aliases_before
    assert summary["alias_discovery"]["db_writes"] is False
    sim = json.loads(
        (out_dir / "alias_v2_simulation_summary.json").read_text(encoding="utf-8")
    )
    assert sim["db_writes"] is False
    assert sim["team_aliases_modified"] is False


def test_lookup_profile_and_reports(tmp_path: Path):
    results = [
        _exact_result(
            _csv_row(source_match_id=f"e{i}", kickoff_utc=f"2021-08-{21 + i} 19:00:00"),
            _candidate(id=i + 1, kickoff_at=_ko(2021, 8, 21 + i, 18, 0)),
            60,
        )
        for i in range(5)
    ]
    profiles = build_kickoff_delta_profiles(results)
    row = parse_csv_row(_csv_row())
    by_key = {(p.competition_norm, p.season_key): p for p in profiles}
    found = lookup_kickoff_profile(row, by_key)
    assert found is not None
    assert found.trusted

    discovery = run_alias_discovery_v2(results, [])
    paths = write_alias_discovery_v2_reports(tmp_path, discovery)
    assert Path(paths["kickoff_delta_profiles_csv"]).is_file()
    assert Path(paths["alias_v2_simulation_summary_json"]).is_file()
