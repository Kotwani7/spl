from django.conf import settings
from django.db import transaction
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.core.exceptions import BadRequest
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import render,get_object_or_404,redirect
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import logging
from .models import (Auction, AuctionBid, AuctionLot, AuctionPurse, PlayerCategory,
                     Tournament,Team,Player,Match,Delivery,Sponsor,ContactEnquiry,PlayerMatchStat)
from .statistics import calculate_leaderboards
from .importer import import_delivery_csv
from .forms import (AuctionCreateForm, AuctionIncrementForm, AuctionPurseForm, ContactEnquiryForm,
                    PlayerAuctionForm, PlayerCategoryForm, SeasonFilterForm)
from .auction_services import (AuctionActionError, change_auction_state,
                               move_queued_lot, place_bid, resolve_current_lot,
                               sync_pending_lots_for_category, sync_pending_lots_for_player)

logger = logging.getLogger(__name__)


def _positive_post_id(request, field_name):
    try:
        value = int(request.POST.get(field_name, ""))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _season_filter(request):
    form = SeasonFilterForm(request.GET)
    if not form.is_valid():
        raise BadRequest("Choose a valid positive season number.")
    return form.cleaned_data["season"]

def about(request):
    season_history = Tournament.objects.annotate(
        matches_count=Count("matches", distinct=True),
        teams_count=Count("teams", distinct=True),
    ).order_by("season")
    return render(request, "about.html", {"season_history": season_history})

def home(request):
    current=Tournament.objects.filter(is_current=True).first() or Tournament.objects.order_by("-season").first()
    return render(request,"home.html",{"tournament":current,"teams_count":Team.objects.count(),"matches_count":Match.objects.count(),"players_count":Player.objects.count(),"sponsors":Sponsor.objects.all()[:4],"live_matches":Match.objects.filter(status="live").select_related("team_a","team_b","tournament")[:3]})
def teams(request):
    qs=Team.objects.select_related("tournament").prefetch_related("players").annotate(matches_played_count=Count("player_match_stats__match",distinct=True))
    season = _season_filter(request)
    if season is not None: qs=qs.filter(tournament__season=season)
    return render(request,"teams.html",{"teams":qs,"seasons":Tournament.objects.order_by("-season")})
def matches(request):
    qs=Match.objects.select_related("tournament","team_a","team_b","winner").order_by("-date","-pk")
    season = _season_filter(request)
    if season is not None: qs=qs.filter(tournament__season=season)
    if request.GET.get("q"): qs=qs.filter(team_a__name__icontains=request.GET["q"])|qs.filter(team_b__name__icontains=request.GET["q"])
    live_matches=Match.objects.filter(status="live").select_related("tournament","team_a","team_b").order_by("-pk")
    return render(request,"matches.html",{"matches":qs,"live_matches":live_matches,"seasons":Tournament.objects.order_by("-season")})
def match_detail(request,pk):
    match=get_object_or_404(Match.objects.select_related("team_a","team_b","tournament","winner"),pk=pk)
    return render(request,"match_detail.html",{"match":match,"live_innings":match.innings.select_related("batting_team","bowling_team").order_by("innings_number")})
def players(request):
    qs=Player.objects.filter(is_active=True).prefetch_related("teams").annotate(matches_played_count=Count("match_stats__match",distinct=True))
    if request.GET.get("q"): qs=qs.filter(name__icontains=request.GET["q"])
    return render(request,"players.html",{"players":qs})
def player_detail(request,pk):
    p=get_object_or_404(Player,pk=pk)
    scorecard_stats=PlayerMatchStat.objects.filter(player=p)
    runs=sum(x.runs for x in scorecard_stats)
    wickets=sum(x.wickets for x in scorecard_stats)
    dots=sum(x.dot_balls for x in scorecard_stats)
    matches_played=scorecard_stats.values("match_id").distinct().count()
    return render(request,"player_detail.html",{"player":p,"runs":runs,"wickets":wickets,"dots":dots,"matches_played":matches_played,"scorecard_stats":scorecard_stats.select_related("match","team").order_by("-match__date")})
def leaderboards(request):
    season = _season_filter(request)
    t = get_object_or_404(Tournament, season=season) if season is not None else None
    return render(request,"leaderboards.html",{"stats":calculate_leaderboards(t.pk if t else None),"seasons":Tournament.objects.order_by("-season")})


def team_detail(request, pk):
    team = get_object_or_404(Team.objects.select_related("tournament").prefetch_related("players"), pk=pk)
    players = team.players.filter(match_stats__team=team).distinct().order_by("name")
    return render(request, "team_detail.html", {"team": team, "players": players})


@require_http_methods(["GET", "HEAD", "POST"])
def live_match(request, pk):
    match = get_object_or_404(Match.objects.select_related("tournament", "team_a", "team_b"), pk=pk)
    innings = match.innings.select_related("batting_team", "bowling_team").prefetch_related("deliveries").order_by("innings_number")
    current_innings = innings.last()
    if request.method == "POST":
        if not request.user.is_staff:
            messages.error(request, "Only an SPL organiser can update the live score.")
            return redirect("match_detail", pk=match.pk)
        if match.status != "live":
            return HttpResponse("This match is not open for scoring.", status=409)
        action = request.POST.get("action")
        if action == "end_innings":
            if current_innings is None:
                messages.error(request, "Start the match before ending an innings.")
            elif innings.count() >= 2:
                messages.info(request, "Both innings have already been started. Finish the match to close scoring.")
            else:
                next_batting = match.team_b if current_innings.batting_team_id == match.team_a_id else match.team_a
                from .models import Innings
                Innings.objects.create(
                    match=match,
                    batting_team=next_batting,
                    bowling_team=current_innings.batting_team,
                    innings_number=2
                )
                messages.success(request, f"Second innings started: {next_batting.name}.")
            return redirect("live_match", pk=match.pk)

        if action == "finish":
            from .live_stats import save_live_match_statistics

            try:
                with transaction.atomic():
                    saved_count = save_live_match_statistics(match)
                    match.status = "completed"
                    match.save(update_fields=["status"])

                messages.success(
                    request,
                    f"Match completed successfully. Statistics saved for {saved_count} players."
                )
            except Exception as exc:
                messages.error(request, f"Unable to complete match: {exc}")

            return redirect("match_detail", pk=match.pk)
        if action == "ball" and current_innings:
            from .models import Delivery
            try:
                batter = Player.objects.get(pk=request.POST.get("batter"))
                bowler = Player.objects.get(pk=request.POST.get("bowler"))
                batter_runs = int(request.POST.get("batter_runs", "0"))
                extra_runs = int(request.POST.get("extra_runs", "0"))
                if not (0 <= batter_runs <= 6 and 0 <= extra_runs <= 6):
                    raise ValueError("Runs must be between 0 and 6.")
                extra_type = request.POST.get("extra_type", "none")
                dismissal_type = request.POST.get("dismissal_type", "")
                dismissed = Player.objects.filter(pk=request.POST.get("dismissed_player")).first() if dismissal_type else None
                fielder = Player.objects.filter(pk=request.POST.get("fielder")).first() if request.POST.get("fielder") else None
                if batter.teams.filter(pk=current_innings.batting_team_id).exists() is False:
                    raise ValueError("Select a batter from the batting team.")
                if bowler.teams.filter(pk=current_innings.bowling_team_id).exists() is False:
                    raise ValueError("Select a bowler from the bowling team.")
                legal = extra_type not in ("wide", "no_ball")
                with transaction.atomic():
                    last = current_innings.deliveries.order_by("-over_number", "-ball_number").first()
                    legal_balls = current_innings.legal_balls
                    over_number = legal_balls // 6
                    ball_number = legal_balls % 6 + 1
                    if last and not legal:
                        over_number, ball_number = last.over_number, last.ball_number
                    Delivery.objects.create(innings=current_innings, over_number=over_number, ball_number=ball_number,
                        batter=batter, bowler=bowler, batter_runs=batter_runs, extra_runs=extra_runs,
                        extra_type=extra_type, dismissal_type=dismissal_type, dismissed_player=dismissed,
                        fielder=fielder, is_legal=legal)
                    current_innings.total_runs = current_innings.deliveries.aggregate(v=Sum("batter_runs"))['v'] or 0
                    current_innings.total_runs += current_innings.deliveries.aggregate(v=Sum("extra_runs"))['v'] or 0
                    current_innings.wickets = current_innings.deliveries.exclude(dismissal_type="").count()
                    current_innings.legal_balls = current_innings.deliveries.filter(is_legal=True).count()
                    current_innings.save(update_fields=["total_runs", "wickets", "legal_balls"])
                messages.success(request, "Ball added to the live score.")
            except (Player.DoesNotExist, ValueError, TypeError) as exc:
                messages.error(request, str(exc) or "Please check the scoring details.")
            return redirect("live_match", pk=match.pk)
    current_innings = match.innings.select_related("batting_team", "bowling_team").order_by("innings_number").last()
    players = Player.objects.filter(is_active=True).filter(teams__in=[match.team_a, match.team_b]).distinct().order_by("name")
    return render(request, "live_match.html", {"match": match, "innings_list": match.innings.select_related("batting_team", "bowling_team").order_by("innings_number"), "current_innings": current_innings, "players": players})


@staff_member_required
@require_http_methods(["GET", "HEAD", "POST"])
def start_match(request):
    if request.method == "POST":
        tournament = get_object_or_404(Tournament, pk=request.POST.get("tournament"))
        team_a = get_object_or_404(Team, pk=request.POST.get("team_a"), tournament=tournament)
        team_b = get_object_or_404(Team, pk=request.POST.get("team_b"), tournament=tournament)
        if team_a == team_b:
            messages.error(request, "Choose two different teams.")
        else:
            from .models import Innings
            with transaction.atomic():
                match = Match.objects.create(tournament=tournament, team_a=team_a, team_b=team_b,
                    date=timezone.localdate(), stage="Live Match", status="live", ground=tournament.venue)
                Innings.objects.create(match=match, batting_team=team_a, bowling_team=team_b, innings_number=1)
            messages.success(request, "Match started. Team A will bat first.")
            return redirect("live_match", pk=match.pk)
    return render(request, "start_match.html", {"tournaments": Tournament.objects.order_by("-season"), "teams": Team.objects.select_related("tournament").order_by("tournament__season", "name")})
def sponsors(request):
    return render(request,"sponsors.html",{"sponsors":Sponsor.objects.all()})
def register(request):
    return redirect(settings.GOOGLE_FORM_URL) if settings.GOOGLE_FORM_URL else render(request,"registration.html")
@require_http_methods(["GET", "HEAD", "POST"])
def contact(request):
    form = ContactEnquiryForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        enquiry = form.save()
        # Persistence succeeds independently of the optional notification channel.
        try:
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                send_mail(
                    f"SPL website enquiry: {enquiry.subject}",
                    f"From: {enquiry.name}\nEmail: {enquiry.email}\n"
                    f"Phone: {enquiry.phone}\n\n{enquiry.message}",
                    settings.DEFAULT_FROM_EMAIL, [settings.ADMIN_EMAIL],
                )
        except Exception:
            logger.warning("Contact notification failed for enquiry %s", enquiry.pk)
        messages.success(request,"Your enquiry has been submitted.")
        return redirect("contact")
    return render(request,"contact.html", {"form": form})
@staff_member_required
def organiser(request):
    if request.method=="POST" and request.FILES.get("csv_file"):
        try: messages.success(request,f"Imported {import_delivery_csv(request.FILES['csv_file'])} ball-by-ball rows.")
        except Exception as e: messages.error(request,str(e))
        return redirect("organiser")
    return render(request,"organiser.html",{
        "matches":Match.objects.count(),"players":Player.objects.count(),
        "deliveries":Delivery.objects.count(),"teams":Team.objects.count(),
        "enquiries":ContactEnquiry.objects.filter(is_resolved=False).count(),
        "marquee_players":Player.objects.filter(is_marquee=True).count(),
        "auction_categories":PlayerCategory.objects.count(),
    })


def _public_auction_context(auction):
    if auction is None:
        return {"auction": None, "refresh_active": False}
    lots = auction.lots.select_related("player", "category", "highest_team").order_by("position", "pk")
    current_lot = lots.filter(status="current").first()
    total = lots.count()
    sold = lots.filter(status="sold").count()
    unsold = lots.filter(status="unsold").count()
    queued = lots.filter(status="queued").count()
    highest_bid = lots.order_by("-current_bid").values_list("current_bid", flat=True).first() or 0
    top_sale = lots.filter(status="sold").order_by("-sold_price", "position").first()
    purse_rows = list(auction.purses.select_related("team").order_by("team__name"))
    acquisitions = dict(lots.filter(status="sold").values("highest_team_id").annotate(total=Count("pk")).values_list("highest_team_id", "total"))
    for purse in purse_rows:
        purse.acquired_count = acquisitions.get(purse.team_id, 0)
        purse.percent_spent = min(100, (purse.spent * 100) // purse.budget) if purse.budget else 0
    recent_bids = AuctionBid.objects.filter(lot__auction=auction).select_related(
        "team", "lot__player"
    ).order_by("-placed_at", "-pk")[:6]
    upcoming = lots.filter(status="queued")[:8]
    previous = lots.filter(status__in=["sold", "unsold"]).order_by("-position", "-pk")[:8]
    category_sales = list(lots.filter(status="sold").values("category_name").annotate(
        players_sold=Count("pk"), total_spend=Sum("sold_price")
    ).order_by("category_name"))
    player_stats = None
    if current_lot:
        player_stats = PlayerMatchStat.objects.filter(player_id=current_lot.player_id).aggregate(
            runs=Sum("runs"), wickets=Sum("wickets"), appearances=Count("match_id", distinct=True)
        )
    return {
        "auction": auction, "refresh_active": auction.status in {"ready", "running", "paused"},
        "current_lot": current_lot, "total_lots": total,
        "sold_count": sold, "unsold_count": unsold, "queued_count": queued,
        "auctioned_count": sold + unsold, "highest_bid": highest_bid,
        "top_sale": top_sale, "team_purses": purse_rows,
        "recent_bids": recent_bids, "upcoming_lots": upcoming,
        "previous_lots": previous, "category_sales": category_sales,
        "current_player_stats": player_stats,
    }


def auction(request):
    selected = Auction.objects.select_related("tournament").order_by("-created_at", "-pk").first()
    context = _public_auction_context(selected)
    if request.GET.get("fragment") == "live":
        return render(request, "components/auction_live.html", context)
    return render(request, "auction.html", context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def auction_config(request):
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in {"category_save", "category_delete"}:
            raw_category_id = request.POST.get("category_id")
            category_id = _positive_post_id(request, "category_id") if raw_category_id else None
            if raw_category_id and category_id is None:
                messages.error(request, "Choose a valid category.")
                return redirect("auction_config")
            category = get_object_or_404(PlayerCategory, pk=category_id) if category_id else None
            if action == "category_delete":
                if category is None:
                    messages.error(request, "Choose a category to remove.")
                else:
                    try:
                        category.delete()
                        messages.success(request, "Category deleted.")
                    except ProtectedError:
                        messages.error(request, "This category is assigned to players or saved auction lots. Reassign those players before deleting it.")
            else:
                form = PlayerCategoryForm(request.POST, instance=category)
                if form.is_valid():
                    with transaction.atomic():
                        saved_category = form.save()
                        queued_updates = sync_pending_lots_for_category(saved_category)
                    messages.success(request, f"Category saved. {queued_updates} prepared queue lot(s) refreshed; started or completed results retain their saved details.")
                else:
                    messages.error(request, "Category was not saved. Check its name, order and non-negative base price.")
            return redirect("auction_config")

        if action in {"player_save", "player_create"}:
            player_id = _positive_post_id(request, "player_id") if action == "player_save" else None
            if action == "player_save" and player_id is None:
                messages.error(request, "Choose a valid player.")
                return redirect("auction_config")
            player = get_object_or_404(Player, pk=player_id) if player_id else None
            form = PlayerAuctionForm(request.POST, request.FILES, instance=player, initial={"in_auction_pool": True} if player is None else None)
            if form.is_valid():
                protected_fields = {"auction_category", "auction_base_price", "is_marquee", "in_auction_pool"}
                locked = player and player.auction_lots.filter(auction__status__in=["running", "paused"]).exists()
                if locked and protected_fields.intersection(form.changed_data):
                    messages.error(request, "Category, marquee status, pool membership and base-price settings are locked after an auction starts. Saved lot snapshots remain unchanged.")
                else:
                    candidate = form.save(commit=False)
                    has_prepared_lots = player and player.auction_lots.filter(
                        status="queued", auction__status__in=["draft", "ready"]
                    ).exists()
                    if has_prepared_lots and candidate.effective_auction_base_price is None:
                        messages.error(request, "A player already in a prepared auction must have a category price or individual override.")
                    else:
                        with transaction.atomic():
                            saved = form.save()
                            queued_updates = sync_pending_lots_for_player(saved) if player else 0
                        if player is None:
                            messages.success(request, f"{saved.name} was added to the player records.")
                        else:
                            messages.success(request, f"{saved.name}'s auction details were saved. {queued_updates} prepared queue lot(s) refreshed; started or completed results retain their saved details.")
            else:
                messages.error(request, "Player details were not saved. Check the required name and base price.")
            return redirect("auction_config")

        if action == "auction_create":
            form = AuctionCreateForm(request.POST)
            if form.is_valid():
                players_to_queue = list(form.cleaned_data["players"])
                missing_price = [player.name for player in players_to_queue if player.effective_auction_base_price is None]
                if missing_price:
                    messages.error(request, "Assign a category base price or individual base-price override to: " + ", ".join(missing_price[:8]))
                else:
                    tournament = form.cleaned_data["tournament"]
                    with transaction.atomic():
                        new_auction = Auction.objects.create(
                            tournament=tournament, name=form.cleaned_data["name"],
                            bid_increment=form.cleaned_data["bid_increment"], status="ready",
                        )
                        AuctionPurse.objects.bulk_create([
                            AuctionPurse(auction=new_auction, team=team, budget=form.cleaned_data["team_budget"])
                            for team in Team.objects.filter(tournament=tournament).order_by("name")
                        ])
                        players_to_queue.sort(key=lambda player: (
                            player.auction_category.position if player.auction_category_id else 32767,
                            player.auction_category.name.casefold() if player.auction_category_id else "~",
                            player.name.casefold(),
                        ))
                        AuctionLot.objects.bulk_create([
                            AuctionLot(
                                auction=new_auction, player=player, category=player.auction_category,
                                category_name=player.auction_category.name if player.auction_category_id else "Uncategorised",
                                base_price=player.effective_auction_base_price,
                                is_marquee=player.is_marquee, position=index,
                            ) for index, player in enumerate(players_to_queue, 1)
                        ])
                    messages.success(request, f"{new_auction.name} is ready with {len(players_to_queue)} queued players. Team purses and the queue can be adjusted below.")
                    return redirect(f"/organiser/auction/?auction={new_auction.pk}")
            else:
                messages.error(request, "Auction was not created. Add a name, positive bid increment and team budget, then select players.")
            return redirect("auction_config")

        selected_id = request.POST.get("auction_id")
        auction_id = _positive_post_id(request, "auction_id") if selected_id else None
        if auction_id is None:
            messages.error(request, "Choose an auction before changing its controls.")
            return redirect("auction_config")
        selected_auction = get_object_or_404(Auction, pk=auction_id)
        if action == "increment_save":
            form = AuctionIncrementForm(request.POST)
            if selected_auction.status not in {"draft", "ready"}:
                messages.error(request, "The bid increment is locked once the auction starts.")
            elif form.is_valid():
                selected_auction.bid_increment = form.cleaned_data["bid_increment"]
                selected_auction.save(update_fields=["bid_increment", "updated_at"])
                messages.success(request, "Bid increment updated.")
            else:
                messages.error(request, "Enter a positive whole-rupee bid increment.")
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")
        if action == "purse_save":
            purse_id = _positive_post_id(request, "purse_id")
            if purse_id is None:
                messages.error(request, "Choose a valid team purse.")
                return redirect(f"/organiser/auction/?auction={selected_auction.pk}")
            purse = get_object_or_404(AuctionPurse, pk=purse_id, auction=selected_auction)
            form = AuctionPurseForm(request.POST)
            if selected_auction.status not in {"draft", "ready"}:
                messages.error(request, "Team purses are locked once the auction starts.")
            elif form.is_valid() and form.cleaned_data["budget"] >= purse.spent:
                purse.budget = form.cleaned_data["budget"]
                purse.save(update_fields=["budget"])
                messages.success(request, f"{purse.team.name}'s purse was updated.")
            else:
                messages.error(request, "Enter a valid purse amount that is not below the team's recorded spend.")
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")

        if action == "queue_move":
            try:
                move_queued_lot(request.POST.get("lot_id"), request.POST.get("direction"))
                messages.success(request, "Auction queue updated.")
            except AuctionActionError as exc:
                messages.error(request, str(exc))
            except AuctionLot.DoesNotExist:
                messages.error(request, "That queued player is no longer available to move.")
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")

        if action in {"start", "pause", "resume"}:
            try:
                change_auction_state(selected_auction.pk, action)
                messages.success(request, "Auction state updated.")
            except AuctionActionError as exc:
                messages.error(request, str(exc))
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")

        if action == "bid":
            try:
                place_bid(selected_auction.pk, request.POST.get("lot_id"), request.POST.get("team_id"), request.POST.get("amount"), request.user)
                messages.success(request, "Bid accepted and saved in the bid history.")
            except (AuctionActionError, Auction.DoesNotExist, AuctionPurse.DoesNotExist, AuctionLot.DoesNotExist) as exc:
                messages.error(request, str(exc) or "That bid could not be accepted.")
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")

        if action in {"sold", "unsold"}:
            try:
                resolve_current_lot(selected_auction.pk, request.POST.get("lot_id"), action)
                messages.success(request, "Player result recorded and the queue advanced.")
            except (AuctionActionError, Auction.DoesNotExist, AuctionLot.DoesNotExist, AuctionPurse.DoesNotExist) as exc:
                messages.error(request, str(exc) or "That result could not be recorded.")
            return redirect(f"/organiser/auction/?auction={selected_auction.pk}")

        messages.error(request, "That organiser action was not recognised.")
        return redirect("auction_config")

    categories = PlayerCategory.objects.annotate(
        player_count=Count("players", distinct=True), lot_count=Count("auction_lots", distinct=True)
    ).order_by("position", "name")
    for category in categories:
        category.edit_form = PlayerCategoryForm(instance=category)
    active_players_query = Player.objects.filter(is_active=True).select_related("auction_category").prefetch_related("teams").order_by("name")
    selected_category = PlayerCategory.objects.filter(pk=request.GET.get("category")).first() if request.GET.get("category", "").isdigit() else None
    if selected_category:
        active_players_query = active_players_query.filter(auction_category=selected_category)
    marquee_only = request.GET.get("marquee") == "1"
    if marquee_only:
        active_players_query = active_players_query.filter(is_marquee=True)
    active_players = list(active_players_query)
    locked_player_ids = set(AuctionLot.objects.filter(
        auction__status__in=["running", "paused"]
    ).values_list("player_id", flat=True).distinct())
    for player in active_players:
        player.is_auction_locked = player.pk in locked_player_ids
        player.edit_form = PlayerAuctionForm(instance=player)
        if player.is_auction_locked:
            for field in ("auction_category", "auction_base_price", "is_marquee", "in_auction_pool"):
                player.edit_form.fields[field].disabled = True
    auction_list = list(Auction.objects.select_related("tournament").order_by("-created_at", "-pk"))
    requested_auction = request.GET.get("auction")
    selected_auction = next((item for item in auction_list if str(item.pk) == str(requested_auction)), None) if requested_auction else (auction_list[0] if auction_list else None)
    if selected_auction:
        selected_auction.lot_list = list(selected_auction.lots.select_related("player", "category", "highest_team").order_by("position", "pk"))
        selected_auction.purse_list = list(selected_auction.purses.select_related("team").order_by("team__name"))
        current_lot = next((lot for lot in selected_auction.lot_list if lot.status == "current"), None)
        for lot in selected_auction.lot_list:
            lot.can_move_up = lot.status == "queued" and any(other.status == "queued" and other.position < lot.position for other in selected_auction.lot_list)
            lot.can_move_down = lot.status == "queued" and any(other.status == "queued" and other.position > lot.position for other in selected_auction.lot_list)
    context = {
        "categories": categories, "players": active_players,
        "selected_category": selected_category,
        "marquee_only": marquee_only,
        "marquee_player_count": Player.objects.filter(is_active=True, is_marquee=True).count(),
        "locked_player_ids": locked_player_ids, "auction_list": auction_list,
        "selected_auction": selected_auction,
        "current_lot": current_lot if selected_auction else None,
        "category_form": PlayerCategoryForm(), "player_form": PlayerAuctionForm(initial={"in_auction_pool": True}),
        "auction_form": AuctionCreateForm(), "purse_form": AuctionPurseForm(),
        "increment_form": AuctionIncrementForm(initial={"bid_increment": selected_auction.bid_increment} if selected_auction else None),
    }
    return render(request, "organiser_auction.html", context)
