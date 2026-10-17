"""Canonical on-disk locations for the auth store."""

from __future__ import annotations

from pathlib import Path

#: Default operator auth root (sibling of ``~/.molab/config.json``).
AUTH_DIR = Path.home() / ".molab" / "auth"
USERS_PATH = AUTH_DIR / "users.json"
SESSIONS_DIR = AUTH_DIR / "sessions"
SECRET_PATH = AUTH_DIR / "secret"


def default_auth_root() -> Path:
    """Return the default ``~/.molab/auth`` directory."""
    return AUTH_DIR
