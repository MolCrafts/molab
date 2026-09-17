"""molab.harness — plugin host (atom = AgentCall) plus default orchestration plugins.

The host lives at :mod:`molab.harness.host` (not re-exported here). Workspace,
workflow, agent, and science adapters mount as plugins; :class:`Plan`
and :class:`Chat` are bundles. See ``.claude/notes/harness-plugins.md``.

Provenance split (one owner per concern): the harness records
**pipeline-artifact lineage only** — which stage of which run produced which
artifact, derived from which prior artifact (``ArtifactLineageStore``)
— plus the audit event timeline. **Run-level provenance** (params, merged
config + ``config_hash``, profile, workflow identity, execution history,
environment) is owned by :mod:`molab.workspace` (``RunMetadata`` /
per-scope ``AssetManifest``); code-version and environment capture belong
there, never here.

Public surface (deliberately small): the Stage execution machinery, the two
shipped bundles (:class:`Chat` + :class:`Plan`), the stores
their artifacts and audit trail live in, the executor seam, the approval
gate, and the agent gateway. Everything else — stage classes, schemas,
validators, policies, curation actions — is imported via its full submodule
path (``molab.harness.stages`` / ``.schemas`` / ``.validators`` / …).

Dependency direction: the harness sits **above** molab and may import any
of it (``workspace`` / ``workflow`` / ``services`` / ``server`` / ``cli`` /
``plugins``). molab must never import back — enforced by
``tests/test_import_direction.py``, which also keeps ``pydantic_ai`` /
``pydantic_graph`` out of a plain ``import molab``.

The host itself stays narrower than the package: ``harness.host`` composes
plugins it is *handed* (``compose_*(extra=…)``) and does not reach for
``molab.plugins`` — that is the face's job (``harness.cli`` /
``harness.server``).
"""

from __future__ import annotations

from molab.harness.audit import replay_metadata
from molab.harness.core import HarnessRunContext, Stage, StageRunner
from molab.harness.errors import ApprovalPendingError, StageExecutionError
from molab.harness.executors import DryRunExecutor, Executor, LocalExecutor
from molab.harness.gateways import AgentGateway, RouterBackedAgentGateway
from molab.harness.modes import Chat, Plan, chat_loop_config
from molab.harness.registry import CapabilityRegistry
from molab.harness.schemas import ModeResult
from molab.harness.stages import ApprovalGate
from molab.harness.store import (
    ArtifactStore,
    FileApprovalStore,
    FileArtifactStore,
    FileLineageStore,
    JsonlEventLog,
)

__all__ = [
    "AgentGateway",
    "ApprovalGate",
    "ApprovalPendingError",
    "ArtifactStore",
    "CapabilityRegistry",
    "Chat",
    "DryRunExecutor",
    "Executor",
    "FileApprovalStore",
    "FileArtifactStore",
    "FileLineageStore",
    "HarnessRunContext",
    "JsonlEventLog",
    "LocalExecutor",
    "ModeResult",
    "Plan",
    "RouterBackedAgentGateway",
    "Stage",
    "StageExecutionError",
    "StageRunner",
    "chat_loop_config",
    "replay_metadata",
]
