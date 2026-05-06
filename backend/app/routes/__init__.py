from fastapi import APIRouter

from app.routes import (
    admin,
    admin_data_health,
    admin_debug_player_stats,
    admin_ingest,
    admin_refresh,
    backtest,
    dashboard,
    features,
    health,
    h2h,
    ingestion,
    match_analysis,
    match_context,
    model,
    player_sot_profiles,
    predictions,
    standings,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(admin_debug_player_stats.router)
api_router.include_router(admin_ingest.router)
api_router.include_router(admin_refresh.router)
api_router.include_router(admin_data_health.router)
api_router.include_router(ingestion.router)
api_router.include_router(dashboard.router)
api_router.include_router(features.router)
api_router.include_router(predictions.router)
api_router.include_router(backtest.router)
api_router.include_router(player_sot_profiles.router)
api_router.include_router(h2h.router)
api_router.include_router(standings.router)
api_router.include_router(match_context.router)
api_router.include_router(model.router)
api_router.include_router(match_analysis.router)
