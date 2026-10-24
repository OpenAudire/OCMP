# ADR 006: Testing Strategy

## Status

Accepted

## Context

OCMP requires comprehensive testing to ensure:
- Permission logic is correct (security critical)
- Reports produce accurate numbers
- AI integration works correctly
- UI workflows function end-to-end

## Decision

### Backend Testing

**Framework**: pytest with pytest-asyncio

**Test types**:
1. **Unit tests**: Services, utilities, validators
2. **Integration tests**: API endpoints with database
3. **Permission tests**: Every role/scope combination

**Fixtures**: factory_boy for model factories

**Database**: PostgreSQL container in CI (not SQLite)
- Ensures pgvector compatibility
- Tests real database behavior
- Uses transactions for test isolation

**Coverage target**: ≥80% for services, permissions, and reports

### Frontend Testing

**Framework**: Vitest + Testing Library

**Test types**:
1. **Component tests**: Isolated component rendering
2. **Hook tests**: Custom hooks with renderHook
3. **E2E tests**: Playwright for critical journeys

**E2E journeys**:
- Login flow
- Build curriculum structure
- Import Excel
- AI mapping (mocked provider)
- Review queue workflow
- Coverage report
- Student explorer

### AI Testing

- Mock AI providers in unit/integration tests
- Recorded fixtures for deterministic responses
- Eval harness for real model testing (manual runs)

## Rationale

1. **Real PostgreSQL**: pgvector and full-text search behave differently from SQLite
2. **factory_boy**: Standard, well-documented model factory library
3. **Playwright**: Reliable, modern E2E testing with good debugging

## Consequences

- CI runs backend and frontend tests in parallel
- PostgreSQL service in GitHub Actions
- E2E tests run on PR merge (slower, more comprehensive)
- Test data factories maintained alongside models
