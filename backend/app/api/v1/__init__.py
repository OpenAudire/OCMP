"""Version 1 of the OCMP API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.curriculum import router as curriculum_router
from app.api.v1.institution import router as institution_router
from app.api.v1.oidc import router as oidc_router
from app.api.v1.roles import router as roles_router
from app.api.v1.setup import router as setup_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(oidc_router)
router.include_router(roles_router)
router.include_router(users_router)
router.include_router(audit_router)
router.include_router(institution_router)
router.include_router(curriculum_router)
router.include_router(setup_router)
