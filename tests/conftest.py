import pytest
from django.contrib.auth import get_user_model

from league.models import Innings, Match, Player, Team, Tournament


@pytest.fixture
def league_data(db):
    tournament = Tournament.objects.create(season=99, is_current=True)
    team_a = Team.objects.create(tournament=tournament, name="Test batting team")
    team_b = Team.objects.create(tournament=tournament, name="Test bowling team")
    batter = Player.objects.create(name="Test batter")
    bowler = Player.objects.create(name="Test bowler")
    batter.teams.add(team_a)
    bowler.teams.add(team_b)
    match = Match.objects.create(
        tournament=tournament, team_a=team_a, team_b=team_b, status="live"
    )
    innings = Innings.objects.create(
        match=match, batting_team=team_a, bowling_team=team_b
    )
    return {
        "tournament": tournament, "team_a": team_a, "team_b": team_b,
        "batter": batter, "bowler": bowler, "match": match, "innings": innings,
    }


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        username="test-organiser", password="test-password", is_staff=True
    )
