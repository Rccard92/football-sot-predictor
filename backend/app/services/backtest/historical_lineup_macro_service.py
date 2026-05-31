"""Macro Lineups / formazioni storica point-in-time (Step J)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from statistics import mode as stats_mode

from sqlalchemy.orm import Session

from app.schemas.backtest_historical_fixture_snapshot import HistoricalFixtureOfficialSnapshot
from app.schemas.backtest_historical_lineup_audit import HistoricalLineupSideCoverage
from app.schemas.backtest_point_in_time import TeamLineupMacroPointInTime
from app.services.backtest.historical_fixture_snapshot_service import (
    side_bench_raw,
    side_starters_raw,
)
from app.services.backtest.pit_player_rolling_stats import (
    RawPlayerRow,
    count_xi_overlap,
    load_previous_official_lineups,
)

LINEUP_MACRO_INDEX_MIN = 0.85
LINEUP_MACRO_INDEX_MAX = 1.15

_OFFENSIVE_POSITION_TOKENS = (
    "F", "FW", "FORWARD", "ST", "CF", "SS", "A", "AM", "CAM", "LW", "RW", "WG", "W",
    "ATT", "ATTACK", "TREQUART", "WINGER",
)


def _clamp_lineup_index(value: float) -> float:
    return round(max(LINEUP_MACRO_INDEX_MIN, min(LINEUP_MACRO_INDEX_MAX, float(value))), 4)


def _normalize_formation(formation: str | None) -> str | None:
    if not formation:
        return None
    cleaned = re.sub(r"\s+", "", str(formation).strip())
    return cleaned or None


def _parse_formation_parts(formation: str | None) -> list[int]:
    norm = _normalize_formation(formation)
    if not norm:
        return []
    parts: list[int] = []
    for chunk in re.split(r"[-/]", norm):
        if chunk.isdigit():
            parts.append(int(chunk))
    return parts


def official_xi_presence_index(coverage: HistoricalLineupSideCoverage) -> float:
    if not coverage.has_official_xi:
        return 0.97
    if coverage.source_table == "fixture_lineups" and coverage.starters_count >= 11:
        return 1.03
    if coverage.starters_count >= 9:
        return 1.00
    return 0.97


def starter_completeness_index(starters_count: int) -> float:
    if starters_count >= 11:
        return 1.00
    if starters_count >= 9:
        return 0.96
    return 0.92


def formation_structure_index(formation: str | None) -> float:
    parts = _parse_formation_parts(formation)
    if not parts:
        return 1.00
    offensive_line = parts[-1] if parts else 0
    defenders = parts[0] if parts else 0
    if offensive_line >= 3:
        return 1.02
    if defenders >= 5 and offensive_line <= 1:
        return 0.98
    return 1.00


def xi_continuity_index(overlap_count: int | None) -> float:
    if overlap_count is None:
        return 1.00
    if overlap_count >= 8:
        return 1.03
    if overlap_count >= 6:
        return 1.00
    if overlap_count >= 4:
        return 0.97
    return 0.94


def _formation_similar(current: str | None, other: str | None) -> bool:
    cur_parts = _parse_formation_parts(current)
    oth_parts = _parse_formation_parts(other)
    if not cur_parts or not oth_parts:
        return False
    if cur_parts == oth_parts:
        return True
    if len(cur_parts) == len(oth_parts) and cur_parts[:2] == oth_parts[:2]:
        return True
    return False


def formation_change_index(
    current: str | None,
    previous: str | None,
    common: str | None,
) -> float:
    baseline = previous or common
    if baseline is None:
        return 1.00
    norm_current = _normalize_formation(current)
    norm_baseline = _normalize_formation(baseline)
    if norm_current and norm_baseline and norm_current == norm_baseline:
        return 1.02
    if _formation_similar(current, baseline):
        return 1.00
    return 0.97


def _is_offensive_position(position: str | None) -> bool:
    if not position:
        return False
    upper = position.strip().upper()
    return any(tok in upper for tok in _OFFENSIVE_POSITION_TOKENS)


def offensive_starter_count_index(starters: list[RawPlayerRow]) -> tuple[float, bool]:
    if not starters:
        return 1.00, False
    has_roles = any(s.position for s in starters)
    if not has_roles:
        return 1.00, False
    offensive_count = sum(1 for s in starters if _is_offensive_position(s.position))
    if offensive_count >= 3:
        return 1.03, True
    if offensive_count == 2:
        return 1.00, True
    return 0.97, True


def bench_availability_index(bench_count: int, *, bench_present: bool) -> tuple[float, bool]:
    if not bench_present:
        return 1.00, False
    if bench_count >= 7:
        return 1.01, True
    if bench_count >= 3:
        return 1.00, True
    return 0.98, True


def _common_formation(previous_lineups: list) -> str | None:
    formations = [_normalize_formation(item.formation) for item in previous_lineups]
    formations = [f for f in formations if f]
    if not formations:
        return None
    try:
        return stats_mode(formations)
    except Exception:
        return Counter(formations).most_common(1)[0][0]


def compute_lineup_macro_index(components: dict[str, float]) -> float:
    raw = (
        0.15 * components["official_xi_presence_index"]
        + 0.15 * components["starter_completeness_index"]
        + 0.15 * components["formation_structure_index"]
        + 0.25 * components["xi_continuity_index"]
        + 0.15 * components["formation_change_index"]
        + 0.10 * components["offensive_starter_count_index"]
        + 0.05 * components["bench_availability_index"]
    )
    return _clamp_lineup_index(raw)


class HistoricalLineupMacroService:
    def build_team_lineup_macro(
        self,
        db: Session,
        *,
        snapshot: HistoricalFixtureOfficialSnapshot,
        competition_id: int,
        team_id: int,
        cutoff_time: datetime,
        side: str,
    ) -> TeamLineupMacroPointInTime:
        side_snap = snapshot.home if side == "home" else snapshot.away
        coverage = side_snap.coverage
        starters = side_starters_raw(side_snap)
        bench = side_bench_raw(side_snap)

        if side_snap.status == "missing" or not coverage.has_official_xi or not starters:
            return TeamLineupMacroPointInTime(
                status="neutral_fallback",
                lineup_macro_index=1.0,
                starters_count=len(starters),
                bench_count=len(bench),
                formation=side_snap.formation,
                warnings=["target_fixture_lineup_missing"],
                fallback_variables=["historical_lineup_macro"],
                source_fixture_id=int(snapshot.fixture_id),
            )

        warnings: list[str] = []
        previous_lineups = load_previous_official_lineups(
            db,
            team_id=int(team_id),
            competition_id=int(competition_id),
            cutoff=cutoff_time,
            limit=5,
        )

        overlap_count: int | None = None
        overlap_pct: float | None = None
        formation_changed_vs_previous: bool | None = None
        formation_changed_vs_common: bool | None = None

        if previous_lineups:
            prev = previous_lineups[0]
            overlap_count = count_xi_overlap(starters, prev.starters)
            overlap_pct = round(100.0 * overlap_count / 11.0, 2)
            norm_cur = _normalize_formation(coverage.formation)
            norm_prev = _normalize_formation(prev.formation)
            if norm_cur and norm_prev:
                formation_changed_vs_previous = norm_cur != norm_prev
            common = _common_formation(previous_lineups)
            if common and norm_cur:
                formation_changed_vs_common = norm_cur != common
        else:
            warnings.append("no_previous_xi_for_continuity")

        common_formation = _common_formation(previous_lineups) if previous_lineups else None
        prev_formation = previous_lineups[0].formation if previous_lineups else None

        offensive_idx, roles_used = offensive_starter_count_index(starters)
        if not roles_used:
            warnings.append("offensive_roles_missing")

        bench_present = len(bench) > 0 or coverage.bench_count > 0
        bench_idx, bench_used = bench_availability_index(len(bench), bench_present=bench_present)
        if not bench_used:
            warnings.append("bench_missing")

        if previous_lineups and prev_formation is None and common_formation is None:
            warnings.append("formation_change_baseline_missing")

        components = {
            "official_xi_presence_index": official_xi_presence_index(coverage),
            "starter_completeness_index": starter_completeness_index(len(starters)),
            "formation_structure_index": formation_structure_index(coverage.formation),
            "xi_continuity_index": xi_continuity_index(overlap_count),
            "formation_change_index": formation_change_index(
                coverage.formation,
                prev_formation,
                common_formation,
            ),
            "offensive_starter_count_index": offensive_idx,
            "bench_availability_index": bench_idx,
        }
        macro_index = compute_lineup_macro_index(components)

        partial_warnings = {
            "no_previous_xi_for_continuity",
            "formation_change_baseline_missing",
            "bench_missing",
            "offensive_roles_missing",
        }
        if warnings and all(w in partial_warnings for w in warnings):
            status = "partial_low_sample"
        elif len(starters) < 11 or coverage.starters_count < 11:
            status = "partial_low_sample"
            if "historical_lineup_macro_partial" not in warnings:
                warnings.append("historical_lineup_macro_partial")
        else:
            status = "available"

        return TeamLineupMacroPointInTime(
            status=status,
            lineup_macro_index=macro_index,
            formation=coverage.formation,
            starters_count=len(starters),
            bench_count=len(bench),
            previous_xi_overlap_count=overlap_count,
            previous_xi_overlap_pct=overlap_pct,
            formation_changed_vs_previous=formation_changed_vs_previous,
            formation_changed_vs_common=formation_changed_vs_common,
            components={k: round(float(v), 4) for k, v in components.items()},
            warnings=warnings,
            fallback_variables=[],
            source_fixture_id=int(snapshot.fixture_id),
        )
