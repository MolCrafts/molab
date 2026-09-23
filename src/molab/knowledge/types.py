"""Generic concept-type registry — the core of ``molab.knowledge``.

An open, forward-compatible registry mapping a Concept's ``type`` string to its
Python class, so a storage layer (``molab.workspace``) can reconstruct typed
Concepts from disk. Upstream layers register their own types via
``@concept_type`` / ``register_concept_type`` without ``knowledge`` importing
them; an unknown type resolves to a caller-supplied default.

The registry is **generic** — it stores plain classes and preserves the
caller's class type via a ``TypeVar`` — so it works for any storage layer's
Folder/Concept classes (knowledge owns no Folder of its own in the end state).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

#: type string → every class registered for it, in registration order.
#: One string legitimately maps to two classes when two storage families
#: model the same concept (``workspace.concepts.Note`` is a ``Folder``,
#: ``knowledge.concepts.Note`` is a ``Concept``); each asks for its own
#: through :func:`resolve_concept_type`'s ``base`` filter.
_REGISTRY: dict[str, list[type]] = {}


def register_concept_type(type_str: str, cls: type) -> None:
    """Register *cls* as a class for Concept ``type`` *type_str*.

    Re-registering the *same* class is a no-op. A *different* class is recorded
    alongside the first rather than rejected: ``molab.workspace`` and
    ``molab.knowledge`` are disjoint storage families that model the same
    concepts (a note is a ``Folder`` in one and a ``Concept`` in the other), and
    each retrieves its own through :func:`resolve_concept_type`'s ``base``
    filter. Registration order decides only what a ``base``-less resolve gets.
    """
    classes = _REGISTRY.setdefault(type_str, [])
    if cls not in classes:
        classes.append(cls)


def concept_type[C: type](type_str: str) -> Callable[[C], C]:
    """Class decorator registering the decorated Concept class as *type_str*."""

    def register(cls: C) -> C:
        register_concept_type(type_str, cls)
        return cls

    return register


def resolve_concept_type[D: type](type_str: str, default: D, *, base: type | None = None) -> D:
    """Return the class registered for *type_str*, or *default* if unknown.

    The return type matches *default* (a type parameter), so a caller passing its
    own ``Folder`` base gets its own ``Folder`` subtype back.

    ``base`` selects the caller's storage family: only a registered subclass of
    it is returned, so a ``workspace`` walk never receives a ``knowledge``
    ``Concept`` class and vice versa. A directory belonging to the other family
    resolves to *default* and is rebuilt read-only from its bare marker, which
    keeps each walk total over a heterogeneous tree rather than raising. It is
    an explicit opt-in rather than inferred from *default*, because a caller may
    legitimately register classes that are not subclasses of it.

    Args:
        type_str: The Concept ``type`` string read from ``meta.json``.
        default: The class to fall back to when *type_str* is unknown.
        base: When given, only a registered subclass of *base* is returned.
    """
    classes = _REGISTRY.get(type_str)
    if not classes:
        return default
    if base is None:
        return cast("D", classes[0])
    for cls in classes:
        if issubclass(cls, base):
            return cast("D", cls)
    return default


def non_concept_subdirs(type_str: str | None) -> frozenset[str]:
    """Subdirectory names a Concept of type *type_str* declares can hold no Concept.

    A class may declare a ``NON_CONCEPT_SUBDIRS`` attribute naming the children
    it *produces* rather than *contains* — for a workspace ``Run``, its
    ``executions/`` / ``artifacts/`` / ``logs/`` job output. A walk reads each
    directory's marker anyway, so it knows the **parent's** type and can skip
    those subtrees without enumerating them.

    This is why pruning is **position-aware**: the same bare name means
    different things in different places, so a global name denylist would hide
    a real Concept in a directory that happens to be called ``logs`` somewhere
    else in the tree. Declaring the set on the *parent* type scopes the skip to
    exactly where the layout guarantees nothing is mounted.

    The set is read from the registry first, so a host that registers its own
    classes through ``@concept_type`` is answered without importing it. A host
    that registers nothing — ``molab.workspace``, whose entity directories are
    identified by their class-named JSON — has its declaration read **directly
    off the class** (:attr:`molab.workspace.run.Run.NON_CONCEPT_SUBDIRS`),
    through the function-body import the layer firewall allows. An unknown
    type, or one declaring nothing, prunes nothing.

    Args:
        type_str: The Concept ``type`` of the directory being descended into,
            or ``None`` when it carries no marker.
    """
    if type_str is None:
        return frozenset()
    names: set[str] = set()
    for cls in _REGISTRY.get(type_str, ()):
        declared = getattr(cls, "NON_CONCEPT_SUBDIRS", None)
        if declared:
            names.update(declared)
    if not names:
        # A workspace run declares its own output subtrees and registers no
        # concept type; read them off the owning class. Function-body import:
        # ``molab.workspace`` eagerly loads this package the other way.
        from molab.workspace.folder import WORKSPACE_RUN_KIND
        from molab.workspace.run import Run

        if type_str == WORKSPACE_RUN_KIND:
            names.update(Run.NON_CONCEPT_SUBDIRS)
    return frozenset(names)


__all__ = [
    "concept_type",
    "non_concept_subdirs",
    "register_concept_type",
    "resolve_concept_type",
]
