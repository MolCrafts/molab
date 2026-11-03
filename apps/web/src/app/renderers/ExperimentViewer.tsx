import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@molcrafts/ui";
import {
  Check,
  Copy,
  FileQuestion,
  FlaskConical,
  Grid3x3,
  ListChecks,
  ListPlus,
  MoreHorizontal,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { experimentsApi } from "@/api";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import { useCompareSet } from "@/app/compare";
import { activeWorkspace, itemFromRunSummary } from "@/app/compare/entries";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import { CreateSweepDialog } from "@/app/components/CreateSweepDialog";
import type { DataTableColumn, DataTableRowAction } from "@/app/components/entity";
import {
  ChoiceToggle,
  CopyButton,
  DataTable,
  EMPTY_COPY,
  EmptyState,
  EntityPage,
  InventoryCanvas,
  MagnitudeBar,
  OverviewCanvas,
  OverviewSurface,
  StatusIcon,
  SweepMatrix,
} from "@/app/components/entity";
import {
  paramGroup,
  rollupExecutions,
  varyingParameterKeys,
} from "@/app/dashboard/dashboardWidgets";
import { ExecutionOverview } from "@/app/dashboard/ExecutionOverview";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { buildRunListActions, type RunListHandlers } from "@/app/entities/runListActions";
import { countRunStatuses, formatDuration, formatScalar } from "@/app/renderers/dashboardData";
import {
  buildExperimentWorkbenchData,
  experimentRunCompleteness,
} from "@/app/renderers/entityWorkbenchData";
import { sweepAxes, unrunValueCount } from "@/app/renderers/overview/gaugeData";
import { ConstantsNote } from "@/app/renderers/overview/MarginNotes";
import { useRunMultiSelect } from "@/app/runs/useRunMultiSelect";
import { experimentWorkflowLabel } from "@/app/state/api";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { ExperimentView, RunSummary, ScopedRendererProps } from "@/app/types";
import { toast } from "@/components/ui/toast";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { parseWorkflowIr } from "@/components/workflow/workflow-graph";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { formatRelative } from "@/lib/format-time";
import { getWorkspaceFs } from "@/lib/workspace-fs";
import { formatQualifiedPath, runWorkspaceRelativePath } from "@/lib/workspace-path";
import { ExperimentNotebook } from "@/plugins/knowledge/ExperimentNotebook";
import { isPluginEnabled, usePluginPreferencesGeneration } from "@/plugins/preferences";

const WorkflowGraphViewer = lazy(() =>
  import("@/plugins/workflow/WorkflowGraphViewer").then((module) => ({
    default: module.WorkflowGraphViewer,
  })),
);

const ParametersCell = ({ run, keys }: { run: RunSummary; keys: string[] }): JSX.Element => {
  const entries = keys
    .map((key) => [key, run.parameters?.[key]] as const)
    .filter(([, value]) => value !== undefined);
  if (entries.length === 0) return <span className="text-label text-muted-foreground">—</span>;
  const visible = entries.slice(0, 2);
  return (
    <div className="flex max-w-56 flex-nowrap items-center gap-1 overflow-hidden">
      {visible.map(([key, value]) => (
        <span
          key={key}
          className="min-w-0 truncate text-label text-muted-foreground"
          title={`${key}=${formatScalar(value)}`}
        >
          <span className="text-foreground">
            {key}={formatScalar(value)}
          </span>
        </span>
      ))}
      {entries.length > visible.length && (
        <Popover>
          <PopoverTrigger asChild>
            <WorkbenchIconAction
              label={`View all ${entries.length} parameters`}
              onClick={(event) => event.stopPropagation()}
            >
              <SlidersHorizontal aria-hidden />
            </WorkbenchIconAction>
          </PopoverTrigger>
          <PopoverContent
            side="bottom"
            align="start"
            className="max-h-80 w-72 overflow-auto p-3"
            onClick={(event) => event.stopPropagation()}
          >
            <dl className="space-y-2">
              {entries.map(([key, value]) => (
                <div
                  key={key}
                  className="grid grid-cols-(--experiment-meta-grid-columns) gap-2 text-label"
                >
                  <dt className="truncate text-muted-foreground">{key}</dt>
                  <dd className="truncate font-mono text-foreground" title={formatScalar(value)}>
                    {formatScalar(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </PopoverContent>
        </Popover>
      )}
      <CopyButton
        value={JSON.stringify(run.parameters ?? {}, null, 2)}
        label={`${run.name || run.id} parameters`}
        className="size-4-lg"
      />
    </div>
  );
};

export const ExperimentViewer = ({
  selection,
  snapshot,
  inspectorTarget,
  onInspectorTargetChange,
  onRefresh,
}: ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "workspaces"
>): JSX.Element => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [sweepOpen, setSweepOpen] = useState(false);
  // Re-render when the user toggles the Workflow plugin in Settings.
  usePluginPreferencesGeneration();
  useContributionGeneration();

  const { setSelection } = useNavigationState(snapshot);

  const experimentId = selection.objectId;
  const experiment = snapshot.experiments.find((e) => e.id === experimentId);
  const projectId = experiment?.projectId || "";
  const activeTab: ExperimentView =
    selection.objectType === "experiment" ? (selection.experimentView ?? "overview") : "overview";

  const setEntityTab = useCallback(
    (value: string) => {
      const experimentView: ExperimentView =
        value === "workflow" || value === "runs" || value === "parameters" || value === "notebook"
          ? value
          : "overview";
      setSelection({ objectType: "experiment", objectId: experimentId, experimentView });
    },
    [experimentId, setSelection],
  );

  const runs = useMemo(
    () => snapshot.runs.filter((r) => r.experimentId === experimentId),
    [snapshot.runs, experimentId],
  );

  const counts = useMemo(() => countRunStatuses(runs), [runs]);
  const {
    query: scopeRuns,
    rows: scopeRows,
    truncated: scopeTruncated,
  } = useScopeRuns({ experimentId }, Boolean(experimentId) && activeTab === "overview");
  const [groupAxis, setGroupAxis] = useState<string | null>(null);
  // Domain for the in-row duration bars: the slowest run in this experiment.
  const maxRunDurationMs = useMemo(
    () =>
      runs.reduce((longest, run) => {
        if (!run.startedAt || !run.finishedAt) return longest;
        const ms = Date.parse(run.finishedAt) - Date.parse(run.startedAt);
        return Number.isFinite(ms) && ms > longest ? ms : longest;
      }, 0),
    [runs],
  );

  // Union of parameter keys across all runs — stable first-seen order. Declared
  // before any early return so the hook order is unconditional.
  const parameterKeys = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    for (const run of runs) {
      for (const key of Object.keys(run.parameters ?? {})) {
        if (!seen.has(key)) {
          seen.add(key);
          order.push(key);
        }
      }
    }
    return order;
  }, [runs]);

  // Ephemeral multi-run selection (local React state, not the Zustand store) for
  // the metrics-aggregation flow: pick runs in this tab, aggregate in the next.
  const orderedRunIds = useMemo(() => runs.map((run) => run.id), [runs]);
  const runIndex = useMemo(
    () => new Map(orderedRunIds.map((id, index) => [id, index] as const)),
    [orderedRunIds],
  );
  const multi = useRunMultiSelect(orderedRunIds);
  const compare = useCompareSet();

  // The comparison set spans workspaces, so a run added from here has to carry
  // the workspace it came from. An experiment page always shows the active one.
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

  const selectedRuns = useMemo(
    () => runs.filter((run) => multi.selected.has(run.id)),
    [runs, multi.selected],
  );

  const addSelectedToCompare = useCallback(() => {
    if (!compareScope) return;
    compare.addMany(selectedRuns.map((run) => itemFromRunSummary(run, compareScope)));
  }, [compare, compareScope, selectedRuns]);

  const handleDelete = async () => {
    if (!projectId) return;
    if (!window.confirm(`Delete “${experiment?.name ?? "this experiment"}”?`)) {
      return;
    }
    setIsDeleting(true);
    try {
      await experimentsApi.deleteExperiment(projectId, experimentId);
      onRefresh();
    } catch (error) {
      console.error("Failed to delete experiment:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const navigateToRun = (runId: string) => {
    setSelection({ objectType: "run", objectId: runId });
  };

  const runListHandlers: RunListHandlers = useMemo(() => {
    const active = snapshot.workspaces.find((w) => w.active) ?? snapshot.workspaces[0] ?? null;
    const pathContext = {
      root: getWorkspaceFs().root,
      workspace: active
        ? { label: active.label, isRemote: active.isRemote, path: active.path }
        : null,
    };
    return {
      copyId: (run) => {
        void navigator.clipboard.writeText(run.id);
        toast.success("Copied ID");
      },
      copyPath: (run) => {
        const text = formatQualifiedPath(runWorkspaceRelativePath(run), pathContext);
        void navigator.clipboard.writeText(text);
        toast.success("Copied path");
      },
    };
  }, [snapshot.workspaces]);

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
  const workbench = buildExperimentWorkbenchData(
    experiment,
    runs,
    workflowGraph ? { graph: workflowGraph } : workflow,
  );

  const runColumns: DataTableColumn<RunSummary>[] = [
    {
      key: "id",
      header: "Run",
      width: "w-44",
      cell: (run) => (
        <div className="flex min-w-0 items-center gap-1" title={run.name || "Run"}>
          <span className="min-w-0 flex-1 truncate text-body">{run.name || run.id}</span>
          <CopyButton
            value={run.id}
            label="run ID"
            className="size-5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "State",
      width: "w-18",
      cell: (run) => <StatusIcon status={run.status} />,
    },
    {
      key: "parameters",
      header: "Parameters",
      width: "w-48",
      cell: (run) => (
        <ParametersCell
          run={run}
          keys={
            workbench.varyingAxes.length > 0
              ? workbench.varyingAxes.map((axis) => axis.key)
              : parameterKeys
          }
        />
      ),
    },
    {
      key: "executions",
      header: "Executions",
      cell: (run) => (
        <span className="whitespace-nowrap text-label tabular-nums text-muted-foreground">
          {run.statusSummary.total} ({run.statusSummary.active} active)
        </span>
      ),
    },
    {
      key: "duration",
      header: "Duration",
      width: "w-32",
      cell: (run) => {
        const label = formatDuration(run.startedAt, run.finishedAt);
        const ms =
          run.startedAt && run.finishedAt
            ? Date.parse(run.finishedAt) - Date.parse(run.startedAt)
            : null;
        return (
          <MagnitudeBar
            value={Number.isFinite(ms) ? ms : null}
            max={maxRunDurationMs}
            label={label ?? "—"}
            title={label ? `${label} wall clock` : "Not finished"}
          />
        );
      },
    },
    {
      key: "updated",
      header: "Updated",
      width: "w-32",
      cell: (run) => (
        <span className="text-label text-muted-foreground" title={run.updatedAt}>
          {formatRelative(run.updatedAt)}
        </span>
      ),
    },
  ];

  // Leading tick column, shown only in multi-select mode. The cell button reads
  // the native event so shift (range) / ctrl|meta (toggle) modifiers reach the
  // pure selection reducer — DataTable's row activation carries no native event.
  const selectionColumn: DataTableColumn<RunSummary> = {
    key: "select",
    header: "",
    width: "w-control-comfortable",
    cell: (run) => {
      const checked = multi.selected.has(run.id);
      return (
        <WorkbenchAction
          kind="ghost"
          size="content"
          type="button"
          aria-pressed={checked}
          aria-label={checked ? "Deselect run" : "Select run"}
          onClick={(event) => {
            event.stopPropagation();
            multi.selectAt(runIndex.get(run.id) ?? 0, {
              shift: event.shiftKey,
              meta: event.metaKey || event.ctrlKey,
            });
          }}
          className={`flex size-4 items-center justify-center rounded-control border transition-colors ${
            checked
              ? "border-accent bg-accent text-accent-foreground"
              : "border-border hover:border-accent"
          }`}
        >
          {checked && <Check className="h-3 w-3" />}
        </WorkbenchAction>
      );
    },
  };
  const tableColumns = multi.enabled ? [selectionColumn, ...runColumns] : runColumns;

  const runRowActions = (run: RunSummary): DataTableRowAction<RunSummary>[] =>
    buildRunListActions(run, runListHandlers).map((action) => ({
      id: action.id,
      label: action.label,
      icon: action.icon,
      disabled: action.disabled,
      destructive: action.destructive,
      separatorBefore: action.separatorBefore,
      title: action.title,
      onSelect: () => action.onSelect(),
    }));
  const sweep = sweepAxes(workbench.axisBreakdowns);
  const unrun = unrunValueCount(sweep);
  const workflowPluginEnabled = isPluginEnabled("workflow");
  const hasWorkflowData = Boolean(
    workflowPluginEnabled && workflow && workbench.workflowSummary.exists,
  );
  const workflowSelection =
    hasWorkflowData && workflow
      ? { objectType: "workflow" as const, objectId: workflow.id, workflowId: workflow.id }
      : null;
  const workflowViewer = workflowSelection ? (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center p-6">
          <EmptyState title="Loading workflow" description="Preparing the graph viewer…" />
        </div>
      }
    >
      <WorkflowGraphViewer
        selection={workflowSelection}
        snapshot={snapshot}
        inspectorTarget={inspectorTarget}
        onInspectorTargetChange={onInspectorTargetChange}
        onRefresh={onRefresh}
      />
    </Suspense>
  ) : null;

  const { runsComplete, runCount } = experimentRunCompleteness(experiment, runs.length);
  const runCountValue = runCount ?? (runs.length > 0 ? counts.total : null);

  // Always pass full tab bodies (EntityTabContent hides inactive with CSS).
  // Conditional `activeTab === … ? content : null` remounted Flowgram on every switch.
  // Group the Overview by a swept parameter; the user may pick which one.
  const axisKeys = varyingParameterKeys(scopeRows);
  const activeAxis = groupAxis && axisKeys.includes(groupAxis) ? groupAxis : (axisKeys[0] ?? null);
  const needsAuth = activeNeedsAuth(snapshot.workspaces);
  const overviewError = shouldShowFailure(scopeRuns.error, {
    fetching: scopeRuns.isFetching,
    needsAuth,
  })
    ? scopeRuns.error instanceof Error
      ? scopeRuns.error.message
      : "Could not load experiment activity"
    : null;
  const overviewPending = scopeRuns.isPending || (needsAuth && scopeRuns.data === undefined);

  // Always pass full tab bodies (EntityTabContent hides inactive with CSS).
  // Conditional `activeTab === … ? content : null` remounted Flowgram on every switch.
  const overviewContent = (
    <OverviewCanvas>
      {overviewError ? (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load experiment activity"
          detail={overviewError}
          action={<WorkbenchRetryAction onClick={() => void scopeRuns.refetch()} />}
        />
      ) : overviewPending ? (
        <WorkbenchOperationState
          kind="loading"
          density="compact"
          title="Loading experiment activity…"
          skeletonRows={3}
        />
      ) : rollupExecutions(scopeRows).total === 0 ? (
        <EmptyState
          title="No executions yet"
          description="Start a run, or a sweep from the More menu, and this page fills in."
        />
      ) : (
        <ExecutionOverview
          rows={scopeRows}
          partial={scopeTruncated || !runsComplete}
          inventoryBlocked={scopeTruncated}
          groupBy={activeAxis ? paramGroup(activeAxis) : "experiment"}
          groupControl={
            axisKeys.length > 1 && activeAxis ? (
              <ChoiceToggle
                label="Group by parameter"
                value={activeAxis}
                choices={axisKeys.map((key) => ({ value: key, label: key }))}
                onChange={setGroupAxis}
              />
            ) : undefined
          }
          onOpenAttention={() => setEntityTab("runs")}
          onOpenTimeline={() => setEntityTab("runs")}
          attentionHint="Runs"
          timelineHint="Runs"
        />
      )}
    </OverviewCanvas>
  );

  return (
    <EntityPage
      icon={FlaskConical}
      title={experiment.name}
      meta={
        <span>
          <span className="text-foreground">{runCountValue === null ? "—" : runCountValue}</span>{" "}
          runs
        </span>
      }
      actions={
        <>
          <CreateRunDialog
            projectId={projectId}
            experimentId={experimentId}
            workflowFile={experimentWorkflowLabel(experiment)}
            onRunCreated={(runId) => {
              onRefresh();
              navigateToRun(runId);
            }}
          />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <WorkbenchIconAction label="More">
                <MoreHorizontal className="size-4" />
              </WorkbenchIconAction>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onClick={() => setSweepOpen(true)}>
                <Grid3x3 className="size-icon-sm" />
                Sweep
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => {
                  void navigator.clipboard.writeText(experiment.id);
                  toast.success("Copied");
                }}
              >
                <Copy className="size-icon-sm" />
                Copy ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={isDeleting}
                className="text-destructive focus:text-destructive"
                onClick={() => void handleDelete()}
              >
                <Trash2 className="size-icon-sm" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <CreateSweepDialog
            projectId={projectId}
            experimentId={experimentId}
            open={sweepOpen}
            onOpenChange={setSweepOpen}
            onCreated={() => {
              onRefresh();
              setEntityTab("runs");
            }}
          />
        </>
      }
      activeTab={activeTab}
      onActiveTabChange={setEntityTab}
      tabs={[
        {
          value: "overview",
          label: "Overview",
          content: overviewContent,
        },
        {
          value: "workflow",
          label: "Workflow",
          content: (
            <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
              <InventoryCanvas fill className="min-h-0 flex-1 gap-0 space-y-0">
                {hasWorkflowData && workflowViewer ? (
                  <div className="min-h-0 flex-1 overflow-hidden bg-canvas">{workflowViewer}</div>
                ) : (
                  <EmptyState
                    title={
                      workflowPluginEnabled ? "No workflow available" : "Workflow viewer disabled"
                    }
                    description={
                      workflowPluginEnabled
                        ? "This experiment does not have a workflow graph to display."
                        : "Enable the Workflow plugin in Settings to inspect the graph."
                    }
                  />
                )}
              </InventoryCanvas>
            </OverviewSurface>
          ),
        },
        {
          value: "runs",
          label: counts.total > 0 ? `Runs (${counts.total})` : "Runs",
          content: (
            <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
              <InventoryCanvas fill className="min-h-0 flex-1 gap-0 space-y-0">
                <div className="flex min-h-0 flex-1 flex-col">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <WorkbenchAction
                      icon={<ListChecks aria-hidden />}
                      aria-pressed={multi.enabled}
                      kind={multi.enabled ? "secondary" : "ghost"}
                      size="compact"
                      type="button"
                      onClick={multi.toggleMode}
                    >
                      {multi.enabled ? "Done selecting" : "Select"}
                    </WorkbenchAction>
                    {multi.enabled && (
                      <>
                        <span className="text-label text-muted-foreground">
                          {multi.selected.size} selected
                        </span>
                        <WorkbenchAction
                          kind="secondary"
                          size="compact"
                          icon={<ListPlus aria-hidden />}
                          type="button"
                          disabled={multi.selected.size === 0 || !compareScope}
                          deniedReason={
                            compareScope ? null : "No served workspace to attribute these runs to."
                          }
                          onClick={addSelectedToCompare}
                        >
                          Add to selection
                        </WorkbenchAction>
                        <WorkbenchAction
                          kind="ghost"
                          size="compact"
                          icon={<X aria-hidden />}
                          type="button"
                          disabled={multi.selected.size === 0}
                          onClick={multi.clear}
                        >
                          Clear
                        </WorkbenchAction>
                      </>
                    )}
                  </div>
                  <div className="min-h-0 flex-1 overflow-auto">
                    {!runsComplete && runs.length === 0 ? (
                      <p className="text-label text-muted-foreground">Loading runs…</p>
                    ) : (
                      <DataTable
                        columns={tableColumns}
                        data={runs}
                        getRowKey={(run) => run.id}
                        getRowLabel={(run) =>
                          multi.enabled
                            ? `${multi.selected.has(run.id) ? "Deselect" : "Select"} run ${run.name || run.id}`
                            : `Open run ${run.name || run.id}`
                        }
                        onRowActivate={
                          multi.enabled
                            ? (run) =>
                                multi.selectAt(runIndex.get(run.id) ?? 0, {
                                  shift: false,
                                  meta: true,
                                })
                            : (run) => navigateToRun(run.id)
                        }
                        rowActions={runRowActions}
                        rowClassName={(run) =>
                          multi.enabled && multi.selected.has(run.id) ? "bg-accent/5" : ""
                        }
                        empty={
                          <EmptyState
                            title={EMPTY_COPY.runs.title}
                            description={EMPTY_COPY.runs.description}
                          />
                        }
                      />
                    )}
                  </div>
                </div>
              </InventoryCanvas>
            </OverviewSurface>
          ),
        },
        {
          value: "parameters",
          label:
            sweep.length + workbench.fixedAxes.length > 0
              ? `Parameters (${sweep.length + workbench.fixedAxes.length})`
              : "Parameters",
          content: (
            <OverviewSurface>
              <InventoryCanvas>
                {!runsComplete && runs.length === 0 ? (
                  <p className="text-label text-muted-foreground">Loading parameters…</p>
                ) : sweep.length === 0 && workbench.fixedAxes.length === 0 ? (
                  <EmptyState title="No parameters" />
                ) : (
                  <>
                    {sweep.length > 0 ? (
                      <div className="min-w-0">
                        <p className="mb-3 text-label text-muted-foreground">
                          <span className="tabular-nums text-foreground">{sweep.length}</span>{" "}
                          varying
                          {unrun > 0 ? (
                            <>
                              {" · "}
                              <span className="tabular-nums text-foreground">{unrun}</span> values
                              not run
                            </>
                          ) : null}
                        </p>
                        <SweepMatrix axes={sweep} />
                      </div>
                    ) : null}
                    <ConstantsNote
                      constants={workbench.fixedAxes.map((axis) => ({
                        key: axis.key,
                        value: axis.values[0] ?? "",
                      }))}
                    />
                  </>
                )}
              </InventoryCanvas>
            </OverviewSurface>
          ),
        },
        {
          value: "notebook",
          label: "Notebook",
          content: experiment ? (
            <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
              <ExperimentNotebook
                hostPath={experiment.path}
                runs={snapshot.runs}
                onOpen={setSelection}
              />
            </OverviewSurface>
          ) : null,
        },
      ]}
    />
  );
};
