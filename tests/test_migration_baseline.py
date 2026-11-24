"""Compare fresh migration output to the audited legacy schema, without row data."""

import json
from pathlib import Path
import re

import pytest
from django.db import connection


def sqlite_schema_contract(database):
    tables = {}
    for name, sql in database.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='table' AND name LIKE 'league_%' ORDER BY name"
    ).fetchall():
        columns = sorted([list(row)[1:] for row in database.execute(f'PRAGMA table_info("{name}")')])
        foreign_keys = sorted([
            list(row)[2:] for row in database.execute(f'PRAGMA foreign_key_list("{name}")')
        ])
        indexes = []
        for index in database.execute(f'PRAGMA index_list("{name}")').fetchall():
            indexed = [row[2] for row in database.execute(f'PRAGMA index_info("{index[1]}")')]
            indexes.append([bool(index[2]), indexed])
        # Collect full CHECK expressions, including nested JSON_VALID calls.
        checks = []
        for match in re.finditer(r"\bCHECK\s*\(", sql, re.I):
            start = match.end()
            level = 1
            end = start
            while level:
                if sql[end] == "(":
                    level += 1
                elif sql[end] == ")":
                    level -= 1
                end += 1
            checks.append(re.sub(r"\s+", " ", sql[start:end - 1]).strip())
        tables[name] = {
            "columns": columns, "foreign_keys": foreign_keys,
            "indexes": sorted(indexes), "checks": sorted(checks),
        }
    return tables


@pytest.mark.django_db
def test_fresh_migrations_match_audited_legacy_schema():
    fixture = Path(__file__).parent / "fixtures" / "legacy_schema.json"
    baseline = json.loads(fixture.read_text())
    with connection.cursor() as cursor:
        assert sqlite_schema_contract(cursor) == baseline
