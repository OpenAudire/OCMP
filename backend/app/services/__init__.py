"""Business logic services package."""

# Importing the audit service registers the session hook that records every
# change to audited models, wherever services are used (API, worker, commands).
from app.services import audit  # noqa: F401
