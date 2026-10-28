"""Base class for workspace hierarchy nodes.

Provides the record payload / metadata loading shared by Workspace, Project,
Experiment, and Run (their record is the frontmatter of ``index.md``), and
child reconstruction.

The atomic write helpers ``atomic_write_json`` / ``atomic_write_text``
are re-exported from the cross-layer primitive :mod:`molab.atomicio`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

from molab.atomicio import atomic_write_json, atomic_write_text

T = TypeVar("T")


def _record_payload(metadata: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    """The canonical zone of an ``index.md`` record for *metadata*.

    Exactly the fields the model writes, ``type`` first, stamped with the
    current ``schema_version``. ``datetime`` values are already ISO strings
    (``model_dump(mode="json")``), so nothing typed reaches the YAML dumper.
    """
    from .schema_version import MOLAB_SCHEMA_VERSION

    payload = dict(
        metadata.model_dump(mode="json") if isinstance(metadata, BaseModel) else metadata
    )
    payload.pop("schema_version", None)
    head = {"type": payload.pop("type")} if "type" in payload else {}
    return {**head, **payload, "schema_version": MOLAB_SCHEMA_VERSION}


def _load_metadata[T](metadata_cls: type[T], canonical: Mapping[str, Any]) -> T:
    """Validate a record's canonical zone into a Pydantic metadata model.

    The ``schema_version`` stamp is dropped, not checked (see
    :class:`~molab.workspace.schema_version.IncompatibleSchemaError`).
    """
    data = {key: value for key, value in canonical.items() if key != "schema_version"}
    return metadata_cls(**data)


def _reconstruct[T](
    cls: type[T],
    attrs: dict[str, object],
) -> T:
    """Reconstruct a hierarchy object without calling ``__init__``.

    The attribute values are heterogeneous — pydantic metadata models,
    parent containers (``Workspace`` / ``Project`` / ``Experiment``),
    paths — so the parameter type is the structural top-type ``object``.
    Each call site already knows the concrete shape it is reconstituting.

    Args:
        cls: Target class.
        attrs: Mapping of attribute names to values to set on the instance.

    Returns:
        Reconstructed instance with attributes set.
    """
    obj = cls.__new__(cls)
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


__all__ = ["atomic_write_json", "atomic_write_text"]
