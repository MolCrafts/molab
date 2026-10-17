"""Public-API goldens for arch-own-02e-readers.

Every reader of run-level provenance (profile, script, executor facts) and of
the run's status reads the latest ``Execution`` record, not ``run.json``:

1. A run gets one QUEUED attempt via ``run.create_execution`` carrying a
   ``cpu`` profile, the script ``/lab/s.py`` and a slurm executor record
   (job ``4242``).
2. ``run_environment`` / ``run_executor_info`` project that attempt's
   profile, script, scheduler and scheduler job id.
3. ``run.status_label`` is the latest attempt's raw status (``queued``, not
   folded into ``running``), and ``molab runs list p e`` shows the profile
   ``cpu`` read from the attempt.

Expected stdout (exactly this line, exit code 0):

    e01 cpu /lab/s.py slurm 4242 queued True

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory and the CLI is driven through typer's
``CliRunner`` — no subprocess, no network, no third-party runtime.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from molab.cli import app
from molab.cli._common import run_environment, run_executor_info
from molab.profile import ProfileConfig
from molab.workspace import Workspace

_GOLDEN = "e01 cpu /lab/s.py slurm 4242 queued True"


def _check(tmp: Path) -> str:
    root = tmp / "lab"
    ws = Workspace(root, name="Lab")
    ws.materialize()
    exp = ws.add_project("p").add_experiment("e")
    run = exp.add_run(params={"x": 1})
    rec = run.create_execution(
        profile_config=ProfileConfig({"nodes": 2}, name="cpu"),
        environment={"script": "/lab/s.py"},
        executor={"backend": "molq", "scheduler": "slurm", "scheduler_job_id": "4242"},
    )

    env = run_environment(run)
    info = run_executor_info(run)
    listing = CliRunner().invoke(app, ["runs", "list", "p", "e", "--workspace", str(root)])
    print(f"$ molab runs list p e -> {listing.exit_code}", file=sys.stderr)
    print(listing.output, file=sys.stderr)
    assert listing.exit_code == 0, listing.exit_code

    line = " ".join(
        str(part)
        for part in (
            rec.id,
            env["profile"],
            env["script"],
            info["scheduler"],
            info["scheduler_job_id"],
            run.status_label,
            "cpu" in listing.stdout,
        )
    )
    assert line == _GOLDEN, f"{line!r} != {_GOLDEN!r}"
    return line


def main() -> None:
    saved_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        os.chdir(raw)
        try:
            line = _check(Path(raw))
        finally:
            os.chdir(saved_cwd)
    print(line)


if __name__ == "__main__":
    main()
