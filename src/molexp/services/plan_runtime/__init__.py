"""Plan application types shared by the CLI and the server.

The plan *bundle* is :class:`molexp.harness.Plan` (``open`` / ``execute`` /
``save``). This package holds the application types around it: background
:class:`PlanTask`, gateway preflight errors, and record outcomes.
"""

from __future__ import annotations

from molexp.services.plan_runtime.gateway import PlanPreflightError
from molexp.services.plan_runtime.materialize import (
    PlanFailure,
    PlanRecordError,
    PlanRecordOutcome,
)
from molexp.services.plan_runtime.registry import PlanTaskRegistry
from molexp.services.plan_runtime.resume_scope import ResumeDriver, RouterBackedResumeDriver
from molexp.services.plan_runtime.task import PlanTask, PlanTaskStatus

__all__ = [
    "PlanFailure",
    "PlanPreflightError",
    "PlanRecordError",
    "PlanRecordOutcome",
    "PlanTask",
    "PlanTaskRegistry",
    "PlanTaskStatus",
    "ResumeDriver",
    "RouterBackedResumeDriver",
]
