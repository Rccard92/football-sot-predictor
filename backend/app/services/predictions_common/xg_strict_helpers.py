"""Helper xG strict condiviso — replica logica v1.1 senza importare il service v1.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models import Fixture
from app.services.predictions_v11.league_baselines_strict import REQUIRED_LEAGUE_XG_KEYS
from app.services.predictions_v11.opponent_stats_agg import agg_xg_conceded_by_opponent
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.v11_shared import clamp, safe_float
from app.services.predictions_v11.xg_feature_sources import XG_INPUT_SOURCE_PATHS
from app.services.predictions_v21.v21_xg_league_features import latest_prior_kickoff
from app.services.sot_feature_registry import V11_MIN_XG_MATCHES

REQUIRED_XG_STRICT_BASELINE_KEYS: tuple[str, ...] = (
    *REQUIRED_LEAGUE_XG_KEYS,
    "league_avg_sot_for",
    "league_avg_sot_conceded",
)

V21_XG_SOURCE_PATHS: dict[str, str] = {
    "xg_produced": XG_INPUT_SOURCE_PATHS["avg_xg_for"],
    "xg_conceded_by_opponent": XG_INPUT_SOURCE_PATHS["opponent_avg_xg_conceded"],
    "xg_delta_vs_league": XG_INPUT_SOURCE_PATHS["team_xg_delta_vs_league"],
    "opp_xg_conceded_delta": XG_INPUT_SOURCE_PATHS["opponent_xg_conceded_delta_vs_league"],
    "xg_prudent_adjustment": XG_INPUT_SOURCE_PATHS["xg_prudent_adjustment_signal"],
}


def _missing_strict_baseline_keys(league_baselines: dict[str, float | None]) -> list[str]:
    miss: list[str] = []
    for k in REQUIRED_XG_STRICT_BASELINE_KEYS:
        v = league_baselines.get(k)
        if v is None or float(v) <= 0:
            miss.append(k)
    return miss


@dataclass
class StrictXgSnapshot:
    avg_xg_for: float | None = None
    opponent_avg_xg_conceded: float | None = None
    team_xg_delta_vs_league: float | None = None
    opponent_xg_conceded_delta_vs_league: float | None = None
    xg_adjustment_pct: float | None = None
    xg_prudent_signal: float | None = None
    norm_xg_produced: float | None = None
    norm_xg_conceded: float | None = None
    norm_team_delta: float | None = None
    norm_opp_delta: float | None = None
    norm_prudent: float | None = None
    team_xg_n: int = 0
    opp_xg_n: int = 0
    league_avg_xg_for: float | None = None
    league_avg_xg_conceded: float | None = None
    league_avg_sot_for: float | None = None
    league_avg_sot_conceded: float | None = None
    latest_fixture_used_at: str | None = None
    leakage_guard: bool = True
    status: str = "missing_required_xg_league_baseline"
    warnings: list[str] = field(default_factory=list)


def build_strict_xg_snapshot(
    *,
    prior_fixtures: list[Fixture],
    opponent_prior_fixtures: list[Fixture],
    stats_map: dict[Any, Any],
    team_id: int,
    opponent_id: int,
    league_baselines: dict[str, float | None],
    cutoff_kickoff: datetime | None = None,
    cutoff_fixture_id: int | None = None,
) -> StrictXgSnapshot:
    """Calcola snapshot xG strict (stessa logica numerica di xg_quality_strict v1.1)."""
    _ = cutoff_kickoff, cutoff_fixture_id  # anti-leakage già applicato sulle prior lists
    all_fx = list({id(f): f for f in prior_fixtures + opponent_prior_fixtures}.values())
    latest = latest_prior_kickoff(all_fx)
    latest_iso = latest.isoformat() if latest is not None else None

    lb_miss = _missing_strict_baseline_keys(league_baselines)
    if lb_miss:
        return StrictXgSnapshot(
            latest_fixture_used_at=latest_iso,
            leakage_guard=True,
            status="missing_required_xg_league_baseline",
            warnings=[f"Baseline xG/SOT mancanti: {', '.join(lb_miss)}"],
        )

    lxg_for = float(league_baselines["league_avg_xg_for"])  # type: ignore[arg-type]
    lxg_conc = float(league_baselines["league_avg_xg_conceded"])  # type: ignore[arg-type]
    lsot_for = float(league_baselines["league_avg_sot_for"])  # type: ignore[arg-type]
    lsot_conc = float(league_baselines["league_avg_sot_conceded"])  # type: ignore[arg-type]

    team_agg = agg_for_team(
        fixtures=prior_fixtures,
        stats_map=stats_map,
        team_id=int(team_id),
    )
    opp_agg = agg_xg_conceded_by_opponent(
        fixtures=opponent_prior_fixtures,
        stats_map=stats_map,
        opponent_id=int(opponent_id),
    )

    team_xg_n = int(team_agg.get("xg_n") or 0)
    opp_xg_n = int(opp_agg.get("xg_n") or 0)

    avg_xg_for = safe_float(team_agg.get("xg_mean"))
    opponent_avg_xg_conc = safe_float(opp_agg.get("xg_mean"))

    if avg_xg_for is None or opponent_avg_xg_conc is None:
        return StrictXgSnapshot(
            team_xg_n=team_xg_n,
            opp_xg_n=opp_xg_n,
            league_avg_xg_for=lxg_for,
            league_avg_xg_conceded=lxg_conc,
            league_avg_sot_for=lsot_for,
            league_avg_sot_conceded=lsot_conc,
            latest_fixture_used_at=latest_iso,
            leakage_guard=True,
            status="missing_required_data",
            warnings=["Dati xG squadra o avversario assenti sul campione prior"],
        )

    xg_for_scaled = float(avg_xg_for) * lsot_for / lxg_for
    opponent_xg_conceded_scaled = float(opponent_avg_xg_conc) * lsot_conc / lxg_conc

    team_delta_raw = float(avg_xg_for) - lxg_for
    opp_delta_raw = float(opponent_avg_xg_conc) - lxg_conc

    team_xg_delta_scaled = lsot_for + clamp(
        (float(avg_xg_for) - lxg_for) * lsot_for / lxg_for,
        -1.0,
        1.0,
    )
    opponent_xg_conceded_delta_scaled = lsot_conc + clamp(
        (float(opponent_avg_xg_conc) - lxg_conc) * lsot_conc / lxg_conc,
        -1.0,
        1.0,
    )

    team_xg_delta_pct = (float(avg_xg_for) - lxg_for) / lxg_for
    opponent_xg_delta_pct = (float(opponent_avg_xg_conc) - lxg_conc) / lxg_conc
    combined_xg_delta_pct = 0.60 * team_xg_delta_pct + 0.40 * opponent_xg_delta_pct
    xg_adjustment_pct = clamp(combined_xg_delta_pct * 0.10, -0.08, 0.08)
    prudent_signal = lsot_for * (1.0 + xg_adjustment_pct)

    status = "ok"
    warnings: list[str] = []
    if team_xg_n < V11_MIN_XG_MATCHES or opp_xg_n < V11_MIN_XG_MATCHES:
        status = "insufficient_xg_sample"
        warnings.append(
            f"Campione xG basso (squadra={team_xg_n}, avversario={opp_xg_n}, min={V11_MIN_XG_MATCHES})",
        )

    return StrictXgSnapshot(
        avg_xg_for=float(avg_xg_for),
        opponent_avg_xg_conceded=float(opponent_avg_xg_conc),
        team_xg_delta_vs_league=team_delta_raw,
        opponent_xg_conceded_delta_vs_league=opp_delta_raw,
        xg_adjustment_pct=float(xg_adjustment_pct),
        xg_prudent_signal=float(prudent_signal),
        norm_xg_produced=xg_for_scaled,
        norm_xg_conceded=opponent_xg_conceded_scaled,
        norm_team_delta=team_xg_delta_scaled,
        norm_opp_delta=opponent_xg_conceded_delta_scaled,
        norm_prudent=prudent_signal,
        team_xg_n=team_xg_n,
        opp_xg_n=opp_xg_n,
        league_avg_xg_for=lxg_for,
        league_avg_xg_conceded=lxg_conc,
        league_avg_sot_for=lsot_for,
        league_avg_sot_conceded=lsot_conc,
        latest_fixture_used_at=latest_iso,
        leakage_guard=True,
        status=status,
        warnings=warnings,
    )


def v21_norm_from_strict_snapshot(snap: StrictXgSnapshot, micro_key: str) -> float | None:
    """Bridge normalizzazione v1.1 SOT-scaled → ratio ~1.0 per macro moltiplicativa v2.1."""
    if micro_key == "xg_produced":
        if snap.norm_xg_produced is None or not snap.league_avg_sot_for:
            return None
        return float(snap.norm_xg_produced) / float(snap.league_avg_sot_for)
    if micro_key == "xg_conceded_by_opponent":
        if snap.norm_xg_conceded is None or not snap.league_avg_sot_conceded:
            return None
        return float(snap.norm_xg_conceded) / float(snap.league_avg_sot_conceded)
    if micro_key == "xg_delta_vs_league":
        if snap.norm_team_delta is None or not snap.league_avg_sot_for:
            return None
        return float(snap.norm_team_delta) / float(snap.league_avg_sot_for)
    if micro_key == "opp_xg_conceded_delta":
        if snap.norm_opp_delta is None or not snap.league_avg_sot_conceded:
            return None
        return float(snap.norm_opp_delta) / float(snap.league_avg_sot_conceded)
    if micro_key == "xg_prudent_adjustment":
        if snap.xg_adjustment_pct is None:
            return None
        return 1.0 + float(snap.xg_adjustment_pct)
    return None
