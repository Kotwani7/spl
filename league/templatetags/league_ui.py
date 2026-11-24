"""Read-only presentation data and formatting; no domain mutations or new rules."""

import re

from django import template
from django.db.models import Q

from league.models import Match, Player, Team, Tournament
from league.statistics import calculate_leaderboards

register = template.Library()


@register.filter
def initials(value):
    words = re.findall(r"[A-Za-z0-9]+", str(value or ""))
    return "".join(word[0] for word in words[:3]).upper() or "SPL"


@register.filter
def abbreviation(team):
    if team.short_name and len(team.short_name) <= 5:
        return team.short_name.upper()
    words = re.findall(r"[A-Za-z0-9]+", team.name)
    return "".join(word[0] for word in words[:4]).upper() or "SPL"


@register.filter
def team_colour(value):
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", str(value)) else "#101C35"


@register.filter
def overs(balls):
    try:
        balls = int(balls)
        return f"{balls // 6}.{balls % 6}"
    except (ValueError, TypeError):
        return "—"


@register.filter
def inr(value):
    """Format an integer rupee value using Indian digit grouping."""
    try:
        number = int(value)
    except (ValueError, TypeError):
        return "—"
    sign = "−" if number < 0 else ""
    digits = str(abs(number))
    if len(digits) <= 3:
        return sign + digits
    last = digits[-3:]
    leading = digits[:-3]
    groups = []
    while leading:
        groups.insert(0, leading[-2:])
        leading = leading[:-2]
    return sign + ",".join(groups + [last])


@register.filter
def score_for(match, team):
    key = team.name.strip().casefold()
    for row in match.score_summaries or []:
        if isinstance(row, dict) and str(row.get("team", "")).strip().casefold() == key:
            return {"score": row.get("score", "—"), "overs": row.get("overs", "")}
    source = match.full_scorecard if isinstance(match.full_scorecard, dict) else {}
    for row in source.get("innings", []):
        if str(row.get("team", "")).strip().casefold() == key:
            return {"score": f"{row.get('runs', '—')}/{row.get('wickets', '—')}", "overs": row.get("overs", "")}
    for innings in match.innings.all():
        if innings.batting_team_id == team.pk:
            return {"score": f"{innings.total_runs}/{innings.wickets}", "overs": overs(innings.legal_balls)}
    return {"score": "—", "overs": ""}


@register.simple_tag(takes_context=True)
def league_content(context):
    if context.get("_league_content") is not None:
        return context["_league_content"]
    tournament = context.get("tournament")
    if tournament is None:
        tournament = Tournament.objects.filter(is_current=True).first() or Tournament.objects.order_by("-season").first()
    matches = Match.objects.select_related("team_a", "team_b", "tournament", "winner").prefetch_related("innings")
    recent = list(matches.filter(status="completed").order_by("-date", "-pk")[:4])
    live = list(matches.filter(status="live").order_by("-pk")[:4])
    upcoming = list(matches.filter(status="scheduled").order_by("date", "pk")[:4])
    standings = calculate_leaderboards(tournament.pk) if tournament and context.get("tournament") is not None else {}
    # Existing statistics calculations are reused unchanged. Resolve photos/links
    # only for unambiguous exact identities; never fabricate player portraits.
    identities = {}
    for player in Player.objects.all() if standings else []:
        identities.setdefault(player.name.casefold(), []).append(player)
    for category in ("batting", "bowling", "mvp"):
        for row in standings.get(category, [])[:5]:
            candidates = identities.get(row["name"].casefold(), [])
            row["profile"] = candidates[0] if len(candidates) == 1 else None
    result = {
        "tournament": tournament,
        "seasons": Tournament.objects.order_by("-season"),
        "recent": recent,
        "live": live,
        "upcoming": upcoming,
        "ticker": (live + upcoming + recent)[:4],
        "leaders": standings,
        "teams": Team.objects.filter(tournament=tournament).order_by("name") if tournament else Team.objects.none(),
        "champions": matches.filter(stage__iexact="final", winner__isnull=False).order_by("-tournament__season")[:3],
    }
    context["_league_content"] = result
    return result


@register.simple_tag
def profile_content(records, player):
    rows = list(records.select_related("match__team_a", "match__team_b", "match__tournament", "team"))
    return {
        "rows": rows,
        "seasons": sorted({row.match.tournament.season for row in rows}, reverse=True),
        "max_runs": max((row.runs for row in rows), default=1) or 1,
        "max_wickets": max((row.wickets for row in rows), default=1) or 1,
        "teams": player.teams.select_related("tournament").all(),
    }


@register.simple_tag
def team_matches(team):
    return Match.objects.filter(Q(team_a=team) | Q(team_b=team)).select_related("team_a", "team_b", "tournament", "winner").prefetch_related("innings").order_by("-date", "-pk")


@register.filter
def bar_height(value, maximum):
    try:
        return max(2, round(100 * int(value) / max(1, int(maximum))))
    except (TypeError, ValueError):
        return 2
