# TrustBuilding production deployment

Target: `trust-building.uz`, server `116.203.50.220`, 4 vCPU / 8 GB RAM.
This is a **first deployment** with a new database. Host Nginx terminates TLS;
Docker runs Gunicorn, PostgreSQL 18, Redis, a Celery worker, and one Celery Beat.

## 1. Prepare the server

The commands below assume Debian/Ubuntu, Docker Engine with the Compose plugin,
and this repository checked out on the server. Run project commands from its root.

- Point the domain's DNS **A** record to `116.203.50.220`. If an AAAA record exists,
  it must reach this server too; otherwise remove it before requesting a certificate.
- Allow inbound TCP 80 and 443 in the server/provider firewall, plus your SSH port.
  PostgreSQL and Redis have no published ports; Gunicorn binds to loopback only.
- Securely copy the updated `env/.production` to the server: it is Git-ignored and
  excluded from image builds. Run `chmod 600 env/.production`.
- The file contains fresh Django and database secrets. Existing administrator and
  Eskiz credentials were retained. Review those credentials before the first start.
  Keep the same database password on subsequent deployments; changing the env file
  alone does not change an initialized PostgreSQL user's password.

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo install -d -o 10001 -g 10001 -m 0755 /var/www/trustbuilding/static /var/www/trustbuilding/media
sudo install -d -m 0755 /var/www/letsencrypt
./compose/production/compose config --quiet
```

The application runs as UID/GID `10001`. These host directories must be writable
by that user and readable by Nginx. Put any initial uploaded files in the media
directory with the same ownership. The existing application serves `/media/`
directly through Nginx; keep that in mind when uploading documents.

## 2. Install the HTTP-only Nginx site

This file deliberately has no certificate paths or HTTPS redirect, so Nginx can
start before a certificate exists.

```bash
sudo install -m 0644 compose/production/nginx/trust-building.uz /etc/nginx/sites-available/trust-building.uz
sudo ln -sfn /etc/nginx/sites-available/trust-building.uz /etc/nginx/sites-enabled/trust-building.uz
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
```

Until the application starts, proxied pages will return 502; the ACME challenge
path remains available for certificate issuance.

## 3. Obtain HTTPS with Certbot

```bash
sudo certbot --nginx -d trust-building.uz --redirect
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

Enter the certificate contact email when Certbot prompts. Certbot's Nginx plugin
[obtains the certificate and edits the installed Nginx configuration](https://eff-certbot.readthedocs.io/en/stable/using.html#nginx).
**Do not overwrite the installed site with the HTTP bootstrap file afterward.**

Set `DJANGO_HTTPS_ENABLED='1'` in `env/.production` before starting the application.
This enables secure cookies and Django's HTTPS redirect. Keep
`DJANGO_SECURE_HSTS_SECONDS='0'` until HTTPS and renewal are verified; you can then
set it to `3600` and increase it later. Nginx supplies `X-Forwarded-Proto`, so
Django recognizes proxied HTTPS without a redirect loop.

If you need to smoke-test HTTP before obtaining the certificate, start the stack
with `DJANGO_HTTPS_ENABLED='0'` temporarily. After Certbot succeeds, set it to `1`
and recreate the application services using the command in section 5.

## 4. Start the production stack

```bash
./compose/production/compose build web
./compose/production/compose up -d
./compose/production/compose ps
./compose/production/compose logs --tail=100 web celery_worker celery_beat
curl --fail https://trust-building.uz/health/
```

The helper supplies `-f docker-compose.prod.yml`. Each application service and
PostgreSQL load `env/.production` through `env_file`; worker concurrency is
expanded inside the container. No CLI `--env-file` option or exported shell
variables are required. The direct command also works:

```bash
docker compose -f docker-compose.prod.yml up --build
```

Avoid printing the expanded Compose configuration because it contains credentials.

The image builds CSS and translations in advance. Web startup runs migrations,
creates the shared cache table, creates the initial administrator if none exists,
and collects static files. No separate manual migration command is needed.
The worker and Beat wait for the web readiness check before starting.

Daily payment reminders are enabled immediately with this deployment and execute
at **10:00 Asia/Tashkent** according to `application/celery.py`. Enabling the
scheduler does not send a manual batch immediately. Run **exactly one Beat** to
avoid duplicate scheduling. Its schedule state and Redis queue persist across
container restarts. Successful SMS delivery still requires valid Eskiz credentials,
an approved message template where required, and sufficient account balance.

Gunicorn defaults to 3 workers with 2 threads each; Celery uses 2 worker processes.
These are initial settings for this server, adjustable in `env/.production` after
observing CPU, RAM, and request latency.

## 5. Subsequent updates and operations

After a code change:

```bash
./compose/production/compose build web
./compose/production/compose up -d
```

After an environment-only change, including the HTTP-to-HTTPS switch:

```bash
./compose/production/compose up -d --force-recreate web celery_worker celery_beat
```

Logs rotate at 10 MB with three files per service. Database, Redis, and Beat data
use dedicated `trustbuilding_production` volumes. PostgreSQL 18 stores data under
`/var/lib/postgresql/18/docker`, with the volume mounted at
[`/var/lib/postgresql`](https://hub.docker.com/_/postgres).
Do not use `down -v` when data must be retained.

Back up both PostgreSQL and `/var/www/trustbuilding/media` off the server. For a
database dump (the shell expands the database variables inside the container):

```bash
umask 077
./compose/production/compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > trustbuilding.dump
```

Verify restore procedures before relying on backups. Static files can be rebuilt;
uploaded media and the database cannot. Local development Compose files remain
separate from this production stack.
