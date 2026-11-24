import pytest
from django.urls import reverse


@pytest.mark.django_db
@pytest.mark.parametrize("name", [
    "home", "about", "teams", "matches", "players", "leaderboards",
    "sponsors", "register", "contact",
])
def test_public_pages_render_with_no_records(client, name):
    assert client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize("name,key", [
    ("team_detail", "team_a"), ("match_detail", "match"),
    ("live_match", "match"), ("player_detail", "batter"),
])
def test_record_pages_render(client, league_data, name, key):
    assert client.get(reverse(name, args=[league_data[key].pk])).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["teams", "matches", "leaderboards"])
@pytest.mark.parametrize("season", ["invalid", "-1", "99999999999999999999999"])
def test_invalid_season_filters_return_bad_request(client, name, season):
    assert client.get(reverse(name), {"season": season}).status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["team_detail", "match_detail", "live_match", "player_detail"])
def test_unknown_records_return_404(client, name):
    assert client.get(reverse(name, args=[99999])).status_code == 404


def test_team_squad_only_includes_appearances_for_that_team(client, league_data):
    from league.models import PlayerMatchStat

    batter = league_data["batter"]
    batter.teams.add(league_data["team_b"])
    PlayerMatchStat.objects.create(
        match=league_data["match"], player=batter, team=league_data["team_a"],
        runs=4, balls_faced=1,
    )
    response = client.get(reverse("team_detail", args=[league_data["team_b"].pk]))
    assert list(response.context["players"]) == []


def test_unknown_season_does_not_fall_back_to_all_time_rankings(client, league_data):
    response = client.get(reverse("leaderboards"), {"season": 999})
    assert response.status_code == 404
