# SPL 2.0 implementation roadmap

Updated: 20 November 2026. Delivery is incremental. **Phase 1 and the frontend work in Phase 3 are implemented and verified.** The frontend was prioritised at the user’s request. Backend phases and production performance verification remain open. A checked item means working code or a completed check, not a proposed design. Do not infer production readiness from this checklist.

Every phase must preserve historical IDs, source JSON/text, and existing working routes, create/verify a fresh backup before data migrations, provide reviewable changes, run its critical tests, update this file and the changelog, and state any verification limits. Destructive changes require user approval. No automatic commits, pushes, or publishing.

## Phase 1 — Audit, backups, baseline tests, repository hygiene

Objective: make the existing product safe to change and reproducible without touching historical data.

- [x] Inspect models, routes/views, templates/CSS, scoring, statistics, admin, imports, converters, dependencies, source archives, and database metadata.
- [x] Record inventory, architecture/security issues, data gaps, and performance findings in `docs/AUDIT.md`.
- [x] Create read-only integrity and content fingerprint tooling.
- [x] Create verified online SQLite backup and private checksum manifest; include WAL in snapshot.
- [x] Verify recovery on disposable files, reject tampering/missing sources/FK corruption, prevent overwrites.
- [x] Reconstruct the two missing migration files under their recorded names.
- [x] Verify fresh migration output against the audited legacy schema and confirm no pending operations on the existing database.
- [x] Establish pytest with an in-memory database and baseline coverage for public routes, archive import idempotency/rollback, statistics, permissions, CSRF, forms, and constraints.
- [x] Fix demonstrated malformed-filter, contact-validation, completed-match-write, wrong-team-squad, and partial-start-transaction defects.
- [x] Reduce historical fielding N+1 queries while preserving all existing season/all-time ranking outputs.
- [x] Honor environment hosts/origins and strengthen production configuration defaults.
- [x] Expand ignore rules; retain all source data, archives, previous database files, and existing environments.
- [x] Remove automatic migration generation from Windows helpers and add pre-migration backup checks.
- [x] Add verified dependency constraints and a GitHub Actions test workflow.
- [x] Create architecture, database, auction design, route, deployment, roadmap, and changelog documentation; retain the legacy README.
- [x] Verify original database file SHA-256 and every table fingerprint remain unchanged.

Files: `tools/database_safety.py`, `tools/__init__.py`, `league/management/commands/backup_database.py`, `league/migrations/`, `league/forms.py`, targeted `league/views.py` / `league/statistics.py` fixes, `templates/contact.html`, `config/settings.py`, `config/test_settings.py`, `.env.example`, `.gitignore`, `requirements-dev.txt`, `requirements-lock.txt`, `pytest.ini`, `tests/`, `.github/workflows/tests.yml`, Windows helpers, and the documentation named above.

Decision: retain the current `league` app and SQLite database while establishing a verified baseline. Recover migration history before schema evolution; do not generate a new destructive baseline or fake unapplied operations.

Verification: 81 tests pass; Django checks pass; no model drift; existing migration plan empty; read-only real-data route smoke checks; exact leaderboard comparison; database file and contents unchanged. Browser/mobile QA and actual GitHub Actions execution are pending their relevant environments/phases.

Suggested commit message (not committed): `chore: establish verified SPL data safety and regression baseline`

## Phase 2 — Data model, PostgreSQL, migration safety

Objective: evolve the historical schema through additive, reversible, verified changes and establish PostgreSQL as the production authority.

- [ ] Add environment-selected PostgreSQL configuration and psycopg dependency with integration-test settings.
- [ ] Provide Docker Compose PostgreSQL/Redis services with health checks, private credentials, volumes, and documented backup/restore.
- [ ] Introduce source-aware integer legal-ball counts for imported bowling figures, preserving source notation; validate malformed values before backfill.
- [ ] Centralize cricket notation parsing and test `4.5 → 29`, invalid fractional digits, blank/unavailable values, and round trips.
- [ ] Add timestamps, useful composite indexes, a single-current-season constraint, innings ranges, distinct-team constraints, and documented deletion policies.
- [ ] Introduce aliases/source identity and season squad provenance without blindly merging players/franchises.
- [ ] Add import provenance, dry runs, checksums, repeatability, result parsing, and reconciliation reports protecting manual corrections.
- [ ] Audit and repair existing violations only through reviewed, reversible operations with before/after reports.
- [ ] Rehearse export/import to a separate empty PostgreSQL database preserving primary keys, relationships, auth/password hashes, JSON and raw text; reset sequences.
- [ ] Compare all entity counts, per-season figures, aggregate totals, raw-scorecard hashes, leaderboards, and media references.
- [ ] Test actual PostgreSQL transactions/rollback/locks; create verified target backup and rehearse rollback before cutover.
- [ ] Cut over only after verification; retain original SQLite and backups permanently under the retention policy.

Expected files: `config/settings.py`, `config/postgres_test_settings.py`, `compose.yml`, `Dockerfile`, `.env.example`, `requirements*.txt`, additive `league/migrations/`, cricket helpers, import services/commands, PostgreSQL integration tests, `DATABASE.md`, `DEPLOYMENT.md`.

Decision: no wholesale table renaming/app split during data cutover. Keep aggregate historical records independent of live deliveries. Compute standings rather than prematurely storing a PointsTable model.

Gate: separate-database migration report and PostgreSQL tests pass; source content unchanged. Suggested commit: `feat(db): add verified PostgreSQL migration and data invariants`.

## Phase 3 — Design system and complete responsive redesign

Objective: deliver a coherent mobile-first sports identity across all current pages.

- [x] Implement the latest requested light editorial palette: navy `#101C35`, paper `#F6F7F9`, white surfaces, restrained gold `#D9AD50`, Inter and Barlow Condensed. Secondary text is slightly darkened on paper for contrast.
- [x] Replace compressed templates with readable reusable components, semantic layouts, Lucide icons, consistent buttons/forms/status/empty/error states and accessible contrast.
- [x] Build responsive desktop navigation, accessible mobile More sheet, and Home/Matches/Auction/Stats/More bottom navigation with safe-area support.
- [x] Make Auction show an honest unavailable state until the engine is shipped; do not simulate live bids.
- [x] Build backend-driven homepage sections; remove hardcoded season/date claims. Display confirmed content or clear unavailable states.
- [x] Redesign teams, team detail, players, player detail, fixtures, scorecards, live match, leaderboards, registration, sponsors, about, contact and organiser pages.
- [x] Add compact horizontal match carousel, sticky live score headers, contained scorecard scrolling, collapsible filters, touch targets >=44px, responsive forms/images and reduced-motion support.
- [x] Test keyboard/focus/menus, portrait and landscape, and widths 320, 375, 390, 430, 768, 1024, 1440; assert no document-level overflow.
- [x] Capture and visually review desktop/mobile screenshots. Pass 91 public page/viewport checks, 21 staff fixture checks and 7 auction display checks; verify navigation, tabs, filters and form preservation. See `docs/UI_REDESIGN.md`.
- [ ] Measure Lighthouse/real-device performance before making production performance claims (Phase 9).

Expected files: `templates/base.html`, `templates/components/`, existing page templates, `static/css/`, `static/js/`, local font/icon assets, public selectors/context, Playwright tests/config.

Decision: retain Django templates and lightweight JS/HTMX; no React rewrite or new SPA. Use real backend content and licensed existing imagery; no placeholder production statistics.

Frontend gate passed: browser interaction and responsive assertions plus route regressions. Latest suite: 94 tests. Auctions, standings and announcements without backend support use honest unavailable states; no new domain logic or database writes were introduced. Suggested commit: `feat(ui): redesign SPL with a mobile-first sports identity`.

## Phase 4 — Players, teams, analytics, tournaments

Objective: expose trustworthy performance and tournament management derived from available records.

- [ ] Add player roles/styles only when sourced; current and previous rosters, career/season/recent form, auction history and awards when available.
- [ ] Calculate supported batting/bowling/fielding metrics once in selectors/services; represent unknowns separately from zero, preserve not-out semantics, fix reviewed dismissal parsing.
- [ ] Add charts for runs/wickets/strike rates/economy and side-by-side player comparison with season filters and mobile layouts.
- [ ] Paginate/search/filter public lists and leaderboard results server-side.
- [ ] Add venues, configurable tournament rules/stages, playing XI, captain/vice-captain and fixture scheduling/generation with conflict checks.
- [ ] Implement standings, result points and correct NRR including all-out quotas/no-results/ties and explicitly unavailable historical denominators.
- [ ] Add playoffs, season archives, previous winners, caps, documented MVP formula, awards and team head-to-head records.
- [ ] Add efficient joins/aggregates and query-budget tests; prevent mixed live/imported sources from double counting.

Expected files: gradual `players/`, `teams/`, `tournaments/`, `statistics/` domains or compatible `league` services/selectors, additive migrations, profile/team/comparison templates, chart JS, domain tests.

Gate: source-backed figures and NRR fixtures verified; query budgets and mobile comparisons pass. Suggested commit: `feat(stats): add source-aware profiles and tournament analytics`.

## Phase 5 — Authentication, registration, scoped dashboards

Objective: authorize every action by role and tournament/team ownership on the server.

- [ ] Define Super Admin, Organiser, Auctioneer, Team Owner, Scorer, Registered Player and Spectator role matrix with tournament scopes.
- [ ] Add explicit TeamOwnership and organiser/scorer assignments; prevent owners from impersonating other teams.
- [ ] Build registration, consent/private fields, approval/rejection/tracking and secure upload validation.
- [ ] Add password reset, secure sessions, rate limits, auth/audit events and object-permission checks.
- [ ] Build custom organiser, scorer, owner and player dashboards; retain Django Admin for maintenance.
- [ ] Test anonymous/nonstaff/staff/scoped roles, cross-team/tournament access, CSRF and registration privacy.

Expected files: `accounts/`, `registrations/`, permissions/forms/services, additive migrations, auth/dashboard templates, privacy and authorization tests.

Gate: permission matrix verified through HTTP and service entry points. Suggested commit: `feat(auth): add scoped roles and registration dashboards`.

## Phase 6 — Transactional auction engine

Objective: persist an auditable, restart-safe auction in PostgreSQL with backend-enforced business rules.

**Partial delivery (24 November 2026):** the SQLite Django app now includes configurable categories, player marquee/pool/base-price settings, auction/lot/bid/purse records, a staff-operated start/pause/resume/bid/sold/unsold workflow, category and lot snapshots, and a public auction page with 12-second polling. See [AUCTION_ENGINE.md](AUCTION_ENGINE.md). These changes do not pass the Phase 6 gate: PostgreSQL concurrency, team-owner authorization, idempotency, purse ledger/reserve rules, deadlines, audited correction/re-auction and real PostgreSQL tests remain open.

- [ ] Implement Auction, AuctionLot, Bid, AuctionResult, TeamPurse, PurseTransaction, retention, shortlist and audit models only where independently required.
- [ ] Implement auction lifecycle/configuration, player categories/base prices, increments, budgets, squad/category/retention limits and mandatory-slot reserve.
- [ ] Enforce database constraints, row locks, idempotency keys, expected state versions, server deadlines and team ownership.
- [ ] Handle sold/unsold/re-auction, pause/resume/extend, retention, finalization and compensating audited reversals atomically.
- [ ] Record monetary amounts as integer currency units (or explicit fixed decimal units) with no floating-point money; document purse invariants.
- [ ] Broadcast state events only after commit; retain durable events for publication recovery.
- [ ] Implement CSV result export with formula-injection handling and authorization.
- [ ] Run real PostgreSQL concurrency tests: simultaneous/duplicate/late bids, overspending, squad reserves, double sale, rollback, stale versions and restarts.

Expected files: `auctions/models.py`, `services.py`, `selectors.py`, `validators.py`, `permissions.py`, migrations, PostgreSQL tests, `AUCTION_ENGINE.md`.

Gate: transactional invariants and concurrent integration tests pass before exposing bidding. Suggested commit: `feat(auction): implement transactional bidding and purse accounting`.

## Phase 7 — Real-time auction experience

Objective: ship public, auctioneer, team owner and projector interfaces over the verified engine.

- [ ] Integrate Channels ASGI and Redis channel layer with origin/auth checks and authoritative state snapshots.
- [ ] Provide state/event versioning, reconnect resync, server time/deadlines, reconnect/offline notices and post-commit broadcasts.
- [ ] Build public player/bid/history/purse/progress/sold/unsold/retained/upcoming views and expensive-purchase summaries.
- [ ] Build auctioneer configuration/control/reversal/finalization and owner bidding/shortlist/squad/maximum-affordability dashboards.
- [ ] Build full-screen projector mode with readable photo/bid/timer/leader/purses.
- [ ] Ensure timer expiry and bid validity remain server decisions; disable stale/offline mutation controls.
- [ ] Verify cross-device bids, reconnects, Redis failure recovery, mobile taps/viewport and projector layout.

Expected files: `auctions/consumers.py`, `routing.py`, HTTP views/forms or DRF serializers, `config/asgi.py`, auction templates/JS, Redis/config dependencies, browser and WebSocket tests.

Gate: full bid-to-snapshot flow verified against PostgreSQL and Redis. Suggested commit: `feat(auction): add live bidding dashboards and projector mode`.

## Phase 8 — Reliable scoring and broadcasts

Objective: replace fragile score-entry mutations with a tested transactional cricket state machine.

- [ ] Define configurable rules, innings state, striker/non-striker, free hits and playing XI eligibility.
- [ ] Centralize delivery validation and atomic sequence/idempotency/row locking; reject completed/stale state and invalid wickets/extras.
- [ ] Implement rotation, bowler changes/limits, overs, all-out/target/result, innings transitions, partnerships/FOW and correct batting/bowling/fielding attribution.
- [ ] Implement append-only audited correction/undo operations and consistent aggregate rebuilding.
- [ ] Add score snapshots and post-commit WebSocket events with reconnect synchronization.
- [ ] Build mobile scorer controls and sticky spectator scores with accessible status and connection feedback.
- [ ] Test cricket edge cases, simultaneous submissions, duplicate retries, undo, result/NRR effects and imported/live source boundaries.

Expected files: `scoring/` services/models/validators/selectors/consumers, additive migrations, scorer/live templates, JS, PostgreSQL and browser tests.

Gate: scoring rule fixtures and race/rollback tests pass. Suggested commit: `feat(scoring): add audited transactional live scoring`.

## Phase 9 — Content, PWA, performance, SEO

Objective: complete the spectator experience and measure mobile performance.

- [ ] Add announcements, gallery, sponsors/season links, winners/Hall of Fame and notifications; fan polls only with clear abuse controls.
- [ ] Add shareable scorecards/profiles, safe CSV exports and reliable available-data head-to-head analytics.
- [ ] Add installable manifest/icons and versioned public static caches; never cache auth/mutation/scoring/bidding endpoints or queue their writes offline.
- [ ] Add page metadata/Open Graph, sitemap and robots policy for private pages.
- [ ] Optimize image formats/dimensions/lazy loading, fonts, production minification, public caching and query budgets.
- [ ] Measure Lighthouse/mobile behavior and layout shifts on representative pages and document device/network/test conditions; target >90 where achievable.
- [ ] Defer fantasy and complex prediction features as explicit future extensions.

Expected files: content apps/migrations/admin/forms, public templates/selectors, service worker/manifest/static build, sitemap/metadata, performance reports/tests.

Gate: no stale/offline writes, SEO assertions, measured performance report, and responsive regression pass. Suggested commit: `feat(web): add spectator content PWA and measured performance improvements`.

## Phase 10 — Security, operations, deployment readiness

Objective: make the verified application deployable and supportable without claiming untested readiness.

- [ ] Complete threat/permission/data-privacy review, request/upload limits, distributed rate limiting and dependency checks.
- [ ] Add production Docker/ASGI service configuration, HTTPS/static/media hosting, health/readiness and structured redacted logs.
- [ ] Configure off-device backups, schedules/retention, restore drills, alerting and database/Redis failure handling.
- [ ] Run full PostgreSQL/Redis/HTTP/WebSocket/browser suite, multiple-device auction/scoring exercise and realistic load tests.
- [ ] Review migration/backfill plans and before/after reconciliation reports; document reversible cutover and rollback.
- [ ] Update all docs and validate deployment configuration with `check --deploy` in its real environment.
- [ ] Produce a concrete release review with outstanding risks and measured results.
- [ ] Obtain any required explicit publication/destructive-action authorization; no Git commit/push without user authorization.

Expected files: production Compose/container/ingress config, CI integration matrix, operational scripts, deployment/security/load reports and final documentation.

Gate: critical flows verified under the target infrastructure; deployment observed healthy. Suggested commit: `chore(release): verify SPL production operations and security`.
