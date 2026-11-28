import copy
import json
from pathlib import Path

import pytest
from django.urls import reverse

from league.management.commands.import_season_json import import_season_rows
from league.models import Innings, Match, Player, PlayerMatchStat, Team, Tournament
from league.scorecard_archives import validate_scorecard_record


@pytest.mark.django_db
def test_pdf_verified_scorecard_reorders_batting_and_is_idempotent(client):
    source_path = Path(__file__).resolve().parents[1] / "data" / "season2.json"
    source_rows = json.loads(source_path.read_text(encoding="utf-8"))
    source = next(row for row in source_rows if str(row["id"]) == "14798534")

    record, issues, recovered = validate_scorecard_record(
        source,
        source["scorecardText"],
        source["sourcePdf"],
    )
    assert issues == []
    assert recovered == []
    assert record is not None
    assert [row["name"] for row in record["innings"][0]["batting"]] == [
        "Manish Nagdev",
        "Sunny Talreja",
        "SAGAR MATANI",
        "(BABU)JEETU BADLANI",
        "Krish",
        "MJ",
    ]

    first_counts = import_season_rows([record], season=2)
    match = Match.objects.get(cricheroes_url="https://cricheroes.com/match/14798534")
    stat_ids = list(PlayerMatchStat.objects.filter(match=match).order_by("pk").values_list("pk", flat=True))
    innings_ids = list(Innings.objects.filter(match=match).order_by("pk").values_list("pk", flat=True))

    assert first_counts["matches_created"] == 1
    assert match.full_scorecard["innings"][0]["batting"][0]["name"] == "Manish Nagdev"
    assert Innings.objects.filter(match=match, total_runs=117, wickets=4, legal_balls=48).exists()
    assert PlayerMatchStat.objects.filter(match=match).exists()
    assert client.get(reverse("match_detail", args=[match.pk])).status_code == 200
    representative_stat = PlayerMatchStat.objects.filter(match=match).order_by("pk").first()
    assert client.get(reverse("team_detail", args=[representative_stat.team_id])).status_code == 200
    assert client.get(reverse("player_detail", args=[representative_stat.player_id])).status_code == 200
    assert client.get(reverse("leaderboards"), {"season": 2}).status_code == 200
    assert client.get(reverse("matches"), {"season": 2}).status_code == 200

    second_counts = import_season_rows([record], season=2)
    match.refresh_from_db()
    assert second_counts["matches_created"] == 0
    assert second_counts["matches_updated"] == 1
    assert Match.objects.filter(tournament__season=2).count() == 1
    assert Team.objects.filter(tournament__season=2).count() == 2
    assert list(PlayerMatchStat.objects.filter(match=match).order_by("pk").values_list("pk", flat=True)) == stat_ids
    assert list(Innings.objects.filter(match=match).order_by("pk").values_list("pk", flat=True)) == innings_ids


def test_conflicting_json_result_is_not_importable():
    source_path = Path(__file__).resolve().parents[1] / "data" / "season3.json"
    source = next(
        row for row in json.loads(source_path.read_text(encoding="utf-8"))
        if str(row["id"]) == "21874172"
    )
    conflicting = copy.deepcopy(source)
    conflicting["result"] = "A different result"

    record, issues, _ = validate_scorecard_record(
        conflicting,
        source["scorecardText"],
        source["sourcePdf"],
    )
    assert record is None
    assert "result differs between PDF and JSON" in issues


@pytest.mark.django_db
def test_ambiguous_existing_player_ids_are_reported_and_left_unchanged():
    source_path = Path(__file__).resolve().parents[1] / "data" / "season2.json"
    source = next(
        row for row in json.loads(source_path.read_text(encoding="utf-8"))
        if str(row["id"]) == "14798597"
    )
    record, issues, _ = validate_scorecard_record(
        source,
        source["scorecardText"],
        source["sourcePdf"],
    )
    assert issues == []
    record = copy.deepcopy(record)
    record["squads"] = []

    tournament = Tournament.objects.create(season=2)
    team_a = Team.objects.create(tournament=tournament, name=record["teamA"])
    team_b = Team.objects.create(tournament=tournament, name=record["teamB"])
    match = Match.objects.create(
        tournament=tournament,
        team_a=team_a,
        team_b=team_b,
        cricheroes_url=f"https://cricheroes.com/match/{record['id']}",
    )
    canonical = Player.objects.create(name="Vijay Dengra")
    role_suffix = Player.objects.create(name="Vijay Dengra (c & wk)")
    canonical_stat = PlayerMatchStat.objects.create(
        match=match, player=canonical, team=team_a, runs=91, played_in_squad=False
    )
    suffix_stat = PlayerMatchStat.objects.create(
        match=match, player=role_suffix, team=team_a, runs=92, played_in_squad=True
    )

    counts = import_season_rows([record], season=2)

    assert (record["sourcePdf"], "Vijay Dengra") in counts["identity_review"]
    canonical_stat.refresh_from_db()
    suffix_stat.refresh_from_db()
    assert canonical_stat.runs == 91
    assert canonical_stat.played_in_squad is False
    assert suffix_stat.runs == 92
    assert suffix_stat.played_in_squad is True


def test_pdf_text_recovers_result_omitted_from_season_json():
    source_path = Path(__file__).resolve().parents[1] / "data" / "season3.json"
    source = next(
        row for row in json.loads(source_path.read_text(encoding="utf-8"))
        if str(row["id"]) == "21874172"
    )
    source = copy.deepcopy(source)
    source["result"] = ""

    record, issues, recovered = validate_scorecard_record(
        source,
        source["scorecardText"],
        source["sourcePdf"],
    )
    assert issues == []
    assert record["result"] == "BAHUBALI KNIGHTRIDERS won by 33 runs"
    assert "result" in recovered


def test_wrong_pdf_identifier_is_rejected():
    source_path = Path(__file__).resolve().parents[1] / "data" / "season1.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))[0]

    record, issues, _ = validate_scorecard_record(
        source,
        source["scorecardText"],
        "Scorecard_99999999.pdf",
    )
    assert record is None
    assert "PDF filename ID does not match the season JSON record ID" in issues
