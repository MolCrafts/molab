"""Shared molab public-surface contract for plan codegen agents.

The structured source of truth is
:file:`contracts/molab_codegen.v1.yaml`. This module re-exports a YAML
render for any caller that still expects a string block, and keeps the
historical name ``MOLAB_CODEGEN_CONTRACT``.
"""

from __future__ import annotations

from molab.harness.prompts.codegen_prompt import render_contract_yaml

__all__ = ["MOLAB_CODEGEN_CONTRACT"]

#: YAML render of ``molab_codegen.v1.yaml`` (not free-form prose).
MOLAB_CODEGEN_CONTRACT = render_contract_yaml()
