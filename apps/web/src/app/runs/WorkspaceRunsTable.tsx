/**
 * The workspace Runs table (Figma L05-1 … L05-3, L05-8): one 24px row per run —
 * status glyph · title · project › experiment · latest attempt (eNN · mode) ·
 * time · age · target · id. Every column sorts. A click previews (L12),
 * double-click or ↵ opens, ⌘↵ opens in the background, ↑↓ moves the Preview;
 * a checkbox or ⌘ / ⇧ click selects. On a phone a row is two lines: the
 * title, then experiment · time · age.
 */

import { ChevronDown, ChevronUp, Laptop, Server } from "lucide-react";
import { type JSX, type KeyboardEvent, type MouseEvent, useMemo, useState } from "react";
import { formatSpan, StatusIcon } from "@/app/components/entity";
import { normalizeStatus, STATUS } from "@/app/status/vocabulary";
import { formatRelative, parseInstant } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import { runExecutorFacet, runPresentationStatus, runStartedAt } from "./projections";
import { runLabel } from "./runTitle";
import type { WorkspaceRunRow } from "./types";
import { type MultiSelectState, nextSelection } from "./useRunMultiSelect";

/** A run's key across served workspaces. */
export const workspaceRunKey = (run: Pick<WorkspaceRunRow, "workspaceKey" | "id">): string =>
  `${run.workspaceKey}:${run.id}`;

interface Row {
  run: WorkspaceRunRow;
  key: string;
  title: string;
  status: string;
  attempt: string | null;
  seconds: number | null;
  /** When it started (or was created), epoch ms. */
  at: number | null;
  target: string | null;
}

const STATUS_ORDER = [
  "failed",
  "interrupted",
  "running",
  "finalizing",
  "queued",
  "pending",
  "cancelled",
  "succeeded",
];

const latestOf = (run: WorkspaceRunRow) =>
  [...run.executions]
    .sort(
      (left, right) =>
        (parseInstant(left.startedAt ?? left.createdAt) ?? 0) -
        (parseInstant(right.startedAt ?? right.createdAt) ?? 0),
    )
    .at(-1) ?? null;

const rowOf = (run: WorkspaceRunRow, now: number): Row => {
  const latest = latestOf(run);
  const start = parseInstant(latest?.startedAt ?? null);
  const end = parseInstant(latest?.finishedAt ?? null);
  return {
    run,
    key: workspaceRunKey(run),
    title: runLabel(run),
    status: runPresentationStatus(run),
    attempt: latest ? `${latest.executionId} · ${latest.mode}` : null,
    seconds:
      latest?.durationSeconds ?? (start === null ? null : Math.max(0, (end ?? now) - start) / 1000),
    at: parseInstant(runStartedAt(run) ?? run.createdAt),
    target: runExecutorFacet(run, "target")[0] ?? run.targetHint ?? latest?.backend ?? null,
  };
};

type Column = "status" | "run" | "experiment" | "attempt" | "time" | "age" | "target" | "id";
export interface RunsSort {
  column: Column;
  dir: 1 | -1;
}
export const DEFAULT_RUNS_SORT: RunsSort = { column: "age", dir: 1 };

const sortValue = (row: Row, column: Column): unknown => {
  switch (column) {
    case "status":
      return STATUS_ORDER.indexOf(normalizeStatus(row.status));
    case "run":
      return row.title;
    case "experiment":
      return `${row.run.projectName} ${row.run.experimentName}`;
    case "attempt":
      return row.attempt;
    case "time":
      return row.seconds;
    case "age":
      // Newest first reads as “age ascending”.
      return row.at === null ? null : -row.at;
    case "target":
      return row.target;
    case "id":
      return row.run.id;
  }
};

const compare = (left: unknown, right: unknown): number => {
  if (left === right) return 0;
  if (left === null || left === undefined) return 1;
  if (right === null || right === undefined) return -1;
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), undefined, { numeric: true });
};

export interface WorkspaceRunsTableProps {
  runs: readonly WorkspaceRunRow[];
  /** The run the Preview shows. */
  previewedKey: string | null;
  onPreview: (run: WorkspaceRunRow) => void;
  onOpen: (run: WorkspaceRunRow, background?: boolean) => void;
  selection: MultiSelectState;
  onSelectionChange: (next: MultiSelectState) => void;
  sort: RunsSort;
  onSortChange: (next: RunsSort) => void;
}

const HEADERS: readonly { column: Column; label: string; numeric?: boolean; className?: string }[] =
  [
    { column: "status", label: "", className: "w-6" },
    { column: "run", label: "run" },
    { column: "experiment", label: "experiment", className: "max-sm:hidden" },
    { column: "attempt", label: "attempt", className: "max-md:hidden" },
    { column: "time", label: "time", numeric: true, className: "max-sm:hidden" },
    { column: "age", label: "age", numeric: true, className: "max-sm:hidden" },
    { column: "target", label: "target", className: "max-md:hidden" },
    { column: "id", label: "id", className: "max-lg:hidden" },
  ];

export const WorkspaceRunsTable = ({
  runs,
  previewedKey,
  onPreview,
  onOpen,
  selection,
  onSelectionChange,
  sort,
  onSortChange,
}: WorkspaceRunsTableProps): JSX.Element => {
  const [now] = useState(() => Date.now());
  const rows = useMemo(() => {
    const built = runs.map((run) => rowOf(run, now));
    return built.sort(
      (left, right) =>
        compare(sortValue(left, sort.column), sortValue(right, sort.column)) * sort.dir ||
        compare(left.title, right.title),
    );
  }, [runs, now, sort]);
  const order = useMemo(() => rows.map((row) => row.key), [rows]);
  const select = (index: number, modifiers: { shift: boolean; meta: boolean }): void =>
    onSelectionChange(nextSelection(selection, index, order, modifiers));
  const allSelected = rows.length > 0 && rows.every((row) => selection.selected.has(row.key));

  const onRowClick = (event: MouseEvent, row: Row, index: number): void => {
    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      select(index, { shift: event.shiftKey, meta: event.metaKey || event.ctrlKey });
      return;
    }
    onPreview(row.run);
  };
  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, row: Row, index: number): void => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = rows[index + (event.key === "ArrowDown" ? 1 : -1)];
      const element =
        event.key === "ArrowDown"
          ? event.currentTarget.nextElementSibling
          : event.currentTarget.previousElementSibling;
      if (next && element instanceof HTMLElement) {
        element.focus();
        onPreview(next.run);
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      onOpen(row.run, event.metaKey || event.ctrlKey);
    } else if (event.key === " ") {
      event.preventDefault();
      select(index, { shift: event.shiftKey, meta: true });
    }
  };

  return (
    <table aria-label="Runs" className="w-full border-collapse text-body">
      <thead className="sticky top-0 z-10 border-b border-border bg-background text-label text-muted-foreground">
        <tr>
          <th scope="col" className="h-7 w-10 pl-6">
            <input
              type="checkbox"
              aria-label={allSelected ? "Deselect all runs" : "Select all runs"}
              checked={allSelected}
              onChange={() =>
                onSelectionChange({
                  selected: allSelected ? new Set() : new Set(order),
                  anchor: null,
                })
              }
              className="size-3.5 accent-accent"
            />
          </th>
          {HEADERS.map((header) => {
            const active = sort.column === header.column;
            const Arrow = sort.dir === 1 ? ChevronUp : ChevronDown;
            return (
              <th
                key={header.column}
                scope="col"
                aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                className={cn(
                  "h-7 px-2 font-normal",
                  header.numeric ? "text-right" : "text-left",
                  header.className,
                )}
              >
                <button
                  type="button"
                  title={header.column === "status" ? "Sort by status" : undefined}
                  onClick={() =>
                    onSortChange({
                      column: header.column,
                      dir: active ? (sort.dir === 1 ? -1 : 1) : 1,
                    })
                  }
                  className={cn(
                    "inline-flex items-center gap-hairline rounded-hairline hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                    header.numeric && "flex-row-reverse",
                    active && "text-foreground",
                  )}
                >
                  {header.label}
                  {active ? <Arrow aria-hidden className="size-3" /> : null}
                </button>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => {
          const selected = selection.selected.has(row.key);
          const previewed = previewedKey === row.key;
          return (
            <tr
              key={row.key}
              tabIndex={0}
              aria-selected={selected}
              aria-label={`${row.title} · ${STATUS[normalizeStatus(row.status)].word}`}
              onClick={(event) => onRowClick(event, row, index)}
              onDoubleClick={(event) => {
                if ((event.target as HTMLElement).closest("input")) return;
                onOpen(row.run);
              }}
              onKeyDown={(event) => onRowKey(event, row, index)}
              className={cn(
                "h-6 cursor-default outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring max-sm:h-auto",
                selected && "bg-accent-muted hover:bg-accent-muted",
                previewed &&
                  !selected &&
                  "bg-interactive shadow-[inset_2px_0_0_var(--molab-accent)]",
              )}
            >
              <td className="pl-6">
                <input
                  type="checkbox"
                  aria-label={`${selected ? "Deselect" : "Select"} ${row.title}`}
                  checked={selected}
                  onClick={(event) => event.stopPropagation()}
                  onChange={() => select(index, { shift: false, meta: true })}
                  className="size-3.5 accent-accent"
                />
              </td>
              <td className="w-6 px-2">
                <StatusIcon status={row.status} className="size-icon-sm" />
              </td>
              <td className="max-w-[20rem] px-2 max-sm:max-w-60 max-sm:py-1">
                <span className="block truncate font-mono" title={row.title}>
                  {row.title}
                </span>
                <span className="block truncate text-label text-muted-foreground sm:hidden">
                  {row.run.experimentName}
                  {row.seconds === null ? "" : ` · ${formatSpan(row.seconds)}`}
                  {row.at === null ? "" : ` · ${formatRelative(new Date(row.at).toISOString())}`}
                </span>
              </td>
              <td className="max-w-[18rem] truncate px-2 max-sm:hidden">
                <span className="text-muted-foreground">{row.run.projectName} ›</span>{" "}
                {row.run.experimentName}
              </td>
              <td className="px-2 font-mono text-label text-muted-foreground max-md:hidden">
                {row.attempt ?? "—"}
              </td>
              <td className="px-2 text-right tabular-nums max-sm:hidden">
                {row.seconds === null ? "—" : formatSpan(row.seconds)}
              </td>
              <td className="px-2 text-right tabular-nums text-muted-foreground max-sm:hidden">
                {row.at === null
                  ? "—"
                  : formatRelative(new Date(row.at).toISOString()).replace(/ ago$/, "")}
              </td>
              <td className="px-2 text-muted-foreground max-md:hidden">
                {row.target ? (
                  <span className="inline-flex items-center gap-1">
                    {row.target === "laptop" || row.target === "local" ? (
                      <Laptop aria-hidden className="size-icon-sm" />
                    ) : (
                      <Server aria-hidden className="size-icon-sm" />
                    )}
                    {row.target}
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-2 pr-6 font-mono text-label text-muted-foreground max-lg:hidden">
                {row.run.id}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};
