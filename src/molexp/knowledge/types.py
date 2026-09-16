"""Generic concept-type registry — the core of ``molexp.knowledge``.

An open, forward-compatible registry mapping a Concept's ``type`` string to its
Python class, so a storage layer (``molexp.workspace``) can reconstruct typed
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

_REGISTRY: dict[str, type] = {}


def register_concept_type(type_str: str, cls: type) -> None:
    """Register *cls* as the class for Concept ``type`` *type_str*.

    Re-registering the *same* class is a no-op; registering a *different* class
    for an already-claimed type raises, to surface collisions.

    Raises:
        ValueError: if *type_str* is already bound to a different class.
    """
    existing = _REGISTRY.get(type_str)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"concept type {type_str!r} already registered to {existing.__name__!r}; "
            f"cannot re-register to {cls.__name__!r}"
        )
    _REGISTRY[type_str] = cls


def concept_type[C: type](type_str: str) -> Callable[[C], C]:
    """Class decorator registering the decorated Concept class as *type_str*."""

    def register(cls: C) -> C:
        register_concept_type(type_str, cls)
        return cls

    return register


def resolve_concept_type[D: type](
    type_str: str,
    default: D,
    *,
    base: type | None = None,
) -> D:
    """Return the class registered for *type_str*, or *default* if unknown.

    The return type matches *default* (a type parameter), so a caller passing its
    own ``Folder`` base gets its own ``Folder`` subtype back.

    A registered class that is **not** a subclass of *base* is treated as
    unknown, so *default* is returned. One open registry is therefore shared by
    disjoint storage families — a ``molexp.workspace`` ``Folder`` tree and a
    ``molexp.knowledge`` ``Concept`` bundle — without either ever receiving the
    other's class. Both families reconstruct an out-of-family directory
    read-only from its bare ``meta.yaml`` marker, so each walk stays *total*
    over a heterogeneous tree rather than raising.

    ``base`` is an explicit opt-in rather than inferred from *default*:
    third-party callers may legitimately register classes that are not subclasses
    of the default they pass, and inferring would silently change that contract.

    Args:
        type_str: The Concept ``type`` string read from ``meta.yaml``.
        default: The class to fall back to when *type_str* is unknown.
        base: When given, only a registered subclass of *base* is returned.
    """
    cls = _REGISTRY.get(type_str)
    if cls is None:
        return default
    if base is not None and not issubclass(cls, base):
        return default
    return cast("D", cls)


def non_concept_subdirs(type_str: str | None) -> frozenset[str]:
    """Subdirectory names a Concept of type *type_str* declares can hold no Concept.

    A registered class may declare a ``NON_CONCEPT_SUBDIRS`` attribute naming the
    children it *produces* rather than *contains* — for a workspace ``Run``, its
    ``executions/`` / ``artifacts/`` / ``logs/`` job output. A walk reads each
    directory's marker anyway, so it knows the **parent's** type and can skip
    those subtrees without enumerating them.

    This is why pruning is **position-aware**: the same bare name means
    different things in different places, so a global name denylist would hide
    a real Concept in a directory that happens to be called ``logs`` somewhere
    else in the tree. Declaring the set on the *parent* type scopes the skip to
    exactly where the layout guarantees nothing is mounted.

    The set flows through the registry at runtime, so ``knowledge`` learns a
    host layer's layout without importing it. An unknown or unregistered type,
    or one declaring nothing, prunes nothing.

    Args:
        type_str: The Concept ``type`` of the directory being descended into,
            or ``None`` when it carries no marker.
    """
    if type_str is None:
        return frozenset()
    cls = _REGISTRY.get(type_str)
    if cls is None:
        return frozenset()
    declared = getattr(cls, "NON_CONCEPT_SUBDIRS", None)
    if not declared:
        return frozenset()
    return frozenset(declared)


__all__ = [
    "concept_type",
    "non_concept_subdirs",
    "register_concept_type",
    "resolve_concept_type",
]
