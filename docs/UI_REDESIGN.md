# SPL frontend redesign handoff

Delivered 20 November 2026. This work follows the latest frontend-only brief: a light sports editorial website with navy contrast, restrained gold, dense readable scores and mobile navigation. It replaces the earlier proposed dark dashboard direction.

## What changed

- Rebuilt the global shell and all 16 existing page templates. Removed the original stylesheet rather than layering patches over it.
- Added reusable team marks, player tiles, match rows, rankings, Lucide navigation icons (original license included) and the auction display.
- Built a source-driven homepage: match ticker, actual results/upcoming fixtures, cap leaders, participating teams, featured players, recorded final winners, sponsors and clear unavailable states.
- Reworked player profiles into overview/batting/bowling/fielding/history tabs, with season selection, display-only filtering of recorded figures, and runs/wickets charts with accessible text and scroll containers.
- Reworked team rosters, match centre, batting/bowling scorecards, live-scoring forms, statistics, registration, sponsors, contact, about and organiser pages.
- Added branded error templates and a database-independent 500 page.
- Implemented a compact desktop masthead, fixed mobile bottom navigation with safe-area padding, an accessible More dialog, native focus trapping, Escape close/focus return, keyboard tab switching, collapsible filters and incremental list expansion.
- Added versioned asset URLs so browsers with the original stylesheet cached load the new UI correctly.
- Self-hosted Inter/Barlow Condensed fonts and responsive WebP cricket photography. No frontend framework or runtime CDN dependency was added.

## Scope boundaries

The historical database, model definitions, existing views, routing, scoring services, importers, statistics calculations and settings were not changed. A new `league/templatetags/league_ui.py` presentation helper reads existing public records, reuses the existing leaderboard function, matches score summaries to teams, formats legal balls, and supplies chart scales. It performs no writes, migrations, new cricket rules, or role changes.

The profile season control filters already supplied match records in the browser. Its totals match the existing recorded fields; it does not change scoring state or invent averages, batting styles, jersey numbers, fielding figures or valuations.

No auction engine exists in the supplied backend. The navigation opens a full-window dark auction display, also available through `/#auction`. Public, owner and auctioneer views state their availability accurately; bid/purse/deadline values remain unset. No fake countdown, bid, sale, owner grant or scoring update is generated. Projector layout is implemented; native browser fullscreen depends on browser support and was unavailable in the embedded test browser.

Official standings and future announcements are also unavailable in the backend. Their homepage sections say so rather than fabricating a points table or season dates.

## Assets and typography

No usable local player portraits, team logos or cricket photographs were found, including in the supplied source ZIP. The recorded sponsor image path points to a missing file. Initials and sponsor-name fallbacks remain visible while images load or when files are absent. Uploaded real images are used when available.

Cricket photograph: [Marcus Wallis, Adelaide Oval, Unsplash](https://unsplash.com/photos/mUtQXjjLPbw), used under the [Unsplash license](https://unsplash.com/license). It is identified as Adelaide Oval and is not presented as an SPL event photograph. Source attribution is also in the site footer.

Font licenses are retained in `static/fonts/inter-OFL.txt` and `static/fonts/barlowcondensed-OFL.txt`. Only local WOFF2 subsets are served. The four font files and two photographs total approximately 268 KB before HTTP compression. This is an asset inventory, not a Lighthouse score.

The requested secondary grey is retained as a palette token. Small text on paper uses a slightly darker grey to exceed 4.5:1 contrast. Live dots retain the requested red; live text uses accessible dark/light variants on different surfaces. White/navy and gold/navy combinations also pass the checked contrast ratios. Placeholder initials are decorative and paired with readable player/team names.

## Verification

`python -m pytest -q`: **94 tests pass**. Django system checks and JavaScript syntax checks pass. Tests protect existing actions/CSRF fields, source score display, profile season data, error statuses, CSS-value sanitization and a server-error template that works with database access blocked, alongside the earlier data-safety/business regression suite.

Browser testing used the in-app browser through the available CUA/Playwright APIs, with explicit viewport overrides:

| Coverage | Cases | Result |
| --- | ---: | --- |
| 13 public pages × 320, 375, 390, 430, 768, 1024, 1440 px | 91 | No document overflow, uncontained offscreen elements or missing primary headings |
| Organiser, start-match and scorer visual fixtures × seven widths | 21 | No document overflow or uncontained offscreen elements |
| Auction display × seven widths | 7 | Dialog scroll width equals viewport width |

Staff visual fixtures were rendered temporarily outside the repository, with in-memory display contexts and disconnected forms. No accounts were created, sessions inserted, matches started or scores posted to the historical database. Existing staff/CSRF behavior is verified separately by the Django suite.

Interactions verified in the browser:

- More dialog opens, focuses its close button, closes with Escape and restores the triggering control.
- Player season filtering changes career figures to the correct recorded season values; tab panels switch without page refresh and arrow/Home keyboard controls work.
- Team season filtering submits the existing GET route and returns the 16 actual Season 3 team entries.
- Player list expands from 24 to 48 visible entries; rankings expand from 10 to 20.
- Match-info/scorecard tabs switch correctly; score tables remain in their own horizontal scroll regions.
- Auction owner controls remain unavailable, projector presentation toggles, and auction dialog widths remain contained.
- Scorer selectors and action buttons have 46 px control heights.
- Missing sponsor imagery retains the actual sponsor name, including before lazy-loaded images resolve.

Additional checks passed for the bowling-chart tab at seven widths and four phone-landscape page cases.

Reports: `docs/screenshots/responsive-checks.json`, `staff-layout-checks.json`, `auction-checks.json`, `profile-bowling-checks.json` and `landscape-checks.json`. Screenshots include desktop/mobile homepages, scorecards, profiles, auction display and the clearly labelled scorer review fixture.

No physical-device lab, Lighthouse run, production deployment, or functioning auction backend was verified in this task. Reduced-motion support is implemented in CSS; the user's operating-system preference was not changed.

Protected-file hashes and the historical database checksum were checked before/after. The database remains `d6d009bccc40ae3a58a2b016ef417c23daa23f1e9ad7b841876fdb55e91111c7`. No Git repository was present, and no commits or pushes were made.

## Open the redesigned site

Run the normal Django development server from `.venv-local` and open `http://127.0.0.1:8000/`. Restart an already running server once if it was started before the new template-tag library was added. The database needs no migration or import for this redesign.

The remaining product/backend phases are tracked separately in `ROADMAP.md`; they are not prerequisites for viewing the delivered frontend.

## Auction implementation update — 24 November 2026

The auction display is now a dedicated SPL page with a staff configuration desk. Django models and an additive migration cover editable player categories, player marquee/pool/base-price fields, auctions, lot snapshots, bid history and team purses. The public view includes current/upcoming/results, team purse totals, recent bids, category sales and scorecard statistics. While live, it fetches a server-rendered snapshot every 12 seconds. The organiser can configure categories and prices, edit the player pool, set queue order/increments/team budgets, enter team bids and record sold/unsold outcomes.

Targeted verification on the in-memory Django test database passed seven auction workflow tests. Django system checks, migration consistency checks and the JavaScript syntax check passed. The existing `pytest` suite could not be run because `pytest` is not installed in the supplied virtual environments. A local browser visual check was attempted using an isolated temporary database, but the sandbox denied opening a loopback socket; this update does not claim screenshot or mobile-device verification. The reference YouTube broadcast also could not be fetched in this environment.

The earlier display-only auction notes above describe the 20 November frontend delivery. The current SQLite workflow remains single-organiser only: owner accounts, concurrent PostgreSQL bidding, WebSockets, deadlines and roster rules are still open gates in `AUCTION_ENGINE.md` and `ROADMAP.md`.
