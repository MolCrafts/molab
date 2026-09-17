"""A Run's ``definition_hash`` has exactly one implementation.

Before ``compute_run_definition_hash`` existed there were three call sites
with two different digest shapes — ``Run.__init__`` omitted
``input_asset_ids`` — and the HTTP API folded a synthesized
``workflow_snapshot`` in while ``Experiment.define`` did not. The same
experiment and the same parameter cell therefore got a *different* identity
depending on which door created it, which is the bug these tests lock out.
"""

from __future__ import annotations

import ast
from pathlib import Path

from molab.workspace import Workspace
from molab.workspace.run import Run, compute_run_definition_hash

WORKSPACE_SRC = Path(__file__).resolve().parents[2] / "src" / "molab" / "workspace"


class TestOneImplementation:
    def test_no_other_module_hand_rolls_a_run_definition_hash(self) -> None:
        """Only ``compute_run_definition_hash`` may hash a run's definition.

        A hand-rolled ``compute_definition_hash({... "experiment_revision_id"
        ...})`` anywhere else is a second implementation by construction.
        """
        offenders: list[str] = []
        for path in sorted(WORKSPACE_SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            # The helper's own body holds the one sanctioned call.
            sanctioned = {
                id(node)
                for fn in ast.walk(tree)
                if isinstance(fn, ast.FunctionDef) and fn.name == "compute_run_definition_hash"
                for node in ast.walk(fn)
            }
            for node in ast.walk(tree):
                if id(node) in sanctioned:
                    continue
                if not (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "compute_definition_hash"
                ):
                    continue
                keys = {
                    k.value
                    for arg in node.args
                    if isinstance(arg, ast.Dict)
                    for k in arg.keys
                    if isinstance(k, ast.Constant)
                }
                if "experiment_revision_id" in keys:
                    offenders.append(f"{path.relative_to(WORKSPACE_SRC)}:{node.lineno}")
        assert not offenders, (
            "run definition_hash must go through compute_run_definition_hash; "
            f"hand-rolled at {offenders}"
        )

    def test_every_creation_door_agrees(self, tmp_path: Path) -> None:
        """``add_run``, direct construction, and the helper produce one hash."""
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        experiment = ws.add_project("p").add_experiment("e")
        params = {"seed": 1}

        via_add_run = experiment.add_run(params=params)
        via_helper = compute_run_definition_hash(
            experiment_revision_id=experiment.metadata.revision_id,
            parameters=params,
        )
        via_constructor = Run(
            parent=experiment,
            parameters=params,
            experiment_revision_id=experiment.metadata.revision_id,
        )

        assert via_add_run.metadata.definition_hash == via_helper
        assert via_constructor.metadata.definition_hash == via_helper


class TestIdentityIsNeverThePath:
    def test_the_workflow_locator_does_not_enter_the_hash(self, tmp_path: Path) -> None:
        """Moving the defining script must not change what a run *is*.

        The workflow is the experiment's property (reached through
        ``experiment_revision_id``); a locator is a file path, and CLAUDE.md's
        identity law forbids folding a path into identity.
        """
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        experiment = ws.add_project("p").add_experiment("e")
        baseline = experiment.add_run(params={"seed": 1}).metadata.definition_hash

        experiment.metadata = experiment.metadata.model_copy(
            update={"workflow_entrypoint": "/somewhere/else/wf.py:compiled"}
        )
        experiment.save()
        moved = compute_run_definition_hash(
            experiment_revision_id=experiment.metadata.revision_id,
            parameters={"seed": 1},
        )
        assert moved == baseline

    def test_a_legacy_run_snapshot_does_not_change_identity(self, tmp_path: Path) -> None:
        """A run carrying the retired per-run copy hashes like one without it."""
        ws = Workspace(root=tmp_path / "lab")
        ws.materialize()
        experiment = ws.add_project("p").add_experiment("e")
        plain = experiment.add_run(params={"seed": 2})
        with_snapshot = Run(
            parent=experiment,
            parameters={"seed": 2},
            experiment_revision_id=experiment.metadata.revision_id,
            workflow_snapshot={"entrypoint": "/old/wf.py:compiled"},
        )
        assert with_snapshot.metadata.definition_hash == plain.metadata.definition_hash
