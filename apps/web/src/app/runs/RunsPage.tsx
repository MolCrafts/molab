import { ListChecks, RefreshCw } from "lucide-react";
import { type JSX, lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ComparePane, useCompareSet } from "@/app/compare";
import { entryFromWorkspaceRunRow } from "@/app/compare/entries";
import { EntityHeader } from "@/app/components/entity";
import { runPath } from "@/app/entities/paths";
import { SurfaceErrorBoundary } from "@/app/layout/SurfaceErrorBoundary";
import type { InspectorSurfaceRegistration } from "@/app/panels/inspectorSurface";
import type { ObjectView, WorkspaceSnapshot } from "@/app/types";
import {
  WorkbenchAction,
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
import type { WorkspaceRunRow, WorkspaceRunsFilters } from "./types";
import { type MultiSelectState, nextSelection } from "./useRunMultiSelect";
import { useWorkspaceRuns } from "./useWorkspaceRuns";

const RunInspector = lazy(() =>
  import("./inspector/RunInspector").then((module) => ({ default: module.RunInspector })),
);

interface RunsPageProps {
  snapshot: WorkspaceSnapshot;
  onInspectorChange: (registration: InspectorSurfaceRegistration | null) => void;
}

const writeRunsParams = (
  prev: URLSearchParams,
  patch: {
    tab?: RunsTab;
    runId?: string | null;
    executionId?: string | null;
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
  const selectedRunId = searchParams.get("runId");
  const selectedExecutionId = searchParams.get("executionId");
  const jobsSort = useMemo(() => parseJobsSort(searchParams.get("sort")), [searchParams]);
  const jobsPage = useMemo(() => parsePage(searchParams.get("page")), [searchParams]);
  const jobsPageSize = useMemo(() => parsePageSize(searchParams.get("pageSize")), [searchParams]);

  const { rows, truncated, unreachable, loading, error, lastSyncedAt, refresh } =
    useWorkspaceRuns();

  const filteredRuns = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  // Gathering runs for comparison is additive and never navigates: ticking a
  // row adds it, clicking the row still opens it.
  const compare = useCompareSet();
  const [compareSelection, setCompareSelection] = useState<MultiSelectState>(() => ({
    selected: new Set<string>(),
    anchor: null,
  }));
  // `orderedIds` comes from the table, in the order it actually rendered.
  const selectCompareAt = useCallback(
    (index: number, orderedIds: string[], modifiers: { shift: boolean; meta: boolean }) => {
      setCompareSelection((current) => nextSelection(current, index, orderedIds, modifiers));
    },
    [],
  );

  const workspaceLabels = useMemo(
    () => new Map(snapshot.workspaces.map((ws) => [ws.key, ws.label])),
    [snapshot.workspaces],
  );

  const addSelectedToCompare = useCallback(() => {
    const picked = filteredRuns.filter((run) => compareSelection.selected.has(run.id));
    compare.addMany(
      picked.map((run) =>
        entryFromWorkspaceRunRow(run, {
          key: run.workspaceKey,
          label: workspaceLabels.get(run.workspaceKey) ?? run.workspaceKey,
        }),
      ),
    );
    setCompareSelection({ selected: new Set<string>(), anchor: null });
  }, [compare, compareSelection.selected, filteredRuns, workspaceLabels]);

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

  // A served workspace that failed this poll contributes no rows. Say so —
  // an absent workspace is otherwise indistinguishable from an empty one.
  const unreachableNote =
    unreachable.length > 0
      ? ` · ${unreachable.length} workspace${unreachable.length === 1 ? "" : "s"} unreachable (${unreachable.join(", ")})`
      : "";

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
        {unreachableNote}
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

        {tab === "jobs" && compareSelection.selected.size > 0 && (
          <div className="mb-2 flex items-center gap-2">
            <span className="text-label text-muted-foreground">
              {compareSelection.selected.size} selected
            </span>
            <WorkbenchAction kind="secondary" size="compact" onClick={addSelectedToCompare}>
              Add to comparison
            </WorkbenchAction>
            <WorkbenchAction
              kind="ghost"
              size="compact"
              onClick={() => setCompareSelection({ selected: new Set<string>(), anchor: null })}
            >
              Clear selection
            </WorkbenchAction>
          </div>
        )}

        {tab === "jobs" && (
          <RunsJobsTable
            rows={filteredRuns}
            selectedRunId={selectedRunId}
            onSelectRun={selectRun}
            selection={{
              selected: compareSelection.selected,
              selectAt: selectCompareAt,
            }}
            sort={jobsSort}
            onSortChange={setJobsSort}
            page={jobsPage}
            pageSize={jobsPageSize}
            onPageChange={setJobsPage}
            onPageSizeChange={setJobsPageSize}
          />
        )}

        {tab === "compare" && (
          <div className="h-full min-h-0">
            <ComparePane />
          </div>
        )}
      </div>
    </div>
  );
};
