# molab Layer-Integration Spec

**Status**: target architecture (coordination layer). Companion to
`architecture.md` (the current module map). This file does **not** redefine
Workspace / Workflow / Experiment / Run / Artifact / Knowledge — those exist
(see `architecture.md`). It adds the **coordination contracts** between them.
Reconcile incrementally; each slice in §9 lands a piece. Section numbers are
stable: sections 6 and 8 (and features 7.2, 7.3, 7.5, 7.6) described the agent
operation model deleted in D86 and are gone rather than renumbered.

> **Hard rule — no parallel architecture.** Everything below is expressed in
> terms of modules that already exist. New code is a thin *seam* (a read-model
> assembler, an event log), never a second copy of an existing subsystem. Where
> a concept already lives somewhere, this spec says *reuse it*, not *rebuild it*.

---

## 0. The coordination loop

The product thesis — *a scientific work system bounded by Workspace, structured
by Workflow / Experiment / Run, grounded by Artifact and Knowledge, operated
through CLI / server / UI verbs* — reduces to one loop the layers must support:

```text
WorkspaceContext                          (§1 — assembled from authoritative state)
  → Experiment + workflow authored by the researcher   (§3)
  → Run / Artifact                        (§3, §4 — existing workspace machinery)
  → KnowledgeDelta                        (§5 — source-linked KnowledgeItems)
  → updated WorkspaceContext              (loop closes; §2 events drive the refresh)
```

Each arrow is a contract between two layers. The rest of this document specifies
those contracts and which existing module owns each side.

**Ownership stance carried throughout** (these resolve the gaps in
`architecture.md`'s audit):

- Canonical state is **workspace on disk** (entity `*.json`, `run.json (hot state) + alive`,
  `assets.json`, OKF `meta.json`/`index.md`). Frontend state is never canonical.
- Every artifact used in reasoning is **citeable by source reference**; every
  KnowledgeItem carries **source attribution**; every mutation is
  **traceable** through the event + provenance spine.

---

## 1. WorkspaceContext

### 1.1 What it is

`WorkspaceContext` is the **canonical read-model** the system hands to the
server, CLI and UI so they reason over structured state instead of scraped chat.
It is a *projection* assembled on demand from authoritative sources — it stores
nothing new and is never itself canonical.

Today two places independently re-assemble overlapping context:
`server/routes/workspace.py` (`GET /info|/runs|/files`) and the UI
`WorkspaceSnapshot` (`apps/web/src/app/state/useWorkspaceState.ts`, polled every 3 s).
**This spec unifies them behind one assembler** so both become consumers of the
same shape.

### 1.2 Shape (illustrative)

```python
class WorkspaceContext(BaseModel):
    # identity
    workspace: WorkspaceRef                      # id, name, root, targets
    # focus (ephemeral — supplied by the caller, NOT stored)
    focus: ContextFocus                          # active project/experiment/run + selection
    # structure
    projects: list[ProjectRef]
    experiments: list[ExperimentRef]             # incl. parameter_space summary
    workflows: list[WorkflowRef]                 # available compiled/IR workflows
    # execution
    recent_runs: list[RunRef]                    # ordered by finished/started
    failed_runs: list[RunRef]                    # status ∈ retryable domain
    running_runs: list[RunRef]
    # grounding
    artifacts: list[ArtifactRef]                 # recent / focus-scoped
    knowledge: list[KnowledgeRef]                # relevant items (§5)
    open_questions: list[KnowledgeRef]           # OpenQuestion items + spec ResolvedQuestion gaps
    # health
    stale_or_missing: list[HealthFlag]           # see §1.4
```

`ContextFocus` (active project/experiment/run + `selected_object_refs`) is the
**only** part that comes from the caller's ephemeral session/selection — it is
passed in, never persisted as workspace state. Everything else is derived from
disk.

### 1.3 Producers vs consumers

| Field group | Authoritative source (PROVIDER) | Module |
|---|---|---|
| workspace identity, projects, experiments | `Workspace` / `Project` / `Experiment` folder tree | `workspace/workspace.py`, `project.py`, `experiment.py` |
| workflows available | `Experiment.workflow.json` IR + compiled refs | `workspace/experiment.py:98`, `workflow/codec.py` |
| runs (recent/failed/running) | `Run` + hot-state sidecar | `workspace/run.py:225` (`read_ops`), `run_ops.py` |
| artifacts | manifest scan | `workspace/assets/scan.py` (`scan_assets`/`get_asset`) |
| knowledge / open questions | OKF concepts via Bundle | `workspace/bundle.py`, `concepts.py`, §5 |
| health flags | computed over the above | new assembler (§1.4) |

**New seam (P0):** a `workspace.context` read module (layer-legal: it imports
only `workspace` + `knowledge`, never `workflow`) that composes the above into
`WorkspaceContext`. It is a **pure read**, reusing `read_ops`, `scan_assets`, and
`Bundle`.

**Consumers (must only read it):** the server (`GET /context`, replacing the
piecemeal `workspace.py` reads), the CLI (`molexp context`), the UI
`WorkspaceSnapshot` (re-pointed at `/context`), and the Workspace Copilot (§7.1).
Any filtered/ranked view is assembled one layer up (server) on top of the
canonical context — workspace stays relevance-agnostic.

### 1.4 Health flags (stale / missing / failed)

Computed, never stored:

- **failed run** — `Run.status ∈ RETRYABLE_STATUSES` (`workspace/run.py:61`).
- **stale running** — `running` with dead owner PID or stale heartbeat (reuse the
  existing reaper rule in `run_ops.py`).
- **missing output** — an `ExpectedOutput`/`acceptance_criteria` with no matching
  `ArtifactAsset` in `scan_assets`.
- **stale knowledge** — KnowledgeItem whose `sources` point at a superseded
  artifact content-hash or a deleted run (§5.4).
- **orphan artifact** — asset with a `Producer.run_id` that no longer resolves.

These flags are exactly what the Workspace Copilot (§7.1) surfaces as "next
actions."

---

## 2. Cross-layer event model

### 2.1 The coordination spine

This spec adds one coordination spine.

| Stream | Scope | Persisted? | Existing module | Role |
|---|---|---|---|---|
| **`WorkspaceEvent`** *(new, P0)* | whole workspace | yes (`<root>/workspace.events.sqlite`) | new | **cross-object coordination spine** |

The new `WorkspaceEvent` log is the canonical "what happened across objects"
timeline — append-only, `seq`-ordered, never overwritten, at workspace scope.
The workspace log holds the coordination event + a `run_id`/`content_hash`
pointer to drill down into the run's own `executions/eNN/` records. This keeps
the deep record local to a run while giving the copilot one place to observe the
whole project.

`workspace.selection.changed` is **ephemeral** — it stays a UI/session signal
(reuse the existing `apps/web/src/app/state/workspaceSwitchEvents.ts` CustomEvent bus
pattern) and is **never** persisted or given provenance.

### 2.2 Event catalogue

P = produces provenance edge · A = agent-visible · K = may trigger knowledge
extraction.

| Event | Producer | Consumers | Payload (core) | P | A | K |
|---|---|---|---|---|---|---|
| `workspace.asset.added` | `ArtifactAccessor.save` / asset register (`workspace/assets/accessors.py`) | Context, Artifact Interpreter, UI | asset_id, scope, kind, content_hash, producer(run/exec/task) | ✓ | ✓ | ✓ |
| `workspace.selection.changed` | UI / session | agent focus view | selected_object_refs | ✗ | ✓ | ✗ |
| `workflow.created` | `Experiment.set_workflow` / compile (`workflow/compiler.py`) | Context, Planner | workflow_id, version, ir_hash | ✓ | ✓ | ✗ |
| `experiment.created` | `Project.add_experiment` | Context, Planner | experiment_id, project_id, parameter_space | ✓ | ✓ | ✗ |
| `run.created` | `Experiment.add_run` (`workspace/experiment.py:376`) | Context, Monitor | run_id, experiment_id, params, config_hash | ✓ | ✓ | ✗ |
| `run.started` | `RunLifecycle.enter` (`workspace/run_lifecycle.py:52`) | Monitor, Context | run_id, exec_id, owner, started_at | ✓ | ✓ | ✗ |
| `run.failed` | `RunLifecycle.exit` / reaper | Run Monitor → FailureAnalysis, Context | run_id, exec_id, error, last_stage | ✓ | ✓ | ✓ |
| `run.completed` | `RunLifecycle.exit` | Monitor, Artifact Interpreter, Context | run_id, exec_id, output_refs, finished_at | ✓ | ✓ | ✓ |
| `artifact.created` | `ArtifactAccessor` | Interpreter, Context, provenance | ArtifactRef (id, kind, content_hash, parent_ids) | ✓ | ✓ | ✓ |
| `artifact.updated` | re-register / new version | Interpreter, Context | new ref + supersedes_id | ✓ | ✓ | ◻ |
| `knowledge.created` | KnowledgeItem write (§5) | Planner, Copilot, Context | item_id, kind, sources, status | ✓ | ✓ | ✗ |
| `knowledge.conflict.detected` | conflict detector (§5.4) | Curator, UI, user | conflicting_ids, basis | ✓ | ✓ | flag |

### 2.3 Provenance contract

A "P ✓" event MUST write a provenance edge when it links artifacts: reuse the
workspace `Producer` field (`workspace/assets/base.py`) for run→artifact lineage.
Knowledge links reuse the typed OKF out-edge (§4.3 / §5.2). The two together
answer "trace this artifact back to the run and experiment that produced it".

---

## 3. Workflow / Experiment / Run cooperation

This is **lifecycle + data flow only** — the entities are unchanged.

```text
Experiment ──references──► Workflow (IR)         Experiment.workflow.json  (workspace/experiment.py:98)
    │                          │
    │ add_run(params|space)    │ compile()                                 (workflow/compiler.py)
    ▼                          ▼
   Run ──binds──► (workflow × params × env × time)                         (workspace/run.py, RunContext)
    │ execute
    ▼
 Execution ──produces──► ArtifactAssets  ───► (interpret) ───► KnowledgeItems   (§4, §5)
    │                                                              │
    └────────────────── run.failed ──► FailureAnalysis ◄──────────┘
                                                                   │
 Knowledge ──informs──► next experiment / workflow revision (§3.1)
```

### 3.1 Experiment ↔ Workflow

- An `Experiment` **references** a workflow, it does not embed engine code. The
  reference is the externalized IR doc `Experiment.workflow.json`
  (`workspace/experiment.py:98`) + a compiled hash. **Reconciliation needed**
  (architecture audit gap): make the *workflow-layer IR* (`workflow/codec.py`,
  `schema/workflow.json`) the single canonical workflow definition. Python task
  code is the escape hatch, not the primary model.
- Workflow availability flows into `WorkspaceContext.workflows` (§1.3).

### 3.2 Run binds Workflow to concreteness

- `Experiment.add_run(params=…)` / `add_runs(space)` create content-addressed
  Runs (`derive_run_id`). A `Run` binds: the referenced workflow, concrete
  `params`, environment (`profile`/`config_hash`), and time
  (`run.json (hot state) + alive` started/finished). This is the existing model — reuse as-is.
- Execution persists node-level outputs under `executions/<exec_id>/workflow.json`
  (resume seed) — unchanged.

### 3.3 Run → Artifact → Knowledge

- Run outputs become `ArtifactAsset`s via `ctx.register_artifact(...)`
  (`workspace/assets/accessors.py`) with `Producer(run_id, execution_id,
  task_id, inputs)` lineage — **this linkage already exists**; the gap is only
  that nothing consumes it for knowledge.
- Artifacts + logs become `KnowledgeItem`s via source-linked knowledge writes (§5).
  This is the missing edge the loop needs.
- Knowledge informs the next experiment (read through `WorkspaceContext.knowledge`).
  Loop closes.

---

## 4. Artifact & provenance bridge

### 4.1 One artifact concept, one store

Artifacts live in one system — the workspace `ArtifactAsset` + `assets.json`; the
agent pipeline's second store was deleted in D86. `content_hash`
(`compute_content_hash`, "sha256:…") is the artifact identity.

### 4.2 Per-type expected metadata

Every artifact carries the base `Asset` fields (id, scope, path, content_hash,
`Producer`, tags) plus a typed `metadata` block. Types map onto existing/known
`ArtifactKind`s:

| Type | `kind` | Expected metadata | Agent operation |
|---|---|---|---|
| file | `artifact`/`output_file` | mime, size, role | summarize, diff vs prior version |
| table | `dataset`/`table` | schema (cols+dtypes), rowcount, units | extract metrics, compare across runs |
| figure | `plot` | caption, axes, source dataset id | summarize, describe trend (vision) |
| model | `checkpoint`/`model` | architecture, params, training run_id, metric snapshot | record provenance, compare metrics |
| log | `log`/`stdout`/`stderr` | stream, exit_code, run/exec id | classify failure → FailureAnalysis |
| report | `final_report`/`experiment_report` | sections, linked artifact ids | extract Findings/Decisions |
| metric | `metric` | name, value (`ParameterValue`), tolerance, run_id | compare to acceptance criteria |
| dataset | `dataset` | format, n_records, content_hash, source | validate, summarize, derive Observation |

An artifact `kind` is an open `str` (any non-empty string), **not** a closed
`Literal` — so new kinds (`table`, `metric`, `model`) are just new strings: there
is no vocabulary to "extend" and no schema change to make. Reuse a well-known kind
where one fits and mint a new string where none does.

### 4.3 How agents use artifacts (source-linked, never paraphrased-as-truth)

- **Summarize / describe** → produce an `Observation` KnowledgeItem whose
  `sources` cite the artifact `content_hash` + `run_id`.
- **Compare** (across runs / versions) → produce a `Finding` citing both
  artifacts.
- **Validate** (against `acceptance_criteria` / `expected_metrics`) → a
  `test_result`-style artifact + (on mismatch) a `FailureAnalysis`.
- **Extract metric** → a `metric` artifact + `ParameterRationale` if the value
  feeds a decision.

The cite mechanism is the typed OKF out-edge (reuse `Folder.append_link` /
`out_edges`, `workspace/folder.py:727,299`), given an edge **role** (`derived_from`,
`cites`, `supersedes`). This is the single small primitive several slices depend
on (§9 P0).

---

## 5. Knowledge as long-term project context

### 5.1 Typed, source-linked — not generic notes

Today knowledge = untyped `Note`/`ReferenceConcept` linked by plain markdown
links, plus an ad-hoc `experiment-record-*` Note that encodes ids in its
*name/body text* (written by the plan pipeline deleted in D86). This spec
replaces the ad-hoc bridge with a typed concept.

`KnowledgeItem` is a new OKF concept type (`@concept_type("knowledge.item")`,
registered in `knowledge/types.py`, stored as a `Folder` with
`meta.json`+`index.md` exactly like `Note`). It does **not** introduce a new
storage substrate — it is a `Note` with a typed head:

```python
KnowledgeKind = Literal[
    "Observation", "Decision", "Assumption", "Constraint", "Finding",
    "FailureAnalysis", "ProtocolNote", "ParameterRationale", "OpenQuestion",
]

class KnowledgeMeta(ConceptMeta):              # extends workspace/concept_meta.py
    kind: KnowledgeKind
    sources: list[SourceRef]                   # REQUIRED, non-empty (see 5.2)
    status: Literal["active", "stale", "superseded", "conflicting"] = "active"
    supersedes: list[str] = []                 # KnowledgeItem ids
    confidence: float | None = None
    created_by: str                            # user / agent:name
```

The body (`index.md`) holds the human-readable content; `meta.json` holds the
typed head. Reuse `Bundle` for traversal/index.

### 5.2 Source attribution (mandatory invariant)

`sources` is **required and non-empty** — a KnowledgeItem with no source fails
validation loudly (no silent empty). A `SourceRef` is a typed pointer to an
existing canonical object:

```python
class SourceRef(BaseModel):
    kind: Literal["artifact", "run", "experiment", "file", "decision", "agent_action", "reference"]
    ref: str            # content_hash | run_id | path | proposal_id | reference id
    span: str | None = None   # line range / cell / figure region, when applicable
```

Persisted as typed OKF out-edges so the knowledge graph is queryable both ways
(reuse `out_edges`). This is what makes every reasoning artifact *citeable*.

### 5.3 Who consumes knowledge

| Consumer | Uses knowledge for | Reads |
|---|---|---|
| Run failure diagnosis (§7.4) | prior FailureAnalysis with matching signature | knowledge filtered by error class |
| Workspace summaries (§7.1) | open questions, recent findings | `WorkspaceContext.knowledge` + `open_questions` |

### 5.4 Stale / duplicate / conflict detection

Detection computes, never silently mutates:

- **stale** — a `source` content-hash superseded by a newer artifact, or a `run`
  source now `failed`/deleted → flag `status="stale"`.
- **duplicate** — high text + same-`kind` + overlapping-`sources` similarity →
  flag.
- **conflict** — two `active` items of the same `kind` with contradictory claims
  over the same sources → emit `knowledge.conflict.detected` and flag both items
  `status="conflicting"`. Conflicts are **never** auto-resolved; both source
  attributions are preserved.

---

## 7. Assistive features (first useful set)

Each feature is a **consumer of `WorkspaceContext` + a producer of
artifacts/knowledge** — none owns canonical state. Mapping to existing
infra is explicit so these are seams, not new stacks.

| # | Feature | Reuses | Adds | Output |
|---|---|---|---|---|
| 7.1 | **Workspace Copilot** | `WorkspaceContext` (§1), health flags (§1.4) — served by `workspace/copilot.py` at `GET /api/workspace/copilot` | a read-only summary mode | workspace summary + ranked next-actions (advisory) |
| 7.4 | **Run Monitor** | `read_ops` (`run.py:225`), `scan_assets`, log artifacts | failure classifier over `run.failed` events | run summary + failure `Report` (`services.run_failure`) |

---

## 9. Implementation roadmap

Small cooperation-focused slices. No broad rewrite. Each builds on the prior.

### P0 — make the loop expressible (state, events, linkage, skeleton)

| Slice | Goal | Reuse | New | Files (likely) | Tests | Risk | Exit criteria |
|---|---|---|---|---|---|---|---|
| **P0.1 Typed provenance edge** | give OKF out-edges a `role` + fix Bundle nested-mount | `folder.py` links/out_edges/append_link, `bundle.py` | `EdgeRole` enum | `workspace/folder.py`, `bundle.py` | edge round-trip; nested mount under Run | low | a concept can typed-link to a Run/Artifact and resolve back |
| **P0.2 WorkspaceContext assembler** | one canonical read-model (§1) | `read_ops`, `scan_assets`, `Bundle`, folder tree | `workspace/context.py`, `WorkspaceContext` schema | `workspace/context.py`, `server/routes/` (`GET /context`), `cli` (`molexp context`) | assembler unit; route parity with old `/info` | low | server + CLI + UI read identical context |
| **P0.3 WorkspaceEvent spine** | append-only cross-object log (§2) | a new Layer-0 append-only log primitive (no store copy) | `workspace/events.py` (`WorkspaceEventLog`) + the Layer-0 primitive | `workspace/events.py`, emit sites in `run_lifecycle.py`, `assets/accessors.py` | append/seq/ordering; emit on run+asset lifecycle; single store impl (no duplicate) | medium-high | `run.*` / `asset.added` / `knowledge.created` queryable per workspace, **zero store duplication** |
| **P0.4 Run→Artifact→Knowledge link + KnowledgeItem** | typed `knowledge.item` concept with required sources (§5) | `concepts.py`, `concept_meta.py`, `knowledge/types.py`, P0.1 | `KnowledgeMeta`, `SourceRef` | `workspace/concepts.py`, `knowledge/types.py`, `server/routes/knowledge.py` | source-required validation; provenance query | medium | a KnowledgeItem cites a run/artifact and is reachable from it |
| **P0.6 Workspace summary assistant** | Copilot read-only over context (§7.1) | `WorkspaceContext`, health flags | a summary mode | `workspace/copilot.py`, `server` route (`GET /api/workspace/copilot`), UI panel | summary shape; next-action ranking | low | UI shows a grounded workspace summary + next actions |

### P1 — the assistive features

| Slice | Goal | Reuse | New | Files | Tests | Risk | Exit criteria |
|---|---|---|---|---|---|---|---|
| **P1.3 Run failure analyzer** | classify `run.failed`, emit FailureAnalysis (§7.4) | `read_ops`, log assets, P0.3/P0.4 | failure classifier | `server` monitor feature, `services.run_failure` | failure-class → knowledge | medium | a failed run produces a cited FailureAnalysis |
| **P1.5 Knowledge stale/conflict detection** | detectors (§5.4) | Bundle, KnowledgeItem, P0.4 | similarity + flags | `knowledge` detector | stale/dup/conflict cases | medium | conflicts surface as `knowledge.conflict.detected` |

### P2 — execution & learning

| Slice | Goal | Reuse | New | Risk | Exit criteria |
|---|---|---|---|---|---|
| **P2.4 Project-level learning** | mine repeated runs → ProtocolNotes/ParameterRationale | knowledge, runs, artifacts | aggregator | medium | recurring outcomes become reusable knowledge |

---

## 10. Coordination invariants (enforceable contracts)

These restate the task rules as checks the design must keep true (candidates for
import-guard / unit tests, then promotion to `CLAUDE.md`). Numbering is stable —
source cites these by number (e.g. `knowledge/knowledge_item.py` cites #4) — so a
removed invariant is marked retired, never renumbered.

1. **No parallel architecture** — every new module is a seam over an existing
   subsystem (§0). A second copy of an existing store/registry/mode is a defect.
2. **Canonical state is workspace-on-disk** — frontend state is never read as
   truth (§0, §1.1).
3. *Retired (D86).*
4. **Every KnowledgeItem has ≥1 SourceRef** — empty sources fail loudly (§5.2).
5. **Every Run output is connectable to an Artifact** — via `Producer` lineage,
   already true (§3.3, §4.1).
6. **Every Artifact used in reasoning is citeable** — by `content_hash`/`run_id`
   source ref (§4.3, §5.2).
7. **Every mutation is traceable** — a `WorkspaceEvent` with provenance (§2.2).
8. *Retired (D86).*
9. **Structured objects over free-form chat** — features emit
   artifacts/knowledge, not prose-as-state (§7).
10. **No silent invalid state** — stale/missing/conflict is *flagged*, never
    hidden by fallback (§1.4, §5.4); this extends the project's existing
    "fail loudly / no fallback" rule.

---

## Relationship to the other notes

- `architecture.md` — current-state map; the audit that motivated this spec.
- New invariants here graduate to `CLAUDE.md` via `/mol:note` **only after a
  slice lands and proves them** — not before.
