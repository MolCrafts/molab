"""molab.services — application services shared by the CLI and the server.

One backend code path per user-facing operation ("Python operation ≡ UI
operation"): CLI commands and server routes both delegate here instead of
duplicating logic or importing each other.

Contents:

- :mod:`molab.services.operator_config` — the ``~/.molab/config.json``
  loader/saver (one source of truth for the path and the parsing).
- :mod:`molab.services.run_failure` — failure analysis for a finished run.
- :mod:`molab.services.auth` — filesystem users + sessions for
  ``molab serve`` HTTP auth (CLI ``molab auth`` and the server share it).
- :mod:`molab.services.workflow_kind` — legacy workflow-kind classification
  (one rule for ``molab migrate workflow-kind`` and the server writers' 409 gate).
- :mod:`molab.services.knowledge_context` — the document read-model and its producer.
- :mod:`molab.services.copilot` — the deterministic workspace summary.

Layer rules: services may import ``workflow`` / ``workspace`` / ``knowledge``
(and cross-layer primitives); it MUST NOT import ``molab.server`` or
``molab.cli`` — those application shells sit *above* services and import it,
never the reverse. Enforced by ``tests/test_services/test_import_guard.py``.

No eager re-exports: importing :mod:`molab.services` stays light; consumers
import the specific submodule they need.
"""

from __future__ import annotations
