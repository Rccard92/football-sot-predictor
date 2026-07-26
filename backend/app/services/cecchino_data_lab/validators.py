"""Validazioni riga Football-Data — nessuna correzione silenziosa."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.services.cecchino_data_lab.constants import (
    ISSUE_AH_LINE_NOT_QUARTER,
    ISSUE_DUPLICATE_MATCH,
    ISSUE_FT_RESULT_INCONSISTENT,
    ISSUE_HT_RESULT_INCONSISTENT,
    ISSUE_INVALID_DATE,
    ISSUE_INVALID_TIME,
    ISSUE_MISSING_AWAY_TEAM,
    ISSUE_MISSING_DIVISION,
    ISSUE_MISSING_HOME_TEAM,
    ISSUE_ODDS_LTE_ONE,
    ISSUE_PARTIAL_BET365,
    ISSUE_PARTIAL_STATISTICS,
    ISSUE_SAME_TEAM,
)

if TYPE_CHECKING:
    from app.services.cecchino_data_lab.csv_parser import ParsedIssue, ParsedMatchRow


def _expected_ftr(home: int, away: int) -> str:
    if home > away:
        return "H"
    if home < away:
        return "A"
    return "D"


def _is_quarter_line(value: Decimal) -> bool:
    # Multiplo di 0.25: value * 4 è intero
    scaled = value * 4
    return scaled == scaled.to_integral_value()


def validate_match_row(
    match: ParsedMatchRow,
    *,
    expected_col_count: int,
    raw_row: dict[str, str | None],
) -> list[ParsedIssue]:
    from app.services.cecchino_data_lab.csv_parser import ParsedIssue, parse_football_date, parse_football_time

    issues: list[ParsedIssue] = []
    rn = match.source_row_number

    if not match.division_code:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_MISSING_DIVISION,
                message=f"Riga {rn}: divisione mancante.",
                source_row_number=rn,
                field_name="Div",
                raw_value=raw_row.get("Div"),
            )
        )

    raw_date = raw_row.get("Date")
    if raw_date and raw_date.strip() and match.match_date is None:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_INVALID_DATE,
                message=f"Riga {rn}: data non valida '{raw_date}'.",
                source_row_number=rn,
                field_name="Date",
                raw_value=raw_date,
            )
        )
    elif not match.match_date:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_INVALID_DATE,
                message=f"Riga {rn}: data mancante.",
                source_row_number=rn,
                field_name="Date",
                raw_value=raw_date,
            )
        )

    raw_time = raw_row.get("Time")
    if raw_time and raw_time.strip() and match.match_time is None:
        issues.append(
            ParsedIssue(
                severity="warning",
                issue_code=ISSUE_INVALID_TIME,
                message=f"Riga {rn}: ora non valida '{raw_time}'.",
                source_row_number=rn,
                field_name="Time",
                raw_value=raw_time,
            )
        )

    if not match.home_team:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_MISSING_HOME_TEAM,
                message=f"Riga {rn}: squadra casa mancante.",
                source_row_number=rn,
                field_name="HomeTeam",
            )
        )
    if not match.away_team:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_MISSING_AWAY_TEAM,
                message=f"Riga {rn}: squadra ospite mancante.",
                source_row_number=rn,
                field_name="AwayTeam",
            )
        )
    if match.home_team and match.away_team and match.home_team == match.away_team:
        issues.append(
            ParsedIssue(
                severity="error",
                issue_code=ISSUE_SAME_TEAM,
                message=f"Riga {rn}: stessa squadra in casa e trasferta ({match.home_team}).",
                source_row_number=rn,
                field_name="HomeTeam",
                raw_value=match.home_team,
            )
        )

    if (
        match.ft_home_goals is not None
        and match.ft_away_goals is not None
        and match.ft_result
    ):
        expected = _expected_ftr(match.ft_home_goals, match.ft_away_goals)
        if match.ft_result.upper() != expected:
            issues.append(
                ParsedIssue(
                    severity="error",
                    issue_code=ISSUE_FT_RESULT_INCONSISTENT,
                    message=(
                        f"Riga {rn}: FTR '{match.ft_result}' incoerente con "
                        f"{match.ft_home_goals}-{match.ft_away_goals} (atteso {expected})."
                    ),
                    source_row_number=rn,
                    field_name="FTR",
                    raw_value=match.ft_result,
                    details={"expected": expected},
                )
            )

    if (
        match.ht_home_goals is not None
        and match.ht_away_goals is not None
        and match.ht_result
    ):
        expected = _expected_ftr(match.ht_home_goals, match.ht_away_goals)
        if match.ht_result.upper() != expected:
            issues.append(
                ParsedIssue(
                    severity="error",
                    issue_code=ISSUE_HT_RESULT_INCONSISTENT,
                    message=(
                        f"Riga {rn}: HTR '{match.ht_result}' incoerente con "
                        f"{match.ht_home_goals}-{match.ht_away_goals} (atteso {expected})."
                    ),
                    source_row_number=rn,
                    field_name="HTR",
                    raw_value=match.ht_result,
                    details={"expected": expected},
                )
            )

    odds_fields = [
        ("B365H", match.bet365_home),
        ("B365D", match.bet365_draw),
        ("B365A", match.bet365_away),
        ("B365CH", match.bet365_closing_home),
        ("B365CD", match.bet365_closing_draw),
        ("B365CA", match.bet365_closing_away),
        ("B365>2.5", match.bet365_over_25),
        ("B365<2.5", match.bet365_under_25),
        ("B365C>2.5", match.bet365_closing_over_25),
        ("B365C<2.5", match.bet365_closing_under_25),
        ("B365AHH", match.bet365_ah_home),
        ("B365AHA", match.bet365_ah_away),
        ("B365CAHH", match.bet365_closing_ah_home),
        ("B365CAHA", match.bet365_closing_ah_away),
    ]
    for field_name, value in odds_fields:
        if value is not None and value <= Decimal("1"):
            issues.append(
                ParsedIssue(
                    severity="warning",
                    issue_code=ISSUE_ODDS_LTE_ONE,
                    message=f"Riga {rn}: quota {field_name}={value} ≤ 1.",
                    source_row_number=rn,
                    field_name=field_name,
                    raw_value=str(value),
                )
            )

    for field_name, value in [
        ("AHh", match.asian_handicap_home_line),
        ("AHCh", match.asian_handicap_closing_home_line),
    ]:
        if value is not None and not _is_quarter_line(value):
            issues.append(
                ParsedIssue(
                    severity="warning",
                    issue_code=ISSUE_AH_LINE_NOT_QUARTER,
                    message=f"Riga {rn}: linea AH {field_name}={value} non multipla di 0,25.",
                    source_row_number=rn,
                    field_name=field_name,
                    raw_value=str(value),
                )
            )

    # Partial statistics
    stats = [
        match.home_shots,
        match.away_shots,
        match.home_shots_on_target,
        match.away_shots_on_target,
        match.home_fouls,
        match.away_fouls,
        match.home_corners,
        match.away_corners,
        match.home_yellow_cards,
        match.away_yellow_cards,
        match.home_red_cards,
        match.away_red_cards,
    ]
    present = sum(1 for s in stats if s is not None)
    if 0 < present < len(stats):
        issues.append(
            ParsedIssue(
                severity="warning",
                issue_code=ISSUE_PARTIAL_STATISTICS,
                message=f"Riga {rn}: statistiche parziali ({present}/{len(stats)}).",
                source_row_number=rn,
                details={"present": present, "total": len(stats)},
            )
        )

    # Partial Bet365 groups
    groups = [
        ("1x2_pre", [match.bet365_home, match.bet365_draw, match.bet365_away]),
        ("1x2_closing", [match.bet365_closing_home, match.bet365_closing_draw, match.bet365_closing_away]),
        ("ou25_pre", [match.bet365_over_25, match.bet365_under_25]),
        ("ou25_closing", [match.bet365_closing_over_25, match.bet365_closing_under_25]),
        ("ah_pre", [match.asian_handicap_home_line, match.bet365_ah_home, match.bet365_ah_away]),
        (
            "ah_closing",
            [
                match.asian_handicap_closing_home_line,
                match.bet365_closing_ah_home,
                match.bet365_closing_ah_away,
            ],
        ),
    ]
    for group_name, vals in groups:
        present_g = sum(1 for v in vals if v is not None)
        if 0 < present_g < len(vals):
            issues.append(
                ParsedIssue(
                    severity="warning",
                    issue_code=ISSUE_PARTIAL_BET365,
                    message=f"Riga {rn}: quote Bet365 parziali ({group_name}: {present_g}/{len(vals)}).",
                    source_row_number=rn,
                    details={"group": group_name, "present": present_g, "total": len(vals)},
                )
            )

    # Silence unused (parse helpers kept for type checkers / future)
    _ = parse_football_date, parse_football_time, expected_col_count
    return issues


def flag_duplicate_matches(matches: list[ParsedMatchRow]) -> None:
    from app.services.cecchino_data_lab.csv_parser import ParsedIssue

    seen: dict[tuple[Any, ...], int] = {}
    for m in matches:
        if not m.match_date or not m.home_team or not m.away_team:
            continue
        key = (m.match_date, m.home_team.lower(), m.away_team.lower())
        if key in seen:
            issue = ParsedIssue(
                severity="warning",
                issue_code=ISSUE_DUPLICATE_MATCH,
                message=(
                    f"Riga {m.source_row_number}: partita duplicata rispetto a riga {seen[key]} "
                    f"({m.match_date} {m.home_team} vs {m.away_team})."
                ),
                source_row_number=m.source_row_number,
                details={"first_row": seen[key]},
            )
            m.issues.append(issue)
        else:
            seen[key] = m.source_row_number
