"""Sole-writer guard: association fields are written only under workspace."""

from __future__ import annotations

import ast
from pathlib import Path

ASSOCIATION_FIELDS = {
    "workflow_kind",
    "workflow_entrypoint",
    "workflow_source",
    "workflow_type",
    "git_commit",
    "plan_run_id",
}

_EXPERIMENT_CALLS = {"add_experiment", "set_experiment", "Experiment"}
_EXPERIMENT_CALL_FIELDS = {"workflow_source", "workflow_type", "git_commit"}

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src" / "molab"
_WORKSPACE = _SRC / "workspace"


def association_writer_hits(tree: ast.AST, filename: str) -> list[str]:
    """Return one hit per association-field write in a module AST."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_writes_association(node):
            hits.append(f"{filename}:{node.lineno}:call")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and (
            _assignment_writes_association(node)
        ):
            hits.append(f"{filename}:{node.lineno}:assign")
    return hits


def _call_writes_association(node: ast.Call) -> bool:
    if _model_copy_updates_association(node):
        return True
    return _experiment_call_sets_association(node)


def _model_copy_updates_association(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "model_copy":
        return False
    for keyword in node.keywords:
        if keyword.arg != "update" or not isinstance(keyword.value, ast.Dict):
            continue
        for key in keyword.value.keys:
            if isinstance(key, ast.Constant) and key.value in ASSOCIATION_FIELDS:
                return True
    return False


def _experiment_call_sets_association(node: ast.Call) -> bool:
    name = _call_name(node.func)
    if name not in _EXPERIMENT_CALLS:
        return False
    return any(keyword.arg in _EXPERIMENT_CALL_FIELDS for keyword in node.keywords)


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _assignment_writes_association(
    node: ast.Assign | ast.AnnAssign | ast.AugAssign,
) -> bool:
    targets: tuple[ast.expr, ...]
    if isinstance(node, ast.Assign):
        targets = tuple(node.targets)
    else:
        targets = (node.target,)
    return any(
        isinstance(target, ast.Attribute) and target.attr in ASSOCIATION_FIELDS
        for target in targets
    )


def production_association_hits() -> list[str]:
    """Scan src/molab except workspace for association-field writes."""
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if path.is_relative_to(_WORKSPACE):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(_REPO_ROOT).as_posix()
        hits.extend(association_writer_hits(tree, relative))
    return hits


class TestExperimentBindingWriters:
    def test_production_outside_workspace_has_no_association_writers(self) -> None:
        assert production_association_hits() == []

    def test_model_copy_workflow_kind_is_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('m.model_copy(update={"workflow_kind": 1})'),
            "snippet.py",
        )
        assert len(hits) == 1

    def test_add_experiment_workflow_source_is_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('p.add_experiment("e", workflow_source="x")'),
            "snippet.py",
        )
        assert len(hits) == 1

    def test_plan_run_id_assignment_is_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('e.metadata.plan_run_id = "r"'),
            "snippet.py",
        )
        assert len(hits) == 1

    def test_model_copy_name_is_not_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('m.model_copy(update={"name": 1})'),
            "snippet.py",
        )
        assert hits == []

    def test_model_copy_workflow_digest_is_not_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('m.model_copy(update={"workflow_digest": 1})'),
            "snippet.py",
        )
        assert hits == []

    def test_bind_workflow_is_not_flagged(self) -> None:
        hits = association_writer_hits(
            ast.parse('exp.bind_workflow("code")'),
            "snippet.py",
        )
        assert hits == []
