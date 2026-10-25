# Upgrade

Curriculum in Context is upgraded by fetching a newer version of the repository and rebuilding the
images. Database changes are applied automatically by the `migrate` service when the
stack starts.

!!! note "Before the first release"
    No versions are tagged yet: until then, upgrading means moving to the latest `main`.
    From the first release, install and upgrade to release tags (for example `v0.2.0`)
    and read their release notes on
    [GitHub](https://github.com/OpenAudire/OCMP/releases) first.

## Steps

All commands run in `/opt/ocmp/deploy`.

**1. Note the current version**, so you can go back to it:

```bash
git rev-parse --short HEAD
```

**2. Make a backup** and keep it until the upgrade is confirmed:

```bash
./backup.sh
```

**3. Get the new version:**

```bash
git fetch --tags
git checkout v0.2.0        # the release to install; before releases: git pull
```

For a private copy, `git fetch` asks for your GitHub username and token, as during
[installation](install.md#3-get-curriculum-in-context).

If git refuses because of local changes, a tracked file was edited by hand. Move local
changes into `docker-compose.override.yml` or `deploy/caddy/` (see [Install](install.md))
and restore the file with `git checkout -- <file>`.

**4. Check for new settings.** Compare the template of the old and the new version and
copy any new settings you need into `.env`:

```bash
git diff <old version> HEAD -- .env.example
```

**5. Rebuild and restart:**

```bash
docker compose up -d --build --wait
```

The site is unavailable for a short time while the containers are replaced.

**6. Check the result:**

```bash
docker compose ps -a              # migrate: Exited (0); the others Up
docker compose logs migrate       # the migrations that ran
curl https://curriculum.example.ac.za/ready
```

Sign in and open a few pages. Then remove old images to free disk space:

```bash
docker image prune
```

## Use released images

From the first release, every version tag publishes ready-built images to GitHub
Container Registry, so the server does not need to build them:

- `ghcr.io/openaudire/ocmp-backend:<version>`
- `ghcr.io/openaudire/ocmp-web:<version>`

To use them, add to `.env` (with the version you install):

```ini
OCMP_BACKEND_IMAGE=ghcr.io/openaudire/ocmp-backend:0.2.0
OCMP_WEB_IMAGE=ghcr.io/openaudire/ocmp-web:0.2.0
```

and replace step 5 with:

```bash
docker compose pull
docker compose up -d --wait
```

Leave out `--build`: it would build the images from the checkout instead. Still check out
the same tag in git, because the compose file, Caddyfile and scripts come from the
checkout. The released images are public and need no sign-in. For private images (for
example from a private fork), sign in first with `docker login ghcr.io`, using a GitHub
personal access token (classic) with the `read:packages` scope as the password.

## If the upgrade fails

**The `migrate` service failed** (`docker compose up` reports it and `api` does not
start): read `docker compose logs migrate`. PostgreSQL applies schema changes in a
transaction, so a failed migration leaves the database as it was. Report the error, then
go back to the previous version:

```bash
git checkout <old version>
docker compose up -d --build --wait
```

**The new version runs but does not work correctly:** migrations cannot be undone by the
older version. Go back to the previous version **and** restore the backup from step 2:

```bash
git checkout <old version>
docker compose up -d --build --wait
./restore.sh backups/<backup from step 2>
```

Changes made after the upgrade are lost.

## Docker and PostgreSQL updates

- Apply operating system and Docker updates as usual. Restarting Docker restarts Curriculum in Context.
- `docker compose pull` followed by `docker compose up -d --build --wait` updates the
  third-party images (PostgreSQL 16 minor versions, Redis, Caddy) within their pinned
  major versions.
- A new PostgreSQL major version (for example 17) is never applied automatically; it will
  come with instructions in the release notes, based on backup and restore.
