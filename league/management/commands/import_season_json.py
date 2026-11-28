import copy
import json
import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from league.models import Innings, Match, Player, PlayerMatchStat, Team, Tournament


def clean_name(value):
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    name = re.sub(
        r"\s*\(\s*(?:c|wk|vc|wkt|c\s*&\s*wk|rh[b]?|lh[b]?)\s*\)\s*",
        " ",
        name,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", name).strip(" .")


def over_balls(value):
    """Convert cricket overs notation (for example, 7.4) to legal balls."""
    match = re.fullmatch(r"\s*(\d+)(?:\.(\d))?\s*", str(value or "0"))
    if not match:
        raise ValueError(f"Invalid cricket overs value: {value!r}")
    partial = int(match.group(2) or 0)
    if partial > 5:
        raise ValueError(f"Invalid partial over in cricket overs value: {value!r}")
    return int(match.group(1)) * 6 + partial


def _player_key(value):
    return clean_name(value).casefold()


def _merge_rows(existing_rows, incoming_rows):
    """Update scorecard rows by exact cleaned player name, retaining extra keys."""
    old_rows = {}
    for row in existing_rows or []:
        old_rows.setdefault(_player_key(row.get("name")), []).append(row)

    merged_rows = []
    for row in incoming_rows or []:
        choices = old_rows.get(_player_key(row.get("name")), [])
        merged = copy.deepcopy(choices.pop(0)) if choices else {}
        merged.update(copy.deepcopy(row))
        merged_rows.append(merged)
    return merged_rows


def _merge_scorecard(existing, incoming):
    """Refresh validated scorecard facts without discarding supplemental fields."""
    merged = copy.deepcopy(existing or {})
    old_innings = merged.get("innings") or []
    used = set()
    new_innings = []

    for index, source_innings in enumerate(incoming.get("innings") or []):
        source_key = _player_key(source_innings.get("team"))
        old_index = next(
            (
                i for i, old in enumerate(old_innings)
                if i not in used and _player_key(old.get("team")) == source_key
            ),
            index if index < len(old_innings) and index not in used else None,
        )
        previous = old_innings[old_index] if old_index is not None else {}
        if old_index is not None:
            used.add(old_index)
        innings = copy.deepcopy(previous)
        for key, value in source_innings.items():
            if key in {"batting", "bowling"}:
                innings[key] = _merge_rows(previous.get(key), value)
            elif value is not None:
                innings[key] = copy.deepcopy(value)
        new_innings.append(innings)

    for key, value in incoming.items():
        if key == "innings":
            merged[key] = new_innings
        elif value not in (None, ""):
            merged[key] = copy.deepcopy(value)
    return merged


@transaction.atomic
def import_season_rows(rows, season):
    """Import one season while preserving existing identities and unrelated rows."""
    tournament, _ = Tournament.objects.get_or_create(
        season=season,
        defaults={
            "name": "Sindhi Premier League",
            "venue": "Ulhasnagar",
            "is_current": False,
        },
    )

    dates = []
    for row in rows:
        if row.get("date"):
            try:
                dates.append(date.fromisoformat(row["date"]))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid match date {row.get('date')!r}") from exc
    if dates:
        source_start, source_end = min(dates), max(dates)
        if tournament.start_date is None or source_start < tournament.start_date:
            tournament.start_date = source_start
        if tournament.end_date is None or source_end > tournament.end_date:
            tournament.end_date = source_end
    source_venue = next((row.get("ground") for row in rows if row.get("ground")), None)
    if source_venue and (not tournament.venue or tournament.venue == "Ulhasnagar"):
        tournament.venue = source_venue
    tournament.description = f"Season {season} scorecard archive imported from CricHeroes."
    tournament.save(update_fields=["start_date", "end_date", "venue", "description"])

    counts = {
        "matches_created": 0,
        "matches_updated": 0,
        "players_created": 0,
        "team_links_added": 0,
        "stats_saved": 0,
        "stats_created": 0,
        "innings_saved": 0,
        "innings_created": 0,
        "identity_review": [],
    }
    player_candidates = {}
    for player in Player.objects.all():
        player_candidates.setdefault(_player_key(player.name), []).append(player)

    for row in rows:
        team_a_name = str(row.get("teamA") or "").strip()
        team_b_name = str(row.get("teamB") or "").strip()
        if not team_a_name or not team_b_name:
            raise ValueError(f"Match {row.get('id')}: team names are required")

        team_a, _ = Team.objects.get_or_create(
            tournament=tournament,
            name=team_a_name,
            defaults={"short_name": team_a_name[:20]},
        )
        team_b, _ = Team.objects.get_or_create(
            tournament=tournament,
            name=team_b_name,
            defaults={"short_name": team_b_name[:20]},
        )

        match_date = date.fromisoformat(row["date"]) if row.get("date") else None
        match_id = str(row.get("id") or "").strip()
        cricheroes_url = f"https://cricheroes.com/match/{match_id}" if match_id else ""
        result_text = str(row.get("result") or "").strip()
        winner = None
        if result_text:
            if result_text.casefold().startswith(team_a.name.casefold()):
                winner = team_a
            elif result_text.casefold().startswith(team_b.name.casefold()):
                winner = team_b

        if cricheroes_url:
            existing = Match.objects.filter(
                tournament=tournament, cricheroes_url=cricheroes_url
            ).first()
        else:
            existing = Match.objects.filter(
                tournament=tournament,
                team_a=team_a,
                team_b=team_b,
                date=match_date,
                stage=row.get("stage", ""),
            ).first()

        existing_scorecard = existing.full_scorecard if existing else {}
        incoming_scorecard = {
            "innings": row.get("innings", []),
            "source_pdf": row.get("sourcePdf", ""),
        }
        defaults = {
            "match_number": (
                row.get("matchNumber")
                if row.get("matchNumber") is not None
                else (existing.match_number if existing else None)
            ),
            "date": match_date or (existing.date if existing else None),
            "stage": row.get("stage") or (existing.stage if existing else ""),
            "team_a": team_a,
            "team_b": team_b,
            "winner": winner or (existing.winner if existing else None),
            "result_text": result_text or (existing.result_text if existing else ""),
            "status": "completed" if result_text else (existing.status if existing else "scheduled"),
            "ground": row.get("ground") or (existing.ground if existing else ""),
            "toss": row.get("toss") or (existing.toss if existing else ""),
            "scorecard_text": row.get("scorecardText") or (existing.scorecard_text if existing else ""),
            "score_summaries": row.get("totals") or (existing.score_summaries if existing else []),
            "best_batters": row.get("bestBatters") or (existing.best_batters if existing else []),
            "best_bowlers": row.get("bestBowlers") or (existing.best_bowlers if existing else []),
            "full_scorecard": _merge_scorecard(existing_scorecard, incoming_scorecard),
        }
        if cricheroes_url:
            match, created = Match.objects.update_or_create(
                tournament=tournament,
                cricheroes_url=cricheroes_url,
                defaults=defaults,
            )
        else:
            match, created = Match.objects.update_or_create(
                tournament=tournament,
                team_a=team_a,
                team_b=team_b,
                date=match_date,
                stage=row.get("stage", ""),
                defaults=defaults,
            )
        counts["matches_created" if created else "matches_updated"] += 1

        resolved_players = {}

        def get_player(raw_name, team=None):
            name = clean_name(raw_name)
            if not name or name.casefold() in {"deleted user", "cricheroes deleted user"}:
                return None
            key = name.casefold()
            if key in resolved_players:
                return resolved_players[key]

            candidates = player_candidates.get(key, [])
            player = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1:
                candidate_ids = [candidate.pk for candidate in candidates]
                match_candidates = list(
                    PlayerMatchStat.objects.filter(
                        match=match, player_id__in=candidate_ids
                    ).values_list("player_id", flat=True).distinct()
                )
                if len(match_candidates) == 1:
                    player = next(p for p in candidates if p.pk == match_candidates[0])
                elif len(match_candidates) > 1:
                    player = None
                elif team is not None:
                    team_candidates = [
                        candidate for candidate in candidates
                        if candidate.teams.filter(pk=team.pk).exists()
                    ]
                    if len(team_candidates) == 1:
                        player = team_candidates[0]
                if player is None and not match_candidates:
                    raw_key = str(raw_name or "").strip().casefold()
                    exact_candidates = [
                        candidate for candidate in candidates
                        if candidate.name.strip().casefold() == raw_key
                    ]
                    if len(exact_candidates) == 1:
                        player = exact_candidates[0]
                if player is None:
                    review_item = (str(row.get("sourcePdf") or ""), name)
                    if review_item not in counts["identity_review"]:
                        counts["identity_review"].append(review_item)
                    resolved_players[key] = None
                    return None
            if player is None:
                player = Player.objects.create(name=name)
                player_candidates.setdefault(key, []).append(player)
                counts["players_created"] += 1
            resolved_players[key] = player
            return player

        def team_for(name):
            normalized = str(name or "").strip().casefold()
            if normalized == team_a.name.casefold():
                return team_a
            if normalized == team_b.name.casefold():
                return team_b
            return None

        # Historical scorecards contain innings aggregates, not ball-by-ball events.
        for innings_number, innings_data in enumerate(row.get("innings", []), start=1):
            batting_team = team_for(innings_data.get("team"))
            if batting_team is None:
                continue
            bowling_team = team_b if batting_team.pk == team_a.pk else team_a
            current_innings = Innings.objects.filter(
                match=match, innings_number=innings_number
            ).first()
            # Preserve live scoring data if deliveries have already been recorded.
            if current_innings and current_innings.deliveries.exists():
                continue
            _, innings_created = Innings.objects.update_or_create(
                match=match,
                innings_number=innings_number,
                defaults={
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "total_runs": int(innings_data.get("runs") or 0),
                    "wickets": int(innings_data.get("wickets") or 0),
                    "legal_balls": over_balls(innings_data.get("overs")),
                },
            )
            counts["innings_saved"] += 1
            counts["innings_created"] += int(innings_created)

        stats = {}

        def stat_for(player, team):
            if not player or not team:
                return None
            stat = stats.get(player.pk)
            if stat is None:
                stat = {
                    "player": player,
                    "team": team,
                    "runs": 0,
                    "balls_faced": 0,
                    "fours": 0,
                    "sixes": 0,
                    "batting_dismissed": False,
                    "bowling_overs": "",
                    "_bowling_balls": 0,
                    "bowling_runs": 0,
                    "wickets": 0,
                    "dot_balls": 0,
                    "bowling_maidens": 0,
                    "played_in_squad": False,
                }
                stats[player.pk] = stat
            if stat["team"].pk != team.pk:
                stat["team"] = team
            return stat

        for squad in row.get("squads", []):
            squad_team = team_for(squad.get("team"))
            if squad_team is None:
                continue
            for raw_name in squad.get("players", []):
                stat = stat_for(get_player(raw_name, squad_team), squad_team)
                if stat is not None:
                    stat["played_in_squad"] = True

        for innings_data in row.get("innings", []):
            batting_team = team_for(innings_data.get("team"))
            bowling_team = team_b if batting_team and batting_team.pk == team_a.pk else team_a if batting_team else None
            for batter in innings_data.get("batting", []):
                stat = stat_for(get_player(batter.get("name"), batting_team), batting_team)
                if stat is None:
                    continue
                stat["runs"] += int(batter.get("runs") or 0)
                stat["balls_faced"] += int(batter.get("balls") or 0)
                stat["fours"] += int(batter.get("fours") or 0)
                stat["sixes"] += int(batter.get("sixes") or 0)
                status = str(batter.get("status") or "").strip().casefold()
                if status and "not out" not in status and status not in ("did not bat", "absent hurt"):
                    stat["batting_dismissed"] = True
            for bowler in innings_data.get("bowling", []):
                stat = stat_for(get_player(bowler.get("name"), bowling_team), bowling_team)
                if stat is None:
                    continue
                stat["_bowling_balls"] += over_balls(bowler.get("overs"))
                stat["bowling_runs"] += int(bowler.get("runs") or 0)
                stat["wickets"] += int(bowler.get("wickets") or 0)
                stat["dot_balls"] += int(bowler.get("dot_balls") or 0)
                stat["bowling_maidens"] += int(bowler.get("maidens") or 0)

        for stat in stats.values():
            player = stat.pop("player")
            team = stat.pop("team")
            balls = stat.pop("_bowling_balls", 0)
            stat["bowling_overs"] = f"{balls // 6}.{balls % 6}"
            if not player.teams.filter(pk=team.pk).exists():
                player.teams.add(team)
                counts["team_links_added"] += 1
            _, stat_created = PlayerMatchStat.objects.update_or_create(
                match=match,
                player=player,
                defaults={"team": team, **stat},
            )
            counts["stats_saved"] += 1
            counts["stats_created"] += int(stat_created)

    return counts


class Command(BaseCommand):
    help = "Import a season JSON archive, reusing existing teams, players, matches, and statistics."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--season", type=int, required=True)

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc
        if not isinstance(rows, list):
            raise CommandError("Expected a JSON array of match records.")

        counts = import_season_rows(rows, options["season"])
        for filename, player_name in counts["identity_review"]:
            self.stderr.write(
                self.style.WARNING(
                    f"{filename or 'Scorecard'}: {player_name} has multiple existing player IDs "
                    "with match statistics; that player aggregate was left unchanged for review."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Season {options['season']}: {counts['matches_created']} matches created, "
                f"{counts['matches_updated']} updated; {counts['players_created']} players created; "
                f"{counts['team_links_added']} team links added; {counts['stats_saved']} "
                f"player-match records saved ({counts['stats_created']} new); "
                f"{counts['innings_saved']} innings totals saved ({counts['innings_created']} new)."
            )
        )
