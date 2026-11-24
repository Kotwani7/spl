# SPL auction — current implementation and production boundary

Updated 24 November 2026.

## Delivered workflow

The Django app now has a staff-operated auction workflow built on the existing `Tournament`, `Team` and `Player` records. `PlayerCategory` is configurable through the organiser desk. The first migration adds editable example categories; organisers can change their names, descriptions, ordering and default base prices, and can add more. Player marquee status is an independent saved flag.

An organiser can add existing players to the auction pool, edit profile photos/details, assign categories, set an optional player-level price override and choose an auction order. A blank player override uses the assigned category's current base price. Category and player edits refresh queued lots in draft/ready auctions. Category, marquee and base-price edits are locked while an auction is running or paused; after finalization, a player can be prepared for a future auction. Started or completed lot snapshots are never rewritten by those edits.

Each auction stores its tournament, lifecycle state and integer-rupee bid increment. The organiser selects queue players and an opening team purse, can adjust each team's purse and lot order before starting, then starts, pauses and resumes the auction. The public auction page presents the current player, marquee badge, category, verified SPL scorecard totals, base/current/next bid, leading team, team logos/purses, bid history, upcoming queue, sold/unsold results and database-derived totals. While an auction is running, that page polls a server-rendered snapshot every 12 seconds.

Bids, lot results and purse spending are written in Django transactions. Competing bids must meet the saved increment and fit the selected team's remaining purse. Only tournament teams with an auction purse can bid. A sale records one sold price on the lot and updates the winning purse in the same transaction. Unsold lots keep their bid history. Each staff mutation includes the lot ID currently displayed, so a stale tab cannot resolve or bid on the next lot by accident.

## Local operating limits

- Only Django staff can configure an auction and enter team bids. Team owner accounts and team ownership authorization are not implemented. Team owners cannot bid themselves.
- The app still uses SQLite by default. `select_for_update()` is used in the service layer, but SQLite does not provide the row-lock behavior required for concurrent auctioneer sessions. Operate with one auctioneer until the PostgreSQL concurrency and idempotency work below is complete.
- Public status refreshes by polling. Django Channels, Redis, WebSockets, persisted bid deadlines, reconnect/version-gap recovery and timers are not implemented.
- No mandatory squad sizes, category eligibility, purse reserve, retention or reversal rules existed in the earlier app, so this workflow does not invent them. It enforces the configured base price, bid increment and team purse only.
- The public purse uses organizer-entered budgets. Amounts are integer rupees; category, lot, bid, sale and purse fields are not floating point.

## Migration and database safety

`league/migrations/0003_playercategory_player_auction_base_price_and_more.py` is additive. It creates the category, auction, lot, bid and purse tables; adds nullable/defaulted auction fields to existing players; and seeds six editable example categories. It does not create player/team records or change the existing season/match/scorecard rows.

Back up the configured database before applying the migration:

```powershell
python manage.py backup_database
python manage.py migrate --plan
python manage.py migrate
```

Review the plan and stop if it includes operations beyond the new `league.0003` migration. No migration has been applied to the historical `db.sqlite3` during this implementation. Regression tests use Django's disposable in-memory database.

## Work remaining before concurrent/owner bidding

The original auction-engine design remains the gate for a production multi-user auction: move authoritative auction state to PostgreSQL, add transaction-safe row locks and purse ledger constraints, idempotency receipts and version checks, define team ownership/roles and roster rules with the organiser, add persistent deadlines and audited correction/re-auction operations, then verify cross-connection concurrency tests. Add Redis/Channels only with origin/auth checks, after-commit events, reconnect snapshots and failure recovery are tested.
