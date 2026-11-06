import { runExecutorFacet } from "./projections";
import { groupForStatus } from "./statusGroups";
import type { RunsQuickView, WorkspaceRunRow, WorkspaceRunsFilters } from "./types";

const HOUR_MS = 60 * 60 * 1000;

const safeDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const includesValue = (filter: string[] | undefined, value: string | null): boolean => {
  if (!filter || filter.length === 0) return true;
  if (!value) return false;
  return filter.includes(value);
};

const matchesQuickView = (run: WorkspaceRunRow, view: RunsQuickView, now: number): boolean => {
  switch (view) {
    case "active":
      return run.statusSummary.active > 0;
    case "failed24h": {
      return run.executions.some((execution) => {
        if (groupForStatus(execution.status) !== "failed") return false;
        const finished = safeDate(execution.finishedAt);
        return finished !== null && now - finished.getTime() <= 24 * HOUR_MS;
      });
    }
    case "longRunning": {
      const earliestStart = run.executions
        .filter((execution) => groupForStatus(execution.status) === "running")
        .reduce<number | null>((min, exec) => {
          const start = safeDate(exec.startedAt);
          if (!start) return min;
          return min === null ? start.getTime() : Math.min(min, start.getTime());
        }, null);
      if (earliestStart === null) return false;
      return now - earliestStart >= HOUR_MS;
    }
    default:
      return true;
  }
};

interface FilterPredicates {
  status: (run: WorkspaceRunRow) => boolean;
  projectId: (run: WorkspaceRunRow) => boolean;
  experimentId: (run: WorkspaceRunRow) => boolean;
  backend: (run: WorkspaceRunRow) => boolean;
  cluster: (run: WorkspaceRunRow) => boolean;
  target: (run: WorkspaceRunRow) => boolean;
  quickView: (run: WorkspaceRunRow) => boolean;
}

const buildPredicates = (filters: WorkspaceRunsFilters, now: number): FilterPredicates => ({
  status: (run) => {
    if (!filters.status || filters.status.length === 0) return true;
    const observed = run.statusSummary.notStarted
      ? ["not_started"]
      : Object.keys(run.statusSummary.byStatus);
    return filters.status.some((filter) => {
      const filterGroup = groupForStatus(filter);
      return observed.some(
        (status) =>
          status === filter || (filterGroup !== null && groupForStatus(status) === filterGroup),
      );
    });
  },
  projectId: (run) => includesValue(filters.projectId, run.projectId),
  experimentId: (run) => includesValue(filters.experimentId, run.experimentId),
  backend: (run) => {
    const values = runExecutorFacet(run, "backend");
    return !filters.backend?.length || filters.backend.some((value) => values.includes(value));
  },
  cluster: (run) => {
    const values = runExecutorFacet(run, "cluster_name");
    return !filters.cluster?.length || filters.cluster.some((value) => values.includes(value));
  },
  target: (run) => {
    const values = [
      ...runExecutorFacet(run, "target"),
      ...(run.targetHint ? [run.targetHint] : []),
    ];
    return !filters.target?.length || filters.target.some((value) => values.includes(value));
  },
  quickView: (run) => {
    const views = filters.quickView;
    if (!views || views.length === 0) return true;
    return views.some((view) => matchesQuickView(run, view, now));
  },
});

export const applyFilters = (
  runs: WorkspaceRunRow[],
  filters: WorkspaceRunsFilters,
  now: number = Date.now(),
): WorkspaceRunRow[] => {
  const predicates = buildPredicates(filters, now);
  return runs.filter(
    (run) =>
      predicates.status(run) &&
      predicates.projectId(run) &&
      predicates.experimentId(run) &&
      predicates.backend(run) &&
      predicates.cluster(run) &&
      predicates.target(run) &&
      predicates.quickView(run),
  );
};

export interface FacetCount {
  value: string;
  label: string;
  count: number;
}

export interface FacetSnapshot {
  status: FacetCount[];
  backend: FacetCount[];
  cluster: FacetCount[];
  target: FacetCount[];
  projectId: FacetCount[];
  experimentId: FacetCount[];
  quickView: Record<RunsQuickView, number>;
}

const tally = (
  runs: WorkspaceRunRow[],
  pick: (run: WorkspaceRunRow) => Array<{ value: string; label: string } | null>,
): FacetCount[] => {
  const map = new Map<string, FacetCount>();
  for (const run of runs) {
    for (const entry of pick(run)) {
      if (!entry) continue;
      const existing = map.get(entry.value);
      if (existing) existing.count += 1;
      else map.set(entry.value, { value: entry.value, label: entry.label, count: 1 });
    }
  }
  return Array.from(map.values()).sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.label.localeCompare(b.label);
  });
};

const omit = <K extends keyof FilterPredicates>(
  predicates: FilterPredicates,
  excluded: K,
): ((run: WorkspaceRunRow) => boolean) => {
  return (run) => {
    for (const key of Object.keys(predicates) as Array<keyof FilterPredicates>) {
      if (key === excluded) continue;
      if (!predicates[key](run)) return false;
    }
    return true;
  };
};

export const computeFacetCounts = (
  allRuns: WorkspaceRunRow[],
  filters: WorkspaceRunsFilters,
  now: number = Date.now(),
): FacetSnapshot => {
  const predicates = buildPredicates(filters, now);

  const filterFor = <K extends keyof FilterPredicates>(excluded: K): WorkspaceRunRow[] =>
    allRuns.filter(omit(predicates, excluded));

  const statusRuns = filterFor("status");
  const backendRuns = filterFor("backend");
  const clusterRuns = filterFor("cluster");
  const targetRuns = filterFor("target");
  const projectRuns = filterFor("projectId");
  const experimentRuns = filterFor("experimentId");
  const quickRuns = filterFor("quickView");

  return {
    status: tally(statusRuns, (run) =>
      run.statusSummary.notStarted
        ? [{ value: "not_started", label: "not started" }]
        : Object.keys(run.statusSummary.byStatus).map((status) => ({
            value: status,
            label: status,
          })),
    ),
    backend: tally(backendRuns, (run) =>
      runExecutorFacet(run, "backend").map((value) => ({ value, label: value })),
    ),
    cluster: tally(clusterRuns, (run) =>
      runExecutorFacet(run, "cluster_name").map((value) => ({ value, label: value })),
    ),
    target: tally(targetRuns, (run) =>
      [
        ...new Set([
          ...runExecutorFacet(run, "target"),
          ...(run.targetHint ? [run.targetHint] : []),
        ]),
      ].map((value) => ({ value, label: value })),
    ),
    projectId: tally(projectRuns, (run) => [{ value: run.projectId, label: run.projectName }]),
    experimentId: tally(experimentRuns, (run) => [
      { value: run.experimentId, label: run.experimentName },
    ]),
    quickView: {
      active: quickRuns.filter((run) => matchesQuickView(run, "active", now)).length,
      failed24h: quickRuns.filter((run) => matchesQuickView(run, "failed24h", now)).length,
      longRunning: quickRuns.filter((run) => matchesQuickView(run, "longRunning", now)).length,
    },
  };
};

export type RecentEventKind = "submitted" | "started" | "finished";

export interface RecentEvent {
  kind: RecentEventKind;
  at: string;
  executionId?: string;
  /** For finished events, mirrors execution.status (succeeded/failed/cancelled). */
  outcome?: string;
}

/**
 * Derives a "Recent events" list for a single run strictly from data the
 * backend already exposes — `createdAt`, plus per-execution `startedAt` /
 * `finishedAt`. Emits ONLY `submitted | started | finished`; never invents
 * synthetic events ("checkpoint saved", "stdout streaming", etc.).
 */
export const computeRecentEventsForRun = (run: WorkspaceRunRow): RecentEvent[] => {
  const events: RecentEvent[] = [];

  if (run.createdAt) {
    events.push({ kind: "submitted", at: run.createdAt });
  }

  for (const exec of run.executions) {
    if (exec.startedAt) {
      events.push({ kind: "started", at: exec.startedAt, executionId: exec.executionId });
    }
    if (exec.finishedAt) {
      events.push({
        kind: "finished",
        at: exec.finishedAt,
        executionId: exec.executionId,
        outcome: exec.status,
      });
    }
  }

  return events.sort((a, b) => {
    const ta = new Date(a.at).getTime();
    const tb = new Date(b.at).getTime();
    if (Number.isNaN(ta) && Number.isNaN(tb)) return 0;
    if (Number.isNaN(ta)) return 1;
    if (Number.isNaN(tb)) return -1;
    return tb - ta;
  });
};
