"""Capability registry contract for ``molab.harness``.

Two public symbols:

- :class:`CapabilityRegistry` — ``runtime_checkable`` Protocol every backend
  implements. The validator
  (:func:`molab.harness.validators.bound_workflow.validate_bound_workflow`)
  programs against this Protocol; per-package adapters (molpy, molpack, …)
  ship their own concrete impls.
- :class:`InMemoryCapabilityRegistry` — concrete impl used by tests + by
  callers who want to assemble a registry by hand from a list of
  :class:`ToolCapability` instances.

Per-package adapters (MolPy / MolPack / Molab / MolVis / MolQ from
``harness-goal.md`` §16 Phase 4) intentionally live in their *own*
packages, not in the harness — the harness defines the contract, each
package supplies its capability catalog.
"""

from __future__ import annotations

from molab.harness.registry.bindable import (
    PLAN_SCIENCE_PACKAGE_ROOTS,
    is_bindable_capability,
    is_bindable_capability_id,
    is_bindable_kind,
)
from molab.harness.registry.capability_registry import CapabilityRegistry
from molab.harness.registry.in_memory import InMemoryCapabilityRegistry

__all__ = [
    "PLAN_SCIENCE_PACKAGE_ROOTS",
    "CapabilityRegistry",
    "InMemoryCapabilityRegistry",
    "is_bindable_capability",
    "is_bindable_capability_id",
    "is_bindable_kind",
]
