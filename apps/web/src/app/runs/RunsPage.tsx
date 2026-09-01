import { ListChecks, RefreshCw } from "lucide-react";
import { type JSX, lazy, Suspense, useCallback, useEffect, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { EntityHeader } from "@/app/components/entity";
import { runPath } from "@/app/entities/paths";
import { SurfaceErrorBoundary } from "@/app/layout/SurfaceErrorBoundary";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import type { ObjectView, WorkspaceSnapshot } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import { applyFilters } from "./aggregates";
import { parseFilterParams } from "./filterParams";
import {
  DEFAULT_JOBS_SORT,
  DEFAULT_PAGE_SIZE,
  formatJobsSort,
  type JobsSort,
  parseJobsSort,
  parsePage,
  parsePageSize,
} from "./jobsTable";
import { RunsJobsTable } from "./RunsJobsTable";
import { parseRunsTab, type RunsTab, RunsTabBar } from "./RunsTabBar";
import type { GanttMode } from "./RunsTimelineView";
import type { WorkspaceExecutionRow, WorkspaceRunRow, WorkspaceRunsFilters } from "./types";
import { useWorkspaceRuns } from "./useWorkspaceRuns";

const RunInspector = lazy(() =>
  import("./inspector/RunInspector").then((module) => ({ default: module.RunInspector })),
);
const RunsTimelineView = lazy(() =>
  import("./RunsTimelineView").then((module) => ({ default: module.RunsTimelineView })),
);

interface RunsPageProps {
  snapshot: WorkspaceSnapshot;
  onInspectorChange: (registration: InspectorSurfaceRegistration | null) => void;
}

const VALID_GANTT_MODES: ReadonlySet<string> = new Set<string>(["runs", "executions"]);

const parseGanttMode = (raw: string | null): GanttMode =>
  raw && VALID_GANTT_MODES.has(raw) ? (raw as GanttMode) : "runs";

const writeRunsParams = (
  prev: URLSearchParams,
  patch: {
    tab?: RunsTab;
    runId?: string | null;
    executionId?: string | null;
    mode?: GanttMode;
    sort?: JobsSort | null;
    page?: number | null;
    pageSize?: number | null;
  },
): URLSearchParams => {
  const next = new URLSearchParams(prev);
  if (patch.tab !== undefined) {
    if (patch.tab === "jobs") next.delete("tab");
    else next.set("tab", patch.tab);
  }
  if (patch.runId !== undefined) {
    if (patch.runId === null || patch.runId === "") next.delete("runId");
    else next.set("runId", patch.runId);
  }
  if (patch.executionId !== undefined) {
    if (patch.executionId === null || patch.executionId === "") next.delete("executionId");
    else next.set("executionId", patch.executionId);
  }
  if (patch.mode !== undefined) {
    if (patch.mode === "runs") next.delete("mode");
    else next.set("mode", patch.mode);
  }
  if (patch.sort !== undefined) {
    if (
      patch.sort === null ||
      (patch.sort.key === DEFAULT_JOBS_SORT.key && patch.sort.dir === DEFAULT_JOBS_SORT.dir)
    ) {
      next.delete("sort");
    } else {
      next.set("sort", formatJobsSort(patch.sort));
    }
  }
  if (patch.page !== undefined) {
    if (patch.page === null || patch.page <= 1) next.delete("page");
    else next.set("page", String(patch.page));
  }
  if (patch.pageSize !== undefined) {
    if (patch.pageSize === null || patch.pageSize === DEFAULT_PAGE_SIZE) next.delete("pageSize");
    else next.set("pageSize", String(patch.pageSize));
  }
  return next;
};

export const RunsPage = ({ snapshot, onInspectorChange }: RunsPageProps): JSX.Element => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo<WorkspaceRunsFilters>(
    () => parseFilterParams(searchParams),
    [searchParams],
  );

  const tab = parseRunsTab(searchParams.get("tab"));
  const ganttMode = parseGanttMode(searchParams.get("mode"));
  const selectedRunId = searchParams.get("runId");
  const selectedExecutionId = searchParams.get("executionId");
  const jobsSort = useMemo(() => parseJobsSort(searchParams.get("sort")), [searchParams]);
  const jobsPage = useMemo(() => parsePage(searchParams.get("page")), [searchParams]);
  const jobsPageSize = useMemo(() => parsePageSize(searchParams.get("pageSize")), [searchParams]);

  const { rows, truncated, loading, error, lastSyncedAt, refresh } = useWorkspaceRuns();

  const filteredRuns = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  const selectedRun = useMemo<WorkspaceRunRow | null>(
    () => (selectedRunId ? (rows.find((row) => row.id === selectedRunId) ?? null) : null),
    [rows, selectedRunId],
  );

  const setTab = useCallback(
    (next: RunsTab): void => {
      setSearchParams((prev) => writeRunsParams(prev, { tab: next }), { replace: true });
    },
    [setSearchParams],
  );

  const setGanttMode = useCallback(
    (next: GanttMode): void => {
      setSearchParams((prev) => writeRunsParams(prev, { mode: next }), { replace: true });
    },
    [setSearchParams],
  );

  const setJobsSort = useCallback(
    (next: JobsSort): void => {
      setSearchParams((prev) => writeRunsParams(prev, { sort: next, page: 1 }), { replace: true });
    },
    [setSearchParams],
  );

  const setJobsPage = useCallback(
    (next: number): void => {
      setSearchParams((prev) => writeRunsParams(prev, { page: next }), { replace: true });
    },
    [setSearchParams],
  );

  const setJobsPageSize = useCallback(
    (next: number): void => {
      setSearchParams((prev) => writeRunsParams(prev, { pageSize: next, page: 1 }), {
        replace: true,
      });
    },
    [setSearchParams],
  );

  const selectRun = useCallback(
    (run: WorkspaceRunRow): void => {
      setSearchParams((prev) => writeRunsParams(prev, { runId: run.id, executionId: null }), {
        replace: true,
      });
    },
    [setSearchParams],
  );

  const selectExecution = useCallback(
    (run: WorkspaceRunRow, execution: WorkspaceExecutionRow): void => {
      setSearchParams(
        (prev) => writeRunsParams(prev, { runId: run.id, executionId: execution.executionId }),
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setSelectedExecutionId = useCallback(
    (id: string | null): void => {
      setSearchParams((prev) => writeRunsParams(prev, { executionId: id }), { replace: true });
    },
    [setSearchParams],
  );

  const clearSelection = useCallback(() => {
    setSearchParams((prev) => writeRunsParams(prev, { runId: null, executionId: null }), {
      replace: true,
    });
  }, [setSearchParams]);

  const navigateToRun = useCallback(
    (run: WorkspaceRunRow, view?: ObjectView): void => {
      navigate(runPath(run.projectId, run.experimentId, run.id, view));
    },
    [navigate],
  );

  useEffect(() => {
    if (!selectedRun) {
      onInspectorChange(null);
      return;
    }

    onInspectorChange({
      id: `runs:${selectedRun.id}`,
      render: ({ className }) => (
        <SurfaceErrorBoundary
          resetKey={`runs-inspector:${selectedRun.id}`}
          fallback={(error) => (
            <WorkbenchOperationState
              kind="error"
              title="Could not load run details"
              detail={error.message}
              className={className}
              action={
                <WorkbenchRetryAction
                  label="Reload application"
                  onClick={() => window.location.reload()}
                />
              }
            />
          )}
        >
          <Suspense
            fallback={
              <WorkbenchOperationState
                kind="loading"
                title="Loading run details…"
                className={className}
                skeletonRows={4}
              />
            }
          >
            <RunInspector
              run={selectedRun}
              snapshot={snapshot}
              selectedExecutionId={selectedExecutionId}
              onSelectExecution={setSelectedExecutionId}
              onClear={clearSelection}
              onOpenRun={navigateToRun}
              className={className}
            />
          </Suspense>
        </SurfaceErrorBoundary>
      ),
    });
  }, [
    clearSelection,
    navigateToRun,
    onInspectorChange,
    selectedExecutionId,
    selectedRun,
    setSelectedExecutionId,
    snapshot,
  ]);

  useEffect(
    () => () => {
      onInspectorChange(null);
    },
    [onInspectorChange],
  );

  const headerSummary = truncated
    ? `Showing first ${rows.length} runs (truncated). Narrow filters or raise the limit.`
    : `${filteredRuns.length} of ${rows.length} runs match current filters`;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
      <EntityHeader
        icon={ListChecks}
        title="Runs"
        titleTooltip={headerSummary}
        actions={
          <WorkbenchIconAction
            label={loading ? "Refreshing runs" : "Refresh runs"}
            kind="ghost"
            type="button"
            onClick={refresh}
            disabled={loading}
            title={
              loading
                ? "Refreshing…"
                : lastSyncedAt
                  ? `Refresh · synced ${formatRelative(lastSyncedAt.toISOString())}`
                  : "Refresh"
            }
            size="default"
            className="text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "mol-motion-progress-spin")} />
          </WorkbenchIconAction>
        }
      />
      <div className="border-b border-border/60 px-3 pb-2 text-micro text-muted-foreground">
        {headerSummary}
        {lastSyncedAt ? ` · synced ${formatRelative(lastSyncedAt.toISOString())}` : ""}
      </div>
      <div className="shrink-0 border-b border-border/60 bg-background px-4">
        <RunsTabBar value={tab} onChange={setTab} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {error ? (
          <WorkbenchOperationState
            kind="error"
            density="compact"
            title="Could not load runs"
            detail={error}
            action={<WorkbenchRetryAction onClick={refresh} />}
          />
        ) : null}

        {tab === "jobs" && (
          <RunsJobsTable
            rows={filteredRuns}
            selectedRunId={selectedRunId}
            onSelectRun={selectRun}
            sort={jobsSort}
            onSortChange={setJobsSort}
            page={jobsPage}
            pageSize={jobsPageSize}
            onPageChange={setJobsPage}
            onPageSizeChange={setJobsPageSize}
          />
        )}

        {tab === "timeline" ? (
          <SurfaceErrorBoundary
            resetKey="runs-timeline"
            fallback={(timelineError) => (
              <WorkbenchOperationState
                kind="error"
                title="Could not load the timeline"
                detail={timelineError.message}
                action={
                  <WorkbenchRetryAction
                    label="Reload application"
                    onClick={() => window.location.reload()}
                  />
                }
              />
            )}
          >
            <Suspense
              fallback={
                <WorkbenchOperationState
                  kind="loading"
                  title="Loading timeline…"
                  skeletonRows={5}
                />
              }
            >
              <RunsTimelineView
                rows={filteredRuns}
                mode={ganttMode}
                onModeChange={setGanttMode}
                onSelectRun={selectRun}
                onSelectExecution={selectExecution}
              />
            </Suspense>
          </SurfaceErrorBoundary>
        ) : null}
      </div>
    </div>
  );
};
