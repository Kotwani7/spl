"""Protect existing form actions and source figures during the UI overhaul."""

import pytest
from django.urls import reverse

from league.models import PlayerMatchStat
from league.templatetags.league_ui import score_for, team_colour


def test_homepage_uses_the_recorded_season(client, league_data):
    response = client.get(reverse('home'))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'SEASON 99' in content
    assert '22–26 JANUARY 2027' not in content
    assert 'href="/auction/"' in content


def test_profile_keeps_recorded_figures_and_season_controls(client, league_data):
    PlayerMatchStat.objects.create(
        player=league_data['batter'], match=league_data['match'],
        team=league_data['team_a'], runs=37, balls_faced=18, wickets=2,
    )
    response = client.get(reverse('player_detail', args=[league_data['batter'].pk]))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'data-runs="37"' in content
    assert 'data-wickets="2"' in content
    assert '<option value="99">Season 99</option>' in content
    assert 'aria-controls="profile-batting"' in content


@pytest.mark.parametrize('name', ['organiser', 'start_match', 'live_match'])
def test_staff_forms_keep_csrf_and_existing_actions(client, staff, league_data, name):
    client.force_login(staff)
    arguments = [league_data['match'].pk] if name == 'live_match' else []
    response = client.get(reverse(name, args=arguments))
    content = response.content.decode()
    assert response.status_code == 200
    assert 'csrfmiddlewaretoken' in content
    fields = {
        'organiser': ['csv_file'],
        'start_match': ['tournament', 'team_a', 'team_b'],
        'live_match': ['action', 'batter', 'bowler', 'batter_runs', 'extra_runs',
                       'extra_type', 'dismissal_type', 'dismissed_player', 'fielder'],
    }
    for field in fields[name]:
        assert f'name="{field}"' in content
    if name == 'live_match':
        for action in ['ball', 'end_innings', 'finish']:
            assert f'value="{action}"' in content


def test_score_display_uses_source_innings_when_summary_is_incomplete(league_data):
    match = league_data['match']
    match.score_summaries = [{'team': league_data['team_a'].name, 'score': '30/2', 'overs': '4.0'}]
    match.full_scorecard = {'innings': [{'team': league_data['team_b'].name, 'runs': 31, 'wickets': 1, 'overs': '3.2'}]}
    assert score_for(match, league_data['team_b']) == {'score': '31/1', 'overs': '3.2'}
    assert score_for(match, league_data['team_a']) == {'score': '30/2', 'overs': '4.0'}


@pytest.mark.parametrize('value', ['red; background:url(x)', '" onload="alert(1)', '', None])
def test_untrusted_team_colour_cannot_inject_css(value):
    assert team_colour(value) == '#101C35'


@pytest.mark.django_db
@pytest.mark.parametrize('url,status,heading', [
    ('/teams/?season=invalid', 400, 'Let’s try that again.'),
    ('/not-a-league-page/', 404, 'Back to the game.'),
])
def test_error_pages_preserve_status_and_offer_navigation(client, url, status, heading):
    response = client.get(url)
    assert response.status_code == status
    assert heading in response.content.decode()
    assert 'Back to the league' in response.content.decode()


def test_server_error_template_does_not_require_a_working_database():
    from django.template.loader import render_to_string

    # pytest-django blocks every database access for this unmarked test.
    content = render_to_string('500.html')
    assert 'A short break in play.' in content
