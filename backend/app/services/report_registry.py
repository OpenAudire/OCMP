"""The reports that can be shown and exported (Slices 1.22 to 1.24, ADR 051): a name and the
function that builds its document. A new report is added here."""

from app.services.report_context import Builder
from app.services.report_docs import build_coverage, build_gaps
from app.services.report_docs_credits import build_credits
from app.services.report_docs_curriculum import build_redundancy, build_traceability
from app.services.report_docs_teaching import (
    build_assessment_methods,
    build_formats,
    build_relationship,
    build_role_balance,
)

REPORTS: dict[str, Builder] = {
    "coverage": build_coverage,
    "gaps": build_gaps,
    "redundancy": build_redundancy,
    "traceability": build_traceability,
    "formats": build_formats,
    "relationship": build_relationship,
    "role-balance": build_role_balance,
    "assessments": build_assessment_methods,
    "credits": build_credits,
}
