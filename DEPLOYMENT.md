# Setup and deployment status

## Render deployment preparation

The repository now includes a Render Blueprint in `render.yaml`. It provisions a Python web service, a managed PostgreSQL database, and a persistent disk for uploaded media. The blueprint uses paid Render resources because the free service does not provide persistent media storage or a durable production database. Review current [Render pricing](https://render.com/pricing) before applying it.

The web service runs `collectstatic` during build, migrations in Render's pre-deploy step, and Gunicorn against Django's WSGI application. Render generates `SECRET_KEY`; production mode is enabled and the Render hostname is added to Django's host and CSRF settings. Local development continues to use SQLite unless `DATABASE_URL` is set.

**Important: this deploy starts with an empty PostgreSQL database.** The local `db.sqlite3`, `.env`, and backups are intentionally not uploaded. Existing season records, accounts, enquiries, and uploaded images need a separately planned and verified data transfer before the public launch. Do not switch users to the new site until the intended data has been migrated and checked.

To deploy, first push this repository to a Git provider, then in Render choose **New → Blueprint**, connect that repository, review the resources and charges, and apply the blueprint. After the first deploy, create an administrator with `python manage.py createsuperuser` in the Render Shell. If you want the current local data online, arrange a backup and migration rehearsal before importing it.

No Render resources have been created and the site has not been published from this workspace.

**The app remains undeployed.** It runs locally with SQLite. Render configuration now supports PostgreSQL, but no production database is connected or migrated. Redis, Channels, Docker/Compose, granular roles, reliable concurrent scoring, and the production auction engine remain unimplemented. Nothing was published or pushed.

## Reproducible local checks

Use Python 3.12 and a native virtual environment (see README). Install with:

```sh
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python -m pytest -q
```

Test settings explicitly use an in-memory database and local-memory email. Never run test jobs with production settings or a production database alias. The GitHub Actions workflow provides these same SQLite checks when the source is eventually placed in an authorized Git repository; that remote workflow has not been run here.

For an existing historical database, verify a backup and inspect `migrate --plan` before any migration. A new installation may migrate a separate empty `SQLITE_PATH`. Never run `makemigrations` automatically on server start. Never import season JSON as a prerequisite for serving the supplied database.

## Production configuration contract

- Set `DEBUG=False`, a private random `SECRET_KEY` of at least 50 characters, explicit `ALLOWED_HOSTS`, and HTTPS `CSRF_TRUSTED_ORIGINS`.
- Keep `.env`, database files, private backups, credentials, and uploaded private documents out of source control. Constraints files pin verified package versions; update and test them deliberately.
- Secure session/CSRF cookies and HTTPS redirect default on outside debug. Configure TLS before enabling redirects in a real environment.
- `TRUST_PROXY_HEADERS=True` is appropriate only when the trusted ingress overwrites/removes visitor-provided forwarding headers. Never trust arbitrary `X-Forwarded-Proto` from the open Internet.
- HSTS is configurable but deliberately defaults to zero until HTTPS is verified. Choose its scope/preload policy after the domain and subdomains are ready.
- Serve static and validated public media via an appropriate production server/storage. Private registration files need authenticated access, not public media URLs.
- Use the planned ASGI/Channels runtime after it is implemented; Django's development server is not a production server. PostgreSQL/Redis credentials must be environment secrets.
- Configure optional SMTP with private credentials. Saved enquiries are authoritative; email is a notification channel.

Run `python manage.py check --deploy` with the actual production configuration. A successful unit suite is not a substitute for this check, TLS verification, object-permission testing or infrastructure health checks. HSTS/deployment warnings remain expected under default local configuration.

## Planned release procedure

1. Complete relevant roadmap gates and test PostgreSQL/Redis under the target infrastructure.
2. Review a concrete change set and additive migration plan. Take and independently verify fresh source/target backups; rehearse restores to separate databases.
3. Build/pin the application artifact and production static assets. Scan configuration/dependencies; retain exact source/version provenance.
4. Rehearse database transfer/backfills using the documented reconciliation reports and rollback boundary. Obtain approval for any destructive operation. Do not overwrite source archives.
5. Schedule a short write freeze for database cutover; deploy compatible application/schema changes in order. Never dual-write independently to SQLite and PostgreSQL.
6. Verify login, scoped dashboards, a controlled registration, score snapshots, auction/scoring test flows, public pages, static assets, WebSocket origin/auth checks and health/readiness endpoints.
7. Observe error rates, latency/query budgets, connection counts, locks, event delivery and mobile layouts before declaring the release ready.
8. Retain backups/source/previous artifacts and a rollback plan that accounts for post-cutover writes.

## Backups and operations to implement

The local backup tool is available now. Scheduled backups, protected off-device replication, retention, production restore drills, alerting, structured/redacted logs, and operational dashboards remain Phase 10 tasks. A local backup next to the application is not off-device disaster recovery.

No production host, domain, SMTP credentials, or PostgreSQL target have been configured. The repository has an `origin` remote, but no commits, pushes, releases or hosting access changes were made for this Render preparation.
