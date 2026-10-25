# Install

This guide sets up OCMP on one Linux server with Docker. It is written for a university IT
technician and takes about 30 minutes, most of it waiting for the first build.

## 1. What you need

**Server**

- A 64-bit Linux server (these steps were written for Ubuntu Server 24.04 LTS; any
  distribution supported by Docker works).
- At least 4 vCPU, 8 GB RAM and 40 GB free disk space (the images take about 3 GB; leave
  room for the database and [backups](backup-restore.md)). A local AI model needs more;
  it is optional and not part of this guide.
- Shell access with `sudo`.

**Network**

- A DNS name for the site, for example `curriculum.example.ac.za`, pointing at the server.
- Inbound TCP ports **80** and **443** open to your users. OCMP publishes no other ports;
  the database and Redis are reachable only inside Docker.
- For an automatic Let's Encrypt certificate, ports 80 and 443 must also be reachable from
  the internet. If the server is internal only, use your institution's certificate instead
  (see [Use your own certificate](#use-your-own-certificate)).
- Outbound access to Docker Hub, GitHub, the Python and npm package registries (for the
  build) and to your SMTP server.

**Accounts and details**

- An SMTP server OCMP may send from (host, port, user, password, sender address). Without
  email, "forgotten password" cannot work.
- Optional: an OpenID Connect app registration for single sign-on, see
  [Single sign-on](../admin/sso.md). You can add it later.

## 2. Install Docker

Install Docker Engine and the Compose plugin from Docker's own repository by following the
official guide for your distribution:
[docs.docker.com/engine/install](https://docs.docker.com/engine/install/) (for Ubuntu:
[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)). The
`docker.io` package shipped by some distributions is often too old.

Check the installation:

```bash
sudo docker run --rm hello-world
docker compose version    # Docker Compose version v2.24 or later
```

The remaining commands assume your user may run Docker. Either prefix every `docker`
command (and the backup scripts) with `sudo`, or add yourself to the `docker` group with
`sudo usermod -aG docker $USER` and sign in again. Membership of the `docker` group is
equivalent to root access on the server; give it only to administrators.

## 3. Get OCMP

```bash
sudo mkdir -p /opt/ocmp
sudo chown "$USER" /opt/ocmp
git clone https://github.com/OpenAudire/OCMP.git /opt/ocmp
cd /opt/ocmp/deploy
```

All later commands run in `/opt/ocmp/deploy`.

## 4. Configure

Create the configuration file from the template and make it readable only by you:

```bash
cp .env.example .env
chmod 600 .env
```

Generate the two secrets (this replaces the placeholders in `.env`):

```bash
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
```

!!! warning "Keep `.env` safe"
    `.env` holds the secret key and the database password. Keep a copy in your
    institution's password or secrets store: backups of the database do not include it.
    If you set the database password by hand, use only letters and digits, because it is
    also part of `DATABASE_URL`. The password is applied when the database is first
    created; changing it in `.env` later does not change it in the database.

Open `.env` in an editor (for example `nano .env`) and set at least:

```ini
# The site's DNS name: Caddy gets a certificate for it
DOMAIN=curriculum.example.ac.za

# Email (needed for password reset)
SMTP_HOST=smtp.example.ac.za
SMTP_PORT=587
SMTP_USER=ocmp
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=noreply@example.ac.za
SMTP_TLS=true
```

Remove the `#` in front of each line you set. `PUBLIC_URL` defaults to
`https://<DOMAIN>`; set it only if users reach the site under a different address. Every
setting is described in [Configuration](configuration.md).

## 5. Start

```bash
docker compose up -d --build --wait
```

The first run builds the OCMP images and takes 5 to 15 minutes. The command returns when
all services are healthy. Check the result:

```bash
docker compose ps -a
```

`db`, `redis`, `api` and `web` should be `Up (healthy)`, `worker` and `caddy` `Up`, and
`migrate` `Exited (0)`: it updates the database schema on every start and then stops.

Check the site from the server and from your own computer:

```bash
curl https://curriculum.example.ac.za/ready
```

The answer reports `"status":"ready"` with the database and Redis up. If it does not,
see [Troubleshooting](#troubleshooting).

## 6. Run the setup wizard

While no institution exists, OCMP is waiting for its first-run setup, protected by a
setup token that only someone with access to the server can see:

```bash
docker compose exec api python -m app.cli setup-token
```

Open `https://curriculum.example.ac.za/setup` in a browser, enter the token, then:

1. the institution (name, short code, country, and whether to enable the health
   sciences profile),
2. the first administrator (name, email address, password),
3. confirm.

You are signed in as the platform administrator. The wizard works once only; afterwards
the token is no longer accepted. Continue with [Admin basics](../admin/basics.md).

## 7. Set up backups

Schedule the daily database backup now, before real data arrives: see
[Backup and restore](backup-restore.md).

## Use your own certificate

If the server cannot be reached from the internet, Let's Encrypt cannot issue a
certificate. Use a certificate from your institution's certificate authority instead:

1. Copy the certificate (with its intermediate chain) and the private key into
   `deploy/caddy/` as `cert.pem` and `key.pem`, and protect the key:
   `chmod 600 caddy/key.pem`.
2. Create `deploy/caddy/tls.caddy` containing:

    ```
    tls /etc/caddy/site.d/cert.pem /etc/caddy/site.d/key.pem
    ```

3. Restart Caddy: `docker compose restart caddy`.

Files in `deploy/caddy/` are not tracked by git, so upgrades keep them. Renew the
certificate before it expires by replacing the files and restarting Caddy again.

## Change ports or other service details

Do not edit `docker-compose.yml`, because upgrades replace it. Put local changes in
`deploy/docker-compose.override.yml`, which Docker Compose reads automatically and git
ignores. For example, to publish HTTPS on port 8443:

```yaml
services:
  caddy:
    ports: !override
      - "8080:80"
      - "8443:443"
```

## Try OCMP with the demo data

To explore OCMP before entering real curricula, load the fictional demo programme
"BSc Health Sciences (Demo)" after the setup wizard:

```bash
docker compose exec api python -m app.cli load-demo
```

It adds 3 modules, 20 sessions, 60 objectives, a demo competency framework and Bloom and
Miller scales. There is no command to remove it yet, so load it on a trial installation
rather than the production server.

## Troubleshooting

`docker compose up` stops with "POSTGRES_PASSWORD is required" or "SECRET_KEY is required"
:   The setting is missing or empty in `.env`. Run the commands in step 4 again.

`migrate` exited with an error, `api` does not start
:   Show the error with `docker compose logs migrate`. A database password changed after
    the first start is a common cause (see the warning in step 4).

The browser warns about the certificate
:   Check `docker compose logs caddy`. Let's Encrypt needs the DNS name to point at the
    server and ports 80 and 443 to be reachable from the internet; otherwise
    [use your own certificate](#use-your-own-certificate). With `DOMAIN` unset, Caddy
    serves `localhost` with its own internal certificate, which browsers do not trust.

The setup token is not accepted
:   Copy it again from `setup-token`; dashes and capitals do not matter. The token
    changes if `SECRET_KEY` changes.

Password reset emails do not arrive
:   Check `docker compose logs worker` for SMTP errors and the `SMTP_*` settings. Changes
    to `.env` take effect after `docker compose up -d`.

Logs
:   `docker compose logs --tail 100 api` (or `worker`, `caddy`, `db`). OCMP logs in JSON
    and never logs passwords, tokens or email addresses.
