import { Table, TableBody, TableCell, TableRow } from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Copy,
  ExternalLink,
  FlaskConical,
  FolderKanban,
  Play,
  Trash2,
  Workflow,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { experimentsApi, projectsApi } from "@/api";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import type { DataTableColumn, DataTableRowAction } from "@/app/components/entity";
import {
  DashboardCanvas,
  DashboardCard,
  DataTable,
  EMPTY_COPY,
  EmptyState,
  EntityPage,
  InventoryCanvas,
  OverviewSurface,
  StatusDistribution,
} from "@/app/components/entity";
import {
  attentionRuns,
  NeedsAttention,
  RunTimeline,
  rollupExecutions,
} from "@/app/dashboard/dashboardWidgets";
import { ExecutionOverview } from "@/app/dashboard/ExecutionOverview";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import {
  buildProjectWorkbenchData,
  experimentRunCompleteness,
  projectSnapshotCompleteness,
} from "@/app/renderers/entityWorkbenchData";
import { experimentWorkflowLabel } from "@/app/state/api";
import { projectAssetsQueryOptions } from "@/app/state/entityQueries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type {
  ApiAssetResponse,
  ExperimentSummary,
  ProjectView,
  ScopedRendererProps,
} from "@/app/types";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";

type ProjectRendererProps = ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "assets" | "workspaces"
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
  const requestedView: ProjectView =
    selection.objectType === "project" ? (selection.projectView ?? "overview") : "overview";
  const activeTab: ProjectView = requestedView;
  const assetsQuery = useQuery({
    ...projectAssetsQueryOptions(projectId),
    enabled: Boolean(projectId) && activeTab === "assets",
  });
  const { query: overviewRuns, rows: overviewRows } = useScopeRuns(
    { projectId },
    Boolean(projectId) &&
      (activeTab === "overview" || activeTab === "attention" || activeTab === "timeline"),
  );
  const needsAuth = activeNeedsAuth(snapshot.workspaces);
  const projectAssets = assetsQuery.data ?? [];
  const projectAssetsPending =
    assetsQuery.isPending || (needsAuth && assetsQuery.data === undefined);
  const projectAssetsError = shouldShowFailure(assetsQuery.error, {
    fetching: assetsQuery.isFetching,
    needsAuth,
  })
    ? assetsQuery.error instanceof Error
      ? assetsQuery.error.message
      : "Failed to load project assets"
    : null;
  const setProjectTab = useCallback(
    (value: string): void => {
      const projectView: ProjectView =
        value === "experiments" ||
        value === "attention" ||
        value === "timeline" ||
        value === "assets" ||
        value === "settings"
          ? value
          : "overview";
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
    if (!confirm(`Are you sure you want to delete project "${project?.name ?? "this project"}"?`)) {
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
    if (!confirm(`Are you sure you want to delete experiment "${experiment.name}"?`)) {
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
      header: "Name",
      cell: (exp) => (
        <div className="flex min-w-0 items-center gap-2" title={exp.name}>
          <FlaskConical className="size-icon-sm shrink-0 text-muted-foreground" />
          <span className="truncate text-body font-medium text-foreground">{exp.name}</span>
        </div>
      ),
    },
    {
      key: "runs",
      header: "Runs",
      width: "w-40",
      cell: (exp) => {
        const rollup = workbench.experiments.find((item) => item.experiment.id === exp.id);
        const loadedRunCount = rollup?.counts.total ?? 0;
        const { runCount, runsComplete } = experimentRunCompleteness(exp, loadedRunCount);
        if (!runsComplete || runCount === 0) {
          return (
            <span
              className="tabular-nums text-foreground"
              title={runCount === null ? "Loaded runs; total unknown" : undefined}
            >
              {runCount ?? (loadedRunCount > 0 ? `≥${loadedRunCount}` : "—")}
            </span>
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
      width: "w-20",
      align: "right",
      cell: (exp) => {
        const rollup = workbench.experiments.find((item) => item.experiment.id === exp.id);
        return (
          <span className="text-label tabular-nums text-muted-foreground">
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
        <span
          className="whitespace-nowrap text-label tabular-nums text-muted-foreground"
          title={exp.updatedAt}
        >
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
      cell: (asset) => <span className="text-label text-muted-foreground">{asset.scopeKind}</span>,
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
  const experimentCountValue =
    completeness.experimentCount ??
    (projectExperiments.length > 0 ? `≥${projectExperiments.length}` : "—");
  const executionCounts = rollupExecutions(overviewRows);
  const flaggedCount = attentionRuns(overviewRows).length;
  const activityPartial = Boolean(overviewRuns.data?.truncated);
  const activityError = shouldShowFailure(overviewRuns.error, {
    fetching: overviewRuns.isFetching,
    needsAuth,
  })
    ? overviewRuns.error instanceof Error
      ? overviewRuns.error.message
      : "Could not load project activity"
    : null;
  const activityPending = overviewRuns.isPending || (needsAuth && overviewRuns.data === undefined);
  const activityState = (body: JSX.Element): JSX.Element =>
    activityError ? (
      <WorkbenchOperationState
        kind="error"
        density="compact"
        title="Could not load project activity"
        detail={activityError}
        action={<WorkbenchRetryAction onClick={() => void overviewRuns.refetch()} />}
      />
    ) : activityPending ? (
      <WorkbenchOperationState
        kind="loading"
        density="compact"
        title="Loading project activity…"
        skeletonRows={3}
      />
    ) : (
      body
    );

  return (
    <>
      <EntityPage
        icon={FolderKanban}
        title={project.name}
        meta={
          <>
            <span>
              <span className="text-foreground">{experimentCountValue}</span> experiments
            </span>
            {completeness.runCount !== null ? (
              <span>
                <span className="text-foreground">{completeness.runCount}</span> runs
              </span>
            ) : null}
          </>
        }
        activeTab={activeTab}
        onActiveTabChange={setProjectTab}
        tabs={[
          {
            value: "overview",
            label: "Overview",
            content: (
              <OverviewSurface>
                <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                  {activityState(
                    executionCounts.total === 0 ? (
                      <div className="max-w-xl">
                        <p className="text-label text-muted-foreground">No executions yet.</p>
                        {projectExperiments.length > 0 && (
                          <ul className="mt-3 divide-y divide-border/70 border-y border-border/70">
                            {projectExperiments.map((experiment) => (
                              <li key={experiment.id}>
                                <WorkbenchAction
                                  kind="ghost"
                                  size="content"
                                  type="button"
                                  className="flex h-auto w-full items-center justify-start gap-2 rounded-none px-1 py-2 text-left font-normal"
                                  onClick={() => navigateToExperiment(experiment.id)}
                                >
                                  <FlaskConical className="size-icon-sm shrink-0 text-muted-foreground" />
                                  <span className="min-w-0 truncate text-body font-medium text-foreground">
                                    {experiment.name}
                                  </span>
                                </WorkbenchAction>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ) : (
                      <ExecutionOverview
                        rows={overviewRows}
                        partial={activityPartial}
                        inventoryBlocked={activityPartial}
                        groupBy="experiment"
                        onGroupSelect={navigateToExperiment}
                        onOpenAttention={() => setProjectTab("attention")}
                        onOpenTimeline={() => setProjectTab("timeline")}
                      />
                    ),
                  )}
                </DashboardCanvas>
              </OverviewSurface>
            ),
          },
          {
            value: "experiments",
            label:
              (completeness.experimentCount ?? projectExperiments.length) > 0
                ? `Experiments (${completeness.experimentCount ?? projectExperiments.length})`
                : "Experiments",
            content: (
              <OverviewSurface>
                <InventoryCanvas>
                  <div aria-busy={deletingExperimentId !== null}>
                    {deletingExperimentId && (
                      <WorkbenchOperationState
                        kind="running"
                        density="compact"
                        title="Deleting experiment…"
                        detail={
                          projectExperiments.find((item) => item.id === deletingExperimentId)?.name
                        }
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
                    {project?.experimentsError ? (
                      <WorkbenchOperationState
                        kind="error"
                        title="Could not load experiments"
                        detail={project.experimentsError}
                        action={<WorkbenchRetryAction onClick={onRefresh} />}
                      />
                    ) : !completeness.experimentsComplete &&
                      projectExperiments.length === 0 &&
                      (completeness.experimentCount ?? 0) > 0 ? (
                      <WorkbenchOperationState
                        kind="loading"
                        title="Loading experiments…"
                        skeletonRows={3}
                      />
                    ) : (
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
                    )}
                  </div>
                </InventoryCanvas>
              </OverviewSurface>
            ),
          },
          {
            value: "attention",
            label: flaggedCount > 0 ? `Attention (${flaggedCount})` : "Attention",
            content: (
              <OverviewSurface>
                <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                  {activityState(
                    <div className="mx-auto w-full max-w-6xl">
                      <NeedsAttention rows={overviewRows} inventoryBlocked={activityPartial} />
                    </div>,
                  )}
                </DashboardCanvas>
              </OverviewSurface>
            ),
          },
          {
            value: "timeline",
            label: "Timeline",
            content: (
              <OverviewSurface>
                <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
                  {activityState(
                    <div className="mx-auto w-full max-w-6xl">
                      <RunTimeline rows={overviewRows} inventoryBlocked={activityPartial} />
                    </div>,
                  )}
                </DashboardCanvas>
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
                <DashboardCanvas>
                  <DashboardCard title="Project">
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
                          <TableCell className="text-label text-muted-foreground">
                            Contents
                          </TableCell>
                          <TableCell className="text-label text-muted-foreground">
                            {experimentCountValue} experiments
                            {completeness.runCount !== null
                              ? ` · ${completeness.runCount} runs`
                              : ""}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </DashboardCard>

                  <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4">
                    <div className="min-w-0">
                      <p className="text-body text-foreground">Delete project</p>
                      <p className="mt-1 text-label text-muted-foreground">
                        Removes this project, its experiments, and its runs.
                      </p>
                    </div>
                    <WorkbenchAction
                      icon={<Trash2 aria-hidden />}
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
                      detail={project.name}
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
          workflowFile={experimentWorkflowLabel(createRunExperiment)}
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
