import json
from pathlib import Path
import sqlite3

import pytest

from tools.database_safety import (
    create_backup,
    file_sha256,
    inspect_database,
    read_only_connection,
    verify_backup,
)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO records VALUES (1, 'historical scorecard')")
    return path


def test_backup_preserves_source_and_all_rows(source, tmp_path):
    original_hash = file_sha256(source)
    backup, manifest = create_backup(source, tmp_path / "backups")
    assert file_sha256(source) == original_hash
    assert inspect_database(backup) == inspect_database(source)
    assert verify_backup(backup)["snapshot"]["tables"]["records"]["rows"] == 1
    assert json.loads(manifest.read_text())["source"] == str(source)
    assert backup.stat().st_mode & 0o777 == 0o600


def test_backups_never_overwrite_existing_files(source, tmp_path):
    first, _ = create_backup(source, tmp_path)
    original_hash = file_sha256(first)
    second, _ = create_backup(source, tmp_path)
    assert first != second
    assert file_sha256(first) == original_hash


def test_missing_source_is_not_created(tmp_path):
    missing = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(FileNotFoundError):
        inspect_database(missing)
    assert not missing.exists()


def test_source_connection_rejects_writes(source):
    connection = read_only_connection(source)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM records")
    finally:
        connection.close()


def test_tampered_backup_fails_verification(source, tmp_path):
    backup, _ = create_backup(source, tmp_path)
    with sqlite3.connect(backup) as db:
        db.execute("UPDATE records SET value='modified'")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_backup(backup)


def test_foreign_key_violations_prevent_backup(tmp_path):
    source = tmp_path / "broken.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        db.execute("INSERT INTO child VALUES (123)")
    with pytest.raises(ValueError, match="foreign_key_violations=1"):
        create_backup(source, tmp_path / "backups")


def test_backup_includes_uncheckpointed_wal_rows(tmp_path):
    source = tmp_path / "wal.sqlite3"
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value BLOB)")
        writer.execute("INSERT INTO records VALUES (1, ?)", (b"preserved",))
        writer.commit()
        assert Path(str(source) + "-wal").exists()
        backup, _ = create_backup(source, tmp_path / "backups")
        with sqlite3.connect(backup) as copied:
            assert copied.execute("SELECT value FROM records").fetchone()[0] == b"preserved"
