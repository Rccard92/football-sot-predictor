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
from app.models.cecchino_live_prediction import LIVE_STATUS_SETTLED, CecchinoLivePrediction
from app.services.cecchino_live.observation import group_active_patterns, group_outcome, observation_dashboard
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
    elif items[MODEL_V25].get("status") == "open" and not (items[MODEL_V25].get("modules") or {}).get("purchasability_index"):
        # previsione registrata prima dell'indice orchestratore: indice calcolato al momento (non salvato)
        today = db.get(CecchinoTodayFixture, int(today_fixture_id))
        fixture = db.get(Fixture, int(today.local_fixture_id)) if today and today.local_fixture_id else None
        if fixture is not None:
            try:
                _, preview_modules = v25_payload(compute_v25_live(db, fixture, today.kpi_panel_json))
                modules = dict(items[MODEL_V25].get("modules") or {})
                modules["purchasability_index"] = {**preview_modules["purchasability_index"], "source": "anteprima_non_registrata"}
                items[MODEL_V25] = {**items[MODEL_V25], "modules": modules}
            except Exception:  # noqa: BLE001
                pass
            finally:
                db.rollback()
    if "V3" not in items:
        items["V3"] = _v3_preview(db, int(today_fixture_id))
    if "V2" not in items:
        items["V2"] = _v2_preview(db, int(today_fixture_id))
    elif items["V2"].get("status") == "open" and not (
        (items["V2"].get("modules") or {}).get("patterns")
        and (items["V2"].get("modules") or {}).get("goal_intensity_pillars")
    ):
        # previsione registrata prima dei pattern V2 o del dettaglio Intensita' Goal:
        # le parti mancanti arrivano dai moduli calcolati al momento (non salvati)
        preview = _v2_preview(db, int(today_fixture_id))
        if preview.get("modules"):
            registered = items["V2"].get("modules") or {}
            merged = {**preview["modules"], **{k: v for k, v in registered.items() if v}}
            items["V2"] = {**items["V2"], "modules": merged, "modules_source": "anteprima_non_registrata"}
    from app.services.cecchino_live.pattern_signals import annotate_book_conditions

    for model, item in items.items():
        try:
            annotate_book_conditions(db, model, (item.get("modules") or {}).get("patterns"))
        except Exception:  # noqa: BLE001 - l'annotazione non deve mai rompere la scheda
            db.rollback()
    return JSONResponse(content=jsonable_encoder({"today_fixture_id": int(today_fixture_id), "models": items}))


def _v2_preview(db: Session, today_fixture_id: int) -> dict:
    """Moduli V2 (come nella RUN V2) e Pattern Master V2 calcolati al momento, non registrati."""
    from app.models import Fixture
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.services.cecchino_live.registry import v2_live_modules, v2_markets

    today = db.get(CecchinoTodayFixture, today_fixture_id)
    fixture = db.get(Fixture, int(today.local_fixture_id)) if today and today.local_fixture_id else None
    if fixture is None:
        return {"model": "V2", "status": "unavailable", "source": "anteprima", "reason": "no_fixture"}
    try:
        markets = v2_markets(today)
        modules = v2_live_modules(db, fixture, today, markets)
        return {
            "model": "V2",
            "status": "preview",
            "source": "anteprima_non_registrata",
            "eligible": True,
            "markets": markets,
            "modules": modules,
        }
    except Exception as exc:  # noqa: BLE001
        return {"model": "V2", "status": "error", "source": "anteprima", "error": str(exc)[:300]}
    finally:
        db.rollback()


def _v3_preview(db: Session, today_fixture_id: int) -> dict:
    """V3 estesa calcolata al momento (anteprima non registrata) o motivo per cui non c'e'."""
    from app.models import Fixture
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.services.cecchino_live.registry import v3_payload
    from app.services.cecchino_v3_live.engine import compute_for_fixtures

    today = db.get(CecchinoTodayFixture, today_fixture_id)
    fixture = db.get(Fixture, int(today.local_fixture_id)) if today and today.local_fixture_id else None
    if fixture is None:
        return {"model": "V3", "status": "unavailable", "source": "anteprima", "reason": "no_fixture"}
    try:
        res = compute_for_fixtures(db, [fixture]).get(int(fixture.id)) or {}
        if res.get("status") != "ok":
            return {
                "model": "V3",
                "status": "unavailable",
                "source": "anteprima",
                "reason": res.get("status") or "not_computable",
                "history": res.get("history"),
            }
        markets, modules = v3_payload(res, today.kpi_panel_json)
        from app.services.cecchino_v3_live.patterns import v3_pattern_signals

        modules["patterns"] = v3_pattern_signals(db, res, markets)
        return {
            "model": "V3",
            "status": "preview",
            "source": "anteprima_non_registrata",
            "eligible": bool(res.get("eligible")),
            "engine_version": res.get("engine_version"),
            "markets": markets,
            "modules": modules,
        }
    except Exception as exc:  # noqa: BLE001
        return {"model": "V3", "status": "error", "source": "anteprima", "error": str(exc)[:300]}
    finally:
        db.rollback()


@router.get("/fixture/{today_fixture_id}/lineups")
def fixture_lineups(today_fixture_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    """Formazioni ufficiali e assenti (API-Football) salvati dal cron pre-match."""
    from app.models.cecchino_today_fixture import CecchinoTodayFixture
    from app.models.fixture_lineup import FixtureLineup
    from app.models.fixture_missing_player import FixtureMissingPlayer
    from app.services.cecchino_live.prematch_lineups import PROVIDER

    today = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if today is None or not today.local_fixture_id:
        return JSONResponse(content={"today_fixture_id": int(today_fixture_id), "lineups": [], "missing": []})
    fid = int(today.local_fixture_id)
    lineups = db.scalars(select(FixtureLineup).where(FixtureLineup.fixture_id == fid)).all()
    missing = db.scalars(
        select(FixtureMissingPlayer).where(
            FixtureMissingPlayer.fixture_id == fid, FixtureMissingPlayer.provider_name == PROVIDER
        )
    ).all()
    return JSONResponse(
        content=jsonable_encoder(
            {
                "today_fixture_id": int(today_fixture_id),
                "lineups": [
                    {
                        "api_team_id": r.api_team_id,
                        "formation": r.formation,
                        "coach": r.coach_name,
                        "official": r.is_official,
                        "source": r.source,
                        "fetched_at": r.fetched_at,
                        "start_xi": r.start_xi,
                        "substitutes": r.substitutes,
                    }
                    for r in lineups
                ],
                "missing": [
                    {"side": m.team_side, "player": m.player_name, "type": m.external_type, "reason": m.reason}
                    for m in missing
                ],
            }
        )
    )


@router.get("/observation")
def observation(scan_date: date = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    """Pattern Master accesi sulle partite del giorno (osservazione: nessuna giocata automatica)."""
    rows = db.scalars(
        select(CecchinoLivePrediction)
        .where(CecchinoLivePrediction.scan_date == scan_date, CecchinoLivePrediction.model.in_(("V2", "V2.5", "V3")))
        .order_by(CecchinoLivePrediction.kickoff, CecchinoLivePrediction.id)
    ).all()
    out = []
    groups = []
    for r in rows:
        patterns = (r.modules_json or {}).get("patterns") or {}
        for g in group_active_patterns(patterns.get("active")):
            groups.append({
                "today_fixture_id": int(r.today_fixture_id),
                "kickoff": r.kickoff.isoformat() if r.kickoff else None,
                "league_name": r.league_name,
                "home_team_name": r.home_team_name,
                "away_team_name": r.away_team_name,
                "model": r.model,
                "status": r.status,
                "group": g,
                "result": group_outcome(r, g) if r.status == LIVE_STATUS_SETTLED else None,
            })
        for p in patterns.get("active") or []:
            if p["target_type"] == "market":
                result = ((r.result_json or {}).get("markets") or {}).get(p["target_key"])
            else:
                result = ((r.result_json or {}).get("patterns") or {}).get(str(p["id"]))
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
    return JSONResponse(content=jsonable_encoder({"scan_date": scan_date.isoformat(), "items": out, "groups": groups}))


@router.get("/observation-dashboard")
def observation_dashboard_route(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Osservazione live: precisione dei motori e rendimento dei pattern Master nel tempo."""
    return JSONResponse(content=jsonable_encoder(observation_dashboard(db, date_from=date_from, date_to=date_to)))


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(live_summary(db)))


@admin_router.post("/record")
def record(scan_date: date = Query(...), db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(record_predictions(db, scan_date=scan_date)))


@admin_router.post("/settle")
def settle(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(settle_predictions(db)))
