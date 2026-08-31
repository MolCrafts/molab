"""Persistence backends for ``molexp.harness``.

Four stores, each a Protocol + concrete impl pair (mirroring
:mod:`molexp.workflow.cache_store`):

- :class:`ArtifactStore` Protocol / :class:`FileArtifactStore` — content +
  refs + per-kind index on the filesystem, atomic writes via
  :func:`molexp.workspace.atomic_write_json` / ``atomic_write_text``, hashing
  via :func:`molexp.workspace.utils.compute_content_hash`.
- :class:`EventLog` Protocol / :class:`JsonlEventLog` — append-only audit
  timeline as ``events.jsonl``, per-``run_id`` ``seq`` assigned under a file lock.
- :class:`ArtifactLineageStore` Protocol / :class:`FileLineageStore` —
  ``derived_from`` edges stored as ``PlanArtifactRef.parent_ids`` (no
  ``edges.json``). Scoped strictly to pipeline-artifact lineage; run-level
  provenance (params, config, env, workflow identity) is owned by
  :mod:`molexp.workspace`.
- :class:`ApprovalStore` Protocol / :class:`FileApprovalStore` — persisted
  approval decisions (store-first gates, pending-approval inbox, grant
  replay across ledger re-entry) in ``approvals.json``.
"""

from __future__ import annotations

from molexp.harness.store.approval_store import ApprovalStore
from molexp.harness.store.artifact_store import ArtifactStore
from molexp.harness.store.event_log import EventLog
from molexp.harness.store.file_approval_store import FileApprovalStore
from molexp.harness.store.file_artifact_store import FileArtifactStore
from molexp.harness.store.file_lineage_store import FileLineageStore
from molexp.harness.store.jsonl_event_log import JsonlEventLog
from molexp.harness.store.lineage_store import ArtifactLineageStore

__all__ = [
    "ApprovalStore",
    "ArtifactLineageStore",
    "ArtifactStore",
    "EventLog",
    "FileApprovalStore",
    "FileArtifactStore",
    "FileLineageStore",
    "JsonlEventLog",
]
