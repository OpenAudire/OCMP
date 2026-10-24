"""Version 1 of the OCMP API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.oidc import router as oidc_router
from app.api.v1.roles import router as roles_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(oidc_router)
router.include_router(roles_router)
router.include_router(users_router)
