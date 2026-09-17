"""``ArtifactLineageStore`` Protocol — pipeline-artifact lineage, nothing more.

Scope (deliberately narrow): this store records **which artifact was derived
from which prior artifact** — the ``derived_from`` edge graph between harness
:class:`PlanArtifactRef` ids, stored as ``parent_ids`` on the child ref.
Stage / run stamps live on the :class:`~molab.harness.store.event_log.EventLog`.

It is NOT a general provenance system. Run-level provenance — parameters,
merged config + ``config_hash``, profile, workflow identity, execution
history, environment — is owned by :mod:`molab.workspace`
(``RunMetadata`` / per-scope ``AssetManifest`` / ``Asset.producer``).
Code-version and environment capture belong there, never here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from molab.harness.schemas import PlanArtifactRef

__all__ = ["ArtifactLineageStore"]


@runtime_checkable
class ArtifactLineageStore(Protocol):
    """Structural type for any artifact-lineage-edge backend."""

    def add_edge(
        self,
        parent_id: str,
        child_id: str,
        relation: str = "derived_from",
    ) -> None: ...

    def trace_backward(self, artifact_id: str) -> list[PlanArtifactRef]: ...

    def trace_forward(self, artifact_id: str) -> list[PlanArtifactRef]: ...

    def lineage_graph(self, artifact_id: str) -> dict[str, object]: ...
