"""Back up the configured SQLite database before any migration/import."""

from pathlib import Path
import sqlite3

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tools.database_safety import create_backup, verify_backup


class Command(BaseCommand):
    help = "Create and verify a private backup of the configured SQLite database."

    def add_arguments(self, parser):
        parser.add_argument("--directory", default=str(settings.BASE_DIR / "backups"))
        parser.add_argument(
            "--if-exists", action="store_true",
            help="Skip a missing database during first-time setup; never create it.",
        )

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("This command supports SQLite only; use verified PostgreSQL backups after cutover.")
        name = str(database["NAME"])
        if name == ":memory:" or name.startswith("file:"):
            raise CommandError("Backup requires a filesystem SQLite path, not memory or a URI.")
        source = Path(name).resolve()
        if not source.exists() and options["if_exists"]:
            self.stdout.write("No existing database; backup skipped for first-time setup.")
            return
        try:
            target, manifest = create_backup(source, options["directory"])
            verify_backup(target, manifest)
        except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
            raise CommandError(f"Database backup failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Verified backup: {target}\nManifest: {manifest}"))
