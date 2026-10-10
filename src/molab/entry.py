"""Entry point registry for CLI discovery.

A user script declares its runnable study with the fluent OOP chain and that
registers it for ``molab run`` — no flat helper, no source scanning, no magic
attribute discovery. :func:`entry` is the low-level primitive (register a
pre-built workspace); :meth:`~molab.workspace.Experiment.run` is the fluent
surface that calls it through the :class:`~molab.workspace.experiment.WorkflowExecutor`
seam this module wires up. The CLI calls :func:`load_workspaces` to import the
script and retrieve all registered workspaces.

Example (user script)::

    import molab as me
    from molab.workflow import Workflow, WorkflowCompiler


    def build_workflow():
        return WorkflowCompiler().compile(Workflow(name="train").add(...))


    (
        me.Workspace(name="lab")
        .project("demo")
        .experiment("series")
        .run(build_workflow(), params={"lr": [1e-3, 1e-4]})
    )

``params`` is the per-run sweep (inputs); ``execute`` seeds one content-addressed
run per cell, binds the workflow, and registers the workspace. ``molab run``
then drives execution.

Example (CLI internal)::

    from molab.entry import load_workspaces

    workspaces = load_workspaces(Path("train.py"))
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from molab.fs import LocalFileSystem
from molab.workspace.experiment import set_workflow_executor

if TYPE_CHECKING:
    from molab.workspace.experiment import Experiment
    from molab.workspace.workspace import Workspace

_registry: list[Workspace] = []


def entry(workspace: Workspace) -> None:
    """Register a workspace as a CLI entry point.

    When a script is imported by ``molab run``, this call populates
    the global registry.  When the script is run directly
    (``python script.py``), nobody reads the registry — it is
    effectively a no-op.

    Idempotent per workspace root: ``Experiment.define`` already registers
    its workspace, so a script that also calls ``me.entry(ws)``, defines
    several experiments of one workspace, or builds two ``Workspace``
    objects on the same directory still lists it once — otherwise
    ``molab run`` would dispatch every run once per registration. The first
    registration wins. A workspace on a non-local disk is compared by
    identity, because its root names a path on another machine.

    Args:
        workspace: A :class:`~molab.Workspace` to register.
    """
    key = _registry_key(workspace)
    if any(_registry_key(registered) == key for registered in _registry):
        return
    _registry.append(workspace)


def _registry_key(workspace: Workspace) -> Path | int:
    """What makes two registrations the same workspace.

    Args:
        workspace: A registered or about-to-be-registered workspace.

    Returns:
        The resolved root for a local workspace, else the object's ``id``.
    """
    if isinstance(workspace.fs, LocalFileSystem):
        return Path(workspace.root).resolve()
    return id(workspace)


def _execute_experiment(experiment: Experiment, workflow: object) -> None:
    """Back :meth:`Experiment.run` — the cross-layer workflow association.

    Registered into the workspace layer (which must not import workflow) via
    :func:`~molab.workspace.experiment.set_workflow_executor`. Binding goes
    through :meth:`~molab.workspace.Experiment.bind_workflow` for the code
    kind (the binding registry still holds this script's compiled object, so
    ``molab run`` resolves it), and the owning workspace is registered as a
    CLI entry. Runs are already seeded by ``Experiment.run`` before this is
    called.
    """
    from molab.workflow import (
        CompiledWorkflow,
        Workflow,
        WorkflowCompiler,
        default_binding_registry,
    )

    authored = workflow
    if isinstance(workflow, Workflow):
        workflow = WorkflowCompiler().compile(workflow)
    if not isinstance(workflow, CompiledWorkflow):
        raise TypeError(
            f"Experiment.define expects a Workflow or CompiledWorkflow, "
            f"got {type(workflow).__name__}."
        )
    default_binding_registry.bind(experiment, workflow)
    # Code-kind binding goes through Experiment.bind_workflow. A spec with no
    # module-level name (a promoted callable, a test fixture) stores
    # entrypoint None and stays script-driven. Script edits refresh the
    # binding on the next (idempotent) re-import.
    from molab.workflow.promote import resolve_spec_entrypoint

    try:
        entrypoint = resolve_spec_entrypoint(workflow, authored=authored)
    except (ValueError, OSError, TypeError):
        entrypoint = None
    experiment.bind_workflow(
        "code",
        entrypoint=entrypoint,
        document=workflow.to_graph_ir().model_dump(mode="json"),
    )
    entry(experiment.project.workspace)


# Wire the seam at import time so ``exp.run(workflow, ...)`` works as soon as
# ``molab`` is imported, without the workspace layer importing the workflow layer.
set_workflow_executor(_execute_experiment)


def infer_workspace_root(script: Path) -> Path:
    """Infer the workspace root from an entry-script path.

    Pure path arithmetic — the root is the directory containing *script*.
    Used by ``molab run`` so a script may write ``Workspace(name=...)`` with
    no explicit root and have it resolve to the script's own directory.

    Args:
        script: Path to the entry script (the argument to ``molab run``).

    Returns:
        The resolved parent directory of *script*.

    Raises:
        ValueError: If *script* is falsy or has no resolvable parent. The
            caller (not this helper) owns any cwd fallback — this fails fast
            rather than silently defaulting.
    """
    # A usable script path has a filename component; an empty path (``Path("")``
    # → ``.``) or a bare directory marker does not.
    if not script or not Path(script).name:
        raise ValueError(f"infer_workspace_root: {script!r} is not a usable script path")
    resolved = Path(script).resolve()
    parent = resolved.parent
    if parent == resolved:  # a filesystem root has no distinct parent
        raise ValueError(f"infer_workspace_root: {script!r} has no resolvable parent directory")
    return parent


def load_workspaces(script: Path) -> list[Workspace]:
    """Import a user script and return all registered workspaces.

    Args:
        script: Path to the Python script containing ``me.entry()`` calls.

    Returns:
        List of registered :class:`~molab.Workspace` instances.

    Raises:
        RuntimeError: If the script cannot be loaded.
    """
    _registry.clear()
    _import_script(script)
    return list(_registry)


def clear_registry() -> None:
    """Clear the registry (for tests)."""
    _registry.clear()


def _import_script(script: Path) -> None:
    """Dynamically import a user script *as ``__main__``*.

    Setting the spec name to ``"__main__"`` makes the user's
    ``if __name__ == "__main__":`` guard fire — that block is exactly
    where the script wires up its workspace, projects, experiments and
    bound workflows, which ``molab run`` needs to discover via
    :func:`entry`.

    Recovering a bound workflow from a stored locator is
    :func:`molab.workflow.loader.load_workflow_from_entrypoint`, which
    imports the same file under a private module name so this guard does
    not re-run.
    """
    spec = importlib.util.spec_from_file_location("__main__", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load script: {script}")
    module = importlib.util.module_from_spec(spec)
    # Register the user-script module as ``sys.modules["__main__"]`` so
    # ``inspect``-based helpers (e.g. ``_resolve_spec_entrypoint`` in
    # :mod:`molab.workspace.experiment`) find the user's globals via
    # ``sys.modules["__main__"]`` instead of the CLI's own ``__main__``.
    # Matches the semantics of a normal ``python script.py`` invocation.
    sys.modules["__main__"] = module
    # Match `python script.py`: make the script's directory importable so sibling
    # modules resolve (e.g. a phase script importing its shared ``experiment`` /
    # ``quant_teff`` helpers). spec-based loading does not add this automatically.
    script_dir = str(script.resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
