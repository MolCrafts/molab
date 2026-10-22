# molab layer integration

Coordination between the layers that already exist. Module roles live in `architecture.md`. This note only records the read-models and the seams.

## Read-models

`WorkspaceContext` (`molab.workspace.workspace_context`) fields:

- `workspace`
- `focus`
- `projects`
- `experiments`
- `workflows`
- `recent_runs`
- `failed_runs`
- `running_runs`
- `artifacts`
- `stale_or_missing`

`KnowledgeContext` (`molab.services.knowledge_context`) is that model plus `knowledge` (a list of document refs: workspace-relative path, class name, title). It adds no other field.

## Workflow identity

The workflow-layer IR is the wire IR owned by `WorkflowCodec` (`molab.workflow.codec`) and `WorkflowGraphIR` (`molab.workflow.ir`). A compiled workflow's identity is `workflow_digest` (`molab.workflow.digest`). It is stored on the Execution record and in the journal header. The document itself carries none.

## Events

History is the workspace git log. An event that names a workflow carries `workflow_digest`, not a second topology id.

## Seams

- `molab.workspace.run.set_run_executor` is installed lazily by the composition root with `workspace_run_executor`.
- `molab.workspace.metrics_seam` registers the metrics writer.
- `Experiment.bind_workflow` is the only writer of `workflow_kind` and of `workflow.ir.json`.
- Cross-entity references are `molab:` strings from `molab.workspace.refs`.
