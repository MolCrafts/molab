# NOTES.md — Evolving Decisions

Captured by `/molexp-note`. Stable entries are promoted to CLAUDE.md then deleted here.

<!-- Format: ## <slug> | <date> | <author>
Decision body.
**Status:** evolving | stable | promoted -->

## cross-layer-data-reference | 2026-05-06 | impl

Cross-layer references go through URI / asset_id / string id, never `from <upstream_layer> import SomeType` to define a shape in `<downstream_layer>`. If two layers need the same type, move the type to the downstream common layer (or a shared root); duplicating it in the upper layer is the bug pattern. **Counter-example**: `molexp.workflow.proposal` once imported `molexp.agent.types.ArtifactRef` — corrected to `code_artifact: Path | None`.

Pure data types → `pydantic.BaseModel(frozen=True)`. Runtime containers (live callables / asyncio objects / non-pydantic instances) → plain Python class with explicit `__init__`. **`arbitrary_types_allowed=True` is forbidden in `src/molexp/agent/`** — anything that needs it is a runtime container by definition. See full table in `CLAUDE.md ## Data type ownership`.

**Status:** stable

## three-layer-rectification | 2026-05-09 | impl

The molexp dependency DAG was inverted by the rectification spec:
**workspace ← workflow ← agent**, where the arrows point from "uses" to "is used by".

Why the inversion: pre-2026-05-09 the codebase had workspace importing
workflow types (`Experiment.workflow: WorkflowSpec`,
`workspace/sessions.py:SessionLibrary` knowing about agent session
schemas, `workspace/subsystem.py` hardcoding `"agent.sessions"`),
which made workspace neither a clean storage primitive nor a clean
upstream concern. The fix:

- workspace becomes a pure storage primitive (filesystem hierarchy,
  atomic JSON, content-addressed assets, generic per-kind `SubsystemStore`).
  Knows nothing about workflows, sessions, agents, or LLMs.
- workflow becomes a graph engine that uses workspace for caching
  (`WorkspaceCacheStore` backed by `SubsystemStore("workflow.cache")`)
  and for atomic state writes (`workspace.atomic_write_json` for
  `workflow.json` snapshots). The `~/.molexp/cache/` user-home
  shortcut is gone.

Mechanical enforcement: three import-guard tests
(`tests/test_<layer>/test_import_guard.py`). The audit + design lives
in `.claude/specs/molexp-rectification.md`; the binding "done"
contract is `molexp-rectification.acceptance.md` (criteria
P0-01..P0-07, P1-01..P1-05, P2-01..P2-04, P3-01..P3-05, P4-01..P4-02,
P5-01..P5-02, P6-01..P6-03).

Side effects worth remembering:
- `Experiment.workflow` field, `Experiment.set_workflow`, the
  workspace-side `_promote_to_workflow` / `_resolve_*_entrypoint`
  helpers, and `workspace/sessions.py:SessionLibrary` are **gone**.
  Pairing an Experiment with a workflow is the caller's concern;
  workflow exposes `promote_callable` / `WorkflowSnapshotRef`
  publicly.
- `agent/_legacy_types.py` is gone; `ToolSchema` / `ModelToolCall`
  live permanently in `agent/tools/spec.py`; `to_jsonable` lives
  privately in `agent/sessions/_serde.py`.
- Old on-disk `experiment.json` files with a `workflow` field still
  load (`ExperimentMetadata` carries `extra="ignore"`).

**Status:** stable

## workspace-read-model-memory | 2026-09-16 | impl

The server now keeps state resident that used to be re-read per request: the
`Workspace` instance caches `Run` entities via `Folder._children_cache`
(`Experiment.list_runs` reuses them), and `services.workspace_read_model`
holds the `RunsSnapshot` / `AssetScanSnapshot` / `KnowledgeSnapshot` plus the
BM25F corpus. Cost is roughly **50–100 MB at 10 000 runs**, in exchange for
warm list requests doing zero filesystem I/O.

No eviction policy exists. Above ~100 k runs, add one (LRU over
`_children_cache`, or drop snapshot rows outside the active project) rather
than reverting the cache — the alternative is ~5 file reads per run per
request, which is what made the UI unusable on NFS.

**Status:** evolving

## perf-syscall-budgets | 2026-09-16 | impl

`tests/test_perf/` locks filesystem-call counts against a synthetic workspace
built directly on disk (not via `add_run`, whose index rewrite is O(N²)).
`tests/test_perf/BASELINE.md` holds the before/after tables measured against
pristine `HEAD e0ebdec7`.

```bash
python -m pytest tests/test_perf -m perf          # small: 5x4x10 = 200 runs (default)
MOLEXP_PERF_SCALE=full python -m pytest tests/test_perf -m perf   # 50x20x10 = 10 000 runs
MOLEXP_PERF=1 python -m pytest tests/test_perf    # adds the informational wall-clock locks
```

Keep CI on `small`: the full fixture takes ~134 s to build on NFS (I/O bound;
the 25 k single-row sqlite event appends dominate). Budgets are asserted with
`tests/support/counting_fs.py::CountingFileSystem`, which proxies `__class__`
to the wrapped type so `isinstance(fs, LocalFileSystem)` still holds — without
that, `Workspace` treats a counted workspace as remote and the event spine
short-circuits.

**Status:** stable

## local-toolchain-gotchas | 2026-09-16 | impl

Four environment facts that cost time if rediscovered:

- **`ty` needs an explicit interpreter.** `[tool.ty.environment] python = "./.venv"`
  in `pyproject.toml` points at a directory that does not exist in this
  checkout, so bare `ty check` fails before analysing anything. Use
  `ty check --python $(python -c 'import sys;print(sys.prefix)')`.
- **`ui/` is an npm workspace member.** `node_modules` and the binaries
  (`rstest`, `tsc`, `biome`, `rsbuild`) hoist to the **repo root**, not
  `ui/node_modules`. `npm install` / `npm test` still run from `ui/`.
- **The sibling `@molcrafts/molplot` must be built** or `npm run typecheck`
  fails with 15 `TS2307` "cannot find module" errors:
  `cd ../molplot/core && npm install && npm run build`. `package.json`
  resolves it by `file:` path, and the repo ships no `dist/`.
- **Two molq test modules fail on a pre-existing config issue** unrelated to
  any of this: `tests/test_plugins/test_submit_molq/test_dashboard.py` and
  `tests/test_server/test_molq_routes.py` (molq rejects the `config.toml`).
  Deselect them when measuring a suite run.

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

The CLI shares this now (`target_to_filesystem(cached=True)` is the default,
mirror under `~/.molexp/remote_cache/`), so a CLI verb against a remote target
no longer pays raw per-call SSH. `revalidate_before` makes each invocation
revalidate what it touches once, then pin.
