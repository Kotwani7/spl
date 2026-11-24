import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from league.models import Delivery, Match


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["organiser", "start_match"])
def test_private_pages_require_login(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert "/django-admin/login/" in response.url


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["organiser", "start_match"])
def test_regular_users_cannot_open_staff_pages(client, name):
    user = get_user_model().objects.create_user(username="spectator")
    client.force_login(user)
    assert client.get(reverse(name)).status_code == 302


@pytest.mark.parametrize("action", ["ball", "end_innings", "finish"])
def test_spectators_cannot_modify_live_match(client, league_data, action):
    response = client.post(reverse("live_match", args=[league_data["match"].pk]), {
        "action": action, "batter": league_data["batter"].pk,
        "bowler": league_data["bowler"].pk,
    })
    assert response.status_code == 302
    assert Delivery.objects.count() == 0
    league_data["match"].refresh_from_db()
    assert league_data["match"].status == "live"
    assert league_data["match"].innings.count() == 1


def test_staff_can_start_match(client, staff, league_data):
    client.force_login(staff)
    response = client.post(reverse("start_match"), {
        "tournament": league_data["tournament"].pk,
        "team_a": league_data["team_a"].pk, "team_b": league_data["team_b"].pk,
    })
    assert response.status_code == 302
    created = Match.objects.latest("pk")
    assert created.status == "live"
    assert created.innings.count() == 1


def test_start_match_rejects_identical_teams(client, staff, league_data):
    client.force_login(staff)
    client.post(reverse("start_match"), {
        "tournament": league_data["tournament"].pk,
        "team_a": league_data["team_a"].pk, "team_b": league_data["team_a"].pk,
    })
    assert Match.objects.count() == 1


@pytest.mark.parametrize("action", ["ball", "end_innings", "finish"])
def test_completed_match_rejects_scoring_actions(client, staff, league_data, action):
    match = league_data["match"]
    match.status = "completed"
    match.save()
    client.force_login(staff)
    response = client.post(reverse("live_match", args=[match.pk]), {
        "action": action, "batter": league_data["batter"].pk,
        "bowler": league_data["bowler"].pk,
    })
    assert response.status_code == 409
    assert Delivery.objects.count() == 0
    assert match.innings.count() == 1


def test_csrf_is_required_for_scoring(staff, league_data):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(staff)
    response = client.post(reverse("live_match", args=[league_data["match"].pk]), {
        "action": "finish",
    })
    assert response.status_code == 403


def test_start_match_and_first_innings_roll_back_together(client, staff, league_data, monkeypatch):
    from league.models import Innings

    def unavailable(*args, **kwargs):
        raise RuntimeError("Simulated innings failure")

    client.force_login(staff)
    monkeypatch.setattr(Innings.objects, "create", unavailable)
    with pytest.raises(RuntimeError, match="Simulated innings failure"):
        client.post(reverse("start_match"), {
            "tournament": league_data["tournament"].pk,
            "team_a": league_data["team_a"].pk, "team_b": league_data["team_b"].pk,
        })
    assert Match.objects.count() == 1
    assert Innings.objects.count() == 1
