# Changelog

## 2026-11-20 — Complete frontend redesign

- Replaced the old stylesheet and rebuilt all 16 existing page templates with a light sports editorial identity, compact navy masthead, match ticker, self-hosted typography and credited cricket photography.
- Added mobile bottom navigation and an accessible More sheet, source-driven homepage sections, team rosters, athlete profiles, season-filtered runs/wickets charts, scorecard tabs, aligned tables and contained horizontal scrolling.
- Redesigned organiser/scorer forms while preserving their field names, POST actions, CSRF tokens and staff gates.
- Added frontend auction presentation modes with explicit unavailable states. No auction engine, bids, budgets, deadlines or ownership permissions were invented.
- Added branded 400/403/404/500 templates; the 500 template renders with database access blocked.
- Added read-only template presentation helpers, reusable components, missing-image fallbacks, keyboard/focus handling and reduced-motion styles.
- Verified 94 regression tests and 119 layout cases (91 public, 21 temporary staff fixtures, 7 auction states) across seven requested widths. Saved screenshots and reports in `docs/screenshots/`.
- Confirmed original database, models, views, routes, scoring, import and statistics files remain byte-for-byte unchanged for this frontend task. No commits, pushes or deployments.
- Native fullscreen could not be entered in the embedded browser; the projector layout toggle was verified. Lighthouse and physical-device testing were not performed.

Suggested commit message (not executed): `feat(ui): rebuild SPL as a mobile-first sports editorial platform`.

## 2026-11-20 — SPL 2.0 Phase 1

### Implemented

- Audited the codebase, historical archives, schema, data inventory, auth, imports, scoring and public performance.
- Added `ROADMAP.md` with ten incremental phases and explicit acceptance gates.
- Added read-only database inspection and verified online SQLite backups with private permissions, unique filenames, all-table fingerprints and SHA-256 manifests.
- Created/verified a backup of the existing database; retained every original record and source file.
- Reconstructed the two missing recorded migrations; verified fresh schema against legacy columns, defaults, PKs, FKs, indexes and CHECKs.
- Added pytest with isolated in-memory databases, 81 regression checks, dependency constraints and a GitHub Actions workflow.
- Fixed invalid season filters, unknown-season all-time fallback, contact validation and optional email failure handling, completed-match mutations, wrong-team squad listings and atomic fixture/innings creation.
- Reduced the real-data leaderboard view from 1,448 SQL statements to 6 without changing any existing season/all-time ranking output.
- Made allowed hosts and trusted origins environment-driven; strengthened production secrets/cookie/HTTPS defaults and explicit proxy trust.
- Expanded ignore rules and added backup guards to Windows startup/import helpers; stopped generating migrations during startup.
- Updated setup, architecture, database, API, auction design and deployment documentation; preserved the original README in `docs/LEGACY_README.md`.

### Verification and limits

- 81 pytest tests pass; Django system check passes; no model/migration drift; existing database migration plan is empty.
- Read-only real-data route checks pass for public lists and existing team/match/player records; staff-only pages redirect anonymous visitors.
- Source database SHA-256 and all table fingerprints remain unchanged.
- Initial regression suite exposed 18 defects/cases before fixes (47 passing / 18 failing); additional tests brought the suite to 81 passing.
- No migration/import/data modification was performed on the historical database. No Git commit/push, deployment, fake data, identity merges or file deletion was performed.
- PostgreSQL, full redesign, granular roles, auctions, WebSockets, reliable scoring, PWA, browser responsive checks and Lighthouse are planned work, not verified features.

Suggested conventional commit message, not executed: `chore: establish verified SPL data safety and regression baseline`.
