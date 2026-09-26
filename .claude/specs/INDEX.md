# Specs Index

One line per **live** spec. `/mol:spec` adds entries; `/mol:impl` ticks the spec's tasks and prunes the entry (with the spec file) on completion.

## Open

## arch-own (chain)

_Step 2 target architecture (plan `pasted-content-id-0977-you-are-scalable-puddle.md`): one owner per concept across workspace / workflow / knowledge. Every sub-spec design-gated by `architect` design-mode (≥ 2 rounds); decisions D1–D83 in [arch-own.decisions.md](arch-own.decisions.md); every spec audited by `/mol:grill` spec-audit (`grilled: true`). Order = table order; see each spec's `depends_on`._

| # | Spec | Summary |
|---|---|---|
| 00 | [arch-own-00-safety-net](arch-own-00-safety-net.md) | 安全网：活路径特征测试与目标行为 strict xfail [done] |
| 01 | [arch-own-01-cleanup](arch-own-01-cleanup.md) | Phase 1 安全清理（死代码删除 + 四处写入顺序/锁/心跳/prune 修复） [done] |
| 02a | [arch-own-02a-record](arch-own-02a-record.md) | Execution record carries creation-time vs start-time provenance [approved] |
| 02b | [arch-own-02b-capture](arch-own-02b-capture.md) | per-execution source capture and config-aware run identity [approved] |
| 02c | [arch-own-02c-dispatch](arch-own-02c-dispatch.md) | molab run creates the Execution record at dispatch time; the worker reads it [approved] |
| 02d | [arch-own-02d-submit](arch-own-02d-submit.md) | molq submitter creates the QUEUED eNN before submit; staging carries executions/<id>/ and merges the remote record [approved] |
| 02e | [arch-own-02e-readers](arch-own-02e-readers.md) | CLI/TUI 读取方改读最新 Execution；状态投影合一 [approved] |
| 02f | [arch-own-02f-runtime](arch-own-02f-runtime.md) | workflow runtime reads bypass_cache from the Execution record; no execution-id minting [approved] |
| 02g | [arch-own-02g-harness-ids](arch-own-02g-harness-ids.md) | harness 新 run 走 Experiment.ensure_run（UUIDv7） [approved] |
| 02h | [arch-own-02h-sever](arch-own-02h-sever.md) | 切断：移除 RunMetadata 执行期来源字段、显式 id 回退与 run 级 source/ [approved] |
| 03a | [arch-own-03a-modes](arch-own-03a-modes.md) | 执行模式创建规则与 Run 路径访问器 [approved] |
| 03b | [arch-own-03b-journal](arch-own-03b-journal.md) | workflow digest + node journal owned by workflow [approved] |
| 03c | [arch-own-03c-cache](arch-own-03c-cache.md) | 节点缓存按 run 身份定位，缓存键覆盖有效配置 [approved] |
| 03d | [arch-own-03d-seam](arch-own-03d-seam.md) | run-executor 接缝懒注册 + 结果读取经接缝（删除 execution_results.py） [approved] |
| 03e | [arch-own-03e-routes](arch-own-03e-routes.md) | 服务端路由改经所有者读取 journal 与 results [approved] |
| 03f | [arch-own-03f-results](arch-own-03f-results.md) | results.json becomes a result Artifact [approved] |
| 03g | [arch-own-03g-execute](arch-own-03g-execute.md) | execute_run 统一：启动 QUEUED 记录、RESUME 从 based_on 取种子（配置一致才复用）、启动时记录 digest [approved] |
| 03h | [arch-own-03h-cli](arch-own-03h-cli.md) | CLI resume/rerun and the worker go through execute_run [approved] |
| 03i | [arch-own-03i-harness](arch-own-03i-harness.md) | harness 生命周期 resume/rerun 域对齐单一 resume 语义，plan Execution 启动即记录 digest [approved] |
| 03j | [arch-own-03j-prune](arch-own-03j-prune.md) | 收尾：删除遗留 journal 辅助函数与 RunMetadata 执行期字段，加 workflow 布局守卫 [approved] |
| 04a | [arch-own-04a-bind](arch-own-04a-bind.md) | Experiment.bind_workflow — the association record and its sole writer [approved] |
| 04b | [arch-own-04b-writers](arch-own-04b-writers.md) | switch every Workflow↔Experiment writer to Experiment.bind_workflow, plus molab migrate workflow-kind [approved] |
| 04c | [arch-own-04c-resolve](arch-own-04c-resolve.md) | kind-dispatched workflow resolution, loader moved into workflow [approved] |
| 04d | [arch-own-04d-readers](arch-own-04d-readers.md) | workflow 关联的读者切换与遗留字段删除 [approved] |
| 04e | [arch-own-04e-identity](arch-own-04e-identity.md) | workflow identity — workflow_digest is the only identity; the document carries none; retire run-level workflow fields [approved] |
| 04f | [arch-own-04f-generated](arch-own-04f-generated.md) | generated workflows bind by id (plan run + execution + entry); recoverer seam removed [approved] |
| 05a | [arch-own-05a-find-refs](arch-own-05a-find-refs.md) | molab: 引用与 Workspace.find [approved] |
| 05b | [arch-own-05b-artifact-readers](arch-own-05b-artifact-readers.md) | Artifact readers move onto Execution records, execution-relative Artifact.path [approved] |
| 05c | [arch-own-05c-asset-model](arch-own-05c-asset-model.md) | one Asset schema at every scope [approved] |
| 05d | [arch-own-05d-asset-readers](arch-own-05d-asset-readers.md) | move every remaining asset reader onto AssetRepository / Workspace.find [approved] |
| 05e | [arch-own-05e-asset-writers](arch-own-05e-asset-writers.md) | AssetRepository import writers, legacy record rewrite, `molab migrate assets` [approved] |
| 05f | [arch-own-05f-manifest-delete](arch-own-05f-manifest-delete.md) | delete the manifest family and the legacy asset read branches [approved] |
| 06a | [arch-own-06a-walker](arch-own-06a-walker.md) | one walker over workspace host enumeration, with the ranker moved out of Bundle [approved] |
| 06b | [arch-own-06b-verbs](arch-own-06b-verbs.md) | document verbs on Concept, one container rule, hostPath creation/move, CLI/UI off Bundle [approved] |
| 06c | [arch-own-06c-refs](arch-own-06c-refs.md) | molab: entity references as the one knowledge link form [approved] |
| 06d | [arch-own-06d-migrate](arch-own-06d-migrate.md) | molab migrate knowledge (opt-in, dry-run, one commit, owner-side writes) [approved] |
| 06e | [arch-own-06e-delete](arch-own-06e-delete.md) | 删除 Bundle / 目录形态 / 概念类型注册表 / 06c 遗留读垫片 [approved] |
| 06f | [arch-own-06f-sever](arch-own-06f-sever.md) | workspace sheds knowledge vocabulary [approved] |
| 07 | [arch-own-07-ui](arch-own-07-ui.md) | run-mode, workflow-kind, host-picker, molab-ref and Copilot UX left unowned by 03–06 [approved] |
| 08 | [arch-own-08-guards](arch-own-08-guards.md) | Guards: boundary, layout, one-writer, one ref composer [approved] |
| 09 | [arch-own-09-docs](arch-own-09-docs.md) | Documentation alignment (Phase 9) [approved] |

## knowledge-crossref (chain)

_Closed 01–12 on `feat/knowledge-crossref` (2026-09-23) — knowledge depends on workspace (one way); `.ref(knowledge)` cross-reference; workspace stops knowing knowledge. Design-gated by `architect` design-mode (two passes)._

| # | Spec | Commit theme |
|---|---|---|
| 01 | knowledge-crossref-01-ref | `Concept.ref` cross-reference |
| 02 | knowledge-crossref-02-owner | `folder(host, name, of)` + host construction |
| 03 | knowledge-crossref-03-verbs | write verbs move into `molab.knowledge` |
| 04 | knowledge-crossref-04-services | services own the knowledge projection |
| 05 | knowledge-crossref-05-harness | harness redirect + Folder type table |
| 06 | knowledge-crossref-06-server | server redirect |
| 07 | knowledge-crossref-07-cli | CLI harvest redirect |
| 08 | knowledge-crossref-08-sever-writes | sever the workspace write verbs |
| 09 | knowledge-crossref-09-sever-types | keep only the workspace Folder type table |
| 10 | knowledge-crossref-10-sever-reads | shed the knowledge-shaped reads |
| 11 | knowledge-crossref-11-guards | guards + CLAUDE.md law flip |
| 12 | knowledge-crossref-12-docs | public docs rewritten |

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
| 02 | [persist-one-02-run-state](persist-one-02-run-state.md) | fold ops into run.json; alive mtime heartbeat [superseded by arch-own-02a-record] |
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
