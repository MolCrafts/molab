/**
 * The workspace Runs filter in the URL (L05): facet picks (`status`, `projectId`,
 * `experimentId`, `target`, `backend`, `cluster`, `started`) and the filter
 * bar's free tokens (`q`). Facets and tokens are one filter: a `status:` /
 * `project:` / `target:` / `started:` token typed in the bar becomes a facet
 * pick (`absorbFacetTokens`).
 */

import type { RunsStartedWindow, WorkspaceRunsFilters } from "./types";

const ARRAY_KEYS = ["projectId", "experimentId", "backend", "cluster", "target", "status"] as const;
type ArrayKey = (typeof ARRAY_KEYS)[number];

const STARTED_VALUES: ReadonlySet<RunsStartedWindow> = new Set(["24h", "7d"]);

const splitCsv = (value: string): string[] =>
  value
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);

export const parseFilterParams = (params: URLSearchParams): WorkspaceRunsFilters => {
  const out: WorkspaceRunsFilters = {};
  for (const key of ARRAY_KEYS) {
    const raw = params.get(key);
    if (!raw) continue;
    const values = splitCsv(raw);
    if (values.length > 0) out[key] = values;
  }
  const started = splitCsv(params.get("started") ?? "").filter(
    (value): value is RunsStartedWindow => STARTED_VALUES.has(value as RunsStartedWindow),
  );
  if (started.length > 0) out.started = started;
  const q = params.get("q")?.trim();
  if (q) out.q = q;
  const limit = params.get("limit");
  if (limit) {
    const parsed = Number.parseInt(limit, 10);
    if (Number.isFinite(parsed) && parsed > 0) out.limit = parsed;
  }
  return out;
};

export const writeFilterParams = (
  prev: URLSearchParams,
  next: WorkspaceRunsFilters,
): URLSearchParams => {
  const merged = new URLSearchParams(prev);
  for (const key of ARRAY_KEYS) {
    const values = next[key];
    if (values && values.length > 0) merged.set(key, values.join(","));
    else merged.delete(key);
  }
  if (next.started && next.started.length > 0) merged.set("started", next.started.join(","));
  else merged.delete("started");
  if (next.q) merged.set("q", next.q);
  else merged.delete("q");
  if (next.limit !== undefined) merged.set("limit", String(next.limit));
  else merged.delete("limit");
  return merged;
};

export const toggleArrayFilter = (
  filters: WorkspaceRunsFilters,
  key: ArrayKey,
  value: string,
): WorkspaceRunsFilters => {
  const current = filters[key] ?? [];
  const exists = current.includes(value);
  const nextValues = exists ? current.filter((v) => v !== value) : [...current, value];
  const next: WorkspaceRunsFilters = { ...filters };
  if (nextValues.length > 0) next[key] = nextValues;
  else delete next[key];
  if (key === "projectId") delete next.experimentId;
  return next;
};

export const toggleStarted = (
  filters: WorkspaceRunsFilters,
  window: RunsStartedWindow,
): WorkspaceRunsFilters => {
  const current = filters.started ?? [];
  const nextValues = current.includes(window)
    ? current.filter((value) => value !== window)
    : [...current, window];
  const next: WorkspaceRunsFilters = { ...filters };
  if (nextValues.length > 0) next.started = nextValues;
  else delete next.started;
  return next;
};

export const hasActiveFilters = (filters: WorkspaceRunsFilters): boolean =>
  ARRAY_KEYS.some((key) => (filters[key]?.length ?? 0) > 0) ||
  (filters.started?.length ?? 0) > 0 ||
  Boolean(filters.q);

/**
 * Move `status:` `project:` `target:` `started:` tokens out of the bar's text
 * into facet picks; everything else stays as free tokens. A project token
 * names a project by id or by name (case-insensitive).
 */
export const absorbFacetTokens = (
  filters: WorkspaceRunsFilters,
  text: string,
  projects: readonly { id: string; name: string }[],
): WorkspaceRunsFilters => {
  let next: WorkspaceRunsFilters = { ...filters };
  const rest: string[] = [];
  for (const token of text.trim().split(/\s+/).filter(Boolean)) {
    const match = /^(status|project|target|started):(.+)$/i.exec(token);
    if (!match) {
      rest.push(token);
      continue;
    }
    const key = (match[1] as string).toLowerCase();
    for (const value of splitCsv(match[2] as string)) {
      if (key === "status" && !(next.status ?? []).includes(value.toLowerCase())) {
        next = toggleArrayFilter(next, "status", value.toLowerCase());
      } else if (key === "target" && !(next.target ?? []).includes(value)) {
        next = toggleArrayFilter(next, "target", value);
      } else if (key === "project") {
        const project = projects.find(
          (candidate) =>
            candidate.id === value || candidate.name.toLowerCase() === value.toLowerCase(),
        );
        if (project && !(next.projectId ?? []).includes(project.id)) {
          next = toggleArrayFilter(next, "projectId", project.id);
        } else if (!project) rest.push(token);
      } else if (key === "started" && STARTED_VALUES.has(value as RunsStartedWindow)) {
        if (!(next.started ?? []).includes(value as RunsStartedWindow)) {
          next = toggleStarted(next, value as RunsStartedWindow);
        }
      }
    }
  }
  const q = rest.join(" ");
  if (q) next.q = q;
  else delete next.q;
  return next;
};

export const ARRAY_FILTER_KEYS = ARRAY_KEYS;
export type ArrayFilterKey = ArrayKey;
