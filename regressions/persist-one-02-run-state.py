"""Public-API regression for persist-one-02-run-state.

Hard-coded goldens: ``HEARTBEAT_INTERVAL_SECONDS == 30.0``,
``HEARTBEAT_STALE_SECONDS == 600.0``. ``with run.start()`` writes status and
``owner_pid`` to ``run.json``, creates an empty ``alive`` file, and never an
``ops/`` directory. ``refresh_heartbeat`` does not rewrite ``run.json``. After
exit: status succeeded, ``alive`` gone, ownership None. Public API only
(Workspace / add_run / run.start). No third-party runtime.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molexp.workspace import Workspace
from molexp.workspace.run_heartbeat import (
    ALIVE_NAME,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_STALE_SECONDS,
)


def main() -> None:
    assert HEARTBEAT_INTERVAL_SECONDS == 30.0
    assert HEARTBEAT_STALE_SECONDS == 600.0
    assert ALIVE_NAME == "alive"

    root = Path(tempfile.mkdtemp(prefix="persist-one-02-run-state-"))
    ws = Workspace(root / "lab", name="lab")
    run = ws.add_project(name="p").add_experiment(name="e").add_run()
    run_dir = Path(str(run.run_dir))
    run_json = run_dir / "run.json"
    alive = run_dir / ALIVE_NAME
    ops = run_dir / "ops"
    legacy = run_dir / "_ops"

    with run.start() as ctx:
        payload = json.loads(run_json.read_text())
        assert payload["status"] == "running"
        assert payload["owner_pid"] is not None
        assert not ops.exists()
        assert not legacy.exists()
        assert alive.is_file()
        assert alive.stat().st_size == 0
        before = run_json.read_bytes()
        ctx._lifecycle.refresh_heartbeat()
        assert run_json.read_bytes() == before
        assert alive.is_file()
        assert alive.stat().st_size == 0

    after = json.loads(run_json.read_text())
    assert after["status"] == "succeeded"
    assert after["owner_pid"] is None
    assert after["owner_host"] is None
    assert not alive.exists()
    assert not ops.exists()
    assert not legacy.exists()
    print("persist-one-02-run-state: ok")


if __name__ == "__main__":
    main()
