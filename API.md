# HTTP interfaces

## Current routes

The application is server-rendered HTML. It has no public JSON/DRF API and no WebSocket endpoints yet. All paths below retain their existing URL names.

| Path | Intended methods | Access / behavior |
| --- | --- | --- |
| `/` | GET | Backend counts, current/latest season, live fixture links |
| `/about/` | GET | League introduction and season history |
| `/teams/?season=` | GET | Optional positive integer season filter |
| `/teams/<id>/` | GET | Squad from recorded appearances for that exact team |
| `/players/?q=` | GET | Active players and name search |
| `/players/<id>/` | GET | Existing scorecard-derived totals |
| `/matches/?season=&q=` | GET | Fixtures/results and team search |
| `/matches/<id>/` | GET | Imported scorecard/actual innings |
| `/matches/<id>/live/` | GET, HEAD, POST | Public reads; staff POST actions; only live state accepts updates |
| `/matches/start/` | GET, HEAD, POST | Active staff only; atomic match/first-innings creation |
| `/leaderboards/?season=` | GET | Six recorded-data rankings; omitted season means all-time |
| `/sponsors/` | GET | Stored sponsors |
| `/register/` | GET | Registration information or configured external-form redirect |
| `/contact/` | GET, HEAD, POST | Validated enquiry submission |
| `/auction/` | GET | Public auction page; `?fragment=live` returns the HTML snapshot used for 12-second polling |
| `/organiser/` | GET, POST | Active staff; optional CSV import and auction dashboard link |
| `/organiser/auction/` | GET, POST | Active staff; category/player/queue/budget configuration and staff-entered auction mutations |
| `/django-admin/` | Django admin routes | Django admin authentication/permissions |

Read-only legacy views are documented by their intended GET use; not all have strict method decorators yet. Unknown object IDs return 404. Invalid/negative/oversized season filters return 400, and unknown requested leaderboard seasons return 404 instead of exposing all-time results.

## Current mutations

Use session authentication and a CSRF token. Do not exempt scoring/import/auction operations from CSRF to simplify browser integration.

- **Contact:** `name`, `email`, `phone` (optional), `subject` (optional), `message`. Invalid values render the bound form with errors (200); success saves the enquiry and redirects (302). Email failure does not erase the saved enquiry. This is a form workflow, not an HTTP JSON validation contract.
- **Start match:** `tournament`, `team_a`, `team_b`. Teams must belong to the selected tournament and differ. Staff only; success redirects to the created live fixture. Failure creating innings rolls back fixture creation.
- **Live match:** `action=ball|end_innings|finish`. Existing delivery fields include batter/bowler/runs/extras/dismissal/dismissed-player/fielder. Nonstaff mutation is refused; non-live staff mutations return 409. Remaining validation/concurrency limitations are documented in the audit; this endpoint is not a production-safe concurrent scoring API.
- **Organiser import:** multipart `csv_file`. Staff only; CSV headers and transaction semantics are covered by baseline tests. Duplicate-upload detection and complete scoring reconciliation are pending.
- **Auction configuration:** staff-only form actions create/edit/delete categories, edit player auction fields, create an auction from selected pool players, set team purses and queue order, and update the increment before start. Prices are whole rupees; lots preserve category/base-price/marquee snapshots.
- **Auction control:** staff-only form actions start/pause/resume an auction, submit a bid (`auction_id`, displayed `lot_id`, `team_id`, `amount`), or resolve the displayed lot as `sold`/`unsold`. Bid increment and purse checks execute in transaction-backed service functions. Every mutation is CSRF-protected. The workflow is single-auctioneer only on SQLite; see [AUCTION_ENGINE.md](AUCTION_ENGINE.md) for concurrency and owner-account limits.

Missing CSRF yields 403. Staff-gated pages redirect unauthenticated/nonstaff users to the admin login. There is no team-owner/scorer/tournament-scoped authorization contract until Phase 5.

## Planned versioned interfaces — not implemented

Future interfaces include JSON auction/scoring snapshots; idempotent bid/lot-control/delivery/correction commands; authorized CSV result exports; and read-only public stats/comparison selectors. Each API mutation should define request schema, actor scope, idempotency key, expected state version, error codes and audit result.

Proposed real-time envelopes contain `event_type`, entity IDs, monotonic `version`, server timestamp, and public state changes. Reconnect obtains a complete authoritative snapshot; Redis messages alone are insufficient. Private subscriptions must enforce ownership/tournament scope and never serialize registration PII.

HTTP errors for future JSON endpoints should consistently distinguish unauthenticated (401), unauthorized (403), unknown object (404), stale/conflicting state (409), invalid input (400/422 as selected), and rate limit (429), with stable machine-readable codes and safe human messages. Finalize these contracts and test them before documenting paths as available.
