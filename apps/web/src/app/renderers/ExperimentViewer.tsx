/**
 * The experiment page (Figma L03): views Overview · Runs (n) · Params ·
 * Workflow · Notebook, a rule, then Structures. The state's primary action and
 * ⋯ sit at the right of the editor tab row. The Runs filter lives in the URL
 * (`…/runs?filter=status:failed,interrupted`), so the Overview's verdict can
 * open exactly the runs it counts.
 */

import {
  Activity,
  Atom,
  FileQuestion,
  FileText,
  FlaskConical,
  SlidersHorizontal,
  Table2,
  Workflow,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { experimentsApi } from "@/api";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import { useCompareSet } from "@/app/compare";
import { activeWorkspace, itemFromRunSummary } from "@/app/compare/entries";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import { EmptyState, EntityPage, ViewLabel } from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { experimentPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import { ExperimentStructures } from "@/app/renderers/ExperimentStructures";
import { experimentRunCompleteness } from "@/app/renderers/entityWorkbenchData";
import { ExperimentEditorActions } from "@/app/renderers/experiment/ExperimentEditorActions";
import { ExperimentOverview } from "@/app/renderers/experiment/ExperimentOverview";
import { ExperimentParams } from "@/app/renderers/experiment/ExperimentParams";
import { ExperimentRunsTable } from "@/app/renderers/experiment/ExperimentRunsTable";
import { UnboundWorkflow } from "@/app/renderers/experiment/UnboundWorkflow";
import { runLabel } from "@/app/runs/runTitle";
import { isEditorDirty, useDirtyEditors } from "@/app/shell/dirtyEditors";
import { experimentWorkflowLabel } from "@/app/state/api";
import { useNavigationState } from "@/app/state/useNavigationState";
import { SweepDialog } from "@/app/sweep/SweepDialog";
import type { ExperimentView, RunSummary, ScopedRendererProps } from "@/app/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { parseWorkflowIr } from "@/components/workflow/workflow-graph";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { ExperimentNotebook } from "@/plugins/knowledge/ExperimentNotebook";
import { isPluginEnabled, usePluginPreferencesGeneration } from "@/plugins/preferences";

const WorkflowGraphViewer = lazy(() =>
  import("@/plugins/workflow/WorkflowGraphViewer").then((module) => ({
    default: module.WorkflowGraphViewer,
  })),
);

const VIEWS: readonly ExperimentView[] = [
  "overview",
  "runs",
  "parameters",
  "workflow",
  "notebook",
  "products",
];

export const ExperimentViewer = ({
  selection,
  snapshot,
  inspectorTarget,
  onInspectorTargetChange,
  onRefresh,
}: ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "workspaces"
>): JSX.Element => {
  const [sweepOpen, setSweepOpen] = useState(false);
  const { confirm, dialog: confirmDialog } = useConfirm();
  const navigate = useNavigate();
  const preview = usePreview();
  const compare = useCompareSet();
  // `?run=new` (a Preview's New run) opens the dialog once, then leaves the URL.
  const [searchParams, setSearchParams] = useSearchParams();
  const [createRunOpen, setCreateRunOpen] = useState(false);
  useEffect(() => {
    if (searchParams.get("run") !== "new") return;
    setCreateRunOpen(true);
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("run");
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);
  // Re-render when the user toggles the Workflow plugin in Settings.
  usePluginPreferencesGeneration();
  useContributionGeneration();

  const { setSelection } = useNavigationState(snapshot);
  const dirtyEditors = useDirtyEditors();
  const experimentId = selection.objectId;
  const experiment = snapshot.experiments.find((e) => e.id === experimentId);
  const projectId = experiment?.projectId || "";
  const activeTab: ExperimentView =
    selection.objectType === "experiment" ? (selection.experimentView ?? "overview") : "overview";

  const setEntityTab = useCallback(
    (value: string) => {
      const experimentView = (VIEWS as readonly string[]).includes(value)
        ? (value as ExperimentView)
        : "overview";
      setSelection({ objectType: "experiment", objectId: experimentId, experimentView });
    },
    [experimentId, setSelection],
  );

  const runs = useMemo(
    () => snapshot.runs.filter((r) => r.experimentId === experimentId),
    [snapshot.runs, experimentId],
  );
  const {
    query: scopeRuns,
    rows: scopeRows,
    truncated,
  } = useScopeRuns({ experimentId }, Boolean(experimentId) && activeTab === "overview");

  const compareScope = useMemo(() => {
    const ws = activeWorkspace(snapshot.workspaces);
    if (!ws) return null;
    return {
      workspaceKey: ws.key,
      workspaceLabel: ws.label,
      projectName: snapshot.projects.find((project) => project.id === projectId)?.name ?? projectId,
      experimentName: experiment?.name ?? experimentId,
    };
  }, [snapshot.workspaces, snapshot.projects, projectId, experiment?.name, experimentId]);

  const compareRuns = useCallback(
    (picked: readonly RunSummary[]) => {
      if (!compareScope) return;
      compare.addMany(picked.map((run) => itemFromRunSummary(run, compareScope)));
      navigate("/compare");
    },
    [compare, compareScope, navigate],
  );

  const filter = searchParams.get("filter") ?? "";
  const setFilter = (next: string): void =>
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        if (next) params.set("filter", next);
        else params.delete("filter");
        return params;
      },
      { replace: true },
    );
  const openRuns = (next?: string): void => {
    const base = experimentPath(projectId, experimentId, "runs");
    navigate(next ? `${base}?${new URLSearchParams({ filter: next })}` : base);
  };

  const handleDelete = async (): Promise<void> => {
    if (!projectId) return;
    const confirmed = await confirm({
      title: `Delete experiment “${experiment?.name ?? "this experiment"}”?`,
      description: `Its ${runs.length} ${runs.length === 1 ? "run is" : "runs are"} removed with it.`,
      confirmLabel: "Delete experiment",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await experimentsApi.deleteExperiment(projectId, experimentId);
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete the experiment");
    }
  };

  if (!experiment || !projectId) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState icon={<FileQuestion className="h-6 w-6" />} title="Not found" />
      </div>
    );
  }

  if (experiment.runsError) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Could not load runs"
        detail={experiment.runsError}
        action={<WorkbenchRetryAction onClick={onRefresh} />}
      />
    );
  }

  const workflow = snapshot.workflows.find((item) => item.experimentId === experiment.id);
  const workflowGraph = workflow?.graph ?? parseWorkflowIr(experiment.workflowSource);
  // Every experiment has a workflow entry in the catalog; it is bound only if it has a graph or a locator.
  const hasWorkflow = Boolean(
    workflowGraph || experiment.workflowFile || experiment.workflowEntrypoint,
  );
  const workflowPluginEnabled = isPluginEnabled("workflow");
  const workflowSelection =
    workflowPluginEnabled && workflow && hasWorkflow
      ? { objectType: "workflow" as const, objectId: workflow.id, workflowId: workflow.id }
      : null;
  const { runsComplete } = experimentRunCompleteness(experiment, runs.length);
  const workflowDirty = isEditorDirty(dirtyEditors, experimentPath(projectId, experimentId));

  const needsAuth = activeNeedsAuth(snapshot.workspaces);
  const overviewError = shouldShowFailure(scopeRuns.error, {
    fetching: scopeRuns.isFetching,
    needsAuth,
  })
    ? scopeRuns.error instanceof Error
      ? scopeRuns.error.message
      : "Could not load experiment activity"
    : null;

  const previewRun = (run: RunSummary | string): void => {
    const target = typeof run === "string" ? runs.find((item) => item.id === run) : run;
    preview.preview({
      kind: "run",
      runId: typeof run === "string" ? run : run.id,
      projectId,
      experimentId,
      ...(target ? { label: runLabel(target) } : {}),
    });
  };

  const overview = overviewError ? (
    <WorkbenchOperationState
      kind="error"
      density="compact"
      title="Could not load experiment activity"
      detail={overviewError}
      action={<WorkbenchRetryAction onClick={() => void scopeRuns.refetch()} />}
    />
  ) : !runsComplete && runs.length === 0 ? (
    <WorkbenchOperationState
      kind="loading"
      density="compact"
      title="Loading runs…"
      skeletonRows={3}
    />
  ) : (
    <ExperimentOverview
      experiment={experiment}
      runs={runs}
      rows={scopeRows}
      partial={truncated || !runsComplete}
      hasWorkflow={hasWorkflow}
      onOpenRuns={openRuns}
      onPreviewRun={previewRun}
      onOpenWorkflow={() => setEntityTab("workflow")}
      onNewRun={() => setCreateRunOpen(true)}
      onSweep={() => setSweepOpen(true)}
    />
  );

  const tabs = [
    {
      value: "overview",
      label: <ViewLabel icon={Activity}>Overview</ViewLabel>,
      content: overview,
    },
    {
      value: "runs",
      label: (
        <ViewLabel icon={Table2} count={runs.length}>
          Runs
        </ViewLabel>
      ),
      content: (
        <ExperimentRunsTable
          runs={runs}
          experimentId={experimentId}
          filter={filter}
          onFilterChange={setFilter}
          onPreview={previewRun}
          onOpen={(run, background) =>
            background
              ? preview.open(
                  { kind: "run", runId: run.id, projectId, experimentId },
                  { background: true },
                )
              : setSelection({ objectType: "run", objectId: run.id })
          }
          compareDisabledReason={
            compareScope ? null : "No served workspace to attribute these runs to."
          }
          onCompare={compareRuns}
          onChanged={onRefresh}
        />
      ),
    },
    {
      value: "parameters",
      label: <ViewLabel icon={SlidersHorizontal}>Params</ViewLabel>,
      content: (
        <ExperimentParams experiment={experiment} runs={runs} onSweep={() => setSweepOpen(true)} />
      ),
    },
    {
      value: "workflow",
      label: (
        <ViewLabel icon={Workflow} dirty={workflowDirty}>
          Workflow
        </ViewLabel>
      ),
      content: workflowSelection ? (
        <Suspense
          fallback={
            <WorkbenchOperationState
              kind="loading"
              density="compact"
              title="Loading workflow…"
              skeletonRows={3}
            />
          }
        >
          <div className="h-full min-h-0 overflow-hidden bg-canvas">
            <WorkflowGraphViewer
              selection={workflowSelection}
              snapshot={snapshot}
              inspectorTarget={inspectorTarget}
              onInspectorTargetChange={onInspectorTargetChange}
              onRefresh={onRefresh}
            />
          </div>
        </Suspense>
      ) : workflowPluginEnabled ? (
        <UnboundWorkflow
          projectName={snapshot.projects.find((item) => item.id === projectId)?.name ?? projectId}
          experimentName={experiment.name}
        />
      ) : (
        <div className="flex h-full items-center justify-center bg-background px-6">
          <EmptyState
            title="Workflow viewer disabled"
            description="Enable the Workflow plugin in Settings to see the graph."
          />
        </div>
      ),
    },
    {
      value: "notebook",
      label: <ViewLabel icon={FileText}>Notebook</ViewLabel>,
      content: (
        <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
          <ExperimentNotebook
            hostPath={experiment.path}
            runs={snapshot.runs}
            onOpen={setSelection}
          />
        </div>
      ),
    },
    ...(runs.length > 0
      ? [
          {
            value: "products",
            dividerBefore: true,
            label: <ViewLabel icon={Atom}>Structures</ViewLabel>,
            content: <ExperimentStructures runs={runs} />,
          },
        ]
      : []),
  ];

  return (
    <>
      <EntityPage
        icon={FlaskConical}
        title={experiment.name}
        actions={
          <ExperimentEditorActions
            experiment={experiment}
            runs={runs}
            onNewRun={() => setCreateRunOpen(true)}
            onSweep={() => setSweepOpen(true)}
            onCompareAll={compareScope ? () => compareRuns(runs) : null}
            onDelete={() => void handleDelete()}
            onChanged={onRefresh}
          />
        }
        activeTab={activeTab}
        onActiveTabChange={setEntityTab}
        tabs={tabs}
      />
      {confirmDialog}
      <CreateRunDialog
        projectId={projectId}
        experimentId={experimentId}
        workflowFile={experimentWorkflowLabel(experiment)}
        open={createRunOpen}
        onOpenChange={setCreateRunOpen}
        trigger={null}
        onRunCreated={(runId) => {
          onRefresh();
          setSelection({ objectType: "run", objectId: runId });
        }}
      />
      <SweepDialog
        projectId={projectId}
        experimentId={experimentId}
        parameterSpace={experiment.parameterSpace}
        runs={runs}
        open={sweepOpen}
        onOpenChange={setSweepOpen}
        onCreated={() => {
          onRefresh();
          setEntityTab("runs");
        }}
      />
    </>
  );
};
