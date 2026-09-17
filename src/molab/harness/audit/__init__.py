"""Audit + replay helpers for ``molab.harness`` (Phase 10).

- :func:`generate_audit_report` — assemble an :class:`AuditReport` from
  the event log + artifact store + lineage store.
- :func:`replay_metadata` — re-read events for a run.
- :func:`find_last_successful_stage` — pinpoint resume-from-failure point.
"""

from __future__ import annotations

from molab.harness.audit.generate import generate_audit_report
from molab.harness.audit.replay import find_last_successful_stage, replay_metadata

__all__ = [
    "find_last_successful_stage",
    "generate_audit_report",
    "replay_metadata",
]
