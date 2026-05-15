"""
Correzione xG additiva esplicita per baseline_v1_0_sot (expected_goals da fixture_team_stats).
Solo partite concluse prima del cutoff (no data leakage).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat
from app.services.sot_feature_math import fixture_key_before

MIN_XG_MATCHES = 5

XG_SENSITIVITY = 0.10
XG_ATTACK_SHARE = 0.60
XG_OPP_SHARE = 0.40
XG_ADJ_CAP = 0.08

FALLBACK_REASON_IT = "expected_goals non disponibile o sample insufficiente"
FORMULA_DESC_ADDITIVE = (
    "expected_sot = base_explicit_sot + (base_explicit_sot * clamp("
    "(((team_avg_xg_for-league_avg_xg_for)/league_avg_xg_for)*0.60 + "
    "((opponent_avg_xg_conceded-league_avg_xg_conceded)/league_avg_xg_conceded)*0.40) * 0.10, -0.08, 0.08))"
)


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _prior_completed_fixtures_for_team(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    team_id: int,
) -> list[Fixture]:
    q = (
        select(Fixture)
        .where(
            Fixture.season_id == season_id,
            Fixture.status.in_(FINISHED_STATUSES),
            (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
        )
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
    )
    xs = db.scalars(q).all()
    return [f for f in xs if fixture_key_before(f.kickoff_at, f.id, cutoff_kickoff, cutoff_fixture_id)]


def _team_stats_map(db: Session, fixture_ids: list[int]) -> dict[tuple[int, int], FixtureTeamStat]:
    if not fixture_ids:
        return {}
    rows = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids))).all()
    return {(int(r.fixture_id), int(r.team_id)): r for r in rows}


def _league_fixtures_before(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> list[Fixture]:
    q = (
        select(Fixture)
        .where(
            Fixture.season_id == season_id,
            Fixture.status.in_(FINISHED_STATUSES),
        )
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
    )
    xs = db.scalars(q).all()
    return [f for f in xs if fixture_key_before(f.kickoff_at, f.id, cutoff_kickoff, cutoff_fixture_id)]


def _collect_xg_samples(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    team_id: int,
    opponent_id: int,
) -> tuple[list[float], list[float], list[float], list[float], int]:
    priors_team = _prior_completed_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(team_id),
    )
    priors_opp = _prior_completed_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(opponent_id),
    )
    league_fx = _league_fixtures_before(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
    )
    all_ids = list({int(f.id) for f in priors_team} | {int(f.id) for f in priors_opp} | {int(f.id) for f in league_fx})
    stats_map = _team_stats_map(db, all_ids)

    team_xg: list[float] = []
    for f in priors_team:
        st = stats_map.get((int(f.id), int(team_id)))
        if st is not None and st.expected_goals is not None:
            team_xg.append(float(st.expected_goals))

    opp_conc: list[float] = []
    for f in priors_opp:
        oid = int(opponent_id)
        other = int(f.away_team_id) if int(f.home_team_id) == oid else int(f.home_team_id)
        st_att = stats_map.get((int(f.id), int(other)))
        if st_att is not None and st_att.expected_goals is not None:
            opp_conc.append(float(st_att.expected_goals))

    league_for_vals: list[float] = []
    league_conc_vals: list[float] = []
    for f in league_fx:
        sh = stats_map.get((int(f.id), int(f.home_team_id)))
        sa = stats_map.get((int(f.id), int(f.away_team_id)))
        if sh is not None and sh.expected_goals is not None:
            league_for_vals.append(float(sh.expected_goals))
            if sa is not None and sa.expected_goals is not None:
                league_conc_vals.append(float(sa.expected_goals))
        if sa is not None and sa.expected_goals is not None:
            league_for_vals.append(float(sa.expected_goals))
            if sh is not None and sh.expected_goals is not None:
                league_conc_vals.append(float(sh.expected_goals))

    return team_xg, opp_conc, league_for_vals, league_conc_vals, len(league_for_vals)


def compute_xg_adjustment_for_side(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    team_id: int,
    opponent_id: int,
    base_explicit_sot: float,
) -> tuple[dict[str, Any], float]:
    """
    Ritorna (xg_component, xg_adjustment_sot).
    Se fallback: xg_adjustment_sot = 0.0 senza eccezioni.
    """
    team_xg, opp_conc, league_for_vals, league_conc_vals, league_sample = _collect_xg_samples(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
    )

    sample_team = len(team_xg)
    sample_opp = len(opp_conc)

    team_avg = sum(team_xg) / len(team_xg) if team_xg else None
    opp_conc_avg = sum(opp_conc) / len(opp_conc) if opp_conc else None
    league_avg_for = sum(league_for_vals) / len(league_for_vals) if league_for_vals else None
    league_avg_conc = sum(league_conc_vals) / len(league_conc_vals) if league_conc_vals else None

    base_common = {
        "key": "expected_goals",
        "label": "xG / Expected goals",
        "source": "fixtures/statistics::expected_goals",
        "team_avg_xg_for": _round2(team_avg),
        "opponent_avg_xg_conceded": _round2(opp_conc_avg),
        "league_avg_xg_for": _round2(league_avg_for),
        "league_avg_xg_conceded": _round2(league_avg_conc),
        "team_xg_sample_matches": int(sample_team),
        "opponent_xg_conceded_sample_matches": int(sample_opp),
        "league_xg_sample_matches": int(league_sample),
        "xg_sensitivity": XG_SENSITIVITY,
    }

    xg_available = bool(
        team_avg is not None
        and opp_conc_avg is not None
        and league_avg_for is not None
        and league_avg_conc is not None
        and float(league_avg_for) > 0
        and float(league_avg_conc) > 0
        and sample_team >= MIN_XG_MATCHES
        and sample_opp >= MIN_XG_MATCHES
        and league_sample > 0
    )

    if not xg_available:
        comp = {
            **base_common,
            "attack_xg_delta": None,
            "opponent_xg_delta": None,
            "combined_xg_delta": None,
            "xg_adjustment_pct": 0.0,
            "xg_adjustment_sot": 0.0,
            "xg_available": False,
            "xg_adjustment_applied": False,
            "fallback_used": True,
            "fallback_reason": FALLBACK_REASON_IT,
            "cap_applied": False,
            "formula": FORMULA_DESC_ADDITIVE,
        }
        return comp, 0.0

    assert team_avg is not None and opp_conc_avg is not None and league_avg_for is not None and league_avg_conc is not None

    attack_xg_delta = (float(team_avg) - float(league_avg_for)) / float(league_avg_for)
    opponent_xg_delta = (float(opp_conc_avg) - float(league_avg_conc)) / float(league_avg_conc)
    combined_xg_delta = attack_xg_delta * XG_ATTACK_SHARE + opponent_xg_delta * XG_OPP_SHARE
    raw_adj_pct = combined_xg_delta * XG_SENSITIVITY
    xg_adjustment_pct = _clamp(raw_adj_pct, -XG_ADJ_CAP, XG_ADJ_CAP)
    cap_applied = abs(float(raw_adj_pct)) > float(XG_ADJ_CAP) + 1e-12
    xg_adjustment_sot = round(float(base_explicit_sot) * float(xg_adjustment_pct), 2)

    comp = {
        **base_common,
        "attack_xg_delta": round(float(attack_xg_delta), 6),
        "opponent_xg_delta": round(float(opponent_xg_delta), 6),
        "combined_xg_delta": round(float(combined_xg_delta), 6),
        "xg_adjustment_pct": round(float(xg_adjustment_pct), 6),
        "xg_adjustment_sot": float(xg_adjustment_sot),
        "xg_available": True,
        "xg_adjustment_applied": True,
        "fallback_used": False,
        "fallback_reason": None,
        "cap_applied": bool(cap_applied),
        "formula": FORMULA_DESC_ADDITIVE,
    }
    return comp, float(xg_adjustment_sot)


__all__ = [
    "MIN_XG_MATCHES",
    "XG_SENSITIVITY",
    "compute_xg_adjustment_for_side",
    "FALLBACK_REASON_IT",
]
