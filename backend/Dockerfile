# Curriculum in Context Backend Dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies only (cached until pyproject.toml changes).
# A stub package lets the build backend resolve metadata; the project itself
# is uninstalled afterwards and loaded from /app via PYTHONPATH.
COPY pyproject.toml README.md ./
RUN mkdir app && touch app/__init__.py \
    && pip install --no-cache-dir . \
    && pip uninstall -y ocmp-backend \
    && rm -rf app

# Copy application code
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application. Forwarded headers are handled by the app, which only
# trusts the proxies in TRUSTED_PROXIES, so uvicorn's own handling is off.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
