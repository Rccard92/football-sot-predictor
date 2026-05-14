"""Inferenza db_status e model_v04_status per campi catalogo diretto."""

from __future__ import annotations

import re
from typing import Any

# (pattern su json_path case-insensitive, db_status, hint)
DB_RULES: list[tuple[re.Pattern[str], str, str | None]] = [
    (re.compile(r"^fixture\.id$", re.I), "saved_column", "fixtures.api_fixture_id"),
    (re.compile(r"fixture\.date|fixture\.timestamp", re.I), "saved_column", "fixtures.kickoff_at"),
    (re.compile(r"fixture\.status\.short", re.I), "saved_column", "fixtures.status"),
    (re.compile(r"fixture\.referee", re.I), "saved_column", "fixtures.referee"),
    (re.compile(r"fixture\.venue\.name", re.I), "saved_column", "fixtures.venue_name"),
    (re.compile(r"goals\.home", re.I), "saved_column", "fixtures.goals_home"),
    (re.compile(r"goals\.away", re.I), "saved_column", "fixtures.goals_away"),
    (re.compile(r'statistics\["Shots on Goal"\]', re.I), "saved_column", "fixture_team_stats.shots_on_target"),
    (re.compile(r'statistics\["Total Shots"\]', re.I), "saved_column", "fixture_team_stats.total_shots"),
    (re.compile(r'statistics\["Shots insidebox"\]', re.I), "saved_column", "fixture_team_stats.shots_inside_box"),
    (re.compile(r'statistics\["Shots outsidebox"\]', re.I), "saved_column", "fixture_team_stats.shots_outside_box"),
    (re.compile(r'statistics\["Blocked Shots"\]', re.I), "saved_column", "fixture_team_stats.blocked_shots"),
    (re.compile(r'statistics\["Fouls"\]', re.I), "saved_column", "fixture_team_stats.fouls"),
    (re.compile(r'statistics\["Corner Kicks"\]', re.I), "saved_column", "fixture_team_stats.corner_kicks"),
    (re.compile(r'statistics\["Yellow Cards"\]', re.I), "saved_column", "fixture_team_stats.yellow_cards"),
    (re.compile(r'statistics\["Red Cards"\]', re.I), "saved_column", "fixture_team_stats.red_cards"),
]

V04_USED_RULES: list[re.Pattern[str]] = [
    re.compile(r'statistics\["Shots on Goal"\]', re.I),
    re.compile(r'statistics\["Total Shots"\]', re.I),
    re.compile(r'statistics\["Shots insidebox"\]', re.I),
    re.compile(r'statistics\["Shots outsidebox"\]', re.I),
    re.compile(r"goals\.(home|away)", re.I),
    re.compile(r"fixture\.date|fixture\.timestamp", re.I),
    re.compile(r"rank|points|played|goals(diff|sfor|against)", re.I),  # standings context
]


def infer_db_status(endpoint: str, json_path: str) -> tuple[str, str | None]:
    for rx, st, hint in DB_RULES:
        if rx.search(json_path):
            return st, hint
    if endpoint in ("fixtures/statistics", "fixtures", "fixtures/players", "fixtures/lineups"):
        return "unknown", None
    return "unknown", None


def infer_model_v04(endpoint: str, json_path: str) -> str:
    jp = json_path
    for rx in V04_USED_RULES:
        if rx.search(jp):
            return "used_v04"
    if endpoint == "standings" and re.search(r"rank|points|form|played|goals", jp, re.I):
        return "used_v04"
    return "not_used_v04"


def refine_db_with_raw_json(
    db_status: str,
    appeared_raw: bool,
) -> str:
    if db_status == "saved_column":
        return "saved_column"
    if appeared_raw:
        return "raw_json_only"
    if db_status == "unknown":
        return "unknown"
    return "not_saved"
