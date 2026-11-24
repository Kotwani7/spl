import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = """
import json
from config import settings
print(json.dumps({
    'hosts': settings.ALLOWED_HOSTS,
    'origins': settings.CSRF_TRUSTED_ORIGINS,
    'session_secure': settings.SESSION_COOKIE_SECURE,
    'csrf_secure': settings.CSRF_COOKIE_SECURE,
    'redirect': settings.SECURE_SSL_REDIRECT,
    'database': str(settings.DATABASES['default']['NAME']),
    'proxy_header': getattr(settings, 'SECURE_PROXY_SSL_HEADER', None),
}))
"""


def read_settings(**overrides):
    environment = os.environ.copy()
    environment.update({
        "DEBUG": "False", "SECRET_KEY": "test-" + "s" * 60,
        "ALLOWED_HOSTS": " league.example.com, www.example.com ",
        "CSRF_TRUSTED_ORIGINS": "https://league.example.com",
        "SESSION_COOKIE_SECURE": "True", "CSRF_COOKIE_SECURE": "True",
        "SECURE_SSL_REDIRECT": "True", "TRUST_PROXY_HEADERS": "False",
    })
    environment.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=ROOT, env=environment,
        capture_output=True, text=True, check=False,
    )


def test_hosts_origins_and_secure_cookies_come_from_environment():
    result = read_settings()
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["hosts"] == ["league.example.com", "www.example.com"]
    assert values["origins"] == ["https://league.example.com"]
    assert values["session_secure"] and values["csrf_secure"] and values["redirect"]
    assert values["proxy_header"] is None


@pytest.mark.parametrize("key", ["", "short", "replace-with-a-long-random-secret"])
def test_production_rejects_missing_or_weak_secret_key(key):
    result = read_settings(SECRET_KEY=key)
    assert result.returncode != 0
    assert "Set a private SECRET_KEY" in result.stderr


def test_proxy_headers_must_be_explicitly_trusted():
    result = read_settings(TRUST_PROXY_HEADERS="True")
    assert json.loads(result.stdout)["proxy_header"] == ["HTTP_X_FORWARDED_PROTO", "https"]


def test_rehearsals_can_use_an_alternate_database(tmp_path):
    target = str(tmp_path / "rehearsal.sqlite3")
    result = read_settings(SQLITE_PATH=target)
    assert json.loads(result.stdout)["database"] == target
    assert not Path(target).exists()
