"""``molab init`` mints a new asset id for bytes that still live in an old home.

The old id is not reused. A version directory and an attempt's old product
directory are removed once the bytes have a record a reader can open.
"""

from __future__ import annotations

import json
from pathlib import Path

from molab.workspace.rewrite import rewrite_records


def test_init_remints_legacy_bytes_under_new_ids(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "demo"
    experiment = project / "experiments" / "cooling"
    execution = experiment / "runs" / "seed=1" / "executions" / "e01"
    product = execution / "artifacts"
    product.mkdir(parents=True)
    (product / "note.txt").write_text("from the attempt", encoding="utf-8")
    (product / "metrics.mlp.jsonl").write_text("{}\n", encoding="utf-8")
    (execution / "execution.json").write_text(
        json.dumps(
            {
                "id": "e01",
                "artifacts": [
                    {
                        "id": "old-artifact",
                        "name": "note.txt",
                        "path": "artifacts/note.txt",
                        "media_type": "text/plain",
                        "metadata": {"task_id": "sim"},
                    }
                ],
                "checkpoint_artifact_id": "old-artifact",
                "observed_input_ids": ["gone"],
            }
        ),
        encoding="utf-8",
    )
    legacy = project / "assets" / "model"
    (legacy / "versions").mkdir(parents=True)
    payload = legacy / "payload"
    payload.write_text("imported", encoding="utf-8")
    (legacy / "asset.json").write_text(
        json.dumps(
            {
                "id": "old-asset",
                "title": "model",
                "created_at": "2026-01-02T03:04:05Z",
                "created_by": {"id": "molab", "type": "system", "name": "Molab"},
            }
        ),
        encoding="utf-8",
    )
    (legacy / "versions" / "v001.json").write_text(
        json.dumps({"path": "assets/model/payload", "media_type": "text/plain"}),
        encoding="utf-8",
    )

    rewrite_records(tmp_path, name="demo")

    record = json.loads((execution / "execution.json").read_text(encoding="utf-8"))
    assert "artifacts" not in record
    assert "checkpoint_artifact_id" not in record
    assert "observed_input_ids" not in record
    assert not product.exists()
    assert (execution / "metrics.mlp.jsonl").read_text(encoding="utf-8") == "{}\n"
    assert not (legacy / "versions").exists()

    stored = list(tmp_path.rglob("asset.json"))
    assert stored
    texts = {}
    ids = []
    for path in stored:
        body = json.loads(path.read_text(encoding="utf-8"))
        ids.append(body["id"])
        payload_path = path.parent / body["file"]
        texts[payload_path.read_text(encoding="utf-8")] = body
    assert "old-artifact" not in ids
    assert "old-asset" not in ids
    note = texts["from the attempt"]
    imported = texts["imported"]
    assert note["origin"]["kind"] == "execution"
    assert note["origin"]["task"] == "sim"
    assert note["origin"]["execution_id"] == "e01"
    assert imported["origin"]["kind"] == "import"
    assert note["id"] != imported["id"]


def test_init_reslots_suffixed_products_keeping_the_newest_attempt(tmp_path: Path) -> None:
    from molab.workspace import Workspace

    ws = Workspace(root=tmp_path, name="demo")
    experiment = ws.add_project("p").add_experiment("e")
    run = experiment.add_run(params={"model": "a"})
    assets = Path(str(experiment.path)) / "assets"

    def plant(name: str, title: str, execution_id: str, payload: bytes) -> None:
        directory = assets / name
        directory.mkdir(parents=True)
        (directory / "payload.data").write_bytes(payload)
        (directory / "asset.json").write_text(
            json.dumps(
                {
                    "id": f"id-{name}",
                    "title": title,
                    "file": "payload.data",
                    "content": {"digest": f"sha256:{name}", "size": len(payload), "kind": "file"},
                    "origin": {
                        "kind": "execution",
                        "project_id": "p",
                        "experiment_id": "e",
                        "run_id": run.id,
                        "execution_id": execution_id,
                        "task": "export",
                    },
                    "created_at": "2026-01-01T00:00:00Z",
                    "created_by": {"id": "molab", "type": "system", "name": "Molab"},
                    "tags": {},
                }
            ),
            encoding="utf-8",
        )

    plant("networkdata", "network.data", "e01", b"old")
    plant("networkdata-2", "network.data", "e06", b"new")
    plant("exportlog", "export.log", "e06", b"log")

    rewrite_records(tmp_path, name="demo")

    names = sorted(path.name for path in assets.iterdir())
    assert names == ["model-a--network-data"]
    kept = json.loads((assets / "model-a--network-data" / "asset.json").read_text(encoding="utf-8"))
    assert kept["id"] == "id-networkdata-2"


def test_init_credits_identical_legacy_bytes_to_the_newest_attempt(tmp_path: Path) -> None:
    run_dir = tmp_path / "projects" / "demo" / "experiments" / "cooling" / "runs" / "seed=1"
    for execution_id in ("e01", "e02"):
        execution = run_dir / "executions" / execution_id
        (execution / "artifacts").mkdir(parents=True)
        (execution / "artifacts" / "frag.pdb").write_text("ATOM\n", encoding="utf-8")
        (execution / "execution.json").write_text(
            json.dumps(
                {
                    "id": execution_id,
                    "artifacts": [{"name": "frag.pdb", "path": "artifacts/frag.pdb"}],
                }
            ),
            encoding="utf-8",
        )

    rewrite_records(tmp_path, name="demo")

    records = list(
        (tmp_path / "projects" / "demo" / "experiments" / "cooling" / "assets").glob("*/asset.json")
    )
    assert len(records) == 1
    assert json.loads(records[0].read_text(encoding="utf-8"))["origin"]["execution_id"] == "e02"
