"""
Pipeline admin: orchestrazione refresh dati + previsioni v0.4 upcoming (nessuna modifica a formule).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT
from app.core.database import get_db
from app.services.ingestion_service import IngestionService
from app.services.player_sot_profile_service import PlayerSotProfileService
from app.services.prediction_readiness import (
    build_model_status_payload,
    build_upcoming_active_payload,
    upcoming_summary_from_payload,
)
from app.services.predictions_v04.offensive_core_sot_service import SotPredictionV04OffensiveCoreSotService
from app.services.predictions_v10.baseline_v1_sot_service import SotPredictionV10BaselineSotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/pipeline", tags=["admin-pipeline"])


def _require_api_football_key() -> None:
    if not get_settings().api_football_key.strip():
        raise HTTPException(
            status_code=400,
            detail="API_FOOTBALL_KEY non configurata sul server",
        )


def _ingestion_step(
    *,
    key: str,
    label: str,
    run,
) -> dict[str, Any]:
    ok = getattr(run, "status", None) == "success"
    rec = int(getattr(run, "records_processed", 0) or 0)
    err = getattr(run, "error_message", None) or ""
    return {
        "key": key,
        "label": label,
        "status": "success" if ok else "failed",
        "records_processed": rec,
        "message": "OK" if ok else (err[:500] if err else "Ingestion fallita"),
    }


@router.post("/serie-a/{season}/refresh-upcoming-v04", response_model=None)
def admin_pipeline_refresh_upcoming_v04(
    season: int,
    db: Session = Depends(get_db),
    generate_v10: bool = Query(default=True, description="Se true, dopo v0.4 genera anche baseline_v1_0_sot"),
):
    """
    Esegue in sequenza: fixture, statistiche squadra partite finite, classifica,
    statistiche giocatori, formazioni, (opzionale disponibilità), profili giocatori (best-effort),
    generazione previsioni upcoming v0.4, poi model-status e sintesi upcoming-active.
    """
    _require_api_football_key()

    warnings: list[str] = []
    steps: list[dict[str, Any]] = []
    svc = IngestionService()

    def fail_response(
        *,
        failed_step: str,
        message: str,
        details: str | None = None,
        http_status: int = 409,
    ) -> JSONResponse:
        body: dict[str, Any] = {
            "status": "error",
            "season": int(season),
            "active_model_version": None,
            "failed_step": failed_step,
            "message": message,
            "steps": steps,
            "warnings": warnings,
        }
        if details:
            body["details"] = details
        ms, _mc = build_model_status_payload(db, season)
        body["model_status"] = ms
        up, _uc = build_upcoming_active_payload(
            db,
            season,
            limit=50,
            only_next_round=True,
            model_version=BASELINE_SOT_MODEL_VERSION_V04_OFFENSIVE_CORE_SOT,
        )
        body["upcoming_summary"] = upcoming_summary_from_payload(up)
        return JSONResponse(status_code=http_status, content=jsonable_encoder(body))

    # 1 — Fixture / calendario
    try:
        r1 = svc.sync_serie_a_fixtures(db, season)
        steps.append(_ingestion_step(key="sync_fixtures", label="Aggiorna calendario", run=r1))
        if r1.status != "success":
            return fail_response(
                failed_step="sync_fixtures",
                message="Sincronizzazione calendario fallita.",
                details=r1.error_message,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline: sync_fixtures")
        steps.append(
            {
                "key": "sync_fixtures",
                "label": "Aggiorna calendario",
                "status": "failed",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )
        return fail_response(failed_step="sync_fixtures", message=str(exc)[:200], details=str(exc)[:800])

    # 2 — Statistiche squadra (partite finite)
    try:
        s2 = svc.sync_serie_a_team_stats_admin(db, season)
        rec = int(s2.get("team_stats_rows_created_or_updated") or s2.get("fixtures_processed") or 0)
        ok = s2.get("status") == "success"
        steps.append(
            {
                "key": "team_stats",
                "label": "Statistiche squadra (finite)",
                "status": "success" if ok else "failed",
                "records_processed": rec,
                "message": s2.get("message") or ("OK" if ok else "Import team stats fallito"),
            },
        )
        if not ok:
            return fail_response(
                failed_step="team_stats",
                message="Import statistiche squadra fallito.",
                details=str(s2.get("errors") or s2.get("message") or "")[:800],
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline: team_stats")
        steps.append(
            {
                "key": "team_stats",
                "label": "Statistiche squadra (finite)",
                "status": "failed",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )
        return fail_response(failed_step="team_stats", message=str(exc)[:200], details=str(exc)[:800])

    # 3 — Classifica
    try:
        r3 = svc.ingest_serie_a_standings(db, season)
        steps.append(_ingestion_step(key="standings", label="Classifica", run=r3))
        if r3.status != "success":
            return fail_response(
                failed_step="standings",
                message="Import classifica fallito.",
                details=r3.error_message,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline: standings")
        steps.append(
            {
                "key": "standings",
                "label": "Classifica",
                "status": "failed",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )
        return fail_response(failed_step="standings", message=str(exc)[:200], details=str(exc)[:800])

    # 4 — Statistiche giocatori (critico per coerenza dataset)
    try:
        r4 = svc.ingest_serie_a_player_stats(db, season, run_source="serie_a_player_stats")
        steps.append(_ingestion_step(key="player_stats", label="Statistiche giocatori", run=r4))
        if r4.status != "success":
            return fail_response(
                failed_step="player_stats",
                message="Import statistiche giocatori fallito.",
                details=r4.error_message,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline: player_stats")
        steps.append(
            {
                "key": "player_stats",
                "label": "Statistiche giocatori",
                "status": "failed",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )
        return fail_response(failed_step="player_stats", message=str(exc)[:200], details=str(exc)[:800])

    # 5 — Formazioni (non critico)
    try:
        r5 = svc.ingest_serie_a_lineups(db, season, run_source="serie_a_lineups")
        st = _ingestion_step(key="lineups", label="Formazioni", run=r5)
        steps.append(st)
        if r5.status != "success":
            warnings.append(f"Formazioni: {r5.error_message or 'step non completato'}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline: lineups optional failure: %s", exc, exc_info=True)
        warnings.append(f"Formazioni saltate: {str(exc)[:300]}")
        steps.append(
            {
                "key": "lineups",
                "label": "Formazioni",
                "status": "skipped",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )

    # 6 — Disponibilità / infortuni (non critico)
    try:
        from app.services.availability.availability_ingestion import ingest_serie_a_availability

        r6 = ingest_serie_a_availability(db, season)
        rec6 = int(r6.get("availability_records_upserted") or 0)
        ok6 = r6.get("status") in ("success", "partial_success")
        steps.append(
            {
                "key": "availability",
                "label": "Disponibilità / infortuni",
                "status": "success" if ok6 else "skipped",
                "records_processed": rec6,
                "message": f"Upsert {rec6} record" if ok6 else str(r6.get("errors") or "non completato")[:200],
            },
        )
        if not ok6:
            warnings.append(f"Disponibilità: step non completato")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline: availability optional failure: %s", exc, exc_info=True)
        warnings.append(f"Disponibilità saltata: {str(exc)[:300]}")
        steps.append(
            {
                "key": "availability",
                "label": "Disponibilità / infortuni",
                "status": "skipped",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )

    # 7 — Profili giocatori (non critico)
    try:
        prof = PlayerSotProfileService().build_for_season(db, season)
        ok = prof.get("status") == "success"
        rec = int(prof.get("rows_upserted") or prof.get("players_profiled") or 0)
        steps.append(
            {
                "key": "player_profiles",
                "label": "Profili impatto giocatori",
                "status": "success" if ok else "skipped",
                "records_processed": rec,
                "message": prof.get("message") or ("OK" if ok else "Profili non aggiornati"),
            },
        )
        if not ok:
            warnings.append(f"Profili giocatori: {prof.get('message') or 'status non success'}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline: player_profiles optional failure: %s", exc, exc_info=True)
        warnings.append(f"Profili giocatori saltati: {str(exc)[:300]}")
        steps.append(
            {
                "key": "player_profiles",
                "label": "Profili impatto giocatori",
                "status": "skipped",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )

    # 8 — Previsioni v0.4 upcoming (critico)
    v04_svc = SotPredictionV04OffensiveCoreSotService()
    try:
        v04 = v04_svc.generate_for_upcoming_season(db, season)
        pred_n = int(v04.get("predictions_created_or_updated") or 0)
        fx_n = int(v04.get("upcoming_fixtures_found") or 0)
        ok = v04.get("status") == "success"
        steps.append(
            {
                "key": "generate_v04_upcoming",
                "label": "Genera previsioni v0.4 upcoming",
                "status": "success" if ok else "failed",
                "records_processed": pred_n,
                "predictions_created_or_updated": pred_n,
                "upcoming_fixtures_found": fx_n,
                "message": "Previsioni v0.4 aggiornate" if ok else (str(v04.get("message") or "Errore generazione v0.4")),
            },
        )
        if not ok:
            errs = v04.get("errors") or []
            return fail_response(
                failed_step="generate_v04_upcoming",
                message="Generazione previsioni v0.4 fallita.",
                details=str(errs)[:800] if errs else str(v04.get("message")),
                http_status=409,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pipeline: v04")
        steps.append(
            {
                "key": "generate_v04_upcoming",
                "label": "Genera previsioni v0.4 upcoming",
                "status": "failed",
                "records_processed": 0,
                "message": str(exc)[:500],
            },
        )
        return fail_response(
            failed_step="generate_v04_upcoming",
            message="Errore durante la generazione v0.4.",
            details=str(exc)[:800],
            http_status=409,
        )

    if generate_v10:
        v10_svc = SotPredictionV10BaselineSotService()
        try:
            v10 = v10_svc.generate_for_upcoming_season(db, season)
            pred10 = int(v10.get("predictions_created_or_updated") or 0)
            ok10 = v10.get("status") == "success"
            steps.append(
                {
                    "key": "generate_v10_upcoming",
                    "label": "Genera previsioni v1.0 SOT (opzionale)",
                    "status": "success" if ok10 else "failed",
                    "records_processed": pred10,
                    "predictions_created_or_updated": pred10,
                    "architecture": str(v10.get("architecture") or "explicit_terms_from_v04_plus_xg"),
                    "xg_applied_count": int(v10.get("xg_applied_count") or 0),
                    "xg_fallback_count": int(v10.get("xg_fallback_count") or 0),
                    "aligned_base_terms_count": int(v10.get("aligned_base_terms_count") or 0),
                    "aligned_with_v04": int(v10.get("aligned_with_v04") or 0),
                    "minor_rounding_difference": int(v10.get("minor_rounding_difference") or 0),
                    "needs_review": int(v10.get("needs_review") or 0),
                    "message": str(v10.get("message") or ("OK" if ok10 else "Errore generazione v1.0")),
                },
            )
            if not ok10:
                warnings.append(f"v1.0 SOT: {v10.get('message') or 'generazione non riuscita'}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("pipeline: v10 optional failure: %s", exc, exc_info=True)
            warnings.append(f"v1.0 SOT saltata: {str(exc)[:300]}")
            steps.append(
                {
                    "key": "generate_v10_upcoming",
                    "label": "Genera previsioni v1.0 SOT (opzionale)",
                    "status": "skipped",
                    "records_processed": 0,
                    "message": str(exc)[:500],
                },
            )

    # 9 — Model status + 10 — Upcoming summary (lettura; non bloccano esito success)
    model_payload, _mc = build_model_status_payload(db, season)
    if model_payload.get("status") != "success":
        warnings.append("Lettura model-status con anomalie dopo pipeline.")

    recommended_mv = model_payload.get("recommended_model_version")
    up_payload, up_code = build_upcoming_active_payload(
        db,
        season,
        limit=50,
        only_next_round=True,
        model_version=recommended_mv,
    )
    if up_code != 200:
        warnings.append("Lettura upcoming-active non riuscita dopo pipeline.")

    active_mv = model_payload.get("active_model_version") or model_payload.get("recommended_model_version")
    summary = upcoming_summary_from_payload(up_payload)

    body: dict[str, Any] = {
        "status": "success",
        "season": int(season),
        "active_model_version": active_mv,
        "recommended_model_version": model_payload.get("recommended_model_version"),
        "model_version_used_for_summary": recommended_mv or active_mv,
        "steps": steps,
        "model_status": model_payload,
        "upcoming_summary": summary,
        "warnings": warnings + list(model_payload.get("warnings") or []) + list(summary.get("warnings") or []),
    }
    return JSONResponse(status_code=200, content=jsonable_encoder(body))
