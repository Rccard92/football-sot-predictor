import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION,
    BASELINE_SOT_MODEL_VERSION_V02,
    BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
    BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
    BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
    FINISHED_STATUSES,
)
from app.core.database import get_db
from app.models import Fixture, Team, TeamSotPrediction
from app.schemas.predictions import (
    EvaluateMatchSotLineBody,
    EvaluateMatchSotLineResponse,
    EvaluateSotLineBody,
    EvaluateSotLineResponse,
    FixturePredictionsEnrichedResponse,
    FixtureSotPredictionItem,
    GeneratePredictionsBody,
    SotPredictionsSeasonSummaryResponse,
    TeamPredictionsResponse,
    TeamSotPredictionRead,
    UpcomingMatchesResponse,
    UpcomingV02Response,
    V02ReadinessResponse,
)
from app.services.sot_line_evaluate import evaluate_match_sot_line, evaluate_sot_line
from app.services.sot_prediction_service import SotPredictionService
from app.services.sot_prediction_v02_service import SotPredictionV02Service
from app.services.predictions_v02.player_adjusted_service import SotPredictionV02PlayerAdjustedService
from app.services.predictions_v03.core_sot_service import SotPredictionV03CoreSotService
from app.services.predictions_v04.offensive_core_sot_service import SotPredictionV04OffensiveCoreSotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions/sot", tags=["predictions"])


def _preferred_model_versions() -> list[str]:
    return [
        BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V03_CORE_SOT,
        BASELINE_SOT_MODEL_VERSION_V02_PLAYER_ADJUSTED,
        BASELINE_SOT_MODEL_VERSION_V02,
        BASELINE_SOT_MODEL_VERSION,
    ]


@router.post("/serie-a/{season}/generate", response_model=None)
def generate_serie_a_predictions(
    season: int,
    db: Session = Depends(get_db),
    body: GeneratePredictionsBody = Body(default_factory=GeneratePredictionsBody),
):
    _ = body  # line_value non usato nello Step 5
    svc = SotPredictionService()
    try:
        summary = svc.generate_for_season_admin(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_sot_predictions: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("predictions_created_or_updated", 0) == 0:
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.post("/serie-a/{season}/generate-upcoming", response_model=None)
def generate_serie_a_predictions_upcoming(
    season: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
):
    svc = SotPredictionService()
    try:
        summary = svc.generate_upcoming_predictions_for_season(db, season, model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_sot_predictions_upcoming: errore database")
        raise HTTPException(
            status_code=503,
            detail="Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        ) from exc

    if summary.get("status") == "error" and summary.get("predictions_created_or_updated", 0) == 0:
        return JSONResponse(status_code=502, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming", response_model=UpcomingMatchesResponse)
def sot_predictions_serie_a_upcoming(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    match_round: str | None = Query(default=None, alias="round"),
    only_next_round: bool = Query(default=True),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
) -> UpcomingMatchesResponse:
    svc = SotPredictionService()
    try:
        data = svc.get_serie_a_upcoming_matches(
            db,
            season,
            limit=limit,
            round_filter=match_round,
            only_next_round=only_next_round,
            model_version=model_version,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return UpcomingMatchesResponse.model_validate(data)


@router.get("/serie-a/{season}/model-status", response_model=None)
def sot_predictions_serie_a_model_status(
    season: int,
    db: Session = Depends(get_db),
):
    """
    Read-only: mostra quali model_version esistono davvero in `team_sot_predictions` per la stagione
    e quali hanno coverage sulle fixture upcoming.
    """
    preferred = _preferred_model_versions()
    warnings: list[str] = []

    def _safe_details(exc: Exception) -> str:
        # Evita di esporre URL/credenziali in chiaro nei dettagli.
        msg = f"{exc.__class__.__name__}: {exc}"
        lowered = msg.lower()
        if "postgresql://" in lowered or "mysql://" in lowered or "mongodb://" in lowered:
            return f"{exc.__class__.__name__}: [redacted]"
        if "database_url" in lowered or "apikey" in lowered or "api_key" in lowered or "secret" in lowered:
            return f"{exc.__class__.__name__}: [redacted]"
        return msg[:800]

    # Lookup league/season in modo esplicito (no helper privati)
    try:
        from app.models import League, Season
        from app.services.ingestion_service import IngestionService

        league = db.scalar(select(League).where(League.name == IngestionService.SERIE_A_LEAGUE_NAME))
        if league is None:
            # fallback: lega default configurata
            from app.core.config import get_settings

            settings = get_settings()
            league = db.scalar(select(League).where(League.api_league_id == settings.default_league_id))
        if league is None:
            return JSONResponse(
                status_code=404,
                content=jsonable_encoder(
                    {
                        "status": "error",
                        "message": "Errore durante il caricamento dello stato modelli SOT.",
                        "failed_step": "league_lookup",
                        "details": "Lega Serie A non trovata.",
                        "season": int(season),
                    }
                ),
            )

        season_row = db.scalar(select(Season).where(Season.league_id == league.id, Season.year == int(season)))
        if season_row is None:
            return JSONResponse(
                status_code=404,
                content=jsonable_encoder(
                    {
                        "status": "error",
                        "message": "Errore durante il caricamento dello stato modelli SOT.",
                        "failed_step": "season_lookup",
                        "details": f"Stagione non trovata per year={int(season)}.",
                        "season": int(season),
                    }
                ),
            )
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET model-status: errore DB durante league/season lookup")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "league_season_lookup_db",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET model-status: errore inatteso durante league/season lookup")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "league_season_lookup_unexpected",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
        )

    # Upcoming fixtures
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
        logger.exception("GET model-status: errore DB durante upcoming fixtures lookup")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "upcoming_fixtures_lookup_db",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET model-status: errore inatteso durante upcoming fixtures lookup")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "upcoming_fixtures_lookup_unexpected",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
        )

    # Aggregazioni per model_version (robuste, JSON-safe)
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
        logger.exception("GET model-status: errore DB durante aggregation")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "aggregation_db",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET model-status: errore inatteso durante aggregation")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "message": "Errore durante il caricamento dello stato modelli SOT.",
                    "failed_step": "aggregation_unexpected",
                    "details": _safe_details(exc),
                    "season": int(season),
                }
            ),
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

    # Se non esistono righe nel DB, non fallire: lista vuota + warning chiaro.
    if not by_version:
        warnings.append("Nessuna prediction trovata in team_sot_predictions per questa stagione.")
        if upcoming_fixtures_total > 0:
            warnings.append("Nessuna prediction upcoming trovata. Generare prima una baseline.")
        payload = {
            "status": "success",
            "season": int(season),
            "active_model_version": None,
            "recommended_model_version": None,
            "upcoming_fixtures_total": int(upcoming_fixtures_total),
            "available_model_versions": [],
            "warnings": warnings,
        }
        return JSONResponse(status_code=200, content=jsonable_encoder(payload))

    # Ordina: preferiti prima, poi eventuali versioni extra presenti nel DB.
    preferred_present = [by_version[k] for k in preferred if k in by_version]
    extras = [v for k, v in by_version.items() if k not in preferred]
    available_list = preferred_present + sorted(extras, key=lambda x: x["model_version"])

    recommended = None
    for mv in preferred:
        row = by_version.get(mv)
        if row and row.get("is_available_for_upcoming"):
            recommended = mv
            break
    if recommended is None:
        warnings.append("Nessuna prediction upcoming trovata. Generare prima una baseline.")

    # warnings for missing preferred
    for mv in preferred:
        if mv not in by_version:
            warnings.append(f"Model version non presente in DB: {mv}")
        elif not by_version[mv]["is_available_for_upcoming"]:
            warnings.append(f"Model version senza coverage upcoming: {mv}")

    payload = {
        "status": "success",
        "season": int(season),
        "active_model_version": recommended,
        "recommended_model_version": recommended,
        "upcoming_fixtures_total": int(upcoming_fixtures_total),
        "available_model_versions": available_list,
        "warnings": warnings,
    }
    return JSONResponse(status_code=200, content=jsonable_encoder(payload))


@router.get("/serie-a/{season}/upcoming-active", response_model=None)
def sot_predictions_serie_a_upcoming_active(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
    model_version: str | None = Query(default=None),
):
    """
    Upcoming matches usando il miglior modello disponibile (recommended) o quello richiesto.
    Nessun ricalcolo: solo lettura `team_sot_predictions` + fallback per fixture.
    """
    preferred = _preferred_model_versions()

    from app.services.sot_prediction_service import SotPredictionService, _fixture_round_display, default_model_limitations_dict  # type: ignore
    from app.services.sot_feature_service import SotFeatureService

    svc = SotPredictionService()
    try:
        _league, season_row = svc._season_row(db, season)  # type: ignore[attr-defined]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-active: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-active: errore inatteso (season lookup)")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc

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

    # determine recommended among preferred based on coverage upcoming
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

    recommended = next((mv for mv in preferred if has_any_upcoming(mv)), BASELINE_SOT_MODEL_VERSION)
    requested = model_version or recommended
    warnings: list[str] = []
    if model_version is None:
        pass
    elif requested not in preferred:
        warnings.append(f"Model version richiesta non riconosciuta: {requested}. Uso fallback per fixture.")

    fx_ids = [int(f.id) for f in upcoming]
    team_ids = list({int(f.home_team_id) for f in upcoming} | {int(f.away_team_id) for f in upcoming})
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids))).all()} if team_ids else {}

    # preload predictions for these fixtures for all preferred versions + requested (if custom)
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
        # try requested, then preferred: choose a single model version that exists for both teams
        for mv in [requested] + [x for x in preferred if x != requested]:
            ph = pred_map.get((int(fx.id), int(fx.home_team_id), mv))
            pa = pred_map.get((int(fx.id), int(fx.away_team_id), mv))
            if ph and ph.predicted_sot is not None and pa and pa.predicted_sot is not None:
                return mv
        return None

    def baseline_v01(fx: Fixture, team_id: int) -> float | None:
        row = pred_map.get((int(fx.id), int(team_id), BASELINE_SOT_MODEL_VERSION))
        return float(row.predicted_sot) if row and row.predicted_sot is not None else None

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
            b01 = baseline_v01(fx, team_id)
            return {
                "expected_sot": round(exp, 2),
                "model_version": mv_used,
                "baseline_v01_expected_sot": round(b01, 2) if b01 is not None else None,
                "difference_from_v01": round(exp - b01, 2) if b01 is not None else None,
                "breakdown": row.raw_json if isinstance(row.raw_json, dict) else None,
            }

        home = side(int(fx.home_team_id))
        away = side(int(fx.away_team_id))
        if home is None or away is None:
            warnings.append(
                f"Fixture {int(fx.id)}: model_version '{mv_used}' incompleta (home/away missing)."
            )

        total_exp = None
        if home and away:
            total_exp = round(float(home["expected_sot"]) + float(away["expected_sot"]), 2)

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
            }
        )

    round_label = _fixture_round_display(upcoming[0]) if upcoming else None
    return jsonable_encoder(
        {
            "season": int(season),
            "model_version_used": requested if model_version else recommended,
            "recommended_model_version": recommended,
            "round": round_label,
            "matches_count": len(matches),
            "matches": matches,
            "model_limitations": default_model_limitations_dict(),
            "warnings": warnings,
        }
    )


@router.post("/evaluate-line", response_model=EvaluateSotLineResponse)
def evaluate_sot_line_endpoint(body: EvaluateSotLineBody) -> EvaluateSotLineResponse:
    return EvaluateSotLineResponse.model_validate(evaluate_sot_line(body.expected_sot, body.line_value))


@router.post("/evaluate-match-line", response_model=EvaluateMatchSotLineResponse)
def evaluate_match_sot_line_endpoint(body: EvaluateMatchSotLineBody) -> EvaluateMatchSotLineResponse:
    return EvaluateMatchSotLineResponse.model_validate(
        evaluate_match_sot_line(
            body.home_expected_sot,
            body.away_expected_sot,
            body.line_value,
            home_adjusted_expected_sot=body.home_adjusted_expected_sot,
            away_adjusted_expected_sot=body.away_adjusted_expected_sot,
            use_adjusted=body.use_adjusted,
            odds=body.odds,
            bookmaker=body.bookmaker,
            market_type=body.market_type,
        ),
    )


@router.post("/serie-a/{season}/generate-v02-upcoming", response_model=None)
def generate_serie_a_predictions_v02_upcoming(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV02Service()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_v02_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v02_upcoming: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v02_upcoming: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v02_upcoming",
                    "message": "Errore inatteso durante la generazione v0.2.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(
            status_code=502,
            content=jsonable_encoder(summary),
        )
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/v02-readiness", response_model=V02ReadinessResponse)
def get_serie_a_v02_readiness(
    season: int,
    db: Session = Depends(get_db),
) -> V02ReadinessResponse:
    svc = SotPredictionV02Service()
    try:
        data = svc.v02_readiness(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("GET v02-readiness: errore database")
        payload = {
            "season": season,
            "upcoming_fixtures": 0,
            "baseline_v01_upcoming_predictions": 0,
            "player_profiles_available": False,
            "standings_available": False,
            "adjustments_table_exists": False,
            "ready": False,
            "missing_requirements": ["database_unavailable"],
            "message": "Database non disponibile o schema non aggiornato. Eseguire alembic upgrade head.",
        }
        return JSONResponse(status_code=503, content=jsonable_encoder(payload))
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET v02-readiness: errore inatteso")
        payload = {
            "season": season,
            "upcoming_fixtures": 0,
            "baseline_v01_upcoming_predictions": 0,
            "player_profiles_available": False,
            "standings_available": False,
            "adjustments_table_exists": False,
            "ready": False,
            "missing_requirements": ["unexpected_error"],
            "message": "Errore inatteso durante il readiness check.",
        }
        return JSONResponse(status_code=500, content=jsonable_encoder(payload))
    return V02ReadinessResponse.model_validate(data)


@router.get("/serie-a/{season}/upcoming-v02", response_model=UpcomingV02Response)
def sot_predictions_serie_a_upcoming_v02(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
) -> UpcomingV02Response:
    svc = SotPredictionV02Service()
    try:
        data = svc.upcoming_v02(
            db,
            season,
            limit=limit,
            only_next_round=only_next_round,
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v02: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return UpcomingV02Response.model_validate(data)


@router.post("/serie-a/{season}/generate-v02-player-adjusted", response_model=None)
def generate_serie_a_predictions_v02_player_adjusted(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV02PlayerAdjustedService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v02_player_adjusted: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v02_player_adjusted: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v02_player_adjusted",
                    "message": "Errore inatteso durante la generazione v0.2 player adjusted.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        # Errore applicativo (es. baseline v0.1 mancante) → messaggio chiaro, senza 500 generico.
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v02-player-adjusted", response_model=None)
def sot_predictions_serie_a_upcoming_v02_player_adjusted(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    svc = SotPredictionV02PlayerAdjustedService()
    try:
        data = svc.upcoming_player_adjusted(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v02-player-adjusted: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v02-player-adjusted: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    return jsonable_encoder(data)


@router.post("/serie-a/{season}/generate-v03-core-sot", response_model=None)
def generate_serie_a_predictions_v03_core_sot(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV03CoreSotService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v03_core_sot: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v03_core_sot: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v03_core_sot",
                    "message": "Errore inatteso durante la generazione v0.3 core SOT.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v03-core-sot", response_model=None)
def sot_predictions_serie_a_upcoming_v03_core_sot(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    svc = SotPredictionV03CoreSotService()
    try:
        data = svc.upcoming_v03(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v03-core-sot: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v03-core-sot: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    if isinstance(data, dict) and data.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(data))
    return jsonable_encoder(data)


@router.post("/serie-a/{season}/generate-v04-offensive-core-sot", response_model=None)
def generate_serie_a_predictions_v04_offensive_core_sot(
    season: int,
    db: Session = Depends(get_db),
):
    svc = SotPredictionV04OffensiveCoreSotService()
    partial_result = {
        "upcoming_fixtures_found": 0,
        "predictions_created_or_updated": 0,
        "errors": [],
    }
    try:
        summary = svc.generate_for_upcoming_season(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.exception("POST generate_v04_offensive_core_sot: errore database")
        return JSONResponse(
            status_code=503,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "database_operation",
                    "message": "Database non disponibile o schema non aggiornato.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("POST generate_v04_offensive_core_sot: errore inatteso")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                {
                    "status": "error",
                    "failed_step": "generate_v04_offensive_core_sot",
                    "message": "Errore inatteso durante la generazione v0.4 offensive core SOT.",
                    "details": str(exc),
                    "partial_result": partial_result,
                },
            ),
        )
    if summary.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(summary))
    return jsonable_encoder(summary)


@router.get("/serie-a/{season}/upcoming-v04-offensive-core-sot", response_model=None)
def sot_predictions_serie_a_upcoming_v04_offensive_core_sot(
    season: int,
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    only_next_round: bool = Query(default=True),
):
    _ = only_next_round  # non ancora filtrato per round in v0.4
    svc = SotPredictionV04OffensiveCoreSotService()
    try:
        data = svc.upcoming_v04(db, season, limit=limit, only_next_round=only_next_round)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET upcoming-v04-offensive-core-sot: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GET upcoming-v04-offensive-core-sot: errore inatteso")
        raise HTTPException(status_code=500, detail="Errore inatteso") from exc
    if isinstance(data, dict) and data.get("status") == "error":
        return JSONResponse(status_code=409, content=jsonable_encoder(data))
    return jsonable_encoder(data)


@router.get("/serie-a/{season}/summary", response_model=SotPredictionsSeasonSummaryResponse)
def sot_predictions_season_summary(
    season: int,
    db: Session = Depends(get_db),
) -> SotPredictionsSeasonSummaryResponse:
    svc = SotPredictionService()
    try:
        data = svc.get_season_predictions_summary(db, season)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET predictions summary: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc
    return SotPredictionsSeasonSummaryResponse.model_validate(data)


@router.get("/fixture/{fixture_id}", response_model=FixturePredictionsEnrichedResponse)
def get_fixture_predictions(
    fixture_id: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
) -> FixturePredictionsEnrichedResponse:
    svc = SotPredictionService()
    try:
        items = svc.get_fixture_predictions_enriched(db, fixture_id, model_version=model_version)
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("GET fixture predictions: DB error (%s)", exc.__class__.__name__, exc_info=True)
        raise HTTPException(status_code=503, detail="Database error") from exc

    return FixturePredictionsEnrichedResponse(
        fixture_id=fixture_id,
        predictions=[FixtureSotPredictionItem.model_validate(x) for x in items],
    )


@router.get("/team/{team_id}", response_model=TeamPredictionsResponse)
def get_team_predictions(
    team_id: int,
    db: Session = Depends(get_db),
    model_version: str = Query(default=BASELINE_SOT_MODEL_VERSION),
    limit: int = Query(default=100, ge=1, le=500),
) -> TeamPredictionsResponse:
    rows = db.scalars(
        select(TeamSotPrediction)
        .join(Fixture, Fixture.id == TeamSotPrediction.fixture_id)
        .where(
            TeamSotPrediction.team_id == team_id,
            TeamSotPrediction.model_version == model_version,
        )
        .order_by(Fixture.kickoff_at.desc(), Fixture.id.desc())
        .limit(limit),
    ).all()
    return TeamPredictionsResponse(
        team_id=team_id,
        predictions=[TeamSotPredictionRead.model_validate(r) for r in rows],
    )
