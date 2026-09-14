from fastapi import APIRouter

from app.routes import (
    api_usage,
    cecchino_admin,
    cecchino_kpi_signals,
    cecchino_module_monitoring,
    cecchino_module_monitoring_backfill,
    cecchino_research,
    cecchino_signals,
    cecchino_today,
    cecchino_bet_builder,
    cecchino_lab,
    cecchino_run_v2,
    cecchino_run_v25,
    cecchino_v3,
    master_pattern,
    cecchino_home_wins,
    admin,
    admin_bookmakers,
    admin_competition_bookmakers,
    admin_competition_ingest,
    admin_competitions,
    admin_debug_player_db,
    admin_data_health,
    admin_debug_team_shot_stats,
    admin_ingest,
    admin_session_auth,
    admin_sportapi,
    competitions,
    health,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(api_usage.router)
api_router.include_router(admin_debug_player_db.router)
api_router.include_router(admin_debug_team_shot_stats.router)
api_router.include_router(admin_ingest.router)
api_router.include_router(admin_data_health.router)
api_router.include_router(admin_session_auth.router)
api_router.include_router(admin_sportapi.router)
api_router.include_router(admin_bookmakers.router)
api_router.include_router(admin_competition_bookmakers.router)
api_router.include_router(admin_competitions.router)
api_router.include_router(admin_competition_ingest.router)
api_router.include_router(competitions.router)
api_router.include_router(cecchino_admin.router)
api_router.include_router(cecchino_kpi_signals.router)
api_router.include_router(cecchino_kpi_signals.admin_router)
api_router.include_router(cecchino_kpi_signals.validation_admin_router)
api_router.include_router(cecchino_module_monitoring.router)
api_router.include_router(cecchino_module_monitoring_backfill.admin_router)
api_router.include_router(cecchino_module_monitoring_backfill.status_router)
api_router.include_router(cecchino_research.router)
api_router.include_router(cecchino_v3.router)
api_router.include_router(master_pattern.router)
api_router.include_router(cecchino_signals.router)
api_router.include_router(cecchino_today.router)
api_router.include_router(cecchino_today.admin_router)
api_router.include_router(cecchino_bet_builder.router)
api_router.include_router(cecchino_lab.router)
api_router.include_router(cecchino_lab.admin_router)
api_router.include_router(cecchino_run_v2.router)
api_router.include_router(cecchino_run_v2.admin_router)
api_router.include_router(cecchino_run_v25.router)
api_router.include_router(cecchino_run_v25.admin_router)
api_router.include_router(cecchino_home_wins.router)
