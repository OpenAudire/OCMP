# Local Caddy additions

Files named `*.caddy` in this directory are included in the site block of
`deploy/Caddyfile`, so local changes survive upgrades. They are not tracked by git.
The directory is mounted read-only at `/etc/caddy/site.d` in the `caddy` container.

Use your institution's certificate instead of Let's Encrypt (for servers that cannot be
reached from the internet): copy the certificate chain and key here and create `tls.caddy`:

```
tls /etc/caddy/site.d/cert.pem /etc/caddy/site.d/key.pem
```

Then run `docker compose restart caddy`. See the install guide for details.
