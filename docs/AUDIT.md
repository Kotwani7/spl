# SPL 2.0 — Phase 1 audit

Audit date: 20 November 2026 (Asia/Kolkata). Scope: the supplied working directory, source archives, current SQLite database, application code, templates, dependencies, import/conversion scripts, and configuration. No production data was edited. This is an engineering baseline, not a production certification.

## Repository and runtime

- One Django app, `league`; configuration in `config`; 16 server-rendered HTML templates; one CSS file; PDF converters in `tools`; two historical import commands and a CSV importer.
- No `.git` directory or applicable `AGENTS.md` found. Consequently tracked-file cleanup, Git diffs, and commits cannot be verified or performed here. Generated files were retained and ignore rules added for a future repository.
- The supplied `.venv` contains Windows executables and cannot run on macOS. A separate ignored `.venv-local` uses Python 3.12.14, leaving the supplied environment untouched.
- Original dependency declarations: Django 5.x, python-dotenv, Pillow, pypdf. The Season 1 converter also imports `fitz` (PyMuPDF), which is undeclared; it is not required to serve/import existing JSON. Decide whether to retain that converter and add an optional tooling dependency in a later phase.
- No test suite or CI was supplied. Initial `manage.py check` passed; Django's test discovery found zero tests.
- Existing templates are mostly compressed into one or a few lines; none is empty. This impairs readability, but wholesale formatting is deferred to the redesign.

## Verified database inventory

The source was opened with `mode=ro`. SQLite integrity check returned `ok`; foreign-key check returned no violations.

| Entity | Records |
| --- | ---: |
| Tournaments | 3 |
| Teams (season-specific identities) | 40 |
| Players | 302 |
| Player/team memberships | 564 |
| Matches | 74 |
| Player-match aggregates | 1,810 |
| Innings | 118 |
| Deliveries | 0 |
| Sponsors | 1 |
| Contact enquiries | 0 |

There is also one authentication account; account/session row values were not printed or copied into documentation. Backups include these private tables and must remain private.

| Season | Teams | Matches | Player-match aggregates |
| --- | ---: | ---: | ---: |
| 1 | 10 | 15 | 373 |
| 2 | 14 | 28 | 700 |
| 3 | 16 | 31 | 737 |

Aggregate baseline: **11,686 runs; 6,624 balls faced; 620 wickets; 2,409 dot balls** in `PlayerMatchStat`. These are the recorded figures, not an independent assertion that every extracted source row is correct. No invalid team/winner associations, stat-team mismatches, missing stat-team memberships, or case-insensitive exact-name duplicate player groups were found. Similar names and spelling variants still require human identity review.

The database records `league.0001_initial` and `league.0002_match_full_scorecard_playermatchstat`, but both source files were missing, including from the supplied ZIP. Reconstructed definitions use those exact names. A fresh disposable database is compared against a schema-only legacy fixture covering columns, defaults, primary keys, foreign keys, unique/nonunique indexes, and CHECK expressions. The existing database has an empty migration plan; no migration was applied to it.

Source JSON contains 15, 28, and 31 matches for Seasons 1–3. PDFs and original extracted scorecard text are preserved. Zero delivery rows confirms that historical data must not be presented as complete ball-by-ball coverage. Existing innings aggregates must not be rebuilt from an empty delivery table.

## Findings addressed in Phase 1

| Finding | Change | Verification |
| --- | --- | --- |
| Missing migration source makes deployments/tests irreproducible | Reconstruct the two recorded migrations without changing models | Fresh-schema contract test, no model drift, empty existing migration plan |
| Backups were informal and unverified | Read-only online SQLite snapshot, independent row/schema verification, SHA-256 manifest, private files, unique filenames | Recovery, tampering, missing source, FK failure, and uncheckpointed WAL tests |
| Contact POST accepts blank/invalid/overlong values | Django ModelForm and bound field errors | Valid/invalid input and notification-failure tests |
| Completed/abandoned/scheduled fixtures accept scoring POSTs from staff | Require `status=live` before actions, return HTTP 409 otherwise | All three actions tested on completed fixtures |
| Starting a match can leave an orphan fixture if first innings creation fails | One transaction around fixture and first innings | Injected failure rolls back both |
| Invalid season strings produce 500 errors; unknown leaderboard season shows all-time data | Shared bounded integer filter validation; unknown season returns 404 | Invalid, negative, oversized, unknown season tests |
| Squad listing can include a player whose appearance was for another team in the same season | Filter by recorded `PlayerMatchStat.team` | Wrong-team membership regression test |
| Host configuration ignores environment and includes a private LAN address | Read hosts/origins from environment; remove duplicate assignment | Isolated configuration tests |
| Insecure production secret and cookie defaults | Reject weak deployment secrets, secure cookies/redirects by default outside debug, explicit proxy trust | Configuration tests |
| Historical fielding lookup performs multiple SQL statements per dismissal | Prefetch player memberships and resolve unambiguous names in memory | Five-query calculation regression and exact all-season output comparison |
| Startup/import helpers generate migrations and modify databases without a backup | Use versioned migrations and abort when backup fails | Script inspection; Windows execution not available on this macOS host |

## Remaining high-priority work

### Scoring correctness and concurrency — Phases 2 and 8

- Scoring logic lives in a large view. Totals are recalculated through separate aggregates; there are no row locks, operation IDs, sequence checks, audit events, or delivery undo.
- Two scorers can race, and resubmitting a POST records the same delivery again. SQLite cannot validate PostgreSQL row-lock semantics.
- Delivery payload choices are not fully validated server-side. Invalid dismissal/extra combinations, dismissed-player/team mismatch, zero-run wides, and invalid fielders can be accepted. No-ball balls-faced handling needs cricket-rule tests.
- Strike/non-striker state, bowler limits, free hits, configured innings length, all-out state, targets, required run rate, result calculation, innings completion, and match state transitions are incomplete.
- `save_live_match_statistics` replaces match aggregates; it must remain prohibited for archive-only matches. It cannot establish all playing-XI appearances from delivery participants alone.
- Live scoring is plain HTTP with manual refresh; `live_status.py` is an unused empty module. No Channels/Redis consumers exist.

### Data model and import safety — Phase 2

- `PlayerMatchStat.bowling_overs` is text notation. Migrate to integer legal balls with reversible backfill and source preservation; do not cast decimal overs to arithmetic overs.
- Multiple functions parse overs independently and silently coerce malformed values to zero or truncate them. Central strict validation is needed before imports/backfills.
- Player identity is name-based and not uniquely constrained; the two import commands use different identity rules. Retain aliases/source IDs and explicit merge review, not blind fuzzy matching.
- Import winner detection uses result-text prefixes; a re-import can overwrite manual winner corrections. `fix_winners.py` is a legacy script that mutates data on execution/import; do not run it as part of setup.
- CSV import is transactional but not repeatable: duplicate uploads create duplicate deliveries. It does not rebuild innings totals or player aggregates and does not reliably establish memberships. Add ImportBatch, validation, checksums, dry runs, and audit/provenance before wider use.
- Season JSON refresh deletes/recreates aggregate rows, changing their IDs and potentially overwriting manual edits. It is not a merge/reconciliation process. Preserve originals and rehearse all imports on a new database path.
- Missing constraints: one current season; distinct match teams; match/innings team membership; valid innings/ball ranges; legal dismissal/extra combinations. Cross-row invariants need services and, when justified, database enforcement.
- Cascade deletion on tournaments/players can destroy archives; review PROTECT/archival policy before migrations. Retain source JSON/text and nullable fields for unavailable historical facts.
- No franchise, roster provenance, venue entity, registration/approval, awards, ownership, audit log, or retention history exists. Add only entities justified by implemented behavior.

### Authentication and administration — Phase 5

- All organisers/scorers currently share Django's `is_staff` gate. No scoped tournament membership, owner identity, auctioneer/scorer grants, player accounts, or custom role dashboards exist.
- Django supplies session authentication, CSRF middleware, password hashing, and admin. Granular object permissions, password reset flows, account lifecycle tests, and rate limits are still needed.
- Contact input is now validated, but distributed request throttling, spam prevention, and file-upload validation remain pending.
- Production media/static hosting, TLS, secret rotation, off-device backup schedules, and operational observability are not configured.

### UI/UX, public content, and performance — Phases 3, 4, and 9

- Current identity is navy/gold with light content panels and DM Sans/Barlow Condensed, not the requested Inter/dark system. Headings are large and metadata/text often too small.
- A hamburger menu exists, but no five-item bottom navigation, safe-area handling, mobile sheets, sticky live headers, or responsive automation exists.
- Home/registration templates hardcode 2027 and January dates; no backend tournament currently supplies that future announcement. Replace these with confirmed backend content during the redesign, without inventing a season.
- No auction page, points table/NRR, featured-player selection, sponsor season links, announcement/gallery CMS, season winners, charts/comparisons, or cap awards exists.
- Public lists and leaderboard HTML are unpaginated. The leaderboard response is approximately 267 KB even when only ten rows per board are visible. Server pagination is still required.
- Player profile performs Python sums and incomplete metrics; match cards use JSON scorecards and need careful source-aware selectors. No-ball/fielding attribution ambiguities must remain visibly unavailable where unresolved.
- Historical catch parsing can misread a fielder surname beginning with `b` because the dismissal separator regex permits no following space. Fix against reviewed source formats with regression examples; Phase 1 deliberately preserves current ranking outputs.
- Sponsor category loops can display an empty section without its empty state when sponsors exist only in the other category.
- No page-specific description/Open Graph metadata, sitemap, PWA, image pipeline, cache policy, or Lighthouse baseline exists. Do not claim a >90 mobile score without measurement.

## Measurement and verification

Local Django test-client measurements against the real database opened **read-only**, on Python 3.12.14 / Django 5.2.19, without browser rendering or network latency:

| Page | Queries before | Queries after | Observed response |
| --- | ---: | ---: | --- |
| `/leaderboards/` | 1,448 | 6 | 200; ~267 KB |
| `/` | 7 | 7 | 200 |
| `/teams/` | 3 | 3 | 200 |
| `/matches/` | 3 | 3 | 200 |
| `/players/` | 2 | 2 | 200; ~58 KB |

Observed leaderboard server time in one local run fell from approximately 359 ms to 172 ms. These timings are diagnostic samples, not a benchmark or mobile/Lighthouse result. SQL reduction is the repeatable improvement. All-time and three season leaderboard structures were compared exactly before/after optimization.

81 automated tests pass. They cover public routes and missing records, filters, staff/CSRF boundaries, atomic match creation, contact validation, imports/rollback, statistics/overs, existing uniqueness, backup recovery/WAL/tampering, configuration, schema reconstruction, and bounded fielding queries. Browser responsiveness, PostgreSQL contention, Redis/Channels, auction operations, and real deployment are not yet tested because those phases are not implemented.

Initial new regression suite: 47 passed / 18 failed. The 18 failures demonstrated the input/state/squad defects corrected in this phase. Additional verification tests brought the final suite to 81 passes.

Original and final source-file SHA-256: `d6d009bccc40ae3a58a2b016ef417c23daa23f1e9ad7b841876fdb55e91111c7`. The verified backup has matching schema and row fingerprints for every table. No data was reset, merged, re-imported, or replaced.
