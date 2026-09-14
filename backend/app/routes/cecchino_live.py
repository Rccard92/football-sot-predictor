"""API registro previsioni live: consultazione pubblica, comandi con sessione admin."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_session import require_admin_session
from app.core.database import get_db
from app.models.cecchino_live_prediction import CecchinoLivePrediction
from app.services.cecchino_live.registry import record_predictions, settle_predictions
from app.services.cecchino_live.summary import live_summary

router = APIRouter(prefix="/cecchino-live", tags=["cecchino-live"])
admin_router = APIRouter(
    prefix="/admin/cecchino-live",
    tags=["admin-cecchino-live"],
    dependencies=[Depends(require_admin_session)],
)


def _to_dict(p: CecchinoLivePrediction) -> dict:
    return {
        "id": int(p.id),
        "today_fixture_id": int(p.today_fixture_id),
        "scan_date": p.scan_date.isoformat(),
        "kickoff": p.kickoff.isoformat() if p.kickoff else None,
        "league_name": p.league_name,
        "country_name": p.country_name,
        "home_team_name": p.home_team_name,
        "away_team_name": p.away_team_name,
        "model": p.model,
        "engine_version": p.engine_version,
        "status": p.status,
        "eligible": p.eligible,
        "frozen_at": p.frozen_at.isoformat() if p.frozen_at else None,
        "markets": p.markets_json,
        "modules": p.modules_json,
        "settled_at": p.settled_at.isoformat() if p.settled_at else None,
        "result": p.result_json,
    }


@router.get("/predictions")
def list_predictions(
    scan_date: date = Query(...),
    model: str | None = Query(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    q = select(CecchinoLivePrediction).where(CecchinoLivePrediction.scan_date == scan_date)
    if model:
        q = q.where(CecchinoLivePrediction.model == model)
    rows = db.scalars(q.order_by(CecchinoLivePrediction.kickoff, CecchinoLivePrediction.id)).all()
    return JSONResponse(content=jsonable_encoder({"items": [_to_dict(r) for r in rows]}))


@router.get("/fixture/{today_fixture_id}")
def fixture_predictions(today_fixture_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    """Previsioni registrate della partita; se la V2.5 non e' registrata la calcola al momento
    (anteprima non salvata, segnalata come tale)."""
    from app.models import Fixture
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.services.cecchino_live.registry import MODEL_V25, v25_pattern_signals, v25_payload
    from app.services.cecchino_live.v25_live import compute_v25_live

    rows = db.scalars(
        select(CecchinoLivePrediction).where(CecchinoLivePrediction.today_fixture_id == int(today_fixture_id))
    ).all()
    items = {r.model: {**_to_dict(r), "source": "registro"} for r in rows}
    if MODEL_V25 not in items:
        today = db.get(CecchinoTodayFixture, int(today_fixture_id))
        fixture = db.get(Fixture, int(today.local_fixture_id)) if today and today.local_fixture_id else None
        if fixture is not None:
            try:
                pre = compute_v25_live(db, fixture, today.kpi_panel_json)
                markets, modules = v25_payload(pre)
                modules["patterns"] = v25_pattern_signals(db, fixture, markets, modules)
                items[MODEL_V25] = {
                    "model": MODEL_V25,
                    "status": "preview",
                    "source": "anteprima_non_registrata",
                    "eligible": bool(pre["eligibility"].get("core_eligible")),
                    "markets": markets,
                    "modules": modules,
                }
            except Exception as exc:  # noqa: BLE001
                items[MODEL_V25] = {"model": MODEL_V25, "status": "error", "source": "anteprima", "error": str(exc)[:300]}
            finally:
                db.rollback()
    return JSONResponse(content=jsonable_encoder({"today_fixture_id": int(today_fixture_id), "models": items}))


@router.get("/observation")
def observation(scan_date: date = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    """Pattern Master accesi sulle partite del giorno (osservazione: nessuna giocata automatica)."""
    rows = db.scalars(
        select(CecchinoLivePrediction)
        .where(CecchinoLivePrediction.scan_date == scan_date, CecchinoLivePrediction.model == "V2.5")
        .order_by(CecchinoLivePrediction.kickoff, CecchinoLivePrediction.id)
    ).all()
    out = []
    for r in rows:
        patterns = (r.modules_json or {}).get("patterns") or {}
        for p in patterns.get("active") or []:
            result = ((r.result_json or {}).get("markets") or {}).get(p["target_key"]) if p["target_type"] == "market" else None
            out.append({
                "today_fixture_id": int(r.today_fixture_id),
                "kickoff": r.kickoff.isoformat() if r.kickoff else None,
                "league_name": r.league_name,
                "home_team_name": r.home_team_name,
                "away_team_name": r.away_team_name,
                "model": r.model,
                "status": r.status,
                "pattern": p,
                "result": result,
            })
    return JSONResponse(content=jsonable_encoder({"scan_date": scan_date.isoformat(), "items": out}))


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(live_summary(db)))


@admin_router.post("/record")
def record(scan_date: date = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(record_predictions(db, scan_date=scan_date)))


@admin_router.post("/settle")
def settle(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(settle_predictions(db)))
