# ADR 037: Deleting Unused Frameworks and Accounts, and End-to-End Hygiene

## Status

Accepted (Slice 1.10a). Builds on ADR 012 (permissions), ADR 017 (audit log) and ADR 036 (pack
import).

## Context

The end-to-end journeys import framework packs and create an account, and these stayed on the
local demo stack run after run. Frameworks had no delete endpoint and accounts could not be
deleted. Raw SQL against a stack would bypass the audit log, which the project forbids, and a
separate e2e stack (second compose project, ports, demo data, admin account) is a heavy extra to
keep in step.

## Decision

- **`DELETE /api/v1/frameworks/{id}`** (`frameworks.manage`, instance): soft-deletes a framework
  version (audit label `framework.delete`). It answers 409 when an objective is mapped to one of
  its items, a review is assigned on it, or a newer live version has a crosswalk from it; 404 for
  a missing or deleted one. The items stay with the hidden row. It frees the key and version for
  a new import. Tag lists and scales that a pack created are separate and are deleted on their
  own (tag lists already can be).
- **`DELETE /api/v1/users/{id}`** (`users.manage`): the account's email and name are replaced
  (`deleted-<id>@deleted.invalid`, "Deleted user"), the password hash is cleared, role
  assignments and linked sign-in identities are removed through the ORM, sessions are revoked
  and the row is soft-deleted (audit label `user.delete`). Not your own account (409), not the
  last platform admin (409). The row stays so authorship and the audit log keep pointing at a
  person-less record; the address can be used again. This is the minimal deletion the journeys
  need, not the full POPIA export and deletion flow of the brief, which is still to come.
- **End-to-end journeys clean up after themselves**: the framework-import journey deletes the
  framework and tag list it made; the tagging journeys delete their list even when they fail;
  a Playwright teardown project (`cleanup.teardown.ts`) deletes the test lecturer after the
  run. The platform admin that signs in for the tests is created by the operator (README), not
  by the tests, and stays. No separate e2e database was needed.

## Consequences

- A framework that has mappings cannot be deleted; retiring it is the way (status), and there is
  still no screen for deleting (the framework library is Slice 1.11).
- A deleted user's old email address no longer appears anywhere; audit entries keep the user id.
- The data inventory notes the anonymisation on deletion.
