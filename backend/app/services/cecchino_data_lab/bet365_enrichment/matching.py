"""Matching CSV Bet365 → CecchinoLabMatch (stati EXACT/SAFE_ALIAS/AMBIGUOUS/NOT_FOUND)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from app.services.cecchino_data_lab.bet365_enrichment.constants import (
    KICKOFF_TOLERANCE,
    LAST_SEEN_ODDS_MAP,
    MATCH_STATUS_AMBIGUOUS,
    MATCH_STATUS_EXACT,
    MATCH_STATUS_NOT_FOUND,
    MATCH_STATUS_SAFE_ALIAS,
    RULE_AMBIGUOUS,
    RULE_EXACT_NORMALIZED,
    RULE_NOT_FOUND,
    RULE_SAFE_ALIAS,
)
from app.services.cecchino_data_lab.bet365_enrichment.normalize import (
    competition_names_match,
    normalize_name,
    team_names_equal,
)


@dataclass(frozen=True)
class LabMatchCandidate:
    id: int
    dataset_id: int
    competition_name: str
    season_label: str
    start_year: int | None
    home_team: str | None
    away_team: str | None
    kickoff_at: datetime | None


@dataclass
class CsvMatchRow:
    source_match_id: str
    competition_name: str | None
    competition_api_name: str | None
    season: str | None
    season_start_year: int | None
    kickoff_utc: datetime | None
    home_team: str | None
    away_team: str | None
    bookmaker: str | None
    odds_available: dict[str, bool] = field(default_factory=dict)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class MatchResult:
    csv_row: CsvMatchRow
    match_status: str
    matching_rule: str
    matched: LabMatchCandidate | None = None
    kickoff_delta_minutes: int | None = None
    warnings: list[str] = field(default_factory=list)
    candidate_ids: list[int] = field(default_factory=list)


def parse_kickoff_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Supporta "2021-07-23 18:45:00" / ISO con Z
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_season_start_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def odds_fields_available_from_row(row: dict[str, str]) -> dict[str, bool]:
    available: dict[str, bool] = {}
    for csv_col, model_field in LAST_SEEN_ODDS_MAP.items():
        raw = row.get(csv_col)
        available[model_field] = bool(str(raw).strip()) if raw is not None else False
    return available


def parse_csv_row(row: dict[str, str]) -> CsvMatchRow:
    # Solo colonne identity + last_seen: non leggere *_opening
    identity_keys = {
        "source_match_id",
        "competition_name",
        "competition_api_name",
        "season",
        "season_start_year",
        "kickoff_utc",
        "home_team",
        "away_team",
        "bookmaker",
        *LAST_SEEN_ODDS_MAP.keys(),
    }
    filtered = {k: v for k, v in row.items() if k in identity_keys}
    return CsvMatchRow(
        source_match_id=str(filtered.get("source_match_id") or "").strip(),
        competition_name=(filtered.get("competition_name") or None),
        competition_api_name=(filtered.get("competition_api_name") or None),
        season=(filtered.get("season") or None),
        season_start_year=parse_season_start_year(filtered.get("season_start_year")),
        kickoff_utc=parse_kickoff_utc(filtered.get("kickoff_utc")),
        home_team=(filtered.get("home_team") or None),
        away_team=(filtered.get("away_team") or None),
        bookmaker=(filtered.get("bookmaker") or None),
        odds_available=odds_fields_available_from_row(filtered),
        raw=filtered,
    )


def _kickoff_delta_minutes(csv_ko: datetime | None, db_ko: datetime | None) -> int | None:
    if csv_ko is None or db_ko is None:
        return None
    db = db_ko if db_ko.tzinfo else db_ko.replace(tzinfo=timezone.utc)
    db = db.astimezone(timezone.utc)
    return int(round((csv_ko - db).total_seconds() / 60.0))


def _kickoff_within_tolerance(csv_ko: datetime | None, db_ko: datetime | None) -> bool:
    delta = _kickoff_delta_minutes(csv_ko, db_ko)
    if delta is None:
        return False
    return abs(delta) <= int(KICKOFF_TOLERANCE.total_seconds() // 60)


def _season_compatible(csv_row: CsvMatchRow, candidate: LabMatchCandidate) -> bool:
    if csv_row.season_start_year is not None and candidate.start_year is not None:
        if csv_row.season_start_year == candidate.start_year:
            return True
    if csv_row.season and candidate.season_label:
        if normalize_name(csv_row.season) == normalize_name(candidate.season_label):
            return True
        # "2021/2022" vs start_year 2021 già coperto; anche prefisso anno
        season_norm = normalize_name(csv_row.season)
        label_norm = normalize_name(candidate.season_label)
        if season_norm and label_norm and (
            season_norm.startswith(label_norm) or label_norm.startswith(season_norm)
        ):
            return True
    return False


def _team_pair_match(
    csv_row: CsvMatchRow, candidate: LabMatchCandidate
) -> tuple[bool, bool]:
    home_ok, home_alias = team_names_equal(csv_row.home_team, candidate.home_team)
    away_ok, away_alias = team_names_equal(csv_row.away_team, candidate.away_team)
    if home_ok and away_ok:
        return True, bool(home_alias or away_alias)
    return False, False


def _fuzzy_suggestions(
    csv_row: CsvMatchRow, pool: list[LabMatchCandidate], *, limit: int = 3
) -> list[str]:
    """Solo suggerimenti testuali per NOT_FOUND/AMBIGUOUS; non assegna match."""
    if not pool:
        return []
    csv_home = normalize_name(csv_row.home_team)
    csv_away = normalize_name(csv_row.away_team)
    scored: list[tuple[float, LabMatchCandidate]] = []
    for cand in pool:
        h = SequenceMatcher(None, csv_home, normalize_name(cand.home_team)).ratio()
        a = SequenceMatcher(None, csv_away, normalize_name(cand.away_team)).ratio()
        scored.append((h + a, cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    for score, cand in scored[:limit]:
        if score < 0.4:
            continue
        out.append(
            f"suggest_id={cand.id}:{cand.home_team} vs {cand.away_team} "
            f"(score={score:.2f})"
        )
    return out


def find_compatible_candidates(
    csv_row: CsvMatchRow, candidates: list[LabMatchCandidate]
) -> list[tuple[LabMatchCandidate, bool, int | None]]:
    """Restituisce lista (candidate, used_alias, kickoff_delta_minutes)."""
    compatible: list[tuple[LabMatchCandidate, bool, int | None]] = []
    for cand in candidates:
        if not competition_names_match(
            csv_row.competition_name,
            csv_row.competition_api_name,
            cand.competition_name,
        ):
            continue
        if not _season_compatible(csv_row, cand):
            continue
        teams_ok, used_alias = _team_pair_match(csv_row, cand)
        if not teams_ok:
            continue
        if not _kickoff_within_tolerance(csv_row.kickoff_utc, cand.kickoff_at):
            continue
        delta = _kickoff_delta_minutes(csv_row.kickoff_utc, cand.kickoff_at)
        compatible.append((cand, used_alias, delta))
    return compatible


def match_csv_row(
    csv_row: CsvMatchRow, candidates: list[LabMatchCandidate]
) -> MatchResult:
    compatible = find_compatible_candidates(csv_row, candidates)
    if len(compatible) == 1:
        cand, used_alias, delta = compatible[0]
        if used_alias:
            return MatchResult(
                csv_row=csv_row,
                match_status=MATCH_STATUS_SAFE_ALIAS,
                matching_rule=RULE_SAFE_ALIAS,
                matched=cand,
                kickoff_delta_minutes=delta,
                candidate_ids=[cand.id],
            )
        return MatchResult(
            csv_row=csv_row,
            match_status=MATCH_STATUS_EXACT,
            matching_rule=RULE_EXACT_NORMALIZED,
            matched=cand,
            kickoff_delta_minutes=delta,
            candidate_ids=[cand.id],
        )
    if len(compatible) > 1:
        warnings = [
            f"ambiguous_count={len(compatible)}",
            *[f"candidate_id={c.id}" for c, _, _ in compatible[:5]],
        ]
        warnings.extend(_fuzzy_suggestions(csv_row, [c for c, _, _ in compatible]))
        return MatchResult(
            csv_row=csv_row,
            match_status=MATCH_STATUS_AMBIGUOUS,
            matching_rule=RULE_AMBIGUOUS,
            matched=None,
            kickoff_delta_minutes=None,
            warnings=warnings,
            candidate_ids=[c.id for c, _, _ in compatible],
        )
    # NOT_FOUND: restringi pool per suggerimenti (stessa stagione se nota)
    suggestion_pool = candidates
    if csv_row.season_start_year is not None:
        suggestion_pool = [
            c
            for c in candidates
            if c.start_year == csv_row.season_start_year
            or (
                c.season_label
                and csv_row.season
                and normalize_name(c.season_label) == normalize_name(csv_row.season)
            )
        ] or candidates
    warnings = _fuzzy_suggestions(csv_row, suggestion_pool)
    return MatchResult(
        csv_row=csv_row,
        match_status=MATCH_STATUS_NOT_FOUND,
        matching_rule=RULE_NOT_FOUND,
        matched=None,
        kickoff_delta_minutes=None,
        warnings=warnings,
        candidate_ids=[],
    )
