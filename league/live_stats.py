
from collections import defaultdict
from django.db import transaction
from .models import Delivery, PlayerMatchStat


BOWLER_CREDITED_DISMISSALS = {
    "bowled",
    "caught",
    "caught_and_bowled",
    "lbw",
    "stumped",
    "hit_wicket",
}


@transaction.atomic
def save_live_match_statistics(match):

    deliveries = (
        Delivery.objects.filter(innings__match=match)
        .select_related(
            "innings",
            "innings__batting_team",
            "innings__bowling_team",
            "batter",
            "bowler",
            "fielder",
            "dismissed_player",
        )
        .order_by(
            "innings__innings_number",
            "over_number",
            "ball_number",
        )
    )

    if not deliveries.exists():
        raise ValueError(
            "No ball-by-ball deliveries found. Cannot calculate statistics."
        )

    stats = defaultdict(lambda: {
        "team_id": None,
        "runs": 0,
        "balls_faced": 0,
        "fours": 0,
        "sixes": 0,
        "dismissed": False,
        "bowling_balls": 0,
        "bowling_runs": 0,
        "wickets": 0,
        "dot_balls": 0,
    })

    for delivery in deliveries:

        innings = delivery.innings
        batting_team_id = innings.batting_team_id
        bowling_team_id = innings.bowling_team_id

        # Batting statistics
        batter = stats[delivery.batter_id]
        batter["team_id"] = batting_team_id
        batter["runs"] += delivery.batter_runs

        if delivery.extra_type != "wide":
            batter["balls_faced"] += 1

        if delivery.batter_runs == 4:
            batter["fours"] += 1
        elif delivery.batter_runs == 6:
            batter["sixes"] += 1

        # Bowling statistics
        bowler = stats[delivery.bowler_id]
        bowler["team_id"] = bowling_team_id

        if delivery.is_legal:
            bowler["bowling_balls"] += 1

        if delivery.extra_type not in ("bye", "leg_bye", "penalty"):
            bowler["bowling_runs"] += (
                delivery.batter_runs + delivery.extra_runs
            )

        if delivery.is_dot_ball:
            bowler["dot_balls"] += 1

        # Dismissed batter
        if delivery.dismissed_player_id:
            dismissed = stats[delivery.dismissed_player_id]
            dismissed["team_id"] = batting_team_id
            dismissed["dismissed"] = True

        # Wickets credited to the bowler
        if delivery.dismissal_type in BOWLER_CREDITED_DISMISSALS:
            bowler["wickets"] += 1

        # Register fielders as participants
        if delivery.fielder_id:
            fielder = stats[delivery.fielder_id]
            fielder["team_id"] = bowling_team_id

    # Replace statistics for this match
    PlayerMatchStat.objects.filter(match=match).delete()

    records = []

    for player_id, data in stats.items():

        if data["team_id"] is None:
            continue

        legal_balls = data["bowling_balls"]
        overs = f"{legal_balls // 6}.{legal_balls % 6}"

        records.append(
            PlayerMatchStat(
                match=match,
                player_id=player_id,
                team_id=data["team_id"],
                runs=data["runs"],
                balls_faced=data["balls_faced"],
                fours=data["fours"],
                sixes=data["sixes"],
                batting_dismissed=data["dismissed"],
                bowling_overs=overs,
                bowling_runs=data["bowling_runs"],
                wickets=data["wickets"],
                dot_balls=data["dot_balls"],
                bowling_maidens=0,
                played_in_squad=True,
            )
        )

    PlayerMatchStat.objects.bulk_create(records)

    return len(records)
