"""
Lettura stato modelli e upcoming attivo (logica condivisa tra route GET e pipeline admin).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
from app.services.sot_model_registry import get_model_display, user_visible_model_versions
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixtureProviderMapping,
    FixtureTeamStat,
    League,
    PlayerSeasonProfile,
    Season,
    Team,
    TeamSotPrediction,
)
from app.services.ingestion_service import IngestionService
from app.services.model_operating_context import (
    attach_global_v20_fields,
    build_v20_operating_context,
    operating_mode_message,
)
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
    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    payload["global_model_version"] = BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    payload["global_model_label"] = display.label if display else BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    v20_row = by_version.get(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    if v20_row and v20_row.get("is_available_for_upcoming"):
        payload["operating_mode"] = "complete"
    elif v20_row:
        payload["operating_mode"] = "degraded_fallback"
    else:
        payload["operating_mode"] = "not_ready"
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


def build_model_status_for_competition(db: Session, comp: Any) -> tuple[dict[str, Any], int]:
    """Model-status scoped per competition. Serie A IT delega al payload legacy."""
    settings = get_settings()
    is_legacy_serie_a = (
        int(getattr(comp, "provider_league_id", 0)) == int(settings.default_league_id)
        and str(getattr(comp, "country", "") or "").strip().lower() == "italy"
    )
    if is_legacy_serie_a:
        payload, code = build_model_status_payload(db, int(comp.season))
        if code == 200 and isinstance(payload, dict):
            ctx = build_v20_operating_context(db, comp)
            payload = attach_global_v20_fields(payload, ctx)
            payload["competition_id"] = int(comp.id)
            payload["competition_key"] = getattr(comp, "key", None)
        return payload, code

    competition_id = int(comp.id)
    season = int(comp.season)
    warnings: list[str] = []
    v20_ctx = build_v20_operating_context(db, comp)

    try:
        upcoming_fixture_ids = list(
            db.scalars(
                select(Fixture.id).where(
                    Fixture.competition_id == competition_id,
                    ~Fixture.status.in_(FINISHED_STATUSES),
                )
            ).all()
        )
        upcoming_fixtures_total = len(upcoming_fixture_ids)
        predictions_total = db.scalar(
            select(func.count())
            .select_from(TeamSotPrediction)
            .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
            .where(Fixture.competition_id == competition_id)
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("model-status competition=%s: errore DB", competition_id)
        return (
            {
                "status": "error",
                "message": "Errore durante il caricamento dello stato modelli SOT.",
                "competition_id": competition_id,
                "details": _safe_details(exc),
                "season": season,
            },
            503,
        )

    if int(predictions_total or 0) == 0 and upcoming_fixtures_total == 0:
        return (
            attach_global_v20_fields(
                {
                    "status": "not_initialized",
                    "message": "Modello non ancora inizializzato",
                    "competition_id": competition_id,
                    "competition_key": getattr(comp, "key", None),
                    "season": season,
                    "upcoming_fixtures_total": 0,
                    "available_model_versions": [],
                    "active_model_version": None,
                    "recommended_model_version": None,
                    "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
                    "warnings": [
                        "Nessuna fixture o prediction per questa competition. Eseguire bootstrap e generazione."
                    ],
                },
                v20_ctx,
            ),
            200,
        )

    if int(predictions_total or 0) == 0:
        lineups_ready = bool(v20_ctx.get("lineups_ready"))

        if upcoming_fixtures_total > 0 and v20_ctx["inputs_available"].get("v11_base_ready"):
            if not lineups_ready:
                warnings.append("v2.0 senza lineups")
                warnings.append(
                    "Lineups o mapping SportAPI non ancora disponibili per questa competition."
                )
            else:
                warnings.append("Nessuna prediction trovata per questa competition.")

            available_versions: list[dict[str, Any]] = [
                {
                    "model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
                    "predictions_total": 0,
                    "upcoming_predictions": 0,
                    "is_available_for_upcoming": False,
                    "generated_at": None,
                },
                {
                    "model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                    "predictions_total": 0,
                    "upcoming_predictions": 0,
                    "is_available_for_upcoming": False,
                    "degraded": not lineups_ready,
                    "generated_at": None,
                },
            ]
            mode = str(v20_ctx.get("operating_mode") or "not_ready")
            message = operating_mode_message(mode)
            return (
                attach_global_v20_fields(
                    {
                        "status": "fallback_ready",
                        "message": message,
                        "competition_id": competition_id,
                        "competition_key": getattr(comp, "key", None),
                        "season": season,
                        "upcoming_fixtures_total": upcoming_fixtures_total,
                        "active_model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                        "recommended_model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
                        "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
                        "available_model_versions": available_versions,
                        "warnings": warnings,
                    },
                    v20_ctx,
                ),
                200,
            )

        warnings.append("Nessuna prediction trovata per questa competition.")
        return (
            attach_global_v20_fields(
                {
                    "status": "not_initialized",
                    "message": "Modello non ancora inizializzato",
                    "competition_id": competition_id,
                    "competition_key": getattr(comp, "key", None),
                    "season": season,
                    "upcoming_fixtures_total": upcoming_fixtures_total,
                    "available_model_versions": [],
                    "active_model_version": None,
                    "recommended_model_version": None,
                    "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
                    "warnings": warnings,
                },
                v20_ctx,
            ),
            200,
        )

    is_upcoming_fixture = ~Fixture.status.in_(FINISHED_STATUSES)
    agg = (
        db.execute(
            select(
                TeamSotPrediction.model_version.label("model_version"),
                func.count(TeamSotPrediction.id).label("predictions_total"),
                func.sum(case((is_upcoming_fixture, 1), else_=0)).label("upcoming_predictions"),
                func.max(TeamSotPrediction.updated_at).label("generated_at"),
            )
            .select_from(TeamSotPrediction)
            .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
            .where(Fixture.competition_id == competition_id)
            .group_by(TeamSotPrediction.model_version)
        )
        .mappings()
        .all()
    )

    by_version: dict[str, dict[str, Any]] = {}
    for r in agg:
        mv = str(r.get("model_version"))
        up_n = int(r.get("upcoming_predictions") or 0)
        by_version[mv] = {
            "model_version": mv,
            "predictions_total": int(r.get("predictions_total") or 0),
            "upcoming_predictions": up_n,
            "generated_at": r.get("generated_at"),
            "is_available_for_upcoming": bool(up_n > 0),
        }

    visible = user_visible_model_versions()
    available_list = [by_version[k] for k in visible if k in by_version]
    recommended = resolve_recommended_model_version(
        db,
        upcoming_fixture_ids=upcoming_fixture_ids,
        by_version=by_version,
        upcoming_fixtures_total=int(upcoming_fixtures_total),
    )

    payload: dict[str, Any] = {
        "status": "success",
        "competition_id": competition_id,
        "competition_key": getattr(comp, "key", None),
        "season": season,
        "active_model_version": recommended,
        "recommended_model_version": recommended,
        "stable_model_version": BASELINE_SOT_MODEL_VERSION_V11_SOT,
        "upcoming_fixtures_total": int(upcoming_fixtures_total),
        "available_model_versions": available_list,
        "warnings": warnings,
    }
    v20_row = by_version.get(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)
    if v20_row and v20_row.get("is_available_for_upcoming") and v20_ctx.get("lineups_ready"):
        payload["operating_mode"] = "complete"
    elif v20_row and v20_row.get("is_available_for_upcoming"):
        payload["operating_mode"] = "degraded_fallback"
    else:
        payload["operating_mode"] = v20_ctx.get("operating_mode", "not_ready")
    return attach_global_v20_fields(payload, v20_ctx), 200


def build_upcoming_active_payload(
    db: Session,
    season: int,
    *,
    limit: int = 20,
    only_next_round: bool = True,
    model_version: str | None = None,
    competition_id: int | None = None,
    fixture_ids: list[int] | None = None,
) -> tuple[dict[str, Any], int]:
    """
    Stesso contratto della GET upcoming-active (corpo JSON). Ritorna (dict, http_status).
    Con competition_id: contesto multi-campionato (no _season_row legacy Serie A).
    """
    preferred = preferred_model_versions()
    competition_name: str | None = None

    try:
        if competition_id is not None:
            comp = db.get(Competition, int(competition_id))
            if comp is None:
                return (
                    {
                        "status": "error",
                        "code": "competition_not_found",
                        "message": f"Competition {competition_id} non trovata.",
                        "competition_id": int(competition_id),
                        "step": "load_competition",
                    },
                    404,
                )
            season = int(comp.season)
            competition_name = comp.name
            from app.services.next_round_selection import select_next_round_fixtures

            raw_upcoming = list(
                db.scalars(
                    select(Fixture)
                    .where(Fixture.competition_id == comp.id)
                    .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
                ).all()
            )
            raw_upcoming = [f for f in raw_upcoming if (f.status or "").upper() not in FINISHED_STATUSES]
            if fixture_ids:
                wanted = {int(x) for x in fixture_ids}
                raw_upcoming = [f for f in raw_upcoming if int(f.id) in wanted]
            apply_next_round = only_next_round and not fixture_ids
            selection = select_next_round_fixtures(
                raw_upcoming,
                limit=max(1, min(limit, 100)),
                only_next_round=apply_next_round,
            )
            upcoming = selection.fixtures
        else:
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
            if fixture_ids:
                wanted = {int(x) for x in fixture_ids}
                upcoming = [f for f in upcoming if int(f.id) in wanted]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("upcoming-active: DB error (%s)", exc.__class__.__name__, exc_info=True)
        err: dict[str, Any] = {
            "status": "error",
            "code": "database_error",
            "message": "Database error",
            "details": _safe_details(exc),
            "step": "load_fixtures",
        }
        if competition_id is not None:
            err["competition_id"] = int(competition_id)
        return (err, 503)
    except ValueError as exc:
        logger.warning("upcoming-active: lookup fallito (%s)", exc)
        err = {
            "status": "error",
            "code": "season_lookup_failed",
            "message": str(exc),
            "step": "season_lookup",
        }
        if competition_id is not None:
            err["competition_id"] = int(competition_id)
        return (err, 404)
    except Exception as exc:  # noqa: BLE001
        logger.exception("upcoming-active: errore inatteso (fixture load)")
        err = {
            "status": "error",
            "message": "Errore inatteso",
            "details": _safe_details(exc),
            "step": "load_fixtures",
        }
        if competition_id is not None:
            err["competition_id"] = int(competition_id)
        return (err, 500)

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

    from app.services.tracked_betting_pick_service import TrackedBettingPickService

    pick_svc = TrackedBettingPickService()
    tracked_by_fx = pick_svc.load_auto_pre_match_by_fixture_ids(db, fx_ids)
    open_by_fx = pick_svc.load_open_picks_by_fixture_ids(db, fx_ids)

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

        tracked_rows = tracked_by_fx.get(int(fx.id)) or []
        open_rows = open_by_fx.get(int(fx.id)) or []
        tracked_badge = None
        tracked_summary = None
        tracked_pick_badges: list[str] = []
        pre_match_job_updated_at = None
        if open_rows:
            tracked_pick_badges.append("Monitorata")
            tracked_badge = "Monitorata"
            tracked_summary = "Pick sincronizzata nel monitoraggio giocate."
        if tracked_rows:
            latest_auto = max(
                tracked_rows,
                key=lambda r: r.auto_generated_at or r.prediction_generated_at or datetime.min.replace(tzinfo=timezone.utc),
            )
            if latest_auto.auto_generated_at:
                pre_match_job_updated_at = latest_auto.auto_generated_at.isoformat()
            if "Auto pre-match" not in tracked_pick_badges:
                tracked_pick_badges.append("Auto pre-match")
            if tracked_badge is None:
                tracked_badge = "Auto pre-match"
                tracked_summary = "Aggiornata dal job formazioni ufficiali pre-match."

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
                "tracked_pick_badge": tracked_badge,
                "tracked_pick_summary": tracked_summary,
                "tracked_pick_badges": tracked_pick_badges,
                "pre_match_job_updated_at": pre_match_job_updated_at,
            },
        )

    round_label = _fixture_round_display(upcoming[0]) if upcoming else None
    payload: dict[str, Any] = {
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
    if competition_id is not None:
        payload["competition_id"] = int(competition_id)
        payload["competition_name"] = competition_name
    return payload, 200


def _validate_fixture_for_competition(
    db: Session,
    comp: Competition,
    fixture_id: int,
) -> tuple[Fixture | None, dict[str, Any] | None, int | None]:
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return None, {
            "status": "error",
            "code": "fixture_not_found",
            "message": f"Fixture {fixture_id} non trovata.",
            "competition_id": int(comp.id),
            "fixture_id": int(fixture_id),
            "step": "fixture_validation",
        }, 404
    if int(fx.competition_id or 0) != int(comp.id):
        return None, {
            "status": "error",
            "code": "fixture_competition_mismatch",
            "message": f"Fixture {fixture_id} non appartiene alla competition {comp.id}.",
            "competition_id": int(comp.id),
            "fixture_id": int(fixture_id),
            "step": "fixture_validation",
        }, 404
    return fx, None, None


def build_competition_audit_fixtures_list(
    db: Session,
    comp: Competition,
    *,
    scope: str = "next_round",
    model_version: str | None = None,
    limit: int = 40,
) -> tuple[dict[str, Any], int]:
    """Lista fixture per dropdown audit/spiegazione, scoped per competition."""
    from app.services.next_round_selection import select_next_round_fixtures

    if scope not in ("next_round", "upcoming", "all_with_predictions"):
        return (
            {
                "status": "error",
                "code": "invalid_scope",
                "message": "scope deve essere next_round, upcoming o all_with_predictions.",
                "competition_id": int(comp.id),
                "step": "validate_scope",
            },
            400,
        )

    try:
        raw_rows = list(
            db.scalars(
                select(Fixture)
                .where(Fixture.competition_id == comp.id)
                .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
            ).all()
        )
        if scope == "upcoming":
            rows = [f for f in raw_rows if (f.status or "").upper() not in FINISHED_STATUSES]
        elif scope == "all_with_predictions":
            pred_fx_ids = set(
                int(x)
                for x in db.scalars(
                    select(TeamSotPrediction.fixture_id)
                    .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
                    .where(
                        Fixture.competition_id == comp.id,
                        TeamSotPrediction.predicted_sot.isnot(None),
                        *(
                            [TeamSotPrediction.model_version == str(model_version)]
                            if model_version
                            else []
                        ),
                    )
                    .distinct()
                ).all()
            )
            rows = [f for f in raw_rows if int(f.id) in pred_fx_ids]
        else:
            upcoming = [f for f in raw_rows if (f.status or "").upper() not in FINISHED_STATUSES]
            selection = select_next_round_fixtures(
                upcoming,
                limit=max(1, min(limit, 200)),
                only_next_round=True,
            )
            rows = selection.fixtures

        rows = rows[: max(1, min(limit, 200))]
        fx_ids = [int(f.id) for f in rows]
        pred_counts: dict[int, int] = {}
        if fx_ids:
            pred_q = (
                select(TeamSotPrediction.fixture_id, func.count())
                .where(
                    TeamSotPrediction.fixture_id.in_(fx_ids),
                    TeamSotPrediction.predicted_sot.isnot(None),
                )
                .group_by(TeamSotPrediction.fixture_id)
            )
            if model_version:
                pred_q = pred_q.where(TeamSotPrediction.model_version == str(model_version))
            pred_counts = {int(fid): int(cnt) for fid, cnt in db.execute(pred_q).all()}

        fixtures_payload: list[dict[str, Any]] = []
        for f in rows:
            home = db.get(Team, f.home_team_id)
            away = db.get(Team, f.away_team_id)
            home_name = home.name if home else ""
            away_name = away.name if away else ""
            kickoff_iso = f.kickoff_at.isoformat() if f.kickoff_at else None
            fixtures_payload.append(
                {
                    "fixture_id": int(f.id),
                    "api_fixture_id": int(f.api_fixture_id),
                    "match_name": f"{home_name} – {away_name}".strip(" –"),
                    "kickoff": kickoff_iso,
                    "kickoff_at": kickoff_iso,
                    "round": f.round,
                    "status": f.status,
                    "status_short": f.status,
                    "has_prediction": pred_counts.get(int(f.id), 0) >= 2,
                    "competition_id": int(comp.id),
                    "home_team": {
                        "id": int(f.home_team_id),
                        "name": home_name,
                        "logo_url": home.logo_url if home else None,
                    },
                    "away_team": {
                        "id": int(f.away_team_id),
                        "name": away_name,
                        "logo_url": away.logo_url if away else None,
                    },
                }
            )

        return (
            {
                "competition_id": int(comp.id),
                "competition_name": comp.name,
                "season": int(comp.season),
                "scope": scope,
                "fixtures": fixtures_payload,
            },
            200,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("audit fixtures list: DB error competition=%s", comp.id, exc_info=True)
        return (
            {
                "status": "error",
                "code": "database_error",
                "message": "Database error",
                "competition_id": int(comp.id),
                "step": "load_fixtures",
                "details": _safe_details(exc),
            },
            503,
        )


def build_competition_fixture_explanation(
    db: Session,
    comp: Competition,
    fixture_id: int,
    *,
    model_version: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Spiegazione audit fixture con guardrail competition_id."""
    from app.services.sot_fixture_explanation_service import build_fixture_sot_explanation

    _fx, err, code = _validate_fixture_for_competition(db, comp, fixture_id)
    if err is not None:
        return err, int(code or 404)

    try:
        payload = build_fixture_sot_explanation(db, int(fixture_id), model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "competition fixture explanation: DB error competition=%s fixture=%s",
            comp.id,
            fixture_id,
            exc_info=True,
        )
        return (
            {
                "status": "error",
                "code": "database_error",
                "message": "Errore database durante la lettura della spiegazione.",
                "competition_id": int(comp.id),
                "fixture_id": int(fixture_id),
                "step": "build_explanation",
                "details": _safe_details(exc),
            },
            503,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "competition fixture explanation: errore inatteso competition=%s fixture=%s",
            comp.id,
            fixture_id,
        )
        return (
            {
                "status": "error",
                "code": "unexpected_error",
                "message": "Errore durante la costruzione della spiegazione.",
                "competition_id": int(comp.id),
                "fixture_id": int(fixture_id),
                "step": "build_explanation",
                "details": _safe_details(exc),
            },
            422,
        )

    if isinstance(payload, dict):
        payload.setdefault("competition_id", int(comp.id))
        payload.setdefault("competition_name", comp.name)
        if payload.get("status") == "error":
            return payload, 422
        if payload.get("status") == "missing":
            return payload, 404
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
