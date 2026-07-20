"""Route Monitoraggio Moduli Cecchino — overview + analysis pack."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.cecchino.cecchino_module_monitoring_exports import (
    VALID_MODULE_KEYS,
    build_module_analysis_pack_audit,
    build_module_analysis_pack_zip,
    build_module_export_status,
    build_module_monitoring_overview,
    build_module_rows_csv,
    build_module_summary_payload,
    build_modules_analysis_packs_audit,
)
from app.services.cecchino.cecchino_module_monitoring_reconciliation import (
    build_purchasability_evaluation_cardinality_report,
)

router = APIRouter(
    prefix="/cecchino/module-monitoring",
    tags=["cecchino-module-monitoring"],
)


@router.get("/overview")
def module_monitoring_overview(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_module_monitoring_overview(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/analysis-packs-audit")
def module_monitoring_all_analysis_packs_audit(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    payload = build_modules_analysis_packs_audit(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        market_key=market_key,
        include_rows=include_rows,
        include_debug=include_debug,
        source_cohort_filter=source_cohort or "all",
    )
    return JSONResponse(content=jsonable_encoder(payload))


# IMPORTANT: dedicated paths BEFORE /{module_key} routes to avoid conflicts
@router.get("/purchasability-cardinality")
def purchasability_cardinality_report(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    payload = build_purchasability_evaluation_cardinality_report(
        db,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
    )
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/balance-v5/empirical/health")
def balance_empirical_health(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_health,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_health(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


@router.get("/balance-v5/empirical/summary")
def balance_empirical_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_summary,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_summary(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


@router.get("/balance-v5/empirical/rows")
def balance_empirical_rows(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    evaluation_status: str | None = Query(None),
    f36_class: str | None = Query(None),
    dominance_class: str | None = Query(None),
    draw_credibility_class: str | None = Query(None),
    gap_class: str | None = Query(None),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        query_balance_empirical_rows,
    )

    return JSONResponse(
        content=jsonable_encoder(
            query_balance_empirical_rows(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
                evaluation_status=evaluation_status,
                f36_class=f36_class,
                dominance_class=dominance_class,
                draw_credibility_class=draw_credibility_class,
                gap_class=gap_class,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.get("/balance-v5/empirical/target-contract")
def balance_empirical_target_contract():
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_target_contract,
    )

    return JSONResponse(content=jsonable_encoder(build_balance_empirical_target_contract()))


@router.get("/balance-v5/empirical/cardinality")
def balance_empirical_cardinality(
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    source_cohort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    from app.services.cecchino.cecchino_balance_v5_empirical import (
        build_balance_empirical_cardinality,
    )

    return JSONResponse(
        content=jsonable_encoder(
            build_balance_empirical_cardinality(
                db,
                date_from=date_from,
                date_to=date_to,
                competition_id=competition_id,
                source_cohort=source_cohort,
            )
        )
    )


@router.get("/{module_key}/analysis-pack-audit")
def module_monitoring_analysis_pack_audit(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_analysis_pack_audit(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            include_debug=include_debug,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/{module_key}/export-status")
def module_monitoring_export_status(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_export_status(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/{module_key}/analysis-pack.zip")
def module_monitoring_analysis_pack(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_analysis_pack_zip(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            include_rows=include_rows,
            include_debug=include_debug,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{module_key}/summary.json")
def module_monitoring_summary_json(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        payload = build_module_summary_payload(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    raw = jsonable_encoder(payload)
    body = __import__("json").dumps(raw, ensure_ascii=False, allow_nan=False).encode(
        "utf-8"
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="SOT_MONITOR_{module_key}_summary.json"'
            )
        },
    )


@router.get("/{module_key}/rows.csv")
def module_monitoring_rows_csv(
    module_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    competition_id: int | None = Query(None),
    market_key: str | None = Query(None),
    include_rows: bool = Query(True),
    include_debug: bool = Query(False),
    source_cohort: str | None = Query(None, description="Cohort filter: all, prospective, historical_persisted_verified, etc."),
    db: Session = Depends(get_db),
):
    _ = include_rows, include_debug
    if module_key not in VALID_MODULE_KEYS:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    try:
        data, filename = build_module_rows_csv(
            db,
            module_key=module_key,
            date_from=date_from,
            date_to=date_to,
            competition_id=competition_id,
            market_key=market_key,
            source_cohort_filter=source_cohort or "all",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown_module_key")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
