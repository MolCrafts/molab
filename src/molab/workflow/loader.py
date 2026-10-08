"""Load a workflow from a ``"<path>:<qualname>"`` locator.

The process-global :data:`_LOAD_LOCK` serializes every user ``build_workflow()``
call, including concurrent requests on the server thread pool. The alias
window and ``sys.modules`` rewrite cannot run concurrently, so that cost is
accepted. Do not do slow work inside ``build_workflow()``.

The alias window only covers top-level absolute imports inside a package
(``from workflow.step import NAME``). An absolute import that runs later,
such as inside a task body, is not supported.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import threading
from functools import reduce
from pathlib import Path
from types import ModuleType

from molab.workflow.compiled import CompiledWorkflow
from molab.workflow.compiler import Workflow, WorkflowCompiler

_LOAD_LOCK = threading.Lock()
_loading = threading.local()


def load_workflow_from_entrypoint(entrypoint: str) -> CompiledWorkflow:
    """Import the workflow named by *entrypoint*.

    *entrypoint* is ``"<path>:<qualname>"``. The path is used as given. A
    missing path raises :class:`ImportError` (``Did the source move``). A
    directory is a package root and must contain ``__init__.py``.

    The resolved object may be a :class:`CompiledWorkflow`, a :class:`Workflow`
    (compiled here), or a zero-argument callable returning one of those two.
    The file is imported under a non-``__main__`` name, so an
    ``if __name__ == "__main__"`` block does not run.

    A load that calls this function again on the same thread raises
    :class:`RuntimeError` (``nested workflow load is not supported``) instead
    of taking the process-global lock a second time.

    Args:
        entrypoint: ``"<path>:<qualname>"``.

    Returns:
        The compiled workflow.

    Raises:
        ValueError: *entrypoint* has no colon.
        ImportError: The path is missing, or a directory has no ``__init__.py``.
        AttributeError: *qualname* is not an attribute of the loaded module.
        TypeError: The object is not a workflow and is not a callable that
            returns one.
        RuntimeError: This thread is already inside a load.
    """
    if getattr(_loading, "active", False):
        raise RuntimeError("nested workflow load is not supported")
    with _LOAD_LOCK:
        _loading.active = True
        previous_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            return _load_locked(entrypoint)
        finally:
            sys.dont_write_bytecode = previous_bytecode
            _loading.active = False


def _load_locked(entrypoint: str) -> CompiledWorkflow:
    if ":" not in entrypoint:
        raise ValueError(
            f"Invalid workflow entrypoint {entrypoint!r}; expected '<file_path>:<qualname>'."
        )
    file_str, qualname = entrypoint.rsplit(":", 1)
    path = Path(file_str)
    if not path.exists():
        raise ImportError(
            f"Workflow file not found: {path}. Did the source move between submission and execution?"
        )
    key = "_molab_wf_" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
    if path.is_dir():
        module = _load_package(path, key)
    else:
        module = _load_file(path, key)
    try:
        resolved = reduce(getattr, qualname.split("."), module)
    except AttributeError as exc:
        raise AttributeError(f"Cannot resolve {qualname!r} in {path}: {exc}") from exc
    return _materialize(resolved, entrypoint)


def _load_file(path: Path, key: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load workflow file: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _load_package(path: Path, key: str) -> ModuleType:
    init = path / "__init__.py"
    if not init.is_file():
        raise ImportError(f"Workflow package {path} has no __init__.py")
    spec = importlib.util.spec_from_file_location(key, init, submodule_search_locations=[str(path)])
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load workflow package: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    basename = path.name
    prefix = basename + "."
    before = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == basename or name.startswith(prefix)
    }
    sys.modules[basename] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        for name in list(sys.modules):
            if (name == basename or name.startswith(prefix)) and name not in before:
                del sys.modules[name]
        sys.modules.update(before)
    return module


def _materialize(resolved: object, entrypoint: str) -> CompiledWorkflow:
    if isinstance(resolved, CompiledWorkflow):
        return resolved
    if isinstance(resolved, Workflow):
        return WorkflowCompiler().compile(resolved)
    if callable(resolved):
        produced = resolved()  # ty: ignore[call-top-callable]
        if isinstance(produced, CompiledWorkflow):
            return produced
        if isinstance(produced, Workflow):
            return WorkflowCompiler().compile(produced)
    raise TypeError(
        f"Entrypoint {entrypoint!r} resolved to {type(resolved).__name__}, "
        "expected a CompiledWorkflow, a Workflow, or a zero-arg callable returning one."
    )
