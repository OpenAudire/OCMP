# Configuration

Curriculum in Context reads its settings from `deploy/.env`, created from `deploy/.env.example` during
[installation](install.md). After changing `.env`, apply it with:

```bash
docker compose up -d
```

Settings that the institution manages in the application (terminology, profiles, mapping
review policy) are not in `.env`; see [Admin basics](../admin/basics.md).

## Required

| Setting | Meaning |
|---|---|
| `SECRET_KEY` | Random secret of at least 32 characters (`openssl rand -hex 32`). Protects sessions against cross-site request forgery and derives the setup token. After changing it, people must sign in again before they can save changes. |
| `POSTGRES_PASSWORD` | Database password, set when the database is first created. Letters and digits only. |
| `POSTGRES_USER`, `POSTGRES_DB` | Database user and name. Default `ocmp`. |
| `DATABASE_URL` | Built from the three values above; leave as it is. |
| `REDIS_URL` | Default `redis://redis:6379/0`; leave as it is. |

## Site address

| Setting | Default | Meaning |
|---|---|---|
| `DOMAIN` | `localhost` | DNS name Caddy serves and gets a certificate for. |
| `PUBLIC_URL` | `https://<DOMAIN>` | Address users type, used in email links and the single sign-on redirect address. |
| `ENVIRONMENT` | `production` | `production` or `development`. In production, saving an AI provider key needs `SECRETS_ENCRYPTION_KEYS` (below). Leave it at `production` on a server; a developer's `.env` sets `development`. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `TIMEZONE` | `Africa/Johannesburg` | IANA time zone name. Decides which day the committee dashboard's daily figures belong to, and the `scheduler` service records them at 23:55 in this zone. An unknown name stops the application at start. |
| `TRUSTED_PROXIES` | `caddy` | Proxies whose `X-Forwarded-For` header is believed (IPs, CIDR networks or hostnames, comma-separated). Only change it if another proxy or load balancer sits in front of Caddy. |

## Sign-in and sessions

| Setting | Default | Meaning |
|---|---|---|
| `SESSION_EXPIRE_HOURS` | `24` | Sessions end after this long without activity. |
| `SESSION_COOKIE_SECURE` | `true` | Keep `true`; `false` only for local development over plain HTTP. |
| `LOGIN_RATE_LIMIT_PER_IP` | `20` | Sign-in attempts per client address per 15 minutes; more are refused for a while. |
| `LOGIN_DELAY_FREE_FAILURES` | `3` | Failed sign-ins for one account before attempts are slowed down. |
| `LOGIN_DELAY_BASE_SECONDS` | `1` | First delay; doubles with each further failure. |
| `LOGIN_DELAY_MAX_SECONDS` | `20` | Longest delay. Accounts are never locked. |

Passwords must have 12 to 256 characters and must not be the email address.

## Email

Needed for password reset and "password changed" notices.

| Setting | Default | Meaning |
|---|---|---|
| `SMTP_HOST` | (none) | SMTP server. Email is off while this or `SMTP_FROM_EMAIL` is empty. |
| `SMTP_PORT` | `587` | Usually 587 (STARTTLS) or 465 (implicit TLS). |
| `SMTP_USER`, `SMTP_PASSWORD` | (none) | Leave empty if the server accepts mail without signing in. |
| `SMTP_FROM_EMAIL` | (none) | Sender address. |
| `SMTP_FROM_NAME` | `Curriculum in Context` | Sender name. |
| `SMTP_TLS` | `true` | STARTTLS. |
| `SMTP_SSL` | `false` | Implicit TLS; takes precedence over `SMTP_TLS`. |
| `PASSWORD_RESET_TOKEN_MINUTES` | `60` | How long a reset link works. |

## Single sign-on (OpenID Connect)

`OIDC_ENABLED`, `OIDC_PROVIDER_NAME`, `OIDC_DISCOVERY_URL`, `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET`, `OIDC_SCOPES`, `OIDC_AUTO_PROVISION`: see
[Single sign-on](../admin/sso.md).

## Retention

| Setting | Default | Meaning |
|---|---|---|
| `AUDIT_LOG_RETENTION_DAYS` | `0` | Audit log entries older than this are deleted by `purge-audit-log`. `0` keeps them forever. |
| `PACK_MAX_UPLOAD_MB` | `10` | Largest framework pack file the import screen accepts, in megabytes (1 to 200). Bigger files are refused before they are read. |
| `PACK_MAX_ITEMS` | `20000` | Most items in one framework pack. A pack with more is refused with a message; split it or raise the limit. |
| `AI_CALL_RETENTION_DAYS` | `365` | Stored AI prompts and responses older than this are cleared by `purge-ai-content`. Run records and counts are kept. `0` keeps them. |

The purge commands are run on a schedule; see [Admin basics](../admin/basics.md#retention).

## Secrets

| Setting | Default | Meaning |
|---|---|---|
| `SECRETS_ENCRYPTION_KEYS` | empty | Keys that encrypt stored secrets (AI provider keys), comma-separated, **newest first**. Make one with `docker compose exec api python -m app.cli new-encryption-key`. **Required in production** (`ENVIRONMENT=production`, the default): while it is empty a new AI provider key cannot be saved, the AI settings screen shows a warning and the server logs one at every start (it still starts). Only with `ENVIRONMENT=development` does an empty value fall back to a key derived from `SECRET_KEY`. A key derived from `SECRET_KEY` is always kept as a read-only fallback, so values stored before this was set stay readable until `rotate-secrets` re-encrypts them. See [AI settings](../admin/ai.md#encryption-keys-and-rotation). |

AI providers, their keys, budgets and local-only mode are set on the admin AI settings screen, not
in `.env`. The `AI_ENABLED`, `AI_ANTHROPIC_API_KEY`, `AI_OPENAI_*`, `AI_OLLAMA_BASE_URL` and
`AI_MONTHLY_BUDGET_CAP` settings of earlier templates were never read and have been removed; delete
them from your `.env` if present (they are ignored).

## Reserved for later phases

`CONNECTOR_ENCRYPTION_KEY` is read but not used yet: the Brightspace connector is Phase 2. Leave
it as it is in the template.

## Embeddings

Optional (ADR 044); see [Embeddings](embeddings.md) for the whole procedure.

| Setting | Default | Meaning |
|---|---|---|
| `EMBEDDINGS_LOCAL` | `false` | Turn meaning-based matching on. Set it for the `api` and the `worker` (both read `.env`). Everything works without it |
| `EMBEDDINGS_LOCAL_URL` | `http://embeddings:8080` | Where the embeddings server is. It must be on this server or a private network; a public address is refused |
| `EMBEDDINGS_MODEL_ID` | `intfloat/multilingual-e5-small` | Read by Compose for the `embeddings` service: a model id, or a folder inside its volume for a server without internet access. Do not change it without asking |
| `OCMP_EMBEDDINGS_IMAGE` | the pinned CPU image | Set the ARM image on an ARM server (digest in `.env.example`) |

The Phase 0 settings `EMBEDDINGS_OPENAI` and `EMBEDDINGS_OPENAI_MODEL` were never used and are
removed; delete them from your `.env` if present (they are ignored). Cloud embeddings are not
offered in Phase 1.

## Images

| Setting | Default | Meaning |
|---|---|---|
| `OCMP_BACKEND_IMAGE` | `ocmp-backend:local` | Image for `api`, `worker` and `migrate`. The default is built from the checkout; set a released image to skip the build (see [Upgrade](upgrade.md#use-released-images)). |
| `OCMP_WEB_IMAGE` | `ocmp-web:local` | Image for `web`, as above. |

## Optional services

These Docker Compose profiles are off unless started with `--profile <name>`:

| Profile | Service | State |
|---|---|---|
| `mailpit` | Catches all outgoing email, web UI on `http://localhost:8025` | Development only |
| `embeddings` | Local embedding model (ADR 044): about 1 GB image, 470 MB model, about 3 GB of memory | Optional; [turn it on](embeddings.md#turn-it-on) with `EMBEDDINGS_LOCAL=true` |
| `ollama` | Local language model | For Phase 1 AI features; not used yet |

## Backup scripts

The [backup script](backup-restore.md) reads two environment variables of its own (not from
`.env`): `BACKUP_DIR` (default `deploy/backups`) and `BACKUP_KEEP_DAYS` (default `14`).
