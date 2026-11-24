"""Read-only SQLite inspection and verified online backups using only Python stdlib.

Run `python -m tools.database_safety --help`. There is deliberately no restore,
delete, or migrate command: recovery must use a separate database path.
"""

import argparse
import hashlib
import json
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


def read_only_connection(path):
    path = Path(path).resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only = ON")
    return connection


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_connection(connection):
    """Fingerprint every persisted row without returning private row contents."""
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != ["ok"] or foreign_keys:
        raise ValueError(
            f"Database verification failed: integrity={integrity}; "
            f"foreign_key_violations={len(foreign_keys)}"
        )

    schema = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL ORDER BY type, name"
    ).fetchall()
    tables = {}
    for (name,) in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall():
        quoted = quote_identifier(name)
        columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
        # Order by all columns also handles tables without a primary key.
        ordering = ", ".join(quote_identifier(row[1]) for row in columns)
        digest = hashlib.sha256()
        count = 0
        for row in connection.execute(f"SELECT * FROM {quoted} ORDER BY {ordering}"):
            values = [
                {"blob_hex": value.hex()} if isinstance(value, bytes) else value
                for value in row
            ]
            digest.update(json.dumps(values, ensure_ascii=True).encode() + b"\n")
            count += 1
        tables[name] = {"rows": count, "sha256": digest.hexdigest()}

    return {
        "integrity": "ok",
        "foreign_key_violations": 0,
        "schema_sha256": hashlib.sha256(json.dumps(schema).encode()).hexdigest(),
        "tables": tables,
    }


def inspect_database(path):
    with closing(read_only_connection(path)) as connection:
        connection.execute("BEGIN")
        return inspect_connection(connection)


def create_backup(source, directory):
    source = Path(source).resolve(strict=True)
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"spl-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
    manifest_path = Path(str(target) + ".manifest.json")

    # Exclusive creation prevents accidentally replacing any existing backup.
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(read_only_connection(source)) as connection:
            # Inspection and backup read the same consistent snapshot, including WAL.
            connection.execute("BEGIN")
            expected = inspect_connection(connection)
            with closing(sqlite3.connect(target)) as destination:
                connection.backup(destination)
        actual = inspect_database(target)
        if actual != expected:
            raise ValueError("Backup differs from the source database snapshot.")
        manifest = {
            "format_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "backup_filename": target.name,
            "backup_sha256": file_sha256(target),
            "snapshot": actual,
        }
        descriptor = os.open(
            manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
        return target, manifest_path
    except Exception:
        # Retain failed artifacts for diagnosis. A manifest is the success marker.
        raise


def verify_backup(path, manifest_path=None):
    path = Path(path).resolve(strict=True)
    manifest_path = Path(manifest_path or (str(path) + ".manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("Unsupported backup manifest format.")
    if file_sha256(path) != manifest["backup_sha256"]:
        raise ValueError("Backup file checksum mismatch.")
    if inspect_database(path) != manifest["snapshot"]:
        raise ValueError("Backup content differs from its manifest.")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Read-only integrity and row fingerprints")
    inspect.add_argument("--database", default="db.sqlite3")
    backup = commands.add_parser("backup", help="Create and independently verify a new backup")
    backup.add_argument("--database", default="db.sqlite3")
    backup.add_argument("--directory", default="backups")
    verify = commands.add_parser("verify", help="Verify a backup against its manifest")
    verify.add_argument("backup")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            print(json.dumps(inspect_database(args.database), indent=2))
        elif args.command == "backup":
            target, manifest = create_backup(args.database, args.directory)
            print(f"Verified backup: {target}\nManifest: {manifest}")
        else:
            manifest = verify_backup(args.backup)
            count = sum(t["rows"] for t in manifest["snapshot"]["tables"].values())
            print(f"Verified backup: {args.backup} ({count} total rows)")
    except (OSError, sqlite3.Error, ValueError, KeyError) as exc:
        parser.exit(1, f"Database safety check failed: {exc}\n")


if __name__ == "__main__":
    main()
