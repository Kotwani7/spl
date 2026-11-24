"""Tests always use a disposable in-memory database, never local league records."""

import os

os.environ["SECRET_KEY"] = "test-only-" + "x" * 60

from .settings import *  # noqa: F403

SECRET_KEY = "test-only-not-a-deployment-secret"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SECURE_SSL_REDIRECT = False
