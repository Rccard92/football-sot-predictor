"""Report rapido Prossima giornata (leggero) e dettaglio singola fixture on-demand."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, load_only

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
)
from app.models import Competition, Fixture, FixtureLineup, Team, TeamSotPrediction
from app.services.model_version_preference import (
    preferred_model_versions,
    resolve_recommended_model_version,
)
from app.services.prediction_readiness import (
    _safe_details,
    default_model_limitations_dict,
)
from app.services.sot_feature_service import SotFeatureService
from app.services.sot_prediction_service import SotPredictionService, _fixture_round_display

logger = logging.getLogger(__name__)

_PERF_LOG = os.environ.get("SOT_PERF_LOG", "").strip().lower() in ("1", "true", "yes")


def _slim_lineup_refresh_impact(impact: dict[str, Any] | None) -> dict[str, Any]:
    if not impact:
        return {"has_comparison": False}
    keys = (
        "has_comparison",
        "direction_total",
        "delta_total_sot",
        "direction_home",
        "delta_home_sot",
        "direction_away",
        "delta_away_sot",
        "main_reason",
        "before_total_sot",
        "after_total_sot",
        "created_at",
    )
    return {k: impact.get(k) for k in keys if k in impact or k == "has_comparison"}


def _load_upcoming_fixtures(
    db: Session,
    season: int,
    *,
    limit: int,
    only_next_round: bool,
) -> tuple[Any, list[Fixture], str | None]:
    svc = SotPredictionService()
    _league, season_row = svc._season_row(db, season)  # type: ignore[attr-defined]
    feat_svc = SotFeatureService()
    raw_upcoming = feat_svc.list_upcoming_fixtures_for_season(db, season_row.id)
    upcoming = [f for f in raw_upcoming if (f.status or "").upper() not in FINISHED_STATUSES]
    upcoming.sort(key=lambda f: (f.kickoff_at, f.id))
    if only_next_round and upcoming:
        r0 = _fixture_round_display(upcoming[0]) or upcoming[0].round
        if r0:
            upcoming = [f for f in upcoming if (_fixture_round_display(f) or f.round) == r0]
        else:
            d0 = upcoming[0].kickoff_at.date()
            upcoming = [f for f in upcoming if f.kickoff_at.date() == d0]
    upcoming = upcoming[: max(1, min(limit, 100))]
    round_label = _fixture_round_display(upcoming[0]) if upcoming else None
    return season_row, upcoming, round_label


def _load_upcoming_fixtures_for_competition(
    db: Session,
    comp: Competition,
    *,
    limit: int,
    only_next_round: bool,
) -> tuple[Competition, list[Fixture], str | None]:
    raw_upcoming = list(
        db.scalars(
            select(Fixture)
            .where(Fixture.competition_id == comp.id)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        ).all()
    )
    upcoming = [f for f in raw_upcoming if (f.status or "").upper() not in FINISHED_STATUSES]
    if only_next_round and upcoming:
        r0 = _fixture_round_display(upcoming[0]) or upcoming[0].round
        if r0:
            upcoming = [f for f in upcoming if (_fixture_round_display(f) or f.round) == r0]
        else:
            d0 = upcoming[0].kickoff_at.date()
            upcoming = [f for f in upcoming if f.kickoff_at.date() == d0]
    upcoming = upcoming[: max(1, min(limit, 100))]
    round_label = _fixture_round_display(upcoming[0]) if upcoming else None
    return comp, upcoming, round_label


def build_next_round_quick_report_for_competition(
    db: Session,
    comp: Competition,
    *,
    limit: int = 20,
    only_next_round: bool = True,
    model_version: str | None = None,
) -> dict[str, Any]:
    payload, code = build_next_round_quick_report_payload(
        db,
        comp.season,
        limit=limit,
        only_next_round=only_next_round,
        model_version=model_version,
        competition_id=comp.id,
        competition_name=comp.name,
    )
    _ = code
    return payload


def _load_prediction_context(
    db: Session,
    upcoming: list[Fixture],
    requested: str,
) -> tuple[
    dict[tuple[int, int, str], TeamSotPrediction],
    str | None,
    list[str],
    Callable[[Fixture], str | None],
]:
    preferred = preferred_model_versions()
    fx_ids = [int(f.id) for f in upcoming]
    warnings: list[str] = []

    def has_any_upcoming(mv: str) -> bool:
        if not fx_ids:
            return False
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .where(
                    TeamSotPrediction.fixture_id.in_(fx_ids),
                    TeamSotPrediction.model_version == mv,
                    TeamSotPrediction.predicted_sot.isnot(None),
                ),
            )
            or 0,
        )
        return n > 0

    by_version_upcoming: dict[str, dict[str, Any]] = {}
    for mv in preferred:
        if not has_any_upcoming(mv):
            continue
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .where(
                    TeamSotPrediction.fixture_id.in_(fx_ids),
                    TeamSotPrediction.model_version == mv,
                    TeamSotPrediction.predicted_sot.isnot(None),
                ),
            )
            or 0,
        )
        by_version_upcoming[mv] = {"is_available_for_upcoming": n > 0, "upcoming_predictions": n}

    recommended = resolve_recommended_model_version(
        db,
        upcoming_fixture_ids=fx_ids,
        by_version=by_version_upcoming,
        upcoming_fixtures_total=len(upcoming),
    )
    if recommended is None:
        recommended = next((mv for mv in preferred if has_any_upcoming(mv)), BASELINE_SOT_MODEL_VERSION)

    versions_to_load = list(dict.fromkeys([requested] + preferred))
    preds = db.scalars(
        select(TeamSotPrediction)
        .options(
            load_only(
                TeamSotPrediction.fixture_id,
                TeamSotPrediction.team_id,
                TeamSotPrediction.model_version,
                TeamSotPrediction.predicted_sot,
            ),
        )
        .where(
            TeamSotPrediction.fixture_id.in_(fx_ids) if fx_ids else False,
            TeamSotPrediction.model_version.in_(versions_to_load),
        ),
    ).all()
    pred_map = {(int(p.fixture_id), int(p.team_id), str(p.model_version)): p for p in preds}

    def pick_match_version(fx: Fixture) -> str | None:
        for mv in [requested] + [x for x in preferred if x != requested]:
            ph = pred_map.get((int(fx.id), int(fx.home_team_id), mv))
            pa = pred_map.get((int(fx.id), int(fx.away_team_id), mv))
            if ph and ph.predicted_sot is not None and pa and pa.predicted_sot is not None:
                return mv
        return None

    return pred_map, recommended, warnings, pick_match_version


def build_next_round_quick_report_payload(
    db: Session,
    season: int,
    *,
    limit: int = 20,
    only_next_round: bool = True,
    model_version: str | None = None,
    competition_id: int | None = None,
    competition_name: str | None = None,
) -> tuple[dict[str, Any], int]:
    t0 = time.perf_counter()
    lineup_warning: str | None = None
    try:
        if competition_id is not None:
            comp = db.get(Competition, competition_id)
            if comp is None:
                return ({"status": "error", "message": "Competition non trovata"}, 404)
            _ctx, upcoming, round_label = _load_upcoming_fixtures_for_competition(
                db, comp, limit=limit, only_next_round=only_next_round
            )
            competition_name = competition_name or comp.name
            lineups_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(FixtureLineup)
                    .where(FixtureLineup.competition_id == comp.id)
                )
                or 0
            )
            if lineups_count == 0:
                lineup_warning = (
                    "Lineups non disponibili: prediction generate senza impatto formazioni."
                )
        else:
            _season_row, upcoming, round_label = _load_upcoming_fixtures(
                db, season, limit=limit, only_next_round=only_next_round
            )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("quick-report: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return ({"status": "error", "message": "Database error", "details": _safe_details(exc)}, 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("quick-report: errore inatteso")
        return ({"status": "error", "message": "Errore inatteso", "details": _safe_details(exc)}, 500)

    preferred = preferred_model_versions()
    requested = model_version or BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    warnings: list[str] = []
    if lineup_warning:
        warnings.append(lineup_warning)
    if model_version is not None and requested not in preferred:
        warnings.append(f"Model version richiesta non riconosciuta: {requested}.")

    pred_map, recommended, _w, pick_match_version = _load_prediction_context(db, upcoming, requested)
    warnings.extend(_w)
    mv_default = model_version or recommended or requested

    fx_ids = [int(f.id) for f in upcoming]
    team_ids = list({int(f.home_team_id) for f in upcoming} | {int(f.away_team_id) for f in upcoming})
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()} if team_ids else {}

    from app.services.sportapi.sportapi_lineup_status import (
        formation_status_from_lineup,
        load_lineups_by_fixture_ids,
    )
    from app.services.sot_betting_advice_service import (
        advice_context_from_upcoming_lineup,
        build_upcoming_report_markets,
    )
    from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator
    from app.services.tracked_betting_pick_service import TrackedBettingPickService

    lineups_by_fx = load_lineups_by_fixture_ids(db, fx_ids)
    impacts_by_fx = LineupRefreshImpactOrchestrator.load_latest_impact_by_fixture_ids(db, fx_ids)
    pick_svc = TrackedBettingPickService()
    open_by_fx = pick_svc.load_open_picks_by_fixture_ids(db, fx_ids)

    matches: list[dict[str, Any]] = []
    for fx in upcoming:
        mv_used = pick_match_version(fx) or mv_default
        ph = pred_map.get((int(fx.id), int(fx.home_team_id), mv_used))
        pa = pred_map.get((int(fx.id), int(fx.away_team_id), mv_used))
        if ph is None or pa is None or ph.predicted_sot is None or pa.predicted_sot is None:
            warnings.append(f"Fixture {int(fx.id)}: prediction incompleta.")
            continue

        home_exp = round(float(ph.predicted_sot), 2)
        away_exp = round(float(pa.predicted_sot), 2)
        total_exp = round(home_exp + away_exp, 2)

        lineup_status = formation_status_from_lineup(lineups_by_fx.get(int(fx.id)))
        advice_ctx = advice_context_from_upcoming_lineup(lineup_status)
        markets = build_upcoming_report_markets(
            home_exp,
            away_exp,
            model_version=mv_used,
            context=advice_ctx,
        )
        impact_full = impacts_by_fx.get(int(fx.id))
        impact_slim = _slim_lineup_refresh_impact(impact_full)

        open_rows = open_by_fx.get(int(fx.id)) or []
        monitored = len(open_rows) > 0

        matches.append(
            {
                "fixture_id": int(fx.id),
                "api_fixture_id": int(fx.api_fixture_id),
                "kickoff_at": fx.kickoff_at,
                "round": fx.round,
                "status_short": fx.status,
                "home_team": {
                    "id": int(fx.home_team_id),
                    "name": teams.get(int(fx.home_team_id)).name if int(fx.home_team_id) in teams else "",
                    "logo_url": teams.get(int(fx.home_team_id)).logo_url if int(fx.home_team_id) in teams else None,
                },
                "away_team": {
                    "id": int(fx.away_team_id),
                    "name": teams.get(int(fx.away_team_id)).name if int(fx.away_team_id) in teams else "",
                    "logo_url": teams.get(int(fx.away_team_id)).logo_url if int(fx.away_team_id) in teams else None,
                },
                "model_version_used": mv_used,
                "predicted_total_sot": total_exp,
                "total_expected_sot": total_exp,
                "variation_delta": impact_slim.get("delta_total_sot"),
                "variation_reason": impact_slim.get("main_reason"),
                "lineup_refresh_impact": impact_slim,
                "markets": markets,
                "lineup_status": lineup_status,
                "monitored": monitored,
                "tracked_pick_badge": "Monitorata" if monitored else None,
                "tracked_pick_badges": ["Monitorata"] if monitored else [],
            },
        )

    payload = {
        "season": int(season),
        "competition_id": competition_id,
        "competition_name": competition_name,
        "model_version_used": mv_default,
        "recommended_model_version": recommended,
        "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "round": round_label,
        "matches_count": len(matches),
        "matches": matches,
        "model_limitations": default_model_limitations_dict(),
        "warnings": warnings,
    }
    if _PERF_LOG:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "quick-report season=%s fixtures=%s ms=%.1f",
            season,
            len(matches),
            elapsed_ms,
        )
    return payload, 200


def build_upcoming_fixture_detail_payload(
    db: Session,
    season: int,
    fixture_id: int,
    *,
    model_version: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Dettaglio completo di una fixture (stesso contratto riga upcoming-active)."""
    from app.services.prediction_readiness import build_upcoming_active_payload

    payload, code = build_upcoming_active_payload(
        db,
        season,
        limit=100,
        only_next_round=False,
        model_version=model_version,
    )
    if code != 200:
        return payload, code
    matches = payload.get("matches") or []
    match = next((m for m in matches if int(m.get("fixture_id", 0)) == int(fixture_id)), None)
    if match is None:
        return (
            {
                "status": "error",
                "message": f"Fixture {fixture_id} non trovata tra le partite upcoming della stagione.",
            },
            404,
        )
    from app.services.referee_severity_service import build_referee_summary_for_fixture

    referee_summary = build_referee_summary_for_fixture(db, int(fixture_id))
    return (
        {
            "status": "success",
            "season": int(season),
            "match": {**match, "referee_summary": referee_summary},
            "referee_summary": referee_summary,
            "model_limitations": payload.get("model_limitations"),
        },
        200,
    )
