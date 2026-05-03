from fastapi import APIRouter

from app.routes import admin, backtest, dashboard, features, health, ingestion, predictions

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(ingestion.router)
api_router.include_router(dashboard.router)
api_router.include_router(features.router)
api_router.include_router(predictions.router)
api_router.include_router(backtest.router)
