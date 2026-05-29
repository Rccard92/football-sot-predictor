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
from app.models import Competition, Fixture, Team, TrackedBettingPick
from app.models.tracked_betting_pick import (
    PICK_TYPE_CAUTIOUS,
    SOURCE_AUTO_PRE_MATCH,
    SOURCE_BACKFILL_ROUND,
    SOURCE_MANUAL,
    STATUS_LIVE,
)
from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
from app.services.ingestion_service import IngestionService
from app.services.tracked_betting_pick_service import MARKET_MATCH_TOTAL
from app.services.tracked_monitoring_constants import (
    LIVE_STATUSES,
    is_live_fixture,
    sot_display_and_reason,
)
from app.services.tracked_monitoring_snapshot_resolver import (
    resolve_initial_snapshot,
    resolve_official_snapshot,
)

SOURCE_PRIORITY = (SOURCE_AUTO_PRE_MATCH, SOURCE_BACKFILL_ROUND, SOURCE_MANUAL)


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


def _official_with_stale_guard(
    pick: TrackedBettingPick,
    latest_impact: dict[str, Any] | None,
    db: Session,
    fx: Fixture,
) -> Any:
    """Se pick.predicted è stale rispetto all'ultimo after, preferisce impact after."""
    from app.services.tracked_monitoring_snapshot_resolver import (
        ResolvedSnapshot,
        _approx_eq,
        _cautious_from_totals,
        _pick_line_coherent,
        _round2,
        _totals_from_delta_dict,
    )

    snap = resolve_official_snapshot(pick, latest_impact=latest_impact, db=db, fx=fx)
    if snap.total is None or not pick.lineup_confirmed or not latest_impact:
        return snap

    _, _, after_t = _totals_from_delta_dict(latest_impact, prefix="after")
    if after_t is None:
        return snap

    if snap.source == "pick_predicted_total" and not _approx_eq(snap.total, after_t):
        oh, oa, _ = _totals_from_delta_dict(latest_impact, prefix="after")
        ps, ln = _pick_line_coherent(after_t, pick.suggested_pick, pick.line_value, oh, oa)
        if ps is None:
            ps, ln = _cautious_from_totals(oh, oa)
        return ResolvedSnapshot(
            total=_round2(after_t),
            home=oh,
            away=oa,
            suggested_pick=ps,
            line_value=ln,
            source="latest_impact_after_stale_pick_guard",
        )
    return snap


def build_dashboard_row(
    pick: TrackedBettingPick,
    fx: Fixture,
    ht: Team | None,
    at: Team | None,
    impact_snapshots: dict[str, dict[str, Any] | None] | None,
    db: Session,
) -> dict[str, Any]:
    fixture_status = (pick.fixture_status or fx.status or "").strip()
    home_name = ht.name if ht else "Casa"
    away_name = at.name if at else "Trasferta"

    first_impact = (impact_snapshots or {}).get("first")
    latest_impact = (impact_snapshots or {}).get("latest")

    official_snap = _official_with_stale_guard(pick, latest_impact, db, fx)
    initial_snap = resolve_initial_snapshot(
        pick,
        first_impact=first_impact,
        latest_impact=latest_impact,
        db=db,
        fx=fx,
        official_total_hint=official_snap.total,
    )

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
        line_value=initial_snap.line_value,
    )
    official_outcome = compute_prognosis_outcome(
        fixture_status=fixture_status,
        pick_status=pick.status,
        result_total_sot=pick.result_total_sot,
        line_value=official_snap.line_value,
    )

    def _team_payload(team: Team | None, team_id: int, fallback: str) -> dict[str, Any]:
        return {
            "id": int(team.id) if team else int(team_id),
            "name": team.name if team else fallback,
            "logo_url": team.logo_url if team else None,
        }

    return {
        "id": int(pick.id),
        "fixture_id": int(pick.fixture_id),
        "kickoff_at": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
        "home_team_name": home_name,
        "away_team_name": away_name,
        "home_team": _team_payload(ht, int(fx.home_team_id), home_name),
        "away_team": _team_payload(at, int(fx.away_team_id), away_name),
        "match_name": f"{home_name} - {away_name}",
        "initial_predicted_total_sot": initial_snap.total,
        "official_predicted_total_sot": official_snap.total,
        "initial_suggested_pick": initial_snap.suggested_pick,
        "initial_line_value": initial_snap.line_value,
        "initial_odd": pick.initial_odd,
        "official_suggested_pick": official_snap.suggested_pick,
        "official_line_value": official_snap.line_value,
        "official_odd": pick.official_odd,
        "initial_reconstruction_source": initial_snap.source,
        "official_reconstruction_source": official_snap.source,
        "initial_reconstruction_note": initial_snap.reconstruction_note,
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
        "model_id": str(pick.model_id),
        "model_version": str(pick.model_id),
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
    impact_snaps: dict[int, Any] = {}

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
        impact_snaps = LineupRefreshImpactOrchestrator.load_impact_snapshots_by_fixture_ids(
            db,
            [fid],
            model_id=str(pick.model_id),
        )
        ht = teams.get(int(fx.home_team_id))
        at = teams.get(int(fx.away_team_id))
        rows_out.append(
            build_dashboard_row(pick, fx, ht, at, impact_snaps.get(fid), db),
        )

    return {
        "status": "success",
        "season": season_year,
        "picks": rows_out,
        "count": len(rows_out),
        "summary": compute_dashboard_summary(rows_out),
    }


def list_tracked_dashboard_for_competition(
    db: Session,
    comp: Competition,
    *,
    model_version: str | None = None,
) -> dict[str, Any]:
    """Carica pick del campionato selezionato."""
    q = (
        select(TrackedBettingPick)
        .join(Fixture, Fixture.id == TrackedBettingPick.fixture_id)
        .where(Fixture.competition_id == comp.id)
        .order_by(Fixture.kickoff_at.asc(), TrackedBettingPick.id.asc())
    )
    if model_version:
        q = q.where(TrackedBettingPick.model_id == str(model_version))
    picks = list(db.scalars(q).all())
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
    result = build_dashboard_payload(
        db,
        picks,
        fixtures,
        teams,
        season_year=comp.season,
    )
    result["competition_id"] = comp.id
    result["competition_name"] = comp.name
    if model_version:
        result["model_version"] = str(model_version)
    return result


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
