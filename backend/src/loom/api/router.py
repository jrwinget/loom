from fastapi import APIRouter

from loom.api.v1.auth import router as auth_router
from loom.api.v1.cases import router as cases_router
from loom.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(cases_router)
