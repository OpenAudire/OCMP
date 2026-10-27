# ADR 041: Encrypted Secrets at Rest and Key Rotation

## Status

Accepted (Slice 1.14). The brief (section 12) asks for "secrets encrypted at rest (connector
credentials, AI keys) using a key from the environment". This ADR decides how. It is used first for
AI provider API keys (ADR 042); the Phase 2 connectors will use the same box.

## Context

An AI provider API key can spend the institution's money. It must be entered on the admin screen
(not in a file on the server), stored so that a database backup or a read-only SQL slip does not
hand it over, and never come back out through the API, the audit log or a log line. An operator
must also be able to change the encryption key without losing the stored keys.

## Decision

### Library

`cryptography` (added to `pyproject.toml` as a direct dependency; it was already installed as a
dependency of `joserfc`, which this project uses for OIDC). Its **Fernet** recipe is a vetted,
authenticated construction (AES-128-CBC with an HMAC-SHA256 tag, a random IV and a timestamp), so
a changed value is detected and refused. No encryption is written by hand.

### Where the key comes from

- `SECRETS_ENCRYPTION_KEYS`: one or more Fernet keys, comma-separated, **newest first**
  (`python -m app.cli new-encryption-key` prints one). Empty by default.
- A key **derived from `SECRET_KEY`** (HKDF-SHA256, fixed context string `ocmp secret store v1`)
  is always added **last, for reading only**.

So an install that never sets the variable works with only `SECRET_KEY` (which an operator must
already protect), and an install that sets it later keeps reading what it stored before. The
choice between "derive from `SECRET_KEY`" and "a dedicated setting" is therefore "both": the
dedicated setting is the recommended way, the derived key is the safe default.

Trade-off, recorded for review: with only the derived key, changing `SECRET_KEY` makes stored keys
unreadable (the screen says so and the admin types them again). Operators who rotate `SECRET_KEY`
should set `SECRETS_ENCRYPTION_KEYS` first.

### Stored format

`ocmp1:<key id>:<Fernet token>`. The key id is the first 8 hex characters of a hash of the key,
which does not reveal the key. It tells `rotate-secrets` which values are old, and lets an error say
"the key that encrypted this secret is not configured" rather than a bare failure.

### Rotation

1. `python -m app.cli new-encryption-key`, put the result at the **front** of
   `SECRETS_ENCRYPTION_KEYS` (keep the old one after it), restart.
2. `python -m app.cli rotate-secrets` re-encrypts every stored secret with the newest key (through
   the ORM, audited as `secrets.rotate`, naming the column and never the value). It reports secrets
   it cannot read and leaves them as they were (exit code 1).
3. When it reports nothing unread, the old key can be removed.

### Never out

- The API schema has no field that can carry a key; keys are accepted as `SecretStr` and returned
  only as a status (`not_set`, `set`, `unreadable`) with the time it was set. No last-four-characters
  hint is stored or shown: a hint needs the plaintext or a second column, and "set" is enough.
- `AIProviderConfig.api_key_encrypted` is in `__audit_exclude__`: an audit entry records that the
  column changed, never its value.
- Pydantic validation errors do not echo input (`hide_input_in_errors`), so a wrongly typed
  `SECRETS_ENCRYPTION_KEYS` or password is not printed into a log.
- The decrypted key lives in memory only for the duration of a provider call and is scrubbed from
  provider error text before that is stored or shown.
- Keys are never in tests, fixtures or the repository: tests use obvious placeholders.

## Consequences

- Backups contain only ciphertext. Restoring a backup onto a server with different keys leaves the
  stored keys unreadable; the admin screen shows this and asks for the keys again. The backup guide
  says to keep `SECRET_KEY` and `SECRETS_ENCRYPTION_KEYS` with the backup.
- The Fernet key is 128-bit AES plus a separate 128-bit HMAC key; this is the library's choice.
- Environment variables `AI_ANTHROPIC_API_KEY`, `AI_OPENAI_API_KEY` and the other `AI_*` provider
  settings from Phase 0 are removed (they were read but never used); keys are entered on the screen.
