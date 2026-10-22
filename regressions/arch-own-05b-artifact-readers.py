"""Hard-coded goldens for execution-relative artifact reads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.workspace import Workspace
from molab.workspace.artifact_repository import walk_artifacts

PAYLOAD = b'{"t": 1}\n'
DIGEST = "sha256:1f0815cc7721e69167e468ea09127f28bc7fd819ffc4304d71f2095b50d89dda"


def main() -> None:
    assert hashlib.sha256(PAYLOAD).hexdigest() == DIGEST.removeprefix("sha256:")
    assert len(PAYLOAD) == 9
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "lab"
        ws = Workspace(root=root, name="Lab")
        ws.materialize()
        project = ws.add_project("p")
        experiment = project.add_experiment("e")
        run = experiment.add_run(params={"seed": 1})
        with run.start() as ctx:
            path = ctx.get_dir("work") / "result.json"
            path.write_bytes(PAYLOAD)
            artifact = ctx.emit_artifact(path, metadata={"task_id": "sim"})
            execution_id = ctx.id
        assert artifact.path == "artifacts/result.json"
        assert artifact.content.size == 9
        assert artifact.content.digest == DIGEST
        location = run.artifact_location(execution_id, artifact)
        assert Path(location).read_bytes() == PAYLOAD
        legacy_path = "projects/p/experiments/e/runs/seed=1/executions/e01/artifacts/result.json"
        legacy = artifact.model_copy(update={"path": legacy_path})
        assert run.artifact_location(execution_id, legacy) == location
        assert [loc.artifact.id for loc in walk_artifacts(ws)] == [artifact.id]
        set_workspace_path_override(Path(str(ws.root)))
        try:
            with TestClient(create_app(serve_static=False)) as client:
                url = (
                    f"/api/projects/{project.id}/experiments/{experiment.id}"
                    f"/runs/{run.id}/executions/{execution_id}"
                )
                content = client.get(f"{url}/artifacts/{artifact.id}/content")
                assert content.status_code == 200, content.text
                assert content.content == PAYLOAD
                outputs = client.get(f"{url}/outputs")
                assert outputs.status_code == 200, outputs.text
                assert outputs.json()["artifacts"][0]["name"] == "result.json"
        finally:
            set_workspace_path_override(None)
    print("arch-own-05b-artifact-readers: ok")


if __name__ == "__main__":
    main()
