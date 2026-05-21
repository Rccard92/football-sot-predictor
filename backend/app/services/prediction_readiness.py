"""
Lettura stato modelli e upcoming attivo (logica condivisa tra route GET e pipeline admin).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V10_SOT,
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    FINISHED_STATUSES,
)
from app.services.sot_model_registry import user_visible_model_versions
from app.models import Fixture, League, Season, Team, TeamSotPrediction
from app.services.ingestion_service import IngestionService
from app.services.model_version_preference import (
    build_v10_coherence_warnings,
    build_v11_coherence_warnings,
    enrich_v10_model_status_row,
    enrich_v11_model_status_row,
    preferred_model_versions,
    resolve_recommended_model_version,
)
from app.services.sot_feature_service import SotFeatureService
from app.services.sot_prediction_service import (  # type: ignore[attr-defined]
    SotPredictionService,
    _fixture_round_display,
    default_model_limitations_dict,
)

logger = logging.getLogger(__name__)


def _safe_details(exc: Exception) -> str:
    msg = f"{exc.__class__.__name__}: {exc}"
    lowered = msg.lower()
    if "postgresql://" in lowered or "mysql://" in lowered or "mongodb://" in lowered:
        return f"{exc.__class__.__name__}: [redacted]"
    if "database_url" in lowered or "apikey" in lowered or "api_key" in lowered or "secret" in lowered:
        return f"{exc.__class__.__name__}: [redacted]"
    return msg[:800]


def build_model_status_payload(db: Session, season: int) -> tuple[dict[str, Any], int]:
    """
    Stesso contratto della GET /predictions/sot/serie-a/{season}/model-status.
    Ritorna (payload_dict, http_status).
    """
    preferred = preferred_model_versions()
    warnings: list[str] = []

    try:
        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            settings = get_settings()
            league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            return (
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "league_lookup",
                    "details": "Lega Serie A non trovata.",
                    "season": int(season),
                },
                404,
            )

        season_row = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season)))
        if season_row is None:
            return (
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "season_lookup",
                    "details": f"Stagione non trovata per year={int(season)}.",
                    "season": int(season),
                },
                404,
            )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("model-status: errore DB durante league/season lookup")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "league_season_lookup_db",
                "details": _safe_details(exc),
                "season": int(season),
            },
            503,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("model-status: errore inatteso durante league/season lookup")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "league_season_lookup_unexpected",
                "details": _safe_details(exc),
                "season": int(season),
            },
            500,
        )

    try:
        upcoming_fixture_ids = list(
            db.scalars(
                select(Fixture.id).where(
                    Fixture.season_id == season_row.id,
                    ~Fixture.status.in_(FINISHED_STATUSES),
                )
            ).all()
        )
        upcoming_fixtures_total = len(upcoming_fixture_ids)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("model-status: errore DB durante upcoming fixtures lookup")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "upcoming_fixtures_lookup_db",
                "details": _safe_details(exc),
                "season": int(season),
            },
            503,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("model-status: errore inatteso durante upcoming fixtures lookup")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "upcoming_fixtures_lookup_unexpected",
                "details": _safe_details(exc),
                "season": int(season),
            },
            500,
        )

    try:
        is_upcoming_fixture = ~Fixture.status.in_(FINISHED_STATUSES)
        agg = (
            db.execute(
                select(
                    TeamSotPrediction.model_version.label("model_version"),
                    func.count(TeamSotPrediction.id).label("predictions_total"),
                    func.sum(case((is_upcoming_fixture, 1), else_=0)).label("upcoming_predictions"),
                    func.avg(case((is_upcoming_fixture, TeamSotPrediction.predicted_sot), else_=None)).label(
                        "avg_expected_sot"
                    ),
                    func.min(case((is_upcoming_fixture, TeamSotPrediction.predicted_sot), else_=None)).label(
                        "min_expected_sot"
                    ),
                    func.max(case((is_upcoming_fixture, TeamSotPrediction.predicted_sot), else_=None)).label(
                        "max_expected_sot"
                    ),
                    func.max(TeamSotPrediction.updated_at).label("generated_at"),
                )
                .select_from(TeamSotPrediction)
                .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                .where(Fixture.season_id == season_row.id)
                .group_by(TeamSotPrediction.model_version)
            )
            .mappings()
            .all()
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("model-status: errore DB durante aggregation")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "aggregation_db",
                "details": _safe_details(exc),
                "season": int(season),
            },
            503,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("model-status: errore inatteso durante aggregation")
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "failed_step": "aggregation_unexpected",
                "details": _safe_details(exc),
                "season": int(season),
            },
            500,
        )

    by_version: dict[str, dict[str, Any]] = {}
    for r in agg:
        mv = str(r.get("model_version"))
        up_n = int(r.get("upcoming_predictions") or 0)
        by_version[mv] = {
            "model_version": mv,
            "predictions_total": int(r.get("predictions_total") or 0),
            "upcoming_predictions": up_n,
            "avg_expected_sot": round(float(r["avg_expected_sot"]), 2) if r.get("avg_expected_sot") is not None else None,
            "min_expected_sot": round(float(r["min_expected_sot"]), 2) if r.get("min_expected_sot") is not None else None,
            "max_expected_sot": round(float(r["max_expected_sot"]), 2) if r.get("max_expected_sot") is not None else None,
            "generated_at": r.get("generated_at"),
            "is_available_for_upcoming": bool(up_n > 0),
        }
    if BASELINE_SOT_MODEL_VERSION_V11_SOT in by_version:
        enrich_v11_model_status_row(
            db,
            by_version[BASELINE_SOT_MODEL_VERSION_V11_SOT],
            upcoming_fixture_ids=upcoming_fixture_ids,
        )
    if BASELINE_SOT_MODEL_VERSION_V10_SOT in by_version:
        enrich_v10_model_status_row(
            db,
            by_version[BASELINE_SOT_MODEL_VERSION_V10_SOT],
            upcoming_fixture_ids=upcoming_fixture_ids,
        )

    if not by_version:
        warnings.append("Nessuna prediction trovata in team_sot_predictions per questa stagione.")
        if upcoming_fixtures_total > 0:
            warnings.append("Nessuna prediction upcoming trovata. Generare prima una baseline.")
        payload = {
            "status": "success",
            "season": int(season),
            "active_model_version": None,
            "recommended_model_version": None,
            "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
            "upcoming_fixtures_total": int(upcoming_fixtures_total),
            "available_model_versions": [],
            "warnings": warnings,
        }
        return payload, 200

    visible = user_visible_model_versions()
    preferred_present = [by_version[k] for k in visible if k in by_version]
    available_list = preferred_present

    recommended = resolve_recommended_model_version(
        db,
        upcoming_fixture_ids=upcoming_fixture_ids,
        by_version=by_version,
        upcoming_fixtures_total=int(upcoming_fixtures_total),
    )
    if recommended is None:
        warnings.append("Nessuna prediction upcoming trovata. Generare prima una baseline.")
    warnings.extend(
        build_v11_coherence_warnings(
            by_version=by_version,
            recommended=recommended,
        ),
    )
    warnings.extend(
        build_v10_coherence_warnings(
            db,
            upcoming_fixture_ids=upcoming_fixture_ids,
            upcoming_fixtures_total=int(upcoming_fixtures_total),
            by_version=by_version,
            recommended=recommended,
        ),
    )

    for mv in preferred:
        if mv not in by_version:
            warnings.append(f"Model version non presente in DB: {mv}")
        elif not by_version[mv]["is_available_for_upcoming"]:
            warnings.append(f"Model version senza coverage upcoming: {mv}")

    payload: dict[str, Any] = {
        "status": "success",
        "season": int(season),
        "active_model_version": recommended,
        "recommended_model_version": recommended,
        "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "upcoming_fixtures_total": int(upcoming_fixtures_total),
        "available_model_versions": available_list,
        "warnings": warnings,
    }
    v11_payload_row = by_version.get(BASELINE_SOT_MODEL_VERSION_V11_SOT)
    if isinstance(v11_payload_row, dict):
        mfs = v11_payload_row.get("missing_fields_summary")
        if isinstance(mfs, dict) and mfs:
            ranked = sorted(((str(k), int(v)) for k, v in mfs.items()), key=lambda kv: (-kv[1], kv[0]))[:3]
            payload["v11_diagnostic_hints"] = {
                "missing_fields_summary": {str(k): int(v) for k, v in mfs.items()},
                "top_missing_feature_keys": [k for k, _ in ranked],
            }
    return payload, 200


def build_upcoming_active_payload(
    db: Session,
    season: int,
    *,
    limit: int = 20,
    only_next_round: bool = True,
    model_version: str | None = None,
) -> tuple[dict[str, Any], int]:
    """
    Stesso contratto della GET upcoming-active (corpo JSON). Ritorna (dict, http_status).
    """
    preferred = preferred_model_versions()

    svc = SotPredictionService()
    try:
        _league, season_row = svc._season_row(db, season)  # type: ignore[attr-defined]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("upcoming-active: DB error (%s)", exc.__class__.__name__, exc_info=True)
        return ({"status": "error", "message": "Database error", "details": _safe_details(exc)}, 503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("upcoming-active: errore inatteso (season lookup)")
        return ({"status": "error", "message": "Errore inatteso", "details": _safe_details(exc)}, 500)

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

    def has_any_upcoming(mv: str) -> bool:
        if not upcoming:
            return False
        fx_ids = [int(f.id) for f in upcoming]
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .where(
                    TeamSotPrediction.fixture_id.in_(fx_ids),
                    TeamSotPrediction.model_version == mv,
                    TeamSotPrediction.predicted_sot.isnot(None),
                )
            )
            or 0
        )
        return n > 0

    upcoming_fixture_ids_local = [int(f.id) for f in upcoming]
    by_version_upcoming: dict[str, dict[str, Any]] = {}
    for mv in preferred:
        if not has_any_upcoming(mv):
            continue
        n = int(
            db.scalar(
                select(func.count())
                .select_from(TeamSotPrediction)
                .where(
                    TeamSotPrediction.fixture_id.in_(upcoming_fixture_ids_local),
                    TeamSotPrediction.model_version == mv,
                    TeamSotPrediction.predicted_sot.isnot(None),
                ),
            )
            or 0,
        )
        by_version_upcoming[mv] = {
            "is_available_for_upcoming": n > 0,
            "upcoming_predictions": n,
        }
    recommended = resolve_recommended_model_version(
        db,
        upcoming_fixture_ids=upcoming_fixture_ids_local,
        by_version=by_version_upcoming,
        upcoming_fixtures_total=len(upcoming),
    )
    if recommended is None:
        recommended = next((mv for mv in preferred if has_any_upcoming(mv)), BASELINE_SOT_MODEL_VERSION)
    requested = model_version or recommended
    warnings: list[str] = []
    if model_version is not None and requested not in preferred:
        warnings.append(f"Model version richiesta non riconosciuta: {requested}. Uso fallback per fixture.")

    fx_ids = [int(f.id) for f in upcoming]
    team_ids = list({int(f.home_team_id) for f in upcoming} | {int(f.away_team_id) for f in upcoming})
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()} if team_ids else {}

    versions_to_load = list(dict.fromkeys([requested] + preferred))
    preds = db.scalars(
        select(TeamSotPrediction).where(
            TeamSotPrediction.fixture_id.in_(fx_ids) if fx_ids else False,
            TeamSotPrediction.model_version.in_(versions_to_load),
        )
    ).all()
    pred_map: dict[tuple[int, int, str], TeamSotPrediction] = {
        (int(p.fixture_id), int(p.team_id), str(p.model_version)): p for p in preds
    }

    def pick_match_version(fx: Fixture) -> str | None:
        for mv in [requested] + [x for x in preferred if x != requested]:
            ph = pred_map.get((int(fx.id), int(fx.home_team_id), mv))
            pa = pred_map.get((int(fx.id), int(fx.away_team_id), mv))
            if ph and ph.predicted_sot is not None and pa and pa.predicted_sot is not None:
                return mv
        return None

    def baseline_v01(fx: Fixture, team_id: int) -> float | None:
        row = pred_map.get((int(fx.id), int(team_id), BASELINE_SOT_MODEL_VERSION))
        return float(row.predicted_sot) if row and row.predicted_sot is not None else None

    def baseline_v11(fx: Fixture, team_id: int) -> float | None:
        row = pred_map.get((int(fx.id), int(team_id), BASELINE_SOT_MODEL_VERSION_V11_SOT))
        return float(row.predicted_sot) if row and row.predicted_sot is not None else None

    from app.services.sportapi.sportapi_lineup_status import (
        formation_status_from_lineup,
        load_lineups_by_fixture_ids,
    )
    from app.services.sot_betting_advice_service import (
        advice_context_from_upcoming_lineup,
        build_betting_advice_compact,
        build_upcoming_report_markets,
    )

    lineups_by_fx = load_lineups_by_fixture_ids(db, fx_ids)

    from app.services.sportapi.lineup_refresh_impact_orchestrator import LineupRefreshImpactOrchestrator

    impacts_by_fx = LineupRefreshImpactOrchestrator.load_latest_impact_by_fixture_ids(db, fx_ids)

    matches: list[dict[str, Any]] = []
    for fx in upcoming:
        mv_used = pick_match_version(fx)
        if mv_used is None:
            warnings.append(f"Fixture {int(fx.id)}: nessuna prediction disponibile per nessuna model_version.")
            mv_used = requested

        def side(team_id: int) -> dict[str, Any] | None:
            row = pred_map.get((int(fx.id), int(team_id), mv_used))
            if row is None or row.predicted_sot is None:
                return None
            exp = float(row.predicted_sot)
            raw = row.raw_json if isinstance(row.raw_json, dict) else {}
            out: dict[str, Any] = {
                "expected_sot": round(exp, 2),
                "model_version": mv_used,
                "breakdown": raw,
            }
            if mv_used == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
                b11 = baseline_v11(fx, team_id)
                if b11 is not None:
                    out["baseline_v11_expected_sot"] = round(b11, 2)
                    out["difference_from_v11"] = round(exp - b11, 2)
                readiness = raw.get("pre_match_readiness")
                if isinstance(readiness, dict):
                    out["pre_match_readiness"] = readiness
            else:
                b01 = baseline_v01(fx, team_id)
                if b01 is not None:
                    out["baseline_v01_expected_sot"] = round(b01, 2)
                    out["difference_from_v01"] = round(exp - b01, 2)
            return out

        home = side(int(fx.home_team_id))
        away = side(int(fx.away_team_id))
        if home is None or away is None:
            warnings.append(
                f"Fixture {int(fx.id)}: model_version '{mv_used}' incompleta (home/away missing).",
            )

        total_exp = None
        if home and away:
            total_exp = round(float(home["expected_sot"]) + float(away["expected_sot"]), 2)

        lineup_status = formation_status_from_lineup(lineups_by_fx.get(int(fx.id)))
        advice_ctx = advice_context_from_upcoming_lineup(lineup_status)

        betting_compact = None
        markets: list[dict[str, Any]] = []
        if home and away:
            home_exp = float(home["expected_sot"])
            away_exp = float(away["expected_sot"])
            markets = build_upcoming_report_markets(
                home_exp,
                away_exp,
                model_version=mv_used,
                context=advice_ctx,
            )
            betting_compact = build_betting_advice_compact(
                home_exp,
                away_exp,
                model_version=mv_used,
                context=advice_ctx,
            )

        matches.append(
            {
                "fixture_id": int(fx.id),
                "api_fixture_id": int(fx.api_fixture_id),
                "round": fx.round,
                "kickoff_at": fx.kickoff_at,
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
                "home_prediction": home,
                "away_prediction": away,
                "total_expected_sot": total_exp,
                "betting_advice_compact": betting_compact,
                "markets": markets,
                "lineup_status": lineup_status,
                "lineup_refresh_impact": impacts_by_fx.get(int(fx.id))
                or {"has_comparison": False},
            },
        )

    round_label = _fixture_round_display(upcoming[0]) if upcoming else None
    payload = {
        "season": int(season),
        "model_version_used": requested if model_version else recommended,
        "recommended_model_version": recommended,
        "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "round": round_label,
        "matches_count": len(matches),
        "matches": matches,
        "model_limitations": default_model_limitations_dict(),
        "warnings": warnings,
    }
    return payload, 200


def upcoming_summary_from_payload(up: dict[str, Any]) -> dict[str, Any]:
    """Sintesi per pipeline admin / dashboard."""
    if up.get("status") == "error":
        return {
            "fixtures": 0,
            "predictions": 0,
            "model_version_used": None,
            "recommended_model_version": None,
            "first_kickoff": None,
            "last_kickoff": None,
            "warnings": [up.get("message") or "upcoming-active error"],
        }
    matches = up.get("matches") or []
    pred_count = 0
    for m in matches:
        if m.get("home_prediction") and m.get("away_prediction"):
            pred_count += 2
    return {
        "fixtures": len(matches),
        "predictions": pred_count,
        "model_version_used": up.get("model_version_used"),
        "recommended_model_version": up.get("recommended_model_version"),
        "first_kickoff": matches[0].get("kickoff_at") if matches else None,
        "last_kickoff": matches[-1].get("kickoff_at") if matches else None,
        "warnings": list(up.get("warnings") or []),
    }
