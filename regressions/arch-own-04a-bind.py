"""Public-API goldens for arch-own-04a-bind.

Hard-coded golden. Provenance: ``.claude/specs/arch-own-04a-bind.md``
Testing strategy (CODE_CANON / DOC_CANON literals and steps 1-6), step 5
rewritten per ``.claude/specs/arch-own-04d-readers.md`` D44 (direct
``workflow.ir.json`` write, ``workflow_kind`` stays None — no
``workflow_source`` kwarg). Digest is stdlib ``hashlib.sha256`` of the canon
UTF-8 bytes, not ``compute_definition_hash`` and not a third-party oracle.
Recorded 2026-10-01. In-process tempfile workspace; no subprocess, no network.

Expected stdout (exactly this line, exit code 0):

    arch-own-04a-bind: ok
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from molab.workspace import Workspace

DOC_V1 = {
    "name": "demo",
    "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
    "links": [],
}
DOC_V2 = {
    "name": "demo",
    "task_configs": [
        {"task_id": "prep", "task_type": "demo.prep"},
        {"task_id": "fit", "task_type": "demo.fit"},
    ],
    "links": [{"source": "prep", "target": "fit"}],
}
CODE_CANON = (
    '{"default_target":null,"description":"","n_replicas":1,"name":"code",'
    '"parameter_space":{},"seeds":null,"tags":[],"workflow_document":null}'
)
DOC_CANON = (
    '{"default_target":null,"description":"","n_replicas":1,"name":"doc",'
    '"parameter_space":{},"seeds":null,"tags":[],"workflow_document":'
    '{"links":[],"name":"demo","task_configs":[{"task_id":"prep","task_type":"demo.prep"}]}}'
)
_IR_NAME = "workflow.ir.json"


def _golden(canon: str) -> str:
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _assert_hash(actual: str, canon: str) -> None:
    expected = _golden(canon)
    if actual != expected:
        raise AssertionError(f"hash {actual} != {expected} canon {canon}")


def _value_error(action: Callable[[], object]) -> None:
    try:
        action()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def _check(root: Path) -> None:
    project = Workspace(root=root, name="lab").add_project("p")

    doc = project.add_experiment("doc", workflow_document=DOC_V1)
    assert doc.workflow_kind == "document"
    assert doc.metadata.revision == 1
    _assert_hash(doc.metadata.definition_hash, DOC_CANON)
    doc_hash = doc.metadata.definition_hash

    doc.bind_workflow("document", document=DOC_V1)
    assert doc.metadata.revision == 1
    assert doc.metadata.definition_hash == doc_hash

    doc_revision_id = doc.metadata.revision_id
    doc.bind_workflow("document", document=DOC_V2)
    assert doc.metadata.revision == 2
    assert doc.metadata.revision_id != doc_revision_id
    reloaded = Workspace(root=root, name="lab").get_project("p").get_experiment("doc")
    assert reloaded.workflow_document == DOC_V2

    code = project.add_experiment("code")
    _assert_hash(code.metadata.definition_hash, CODE_CANON)
    code_revision_id = code.metadata.revision_id
    code_hash = _golden(CODE_CANON)
    code.bind_workflow("code", entrypoint="train.py:build", document=DOC_V1)
    assert code.metadata.revision == 1
    assert code.metadata.revision_id == code_revision_id
    _assert_hash(code.metadata.definition_hash, CODE_CANON)
    code.bind_workflow("code", entrypoint="/elsewhere/train.py:build")
    assert code.metadata.revision == 1
    assert code.metadata.revision_id == code_revision_id
    assert code.metadata.definition_hash == code_hash
    assert not (Path(code.experiment_dir) / _IR_NAME).exists()

    code.bind_workflow("document", document=DOC_V1)
    assert code.metadata.revision == 2
    assert code.metadata.workflow_entrypoint is None
    document_revision_id = code.metadata.revision_id
    code.bind_workflow("code", entrypoint="train.py:build")
    assert code.metadata.revision == 3
    assert code.metadata.revision_id != document_revision_id
    _assert_hash(code.metadata.definition_hash, CODE_CANON)
    assert not (Path(code.experiment_dir) / _IR_NAME).exists()

    legacy = project.add_experiment("legacy")
    assert legacy.workflow_kind is None
    (Path(legacy.experiment_dir) / _IR_NAME).write_text(json.dumps(DOC_V1), encoding="utf-8")
    assert legacy.workflow_kind is None
    legacy_revision_id = legacy.metadata.revision_id
    legacy.bind_workflow("document", document=DOC_V1)
    assert legacy.metadata.revision == 1
    assert legacy.metadata.revision_id == legacy_revision_id
    legacy.bind_workflow("document", document=DOC_V2)
    assert legacy.metadata.revision == 2

    bad = project.add_experiment("bad")
    _value_error(lambda: bad.bind_workflow("document"))
    _value_error(lambda: bad.bind_workflow("document", document=DOC_V1, entrypoint="a.py:f"))
    _value_error(lambda: bad.bind_workflow("script"))
    _value_error(lambda: project.add_experiment("doc", workflow_document=DOC_V1))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _check(Path(tmp))
    print("arch-own-04a-bind: ok")


if __name__ == "__main__":
    main()
