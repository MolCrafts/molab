# Guide

The guide section is for topics that are easier to read after the first-run path already makes sense. The pages here assume you know what a workflow is, why `Project`, `Experiment`, and `Run` are separate, and how `molab run` discovers a registered workspace.

## Workflow Authoring

When the question is about the shape of the graph itself, start with [Task and Actor](task-and-actor.md). Continue with [TaskContext](task-context.md) when you need the execution boundary inside one task, and [Workflow Runtime](workflow-runtime.md) when you need to understand what happens after `WorkflowRuntime().execute(...)` starts. [Control Flow](control-flow.md) and [Sub-workflows](subworkflows.md) are the pages to read once ordinary dependency edges are no longer enough.

## Records and Assets

When the question is about persistent state, start with [Workspace API](workspace-api.md) and [Workspace Architecture](workspace-architecture.md). Those two pages describe the same model from different angles: one from the Python surface, one from the on-disk structure. [Assets](assets.md) explains reusable named resources, and [Workflow Persistence](workflow-persistence.md) explains which pieces of execution state are serialized and which are reconstructed from source.

## Knowledge

When the question is "what did this run *mean*," go to [Knowledge and Cross-References](knowledge.md). It covers the markdown documents — notes, plans, reports, findings — that sit beside the experiments they describe, why a document's path is its identity, and how the links between documents form the project's knowledge graph.

## Operations and Scheduling

When the question is about long-running services or scheduler transport, go to [Server Lifecycle](server-lifecycle.md) and [Molq Plugin](molq.md). Those pages are intentionally outside the onboarding path because they matter only after the local workflow and workspace model are already stable. Checkout vs bundled UI vs wheel: [Serve and rebuild the UI](../development/ui-serve.md).
