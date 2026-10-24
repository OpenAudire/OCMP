# ADR 005: API Versioning

## Status

Accepted

## Context

OCMP exposes a REST API used by:
- The frontend application
- External integrations (LTI, webhooks)
- API token access for automation

We need a versioning strategy that allows evolution without breaking clients.

## Decision

Use **URL path versioning** with the prefix `/api/v1/`.

### Structure

```
/api/v1/auth/login
/api/v1/programmes
/api/v1/programmes/{id}/modules
/api/v1/frameworks
/api/v1/mappings
```

### Non-versioned endpoints

```
/health          # Health check
/ready           # Readiness check
/api/docs        # OpenAPI documentation
/api/openapi.json
```

### Versioning rules

1. Breaking changes require a new version (v2, v3)
2. Additive changes (new fields, new endpoints) are allowed within a version
3. Deprecation warnings in response headers before removal
4. Support at least one previous version during transition
5. Version in URL, not headers (easier to test, cache, debug)

## Rationale

1. **URL versioning**: Most explicit, easy to understand and implement
2. **v1 prefix**: Sets expectation that API may evolve
3. **Separate health endpoints**: Infrastructure checks don't need versioning

## Consequences

- All API routers mounted under `/api/v1/`
- OpenAPI spec includes version in paths
- Frontend API client uses versioned base URL
- Future versions can coexist during migration
