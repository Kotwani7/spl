import pytest
from django.urls import reverse

from league.models import (
    Auction, AuctionBid, AuctionLot, AuctionPurse, PlayerCategory,
)


def _create_auction(client, staff, league_data, players, *, budget=500, increment=10):
    client.force_login(staff)
    response = client.post(reverse("auction_config"), {
        "action": "auction_create",
        "name": "Season 99 player auction",
        "tournament": league_data["tournament"].pk,
        "bid_increment": increment,
        "team_budget": budget,
        "players": [player.pk for player in players],
    })
    assert response.status_code == 302
    return Auction.objects.get(name="Season 99 player auction")


def test_example_categories_are_database_rows_and_prices_can_be_edited(client, staff):
    client.force_login(staff)
    assert PlayerCategory.objects.filter(name="Marquee Players", base_price=2_000_000).exists()
    response = client.post(reverse("auction_config"), {
        "action": "category_save", "name": "Emerging Players", "description": "Local talent",
        "base_price": 350_000, "position": 7,
    })
    assert response.status_code == 302
    assert PlayerCategory.objects.get(name="Emerging Players").base_price == 350_000


def test_category_price_and_marquee_are_snapshotted_on_lot_creation(client, staff, league_data):
    category = PlayerCategory.objects.get(name="A Category")
    category.base_price = 100
    category.save()
    player = league_data["batter"]
    player.auction_category = category
    player.is_marquee = True
    player.in_auction_pool = True
    player.save()

    auction = _create_auction(client, staff, league_data, [player])
    lot = auction.lots.get()
    category.base_price = 250
    category.save()
    player.refresh_from_db()

    assert player.effective_auction_base_price == 250
    assert lot.base_price == 100
    assert lot.category_name == "A Category"
    assert lot.is_marquee is True


def test_staff_can_run_bids_sell_unsold_and_purses_remain_accurate(client, staff, league_data):
    category = PlayerCategory.objects.get(name="B Category")
    category.base_price = 100
    category.save()
    first, second = league_data["batter"], league_data["bowler"]
    for player in (first, second):
        player.auction_category = category
        player.in_auction_pool = True
        player.save()

    auction = _create_auction(client, staff, league_data, [first, second], budget=500, increment=10)
    client.post(reverse("auction_config"), {"auction_id": auction.pk, "action": "start"})
    auction.refresh_from_db()
    first_lot = auction.lots.get(status="current")
    team_a, team_b = league_data["team_a"], league_data["team_b"]

    client.post(reverse("auction_config"), {
        "auction_id": auction.pk, "lot_id": first_lot.pk, "action": "bid", "team_id": team_a.pk, "amount": 100,
    })
    client.post(reverse("auction_config"), {
        "auction_id": auction.pk, "lot_id": first_lot.pk, "action": "bid", "team_id": team_b.pk, "amount": 105,
    })
    assert AuctionBid.objects.filter(lot=first_lot).count() == 1
    client.post(reverse("auction_config"), {
        "auction_id": auction.pk, "lot_id": first_lot.pk, "action": "bid", "team_id": team_b.pk, "amount": 110,
    })
    client.post(reverse("auction_config"), {"auction_id": auction.pk, "lot_id": first_lot.pk, "action": "sold"})

    first_lot.refresh_from_db()
    team_b_purse = AuctionPurse.objects.get(auction=auction, team=team_b)
    next_lot = auction.lots.get(status="current")
    assert first_lot.status == "sold"
    assert first_lot.sold_price == 110
    assert team_b_purse.spent == 110
    assert team_b_purse.remaining == 390
    assert next_lot.player == second
    assert AuctionBid.objects.filter(lot=first_lot).count() == 2

    client.post(reverse("auction_config"), {"auction_id": auction.pk, "lot_id": next_lot.pk, "action": "unsold"})
    auction.refresh_from_db()
    next_lot.refresh_from_db()
    assert next_lot.status == "unsold"
    assert auction.status == "finalized"
    assert team_b_purse.spent == 110


def test_public_auction_displays_saved_marquee_player_and_live_fragment(client, staff, league_data):
    category = PlayerCategory.objects.get(name="A Category")
    category.base_price = 100
    category.save()
    player = league_data["batter"]
    player.auction_category = category
    player.is_marquee = True
    player.in_auction_pool = True
    player.save()
    auction = _create_auction(client, staff, league_data, [player])
    client.post(reverse("auction_config"), {"auction_id": auction.pk, "action": "start"})

    response = client.get(reverse("auction"))
    assert response.status_code == 200
    assert "Season 99 player auction" in response.content.decode()
    assert "MARQUEE PLAYER" in response.content.decode()
    assert "₹100" in response.content.decode()

    fragment = client.get(reverse("auction"), {"fragment": "live"})
    assert fragment.status_code == 200
    assert 'data-auction-status="running"' in fragment.content.decode()


def test_regular_account_cannot_access_auction_controls(client):
    from django.contrib.auth import get_user_model

    spectator = get_user_model().objects.create_user(username="auction-spectator")
    client.force_login(spectator)
    assert client.get(reverse("auction_config")).status_code == 302


@pytest.mark.django_db
def test_auction_page_has_an_honest_empty_state(client):
    response = client.get(reverse("auction"))
    assert response.status_code == 200
    assert "No auction announced" in response.content.decode()
