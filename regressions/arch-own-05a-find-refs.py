"""arch-own-05a: one workspace resolves canonical ``molab:`` references.

Hard-coded golden: the five strings in ``_CANONICAL`` are the spec forms
(project, experiment, run, execution, artifact). Not a live third-party oracle.

Provenance: molab spec arch-own-05a-find-refs, written 2026-10-01.
Public API: ``molab.workspace`` / ``molab.workspace.refs``, ``create_app``,
and ``POST /api/knowledge/doc/embed``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from molab.knowledge import Note
from molab.server.app import create_app
from molab.server.dependencies import set_workspace_path_override
from molab.workspace import Workspace
from molab.workspace.errors import AmbiguousRefError, RefNotFoundError
from molab.workspace.refs import InvalidRefError, is_ref, parse_ref, qualify_run_id

_CANONICAL = (
    "molab:project/P",
    "molab:experiment/E",
    "molab:experiment/E/run/r1",
    "molab:experiment/E/run/r1/execution/e01",
    "molab:experiment/E/run/r1/artifact/A",
)


def _scenario(root: Path) -> None:
    for golden in _CANONICAL:
        assert str(parse_ref(golden)) == golden
    assert is_ref("molab://x") is False

    ws = Workspace(root / "lab", name="Lab")
    project = ws.add_project("p")
    exp_a = project.add_experiment("A")
    exp_b = project.add_experiment("B")
    run_a = exp_a.add_run(id="r1")
    exp_b.add_run(id="r1")
    found_a = ws.find(f"molab:experiment/{exp_a.id}/run/r1")
    found_b = ws.find(f"molab:experiment/{exp_b.id}/run/r1")
    assert found_a.id == found_b.id == "r1"
    assert found_a.experiment.id != found_b.experiment.id

    with run_a.start() as ctx:
        art = ctx.emit_artifact("hello", name="note.txt")
    execution = ws.find(f"molab:experiment/{exp_a.id}/run/r1/execution/e01")
    assert execution.id == "e01"
    artifact = ws.find(f"molab:experiment/{exp_a.id}/run/r1/artifact/{art.id}")
    assert artifact.name == "note.txt"
    try:
        ws.find(f"molab:experiment/{exp_a.id}/run/r1/execution/e09")
    except RefNotFoundError as exc:
        assert exc.segment == "execution"
    else:
        raise AssertionError("missing execution e09 did not raise")

    try:
        qualify_run_id(ws, "r1")
    except AmbiguousRefError as exc:
        assert len(exc.candidates) == 2
    else:
        raise AssertionError("qualify_run_id did not raise")

    for bad in ("molab://projects/x", "molab:experiment/e/asset/x"):
        try:
            parse_ref(bad)
        except InvalidRefError:
            pass
        else:
            raise AssertionError(f"{bad} did not raise InvalidRefError")

    note = Note(Path(str(ws.root)) / "knowledges" / "idea")
    note.write("# Cooling rate\n")
    set_workspace_path_override(Path(str(ws.root)))
    try:
        app = create_app(serve_static=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            ambiguous = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": "r1"},
            )
            missing = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": "missing-run"},
            )
            invalid = client.post(
                "/api/knowledge/doc/embed",
                params={"path": "knowledges/idea.md"},
                json={"target_kind": "run", "target": "molab:asset/x"},
            )
    finally:
        set_workspace_path_override(None)

    assert ambiguous.status_code == 409, ambiguous.text
    assert len(ambiguous.json()["error"]["details"]["candidates"]) == 2
    assert missing.status_code == 404, missing.text
    assert invalid.status_code == 422, invalid.text


def test_arch_own_05a_find_refs() -> None:
    with tempfile.TemporaryDirectory() as raw:
        _scenario(Path(raw))
    print("arch-own-05a-find-refs: ok")


if __name__ == "__main__":
    test_arch_own_05a_find_refs()
