import json
import re
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from league.management.commands.import_season_json import clean_name, import_season_rows
from league.models import Match, Player, PlayerMatchStat
from league.scorecard_archives import (
    ScorecardDataError,
    _display,
    _compact,
    extract_pdf_text,
    validate_scorecard_record,
)


SEASON_ARCHIVE_OPTIONS = {
    1: "season_1_archive",
    2: "season_2_archive",
    3: "season_3_archive",
}


def _database_differences(season, record):
    match_id = str(record.get("id") or "").strip()
    if not match_id:
        return []
    existing = Match.objects.filter(
        tournament__season=season,
        cricheroes_url=f"https://cricheroes.com/match/{match_id}",
    ).select_related("team_a", "team_b").first()
    if existing is None:
        return []

    differences = []
    for field, current, source in (
        ("date", existing.date.isoformat() if existing.date else "", record.get("date", "")),
        ("stage", existing.stage, record.get("stage", "")),
        ("result", existing.result_text, record.get("result", "")),
        ("venue", existing.ground, record.get("ground", "")),
        ("toss", existing.toss, record.get("toss", "")),
    ):
        if current and source and _display(current) != _display(source):
            differences.append(field)

    current_innings = existing.full_scorecard.get("innings", []) if existing.full_scorecard else []
    source_innings_rows = record.get("innings", [])
    if len(current_innings) != len(source_innings_rows):
        differences.append("innings count")
    for source_innings in source_innings_rows:
        source_team = _compact(source_innings.get("team"))
        old = next(
            (row for row in current_innings if _compact(row.get("team")) == source_team),
            None,
        )
        if old is None:
            differences.append(f"{source_innings.get('team')} innings")
            continue
        current_order = [str(row.get("name", "")) for row in old.get("batting", [])]
        source_order = [str(row.get("name", "")) for row in source_innings.get("batting", [])]
        if [_compact(name) for name in current_order] != [_compact(name) for name in source_order]:
            differences.append(f"{source_innings.get('team')} batting order/rows")

    expected_player_names = set()
    for squad in record.get("squads", []):
        expected_player_names.update(
            clean_name(name).casefold()
            for name in squad.get("players", [])
            if clean_name(name)
        )
    for innings in source_innings_rows:
        for section in ("batting", "bowling"):
            expected_player_names.update(
                clean_name(row.get("name")).casefold()
                for row in innings.get(section, [])
                if clean_name(row.get("name"))
            )

    player_rows = list(Player.objects.only("pk", "name"))
    player_by_exact_name = {player.name.strip().casefold(): player for player in player_rows}
    player_ids_by_clean_name = {}
    for player in player_rows:
        player_ids_by_clean_name.setdefault(clean_name(player.name).casefold(), []).append(player.pk)
    expected_player_ids = {
        player_by_exact_name[name].pk
        for name in expected_player_names
        if name in player_by_exact_name
    }
    stored_player_ids = set(
        PlayerMatchStat.objects.filter(match=existing).values_list("player_id", flat=True)
    )
    retained_ids = stored_player_ids - expected_player_ids
    retained_names = list(
        Player.objects.filter(pk__in=retained_ids).order_by("name").values_list("name", flat=True)
    )
    if retained_names:
        differences.append(
            f"{len(retained_names)} unmatched existing player-stat rows retained "
            f"({', '.join(retained_names)})"
        )
    ambiguous_names = sorted(
        name
        for name in expected_player_names
        if len(set(player_ids_by_clean_name.get(name, [])) & stored_player_ids) > 1
    )
    if ambiguous_names:
        differences.append(
            "multiple existing player-stat IDs match the same cleaned name "
            f"({', '.join(ambiguous_names)})"
        )
    return differences


class Command(BaseCommand):
    help = "Verify each named season ZIP against the existing JSON, then update the Django scorecards."

    def add_arguments(self, parser):
        parser.add_argument("--season-1-archive", required=True)
        parser.add_argument("--season-2-archive", required=True)
        parser.add_argument("--season-3-archive", required=True)
        parser.add_argument(
            "--json-dir",
            default=str(Path(settings.BASE_DIR) / "data"),
            help="Directory containing season1.json, season2.json, and season3.json.",
        )

    def handle(self, *args, **options):
        json_dir = Path(options["json_dir"])
        if not json_dir.is_dir():
            raise CommandError(f"Season JSON directory not found: {json_dir}")

        for season, option in SEASON_ARCHIVE_OPTIONS.items():
            archive_path = Path(options[option])
            json_path = json_dir / f"season{season}.json"
            if not archive_path.is_file():
                raise CommandError(f"Season {season} scorecard ZIP not found: {archive_path}")
            if not json_path.is_file():
                raise CommandError(f"Season {season} JSON file not found: {json_path}")

        for season, option in SEASON_ARCHIVE_OPTIONS.items():
            self._import_archive(season, Path(options[option]), json_dir / f"season{season}.json")

    def _import_archive(self, season, archive_path, json_path):
        try:
            source_rows = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CommandError(f"Season {season} JSON is invalid: {exc}") from exc
        if not isinstance(source_rows, list):
            raise CommandError(f"Season {season} JSON must contain an array of match records.")

        by_id = {}
        for row in source_rows:
            match_id = str(row.get("id") or "").strip()
            if not match_id or match_id in by_id:
                raise CommandError(f"Season {season} JSON has a missing or duplicate match ID: {match_id!r}")
            by_id[match_id] = row

        try:
            archive = zipfile.ZipFile(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise CommandError(f"Season {season} ZIP could not be opened: {exc}") from exc

        verified_rows = []
        seen_ids = set()
        pdf_count = 0
        skipped = 0
        with archive:
            pdfs = [info for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".pdf")]
            if not pdfs:
                raise CommandError(f"Season {season} ZIP contains no PDFs: {archive_path}")
            for info in pdfs:
                filename = Path(info.filename).name
                pdf_count += 1
                id_match = re.fullmatch(r"Scorecard_(\d+)\.pdf", filename, re.I)
                if not id_match:
                    self.stderr.write(self.style.WARNING(f"{filename}: unexpected scorecard filename; skipped."))
                    skipped += 1
                    continue
                match_id = id_match.group(1)
                if match_id in seen_ids:
                    self.stderr.write(self.style.WARNING(f"{filename}: duplicate PDF match ID; skipped."))
                    skipped += 1
                    continue
                seen_ids.add(match_id)
                source_row = by_id.get(match_id)
                if source_row is None:
                    self.stderr.write(self.style.WARNING(f"{filename}: no Season {season} JSON match with this ID; skipped."))
                    skipped += 1
                    continue
                if source_row.get("sourcePdf") and Path(source_row["sourcePdf"]).name != filename:
                    self.stderr.write(
                        self.style.WARNING(
                            f"{filename}: JSON sourcePdf points to {source_row['sourcePdf']}; match left for review."
                        )
                    )
                    skipped += 1
                    continue
                try:
                    pdf_text = extract_pdf_text(archive.read(info))
                except ScorecardDataError as exc:
                    self.stderr.write(
                        self.style.WARNING(f"{filename}: {exc}; skipped for manual review.")
                    )
                    skipped += 1
                    continue

                record, issues, recovered = validate_scorecard_record(source_row, pdf_text, filename)
                if issues:
                    self.stderr.write(
                        self.style.WARNING(f"{filename}: {', '.join(issues)}; skipped for manual review.")
                    )
                    skipped += 1
                    continue
                for field in recovered:
                    self.stdout.write(
                        f"{filename}: recovered {field} from embedded PDF text; JSON field was blank."
                    )
                differences = _database_differences(season, record)
                identity_prefixes = (
                    "unmatched existing player-stat rows retained",
                    "multiple existing player-stat IDs match the same cleaned name",
                )
                scorecard_differences = [
                    item for item in differences if not item.startswith(identity_prefixes)
                ]
                identity_notes = [
                    item for item in differences if item.startswith(identity_prefixes)
                ]
                if scorecard_differences:
                    self.stderr.write(
                        self.style.WARNING(
                            f"{filename}: existing database {', '.join(dict.fromkeys(scorecard_differences))} "
                            "differs from the verified PDF/JSON; scorecard fields will be refreshed."
                        )
                    )
                for note in identity_notes:
                    self.stderr.write(
                        self.style.WARNING(
                            f"{filename}: {note}; player identities were not merged or deleted."
                        )
                    )
                verified_rows.append(record)

            missing_ids = set(by_id) - seen_ids
            for match_id in sorted(missing_ids):
                filename = str(by_id[match_id].get("sourcePdf") or f"Scorecard_{match_id}.pdf")
                self.stderr.write(
                    self.style.WARNING(f"{Path(filename).name}: expected by Season {season} JSON but missing from ZIP; not imported.")
                )
                skipped += 1

        counts = import_season_rows(verified_rows, season) if verified_rows else {
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
        for filename, player_name in counts["identity_review"]:
            self.stderr.write(
                self.style.WARNING(
                    f"{filename or 'Scorecard'}: {player_name} has multiple existing player IDs "
                    "with match statistics; that player aggregate was left unchanged for review."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Season {season}: {pdf_count} PDFs found; {len(verified_rows)} scorecards verified/imported; "
                f"{skipped} skipped; {counts['matches_created']} matches created, "
                f"{counts['matches_updated']} updated; {counts['players_created']} players created; "
                f"{counts['team_links_added']} team links added; {counts['stats_saved']} player-match records saved "
                f"({counts['stats_created']} new); {counts['innings_saved']} innings totals saved "
                f"({counts['innings_created']} new)."
            )
        )
