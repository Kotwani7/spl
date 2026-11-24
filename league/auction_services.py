"""Validated, atomic mutations for the staff-operated auction workflow."""

from django.db import transaction

from .models import Auction, AuctionBid, AuctionLot, AuctionPurse


class AuctionActionError(ValueError):
    """A requested auction transition does not satisfy the current state."""


MAX_RUPEES = 9_223_372_036_854_775_807


def _positive_id(value, label):
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise AuctionActionError(f"Choose a valid {label}.")
    if identifier < 1:
        raise AuctionActionError(f"Choose a valid {label}.")
    return identifier


@transaction.atomic
def sync_pending_lots_for_player(player):
    """Refresh prepared, not-yet-started lots after player auction fields change."""
    lots = AuctionLot.objects.select_for_update().filter(
        player=player, status="queued", auction__status__in=["draft", "ready"]
    )
    if not lots.exists():
        return 0
    base_price = player.effective_auction_base_price
    if base_price is None:
        raise AuctionActionError("A queued player must keep a category price or individual override before the auction starts.")
    category_name = player.auction_category.name if player.auction_category_id else "Uncategorised"
    return lots.update(
        category=player.auction_category, category_name=category_name,
        base_price=base_price, is_marquee=player.is_marquee,
    )


@transaction.atomic
def sync_pending_lots_for_category(category):
    """Refresh queued base-price/category snapshots without touching auction history."""
    lots = AuctionLot.objects.select_for_update().filter(
        player__auction_category=category, status="queued",
        auction__status__in=["draft", "ready"],
    ).select_related("player")
    updated = 0
    for lot in lots:
        lot.category = category
        lot.category_name = category.name
        if lot.player.auction_base_price is None:
            lot.base_price = category.base_price
        lot.save(update_fields=["category", "category_name", "base_price"])
        updated += 1
    return updated


@transaction.atomic
def place_bid(auction_id, lot_id, team_id, amount, actor):
    lot_id = _positive_id(lot_id, "player lot")
    team_id = _positive_id(team_id, "team")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise AuctionActionError("Enter a valid whole-rupee bid.")
    if amount < 0 or amount > MAX_RUPEES:
        raise AuctionActionError("Enter a supported non-negative whole-rupee bid.")
    auction = Auction.objects.select_for_update().get(pk=auction_id)
    lot = AuctionLot.objects.select_for_update().select_related("highest_team").get(
        pk=lot_id, auction=auction, status="current"
    )
    if auction.status != "running":
        raise AuctionActionError("Bids are accepted only while the auction is live.")
    if lot.highest_team_id == team_id:
        raise AuctionActionError("That team already leads this player.")
    purse = AuctionPurse.objects.select_for_update().get(auction=auction, team_id=team_id)
    if purse.team.tournament_id != auction.tournament_id:
        raise AuctionActionError("Choose a team participating in this auction.")
    if amount < lot.next_bid:
        raise AuctionActionError(f"The next bid must be at least ₹{lot.next_bid:,}.")
    if amount > purse.remaining:
        raise AuctionActionError(f"That bid exceeds {purse.team.name}'s remaining purse of ₹{purse.remaining:,}.")
    bid = AuctionBid.objects.create(lot=lot, team=purse.team, amount=amount, placed_by=actor)
    lot.current_bid = amount
    lot.highest_team = purse.team
    lot.save(update_fields=["current_bid", "highest_team"])
    return bid


@transaction.atomic
def change_auction_state(auction_id, action):
    auction = Auction.objects.select_for_update().get(pk=auction_id)
    if action == "start":
        if auction.status not in {"draft", "ready"}:
            raise AuctionActionError("This auction cannot be started from its current state.")
        if not auction.lots.exists():
            raise AuctionActionError("Add at least one player to the auction queue first.")
        if not auction.purses.exists() or auction.purses.filter(budget__lte=0).exists():
            raise AuctionActionError("Set a positive purse for every participating team first.")
        current = auction.lots.filter(status="current").first()
        if current is None:
            current = auction.lots.filter(status="queued").order_by("position", "pk").first()
            if current is None:
                raise AuctionActionError("There are no queued players to auction.")
            current.status = "current"
            current.save(update_fields=["status"])
        auction.status = "running"
    elif action == "pause" and auction.status == "running":
        auction.status = "paused"
    elif action == "resume" and auction.status == "paused":
        auction.status = "running"
    else:
        raise AuctionActionError("That auction action is not available in its current state.")
    auction.save(update_fields=["status", "updated_at"])
    return auction


def _advance(auction):
    next_lot = auction.lots.filter(status="queued").order_by("position", "pk").first()
    if next_lot:
        next_lot.status = "current"
        next_lot.save(update_fields=["status"])
    else:
        auction.status = "finalized"
        auction.save(update_fields=["status", "updated_at"])


@transaction.atomic
def resolve_current_lot(auction_id, lot_id, result):
    lot_id = _positive_id(lot_id, "player lot")
    auction = Auction.objects.select_for_update().get(pk=auction_id)
    if auction.status != "running":
        raise AuctionActionError("Pause or resume the auction before resolving a player.")
    lot = AuctionLot.objects.select_for_update().select_related("highest_team").get(
        pk=lot_id, auction=auction, status="current"
    )
    if result == "sold":
        if lot.highest_team_id is None or lot.current_bid < lot.base_price:
            raise AuctionActionError("A player can be sold after a valid team bid has been placed.")
        purse = AuctionPurse.objects.select_for_update().get(auction=auction, team_id=lot.highest_team_id)
        if purse.remaining < lot.current_bid:
            raise AuctionActionError("The leading team's remaining purse no longer covers this bid.")
        purse.spent += lot.current_bid
        purse.save(update_fields=["spent"])
        lot.status = "sold"
        lot.sold_price = lot.current_bid
    elif result == "unsold":
        lot.status = "unsold"
    else:
        raise AuctionActionError("Choose Sold or Unsold.")
    lot.save(update_fields=["status", "sold_price"])
    _advance(auction)
    return lot


@transaction.atomic
def move_queued_lot(lot_id, direction):
    lot_id = _positive_id(lot_id, "player lot")
    if direction not in {"up", "down"}:
        raise AuctionActionError("Choose an available queue direction.")
    lot = AuctionLot.objects.select_for_update().get(pk=lot_id, status="queued")
    order = "-position" if direction == "up" else "position"
    neighbour = AuctionLot.objects.select_for_update().filter(
        auction=lot.auction, status="queued", **({"position__lt": lot.position} if direction == "up" else {"position__gt": lot.position})
    ).order_by(order, "pk").first()
    if neighbour is None:
        return
    original_lot_position = lot.position
    original_neighbour_position = neighbour.position
    temporary = max(lot.auction.lots.values_list("position", flat=True), default=0) + 1
    lot.position = temporary
    lot.save(update_fields=["position"])
    neighbour.position = original_lot_position
    neighbour.save(update_fields=["position"])
    lot.position = original_neighbour_position
    lot.save(update_fields=["position"])
