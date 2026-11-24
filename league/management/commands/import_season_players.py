"""Populate Django Admin Players from scorecard playing squads and batting/bowling tables."""
import json
import re
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from league.models import Player, Team, Tournament

HEADER = re.compile(r'^SINDHI PREMIER LEAGUE', re.I)
ROLE = re.compile(r'\s*\(\s*(?:C|WK|VC)\s*\)\s*', re.I)


def normalize_name(value):
    name = ROLE.sub(' ', str(value or '')).strip()
    return re.sub(r'\s+', ' ', name).strip(' ,')


def squads_from_text(text):
    """CricHeroes page 2: two columns, one player per team per numbered row."""
    lines = [x.strip() for x in text.splitlines() if x.strip() and x.strip() != '\xa0']
    try:
        start = next(i for i, line in enumerate(lines) if line == 'Playing Squad')
    except StopIteration:
        return {}
    end = next((i for i in range(start+1,len(lines)) if HEADER.match(lines[i])), len(lines))
    block=lines[start+1:end]
    if len(block)<5:
        return {}
    teams=block[:2]
    result={teams[0]:[],teams[1]:[]}
    for i,line in enumerate(block[2:]):
        if re.fullmatch(r'\d{1,2}',line):
            j=i+2
            if j+1<len(block) and not re.fullmatch(r'\d{1,2}',block[j]):
                result[teams[0]].append(normalize_name(block[j]))
                result[teams[1]].append(normalize_name(block[j+1]))
    return result


def player_team_names(row):
    mapping={row['teamA']:set(),row['teamB']:set()}
    for team,names in squads_from_text(row.get('scorecardText','')).items():
        key=next((k for k in mapping if k.casefold()==team.casefold()),None)
        if key:
            mapping[key].update(filter(None,names))
    for innings in row.get('innings',[]):
        team=next((k for k in mapping if k.casefold()==str(innings.get('team','')).casefold()),None)
        if team:
            mapping[team].update(normalize_name(b.get('name')) for b in innings.get('batting',[]))
        # Bowling team is the other side in this two-team match.
        if team:
            other=next((k for k in mapping if k!=team),None)
            if other:
                mapping[other].update(normalize_name(b.get('name')) for b in innings.get('bowling',[]))
    return {k:{x for x in v if x} for k,v in mapping.items()}

class Command(BaseCommand):
    help='Import all identifiable players from Season 2/3 scorecard playing squads into Django Admin Players.'
    def add_arguments(self,parser):
        parser.add_argument('--file',required=True)
        parser.add_argument('--season',type=int,required=True)
    @transaction.atomic
    def handle(self,*args,**opts):
        path=Path(opts['file'])
        if not path.exists():raise CommandError(f'File not found: {path}')
        rows=json.loads(path.read_text(encoding='utf-8'))
        try:tournament=Tournament.objects.get(season=opts['season'])
        except Tournament.DoesNotExist:raise CommandError('Import matches for this season first.')
        created=linked=0
        for row in rows:
            for team_name,names in player_team_names(row).items():
                team=Team.objects.filter(tournament=tournament,name__iexact=team_name).first()
                if not team:raise CommandError(f'Team missing: {team_name}')
                for name in names:
                    # Same name is not definitive proof of same identity across different teams.
                    candidates=list(Player.objects.filter(name__iexact=name).order_by('pk'))
                    player=next((p for p in candidates if p.teams.filter(pk=team.pk).exists()),None)
                    if not player:
                        player=next((p for p in candidates if not p.teams.filter(tournament=tournament).exclude(pk=team.pk).exists()),None)
                    if not player:
                        player=Player.objects.create(name=name);created+=1
                    if not player.teams.filter(pk=team.pk).exists():
                        player.teams.add(team);linked+=1
        self.stdout.write(self.style.SUCCESS(f'Season {opts["season"]}: {created} player records created, {linked} team memberships added.'))
