from django.contrib import admin
from django.db import transaction
from .models import (Auction, AuctionBid, AuctionLot, AuctionPurse, PlayerCategory,
                     Tournament,Team,Player,Match,Innings,Delivery,Sponsor,ContactEnquiry,PlayerMatchStat)
from .auction_services import sync_pending_lots_for_category
class InningsInline(admin.TabularInline):
    model=Innings
    extra=0
@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display=("name","season","start_date","end_date","is_current")
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display=("name","tournament","short_name")
    list_filter=("tournament",)
@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display=("name","team_names","city","auction_category","is_marquee","in_auction_pool","is_active")
    list_filter=("auction_category","is_marquee","in_auction_pool","is_active")
    search_fields=("name","city","teams__name","auction_category__name")
    filter_horizontal=("teams",)
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.auction_lots.filter(
            status="queued", auction__status__in=["draft", "ready", "running", "paused"]
        ).exists():
            return ("auction_category", "auction_base_price", "is_marquee", "in_auction_pool")
        return ()
    @admin.display(description="Teams")
    def team_names(self, obj): return ", ".join(obj.teams.values_list("name", flat=True)) or "Not linked"


@admin.register(PlayerCategory)
class PlayerCategoryAdmin(admin.ModelAdmin):
    list_display=("name","base_price","position","player_count")
    search_fields=("name","description")
    ordering=("position","name")
    @admin.display(description="Players")
    def player_count(self, obj): return obj.players.count()
    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            sync_pending_lots_for_category(obj)


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display=("name","tournament","status","bid_increment","created_at")
    list_filter=("status","tournament")
    search_fields=("name","tournament__name")
    readonly_fields=("status","created_at","updated_at")
    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status not in {"draft", "ready"}:
            fields.append("bid_increment")
        return fields
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuctionLot)
class AuctionLotAdmin(admin.ModelAdmin):
    list_display=("auction","position","player","category_name","base_price","status","current_bid","highest_team","sold_price")
    list_filter=("auction","status","category")
    search_fields=("player__name","category_name","auction__name")
    readonly_fields=("auction","player","category","category_name","base_price","is_marquee","position","status","current_bid","highest_team","sold_price")
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuctionBid)
class AuctionBidAdmin(admin.ModelAdmin):
    list_display=("lot","team","amount","placed_by","placed_at")
    list_filter=("lot__auction","team")
    search_fields=("lot__player__name","team__name")
    readonly_fields=("lot","team","amount","placed_by","placed_at")
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuctionPurse)
class AuctionPurseAdmin(admin.ModelAdmin):
    list_display=("auction","team","budget","spent","remaining_amount")
    list_filter=("auction","team__tournament")
    def get_readonly_fields(self, request, obj=None):
        fields = ["spent"]
        if obj and obj.auction.status not in {"draft", "ready"}:
            fields.extend(["auction", "team", "budget"])
        return fields
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    @admin.display(description="Remaining")
    def remaining_amount(self, obj): return obj.remaining
@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display=("__str__","date","stage","status","winner")
    list_filter=("tournament","status")
    inlines=[InningsInline]
@admin.register(Innings)
class InningsAdmin(admin.ModelAdmin):
    list_display=("match","innings_number","batting_team","total_runs","wickets")
@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display=("innings","over_number","ball_number","batter","bowler","batter_runs","extra_type","dismissal_type")
@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display=("name","category")

@admin.register(ContactEnquiry)
class ContactEnquiryAdmin(admin.ModelAdmin):
    list_display=("name","email","subject","created_at","is_resolved")
    list_filter=("is_resolved","created_at")
    search_fields=("name","email","message")


@admin.register(PlayerMatchStat)
class PlayerMatchStatAdmin(admin.ModelAdmin):
    list_display=("player","team","match","runs","wickets","played_in_squad")
    list_filter=("match__tournament","team")
    search_fields=("player__name","team__name","match__team_a__name","match__team_b__name")
