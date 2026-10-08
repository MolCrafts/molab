"""Route test for ``GET …/runs/{run_id}/lammps-log`` (shell only).

The log is parsed by ``molpy.io.read_lammps_log``; the route owns the run-path
guard and the wire shape: one stage per ``run`` with a thermo table.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from molexp.server.app import create_app
from molexp.server.dependencies import get_workspace
from molexp.workspace import Workspace

_TWO_RUN_LOG = """LAMMPS (2 Aug 2023)
Per MPI rank memory allocation (min/avg/max) = 3.5 | 3.5 | 3.5 Mbytes
   Step          Temp
         0   300.00
       100   298.00
Loop time of 4.21 on 4 procs for 100 steps with 1000 atoms
Per MPI rank memory allocation (min/avg/max) = 3.5 | 3.5 | 3.5 Mbytes
   Step          Temp          PotEng
       100   298.00        -1234.5
Loop time of 2.10 on 4 procs for 100 steps with 1000 atoms
Total wall time: 0:00:06
"""


@pytest.fixture()
def ws(tmp_path: Path) -> Workspace:
    workspace = Workspace(root=tmp_path / "ws", name="lab")
    workspace.materialize()
    return workspace


@pytest.fixture()
def client(ws: Workspace) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_workspace] = lambda: ws
    return TestClient(app)


def _run_with_log(ws: Workspace) -> str:
    run = ws.add_project("p").add_experiment("e").add_run(params={"x": 1}, id="aabbcc02")
    (run.run_dir / "log.lammps").write_text(_TWO_RUN_LOG, encoding="utf-8")
    return run.id


def test_returns_one_stage_per_thermo_table(client: TestClient, ws: Workspace) -> None:
    run_id = _run_with_log(ws)
    res = client.get(
        f"/api/projects/p/experiments/e/runs/{run_id}/lammps-log", params={"path": "log.lammps"}
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["nStages"] == 2
    assert body["stages"][0] == {
        "columns": ["Step", "Temp"],
        "rows": [[0.0, 300.0], [100.0, 298.0]],
    }
    assert body["stages"][1]["columns"] == ["Step", "Temp", "PotEng"]


def test_rejects_a_path_outside_the_run(client: TestClient, ws: Workspace) -> None:
    run_id = _run_with_log(ws)
    res = client.get(
        f"/api/projects/p/experiments/e/runs/{run_id}/lammps-log", params={"path": "../x.log"}
    )

    assert res.status_code == 400
