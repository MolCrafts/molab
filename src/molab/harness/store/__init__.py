"""Persistence backends for ``molab.harness``.

Four stores, each a Protocol + concrete impl pair (mirroring
:mod:`molab.workflow.cache_store`):

- :class:`ArtifactStore` Protocol / :class:`FileArtifactStore` — content +
  refs + per-kind index on the filesystem, atomic writes via
  :func:`molab.workspace.atomic_write_json` / ``atomic_write_text``, hashing
  via :func:`molab.workspace.utils.compute_content_hash`.
- :class:`EventLog` Protocol / :class:`JsonlEventLog` — append-only audit
  timeline as ``events.jsonl``, per-``run_id`` ``seq`` assigned under a file lock.
- :class:`ArtifactLineageStore` Protocol / :class:`FileLineageStore` —
  ``derived_from`` edges stored as ``PlanArtifactRef.parent_ids`` (no
  ``edges.json``). Scoped strictly to pipeline-artifact lineage; run-level
  provenance (params, config, env, workflow identity) is owned by
  :mod:`molab.workspace`.
- :class:`ApprovalStore` Protocol / :class:`FileApprovalStore` — persisted
  approval decisions (store-first gates, pending-approval inbox, grant
  replay across ledger re-entry) in ``approvals.json``.
"""

from __future__ import annotations

from molab.harness.store.approval_store import ApprovalStore
from molab.harness.store.artifact_store import ArtifactStore
from molab.harness.store.event_log import EventLog
from molab.harness.store.file_approval_store import FileApprovalStore
from molab.harness.store.file_artifact_store import FileArtifactStore
from molab.harness.store.file_lineage_store import FileLineageStore
from molab.harness.store.jsonl_event_log import JsonlEventLog
from molab.harness.store.lineage_store import ArtifactLineageStore
from molab.harness.store.paths import HARNESS_DIRNAME, harness_artifact_root
from molab.harness.store.run_approval_store import RunApprovalStore

__all__ = [
    "HARNESS_DIRNAME",
    "ApprovalStore",
    "ArtifactLineageStore",
    "ArtifactStore",
    "EventLog",
    "FileApprovalStore",
    "FileArtifactStore",
    "FileLineageStore",
    "JsonlEventLog",
    "RunApprovalStore",
    "harness_artifact_root",
]
