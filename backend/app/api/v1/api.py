"""
Master API v1 Router.
Aggregates active endpoint routers under the /api/v1 version prefix.
Scope reduced for stabilization: invitations, api_keys, ingest, and usage disabled.
"""
from fastapi import APIRouter

from app.api.v1.routers.analytics import router as analytics_router
from app.api.v1.routers.analyze import router as analyze_router
from app.api.v1.routers.audit import router as audit_router
from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.calibration import router as calibration_router
from app.api.v1.routers.cameras import router as cameras_router
from app.api.v1.routers.eval import router as eval_router
from app.api.v1.routers.health import router as health_router
from app.api.v1.routers.incidents import router as incidents_router
from app.api.v1.routers.orgs import router as orgs_router
from app.api.v1.routers.privacy import router as privacy_router
from app.api.v1.routers.rules import router as rules_router
from app.api.v1.routers.scenarios import router as scenarios_router
from app.api.v1.routers.signals import router as signals_router
from app.api.v1.routers.sites import router as sites_router
from app.api.v1.routers.sos import router as sos_router
from app.api.v1.routers.stream import router as stream_router
from app.api.v1.routers.users import router as users_router
from app.api.v1.routers.zones import router as zones_router

# TODO [STABILIZATION]: Disabled routers kept in codebase for future phase
# from app.api.v1.routers.invitations import router as invitations_router
# from app.api.v1.routers.api_keys import router as api_keys_router
# from app.api.v1.routers.ingest import router as ingest_router
# from app.api.v1.routers.usage import router as usage_router

api_v1_router = APIRouter(prefix="/api/v1")

# Core active routes
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(orgs_router)
api_v1_router.include_router(sites_router)
api_v1_router.include_router(zones_router)
api_v1_router.include_router(cameras_router)
api_v1_router.include_router(rules_router)
api_v1_router.include_router(incidents_router)
api_v1_router.include_router(signals_router)
api_v1_router.include_router(scenarios_router)
api_v1_router.include_router(calibration_router)
api_v1_router.include_router(privacy_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(eval_router)
api_v1_router.include_router(stream_router)
api_v1_router.include_router(analyze_router)
api_v1_router.include_router(sos_router)
api_v1_router.include_router(analytics_router)
