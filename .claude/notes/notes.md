# NOTES.md — Evolving Decisions

Project decisions. Stable entries are promoted to CLAUDE.md then deleted here.

<!-- Format: ## <slug> | <date> | <author>
Decision body.
**Status:** evolving | stable | promoted -->

## cross-layer-data-reference | 2026-05-06 | impl

Cross-layer references go through URI / asset_id / string id, never `from <upstream_layer> import SomeType` to define a shape in `<downstream_layer>`. If two layers need the same type, move the type to the downstream common layer (or a shared root); duplicating it in the upper layer is the bug pattern. **Counter-example**: `molab.workflow.proposal` once imported `molab.agent.types.ArtifactRef` — corrected to `code_artifact: Path | None`.

Pure data types → `pydantic.BaseModel(frozen=True)`. Runtime containers (live callables / asyncio objects / non-pydantic instances) → plain Python class with explicit `__init__`. **`arbitrary_types_allowed=True` is forbidden in `src/molab/agent/`** — anything that needs it is a runtime container by definition. See full table in `CLAUDE.md ## Data type ownership`.

**Status:** stable

## three-layer-rectification | 2026-05-09 | impl

The molab dependency DAG was inverted by the rectification spec:
**workspace ← workflow ← agent**, where the arrows point from "uses" to "is used by".

Why the inversion: pre-2026-05-09 the codebase had workspace importing
workflow types (`Experiment.workflow: WorkflowSpec`,
`workspace/sessions.py:SessionLibrary` knowing about agent session
schemas, `workspace/subsystem.py` hardcoding `"agent.sessions"`),
which made workspace neither a clean storage primitive nor a clean
upstream concern. The fix:

- workspace becomes a pure storage primitive (filesystem hierarchy,
  atomic JSON, per-host `asset.json` records, generic per-kind `SubsystemStore`).
  Knows nothing about workflows, sessions, agents, or LLMs.
- workflow becomes a graph engine that uses workspace for caching
  (`WorkspaceCacheStore` backed by `SubsystemStore("workflow.cache")`)
  and for atomic state writes (`workspace.atomic_write_json` for
  `workflow.json` snapshots). The `~/.molab/cache/` user-home
  shortcut is gone.

Mechanical enforcement: three import-guard tests
(`tests/test_<layer>/test_import_guard.py`). The audit + design lives
in `.claude/specs/molab-rectification.md`; the binding "done"
contract is `molab-rectification.acceptance.md` (criteria
P0-01..P0-07, P1-01..P1-05, P2-01..P2-04, P3-01..P3-05, P4-01..P4-02,
P5-01..P5-02, P6-01..P6-03).

Side effects worth remembering:
- `Experiment.workflow` field, `Experiment.set_workflow`, the
  workspace-side `_promote_to_workflow` / `_resolve_*_entrypoint`
  helpers, and `workspace/sessions.py:SessionLibrary` are **gone**.
  Pairing an Experiment with a workflow is the caller's concern;
  workflow exposes `promote_callable` publicly. Identity of a run's
  workflow is `workflow_hash` on the Execution and the journal header.
- `agent/_legacy_types.py` is gone; `ToolSchema` / `ModelToolCall`
  live permanently in `agent/tools/spec.py`; `to_jsonable` lives
  privately in `agent/sessions/_serde.py`.
- Old on-disk `experiment.json` files with a `workflow` field still
  load (`ExperimentMetadata` carries `extra="ignore"`).

**Status:** stable

## local-toolchain-gotchas | 2026-11-12 | impl

Environment facts that cost time if rediscovered:

- **`ty` resolves against `./.venv`** (`[tool.ty.environment] python`), so a
  checkout without that venv fails before analysing anything. Run
  `ty check --python .venv src/` from the repo root.
- **The npm workspace is `apps/*`.** `node_modules` and the binaries
  (`rstest`, `tsc`, `biome`, `rsbuild`) hoist to the **repo root**;
  `npm run typecheck` / `npm test` run from `apps/web`.

**Status:** evolving

## remote-workspace-cache-cost | 2026-09-16 | impl

What a remote (SSH) workspace actually costs after the cache landed, measured on
a scripted 5x4x10 tree (200 runs):

- Cold `prefetch_workspace_indices` with the bulk accelerators: **2 SSH
  round-trips total**, not 2 per run. It needs GNU `find` on the remote host
  (`-printf`); a BSD/macOS host falls back to the per-level walk (~504 RTT),
  which is logged at debug, not warned — falling back is normal there.
- Warm walk of all 200 runs: **0**. A warm `stat` of a child a listing already
  covered: **0**. `read_bytes` of a mirrored file: **0**; of an evicted one
  (metadata retained): 1.
- Sidecar for a 1000-record walk: **2 writes / 0.2 MB**, down from
  1000 writes / 103 MB — the per-record rewrite was O(N^2) in bytes.

The CLI shares this cache (mirror under `~/.molab/remote_cache/`), so a CLI
verb against a remote target no longer pays raw per-call SSH.
