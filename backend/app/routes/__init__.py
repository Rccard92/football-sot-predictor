from fastapi import APIRouter, Depends

from app.core.admin_session import require_admin_session_for_writes

from app.routes import (
    api_usage,
    audit,
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
    cecchino_live,
    cecchino_v3,
    cecchino_v4,
    cecchino_v5,
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
# router /admin: sessione admin obbligatoria per POST/PUT/PATCH/DELETE (20/10/2026); le letture restano libere
_ADMIN_WRITES = [Depends(require_admin_session_for_writes)]
api_router.include_router(health.router, tags=["health"])
api_router.include_router(audit.router)
api_router.include_router(admin.router, tags=["admin"], dependencies=_ADMIN_WRITES)
api_router.include_router(api_usage.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_debug_player_db.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_debug_team_shot_stats.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_ingest.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_data_health.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_session_auth.router)
api_router.include_router(admin_sportapi.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_bookmakers.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_competition_bookmakers.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_competitions.router, dependencies=_ADMIN_WRITES)
api_router.include_router(admin_competition_ingest.router, dependencies=_ADMIN_WRITES)
api_router.include_router(competitions.router)
api_router.include_router(cecchino_admin.router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_kpi_signals.router)
api_router.include_router(cecchino_kpi_signals.admin_router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_kpi_signals.validation_admin_router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_module_monitoring.router)
api_router.include_router(cecchino_module_monitoring_backfill.admin_router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_module_monitoring_backfill.status_router)
api_router.include_router(cecchino_research.router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_v3.router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_v4.router)
api_router.include_router(cecchino_v4.admin_router)
api_router.include_router(cecchino_v5.router)
api_router.include_router(master_pattern.router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_signals.router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_today.router)
api_router.include_router(cecchino_today.admin_router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_bet_builder.router)
api_router.include_router(cecchino_lab.router)
api_router.include_router(cecchino_lab.admin_router, dependencies=_ADMIN_WRITES)
api_router.include_router(cecchino_run_v2.router)
api_router.include_router(cecchino_run_v2.admin_router)
api_router.include_router(cecchino_run_v25.router)
api_router.include_router(cecchino_run_v25.admin_router)
api_router.include_router(cecchino_live.router)
api_router.include_router(cecchino_live.admin_router)
api_router.include_router(cecchino_home_wins.router)
