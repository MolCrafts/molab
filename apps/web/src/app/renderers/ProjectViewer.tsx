import {
  Archive,
  Copy,
  ExternalLink,
  FlaskConical,
  FolderKanban,
  Play,
  Workflow,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
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
  OverviewHighlight,
  OverviewSurface,
  StatusDistribution,
  StatusDonut,
} from "@/app/components/entity";
import { statusDonutSegments, successRate } from "@/app/renderers/dashboardData";
import {
  buildProjectWorkbenchData,
  experimentRunCompleteness,
  projectSnapshotCompleteness,
} from "@/app/renderers/entityWorkbenchData";
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
  const [projectAssets, setProjectAssets] = useState<ApiAssetResponse[]>([]);
  const [projectAssetsLoading, setProjectAssetsLoading] = useState(true);
  const [projectAssetsError, setProjectAssetsError] = useState<string | null>(null);
  const [settledProjectAssetsId, setSettledProjectAssetsId] = useState<string | null>(null);
  const [projectAssetsRequestVersion, setProjectAssetsRequestVersion] = useState(0);
  const [createRunExperimentId, setCreateRunExperimentId] = useState<string | null>(null);
  const { setSelection } = useNavigationState(snapshot);

  const projectId = selection.objectId;
  const project = snapshot.projects.find((p) => p.id === projectId);
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

  useEffect(() => {
    void projectAssetsRequestVersion;
    if (!projectId) {
      setProjectAssets([]);
      setProjectAssetsLoading(false);
      setProjectAssetsError(null);
      setSettledProjectAssetsId(null);
      return;
    }

    let cancelled = false;
    setProjectAssets([]);
    setProjectAssetsLoading(true);
    setProjectAssetsError(null);
    projectsApi
      .listProjectAssets(projectId)
      .then((assets) => {
        if (!cancelled) setProjectAssets(assets);
      })
      .catch((err) => {
        if (!cancelled) {
          setProjectAssetsError(
            err instanceof Error ? err.message : "Failed to load project assets",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setProjectAssetsLoading(false);
          setSettledProjectAssetsId(projectId);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, projectAssetsRequestVersion]);

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
  const projectAssetsPending = projectAssetsLoading || settledProjectAssetsId !== projectId;

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
            <FlaskConical className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-body-lg font-medium text-foreground">{exp.name}</div>
            <div className="flex items-center gap-0.5 font-mono text-micro text-muted-foreground">
              <span className="truncate">{exp.id.substring(0, 12)}</span>
              <CopyButton value={exp.id} label="experiment ID" className="size-5" />
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
            <Workflow className="h-3.5 w-3.5" />
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
          <Play className="h-4 w-4 text-muted-foreground hover:text-foreground" />
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
          <Archive className="h-4 w-4 text-muted-foreground" />
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

  // Overview only claims status posture when every child run is loaded. Shallow
  // list counts remain useful, but partial snapshots must never look complete.
  const overviewWithNav = (
    <OverviewSurface>
      <DashboardCanvas>
        {completeness.experimentsComplete && completeness.experimentCount === 0 ? (
          <EmptyState
            title={EMPTY_COPY.experiments.title}
            description={EMPTY_COPY.experiments.description}
            icon={<FlaskConical className="size-5" aria-hidden />}
          />
        ) : (
          <section className="grid gap-10 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-center">
            {completeness.runsComplete && workbench.counts.total > 0 ? (
              <StatusDonut
                segments={donutSegments}
                size={148}
                thickness={16}
                centerValue={workbench.counts.total}
                centerLabel="runs"
              />
            ) : completeness.runsComplete ? (
              <div className="flex size-36 items-center justify-center rounded-full border border-dashed border-border text-micro text-muted-foreground">
                no runs
              </div>
            ) : (
              <div className="flex size-36 items-center justify-center rounded-full border border-dashed border-border px-5 text-center text-micro leading-relaxed text-muted-foreground">
                Run status appears after all experiment runs load
              </div>
            )}
            <div className="grid gap-6 sm:grid-cols-3">
              <OverviewHighlight
                label="Experiments"
                value={experimentCountValue}
                detail={
                  completeness.experimentCount === null
                    ? "loaded so far"
                    : completeness.experimentsComplete
                      ? undefined
                      : `${projectExperiments.length} loaded`
                }
              />
              <OverviewHighlight
                label="Runs"
                value={runCountValue}
                detail={
                  completeness.runsComplete && projectSuccessRate !== null
                    ? `${projectSuccessRate.toFixed(0)}% succeeded`
                    : completeness.runCount === null
                      ? "loaded so far"
                      : `${projectRuns.length} loaded; status incomplete`
                }
              />
              <OverviewHighlight
                label="Assets"
                value={projectAssetsPending ? "…" : projectAssetsError ? "!" : projectAssets.length}
              />
            </div>
          </section>
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
                        action={
                          <WorkbenchRetryAction
                            onClick={() => {
                              setProjectAssetsLoading(true);
                              setProjectAssetsRequestVersion((version) => version + 1);
                            }}
                          />
                        }
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
                        <p className="mt-0.5 text-micro text-muted-foreground">
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
