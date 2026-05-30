"""Diagnostica copertura xG nel feed importato (senza proxy)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, FixtureTeamStat, Team
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat

XG_MISSING_WARNING = "xG non disponibile nel feed importato."


def competition_has_xg_in_team_stats(db: Session, competition_id: int) -> bool:
    """True se almeno una riga fixture_team_stats ha xG valorizzato per il campionato."""
    row = db.scalars(
        select(FixtureTeamStat)
        .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
        .where(Fixture.competition_id == int(competition_id))
        .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
        .limit(200),
    ).all()
    for st in row:
        xg, _ = expected_goals_from_team_stat(st)
        if xg is not None:
            return True
    return False


def xg_coverage_summary(db: Session, competition_id: int) -> dict[str, object]:
    total = int(
        db.scalar(
            select(func.count())
            .select_from(FixtureTeamStat)
            .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
            .where(Fixture.competition_id == int(competition_id)),
        )
        or 0,
    )
    if total == 0:
        return {"xg_feed_available": False, "xg_rows_with_value": 0, "xg_rows_total": 0, "xg_coverage_pct": 0.0}

    sample = db.scalars(
        select(FixtureTeamStat)
        .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
        .where(Fixture.competition_id == int(competition_id))
        .limit(2000),
    ).all()
    with_xg = sum(1 for st in sample if expected_goals_from_team_stat(st)[0] is not None)
    pct = round(100.0 * with_xg / max(len(sample), 1), 1)
    return {
        "xg_feed_available": with_xg > 0,
        "xg_rows_with_value": with_xg,
        "xg_rows_total": len(sample),
        "xg_coverage_pct": pct,
    }


def xg_coverage_detailed_report(db: Session, competition_id: int, *, sample_limit: int = 10) -> dict[str, Any]:
    """Report split colonna DB vs raw_json vs lettura effettiva (expected_goals_from_team_stat)."""
    comp = db.get(Competition, int(competition_id))
    rows = db.scalars(
        select(FixtureTeamStat)
        .join(Fixture, Fixture.id == FixtureTeamStat.fixture_id)
        .where(Fixture.competition_id == int(competition_id))
        .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
        .limit(2000),
    ).all()

    total = len(rows)
    column_only = 0
    raw_only = 0
    effective = 0
    sample_effective: list[dict[str, Any]] = []
    sample_raw_only: list[dict[str, Any]] = []

    for st in rows:
        col_val = getattr(st, "expected_goals", None)
        xg_eff, src = expected_goals_from_team_stat(st)
        has_col = col_val is not None
        has_eff = xg_eff is not None
        if has_col:
            column_only += 1
        if has_eff:
            effective += 1
            if not has_col:
                raw_only += 1

    for st in rows:
        if len(sample_effective) >= sample_limit:
            break
        xg_eff, src = expected_goals_from_team_stat(st)
        if xg_eff is None:
            continue
        fx = db.get(Fixture, int(st.fixture_id))
        team = db.get(Team, int(st.team_id))
        sample_effective.append(
            {
                "fixture_id": int(st.fixture_id),
                "team_name": team.name if team else str(st.team_id),
                "side": st.side,
                "expected_goals_column": float(st.expected_goals) if st.expected_goals is not None else None,
                "expected_goals_effective": round(float(xg_eff), 4),
                "source_path": src,
                "kickoff_at": fx.kickoff_at.isoformat() if fx and fx.kickoff_at else None,
            },
        )

    for st in rows:
        if len(sample_raw_only) >= sample_limit:
            break
        if st.expected_goals is not None:
            continue
        xg_eff, src = expected_goals_from_team_stat(st)
        if xg_eff is None:
            continue
        fx = db.get(Fixture, int(st.fixture_id))
        team = db.get(Team, int(st.team_id))
        sample_raw_only.append(
            {
                "fixture_id": int(st.fixture_id),
                "team_name": team.name if team else str(st.team_id),
                "expected_goals_effective": round(float(xg_eff), 4),
                "source_path": src,
            },
        )

    feed_available = effective > 0
    verdict = "real_api_feed" if feed_available else "feed_unavailable"
    if feed_available and raw_only > 0:
        verdict = "real_api_feed_raw_json_only_partial"

    league_baseline_xg_for: float | None = None
    if effective > 0:
        vals = []
        for st in rows:
            xg_eff, _ = expected_goals_from_team_stat(st)
            if xg_eff is not None:
                vals.append(float(xg_eff))
        if vals:
            league_baseline_xg_for = round(sum(vals) / len(vals), 4)

    return {
        "competition_id": int(competition_id),
        "competition_label": comp.name if comp else None,
        "rows_total_sampled": total,
        "rows_with_column_expected_goals": column_only,
        "rows_with_effective_xg": effective,
        "rows_xg_raw_json_only": raw_only,
        "column_coverage_pct": round(100.0 * column_only / max(total, 1), 2),
        "effective_coverage_pct": round(100.0 * effective / max(total, 1), 2),
        "raw_json_only_pct": round(100.0 * raw_only / max(total, 1), 2),
        "xg_feed_available": feed_available,
        "league_baseline_xg_for": league_baseline_xg_for,
        "sample_avg_xg_for": league_baseline_xg_for,
        "verdict": verdict,
        "verdict_note": (
            "xG reali da API-Football (fixtures/statistics) — colonna e/o raw_json"
            if feed_available
            else "Nessun xG nel feed importato per questa competizione — usare feed_unavailable, non proxy"
        ),
        "sample_effective": sample_effective,
        "sample_raw_json_only": sample_raw_only,
    }


def resolve_league_xg_available(
    db: Session,
    *,
    competition_id: int | None,
    league_baselines: dict[str, float | None],
    team_agg: dict[str, Any],
    opp_conceded_agg: dict[str, Any],
) -> bool:
    """True se xG reali sono disponibili (baseline, aggregati squadra o feed competizione)."""
    if league_baselines.get("league_avg_xg_for") is not None:
        return True
    if int(team_agg.get("xg_n") or 0) > 0 or int(opp_conceded_agg.get("xg_n") or 0) > 0:
        return True
    if competition_id is not None:
        return competition_has_xg_in_team_stats(db, int(competition_id))
    return False
