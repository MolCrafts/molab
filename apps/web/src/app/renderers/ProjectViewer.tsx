import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Copy,
  ExternalLink,
  FlaskConical,
  FolderKanban,
  Play,
  Workflow,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { experimentsApi, projectsApi } from "@/api";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import type { DataTableColumn, DataTableRowAction } from "@/app/components/entity";
import {
  CopyButton,
  DashboardCanvas,
  DataTable,
  EMPTY_COPY,
  EmptyState,
  EntityPage,
  InventoryCanvas,
  OverviewSurface,
  StatusBreakdown,
  StatusDistribution,
  StatusDonut,
  StatusLegend,
} from "@/app/components/entity";
import { statusDonutSegments, successRate } from "@/app/renderers/dashboardData";
import {
  buildProjectWorkbenchData,
  experimentRunCompleteness,
  projectSnapshotCompleteness,
} from "@/app/renderers/entityWorkbenchData";
import { projectAssetsQueryOptions } from "@/app/state/entityQueries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type {
  ApiAssetResponse,
  ExperimentSummary,
  ProjectView,
  ScopedRendererProps,
} from "@/app/types";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";

type ProjectRendererProps = ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "assets"
>;

export const ProjectViewer = ({
  selection,
  snapshot,
  onRefresh,
}: ProjectRendererProps): JSX.Element => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingExperimentId, setDeletingExperimentId] = useState<string | null>(null);
  const [experimentDeleteError, setExperimentDeleteError] = useState<{
    experiment: ExperimentSummary;
    message: string;
  } | null>(null);
  const [createRunExperimentId, setCreateRunExperimentId] = useState<string | null>(null);
  const { setSelection } = useNavigationState(snapshot);

  const projectId = selection.objectId;
  const project = snapshot.projects.find((p) => p.id === projectId);
  const assetsQuery = useQuery({
    ...projectAssetsQueryOptions(projectId),
    enabled: Boolean(projectId),
  });
  const projectAssets = assetsQuery.data ?? [];
  const projectAssetsPending = assetsQuery.isPending;
  const projectAssetsError = assetsQuery.error
    ? assetsQuery.error instanceof Error
      ? assetsQuery.error.message
      : "Failed to load project assets"
    : null;
  const activeTab: ProjectView =
    selection.objectType === "project" ? (selection.projectView ?? "overview") : "overview";
  const setProjectTab = useCallback(
    (value: string): void => {
      const projectView: ProjectView =
        value === "experiments" || value === "assets" || value === "settings" ? value : "overview";
      setSelection({ objectType: "project", objectId: projectId, projectView });
    },
    [projectId, setSelection],
  );

  const projectExperiments = useMemo(
    () => snapshot.experiments.filter((e) => e.projectId === projectId),
    [snapshot.experiments, projectId],
  );

  const projectRuns = useMemo(
    () => snapshot.runs.filter((r) => r.projectId === projectId),
    [snapshot.runs, projectId],
  );

  const workbench = useMemo(
    () => buildProjectWorkbenchData(projectId, snapshot, projectAssets),
    [projectId, snapshot, projectAssets],
  );

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete project "${projectId}"?`)) {
      return;
    }
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await projectsApi.deleteProject(projectId);
      onRefresh();
      setSelection(null);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "Failed to delete project");
    } finally {
      setIsDeleting(false);
    }
  };

  const navigateToExperiment = (experimentId: string) => {
    setSelection({
      objectType: "experiment",
      objectId: experimentId,
    });
  };

  const handleDeleteExperiment = async (experiment: ExperimentSummary) => {
    if (!confirm(`Are you sure you want to delete experiment "${experiment.id}"?`)) {
      return;
    }
    setDeletingExperimentId(experiment.id);
    setExperimentDeleteError(null);
    try {
      await experimentsApi.deleteExperiment(experiment.projectId, experiment.id);
      onRefresh();
    } catch (error) {
      setExperimentDeleteError({
        experiment,
        message: error instanceof Error ? error.message : "Failed to delete experiment",
      });
    } finally {
      setDeletingExperimentId(null);
    }
  };

  const copyToClipboard = (text: string) => {
    void navigator.clipboard.writeText(text);
  };

  const experimentRowActions = (
    exp: ExperimentSummary,
  ): DataTableRowAction<ExperimentSummary>[] => {
    const workflow = snapshot.workflows.find((item) => item.experimentId === exp.id);
    return [
      {
        id: "open",
        label: "Open experiment",
        icon: ExternalLink,
        onSelect: () => navigateToExperiment(exp.id),
      },
      {
        id: "new-run",
        label: "New run",
        icon: Play,
        onSelect: () => setCreateRunExperimentId(exp.id),
      },
      {
        id: "open-workflow",
        label: "Open workflow",
        icon: Workflow,
        disabled: !workflow,
        title: workflow ? undefined : "No workflow is configured for this experiment.",
        onSelect: () => {
          if (workflow) {
            setSelection({
              objectType: "experiment",
              objectId: exp.id,
              experimentView: "workflow",
            });
          }
        },
      },
      {
        id: "copy-id",
        label: "Copy experiment ID",
        icon: Copy,
        onSelect: () => copyToClipboard(exp.id),
      },
      {
        id: "delete",
        label: "Delete experiment",
        disabled: deletingExperimentId === exp.id,
        title: deletingExperimentId === exp.id ? "This experiment is being deleted." : undefined,
        destructive: true,
        separatorBefore: true,
        onSelect: (experiment) => {
          void handleDeleteExperiment(experiment);
        },
      },
    ];
  };

  const assetRowActions = (asset: ApiAssetResponse): DataTableRowAction<ApiAssetResponse>[] => [
    {
      id: "open",
      label: "Open asset",
      icon: ExternalLink,
      onSelect: () => setSelection({ objectType: "asset", objectId: asset.id }),
    },
    {
      id: "copy-id",
      label: "Copy asset ID",
      icon: Copy,
      onSelect: () => copyToClipboard(asset.id),
    },
  ];

  if (!project) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Project not found"
        detail="The current workspace snapshot no longer contains this project."
      />
    );
  }

  const completeness = projectSnapshotCompleteness(project, projectExperiments, projectRuns);

  const experimentColumns: DataTableColumn<ExperimentSummary>[] = [
    {
      key: "name",
      header: "Experiment",
      cell: (exp) => (
        <div className="flex items-center gap-3">
          <div className="flex h-control-compact w-control-compact items-center justify-center text-muted-foreground">
            <FlaskConical className="size-icon-sm" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-body-lg font-medium text-foreground">{exp.name}</div>
            <div className="flex items-center gap-hairline font-mono text-micro text-muted-foreground">
              <span className="truncate">{exp.id.substring(0, 12)}</span>
              <CopyButton value={exp.id} label="experiment ID" className="size-4-lg" />
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "runs",
      header: "Runs",
      width: "w-56",
      cell: (exp) => {
        const rollup = workbench.experiments.find((item) => item.experiment.id === exp.id);
        const loadedRunCount = rollup?.counts.total ?? 0;
        const { runCount, runsComplete } = experimentRunCompleteness(exp, loadedRunCount);
        if (runsComplete && runCount === 0) {
          return <span className="text-label text-muted-foreground">No runs</span>;
        }
        if (!runsComplete) {
          return (
            <div className="flex items-baseline gap-2">
              <span className="font-medium tabular-nums text-foreground">
                {runCount ?? (loadedRunCount > 0 ? `≥${loadedRunCount}` : "—")}
              </span>
              <span className="text-micro text-muted-foreground">
                {runCount === null ? "loaded so far" : "status loads on open"}
              </span>
            </div>
          );
        }
        return (
          <div className="flex items-center gap-3">
            <span className="w-control-compact font-medium tabular-nums text-foreground">
              {runCount}
            </span>
            <div className="min-w-32 flex-1">
              {rollup && <StatusDistribution counts={rollup.counts} legend={false} />}
            </div>
          </div>
        );
      },
    },
    {
      key: "workflow",
      header: "Tasks",
      width: "w-24",
      cell: (exp) => {
        const rollup = workbench.experiments.find((item) => item.experiment.id === exp.id);
        return (
          <span className="inline-flex items-center gap-2 text-label tabular-nums text-muted-foreground">
            <Workflow className="size-icon-sm" />
            {rollup?.workflowSummary.exists ? rollup.workflowSummary.taskCount : "—"}
          </span>
        );
      },
    },
    {
      key: "updated",
      header: "Updated",
      width: "w-40",
      cell: (exp) => (
        <span className="text-label text-muted-foreground" title={exp.updatedAt}>
          {formatDateTime(exp.updatedAt)}
        </span>
      ),
    },
    {
      key: "action",
      header: "",
      width: "w-14",
      align: "right",
      cell: (exp) => (
        <WorkbenchIconAction
          label={`New run in ${exp.name}`}
          kind="ghost"
          size="default"
          className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
          onClick={(event) => {
            event.stopPropagation();
            setCreateRunExperimentId(exp.id);
          }}
        >
          <Play className="size-icon text-muted-foreground hover:text-foreground" />
        </WorkbenchIconAction>
      ),
    },
  ];

  const assetColumns: DataTableColumn<ApiAssetResponse>[] = [
    {
      key: "name",
      header: "Name",
      cell: (asset) => (
        <div className="flex items-center gap-2 text-body-lg font-medium text-foreground">
          <Archive className="size-icon text-muted-foreground" />
          {asset.name}
        </div>
      ),
    },
    {
      key: "kind",
      header: "Kind",
      width: "w-36",
      cell: (asset) => <span className="text-muted-foreground">{asset.kind}</span>,
    },
    {
      key: "scope",
      header: "Scope",
      width: "w-40",
      cell: (asset) => (
        <span className="font-mono text-label text-muted-foreground">
          {asset.scopeKind}
          {asset.scopeIds.length > 0 ? ` · ${asset.scopeIds.join("/")}` : ""}
        </span>
      ),
    },
    {
      key: "size",
      header: "Size",
      width: "w-32",
      cell: (asset) => {
        const size = (asset.extra as Record<string, unknown> | undefined)?.size;
        return (
          <span className="font-mono text-label">
            {typeof size === "number" ? `${size} B` : "—"}
          </span>
        );
      },
    },
    {
      key: "updated",
      header: "Updated",
      width: "w-44",
      cell: (asset) => (
        <span className="text-muted-foreground" title={asset.updatedAt}>
          {formatDateTime(asset.updatedAt)}
        </span>
      ),
    },
  ];

  const createRunExperiment = createRunExperimentId
    ? snapshot.experiments.find((experiment) => experiment.id === createRunExperimentId)
    : null;
  const projectSuccessRate = successRate(workbench.counts);
  const donutSegments = statusDonutSegments(workbench.counts);
  const experimentCountValue =
    completeness.experimentCount ??
    (projectExperiments.length > 0 ? `≥${projectExperiments.length}` : "—");
  const runCountValue =
    completeness.runCount ?? (projectRuns.length > 0 ? `≥${projectRuns.length}` : "—");

  // The fold answers "which experiment needs me": one status mix per experiment,
  // read as shape. The Experiments tab keeps the full inventory and row actions.
  // Status posture is only claimed once every child run is loaded — a partial
  // snapshot must never look complete.
  const experimentGroups = workbench.experiments.map((rollup) => ({
    id: rollup.experiment.id,
    label: rollup.experiment.name,
    detail: [
      rollup.workflowSummary.exists ? `${rollup.workflowSummary.taskCount} tasks` : "no workflow",
      rollup.experiment.updatedAt ? formatDateTime(rollup.experiment.updatedAt) : null,
    ]
      .filter(Boolean)
      .join(" · "),
    counts: rollup.counts,
    onSelect: () => navigateToExperiment(rollup.experiment.id),
  }));

  const overviewWithNav = (
    <OverviewSurface>
      <DashboardCanvas className="max-w-6xl space-y-8">
        {completeness.experimentsComplete && completeness.experimentCount === 0 ? (
          <EmptyState
            title={EMPTY_COPY.experiments.title}
            description={EMPTY_COPY.experiments.description}
            icon={<FlaskConical className="size-icon-lg" aria-hidden />}
          />
        ) : (
          <>
            <section className="grid gap-8 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-start">
              {completeness.runsComplete && workbench.counts.total > 0 ? (
                <StatusDonut
                  segments={donutSegments}
                  size={148}
                  thickness={16}
                  centerValue={workbench.counts.total}
                  centerLabel="runs"
                />
              ) : (
                <div className="flex size-36 items-center justify-center rounded-full border border-dashed border-border px-4 text-center text-micro leading-relaxed text-muted-foreground">
                  {completeness.runsComplete
                    ? "no runs"
                    : "Run status appears after all experiment runs load"}
                </div>
              )}
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="text-body-lg font-medium text-foreground">Experiments</h2>
                  <StatusLegend />
                </div>
                {experimentGroups.length > 0 ? (
                  <StatusBreakdown groups={experimentGroups} />
                ) : (
                  <p className="text-micro text-muted-foreground">Loading experiments…</p>
                )}
                {completeness.runsComplete && projectSuccessRate !== null && (
                  <p className="font-mono text-micro tabular-nums text-muted-foreground">
                    {projectSuccessRate.toFixed(0)}% of terminal runs succeeded
                  </p>
                )}
              </div>
            </section>

            <section className="space-y-2 border-t border-border pt-6">
              <h2 className="text-label font-medium text-foreground">Assets</h2>
              {projectAssetsError ? (
                <WorkbenchOperationState
                  kind="error"
                  density="compact"
                  title="Could not load project assets"
                  detail={projectAssetsError}
                  action={<WorkbenchRetryAction onClick={() => void assetsQuery.refetch()} />}
                />
              ) : (
                <p className="font-mono text-micro tabular-nums text-muted-foreground">
                  {projectAssetsPending ? "loading…" : `${projectAssets.length} registered`}
                </p>
              )}
            </section>
          </>
        )}
      </DashboardCanvas>
    </OverviewSurface>
  );

  return (
    <>
      <EntityPage
        icon={FolderKanban}
        title={project.name}
        actions={<CopyButton value={project.id} label="project ID" />}
        activeTab={activeTab}
        onActiveTabChange={setProjectTab}
        tabs={[
          {
            value: "overview",
            label: "Overview",
            content: overviewWithNav,
          },
          {
            value: "experiments",
            label:
              (completeness.experimentCount ?? projectExperiments.length) > 0
                ? `Experiments (${completeness.experimentCount ?? projectExperiments.length})`
                : "Experiments",
            content: (
              <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
                <InventoryCanvas fill className="min-h-0 flex-1">
                  <div
                    className="flex min-h-0 flex-1 flex-col"
                    aria-busy={deletingExperimentId !== null}
                  >
                    {deletingExperimentId && (
                      <WorkbenchOperationState
                        kind="running"
                        density="compact"
                        title="Deleting experiment…"
                        detail={deletingExperimentId}
                      />
                    )}
                    {experimentDeleteError && (
                      <WorkbenchOperationState
                        kind="error"
                        density="compact"
                        title="Could not delete experiment"
                        detail={experimentDeleteError.message}
                        action={
                          <WorkbenchRetryAction
                            onClick={() =>
                              void handleDeleteExperiment(experimentDeleteError.experiment)
                            }
                          />
                        }
                      />
                    )}
                    <div className="min-h-0 flex-1 overflow-auto">
                      <DataTable
                        columns={experimentColumns}
                        data={projectExperiments}
                        getRowKey={(exp) => exp.id}
                        getRowLabel={(exp) => `Open experiment ${exp.name}`}
                        onRowActivate={(exp) => navigateToExperiment(exp.id)}
                        rowActions={experimentRowActions}
                        empty={
                          <EmptyState
                            title={EMPTY_COPY.experiments.title}
                            description={EMPTY_COPY.experiments.description}
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
            value: "assets",
            label: "Assets",
            content: (
              <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
                <InventoryCanvas fill className="min-h-0 flex-1">
                  <div className="flex min-h-0 flex-1 flex-col">
                    {projectAssetsPending ? (
                      <WorkbenchOperationState
                        kind="loading"
                        title="Loading project assets…"
                        skeletonRows={5}
                      />
                    ) : projectAssetsError ? (
                      <WorkbenchOperationState
                        kind="error"
                        title="Could not load project assets"
                        detail={projectAssetsError}
                        action={<WorkbenchRetryAction onClick={() => void assetsQuery.refetch()} />}
                      />
                    ) : (
                      <div className="min-h-0 flex-1 overflow-auto">
                        <DataTable
                          columns={assetColumns}
                          data={projectAssets}
                          getRowKey={(asset) => asset.id}
                          getRowLabel={(asset) => `Open asset ${asset.name}`}
                          onRowActivate={(asset) =>
                            setSelection({ objectType: "asset", objectId: asset.id })
                          }
                          rowActions={assetRowActions}
                          empty={<EmptyState title={EMPTY_COPY.assets.title} />}
                        />
                      </div>
                    )}
                  </div>
                </InventoryCanvas>
              </OverviewSurface>
            ),
          },
          {
            value: "settings",
            label: "Settings",
            content: (
              <OverviewSurface>
                <DashboardCanvas className="max-w-3xl space-y-8">
                  <section className="space-y-3">
                    <h3 className="text-body-lg font-medium text-foreground">Project</h3>
                    <Table>
                      <TableBody>
                        <TableRow>
                          <TableCell className="w-36 text-label text-muted-foreground">
                            Name
                          </TableCell>
                          <TableCell className="text-label text-foreground">
                            {project.name}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="text-label text-muted-foreground">ID</TableCell>
                          <TableCell className="font-mono text-label text-foreground">
                            {project.id}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell className="text-label text-muted-foreground">
                            Contents
                          </TableCell>
                          <TableCell className="font-mono text-label text-muted-foreground">
                            {experimentCountValue} experiments · {runCountValue} runs
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </section>

                  <section className="space-y-3">
                    <h3 className="text-body-lg font-medium text-foreground">Lifecycle</h3>
                    <div className="flex flex-wrap items-center justify-between gap-4 rounded-panel border border-border px-4 py-3">
                      <div className="min-w-0">
                        <p className="text-body text-foreground">Delete project</p>
                        <p className="mt-1 text-micro text-muted-foreground">
                          Removes project, experiments, and runs. Cannot be undone from the UI.
                        </p>
                      </div>
                      <WorkbenchAction
                        kind="danger"
                        size="compact"
                        onClick={handleDelete}
                        disabled={isDeleting}
                        aria-busy={isDeleting}
                      >
                        {isDeleting ? "Deleting…" : "Delete project"}
                      </WorkbenchAction>
                    </div>
                    {isDeleting && (
                      <WorkbenchOperationState
                        kind="running"
                        density="compact"
                        title="Deleting project…"
                        detail={projectId}
                      />
                    )}
                    {deleteError && (
                      <WorkbenchOperationState
                        kind="error"
                        density="compact"
                        title="Could not delete project"
                        detail={deleteError}
                        action={<WorkbenchRetryAction onClick={() => void handleDelete()} />}
                      />
                    )}
                  </section>
                </DashboardCanvas>
              </OverviewSurface>
            ),
          },
        ]}
      />
      {createRunExperiment && (
        <CreateRunDialog
          projectId={createRunExperiment.projectId}
          experimentId={createRunExperiment.id}
          workflowFile={createRunExperiment.workflowFile || ""}
          open
          trigger={null}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setCreateRunExperimentId(null);
          }}
          onRunCreated={(runId) => {
            onRefresh();
            setCreateRunExperimentId(null);
            setSelection({ objectType: "run", objectId: runId });
          }}
        />
      )}
    </>
  );
};
