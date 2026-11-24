from io import StringIO
import sqlite3

from django.core.management import call_command, CommandError
import pytest

from tools.database_safety import inspect_database, verify_backup


def configure_database(monkeypatch, settings, path, engine="django.db.backends.sqlite3"):
    monkeypatch.setitem(settings.DATABASES, "default", {"ENGINE": engine, "NAME": str(path)})


def test_backup_command_uses_configured_database_not_default_file(tmp_path, monkeypatch, settings):
    source = tmp_path / "alternate.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE history (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO history VALUES (1)")
    configure_database(monkeypatch, settings, source)
    directory = tmp_path / "backups"
    call_command("backup_database", directory=str(directory), stdout=StringIO())
    backup = next(directory.glob("*.sqlite3"))
    assert verify_backup(backup)["snapshot"] == inspect_database(source)


def test_first_time_setup_skips_missing_database_without_creating_it(tmp_path, monkeypatch, settings):
    source = tmp_path / "new.sqlite3"
    configure_database(monkeypatch, settings, source)
    call_command("backup_database", if_exists=True, stdout=StringIO())
    assert not source.exists()


def test_missing_database_fails_unless_explicitly_skipped(tmp_path, monkeypatch, settings):
    configure_database(monkeypatch, settings, tmp_path / "missing.sqlite3")
    with pytest.raises(CommandError, match="Database backup failed"):
        call_command("backup_database", stdout=StringIO())


def test_postgres_is_not_silently_treated_as_a_sqlite_path(monkeypatch, settings):
    configure_database(monkeypatch, settings, "league", engine="django.db.backends.postgresql")
    with pytest.raises(CommandError, match="supports SQLite only"):
        call_command("backup_database", stdout=StringIO())
