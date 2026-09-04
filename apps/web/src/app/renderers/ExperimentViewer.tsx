import {
  Bot,
  Check,
  Copy,
  FileQuestion,
  FlaskConical,
  Grid3x3,
  MoreHorizontal,
  Trash2,
} from "lucide-react";
import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { experimentsApi } from "@/api";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import { CreateSweepDialog } from "@/app/components/CreateSweepDialog";
import type { DataTableColumn, DataTableRowAction } from "@/app/components/entity";
import {
  CopyButton,
  DashboardCanvas,
  DataTable,
  EMPTY_COPY,
  EmptyState,
  EntityPage,
  InventoryCanvas,
  OverviewHighlight,
  OverviewSurface,
  ParamChip,
  StatusDonut,
  StatusIcon,
} from "@/app/components/entity";
import {
  countRunStatuses,
  formatDuration,
  formatScalar,
  statusDonutSegments,
  successRate,
} from "@/app/renderers/dashboardData";
import { ExperimentCompare } from "@/app/renderers/ExperimentCompare";
import { buildExperimentWorkbenchData } from "@/app/renderers/entityWorkbenchData";
import {
  buildRunListActions,
  type RunListHandlers,
} from "@/app/runs/runListActions";
import { useRunMultiSelect } from "@/app/runs/useRunMultiSelect";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { ExperimentView, RunSummary, ScopedRendererProps } from "@/app/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { parseWorkflowIr } from "@/components/workflow/workflow-graph";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { formatDateTime } from "@/lib/datetime";
import { getWorkspaceFs } from "@/lib/workspace-fs";
import { formatQualifiedPath, runWorkspaceRelativePath } from "@/lib/workspace-path";
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
  const visible = entries.slice(0, 3);
  return (
    <div className="flex max-w-80 flex-wrap items-center gap-1">
      {visible.map(([key, value]) => (
        <ParamChip key={key} name={key} value={formatScalar(value)} />
      ))}
      {entries.length > visible.length && (
        <Popover>
          <PopoverTrigger asChild>
            <WorkbenchAction kind="ghost" size="compact" className="h-6 px-2 text-micro">
              +{entries.length - visible.length}
            </WorkbenchAction>
          </PopoverTrigger>
          <PopoverContent side="bottom" align="start" className="max-h-80 w-72 overflow-auto p-3">
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
        className="size-5"
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
}: ScopedRendererProps<"experiments" | "runs" | "workflows" | "workspaces">): JSX.Element => {
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
        value === "workflow" || value === "runs" || value === "compare" ? value : "overview";
      setSelection({ objectType: "experiment", objectId: experimentId, experimentView });
    },
    [experimentId, setSelection],
  );

  const runs = useMemo(
    () => snapshot.runs.filter((r) => r.experimentId === experimentId),
    [snapshot.runs, experimentId],
  );

  const counts = useMemo(() => countRunStatuses(runs), [runs]);

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

  const handleDelete = async () => {
    if (!projectId) return;
    if (!window.confirm(`Delete “${experimentId}”?`)) {
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
        <div className="min-w-0">
          <div className="truncate text-body-lg font-medium text-foreground">
            {run.name || run.id}
          </div>
          <div className="flex items-center gap-0.5 font-mono text-micro text-muted-foreground">
            <span className="truncate">{run.id.substring(0, 12)}</span>
            <CopyButton value={run.id} label="run ID" className="size-5" />
          </div>
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
      width: "w-90",
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
        <span className="font-mono text-label text-muted-foreground">
          {run.statusSummary.total} total · {run.statusSummary.active} active
        </span>
      ),
    },
    {
      key: "duration",
      header: "Duration",
      width: "w-24",
      cell: (run) => {
        const d = formatDuration(run.startedAt, run.finishedAt);
        return (
          <span className="font-mono text-label text-muted-foreground">
            {d ?? <span className="text-muted-foreground">—</span>}
          </span>
        );
      },
    },
    {
      key: "updated",
      header: "Updated",
      width: "w-40",
      cell: (run) => (
        <span className="text-label text-muted-foreground" title={run.updatedAt}>
          {formatDateTime(run.updatedAt)}
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
          className={`flex h-4 w-4 items-center justify-center rounded-control border transition-colors ${
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
  const experimentSuccessRate = successRate(counts);
  const donutSegments = statusDonutSegments(counts);

  const paramAxes = [...workbench.varyingAxes, ...workbench.fixedAxes];
  const latestRun =
    runs.length === 0
      ? null
      : [...runs].sort(
          (a, b) =>
            Date.parse(b.updatedAt || b.finishedAt || b.startedAt || "0") -
            Date.parse(a.updatedAt || a.finishedAt || a.startedAt || "0"),
        )[0];
  const completedDurationMs = runs.flatMap((run) => {
    if (!run.startedAt || !run.finishedAt) return [];
    const ms = Date.parse(run.finishedAt) - Date.parse(run.startedAt);
    return Number.isFinite(ms) && ms >= 0 ? [ms] : [];
  });
  const medianDurationLabel = (() => {
    if (completedDurationMs.length === 0) return null;
    const sorted = [...completedDurationMs].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const left = sorted[mid - 1];
    const right = sorted[mid];
    if (right === undefined) return null;
    const ms = sorted.length % 2 === 0 && left !== undefined ? (left + right) / 2 : right;
    // formatDuration expects two ISO instants — anchor at epoch for a pure delta.
    return formatDuration(new Date(0).toISOString(), new Date(ms).toISOString());
  })();

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

  const workflowLabel =
    workflow?.name ||
    (experiment.workflowFile && !experiment.workflowFile.trim().startsWith("{")
      ? experiment.workflowFile
      : null) ||
    "Workflow";

  // Always pass full tab bodies (EntityTabContent hides inactive with CSS).
  // Conditional `activeTab === … ? content : null` remounted Flowgram on every switch.
  const overviewContent = (
    <OverviewSurface>
      <DashboardCanvas className="max-w-6xl space-y-10">
        <section className="grid gap-10 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-center">
          {counts.total > 0 ? (
            <StatusDonut
              segments={donutSegments}
              size={148}
              thickness={16}
              centerValue={counts.total}
              centerLabel="runs"
            />
          ) : (
            <div className="flex size-36 items-center justify-center rounded-full border border-dashed border-border text-micro text-muted-foreground">
              no runs
            </div>
          )}
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
            <OverviewHighlight
              label="Succeeded"
              value={counts.succeeded}
              detail={
                experimentSuccessRate === null
                  ? undefined
                  : `${experimentSuccessRate.toFixed(0)}% of terminal`
              }
            />
            <OverviewHighlight label="Failed" value={counts.failed} />
            <OverviewHighlight
              label="In flight"
              value={counts.running + counts.pending}
              detail={
                counts.running + counts.pending > 0
                  ? `${counts.running} running · ${counts.pending} queued`
                  : undefined
              }
            />
            <OverviewHighlight
              label="Median duration"
              value={medianDurationLabel ?? "—"}
              detail={
                completedDurationMs.length > 0
                  ? `${completedDurationMs.length} finished runs`
                  : undefined
              }
            />
            <OverviewHighlight
              label="Latest run"
              value={latestRun ? latestRun.name || latestRun.id.slice(0, 10) : "—"}
              detail={
                latestRun
                  ? `${latestRun.status} · ${formatDateTime(latestRun.updatedAt)}`
                  : undefined
              }
            />
          </div>
        </section>

        {paramAxes.length > 0 && (
          <section className="space-y-3">
            <h3 className="text-body-lg font-medium text-foreground">Parameters</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-40">Name</TableHead>
                  <TableHead>Values</TableHead>
                  <TableHead className="w-24">Role</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paramAxes.map((axis) => {
                  const varying = axis.count > 1;
                  return (
                    <TableRow key={axis.key}>
                      <TableCell className="font-mono text-label">{axis.key}</TableCell>
                      <TableCell className="font-mono text-label text-muted-foreground">
                        {axis.values.slice(0, 12).join(", ")}
                        {axis.values.length > 12 ? ` +${axis.values.length - 12}` : ""}
                      </TableCell>
                      <TableCell className="text-micro text-muted-foreground">
                        {varying ? "varying" : "fixed"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </section>
        )}

        {hasWorkflowData && (
          <section className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-6">
            <div className="min-w-0">
              <h3 className="text-body-lg font-medium text-foreground">Workflow</h3>
              <p className="mt-1 truncate font-mono text-micro text-muted-foreground">
                {workflowLabel}
              </p>
              <p className="mt-1 text-label text-muted-foreground">
                {workbench.workflowSummary.taskCount} tasks · {workbench.workflowSummary.linkCount}{" "}
                dependencies
              </p>
            </div>
            <WorkbenchAction
              kind="secondary"
              size="compact"
              onClick={() => setEntityTab("workflow")}
            >
              Open workflow
            </WorkbenchAction>
          </section>
        )}
      </DashboardCanvas>
    </OverviewSurface>
  );

  return (
    <>
      <EntityPage
        icon={FlaskConical}
        title={experiment.name}
        actions={
          <>
            <CreateRunDialog
              projectId={projectId}
              experimentId={experimentId}
              workflowFile={experiment.workflowFile || ""}
              onRunCreated={(runId) => {
                onRefresh();
                navigateToRun(runId);
              }}
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <WorkbenchIconAction label="More">
                  <MoreHorizontal className="h-4 w-4" />
                </WorkbenchIconAction>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem onClick={() => setSweepOpen(true)}>
                  <Grid3x3 className="h-3.5 w-3.5" />
                  Sweep
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() =>
                    setSelection({
                      objectType: "agent",
                      objectId: "new",
                      scope: { projectId, experimentId },
                    })
                  }
                >
                  <Bot className="h-3.5 w-3.5" />
                  Agent
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    void navigator.clipboard.writeText(experiment.id);
                    toast.success("Copied");
                  }}
                >
                  <Copy className="h-3.5 w-3.5" />
                  Copy ID
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={isDeleting}
                  className="text-destructive focus:text-destructive"
                  onClick={() => void handleDelete()}
                >
                  <Trash2 className="h-3.5 w-3.5" />
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
                            kind="ghost"
                            size="compact"
                            type="button"
                            disabled={multi.selected.size === 0}
                            onClick={() => setEntityTab("compare")}
                          >
                            Compare
                          </WorkbenchAction>
                          <WorkbenchAction
                            kind="ghost"
                            size="compact"
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
                    </div>
                  </div>
                </InventoryCanvas>
              </OverviewSurface>
            ),
          },
          {
            value: "compare",
            label: "Compare",
            content: (
              <OverviewSurface>
                <InventoryCanvas>
                  <ExperimentCompare runs={runs} onOpenRun={navigateToRun} />
                </InventoryCanvas>
              </OverviewSurface>
            ),
          },
        ]}
      />
    </>
  );
};
