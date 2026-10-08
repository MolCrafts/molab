"""Unit tests for ``molab.workspace.project`` (``Project``).

Project entity with experiment management.

Chain-owned test module: created by arch-own-01-cleanup; later arch-own specs
extend it (add classes / tests here rather than creating sibling files).

arch-own-01 pins the materialize ordering: mkdir -> save the entity JSON ->
record history, so the ``ProjectCreated`` commit stages an existing ``project.json``
rather than an empty directory. History stays a soft dependency.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from molab._typing import JSONValue
from molab.workspace import Workspace
from molab.workspace.history import GitHistory


def _spy_history(monkeypatch: pytest.MonkeyPatch, entity_file: str) -> list[tuple[str, bool]]:
    """Replace ``GitHistory.record``; log (event, entity JSON exists in paths[0])."""
    seen: list[tuple[str, bool]] = []
    original = GitHistory.record

    def spy(self: GitHistory, event: str, **kwargs: object) -> str | None:
        paths = kwargs.get("paths") or ()
        assert isinstance(paths, tuple)
        exists = bool(paths) and (Path(str(paths[0])) / entity_file).exists()
        seen.append((event, exists))
        return original(self, event, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(GitHistory, "record", spy)
    return seen


class TestProjectMaterialize:
    def test_entity_json_exists_when_history_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = Workspace(tmp_path, name="lab")
        seen = _spy_history(monkeypatch, "project.json")

        ws.add_project("p")

        recorded = [exists for event, exists in seen if event == "ProjectCreated"]
        assert recorded == [True]


D1 = cast(
    dict[str, JSONValue],
    {
        "name": "demo",
        "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
        "links": [],
    },
)
D2 = cast(
    dict[str, JSONValue],
    {
        "name": "demo",
        "task_configs": [
            {"task_id": "prep", "task_type": "demo.prep"},
            {"task_id": "fit", "task_type": "demo.fit"},
        ],
        "links": [{"source": "prep", "target": "fit"}],
    },
)
DOC_CANON = (
    '{"default_target":null,"description":"","n_replicas":1,"name":"doc",'
    '"parameter_space":{},"seeds":null,"tags":[],"workflow_document":'
    '{"links":[],"name":"demo","task_configs":[{"task_id":"prep","task_type":"demo.prep"}]}}'
)
_IR_NAME = "workflow.ir.json"


def _golden(canon: str) -> str:
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _meta_bytes(exp) -> bytes:
    return (Path(exp.experiment_dir) / "experiment.json").read_bytes()


def _ir_bytes(exp) -> bytes:
    return (Path(exp.experiment_dir) / _IR_NAME).read_bytes()


class TestProjectWorkflowDocument:
    """arch-own-04a ``workflow_document=`` on add/set. ``workflow_source`` is gone (D44)."""

    def test_add_document_is_born_at_revision_1(
        self, project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _spy_history(monkeypatch, "experiment.json")

        exp = project.add_experiment("doc", workflow_document=D1)

        assert exp.workflow_kind == "document"
        assert exp.metadata.revision == 1
        assert exp.workflow_document == D1
        assert exp.metadata.definition_hash == _golden(DOC_CANON), DOC_CANON
        assert [event for event, _exists in seen] == ["ExperimentCreated"]

    def test_workflow_source_kwarg_is_type_error(self, project) -> None:
        with pytest.raises(TypeError):
            project.add_experiment(  # type: ignore[call-arg]
                "e",
                workflow_document=D1,
                workflow_source="x",
            )

        assert not (Path(project.project_dir) / "experiments" / "e").exists()

    def test_set_experiment_field_and_document_bump_once(self, project) -> None:
        project.add_experiment("e", workflow_document=D1)

        exp = project.set_experiment("e", description="new", workflow_document=D2)

        assert exp.metadata.revision == 2
        assert exp.description == "new"
        assert exp.workflow_document == D2

    def test_set_experiment_document_on_unbound_stays_revision_1(self, project) -> None:
        project.add_experiment("e")

        exp = project.set_experiment("e", workflow_document=D1)

        assert exp.metadata.revision == 1
        assert exp.workflow_kind == "document"
        assert exp.workflow_document == D1

    def test_set_experiment_params_bumps_revision(self, project) -> None:
        project.add_experiment("e")

        exp = project.set_experiment("e", params={"lr": 1e-4})

        assert exp.metadata.revision == 2
        assert exp.params == {"lr": 1e-4}

    def test_add_same_document_twice_creates_once(
        self, project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _spy_history(monkeypatch, "experiment.json")

        first = project.add_experiment("doc", workflow_document=D1)
        second = project.add_experiment("doc", workflow_document=D1)

        assert second.id == first.id
        assert second.metadata.revision == 1
        created = [event for event, _exists in seen if event == "ExperimentCreated"]
        revised = [event for event, _exists in seen if event == "ExperimentRevised"]
        assert created == ["ExperimentCreated"]
        assert revised == []

    def test_add_different_document_raises_and_keeps_bytes(self, project) -> None:
        exp = project.add_experiment("doc", workflow_document=D1)
        meta = _meta_bytes(exp)
        ir = _ir_bytes(exp)

        with pytest.raises(ValueError):
            project.add_experiment("doc", workflow_document=D2)

        assert _meta_bytes(exp) == meta
        assert _ir_bytes(exp) == ir

    def test_add_document_on_unbound_name_raises(self, project) -> None:
        exp = project.add_experiment("code")
        meta = _meta_bytes(exp)

        with pytest.raises(ValueError):
            project.add_experiment("code", workflow_document=D1)

        assert exp.workflow_kind is None
        assert exp.workflow_document is None
        assert exp.metadata.revision == 1
        assert _meta_bytes(exp) == meta

    def test_add_document_on_code_binding_raises(self, project) -> None:
        exp = project.add_experiment("bound")
        exp.bind_workflow("code", entrypoint="train.py:build")
        meta = _meta_bytes(exp)

        with pytest.raises(ValueError):
            project.add_experiment("bound", workflow_document=D1)

        assert exp.workflow_kind == "code"
        assert _meta_bytes(exp) == meta

    def test_add_without_document_returns_existing(self, project) -> None:
        first = project.add_experiment("doc", workflow_document=D1)

        second = project.add_experiment("doc")

        assert second.id == first.id
        assert second.metadata.revision == 1
        assert second.workflow_document == D1
        assert second.metadata.definition_hash == first.metadata.definition_hash

    def test_revision_is_on_disk_before_history(
        self, project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project.add_experiment("e", workflow_document=D1)
        on_disk: list[tuple[int, str, str]] = []
        original = GitHistory.record

        def spy(self: GitHistory, event: str, **kwargs: object) -> str | None:
            if event == "ExperimentRevised":
                paths = kwargs.get("paths") or ()
                assert isinstance(paths, tuple)
                assert paths
                raw = json.loads(
                    (Path(str(paths[0])) / "experiment.json").read_text(encoding="utf-8")
                )
                on_disk.append((raw["revision"], raw["description"], raw["workflow_kind"]))
            return original(self, event, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(GitHistory, "record", spy)

        project.set_experiment("e", description="new", workflow_document=D2)

        assert on_disk == [(2, "new", "document")]

    def test_project_does_not_stamp_revision_itself(self) -> None:
        path = Path(__file__).resolve().parents[2] / "src" / "molab" / "workspace" / "project.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "revision_id":
                raise AssertionError(f"project.py:{node.lineno} names revision_id")
            if isinstance(node, ast.Attribute) and node.attr == "revision_id":
                raise AssertionError(f"project.py:{node.lineno} names revision_id")
            left = node.left if isinstance(node, ast.BinOp) else None
            revises = isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
            revises = revises and isinstance(node.right, ast.Constant) and node.right.value == 1
            named = isinstance(left, ast.Name) and left.id == "revision"
            attributed = isinstance(left, ast.Attribute) and left.attr == "revision"
            if revises and (named or attributed):
                raise AssertionError(f"project.py:{node.lineno} increments revision")


class TestProject:
    def test_removed_kwargs_are_type_errors(self, project) -> None:
        project.add_experiment("e")
        with pytest.raises(TypeError):
            project.add_experiment("e2", workflow_source="x")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            project.add_experiment("e3", git_commit="x")  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            project.set_experiment("e", workflow_type="x")  # type: ignore[call-arg]

    def test_empty_set_experiment_does_not_save(self, project) -> None:
        exp = project.add_experiment(
            "doc",
            workflow_document={
                "name": "demo",
                "task_configs": [{"task_id": "prep", "task_type": "demo.prep"}],
                "links": [],
            },
        )
        revision_id = exp.metadata.revision_id
        before = (Path(exp.experiment_dir) / "experiment.json").read_bytes()
        project.set_experiment("doc")
        again = project.get_experiment("doc")
        assert again.metadata.revision == 1
        assert again.metadata.revision_id == revision_id
        assert (Path(again.experiment_dir) / "experiment.json").read_bytes() == before

    def test_assets_is_scope_repository(self, project) -> None:
        assert project.assets.scope == project.scope


class TestProjectImportAsset:
    def test_import_returns_a_domain_asset(self, project, tmp_path: Path) -> None:
        from molab.workspace.domain import Asset

        source = tmp_path / "d.txt"
        source.write_bytes(b"d")
        asset = project.import_asset("d", source)
        assert type(asset) is Asset
        assert project.assets.get(asset.id).title == "d"
