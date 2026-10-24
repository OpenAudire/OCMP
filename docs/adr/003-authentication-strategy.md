# ADR 003: Authentication Strategy

## Status

Accepted

## Context

OCMP needs to support multiple authentication methods:
- Local accounts with email/password for smaller institutions
- OpenID Connect (OIDC) for enterprise SSO (Microsoft Entra ID, Google, etc.)
- SAML 2.0 for university identity providers (Phase 2)

## Decision

Implement a layered authentication system:

1. **Phase 0**: Local accounts + generic OIDC
2. **Phase 2**: Add SAML 2.0 support

### Local Accounts
- Email/password authentication
- Argon2id password hashing (memory-hard, side-channel resistant)
- Minimum 12 character passwords
- Email-based password reset with time-limited tokens
- Session cookies with CSRF protection

### OIDC
- Generic OIDC flow using discovery documents
- Support any compliant provider (Entra ID, Google, Keycloak, etc.)
- Auto-provisioning of users on first login
- Role mapping from OIDC claims (configurable)

### Sessions
- HTTP-only, secure, SameSite=Lax cookies
- 24-hour sliding expiration
- Session stored server-side in Redis
- CSRF token validation for state-changing requests

## Rationale

1. **Argon2id**: Current best practice for password hashing, recommended by OWASP
2. **Generic OIDC**: Works with most enterprise identity providers without custom code
3. **Session cookies**: Simpler than JWT for web apps, easier to revoke
4. **SAML deferred**: More complex, less common for new deployments

## Consequences

- Users table stores password hash (nullable for SSO-only users)
- OIDC configuration stored per-institution
- Session middleware required on all authenticated routes
- CSRF middleware required for all POST/PUT/DELETE endpoints
