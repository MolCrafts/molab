"""A long-lived process (``molab serve``) sees records another process wrote.

The Folder child cache is a cache of the tree, and the tree is the truth: a
record rewritten on disk by another process (the CLI binding a workflow, an
agent hook, ``molab runs adopt``) must not be shadowed by a stale object.
"""

from __future__ import annotations

from pathlib import Path

from molab.workspace import Workspace


def _lab(tmp_path: Path) -> Workspace:
    ws = Workspace(tmp_path / "lab", name="lab")
    ws.materialize()
    ws.add_project("p").add_experiment("e")
    return ws


def test_a_binding_written_by_another_process_is_seen(tmp_path: Path) -> None:
    served = _lab(tmp_path)
    before = served.project("p").experiment("e")
    assert before.workflow_kind is None

    other = Workspace.load(tmp_path / "lab")
    other.project("p").experiment("e").bind_workflow("code", entrypoint="workflow.py:wf")

    after = served.project("p").experiment("e")
    assert after.workflow_kind == "code"
    assert served.project("p").experiments()[0].workflow_kind == "code"


def test_an_unchanged_record_keeps_the_cached_object(tmp_path: Path) -> None:
    served = _lab(tmp_path)
    first = served.project("p").experiment("e")
    assert served.project("p").experiment("e") is first
    # a child write refreshes the parent's derived index, not its record
    first.add_run(params={"k": 1}, id="r1")
    assert served.project("p").experiment("e") is first


def test_this_process_writing_a_record_keeps_its_object(tmp_path: Path) -> None:
    served = _lab(tmp_path)
    exp = served.project("p").experiment("e")
    exp.bind_workflow("code", entrypoint="workflow.py:wf")
    again = served.project("p").experiment("e")
    assert again is exp
    assert again.workflow_kind == "code"
