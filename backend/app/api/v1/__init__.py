"""Version 1 of the OCMP API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
