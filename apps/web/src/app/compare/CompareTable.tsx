/**
 * The comparison as a matrix: metrics down, runs across.
 *
 * Most runs here do not log a curve. They log a handful of one-off scalars —
 * a final energy, a peak memory, a wall time — and one number per run is a
 * table, not a chart. Plotting a single point per series says nothing that the
 * number itself does not say better.
 *
 * Metric keys are rows and runs are columns, matching `ExperimentCompare`:
 * a sweep has few runs and many measurements, so the long axis has to be the
 * one that scrolls. Rows whose values differ are marked, because the reason to
 * open a comparison is to find the rows that are not identical.
 *
 * Parameters need no scan — the set already carries them — so they render
 * immediately, and the metrics section fills in once the runs are read.
 */

import { GitCompareArrows } from "lucide-react";
import { type JSX, useMemo } from "react";

import { EmptyState } from "@/app/components/entity";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { RunAllSeries } from "@/plugins/molplot";
import { formatScalar } from "@/plugins/molplot/scalar-format";

import { shortestUniqueLabels } from "./labels";
import { type CompareEntry, refKey } from "./types";

const MISSING = "—";

export interface MatrixRow {
  key: string;
  values: string[];
  varies: boolean;
  /** Points behind each cell; >1 means the cell shows the last of a series. */
  counts: number[];
}

const formatCell = (raw: unknown): string => {
  if (raw === undefined || raw === null) return MISSING;
  if (typeof raw === "number") return formatScalar(raw);
  if (typeof raw === "object") return JSON.stringify(raw);
  return String(raw);
};

/** Parameter rows, straight off the set — no metrics read required. */
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
    const values = entries.map((entry) => formatCell(entry.parameters?.[key]));
    return { key, values, varies: new Set(values).size > 1, counts: entries.map(() => 1) };
  });
};

/**
 * Metric rows in the column order the caller passes.
 *
 * A run that logged a series contributes its **last** value — the converged
 * number is what a table is asked for; the shape of getting there is the
 * chart's job, and the point count is shown so a series is not mistaken for a
 * single measurement.
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
    const counts: number[] = [];
    for (const column of columnKeys) {
      const series = byRun.get(column)?.series.find((s) => s.key === key);
      if (!series || series.points.length === 0) {
        values.push(MISSING);
        counts.push(0);
        continue;
      }
      values.push(formatScalar(series.points[series.points.length - 1].y));
      counts.push(series.points.length);
    }
    return { key, values, varies: new Set(values).size > 1, counts };
  });
};

const Section = ({
  title,
  rows,
  columnKeys,
  note,
  onOpenRow,
}: {
  title: string;
  rows: MatrixRow[];
  columnKeys: string[];
  note?: string;
  /** When given, clicking the row opens that measurement's own chart. */
  onOpenRow?: (key: string) => void;
}): JSX.Element | null => {
  if (rows.length === 0) return null;
  const varied = rows.filter((row) => row.varies).length;
  return (
    <>
      <TableRow>
        <TableCell
          colSpan={columnKeys.length + 1}
          className="border-border/60 border-b bg-muted/40 px-3 py-2 font-semibold text-micro text-muted-foreground uppercase tracking-wide"
        >
          {title}
          <span className="ml-2 font-normal normal-case text-muted-foreground/70">
            {note ?? (varied > 0 ? `${varied} differ` : "all identical")}
          </span>
        </TableCell>
      </TableRow>
      {rows.map((row) => (
        <TableRow
          key={`${title}:${row.key}`}
          className={cn(
            "border-border/40 border-b last:border-b-0",
            row.varies && "bg-diff-modified-soft",
            onOpenRow && "cursor-pointer hover:bg-muted/40",
          )}
          onClick={onOpenRow ? () => onOpenRow(row.key) : undefined}
          tabIndex={onOpenRow ? 0 : undefined}
          aria-label={onOpenRow ? `Chart ${row.key} across the selected runs` : undefined}
          onKeyDown={
            onOpenRow
              ? (event) => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  onOpenRow(row.key);
                }
              : undefined
          }
        >
          <TableHead
            scope="row"
            className={cn(
              "sticky left-0 z-10 max-w-44 truncate border-border/60 border-r bg-background px-3 py-2 text-left align-top font-medium font-mono text-label",
              row.varies
                ? "border-l border-l-diff-modified text-foreground"
                : "text-muted-foreground",
            )}
            title={row.key}
          >
            {row.key}
          </TableHead>
          {row.values.map((value, index) => (
            <TableCell
              key={`${row.key}:${columnKeys[index] ?? index}`}
              className={cn(
                "border-border/40 border-r px-3 py-2 align-top font-mono text-label last:border-r-0",
                row.varies ? "text-foreground" : "text-muted-foreground",
                value === MISSING && "text-muted-foreground/50",
              )}
            >
              <span className="block max-w-52 truncate" title={value}>
                {value}
                {row.counts[index] > 1 && (
                  <span className="ml-1 text-micro text-muted-foreground/70">
                    ({row.counts[index]} pts)
                  </span>
                )}
              </span>
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
};

export interface CompareTableProps {
  entries: CompareEntry[];
  perRunAll: RunAllSeries[];
  scanned: boolean;
  /** Open one metric's chart. Parameters have no chart and stay inert. */
  onOpenMetric?: (metricKey: string) => void;
}

export const CompareTable = ({
  entries,
  perRunAll,
  scanned,
  onOpenMetric,
}: CompareTableProps): JSX.Element => {
  const labels = useMemo(() => shortestUniqueLabels(entries), [entries]);
  const columnKeys = useMemo(() => entries.map((entry) => refKey(entry.ref)), [entries]);
  const params = useMemo(() => parameterRows(entries), [entries]);
  const metrics = useMemo(() => metricRows(perRunAll, columnKeys), [perRunAll, columnKeys]);

  if (params.length === 0 && metrics.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={<GitCompareArrows className="h-6 w-6" />}
          title={scanned ? "Nothing recorded" : "Read the runs' metrics"}
          description={
            scanned
              ? "The selected runs carry neither parameters nor scalar metrics."
              : "Refresh above to read each run's measurements. Parameters appear without a read."
          }
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <Table className="w-auto min-w-full border-separate border-spacing-0 text-body">
        <TableHeader>
          <TableRow>
            <TableHead className="sticky left-0 top-0 z-20 border-border/60 border-r border-b bg-background px-3 py-2 text-left font-medium text-label text-muted-foreground">
              {entries.length} runs
            </TableHead>
            {entries.map((entry) => {
              const key = refKey(entry.ref);
              return (
                <TableHead
                  key={key}
                  className="sticky top-0 z-10 max-w-52 border-border/60 border-r border-b bg-background px-3 py-2 text-left align-bottom last:border-r-0"
                >
                  {/* Column labels are shortened to whatever tells the set
                      apart and then truncated to fit, so the full ancestry has
                      to be reachable on hover — otherwise two columns from
                      different projects can read identically. */}
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="min-w-0 cursor-default">
                        <span className="block truncate font-medium font-mono text-foreground text-label">
                          {labels.get(key) ?? entry.runName}
                        </span>
                        <span className="block truncate text-micro text-muted-foreground">
                          {entry.experimentName}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-md">
                      <span className="font-mono text-micro">
                        {entry.workspaceLabel} / {entry.projectName} / {entry.experimentName} /{" "}
                        {entry.runName}
                        {entry.executionId ? ` / ${entry.executionId}` : ""}
                      </span>
                    </TooltipContent>
                  </Tooltip>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          <Section title="Parameters" rows={params} columnKeys={columnKeys} />
          <Section
            title="Metrics"
            rows={metrics}
            columnKeys={columnKeys}
            note={scanned ? "click a row to chart it" : "refresh to fill in"}
            onOpenRow={onOpenMetric}
          />
        </TableBody>
      </Table>
    </div>
  );
};
