from django.core.validators import MinValueValidator
from django.conf import settings
from django.db import models

class Tournament(models.Model):
    name=models.CharField(max_length=150,default="Sindhi Premier League")
    season=models.PositiveIntegerField(unique=True)
    start_date=models.DateField(null=True,blank=True)
    end_date=models.DateField(null=True,blank=True)
    venue=models.CharField(max_length=180,default="Ulhasnagar",blank=True)
    description=models.TextField(blank=True)
    is_current=models.BooleanField(default=False)
    def __str__(self): return f"{self.name} Season {self.season}"

class Team(models.Model):
    tournament=models.ForeignKey(Tournament,on_delete=models.CASCADE,related_name="teams")
    name=models.CharField(max_length=120)
    short_name=models.CharField(max_length=20,blank=True)
    logo=models.ImageField(upload_to="team_logos/",blank=True,null=True)
    primary_colour=models.CharField(max_length=7,default="#D9A441")
    class Meta: unique_together=("tournament","name")
    def __str__(self): return self.name

class Player(models.Model):
    name=models.CharField(max_length=120)
    city=models.CharField(max_length=100,blank=True)
    photo=models.ImageField(upload_to="player_photos/",blank=True,null=True)
    teams=models.ManyToManyField(Team,blank=True,related_name="players")
    auction_category=models.ForeignKey("PlayerCategory",on_delete=models.PROTECT,null=True,blank=True,related_name="players")
    auction_base_price=models.PositiveBigIntegerField(null=True,blank=True,validators=[MinValueValidator(0)])
    is_marquee=models.BooleanField(default=False)
    in_auction_pool=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    @property
    def effective_auction_base_price(self):
        if self.auction_base_price is not None:
            return self.auction_base_price
        return self.auction_category.base_price if self.auction_category_id else None
    def __str__(self): return self.name


class PlayerCategory(models.Model):
    """Configurable auction category; prices are integer rupees."""
    name=models.CharField(max_length=80,unique=True)
    description=models.CharField(max_length=240,blank=True)
    base_price=models.PositiveBigIntegerField(default=0,validators=[MinValueValidator(0)])
    position=models.PositiveSmallIntegerField(default=0)
    class Meta:
        ordering=["position","name"]
        verbose_name_plural="player categories"
    def __str__(self): return self.name


class Auction(models.Model):
    STATUS=[("draft","Draft"),("ready","Ready"),("running","Live"),("paused","Paused"),("finalized","Finalized")]
    tournament=models.ForeignKey(Tournament,on_delete=models.PROTECT,related_name="auctions")
    name=models.CharField(max_length=150)
    status=models.CharField(max_length=12,choices=STATUS,default="draft")
    bid_increment=models.PositiveBigIntegerField(default=100000,validators=[MinValueValidator(1)])
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-created_at","-pk"]
    def __str__(self): return self.name
    @property
    def current_lot(self):
        return self.lots.filter(status="current").select_related("player","highest_team").first()


class AuctionPurse(models.Model):
    auction=models.ForeignKey(Auction,on_delete=models.CASCADE,related_name="purses")
    team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="auction_purses")
    budget=models.PositiveBigIntegerField(default=0,validators=[MinValueValidator(0)])
    spent=models.PositiveBigIntegerField(default=0,validators=[MinValueValidator(0)])
    class Meta:
        constraints=[models.UniqueConstraint(fields=["auction","team"],name="unique_auction_team_purse")]
        ordering=["team__name"]
    @property
    def remaining(self): return self.budget-self.spent
    def __str__(self): return f"{self.auction}: {self.team} purse"


class AuctionLot(models.Model):
    STATUS=[("queued","Upcoming"),("current","On the block"),("sold","Sold"),("unsold","Unsold")]
    auction=models.ForeignKey(Auction,on_delete=models.CASCADE,related_name="lots")
    player=models.ForeignKey(Player,on_delete=models.PROTECT,related_name="auction_lots")
    category=models.ForeignKey(PlayerCategory,on_delete=models.PROTECT,null=True,blank=True,related_name="auction_lots")
    category_name=models.CharField(max_length=80,blank=True)
    base_price=models.PositiveBigIntegerField(default=0,validators=[MinValueValidator(0)])
    is_marquee=models.BooleanField(default=False)
    position=models.PositiveIntegerField(default=0)
    status=models.CharField(max_length=12,choices=STATUS,default="queued")
    current_bid=models.PositiveBigIntegerField(default=0,validators=[MinValueValidator(0)])
    highest_team=models.ForeignKey(Team,on_delete=models.PROTECT,null=True,blank=True,related_name="leading_auction_lots")
    sold_price=models.PositiveBigIntegerField(null=True,blank=True,validators=[MinValueValidator(0)])
    class Meta:
        constraints=[models.UniqueConstraint(fields=["auction","position"],name="unique_auction_lot_position")]
        ordering=["position","pk"]
    @property
    def next_bid(self):
        return max(self.base_price,self.current_bid+self.auction.bid_increment) if self.highest_team_id else self.base_price
    def __str__(self): return f"{self.auction}: {self.player}"


class AuctionBid(models.Model):
    lot=models.ForeignKey(AuctionLot,on_delete=models.PROTECT,related_name="bids")
    team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="auction_bids")
    amount=models.PositiveBigIntegerField(validators=[MinValueValidator(0)])
    placed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name="auction_bids_placed")
    placed_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-placed_at","-pk"]
    def __str__(self): return f"{self.team}: ₹{self.amount} for {self.lot.player}"

class Match(models.Model):
    STATUS=[("scheduled","Scheduled"),("live","Live"),("completed","Completed"),("abandoned","Abandoned")]
    tournament=models.ForeignKey(Tournament,on_delete=models.CASCADE,related_name="matches")
    match_number=models.PositiveIntegerField(null=True,blank=True)
    date=models.DateField(null=True,blank=True)
    stage=models.CharField(max_length=80,blank=True)
    team_a=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="matches_a")
    team_b=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="matches_b")
    result_text=models.CharField(max_length=255,blank=True)
    winner=models.ForeignKey(Team,on_delete=models.SET_NULL,null=True,blank=True,related_name="wins")
    status=models.CharField(max_length=15,choices=STATUS,default="scheduled")
    cricheroes_url=models.URLField(blank=True)
    ground=models.CharField(max_length=180,blank=True)
    toss=models.CharField(max_length=255,blank=True)
    scorecard_text=models.TextField(blank=True)
    score_summaries=models.JSONField(default=list,blank=True)
    best_batters=models.JSONField(default=list,blank=True)
    best_bowlers=models.JSONField(default=list,blank=True)
    full_scorecard=models.JSONField(default=dict,blank=True)
    def __str__(self): return f"{self.team_a} vs {self.team_b} ({self.tournament.season})"

class Innings(models.Model):
    match=models.ForeignKey(Match,on_delete=models.CASCADE,related_name="innings")
    batting_team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="innings_batted")
    bowling_team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="innings_bowled")
    innings_number=models.PositiveSmallIntegerField(default=1)
    total_runs=models.PositiveIntegerField(default=0)
    wickets=models.PositiveIntegerField(default=0)
    legal_balls=models.PositiveIntegerField(default=0)
    class Meta: unique_together=("match","innings_number")
    def __str__(self): return f"{self.match} innings {self.innings_number}"

class Delivery(models.Model):
    EXTRAS=[("none","None"),("wide","Wide"),("no_ball","No-ball"),("bye","Bye"),("leg_bye","Leg-bye"),("penalty","Penalty")]
    DISMISSALS=[("","Not out"),("bowled","Bowled"),("caught","Caught"),("lbw","LBW"),("run_out","Run out"),("stumped","Stumped"),("hit_wicket","Hit wicket"),("caught_and_bowled","Caught and bowled"),("other","Other")]
    innings=models.ForeignKey(Innings,on_delete=models.CASCADE,related_name="deliveries")
    over_number=models.PositiveSmallIntegerField()
    ball_number=models.PositiveSmallIntegerField()
    batter=models.ForeignKey(Player,on_delete=models.PROTECT,related_name="balls_faced")
    bowler=models.ForeignKey(Player,on_delete=models.PROTECT,related_name="balls_bowled")
    batter_runs=models.PositiveSmallIntegerField(default=0)
    extra_runs=models.PositiveSmallIntegerField(default=0)
    extra_type=models.CharField(max_length=12,choices=EXTRAS,default="none")
    dismissal_type=models.CharField(max_length=20,choices=DISMISSALS,blank=True)
    dismissed_player=models.ForeignKey(Player,on_delete=models.PROTECT,null=True,blank=True,related_name="dismissals")
    fielder=models.ForeignKey(Player,on_delete=models.PROTECT,null=True,blank=True,related_name="fielding_events")
    is_legal=models.BooleanField(default=True)
    @property
    def is_dot_ball(self): return self.is_legal and self.batter_runs+self.extra_runs==0
    def __str__(self): return f"{self.innings} {self.over_number}.{self.ball_number}"

class Sponsor(models.Model):
    CATEGORY=[("title","Title Sponsor"),("associate","Associate Sponsor")]
    name=models.CharField(max_length=150)
    category=models.CharField(max_length=12,choices=CATEGORY)
    logo=models.ImageField(upload_to="sponsor_logos/",blank=True,null=True)
    website=models.URLField(blank=True)
    def __str__(self): return self.name


class ContactEnquiry(models.Model):
    name=models.CharField(max_length=120)
    email=models.EmailField()
    phone=models.CharField(max_length=30,blank=True)
    subject=models.CharField(max_length=160,blank=True)
    message=models.TextField()
    created_at=models.DateTimeField(auto_now_add=True)
    is_resolved=models.BooleanField(default=False)
    def __str__(self): return f"{self.name} — {self.subject or 'Enquiry'}"


class PlayerMatchStat(models.Model):
    """Per-player match aggregates imported from CricHeroes scorecards.

    This is scorecard-level data, not ball-by-ball delivery data.
    """
    match=models.ForeignKey(Match,on_delete=models.CASCADE,related_name="player_stats")
    player=models.ForeignKey(Player,on_delete=models.CASCADE,related_name="match_stats")
    team=models.ForeignKey(Team,on_delete=models.PROTECT,related_name="player_match_stats")
    runs=models.PositiveIntegerField(default=0)
    balls_faced=models.PositiveIntegerField(default=0)
    fours=models.PositiveIntegerField(default=0)
    sixes=models.PositiveIntegerField(default=0)
    batting_dismissed=models.BooleanField(default=False)
    bowling_overs=models.CharField(max_length=12,blank=True)
    bowling_runs=models.PositiveIntegerField(default=0)
    wickets=models.PositiveIntegerField(default=0)
    dot_balls=models.PositiveIntegerField(default=0)
    bowling_maidens=models.PositiveIntegerField(default=0)
    played_in_squad=models.BooleanField(default=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["match","player"],name="unique_player_stat_per_match")]
        ordering=["-runs","-wickets"]
    def __str__(self): return f"{self.player} — {self.match}"
