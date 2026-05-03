from fastapi import APIRouter

from app.routes import health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, tags=["health"])
