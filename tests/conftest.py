"""Root-level test configuration.

Hermetic color environment: the CLI tests assert on plain-text output, but
rich/typer help can still embed ANSI (and even split option spellings like
``--workspace`` across SGR codes) when the invoking shell exports
``FORCE_COLOR`` / ``CLICOLOR_FORCE`` / a fancy ``TERM``. Normalized HERE, at
conftest import — before any test module can instantiate a rich ``Console``
— so ``pytest tests/`` behaves identically in a bare terminal, a colored
shell, a git hook, and CI.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest

os.environ.pop("FORCE_COLOR", None)
os.environ.pop("CLICOLOR_FORCE", None)
os.environ.pop("COLORTERM", None)
os.environ["NO_COLOR"] = "1"
os.environ["TERM"] = "dumb"
os.environ["FORCE_COLOR"] = "0"

# Shared by CLI assertion helpers — strip SGR even if a Console was created
# before this module ran (plugin import order).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Return *text* with CSI/SGR color codes removed."""
    return _ANSI_RE.sub("", text)


@pytest.fixture(autouse=True)
def _hermetic_operator_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """Isolate every test from the developer's ``~/.molab/config.json``.

    * **file** — ``OPERATOR_CONFIG_PATH`` is pointed at a fresh tmp path, so
      nothing reads or writes the operator's real config.
    * **process** — ``molab.config`` is a **process-global** singleton that no
      monkeypatch unwinds; it is snapshotted before the test and restored
      after, so a test that sets a key cannot leak it into the next one.
    """
    import molab
    from molab.services import operator_config

    monkeypatch.setattr(
        operator_config,
        "OPERATOR_CONFIG_PATH",
        tmp_path_factory.mktemp("operator-config") / "config.json",
    )
    before = dict(molab.config)
    yield
    for key in list(molab.config.keys()):
        if key not in before:
            del molab.config[key]
    for key, value in before.items():
        molab.config[key] = value
