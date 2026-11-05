"""Version 1 of the OCMP API, mounted at ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1.ai_evaluation import router as ai_evaluation_router
from app.api.v1.ai_mapping import router as ai_mapping_router
from app.api.v1.ai_objectives import router as ai_objectives_router
from app.api.v1.ai_settings import router as ai_settings_router
from app.api.v1.assessments import router as assessments_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.coverage import router as coverage_router
from app.api.v1.curriculum import router as curriculum_router
from app.api.v1.curriculum_edit import router as curriculum_edit_router
from app.api.v1.curriculum_import import router as curriculum_import_router
from app.api.v1.curriculum_objectives import router as curriculum_objectives_router
from app.api.v1.curriculum_versions import router as curriculum_versions_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.excel_imports import router as excel_imports_router
from app.api.v1.explorer import router as explorer_router
from app.api.v1.exports import router as exports_router
from app.api.v1.framework_packs import router as framework_packs_router
from app.api.v1.frameworks import router as frameworks_router
from app.api.v1.institution import router as institution_router
from app.api.v1.intended_repeats import router as intended_repeats_router
from app.api.v1.mapping import router as mapping_router
from app.api.v1.mapping_review import router as mapping_review_router
from app.api.v1.objective_checks import router as objective_checks_router
from app.api.v1.oidc import router as oidc_router
from app.api.v1.reports import router as reports_router
from app.api.v1.roles import router as roles_router
from app.api.v1.search import router as search_router
from app.api.v1.setup import router as setup_router
from app.api.v1.study_guides import router as study_guides_router
from app.api.v1.tagging import router as tagging_router
from app.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(oidc_router)
router.include_router(roles_router)
router.include_router(users_router)
router.include_router(audit_router)
router.include_router(institution_router)
router.include_router(ai_settings_router)
router.include_router(ai_mapping_router)
router.include_router(ai_evaluation_router)
router.include_router(ai_objectives_router)
router.include_router(curriculum_router)
router.include_router(curriculum_edit_router)
router.include_router(curriculum_objectives_router)
router.include_router(assessments_router)
router.include_router(curriculum_versions_router)
router.include_router(objective_checks_router)
router.include_router(study_guides_router)
router.include_router(tagging_router)
router.include_router(framework_packs_router)
router.include_router(frameworks_router)
router.include_router(mapping_router)
router.include_router(mapping_review_router)
router.include_router(search_router)
router.include_router(coverage_router)
router.include_router(dashboard_router)
router.include_router(reports_router)
router.include_router(intended_repeats_router)
router.include_router(curriculum_import_router)
router.include_router(excel_imports_router)
router.include_router(exports_router)
router.include_router(explorer_router)
router.include_router(setup_router)
