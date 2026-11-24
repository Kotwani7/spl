import pytest
from django.db import IntegrityError, transaction

from league.live_stats import save_live_match_statistics
from league.models import Delivery, PlayerMatchStat, Tournament
from league.statistics import _overs_to_balls, calculate_leaderboards


@pytest.mark.parametrize("overs,balls", [(0, 0), (4, 24), ("4.5", 29), ("0.1", 1), ("12.3", 75)])
def test_cricket_overs_are_not_decimal_overs(overs, balls):
    assert _overs_to_balls(overs) == balls


def test_leaderboard_uses_recorded_figures_and_season_scope(league_data):
    PlayerMatchStat.objects.create(
        match=league_data["match"], player=league_data["batter"],
        team=league_data["team_a"], runs=50, balls_faced=25, fours=4, sixes=2,
        batting_dismissed=True,
    )
    PlayerMatchStat.objects.create(
        match=league_data["match"], player=league_data["bowler"],
        team=league_data["team_b"], wickets=2, bowling_runs=29,
        bowling_overs="4.5", dot_balls=10,
    )
    stats = calculate_leaderboards(league_data["tournament"].pk)
    assert stats["batting"][0]["strike_rate"] == 200
    assert stats["batting"][0]["average"] == 50
    assert stats["bowling"][0]["economy"] == 6
    assert stats["mvp"][0]["points"] == 96
    other = Tournament.objects.create(season=100)
    assert calculate_leaderboards(other.pk)["batting"] == []


def test_live_statistics_exclude_byes_and_runouts_from_bowler_figures(league_data):
    common = {
        "innings": league_data["innings"], "batter": league_data["batter"],
        "bowler": league_data["bowler"], "over_number": 0,
    }
    Delivery.objects.create(**common, ball_number=1, batter_runs=4)
    Delivery.objects.create(
        **common, ball_number=2, extra_type="wide", extra_runs=1, is_legal=False
    )
    Delivery.objects.create(**common, ball_number=2, extra_type="bye", extra_runs=2)
    Delivery.objects.create(
        **common, ball_number=3, dismissal_type="run_out",
        dismissed_player=league_data["batter"], fielder=league_data["bowler"],
    )
    assert save_live_match_statistics(league_data["match"]) == 2
    batter = PlayerMatchStat.objects.get(player=league_data["batter"])
    bowler = PlayerMatchStat.objects.get(player=league_data["bowler"])
    assert (batter.runs, batter.balls_faced, batter.batting_dismissed) == (4, 3, True)
    assert (bowler.bowling_runs, bowler.bowling_overs, bowler.wickets) == (5, "0.3", 0)
    save_live_match_statistics(league_data["match"])
    assert PlayerMatchStat.objects.count() == 2


def test_live_statistics_do_not_erase_history_when_no_deliveries_exist(league_data):
    recorded = PlayerMatchStat.objects.create(
        match=league_data["match"], player=league_data["batter"],
        team=league_data["team_a"], runs=50,
    )
    with pytest.raises(ValueError, match="No ball-by-ball"):
        save_live_match_statistics(league_data["match"])
    assert PlayerMatchStat.objects.get(pk=recorded.pk).runs == 50


def test_duplicate_player_match_statistics_are_rejected(league_data):
    values = {
        "match": league_data["match"], "player": league_data["batter"],
        "team": league_data["team_a"],
    }
    PlayerMatchStat.objects.create(**values)
    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerMatchStat.objects.create(**values)


def test_historical_fielding_has_bounded_queries(league_data, django_assert_num_queries):
    bowler = league_data["bowler"]
    bowler.name = "Test fielder"
    bowler.save()
    match = league_data["match"]
    match.full_scorecard = {"innings": [{
        "team": league_data["team_a"].name,
        "batting": [{"status": "c Test fielder b Test bowler"}] * 30,
    }]}
    match.save()
    with django_assert_num_queries(5):
        stats = calculate_leaderboards()
    assert stats["fielding"][0]["catches"] == 30


def test_ambiguous_historical_fielders_are_not_merged(league_data):
    from league.models import Player

    bowler = league_data["bowler"]
    bowler.name = "Test fielder"
    bowler.save()
    duplicate = Player.objects.create(name=bowler.name)
    duplicate.teams.add(league_data["team_b"])
    match = league_data["match"]
    match.full_scorecard = {"innings": [{
        "team": league_data["team_a"].name,
        "batting": [{"status": "c Test fielder b Test bowler"}],
    }]}
    match.save()
    assert calculate_leaderboards()["fielding"] == []
