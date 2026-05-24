"""Vista dashboard Monitoraggio Giocate: doppia previsione, doppia scommessa, doppio esito."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
    SCHEDULED_STATUSES,
)
from app.models import Fixture, Team, TeamSotPrediction, TrackedBettingPick
from app.models.tracked_betting_pick import (
    PICK_TYPE_CAUTIOUS,
    SOURCE_AUTO_PRE_MATCH,
    SOURCE_BACKFILL_ROUND,
    SOURCE_MANUAL,
    STATUS_LIVE,
)
from app.services.sot_betting_advice_service import build_fixture_betting_advice
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.services.ingestion_service import IngestionService
from app.services.tracked_betting_pick_service import MARKET_MATCH_TOTAL, parse_line_value_from_pick
from app.services.tracked_monitoring_constants import (
    LIVE_STATUSES,
    is_live_fixture,
    sot_display_and_reason,
)

SOURCE_PRIORITY = (SOURCE_AUTO_PRE_MATCH, SOURCE_BACKFILL_ROUND, SOURCE_MANUAL)


def _round2(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 2)


def _cautious_from_totals(home_sot: float | None, away_sot: float | None) -> tuple[str | None, float | None]:
    if home_sot is None or away_sot is None:
        return None, None
    advice = build_fixture_betting_advice(
        float(home_sot),
        float(away_sot),
        model_version=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    )
    match = advice.get("match_total") if isinstance(advice.get("match_total"), dict) else {}
    pick = match.get("cautious_pick")
    line = match.get("cautious_line")
    if pick is None:
        return None, None
    line_f = float(line) if line is not None else parse_line_value_from_pick(str(pick))
    return str(pick), line_f


def _totals_from_impact_delta(impact: dict[str, Any] | None, *, prefix: str) -> tuple[float | None, float | None, float | None]:
    if not impact:
        return None, None, None
    h = impact.get(f"{prefix}_home_sot")
    a = impact.get(f"{prefix}_away_sot")
    t = impact.get(f"{prefix}_total_sot")
    if t is None and h is not None and a is not None:
        t = round(float(h) + float(a), 2)
    return (
        _round2(float(h) if h is not None else None),
        _round2(float(a) if a is not None else None),
        _round2(float(t) if t is not None else None),
    )


def _load_v20_totals(
    db: Session,
    fixture_id: int,
    home_team_id: int,
    away_team_id: int,
) -> tuple[float | None, float | None, float | None]:
    mv = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    home_row = db.scalar(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id == int(fixture_id),
            TeamSotPrediction.team_id == int(home_team_id),
            TeamSotPrediction.model_version == mv,
        ),
    )
    away_row = db.scalar(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id == int(fixture_id),
            TeamSotPrediction.team_id == int(away_team_id),
            TeamSotPrediction.model_version == mv,
        ),
    )
    if home_row is None or away_row is None or home_row.predicted_sot is None or away_row.predicted_sot is None:
        return None, None, None
    h = round(float(home_row.predicted_sot), 2)
    a = round(float(away_row.predicted_sot), 2)
    return h, a, round(h + a, 2)


def format_fixture_status_label(fixture_status: str | None, elapsed: int | None) -> str:
    fs = (fixture_status or "").strip().upper()
    if fs in ("", "NS", "TBD", "PST", "SCHEDULED"):
        return "NS"
    if fs == "HT":
        return "HT"
    if fs in LIVE_STATUSES and fs != "HT":
        if elapsed is not None:
            return f"LIVE {int(elapsed)}'"
        return "LIVE"
    if fs in FINISHED_STATUSES:
        if elapsed is not None:
            return f"FT {int(elapsed)}'"
        return "FT 90'"
    return fs or "NS"


def compute_prognosis_outcome(
    *,
    fixture_status: str | None,
    pick_status: str,
    result_total_sot: float | None,
    line_value: float | None,
) -> str:
    if line_value is None:
        return "N/D"
    fs = (fixture_status or "").strip().upper()
    if result_total_sot is None:
        if fs in FINISHED_STATUSES:
            return "N/D"
        if fs in SCHEDULED_STATUSES or fs in ("", "NS", "TBD", "PST"):
            return "In attesa"
        if fs in LIVE_STATUSES or pick_status == STATUS_LIVE:
            return "Live"
        return "In attesa"

    if fs in SCHEDULED_STATUSES or fs in ("", "NS", "TBD", "PST"):
        return "In attesa"

    beaten = float(result_total_sot) > float(line_value)
    is_finished = fs in FINISHED_STATUSES
    is_live = fs in LIVE_STATUSES or pick_status == STATUS_LIVE or fs == "HT"

    if is_finished:
        return "Vinta" if beaten else "Persa"
    if is_live:
        return "Vinta live" if beaten else "Live"
    return "In attesa"


def select_dashboard_pick(picks: list[TrackedBettingPick]) -> TrackedBettingPick | None:
    cautious = [
        p
        for p in picks
        if p.pick_type == PICK_TYPE_CAUTIOUS and p.market_id == MARKET_MATCH_TOTAL and p.status != "void"
    ]
    if not cautious:
        return None
    for src in SOURCE_PRIORITY:
        for p in cautious:
            if p.source == src:
                return p
    return cautious[0]


def _resolve_initial(
    pick: TrackedBettingPick,
    impact: dict[str, Any] | None,
    db: Session,
    fx: Fixture,
) -> tuple[float | None, str | None, float | None]:
    if pick.initial_predicted_total_sot is not None:
        total = _round2(pick.initial_predicted_total_sot)
        pick_s = pick.initial_suggested_pick
        line = pick.initial_line_value
        if pick_s is None and total is not None:
            h = pick.initial_predicted_home_sot
            a = pick.initial_predicted_away_sot
            pick_s, line = _cautious_from_totals(h, a)
        return total, pick_s, line

    ih, ia, it = _totals_from_impact_delta(impact, prefix="before")
    if it is not None:
        pick_s, line = _cautious_from_totals(ih, ia)
        if pick.initial_suggested_pick:
            pick_s = pick.initial_suggested_pick
            line = pick.initial_line_value or line
        return it, pick_s, line

    ih, ia, it = _load_v20_totals(db, int(fx.id), int(fx.home_team_id), int(fx.away_team_id))
    if it is not None:
        pick_s, line = _cautious_from_totals(ih, ia)
        return it, pick_s, line

    total = _round2(pick.predicted_total_sot)
    pick_s = pick.suggested_pick
    line = pick.line_value
    return total, pick_s, line


def _resolve_official(
    pick: TrackedBettingPick,
    impact: dict[str, Any] | None,
) -> tuple[float | None, str | None, float | None]:
    total = _round2(pick.predicted_total_sot)
    pick_s = pick.suggested_pick
    line = pick.line_value

    if total is not None:
        if pick_s is None:
            pick_s, line = _cautious_from_totals(pick.predicted_home_sot, pick.predicted_away_sot)
        return total, pick_s, line

    oh, oa, ot = _totals_from_impact_delta(impact, prefix="after")
    if ot is not None:
        if pick_s is None:
            pick_s, line = _cautious_from_totals(oh, oa)
        return ot, pick_s, line

    return None, pick_s, line


def build_dashboard_row(
    pick: TrackedBettingPick,
    fx: Fixture,
    ht: Team | None,
    at: Team | None,
    impact: dict[str, Any] | None,
    db: Session,
) -> dict[str, Any]:
    fixture_status = (pick.fixture_status or fx.status or "").strip()
    home_name = ht.name if ht else "Casa"
    away_name = at.name if at else "Trasferta"

    initial_total, initial_pick, initial_line = _resolve_initial(pick, impact, db, fx)
    official_total, official_pick, official_line = _resolve_official(pick, impact)

    sot_display, sot_unavailable_reason = sot_display_and_reason(
        fixture_status=fixture_status,
        pick_status=pick.status,
        result_home_sot=pick.result_home_sot,
        result_away_sot=pick.result_away_sot,
        result_total_sot=pick.result_total_sot,
    )
    is_live = is_live_fixture(pick.status, fixture_status)

    initial_outcome = compute_prognosis_outcome(
        fixture_status=fixture_status,
        pick_status=pick.status,
        result_total_sot=pick.result_total_sot,
        line_value=initial_line,
    )
    official_outcome = compute_prognosis_outcome(
        fixture_status=fixture_status,
        pick_status=pick.status,
        result_total_sot=pick.result_total_sot,
        line_value=official_line,
    )

    return {
        "id": int(pick.id),
        "fixture_id": int(pick.fixture_id),
        "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
        "home_team_name": home_name,
        "away_team_name": away_name,
        "match_name": f"{home_name} - {away_name}",
        "initial_predicted_total_sot": initial_total,
        "official_predicted_total_sot": official_total,
        "initial_suggested_pick": initial_pick,
        "initial_line_value": initial_line,
        "initial_odd": pick.initial_odd,
        "official_suggested_pick": official_pick,
        "official_line_value": official_line,
        "official_odd": pick.official_odd,
        "result_home_sot": pick.result_home_sot,
        "result_away_sot": pick.result_away_sot,
        "result_total_sot": pick.result_total_sot,
        "sot_display": sot_display,
        "sot_unavailable_reason": sot_unavailable_reason,
        "fixture_status": fixture_status,
        "elapsed": pick.elapsed,
        "fixture_status_label": format_fixture_status_label(fixture_status, pick.elapsed),
        "initial_outcome": initial_outcome,
        "official_outcome": official_outcome,
        "is_live_fixture": is_live,
        "status": pick.status,
    }


def compute_dashboard_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    live = sum(1 for r in rows if r.get("is_live_fixture"))
    initial_won = initial_lost = official_won = official_lost = 0
    for r in rows:
        io = r.get("initial_outcome")
        oo = r.get("official_outcome")
        if io == "Vinta":
            initial_won += 1
        elif io == "Persa":
            initial_lost += 1
        if oo == "Vinta":
            official_won += 1
        elif oo == "Persa":
            official_lost += 1
    initial_concluded = initial_won + initial_lost
    official_concluded = official_won + official_lost
    return {
        "total": total,
        "live": live,
        "initial_won": initial_won,
        "initial_lost": initial_lost,
        "official_won": official_won,
        "official_lost": official_lost,
        "initial_win_rate": round(initial_won / initial_concluded, 4) if initial_concluded > 0 else None,
        "official_win_rate": round(official_won / official_concluded, 4) if official_concluded > 0 else None,
    }


def build_dashboard_payload(
    db: Session,
    picks: list[TrackedBettingPick],
    fixtures: dict[int, Fixture],
    teams: dict[int, Team],
    *,
    season_year: int,
) -> dict[str, Any]:
    by_fixture: dict[int, list[TrackedBettingPick]] = {}
    for p in picks:
        by_fixture.setdefault(int(p.fixture_id), []).append(p)

    fx_ids = list(by_fixture.keys())
    impacts = LineupRefreshImpactOrchestrator.load_latest_impact_by_fixture_ids(
        db,
        fx_ids,
        model_id=BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    )

    rows_out: list[dict[str, Any]] = []
    for fid in sorted(
        fx_ids,
        key=lambda x: (
            fixtures[x].kickoff_at.isoformat() if fixtures.get(x) and fixtures[x].kickoff_at else "",
            x,
        ),
    ):
        fx = fixtures.get(fid)
        if fx is None:
            continue
        pick = select_dashboard_pick(by_fixture[fid])
        if pick is None:
            continue
        ht = teams.get(int(fx.home_team_id))
        at = teams.get(int(fx.away_team_id))
        rows_out.append(
            build_dashboard_row(pick, fx, ht, at, impacts.get(fid), db),
        )

    return {
        "status": "success",
        "season": season_year,
        "picks": rows_out,
        "count": len(rows_out),
        "summary": compute_dashboard_summary(rows_out),
    }


def list_tracked_dashboard_payload(db: Session, season_year: int) -> dict[str, Any]:
    """Carica pick della stagione e costruisce payload dashboard (nessuna dipendenza da refresh service)."""
    ingest = IngestionService()
    season_row = ingest._serie_a_season_row(db, season_year)  # noqa: SLF001
    picks = list(
        db.scalars(
            select(TrackedBettingPick)
            .join(Fixture, Fixture.id == TrackedBettingPick.fixture_id)
            .where(Fixture.season_id == season_row.id)
            .order_by(Fixture.kickoff_at.asc(), TrackedBettingPick.id.asc()),
        ).all(),
    )
    fx_ids = list({int(p.fixture_id) for p in picks})
    fixtures = (
        {int(f.id): f for f in db.scalars(select(Fixture).where(Fixture.id.in_(fx_ids))).all()}
        if fx_ids
        else {}
    )
    team_ids: set[int] = set()
    for f in fixtures.values():
        team_ids.add(int(f.home_team_id))
        team_ids.add(int(f.away_team_id))
    teams = (
        {int(t.id): t for t in db.scalars(select(Team).where(Team.id.in_(list(team_ids)))).all()}
        if team_ids
        else {}
    )
    return build_dashboard_payload(
        db,
        picks,
        fixtures,
        teams,
        season_year=season_year,
    )
