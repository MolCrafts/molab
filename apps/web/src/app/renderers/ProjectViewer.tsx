/**
 * The project page (Figma L02): views Overview · Experiments (n) · Assets (n)
 * · Plan (when the project hosts a roadmap). New experiment and ⋯ sit at the
 * right of the editor tab row. The Overview's counts open the workspace Runs
 * filtered to this project; Attention, Timeline and Settings left the page.
 */

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Copy,
  ExternalLink,
  FileText,
  FlaskConical,
  FolderKanban,
  ListChecks,
  Package,
} from "lucide-react";
import { type JSX, useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { experimentsApi, projectsApi } from "@/api";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import { useCompareSet } from "@/app/compare";
import { activeWorkspace, itemFromWorkspaceRunRow } from "@/app/compare/entries";
import { CreateExperimentDialog } from "@/app/components/CreateExperimentDialog";
import { CreateRunDialog } from "@/app/components/CreateRunDialog";
import type { DataTableColumn, DataTableRowAction } from "@/app/components/entity";
import {
  DataTable,
  EMPTY_COPY,
  EmptyState,
  EntityPage,
  StatusIcon,
  ViewLabel,
} from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { runPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import { projectSnapshotCompleteness } from "@/app/renderers/entityWorkbenchData";
import { declaredCellCount, experimentVerdict } from "@/app/renderers/experiment/experimentStory";
import { ProjectEditorActions } from "@/app/renderers/project/ProjectEditorActions";
import { ProjectOverview } from "@/app/renderers/project/ProjectOverview";
import { runsHref, type ScopeRun, scopeRunsOf } from "@/app/renderers/scopeStory";
import { runLabel } from "@/app/runs/runTitle";
import { experimentWorkflowLabel } from "@/app/state/api";
import { projectAssetsQueryOptions } from "@/app/state/entityQueries";
import { useNavigationState } from "@/app/state/useNavigationState";
import { isActiveStatus, normalizeStatus } from "@/app/status/vocabulary";
import type {
  ApiAssetResponse,
  ExperimentSummary,
  ProjectView,
  ScopedRendererProps,
} from "@/app/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";
import { formatRelative } from "@/lib/format-time";
import { PlanProgress, usePlanCampaigns } from "@/plugins/knowledge/PlanProgress";

type ProjectRendererProps = ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "assets" | "workspaces"
>;

const VIEWS: readonly ProjectView[] = ["overview", "experiments", "assets", "plan"];

const Muted = ({ children, mono }: { children: string; mono?: boolean }): JSX.Element => (
  <span
    className={`block truncate text-label text-muted-foreground ${mono ? "font-mono" : ""}`}
    title={children}
  >
    {children}
  </span>
);

const assetExtra = (asset: ApiAssetResponse): Record<string, unknown> =>
  (asset.extra as Record<string, unknown> | undefined) ?? {};

export const ProjectViewer = ({
  selection,
  snapshot,
  onRefresh,
}: ProjectRendererProps): JSX.Element => {
  const [newExperimentOpen, setNewExperimentOpen] = useState(false);
  const [createRunExperimentId, setCreateRunExperimentId] = useState<string | null>(null);
  const { setSelection } = useNavigationState(snapshot);
  const { confirm, dialog: confirmDialog } = useConfirm();
  const navigate = useNavigate();
  const preview = usePreview();
  const compare = useCompareSet();

  const projectId = selection.objectId;
  const project = snapshot.projects.find((p) => p.id === projectId);
  const requested: ProjectView =
    selection.objectType === "project" ? (selection.projectView ?? "overview") : "overview";

  const assetsQuery = useQuery({
    ...projectAssetsQueryOptions(projectId),
    enabled: Boolean(projectId),
  });
  const { campaigns } = usePlanCampaigns(project?.path ?? projectId);
  const activeTab: ProjectView =
    requested === "plan" && campaigns.length === 0 ? "overview" : requested;
  // The run inventory, not the lazy snapshot: a project's runs load per experiment.
  const {
    query: inventory,
    rows,
    truncated,
  } = useScopeRuns({ projectId }, Boolean(projectId) && activeTab !== "plan");
  const needsAuth = activeNeedsAuth(snapshot.workspaces);

  const setProjectTab = useCallback(
    (value: string): void => {
      const projectView = (VIEWS as readonly string[]).includes(value)
        ? (value as ProjectView)
        : "overview";
      setSelection({ objectType: "project", objectId: projectId, projectView });
    },
    [projectId, setSelection],
  );

  const experiments = useMemo(
    () => snapshot.experiments.filter((e) => e.projectId === projectId),
    [snapshot.experiments, projectId],
  );
  const runs = useMemo(() => scopeRunsOf(rows, snapshot.runs, "experiment"), [rows, snapshot.runs]);
  const runsOf = useCallback(
    (experimentId: string): ScopeRun[] => runs.filter((run) => run.groupId === experimentId),
    [runs],
  );
  const verdicts = useMemo(
    () =>
      new Map(
        experiments.map((experiment) => [
          experiment.id,
          experimentVerdict(runsOf(experiment.id), {
            declaredCells: declaredCellCount(experiment.parameterSpace),
          }),
        ]),
      ),
    [experiments, runsOf],
  );

  const openExperiment = (experimentId: string): void =>
    setSelection({ objectType: "experiment", objectId: experimentId });
  const previewExperiment = (experimentId: string): void =>
    preview.preview({ kind: "experiment", projectId, experimentId });
  const openRuns = (filter?: string): void => {
    void navigate(runsHref(filter, projectId));
  };

  const compareAll = useMemo(() => {
    const ws = activeWorkspace(snapshot.workspaces);
    if (!ws || !project) return null;
    return () => {
      compare.addMany(rows.map((row) => itemFromWorkspaceRunRow(row, ws)));
      void navigate("/compare");
    };
  }, [snapshot.workspaces, project, compare, rows, navigate]);

  const deleteProject = async (): Promise<void> => {
    await projectsApi.deleteProject(projectId);
    onRefresh();
    setSelection(null);
  };

  const deleteExperiment = async (experiment: ExperimentSummary): Promise<void> => {
    const count = runsOf(experiment.id).length;
    const confirmed = await confirm({
      title: `Delete experiment “${experiment.name}”?`,
      description: `Its ${count} ${count === 1 ? "run is" : "runs are"} removed with it.`,
      confirmLabel: "Delete experiment",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await experimentsApi.deleteExperiment(experiment.projectId, experiment.id);
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete the experiment");
    }
  };

  const copy = (text: string, what: string): void => {
    void navigator.clipboard.writeText(text);
    toast(`Copied ${what}`);
  };

  if (!project) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Project not found"
        detail="The current workspace snapshot no longer contains this project."
      />
    );
  }

  const completeness = projectSnapshotCompleteness(project, experiments, runs);

  const experimentRowActions = (
    experiment: ExperimentSummary,
  ): DataTableRowAction<ExperimentSummary>[] => {
    const workflow = snapshot.workflows.find((item) => item.experimentId === experiment.id);
    return [
      {
        id: "open",
        label: "Open experiment",
        onSelect: () => openExperiment(experiment.id),
      },
      {
        id: "new-run",
        label: "New run…",
        onSelect: () => setCreateRunExperimentId(experiment.id),
      },
      {
        id: "open-workflow",
        label: "Open workflow",
        disabled: !workflow,
        title: workflow ? undefined : "No workflow is bound to this experiment.",
        onSelect: () =>
          setSelection({
            objectType: "experiment",
            objectId: experiment.id,
            experimentView: "workflow",
          }),
      },
      {
        id: "copy-id",
        label: "Copy experiment id",
        onSelect: () => copy(experiment.id, "experiment id"),
      },
      {
        id: "delete",
        label: "Delete experiment…",
        destructive: true,
        separatorBefore: true,
        onSelect: (row) => void deleteExperiment(row),
      },
    ];
  };

  const experimentColumns: DataTableColumn<ExperimentSummary>[] = [
    {
      key: "status",
      header: <span className="sr-only">Status</span>,
      width: "w-8",
      cell: (experiment) => {
        const verdict = verdicts.get(experiment.id);
        return verdict ? <StatusIcon status={verdict.status} className="size-icon-sm" /> : null;
      },
    },
    {
      key: "name",
      header: "experiment",
      cell: (experiment) => (
        <span className="block truncate text-body text-foreground" title={experiment.name}>
          {experiment.name}
        </span>
      ),
    },
    {
      key: "state",
      header: "state",
      cell: (experiment) => <Muted>{verdicts.get(experiment.id)?.subject ?? "—"}</Muted>,
    },
    {
      key: "workflow",
      header: "workflow",
      width: "w-56",
      cell: (experiment) => <Muted mono>{experimentWorkflowLabel(experiment) || "—"}</Muted>,
    },
    {
      key: "updated",
      header: "updated",
      width: "w-24",
      align: "right",
      cell: (experiment) => (
        <span
          className="text-label tabular-nums text-muted-foreground"
          title={experiment.updatedAt}
        >
          {formatRelative(experiment.updatedAt)}
        </span>
      ),
    },
  ];

  const assetFrom = (asset: ApiAssetResponse): JSX.Element => {
    const extra = assetExtra(asset);
    if (extra.originKind !== "execution") return <Muted>imported</Muted>;
    const runId = typeof extra.runId === "string" ? extra.runId : null;
    const run = runId ? rows.find((item) => item.id === runId) : undefined;
    const label = run ? runLabel(run) : (runId ?? "execution");
    return run ? (
      <button
        type="button"
        className="block max-w-full truncate font-mono text-label text-primary hover:underline"
        title={`Open ${label}`}
        onClick={(event) => {
          event.stopPropagation();
          void navigate(runPath(run.projectId, run.experimentId, run.id));
        }}
      >
        {label}
      </button>
    ) : (
      <Muted mono>{label}</Muted>
    );
  };

  const assetColumns: DataTableColumn<ApiAssetResponse>[] = [
    {
      key: "icon",
      header: <span className="sr-only">Kind</span>,
      width: "w-8",
      cell: () => <FileText aria-hidden className="size-icon-sm text-muted-foreground" />,
    },
    {
      key: "name",
      header: "asset",
      cell: (asset) => (
        <span className="block truncate text-body text-foreground" title={asset.name}>
          {asset.name}
        </span>
      ),
    },
    {
      key: "type",
      header: "type",
      width: "w-44",
      cell: (asset) => <Muted mono>{asset.kind}</Muted>,
    },
    {
      key: "size",
      header: "size",
      width: "w-20",
      align: "right",
      cell: (asset) => {
        const size = assetExtra(asset).size;
        return (
          <span className="text-label tabular-nums text-foreground">
            {typeof size === "number" ? formatBytes(size) : "—"}
          </span>
        );
      },
    },
    { key: "from", header: "from", width: "w-64", cell: assetFrom },
    {
      key: "added",
      header: "added",
      width: "w-24",
      align: "right",
      cell: (asset) => (
        <span className="text-label tabular-nums text-muted-foreground" title={asset.createdAt}>
          {formatRelative(asset.createdAt)}
        </span>
      ),
    },
  ];

  const assets = assetsQuery.data ?? [];
  const assetsError = shouldShowFailure(assetsQuery.error, {
    fetching: assetsQuery.isFetching,
    needsAuth,
  })
    ? assetsQuery.error instanceof Error
      ? assetsQuery.error.message
      : "Failed to load project assets"
    : null;

  const experimentsView = project.experimentsError ? (
    <WorkbenchOperationState
      kind="error"
      title="Could not load experiments"
      detail={project.experimentsError}
      action={<WorkbenchRetryAction onClick={onRefresh} />}
    />
  ) : !completeness.experimentsComplete &&
    experiments.length === 0 &&
    (completeness.experimentCount ?? 0) > 0 ? (
    <WorkbenchOperationState kind="loading" title="Loading experiments…" skeletonRows={3} />
  ) : (
    <DataTable
      columns={experimentColumns}
      data={experiments}
      getRowKey={(experiment) => experiment.id}
      getRowLabel={(experiment) => `Experiment ${experiment.name}`}
      onRowActivate={(experiment) => openExperiment(experiment.id)}
      getRowPreview={(experiment) => ({
        kind: "experiment",
        projectId: experiment.projectId,
        experimentId: experiment.id,
      })}
      rowActions={experimentRowActions}
      empty={
        <EmptyState
          title={EMPTY_COPY.experiments.title}
          description={EMPTY_COPY.experiments.description}
        />
      }
    />
  );

  const assetsView =
    assetsQuery.isPending || (needsAuth && assetsQuery.data === undefined) ? (
      <WorkbenchOperationState kind="loading" title="Loading project assets…" skeletonRows={5} />
    ) : assetsError ? (
      <WorkbenchOperationState
        kind="error"
        title="Could not load project assets"
        detail={assetsError}
        action={<WorkbenchRetryAction onClick={() => void assetsQuery.refetch()} />}
      />
    ) : (
      <DataTable
        columns={assetColumns}
        data={assets}
        getRowKey={(asset) => asset.id}
        getRowLabel={(asset) => `Asset ${asset.name}`}
        onRowActivate={(asset) => setSelection({ objectType: "asset", objectId: asset.id })}
        getRowPreview={(asset) => ({ kind: "asset", assetId: asset.id })}
        rowActions={(asset) => [
          {
            id: "open",
            label: "Open asset",
            icon: ExternalLink,
            onSelect: () => setSelection({ objectType: "asset", objectId: asset.id }),
          },
          {
            id: "copy-id",
            label: "Copy asset id",
            icon: Copy,
            onSelect: () => copy(asset.id, "asset id"),
          },
        ]}
        empty={<EmptyState title={EMPTY_COPY.assets.title} />}
      />
    );

  const tabs = [
    {
      value: "overview",
      label: <ViewLabel icon={Activity}>Overview</ViewLabel>,
      content: (
        <ProjectOverview
          experiments={experiments}
          runs={runs}
          rows={rows}
          partial={truncated}
          loading={inventory.isPending}
          onOpenRuns={openRuns}
          onPreviewExperiment={previewExperiment}
          onOpenExperiment={openExperiment}
          onNewExperiment={() => setNewExperimentOpen(true)}
        />
      ),
    },
    {
      value: "experiments",
      label: (
        <ViewLabel icon={FlaskConical} count={completeness.experimentCount ?? experiments.length}>
          Experiments
        </ViewLabel>
      ),
      content: <div className="flex h-full min-h-0 flex-col bg-background">{experimentsView}</div>,
    },
    {
      value: "assets",
      label: (
        <ViewLabel icon={Package} count={assets.length}>
          Assets
        </ViewLabel>
      ),
      content: <div className="flex h-full min-h-0 flex-col bg-background">{assetsView}</div>,
    },
    ...(campaigns.length > 0
      ? [
          {
            value: "plan",
            label: <ViewLabel icon={ListChecks}>Plan</ViewLabel>,
            content: (
              <div className="h-full min-h-0 overflow-auto bg-background px-6 py-6">
                <PlanProgress
                  campaigns={campaigns}
                  onOpenExperiment={(name) => {
                    const match = experiments.find(
                      (item) => item.name === name || item.path.endsWith(`/${name}`),
                    );
                    if (match) openExperiment(match.id);
                  }}
                  onOpenDoc={(path) => setSelection({ objectType: "knowledge", objectId: path })}
                />
              </div>
            ),
          },
        ]
      : []),
  ];

  const createRunExperiment = createRunExperimentId
    ? experiments.find((experiment) => experiment.id === createRunExperimentId)
    : null;

  return (
    <>
      <EntityPage
        icon={FolderKanban}
        title={project.name}
        actions={
          <ProjectEditorActions
            projectId={project.id}
            projectName={project.name}
            experimentCount={completeness.experimentCount ?? experiments.length}
            runCount={completeness.runCount ?? runs.length}
            active={runs.some((run) => isActiveStatus(normalizeStatus(run.status)))}
            onNewExperiment={() => setNewExperimentOpen(true)}
            onOpenRuns={() => openRuns()}
            onCompareAll={compareAll}
            onDelete={deleteProject}
          />
        }
        activeTab={activeTab}
        onActiveTabChange={setProjectTab}
        tabs={tabs}
      />
      <CreateExperimentDialog
        projectId={projectId}
        open={newExperimentOpen}
        onOpenChange={setNewExperimentOpen}
        trigger={null}
        onExperimentCreated={onRefresh}
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
      {confirmDialog}
    </>
  );
};
