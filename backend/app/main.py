"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(
    title="OCMP API",
    description="Open Curriculum Mapping Platform API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness check endpoint."""
    return {"status": "ready"}
