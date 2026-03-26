from fastapi import APIRouter

from loom.api.v1.annotations import router as annotations_router
from loom.api.v1.assets import router as assets_router
from loom.api.v1.auth import router as auth_router
from loom.api.v1.cases import router as cases_router
from loom.api.v1.conflicts import router as conflicts_router
from loom.api.v1.duplicates import router as duplicates_router
from loom.api.v1.exports import router as exports_router
from loom.api.v1.health import router as health_router
from loom.api.v1.ocr import router as ocr_router
from loom.api.v1.scenes import router as scenes_router
from loom.api.v1.search import router as search_router
from loom.api.v1.timeline import router as timeline_router
from loom.api.v1.transcripts import router as transcripts_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(cases_router)
api_router.include_router(assets_router)
api_router.include_router(annotations_router)
api_router.include_router(timeline_router)
api_router.include_router(conflicts_router)
api_router.include_router(exports_router)
api_router.include_router(ocr_router)
api_router.include_router(scenes_router)
api_router.include_router(search_router)
api_router.include_router(transcripts_router)
api_router.include_router(duplicates_router)
