from io import BytesIO, StringIO
import json
from pathlib import Path

import pytest
from django.core.management import call_command

from league.importer import import_delivery_csv
from league.models import Delivery, Match, Player, PlayerMatchStat, Team, Tournament


@pytest.mark.django_db
def test_historical_import_preserves_raw_scorecard_and_is_repeatable(tmp_path):
    source = Path(__file__).resolve().parents[1] / "data" / "season1.json"
    # Real source data, imported exclusively into pytest's disposable database.
    original = json.loads(source.read_text(encoding="utf-8"))[0]
    archive = tmp_path / "one-match.json"
    archive.write_text(json.dumps([original]), encoding="utf-8")
    for _ in range(2):
        call_command("import_season_json", file=str(archive), season=1, stdout=StringIO())
        match = Match.objects.get()
        assert match.full_scorecard["innings"] == original["innings"]
        assert match.scorecard_text == original["scorecardText"]
        assert PlayerMatchStat.objects.filter(match=match).exists()
        assert Delivery.objects.count() == 0
    assert Tournament.objects.count() == 1
    assert Team.objects.count() == 2
    assert not Player.objects.filter(name__icontains="deleted user").exists()


@pytest.mark.django_db
def test_invalid_historical_import_rolls_back_everything(tmp_path):
    source = Path(__file__).resolve().parents[1] / "data" / "season1.json"
    original = json.loads(source.read_text(encoding="utf-8"))[0]
    original["innings"][0]["batting"][0]["runs"] = "invalid"
    archive = tmp_path / "invalid.json"
    archive.write_text(json.dumps([original]), encoding="utf-8")
    with pytest.raises(ValueError):
        call_command("import_season_json", file=str(archive), season=1, stdout=StringIO())
    assert Match.objects.count() == 0
    assert Player.objects.count() == 0
    assert Tournament.objects.count() == 0


@pytest.mark.django_db
def test_csv_missing_headers_rejected_without_writes():
    with pytest.raises(ValueError, match="Missing CSV headers"):
        import_delivery_csv(BytesIO(b"season,team_a\n1,A\n"))
    assert Tournament.objects.count() == 0
