from fastapi import APIRouter

from loom.api.v1.annotations import router as annotations_router
from loom.api.v1.assets import router as assets_router
from loom.api.v1.audit import router as audit_router
from loom.api.v1.auth import router as auth_router
from loom.api.v1.cases import router as cases_router
from loom.api.v1.clusters import router as clusters_router
from loom.api.v1.conflicts import router as conflicts_router
from loom.api.v1.custody import router as custody_router
from loom.api.v1.duplicates import router as duplicates_router
from loom.api.v1.exports import router as exports_router
from loom.api.v1.first_run import router as first_run_router
from loom.api.v1.geo import router as geo_router
from loom.api.v1.health import router as health_router
from loom.api.v1.integrity import router as integrity_router
from loom.api.v1.mfa import router as mfa_router
from loom.api.v1.ocr import router as ocr_router
from loom.api.v1.organizations import router as organizations_router
from loom.api.v1.plugins import router as plugins_router
from loom.api.v1.provenance import router as provenance_router
from loom.api.v1.redactions import router as redactions_router
from loom.api.v1.scenes import router as scenes_router
from loom.api.v1.search import router as search_router
from loom.api.v1.shared_evidence import router as shared_evidence_router
from loom.api.v1.timeline import router as timeline_router
from loom.api.v1.transcripts import router as transcripts_router
from loom.api.v1.workflows import router as workflows_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(audit_router)
api_router.include_router(first_run_router)
api_router.include_router(auth_router)
api_router.include_router(mfa_router)
api_router.include_router(cases_router)
api_router.include_router(assets_router)
api_router.include_router(annotations_router)
api_router.include_router(timeline_router)
api_router.include_router(clusters_router)
api_router.include_router(conflicts_router)
api_router.include_router(exports_router)
api_router.include_router(geo_router)
api_router.include_router(ocr_router)
api_router.include_router(scenes_router)
api_router.include_router(search_router)
api_router.include_router(transcripts_router)
api_router.include_router(duplicates_router)
api_router.include_router(provenance_router)
api_router.include_router(redactions_router)
api_router.include_router(organizations_router)
api_router.include_router(shared_evidence_router)
api_router.include_router(custody_router)
api_router.include_router(integrity_router)
api_router.include_router(plugins_router)
api_router.include_router(workflows_router)
