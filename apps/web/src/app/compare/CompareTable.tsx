/**
 * The comparison as a matrix: runs down, parameters and metrics across.
 *
 * Columns group as Parameters then Metrics. Rows follow the Project →
 * Experiment → Run tree. A regex filters run names; checkboxes pick columns.
 *
 * Identical columns hide by default. Varying columns mark only the min and
 * max cells down the column. Numbers stay a dense tabular grid.
 *
 * The matrix is its own scrollport. The shared `<Table>` wrapper adds a second
 * overflow box and clips headers against `h-control`.
 */

import { ArrowUpDown, Equal, GitCompareArrows, ListFilter } from "lucide-react";
import { type JSX, type PointerEvent, useMemo, useState } from "react";

import { EmptyState } from "@/app/components/entity";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchToggleAction,
} from "@/components/workbench";
import { cn } from "@/lib/utils";
import type { RunAllSeries } from "@/plugins/molplot";
import { formatScalar } from "@/plugins/molplot/scalar-format";

import { type CompareEntry, refKey } from "./types";

const MISSING = "—";

export interface MatrixRow {
  key: string;
  kind: "parameter" | "metric";
  values: string[];
  numeric: (number | null)[];
  varies: boolean;
  /** Points behind each cell; >1 means the cell shows the last of a series. */
  counts: number[];
}

export interface RowGroup {
  key: string;
  label: string;
  count: number;
}

const formatCell = (raw: unknown): string => {
  if (raw === undefined || raw === null) return MISSING;
  if (typeof raw === "number") return formatScalar(raw);
  if (typeof raw === "object") return JSON.stringify(raw);
  return String(raw);
};

const toNumeric = (raw: unknown): number | null =>
  typeof raw === "number" && Number.isFinite(raw) ? raw : null;

const experimentKey = (entry: CompareEntry): string =>
  `${entry.ref.workspaceKey}\0${entry.ref.projectId}\0${entry.ref.experimentId}`;

export type RunSortKey = "run" | "experiment" | "project";

export const RUN_SORT_KEYS: readonly RunSortKey[] = ["run", "experiment", "project"];

export const nextRunSort = (key: RunSortKey): RunSortKey =>
  RUN_SORT_KEYS[(RUN_SORT_KEYS.indexOf(key) + 1) % RUN_SORT_KEYS.length] ?? "run";

/** Order runs by the chosen entity name, then the remaining names. */
export const sortEntries = (entries: readonly CompareEntry[], key: RunSortKey): CompareEntry[] => {
  const rank = (entry: CompareEntry): string[] => {
    if (key === "run") return [entry.runName, entry.experimentName, entry.projectName];
    if (key === "experiment") return [entry.experimentName, entry.runName, entry.projectName];
    return [entry.projectName, entry.experimentName, entry.runName];
  };
  return [...entries].sort((left, right) => {
    const a = rank(left);
    const b = rank(right);
    for (let index = 0; index < a.length; index += 1) {
      const compared = (a[index] ?? "").localeCompare(b[index] ?? "");
      if (compared !== 0) return compared;
    }
    return 0;
  });
};

/** Stable regroup: experiments stay contiguous, order inside an experiment is kept. */
export const groupedEntries = (entries: readonly CompareEntry[]): CompareEntry[] => {
  const buckets = new Map<string, CompareEntry[]>();
  const order: string[] = [];
  for (const entry of entries) {
    const key = experimentKey(entry);
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(entry);
      continue;
    }
    buckets.set(key, [entry]);
    order.push(key);
  }
  return order.flatMap((key) => buckets.get(key) ?? []);
};

/** Consecutive experiment groups for row headers. One group → no extra row. */
export const rowGroups = (entries: readonly CompareEntry[]): RowGroup[] => {
  const showProject = new Set(entries.map((entry) => entry.ref.projectId)).size > 1;
  const groups: RowGroup[] = [];
  for (const entry of entries) {
    const key = experimentKey(entry);
    const last = groups[groups.length - 1];
    if (last?.key === key) {
      last.count += 1;
      continue;
    }
    groups.push({
      key,
      label: showProject ? `${entry.projectName} · ${entry.experimentName}` : entry.experimentName,
      count: 1,
    });
  }
  return groups;
};

export const rowExtrema = (
  numeric: readonly (number | null)[],
): { min: number; max: number } | null => {
  const nums = numeric.filter((value): value is number => value !== null);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  if (min === max) return null;
  return { min, max };
};

/** Compile a run-name filter. Empty matches all; a broken pattern falls back to substring. */
export const compileRunFilter = (source: string): ((name: string) => boolean) => {
  const trimmed = source.trim();
  if (!trimmed) return () => true;
  try {
    const pattern = new RegExp(trimmed);
    return (name) => pattern.test(name);
  } catch {
    return (name) => name.includes(trimmed);
  }
};

export const sliceMeasure = (measure: MatrixRow, indices: readonly number[]): MatrixRow => {
  const values = indices.map((index) => measure.values[index] ?? MISSING);
  const numeric = indices.map((index) => measure.numeric[index] ?? null);
  const counts = indices.map((index) => measure.counts[index] ?? 0);
  return {
    ...measure,
    values,
    numeric,
    counts,
    varies: new Set(values).size > 1,
  };
};

/** Parameter columns, straight off the set — no metrics read required. */
export const parameterRows = (entries: readonly CompareEntry[]): MatrixRow[] => {
  const keys: string[] = [];
  const seen = new Set<string>();
  for (const entry of entries) {
    for (const key of Object.keys(entry.parameters ?? {})) {
      if (!seen.has(key)) {
        seen.add(key);
        keys.push(key);
      }
    }
  }
  return keys.map((key) => {
    const raw = entries.map((entry) => entry.parameters?.[key]);
    const values = raw.map(formatCell);
    const numeric = raw.map(toNumeric);
    return {
      key,
      kind: "parameter" as const,
      values,
      numeric,
      varies: new Set(values).size > 1,
      counts: entries.map(() => 1),
    };
  });
};

/**
 * Metric columns in the order keys first appear, then sorted.
 *
 * A run that logged a series contributes its **last** value — the converged
 * number is what a table is asked for; the shape of getting there is the
 * chart's job.
 */
export const metricRows = (
  perRunAll: readonly RunAllSeries[],
  columnKeys: readonly string[],
): MatrixRow[] => {
  const byRun = new Map(perRunAll.map((row) => [row.key, row]));
  const keys: string[] = [];
  const seen = new Set<string>();
  for (const row of perRunAll) {
    for (const series of row.series) {
      if (!seen.has(series.key)) {
        seen.add(series.key);
        keys.push(series.key);
      }
    }
  }
  keys.sort();

  return keys.map((key) => {
    const values: string[] = [];
    const numeric: (number | null)[] = [];
    const counts: number[] = [];
    for (const column of columnKeys) {
      const series = byRun.get(column)?.series.find((item) => item.key === key);
      if (!series || series.points.length === 0) {
        values.push(MISSING);
        numeric.push(null);
        counts.push(0);
        continue;
      }
      const last = series.points[series.points.length - 1].y;
      values.push(formatScalar(last));
      numeric.push(last);
      counts.push(series.points.length);
    }
    return {
      key,
      kind: "metric" as const,
      values,
      numeric,
      varies: new Set(values).size > 1,
      counts,
    };
  });
};

/** Hide measures that do not differ, unless that would empty the set. */
export const visibleRows = (rows: readonly MatrixRow[], showIdentical: boolean): MatrixRow[] => {
  if (showIdentical) return [...rows];
  const varied = rows.filter((row) => row.varies);
  return varied.length > 0 ? varied : [...rows];
};

export const clampWidth = (px: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, Math.round(px)));

const RUN_MIN = 96;
const RUN_MAX = 480;
const COL_MIN = 48;
const COL_MAX = 480;
const ROW_MIN = 24;
const ROW_MAX = 80;
const ROW_DEFAULT = 28;

const beginDrag = (
  event: PointerEvent<HTMLElement>,
  origin: number,
  axis: "x" | "y",
  apply: (delta: number) => void,
): void => {
  event.preventDefault();
  event.stopPropagation();
  const pointer = event.pointerId;
  const onMove = (next: globalThis.PointerEvent): void => {
    if (next.pointerId !== pointer) return;
    apply((axis === "x" ? next.clientX : next.clientY) - origin);
  };
  const onUp = (next: globalThis.PointerEvent): void => {
    if (next.pointerId !== pointer) return;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
  };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
  window.addEventListener("pointercancel", onUp);
};

const EdgeResize = ({
  orientation,
  size,
  min,
  max,
  onSize,
}: {
  orientation: "vertical" | "horizontal";
  size: number;
  min: number;
  max: number;
  onSize: (px: number) => void;
}): JSX.Element => (
  <span
    aria-hidden
    className={
      orientation === "vertical"
        ? "absolute inset-y-0 -right-1 z-30 w-2 cursor-col-resize hover:bg-accent"
        : "absolute inset-x-0 -bottom-1 z-30 h-2 cursor-row-resize hover:bg-accent"
    }
    onPointerDown={(event) => {
      const start = size;
      const origin = orientation === "vertical" ? event.clientX : event.clientY;
      beginDrag(event, origin, orientation === "vertical" ? "x" : "y", (delta) =>
        onSize(clampWidth(start + delta, min, max)),
      );
    }}
    onDoubleClick={(event) => {
      event.preventDefault();
      event.stopPropagation();
      onSize(0);
    }}
  />
);

const MeasureChecks = ({
  measures,
  hidden,
  onToggle,
}: {
  measures: MatrixRow[];
  hidden: ReadonlySet<string>;
  onToggle: (key: string, on: boolean) => void;
}): JSX.Element | null => {
  if (measures.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      {measures.map((measure) => {
        const id = `compare-col-${measure.kind}-${measure.key}`;
        return (
          <div key={measure.key} className="flex min-w-0 items-center gap-1 text-micro">
            <Checkbox
              id={id}
              checked={!hidden.has(measure.key)}
              onCheckedChange={(value) => onToggle(measure.key, value === true)}
            />
            <label htmlFor={id} className="min-w-0 truncate font-mono" title={measure.key}>
              {measure.key}
            </label>
          </div>
        );
      })}
    </div>
  );
};

export interface CompareTableProps {
  entries: CompareEntry[];
  perRunAll: RunAllSeries[];
  scanned: boolean;
  onOpenMetric?: (metricKey: string) => void;
}

export const CompareTable = ({
  entries,
  perRunAll,
  scanned,
  onOpenMetric,
}: CompareTableProps): JSX.Element => {
  const [showIdentical, setShowIdentical] = useState(false);
  const [runQuery, setRunQuery] = useState("");
  const [sortKey, setSortKey] = useState<RunSortKey>("run");
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [runWidth, setRunWidth] = useState(0);
  const [colWidths, setColWidths] = useState<Record<string, number>>({});
  const [rowHeight, setRowHeight] = useState(ROW_DEFAULT);

  const ordered = useMemo(() => groupedEntries(sortEntries(entries, sortKey)), [entries, sortKey]);
  const entryKeys = useMemo(() => ordered.map((entry) => refKey(entry.ref)), [ordered]);
  const parameters = useMemo(() => parameterRows(ordered), [ordered]);
  const metrics = useMemo(() => metricRows(perRunAll, entryKeys), [perRunAll, entryKeys]);

  const matchRun = useMemo(() => compileRunFilter(runQuery), [runQuery]);
  const visibleRuns = useMemo(
    () => ordered.filter((entry) => matchRun(entry.runName)),
    [ordered, matchRun],
  );
  const visibleIndices = useMemo(
    () => visibleRuns.map((entry) => ordered.indexOf(entry)),
    [visibleRuns, ordered],
  );
  const groups = useMemo(() => rowGroups(visibleRuns), [visibleRuns]);
  const grouped = groups.length > 1;

  const sliced = useMemo(
    () => [...parameters, ...metrics].map((measure) => sliceMeasure(measure, visibleIndices)),
    [parameters, metrics, visibleIndices],
  );
  const columns = useMemo(() => {
    const picked = sliced.filter((measure) => !hidden.has(measure.key));
    return visibleRows(picked, showIdentical);
  }, [sliced, hidden, showIdentical]);
  const paramCols = columns.filter((measure) => measure.kind === "parameter");
  const metricCols = columns.filter((measure) => measure.kind === "metric");
  const splitHeader = paramCols.length > 0 && metricCols.length > 0;

  const extrema = useMemo(
    () => columns.map((measure) => (measure.varies ? rowExtrema(measure.numeric) : null)),
    [columns],
  );
  const blocks = useMemo(() => {
    let offset = 0;
    return groups.map((group) => {
      const runs = visibleRuns.slice(offset, offset + group.count);
      const start = offset;
      offset += group.count;
      return { group, runs, start };
    });
  }, [groups, visibleRuns]);

  const toggleColumn = (key: string, on: boolean): void => {
    setHidden((current) => {
      const next = new Set(current);
      if (on) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const setColWidth = (key: string, px: number): void => {
    setColWidths((current) => {
      if (px <= 0) {
        const next = { ...current };
        delete next[key];
        return next;
      }
      return { ...current, [key]: px };
    });
  };

  const colWidth = (key: string): number | undefined => colWidths[key];
  const runColStyle =
    runWidth > 0 ? { width: runWidth, minWidth: runWidth } : { minWidth: RUN_MIN };

  const openMetric = (key: string): void => {
    onOpenMetric?.(key);
  };

  if (ordered.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <EmptyState icon={<GitCompareArrows className="size-icon-lg" />} title="No runs" />
      </div>
    );
  }

  if (parameters.length === 0 && metrics.length === 0) {
    if (!scanned) {
      return <WorkbenchOperationState kind="loading" skeletonRows={8} />;
    }
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <EmptyState icon={<GitCompareArrows className="size-icon-lg" />} title="Nothing recorded" />
      </div>
    );
  }

  const columnFilter = (kind: "parameter" | "metric"): JSX.Element => (
    <Popover>
      <PopoverTrigger asChild>
        <WorkbenchIconAction label={kind === "parameter" ? "Parameters" : "Metrics"}>
          <ListFilter className="size-icon-sm" />
        </WorkbenchIconAction>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="flex max-h-80 w-72 flex-col gap-2 overflow-y-auto p-3"
      >
        <MeasureChecks
          measures={kind === "parameter" ? parameters : metrics}
          hidden={hidden}
          onToggle={toggleColumn}
        />
        {kind === "metric" ? (
          <WorkbenchToggleAction
            label="Show identical columns"
            pressed={showIdentical}
            onClick={() => setShowIdentical((current) => !current)}
          >
            <Equal className="size-icon-sm" />
          </WorkbenchToggleAction>
        ) : null}
      </PopoverContent>
    </Popover>
  );

  const runHeader = (
    <TableHead
      rowSpan={splitHeader ? 2 : 1}
      className="relative sticky left-0 top-0 z-30 border-border/60 border-r border-b bg-background px-1 py-1"
      style={runColStyle}
    >
      <div className="flex min-w-0 items-center gap-1 pr-2">
        <Input
          aria-label="Runs"
          value={runQuery}
          onChange={(event) => setRunQuery(event.target.value)}
          className="h-control-compact min-w-0 flex-1 border-0 bg-transparent px-1 font-mono text-micro shadow-none focus-visible:ring-0"
        />
        <WorkbenchIconAction
          label={`Sort by ${sortKey}`}
          onClick={() => setSortKey((current) => nextRunSort(current))}
        >
          <ArrowUpDown className="size-icon-sm" />
        </WorkbenchIconAction>
        {splitHeader ? null : columnFilter("metric")}
        {splitHeader ? null : (
          <WorkbenchToggleAction
            label="Show identical columns"
            pressed={showIdentical}
            onClick={() => setShowIdentical((current) => !current)}
          >
            <Equal className="size-icon-sm" />
          </WorkbenchToggleAction>
        )}
      </div>
      <EdgeResize
        orientation="vertical"
        size={runWidth > 0 ? runWidth : RUN_MIN}
        min={RUN_MIN}
        max={RUN_MAX}
        onSize={setRunWidth}
      />
    </TableHead>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-max min-w-full border-separate border-spacing-0 text-micro">
          <colgroup>
            <col style={runWidth > 0 ? { width: runWidth } : undefined} />
            {columns.map((measure) => (
              <col
                key={`${measure.kind}:${measure.key}`}
                style={colWidth(measure.key) ? { width: colWidth(measure.key) } : undefined}
              />
            ))}
          </colgroup>
          <TableHeader>
            {splitHeader ? (
              <TableRow>
                {runHeader}
                <TableHead
                  colSpan={paramCols.length}
                  className="sticky top-0 z-20 h-control-compact border-border/60 border-r border-b bg-background px-1 py-0 text-center font-medium text-micro text-muted-foreground"
                >
                  <div className="flex items-center justify-center gap-1">
                    <span>Parameters</span>
                    {columnFilter("parameter")}
                  </div>
                </TableHead>
                <TableHead
                  colSpan={metricCols.length}
                  className="sticky top-0 z-20 h-control-compact border-border/60 border-b bg-background px-1 py-0 text-center font-medium text-micro text-muted-foreground last:border-r-0"
                >
                  <div className="flex items-center justify-center gap-1">
                    <span>Metrics</span>
                    {columnFilter("metric")}
                  </div>
                </TableHead>
              </TableRow>
            ) : null}
            <TableRow>
              {splitHeader ? null : runHeader}
              {columns.map((measure) => {
                const width = colWidth(measure.key);
                return (
                  <TableHead
                    key={`${measure.kind}:${measure.key}`}
                    className={cn(
                      "relative sticky z-20 border-border/60 border-r border-b bg-background px-1 py-0 last:border-r-0",
                      splitHeader ? "top-control-compact" : "top-0",
                    )}
                    style={width ? { width, minWidth: width } : { minWidth: COL_MIN }}
                  >
                    {measure.kind === "metric" ? (
                      <button
                        type="button"
                        title={measure.key}
                        className="flex h-control-compact w-full min-w-0 items-center justify-center truncate font-mono text-micro text-foreground hover:text-accent"
                        onClick={() => openMetric(measure.key)}
                      >
                        {measure.key}
                      </button>
                    ) : (
                      <span
                        title={measure.key}
                        className="flex h-control-compact w-full min-w-0 items-center justify-center truncate font-mono text-micro text-muted-foreground"
                      >
                        {measure.key}
                      </span>
                    )}
                    <EdgeResize
                      orientation="vertical"
                      size={width ?? COL_MIN}
                      min={COL_MIN}
                      max={COL_MAX}
                      onSize={(px) => setColWidth(measure.key, px)}
                    />
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {blocks.map(({ group, runs, start }) => (
              <GroupRows
                key={group.key}
                label={grouped ? group.label : null}
                runs={runs}
                start={start}
                columns={columns}
                extrema={extrema}
                runWidth={runWidth}
                rowHeight={rowHeight}
                onRowHeight={setRowHeight}
                onRunWidth={setRunWidth}
                onOpenMetric={openMetric}
              />
            ))}
          </TableBody>
        </table>
      </div>
    </div>
  );
};

const GroupRows = ({
  label,
  runs,
  start,
  columns,
  extrema,
  runWidth,
  rowHeight,
  onRowHeight,
  onRunWidth,
  onOpenMetric,
}: {
  label: string | null;
  runs: CompareEntry[];
  start: number;
  columns: MatrixRow[];
  extrema: ({ min: number; max: number } | null)[];
  runWidth: number;
  rowHeight: number;
  onRowHeight: (px: number) => void;
  onRunWidth: (px: number) => void;
  onOpenMetric: (metricKey: string) => void;
}): JSX.Element => (
  <>
    {runs.map((entry, offset) => {
      const index = start + offset;
      const groupStart = offset === 0 && label;
      return (
        <TableRow
          key={refKey(entry.ref)}
          className="border-border/40 border-b last:border-b-0"
          style={{ height: rowHeight }}
        >
          <TableHead
            scope="row"
            className="relative sticky left-0 z-10 border-border/60 border-r bg-background px-1 py-0 text-left align-middle font-mono text-micro text-foreground"
            style={runWidth > 0 ? { width: runWidth, minWidth: runWidth } : { minWidth: RUN_MIN }}
          >
            <div className="min-w-0 pr-1">
              {groupStart ? (
                <div className="truncate text-micro text-muted-foreground">{label}</div>
              ) : null}
              <div className="truncate" title={entry.runName}>
                {entry.runName}
              </div>
            </div>
            <EdgeResize
              orientation="vertical"
              size={runWidth > 0 ? runWidth : RUN_MIN}
              min={RUN_MIN}
              max={RUN_MAX}
              onSize={onRunWidth}
            />
            <EdgeResize
              orientation="horizontal"
              size={rowHeight}
              min={ROW_MIN}
              max={ROW_MAX}
              onSize={onRowHeight}
            />
          </TableHead>
          {columns.map((measure, columnIndex) => {
            const value = measure.values[index] ?? MISSING;
            const number = measure.numeric[index] ?? null;
            const bound = extrema[columnIndex];
            const isMin = bound !== null && number === bound.min;
            const isMax = bound !== null && number === bound.max;
            const chartable = measure.kind === "metric";
            return (
              <TableCell
                key={`${measure.kind}:${measure.key}`}
                title={measure.counts[index] > 1 ? `${value} · ${measure.counts[index]}` : value}
                className={cn(
                  "min-w-0 border-border/40 border-r px-1 py-0 text-right font-mono text-micro tabular-nums last:border-r-0",
                  chartable && "cursor-pointer hover:bg-interactive/50",
                  isMax && "bg-diff-modified-soft text-foreground",
                  isMin && "bg-muted/60 text-foreground",
                  value === MISSING && "text-muted-foreground/50",
                )}
                onClick={chartable ? () => onOpenMetric(measure.key) : undefined}
              >
                <span className="block truncate">{value}</span>
              </TableCell>
            );
          })}
        </TableRow>
      );
    })}
  </>
);
