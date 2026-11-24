import json, re
from datetime import date
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from league.models import Tournament, Team, Match, Player, PlayerMatchStat

def clean_name(value):
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    # Remove scorecard-only role/handedness suffixes without stripping identity text.
    name = re.sub(
        r"\s*\(\s*(?:c|wk|vc|wkt|c\s*&\s*wk|rh[b]?|lh[b]?)\s*\)\s*",
        " ", name, flags=re.I
    )
    return re.sub(r"\s+", " ", name).strip(" .")

def over_balls(value):
    # Cricket overs notation: 3.2 means 20 balls, not 3.2 decimal overs.
    try:
        whole, dot, part = str(value or "0").partition(".")
        return int(whole or 0)*6 + (int(part[:1] or 0) if dot else 0)
    except (ValueError, TypeError): return 0

class Command(BaseCommand):
    help = "Import CricHeroes match scorecards, players, team memberships and player match statistics."
    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--season", type=int, required=True)
    @transaction.atomic
    def handle(self, *args, **opts):
        path=Path(opts["file"])
        if not path.exists(): raise CommandError(f"File not found: {path}")
        try: rows=json.loads(path.read_text(encoding="utf-8"))
        except Exception as e: raise CommandError(f"Invalid JSON: {e}")
        if not isinstance(rows,list): raise CommandError("Expected a JSON array of match records.")
        season=opts["season"]
        tournament,_=Tournament.objects.get_or_create(
            season=season,
            defaults={"name":"Sindhi Premier League","venue":"Ulhasnagar","is_current":False}
        )
        # Keep the tournament's date range and venue in sync with this archive.
        dates=sorted(str(row.get("date")) for row in rows if row.get("date"))
        if dates:
            tournament.start_date=date.fromisoformat(dates[0])
            tournament.end_date=date.fromisoformat(dates[-1])
        tournament.venue=next((row.get("ground") for row in rows if row.get("ground")),"Ulhasnagar")
        tournament.description=f"Season {season} scorecard archive imported from CricHeroes."
        tournament.save(update_fields=["start_date","end_date","venue","description"])
        made=updated=players_created=links=stat_rows=0
        # Exact, case-insensitive global name reuse; no fuzzy identity merges.
        cache={p.name.strip().casefold():p for p in Player.objects.all()}
        for row in rows:
            a=str(row.get("teamA") or "").strip(); b=str(row.get("teamB") or "").strip()
            if not a or not b:
                self.stdout.write(self.style.WARNING(f"Skipped match {row.get('id')}: team names missing")); continue
            ta,_=Team.objects.get_or_create(tournament=tournament,name=a,defaults={"short_name":a[:20]})
            tb,_=Team.objects.get_or_create(tournament=tournament,name=b,defaults={"short_name":b[:20]})
            md=None
            try:
                if row.get("date"): md=date.fromisoformat(row["date"])
            except ValueError: pass
            mid=str(row.get("id") or "")
            url=f"https://cricheroes.com/match/{mid}" if mid else ""
            result_text=row.get("result", "")
            winner=None
            if result_text:
                winner=ta if result_text.casefold().startswith(ta.name.casefold()) else tb if result_text.casefold().startswith(tb.name.casefold()) else None
            defaults={"match_number":row.get("matchNumber"),"date":md,"stage":row.get("stage", ""),"team_a":ta,"team_b":tb,"winner":winner,"result_text":result_text,"status":"completed" if result_text else "scheduled","ground":row.get("ground", ""),"toss":row.get("toss", ""),"scorecard_text":row.get("scorecardText", ""),"score_summaries":row.get("totals", []),"best_batters":row.get("bestBatters", []),"best_bowlers":row.get("bestBowlers", []),"full_scorecard":{"innings":row.get("innings", []),"source_pdf":row.get("sourcePdf", "")}}
            if url: match,created=Match.objects.update_or_create(tournament=tournament,cricheroes_url=url,defaults=defaults)
            else: match,created=Match.objects.update_or_create(tournament=tournament,team_a=ta,team_b=tb,date=md,stage=row.get("stage", ""),defaults=defaults)
            made+=int(created); updated+=int(not created)
            def get_player(raw):
                nonlocal players_created
                name=clean_name(raw)
                if not name or name.casefold() in {"deleted user","cricheroes deleted user"}: return None
                key=name.casefold(); player=cache.get(key)
                if player is None:
                    player=Player.objects.create(name=name); cache[key]=player; players_created+=1
                return player
            def team_for(name):
                n=str(name or "").strip().casefold()
                return ta if n==ta.name.casefold() else tb if n==tb.name.casefold() else None
            # Reset only imported match aggregates so a re-import refreshes the data cleanly.
            PlayerMatchStat.objects.filter(match=match).delete()
            stats={}
            def stat_for(player, team):
                if not player or not team: return None
                key=player.pk
                if key not in stats:
                    stats[key]={"player":player,"team":team,"runs":0,"balls_faced":0,"fours":0,"sixes":0,"batting_dismissed":False,"bowling_overs":"","_bowling_balls":0,"bowling_runs":0,"wickets":0,"dot_balls":0,"bowling_maidens":0,"played_in_squad":False}
                # Prefer the team stated by the squad/innings where known.
                if stats[key]["team"].pk != team.pk: stats[key]["team"]=team
                return stats[key]
            # Playing squads establish appearances and team membership (including non-batters).
            for squad in row.get("squads",[]):
                team=team_for(squad.get("team"))
                if not team: continue
                for raw in squad.get("players",[]):
                    player=get_player(raw); st=stat_for(player,team)
                    if st is not None: st["played_in_squad"]=True
            # Full innings provide actual batting and bowling aggregates (Season 2).
            for inn in row.get("innings",[]):
                batting_team=team_for(inn.get("team"))
                bowling_team=tb if batting_team and batting_team.pk==ta.pk else ta if batting_team else None
                for bat in inn.get("batting",[]):
                    player=get_player(bat.get("name")); st=stat_for(player,batting_team)
                    if st is None: continue
                    st["runs"]+=int(bat.get("runs") or 0); st["balls_faced"]+=int(bat.get("balls") or 0)
                    st["fours"]+=int(bat.get("fours") or 0); st["sixes"]+=int(bat.get("sixes") or 0)
                    status=str(bat.get("status") or "").strip().casefold()
                    if status and "not out" not in status and status not in ("did not bat","absent hurt"): st["batting_dismissed"]=True
                for bowl in inn.get("bowling",[]):
                    player=get_player(bowl.get("name")); st=stat_for(player,bowling_team)
                    if st is None: continue
                    st["_bowling_balls"]+=over_balls(bowl.get("overs"))
                    st["bowling_runs"]+=int(bowl.get("runs") or 0); st["wickets"]+=int(bowl.get("wickets") or 0)
                    st["dot_balls"]+=int(bowl.get("dot_balls") or 0); st["bowling_maidens"]+=int(bowl.get("maidens") or 0)
            # Save player-to-team membership and one appearance/stat record per player per match.
            for st in stats.values():
                player=st.pop("player"); team=st.pop("team")
                bowling_balls=st.pop("_bowling_balls",0)
                st["bowling_overs"]=f"{bowling_balls//6}.{bowling_balls%6}"
                if not player.teams.filter(pk=team.pk).exists(): player.teams.add(team); links+=1
                PlayerMatchStat.objects.create(match=match,player=player,team=team,**st); stat_rows+=1
        self.stdout.write(self.style.SUCCESS(f"Season {season}: {made} matches created, {updated} updated; {players_created} players created; {links} team links added; {stat_rows} player-match records saved."))
