import { filterRuns } from "@/app/runs/runsFilter";
import { CHART_GROUPS, chartGroupOf, normalizeStatus } from "@/app/status/vocabulary";
import { runExecutorFacet, runPresentationStatus, runStartedAt } from "./projections";
import { runLabel } from "./runTitle";
import type { RunsStartedWindow, WorkspaceRunRow, WorkspaceRunsFilters } from "./types";

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

const WINDOW_MS: Record<RunsStartedWindow, number> = {
  "24h": 24 * HOUR_MS,
  "7d": 7 * 24 * HOUR_MS,
};

/** The run started (or, never started, was created) within the window. */
const startedWithin = (run: WorkspaceRunRow, window: RunsStartedWindow, now: number): boolean => {
  const at = safeDate(runStartedAt(run) ?? run.createdAt);
  return at !== null && now - at.getTime() <= WINDOW_MS[window];
};

/** The bar's free tokens, read by the same language as an experiment's Runs filter. */
const matchesTokens = (run: WorkspaceRunRow, q: string | undefined): boolean =>
  !q ||
  filterRuns(
    [
      {
        id: run.id,
        title: `${runLabel(run)} ${run.projectName} ${run.experimentName}`,
        status: runPresentationStatus(run),
        parameters: run.parameters ?? {},
      },
    ],
    q,
  ).length > 0;

interface FilterPredicates {
  status: (run: WorkspaceRunRow) => boolean;
  projectId: (run: WorkspaceRunRow) => boolean;
  experimentId: (run: WorkspaceRunRow) => boolean;
  backend: (run: WorkspaceRunRow) => boolean;
  cluster: (run: WorkspaceRunRow) => boolean;
  target: (run: WorkspaceRunRow) => boolean;
  started: (run: WorkspaceRunRow) => boolean;
  q: (run: WorkspaceRunRow) => boolean;
}

const buildPredicates = (filters: WorkspaceRunsFilters, now: number): FilterPredicates => ({
  // A run is filtered by its status now — its latest attempt — so a run that
  // failed and was resumed to success is not "failed". A word also matches its
  // chart group ("running" includes finalizing).
  status: (run) => {
    if (!filters.status || filters.status.length === 0) return true;
    const current = runPresentationStatus(run);
    const currentGroup = chartGroupOf(current);
    return filters.status.some((filter) => {
      const filterGroup = chartGroupOf(filter);
      return (
        normalizeStatus(filter) === current ||
        (filterGroup !== null && filterGroup === currentGroup)
      );
    });
  },
  projectId: (run) => includesValue(filters.projectId, run.projectId),
  experimentId: (run) => includesValue(filters.experimentId, run.experimentId),
  backend: (run) => {
    if (!filters.backend?.length) return true;
    const values = runExecutorFacet(run, "backend");
    return filters.backend.some((value) => values.includes(value));
  },
  cluster: (run) => {
    if (!filters.cluster?.length) return true;
    const values = runExecutorFacet(run, "cluster_name");
    return filters.cluster.some((value) => values.includes(value));
  },
  target: (run) => {
    if (!filters.target?.length) return true;
    const values = [
      ...runExecutorFacet(run, "target"),
      ...(run.targetHint ? [run.targetHint] : []),
    ];
    return filters.target.some((value) => values.includes(value));
  },
  started: (run) =>
    !filters.started?.length || filters.started.some((window) => startedWithin(run, window, now)),
  q: (run) => matchesTokens(run, filters.q),
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
      predicates.started(run) &&
      predicates.q(run),
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
  started: Record<RunsStartedWindow, number>;
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

/** Status facets in the vocabulary's chart order, not by count. */
const sortByGroup = (counts: FacetCount[]): FacetCount[] =>
  [...counts].sort(
    (left, right) =>
      CHART_GROUPS.findIndex((group) => group.id === left.value) -
      CHART_GROUPS.findIndex((group) => group.id === right.value),
  );

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
  const startedRuns = filterFor("started");

  return {
    // One count per run, by its latest attempt's chart group — what a pick shows.
    status: sortByGroup(
      tally(statusRuns, (run) => {
        const group = chartGroupOf(runPresentationStatus(run));
        if (!group) return [];
        const spec = CHART_GROUPS.find((candidate) => candidate.id === group);
        return [{ value: group, label: spec?.label ?? group }];
      }),
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
    started: {
      "24h": startedRuns.filter((run) => startedWithin(run, "24h", now)).length,
      "7d": startedRuns.filter((run) => startedWithin(run, "7d", now)).length,
    },
  };
};
