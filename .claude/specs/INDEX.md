# Specs Index

One line per **live** spec. `/mol:spec` adds entries; `/mol:impl` ticks the spec's tasks and prunes the entry (with the spec file) on completion.

## Open

## knowledge-crossref (chain)

_Approved 2026-09-23 — knowledge depends on workspace (one way); `.ref(knowledge)` cross-reference; workspace stops knowing knowledge. Design-gated by `architect` design-mode (two passes); orchestrator decisions recorded in the chain's Designs._

| # | Spec | Commit theme |
|---|---|---|
| 12 | [knowledge-crossref-12-docs](knowledge-crossref-12-docs.md) | public docs rewritten |

## knowledge-unify (chain)

_Closed 01–08 on `feat/knowledge-unify` (2026-09-20) — Knowledge + six classes; class-named json; no Bundle / meta.json as product._

| # | Spec | Commit theme |
|---|---|---|
| 01 | knowledge-unify-01-core | Knowledge + six types; class-named json |
| 02 | knowledge-unify-02-workspace | workspace consumes 01 |
| 03 | knowledge-unify-03-services | analyze_run_failure writes Report |
| 04 | knowledge-unify-04-cli | CLI Knowledge(root); harvest Finding/Observation/Report |
| 05 | knowledge-unify-05-server | server walk/search/open; harvest of= |
| 06 | knowledge-unify-06-harness | harness digest + records on six classes |
| 07 | knowledge-unify-07-ui | web plugin six classes + generate:api |
| 08 | knowledge-unify-08-cutover | delete shims, docs, grep-clean |

## persist-one (chain)

_One persist format: JSONL metrics in artifacts/, no ops/ sidecar, no harness.sqlite._

| # | Spec | Commit theme |
|---|---|---|
| 01 | [persist-one-01-metrics](persist-one-01-metrics.md) | JSONL-only host metrics under artifacts/ [approved] |
| 02 | [persist-one-02-run-state](persist-one-02-run-state.md) | fold ops into run.json; alive mtime heartbeat [approved] |
| 03 | [persist-one-03-harness-files](persist-one-03-harness-files.md) | file stores replace harness.sqlite [approved] |
| 04 | [persist-one-04-cutover](persist-one-04-cutover.md) | callers, docs, delete sqlitelog [approved] |

## host-reflect (chain)

_Closed 01 on `dev` (2026-08-19) — `Reflection` plugin on `agent/post-step` waterfall._

| # | Spec | Commit theme |
|---|---|---|
| 01 | host-reflect-01-plugin | AgentStep + Reflection |

## bundle-chat (chain)

_Closed 01 on `dev` (2026-08-19) — `ChatMode` → `Chat`._

| # | Spec | Commit theme |
|---|---|---|
| 01 | bundle-chat-01-class | `Chat` bundle |

## plan-bundle (chain)

_Closed 01–02 on `dev` (2026-08-19) — deleted `PlanOrchestrator`; plan is `run_plan`._

| # | Spec | Commit theme |
|---|---|---|
| 01 | plan-bundle-01-run | `run_plan` replaces the class |
| 02 | plan-bundle-02-callers | CLI/server/docs cut over |

## host-approval (chain)

_Closed 01–02 on `dev` (2026-08-19) — store-first `approval/request` hung on `tools/pre-execute`._

| # | Spec | Commit theme |
|---|---|---|
| 01 | host-approval-01-request | `approval/request` waterfall |
| 02 | host-approval-02-tools | side-effect tools + compose mount |

## host-align (chain)

_Closed 01–04 on `dev` (2026-08-19) — DeepSeek/Cordis `ctx.xxx`: attribute access, `ctx.llm`, `tools/*` pipeline, workspace/workflow plugins._

| # | Spec | Commit theme |
|---|---|---|
| 01 | host-align-01-ctx | `ctx.tools` + `agent/pre-step` |
| 02 | host-align-02-llm | `ctx.llm` is the only model seam |
| 03 | host-align-03-tools | `tools/pre-execute` → execute → post-execute |
| 04 | host-align-04-plugins | `ctx.workspace` / `ctx.workflow` |

## plan-and-solve (superseded)

_Discarded 2026-08-19 — rebuilt as host-align; no impl landed._

## close-loop (chain)

_Closed 01–06 on `feat/close-loop` (2026-08-06) — multi-pillar learning loop: plan knowledge feed, run FailureAnalysis, metrics_ingest product surface, Copilot UI, diagnose wire, entity density locks._

| # | Spec | Commit theme |
|---|---|---|
| 01 | close-loop-01-plan-knowledge | PlanOrchestrator + AssembleKnowledgeContext |
| 02 | close-loop-02-run-failure | services.run_failure + CLI/API |
| 03 | close-loop-03-metrics-land | metrics_ingest plugin + CLI/API + docs |
| 04 | close-loop-04-copilot-ui | RightPanel Copilot over GET /copilot |
| 05 | close-loop-05-diagnose-wire | Analyze button + Copilot diagnose → API |
| 06 | close-loop-06-entity-density | Relations/catalog/lifecycle tests |

### Deferred (not specs yet — open when evidence bites)

| Theme | Why deferred |
|---|---|
| High-risk ChangeProposal policy table (integration P2.1) | lifecycle/curate gates exist; full policy matrix needs production pain |
| `assets.scan` scale index | intentional full-manifest scan; revisit on real large workspaces |
| Multi-agent adversarial plan review (P2.3) | single-auditor StepAuditLoop sufficient for now |
| Workspace-global event timeline UI | `workspace.events` spine exists; consumer is product polish |
| Default-on auto-analyze / auto-ingest | cost/noise; keep opt-in only |

---

## plan-emergent (chain)

_Closed 01–08 (2026-07-11) — two-phase **emergent-planning → deterministic-realization** rewrite of harness PlanMode; cutover landed in `37a3ef0`._

## plan-step-audit (chain)

_Closed 01–05 on feat/plan-step-audit._

_Closed: agent-code-loop 01–05 (2026-07-10); product-gap remediation; agent-record-export 01–08; execution-semantics; pure-task-context-03 (blocked)._
