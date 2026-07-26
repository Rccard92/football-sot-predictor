"""Flag qualità riga e coverage Bet365."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.cecchino_data_lab.csv_parser import ParsedMatchRow


def compute_row_quality_flags(match: ParsedMatchRow) -> None:
    match.result_ft_ready = (
        match.ft_home_goals is not None
        and match.ft_away_goals is not None
        and match.ft_result is not None
    )
    match.result_ht_ready = (
        match.ht_home_goals is not None
        and match.ht_away_goals is not None
        and match.ht_result is not None
    )
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
    match.statistics_ready = all(s is not None for s in stats)
    match.bet365_1x2_pre_ready = all(
        v is not None for v in (match.bet365_home, match.bet365_draw, match.bet365_away)
    )
    match.bet365_1x2_closing_ready = all(
        v is not None
        for v in (match.bet365_closing_home, match.bet365_closing_draw, match.bet365_closing_away)
    )
    match.bet365_ou25_pre_ready = all(
        v is not None for v in (match.bet365_over_25, match.bet365_under_25)
    )
    match.bet365_ou25_closing_ready = all(
        v is not None for v in (match.bet365_closing_over_25, match.bet365_closing_under_25)
    )

    has_error = any(i.severity == "error" for i in match.issues)
    if has_error or not match.importable:
        match.row_quality_status = "error"
    elif (
        match.result_ft_ready
        and match.statistics_ready
        and match.bet365_1x2_pre_ready
    ):
        match.row_quality_status = "complete"
    else:
        match.row_quality_status = "partial"


def compute_bet365_coverage(matches: list[ParsedMatchRow]) -> dict[str, Any]:
    total = len(matches) or 0
    if total == 0:
        return {
            "total": 0,
            "1x2_pre_pct": 0.0,
            "1x2_closing_pct": 0.0,
            "ou25_pre_pct": 0.0,
            "ou25_closing_pct": 0.0,
            "1x2_pre_count": 0,
            "1x2_closing_count": 0,
            "ou25_pre_count": 0,
            "ou25_closing_count": 0,
        }

    c_1x2 = sum(1 for m in matches if m.bet365_1x2_pre_ready)
    c_1x2c = sum(1 for m in matches if m.bet365_1x2_closing_ready)
    c_ou = sum(1 for m in matches if m.bet365_ou25_pre_ready)
    c_ouc = sum(1 for m in matches if m.bet365_ou25_closing_ready)

    def pct(n: int) -> float:
        return round(100.0 * n / total, 1)

    return {
        "total": total,
        "1x2_pre_count": c_1x2,
        "1x2_closing_count": c_1x2c,
        "ou25_pre_count": c_ou,
        "ou25_closing_count": c_ouc,
        "1x2_pre_pct": pct(c_1x2),
        "1x2_closing_pct": pct(c_1x2c),
        "ou25_pre_pct": pct(c_ou),
        "ou25_closing_pct": pct(c_ouc),
    }


def dataset_quality_from_matches(
    complete: int, partial: int, errors: int, total: int
) -> str:
    if total == 0:
        return "unknown"
    if errors > total * 0.2:
        return "poor"
    if complete >= total * 0.8:
        return "complete"
    if complete + partial > 0:
        return "partial"
    return "poor"
