"""Public-API regression for persist-one-01-metrics.

Hard-coded golden: ``ctx.metrics.scalar("train/loss", 0.25, step=1)`` lands at
``executions/<id>/artifacts/metrics.mlp.jsonl`` with ``v == 0.25``. No zarr /
index. Public API only (Workspace / add_run / run.start). No third-party runtime.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molexp.workspace import Workspace


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="persist-one-01-metrics-"))
    ws = Workspace(root / "lab", name="lab")
    run = ws.add_project(name="p").add_experiment(name="e").add_run()
    with run.start() as ctx:
        ctx.metrics.scalar("train/loss", 0.25, step=1)

    eid = run.current_execution_id
    assert eid is not None
    exec_dir = Path(run.run_dir) / "executions" / eid
    wal = exec_dir / "artifacts" / "metrics.mlp.jsonl"
    record = json.loads(wal.read_text().strip())
    assert record["k"] == "train/loss"
    assert record["v"] == 0.25
    assert record["s"] == 1
    assert not (exec_dir / "metrics.mlp.jsonl").exists()
    assert not (exec_dir / "metrics.mlp.zarr").exists()
    assert not (exec_dir / "metrics.mlp.index.json").exists()
    assert not (exec_dir / "artifacts" / "metrics.mlp.zarr").exists()
    assert not (exec_dir / "artifacts" / "metrics.mlp.index.json").exists()
    print("persist-one-01-metrics: ok")


if __name__ == "__main__":
    main()
