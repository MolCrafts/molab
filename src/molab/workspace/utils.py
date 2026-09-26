"""Workspace utility functions.

The layer-agnostic id / slug / content-hash primitives (``slugify``,
``generate_id``, ``generate_asset_id``, ``compute_content_hash``) moved to
the cross-layer primitive :mod:`molab.ids` (okf-01-01) — a cross-layer
primitive shared by workspace and knowledge. They
remain importable from ``molab.workspace.utils`` (same function objects)
for back-compat. The run-domain id derivation below (``derive_run_id``)
stays here — it is workspace-specific, not a layer-agnostic primitive.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING

from molab.ids import (
    compute_content_hash,
    generate_asset_id,
    generate_id,
    hash_bytes,
    hash_copy,
    slugify,
)

if TYPE_CHECKING:
    from .._typing import JSONValue

__all__ = [
    "compute_content_hash",
    "derive_run_id",
    "generate_asset_id",
    "generate_id",
    "hash_bytes",
    "hash_copy",
    "slugify",
]

#: The mandatory Run-directory prefix (layout naming law: ``runs/run-<id>/``).
#: Part of the on-disk contract, not cosmetic — the ONE definition every
#: strip/build site cites instead of restating ``"run-"`` per call site.


def derive_run_id(params: Mapping[str, JSONValue], *, length: int = 16) -> str:
    """Derive the legacy 16-hex run id from a parameter dict — legacy reader only.

    New runs never get this id: every run created today is a UUIDv7
    (:meth:`Experiment.add_run` / :meth:`Experiment.ensure_run`), and
    "find the run for this definition" is a ``definition_hash`` lookup
    (:meth:`Experiment.ensure_run`). This function survives only so runs
    written under the old scheme can still be looked up by their exact id
    (``cli._common.deterministic_run_id``); do not use it to allocate.

    The id is a sha256 over the canonicalized parameters — keys sorted, each
    rendered ``k=repr(v)`` — so it is a pure function of the params and
    independent of dict insertion order. This is the single canonicalization
    shared by the workspace layer and ``cli._common.deterministic_run_id``.

    Args:
        params: The run's parameter mapping (JSON-serializable values).
        length: Number of leading hex characters to keep (default 16).

    Returns:
        A ``length``-character lowercase hex string.
    """
    raw = "|".join(f"{k}={v!r}" for k, v in sorted(params.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:length]
