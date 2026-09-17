"""Executor backends for ``molab.harness`` (Phase 9 §6).

- :class:`Executor` Protocol — runtime-checkable contract.
- :class:`DryRunExecutor` — no real subprocess; for pipeline smoke tests.
- :class:`LocalExecutor` — real ``subprocess.run`` with timeout + stdout/stderr capture.

``SlurmExecutor`` lands in a later phase (HPC submission lifecycle is its
own beast).
"""

from __future__ import annotations

from molab.harness.executors.dry_run import DryRunExecutor
from molab.harness.executors.executor import Executor
from molab.harness.executors.local import LocalExecutor

__all__ = ["DryRunExecutor", "Executor", "LocalExecutor"]
