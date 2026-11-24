import csv
from datetime import datetime
from django.db import transaction
from .models import Tournament,Team,Player,Match,Innings,Delivery

HEADERS={"season","match_date","stage","team_a","team_b","innings","batting_team","bowling_team","over","ball","batter","bowler","batter_runs","extra_runs","extra_type","dismissal_type"}

@transaction.atomic
def import_delivery_csv(upload):
    rows=upload.read().decode("utf-8-sig").splitlines()
    reader=csv.DictReader(rows)
    missing=HEADERS-set(reader.fieldnames or [])
    if missing: raise ValueError("Missing CSV headers: "+", ".join(sorted(missing)))
    cache={}
    count=0
    for r in reader:
        season=int(r["season"])
        tournament,_=Tournament.objects.get_or_create(season=season,defaults={"name":"Sindhi Premier League"})
        def team(name): return Team.objects.get_or_create(tournament=tournament,name=name.strip())[0]
        def player(name): return Player.objects.get_or_create(name=name.strip())[0]
        a,b=team(r["team_a"]),team(r["team_b"])
        date=datetime.strptime(r["match_date"],"%Y-%m-%d").date()
        key=(season,date,r["stage"],a.pk,b.pk)
        match=cache.get(key)
        if not match:
            match,_=Match.objects.get_or_create(tournament=tournament,date=date,stage=r["stage"],team_a=a,team_b=b,defaults={"status":"completed"})
            cache[key]=match
        bat_team,bowl_team=team(r["batting_team"]),team(r["bowling_team"])
        inn_no=int(r["innings"])
        inn,_=Innings.objects.get_or_create(match=match,innings_number=inn_no,defaults={"batting_team":bat_team,"bowling_team":bowl_team})
        extra=r["extra_type"].strip() or "none"
        dismissed=player(r["dismissed_player"]) if r.get("dismissed_player","").strip() else None
        fielder=player(r["fielder"]) if r.get("fielder","").strip() else None
        Delivery.objects.create(innings=inn,over_number=int(r["over"]),ball_number=int(r["ball"]),batter=player(r["batter"]),bowler=player(r["bowler"]),batter_runs=int(r["batter_runs"] or 0),extra_runs=int(r["extra_runs"] or 0),extra_type=extra,dismissal_type=r["dismissal_type"].strip(),dismissed_player=dismissed,fielder=fielder,is_legal=extra not in ("wide","no_ball"))
        count+=1
    return count
