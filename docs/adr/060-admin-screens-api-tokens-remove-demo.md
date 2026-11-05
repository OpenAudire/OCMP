# ADR 060: Administration Screens, Personal API Tokens and Removing the Demo Data

## Status

Accepted (Slice 1.30). Builds on ADR 011 (accounts are never matched by email), ADR 012 (permissions are
checked on the server), ADR 017 (audit log) and the roles of ADR 013.

## Context

Until now users, roles, role assignments and the institution's settings could be changed only through the API
or the command line. Phase 1 plan decision 8 promised personal API tokens in Phase 1, and the demo data had
no way out once an installation went into real use.

## Decision

**Administration screens** (Admin > People, Roles, Institution settings) are a front for the API that already
exists. They add no permission and no rule: every check is the server's (`users.manage`, `roles.manage`,
`settings.manage`, `roles.assign` and the rule that nobody gives a role they could not hold themselves), and
the screens only follow it.

* *People*: search and page the accounts, add a local account, rename, deactivate and reactivate, delete.
  Deactivating ends the person's sessions and, now, revokes their API tokens. You cannot do either to your own
  account, and the last platform admin is protected (both by the server).
* *One person*: their roles by place, and giving a role at the institution, a faculty or a programme (the
  roles that fit that place; an end date is required for roles that ask for one). Roles for one module or
  session are given on the curriculum screens, where the module can be named.
* *Roles*: the built-in roles can be read, not changed; custom roles can be made, changed and deleted.
* *Institution settings*: terminology, profiles, the default taxonomy scale and the mapping, credits, quality
  and coverage policies. **Each block saves by itself** and sends the whole block; the server validates ranges
  and the change is audited. The ranges are not duplicated as the rule: the screen shows them as hints and the
  server answers with its reason when a value is refused.

**Personal API tokens.** A person makes a token on the Account page.

* The token (`ocmp_` and 256 bits) is shown **once**; only its SHA-256 hash is stored, with a visible prefix of
  twelve characters so tokens can be told apart. A token has a name, a **scope** (`read`: safe methods only;
  `write`: any method) and an expiry of 1 to 365 days (default 90). A person may hold 20 active tokens.
* A token carries its owner's permissions, **narrowed** by its scope, never widened. It is sent as
  `Authorization: Bearer ...`. A request with a session cookie keeps the cookie's rules (and CSRF); a request
  with only a bearer token needs no CSRF token because the browser never sends one by itself.
* A token **cannot** change a password or make or list tokens (those need a browser session,
  `SessionAuth`). A revoked, expired or unknown token, and the token of a deactivated or deleted account, is a
  401; a read token used to write is a 403.
* Making and revoking are audited (`api_token.create`, `api_token.revoke`) without the hash; using a token is
  not audited and updates `last_used_at` at most every five minutes. A person with `users.manage` can list and
  revoke anyone's tokens.
* Webhooks stay in Phase 2.

**Removing the demo data.** `python -m app.cli remove-demo` is a dry run; `--apply` removes. It finds the demo's
own things by their codes and keys (programme, faculty, framework key and version, tag list keys, the curriculum
office account's address, the gold set's name), so nothing with another code is touched. The removal runs in a
database savepoint that is rolled back for the dry run, so the list is exactly what would happen. It goes through
the ORM and is audited (`demo.remove`): the programme with every version and what is in it is soft-deleted, the
faculty only if no other programme is in it, the framework only if nothing else is mapped to it, tag lists only
if nothing else uses them (otherwise the list is kept and the command says so). The institution and the taxonomy
scales stay, because a real installation shares them.

## Not in this slice

* Assigning roles at a module or session from the People screen; editing a person's email address or password
  (the person does that themselves; an administrator can add a new account).
* Scopes finer than read and write; webhooks; a way to see which requests a token made.
* A screen for the audit log (it is read through the API).

## Consequences

* A leaked token is as powerful as its owner for its scope until it expires or is revoked; the lifetime limit,
  the read scope and the hash-only storage are the mitigations. The 256-bit token cannot be guessed, so failed
  bearer attempts are not rate limited.
* Settings can be changed by anyone with `settings.manage`; every change is in the audit log.
