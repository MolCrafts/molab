"""Public-API goldens for arch-own-02a-record.

An attempt's record carries its creation-time facts from the moment it is
allocated; starting it adds the start-time facts exactly once:

1. ``run.create_execution(bypass_cache=True, environment={"script": "a.py"})``
   allocates ``e01``; the raw ``execution.json`` has ``schema_version == 4``
   and the record has no ``"python"`` key yet (a start-time fact).
2. ``with run.start(execution_id=ex.id)`` runs it; afterwards
   ``run.execution("e01")`` keeps ``script == "a.py"``, gains ``"python"``,
   keeps ``bypass_cache is True`` and is ``succeeded``.
3. Starting ``e01`` a second time raises ``ValueError``.
4. Passing a start-time key (``host``) to ``create_execution`` raises
   ``ValueError`` mentioning ``"start-time"`` and writes no second attempt.

Expected stdout (exactly three lines, exit code 0):

    e01 True 4
    second start: refused
    start-time key at creation: refused

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no network, no subprocess.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.domain import ExecutionMode

_FIRST_LINE_GOLDEN = "e01 True 4"
_SCHEMA_VERSION_GOLDEN = 4


def _check(root: Path) -> None:
    ws = Workspace(root=root / "ws", name="Lab")
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})

    ex = run.create_execution(bypass_cache=True, environment={"script": "a.py"})
    record_path = Path(run.run_dir) / "executions" / ex.id / "execution.json"
    schema_version = json.loads(record_path.read_text())["schema_version"]
    assert schema_version == _SCHEMA_VERSION_GOLDEN, schema_version
    assert "python" not in ex.environment, ex.environment

    with run.start(execution_id=ex.id):
        pass
    done = run.execution("e01")
    assert done.environment["script"] == "a.py", done.environment
    assert "python" in done.environment, done.environment
    assert done.bypass_cache is True, done.bypass_cache
    assert done.status.value == "succeeded", done.status
    line = f"{ex.id} {ex.bypass_cache} {schema_version}"
    assert line == _FIRST_LINE_GOLDEN, line
    print(line)

    try:
        with run.start(execution_id=ex.id):
            pass
    except ValueError:
        print("second start: refused")
    else:
        raise AssertionError("starting e01 a second time must be refused")

    try:
        run.create_execution(mode=ExecutionMode.RERUN, environment={"host": "elsewhere"})
    except ValueError as exc:
        assert "start-time" in str(exc), str(exc)
    else:
        raise AssertionError("a start-time key at creation must be refused")
    assert len(run.executions) == 1, [e.id for e in run.executions]
    print("start-time key at creation: refused")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        _check(Path(raw))


if __name__ == "__main__":
    main()
