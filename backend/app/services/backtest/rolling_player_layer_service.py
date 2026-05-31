"""Rolling player layer point-in-time da XI ufficiale storico (Step G2B)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.backtest_historical_fixture_snapshot import HistoricalFixtureSideSnapshot
from app.schemas.backtest_historical_lineup_audit import HistoricalLineupPlayerPriorStats
from app.schemas.backtest_point_in_time import TeamPlayerLayerPointInTime
from app.services.backtest.historical_fixture_snapshot_service import (
    side_bench_raw,
    side_starters_raw,
)
from app.services.backtest.pit_player_rolling_stats import (
    build_mapping_summary,
    build_player_prior_stats,
    round4,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _role_weight(position: str | None) -> float:
    if not position:
        return 0.75
    pos = position.upper().strip()
    if pos in ("F", "A", "ATT", "FW", "ST", "CF", "LW", "RW"):
        return 1.00
    if pos in ("M", "C", "MID", "CM", "DM", "AM", "LM", "RM"):
        return 0.75
    if pos in ("D", "CB", "LB", "RB", "WB", "LWB", "RWB", "DF"):
        return 0.35
    if pos in ("G", "GK"):
        return 0.00
    if pos.startswith("F") or pos.startswith("A"):
        return 1.00
    if pos.startswith("M") or pos.startswith("C"):
        return 0.75
    if pos.startswith("D"):
        return 0.35
    if pos.startswith("G"):
        return 0.00
    return 0.75


def _norm(x: float | None, baseline: float) -> float:
    if x is None or baseline <= 0:
        return 1.0
    return _clamp(x / baseline, 0.5, 2.0)


def _player_attack_score(
    prior_sot_per90: float | None,
    prior_shots_per90: float | None,
    prior_team_sot_share: float | None,
    baseline: float,
) -> float:
    sot_norm = _norm(prior_sot_per90, baseline)
    shots_norm = _norm(prior_shots_per90, baseline)
    share_norm = _clamp((prior_team_sot_share or 0.0) * 2.0, 0.5, 2.0) if prior_team_sot_share is not None else 1.0
    return 0.50 * sot_norm + 0.25 * shots_norm + 0.25 * share_norm


def _has_leakage(player: HistoricalLineupPlayerPriorStats, cutoff: datetime) -> bool:
    latest = player.latest_player_stat_fixture_used_at
    return latest is not None and latest >= cutoff


def _eligible_prior(player: HistoricalLineupPlayerPriorStats, cutoff: datetime) -> bool:
    if _has_leakage(player, cutoff):
        return False
    return player.prior_matches_count > 0 and player.prior_sot_per90 is not None


def _top_shooter_eligible(player: HistoricalLineupPlayerPriorStats, cutoff: datetime) -> bool:
    if _has_leakage(player, cutoff):
        return False
    return player.prior_minutes >= 270 or player.prior_matches_count >= 3


class RollingPlayerLayerService:
    def build_team_player_layer(
        self,
        db: Session,
        *,
        competition_id: int,
        team_id: int,
        cutoff_time: datetime,
        side_snapshot: HistoricalFixtureSideSnapshot,
        league_avg_sot_for: float | None = None,
    ) -> TeamPlayerLayerPointInTime:
        coverage = side_snapshot.coverage
        starters_raw = side_starters_raw(side_snapshot)
        bench_raw = side_bench_raw(side_snapshot)

        if side_snapshot.status == "missing" or not coverage.has_official_xi or not starters_raw:
            return self._neutral_fallback(["no_official_xi"])

        starters = [
            build_player_prior_stats(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff_time,
            )
            for r in starters_raw
        ]
        bench = [
            build_player_prior_stats(
                db,
                row=r,
                competition_id=int(competition_id),
                team_id=int(team_id),
                cutoff=cutoff_time,
            )
            for r in bench_raw
        ]

        mapping = build_mapping_summary(starters, bench, [])
        warnings: list[str] = list(coverage.warnings)
        for p in starters + bench:
            warnings.extend(p.warnings)
        warnings = list(dict.fromkeys(warnings))

        critical_leakage = any(_has_leakage(p, cutoff_time) for p in starters + bench)
        if critical_leakage:
            return TeamPlayerLayerPointInTime(
                status="neutral_fallback",
                formation=coverage.formation,
                starters_count=len(starters),
                bench_count=len(bench),
                mapping_coverage_pct=mapping.mapping_coverage_pct,
                prior_stats_coverage_pct=mapping.player_stats_prior_coverage_pct,
                offensive_xi_strength_index=1.0,
                top_shooter_presence_index=1.0,
                replacement_depth_index=1.0,
                player_layer_index=1.0,
                top_starters=[],
                warnings=list(dict.fromkeys(warnings + ["possible_player_stats_leakage"])),
            )

        eligible_starters = [p for p in starters if _eligible_prior(p, cutoff_time)]
        eligible_bench = [p for p in bench if _eligible_prior(p, cutoff_time)]

        sot_values = [
            float(p.prior_sot_per90)
            for p in eligible_starters + eligible_bench
            if p.prior_sot_per90 is not None
        ]
        baseline = round(sum(sot_values) / len(sot_values), 4) if sot_values else None
        if baseline is None and league_avg_sot_for is not None:
            baseline = float(league_avg_sot_for)
        if baseline is None:
            warnings.append("player_layer_baseline_missing")
            baseline = 1.0

        starter_scores: list[tuple[HistoricalLineupPlayerPriorStats, float, float]] = []
        for p in eligible_starters:
            rw = _role_weight(p.role)
            attack = _player_attack_score(
                p.prior_sot_per90,
                p.prior_shots_per90,
                p.prior_team_sot_share,
                baseline,
            )
            weighted = attack * rw
            starter_scores.append((p, attack, weighted))

        expected_baseline = sum(_role_weight(p.role) for p in eligible_starters) or 1.0
        offensive_sum = sum(w for _, _, w in starter_scores)
        if not starter_scores or (baseline == 1.0 and "player_layer_baseline_missing" in warnings):
            offensive_xi = 1.0
        else:
            offensive_xi = _clamp(offensive_sum / expected_baseline, 0.70, 1.30)

        top_shooter_index, top_shooter_warnings = self._compute_top_shooter_presence(
            starters=starters,
            bench=bench,
            cutoff=cutoff_time,
        )
        warnings.extend(top_shooter_warnings)

        replacement_depth, bench_warnings = self._compute_replacement_depth(
            bench=eligible_bench,
            baseline=baseline,
        )
        warnings.extend(bench_warnings)

        player_layer_index = _clamp(
            0.55 * offensive_xi + 0.30 * top_shooter_index + 0.15 * replacement_depth,
            0.70,
            1.30,
        )

        top_starters = self._build_top_starters(starter_scores)
        status = self._resolve_status(
            starters_count=len(starters),
            mapping_pct=mapping.mapping_coverage_pct,
            prior_pct=mapping.player_stats_prior_coverage_pct,
            has_leakage=False,
        )

        if status == "partial_low_sample":
            warnings.append("player_layer_partial_low_sample")

        return TeamPlayerLayerPointInTime(
            status=status,
            formation=coverage.formation,
            starters_count=len(starters),
            bench_count=len(bench),
            mapping_coverage_pct=mapping.mapping_coverage_pct,
            prior_stats_coverage_pct=mapping.player_stats_prior_coverage_pct,
            offensive_xi_strength_index=round4(offensive_xi) or 1.0,
            top_shooter_presence_index=round4(top_shooter_index) or 1.0,
            replacement_depth_index=round4(replacement_depth) or 1.0,
            player_layer_index=round4(player_layer_index) or 1.0,
            top_starters=top_starters,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _neutral_fallback(self, extra_warnings: list[str]) -> TeamPlayerLayerPointInTime:
        return TeamPlayerLayerPointInTime(
            status="neutral_fallback",
            formation=None,
            starters_count=0,
            bench_count=0,
            mapping_coverage_pct=None,
            prior_stats_coverage_pct=None,
            offensive_xi_strength_index=1.0,
            top_shooter_presence_index=1.0,
            replacement_depth_index=1.0,
            player_layer_index=1.0,
            top_starters=[],
            warnings=extra_warnings,
        )

    def _compute_top_shooter_presence(
        self,
        *,
        starters: list[HistoricalLineupPlayerPriorStats],
        bench: list[HistoricalLineupPlayerPriorStats],
        cutoff: datetime,
    ) -> tuple[float, list[str]]:
        warnings: list[str] = []
        candidates = [
            p
            for p in starters + bench
            if _top_shooter_eligible(p, cutoff) and p.prior_team_sot_share is not None
        ]
        if len(candidates) < 3:
            return 1.0, warnings

        ranked = sorted(
            candidates,
            key=lambda p: float(p.prior_team_sot_share or 0.0),
            reverse=True,
        )[:3]
        starter_names = {p.player_name for p in starters}
        bench_names = {p.player_name for p in bench}

        in_xi = sum(1 for p in ranked if p.player_name in starter_names)
        on_bench = sum(1 for p in ranked if p.player_name in bench_names and p.player_name not in starter_names)
        out_xi = 3 - in_xi - on_bench

        if in_xi == 3:
            index = 1.10
        elif on_bench == 1 and out_xi == 0:
            index = 0.95
            warnings.append("top_shooter_only_bench")
        elif out_xi >= 1:
            share_missing = sum(
                float(p.prior_team_sot_share or 0.0) for p in ranked if p.player_name not in starter_names
            )
            total_share = sum(float(p.prior_team_sot_share or 0.0) for p in ranked) or 1.0
            scale = share_missing / total_share if total_share > 0 else 1.0 / 3.0
            index = 0.85 + (1.0 - scale) * 0.15
            warnings.append("top_shooter_missing_from_xi")
        else:
            index = 1.0

        return _clamp(index, 0.70, 1.20), warnings

    def _compute_replacement_depth(
        self,
        *,
        bench: list[HistoricalLineupPlayerPriorStats],
        baseline: float,
    ) -> tuple[float, list[str]]:
        warnings: list[str] = []
        if not bench:
            warnings.append("bench_missing")
            return 1.0, warnings

        scores: list[float] = []
        for p in bench:
            rw = _role_weight(p.role)
            attack = _player_attack_score(
                p.prior_sot_per90,
                p.prior_shots_per90,
                p.prior_team_sot_share,
                baseline,
            )
            scores.append(attack * rw)

        top_bench = sorted(scores, reverse=True)[:3]
        bench_signal = sum(top_bench) / len(top_bench) if top_bench else 1.0
        index = _clamp(0.95 + 0.05 * bench_signal, 0.90, 1.10)
        return index, warnings

    def _build_top_starters(
        self,
        starter_scores: list[tuple[HistoricalLineupPlayerPriorStats, float, float]],
    ) -> list[dict[str, Any]]:
        ranked = sorted(starter_scores, key=lambda t: t[2], reverse=True)[:3]
        return [
            {
                "player_name": p.player_name,
                "role": p.role,
                "prior_sot_per90": p.prior_sot_per90,
                "prior_shots_per90": p.prior_shots_per90,
                "prior_team_sot_share": p.prior_team_sot_share,
                "contribution_score": round4(weighted),
                "attack_score": round4(attack),
            }
            for p, attack, weighted in ranked
        ]

    def _resolve_status(
        self,
        *,
        starters_count: int,
        mapping_pct: float | None,
        prior_pct: float | None,
        has_leakage: bool,
    ) -> str:
        if has_leakage or starters_count == 0:
            return "neutral_fallback"
        if (
            starters_count >= 9
            and mapping_pct is not None
            and mapping_pct >= 80.0
            and prior_pct is not None
            and prior_pct >= 80.0
        ):
            return "available"
        if starters_count >= 1 or (
            mapping_pct is not None
            and 50.0 <= mapping_pct < 80.0
        ) or (
            prior_pct is not None
            and 50.0 <= prior_pct < 80.0
        ):
            return "partial_low_sample"
        return "neutral_fallback"
