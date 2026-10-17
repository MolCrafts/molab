"""Operator config (``~/.molab/config.json``) — the file loader and writer.

The loader is shared: the CLI (``molab config``), the server (tunnel
settings, ``molab.server.tunnel.settings``) and :mod:`molab.services.auth`
all read the file through :func:`load_operator_config`. The writer is
CLI-only: ``molab config set <section>.<key> <value>`` persists through
:func:`set_operator_values` / :func:`save_operator_config`; the server only
reads. Neither application shell may import the other, so the file API lives
here in the :mod:`molab.services` layer: one source of truth for the path,
the parsing and the atomic write. Nothing here copies the file into the
in-code ``molab.config``; a reader loads the file it needs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mollog import get_logger

logger = get_logger(__name__)

#: Canonical on-disk operator config file (shared with ``molab config``).
OPERATOR_CONFIG_PATH = Path.home() / ".molab" / "config.json"


def load_operator_config(path: Path | None = None) -> dict[str, Any]:
    """Load the operator config file as a plain dict (``{}`` when absent/bad).

    Mirrors the CLI's tolerant behaviour: a missing or unparsable file is an
    empty config, never an exception.
    """
    target = path if path is not None else OPERATOR_CONFIG_PATH
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"operator config at {target} could not be read; ignoring: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def save_operator_config(config: dict[str, Any], path: Path | None = None) -> None:
    """Persist *config* to the operator config file atomically.

    The ONE serialization path for the operator config. Its only writer is
    the CLI (``molab config set``); the server never writes the file. Temp
    file + ``rename``, mode ``0o600`` — the file may carry secrets and must
    never be world-readable, nor half-written.
    """
    target = path if path is not None else OPERATOR_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    # Create the temp file 0600 BEFORE writing: the config may carry API
    # keys, and a default-umask window between write and chmod would leave
    # them world-readable on shared hosts.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(json.dumps(config, indent=2))
    tmp.replace(target)


def set_operator_values(
    updates: dict[str, str | int | float | bool],
    *,
    unset: list[str] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Apply dotted-key *updates* (and *unset* removals) to the operator config.

    Loads, mutates a copy, and saves atomically via
    :func:`save_operator_config`. Dotted keys create intermediate sections
    (``"tunnel.via"`` → ``{"tunnel": {"via": …}}``); unsetting a missing
    key is a no-op. Returns the saved config dict.
    """
    config = load_operator_config(path)
    for key, value in updates.items():
        parts = key.split(".")
        node: dict[str, Any] = config
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    for key in unset or []:
        parts = key.split(".")
        node = config
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                node = {}  # missing section — nothing to unset
                break
            node = child
        node.pop(parts[-1], None)
    save_operator_config(config, path)
    return config


__all__ = [
    "OPERATOR_CONFIG_PATH",
    "load_operator_config",
    "save_operator_config",
    "set_operator_values",
]
