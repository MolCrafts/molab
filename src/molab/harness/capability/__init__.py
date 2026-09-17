"""Capability dispatch helpers for the harness.

Owns :func:`resolve_callable`, the single fail-fast bridge from a
:class:`~molab.harness.schemas.capability.ToolCapability`'s ``callable_path``
string to a real Python callable. Kept in its own subpackage so both the
:class:`~molab.harness.stages.invoke_capability.InvokeCapability` stage and the
materialized runner resolve symbols through one code path.
"""

from __future__ import annotations

from molab.harness.capability.resolve import resolve_callable

__all__ = ["resolve_callable"]
