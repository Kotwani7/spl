# Sindhi Premier League — SPL 2.0

Django application for the Sindhi Premier League. The SPL 2.0 upgrade is incremental. **Phase 1, the frontend redesign and a staff-operated auction workflow are implemented.** Concurrent multi-user bidding, team-owner accounts, PostgreSQL auction state and WebSocket delivery remain planned work. See [the UI handoff](docs/UI_REDESIGN.md), [auction engine status](AUCTION_ENGINE.md), [ROADMAP.md](ROADMAP.md) and the [audit](docs/AUDIT.md).

## Current capabilities

- Public season archives, teams, player profiles, scorecards, leaderboards, and sponsors.
- Staff-only organiser desk, CSV delivery import, starting matches, and basic delivery entry.
- Configurable player categories, marquee flags, price overrides and an organiser-controlled auction queue with staff-entered bids, team purses and sold/unsold results.
- Contact enquiries with server-side validation and optional email notification.
- Source JSON and PDF archives retained without inventing historical deliveries.
- Verified SQLite backups, reproducible migrations, regression tests, and a CI workflow.

The existing staff scoring workflow still has concurrency and cricket-rule gaps documented in the audit. It is not ready for concurrent production scorers. The auction workflow is staff-operated and uses SQLite by default; run it with one auctioneer until the PostgreSQL locking, idempotency and team-owner authorization gates in [AUCTION_ENGINE.md](AUCTION_ENGINE.md) are complete.

## Local setup (macOS / Linux)

Use Python 3.12. A Windows `.venv` was supplied with the project; leave it intact and create a native environment:

```sh
python3.12 -m venv .venv-local
source .venv-local/bin/activate
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
cp .env.example .env
python manage.py check
python manage.py backup_database
python manage.py migrate --plan
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ and `/django-admin/` for administration. Do not overwrite an existing `.env`. The new auction migration is additive and creates editable example categories. Review the plan; it should show `league.0003_playercategory_player_auction_base_price_and_more` plus any already-pending migrations. Stop and investigate any unexpected destructive operation before applying it.

**New empty database only:** set `SQLITE_PATH` to a new filename and run `python manage.py migrate`, then `python manage.py createsuperuser`. Do not create sample records in the historical database.

## Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
Copy-Item .env.example .env
python manage.py check
python manage.py backup_database
python manage.py migrate --plan
python manage.py migrate
python manage.py runserver
```

Use the backup step only when the source database exists. The batch helpers back up an existing database before migration; they no longer generate migration files automatically. Review the migration plan before applying it. The import helper intentionally refreshes imported aggregates: rehearse and review it before using it on manually corrected data.

## Verify changes

```sh
python -m pytest -q
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
```

Tests use `config.test_settings` and an in-memory database. Test fixtures never enter the historical database. `requirements-lock.txt` pins the versions verified during Phase 1; it is used as a constraints file for both runtime and development installations. Update it deliberately with regression testing.

## Protect historical data

```sh
python -m tools.database_safety inspect --database db.sqlite3
python -m tools.database_safety backup --database db.sqlite3 --directory backups
python -m tools.database_safety verify backups/<returned-backup-filename>.sqlite3
```

`python manage.py backup_database` backs up the configured database, including an alternate `SQLITE_PATH`. The standalone backup command defaults to `db.sqlite3` unless `--database` is supplied. The backup command opens the source read-only, uses SQLite's online backup API (including WAL data), verifies all rows/schema and SQLite integrity, and creates a checksum manifest. Each filename is unique. A failed check exits nonzero. Backups contain private records: keep them outside version control and copy verified backups to protected off-device storage. This tool does not configure remote storage or scheduled jobs.

Follow [DATABASE.md](DATABASE.md) for recovery rehearsals and the PostgreSQL migration plan. Never delete/reset the database, blindly fake migrations, or re-import archives merely to start the application.

## Configuration

`.env.example` documents local settings. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are now read from the environment. When `DEBUG=False`, a private secret of at least 50 characters is required and secure cookies/HTTPS redirects default on. Enable trusted proxy headers only behind a proxy that strips visitor-supplied forwarding headers. SMTP is optional; enquiry persistence does not depend on email delivery.

## Documentation

| Document | Purpose |
| --- | --- |
| [ROADMAP.md](ROADMAP.md) | Ten phases, checklists, file plans, verification gates |
| [docs/AUDIT.md](docs/AUDIT.md) | Code, data, security, UI, and performance findings |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current architecture and proposed domain boundaries |
| [DATABASE.md](DATABASE.md) | Backup, recovery, schema, and PostgreSQL cutover plan |
| [AUCTION_ENGINE.md](AUCTION_ENGINE.md) | Planned transactional auction protocol |
| [API.md](API.md) | Current HTTP surface and planned real-time interfaces |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Local verification and future production deployment gates |
| [CHANGELOG.md](CHANGELOG.md) | Implemented changes and verification |
| [docs/LEGACY_README.md](docs/LEGACY_README.md) | Original instructions, preserved for provenance |

Original JSON, PDFs, the source ZIP, previous database files, and correction scripts remain on disk. `.gitignore` excludes runtime files and private backups; this folder was not a Git checkout at audit time. No commits, pushes, or deployments were made.
