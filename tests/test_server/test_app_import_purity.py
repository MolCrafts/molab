"""``import molexp.server.app`` must have no side effects.

Importing the module builds no app, so it reads no ``~/.molexp/config.json``
and leaves the process-global ``molexp.config`` untouched: a library user who
imports the server does not pick up the operator's model and API key. The app
is built by the factory (``uvicorn --factory molexp.server.app:create_app``).
"""

from __future__ import annotations

import subprocess
import sys


def test_importing_app_module_does_not_touch_global_config() -> None:
    code = (
        "import molexp\n"
        "import molexp.server.app\n"
        "assert dict(molexp.config) == {}, "
        "f'importing molexp.server.app mutated molexp.config: {dict(molexp.config)}'\n"
        "print('clean')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout
