/**
 * The workspace Runs tab (Figma L05-1 … L05-3): a filter bar, then one table
 * of every run. The side bar is the filter view (`RunsFacetPanel`); its picks
 * show in the bar as chips and the bar takes the same tokens as an
 * experiment's Runs (`status:` `project:` `target:` `started:` become picks,
 * anything else filters by title, parameters, project or experiment). The
 * count in the bar is the one place the filter's size is said. Selection swaps
 * the bar for the L03 selection bar.
 */

import { ListFilter, ListVideo, RefreshCw, X } from "lucide-react";
import { type JSX, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { isSoftRemoteWait } from "@/api/errors";
import { useCompareSet } from "@/app/compare";
import { itemFromWorkspaceRunRow } from "@/app/compare/entries";
import { EntityPage } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { runLabel } from "@/app/runs/runTitle";
import { SelectionActions } from "@/app/runs/SelectionActions";
import { CHART_GROUPS } from "@/app/status/vocabulary";
import type { WorkspaceSnapshot } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { cn } from "@/lib/utils";
import { applyFilters } from "./aggregates";
import {
  type ArrayFilterKey,
  absorbFacetTokens,
  parseFilterParams,
  toggleArrayFilter,
  toggleStarted,
  writeFilterParams,
} from "./filterParams";
import { runSummaryFromRow } from "./projections";
import type { RunsStartedWindow, WorkspaceRunRow, WorkspaceRunsFilters } from "./types";
import type { MultiSelectState } from "./useRunMultiSelect";
import { useWorkspaceRuns } from "./useWorkspaceRuns";
import {
  DEFAULT_RUNS_SORT,
  type RunsSort,
  WorkspaceRunsTable,
  workspaceRunKey,
} from "./WorkspaceRunsTable";

interface RunsPageProps {
  snapshot: WorkspaceSnapshot;
}

const EMPTY_SELECTION: MultiSelectState = { selected: new Set<string>(), anchor: null };

const parseSort = (raw: string | null): RunsSort => {
  const [column, dir] = (raw ?? "").split(":");
  const columns = ["status", "run", "experiment", "attempt", "time", "age", "target", "id"];
  return column && columns.includes(column)
    ? { column: column as RunsSort["column"], dir: dir === "desc" ? -1 : 1 }
    : DEFAULT_RUNS_SORT;
};

interface Chip {
  key: string;
  label: string;
  remove: (filters: WorkspaceRunsFilters) => WorkspaceRunsFilters;
}

/** The facet picks, as the bar's chips. */
const chipsOf = (
  filters: WorkspaceRunsFilters,
  names: { projects: Map<string, string>; experiments: Map<string, string> },
): Chip[] => {
  const picks = (key: ArrayFilterKey, prefix: string, label: (value: string) => string): Chip[] =>
    (filters[key] ?? []).map((value) => ({
      key: `${key}:${value}`,
      label: `${prefix}:${label(value)}`,
      remove: (current) => toggleArrayFilter(current, key, value),
    }));
  const statusWord = (value: string): string =>
    CHART_GROUPS.find((group) => group.id === value)?.label.toLowerCase() ?? value;
  return [
    ...picks("status", "status", statusWord),
    ...picks("projectId", "project", (value) => names.projects.get(value) ?? value),
    ...picks("experimentId", "experiment", (value) => names.experiments.get(value) ?? value),
    ...picks("target", "target", (value) => value),
    ...picks("backend", "backend", (value) => value),
    ...picks("cluster", "cluster", (value) => value),
    ...(filters.started ?? []).map((window: RunsStartedWindow) => ({
      key: `started:${window}`,
      label: `started:${window}`,
      remove: (current: WorkspaceRunsFilters) => toggleStarted(current, window),
    })),
  ];
};

export const RunsPage = ({ snapshot }: RunsPageProps): JSX.Element => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const filters = useMemo<WorkspaceRunsFilters>(
    () => parseFilterParams(searchParams),
    [searchParams],
  );
  const sort = useMemo(() => parseSort(searchParams.get("sort")), [searchParams]);
  const { rows, truncated, unreachable, loading, error, refresh } = useWorkspaceRuns();
  const filteredRuns = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  const setFilters = useCallback(
    (next: WorkspaceRunsFilters) =>
      setSearchParams((previous) => writeFilterParams(previous, next), { replace: true }),
    [setSearchParams],
  );
  const setSort = (next: RunsSort): void =>
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        if (next.column === DEFAULT_RUNS_SORT.column && next.dir === DEFAULT_RUNS_SORT.dir) {
          params.delete("sort");
        } else {
          params.set("sort", `${next.column}:${next.dir === 1 ? "asc" : "desc"}`);
        }
        return params;
      },
      { replace: true },
    );

  const names = useMemo(
    () => ({
      projects: new Map(rows.map((row) => [row.projectId, row.projectName])),
      experiments: new Map(rows.map((row) => [row.experimentId, row.experimentName])),
    }),
    [rows],
  );
  const chips = chipsOf(filters, names);
  // The bar edits the free tokens; facet tokens are absorbed into picks on ↵ and on blur.
  const [draft, setDraft] = useState(filters.q ?? "");
  useEffect(() => setDraft(filters.q ?? ""), [filters.q]);
  const projects = useMemo(
    () => [...names.projects].map(([id, name]) => ({ id, name })),
    [names.projects],
  );
  const commitDraft = (): void =>
    setFilters(absorbFacetTokens({ ...filters, q: undefined }, draft, projects));

  const compare = useCompareSet();
  const [selection, setSelection] = useState<MultiSelectState>(EMPTY_SELECTION);
  const selectedRows = filteredRuns.filter((run) => selection.selected.has(workspaceRunKey(run)));
  const workspaceLabels = useMemo(
    () => new Map(snapshot.workspaces.map((ws) => [ws.key, ws.label])),
    [snapshot.workspaces],
  );
  const compareSelected = (): void => {
    compare.addMany(
      selectedRows.map((run) =>
        itemFromWorkspaceRunRow(run, {
          key: run.workspaceKey,
          label: workspaceLabels.get(run.workspaceKey) ?? run.workspaceKey,
        }),
      ),
    );
    setSelection(EMPTY_SELECTION);
    navigate("/compare");
  };

  // The highlighted row is the one the Preview shows (L12).
  const preview = usePreview();
  const previewed = preview.target?.kind === "run" ? preview.target : null;
  const previewedKey = previewed
    ? (rows
        .filter(
          (row) =>
            row.id === previewed.runId &&
            (!previewed.workspaceKey || row.workspaceKey === previewed.workspaceKey),
        )
        .map(workspaceRunKey)[0] ?? null)
    : null;
  const runTarget = (run: WorkspaceRunRow): PreviewTarget => ({
    kind: "run",
    runId: run.id,
    projectId: run.projectId,
    experimentId: run.experimentId,
    workspaceKey: run.workspaceKey,
    label: runLabel(run),
  });

  const count =
    filteredRuns.length === rows.length
      ? `${rows.length} runs`
      : `${filteredRuns.length} of ${rows.length} runs`;
  const trouble = [
    truncated ? "the first 1000 shown" : null,
    unreachable.length > 0 ? `${unreachable.join(", ")} unreachable` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <EntityPage
      icon={ListVideo}
      title="Runs"
      actions={
        <WorkbenchIconAction
          label={loading ? "Refreshing runs" : "Refresh runs"}
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw
            aria-hidden
            className={cn("size-icon", loading && "mol-motion-progress-spin")}
          />
        </WorkbenchIconAction>
      }
    >
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        <div
          className={cn(
            "flex min-h-9 shrink-0 flex-wrap items-center gap-2 px-6 py-1",
            selectedRows.length > 0 && "bg-accent-muted",
          )}
        >
          {selectedRows.length > 0 ? (
            <SelectionActions
              runs={selectedRows.map(runSummaryFromRow)}
              compareDisabledReason={null}
              onCompare={compareSelected}
              onClear={() => setSelection(EMPTY_SELECTION)}
              onChanged={() => {
                setSelection(EMPTY_SELECTION);
                refresh();
              }}
            />
          ) : (
            <>
              <div
                className={cn(
                  "flex min-h-6 w-[28rem] max-w-full flex-wrap items-center gap-1 rounded-hairline border bg-background px-2 focus-within:border-ring",
                  chips.length > 0 || filters.q ? "border-accent" : "border-border",
                )}
              >
                <ListFilter aria-hidden className="size-icon-sm shrink-0 text-muted-foreground" />
                {chips.map((chip) => (
                  <span
                    key={chip.key}
                    className="inline-flex h-5 items-center gap-hairline rounded-hairline bg-accent-muted pl-2 font-mono text-label text-foreground"
                  >
                    {chip.label}
                    <button
                      type="button"
                      aria-label={`Remove ${chip.label}`}
                      onClick={() => setFilters(chip.remove(filters))}
                      className="flex size-5 items-center justify-center rounded-hairline text-muted-foreground hover:text-foreground"
                    >
                      <X aria-hidden className="size-3" />
                    </button>
                  </span>
                ))}
                <input
                  type="search"
                  aria-label="Filter runs"
                  placeholder={
                    chips.length > 0
                      ? ""
                      : "Filter  status:  project:  target:  driver:  timestep_fs>"
                  }
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onBlur={commitDraft}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") commitDraft();
                    if (event.key === "Backspace" && draft === "" && chips.length > 0) {
                      setFilters((chips.at(-1) as Chip).remove(filters));
                    }
                  }}
                  className="h-6 min-w-24 flex-1 bg-transparent font-mono text-label text-foreground outline-none placeholder:font-sans placeholder:text-muted-foreground"
                />
              </div>
              <span className="text-label tabular-nums text-muted-foreground">{count}</span>
              {trouble ? (
                <span className="text-label text-muted-foreground">· {trouble}</span>
              ) : null}
            </>
          )}
        </div>
        {error && !loading && !isSoftRemoteWait(error) ? (
          <div className="px-6">
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title="Could not load runs"
              detail={error}
              action={<WorkbenchRetryAction onClick={refresh} />}
            />
          </div>
        ) : null}
        <div className="min-h-0 flex-1 overflow-auto">
          {filteredRuns.length === 0 && !loading ? (
            <p className="px-6 py-4 text-body text-muted-foreground">
              {rows.length === 0
                ? "No runs in this workspace yet. Open an experiment and start a run."
                : "No run matches this filter. Clear it to see every run."}
            </p>
          ) : (
            <WorkspaceRunsTable
              runs={filteredRuns}
              previewedKey={previewedKey}
              onPreview={(run) => preview.preview(runTarget(run))}
              onOpen={(run, background = false) => preview.open(runTarget(run), { background })}
              selection={selection}
              onSelectionChange={setSelection}
              sort={sort}
              onSortChange={setSort}
            />
          )}
        </div>
      </div>
    </EntityPage>
  );
};
