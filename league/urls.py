from django.urls import path
from . import views
urlpatterns=[
 path("",views.home,name="home"),path("about/",views.about,name="about"),path("teams/",views.teams,name="teams"),path("teams/<int:pk>/",views.team_detail,name="team_detail"),
 path("matches/",views.matches,name="matches"),path("matches/<int:pk>/",views.match_detail,name="match_detail"),path("matches/<int:pk>/live/",views.live_match,name="live_match"),path("matches/start/",views.start_match,name="start_match"),
 path("players/",views.players,name="players"),path("players/<int:pk>/",views.player_detail,name="player_detail"),
 path("leaderboards/",views.leaderboards,name="leaderboards"),path("sponsors/",views.sponsors,name="sponsors"),
path("auction/",views.auction,name="auction"),
path("register/",views.register,name="register"),path("contact/",views.contact,name="contact"),
path("organiser/",views.organiser,name="organiser"),
path("organiser/auction/",views.auction_config,name="auction_config")]
