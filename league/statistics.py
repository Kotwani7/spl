
import re
from collections import defaultdict

from .models import PlayerMatchStat, Delivery, Match, Player


# ============================================================
# HELPER: CONVERT OVERS INTO BALLS
# ============================================================

def _overs_to_balls(value):
    """
    Convert cricket overs notation into balls.

    Examples:
    4.0 = 24 balls
    4.2 = 26 balls
    4.5 = 29 balls
    """

    try:
        whole, dot, part = str(value or "0").partition(".")

        return (
            int(whole or 0) * 6
            + (int(part[:1] or 0) if dot else 0)
        )

    except (ValueError, TypeError):
        return 0


# ============================================================
# HELPER: EXTRACT FIELDING CONTRIBUTIONS FROM SCORECARDS
# ============================================================

def extract_fielding_contributions(status):
    """
    Extract catches and run-outs from historical scorecard
    dismissal descriptions.

    Returns:
        [(fielder_name, category), ...]
    """

    if not status:
        return []

    text = str(status).strip()

    # Remove batting handedness and wicketkeeper markers.
    text = re.sub(
        r"\((?:RHB|LHB)\)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = text.replace("†", "").strip()

    # Caught and bowled.
    match = re.search(
        r"\bc\s*&\s*b\s*(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        return [(match.group(1).strip(), "catches")]

    # Ordinary catch: c Fielder b Bowler.
    match = re.search(
        r"\bc\s*(.+?)\s+b\s*",
        text,
        flags=re.IGNORECASE
    )

    if match:
        return [(match.group(1).strip(), "catches")]

    # Run-out: one or more fielders.
    match = re.search(
        r"\brun\s*out\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        names = re.split(r"\s*/\s*", match.group(1))

        return [
            (name.strip(), "run_outs")
            for name in names
            if name.strip()
        ]

    return []


# ============================================================
# MAIN FUNCTION: CALCULATE ALL LEADERBOARDS
# ============================================================

def calculate_leaderboards(tournament_id=None):

    # --------------------------------------------------------
    # 1. FETCH PLAYER MATCH STATISTICS
    # --------------------------------------------------------

    qs = PlayerMatchStat.objects.select_related(
        "player",
        "team",
        "match",
        "match__tournament"
    )

    if tournament_id:
        qs = qs.filter(match__tournament_id=tournament_id)

    batting_data = defaultdict(lambda: {
        "name": "",
        "team": "",
        "runs": 0,
        "balls": 0,
        "fours": 0,
        "sixes": 0,
        "dismissals": 0,
        "matches": set(),
        "wickets": 0
    })

    bowling_data = defaultdict(lambda: {
        "name": "",
        "team": "",
        "wickets": 0,
        "runs_conceded": 0,
        "balls_bowled": 0,
        "dot_balls": 0,
        "matches": set()
    })

    appearance_data = defaultdict(lambda: {
        "name": "",
        "teams": set(),
        "matches": set()
    })

    for record in qs:

        player_id = record.player_id

        # Appearances
        appearance = appearance_data[player_id]
        appearance["name"] = record.player.name
        appearance["teams"].add(record.team.name)
        appearance["matches"].add(record.match_id)

        # Batting
        batting = batting_data[player_id]

        batting["name"] = record.player.name
        batting["team"] = record.team.name
        batting["runs"] += record.runs
        batting["balls"] += record.balls_faced
        batting["fours"] += record.fours
        batting["sixes"] += record.sixes
        batting["dismissals"] += int(record.batting_dismissed)
        batting["matches"].add(record.match_id)
        batting["wickets"] += record.wickets

        # Bowling
        bowling = bowling_data[player_id]

        bowling["name"] = record.player.name
        bowling["team"] = record.team.name
        bowling["wickets"] += record.wickets
        bowling["runs_conceded"] += record.bowling_runs
        bowling["balls_bowled"] += _overs_to_balls(
            record.bowling_overs
        )
        bowling["dot_balls"] += record.dot_balls
        bowling["matches"].add(record.match_id)

    # --------------------------------------------------------
    # 2. PREPARE BATTING LEADERBOARD
    # --------------------------------------------------------

    batting_rows = []
    mvp_rows = []

    batting_rows = []
    mvp_rows = []

    for player_id, data in batting_data.items():

        runs = data["runs"]
        balls = data["balls"]
        fours = data["fours"]
        sixes = data["sixes"]
        wickets = data["wickets"]
        dismissals = data["dismissals"]

        average = (
            round(runs / dismissals, 2)
            if dismissals else None
        )

        strike_rate = (
            round(100 * runs / balls, 2)
            if balls else 0
        )

        matches_played = len(data["matches"])

        # Only include players who have batted.
        if runs or balls:
            batting_rows.append({
                "name": data["name"],
                "team": data["team"],
                "runs": runs,
                "balls": balls,
                "fours": fours,
                "sixes": sixes,
                "average": average,
                "strike_rate": strike_rate,
                "matches_played": matches_played
            })

        # Existing MVP points formula.
        points = (
            runs
            + 7 * fours
            + 9 * sixes
            + 25 * wickets
        )

        # Exclude players with zero MVP points.
        if points > 0:
            mvp_rows.append({
                "name": data["name"],
                "team": data["team"],
                "points": points,
                "runs": runs,
                "fours": fours,
                "sixes": sixes,
                "wickets": wickets
            })

    # --------------------------------------------------------
    # 3. PREPARE BOWLING LEADERBOARD
    # --------------------------------------------------------

    bowling_rows = []

    for player_id, data in bowling_data.items():

        balls_bowled = data["balls_bowled"]

        economy = (
            round(
                data["runs_conceded"] / (balls_bowled / 6),
                2
            )
            if balls_bowled else 0
        )

        if data["wickets"] or balls_bowled:

            bowling_rows.append({
                "name": data["name"],
                "team": data["team"],
                "wickets": data["wickets"],
                "runs_conceded": data["runs_conceded"],
                "economy": economy,
                "dot_balls": data["dot_balls"],
                "matches_played": len(data["matches"])
            })

    # --------------------------------------------------------
    # 4. PREPARE APPEARANCES LEADERBOARD
    # --------------------------------------------------------

    appearances_rows = []

    for data in appearance_data.values():

        appearances_rows.append({
            "name": data["name"],
            "teams": ", ".join(sorted(data["teams"])),
            "matches_played": len(data["matches"])
        })

    # --------------------------------------------------------
    # 5. BEST FIELDER - LIVE DELIVERY DATA
    # --------------------------------------------------------

    fielding_data = defaultdict(lambda: {
        "name": "",
        "dismissals": 0,
        "catches": 0,
        "run_outs": 0,
        "teams": set()
    })

    delivery_qs = (
        Delivery.objects
        .select_related(
            "fielder",
            "innings__match",
            "innings__bowling_team"
        )
        .filter(
            dismissal_type__in=[
                "caught",
                "caught_and_bowled",
                "run_out"
            ]
        )
        .exclude(fielder=None)
    )

    if tournament_id:
        delivery_qs = delivery_qs.filter(
            innings__match__tournament_id=tournament_id
        )

    for delivery in delivery_qs:

        player_id = delivery.fielder_id

        data = fielding_data[player_id]

        data["name"] = delivery.fielder.name
        data["teams"].add(delivery.innings.bowling_team.name)

        if delivery.dismissal_type in (
            "caught",
            "caught_and_bowled"
        ):
            data["catches"] += 1

        elif delivery.dismissal_type == "run_out":
            data["run_outs"] += 1

        data["dismissals"] += 1

    # --------------------------------------------------------
    # 6. BEST FIELDER - HISTORICAL SCORECARD DATA
    # --------------------------------------------------------

    historical_matches = Match.objects.exclude(
        pk__in=Delivery.objects.values("innings__match_id")
    ).select_related(
        "team_a",
        "team_b",
        "tournament"
    )

    if tournament_id:
        historical_matches = historical_matches.filter(
            tournament_id=tournament_id
        )

    # Resolve each historical fielder from one prefetched identity index. Previously
    # every dismissal performed several COUNT/SELECT queries (an N+1 query loop).
    # Retain the existing rule: prefer an unambiguous team match, then a unique
    # global exact name. Never fuzzy-merge identities.
    players_by_name = defaultdict(list)
    for player in Player.objects.prefetch_related("teams"):
        players_by_name[player.name.casefold()].append(
            (player, {team.pk for team in player.teams.all()})
        )

    for match in historical_matches:

        scorecard = match.full_scorecard

        if not isinstance(scorecard, dict):
            continue

        innings_list = scorecard.get("innings", [])

        if not isinstance(innings_list, list):
            continue

        for innings in innings_list:

            batting_team_name = innings.get("team", "")

            if not batting_team_name:
                continue

            batting_team_key = batting_team_name.strip().casefold()

            team_a_key = match.team_a.name.strip().casefold()
            team_b_key = match.team_b.name.strip().casefold()

            # Identify fielding team.
            if batting_team_key == team_a_key:
                fielding_team = match.team_b

            elif batting_team_key == team_b_key:
                fielding_team = match.team_a

            else:
                continue

            batting_entries = innings.get("batting", [])

            if not isinstance(batting_entries, list):
                continue

            for batter in batting_entries:

                if not isinstance(batter, dict):
                    continue

                status = batter.get("status", "")

                contributions = extract_fielding_contributions(
                    status
                )

                for fielder_name, category in contributions:

                    clean_name = (
                        str(fielder_name)
                        .replace("†", "")
                        .strip()
                    )

                    if not clean_name:
                        continue

                    # Exact player-name matching.
                    candidates = players_by_name.get(clean_name.casefold(), [])
                    team_candidates = [
                        candidate for candidate, team_ids in candidates
                        if fielding_team.pk in team_ids
                    ]

                    if len(team_candidates) == 1:
                        player = team_candidates[0]

                    elif len(team_candidates) > 1:
                        continue

                    elif len(candidates) == 1:
                        player = candidates[0][0]

                    else:
                        continue

                    data = fielding_data[player.pk]

                    data["name"] = player.name
                    data["teams"].add(fielding_team.name)

                    if category == "catches":
                        data["catches"] += 1

                    elif category == "run_outs":
                        data["run_outs"] += 1

                    data["dismissals"] += 1

    # --------------------------------------------------------
    # 7. FORMAT FIELDING LEADERBOARD
    # --------------------------------------------------------

    fielding_rows = []

    for data in fielding_data.values():

        fielding_rows.append({
            "name": data["name"],
            "team": ", ".join(sorted(data["teams"])),
            "catches": data["catches"],
            "run_outs": data["run_outs"],
            "dismissals": data["dismissals"]
        })

    # --------------------------------------------------------
    # 8. SORT DOT BALLS LEADERBOARD
    # --------------------------------------------------------

    dot_ball_rows = sorted(
        bowling_rows,
        key=lambda x: (
            x["dot_balls"],
            x["wickets"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 9. RETURN ALL SIX LEADERBOARDS
    # --------------------------------------------------------

    return {

        "batting": sorted(
            batting_rows,
            key=lambda x: (
                x["runs"],
                x["strike_rate"]
            ),
            reverse=True
        ),

        "bowling": sorted(
            bowling_rows,
            key=lambda x: (
                x["wickets"],
                x["dot_balls"]
            ),
            reverse=True
        ),

        "dot_balls": dot_ball_rows,

        "appearances": sorted(
            appearances_rows,
            key=lambda x: (
                x["matches_played"],
                x["name"]
            ),
            reverse=True
        ),

        "mvp": sorted(
            mvp_rows,
            key=lambda x: (
                x["points"],
                x["runs"]
            ),
            reverse=True
        ),

        "fielding": sorted(
            fielding_rows,
            key=lambda x: (
                x["dismissals"],
                x["catches"]
            ),
            reverse=True
        )
    }
