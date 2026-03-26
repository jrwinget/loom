from fastapi import APIRouter

from loom.api.v1.annotations import router as annotations_router
from loom.api.v1.assets import router as assets_router
from loom.api.v1.auth import router as auth_router
from loom.api.v1.cases import router as cases_router
from loom.api.v1.exports import router as exports_router
from loom.api.v1.health import router as health_router
from loom.api.v1.timeline import router as timeline_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(cases_router)
api_router.include_router(assets_router)
api_router.include_router(annotations_router)
api_router.include_router(timeline_router)
api_router.include_router(exports_router)
