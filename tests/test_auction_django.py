from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from league.models import Auction, AuctionBid, AuctionPurse, Player, PlayerCategory, Team, Tournament


class AuctionWorkflowTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(season=99, is_current=True)
        self.team_a = Team.objects.create(tournament=self.tournament, name="Ulhasnagar Royals", short_name="UR")
        self.team_b = Team.objects.create(tournament=self.tournament, name="Sindh Strikers", short_name="SS")
        self.category = PlayerCategory.objects.get(name="A Category")
        self.category.base_price = 100
        self.category.save()
        self.first = Player.objects.create(
            name="First auction player", auction_category=self.category,
            is_marquee=True, in_auction_pool=True,
        )
        self.second = Player.objects.create(
            name="Second auction player", auction_category=self.category,
            in_auction_pool=True,
        )
        self.organiser = get_user_model().objects.create_user(
            username="auction-organiser", password="test-password", is_staff=True,
        )
        self.client.force_login(self.organiser)

    def create_auction(self):
        response = self.client.post(reverse("auction_config"), {
            "action": "auction_create", "name": "Season 99 auction",
            "tournament": self.tournament.pk, "bid_increment": 10,
            "team_budget": 500, "players": [self.first.pk, self.second.pk],
        })
        self.assertEqual(response.status_code, 302)
        return Auction.objects.get(name="Season 99 auction")

    def test_configuration_dashboard_and_public_empty_state_render(self):
        self.assertContains(self.client.get(reverse("auction_config")), "Player categories")
        self.assertContains(self.client.get(reverse("home")), 'href="/auction/"')
        self.client.logout()
        self.assertContains(self.client.get(reverse("auction")), "No auction announced")

    def test_prepared_lots_refresh_and_completed_snapshots_survive_later_edits(self):
        auction = self.create_auction()
        first_lot = auction.lots.get(player=self.first)
        self.client.post(reverse("auction_config"), {
            "action": "category_save", "category_id": self.category.pk,
            "name": self.category.name, "description": self.category.description,
            "base_price": 250, "position": self.category.position,
        })
        first_lot.refresh_from_db()
        self.assertEqual(first_lot.base_price, 250)
        self.client.post(reverse("auction_config"), {"action": "start", "auction_id": auction.pk})
        self.client.post(reverse("auction_config"), {
            "action": "bid", "auction_id": auction.pk, "lot_id": first_lot.pk,
            "team_id": self.team_a.pk, "amount": 250,
        })
        self.client.post(reverse("auction_config"), {
            "action": "sold", "auction_id": auction.pk, "lot_id": first_lot.pk,
        })
        self.client.post(reverse("auction_config"), {
            "action": "category_save", "category_id": self.category.pk,
            "name": self.category.name, "description": self.category.description,
            "base_price": 350, "position": self.category.position,
        })
        first_lot.refresh_from_db()
        self.first.refresh_from_db()

        self.assertEqual(self.first.effective_auction_base_price, 350)
        self.assertEqual(first_lot.base_price, 250)
        self.assertEqual(first_lot.sold_price, 250)
        self.assertTrue(first_lot.is_marquee)
        self.assertEqual(first_lot.category_name, "A Category")

    def test_categories_are_validated_protected_and_lots_can_be_reordered(self):
        self.client.post(reverse("auction_config"), {
            "action": "category_save", "name": "Fast Bowlers", "description": "Specialist bowlers",
            "base_price": 75, "position": 8,
        })
        self.assertTrue(PlayerCategory.objects.filter(name="Fast Bowlers", base_price=75).exists())
        self.client.post(reverse("auction_config"), {
            "action": "category_save", "name": "Invalid price", "description": "",
            "base_price": -1, "position": 9,
        })
        self.assertFalse(PlayerCategory.objects.filter(name="Invalid price").exists())
        self.client.post(reverse("auction_config"), {
            "action": "category_delete", "category_id": self.category.pk,
        })
        self.assertTrue(PlayerCategory.objects.filter(pk=self.category.pk).exists())

        auction = self.create_auction()
        first_lot = auction.lots.get(player=self.first)
        second_lot = auction.lots.get(player=self.second)
        self.client.post(reverse("auction_config"), {
            "action": "queue_move", "auction_id": auction.pk,
            "lot_id": second_lot.pk, "direction": "up",
        })
        first_lot.refresh_from_db()
        second_lot.refresh_from_db()
        self.assertLess(second_lot.position, first_lot.position)

    def test_bid_validation_sale_unsold_and_purse_accounting(self):
        auction = self.create_auction()
        self.client.post(reverse("auction_config"), {"action": "start", "auction_id": auction.pk})
        first_lot = auction.lots.get(status="current")

        self.client.post(reverse("auction_config"), {
            "action": "bid", "auction_id": auction.pk,
            "lot_id": first_lot.pk, "team_id": self.team_a.pk, "amount": 100,
        })
        self.client.post(reverse("auction_config"), {
            "action": "bid", "auction_id": auction.pk,
            "lot_id": first_lot.pk, "team_id": self.team_b.pk, "amount": 105,
        })
        self.assertEqual(AuctionBid.objects.filter(lot=first_lot).count(), 1)
        self.client.post(reverse("auction_config"), {
            "action": "bid", "auction_id": auction.pk,
            "lot_id": first_lot.pk, "team_id": self.team_b.pk, "amount": 110,
        })
        self.client.post(reverse("auction_config"), {"action": "sold", "auction_id": auction.pk, "lot_id": first_lot.pk})

        first_lot.refresh_from_db()
        purse = AuctionPurse.objects.get(auction=auction, team=self.team_b)
        self.assertEqual(first_lot.status, "sold")
        self.assertEqual(first_lot.sold_price, 110)
        self.assertEqual(purse.spent, 110)
        self.assertEqual(purse.remaining, 390)
        self.assertEqual(AuctionBid.objects.filter(lot=first_lot).count(), 2)

        self.client.post(reverse("auction_config"), {
            "action": "unsold", "auction_id": auction.pk, "lot_id": first_lot.pk,
        })
        self.assertEqual(auction.lots.get(status="current").player, self.second)
        second_lot = auction.lots.get(player=self.second)
        self.client.post(reverse("auction_config"), {"action": "unsold", "auction_id": auction.pk, "lot_id": second_lot.pk})
        auction.refresh_from_db()
        self.assertEqual(auction.status, "finalized")
        self.assertEqual(auction.lots.get(player=self.second).status, "unsold")

    def test_public_page_announces_marquee_and_fragment_reports_live_status(self):
        auction = self.create_auction()
        self.client.post(reverse("auction_config"), {"action": "start", "auction_id": auction.pk})

        response = self.client.get(reverse("auction"))
        self.assertContains(response, "Season 99 auction")
        self.assertContains(response, "MARQUEE PLAYER")
        self.assertContains(response, "₹100")
        self.assertContains(self.client.get(reverse("auction"), {"fragment": "live"}), 'data-auction-status="running"')

    def test_increment_is_editable_before_start_and_locked_after_start(self):
        auction = self.create_auction()
        self.client.post(reverse("auction_config"), {
            "action": "increment_save", "auction_id": auction.pk, "bid_increment": 25,
        })
        auction.refresh_from_db()
        self.assertEqual(auction.bid_increment, 25)
        self.client.post(reverse("auction_config"), {"action": "start", "auction_id": auction.pk})
        self.client.post(reverse("auction_config"), {
            "action": "increment_save", "auction_id": auction.pk, "bid_increment": 50,
        })
        auction.refresh_from_db()
        self.assertEqual(auction.bid_increment, 25)

    def test_player_category_and_marquee_cannot_change_after_auction_starts(self):
        auction = self.create_auction()
        self.client.post(reverse("auction_config"), {"action": "start", "auction_id": auction.pk})
        other_category = PlayerCategory.objects.get(name="C Category")
        response = self.client.post(reverse("auction_config"), {
            "action": "player_save", "player_id": self.first.pk,
            "name": self.first.name, "city": self.first.city,
            "auction_category": other_category.pk, "auction_base_price": "",
            "is_marquee": "on", "in_auction_pool": "on",
        }, follow=True)
        self.assertContains(response, "locked after an auction starts")
        self.first.refresh_from_db()
        self.assertEqual(self.first.auction_category, self.category)
