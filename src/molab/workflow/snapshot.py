"""Task snapshot for immutable static identity.

A TaskSnapshot captures the static identity of a Task — its code and configuration —
as an immutable record. It does NOT know about inputs; that's the cache's job.

Code hashing uses AST normalization to be insensitive to whitespace, comments,
and formatting changes. Only semantic code changes produce a different hash.

The code hash covers more than the body's own source: every module-level
function, class or constant the body reaches through its globals (recursively,
first-party only — see :func:`_dependency_entries`) is folded in, so editing a
helper the body calls or a constant it reads changes the task's identity. A
body that reaches nothing first-party keeps its plain AST hash.

Usage:
    snapshot = TaskSnapshot.from_task_body(task_id, body)
    print(snapshot.key)  # deterministic identity string
"""

from __future__ import annotations

import ast
import enum
import functools
import hashlib
import inspect
import json
import sys
import sysconfig
import textwrap
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import CodeType
from typing import cast

from mollog import get_logger
from pydantic import BaseModel, ConfigDict, Field

from .._typing import JSONValue

logger = get_logger(__name__)


def task_config_of(body: object) -> dict[str, JSONValue]:
    """The build-time config of a task body = its ``__init__`` arguments.

    A :class:`~molab.workflow.Task` / :class:`~molab.workflow.Actor` instance
    captures its constructor arguments into ``_task_config`` (see
    :class:`~molab.workflow.task._CapturesInitConfig`); that dict is the task's
    config identity and the form IR round-trips via ``cls(**config)``.

    Falls back gracefully: a third-party instance with no captured config exposes
    its public ``__dict__``; a bare function (no construction state) has none.
    """
    captured = getattr(body, "_task_config", None)
    if captured is not None:
        return dict(captured)
    if hasattr(body, "__dict__") and not inspect.isfunction(body) and not inspect.ismethod(body):
        return {k: v for k, v in vars(body).items() if not k.startswith("_")}
    return {}


def _stable_config_default(obj: object) -> JSONValue:
    """Deterministic JSON fallback for non-JSON ``__init__`` args.

    ``json.dumps(default=str)`` is unusable for the config hash: a default
    ``repr`` embeds the instance's memory address (``<… at 0x…>``), so a task
    constructed with a live object would hash differently every process.

    Values that change what the body computes are encoded: callables by their
    AST-normalized source, paths as text, mappings, sequences and dataclass
    fields recursively. Only an object with no stable fields collapses to its
    type name.
    """
    import dataclasses
    from collections.abc import Sequence

    if _function_parts(obj) is not None:
        source_hash = _code_identity_hash(obj)
        mod = getattr(obj, "__module__", "?")
        qualname = getattr(obj, "__qualname__", getattr(obj, "__name__", "?"))
        return f"callable:{mod}.{qualname}:{source_hash or 'nosrc'}"
    if isinstance(obj, Path):
        return {"__path__": str(obj)}
    inner = getattr(obj, "inner", None)
    digest = getattr(inner, "workflow_hash", None) or getattr(obj, "workflow_hash", None)
    if isinstance(digest, str):
        return {"__workflow__": digest}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {"__dataclass__": type(obj).__qualname__, "fields": dataclasses.asdict(obj)}
    if isinstance(obj, Mapping):
        return {str(key): value for key, value in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str | bytes | bytearray):
        return list(obj)
    fields: dict[str, object] = {}
    if hasattr(obj, "__dict__"):
        fields = {
            key: value
            for key, value in vars(obj).items()
            if not key.startswith("_") and not callable(value)
        }
    if fields:
        qualname = f"{type(obj).__module__}.{type(obj).__qualname__}"
        return cast("JSONValue", {"__object__": qualname, "fields": fields})
    return f"<{type(obj).__module__}.{type(obj).__qualname__}>"


@functools.lru_cache(maxsize=4096)
def _normalized_source_hash(code: CodeType) -> str | None:
    """Memoized AST-normalized source hash for a code object.

    The hash depends only on the body's source, and a code object is a stable
    identity for it, so the (expensive) ``inspect.getsource`` + AST parse +
    normalize + sha256 runs once per code object rather than once per
    ``TaskSnapshot.from_task_body`` call (``codec.ir_to_spec`` re-snapshots
    every task on every IR deserialization). Returns ``None`` when source is
    unavailable so the caller can fall back to a bytecode/identity hash.
    """
    try:
        source = inspect.getsource(code)
        normalized = _normalize_ast(source)
    except (OSError, TypeError, SyntaxError):
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _normalize_ast(source: str) -> str:
    """Normalize Python source via AST dump, stripping comments and whitespace.

    Two functions that differ only in comments, blank lines, or formatting
    produce the same normalized output. Decorators ARE part of semantic
    identity: a decorator can change behaviour (``@retry(n)``, ``@lru_cache``,
    a units/validation wrapper), so it must change the code hash — otherwise
    the content-addressed cache silently returns a stale/wrong result. The AST
    dump already ignores a decorator's own whitespace/comment formatting, so
    keeping decorators costs no spurious invalidation.
    """
    tree = ast.parse(textwrap.dedent(source))
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


# --- Module-level dependencies of a body ------------------------------------
#
# ``_normalized_source_hash`` covers one function's own source. A body that
# calls a module-level helper or reads a module-level constant changes
# behaviour when *they* change while its own source does not, so the
# content-addressed cache (and ``--resume``) would reuse an output computed by
# code that no longer exists. ``_dependency_entries`` resolves the names a code
# object (nested lambdas / comprehensions included) loads through the
# function's globals and folds the first-party ones into the identity:
#
# * a function / method -> its normalized source hash, then its own globals
#   are walked the same way (recursively; a visited set stops cycles);
# * a class -> the AST of the ``class`` statement binding it, then its
#   methods and first-party bases are walked;
# * any other global -> the AST of the module-level statements that bind it
#   (``HELPER_VALUE = 1``, ``X = load("a.csv")``, an ``if`` block assigning
#   it), then the names those statements load are walked. The *definition*,
#   not the runtime value: a module dict a task mutates keeps the identity it
#   was written with, and a ``Path`` / client / model needs no stable repr.
#   Only a global no statement binds (``from m import *``, ``globals()[...]``)
#   is identified by value: its canonical JSON when JSON-safe (paths as
#   text, sets sorted, enum members by name), otherwise its type's name —
#   never a ``repr`` that could embed an address.
#
# First-party means defined under the directory of the file defining the
# starting body and outside the stdlib / site-packages, which the environment
# pins. Modules are skipped: a first-party module imported as a whole is
# already covered file-by-file by ``_local_deps_digest``.

#: Module metadata a body may read but that must not enter its identity
#: (``__name__`` is ``"__main__"`` under ``molab run`` and the module name
#: when the same file is imported; ``__file__`` moves with the checkout).
_META_GLOBALS: frozenset[str] = frozenset(
    {
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
    }
)


@functools.lru_cache(maxsize=1)
def _environment_roots() -> tuple[Path, ...]:
    """Directories whose code the environment pins: the stdlib and site-packages."""
    import site

    paths = sysconfig.get_paths()
    roots = {paths[key] for key in ("stdlib", "platstdlib", "purelib", "platlib") if paths.get(key)}
    getsitepackages = getattr(site, "getsitepackages", None)
    if callable(getsitepackages):
        roots.update(getsitepackages())
    roots.add(site.getusersitepackages())
    return tuple(sorted(Path(root).absolute() for root in roots))


@functools.lru_cache(maxsize=4096)
def _is_first_party(filename: str, root: Path) -> bool:
    """Whether *filename* lies under *root* and outside the environment's own trees.

    Paths are made absolute without resolving symlinks (no syscalls on this
    hot path); every ``co_filename`` of one import tree is spelled the same
    way. Memoized: a walk asks the same few files over and over.
    """
    if not filename or filename.startswith("<"):
        return False
    path = Path(filename).absolute()
    if not path.is_relative_to(root):
        return False
    return not any(path.is_relative_to(env) for env in _environment_roots())


def _function_parts(obj: object) -> tuple[CodeType, Mapping[str, object] | None] | None:
    """The code object and globals behind a function, method or wrapped callable.

    A bound method answers through its ``__func__``; a ``functools``-style
    wrapper without a code object of its own (``lru_cache``, ``staticmethod``)
    through ``__wrapped__``. ``None`` for anything that is not Python code.
    """
    unwrapped = obj
    if callable(obj) and hasattr(obj, "__wrapped__"):
        try:
            unwrapped = inspect.unwrap(obj)
        except ValueError:  # a ``__wrapped__`` cycle
            unwrapped = obj
    for candidate in (obj, getattr(obj, "__func__", None), unwrapped):
        code = getattr(candidate, "__code__", None)
        if isinstance(code, CodeType):
            namespace = getattr(candidate, "__globals__", None)
            return code, (namespace if isinstance(namespace, Mapping) else None)
    return None


@functools.lru_cache(maxsize=4096)
def _referenced_names(code: CodeType) -> frozenset[str]:
    """Global and attribute names *code* and its nested code objects load.

    ``co_names`` holds both, so an attribute that happens to share a name with
    a module global over-approximates (a spurious dependency, never a missed
    one).
    """
    names = set(code.co_names)
    for const in code.co_consts:
        if isinstance(const, CodeType):
            names |= _referenced_names(const)
    return frozenset(names)


def _bytecode_hash(code: CodeType) -> str:
    """Source-less fallback identity of a code object."""
    return hashlib.sha256(code.co_code + repr(code.co_consts).encode()).hexdigest()[:32]


def _class_files(cls: type) -> tuple[str, ...]:
    """Files that may hold the ``class`` statement of *cls*, most likely first.

    The module's ``__file__`` (when the module is registered) comes first;
    the distinct ``co_filename`` of each method follows, which also serves a
    module loaded outside ``sys.modules`` and a class whose methods were
    rebound from another file (``_CapturesInitConfig`` wraps ``__init__``).
    Memoized per class (walking ``vars(pathlib.Path)`` on every snapshot is
    the single largest cost of the walk otherwise).
    """
    try:
        return _cached_class_files(cls)
    except TypeError:  # unhashable metaclass
        return _scan_class_files(cls)


@functools.lru_cache(maxsize=4096)
def _cached_class_files(cls: type) -> tuple[str, ...]:
    return _scan_class_files(cls)


def _scan_class_files(cls: type) -> tuple[str, ...]:
    files: dict[str, None] = {}
    module = sys.modules.get(getattr(cls, "__module__", None) or "")
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        files[module_file] = None
    for member in vars(cls).values():
        parts = _function_parts(member)
        if parts is not None and not parts[0].co_filename.startswith("<"):
            files.setdefault(parts[0].co_filename, None)
    return tuple(files)


#: ``name -> (digest, loads)`` for one module file: the AST-normalized digest
#: of the top-level statements binding *name* and the names those statements
#: load (for the recursive walk).
_Bindings = Mapping[str, tuple[str, frozenset[str]]]

_SCOPED_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _bound_names(stmt: ast.stmt) -> set[str]:
    """Module names a top-level *stmt* binds; nested scopes bind nothing here."""
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return {stmt.name}
    bound: set[str] = set()
    stack: list[ast.AST] = [stmt]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            bound.add(node.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            bound.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        if not isinstance(node, _SCOPED_NODES):
            stack.extend(ast.iter_child_nodes(node))
    return bound


def _loaded_names(stmt: ast.stmt) -> frozenset[str]:
    return frozenset(
        node.id
        for node in ast.walk(stmt)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    )


def _index_bindings(tree: ast.Module) -> _Bindings:
    """Index every module-level name of *tree* by the statements that bind it.

    A name bound by several statements (``X = []`` then ``X += [1]``, a
    ``class`` then a re-decoration) digests all of them in order. The dump
    ignores comments and formatting, like :func:`_normalize_ast`.
    """
    dumps: dict[str, list[str]] = {}
    loads: dict[str, set[str]] = {}
    for stmt in tree.body:
        bound = _bound_names(stmt)
        if not bound:
            continue
        dumped = ast.dump(stmt, annotate_fields=True, include_attributes=False)
        loaded = _loaded_names(stmt)
        for name in bound:
            dumps.setdefault(name, []).append(dumped)
            loads.setdefault(name, set()).update(loaded)
    return {
        name: (hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32], frozenset(loads[name]))
        for name, parts in dumps.items()
    }


@functools.lru_cache(maxsize=256)
def _module_bindings(file: str, _stamp: tuple[int, int]) -> _Bindings:
    """Memoized :func:`_index_bindings` of *file*.

    ``_stamp`` is the file's ``(mtime_ns, size)``: part of the cache key only,
    so an edit on disk is re-indexed while an unchanged file is parsed once.
    """
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8"), filename=file)
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return {}
    return _index_bindings(tree)


def _bindings_of(file: str) -> _Bindings:
    """The binding index of *file* as it is on disk now (one ``stat`` per call)."""
    try:
        stat = Path(file).stat()
    except OSError:
        return {}
    return _module_bindings(file, (stat.st_mtime_ns, stat.st_size))


def _constant_json_default(obj: object) -> object:
    """``json.dumps`` default for module constants: paths as text, sets sorted."""
    if isinstance(obj, Path):
        return {"__path__": str(obj)}
    if isinstance(obj, enum.Enum):
        return {"__enum__": f"{type(obj).__qualname__}.{obj.name}"}
    if isinstance(obj, set | frozenset):
        return sorted(
            json.dumps(item, sort_keys=True, default=_constant_json_default) for item in obj
        )
    raise TypeError(f"not a JSON-safe constant: {type(obj).__qualname__}")


def _type_name(value: object) -> str:
    if isinstance(value, type):
        return f"<class {value.__module__}.{value.__qualname__}>"
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _constant_repr(value: object) -> str:
    """Canonical JSON of a JSON-safe module constant, else its type's name.

    The fallback identity of a global the module's own source does not bind
    (``from x import *``, ``globals()[...]``): a value, so it must never embed
    an address.
    """
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=_constant_json_default
        )
    except (TypeError, ValueError, RecursionError):
        return _type_name(value)


class _DependencyWalker:
    """Collects identity entries of the first-party objects a body reaches.

    One instance per walk; ``run`` drains the pending code objects and returns
    the sorted entries (sorted so traversal order never moves the hash).
    Functions and classes are followed as objects (their source, cached per
    object); any other global is identified by the module statements that
    bind it (:func:`_bindings_of`) — the *definition*, not the runtime value,
    so a module-level dict a task mutates keeps the identity it was written
    with — and only by its value when no statement binds it.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._visited: set[int] = set()
        self._visited_names: set[tuple[str, str]] = set()
        self._entries: set[str] = set()
        self._pending: list[tuple[CodeType, Mapping[str, object]]] = []
        self._bindings: dict[str, _Bindings] = {}

    def seed(self, code: CodeType, namespace: Mapping[str, object] | None) -> None:
        """Start from *code* without adding an entry for it (its hash is the base)."""
        self._visited.add(id(code))
        if namespace is not None:
            self._pending.append((code, namespace))

    def run(self) -> list[str]:
        while self._pending:
            code, namespace = self._pending.pop()
            for name in _referenced_names(code):
                self._visit_name(name, namespace, code.co_filename)
        return sorted(self._entries)

    def _visit_name(self, name: str, namespace: Mapping[str, object], file: str) -> None:
        if name in _META_GLOBALS or name not in namespace:
            return
        value = namespace[name]
        if inspect.ismodule(value):
            return
        parts = _function_parts(value)
        if parts is not None:
            self._visit_function(*parts)
        elif isinstance(value, type):
            self.visit_class(value)
        else:
            self._visit_constant(value, name, namespace, file)

    def _visit_function(self, code: CodeType, namespace: Mapping[str, object] | None) -> None:
        if id(code) in self._visited or not _is_first_party(code.co_filename, self._root):
            return
        self._visited.add(id(code))
        qualname = getattr(code, "co_qualname", code.co_name)
        digest = _normalized_source_hash(code) or _bytecode_hash(code)
        self._entries.add(f"def {qualname}: {digest}")
        if namespace is not None:
            self._pending.append((code, namespace))

    def visit_class(self, cls: type) -> None:
        if id(cls) in self._visited:
            return
        files = [file for file in _class_files(cls) if _is_first_party(file, self._root)]
        if not files:
            return
        self._visited.add(id(cls))
        top_level = cls.__qualname__.split(".")[0]
        found = (self._binding(file, top_level) for file in files)
        digest = next((binding[0] for binding in found if binding is not None), "nosrc")
        self._entries.add(f"class {cls.__qualname__}: {digest}")
        for member in vars(cls).values():
            self._visit_member(member)
        for base in cls.__bases__:
            self.visit_class(base)

    def _visit_member(self, member: object) -> None:
        """A class attribute that is code: a method, nested class or property."""
        if isinstance(member, property):
            for accessor in (member.fget, member.fset, member.fdel):
                if accessor is not None:
                    self._visit_member(accessor)
            return
        target = getattr(member, "func", member)  # ``functools.cached_property``
        parts = _function_parts(target)
        if parts is not None:
            self._visit_function(*parts)
        elif isinstance(target, type):
            self.visit_class(target)

    def _visit_constant(
        self, value: object, name: str, namespace: Mapping[str, object], file: str
    ) -> None:
        binding = self._binding(file, name)
        if binding is None:
            self._entries.add(f"const {name}: val:{_constant_repr(value)}")
            return
        if (file, name) in self._visited_names:
            return
        self._visited_names.add((file, name))
        digest, loads = binding
        self._entries.add(f"const {name}: src:{digest}")
        for loaded in loads:
            self._visit_name(loaded, namespace, file)

    def _binding(self, file: str, name: str) -> tuple[str, frozenset[str]] | None:
        index = self._bindings.get(file)
        if index is None:
            index = self._bindings[file] = _bindings_of(file)
        return index.get(name)


def _dependency_entries(fn: object) -> list[str]:
    """Sorted identity entries of the first-party objects *fn* reaches.

    *fn* is a function, a method or a class. A bound method also reaches its
    owning class (``self.helper()`` is an edge the globals cannot show). An
    empty list when *fn* has no source file, so the identity falls back to the
    body's own hash exactly as before.
    """
    parts = _function_parts(fn)
    if parts is not None:
        file: str | None = parts[0].co_filename
    elif isinstance(fn, type):
        file = next(iter(_class_files(fn)), None)
    else:
        return []
    if not file or file.startswith("<") or not Path(file).is_file():
        return []
    walker = _DependencyWalker(Path(file).absolute().parent)
    if parts is None:
        walker.visit_class(cast("type", fn))
        return walker.run()
    walker.seed(*parts)
    owner = getattr(fn, "__self__", None)
    if owner is not None and not inspect.ismodule(owner):
        walker.visit_class(owner if isinstance(owner, type) else type(owner))
    return walker.run()


def _fold_dependencies(own_hash: str, fn: object) -> str:
    """*own_hash* combined with :func:`_dependency_entries`; unchanged when there are none."""
    entries = _dependency_entries(fn)
    if not entries:
        return own_hash
    payload = "\n".join([own_hash, *entries])
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _code_identity_hash(fn: object) -> str | None:
    """The code hash of a Python callable: own normalized source + reachable dependencies.

    The own-source part is memoized per code object
    (:func:`_normalized_source_hash`); the dependency walk is not — it must
    see the globals as they are now, and it costs only dict lookups plus the
    same memoized per-object hashes. ``None`` when the source is unavailable.
    """
    parts = _function_parts(fn)
    if parts is None:
        return None
    own = _normalized_source_hash(parts[0])
    if own is None:
        return None
    return _fold_dependencies(own, fn)


def _local_deps_digest(fn: object) -> str | None:
    """Digest of the first-party modules the file defining *fn* imports, or ``None``."""
    try:
        source_file = inspect.getsourcefile(fn)  # ty: ignore[invalid-argument-type]
    except (TypeError, OSError):
        return None
    if not source_file:
        return None
    from molab.workspace.source_snapshot import local_import_digest

    try:
        return local_import_digest(source_file)
    except OSError:
        return None


class TaskSnapshot(BaseModel):
    """Immutable static snapshot of a Task.

    Captures code_hash (AST-normalized execute() source) and config_hash
    (serialized config). Together they form a deterministic identity key
    for the task definition.
    """

    task_id: str
    task_type: str
    code_hash: str
    config_hash: str
    code_source: str = ""
    created_at: datetime
    config_data: dict[str, JSONValue] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_task_body(
        cls,
        task_id: str,
        body: object,
    ) -> TaskSnapshot:
        """Create a snapshot from any registered task body.

        Accepts the heterogeneous bodies a workflow registers — a ``Task`` /
        ``Actor`` instance, a bare ``async def`` function, or any ``Runnable`` /
        ``Streamable``. It resolves the hashable callable (``execute`` → ``run``
        → the body itself), so the compiler computes one snapshot per task and
        reuses its ``code_hash`` inside ``workflow_hash``.

        The ``config_hash`` is derived from the task *instance's* construction
        identity — its ``__init__`` arguments (see :func:`task_config_of`), NOT a
        separately-declared registration config. A task instance *is* its config.
        """
        fn = getattr(body, "execute", None) or getattr(body, "run", None) or body
        if hasattr(body, "execute") or hasattr(body, "run"):
            task_type = f"{type(body).__module__}.{type(body).__qualname__}"
            identity = task_type
        else:
            module = getattr(body, "__module__", "?")
            qualname = getattr(body, "__qualname__", getattr(body, "__name__", "?"))
            task_type = f"{module}.{qualname}"
            identity = task_type
        cfg = task_config_of(body)
        config_raw = json.dumps(cfg, sort_keys=True, default=_stable_config_default)
        # ``config_data`` must be JSON-clean (a task may be constructed with live
        # objects — a sub-workflow, a callable). Round-trip through the same
        # serialization the hash uses so the stored field matches the hash and is
        # always a valid ``JSONValue`` (non-serializable args land as their str).
        config_clean: dict[str, JSONValue] = json.loads(config_raw)
        try:
            source = inspect.getsource(fn) if callable(fn) else ""
        except (OSError, TypeError):
            source = ""
        code_hash = cls._hash_callable(fn, identity, task_id)
        # The AST hash covers the body and the module-level helpers / constants
        # it reaches by name (:func:`_dependency_entries`). A body that calls
        # into a sibling helper module (``import analysis`` inside the task)
        # must also change identity when that module changes, or the node cache
        # serves results computed by code that no longer exists.
        deps = _local_deps_digest(fn)
        if deps is not None:
            code_hash = hashlib.sha256(f"{code_hash}:{deps}".encode()).hexdigest()[:32]
        return cls(
            task_id=task_id,
            task_type=task_type,
            code_hash=code_hash,
            config_hash=hashlib.sha256(config_raw.encode()).hexdigest()[:32],
            code_source=source,
            created_at=datetime.now(UTC),
            config_data=config_clean,
        )

    @staticmethod
    def _hash_callable(fn: object, identity: str, task_id: str) -> str:
        """AST-normalized code hash of *fn* (+ reachable deps) with bytecode/identity fallbacks."""
        if callable(fn):
            parts = _function_parts(fn)
            if parts is not None:
                # Memoized AST-normalized source hash, keyed by code object,
                # folded with the module-level dependencies the body reaches.
                source_hash = _code_identity_hash(fn)
                if source_hash is not None:
                    return source_hash
                return _bytecode_hash(parts[0])
            # Callable without a code object (e.g. a class / callable instance):
            # hash its source directly (rare, not on the re-snapshot hot path).
            try:
                source = inspect.getsource(fn)
                normalized = _normalize_ast(source)
                own_hash = hashlib.sha256(normalized.encode()).hexdigest()[:32]
                return _fold_dependencies(own_hash, fn)
            except (OSError, TypeError, SyntaxError):
                pass
        logger.warning(
            f"Cannot compute reliable code hash for task {task_id} ({identity}). "
            "Falling back to identity."
        )
        return hashlib.sha256(identity.encode()).hexdigest()[:32]

    @property
    def key(self) -> str:
        """Deterministic identity key = f(code_hash, config_hash)."""
        return f"{self.code_hash}:{self.config_hash}"
